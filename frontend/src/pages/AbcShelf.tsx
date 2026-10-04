import { useEffect, useState } from 'react'
import { Chart, AXIS_STYLE, TOOLTIP, PALETTE } from '../components/Chart'
import { Alert, DemoBadge, Empty, ErrorBox, Loading, Tabs } from '../components/ui'
import { api, fmt } from '../services/api'

export default function AbcShelf() {
  const [tab, setTab] = useState('abc')
  const [abc, setAbc] = useState<any>(null)
  const [shelf, setShelf] = useState<any>(null)
  const [err, setErr] = useState('')
  const [busy, setBusy] = useState(false)
  const [msg, setMsg] = useState('')
  const [thresholds, setThresholds] = useState({ a: 0.7, b: 0.9 })
  const [area, setArea] = useState(20)
  const [alpha, setAlpha] = useState(0.65)

  const loadAbc = () => {
    setErr('')
    api.abc().then(setAbc).catch((e) => setErr(e.message))
  }
  const loadShelf = () => {
    api.optimizeShelf({ total_area: area, alpha, save: false })
      .then(setShelf)
      .catch((e) => setErr(e.message))
  }
  useEffect(loadAbc, [])
  useEffect(loadShelf, [])

  const recalc = async () => {
    setBusy(true); setMsg('')
    try {
      const d = await api.recalcAbc({ a_threshold: thresholds.a, b_threshold: thresholds.b, save: true })
      setAbc(d)
      setMsg(d.summary)
    } catch (e: any) {
      setErr(e.message)
    } finally {
      setBusy(false)
    }
  }

  if (err && !abc) return <ErrorBox message={err} onRetry={loadAbc} />
  if (!abc) return <Loading text="正在计算 ABC 分类…" />

  // ---------- ABC 图表 ----------
  const abcBarOption = {
    grid: { left: 150, right: 60, top: 30, bottom: 40 },
    tooltip: {
      ...TOOLTIP,
      formatter: (p: any) => {
        const r = abc.rows[p.dataIndex]
        return `${r.name}（${r.category}）<br/>${r.abc_class}类<br/>销售额 <b>${fmt.money(r.sales_amount)}</b><br/>占比 ${r.share_pct}%<br/>累计 ${r.cumulative_pct}%`
      },
    },
    legend: { top: 0, itemWidth: 12, itemHeight: 8, textStyle: { fontSize: 11 } },
    xAxis: { type: 'value', ...AXIS_STYLE, name: '销售额（元）' },
    yAxis: {
      type: 'category',
      data: [...abc.rows].reverse().map((r: any) => r.name),
      ...AXIS_STYLE, splitLine: { show: false },
      axisLabel: { ...AXIS_STYLE.axisLabel, fontSize: 10 },
    },
    series: [
      {
        name: 'A类 核心', type: 'bar', stack: 'x',
        data: [...abc.rows].reverse().map((r: any) => ({
          value: r.abc_class === 'A' ? r.sales_amount : 0,
          itemStyle: { color: '#257354' },
        })),
        barWidth: 12,
      },
      {
        name: 'B类 次要', type: 'bar', stack: 'x',
        data: [...abc.rows].reverse().map((r: any) => ({
          value: r.abc_class === 'B' ? r.sales_amount : 0,
          itemStyle: { color: '#4a7fb5' },
        })),
      },
      {
        name: 'C类 长尾', type: 'bar', stack: 'x',
        data: [...abc.rows].reverse().map((r: any) => ({
          value: r.abc_class === 'C' ? r.sales_amount : 0,
          itemStyle: { color: '#d9a520', borderRadius: [0, 4, 4, 0] },
        })),
      },
    ],
  }

  const paretoOption = {
    grid: { left: 50, right: 50, top: 40, bottom: 40 },
    tooltip: { ...TOOLTIP },
    legend: { top: 0, itemWidth: 12, itemHeight: 8, textStyle: { fontSize: 11 } },
    xAxis: { type: 'category', data: abc.rows.map((r: any) => r.name), ...AXIS_STYLE, axisLabel: { show: false } },
    yAxis: [
      { type: 'value', ...AXIS_STYLE, name: '销售额' },
      { type: 'value', ...AXIS_STYLE, name: '累计%', max: 100, splitLine: { show: false } },
    ],
    series: [
      {
        name: '销售额', type: 'bar', data: abc.rows.map((r: any) => r.sales_amount),
        itemStyle: { color: '#8bcbaa' }, barWidth: '60%',
      },
      {
        name: '累计占比', type: 'line', yAxisIndex: 1,
        data: abc.rows.map((r: any) => r.cumulative_pct),
        itemStyle: { color: '#e8833a' }, lineStyle: { width: 2 }, symbolSize: 4,
        markLine: {
          silent: true, symbol: 'none',
          lineStyle: { color: '#d94a4a', type: 'dashed' },
          data: [{ yAxis: 70, label: { formatter: 'A/B 分界 70%', fontSize: 10, color: '#8b9a94' } }],
        },
      },
    ],
  }

  // ---------- 货架图表 ----------
  const shelfOption = shelf ? {
    grid: { left: 90, right: 60, top: 30, bottom: 40 },
    tooltip: {
      ...TOOLTIP,
      formatter: (p: any) => {
        const r = shelf.items[p.dataIndex]
        return `${r.name}（${r.category}）<br/>建议面积 <b>${r.suggest_area} ㎡</b>（${r.share_pct}%）<br/>单位面积产出 ${fmt.n(r.sales_per_sqm)} 元/㎡`
      },
    },
    xAxis: { type: 'value', ...AXIS_STYLE, name: '单位面积产出（元/㎡）' },
    yAxis: {
      type: 'category',
      data: [...shelf.items].reverse().map((r: any) => r.name),
      ...AXIS_STYLE, splitLine: { show: false },
      axisLabel: { ...AXIS_STYLE.axisLabel, fontSize: 10 },
    },
    series: [{
      type: 'bar',
      data: [...shelf.items].reverse().map((r: any) => ({
        value: r.sales_per_sqm,
        itemStyle: {
          color: r.sales_per_sqm > (shelf.summary.avg_sales_per_sqm || 0) * 1.5 ? '#257354'
            : r.sales_per_sqm < (shelf.summary.avg_sales_per_sqm || 0) * 0.7 ? '#d9a520' : '#8bcbaa',
          borderRadius: [0, 4, 4, 0],
        },
      })),
      barWidth: 12,
      label: {
        show: true, position: 'right', fontSize: 9, color: '#6b7d76',
        formatter: (p: any) => `${p.value.toLocaleString()}`,
      },
    }],
  } : null

  const pieOption = shelf ? {
    tooltip: { ...TOOLTIP, trigger: 'item', formatter: '{b}: {c}㎡ ({d}%)' },
    legend: { type: 'scroll', bottom: 0, itemWidth: 11, itemHeight: 7, textStyle: { fontSize: 10 } },
    series: [{
      type: 'pie',
      radius: ['38%', '66%'],
      center: ['50%', '44%'],
      itemStyle: { borderColor: '#fff', borderWidth: 1 },
      label: { show: false },
      data: shelf.items.filter((r: any) => r.share_pct >= 1.2).map((r: any) => ({
        name: r.name,
        value: Number(r.suggest_area.toFixed(3)),
      })),
    }],
  } : null

  return (
    <div className="space-y-4 max-w-[1680px]">
      <div className="flex items-center justify-between gap-4 flex-wrap">
        <div>
          <h1 className="text-[19px] font-semibold text-[#1a2b24]">小类结构分析</h1>
          <p className="text-[12.5px] text-[#6b7d76] mt-0.5">
            ABC 分类定位商品价值层级 ｜ 货架空间优化解决面积分配
          </p>
        </div>
        <DemoBadge text="小类指标由 22022 条交易明细实时聚合" />
      </div>

      {msg && <Alert type="success">{msg}</Alert>}
      {err && <ErrorBox message={err} />}

      <Tabs
        active={tab}
        onChange={setTab}
        items={[
          { key: 'abc', label: 'ABC 分类' },
          { key: 'shelf', label: '货架空间优化' },
        ]}
      />

      {/* ============ ABC ============ */}
      {tab === 'abc' && abc.success && (
        <>
          <Alert type="info">
            <div className="font-medium mb-1">{abc.method}</div>
            <div className="text-[12px] leading-relaxed">{abc.method_note}</div>
          </Alert>

          {abc.data_limitation && (
            <Alert type="warn">
              <div className="font-medium mb-1">数据区分度提示</div>
              <div className="text-[12px] leading-relaxed">{abc.data_limitation}</div>
            </Alert>
          )}

          <Alert type="success">
            <div className="font-medium mb-1">分类结果</div>
            <div className="text-[12.5px]">{abc.summary}</div>
          </Alert>

          {/* 三类概览 */}
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-3">
            {abc.classes.map((c: any) => (
              <div key={c.class} className="card border-l-[3px]" style={{ borderLeftColor: c.color }}>
                <div className="p-4">
                  <div className="flex items-center justify-between mb-2">
                    <span className="text-[14px] font-semibold" style={{ color: c.color }}>{c.name}</span>
                    <span className="tag" style={{ background: `${c.color}15`, color: c.color }}>{c.ratio_desc}</span>
                  </div>
                  <div className="grid grid-cols-3 gap-2 mb-2.5">
                    {[
                      ['商品数', c.count],
                      ['占商品数', `${c.count_pct}%`],
                      ['销售额占比', `${c.sales_pct}%`],
                    ].map(([k, v]) => (
                      <div key={k as string} className="rounded-md bg-[#f7faf9] px-2 py-1.5">
                        <div className="text-[10.5px] text-[#8b9a94]">{k}</div>
                        <div className="text-[14px] font-semibold tabular-nums" style={{ color: c.color }}>{v}</div>
                      </div>
                    ))}
                  </div>
                  <div className="text-[12px] text-[#55665f] leading-relaxed mb-2">{c.description}</div>
                  <div className="text-[12px] text-[#3d5049] leading-relaxed bg-[#f7faf9] rounded-md px-2.5 py-2 mb-2">
                    <b>策略：</b>{c.advice}
                  </div>
                  <div className="text-[11.5px] text-[#8b9a94]">
                    <b>库存策略：</b>{c.inventory_policy}
                  </div>
                  <details className="mt-2.5">
                    <summary className="text-[12px] text-brand-600 cursor-pointer hover:underline">
                      查看 {c.count} 个商品（户均 {fmt.money(c.avg_amount_per_item)}）
                    </summary>
                    <div className="flex flex-wrap gap-1 mt-2">
                      {c.items.map((it: any) => (
                        <span key={it.name} className="tag bg-white text-[#55665f] border border-[#dde4e1] text-[11px]">
                          {it.name}
                          <span className="ml-1 text-[#a8b5b0]">{it.share_pct}%</span>
                        </span>
                      ))}
                    </div>
                  </details>
                </div>
              </div>
            ))}
          </div>

          {/* 阈值调节 */}
          <div className="card">
            <div className="card-title">
              <span>分类阈值</span>
              <button className="btn-primary" onClick={recalc} disabled={busy}>
                {busy ? '计算中…' : '按当前阈值重算'}
              </button>
            </div>
            <div className="p-4 grid grid-cols-1 md:grid-cols-3 gap-4">
              {[
                ['A 类累计上限', thresholds.a, 0.4, 0.9, 0.05, (v: number) => setThresholds({ ...thresholds, a: v })],
                ['B 类累计上限', thresholds.b, 0.6, 0.98, 0.02, (v: number) => setThresholds({ ...thresholds, b: v })],
              ].map(([label, val, min, max, step, setter]: any) => (
                <div key={label}>
                  <div className="flex items-center justify-between mb-1.5">
                    <label className="label mb-0">{label}</label>
                    <span className="text-[13px] font-medium text-brand-700 tabular-nums">
                      {(Number(val) * 100).toFixed(0)}%
                    </span>
                  </div>
                  <input
                    type="range" min={min} max={max} step={step} value={val}
                    onChange={(e) => setter(Number(e.target.value))}
                    className="w-full accent-[#257354]"
                  />
                </div>
              ))}
              <div className="text-[11.5px] text-[#8b9a94] self-end leading-relaxed">
                默认 70% / 90%，即经典的「二八法则」：
                前 70% 销售额由 A 类贡献。B 类上限决定 C 类的起点。
              </div>
            </div>
          </div>

          <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
            <div className="card">
              <div className="card-title">ABC 分布（按销售额）</div>
              <div className="p-4">
                <Chart option={abcBarOption} height={400} title="70个小类的销售额与ABC归属" onExport={() => {}} />
              </div>
            </div>
            <div className="card">
              <div className="card-title">帕累托分析</div>
              <div className="p-4">
                <Chart option={paretoOption} height={400} title="销售额柱状图 + 累计占比折线（帕累托图）" onExport={() => {}} />
              </div>
            </div>
          </div>

          <div className="card overflow-hidden">
            <div className="card-title">小类 ABC 明细（{abc.total_items} 个）</div>
            <div className="overflow-x-auto max-h-[560px] overflow-y-auto">
              <table className="w-full min-w-[820px]">
                <thead className="sticky top-0">
                  <tr>
                    <th className="table-th">#</th>
                    <th className="table-th">小类</th>
                    <th className="table-th">所属大类</th>
                    <th className="table-th">分类</th>
                    <th className="table-th text-right">销售额</th>
                    <th className="table-th text-right">占比</th>
                    <th className="table-th text-right">累计占比</th>
                    <th className="table-th text-right">销量(件)</th>
                  </tr>
                </thead>
                <tbody>
                  {abc.rows.map((r: any, i: number) => (
                    <tr key={r.name} className="hover:bg-[#f9fbfb]">
                      <td className="table-td tabular-nums text-[#8b9a94]">{i + 1}</td>
                      <td className="table-td font-medium">{r.name}</td>
                      <td className="table-td text-[12px]">{r.category}</td>
                      <td className="table-td">
                        <span
                          className="tag"
                          style={{
                            background: r.abc_class === 'A' ? '#f0f9f4' : r.abc_class === 'B' ? '#eef4fb' : '#fffaf0',
                            color: r.abc_class === 'A' ? '#257354' : r.abc_class === 'B' ? '#2d5588' : '#a3700f',
                          }}
                        >
                          {r.abc_class}类
                        </span>
                      </td>
                      <td className="table-td text-right tabular-nums">{fmt.money(r.sales_amount)}</td>
                      <td className="table-td text-right tabular-nums">{r.share_pct}%</td>
                      <td className="table-td text-right tabular-nums text-[#8b9a94]">{r.cumulative_pct}%</td>
                      <td className="table-td text-right tabular-nums">{fmt.n(r.sales_qty)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          {abc.data_discrimination && (
            <div className="card">
              <div className="card-title">数据区分度诊断</div>
              <div className="p-4">
                <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                  {Object.values(abc.data_discrimination).map((d: any) => (
                    <div
                      key={d.label}
                      className={`rounded-lg border p-3.5 ${
                        d.low ? 'border-[#f2dfb8] bg-[#fffdf8]' : 'border-[#e9eeec] bg-[#f7faf9]'
                      }`}
                    >
                      <div className="flex items-center justify-between mb-1.5">
                        <span className="text-[12.5px] font-medium text-[#2c3d36]">{d.label}</span>
                        {d.low ? (
                          <span className="tag bg-[#fff8ec] text-[#a3700f] border border-[#f2dfb8]">区分度偏低</span>
                        ) : (
                          <span className="tag bg-brand-50 text-brand-700 border border-brand-200">正常</span>
                        )}
                      </div>
                      <div className="text-[11.5px] text-[#6b7d76] space-y-0.5">
                        <div>最小 {d.min} ｜ 中位 {d.median} ｜ 最大 {d.max}</div>
                        <div className="font-medium text-[#3d5049]">极差比 {d.ratio} 倍</div>
                      </div>
                    </div>
                  ))}
                </div>
                <div className="mt-3.5">
                  <Alert type="info">
                    平台会在每次分类时自动计算数据的区分度并如实展示。
                    若真实数据接入后销量差距显著扩大，A/B/C 三档的区分会更明显，
                    分类结果会更贴近实际经营分层。
                  </Alert>
                </div>
              </div>
            </div>
          )}
        </>
      )}

      {tab === 'abc' && !abc.success && (
        <Empty title={abc.message} hint={abc.missing_data?.join('、')} />
      )}

      {/* ============ 货架 ============ */}
      {tab === 'shelf' && shelf && (
        <>
          <div className="card">
            <div className="card-title">
              <span>货架参数</span>
              <button className="btn-primary" onClick={loadShelf}>重新计算</button>
            </div>
            <div className="p-4 grid grid-cols-1 md:grid-cols-3 gap-4">
              <div>
                <div className="flex items-center justify-between mb-1.5">
                  <label className="label mb-0">总货架面积</label>
                  <span className="text-[13px] font-medium text-brand-700 tabular-nums">{area} ㎡</span>
                </div>
                <input
                  type="range" min={5} max={60} step={1} value={area}
                  onChange={(e) => setArea(Number(e.target.value))}
                  className="w-full accent-[#257354]"
                />
                <div className="text-[11px] text-[#8b9a94]">拖动后点「重新计算」</div>
              </div>
              <div>
                <div className="flex items-center justify-between mb-1.5">
                  <label className="label mb-0">平滑系数 α</label>
                  <span className="text-[13px] font-medium text-brand-700 tabular-nums">{alpha}</span>
                </div>
                <input
                  type="range" min={0.1} max={1} step={0.05} value={alpha}
                  onChange={(e) => setAlpha(Number(e.target.value))}
                  className="w-full accent-[#257354]"
                />
                <div className="text-[11px] text-[#8b9a94]">α 越小越均衡，α=1 为纯按销售额分配</div>
              </div>
              <div className="text-[11.5px] text-[#8b9a94] self-end leading-relaxed">
                {shelf.method}
              </div>
            </div>
          </div>

          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            {[
              ['总面积', `${shelf.total_area} ㎡`, 'default'],
              ['分配商品数', shelf.summary.subcategory_count, 'brand'],
              ['平均单位产出', `${fmt.n(shelf.summary.avg_sales_per_sqm)} 元/㎡`, 'default'],
              ['Top3 面积占比', `${shelf.summary.top_area_share}%`, 'good'],
            ].map(([label, v, tone]: any) => (
              <div key={label} className="card p-3.5">
                <div className="text-[12px] text-[#6b7d76]">{label}</div>
                <div className={`text-[22px] font-semibold tabular-nums mt-1 ${
                  tone === 'good' ? 'text-brand-600' : tone === 'brand' ? 'text-brand-700' : 'text-[#1a2b24]'
                }`}>
                  {v}
                </div>
              </div>
            ))}
          </div>

          <div className="grid grid-cols-1 xl:grid-cols-3 gap-4">
            <div className="card xl:col-span-2">
              <div className="card-title">各小类建议面积与单位产出</div>
              <div className="p-4">
                <Chart option={shelfOption} height={420} title="绿色=高于均值1.5倍，黄色=低于均值0.7倍" onExport={() => {}} />
              </div>
            </div>
            <div className="card">
              <div className="card-title">面积分配占比</div>
              <div className="p-4">
                <Chart option={pieOption} height={420} title="各小类面积占比（仅显示占比≥1.2%的小类）" onExport={() => {}} />
              </div>
            </div>
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            <div className="card">
              <div className="card-title">α 参数效果对比</div>
              <div className="p-4">
                <div className="space-y-2">
                  {shelf.alpha_guide.map((g: any) => (
                    <div
                      key={g.alpha}
                      className={`rounded-lg border px-3.5 py-2.5 ${
                        Math.abs(g.alpha - shelf.alpha) < 0.01
                          ? 'border-brand-400 bg-brand-50'
                          : 'border-[#e9eeec] bg-[#f7faf9]'
                      }`}
                    >
                      <div className="text-[12.5px] font-medium text-[#2c3d36]">
                        α = {g.alpha}
                        {Math.abs(g.alpha - shelf.alpha) < 0.01 && (
                          <span className="tag bg-brand-600 text-white border-brand-600 ml-1.5">当前</span>
                        )}
                      </div>
                      <div className="text-[11.5px] text-[#6b7d76] mt-0.5 leading-relaxed">{g.effect}</div>
                    </div>
                  ))}
                </div>
              </div>
            </div>

            <div className="card">
              <div className="card-title">对比：贪心装箱策略</div>
              <div className="p-4">
                <Alert type="info">{shelf.greedy_comparison.note}</Alert>
                {shelf.greedy_comparison.dropped_count > 0 && (
                  <div className="mt-3">
                    <div className="text-[12px] font-medium text-[#55665f] mb-1.5">
                      贪心策略下落选的小类（{shelf.greedy_comparison.dropped_count} 个）
                    </div>
                    <div className="flex flex-wrap gap-1">
                      {shelf.greedy_comparison.dropped_sample.map((n: string) => (
                        <span key={n} className="tag bg-[#fdf0f0] text-[#c13f3f] border border-[#f0cccc] text-[11px]">
                          {n}
                        </span>
                      ))}
                    </div>
                  </div>
                )}
                <div className="mt-3.5">
                  <Alert type="success">
                    本模块的差异：贪心按「单位面积产出」从高到低装箱，不考虑长尾保留；
                    本模块用 {shelf.method}
                    在产出效率与长尾覆盖之间取得平衡，更符合社区商超的实际陈列约束。
                  </Alert>
                </div>
              </div>
            </div>
          </div>

          <div className="card overflow-hidden">
            <div className="card-title">面积分配明细（{shelf.summary.subcategory_count} 个小类）</div>
            <div className="overflow-x-auto max-h-[520px] overflow-y-auto">
              <table className="w-full min-w-[760px]">
                <thead className="sticky top-0">
                  <tr>
                    <th className="table-th">#</th>
                    <th className="table-th">小类</th>
                    <th className="table-th">所属大类</th>
                    <th className="table-th text-right">销售额</th>
                    <th className="table-th text-right">建议面积</th>
                    <th className="table-th text-right">面积占比</th>
                    <th className="table-th text-right">单位产出(元/㎡)</th>
                    <th className="table-th">评价</th>
                  </tr>
                </thead>
                <tbody>
                  {shelf.items.map((r: any, i: number) => {
                    const avg = shelf.summary.avg_sales_per_sqm || 1
                    const ratio = r.sales_per_sqm / avg
                    return (
                      <tr key={r.name} className="hover:bg-[#f9fbfb]">
                        <td className="table-td tabular-nums text-[#8b9a94]">{i + 1}</td>
                        <td className="table-td font-medium">{r.name}</td>
                        <td className="table-td text-[12px]">{r.category}</td>
                        <td className="table-td text-right tabular-nums">{fmt.money(r.sales_amount)}</td>
                        <td className="table-td text-right tabular-nums font-medium text-brand-700">{r.suggest_area}</td>
                        <td className="table-td text-right tabular-nums">{r.share_pct}%</td>
                        <td className="table-td text-right tabular-nums">{fmt.n(r.sales_per_sqm)}</td>
                        <td className="table-td">
                          {ratio >= 1.5 ? (
                            <span className="tag bg-brand-50 text-brand-700 border border-brand-200">高产面积</span>
                          ) : ratio < 0.7 ? (
                            <span className="tag bg-[#fff8ec] text-[#a3700f] border border-[#f2dfb8]">低效占用</span>
                          ) : (
                            <span className="tag bg-[#eef2f0] text-[#6b7d76] border border-[#dde4e1]">一般</span>
                          )}
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          </div>

          <Alert type="info">{shelf.note}</Alert>
        </>
      )}
    </div>
  )
}
