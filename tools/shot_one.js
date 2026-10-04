const { spawn } = require('child_process')
const http = require('http'); const crypto = require('crypto'); const net = require('net')
const fs = require('fs'); const path = require('path'); const os = require('os')
const EDGE = 'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe'
const token = process.argv[2], outDir = process.argv[3], hash = process.argv[4]
const clickText = process.argv[5] || ''
const PORT = 9500 + Math.floor(Math.random() * 300)
const get = (u) => new Promise((res, rej) => { http.get(u, (r) => { let d=''; r.on('data',c=>d+=c); r.on('end',()=>res(d)) }).on('error', rej) })
class WS {
  constructor(url){ const u=new URL(url); this.sock=net.connect(+u.port,u.hostname); this.buf=Buffer.alloc(0); this.h={}; this.id=0; this.p=new Map()
    this.ready=new Promise((rs,rj)=>{ const k=crypto.randomBytes(16).toString('base64')
      this.sock.on('connect',()=>this.sock.write(`GET ${u.pathname} HTTP/1.1\r\nHost: ${u.host}\r\nUpgrade: websocket\r\nConnection: Upgrade\r\nSec-WebSocket-Key: ${k}\r\nSec-WebSocket-Version: 13\r\n\r\n`))
      this.sock.on('data',(d)=>{ this.buf=Buffer.concat([this.buf,d]); if(!this.up&&this.buf.includes(Buffer.from('\r\n\r\n'))){this.buf=this.buf.slice(this.buf.indexOf(Buffer.from('\r\n\r\n'))+4);this.up=true;rs()} this.d()})
      this.sock.on('error',rj) }) }
  d(){ while(this.buf.length>=2){ const l0=this.buf[1]&127; let o=2,l=l0
    if(l0===126){if(this.buf.length<4)return;l=this.buf.readUInt16BE(2);o=4} else if(l0===127){if(this.buf.length<10)return;l=Number(this.buf.readBigUInt64BE(2));o=10}
    if(this.buf.length<o+l)return; const p=this.buf.slice(o,o+l).toString('utf8'); this.buf=this.buf.slice(o+l)
    try{ const m=JSON.parse(p); if(m.id&&this.p.has(m.id)){const{resolve,reject}=this.p.get(m.id);this.p.delete(m.id);m.error?reject(new Error(JSON.stringify(m.error))):resolve(m.result)} }catch{} } }
  send(method,params={}){ const id=++this.id; const body=Buffer.from(JSON.stringify({id,method,params}),'utf8')
    const mask=crypto.randomBytes(4); const mk=Buffer.from(body.map((b,i)=>b^mask[i%4])); let h
    if(body.length<126)h=Buffer.from([0x81,0x80|body.length]); else if(body.length<65536){h=Buffer.alloc(4);h[0]=0x81;h[1]=0x80|126;h.writeUInt16BE(body.length,2)} else{h=Buffer.alloc(10);h[0]=0x81;h[1]=0x80|127;h.writeBigUInt64BE(BigInt(body.length),2)}
    this.sock.write(Buffer.concat([h,mask,mk])); return new Promise((res,rej)=>this.p.set(id,{resolve:res,reject:rej})) }
}
const sleep=(ms)=>new Promise(r=>setTimeout(r,ms))
async function main(){
  const prof=path.join(os.tmpdir(),`edge_o${PORT}`); fs.rmSync(prof,{recursive:true,force:true})
  const edge=spawn(EDGE,['--headless=new','--disable-gpu','--no-sandbox','--hide-scrollbars',`--remote-debugging-port=${PORT}`,`--user-data-dir=${prof}`,'--window-size=1920,1080','--no-first-run','about:blank'],{stdio:'ignore'})
  let list=null
  for(let i=0;i<30;i++){await sleep(400);try{list=JSON.parse(await get(`http://127.0.0.1:${PORT}/json/list`));if(list.length)break}catch{}}
  if(!list?.length){edge.kill();throw new Error('端口未就绪')}
  const ws=new WS((list.find(t=>t.type==='page')||list[0]).webSocketDebuggerUrl); await ws.ready
  await ws.send('Page.enable')
  const ev=async(e)=>(await ws.send('Runtime.evaluate',{expression:e,returnByValue:true,awaitPromise:true})).result?.value
  await ev(`location.href='http://127.0.0.1:5174/#/login'`); await sleep(2500)
  await ev(`localStorage.setItem('suguo_token',${JSON.stringify(token)});localStorage.setItem('suguo_user','{"id":1,"username":"admin","role":"管理员","role_code":"admin","permissions":["*"]}')`)
  await ev(`location.hash='#${hash}'`); await sleep(800)
  // HashRouter 需要整页刷新才能可靠切换路由
  await ev('location.reload()'); await sleep(3400)
  if(clickText){
    const r=await ev(`(()=>{const bs=[...document.querySelectorAll('button')];const t=bs.find(b=>b.textContent.trim().startsWith('${clickText}'));if(t){t.click();return 'clicked'}return 'not found: '+bs.map(b=>b.textContent.trim()).slice(0,8).join('|')})()`)
    console.log('click:',r); await sleep(3000)
  }
  const len=await ev('document.body.innerText.length'); const cv=await ev('document.querySelectorAll("canvas").length')
  const s=await ws.send('Page.captureScreenshot',{format:'png'})
  const name=hash.replace(/^\//,'').replace(/\//g,'-')+'.png'
  fs.writeFileSync(path.join(outDir,name),Buffer.from(s.data,'base64'))
  console.log(`✓ ${name} | ${len}字 | canvas×${cv}`)
  edge.kill()
}
main().catch(e=>{console.error('FAILED:',e.message);process.exit(1)})
