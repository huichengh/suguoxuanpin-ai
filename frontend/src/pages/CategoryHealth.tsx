import { useEffect, useRef, useState } from 'react'
import { Chart, AXIS_STYLE, TOOLTIP } from '../components/Chart'
import {
  Alert, DemoBadge, ErrorBox, Loading, Modal, SectionTitle, Tabs,
} from '../components/ui'
import { ALERT_COLOR, api, fmt, scoreColor, scoreLabel } from '../services/api'

export default function CategoryHealth() {
  const [rows, setRows] = useState<any[]>([])
  const [detail, setDetail] = useState<any>(null)
  const [tab, setTab] = useState('list')
  const [busy, setBusy] = useState(false)
  const [msg, setMsg] = useState('')
  const [err, setErr] = useState('')
  const [months, setMonths] = useState(12)

  const fetchRows = async () => {
    try {
      const d = await api.allCategoryHealth()
      const all: any[] = d.items || []
      all.sort((a, b) => (b.overall_score || 0) - (a.overall_score || 0))
      all.forEach((r, i) => (r.rank = i + 1))
      setRows(all)
      if (all.length && !detail) setDetail(all[0])
    } catch (e: any) {
      setErr(e.message)
    }
  }

  useEffect(() => { fetchRows() }, [])

  const recalc = async () => {
    setBusy(true)
    setMsg('')
    try {
      const d = await api.recalcHealth()
      setMsg(`重算完成，共 ${d.count} 个品类，耗时 ${d.duration_ms}ms。权重：销量${d.weights.sales}/毛利${d.weights.margin}/周转${d.weights.turnover}/坪效${d.weights.space}`)
      await fetchRows()
    } catch (e: any) {
      setErr(e.message)
    } finally {
      setBusy(false)
    }
  }

  if (err && !rows.length) return <ErrorBox message={err} onRetry={fetchRows} />
  if (!rows.length) return <Loading text="正在计算品类健康度…" />

  const barOption = {
    grid: { left: 90, right: 60, top: 30, bottom: 30 },
    tooltip: {
      ...TOOLTIP,
      formatter: (p: any) => {
        const r = rows[p.dataIndex]
        return `${r.category}<br/>健康度 <b>${r.overall_score}</b>（${r.stars}）<br/>` +
          `销量分 ${r.sales_score} ｜ 毛利分 ${r.margin_score}<br/>` +
          `周转分 ${r.turnover_score} ｜ 坪效分 ${r.space_score}<br/>` +
          `周转 ${r.avg_turnover_days} 天 ｜ 缺货 ${r.total_stockout} 次`
      },
    },
    legend: { top: 0, itemWidth: 12, itemHeight: 8, textStyle: { fontSize: 11 } },
    xAxis: { type: 'value', max: 100, ...AXIS_STYLE },
    yAxis: {
      type: 'category', data: [...rows].reverse().map((r) => r.category),
      ...AXIS_STYLE, splitLine: { show: false },
    },
    series: [
      {
        name: '销量得分', type: 'bar', stack: 's',
        data: [...rows].reverse().map((r) => r.sales_score),
        itemStyle: { color: '#257354' }, barWidth: 18,
      },
      {
        name: '毛利得分', type: 'bar', stack: 's',
        data: [...rows].reverse().map((r) => r.margin_score - r.sales_score),
        itemStyle: { color: '#57ad84' },
      },
      {
        name: '周转得分', type: 'bar', stack: 's',
        data: [...rows].reverse().map((r) => r.turnover_score - r.sales_score - r.margin_score),
        itemStyle: { color: '#8bcbaa' },
      },
      {
        name: '坪效得分', type: 'bar', stack: 's',
        data: [...rows].reverse().map((r) => r.space_score - r.sales_score - r.margin_score - r.turnover_score),
        itemStyle: { color: '#b8e1cb', borderRadius: [0, 4, 4, 0] },
      },
    ],
  }

  const scatterOption = {
    grid: { left: 60, right: 40, top: 30, bottom: 50 },
    tooltip: {
      ...TOOLTIP,
      formatter: (p: any) => {
        const r = p.data.raw
        return `${r.category}<br/>周转 ${r.avg_turnover_days} 天<br/>坪效 ${r.avg_sales_per_sqm} 元/㎡/月<br/>健康度 ${r.overall_score}`
      },
    },
    xAxis: { type: 'value', name: '库存周转天数', nameLocation: 'middle', nameGap: 32, ...AXIS_STYLE },
    yAxis: { type: 'value', name: '坪效(元/㎡/月)', ...AXIS_STYLE },
    series: [{
      type: 'scatter',
      symbolSize: (v: any, p: any) => Math.max(12, (p.data.raw.overall_score / 100) * 26),
      data: rows.map((r) => ({
        value: [r.avg_turnover_days, r.avg_sales_per_sqm],
        raw: r,
        itemStyle: { color: scoreColor(r.overall_score), opacity: 0.8 },
      })),
      label: {
        show: true, position: 'right', fontSize: 11, color: '#55665f',
        formatter: (p: any) => p.data.raw.category,
      },
      markLine: {
        silent: true, symbol: 'none',
        lineStyle: { color: '#d5ded9', type: 'dashed' },
        data: [
          { xAxis: 45, label: { formatter: '周转阈值 45天', fontSize: 10, color: '#8b9a94' } },
          { yAxis: 600, label: { formatter: '坪效阈值 600', fontSize: 10, color: '#8b9a94' } },
        ],
      },
    }],
  }

  const cur = detail || rows[0]
  const diffCount = rows.filter((r) => r.diff_vs_attachment !== undefined && Math.abs(r.diff_vs_attachment) >= 5).length

  return (
    <div className="space-y-4 max-w-[1680px]">
      <div className="flex items-center justify-between gap-4 flex-wrap">
        <div>
          <h1 className="text-[19px] font-semibold text-[#1a2b24]">品类健康诊断</h1>
          <p className="text-[12.5px] text-[#6b7d76] mt-0.5">
            数据源：dataset_category_sales.csv ｜ 聚合最近 {months} 个月 ｜ ECR 品类管理「评估」环节
          </p>
        </div>
        <div className="flex items-center gap-2">
          <DemoBadge text="附件参考结果与系统重算结果分别标注" />
          <button className="btn-secondary" onClick={recalc} disabled={busy}>
            {busy ? '重算中…' : '按当前权重重算'}
          </button>
        </div>
      </div>

      {msg && <Alert type="success">{msg}</Alert>}

      <Tabs
        active={tab}
        onChange={setTab}
        items={[
          { key: 'list', label: '健康度总览', badge: rows.length },
          { key: 'radar', label: '四维能力雷达' },
          { key: 'scatter', label: '周转-坪效分布' },
          { key: 'detail', label: '诊断详情' },
        ]}
      />

      {tab === 'list' && (
        <div className="space-y-4">
          <div className="card overflow-hidden">
            <div className="card-title">
              <span>品类健康度评分结果</span>
              <span className="text-[12px] text-[#6b7d76] font-normal">
                模型：销量贡献30% + 毛利贡献30% + 库存周转20% + 坪效20%
              </span>
            </div>
            <div className="overflow-x-auto">
              <table className="w-full min-w-[1180px]">
                <thead>
                  <tr>
                    <th className="table-th">排名</th>
                    <th className="table-th">品类</th>
                    <th className="table-th">综合得分</th>
                    <th className="table-th">等级</th>
                    <th className="table-th text-right">销量贡献</th>
                    <th className="table-th text-right">毛利贡献</th>
                    <th className="table-th text-right">周转天数</th>
                    <th className="table-th text-right">坪效</th>
                    <th className="table-th text-right">缺货</th>
                    <th className="table-th text-right">SKU数</th>
                    <th className="table-th">销量趋势</th>
                    <th className="table-th">毛利趋势</th>
                    <th className="table-th">预警灯</th>
                    <th className="table-th">附件参考对比</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((r) => (
                    <tr
                      key={r.category_id}
                      onClick={() => { setDetail(r); setTab('detail') }}
                      className="cursor-pointer hover:bg-[#f9fbfb]"
                    >
                      <td className="table-td tabular-nums">{r.rank}</td>
                      <td className="table-td font-medium">{r.category}</td>
                      <td className="table-td">
                        <div className="flex items-center gap-2">
                          <span className="text-[15px] font-semibold tabular-nums" style={{ color: scoreColor(r.overall_score) }}>
                            {r.overall_score}
                          </span>
                          <div className="w-14 h-1.5 rounded-full bg-[#eef2f0] overflow-hidden">
                            <div
                              className="h-full rounded-full"
                              style={{ width: `${r.overall_score}%`, background: scoreColor(r.overall_score) }}
                            />
                          </div>
                        </div>
                      </td>
                      <td className="table-td">
                        <div className="flex flex-col gap-0.5">
                          <span className="text-[12.5px]">{r.grade}</span>
                          <span className="text-[11px] text-[#b8860b] tracking-tight">{r.stars}</span>
                        </div>
                      </td>
                      <td className="table-td text-right tabular-nums">{fmt.pct(r.sales_contribution)}</td>
                      <td className="table-td text-right tabular-nums">{fmt.pct(r.margin_contribution)}</td>
                      <td className="table-td text-right tabular-nums">{r.avg_turnover_days}</td>
                      <td className="table-td text-right tabular-nums">{r.avg_sales_per_sqm}</td>
                      <td className="table-td text-right tabular-nums">{r.total_stockout}</td>
                      <td className="table-td text-right tabular-nums">{r.sku_count}</td>
                      <td className="table-td text-[12px] tabular-nums">
                        {r.sales_trend != null ? (
                          <span className={r.sales_trend >= 0 ? 'text-brand-600' : 'text-[#c13f3f]'}>
                            {fmt.signPct(r.sales_trend)}
                          </span>
                        ) : <span className="text-[#a8b5b0]">数据不足</span>}
                      </td>
                      <td className="table-td text-[12px] tabular-nums">
                        {r.margin_trend != null ? (
                          <span className={r.margin_trend >= 0 ? 'text-brand-600' : 'text-[#c13f3f]'}>
                            {fmt.signPct(r.margin_trend)}
                          </span>
                        ) : <span className="text-[#a8b5b0]">数据不足</span>}
                      </td>
                      <td className="table-td">
                        <span
                          className="tag"
                          style={{ background: `${ALERT_COLOR[r.alert_light]}18`, color: ALERT_COLOR[r.alert_light] }}
                        >
                          {r.alert_light}
                        </span>
                      </td>
                      <td className="table-td text-[11.5px]">
                        {r.attachment_reference ? (
                          <div className="space-y-0.5">
                            <div>附件 {r.attachment_reference.overall_score} 分</div>
                            <div
                              className={`tabular-nums ${r.consistent_with_attachment ? 'text-[#8b9a94]' : 'text-[#a3700f]'}`}
                            >
                              差异 {r.diff_vs_attachment > 0 ? '+' : ''}{r.diff_vs_attachment}
                            </div>
                          </div>
                        ) : <span className="text-[#a8b5b0]">—</span>}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          {diffCount > 0 && (
            <Alert type="warn">
              <div className="font-medium mb-1">数据说明：系统重算结果与附件预置参考结果存在 {diffCount} 处差异</div>
              <div className="text-[12px] leading-relaxed">
                平台不会强行修改任何一方数据。差异主要来自三处：
                ① 附件的「销量贡献/毛利贡献」是独立计算的份额值，系统按份额最大值归一到 100 分；
                ② 附件的「坪效得分」口径与系统的 Min-Max 标准化不同；
                ③ 附件「周转天数」未做逆向标准化的可比化处理。
                表格中同时展示两者，便于核对模型口径。
              </div>
            </Alert>
          )}
        </div>
      )}

      {tab === 'radar' && (
        <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
          <div className="card">
            <div className="card-title">全部品类四维能力对比</div>
            <div className="p-4">
              <Chart
                option={{
                  tooltip: { ...TOOLTIP, trigger: 'item' },
                  legend: {
                    bottom: 0, type: 'scroll', itemWidth: 11, itemHeight: 7,
                    textStyle: { fontSize: 10 }, pageIconColor: '#257354',
                  },
                  radar: {
                    indicator: [
                      { name: '销量得分', max: 100 }, { name: '毛利得分', max: 100 },
                      { name: '周转得分', max: 100 }, { name: '坪效得分', max: 100 },
                    ],
                    radius: '60%', center: ['50%', '45%'],
                    axisName: { color: '#55665f', fontSize: 11 },
                    splitLine: { lineStyle: { color: '#e3e8e6' } },
                    splitArea: { areaStyle: { color: ['#fbfdfc', '#f5f8f7'] } },
                    axisLine: { lineStyle: { color: '#e3e8e6' } },
                  },
                  series: [{
                    type: 'radar',
                    data: rows.map((r, i) => ({
                      value: [r.sales_score, r.margin_score, r.turnover_score, r.space_score],
                      name: r.category,
                      lineStyle: { color: ['#257354', '#e8833a', '#4a7fb5', '#8bcbaa', '#d9a520', '#7a6bbf', '#5c8a76'][i % 7], width: 1.6 },
                      itemStyle: { color: ['#257354', '#e8833a', '#4a7fb5', '#8bcbaa', '#d9a520', '#7a6bbf', '#5c8a76'][i % 7] },
                      areaStyle: { opacity: 0.06 },
                    })),
                  }],
                }}
                height={420}
                title="7个品类在销量/毛利/周转/坪效四个标准化维度上的得分"
                onExport={() => {}}
              />
            </div>
          </div>

          <div className="card">
            <div className="card-title">得分构成堆叠图</div>
            <div className="p-4">
              <Chart option={barOption} height={420} title="各品类四维得分堆叠对比" onExport={() => {}} />
            </div>
          </div>
        </div>
      )}

      {tab === 'scatter' && (
        <div className="card">
          <div className="card-title">
            <span>库存周转 × 坪效 分布</span>
            <span className="text-[12px] text-[#6b7d76] font-normal">
              气泡大小 = 健康度 ｜ 虚线为风险阈值
            </span>
          </div>
          <div className="p-4">
            <Chart option={scatterOption} height={440} title="品类在周转效率与坪效上的定位" onExport={() => {}} />
            <div className="mt-3 grid grid-cols-1 md:grid-cols-3 gap-3">
              <div className="rounded-lg bg-[#f0f9f4] border border-brand-200 p-3">
                <div className="text-[12px] font-medium text-brand-800">左下象限（周转慢 + 坪效低）</div>
                <div className="text-[11.5px] text-brand-700 mt-1 leading-relaxed">
                  {rows.filter((r) => r.avg_turnover_days > 45 && r.avg_sales_per_sqm < 600).map((r) => r.category).join('、') || '无'}
                </div>
                <div className="text-[11px] text-brand-600/70 mt-1.5">资金占用重且坪效低，是精简与退出的重点对象</div>
              </div>
              <div className="rounded-lg bg-[#fff8ec] border border-[#f2dfb8] p-3">
                <div className="text-[12px] font-medium text-[#8a6212]">右上象限（周转快 + 坪效高）</div>
                <div className="text-[11.5px] text-[#a3700f] mt-1 leading-relaxed">
                  {rows.filter((r) => r.avg_turnover_days <= 45 && r.avg_sales_per_sqm >= 600).map((r) => r.category).join('、') || '无'}
                </div>
                <div className="text-[11px] text-[#a3700f]/70 mt-1.5">门店核心利润来源，应优先保障货源与陈列资源</div>
              </div>
              <div className="rounded-lg bg-[#eef2f0] border border-[#dde4e1] p-3">
                <div className="text-[12px] font-medium text-[#55665f]">需要关注</div>
                <div className="text-[11.5px] text-[#6b7d76] mt-1 leading-relaxed">
                  {rows.filter((r) => (r.avg_turnover_days > 45) !== (r.avg_sales_per_sqm < 600)).map((r) => r.category).join('、') || '无'}
                </div>
                <div className="text-[11px] text-[#8b9a94] mt-1.5">单一维度表现好但另一维度偏弱，需针对性优化</div>
              </div>
            </div>
          </div>
        </div>
      )}

      {tab === 'detail' && cur && (
        <div className="space-y-4">
          <div className="card">
            <div className="card-title">
              <span>选择品类查看诊断详情</span>
            </div>
            <div className="p-4 flex flex-wrap gap-2">
              {rows.map((r) => (
                <button
                  key={r.category_id}
                  onClick={() => setDetail(r)}
                  className={`px-3 py-1.5 rounded-lg border text-[13px] transition-all ${
                    cur.category === r.category
                      ? 'border-brand-500 bg-brand-50 text-brand-800 font-medium'
                      : 'border-[#d5ded9] text-[#3d5049] hover:border-brand-300'
                  }`}
                >
                  {r.category}
                  <span className="ml-1.5 text-[11px] tabular-nums" style={{ color: scoreColor(r.overall_score) }}>
                    {r.overall_score}
                  </span>
                </button>
              ))}
            </div>
          </div>

          <DetailPanel row={cur} />
        </div>
      )}
    </div>
  )
}

function DetailPanel({ row }: { row: any }) {
  // 趋势图需要按需拉取（只有单个品类的 12 个月序列）
  const [trend, setTrend] = useState<any>(null)
  const [full, setFull] = useState<any>(row)
  const [salesAgg, setSalesAgg] = useState<any>(row.sales_summary || null)
  const rowRef = useRef(row)
  rowRef.current = row

  useEffect(() => {
    setFull(rowRef.current)
    setSalesAgg(rowRef.current.sales_summary || null)
    setTrend(null)
    api.categoryHealth(rowRef.current.category_id).then((d) => {
      setTrend(d.trend)
      setFull(d.health)
      setSalesAgg(d.health?.sales_summary || null)
    }).catch(() => {})
  }, [row.category_id])

  const dims = [
    { label: '销量贡献', score: full.sales_score, weight: 0.3, desc: `销量份额 ${row.sales_contribution}%`, good: '越高越好' },
    { label: '毛利贡献', score: full.margin_score, weight: 0.3, desc: `毛利份额 ${row.margin_contribution}%`, good: '越高越好' },
    { label: '库存周转', score: full.turnover_score, weight: 0.2, desc: `平均 ${full.avg_turnover_days} 天`, good: '天数越低越好' },
    { label: '坪效', score: full.space_score, weight: 0.2, desc: `${full.avg_sales_per_sqm} 元/㎡/月`, good: '越高越好' },
  ]

  const trendOption = trend?.months ? {
    grid: { left: 55, right: 55, top: 40, bottom: 35 },
    tooltip: { ...TOOLTIP },
    legend: { top: 0, itemWidth: 12, itemHeight: 8, textStyle: { fontSize: 11 } },
    xAxis: { type: 'category', data: trend.months, ...AXIS_STYLE },
    yAxis: [
      { type: 'value', ...AXIS_STYLE, name: '销量/毛利' },
      { type: 'value', ...AXIS_STYLE, name: '周转/坪效', splitLine: { show: false } },
    ],
    series: [
      { name: '销量(件)', type: 'bar', data: trend.sales_qty, itemStyle: { color: '#8bcbaa' } },
      { name: '毛利额(元)', type: 'line', data: trend.gross_profit, smooth: true, itemStyle: { color: '#257354' }, lineStyle: { width: 2 } },
      { name: '坪效', type: 'line', yAxisIndex: 1, data: trend.sales_per_sqm, smooth: true, itemStyle: { color: '#e8833a' } },
      { name: '周转天数', type: 'line', yAxisIndex: 1, data: trend.turnover_days, smooth: true, itemStyle: { color: '#d94a4a' } },
    ],
  } : null

  return (
    <>
      <div className="grid grid-cols-1 xl:grid-cols-4 gap-4">
        {dims.map((d) => (
          <div key={d.label} className="card p-4">
            <div className="flex items-center justify-between">
              <span className="text-[12.5px] text-[#55665f] font-medium">{d.label}</span>
              <span className="tag bg-[#eef2f0] text-[#6b7d76] border border-[#dde4e1]">权重 {d.weight * 100}%</span>
            </div>
            <div className="text-[28px] font-semibold tabular-nums mt-1.5" style={{ color: scoreColor(d.score) }}>
              {d.score}
            </div>
            <div className="h-1.5 rounded-full bg-[#eef2f0] overflow-hidden mt-2">
              <div className="h-full rounded-full" style={{ width: `${d.score}%`, background: scoreColor(d.score) }} />
            </div>
            <div className="text-[11.5px] text-[#6b7d76] mt-2">{d.desc}</div>
            <div className="text-[10.5px] text-[#a8b5b0]">{d.good}</div>
          </div>
        ))}
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-3 gap-4">
        <div className="card xl:col-span-1">
          <div className="card-title">{row.category} 综合诊断</div>
          <div className="p-4 space-y-4">
            <div className="flex items-center gap-4">
              <div
                className="w-[84px] h-[84px] rounded-full flex items-center justify-center flex-shrink-0"
                style={{ background: `${scoreColor(row.overall_score)}15`, border: `2px solid ${scoreColor(row.overall_score)}` }}
              >
                <div className="text-center">
                  <div className="text-[22px] font-bold tabular-nums leading-none" style={{ color: scoreColor(row.overall_score) }}>
                    {row.overall_score}
                  </div>
                  <div className="text-[10px] text-[#8b9a94] mt-0.5">综合得分</div>
                </div>
              </div>
              <div className="min-w-0">
                <div className="text-[15px] font-semibold text-[#1a2b24]">{row.category}</div>
                <div className="text-[13px] text-[#55665f]">{row.grade} · 第 {row.rank} 名</div>
                <div className="text-[15px] text-[#b8860b] tracking-widest">{row.stars}</div>
                {row.below_three_star && (
                  <span className="tag bg-[#fdf0f0] text-[#c13f3f] border border-[#f0cccc] mt-1">需重点优化</span>
                )}
              </div>
            </div>

            <div className="grid grid-cols-2 gap-2 text-[12.5px]">
              {[
                ['销售额', fmt.money(salesAgg?.total_amount)],
                ['毛利额', fmt.money(salesAgg?.total_profit)],
                ['平均周转', `${full.avg_turnover_days} 天`],
                ['平均坪效', `${full.avg_sales_per_sqm}`],
                ['缺货次数', `${full.total_stockout} 次`],
                ['SKU规模', `${full.sku_count} 个`],
              ].map(([k, v]) => (
                <div key={k} className="rounded-md bg-[#f7faf9] px-2.5 py-2">
                  <div className="text-[11px] text-[#8b9a94]">{k}</div>
                  <div className="text-[13px] font-medium text-[#2c3d36] tabular-nums">{v}</div>
                </div>
              ))}
            </div>

            <div>
              <div className="text-[12px] font-medium text-[#55665f] mb-1">销量趋势 / 毛利趋势</div>
              <div className="flex gap-3 text-[12.5px]">
                <span>销量 {full.sales_trend != null ? fmt.signPct(full.sales_trend) : '数据不足'}</span>
                <span>毛利 {full.margin_trend != null ? fmt.signPct(full.margin_trend) : '数据不足'}</span>
              </div>
            </div>

            <div>
              <div className="text-[12px] font-medium text-[#55665f] mb-1">诊断结论</div>
              <div className="text-[12.5px] text-[#3d5049] leading-relaxed bg-[#f7faf9] rounded-md px-3 py-2.5">
                {row.diagnosis}
              </div>
            </div>

            <div>
              <div className="text-[12px] font-medium text-[#55665f] mb-1">优化建议</div>
              <div className="text-[12.5px] text-[#3d5049] leading-relaxed bg-brand-50 rounded-md px-3 py-2.5 border border-brand-200">
                {row.suggestion}
              </div>
            </div>
          </div>
        </div>

        <div className="card xl:col-span-2">
          <div className="card-title">{row.category} 12个月趋势</div>
          <div className="p-4">
            {trendOption ? (
              <Chart option={trendOption} height={380} title="销量/毛利/坪效/周转的12个月走势" onExport={() => {}} />
            ) : (
              <div className="text-[13px] text-[#8b9a94] py-12 text-center">趋势数据加载中…</div>
            )}
          </div>
        </div>
      </div>

      {row.attachment_reference && (
        <div className="card">
          <div className="card-title">
            <span>数据说明：系统重算 vs 附件预置参考</span>
            <DemoBadge text="两者均原样保留，平台不修改任一方" />
          </div>
          <div className="p-4">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div className="rounded-lg border border-brand-200 bg-brand-50 p-4">
                <div className="flex items-center justify-between mb-2">
                  <span className="text-[13px] font-medium text-brand-800">系统重算结果</span>
                  <span className="tag bg-white text-brand-700 border border-brand-300">系统实时计算</span>
                </div>
                <div className="text-[24px] font-bold tabular-nums text-brand-700">{row.overall_score} 分</div>
                <div className="text-[12.5px] text-brand-800/80 mt-1">{row.grade} · {row.stars}</div>
                <div className="text-[12px] text-brand-700/70 mt-2">优化建议：{row.suggestion}</div>
              </div>
              <div className="rounded-lg border border-[#d3def5] bg-[#eef2fb] p-4">
                <div className="flex items-center justify-between mb-2">
                  <span className="text-[13px] font-medium text-[#2d5588]">附件预置参考结果</span>
                  <span className="tag bg-white text-[#3a5a9a] border border-[#d3def5]">附件原值</span>
                </div>
                <div className="text-[24px] font-bold tabular-nums text-[#2d5588]">
                  {row.attachment_reference.overall_score} 分
                </div>
                <div className="text-[12.5px] text-[#2d5588]/80 mt-1">
                  {row.attachment_reference.grade} · {row.attachment_reference.stars}
                </div>
                <div className="text-[12px] text-[#2d5588]/70 mt-2">
                  优化建议：{row.attachment_reference.suggestion}
                </div>
              </div>
            </div>
            <Alert type="info">
              <div className="font-medium mb-1">差异值：{row.diff_vs_attachment > 0 ? '+' : ''}{row.diff_vs_attachment} 分</div>
              <div className="text-[12px] leading-relaxed">
                差异来源：① 贡献度归一化口径不同（附件按独立份额，系统按份额最大值归一）；
                ② 坪效得分算法不同（附件为独立评分，系统为 Min-Max 标准化）；
                ③ 周转维度处理方式不同（附件未做逆向标准化的可比化处理）。
                平台保持两者原样，便于核对模型口径差异。
              </div>
            </Alert>
          </div>
        </div>
      )}
    </>
  )
}
