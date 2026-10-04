import { useEffect, useMemo, useRef, useState } from 'react'
import { Chart, AXIS_STYLE, TOOLTIP, PALETTE } from '../components/Chart'
import { Alert, DemoBadge, Empty, ErrorBox, Loading, Modal, Tabs } from '../components/ui'
import { api, fmt } from '../services/api'

const CAT_WEIGHTS: Record<string, string> = {
  sales: '销量贡献', margin: '毛利贡献', turnover: '库存周转', space: '坪效',
}
const CAT_DESC: Record<string, string> = {
  sales: '越高越好', margin: '越高越好', turnover: '周转天数越低越好（逆向标准化）', space: '越高越好',
}
const SUB_WEIGHTS: Record<string, string> = {
  sales_qty: '销量', sales_amount: '销售额',
}

export default function Compare() {
  const [mode, setMode] = useState('category')
  const [options, setOptions] = useState<any[]>([])
  const [groups, setGroups] = useState<any[]>([])
  const [optStatus, setOptStatus] = useState<any>(null)
  const [selected, setSelected] = useState<(number | string)[]>([])
  const [result, setResult] = useState<any>(null)
  const [weights, setWeights] = useState<any>({ sales: 0.3, margin: 0.3, turnover: 0.2, space: 0.2 })
  const [editW, setEditW] = useState<any>(null)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')
  const [msg, setMsg] = useState('')
  const [submitting, setSubmitting] = useState(false)
  // 演示预置时用 ref 标记（state 更新是异步的，effect 里读不到最新值）
  const presetModeRef = useRef<string | null>(null)

  useEffect(() => {
    // 演示预置时不要清空已选对象
    if (presetModeRef.current && mode === presetModeRef.current) {
      presetModeRef.current = null
      return
    }
    setSelected([])
    setResult(null)
    setErr('')
    setMsg('')
    if (mode === 'subcategory') {
      api.subCompareOptions()
        .then((d) => {
          setGroups(d.groups || [])
          setOptions([])
          setOptStatus(d.data_status)
        })
        .catch((e) => setErr(e.message))
    } else {
      api.compareOptions(mode)
        .then((d) => { setOptions(d.options || []); setOptStatus(d.status) })
        .catch((e) => setErr(e.message))
    }
  }, [mode])

  useEffect(() => {
    if (result?.weights) setWeights(result.weights)
  }, [result])

  // 演示预置：自动切到小类模式、选中指定商品并直接出结果
  useEffect(() => {
    let preset: any = null
    try { preset = JSON.parse(sessionStorage.getItem('suguo_demo_preset') || 'null') } catch { /* 忽略 */ }
    if (!preset || preset.mode !== 'subcategory') return

    api.subCompareOptions().then((d) => {
      setGroups(d.groups || [])
      setOptStatus(d.data_status)
      if (!preset.names?.length) return
      const ids: number[] = []
      ;(d.groups || []).forEach((g: any) =>
        g.items.forEach((it: any) => { if (preset.names.includes(it.name)) ids.push(it.id) }))
      if (ids.length >= 2) {
        presetModeRef.current = 'subcategory'   // 先标记，避免 mode effect 清空
        setMode('subcategory')
        setSelected(ids)
        if (preset.autoRun) {
          api.compareSubcategories({ ids })
            .then(setResult)
            .catch((e) => setErr(e.message))
        }
      }
    }).catch((e) => setErr(e.message))
  }, [])

  const isSub = mode === 'subcategory'

  const run = async (w?: any) => {
    if (selected.length < 2) return
    setBusy(true); setErr(''); setMsg('')
    try {
      if (isSub) {
        const payload: any = { ids: selected as number[] }
        if (w) payload.weights = w
        setResult(await api.compareSubcategories(payload))
      } else {
        const payload: any = { mode, ids: [], category_ids: selected as number[] }
        if (w) payload.weights = w
        setResult(await api.compare(payload))
      }
    } catch (e: any) {
      setErr(e.message)
    } finally {
      setBusy(false)
    }
  }

  const toggle = (id: number) => {
    setSelected((prev) => {
      if (prev.includes(id)) return prev.filter((x) => x !== id)
      if (prev.length >= 6) return prev
      return [...prev, id]
    })
  }

  const applyWeights = async () => {
    const total = Object.values(editW).reduce((a: number, b: any) => a + Number(b), 0)
    if (Math.abs(total - 1) > 0.001) {
      setErr(`权重之和必须为 1，当前为 ${total.toFixed(4)}`)
      return
    }
    setErr(''); setWeights(editW); setEditW(null)
    await run(editW)
  }

  const submitApproval = async () => {
    if (!result) return
    setSubmitting(true)
    try {
      const top = result.items[0]
      const label = isSub ? '小类比较' : '品类比较'
      const d = await api.createApproval({
        title: `${label}：${top.name} 综合得分 ${top.overall_score} 排名第一`,
        content:
          `推荐优先级：${result.items.map((r: any) => r.priority).join(' > ')}。\n` +
          result.items.map((r: any) => `${r.name}（${r.overall_score}分）：${r.recommendation.action} — ${r.recommendation.reason}`).join('\n'),
        data_basis: result.items
          .map((r: any) => `${r.name} ${Object.entries(r.scores).map(([k, v]) => `${k}=${v}`).join('/')}`)
          .join('；'),
        risk_level: 'Level 3',
        source_module: isSub ? '小类比较中心' : '选品比较中心',
        affected_categories: result.items.map((r: any) => r.name).join(','),
      })
      setMsg(`已提交人工审批，编号 ${d.code}。AI 不能自动执行该操作。`)
    } catch (e: any) {
      setMsg(e.message)
    } finally {
      setSubmitting(false)
    }
  }

  const wSum = Object.values(weights).reduce((a: number, b: any) => a + Number(b), 0)
  const weightLabels: Record<string, string> = isSub ? SUB_WEIGHTS : CAT_WEIGHTS
  const weightDesc: Record<string, string> = isSub
    ? { sales_qty: '越高越好', sales_amount: '越高越好' }
    : CAT_DESC

  const radarOption = useMemo(() => {
    if (!result?.items) return null
    const keys = Object.keys(result.items[0].scores)
    return {
      tooltip: { ...TOOLTIP, trigger: 'item' },
      legend: { bottom: 0, itemWidth: 12, itemHeight: 8, textStyle: { fontSize: 11 } },
      radar: {
        indicator: keys.map((k) => ({ name: weightLabels[k] || k, max: 100 })),
        radius: '64%', center: ['50%', '46%'],
        axisName: { color: '#55665f', fontSize: 11 },
        splitLine: { lineStyle: { color: '#e3e8e6' } },
        splitArea: { areaStyle: { color: ['#fbfdfc', '#f5f8f7'] } },
        axisLine: { lineStyle: { color: '#e3e8e6' } },
      },
      series: [{
        type: 'radar',
        data: result.items.map((r: any, i: number) => ({
          value: keys.map((k) => r.scores[k]),
          name: r.name,
          lineStyle: { color: PALETTE[i % PALETTE.length], width: 2 },
          itemStyle: { color: PALETTE[i % PALETTE.length] },
          areaStyle: { opacity: 0.08 },
        })),
      }],
    }
  }, [result, isSub])

  return (
    <div className="space-y-4 max-w-[1680px]">
      <div className="flex items-center justify-between gap-4 flex-wrap">
        <div>
          <h1 className="text-[19px] font-semibold text-[#1a2b24]">选品比较中心</h1>
          <p className="text-[12.5px] text-[#6b7d76] mt-0.5">
            支持 2-6 个候选对象，按可配置权重进行多维加权比较
          </p>
        </div>
        <DemoBadge />
      </div>

      <div className="card">
        <div className="card-title">
          <span>添加比较对象</span>
          <span className="text-[12px] text-[#6b7d76] font-normal">已选 {selected.length} / 6 个</span>
        </div>
        <div className="p-4 space-y-4">
          <Tabs
            active={mode}
            onChange={setMode}
            items={[
              { key: 'category', label: '模式A：品类比较', badge: options.length || undefined },
              { key: 'subcategory', label: '模式B：小类比较', badge: groups.reduce((s, g) => s + g.items.length, 0) || undefined },
              { key: 'sku', label: '模式C：SKU / 商品比较' },
            ]}
          />

          {mode === 'sku' && optStatus && !optStatus.sufficient && (
            <Alert type="warn">
              <div className="font-medium mb-1.5">{optStatus.message}</div>
              <div className="text-[12px]">
                缺少字段：{optStatus.missing?.join('、') || 'SKU 级经营指标'}。{optStatus.upload_hint}
              </div>
              <button className="btn-secondary mt-2.5" onClick={() => (location.hash = '#/data')}>
                前往数据中心上传 SKU 数据
              </button>
            </Alert>
          )}

          {isSub && optStatus && !optStatus.complete && (
            <Alert type="info">
              <div className="font-medium mb-1">小类层数据完整度说明</div>
              <div className="text-[12px] leading-relaxed">
                {optStatus.note}
                当前已有字段：销量、销售额、均价、成交笔数、连带率、关联强度。
                缺失：{optStatus.missing?.join('、')}。
                <b>平台不会用大类数据摊派到小类</b>，因此小类比较自动降级为两维模型（销量50% + 销售额50%）。
              </div>
            </Alert>
          )}

          {isSub ? (
            groups.length === 0 ? (
              <Empty
                title="暂无小类数据"
                hint="小类数据由交易明细实时聚合生成。请确认已导入 dataset_transactions_sample.csv，或点击下方按钮重新聚合。"
                action={
                  <button
                    className="btn-primary"
                    onClick={() => {
                      setMsg('正在从交易明细聚合小类…')
                      api.rebuildSubcategories()
                        .then((d) => {
                          setMsg(`聚合完成，共 ${d.count} 个小类，ABC 分类：${d.abc?.summary || ''}`)
                          api.subCompareOptions().then((r) => setGroups(r.groups || []))
                        })
                        .catch((e) => setErr(e.message))
                    }}
                  >
                    从交易明细重新聚合
                  </button>
                }
              />
            ) : (
              <div className="space-y-3">
                {groups.map((g) => (
                  <div key={g.category}>
                    <div className="text-[12px] font-medium text-[#55665f] mb-1.5">
                      {g.category}
                      <span className="text-[#a8b5b0] font-normal ml-1.5">{g.items.length} 个小类</span>
                    </div>
                    <div className="flex flex-wrap gap-1.5">
                      {g.items.map((it: any) => {
                        const on = selected.includes(it.id)
                        const disabled = !on && selected.length >= 6
                        return (
                          <button
                            key={it.id}
                            disabled={disabled}
                            onClick={() => toggle(it.id)}
                            title={`销售额 ${fmt.money(it.sales_amount)}`}
                            className={`px-2.5 py-1 rounded-md border text-[12.5px] transition-all ${
                              on
                                ? 'border-brand-500 bg-brand-50 text-brand-800 font-medium'
                                : disabled
                                  ? 'border-[#eef2f0] text-[#c3ceca] cursor-not-allowed'
                                  : 'border-[#d5ded9] text-[#3d5049] hover:border-brand-300 hover:bg-[#f7faf9]'
                            }`}
                          >
                            {it.name}
                            {it.abc_class && (
                              <span
                                className="ml-1 text-[10px] font-medium"
                                style={{
                                  color: it.abc_class === 'A' ? '#257354' : it.abc_class === 'B' ? '#4a7fb5' : '#d9a520',
                                }}
                              >
                                {it.abc_class}
                              </span>
                            )}
                          </button>
                        )
                      })}
                    </div>
                  </div>
                ))}
              </div>
            )
          ) : options.length === 0 ? (
            <Empty title={mode === 'sku' ? '当前没有可比较的 SKU 数据' : '暂无可比较的品类'} hint={optStatus?.message} />
          ) : (
            <div className="flex flex-wrap gap-2">
              {options.map((o: any) => {
                const on = selected.includes(o.id)
                const disabled = !on && selected.length >= 6
                return (
                  <button
                    key={o.id}
                    disabled={disabled}
                    onClick={() => toggle(o.id)}
                    className={`px-3 py-2 rounded-lg border text-[13px] transition-all ${
                      on
                        ? 'border-brand-500 bg-brand-50 text-brand-800 font-medium'
                        : disabled
                          ? 'border-[#eef2f0] text-[#c3ceca] cursor-not-allowed'
                          : 'border-[#d5ded9] text-[#3d5049] hover:border-brand-300 hover:bg-[#f7faf9]'
                    }`}
                  >
                    {o.name}
                    {o.health_score != null && <span className="ml-1.5 text-[11px] text-[#8b9a94]">{o.health_score}分</span>}
                  </button>
                )
              })}
            </div>
          )}

          <div className="flex items-center gap-2.5">
            <button className="btn-primary" disabled={selected.length < 2 || busy} onClick={() => run()}>
              {busy ? '计算中…' : `开始比较（${selected.length} 个对象）`}
            </button>
            {selected.length > 0 && <button className="btn-secondary" onClick={() => setSelected([])}>清空选择</button>}
            {selected.length === 1 && <span className="text-[12px] text-[#8b9a94]">至少再选 1 个对象</span>}
          </div>
        </div>
      </div>

      {err && <ErrorBox message={err} />}
      {msg && <Alert type={msg.includes('已提交') || msg.includes('聚合完成') ? 'success' : 'info'}>{msg}</Alert>}

      {result && !result.sufficient && !result.success && (
        <Alert type="warn">
          <div className="font-medium mb-1">{result.message}</div>
          {result.status?.upload_hint && <div className="text-[12px]">{result.status.upload_hint}</div>}
        </Alert>
      )}

      {result && (result.sufficient || result.success) && (
        <>
          <div className="card">
            <div className="card-title">
              <span>评分模型权重</span>
              <div className="flex items-center gap-2">
                <span className="text-[12px] text-[#6b7d76] font-normal tabular-nums">合计 {wSum.toFixed(2)}</span>
                <button className="btn-secondary" onClick={() => setEditW({ ...weights })}>调整权重</button>
              </div>
            </div>
            <div className="p-4">
              {result.model && (
                <Alert type={result.model.mode === 'full' ? 'success' : 'info'} >
                  <div className="font-medium mb-1">
                    {result.model.mode === 'full' ? '四维模型' : '两维模型（已降级）'}
                  </div>
                  <div className="text-[12px] leading-relaxed">{result.model.reason}</div>
                  {result.model.upgrade_hint && (
                    <div className="text-[12px] mt-1.5">{result.model.upgrade_hint}</div>
                  )}
                </Alert>
              )}
              <div className={`grid gap-3 ${isSub ? 'grid-cols-2' : 'grid-cols-2 md:grid-cols-4'} mt-3.5`}>
                {Object.entries(weights).map(([k, v]) => (
                  <div key={k} className="rounded-lg border border-[#e9eeec] p-3">
                    <div className="text-[12px] text-[#55665f] font-medium">{weightLabels[k] || k}</div>
                    <div className="text-[20px] font-semibold text-brand-700 tabular-nums mt-0.5">
                      {(Number(v) * 100).toFixed(0)}%
                    </div>
                    <div className="text-[11px] text-[#8b9a94] mt-0.5">{weightDesc[k]}</div>
                  </div>
                ))}
              </div>
              <div className="mt-3.5">
                <Alert type="info">
                  综合得分 = {' '}
                  {Object.entries(weights).map(([k, v]: [string, any], i: number) => (
                    <span key={k}>
                      {i > 0 && ' + '}
                      {weightLabels[k] || k}得分×{v}
                    </span>
                  ))}
                  。各指标标准化到 0-100。
                  {result.model?.mode === 'reduced' && ' 小类层无库存周转数据，故不涉及逆向标准化。'}
                </Alert>
              </div>
            </div>
          </div>

          <div className="card overflow-hidden">
            <div className="card-title">
              <span>表格比较</span>
              <DemoBadge text="数据来自数据库实时计算" />
            </div>
            <div className="overflow-x-auto">
              <table className="w-full min-w-[1000px]">
                <thead>
                  <tr>
                    <th className="table-th">优先级</th>
                    <th className="table-th">名称</th>
                    {isSub && <th className="table-th">所属大类</th>}
                    {isSub && <th className="table-th">ABC</th>}
                    <th className="table-th text-right">综合得分</th>
                    {Object.keys(weights).map((k) => (
                      <th key={k} className="table-th text-right">{weightLabels[k] || k}</th>
                    ))}
                    <th className="table-th text-right">销量(件)</th>
                    <th className="table-th text-right">销售额</th>
                    <th className="table-th text-right">均价</th>
                    <th className="table-th text-right">成交笔数</th>
                    {!isSub && <th className="table-th text-right">毛利额</th>}
                    {!isSub && <th className="table-th text-right">毛利率</th>}
                    {!isSub && <th className="table-th text-right">周转天数</th>}
                    {!isSub && <th className="table-th text-right">坪效</th>}
                    {!isSub && <th className="table-th text-right">缺货</th>}
                    {!isSub && <th className="table-th">健康度</th>}
                    {!isSub && <th className="table-th">需求趋势</th>}
                    {isSub && <th className="table-th text-right">关联规则</th>}
                    {isSub && <th className="table-th text-right">最高提升度</th>}
                    <th className="table-th">建议动作</th>
                  </tr>
                </thead>
                <tbody>
                  {result.items.map((r: any) => (
                    <tr key={r.id} className="hover:bg-[#f9fbfb]">
                      <td className="table-td">
                        <span className="w-6 h-6 rounded bg-brand-600 text-white text-[12px] font-semibold flex items-center justify-center">
                          {r.priority}
                        </span>
                      </td>
                      <td className="table-td font-medium">{r.name}</td>
                      {isSub && <td className="table-td text-[12px]">{r.category}</td>}
                      {isSub && (
                        <td className="table-td">
                          {r.abc_class && (
                            <span
                              className="tag"
                              style={{
                                background: r.abc_class === 'A' ? '#f0f9f4' : r.abc_class === 'B' ? '#eef4fb' : '#fffaf0',
                                color: r.abc_class === 'A' ? '#257354' : r.abc_class === 'B' ? '#2d5588' : '#a3700f',
                              }}
                            >
                              {r.abc_class}类
                            </span>
                          )}
                        </td>
                      )}
                      <td className="table-td text-right">
                        <span className="text-[15px] font-semibold text-brand-700 tabular-nums">{r.overall_score}</span>
                      </td>
                      {Object.keys(weights).map((k) => (
                        <td key={k} className="table-td text-right tabular-nums text-[#55665f]">{r.scores[k]}</td>
                      ))}
                      <td className="table-td text-right tabular-nums">{fmt.n(r.raw.sales_qty)}</td>
                      <td className="table-td text-right tabular-nums">{fmt.money(r.raw.sales_amount)}</td>
                      <td className="table-td text-right tabular-nums">{r.raw.avg_price ?? '—'}</td>
                      <td className="table-td text-right tabular-nums">{r.raw.transaction_count ?? '—'}</td>
                      {!isSub && <td className="table-td text-right tabular-nums">{fmt.money(r.raw.gross_profit)}</td>}
                      {!isSub && <td className="table-td text-right tabular-nums">{fmt.pct(r.raw.gross_margin_rate)}</td>}
                      {!isSub && <td className="table-td text-right tabular-nums">{r.raw.turnover_days}</td>}
                      {!isSub && <td className="table-td text-right tabular-nums">{r.raw.sales_per_sqm}</td>}
                      {!isSub && <td className="table-td text-right tabular-nums">{r.raw.stockout_count ?? '—'}</td>}
                      {!isSub && (
                        <td className="table-td">
                          {r.raw.category_health_score != null ? (
                            <span className="tag bg-[#eef2f0] text-[#55665f] border border-[#dde4e1]">
                              {r.raw.category_health_score} 分
                            </span>
                          ) : '—'}
                        </td>
                      )}
                      {!isSub && (
                        <td className="table-td text-[12px]">
                          {r.raw.demand_trend || <span className="text-[#a8b5b0]">无预测数据</span>}
                        </td>
                      )}
                      {isSub && <td className="table-td text-right tabular-nums">{r.raw.association_count ?? 0}</td>}
                      {isSub && <td className="table-td text-right tabular-nums">{r.raw.max_lift ?? '—'}</td>}
                      <td className="table-td">
                        <span
                          className={`tag ${
                            r.recommendation.action === '推荐保留'
                              ? 'bg-brand-50 text-brand-700 border border-brand-200'
                              : r.recommendation.action === '建议退出'
                                ? 'bg-[#fdf0f0] text-[#c13f3f] border border-[#f0cccc]'
                                : 'bg-[#fff8ec] text-[#a3700f] border border-[#f2dfb8]'
                          }`}
                        >
                          {r.recommendation.action}
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          {radarOption && (
            <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
              <div className="card">
                <div className="card-title">能力雷达图</div>
                <div className="p-4">
                  <Chart option={radarOption} height={340} title="各比较对象在各评分维度上的分布" onExport={() => {}} />
                </div>
              </div>
              <div className="card">
                <div className="card-title">综合得分与销量规模</div>
                <div className="p-4">
                  <Chart
                    option={{
                      grid: { left: 90, right: 30, top: 30, bottom: 30 },
                      tooltip: { ...TOOLTIP, trigger: 'axis' },
                      legend: { top: 0, itemWidth: 12, itemHeight: 8, textStyle: { fontSize: 11 } },
                      xAxis: { type: 'value', ...AXIS_STYLE },
                      yAxis: {
                        type: 'category',
                        data: [...result.items].reverse().map((r: any) => r.name),
                        ...AXIS_STYLE, splitLine: { show: false },
                      },
                      series: [
                        {
                          name: '综合得分', type: 'bar',
                          data: [...result.items].reverse().map((r: any) => ({
                            value: r.overall_score,
                            itemStyle: { color: '#257354', borderRadius: [0, 4, 4, 0] },
                          })),
                          barWidth: 14,
                        },
                        {
                          name: '销量(百件)', type: 'bar',
                          data: [...result.items].reverse().map((r: any) => ({
                            value: Math.round((r.raw.sales_qty || 0) / 100),
                            itemStyle: { color: '#4a7fb5', borderRadius: [0, 4, 4, 0] },
                          })),
                          barWidth: 14,
                        },
                      ],
                    }}
                    height={340}
                    title="综合得分 vs 销量规模（按百件计）"
                    onExport={() => {}}
                  />
                </div>
              </div>
            </div>
          )}

          <div className="card">
            <div className="card-title">
              <span>AI 综合判断</span>
              <DemoBadge text="结论基于上表实时计算结果" />
            </div>
            <div className="p-4 space-y-4">
              <div className="rounded-lg bg-brand-50 border border-brand-200 p-4">
                <div className="text-[12px] text-brand-700 font-medium mb-1.5">推荐优先级</div>
                <div className="flex items-center gap-2 flex-wrap">
                  {result.ai_judgement.ranking.map((r: any, i: number) => (
                    <span key={r.name} className="flex items-center gap-1.5">
                      <span className="px-2.5 py-1 rounded-md bg-white border border-brand-300 text-[13px] font-medium text-brand-800">
                        {r.priority}. {r.name}（{r.score}）
                      </span>
                      {i < result.ai_judgement.ranking.length - 1 && <span className="text-brand-500">&gt;</span>}
                    </span>
                  ))}
                </div>
              </div>

              <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
                <div className="space-y-3">
                  <div>
                    <div className="text-[12px] font-medium text-[#55665f] mb-1">为什么推荐</div>
                    <div className="text-[13px] text-[#3d5049] leading-relaxed">{result.ai_judgement.why}</div>
                  </div>
                  <div>
                    <div className="text-[12px] font-medium text-[#55665f] mb-1">关键指标</div>
                    <div className="flex flex-wrap gap-1.5">
                      {result.ai_judgement.key_metrics.map((m: string, i: number) => (
                        <span key={i} className="tag bg-brand-50 text-brand-700 border border-brand-200">{m}</span>
                      ))}
                    </div>
                  </div>
                  <div>
                    <div className="text-[12px] font-medium text-[#55665f] mb-1">最大风险</div>
                    <div className="flex flex-wrap gap-1.5">
                      {result.ai_judgement.max_risk.map((m: string, i: number) => (
                        <span key={i} className="tag bg-[#fdf0f0] text-[#c13f3f] border border-[#f0cccc]">{m}</span>
                      ))}
                    </div>
                  </div>
                  <div>
                    <div className="text-[12px] font-medium text-[#55665f] mb-1">什么情况下结论会改变</div>
                    <div className="text-[12.5px] text-[#3d5049] leading-relaxed bg-[#f7faf9] rounded-md px-3 py-2">
                      {result.ai_judgement.change_condition}
                    </div>
                  </div>
                </div>

                <div className="space-y-2.5">
                  <div className="text-[12px] font-medium text-[#55665f]">分组建议</div>
                  {[
                    ['推荐保留', result.ai_judgement.recommend_keep, 'bg-brand-50 border-brand-200 text-brand-700'],
                    ['建议观察', result.ai_judgement.suggest_watch, 'bg-[#eef2f0] border-[#dde4e1] text-[#55665f]'],
                    ['建议精简', result.ai_judgement.suggest_simplify, 'bg-[#fff8ec] border-[#f2dfb8] text-[#a3700f]'],
                    ['建议退出', result.ai_judgement.suggest_exit, 'bg-[#fdf0f0] border-[#f0cccc] text-[#c13f3f]'],
                  ].map(([label, list, cls]: any) => (
                    <div key={label} className="flex items-start gap-2.5">
                      <span className={`tag flex-shrink-0 ${cls}`}>{label}</span>
                      <span className="text-[12.5px] text-[#3d5049] pt-0.5">
                        {list.length ? list.join('、') : <span className="text-[#a8b5b0]">无</span>}
                      </span>
                    </div>
                  ))}
                </div>
              </div>

              <Alert type="warn">
                {result.ai_judgement.disclaimer}
                本次比较结果可作为 Level 3 高影响建议提交人工审批。
              </Alert>

              <div className="flex items-center gap-2 flex-wrap">
                <button className="btn-primary" onClick={submitApproval} disabled={submitting}>
                  {submitting ? '提交中…' : '提交审批'}
                </button>
                <button className="btn-secondary" onClick={() => setMsg('建议已暂缓，可在下一周期复评时重新比较。')}>暂缓</button>
                <button className="btn-secondary" onClick={() => setMsg('该比较结果已驳回，不会进入审批流程。')}>驳回</button>
                <button className="btn-ghost" onClick={() => { setResult(null); setSelected([]) }}>重新选择</button>
              </div>
            </div>
          </div>
        </>
      )}

      {!result && !err && (
        <Empty
          title="请先选择 2-6 个比较对象"
          hint="选择后点击「开始比较」，系统会按当前权重实时计算各维度得分、综合排序，并给出可解释的 AI 判断与建议动作。"
        />
      )}

      <Modal open={!!editW} onClose={() => setEditW(null)} title="调整评分模型权重" width="max-w-lg">
        <div className="space-y-4">
          <Alert type="info">
            权重之和必须等于 1。
            {isSub
              ? '小类层当前只有销量与销售额两个可用维度。'
              : '品类模型默认：销量 30% + 毛利 30% + 周转 20% + 坪效 20%。库存周转天数为逆向指标（越低越好）。'}
          </Alert>
          {editW &&
            Object.keys(editW).map((k) => (
              <div key={k}>
                <div className="flex items-center justify-between mb-1.5">
                  <label className="label mb-0">{weightLabels[k] || k}</label>
                  <span className="text-[13px] font-medium text-brand-700 tabular-nums">
                    {(Number(editW[k]) * 100).toFixed(0)}%
                  </span>
                </div>
                <input
                  type="range" min={0} max={1} step={0.05} value={editW[k]}
                  onChange={(e) => setEditW({ ...editW, [k]: Number(e.target.value) })}
                  className="w-full accent-[#257354]"
                />
                <div className="text-[11px] text-[#8b9a94]">{weightDesc[k]}</div>
              </div>
            ))}
          <div className="flex items-center justify-between pt-2 border-t border-[#eef2f0]">
            <span className="text-[12.5px] text-[#55665f]">
              合计：
              <span className={Math.abs(Object.values(editW || {}).reduce((a: number, b: any) => a + Number(b), 0) - 1) > 0.001 ? 'text-[#c13f3f]' : 'text-brand-700'}>
                {editW ? Object.values(editW).reduce((a: number, b: any) => a + Number(b), 0).toFixed(2) : '1.00'}
              </span>
            </span>
            <div className="flex gap-2">
              <button className="btn-secondary" onClick={() => setEditW(null)}>取消</button>
              <button className="btn-primary" onClick={applyWeights}>应用并重新计算</button>
            </div>
          </div>
        </div>
      </Modal>
    </div>
  )
}
