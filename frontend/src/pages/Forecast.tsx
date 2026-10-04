import { useEffect, useState } from 'react'
import { Chart, AXIS_STYLE, TOOLTIP } from '../components/Chart'
import { Alert, DemoBadge, Empty, ErrorBox, Loading, RiskBadge, SectionTitle } from '../components/ui'
import { api, fmt } from '../services/api'

export default function Forecast() {
  const [items, setItems] = useState<any[]>([])
  const [cur, setCur] = useState<string>('')
  const [err, setErr] = useState('')
  const [busy, setBusy] = useState(false)
  const [runResult, setRunResult] = useState<any>(null)

  const load = () => {
    setErr('')
    api.forecast().then((d) => {
      setItems(d.items || [])
      if (d.items?.length) setCur(d.items[0].category)
    }).catch((e) => setErr(e.message))
  }
  useEffect(load, [])

  const runModel = async () => {
    if (!cur) return
    setBusy(true)
    setRunResult(null)
    try {
      setRunResult(await api.runForecast({ category: cur, periods: 4 }))
    } catch (e: any) {
      setRunResult({ success: false, message: e.message })
    } finally {
      setBusy(false)
    }
  }

  if (err) return <ErrorBox message={err} onRetry={load} />
  if (!items.length) return <Loading text="正在加载预测数据…" />

  const view = items.find((i) => i.category === cur) || items[0]
  const history = view.series.filter((s: any) => s.type === 'history')
  const forecast = view.series.filter((s: any) => s.type === 'forecast')
  const labels = view.series.map((s: any) => s.period)

  // 置信区间带：用两个 stack 系列的差值模拟
  const upperBand = view.series.map((s: any, i: number) => {
    if (s.type !== 'forecast') return null
    return s.upper
  })
  const lowerBandWidth = view.series.map((s: any, i: number) => {
    if (s.type !== 'forecast') return null
    return s.upper - s.lower
  })

  const mainOption = {
    grid: { left: 60, right: 30, top: 46, bottom: 40 },
    tooltip: {
      ...TOOLTIP,
      formatter: (ps: any[]) => {
        const i = ps[0].dataIndex
        const s = view.series[i]
        if (s.type === 'history') return `${s.period}<br/>历史销量 <b>${fmt.n(s.actual)}</b> 件`
        return `${s.period}<br/>预测销量 <b>${fmt.n(s.forecast)}</b> 件<br/>置信区间 ${fmt.n(s.lower)} ~ ${fmt.n(s.upper)} 件`
      },
    },
    legend: { top: 0, itemWidth: 14, itemHeight: 8, textStyle: { fontSize: 11 } },
    xAxis: { type: 'category', data: labels, ...AXIS_STYLE },
    yAxis: { type: 'value', ...AXIS_STYLE, name: '销量(件)' },
    series: [
      {
        name: '置信区间上界', type: 'line', data: upperBand, stack: 'band',
        lineStyle: { opacity: 0 }, symbol: 'none', areaStyle: { opacity: 0 },
        itemStyle: { color: 'transparent' }, silent: true, legendHoverLink: false, tooltip: { show: false },
      },
      {
        name: '预测区间', type: 'line', data: lowerBandWidth, stack: 'band',
        lineStyle: { opacity: 0 }, symbol: 'none',
        areaStyle: { color: 'rgba(232,131,58,0.18)' },
        itemStyle: { color: 'transparent' }, silent: true, legendHoverLink: false, tooltip: { show: false },
      },
      {
        name: '历史销量', type: 'line', data: view.series.map((s: any) => s.actual),
        smooth: true, symbolSize: 4,
        itemStyle: { color: '#257354' }, lineStyle: { width: 2.5, color: '#257354' },
        markLine: {
          silent: true, symbol: 'none',
          data: [{ xAxis: history.length - 0.5, label: { formatter: '预测起点', fontSize: 10, color: '#8b9a94' } }],
          lineStyle: { color: '#c3ceca', type: 'dashed' },
        },
      },
      {
        name: '预测销量', type: 'line',
        data: view.series.map((s: any, i: number) => (i < history.length - 1 ? null : s.forecast)),
        smooth: true, symbolSize: 5, symbol: 'circle',
        itemStyle: { color: '#e8833a' },
        lineStyle: { width: 2.5, color: '#e8833a', type: 'dashed' },
      },
    ],
  }

  const compareOption = {
    grid: { left: 60, right: 30, top: 30, bottom: 40 },
    tooltip: { ...TOOLTIP },
    xAxis: { type: 'category', data: items.map((i) => i.category), ...AXIS_STYLE, axisLabel: { ...AXIS_STYLE.axisLabel, rotate: 20, fontSize: 10 } },
    yAxis: [
      { type: 'value', ...AXIS_STYLE, name: '销量(件)' },
      { type: 'value', ...AXIS_STYLE, name: '环比%', splitLine: { show: false } },
    ],
    series: [
      {
        name: '最近4期实际', type: 'bar', data: items.map((i) => i.recent_avg),
        itemStyle: { color: '#8bcbaa', borderRadius: [4, 4, 0, 0] }, barWidth: 22,
      },
      {
        name: '未来4期预测', type: 'bar', data: items.map((i) => i.future_avg),
        itemStyle: { color: '#e8833a', borderRadius: [4, 4, 0, 0] }, barWidth: 22,
      },
      {
        name: '环比变化', type: 'line', yAxisIndex: 1, data: items.map((i) => i.change_pct),
        itemStyle: { color: '#257354' }, lineStyle: { width: 2 }, symbolSize: 6,
        label: { show: true, fontSize: 10, formatter: (p: any) => (p.value != null ? `${p.value > 0 ? '+' : ''}${p.value.toFixed(1)}%` : '') },
      },
    ],
  }

  const trendColor = (l: string) =>
    l === '明显上涨' || l === '温和上涨' ? '#257354'
      : l === '明显下降' || l === '温和下降' ? '#d94a4a' : '#8b9a94'

  return (
    <div className="space-y-4 max-w-[1680px]">
      <div className="flex items-center justify-between gap-4 flex-wrap">
        <div>
          <h1 className="text-[19px] font-semibold text-[#1a2b24]">需求预测</h1>
          <p className="text-[12.5px] text-[#6b7d76] mt-0.5">
            数据源：dataset_demand_forecast.csv ｜ {items.length} 个品类 × 12期历史 + 4期预测
          </p>
        </div>
        <DemoBadge text="模拟预测结果" />
      </div>

      {/* 品类选择 */}
      <div className="card">
        <div className="card-title">
          <span>选择品类查看预测明细</span>
          <button className="btn-secondary" onClick={runModel} disabled={busy}>
            {busy ? '预测中…' : '用移动平均模型重跑预测'}
          </button>
        </div>
        <div className="p-4 flex flex-wrap gap-2">
          {items.map((i) => (
            <button
              key={i.category}
              onClick={() => setCur(i.category)}
              className={`px-3.5 py-2 rounded-lg border text-[13px] transition-all ${
                cur === i.category
                  ? 'border-brand-500 bg-brand-50 text-brand-800 font-medium'
                  : 'border-[#d5ded9] text-[#3d5049] hover:border-brand-300'
              }`}
            >
              {i.category}
              <span className="ml-1.5 text-[11px]" style={{ color: trendColor(i.trend_level) }}>
                {i.change_pct != null ? `${i.change_pct > 0 ? '+' : ''}${i.change_pct.toFixed(1)}%` : '—'}
              </span>
            </button>
          ))}
        </div>
      </div>

      {/* 模型重跑结果 */}
      {runResult && (
        <Alert type={runResult.success ? 'success' : 'warn'}>
          {runResult.success ? (
            <div>
              <div className="font-medium mb-1">
                {runResult.category} · {runResult.method} · 历史 {runResult.history_periods} 期
              </div>
              <div className="text-[12px] leading-relaxed">
                未来4期预测：{runResult.predictions.join('、')} 件，均值 {fmt.n(runResult.future_avg)} 件，
                较最近4期实际（{fmt.n(runResult.recent_avg)} 件）{runResult.trend.level}（{fmt.signPct(runResult.trend.change_pct)}）。
                {runResult.note}
                可扩展外生变量：{runResult.extensible?.join('、')}。
              </div>
              <div className="text-[11.5px] text-[#8b9a94] mt-1.5">{runResult.prophet_note}</div>
            </div>
          ) : (
            <div>
              <div className="font-medium mb-1">{runResult.message}</div>
              <div className="text-[12px]">建议补充：{runResult.missing?.join('、')}</div>
            </div>
          )}
        </Alert>
      )}

      {/* 概览指标 */}
      <div className="grid grid-cols-2 md:grid-cols-3 xl:grid-cols-6 gap-3">
        {[
          ['未来4期平均需求', fmt.n(view.future_avg), '件', 'default'],
          ['最近4期实际需求', fmt.n(view.recent_avg), '件', 'default'],
          ['环比趋势', view.change_pct != null ? fmt.signPct(view.change_pct) : '—', '', trendColor(view.trend_level)],
          ['趋势分类', view.trend_level, '', trendColor(view.trend_level)],
          ['需求风险', view.risk.risk_level, '级', view.risk.risk_level === '高' ? 'bad' : view.risk.risk_level === '中' ? 'warn' : 'good'],
          ['预测区间宽度', fmt.pct(view.avg_interval_width_pct), '', 'default'],
        ].map(([label, v, u, tone]: any) => (
          <div key={label} className="card p-4">
            <div className="text-[12px] text-[#6b7d76]">{label}</div>
            <div
              className="text-[24px] font-semibold tabular-nums mt-1 leading-none"
              style={{ color: typeof tone === 'string' && tone.startsWith('#') ? tone : undefined }}
            >
              {v}
              {u && <span className="text-[12px] text-[#8b9a94] ml-1">{u}</span>}
            </div>
          </div>
        ))}
      </div>

      {/* 预测图表 */}
      <div className="card">
        <div className="card-title">
          <span>{view.category} 需求预测（历史实线 + 预测虚线 + 置信区间带）</span>
          <DemoBadge text="模拟预测结果" />
        </div>
        <div className="p-4">
          <Chart option={mainOption} height={360} title="12期历史与4期预测" onExport={() => {}} />
        </div>
      </div>

      {/* 详情 */}
      <div className="grid grid-cols-1 xl:grid-cols-3 gap-4">
        <div className="card xl:col-span-2">
          <div className="card-title">各品类需求对比</div>
          <div className="p-4">
            <Chart option={compareOption} height={320} title="最近4期实际 vs 未来4期预测" onExport={() => {}} />
          </div>
        </div>

        <div className="card">
          <div className="card-title">{view.category} 预测详情</div>
          <div className="p-4 space-y-3.5">
            <div className="grid grid-cols-2 gap-2">
              {[
                ['历史期数', `${view.history_periods} 期`],
                ['预测期数', `${view.forecast_periods} 期`],
                ['未来4期均量', `${fmt.n(view.future_avg)} 件`],
                ['最近4期均量', `${fmt.n(view.recent_avg)} 件`],
              ].map(([k, v]) => (
                <div key={k} className="rounded-md bg-[#f7faf9] px-2.5 py-2">
                  <div className="text-[11px] text-[#8b9a94]">{k}</div>
                  <div className="text-[13px] font-medium text-[#2c3d36] tabular-nums">{v}</div>
                </div>
              ))}
            </div>

            <div>
              <SectionTitle>需求风险判定</SectionTitle>
              <div className="flex items-center gap-2 mb-2">
                <RiskBadge level={view.risk.risk_level} />
                <span className="text-[12.5px] text-[#55665f]">风险等级</span>
              </div>
              <ul className="space-y-1.5">
                {view.risk.factors.map((f: string, i: number) => (
                  <li key={i} className="flex items-start gap-2 text-[12.5px] text-[#3d5049]">
                    <span className="text-brand-500 mt-0.5 flex-shrink-0">▸</span>
                    <span className="leading-relaxed">{f}</span>
                  </li>
                ))}
              </ul>
            </div>

            <div>
              <SectionTitle>数据量说明</SectionTitle>
              <div
                className={`text-[12.5px] leading-relaxed rounded-md px-3 py-2.5 border ${
                  view.sample_sufficient
                    ? 'bg-brand-50 border-brand-200 text-brand-800'
                    : 'bg-[#fff8ec] border-[#f2dfb8] text-[#8a6212]'
                }`}
              >
                {view.sample_note}
              </div>
            </div>

            <div>
              <SectionTitle>未来4期预测明细</SectionTitle>
              <div className="space-y-1.5">
                {forecast.map((f: any) => (
                  <div key={f.week_no} className="flex items-center justify-between text-[12.5px] px-2.5 py-1.5 rounded bg-[#f7faf9]">
                    <span className="text-[#55665f]">{f.period}</span>
                    <span className="font-medium text-[#c96a1f] tabular-nums">{fmt.n(f.forecast)} 件</span>
                    <span className="text-[11px] text-[#a8b5b0] tabular-nums">
                      [{fmt.n(f.lower)} ~ {fmt.n(f.upper)}]
                    </span>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>
      </div>

      <Alert type="warn">
        <div className="font-medium mb-1">关于预测精度的说明</div>
        <div className="text-[12px] leading-relaxed">
          当前展示的预测值来自附件的模拟结果（Prophet 标准输出格式），<b>不是本平台模型计算的结果</b>，
          平台不会为其标注任何预测精度（如 MAPE）。
          点击「用移动平均模型重跑预测」可查看平台基于历史数据的实际计算结果；
          由于历史数据仅 {items[0]?.history_periods} 期（推荐 24-36 期），结果仅供趋势参考。
          真实部署时环境安装 Prophet 后可切换模型，并支持接入节假日、天气、促销、价格、季节等外生变量。
        </div>
      </Alert>
    </div>
  )
}
