import { useEffect, useState } from 'react'
import { Chart, AXIS_STYLE, TOOLTIP } from '../components/Chart'
import { Alert, DemoBadge, Empty, ErrorBox, Loading, StatCard, Tabs } from '../components/ui'
import { api, fmt } from '../services/api'

/**
 * 日期维度与天气影响分析
 *
 * 展示三个日期维度（星期／月份／月内旬）的销量规律，输出备货与排班参考。
 *
 * 天气部分的处理方式：
 * 附件数据集不含温度、湿度、降水字段，因此这些分析不产出结论，
 * 页面显式标注「待接入」并列出缺失字段。平台不用估算值填充——
 * 天气与销量之间没有可验证的关系时，给出的任何「关联」都是猜测。
 */

interface Advice {
  dimension: string
  headline: string
  action: string
  evidence: string
}

export default function DatePattern() {
  const [tab, setTab] = useState('weekday')
  const [status, setStatus] = useState<any>(null)
  const [patterns, setPatterns] = useState<any>(null)
  const [advice, setAdvice] = useState<any>(null)
  const [daily, setDaily] = useState<any[]>([])
  const [cats, setCats] = useState<any[]>([])
  const [catId, setCatId] = useState<number | undefined>(undefined)
  const [err, setErr] = useState('')
  const [busy, setBusy] = useState(false)
  const [msg, setMsg] = useState('')

  const loadAll = () => {
    setErr('')
    api.datePatternStatus().then(setStatus).catch((e) => setErr(e.message))
    api.categories().then((d: any) => setCats(d.items || d || [])).catch(() => {})
  }
  const loadAnalysis = () => {
    setErr('')
    api.datePatterns(catId).then(setPatterns).catch((e) => setErr(e.message))
    api.dateAdvice(catId).then(setAdvice).catch((e) => setErr(e.message))
    api.dateDaily(catId, 180).then((d: any) => setDaily(d.rows || [])).catch((e) => setErr(e.message))
  }

  useEffect(loadAll, [])
  useEffect(loadAnalysis, [catId])

  const rebuild = async () => {
    setBusy(true); setMsg('')
    try {
      const d = await api.rebuildDatePattern()
      setStatus((s: any) => ({ ...s, aggregated: true, rows: d.rows, days: d.days, date_from: d.date_from, date_to: d.date_to }))
      setMsg(`已生成 ${d.rows} 条记录，覆盖 ${d.days} 天（${d.date_from} 至 ${d.date_to}）`)
      loadAnalysis()
    } catch (e: any) {
      setErr(e.message)
    } finally {
      setBusy(false)
    }
  }

  if (err) return <ErrorBox message={err} onRetry={loadAll} />
  if (!status) return <Loading />

  if (!status.aggregated) {
    return (
      <div className="space-y-4">
        <div className="flex items-center gap-3">
          <h1 className="text-xl font-semibold text-gray-900">日期维度与天气影响</h1>
          <DemoBadge />
        </div>
        <Empty
          title="尚未生成日期维度数据"
          hint="从交易明细聚合「品类 × 日」的销售事实后，才能分析星期、月份等日期规律"
          action={
            <button className="btn-primary" onClick={rebuild} disabled={busy}>
              {busy ? '聚合中…' : '生成日期维度数据'}
            </button>
          }
        />
      </div>
    )
  }

  const w = status.weather || {}
  const p = patterns || {}
  const advices: Advice[] = advice?.advices || []

  // ---- 星期效应图 ----
  const weekdayOption = p.weekday?.length ? {
    grid: { left: 46, right: 20, top: 30, bottom: 30 },
    tooltip: { ...TOOLTIP, trigger: 'axis' },
    xAxis: { type: 'category', data: p.weekday.map((x: any) => x.name), ...AXIS_STYLE },
    yAxis: { type: 'value', name: '日均销量（件）', ...AXIS_STYLE },
    series: [{
      type: 'bar',
      data: p.weekday.map((x: any) => ({
        value: x.avg_qty,
        itemStyle: { color: x.day_type === 'weekend' ? '#e8833a' : '#57ad84' },
      })),
      label: { show: true, position: 'top', fontSize: 10, formatter: (x: any) => x.value },
    }],
  } : null

  // ---- 月份效应图 ----
  const monthOption = p.month?.length ? {
    grid: { left: 52, right: 20, top: 30, bottom: 40 },
    tooltip: { ...TOOLTIP, trigger: 'axis' },
    xAxis: { type: 'category', data: p.month.map((x: any) => x.month.slice(5) + '月'), ...AXIS_STYLE },
    yAxis: { type: 'value', name: '日均销量（件）', ...AXIS_STYLE },
    series: [{
      type: 'bar',
      data: p.month.map((x: any) => ({
        value: x.avg_qty,
        itemStyle: { color: x.index >= 100 ? '#257354' : '#8fbfa8' },
      })),
      label: { show: true, position: 'top', fontSize: 10 },
    }],
  } : null

  // ---- 旬效应图 ----
  const tenDayOption = p.ten_day?.length ? {
    grid: { left: 52, right: 20, top: 30, bottom: 30 },
    tooltip: { ...TOOLTIP, trigger: 'axis' },
    xAxis: { type: 'category', data: p.ten_day.map((x: any) => x.segment), ...AXIS_STYLE },
    yAxis: { type: 'value', name: '日均销量（件）', ...AXIS_STYLE },
    series: [{
      type: 'bar',
      data: p.ten_day.map((x: any) => x.avg_qty),
      label: { show: true, position: 'top', fontSize: 10 },
      itemStyle: { color: '#4a9e7d' },
    }],
  } : null

  // ---- 日销量趋势 ----
  const trendOption = daily.length ? {
    grid: { left: 56, right: 20, top: 30, bottom: 46 },
    tooltip: { ...TOOLTIP, trigger: 'axis' },
    xAxis: {
      type: 'category',
      data: daily.map((d: any) => d.date.slice(5)),
      ...AXIS_STYLE,
      axisLabel: { ...AXIS_STYLE.axisLabel, interval: Math.floor(daily.length / 10) },
    },
    yAxis: { type: 'value', name: '销量（件）', ...AXIS_STYLE },
    series: [{
      type: 'line',
      data: daily.map((d: any) => d.sales_qty),
      smooth: true,
      symbol: 'none',
      lineStyle: { width: 2, color: '#257354' },
      areaStyle: { color: 'rgba(87,173,132,0.12)' },
    }],
  } : null

  return (
    <div className="space-y-5">
      {/* 标题行 */}
      <div className="flex items-center gap-3 flex-wrap">
        <h1 className="text-xl font-semibold text-gray-900">日期维度与天气影响</h1>
        <DemoBadge />
        <span className="text-[12px] text-gray-500">
          {status.date_from} 至 {status.date_to}（{status.days} 天 · {status.rows} 条记录）
        </span>
        <div className="ml-auto flex items-center gap-2">
          <select
            className="input text-[13px] py-1.5"
            value={catId ?? ''}
            onChange={(e) => setCatId(e.target.value ? Number(e.target.value) : undefined)}
          >
            <option value="">全平台（9 个品类）</option>
            {cats.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
          </select>
          <button className="btn bg-white border border-gray-300 text-[13px]" onClick={rebuild} disabled={busy}>
            {busy ? '重新聚合…' : '重新聚合'}
          </button>
        </div>
      </div>

      {msg && <Alert type="success">{msg}</Alert>}

      {/* 天气未接入提示 */}
      {!w.available && (
        <Alert type="warn">
          <div className="space-y-1.5">
            <div className="font-medium">天气影响分析暂不可用：{w.reason}</div>
            <div className="text-[13px]">
              缺失字段：{(w.missing_fields || []).join('、')}。
              附件数据集不含气象数据，平台不使用估算值填充——
              在没有实测温度与湿度的情况下，给出的「天气与销量关联」无法验证。
            </div>
            <div className="text-[12px] text-gray-600">{w.how_to_enable}</div>
          </div>
        </Alert>
      )}

      {/* 关键指标 */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        <StatCard
          label="星期效应波动"
          value={`${p.weekday_spread_pct ?? '—'}%`}
          hint={p.weekday_signal ? '显著，可按星期备货' : '不显著，不建议按星期调整'}
        />
        <StatCard
          label="月份效应波动"
          value={`${p.month_spread_pct ?? '—'}%`}
          hint={p.month_signal ? '显著，可按月份备货' : '不显著，不建议按月份调整'}
        />
        <StatCard
          label="月内旬波动"
          value={`${p.ten_day_spread_pct ?? '—'}%`}
          hint={p.ten_day_signal ? '显著，可按旬备货' : '不显著'}
        />
        <StatCard
          label="周末／工作日"
          value={p.weekend_vs_weekday != null ? `${p.weekend_vs_weekday} 倍` : '—'}
          hint="1.0 表示两者无差异"
        />
      </div>

      {/* 备货建议 */}
      <div className="card">
        <div className="card-header">备货与排班参考{advice?.category ? `（${advice.category}）` : '（全平台）'}</div>
        <div className="p-4 space-y-3">
          {advices.length === 0 ? (
            <div className="text-[13px] text-gray-500">暂无建议</div>
          ) : (
            advices.map((a, i) => (
              <div key={i} className="border-l-2 border-brand-400 pl-3 py-1">
                <div className="flex items-center gap-2 mb-1">
                  <span className="text-[11px] px-1.5 py-0.5 rounded bg-brand-50 text-brand-700 font-medium">
                    {a.dimension}
                  </span>
                  <span className="text-[13.5px] font-medium text-gray-900">{a.headline}</span>
                </div>
                <div className="text-[13px] text-gray-700 leading-relaxed">{a.action}</div>
                <div className="text-[12px] text-gray-500 mt-0.5">依据：{a.evidence}</div>
              </div>
            ))
          )}
          <div className="text-[12px] text-gray-500 pt-2 border-t border-gray-100">
            建议阈值：日均波动需超过 {p.restock_threshold_pct ?? 10}% 才具备备货意义。
            低于阈值时平台不给出调整建议——按日均统一备货更简单，也更不容易出错。
          </div>
        </div>
      </div>

      {/* 图表区 */}
      <div className="card">
        <div className="card-header pb-2">
          <Tabs
            items={[
              { key: 'weekday', label: '星期规律' },
              { key: 'month', label: '月份规律' },
              { key: 'tenday', label: '月内旬' },
              { key: 'trend', label: '日销量趋势' },
            ]}
            active={tab}
            onChange={setTab}
          />
        </div>
        <div className="p-4">
          {tab === 'weekday' && (
            <>
              <div className="text-[12.5px] text-gray-600 mb-3 leading-relaxed">
                同一星期几跨多周，需先按「该星期几的总销量 ÷ 该星期几的天数」求日均，
                再比较。图中橙色为周末。
              </div>
              {weekdayOption ? <Chart option={weekdayOption} height={280} /> : <div className="text-[13px] text-gray-500">无数据</div>}
              <table className="table mt-4">
                <thead>
                  <tr><th>星期</th><th>类型</th><th className="text-right">日均销量</th><th className="text-right">指数</th><th className="text-right">样本天数</th></tr>
                </thead>
                <tbody>
                  {(p.weekday || []).map((x: any) => (
                    <tr key={x.weekday}>
                      <td className="font-medium">{x.name}</td>
                      <td>
                        <span className={`text-[11px] px-1.5 py-0.5 rounded ${x.day_type === 'weekend' ? 'bg-orange-50 text-orange-700' : 'bg-gray-100 text-gray-600'}`}>
                          {x.day_type === 'weekend' ? '周末' : '工作日'}
                        </span>
                      </td>
                      <td className="text-right tabular-nums">{x.avg_qty}</td>
                      <td className="text-right tabular-nums font-medium" style={{ color: x.index >= 100 ? '#257354' : '#8a8a8a' }}>
                        {x.index}
                      </td>
                      <td className="text-right tabular-nums text-gray-500">{x.sample_days}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </>
          )}

          {tab === 'month' && (
            <>
              <div className="text-[12.5px] text-gray-600 mb-3 leading-relaxed">
                <strong>按日均口径计算</strong>，不按月总量——各月天数不同，
                用总量比较会把天数差异误读为需求差异。指数 100 为各月日均的基准。
              </div>
              {monthOption ? <Chart option={monthOption} height={280} /> : <div className="text-[13px] text-gray-500">无数据</div>}
            </>
          )}

          {tab === 'tenday' && (
            <>
              <div className="text-[12.5px] text-gray-600 mb-3 leading-relaxed">
                上旬（1—10 日）、中旬（11—20 日）、下旬（21 日至月末）。
                本数据集每月固定为 28 天，因此不做大小月对比。
              </div>
              {tenDayOption ? <Chart option={tenDayOption} height={280} /> : <div className="text-[13px] text-gray-500">无数据</div>}
            </>
          )}

          {tab === 'trend' && (
            <>
              <div className="text-[12.5px] text-gray-600 mb-3">
                日销量序列（{daily.length} 天）。所有指标由交易明细实时聚合，不含估算值。
              </div>
              {trendOption ? <Chart option={trendOption} height={300} /> : <div className="text-[13px] text-gray-500">无数据</div>}
            </>
          )}
        </div>
      </div>

      {/* 口径说明 */}
      <div className="card">
        <div className="card-header">计算口径</div>
        <div className="p-4 space-y-2 text-[12.5px] text-gray-600 leading-relaxed">
          <div>
            <strong>数据来源</strong>：由 {status.rows.toLocaleString()} 条交易明细实时聚合，
            覆盖 {status.days} 天。所有数值可用同一份附件数据复算。
          </div>
          <div>
            <strong>日均口径</strong>：各维度均按「日均」计算，消除天数差异影响。
            这是本章与「按月总量对比」最关键的区别。
          </div>
          <div>
            <strong>指数口径</strong>：以各维度日均的算术平均为 100。
            指数 105 表示高于均值 5%。
          </div>
          <div>
            <strong>天气维度</strong>：表结构已预留温度、湿度、降水字段，
            气象数据接入后本模块自动启用分析，无需修改结构。当前未接入，平台不输出任何天气相关结论。
          </div>
        </div>
      </div>
    </div>
  )
}
