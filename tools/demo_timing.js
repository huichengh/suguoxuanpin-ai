const fs = require('fs')
const src = fs.readFileSync('frontend/src/components/DemoPlayer.tsx', 'utf8')
const arr = src.slice(src.indexOf('const STEPS'), src.indexOf('/** 中文语音时长估算'))
// 用 `no:` 分割，避免 preAction 里的嵌套对象干扰
const blocks = arr.split(/^    no: /m).slice(1)

const OPTS = [[4.5, 3.5], [5.0, 3.0], [5.5, 2.5], [6.0, 2.0]]

let hdr = '步骤'.padEnd(24) + '字数'.padStart(5)
OPTS.forEach(([c]) => { hdr += (c + '字/s').padStart(12) })
console.log(hdr)

const tot = {}
OPTS.forEach(([c]) => { tot[c] = 0 })

for (const b of blocks) {
  const t = b.match(/title:\s*'([^']+)'/)
  if (!t) { console.log('  (跳过，无 title)'); continue }
  const ni = b.indexOf('narration:')
  const hi = b.indexOf('highlights:')
  if (ni < 0 || hi < 0 || hi < ni) { console.log('  (跳过)', t[1], 'narration:' + ni, 'highlights:' + hi); continue }
  const seg = b.slice(ni, hi)
  const narr = [...seg.matchAll(/'([^']*)'/g)].map((m) => m[1]).join('')
  const cjk = (narr.match(/[一-鿿]/g) || []).length
  const units = cjk + (narr.length - cjk) * 0.5
  let row = ('  ' + t[1]).padEnd(24) + String(narr.length).padStart(5)
  for (const [c, buf] of OPTS) {
    const s = Math.round(Math.min(42, Math.max(10, units / c + buf)))
    tot[c] += s
    row += (s + 's').padStart(12)
  }
  console.log(row)
}

console.log()
for (const [c, buf] of OPTS) {
  const m = Math.floor(tot[c] / 60)
  const s = Math.round(tot[c] % 60)
  console.log(`  ${c}字/s + ${buf}s缓冲 → ${m}分${s}秒 ${tot[c] <= 185 ? '✓ 3分钟内' : '✗ 超出'}`)
}
