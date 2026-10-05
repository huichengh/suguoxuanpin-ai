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
 * 自动演示
 *
 * 8 步走完「数据 → 算法 → AI → 管理决策 → 人机协同」完整闭环。
 * 每步自动跳转并显示解说字幕，评委无需操作。
 * 不含语音播报——解说词以字幕形式呈现，由评审自行阅读，
 * 停留时长按默读速度计算（见下方常量说明）。
 * 全程约 2 分 10 秒。
 */

interface Step {
  no: number
  title: string
  subtitle: string
  path: string
  /** 解说词，以字幕形式显示供评审阅读；停留时长按其字数计算 */
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
      '演示从门店开始。这是华润苏果南京江宁黄金海岸广场店，社区购物中心，营业面积 3200 平米。人口与 POI 字段全部显示待接入——平台不编造不存在的数据。',
    highlights: ['社区门店定位', '画像数据待接入', '不编造人口数据'],
    cue: '强调"数据不足时平台明确说不足"，这是数据治理能力的体现',
  },
  {
    no: 2,
    title: '7 大品类健康诊断',
    subtitle: '四维评分模型，区分附件参考与系统重算',
    path: '/category-health',
    narration:
      '品类健康度用四个维度打分：销量 30%、毛利 30%、周转 20%、坪效 20%。周转天数越低越好，做了逆向标准化。生鲜蔬果 100 分居首，纺织服装 15.2 分垫底，周转 87 天、坪效 270。',
    highlights: ['生鲜蔬果 100 分 · 优秀', '纺织服装 15.2 分 · 需重点优化', '周转天数逆向标准化'],
    cue: '重点讲逆向标准化这个技术细节，以及双数据来源的治理设计',
  },
  {
    no: 3,
    title: '选品比较中心',
    subtitle: '2-6 个对象多维加权比较，权重可实时调整',
    path: '/compare',
    narration:
      '比较中心支持品类、小类、单品三种模式，权重可实时调整。小类层缺毛利与周转数据，模型自动降级为两维，不做数据摊派。',
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
      '小类比较实战：鸡蛋、牛奶、垃圾袋、豆腐、拖把五选一。鸡蛋 100 分居首，销量 2018 件，是拖把的三倍多。豆腐 0 分垫底，建议退出。每条结论都附数据依据与风险。',
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
      '关联陈列基于 5000 笔交易篮、70 个商品实时计算。附件预置 20 条规则，只有 11 条通过当前阈值。两份结果分开存放、分别标注，未通过的也原样保留。',
    highlights: ['5000 笔交易篮 · 70 个商品', '附件 20 条中仅 11 条达标', '双来源分开标注'],
    cue: '这是最能体现数据治理能力的一页，务必讲清"为什么不删附件数据"',
  },
  {
    no: 6,
    title: '需求预测',
    subtitle: '历史实线 + 预测虚线 + 置信区间带',
    path: '/forecast',
    narration:
      '需求预测用 12 期历史外推 4 期，实线是历史、虚线是预测，中间是置信区间带。标签已注明是模拟结果，平台不标注任何预测精度。',
    highlights: ['12 期历史 + 4 期预测', '模拟结果如实标注', '可重跑真实模型对比'],
    cue: '强调平台区分"附件模拟值"和"平台实算值"，不混为一谈',
  },
  {
    no: 7,
    title: 'AI 生成综合选品方案',
    subtitle: '五分组输出，每项都有多维数据依据',
    path: '/agent',
    narration:
      'AI 生成综合方案，输出五组：优先扩充、建议保持、重点观察、建议精简、建议退出。每项至少四个维度的数据依据，只看一个健康分不给结论。',
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
      '人机协同。AI 建议分三级，SKU 退出这类高影响操作必须人工审批。AI 不下采购单、不改价格、不删商品，只形成待审批建议，全程可追溯。',
    highlights: ['三级审批机制', 'Level 3 强制人工审批', '全流程可追溯'],
    cue: '结尾停在这一页，强调"AI 辅助决策、人工最终确认"的核心定位',
  },
]

/**
 * 演示时长按「解说词默读所需时间」计算。
 *
 * 本版不再朗读解说词，字幕由评委自行阅读，因此基准从口播速度调整为默读速度：
 *   停留秒数 = 解说词字数 / 默读速度 + 浏览缓冲
 *
 * 默读速度取每秒 5 字——比常速口播（约 6 字/秒）慢，留出辨认数字的余量。
 * 单步封顶 20 秒：字数最多的那一步也不至于拖沓；
 * 全程 8 步合计约 2 分 10 秒。
 */
const READ_CHARS_PER_SEC = 5
/** 留给评委看页面数据的时间（换页动画、图表渲染） */
const BROWSE_BUFFER = 1.5
/** 单步停留上限，防止长文案把某一步拖得过长 */
const MAX_STEP = 20

/** 每步停留秒数。中文按字数计，英文与数字按半个字计。 */
function readSeconds(text: string): number {
  const cjk = (text.match(/[一-鿿]/g) || []).length
  const other = text.length - cjk
  const units = cjk + other * 0.5
  return Math.min(MAX_STEP, Math.round(units / READ_CHARS_PER_SEC + BROWSE_BUFFER))
}

/** 各步停留时长。解说词改动后自动跟随，无需手工调整。 */
const STEP_SECONDS = STEPS.map((s) => readSeconds(s.narration))

export default function DemoPlayer({ onClose }: { onClose: () => void }) {
  const nav = useNavigate()
  const [running, setRunning] = useState(false)
  const [stepIdx, setStepIdx] = useState(0)
  const [left, setLeft] = useState(() => readSeconds(STEPS[0].narration))
  const [elapsed, setElapsed] = useState(0)
  const [finished, setFinished] = useState(false)
  const timerRef = useRef<number | null>(null)

  const step = STEPS[stepIdx]
  const stepRef = useRef(stepIdx)      // 计时器读当前步，不依赖 React 状态时序
  stepRef.current = stepIdx

  const stepSeconds = (i: number) => STEP_SECONDS[i] ?? 20
  const TOTAL_SECONDS = STEP_SECONDS.reduce((a, b) => a + b, 0)


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
    if (auto) nav(STEPS[i].path)
  }, [nav])

  const stop = useCallback(() => {
    if (timerRef.current) {
      clearInterval(timerRef.current)
      timerRef.current = null
    }
    setRunning(false)
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

      if (acc >= stepSeconds(cur) * 1000) {
        acc = 0
        if (cur < STEPS.length - 1) {
          stepRef.current = cur + 1
          goStep(cur + 1)
        } else {
          setRunning(false)
          setFinished(true)
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
  const pct = Math.min(100, ((done + (curSeconds - left)) / TOTAL_SECONDS) * 100)

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
              共 {STEPS.length} 步 · 约 {Math.floor(TOTAL_SECONDS / 60)} 分 {Math.round(TOTAL_SECONDS % 60)} 秒
            </div>
          </div>
        </div>

        <div className="ml-auto flex items-center gap-3">
          <span className="text-[13px] text-white/70 tabular-nums">
            {Math.round(elapsed)}s / {TOTAL_SECONDS}s
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
                全程 {TOTAL_SECONDS} 秒，所有数字均来自数据库实时计算。
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
                    <span>📝</span> 解说词
                    <span className="text-white/30">（{step.narration.length} 字）</span>
                  </span>
                  <span className="text-white/40">
                    按默读速度停留 {stepSeconds(stepIdx)}s
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
