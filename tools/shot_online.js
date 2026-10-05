/**
 * 线上站点截图工具（零依赖 CDP 客户端）。
 *
 * 与 tools/shot_one.js 的差别：地址改为线上域名，登录改为调用线上登录接口取令牌，
 * 令牌同时写入 localStorage（前端会自动带上 X-Auth-Token 头）。
 *
 * 用法：node shot_online.js <路由hash> <输出目录>
 *   例：node shot_online.js /dashboard C:/out
 */
const { spawn } = require('child_process')
const http = require('http'); const https = require('https'); const crypto = require('crypto'); const net = require('net')
const fs = require('fs'); const path = require('path'); const os = require('os')

const SITE = 'https://suguo-assortment-ai.app.workbuddy.host'
const EDGE = 'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe'
const rawArg = process.argv[2] || '/dashboard'
// Git Bash 会把 /dashboard 这类参数转成 Windows 路径，这里还原
const hash = rawArg.includes('\\') ? '/' + rawArg.split(/[\\/]/).filter(Boolean).pop() : rawArg
const outDir = process.argv[3] || '.'
const PORT = 9800 + Math.floor(Math.random() * 150)

const sleep = (ms) => new Promise((r) => setTimeout(r, ms))

function httpReq (url, opts = {}, body = null) {
  const u = new URL(url)
  const lib = u.protocol === 'https:' ? https : http
  return new Promise((resolve, reject) => {
    const req = lib.request({
      hostname: u.hostname, port: u.port || (u.protocol === 'https:' ? 443 : 80),
      path: u.pathname + u.search, method: opts.method || 'GET', headers: opts.headers || {},
    }, (r) => {
      let d = ''
      r.on('data', (c) => (d += c))
      r.on('end', () => resolve(d))
    })
    req.on('error', reject)
    if (body) req.write(body)
    req.end()
  })
}

/** 极简 WebSocket 客户端，够用即可 */
class WS {
  constructor (url) {
    const u = new URL(url)
    this.sock = net.connect(+u.port, u.hostname)
    this.buf = Buffer.alloc(0); this.h = {}; this.id = 0; this.p = new Map()
    this.ready = new Promise((rs, rj) => {
      const k = crypto.randomBytes(16).toString('base64')
      this.sock.on('connect', () => this.sock.write(
        `GET ${u.pathname} HTTP/1.1\r\nHost: ${u.host}\r\nUpgrade: websocket\r\nConnection: Upgrade\r\nSec-WebSocket-Key: ${k}\r\nSec-WebSocket-Version: 13\r\n\r\n`))
      this.sock.on('data', (d) => {
        this.buf = Buffer.concat([this.buf, d])
        if (!this.up && this.buf.includes(Buffer.from('\r\n\r\n'))) {
          this.buf = this.buf.slice(this.buf.indexOf(Buffer.from('\r\n\r\n')) + 4)
          this.up = true; rs()
        }
        this.drain()
      })
      this.sock.on('error', rj)
    })
  }

  drain () {
    while (this.buf.length >= 2) {
      const l0 = this.buf[1] & 127
      let off = 2; let len = l0
      if (l0 === 126) { if (this.buf.length < 4) return; len = this.buf.readUInt16BE(2); off = 4 }
      else if (l0 === 127) { if (this.buf.length < 10) return; len = Number(this.buf.readBigUInt64BE(2)); off = 10 }
      if (this.buf.length < off + len) return
      const payload = this.buf.slice(off, off + len).toString('utf8')
      this.buf = this.buf.slice(off + len)
      try {
        const m = JSON.parse(payload)
        if (m.id && this.p.has(m.id)) {
          const { resolve, reject } = this.p.get(m.id)
          this.p.delete(m.id)
          m.error ? reject(new Error(JSON.stringify(m.error))) : resolve(m.result)
        }
      } catch (e) { /* 非 JSON 帧忽略 */ }
    }
  }

  send (method, params = {}) {
    const id = ++this.id
    const body = Buffer.from(JSON.stringify({ id, method, params }), 'utf8')
    const mask = crypto.randomBytes(4)
    const masked = Buffer.from(body.map((b, i) => b ^ mask[i % 4]))
    let head
    if (body.length < 126) head = Buffer.from([0x81, 0x80 | body.length])
    else if (body.length < 65536) { head = Buffer.alloc(4); head[0] = 0x81; head[1] = 0x80 | 126; head.writeUInt16BE(body.length, 2) }
    else { head = Buffer.alloc(10); head[0] = 0x81; head[1] = 0x80 | 127; head.writeBigUInt64BE(BigInt(body.length), 2) }
    this.sock.write(Buffer.concat([head, mask, masked]))
    return new Promise((resolve, reject) => this.p.set(id, { resolve, reject }))
  }
}

async function main () {
  // 1) 线上登录取令牌
  const raw = await httpReq(SITE + '/api/auth/login',
    { method: 'POST', headers: { 'Content-Type': 'application/json' } },
    JSON.stringify({ username: 'admin', password: 'admin123' }))
  const token = JSON.parse(raw).access_token
  console.log('登录成功，令牌长度', token.length)

  // 2) 起浏览器
  const prof = path.join(os.tmpdir(), `edge_online_${PORT}`)
  fs.rmSync(prof, { recursive: true, force: true })
  const edge = spawn(EDGE, ['--headless=new', '--disable-gpu', '--no-sandbox', '--hide-scrollbars',
    `--remote-debugging-port=${PORT}`, `--user-data-dir=${prof}`,
    '--window-size=1920,1080', '--no-first-run', 'about:blank'], { stdio: 'ignore' })

  let list = null
  for (let i = 0; i < 40; i++) {
    await sleep(400)
    try {
      list = JSON.parse(await new Promise((res, rej) => {
        http.get(`http://127.0.0.1:${PORT}/json/list`, (r) => {
          let d = ''; r.on('data', (c) => (d += c)); r.on('end', () => res(d))
        }).on('error', rej)
      }))
      if (list.length) break
    } catch (e) { /* 未就绪 */ }
  }
  if (!list || !list.length) { edge.kill(); throw new Error('调试端口未就绪') }

  const target = list.find((t) => t.type === 'page') || list[0]
  const ws = new WS(target.webSocketDebuggerUrl)
  await ws.ready
  await ws.send('Page.enable')

  const ev = async (e) => (await ws.send('Runtime.evaluate',
    { expression: e, returnByValue: true, awaitPromise: true })).result?.value

  // 3) 打开站点、写入登录态、跳转目标路由
  await ev(`location.href='${SITE}/#/login'`); await sleep(4000)
  await ev(`localStorage.setItem('suguo_token',${JSON.stringify(token)});
            localStorage.setItem('suguo_user','{"id":1,"username":"admin","role":"管理员","role_code":"admin","permissions":["*"]}')`)
  await ev(`location.hash='#${hash}'`)
  await sleep(600)
  await ev('location.reload()')
  await sleep(5000)

  // 4) 截图
  const textLen = await ev('document.body.innerText.length')
  const canvas = await ev('document.querySelectorAll("canvas").length')
  const shot = await ws.send('Page.captureScreenshot', { format: 'png' })
  const name = 'online-' + hash.replace(/^\//, '').replace(/\//g, '-') + '.png'
  fs.writeFileSync(path.join(outDir, name), Buffer.from(shot.data, 'base64'))
  console.log(`✓ ${name} | 正文 ${textLen} 字 | canvas×${canvas}`)
  edge.kill()
}

main().catch((e) => { console.error('FAILED:', e.message); process.exit(1) })
