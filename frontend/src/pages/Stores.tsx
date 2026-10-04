import { useEffect, useState } from 'react'
import { Chart, AXIS_STYLE, TOOLTIP, PALETTE } from '../components/Chart'
import {
  Alert, DemoBadge, Empty, ErrorBox, Loading, Modal, SectionTitle, Tabs,
} from '../components/ui'
import { api, fmt } from '../services/api'

const EMPTY_STORE = {
  name: '', code: '', city: '南京', district: '', business_district: '',
  store_type: '社区店', area_sqm: '',
  pop_3km: '', resident_ratio: '', office_ratio: '', student_ratio: '', senior_ratio: '',
  poi_residential: '', poi_office: '', poi_school: '',
  consumption_power: '', main_competitors: '', delivery_capability: '',
  sales_amount: '', gross_profit: '', gross_margin_rate: '', sales_qty: '',
  turnover_days: '', sales_per_sqm: '', sku_count: '', stockout_count: '',
  member_ratio: '', daily_customer_count: '', health_score: '',
  data_source: '人工录入',
}

export default function Stores() {
  const [tab, setTab] = useState('list')
  const [data, setData] = useState<any>(null)
  const [err, setErr] = useState('')
  const [msg, setMsg] = useState('')
  const [busy, setBusy] = useState(false)
  const [editOpen, setEditOpen] = useState(false)
  const [form, setForm] = useState<any>(EMPTY_STORE)
  const [editingId, setEditingId] = useState<number | null>(null)
  const [cmpIds, setCmpIds] = useState<number[]>([])
  const [cmp, setCmp] = useState<any>(null)
  const [cmpBusy, setCmpBusy] = useState(false)

  const isAdmin = (() => {
    const u = localStorage.getItem('suguo_user')
    return u ? JSON.parse(u).role_code === 'admin' : false
  })()

  const load = () => {
    setErr('')
    api.allStores().then((d) => {
      setData(d)
      setCmpIds((prev) => {
        const valid = prev.filter((id) => d.items.some((i: any) => i.id === id))
        return valid.length >= 2 ? valid : d.items.slice(0, 3).map((i: any) => i.id)
      })
    }).catch((e) => setErr(e.message))
  }
  useEffect(load, [])

  const openCreate = () => {
    setForm(EMPTY_STORE)
    setEditingId(null)
    setMsg('')
    setEditOpen(true)
  }

  const openEdit = (s: any) => {
    const f: any = { ...EMPTY_STORE }
    f.name = s.name; f.code = s.code; f.city = s.city || ''; f.district = s.district || ''
    f.business_district = s.business_district || ''; f.store_type = s.store_type || ''
    f.area_sqm = s.area_sqm ?? ''
    f.consumption_power = s.consumption_power || ''; f.main_competitors = s.main_competitors || ''
    f.delivery_capability = s.delivery_capability || ''; f.data_source = s.data_source || '人工录入'
    Object.entries(s.profile).forEach(([k, v]) => { f[k] = v ?? '' })
    Object.entries(s.metrics).forEach(([k, v]) => { f[k] = v ?? '' })
    setForm(f)
    setEditingId(s.id)
    setMsg('')
    setEditOpen(true)
  }

  const save = async () => {
    if (!form.name.trim()) { setMsg('门店名称不能为空'); return }
    setBusy(true)
    setMsg('')
    try {
      const payload: any = { ...form }
      for (const k of Object.keys(payload)) {
        if (payload[k] === '') payload[k] = null
        else if (typeof payload[k] === 'string' && k !== 'name' && k !== 'code' && k !== 'city'
          && k !== 'district' && k !== 'business_district' && k !== 'store_type'
          && k !== 'consumption_power' && k !== 'main_competitors' && k !== 'delivery_capability'
          && k !== 'data_source') {
          payload[k] = Number(payload[k])
        }
      }
      const d = editingId
        ? await api.updateStore({ ...payload, store_id: editingId })
        : await api.createStore(payload)
      setMsg(d.message)
      load()
    } catch (e: any) {
      setMsg(e.message)
    } finally {
      setBusy(false)
    }
  }

  const runCompare = async () => {
    if (cmpIds.length < 2) return
    setCmpBusy(true)
    setErr('')
    try {
      setCmp(await api.compareStores(cmpIds))
    } catch (e: any) {
      setErr(e.message)
    } finally {
      setCmpBusy(false)
    }
  }

  useEffect(() => {
    if (cmpIds.length >= 2 && data?.items?.length >= 2) runCompare()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [cmpIds])

  if (err && !data) return <ErrorBox message={err} onRetry={load} />
  if (!data) return <Loading text="正在加载门店数据…" />

  const metricCatalog = data.metrics_catalog
  const profileCatalog = data.profile_catalog

  // ---------- 对比图表 ----------
  const cmpBarOption = cmp?.ranking?.length ? {
    grid: { left: 130, right: 50, top: 30, bottom: 30 },
    tooltip: { ...TOOLTIP, trigger: 'axis', axisPointer: { type: 'shadow' } },
    xAxis: { type: 'value', max: 100, ...AXIS_STYLE },
    yAxis: {
      type: 'category',
      data: cmp.ranking.map((s: any) => s.store.length > 14 ? s.store.slice(0, 14) + '…' : s.store).reverse(),
      ...AXIS_STYLE, splitLine: { show: false },
    },
    series: [{
      type: 'bar', barWidth: 26,
      data: cmp.ranking.map((s: any, i: number) => ({
        value: s.overall_score,
        itemStyle: { color: PALETTE[(cmp.ranking.length - 1 - i) % PALETTE.length], borderRadius: [0, 4, 4, 0] },
      })).reverse(),
      label: { show: true, position: 'right', fontSize: 11, color: '#55665f', formatter: '{c}' },
    }],
  } : null

  const cmpRadarOption = cmp?.ranking?.length >= 2 ? (() => {
    // 选数据完整的维度做雷达
    const dims = cmp.dimensions.filter((d: any) => d.complete && d.higher_is_better !== null).slice(0, 7)
    return {
      tooltip: { ...TOOLTIP, trigger: 'item' },
      legend: { bottom: 0, itemWidth: 12, itemHeight: 8, textStyle: { fontSize: 10 } },
      radar: {
        indicator: dims.map((d: any) => ({ name: d.label, max: 100 })),
        radius: '60%', center: ['50%', '45%'],
        axisName: { color: '#55665f', fontSize: 10 },
        splitLine: { lineStyle: { color: '#e3e8e6' } },
        splitArea: { areaStyle: { color: ['#fbfdfc', '#f5f8f7'] } },
        axisLine: { lineStyle: { color: '#e3e8e6' } },
      },
      series: [{
        type: 'radar',
        data: cmp.ranking.slice(0, 4).map((s: any, i: number) => {
          const row = cmp.stores.find((x: any) => x.store_id === s.store_id)
          return {
            value: dims.map((d: any) => {
              const v = d.values.find((x: any) => x.store_id === s.store_id)
              return v?.score ?? 0
            }),
            name: s.store.length > 12 ? s.store.slice(0, 12) + '…' : s.store,
            lineStyle: { color: PALETTE[i % PALETTE.length], width: 2 },
            itemStyle: { color: PALETTE[i % PALETTE.length] },
            areaStyle: { opacity: 0.07 },
          }
        }),
      }],
    }
  })() : null

  const cmpRadarDims = cmp?.dimensions?.filter((d: any) => d.complete && d.higher_is_better !== null).slice(0, 7) || []

  return (
    <div className="space-y-4 max-w-[1680px]">
      <div className="flex items-center justify-between gap-4 flex-wrap">
        <div>
          <h1 className="text-[19px] font-semibold text-[#1a2b24]">千店千面 · 多门店管理</h1>
          <p className="text-[12.5px] text-[#6b7d76] mt-0.5">
            门店画像录入 ｜ 多门店横向对比 ｜ 支撑「千店千面」差异化选品
          </p>
        </div>
        <div className="flex items-center gap-2">
          <DemoBadge />
          {isAdmin && (
            <button className="btn-primary" onClick={openCreate}>+ 录入新门店</button>
          )}
        </div>
      </div>

      {msg && <Alert type={msg.includes('已创建') || msg.includes('已更新') ? 'success' : 'error'}>{msg}</Alert>}
      {err && <ErrorBox message={err} />}

      <Alert type="warn">
        <div className="font-medium mb-1">数据来源说明</div>
        <div className="text-[12px] leading-relaxed">{data.data_caveat}</div>
      </Alert>

      <Tabs
        active={tab}
        onChange={setTab}
        items={[
          { key: 'list', label: '门店列表', badge: data.count },
          { key: 'compare', label: '多门店对比', badge: cmpIds.length },
          { key: 'framework', label: '千店千面输出框架' },
        ]}
      />

      {/* ============ 门店列表 ============ */}
      {tab === 'list' && (
        <div className="space-y-4">
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            {[
              ['门店总数', data.count, 'brand'],
              ['指标完整', data.ready_count, 'good'],
              ['对比维度', metricCatalog.length, 'default'],
              ['画像维度', profileCatalog.length, 'default'],
            ].map(([label, v, tone]: any) => (
              <div key={label} className="card p-3.5">
                <div className="text-[12px] text-[#6b7d76]">{label}</div>
                <div className={`text-[22px] font-semibold tabular-nums mt-1 ${
                  tone === 'good' ? 'text-brand-600' : tone === 'brand' ? 'text-brand-700' : 'text-[#1a2b24]'
                }`}>{v}</div>
              </div>
            ))}
          </div>

          {data.items.map((s: any) => {
            const st = s.data_status
            return (
              <div key={s.id} className="card">
                <div className="card-title">
                  <div>
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className="text-[14px] font-semibold">{s.name}</span>
                      {s.is_default && (
                        <span className="tag bg-brand-50 text-brand-700 border border-brand-200">当前门店</span>
                      )}
                      <span
                        className="tag"
                        style={{
                          background: st.metrics_ready ? '#f0f9f4' : '#fdf0f0',
                          color: st.metrics_ready ? '#257354' : '#c13f3f',
                        }}
                      >
                        {st.level}
                      </span>
                    </div>
                    <div className="text-[11.5px] text-[#8b9a94] font-normal mt-0.5">
                      {s.code} ｜ {s.city}{s.district} {s.business_district} ｜ {s.store_type}
                      {s.area_sqm ? ` ｜ ${s.area_sqm} ㎡` : ''}
                    </div>
                  </div>
                  {isAdmin && (
                    <button className="btn-secondary" onClick={() => openEdit(s)}>
                      编辑 / 补录数据
                    </button>
                  )}
                </div>
                <div className="p-4">
                  {/* 经营指标 */}
                  <SectionTitle extra={
                    <span className="text-[11.5px] text-[#8b9a94]">
                      已填 {st.metrics_filled}/{st.metrics_total}
                      {s.data_source && ` ｜ 来源：${s.data_source}`}
                    </span>
                  }>
                    经营指标
                  </SectionTitle>
                  <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-2 mb-4">
                    {metricCatalog.map((m: any) => {
                      const v = s.metrics[m.key]
                      const empty = v == null
                      return (
                        <div
                          key={m.key}
                          className={`rounded-lg border px-2.5 py-2 ${
                            empty ? 'border-dashed border-[#e3e8e6] bg-[#fbfcfc]' : 'border-[#e9eeec] bg-[#f7faf9]'
                          }`}
                        >
                          <div className="text-[10.5px] text-[#8b9a94] truncate" title={m.label}>{m.label}</div>
                          <div className={`text-[14px] font-medium mt-0.5 tabular-nums ${empty ? 'text-[#c3ceca]' : 'text-[#2c3d36]'}`}>
                            {empty ? '待接入' : `${fmt.n(v, Number.isInteger(v) ? 0 : 2)}${m.unit && m.unit !== '元' ? ` ${m.unit}` : ''}`}
                          </div>
                        </div>
                      )
                    })}
                  </div>

                  {/* 画像 */}
                  <SectionTitle extra={
                    <span className="text-[11.5px] text-[#8b9a94]">已填 {st.profile_filled}/{profileCatalog.length}</span>
                  }>
                    门店画像（千店千面基础数据）
                  </SectionTitle>
                  <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
                    {profileCatalog.map((p: any) => {
                      const v = s.profile[p.key]
                      const empty = v == null || v === ''
                      return (
                        <div
                          key={p.key}
                          className={`rounded-lg border px-2.5 py-2 ${
                            empty ? 'border-dashed border-[#e3e8e6] bg-[#fbfcfc]' : 'border-[#e9eeec] bg-[#f7faf9]'
                          }`}
                        >
                          <div className="text-[10.5px] text-[#8b9a94]">{p.label}</div>
                          <div className={`text-[14px] font-medium mt-0.5 tabular-nums ${empty ? 'text-[#c3ceca]' : 'text-[#2c3d36]'}`}>
                            {empty ? '待接入' : `${fmt.n(v)}${p.unit !== '人' && p.unit !== '个' ? ` ${p.unit}` : ''}`}
                          </div>
                        </div>
                      )
                    })}
                  </div>

                  {!st.metrics_ready && (
                    <div className="mt-3">
                      <Alert type="info">
                        <div className="text-[12px] leading-relaxed">
                          缺失经营指标：{st.missing_metrics.join('、')}。
                          未填字段在多门店对比中显示「待接入」，<b>不参与该店得分计算</b>，平台不做推算。
                        </div>
                      </Alert>
                    </div>
                  )}
                </div>
              </div>
            )
          })}
        </div>
      )}

      {/* ============ 多门店对比 ============ */}
      {tab === 'compare' && (
        <div className="space-y-4">
          <div className="card">
            <div className="card-title">
              <span>选择要对比的门店</span>
              <button className="btn-primary" onClick={runCompare} disabled={cmpIds.length < 2 || cmpBusy}>
                {cmpBusy ? '对比中…' : `对比（${cmpIds.length} 家）`}
              </button>
            </div>
            <div className="p-4">
              {data.items.length < 2 ? (
                <Empty
                  title="至少需要 2 家门店才能对比"
                  hint="当前只有 1 家门店。请点击右上角「录入新门店」添加其他门店并填写经营指标。"
                  action={isAdmin ? <button className="btn-primary" onClick={openCreate}>+ 录入新门店</button> : undefined}
                />
              ) : (
                <>
                  <div className="flex flex-wrap gap-2">
                    {data.items.map((s: any) => {
                      const on = cmpIds.includes(s.id)
                      return (
                        <button
                          key={s.id}
                          onClick={() => setCmpIds((p) =>
                            on ? p.filter((x) => x !== s.id) : [...p, s.id])}
                          className={`px-3 py-2 rounded-lg border text-[13px] transition-all ${
                            on
                              ? 'border-brand-500 bg-brand-50 text-brand-800 font-medium'
                              : 'border-[#d5ded9] text-[#3d5049] hover:border-brand-300'
                          }`}
                        >
                          {s.name.length > 18 ? s.name.slice(0, 18) + '…' : s.name}
                          <span
                            className="ml-1.5 text-[10.5px]"
                            style={{ color: s.data_status.metrics_ready ? '#257354' : '#c13f3f' }}
                          >
                            {s.data_status.metrics_ready ? '完整' : `${s.data_status.metrics_filled}/${s.data_status.metrics_total}`}
                          </span>
                        </button>
                      )
                    })}
                  </div>
                  <div className="mt-3 flex items-center gap-2">
                    <button className="btn-ghost text-[12px]" onClick={() => setCmpIds(data.items.map((i: any) => i.id))}>
                      全选
                    </button>
                    <button className="btn-ghost text-[12px]" onClick={() => setCmpIds([])}>清空</button>
                    <span className="text-[11.5px] text-[#8b9a94]">已选 {cmpIds.length} 家（至少 2 家）</span>
                  </div>
                </>
              )}
            </div>
          </div>

          {cmp && cmp.success && (
            <>
              <Alert type="info">
                <div className="font-medium mb-1">对比结果</div>
                <div className="text-[12px]">{cmp.summary}</div>
              </Alert>

              {cmp.not_ranked.length > 0 && (
                <Alert type="warn">
                  <div className="text-[12px]">
                    以下门店因缺少经营数据未参与排名：{cmp.not_ranked.map((s: any) => s.store).join('、')}。
                    平台不做数据推算，补录指标后即可参与。
                  </div>
                </Alert>
              )}

              {/* 排名卡 */}
              {cmp.ranking.length > 0 && (
                <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                  {cmp.ranking.map((s: any, i: number) => (
                    <div
                      key={s.store_id}
                      className="card p-4"
                      style={{ borderLeft: `3px solid ${PALETTE[i % PALETTE.length]}` }}
                    >
                      <div className="flex items-center justify-between mb-2">
                        <span className="text-[14px] font-semibold">{s.store}</span>
                        <span
                          className="w-7 h-7 rounded-full flex items-center justify-center text-[13px] font-bold text-white"
                          style={{ background: PALETTE[i % PALETTE.length] }}
                        >
                          {s.rank}
                        </span>
                      </div>
                      <div className="text-[26px] font-semibold tabular-nums" style={{ color: PALETTE[i % PALETTE.length] }}>
                        {s.overall_score}
                        <span className="text-[12px] text-[#8b9a94] ml-1">分</span>
                      </div>
                      <div className="text-[11.5px] text-[#8b9a94] mt-1">
                        参与 {s.scored_dimensions} 个维度 ｜ {s.business_district || s.district || '—'}
                      </div>
                    </div>
                  ))}
                </div>
              )}

              {/* 图表 */}
              <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
                {cmpBarOption && (
                  <div className="card">
                    <div className="card-title">综合得分对比</div>
                    <div className="p-4">
                      <Chart option={cmpBarOption} height={280} title="各门店综合得分（满分100）" onExport={() => {}} />
                    </div>
                  </div>
                )}
                {cmpRadarOption && (
                  <div className="card">
                    <div className="card-title">门店能力雷达</div>
                    <div className="p-4">
                      <Chart
                        option={cmpRadarOption}
                        height={280}
                        title={`${cmpRadarDims.map((d: any) => d.label).join('、')}（标准化得分）`}
                        onExport={() => {}}
                      />
                    </div>
                  </div>
                )}
              </div>

              {/* 差异分析 */}
              {cmp.insights.length > 0 && (
                <div className="card">
                  <div className="card-title">
                    <span>门店差异分析</span>
                    <span className="text-[12px] text-[#6b7d76] font-normal">
                      {cmp.significant_count} 个维度差异显著（比值 ≥ 1.5）
                    </span>
                  </div>
                  <div className="p-4 space-y-2">
                    {cmp.insights.map((ins: any, i: number) => (
                      <div
                        key={i}
                        className={`flex items-center gap-3 px-3.5 py-2.5 rounded-lg border ${
                          ins.significant ? 'border-[#f2dfb8] bg-[#fffdf8]' : 'border-[#e9eeec] bg-[#f7faf9]'
                        }`}
                      >
                        <span className="w-6 h-6 rounded bg-white border border-[#dde4e1] flex items-center justify-center text-[11px] text-[#55665f] flex-shrink-0">
                          {i + 1}
                        </span>
                        <span className="text-[13px] font-medium text-[#2c3d36] w-28 flex-shrink-0">{ins.dimension}</span>
                        <span className="text-[12px] text-[#6b7d76] flex-shrink-0">
                          最佳：<b className="text-brand-700">{ins.best_store}</b>
                        </span>
                        <div className="flex flex-wrap gap-2 ml-auto">
                          {Object.entries(ins.values).map(([k, v]: any) => (
                            <span key={k} className="tag bg-white text-[#55665f] border border-[#dde4e1] text-[11px]">
                              {k.length > 10 ? k.slice(0, 10) + '…' : k}: {fmt.n(v)}
                            </span>
                          ))}
                        </div>
                        <span
                          className={`tag flex-shrink-0 ${
                            ins.significant
                              ? 'bg-[#fff8ec] text-[#a3700f] border border-[#f2dfb8]'
                              : 'bg-[#eef2f0] text-[#6b7d76] border border-[#dde4e1]'
                          }`}
                        >
                          比值 {ins.ratio}
                        </span>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* 明细表 */}
              <div className="card overflow-hidden">
                <div className="card-title">门店对比明细</div>
                <div className="overflow-x-auto">
                  <table className="w-full min-w-[900px]">
                    <thead>
                      <tr>
                        <th className="table-th">维度</th>
                        <th className="table-th">单位</th>
                        {cmp.stores.map((s: any) => (
                          <th key={s.store_id} className="table-th text-right">
                            {s.store.length > 12 ? s.store.slice(0, 12) + '…' : s.store}
                          </th>
                        ))}
                        <th className="table-th">最优</th>
                      </tr>
                    </thead>
                    <tbody>
                      {cmp.dimensions.map((d: any) => (
                        <tr key={d.key} className="hover:bg-[#f9fbfb]">
                          <td className="table-td">
                            <div className="font-medium">{d.label}</div>
                            <div className="text-[10.5px] text-[#a8b5b0]">{d.description}</div>
                          </td>
                          <td className="table-td text-[12px] text-[#8b9a94]">{d.unit}</td>
                          {d.values.map((v: any, i: number) => (
                            <td key={i} className="table-td text-right">
                              {v.value == null ? (
                                <span className="text-[#c3ceca] text-[12px]">待接入</span>
                              ) : (
                                <span className="tabular-nums">
                                  {fmt.n(v.value)}
                                  {v.score != null && (
                                    <span className="ml-1.5 text-[10.5px] text-[#a8b5b0]">({v.score})</span>
                                  )}
                                </span>
                              )}
                            </td>
                          ))}
                          <td className="table-td text-[12px]">
                            {d.best ? (
                              <span className="text-brand-700 font-medium">
                                {d.best.length > 10 ? d.best.slice(0, 10) + '…' : d.best}
                              </span>
                            ) : (
                              <span className="text-[#a8b5b0]">数据不足</span>
                            )}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>

              {/* 画像对比 */}
              <div className="card overflow-hidden">
                <div className="card-title">门店画像对比（千店千面基础）</div>
                <div className="overflow-x-auto">
                  <table className="w-full min-w-[700px]">
                    <thead>
                      <tr>
                        <th className="table-th">画像维度</th>
                        {cmp.stores.map((s: any) => (
                          <th key={s.store_id} className="table-th text-right">
                            {s.store.length > 12 ? s.store.slice(0, 12) + '…' : s.store}
                          </th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {cmp.profiles.map((p: any) => (
                        <tr key={p.key}>
                          <td className="table-td font-medium">{p.label}</td>
                          {p.values.map((v: any, i: number) => (
                            <td key={i} className="table-td text-right">
                              {v.value == null || v.value === '' ? (
                                <span className="text-[#c3ceca] text-[12px]">待接入</span>
                              ) : (
                                <span className="tabular-nums">{fmt.n(v.value)}{p.unit !== '人' && p.unit !== '个' ? ` ${p.unit}` : ''}</span>
                              )}
                            </td>
                          ))}
                        </tr>
                      ))}
                      <tr>
                        <td className="table-td font-medium">消费能力</td>
                        {cmp.stores.map((s: any) => (
                          <td key={s.store_id} className="table-td text-right text-[12px]">
                            {s.consumption_power && s.consumption_power !== '待接入'
                              ? s.consumption_power
                              : <span className="text-[#c3ceca]">待接入</span>}
                          </td>
                        ))}
                      </tr>
                    </tbody>
                  </table>
                </div>
              </div>

              <Alert type="info">
                <div className="font-medium mb-1">评分方法</div>
                <div className="text-[12px] leading-relaxed">{cmp.method_note}</div>
                <div className="text-[12px] leading-relaxed mt-1.5">{cmp.data_caveat}</div>
              </Alert>
            </>
          )}
        </div>
      )}

      {/* ============ 框架说明 ============ */}
      {tab === 'framework' && (
        <div className="space-y-4">
          <div className="card">
            <div className="card-title">千店千面输出框架（画像数据接入后自动生成）</div>
            <div className="p-4">
              <div className="grid grid-cols-1 md:grid-cols-3 lg:grid-cols-6 gap-2.5">
                {[
                  ['目标客群', 'RFM 分层 + 社区客群画像 + POI 周边特征'],
                  ['重点品类', '按客群需求强度匹配品类角色'],
                  ['应扩充品类', '需求强、供给弱的品类'],
                  ['应压缩品类', '需求弱、周转慢的品类'],
                  ['建议价格带', '按商圈消费能力推导'],
                  ['场景组合', '关联规则 + 客群场景'],
                ].map(([t, d], i) => (
                  <div key={t} className="rounded-lg border border-[#e9eeec] bg-[#f7faf9] p-3">
                    <div className="flex items-center gap-1.5 mb-1">
                      <span className="w-4 h-4 rounded bg-brand-600 text-white text-[9.5px] flex items-center justify-center">
                        {i + 1}
                      </span>
                      <span className="text-[12.5px] font-medium text-[#2c3d36]">{t}</span>
                    </div>
                    <div className="text-[11px] text-[#8b9a94] leading-relaxed">{d}</div>
                  </div>
                ))}
              </div>
            </div>
          </div>

          <div className="card">
            <div className="card-title">多门店对比可支撑的决策场景</div>
            <div className="p-4 grid grid-cols-1 md:grid-cols-2 gap-3">
              {[
                ['定位差异化', '对比不同商圈门店的坪效、周转、客群结构，找出经营模型差异，为新店选址与业态定位提供依据'],
                ['标杆复制', '识别综合得分领先门店，分析其在哪些维度领先，把可复制的动作推广到其他门店'],
                ['短板诊断', '某门店在特定维度显著落后（如坪效仅为最优店的 1/5），针对性定位改进方向'],
                ['品类调优', '结合客群结构差异，差异化调整各门店的品类结构，支撑「千店千面」落地'],
              ].map(([t, d]) => (
                <div key={t} className="rounded-lg border border-[#e9eeec] p-3.5">
                  <div className="text-[12.5px] font-medium text-[#2c3d36] mb-1">{t}</div>
                  <div className="text-[11.5px] text-[#6b7d76] leading-relaxed">{d}</div>
                </div>
              ))}
            </div>
          </div>

          <Alert type="info">
            <div className="text-[12px] leading-relaxed">
              当前附件仅包含一家门店的经营数据。多门店对比功能的算法与界面已完成，
              其余门店的指标需人工录入或后续通过系统对接获取。
              录入的数据应来自真实第三方数据源（高德/百度地图 POI、统计局数据、商场客流报告等），
              并确保已获得使用授权。所有修改均记入操作日志。
            </div>
          </Alert>
        </div>
      )}

      {/* ============ 录入弹窗 ============ */}
      <Modal open={editOpen} onClose={() => setEditOpen(false)} width="max-w-5xl"
        title={editingId ? `编辑门店：${form.name}` : '录入新门店'}>
        <div className="space-y-5">
          <div>
            <SectionTitle>基础信息</SectionTitle>
            <div className="grid grid-cols-4 gap-3">
              {[
                ['name', '门店名称', true], ['code', '门店编码'], ['city', '城市'], ['district', '区县'],
                ['business_district', '商圈'], ['store_type', '门店类型'], ['area_sqm', '营业面积(㎡)'],
                ['data_source', '数据来源'],
              ].map(([k, label, req]: any) => (
                <div key={k} className={k === 'business_district' || k === 'data_source' ? 'col-span-2' : ''}>
                  <label className="label">
                    {label}{req && <span className="text-[#c13f3f] ml-0.5">*</span>}
                  </label>
                  <input
                    className="input"
                    type={['area_sqm'].includes(k) ? 'number' : 'text'}
                    value={form[k] ?? ''}
                    placeholder={req ? '必填' : '可留空'}
                    onChange={(e) => setForm({ ...form, [k]: e.target.value })}
                  />
                </div>
              ))}
            </div>
          </div>

          <div>
            <SectionTitle extra={<span className="text-[11.5px] text-[#8b9a94]">千店千面基础数据，可稍后补录</span>}>
              门店画像
            </SectionTitle>
            <div className="grid grid-cols-4 gap-3">
              {profileCatalog.map((p: any) => (
                <div key={p.key}>
                  <label className="label">{p.label}（{p.unit}）</label>
                  <input
                    className="input"
                    type="number"
                    step="0.01"
                    value={form[p.key] ?? ''}
                    placeholder="留空表示待接入"
                    onChange={(e) => setForm({ ...form, [p.key]: e.target.value })}
                  />
                </div>
              ))}
              {[
                ['consumption_power', '消费能力'], ['main_competitors', '主要竞品'],
                ['delivery_capability', '配送能力'],
              ].map(([k, label]: any) => (
                <div key={k}>
                  <label className="label">{label}</label>
                  <input
                    className="input"
                    value={form[k] ?? ''}
                    onChange={(e) => setForm({ ...form, [k]: e.target.value })}
                  />
                </div>
              ))}
            </div>
          </div>

          <div>
            <SectionTitle extra={<span className="text-[11.5px] text-[#8b9a94]">未填字段在对比中显示「待接入」，不参与排名</span>}>
              经营指标（月度）
            </SectionTitle>
            <div className="grid grid-cols-4 gap-3">
              {metricCatalog.map((m: any) => (
                <div key={m.key}>
                  <label className="label" title={m.description}>
                    {m.label}（{m.unit}）
                    {m.higher_is_better === false && <span className="text-[#a3700f] ml-1">↓越低越好</span>}
                    {m.higher_is_better === null && <span className="text-[#8b9a94] ml-1">中性</span>}
                  </label>
                  <input
                    className="input"
                    type="number"
                    step="0.01"
                    value={form[m.key] ?? ''}
                    placeholder="留空表示待接入"
                    onChange={(e) => setForm({ ...form, [m.key]: e.target.value })}
                  />
                </div>
              ))}
            </div>
          </div>

          <Alert type="warn">
            录入的数据应来自真实第三方数据源，并确保已获得使用授权。
            平台不会校验数据真实性，但所有修改会记入操作日志（含修改前后值）。
            请勿录入无来源的估算值——对比结果的可信度取决于数据真实性。
          </Alert>
        </div>

        <div className="flex justify-end gap-2 mt-5 pt-4 border-t border-[#eef2f0]">
          <button className="btn-secondary" onClick={() => setEditOpen(false)}>取消</button>
          <button className="btn-primary" onClick={save} disabled={busy}>
            {busy ? '保存中…' : editingId ? '保存修改' : '创建门店'}
          </button>
        </div>
      </Modal>
    </div>
  )
}
