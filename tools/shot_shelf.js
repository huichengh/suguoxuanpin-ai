/** 快速截图：只截指定页面，避免超时 */
const { spawn } = require('child_process')
const http = require('http')
const crypto = require('crypto')
const net = require('net')
const fs = require('fs')
const path = require('path')
const os = require('os')

const EDGE = 'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe'
const BASE = 'http://127.0.0.1:5174'
const PORT = 9334 + Math.floor(Math.random() * 100)

const token = process.argv[2]
const outDir = process.argv[3]
const only = process.argv[4]   // 逗号分隔的 hash 列表

const TARGETS = (only
  ? only.split(',')
  : ['/', '/compare', '/category-health', '/abc-shelf', '/association', '/forecast',
     '/agent', '/data', '/approvals', '/admin']
).map((h) => ({
  hash: h,
  // 去掉斜杠做文件名，避免 Windows 路径转义问题
  name: h === '/' ? '00-home' : h.replace(/^\//, '').replace(/\//g, '-'),
}))

function get(url) {
  return new Promise((res, rej) => {
    http.get(url, (r) => { let d = ''; r.on('data', (c) => (d += c)); r.on('end', () => res(d)) }).on('error', rej)
  })
}

class WS {
  constructor(url) {
    const u = new URL(url)
    this.sock = net.connect(Number(u.port), u.hostname)
    this.buf = Buffer.alloc(0); this.handlers = {}; this.id = 0; this.pending = new Map()
    this.ready = new Promise((resolve, reject) => {
      const key = crypto.randomBytes(16).toString('base64')
      this.sock.on('connect', () => this.sock.write(
        `GET ${u.pathname} HTTP/1.1\r\nHost: ${u.host}\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n` +
        `Sec-WebSocket-Key: ${key}\r\nSec-WebSocket-Version: 13\r\n\r\n`))
      this.sock.on('data', (d) => {
        this.buf = Buffer.concat([this.buf, d])
        if (!this.up && this.buf.includes(Buffer.from('\r\n\r\n'))) {
          this.buf = this.buf.slice(this.buf.indexOf(Buffer.from('\r\n\r\n')) + 4)
          this.up = true; resolve()
        }
        this.drain()
      })
      this.sock.on('error', reject)
    })
  }
  drain() {
    while (this.buf.length >= 2) {
      const l0 = this.buf[1] & 127; let off = 2, len = l0
      if (l0 === 126) { if (this.buf.length < 4) return; len = this.buf.readUInt16BE(2); off = 4 }
      else if (l0 === 127) { if (this.buf.length < 10) return; len = Number(this.buf.readBigUInt64BE(2)); off = 10 }
      if (this.buf.length < off + len) return
      const payload = this.buf.slice(off, off + len).toString('utf8')
      this.buf = this.buf.slice(off + len)
      try {
        const m = JSON.parse(payload)
        if (m.id && this.pending.has(m.id)) {
          const { resolve, reject } = this.pending.get(m.id); this.pending.delete(m.id)
          m.error ? reject(new Error(JSON.stringify(m.error))) : resolve(m.result)
        } else if (m.method) (this.handlers[m.method] || []).forEach((h) => h(m.params))
      } catch {}
    }
  }
  on(e, f) { (this.handlers[e] ||= []).push(f) }
  send(method, params = {}) {
    const id = ++this.id
    const body = Buffer.from(JSON.stringify({ id, method, params }), 'utf8')
    const mask = crypto.randomBytes(4)
    const masked = Buffer.from(body.map((b, i) => b ^ mask[i % 4]))
    let h
    if (body.length < 126) h = Buffer.from([0x81, 0x80 | body.length])
    else if (body.length < 65536) { h = Buffer.alloc(4); h[0] = 0x81; h[1] = 0x80 | 126; h.writeUInt16BE(body.length, 2) }
    else { h = Buffer.alloc(10); h[0] = 0x81; h[1] = 0x80 | 127; h.writeBigUInt64BE(BigInt(body.length), 2) }
    this.sock.write(Buffer.concat([h, mask, masked]))
    return new Promise((res, rej) => this.pending.set(id, { resolve: res, reject: rej }))
  }
}

const sleep = (ms) => new Promise((r) => setTimeout(r, ms))

async function main() {
  const profile = path.join(os.tmpdir(), `edge_q${PORT}`)
  fs.rmSync(profile, { recursive: true, force: true })
  const edge = spawn(EDGE, [
    '--headless=new', '--disable-gpu', '--no-sandbox', '--hide-scrollbars',
    `--remote-debugging-port=${PORT}`, `--user-data-dir=${profile}`,
    '--window-size=1920,1080', '--no-first-run', 'about:blank',
  ], { stdio: 'ignore' })

  let list = null
  for (let i = 0; i < 30; i++) {
    await sleep(400)
    try { list = JSON.parse(await get(`http://127.0.0.1:${PORT}/json/list`)); if (list.length) break } catch {}
  }
  if (!list?.length) { edge.kill(); throw new Error('调试端口未就绪') }

  const ws = new WS((list.find((t) => t.type === 'page') || list[0]).webSocketDebuggerUrl)
  await ws.ready
  await ws.send('Page.enable')
  const errs = []
  ws.on('Runtime.exceptionThrown', (p) =>
    errs.push('EXC: ' + (p.exceptionDetails?.exception?.description || '').slice(0, 150)))

  const ev = async (e) => (await ws.send('Runtime.evaluate', { expression: e, returnByValue: true, awaitPromise: true })).result?.value

  await ev(`location.href='${BASE}/#/login'`)
  await sleep(2500)
  await ev(`localStorage.setItem('suguo_token',${JSON.stringify(token)});
            localStorage.setItem('suguo_user','{"id":1,"username":"admin","full_name":"系统管理员","role":"管理员","role_code":"admin","permissions":["*"]}')`)

  for (const t of TARGETS) {
    await ev(`location.hash='${t.hash}'`)
    await sleep(2400); await ev('[...document.querySelectorAll(\'button\')].find(b=>b.textContent.trim()===\'货架空间优化\')?.click()'); await sleep(2000)
    await ev('location.reload()')
    await sleep(2600)
    const len = await ev('document.body.innerText.length')
    const cv = await ev('document.querySelectorAll("canvas").length')
    const r = await ws.send('Page.captureScreenshot', { format: 'png' })
    fs.writeFileSync(path.join(outDir, `${t.name}.png`), Buffer.from(r.data, 'base64'))
    console.log(`✓ ${t.name}.png | ${t.hash} | ${len}字 | canvas×${cv}`)
  }

  edge.kill()
  if (errs.length) { console.log('\n错误:'); [...new Set(errs)].slice(0, 8).forEach((e) => console.log('  ' + e)) }
  else console.log('\n无运行时错误')
}
main().catch((e) => { console.error('FAILED:', e.message); process.exit(1) })
