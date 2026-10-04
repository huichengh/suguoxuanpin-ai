import { useEffect, useState } from 'react'
import { Chart, AXIS_STYLE, TOOLTIP, PALETTE } from '../components/Chart'
import {
  Alert, DemoBadge, Empty, ErrorBox, Loading, SectionTitle, SourceTag, Tabs,
} from '../components/ui'
import { api, fmt } from '../services/api'

export default function Association() {
  const [data, setData] = useState<any>(null)
  const [err, setErr] = useState('')
  const [params, setParams] = useState<any>({ min_support: 0.02, min_confidence: 0.5, min_lift: 1.5, top_n: 20 })
  const [busy, setBusy] = useState(false)
  const [view, setView] = useState<'realtime' | 'attachment'>('realtime')
  const [advanced, setAdvanced] = useState(false)
  const [item, setItem] = useState<string | null>(null)
  const [profile, setProfile] = useState<any>(null)
  const [msg, setMsg] = useState('')

  const load = () => {
    setErr('')
    api.association().then(setData).catch((e) => setErr(e.message))
  }
  useEffect(load, [])

  useEffect(() => {
    if (data?.params) setParams((p: any) => ({ ...p, ...data.params }))
  }, [data])

  const recalc = async () => {
    setBusy(true)
    setMsg('')
    try {
      const d = await api.recalcAssociation({ ...params, save: true })
      setMsg(
        `重算完成：${d.basket_count} 笔交易篮 / ${d.item_count} 个商品项 → ${d.rules.length} 条规则通过阈值，耗时 ${d.duration_ms}ms。` +
        `聚合字段：${params.group_by === 'sku_code' ? '商品编码' : '商品名称'}`
      )
      load()
    } catch (e: any) {
      setErr(e.message)
    } finally {
      setBusy(false)
    }
  }

  const clickItem = async (name: string) => {
    setItem(name)
    setProfile(null)
    try {
      setProfile(await api.itemProfile(name))
    } catch (e: any) {
      setProfile({ error: e.message })
    }
  }

  if (err && !data) return <ErrorBox message={err} onRetry={load} />
  if (!data) return <Loading text="正在加载关联规则…" />

  const rt = data.realtime_rules
  const att = data.attachment_rules
  const shown = view === 'realtime' ? rt : att

  // 网络图
  const net = data.network
  const nodeSize = (n: any) => 18 + Math.min(22, n.value * 3)
  const networkOption = {
    tooltip: {
      ...TOOLTIP,
      trigger: 'item',
      formatter: (p: any) => {
        if (p.dataType === 'edge') {
          return `${p.data.source} → ${p.data.target}<br/>提升度 <b>${p.data.value}</b><br/>置信度 ${(p.data.confidence * 100).toFixed(1)}%<br/>支持度 ${(p.data.support * 100).toFixed(2)}%`
        }
        return `${p.name}<br/>关联规则中出现 ${p.data.value} 次`
      },
    },
    legend: [{ data: ['极强关联', '强关联', '中等关联'], top: 0, itemWidth: 12, itemHeight: 8, textStyle: { fontSize: 11 } }],
    series: [
      {
        type: 'graph',
        layout: 'force',
        roam: true,
        draggable: true,
        force: { repulsion: 320, edgeLength: [70, 150], gravity: 0.08 },
        data: net.nodes.map((n: any) => ({
          name: n.name,
          value: n.value,
          symbolSize: nodeSize(n),
          itemStyle: { color: item === n.name ? '#e8833a' : '#257354' },
          label: { show: n.value > 1, fontSize: 10, color: '#33473f' },
        })),
        edgeSymbol: ['none', 'arrow'],
        edgeSymbolSize: 6,
        labelLayout: { hideOverlap: true },
        lineStyle: { curveness: 0.12 },
        emphasis: { focus: 'adjacency', lineStyle: { width: 4 } },
        edges: net.edges.map((e: any) => ({
          source: e.source,
          target: e.target,
          value: e.value,
          confidence: e.confidence,
          support: e.support,
          lineStyle: {
            width: Math.min(5, Math.max(1, e.lift / 4)),
            opacity: 0.55,
            color: e.lift >= 10 ? '#d94a4a' : e.lift >= 5 ? '#e8833a' : '#8bcbaa',
          },
          label: {
            show: false,
            formatter: `${e.lift}`,
            fontSize: 9,
            color: '#8b9a94',
          },
        })),
      },
    ],
  }

  const liftOption = {
    grid: { left: 110, right: 50, top: 30, bottom: 40 },
    tooltip: {
      ...TOOLTIP,
      formatter: (p: any) => {
        const r = shown[p.dataIndex]
        return `${r.display_rule}<br/>提升度 <b>${r.lift}</b><br/>置信度 ${(r.confidence * 100).toFixed(1)}%<br/>支持度 ${(r.support * 100).toFixed(2)}%<br/>${r.strength}`
      },
    },
    xAxis: { type: 'value', ...AXIS_STYLE, name: '提升度 Lift', nameLocation: 'middle', nameGap: 26 },
    yAxis: {
      type: 'category',
      data: [...shown].slice(0, 15).reverse().map((r: any) => r.display_rule),
      ...AXIS_STYLE,
      splitLine: { show: false },
      axisLabel: { ...AXIS_STYLE.axisLabel, fontSize: 10, width: 100, overflow: 'truncate' },
    },
    series: [{
      type: 'bar',
      data: [...shown].slice(0, 15).reverse().map((r: any) => ({
        value: r.lift,
        itemStyle: { color: r.lift >= 10 ? '#d94a4a' : r.lift >= 5 ? '#e8833a' : '#57ad84', borderRadius: [0, 4, 4, 0] },
      })),
      barWidth: 13,
      label: { show: true, position: 'right', fontSize: 10, color: '#55665f', formatter: (p: any) => p.value.toFixed(2) },
    }],
  }

  const failedAtt = att.filter((r: any) => !r.passes_threshold)

  return (
    <div className="space-y-4 max-w-[1680px]">
      <div className="flex items-center justify-between gap-4 flex-wrap">
        <div>
          <h1 className="text-[19px] font-semibold text-[#1a2b24]">关联陈列分析</h1>
          <p className="text-[12.5px] text-[#6b7d76] mt-0.5">
            数据源：dataset_transactions_sample.csv ｜ 购物篮构建：交易号 + 商品名称
            （演示数据商品编码高度离散，同一商品名称存在多个编码，按编码分析会得到无意义规则）
          </p>
        </div>
        <DemoBadge text="附件参考结果与实时重算结果严格区分" />
      </div>

      {msg && <Alert type="success">{msg}</Alert>}

      {/* 参数面板 */}
      <div className="card">
        <div className="card-title">
          <span>Apriori 算法参数</span>
          <div className="flex items-center gap-2">
            <button className="btn-ghost text-[12px]" onClick={() => setAdvanced(!advanced)}>
              {advanced ? '收起高级设置' : '高级设置'}
            </button>
            <button className="btn-primary" onClick={recalc} disabled={busy}>
              {busy ? '重算中…' : '重新计算'}
            </button>
          </div>
        </div>
        <div className="p-4">
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            {[
              ['min_support', '最小支持度', 0.001, 0.5, 0.005],
              ['min_confidence', '最小置信度', 0.05, 0.95, 0.05],
              ['min_lift', '最小提升度', 1.0, 30, 0.5],
              ['top_n', 'TopN 规则数', 5, 100, 5],
            ].map(([k, label, min, max, step]: any) => (
              <div key={k}>
                <label className="label">{label}</label>
                <input
                  type="number"
                  className="input tabular-nums"
                  value={params[k]}
                  min={min}
                  max={max}
                  step={step}
                  onChange={(e) => setParams({ ...params, [k]: Number(e.target.value) })}
                />
              </div>
            ))}
          </div>

          {advanced && (
            <div className="mt-3.5 pt-3.5 border-t border-[#eef2f0] space-y-3">
              <div className="flex items-center gap-3">
                <label className="label mb-0 flex-shrink-0">购物篮聚合字段</label>
                <select
                  className="input w-auto"
                  value={params.group_by}
                  onChange={(e) => setParams({ ...params, group_by: e.target.value })}
                >
                  <option value="product_name">商品名称（演示数据默认）</option>
                  <option value="sku_code">商品编码（真实企业数据，SKU编码稳定时使用）</option>
                </select>
              </div>
              <Alert type="info">
                当前附件的商品编码高度离散（同一商品名称存在多个不同编码），
                因此默认按「交易号 + 商品名称」构建购物篮。真实企业数据接入后 SKU 编码稳定，可切换为商品编码分析。
              </Alert>
            </div>
          )}
        </div>
      </div>

      {/* 数据治理说明 */}
      <Alert type="warn">
        <div className="font-medium mb-1">数据治理说明：附件结果与实时结果并存</div>
        <div className="text-[12px] leading-relaxed">
          附件预置了 {data.summary.attachment_count} 条关联规则，其中 <b>{data.summary.attachment_passed}</b> 条通过当前默认阈值，
          <b>{failedAtt.length}</b> 条未通过。平台原样保留附件结果、不做修改；
          实时重算结果按当前阈值过滤。下方切换标签可分别查看两类结果，每条规则都标注「来源」与「是否通过当前参数阈值」。
        </div>
      </Alert>

      <Tabs
        active={view}
        onChange={(k) => setView(k as any)}
        items={[
          { key: 'realtime', label: '实时重算结果', badge: rt.length },
          { key: 'attachment', label: '附件参考结果', badge: att.length },
        ]}
      />

      {/* 规则表 */}
      <div className="card overflow-hidden">
        <div className="card-title">
          <span>{view === 'realtime' ? '根据交易数据实时重算的关联规则' : '附件预置参考关联规则'}</span>
          <div className="flex items-center gap-2">
            <span className="text-[12px] text-[#6b7d76] font-normal">
              阈值 support≥{data.params.min_support} / confidence≥{data.params.min_confidence} / lift≥{data.params.min_lift}
            </span>
            <SourceTag source={view} />
          </div>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full min-w-[1080px]">
            <thead>
              <tr>
                <th className="table-th">#</th>
                <th className="table-th">前项商品</th>
                <th className="table-th">后项商品</th>
                <th className="table-th text-right">支持度</th>
                <th className="table-th text-right">置信度</th>
                <th className="table-th text-right">提升度</th>
                <th className="table-th">关联强度</th>
                <th className="table-th">业务解释</th>
                <th className="table-th">陈列建议</th>
                <th className="table-th">阈值校验</th>
                <th className="table-th">来源</th>
              </tr>
            </thead>
            <tbody>
              {shown.length === 0 ? (
                <tr><td colSpan={11} className="table-td text-center text-[#8b9a94] py-8">当前阈值下无规则</td></tr>
              ) : (
                shown.map((r: any, i: number) => (
                  <tr
                    key={`${r.source}-${i}`}
                    onClick={() => clickItem(r.consequent)}
                    className="cursor-pointer hover:bg-[#f9fbfb]"
                  >
                    <td className="table-td tabular-nums text-[#8b9a94]">{i + 1}</td>
                    <td className="table-td font-medium">{r.antecedent}</td>
                    <td className="table-td font-medium">{r.consequent}</td>
                    <td className="table-td text-right tabular-nums">{(r.support * 100).toFixed(2)}%</td>
                    <td className="table-td text-right tabular-nums">{(r.confidence * 100).toFixed(2)}%</td>
                    <td className="table-td text-right">
                      <span
                        className="font-semibold tabular-nums"
                        style={{ color: r.lift >= 10 ? '#d94a4a' : r.lift >= 5 ? '#c96a1f' : '#257354' }}
                      >
                        {r.lift}
                      </span>
                    </td>
                    <td className="table-td">
                      <span
                        className="tag"
                        style={{
                          background: r.lift >= 10 ? '#fdf0f0' : r.lift >= 5 ? '#fff8ec' : '#f0f9f4',
                          color: r.lift >= 10 ? '#c13f3f' : r.lift >= 5 ? '#a3700f' : '#257354',
                        }}
                      >
                        {r.strength}
                      </span>
                    </td>
                    <td className="table-td text-[11.5px] text-[#55665f] max-w-[280px] leading-relaxed">
                      {r.business_explanation}
                    </td>
                    <td className="table-td text-[11.5px] text-[#3d5049] max-w-[200px] leading-relaxed">
                      {r.display_suggestion}
                    </td>
                    <td className="table-td text-[11px]">
                      <span className={r.passes_threshold ? 'text-brand-600' : 'text-[#a3700f]'}>
                        {r.passes_threshold ? '✓ 通过' : '✗ 未通过'}
                      </span>
                      <div className="text-[10px] text-[#a8b5b0] mt-0.5">{r.threshold_check}</div>
                    </td>
                    <td className="table-td"><SourceTag source={r.source} /></td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* 网络图 + 提升度图 */}
      <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
        <div className="card">
          <div className="card-title">
            <span>关联网络图</span>
            <span className="text-[12px] text-[#6b7d76] font-normal">点击节点查看商品画像 · 可拖拽/缩放</span>
          </div>
          <div className="p-4">
            <Chart option={networkOption} height={400} title="商品关联网络（连线粗细=提升度）" onExport={() => {}} />
          </div>
        </div>

        <div className="card">
          <div className="card-title">提升度排行</div>
          <div className="p-4">
            <Chart option={liftOption} height={400} title="Top15 关联规则提升度" onExport={() => {}} />
          </div>
        </div>
      </div>

      {/* 商品画像 */}
      {item && (
        <div className="card">
          <div className="card-title">
            <span>商品画像：{item}</span>
            <button className="text-[#8b9a94] hover:text-[#33473f] text-lg" onClick={() => { setItem(null); setProfile(null) }}>×</button>
          </div>
          <div className="p-4">
            {!profile ? (
              <Loading text="查询关联商品…" />
            ) : profile.error ? (
              <Alert type="warn">{profile.error}</Alert>
            ) : (
              <div className="space-y-4">
                <div className="grid grid-cols-3 gap-3">
                  {[
                    ['出现规则数', profile.rule_count],
                    ['关联商品数', profile.top_relations.length],
                    ['最强行数', profile.top_relations[0]?.partner || '—'],
                  ].map(([k, v]: any) => (
                    <div key={k} className="rounded-lg bg-[#f7faf9] border border-[#eef2f0] p-3">
                      <div className="text-[11.5px] text-[#8b9a94]">{k}</div>
                      <div className="text-[18px] font-semibold text-brand-700 mt-0.5">{v}</div>
                    </div>
                  ))}
                </div>
                <div>
                  <SectionTitle>最强关联商品</SectionTitle>
                  <div className="space-y-2">
                    {profile.top_relations.map((t: any, i: number) => (
                      <div key={i} className="flex items-center gap-3 px-3 py-2.5 rounded-lg border border-[#e9eeec]">
                        <span className="w-6 h-6 rounded bg-brand-50 text-brand-700 text-[11px] flex items-center justify-center font-medium flex-shrink-0">
                          {i + 1}
                        </span>
                        <span className="text-[13px] font-medium text-[#1a2b24]">{t.partner}</span>
                        <span className="tag bg-[#eef2f0] text-[#6b7d76] border border-[#dde4e1]">{t.direction}</span>
                        <span className="text-[12px] text-[#55665f] ml-auto tabular-nums">
                          提升度 <b className="text-[#c96a1f]">{t.lift}</b> ｜ 置信度 {(t.confidence * 100).toFixed(1)}% ｜ 支持度 {(t.support * 100).toFixed(2)}%
                        </span>
                        <span className="text-[11.5px] text-[#8b9a94]">
                          建议：{t.partner} 与 {item} 相邻陈列
                        </span>
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            )}
          </div>
        </div>
      )}

      <Alert type="info">{data.data_note}</Alert>
    </div>
  )
}
