import { useCallback, useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Alert, DemoBadge } from '../components/ui'
import { api, fmt } from '../services/api'

/** 演示前的预置动作：在进入某一步时先设置好页面状态 */
export interface DemoAction {
  /** 目标路径 */
  path: string
  /** localStorage 标记，页面读取后执行预置 */
  key: string
  payload: any
}

/**
 * 3 分钟自动演示
 *
 * 8 步走完「数据 → 算法 → AI → 管理决策 → 人机协同」完整闭环。
 * 每步自动跳转 + 解说字幕 + 语音播报，评委无需操作。
 * 总时长约 165 秒，控制在 3 分钟内。
 */

interface Step {
  no: number
  title: string
  subtitle: string
  path: string
  /** 解说词（同时作为字幕与语音播报内容） */
  narration: string
  /** 这一步要展示的数据亮点 */
  highlights: string[]
  /** 演讲提示：这一刻要讲什么 */
  cue: string
  /** 进入该步前要预置的页面状态 */
  preAction?: DemoAction
}

const STEPS: Step[] = [
  {
    no: 1,
    title: '选择门店',
    subtitle: '华润苏果（南京江宁黄金海岸广场店）',
    path: '/stores',
    narration:
      '演示从门店画像开始。当前门店是华润苏果南京江宁黄金海岸广场店，社区购物中心店，营业面积 3200 平米。' +
      '注意这里所有人口与 POI 字段都显示待接入——平台不会编造不存在的数据。',
    highlights: ['社区门店定位', '画像数据待接入', '不编造人口数据'],
    cue: '强调"数据不足时平台明确说不足"，这是数据治理能力的体现',
  },
  {
    no: 2,
    title: '7 大品类健康诊断',
    subtitle: '四维评分模型，区分附件参考与系统重算',
    path: '/category-health',
    narration:
      '品类健康度用四个维度打分：销量贡献 30%、毛利贡献 30%、库存周转 20%、坪效 20%。' +
      '这里有个关键细节：库存周转天数越低越好，所以做了逆向标准化。' +
      '结果是生鲜蔬果 100 分排第一，纺织服装 15.2 分排最后——周转 87 天、坪效只有 270。' +
      '页面下方还展示了系统重算与附件参考结果的差异，平台不修改任何一方。',
    highlights: ['生鲜蔬果 100 分 · 优秀', '纺织服装 15.2 分 · 需重点优化', '周转天数逆向标准化'],
    cue: '重点讲逆向标准化这个技术细节，以及双数据来源的治理设计',
  },
  {
    no: 3,
    title: '选品比较中心',
    subtitle: '2-6 个对象多维加权比较，权重可实时调整',
    path: '/compare',
    narration:
      '选品比较中心支持三种模式：品类比较、小类比较、SKU 比较。' +
      '权重可以实时调整，调整后立即重算。' +
      '小类层因为缺少毛利和周转数据，模型自动降级为两维——平台不做数据摊派。',
    highlights: ['三种比较模式', '权重实时可调', '缺数据自动降级为两维'],
    cue: '如果时间紧，这一步可以只讲 10 秒，重点在下一步的实际操作',
    preAction: {
      path: '/compare',
      key: 'suguo_demo_preset',
      payload: { mode: 'category' },
    },
  },
  {
    no: 4,
    title: '小类比较实战',
    subtitle: '鸡蛋、牛奶、垃圾袋、豆腐、拖把 五选一',
    path: '/compare',
    narration:
      '现在做一次真实的小类比较。选中鸡蛋、牛奶、垃圾袋、豆腐、拖把五个商品。' +
      '结果显示鸡蛋 100 分排名第一——销量 2018 件，是拖把的 3 倍以上。' +
      '豆腐 0 分排名末位，建议退出。' +
      '每个结论都附带数据依据、最大风险，以及什么情况下结论会反转。',
    highlights: ['鸡蛋 100 分 · 销售冠军', '豆腐 0 分 · 建议退出', '每条结论可解释、可反驳'],
    cue: '这是本次升级的核心亮点，务必现场演示并指出排名差距',
    preAction: {
      path: '/compare',
      key: 'suguo_demo_preset',
      payload: { mode: 'subcategory', names: ['鸡蛋', '牛奶', '垃圾袋', '豆腐', '拖把'], autoRun: true },
    },
  },  {
    no: 5,
    title: '关联陈列分析',
    subtitle: 'Apriori 实时重算 vs 附件参考结果',
    path: '/association',
    narration:
      '关联陈列基于 5000 笔交易篮、70 个商品项实时计算。' +
      '购物篮按交易号加商品名称构建，因为演示数据里商品编码高度离散。' +
      '这里要特别注意：附件预置了 20 条规则，其中只有 11 条通过当前阈值，9 条未通过。' +
      '平台把两份结果分开存放、分别标注来源，未通过的附件规则也原样保留不删不改。',
    highlights: ['5000 笔交易篮 · 70 个商品', '附件 20 条中仅 11 条达标', '双来源分开标注'],
    cue: '这是最能体现数据治理能力的一页，务必讲清"为什么不删附件数据"',
  },
  {
    no: 6,
    title: '需求预测',
    subtitle: '历史实线 + 预测虚线 + 置信区间带',
    path: '/forecast',
    narration:
      '需求预测用 12 期历史加 4 期预测。' +
      '历史是实线，预测是虚线，中间还给出了置信区间带。' +
      '注意标签——这是模拟预测结果，平台不会为它标注任何预测精度。' +
      '点击重跑按钮可以用平台自己的移动平均模型实际算一遍，结论会不一样，这个差异本身就是诚实的表现。',
    highlights: ['12 期历史 + 4 期预测', '模拟结果如实标注', '可重跑真实模型对比'],
    cue: '强调平台区分"附件模拟值"和"平台实算值"，不混为一谈',
  },
  {
    no: 7,
    title: 'AI 生成综合选品方案',
    subtitle: '五分组输出，每项都有多维数据依据',
    path: '/agent',
    narration:
      '现在让 AI 生成综合选品方案。' +
      '输出分成五组：优先扩充、建议保持、重点观察、建议精简、建议退出。' +
      '每一项都必须给出多维数据依据——健康度、销量贡献、毛利贡献、周转、坪效、缺货、需求趋势。' +
      '只看一个健康分是不给出结论的。' +
      '回答还严格按六个段落组织：结论、关键数据依据、分析、建议、风险限制、决策状态。',
    highlights: ['五分组方案', '每项 ≥4 维数据依据', '标准六段回答模板'],
    cue: '让 AI 现场回答一个真实问题，比看静态页面更有说服力',
    preAction: {
      path: '/agent',
      key: 'suguo_demo_preset',
      payload: { autoAsk: '生成综合选品方案' },
    },
  },
  {
    no: 8,
    title: '人机协同审批',
    subtitle: 'Level 3 建议必须人工审批，AI 不执行',
    path: '/approvals',
    narration:
      '最后是人机协同。AI 建议分三级：信息提示、经营建议、高影响建议。' +
      '像 SKU 退出、大规模精简、供应商调整这类高影响操作，必须走人工审批。' +
      'AI 不会自动下采购单、不会改价格、不会删商品，只能形成待审批建议。' +
      '每条审批都记录了申请人、审批人、意见、时间和数据依据，可追溯。',
    highlights: ['三级审批机制', 'Level 3 强制人工审批', '全流程可追溯'],
    cue: '结尾停在这一页，强调"AI 辅助决策、人工最终确认"的核心定位',
  },
]

/**
 * 演示时长完全由解说词决定：
 *   停留秒数 = 解说词朗读时间 + 缓冲
 * 中文 TTS 在 rate=1.05 下约每秒 5.5 字；语音播完后会用 `onend` 拿到的
 * 真实时长校正，所以不同机器的语速差异不会影响演示节奏。
 */
const CHARS_PER_SEC = 5.5
/** 语音结束后留出的缓冲，让评委看完最后一句 */
const TAIL_BUFFER = 2.5
/** 单步最短 / 最长停留，避免过短显得仓促或过长显得拖沓 */
const MIN_STEP = 10
const MAX_STEP = 38

/**
 * 每步停留时长 = 解说词朗读时间 + 缓冲。
 * 关闭语音时退化为按字数估算（而非写死的秒数），
 * 这样调整解说词后时长也会自动跟着变。
 */
function estimateSeconds(text: string): number {
  const cjk = (text.match(/[一-鿿]/g) || []).length
  const other = text.length - cjk
  const units = cjk + other * 0.5          // 英文/数字按半个字计
  return Math.round(Math.min(MAX_STEP, Math.max(MIN_STEP, units / CHARS_PER_SEC + TAIL_BUFFER)))
}

export default function DemoPlayer({ onClose }: { onClose: () => void }) {
  const nav = useNavigate()
  const [running, setRunning] = useState(false)
  const [stepIdx, setStepIdx] = useState(0)
  const [left, setLeft] = useState(() => estimateSeconds(STEPS[0].narration))
  const [elapsed, setElapsed] = useState(0)
  const [voice, setVoice] = useState(true)
  const [finished, setFinished] = useState(false)
  const timerRef = useRef<number | null>(null)

  const step = STEPS[stepIdx]
  const stepRef = useRef(stepIdx)      // 计时器读当前步，不依赖 React 状态时序
  stepRef.current = stepIdx

  /** 每步的实际停留秒数：初始按解说词字数估算，语音播完后被真实时长校正 */
  const [durations, setDurations] = useState<number[]>(() =>
    STEPS.map((s) => estimateSeconds(s.narration)))
  /** 真实语音时长（秒）。未播报时为 null，页面显示估算值。 */
  const [spokenSecs, setSpokenSecs] = useState<(number | null)[]>(() =>
    STEPS.map(() => null))
  const durationsRef = useRef(durations)
  durationsRef.current = durations
  const spokenSecsRef = useRef(spokenSecs)
  spokenSecsRef.current = spokenSecs

  const stepSeconds = (i: number) => durationsRef.current[i] ?? 20
  const totalSeconds = () => STEPS.reduce((s, _, i) => s + stepSeconds(i), 0)

  /**
   * 播报解说词。
   * onend 时用真实语音时长校正本步剩余时间 —— 这是「时间跟着语音走」的关键：
   * 语速快/慢、语音引擎差异都能自适应。
   */
  const speak = useCallback((text: string, onDone?: (spokenSec: number) => void) => {
    if (!voice || !('speechSynthesis' in window)) { onDone?.(0); return }
    try {
      window.speechSynthesis.cancel()
      const u = new SpeechSynthesisUtterance(text)
      u.lang = 'zh-CN'
      u.rate = 1.05
      const t0 = performance.now()
      u.onend = () => onDone?.((performance.now() - t0) / 1000)
      // 兜底：某些环境不触发 onend，按估算时长触发
      const est = estimateSeconds(text) * 1000 + 1500
      setTimeout(() => { try { window.speechSynthesis.cancel() } catch { /* noop */ } }, est)
      window.speechSynthesis.speak(u)
    } catch {
      onDone?.(0)
    }
  }, [voice])

  const goStep = useCallback((idx: number, auto = true) => {
    const i = Math.max(0, Math.min(STEPS.length - 1, idx))
    // 先写入预置动作，再跳转，页面挂载时读取
    const pre = STEPS[i].preAction
    try {
      if (auto && pre) sessionStorage.setItem(pre.key, JSON.stringify(pre.payload))
      else sessionStorage.removeItem('suguo_demo_preset')
    } catch { /* 忽略 */ }
    setStepIdx(i)
    setLeft(stepSeconds(i))
    if (auto) {
      nav(STEPS[i].path)
      // 语音结束后按真实时长校正本步停留时间
      speak(STEPS[i].narration, (spokenSec) => {
        if (spokenSec <= 0) return
        const rounded = Math.round(spokenSec * 10) / 10
        setSpokenSecs((prev) => {
          const next = [...prev]; next[i] = rounded
          return next
        })
        const target = Math.round(
          Math.min(MAX_STEP, Math.max(MIN_STEP, spokenSec + TAIL_BUFFER)))
        setDurations((prev) => {
          if (Math.abs(prev[i] - target) < 1) return prev
          const next = [...prev]; next[i] = target
          return next
        })
        if (stepRef.current === i) {
          setLeft((l) => Math.max(0.5, l - spokenSec))
        }
      })
    }
  }, [nav, speak])

  const stop = useCallback(() => {
    if (timerRef.current) {
      clearInterval(timerRef.current)
      timerRef.current = null
    }
    setRunning(false)
    if ('speechSynthesis' in window) window.speechSynthesis.cancel()
  }, [])

  const start = useCallback(() => {
    setFinished(false)
    setElapsed(0)
    if (timerRef.current) clearInterval(timerRef.current)
    goStep(0)
    setRunning(true)
  }, [goStep])

  /**
   * 单一计时器：每 250ms 检查一次，累计时间到就步进。
   * 用累计时间而非递减 left，避免 React 状态更新与 effect 依赖的时序问题。
   */
  useEffect(() => {
    if (!running) return
    const TICK = 250
    let acc = 0
    let cancelled = false

    const id = window.setInterval(() => {
      if (cancelled) return
      const cur = stepRef.current
      acc += TICK
      setLeft((l) => Math.max(0, l - TICK / 1000))
      setElapsed((e) => e + TICK / 1000)

      // 用动态时长：语音播完后会被真实时长校正
      if (acc >= stepSeconds(cur) * 1000) {
        acc = 0
        if (cur < STEPS.length - 1) {
          stepRef.current = cur + 1
          goStep(cur + 1)
        } else {
          setRunning(false)
          setFinished(true)
          if ('speechSynthesis' in window) window.speechSynthesis.cancel()
        }
      }
    }, TICK)

    timerRef.current = id
    return () => {
      cancelled = true
      clearInterval(id)
      timerRef.current = null
    }
  }, [running, goStep])

  useEffect(() => () => stop(), [stop])

  const jump = (idx: number) => {
    stepRef.current = idx
    setLeft(stepSeconds(idx))
    goStep(idx)
  }

  const curSeconds = stepSeconds(stepIdx)
  const done = STEPS.slice(0, stepIdx).reduce((s, _, i) => s + stepSeconds(i), 0)
  const pct = Math.min(100, ((done + (curSeconds - left)) / totalSeconds()) * 100)

  return (
    <div
      className="fixed inset-0 z-[999] flex flex-col"
      style={{ backgroundColor: 'rgba(10, 32, 24, 0.98)' }}
    >
      {/* 顶栏 */}
      <div className="h-14 border-b border-white/10 flex items-center gap-4 px-6 flex-shrink-0">
        <div className="flex items-center gap-2.5">
          <span className="w-8 h-8 rounded-md bg-brand-500 flex items-center justify-center font-bold text-[15px]">
            苏
          </span>
          <div>
            <div className="text-[14px] font-semibold text-white leading-tight">AI 选品全流程自动演示</div>
            <div className="text-[11px] text-white/45 leading-tight">
              共 {STEPS.length} 步 · 约 {Math.floor(totalSeconds() / 60)} 分 {Math.round(totalSeconds() % 60)} 秒（跟随语音长度）
            </div>
          </div>
        </div>

        <div className="ml-auto flex items-center gap-3">
          <label className="flex items-center gap-1.5 text-[12px] text-white/70 cursor-pointer">
            <input
              type="checkbox"
              checked={voice}
              onChange={(e) => {
                setVoice(e.target.checked)
                if (!e.target.checked && 'speechSynthesis' in window) window.speechSynthesis.cancel()
              }}
              className="accent-[#57ad84]"
            />
            语音解说
          </label>
          <span className="text-[13px] text-white/70 tabular-nums">
            {Math.round(elapsed)}s / {Math.round(totalSeconds())}s
          </span>
          {!running && !finished && (
            <button onClick={start} className="btn-primary">▶ 开始演示</button>
          )}
          {running && (
            <button onClick={stop} className="btn bg-white/10 text-white hover:bg-white/20">⏸ 暂停</button>
          )}
          <button onClick={onClose} className="text-white/50 hover:text-white text-xl leading-none px-1">×</button>
        </div>
      </div>

      {/* 进度条 */}
      <div className="h-1 bg-white/10 flex-shrink-0">
        <div className="h-full bg-brand-500 transition-all duration-1000" style={{ width: `${pct}%` }} />
      </div>

      {/* 主体 */}
      <div className="flex-1 flex min-h-0">
        {/* 左侧步骤列表 */}
        <div className="w-[260px] border-r border-white/10 overflow-y-auto flex-shrink-0 p-4">
          {STEPS.map((s, i) => (
            <button
              key={s.no}
              onClick={() => jump(i)}
              className={`w-full text-left px-3 py-2.5 rounded-lg mb-1.5 transition-colors ${
                i === stepIdx
                  ? 'bg-brand-600 text-white'
                  : i < stepIdx
                    ? 'text-white/45 hover:bg-white/5'
                    : 'text-white/60 hover:bg-white/5'
              }`}
            >
              <div className="flex items-center gap-2">
                <span
                  className={`w-5 h-5 rounded-full flex items-center justify-center text-[10.5px] font-medium flex-shrink-0 ${
                    i < stepIdx ? 'bg-brand-500 text-white' : i === stepIdx ? 'bg-white text-brand-700' : 'bg-white/15'
                  }`}
                >
                  {i < stepIdx ? '✓' : s.no}
                </span>
                <span className="text-[12.5px] font-medium truncate">{s.title}</span>
                <span className="text-[10.5px] ml-auto flex-shrink-0 opacity-60">{stepSeconds(i)}s</span>
              </div>
            </button>
          ))}
        </div>

        {/* 中间：解说字幕 */}
        <div className="flex-1 flex flex-col justify-center p-8 min-w-0 overflow-y-auto">
          {finished ? (
            <div className="max-w-2xl mx-auto text-center">
              <div className="text-[52px] mb-4">✓</div>
              <h2 className="text-[24px] font-semibold text-white mb-3">演示完成</h2>
              <p className="text-[14px] text-white/60 leading-relaxed mb-6">
                完整走通了「数据 → 算法 → AI → 管理决策 → 人机协同」闭环。
                <br />
                全程用时 {elapsed} 秒，所有数字均来自数据库实时计算。
              </p>
              <div className="flex items-center justify-center gap-3">
                <button onClick={start} className="btn-primary">重新演示</button>
                <button onClick={onClose} className="btn bg-white/10 text-white hover:bg-white/20">关闭</button>
              </div>
            </div>
          ) : (
            <div className="max-w-4xl mx-auto">
              <div className="flex items-center gap-3 mb-4">
                <span className="px-3 py-1 rounded-full bg-brand-600 text-white text-[12px] font-medium">
                  第 {step.no} 步 / 共 {STEPS.length} 步
                </span>
                <span className="text-[12px] text-white/50">本页停留 {left} 秒</span>
              </div>

              <h2 className="text-[30px] font-semibold text-white mb-2 leading-tight">{step.title}</h2>
              <p className="text-[15px] text-brand-300 mb-6">{step.subtitle}</p>

              {/* 解说字幕 */}
              <div className="rounded-xl bg-white/10 border border-white/20 p-5 mb-5">
                <div className="text-[11px] text-white/40 mb-2 flex items-center justify-between gap-3">
                  <span className="flex items-center gap-1.5">
                    <span>🔊</span> 解说词
                    <span className="text-white/30">（{step.narration.length} 字）</span>
                  </span>
                  <span className="text-white/40">
                    {spokenSecs[stepIdx] != null ? (
                      <>实测语音 {spokenSecs[stepIdx]}s ＋ 缓冲 {TAIL_BUFFER}s ＝ 停留 {stepSeconds(stepIdx)}s</>
                    ) : (
                      <>按字数估算停留 {stepSeconds(stepIdx)}s（语音结束后自动校正）</>
                    )}
                  </span>
                </div>
                <p className="text-[15px] text-white/90 leading-[1.9]">{step.narration}</p>
              </div>

              {/* 数据亮点 */}
              <div className="grid grid-cols-1 sm:grid-cols-3 gap-2.5">
                {step.highlights.map((h) => (
                  <div key={h} className="rounded-lg bg-brand-600/30 border border-brand-500/40 px-3.5 py-2.5">
                    <div className="text-[12.5px] text-brand-200 text-center">{h}</div>
                  </div>
                ))}
              </div>

              {/* 演讲提示 */}
              <div className="mt-5 rounded-lg border border-amber-500/40 bg-amber-500/20 px-4 py-2.5">
                <div className="text-[11px] text-amber-300/70 mb-1">💡 演讲提示</div>
                <div className="text-[12.5px] text-amber-200/90 leading-relaxed">{step.cue}</div>
              </div>

              {/* 手动控制 */}
              <div className="flex items-center gap-2 mt-6">
                <button
                  onClick={() => jump(Math.max(0, stepIdx - 1))}
                  disabled={stepIdx === 0}
                  className="btn bg-white/10 text-white hover:bg-white/20 disabled:opacity-30"
                >
                  ← 上一步
                </button>
                <button
                  onClick={() => (stepIdx < STEPS.length - 1 ? jump(stepIdx + 1) : (stop(), setFinished(true)))}
                  className="btn bg-white/10 text-white hover:bg-white/20"
                >
                  下一步 →
                </button>
                <span className="text-[11.5px] text-white/35 ml-auto">
                  页面已自动跳转到「{step.path}」，可切回浏览器窗口查看
                </span>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
