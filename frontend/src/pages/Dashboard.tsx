import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Chart, AXIS_STYLE, TOOLTIP, PALETTE } from '../components/Chart'
import {
  Alert, DemoBadge, ErrorBox, Loading, PriorityBadge, RiskBadge, SectionTitle, StatCard,
} from '../components/ui'
import { ALERT_COLOR, api, fmt, scoreColor, scoreLabel } from '../services/api'

const DEMO_STEPS = [
  { step: 1, title: '选择黄金海岸广场店', path: '/stores', desc: '确认当前门店与画像数据接入状态' },
  { step: 2, title: '查看品类健康情况', path: '/category-health', desc: '四维评分与系统重算/附件参考对比' },
  { step: 3, title: '选品比较（品类模式）', path: '/compare', desc: '2-6个对象加权比较，权重可调' },
  { step: 4, title: '小类比较实战', path: '/compare', desc: '鸡蛋/牛奶/垃圾袋/豆腐/拖把 五选一' },
  { step: 5, title: 'ABC分类与货架优化', path: '/abc-shelf', desc: '70个小类的价值分层与面积分配' },
  { step: 6, title: '关联陈列场景', path: '/association', desc: '牛奶+面包、火锅底料+丸子等组合' },
  { step: 7, title: '需求预测', path: '/forecast', desc: '置信区间与趋势分类' },
  { step: 8, title: 'AI生成选品优化方案', path: '/agent', desc: '五分组综合方案，每项带数据依据' },
  { step: 9, title: '提交建议进入审批', path: '/approvals', desc: '演示人机协同闭环' },
]

export default function Dashboard() {
  const nav = useNavigate()
  const [data, setData] = useState<any>(null)
  const [err, setErr] = useState('')
  const [showDemo, setShowDemo] = useState(false)
  const [demoStep, setDemoStep] = useState(0)

  const load = () => {
    setErr('')
    api.dashboard().then(setData).catch((e) => setErr(e.message))
  }
  useEffect(load, [])

  if (err) return <ErrorBox message={err} onRetry={load} />
  if (!data) return <Loading text="正在计算驾驶舱指标…" />

  const k = data.kpi
  const health = data.health_overview || []

  const barOption = {
    grid: { left: 90, right: 40, top: 20, bottom: 30 },
    tooltip: {
      ...TOOLTIP,
      formatter: (p: any) => {
        const item = health[p.dataIndex]
        return `${item.category}<br/>健康度 <b>${item.score}</b> 分（${item.stars} ${item.grade}）`
      },
    },
    xAxis: { type: 'value', max: 100, ...AXIS_STYLE, axisLabel: { ...AXIS_STYLE.axisLabel, formatter: '{value}' } },
    yAxis: {
      type: 'category',
      data: [...health].reverse().map((h: any) => h.category),
      ...AXIS_STYLE,
      splitLine: { show: false },
      axisLabel: { ...AXIS_STYLE.axisLabel, fontSize: 12 },
    },
    series: [
      {
        type: 'bar',
        data: [...health].reverse().map((h: any) => ({
          value: h.score,
          itemStyle: { color: scoreColor(h.score), borderRadius: [0, 4, 4, 0] },
        })),
        barWidth: 18,
        label: {
          show: true, position: 'right', fontSize: 11, color: '#55665f',
          formatter: (p: any) => `${p.value} ${scoreLabel(p.value)}`,
        },
      },
    ],
  }

  const radarOption = {
    tooltip: { ...TOOLTIP, trigger: 'item' },
    legend: { bottom: 0, itemWidth: 12, itemHeight: 8, textStyle: { fontSize: 11, color: '#55665f' } },
    radar: {
      indicator: health.slice(0, 5).map((h: any) => ({ name: h.category, max: 100 })),
      radius: '62%',
      center: ['50%', '46%'],
      axisName: { color: '#55665f', fontSize: 11 },
      splitLine: { lineStyle: { color: '#e3e8e6' } },
      splitArea: { areaStyle: { color: ['#fbfdfc', '#f5f8f7'] } },
      axisLine: { lineStyle: { color: '#e3e8e6' } },
    },
    series: [
      {
        type: 'radar',
        data: [
          {
            value: health.slice(0, 5).map((h: any) => h.score),
            name: '品类健康度',
            areaStyle: { color: 'rgba(37,115,84,0.18)' },
            lineStyle: { color: '#257354', width: 2 },
            itemStyle: { color: '#257354' },
          },
        ],
      },
    ],
  }

  const alertByType = (data.risk_alerts || []).reduce((acc: any, a: any) => {
    ;(acc[a.type] ||= []).push(a)
    return acc
  }, {})

  return (
    <div className="space-y-5 max-w-[1680px]">
      {/* 顶部操作条 */}
      <div className="flex items-center justify-between gap-4 flex-wrap">
        <div>
          <h1 className="text-[19px] font-semibold text-[#1a2b24]">AI 经营驾驶舱</h1>
          <p className="text-[12.5px] text-[#6b7d76] mt-0.5">
            门店：{data.store} ｜ 所有 KPI 由数据库实时计算，不含硬编码
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button className="btn-secondary" onClick={load}>刷新数据</button>
          <button
            className="btn-primary"
            onClick={() => window.dispatchEvent(new CustomEvent('suguo:open-demo'))}
          >
            ▶ 一键 3 分钟自动演示
          </button>
          <button className="btn-secondary" onClick={() => setShowDemo(true)}>
            手动演示动线
          </button>
        </div>
      </div>

      {/* KPI 卡片 */}
      <div className="grid grid-cols-2 md:grid-cols-4 xl:grid-cols-8 gap-3">
        <StatCard label="品类总数" value={k.category_total} unit="个" tone="brand" />
        <StatCard label="健康品类" value={k.healthy_category} unit="个" tone="good" hint="健康度 ≥ 70 分" />
        <StatCard label="风险品类" value={k.risk_category} unit="个" tone={k.risk_category > 2 ? 'bad' : 'warn'} hint="健康度 < 55 分" />
        <StatCard label="本月缺货次数" value={k.stockout_this_month} unit="次" tone={k.stockout_this_month > 150 ? 'bad' : 'warn'} hint="近12个月累计" />
        <StatCard label="平均库存周转" value={k.avg_turnover_days} unit="天" tone={k.avg_turnover_days > 40 ? 'warn' : 'good'} hint="全店品类均值" />
        <StatCard label="高价值关联组合" value={k.high_value_associations} unit="条" tone="brand" hint="提升度 ≥ 2" />
        <StatCard label="需求上涨品类" value={k.demand_rising_categories} unit="个" tone="good" />
        <StatCard label="待人工审批" value={k.pending_approvals} unit="条" tone={k.pending_approvals > 0 ? 'warn' : 'default'} />
      </div>

      {/* 健康度概览 + 雷达 */}
      <div className="grid grid-cols-1 xl:grid-cols-3 gap-4">
        <div className="card xl:col-span-2">
          <div className="card-title">
            <span>品类健康度概览</span>
            <div className="flex items-center gap-3 text-[11px] text-[#6b7d76]">
              {[['优秀', '#257354'], ['良好', '#57ad84'], ['一般', '#d9a520'], ['较差', '#e8833a'], ['差', '#d94a4a']].map(([l, c]) => (
                <span key={l} className="flex items-center gap-1">
                  <span className="w-2.5 h-2.5 rounded-sm" style={{ background: c }} />{l}
                </span>
              ))}
            </div>
          </div>
          <div className="p-4">
            <Chart option={barOption} height={280} title="各品类健康度得分（满分100）" onExport={() => {}} />
          </div>
        </div>

        <div className="card">
          <div className="card-title">健康度雷达图</div>
          <div className="p-4">
            <Chart option={radarOption} height={280} title="Top5 品类健康度分布" onExport={() => {}} />
          </div>
        </div>
      </div>

      {/* 风险预警 */}
      <div className="card">
        <div className="card-title">
          <span>风险预警</span>
          <span className="text-[12px] text-[#6b7d76] font-normal">
            共 {data.risk_alerts?.length || 0} 条 ｜ 阈值可在系统管理中调整
          </span>
        </div>
        <div className="p-4">
          {!data.risk_alerts?.length ? (
            <div className="text-[13px] text-[#8b9a94] py-4 text-center">当前未触发预警</div>
          ) : (
            <div className="space-y-3">
              {Object.entries(alertByType).map(([type, list]: any) => (
                <div key={type} className="flex items-start gap-3">
                  <div className="w-[104px] flex-shrink-0 pt-0.5">
                    <span
                      className="tag"
                      style={{
                        background: list[0].level === '高' ? '#fdf0f0' : '#fff8ec',
                        color: list[0].level === '高' ? '#c13f3f' : '#a3700f',
                        border: `1px solid ${list[0].level === '高' ? '#f0cccc' : '#f2dfb8'}`,
                      }}
                    >
                      {type}
                    </span>
                  </div>
                  <div className="flex-1 flex flex-wrap gap-2">
                    {list.map((a: any, i: number) => (
                      <div
                        key={i}
                        className="flex items-center gap-2 px-2.5 py-1.5 rounded-md bg-[#f7faf9] border border-[#eef2f0] text-[12px]"
                      >
                        <span
                          className="w-1.5 h-1.5 rounded-full flex-shrink-0"
                          style={{ background: a.level === '高' ? '#d94a4a' : '#e8833a' }}
                        />
                        <span className="font-medium text-[#2c3d36]">{a.target}</span>
                        <span className="text-[#6b7d76]">{a.value}</span>
                        <span className="text-[#a8b5b0]">{a.detail}</span>
                      </div>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* AI 今日建议 */}
      <div className="card">
        <div className="card-title">
          <span>AI 今日建议</span>
          <button className="btn-ghost text-[12px]" onClick={() => nav('/agent')}>
            与AI选品助手对话 →
          </button>
        </div>
        <div className="p-4 space-y-3">
          {(data.suggestions || []).map((s: any, i: number) => (
            <div key={i} className="border border-[#e9eeec] rounded-lg p-4 hover:border-brand-300 transition-colors">
              <div className="flex items-start justify-between gap-3 mb-2">
                <div className="flex items-center gap-2 flex-wrap">
                  <span className="w-5 h-5 rounded bg-brand-600 text-white text-[11px] flex items-center justify-center font-medium flex-shrink-0">
                    {i + 1}
                  </span>
                  <span className="text-[14px] font-medium text-[#1a2b24]">{s.title}</span>
                </div>
                <div className="flex items-center gap-1.5 flex-shrink-0">
                  <PriorityBadge priority={s.priority} />
                  <span className="tag bg-[#eef2f0] text-[#55665f] border border-[#dde4e1]">{s.risk_level}</span>
                  {s.requires_approval && (
                    <span className="tag bg-[#fdf0f0] text-[#c13f3f] border border-[#f0cccc]">需人工审批</span>
                  )}
                </div>
              </div>
              <div className="text-[13px] text-[#3d5049] leading-relaxed mb-2.5">{s.suggestion}</div>
              <div className="bg-[#f7faf9] rounded-md px-3 py-2 text-[12px] text-[#55665f] leading-relaxed">
                <span className="font-medium text-[#33473f]">数据依据：</span>{s.data_basis}
              </div>
              <div className="mt-2 flex items-center gap-3 text-[11.5px] text-[#8b9a94]">
                <span>影响品类：{s.affected}</span>
                <span className="font-mono">{s.code}</span>
                {s.requires_approval && (
                  <button className="text-brand-600 hover:underline" onClick={() => nav('/approvals')}>
                    前往审批 →
                  </button>
                )}
              </div>
            </div>
          ))}
          <Alert type="info">
            以上建议由平台基于数据库实时计算结果生成，每条均标注数据依据与优先级。
            AI 不自动执行下单、改价、淘汰供应商等操作，涉及 SKU 退出的结论须提交人工审批。
          </Alert>
        </div>
      </div>

      {/* 手动演示流程浮层 */}
      {showDemo && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-6 bg-black/45" onClick={() => setShowDemo(false)}>
          <div className="card w-full max-w-[680px] shadow-2xl" onClick={(e) => e.stopPropagation()}>
            <div className="card-title">
              比赛演示流程（3-5 分钟完整闭环）
              <button onClick={() => setShowDemo(false)} className="text-[#8b9a94] hover:text-[#33473f] text-lg">×</button>
            </div>
            <div className="p-5">
              <div className="space-y-1.5 mb-4">
                {DEMO_STEPS.map((s, i) => (
                  <button
                    key={s.step}
                    onClick={() => { setDemoStep(i); nav(s.path); setShowDemo(false) }}
                    className={`w-full flex items-start gap-3 px-3 py-2.5 rounded-lg text-left transition-colors ${
                      i === demoStep ? 'bg-brand-50 border border-brand-200' : 'hover:bg-[#f7faf9]'
                    }`}
                  >
                    <span
                      className={`w-6 h-6 rounded-full flex items-center justify-center text-[11px] font-medium flex-shrink-0 mt-0.5 ${
                        i <= demoStep ? 'bg-brand-600 text-white' : 'bg-[#eef2f0] text-[#6b7d76]'
                      }`}
                    >
                      {s.step}
                    </span>
                    <div className="min-w-0">
                      <div className="text-[13px] font-medium text-[#1a2b24]">{s.title}</div>
                      <div className="text-[11.5px] text-[#8b9a94]">{s.desc}</div>
                    </div>
                    <span className="text-[#b8c5c0] ml-auto flex-shrink-0">→</span>
                  </button>
                ))}
              </div>
              <Alert type="success">
                演示动线覆盖：数据 → 算法 → AI → 管理决策 → 人机协同。
                建议讲演时重点展示「选品比较中心的AI判断」与「关联陈列的实时重算 vs 附件参考」两处对比。
              </Alert>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
