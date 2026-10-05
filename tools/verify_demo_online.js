/**
 * 验证线上自动演示：触发面板 → 开始 → 读取时长与步进情况。
 *
 * 用法：node verify_demo_online.js [等待秒数]
 */
const { spawn } = require('child_process')
const http = require('http'); const https = require('https')
const crypto = require('crypto'); const net = require('net')
const fs = require('fs'); const path = require('path'); const os = require('os')

const SITE = 'https://suguo-assortment-ai.app.workbuddy.host'
const EDGE = 'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe'
const waitSec = parseInt(process.argv[2] || '0', 10)
const PORT = 9700 + Math.floor(Math.random() * 200)
const sleep = (ms) => new Promise((r) => setTimeout(r, ms))

function postJson (url, obj) {
  return new Promise((res, rej) => {
    const u = new URL(url)
    const lib = u.protocol === 'https:' ? https : http
    const data = Buffer.from(JSON.stringify(obj))
    const req = lib.request({
      hostname: u.hostname, port: u.port || 443, path: u.pathname, method: 'POST',
      headers: { 'Content-Type': 'application/json', 'Content-Length': data.length },
    }, (r) => {
      let d = ''; r.on('data', (c) => (d += c)); r.on('end', () => res(d))
    })
    req.on('error', rej); req.write(data); req.end()
  })
}

const getLocal = (u) => new Promise((res, rej) => {
  http.get(u, (r) => { let d = ''; r.on('data', (c) => (d += c)); r.on('end', () => res(d)) }).on('error', rej)
})

class WS {
  constructor (url) {
    const u = new URL(url)
    this.sock = net.connect(+u.port, u.hostname)
    this.buf = Buffer.alloc(0); this.id = 0; this.p = new Map()
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
      const s = this.buf.slice(off, off + len).toString('utf8')
      this.buf = this.buf.slice(off + len)
      try {
        const m = JSON.parse(s)
        if (m.id && this.p.has(m.id)) {
          const { resolve, reject } = this.p.get(m.id); this.p.delete(m.id)
          m.error ? reject(new Error(JSON.stringify(m.error))) : resolve(m.result)
        }
      } catch (e) { /* 忽略 */ }
    }
  }

  send (method, params = {}) {
    const id = ++this.id
    const body = Buffer.from(JSON.stringify({ id, method, params }), 'utf8')
    const mask = crypto.randomBytes(4)
    const masked = Buffer.from(body.map((b, i) => b ^ mask[i % 4]))
    let h
    if (body.length < 126) h = Buffer.from([0x81, 0x80 | body.length])
    else if (body.length < 65536) { h = Buffer.alloc(4); h[0] = 0x81; h[1] = 0x80 | 126; h.writeUInt16BE(body.length, 2) }
    else { h = Buffer.alloc(10); h[0] = 0x81; h[1] = 0x80 | 127; h.writeBigUInt64BE(BigInt(body.length), 2) }
    this.sock.write(Buffer.concat([h, mask, masked]))
    return new Promise((resolve, reject) => this.p.set(id, { resolve, reject }))
  }
}

async function main () {
  const raw = await postJson(SITE + '/api/auth/login', { username: 'admin', password: 'admin123' })
  const token = JSON.parse(raw).access_token
  console.log('登录成功')

  const prof = path.join(os.tmpdir(), `edge_vdemo_${PORT}`)
  fs.rmSync(prof, { recursive: true, force: true })
  const edge = spawn(EDGE, ['--headless=new', '--disable-gpu', '--no-sandbox', '--hide-scrollbars',
    `--remote-debugging-port=${PORT}`, `--user-data-dir=${prof}`,
    '--window-size=1920,1080', '--no-first-run', 'about:blank'], { stdio: 'ignore' })

  let list = null
  for (let i = 0; i < 40; i++) {
    await sleep(400)
    try { list = JSON.parse(await getLocal(`http://127.0.0.1:${PORT}/json/list`)); if (list.length) break } catch (e) { /* 未就绪 */ }
  }
  if (!list?.length) { edge.kill(); throw new Error('调试端口未就绪') }

  const ws = new WS((list.find((t) => t.type === 'page') || list[0]).webSocketDebuggerUrl)
  await ws.ready
  await ws.send('Page.enable')
  const ev = async (e) => (await ws.send('Runtime.evaluate',
    { expression: e, returnByValue: true, awaitPromise: true })).result?.value

  await ev(`location.href='${SITE}/#/login'`); await sleep(4500)
  await ev(`localStorage.setItem('suguo_token',${JSON.stringify(token)});
            localStorage.setItem('suguo_user','{"id":1,"username":"admin","role":"管理员","role_code":"admin","permissions":["*"]}')`)
  await ev(`location.hash='#/dashboard'`); await sleep(500)
  await ev('location.reload()'); await sleep(5000)

  await ev(`window.dispatchEvent(new CustomEvent('suguo:open-demo'))`)
  await sleep(1500)
  await ev(`(()=>{const bs=[...document.querySelectorAll('button')];
    const t=bs.find(b=>b.textContent.includes('开始演示'));
    if(t){t.click();return 'clicked'}return 'not found'})()`)
  await sleep(1800)

  const probe = `(()=>{
    const txt=document.body.innerText;
    const g=(re)=>{const m=txt.match(re);return m?m[0]:null};
    return {
      head:g(/共 \\d+ 步 · 约 \\d+ 分 \\d+ 秒/),
      timer:g(/\\d+s \\/ \\d+s/),
      step:g(/第 \\d+ 步 \\/ 共 \\d+ 步/),
      hasVoiceSwitch: txt.includes('语音解说'),
      mentionsVoice: txt.includes('语音'),
      perStep:(txt.match(/\\d+s/g)||[]).slice(0,10),
      len:txt.length
    };
  })()`
  console.log('开始时:', JSON.stringify(await ev(probe), null, 2))

  if (waitSec > 0) {
    await sleep(waitSec * 1000)
    console.log(`${waitSec}s 后:`, JSON.stringify(await ev(probe), null, 2))
  }

  const shot = await ws.send('Page.captureScreenshot', { format: 'png' })
  const out = process.argv[3] || '.'
  const name = `online-demo-${waitSec}s.png`
  fs.writeFileSync(path.join(out, name), Buffer.from(shot.data, 'base64'))
  console.log(`✓ ${name}`)
  edge.kill()
}

main().catch((e) => { console.error('FAILED:', e.message); process.exit(1) })
