/**
 * 极简 CDP 客户端：直接用 Node 内置 http/ws 协议驱动 Edge，不依赖任何第三方包。
 * 用于验证前端页面是否真的完成渲染（而非仅返回 HTML 壳）。
 */
const http = require('http')
const crypto = require('crypto')
const net = require('net')
const { spawn } = require('child_process')
const fs = require('fs')
const path = require('path')

const EDGE = 'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe'
const OUT = process.argv[3] || '.'
const PORT = 9333
const BASE = 'http://127.0.0.1:5174'

const PAGES = [
  { hash: '/abc-shelf', name: '01-abc', title: 'AI经营驾驶舱' },
  { hash: '/compare', name: '02-compare', title: '选品比较中心' },
  { hash: '/category-health', name: '03-health', title: '品类健康诊断' },
  { hash: '/abc-shelf', name: '04-abc', title: 'ABC分类' },
  { hash: '/abc-shelf', name: '05-shelf', title: '货架优化', tab: 'shelf' },
  { hash: '/association', name: '06-association', title: '关联陈列分析' },
  { hash: '/forecast', name: '07-forecast', title: '需求预测' },
  { hash: '/stores', name: '08-stores', title: '千店千面' },
  { hash: '/private-label', name: '09-private-label', title: '自有品牌机会' },
  { hash: '/new-products', name: '10-new-products', title: '新品评估' },
  { hash: '/agent', name: '11-agent', title: 'AI选品助手' },
  { hash: '/data', name: '12-data', title: '数据中心' },
  { hash: '/approvals', name: '13-approvals', title: '审批中心' },
  { hash: '/admin', name: '14-admin', title: '系统管理' },
]

function get(url) {
  return new Promise((res, rej) => {
    http.get(url, (r) => {
      let d = ''
      r.on('data', (c) => (d += c))
      r.on('end', () => res(d))
    }).on('error', rej)
  })
}

/* 极简 WebSocket 客户端（仅需 text frame + masking，服务端不校验客户端 mask） */
class WS {
  constructor(url) {
    const u = new URL(url)
    this.sock = net.connect(Number(u.port), u.hostname)
    this.buf = Buffer.alloc(0)
    this.handlers = {}
    this.ready = new Promise((resolve, reject) => {
      const key = crypto.randomBytes(16).toString('base64')
      this.sock.on('connect', () => {
        this.sock.write(
          `GET ${u.pathname} HTTP/1.1\r\nHost: ${u.host}\r\nUpgrade: websocket\r\n` +
          `Connection: Upgrade\r\nSec-WebSocket-Key: ${key}\r\nSec-WebSocket-Version: 13\r\n\r\n`,
        )
      })
      this.sock.on('data', (d) => {
        this.buf = Buffer.concat([this.buf, d])
        if (!this.upgraded && this.buf.includes(Buffer.from('\r\n\r\n'))) {
          const i = this.buf.indexOf(Buffer.from('\r\n\r\n'))
          this.buf = this.buf.slice(i + 4)
          this.upgraded = true
          resolve()
        }
        this.drain()
      })
      this.sock.on('error', reject)
    })
    this.id = 0
    this.pending = new Map()
  }

  drain() {
    while (this.buf.length >= 2) {
      const len0 = this.buf[1] & 127
      let off = 2
      let len = len0
      if (len0 === 126) { if (this.buf.length < 4) return; len = this.buf.readUInt16BE(2); off = 4 }
      else if (len0 === 127) { if (this.buf.length < 10) return; len = Number(this.buf.readBigUInt64BE(2)); off = 10 }
      if (this.buf.length < off + len) return
      const payload = this.buf.slice(off, off + len).toString('utf8')
      this.buf = this.buf.slice(off + len)
      try {
        const msg = JSON.parse(payload)
        if (msg.id && this.pending.has(msg.id)) {
          const { resolve, reject } = this.pending.get(msg.id)
          this.pending.delete(msg.id)
          msg.error ? reject(new Error(JSON.stringify(msg.error))) : resolve(msg.result)
        } else if (msg.method) {
          ;(this.handlers[msg.method] || []).forEach((h) => h(msg.params))
        }
      } catch { /* 忽略非 JSON 帧 */ }
    }
  }

  on(evt, fn) { (this.handlers[evt] ||= []).push(fn) }

  send(method, params = {}) {
    const id = ++this.id
    const body = Buffer.from(JSON.stringify({ id, method, params }), 'utf8')
    const mask = crypto.randomBytes(4)
    const masked = Buffer.from(body.map((b, i) => b ^ mask[i % 4]))
    let header
    if (body.length < 126) { header = Buffer.from([0x81, 0x80 | body.length]) }
    else if (body.length < 65536) {
      header = Buffer.alloc(4); header[0] = 0x81; header[1] = 0x80 | 126; header.writeUInt16BE(body.length, 2)
    } else {
      header = Buffer.alloc(10); header[0] = 0x81; header[1] = 0x80 | 127; header.writeBigUInt64BE(BigInt(body.length), 2)
    }
    this.sock.write(Buffer.concat([header, mask, masked]))
    return new Promise((resolve, reject) => this.pending.set(id, { resolve, reject }))
  }
}

const sleep = (ms) => new Promise((r) => setTimeout(r, ms))

async function main() {
  const token = process.argv[2]
  const profile = path.join(require('os').tmpdir(), 'edge_cdp_profile')
  fs.rmSync(profile, { recursive: true, force: true })

  const edge = spawn(EDGE, [
    '--headless=new', '--disable-gpu', '--no-sandbox', '--hide-scrollbars',
    `--remote-debugging-port=${PORT}`, `--user-data-dir=${profile}`,
    '--window-size=1920,1080', '--no-first-run', '--disable-extensions',
    'about:blank',
  ], { stdio: 'ignore' })

  // 等待调试端口
  let list = null
  for (let i = 0; i < 40; i++) {
    await sleep(500)
    try { list = JSON.parse(await get(`http://127.0.0.1:${PORT}/json/list`)); if (list.length) break } catch {}
  }
  if (!list || !list.length) { edge.kill(); throw new Error('Edge 调试端口未就绪') }

  const target = list.find((t) => t.type === 'page') || list[0]
  const ws = new WS(target.webSocketDebuggerUrl)
  await ws.ready

  const errors = []
  await ws.send('Runtime.enable')
  await ws.send('Page.enable')
  await ws.send('Log.enable')
  ws.on('Runtime.exceptionThrown', (p) =>
    errors.push('EXCEPTION: ' + (p.exceptionDetails?.exception?.description || p.exceptionDetails?.text)))
  ws.on('Log.entryAdded', (p) => { if (p.entry.level === 'error') errors.push('LOG: ' + p.entry.text) })
  ws.on('Runtime.consoleAPICalled', (p) => {
    if (p.type === 'error') errors.push('CONSOLE: ' + p.args.map((a) => a.value || a.description).join(' '))
  })

  const evalJs = async (expr) => {
    const r = await ws.send('Runtime.evaluate', { expression: expr, returnByValue: true, awaitPromise: true })
    return r.result?.value
  }

  const shot = async (file) => {
    const r = await ws.send('Page.captureScreenshot', { format: 'png' })
    fs.writeFileSync(path.join(OUT, file), Buffer.from(r.data, 'base64'))
  }

  const goto = async (hash, wait = 2800) => {
    await evalJs(`location.hash = '${hash}'`)
    await sleep(wait)
  }

  // 登录页
  await evalJs(`location.href = '${BASE}/#/login'`)
  await sleep(3000)
  await shot('00-login.png')
  console.log('✓ 00-login.png')

  // 注入 token
  await evalJs(`
    localStorage.setItem('suguo_token', ${JSON.stringify(token)});
    localStorage.setItem('suguo_user', JSON.stringify({
      id:1, username:'admin', full_name:'系统管理员',
      role:'管理员', role_code:'admin', permissions:['*'], store:null }));
    'ok'
  `)

  for (const p of PAGES) {
    await goto(p.hash)
    await sleep(900)
    // 需要切 Tab 的页面
    if (p.tab) {
      await evalJs(`
        (() => {
          const btns = [...document.querySelectorAll('button')];
          const t = btns.find(b => b.textContent.trim() === '${p.tab === 'shelf' ? '货架空间优化' : 'ABC 分类'}');
          if (t) t.click();
        })()
      `)
      await sleep(2600)
    }
    const txt = await evalJs('document.body.innerText.replace(/\\n+/g," ").slice(0,110)')
    const canvasCount = await evalJs('document.querySelectorAll("canvas").length')
    const len = await evalJs('document.body.innerText.length')
    await shot(`${p.name}.png`)
    console.log(`✓ ${p.name}.png | ${p.title} | 文本${len}字 | canvas×${canvasCount}`)
    console.log(`   ${txt}`)
  }

  edge.kill()

  if (errors.length) {
    console.log('\n--- 运行时错误 ---')
    ;[...new Set(errors)].slice(0, 20).forEach((e) => console.log('  ' + e.slice(0, 180)))
  } else {
    console.log('\n✓ 无运行时错误')
  }
}

main().catch((e) => { console.error('FAILED:', e.message); process.exit(1) })
