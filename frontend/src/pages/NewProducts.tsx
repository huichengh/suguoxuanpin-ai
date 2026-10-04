import { useEffect, useState } from 'react'
import { Alert, DemoBadge, Empty, ErrorBox, Loading, Modal, SectionTitle, Tabs } from '../components/ui'
import { api } from '../services/api'

const EMPTY_FORM = {
  name: '', category_id: '', brand: '', purchase_price: '', suggested_retail_price: '',
  expected_margin_rate: '', supplier: '', target_consumer: '', spec: '', packaging: '',
  season: '', selling_point: '', is_private_label: false, reference_sku: '',
}

const FIELD_GROUPS = [
  {
    title: '基础信息',
    fields: [
      { key: 'name', label: '商品名称', required: true, w: 2 },
      { key: 'brand', label: '品牌', w: 1 },
      { key: 'category_id', label: '所属品类', type: 'category', required: true, w: 1 },
      { key: 'supplier', label: '供应商', w: 1 },
    ],
  },
  {
    title: '价格与毛利',
    fields: [
      { key: 'purchase_price', label: '采购价（元）', type: 'number' },
      { key: 'suggested_retail_price', label: '建议零售价（元）', type: 'number' },
      { key: 'expected_margin_rate', label: '预计毛利率（%）', type: 'number' },
    ],
  },
  {
    title: '客群与规格',
    fields: [
      { key: 'target_consumer', label: '目标消费者', w: 2 },
      { key: 'spec', label: '规格' },
      { key: 'packaging', label: '包装' },
      { key: 'season', label: '季节' },
    ],
  },
  {
    title: '其他',
    fields: [
      { key: 'selling_point', label: '新品卖点', type: 'textarea', w: 4 },
      { key: 'reference_sku', label: '参考同类SKU', w: 2 },
      { key: 'is_private_label', label: '自有品牌/品牌商品', type: 'bool', w: 2 },
    ],
  },
]

export default function NewProducts() {
  const [list, setList] = useState<any>(null)
  const [cats, setCats] = useState<any[]>([])
  const [err, setErr] = useState('')
  const [open, setOpen] = useState(false)
  const [form, setForm] = useState<any>(EMPTY_FORM)
  const [result, setResult] = useState<any>(null)
  const [busy, setBusy] = useState(false)
  const [tab, setTab] = useState('pool')

  const load = () => {
    setErr('')
    Promise.all([api.newProducts(), api.categories()])
      .then(([d, c]) => { setList(d); setCats(c) })
      .catch((e) => setErr(e.message))
  }
  useEffect(load, [])

  const submit = async () => {
    if (!form.name || !form.category_id) {
      setErr('商品名称与所属品类为必填项')
      return
    }
    setBusy(true)
    setErr('')
    try {
      const payload: any = { ...form, category_id: Number(form.category_id) }
      for (const k of ['purchase_price', 'suggested_retail_price', 'expected_margin_rate']) {
        payload[k] = payload[k] === '' ? null : Number(payload[k])
      }
      const d = await api.evaluateNewProduct(payload)
      setResult(d)
      setForm(EMPTY_FORM)
      load()
    } catch (e: any) {
      setErr(e.message)
    } finally {
      setBusy(false)
    }
  }

  const del = async (id: number) => {
    await api.deleteCandidate(id)
    load()
  }

  if (err && !list) return <ErrorBox message={err} onRetry={load} />
  if (!list) return <Loading />

  const levelStyle = (l: string) =>
    l === '高潜力'
      ? { bg: '#f0f9f4', color: '#257354' }
      : l === '中等潜力'
        ? { bg: '#fffaf0', color: '#a3700f' }
        : { bg: '#f7faf9', color: '#6b7d76' }

  return (
    <div className="space-y-4 max-w-[1680px]">
      <div className="flex items-center justify-between gap-4 flex-wrap">
        <div>
          <h1 className="text-[19px] font-semibold text-[#1a2b24]">新品评估</h1>
          <p className="text-[12.5px] text-[#6b7d76] mt-0.5">
            解释型潜力评估（高潜力 / 中等潜力 / 谨慎试销），不输出成功概率等虚构精度
          </p>
        </div>
        <div className="flex items-center gap-2">
          <DemoBadge />
          <button className="btn-primary" onClick={() => { setOpen(true); setResult(null); setForm(EMPTY_FORM) }}>
            + 录入新品候选
          </button>
        </div>
      </div>

      <Tabs
        active={tab}
        onChange={setTab}
        items={[
          { key: 'pool', label: '候选池', badge: list.count },
          { key: 'rule', label: '评估规则说明' },
        ]}
      />

      {tab === 'pool' && (
        <div className="space-y-4">
          {list.count === 0 ? (
            <Empty
              title="新品候选池为空"
              hint="点击右上角「录入新品候选」录入商品信息。系统会结合所属品类的健康度、需求趋势与新品资料完整度，给出解释型潜力等级与试销建议。"
            />
          ) : (
            <div className="card overflow-hidden">
              <div className="card-title">新品候选池（{list.count}）</div>
              <div className="overflow-x-auto">
                <table className="w-full min-w-[1000px]">
                  <thead>
                    <tr>
                      <th className="table-th">商品名称</th>
                      <th className="table-th">品类</th>
                      <th className="table-th">品牌</th>
                      <th className="table-th">供应商</th>
                      <th className="table-th text-right">采购价</th>
                      <th className="table-th text-right">建议零售价</th>
                      <th className="table-th text-right">资料完整度</th>
                      <th className="table-th">潜力等级</th>
                      <th className="table-th">录入人</th>
                      <th className="table-th"></th>
                    </tr>
                  </thead>
                  <tbody>
                    {list.items.map((r: any) => (
                      <tr key={r.id}>
                        <td className="table-td font-medium">
                          {r.name}
                          {r.is_private_label && (
                            <span className="tag bg-brand-50 text-brand-700 border border-brand-200 ml-1.5">自有品牌</span>
                          )}
                        </td>
                        <td className="table-td">{r.category || '—'}</td>
                        <td className="table-td">{r.brand || '—'}</td>
                        <td className="table-td text-[12px]">{r.supplier || '—'}</td>
                        <td className="table-td text-right tabular-nums">{r.purchase_price ?? '—'}</td>
                        <td className="table-td text-right tabular-nums">{r.suggested_retail_price ?? '—'}</td>
                        <td className="table-td text-right">
                          <div className="flex items-center gap-1.5 justify-end">
                            <span className="tabular-nums text-[12px]">{r.completeness_score}%</span>
                            <div className="w-10 h-1.5 rounded-full bg-[#eef2f0] overflow-hidden">
                              <div
                                className="h-full rounded-full"
                                style={{
                                  width: `${r.completeness_score}%`,
                                  background: r.completeness_score >= 70 ? '#257354' : r.completeness_score >= 50 ? '#d9a520' : '#e8833a',
                                }}
                              />
                            </div>
                          </div>
                        </td>
                        <td className="table-td">
                          <span className="tag" style={{ background: levelStyle(r.potential_level).bg, color: levelStyle(r.potential_level).color }}>
                            {r.potential_level}
                          </span>
                        </td>
                        <td className="table-td text-[12px] text-[#8b9a94]">{r.created_by}</td>
                        <td className="table-td">
                          <button className="text-[12px] text-[#c13f3f] hover:underline" onClick={() => del(r.id)}>
                            删除
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </div>
      )}

      {tab === 'rule' && (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          <div className="card">
            <div className="card-title">评估维度</div>
            <div className="p-4 space-y-2.5">
              {[
                ['新品资料完整度', '按 14 个字段的填充情况加权计算，权重按字段重要性分配（如商品名称10分、新品卖点9分、采购价8分）'],
                ['同类品类健康度', '取所属品类的健康度综合得分（权重50%），≥70分额外加20分'],
                ['需求趋势', '取所属品类的需求预测趋势：上涨+20分，下跌-15分，稳定不加分'],
                ['资料完整度修正', '完整度 × 0.2 计入总分，完整度低于60%时明确提示评估置信度有限'],
              ].map(([t, d]) => (
                <div key={t} className="rounded-lg border border-[#e9eeec] bg-[#f7faf9] p-3">
                  <div className="text-[12.5px] font-medium text-[#2c3d36]">{t}</div>
                  <div className="text-[11.5px] text-[#8b9a94] mt-0.5 leading-relaxed">{d}</div>
                </div>
              ))}
            </div>
          </div>
          <div className="card">
            <div className="card-title">等级判定与风险</div>
            <div className="p-4 space-y-3">
              <div className="grid grid-cols-3 gap-2">
                {[
                  ['高潜力', '总分 ≥ 75', '#f0f9f4', '#257354'],
                  ['中等潜力', '总分 55-74', '#fffaf0', '#a3700f'],
                  ['谨慎试销', '总分 < 55', '#f7faf9', '#6b7d76'],
                ].map(([l, r, bg, c]: any) => (
                  <div key={l} className="rounded-lg border p-3 text-center" style={{ background: bg, borderColor: `${c}33` }}>
                    <div className="text-[13px] font-medium" style={{ color: c }}>{l}</div>
                    <div className="text-[11px] mt-0.5" style={{ color: c, opacity: 0.75 }}>{r}</div>
                  </div>
                ))}
              </div>
              <Alert type="warn">
                <div className="text-[12px] leading-relaxed">
                  平台<b>不输出「成功概率 87%」这类看似精确的数值</b>。
                  新品上市初期销量存在不确定性，缺少同类 SKU 实际销售数据时无法量化成功率，
                  因此只给出解释型等级 + 试销建议。
                </div>
              </Alert>
              <div>
                <SectionTitle>固定风险提示</SectionTitle>
                <ul className="space-y-1.5">
                  {[
                    '缺少同类 SKU 实际销售数据，无法给出量化成功概率',
                    '参考同类 SKU 表现仍需结合实际试销验证',
                    '新品上市初期销量存在不确定性，建议设置退出条件',
                  ].map((t, i) => (
                    <li key={i} className="flex items-start gap-2 text-[12.5px] text-[#3d5049]">
                      <span className="text-brand-500 mt-0.5">▸</span>
                      <span>{t}</span>
                    </li>
                  ))}
                </ul>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* 录入弹窗 */}
      <Modal open={open} onClose={() => setOpen(false)} title="录入新品候选" width="max-w-4xl">
        <div className="space-y-4">
          {result && (
            <Alert type="success">
              <div className="font-medium mb-1.5">
                评估完成：{result.potential_level}（资料完整度 {result.completeness_score}%）
              </div>
              <ul className="space-y-1 text-[12px]">
                {result.reasons.map((r: string, i: number) => (
                  <li key={i}>· {r}</li>
                ))}
              </ul>
              <div className="text-[12px] mt-2">试销建议：{result.trial_suggestion}</div>
            </Alert>
          )}

          {FIELD_GROUPS.map((g) => (
            <div key={g.title}>
              <div className="text-[12.5px] font-medium text-[#55665f] mb-2">{g.title}</div>
              <div className="grid grid-cols-4 gap-3">
                {g.fields.map((f: any) => (
                  <div key={f.key} style={{ gridColumn: `span ${f.w || 1}` }}>
                    <label className="label">
                      {f.label}
                      {f.required && <span className="text-[#c13f3f] ml-0.5">*</span>}
                    </label>
                    {f.type === 'textarea' ? (
                      <textarea
                        className="input"
                        rows={2}
                        value={form[f.key]}
                        placeholder="如：同等规格下价格低15%，本地直采当日达"
                        onChange={(e) => setForm({ ...form, [f.key]: e.target.value })}
                      />
                    ) : f.type === 'bool' ? (
                      <select
                        className="input"
                        value={form[f.key] ? '1' : '0'}
                        onChange={(e) => setForm({ ...form, [f.key]: e.target.value === '1' })}
                      >
                        <option value="0">品牌商品</option>
                        <option value="1">自有品牌</option>
                      </select>
                    ) : f.type === 'category' ? (
                      <select
                        className="input"
                        value={form[f.key]}
                        onChange={(e) => setForm({ ...form, [f.key]: e.target.value })}
                      >
                        <option value="">请选择</option>
                        {cats.map((c) => (
                          <option key={c.id} value={c.id}>
                            {c.name}（健康度 {c.health_score}分）
                          </option>
                        ))}
                      </select>
                    ) : (
                      <input
                        className="input"
                        type={f.type === 'number' ? 'number' : 'text'}
                        step="0.01"
                        value={form[f.key]}
                        onChange={(e) => setForm({ ...form, [f.key]: e.target.value })}
                      />
                    )}
                  </div>
                ))}
              </div>
            </div>
          ))}

          {err && <Alert type="error">{err}</Alert>}

          <Alert type="info">
            填写的字段越完整，评估置信度越高。缺少字段时平台会在结果中明确列出，不会用默认值填充。
          </Alert>
        </div>

        <div className="flex justify-end gap-2 mt-5 pt-4 border-t border-[#eef2f0]">
          <button className="btn-secondary" onClick={() => setOpen(false)}>关闭</button>
          <button className="btn-primary" onClick={submit} disabled={busy}>
            {busy ? '评估中…' : '提交评估'}
          </button>
        </div>
      </Modal>
    </div>
  )
}
