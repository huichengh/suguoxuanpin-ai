import { useEffect, useRef, useState } from 'react'
import { Alert, DemoBadge, Empty, Loading } from '../components/ui'
import { api } from '../services/api'

export default function AgentChat() {
  const [msgs, setMsgs] = useState<any[]>([])
  const [input, setInput] = useState('')
  const [busy, setBusy] = useState(false)
  const [session, setSession] = useState<string>('')
  const [tools, setTools] = useState<any>(null)
  const [showTools, setShowTools] = useState(false)
  const endRef = useRef<HTMLDivElement>(null)
  const taRef = useRef<HTMLTextAreaElement>(null)
  const sendRef = useRef<(q?: string) => void>(() => {})

  useEffect(() => {
    api.agentTools().then(setTools).catch(() => {})
  }, [])

  // 演示预置：自动提问并展示回答
  useEffect(() => {
    let preset: any = null
    try { preset = JSON.parse(sessionStorage.getItem('suguo_demo_preset') || 'null') } catch { /* 忽略 */ }
    if (!preset?.autoAsk) return
    sessionStorage.removeItem('suguo_demo_preset')
    const t = setTimeout(() => sendRef.current(preset.autoAsk), 600)
    return () => clearTimeout(t)
  }, [])

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [msgs])

  const send = async (q?: string) => {
    const question = (q ?? input).trim()
    if (!question || busy) return
    setMsgs((m) => [...m, { role: 'user', content: question, ts: new Date() }])
    setInput('')
    setBusy(true)
    try {
      const d = await api.chat(question, session || undefined)
      setSession(d.session_id)
      setMsgs((m) => [...m, { role: 'assistant', answer: d.answer, ts: new Date() }])
    } catch (e: any) {
      setMsgs((m) => [...m, { role: 'error', content: e.message, ts: new Date() }])
    } finally {
      setBusy(false)
      taRef.current?.focus()
    }
  }

  sendRef.current = send

  const onKey = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      send()
    }
  }

  const suggestions = [
    '现在门店的商品结构有哪些问题？',
    '哪些品类健康度比较差？',
    '比较生鲜蔬果和纺织服装',
    '牛奶和面包的关联度有多高？',
    '火锅底料和丸子适合一起陈列吗？',
    '未来4期哪些品类需求上涨？',
    '哪些品类缺货比较频繁？',
    '哪个品类适合做自有品牌？',
    '生成综合选品方案',
    '查看风险预警',
    '当前有哪些数据质量问题？',
    'SKU级别有数据吗',
  ]

  return (
    <div className="flex gap-4 max-w-[1680px] h-[calc(100vh-115px)]">
      {/* 对话区 */}
      <div className="flex-1 card flex flex-col min-w-0">
        <div className="card-title flex-shrink-0">
          <div className="flex items-center gap-2.5">
            <span className="w-7 h-7 rounded-md bg-brand-600 text-white flex items-center justify-center text-[13px] font-semibold">
              AI
            </span>
            <div>
              <div className="text-[14px] font-semibold leading-tight">苏果智选AI</div>
              <div className="text-[11px] text-[#8b9a94] font-normal leading-tight">
                社区商超智能选品决策助手 · 每次回答均调用后台工具取真实计算结果
              </div>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <DemoBadge />
            {msgs.length > 0 && (
              <button
                className="btn-ghost text-[12px]"
                onClick={() => { setMsgs([]); setSession('') }}
              >
                清空对话
              </button>
            )}
          </div>
        </div>

        {/* 消息列表 */}
        <div className="flex-1 overflow-y-auto p-5 space-y-4 bg-[#fbfcfc]">
          {!msgs.length && (
            <div className="py-8">
              <Empty
                title="我是苏果智选AI，可以帮你做品类诊断、商品比较、关联陈列分析和需求预测判断"
                hint="所有量化结论都来自平台数据库与算法实时计算结果。信息不足时我会明确告诉你缺什么数据，不会编造。"
              />
              <div className="mt-5">
                <div className="text-[12px] font-medium text-[#55665f] mb-2.5 text-center">试试这些问题</div>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-2 max-w-3xl mx-auto">
                  {suggestions.map((s) => (
                    <button
                      key={s}
                      onClick={() => send(s)}
                      className="text-left px-3 py-2 rounded-lg border border-[#e3e8e6] text-[12.5px] text-[#3d5049] hover:border-brand-300 hover:bg-brand-50 transition-colors"
                    >
                      {s}
                    </button>
                  ))}
                </div>
              </div>
            </div>
          )}

          {msgs.map((m, i) =>
            m.role === 'user' ? (
              <div key={i} className="flex justify-end">
                <div className="max-w-[76%] rounded-lg px-4 py-2.5 bg-brand-600 text-white text-[13.5px] leading-relaxed">
                  {m.content}
                </div>
              </div>
            ) : m.role === 'error' ? (
              <div key={i} className="max-w-[86%]">
                <Alert type="error">{m.content}</Alert>
              </div>
            ) : (
              <AnswerBlock key={i} a={m.answer} onItemClick={(name) => send(`${name}的关联商品有哪些？`)} />
            ),
          )}

          {busy && (
            <div className="flex items-center gap-2 text-[12.5px] text-[#8b9a94]">
              <span className="w-3.5 h-3.5 border-2 border-brand-200 border-t-brand-600 rounded-full animate-spin" />
              正在调用后台工具计算…
            </div>
          )}
          <div ref={endRef} />
        </div>

        {/* 输入框 */}
        <div className="border-t border-[#e3e8e6] p-3.5 flex-shrink-0">
          <div className="flex gap-2">
            <textarea
              ref={taRef}
              className="input resize-none"
              rows={2}
              placeholder="问点具体的，例如「比较生鲜蔬果和日化清洁」或「哪些品类该精简」…（Enter 发送，Shift+Enter 换行）"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={onKey}
            />
            <button className="btn-primary px-5 self-stretch" onClick={() => send()} disabled={busy || !input.trim()}>
              发送
            </button>
          </div>
        </div>
      </div>

      {/* 侧栏：AI 能力说明 */}
      <div className="w-[290px] flex-shrink-0 space-y-3 overflow-y-auto">
        <div className="card">
          <div className="card-title py-3">AI 能力与约束</div>
          <div className="p-4 space-y-3">
            {[
              ['数据优先', '量化结论必须来自数据库与算法结果，信息不足时明确拒绝推测'],
              ['可解释', '每条建议说明依据、关键指标、最大风险与是否需人工确认'],
              ['人工决策', '不自动执行下单、改价、淘汰供应商、删除商品等操作'],
              ['区分数据来源', '附件参考结果与实时重算结果分别标注，解释差异来源'],
            ].map(([t, d]) => (
              <div key={t}>
                <div className="text-[12.5px] font-medium text-[#33473f]">{t}</div>
                <div className="text-[11.5px] text-[#8b9a94] leading-relaxed mt-0.5">{d}</div>
              </div>
            ))}
          </div>
        </div>

        <div className="card">
          <div className="card-title py-3">
            <button className="w-full text-left flex items-center justify-between" onClick={() => setShowTools(!showTools)}>
              <span>可调用的后台工具（{tools?.tools?.length || 0}）</span>
              <span className="text-[#8b9a94] text-[11px]">{showTools ? '收起' : '展开'}</span>
            </button>
          </div>
          {showTools && (
            <div className="p-3 space-y-1.5 max-h-[320px] overflow-y-auto">
              {tools?.tools?.map((t: any) => (
                <div key={t.name} className="px-2.5 py-2 rounded-md bg-[#f7faf9] border border-[#eef2f0]">
                  <div className="text-[11.5px] font-mono text-brand-700">{t.name}</div>
                  <div className="text-[11px] text-[#8b9a94] leading-relaxed mt-0.5">{t.description}</div>
                </div>
              ))}
            </div>
          )}
        </div>

        <div className="card">
          <div className="card-title py-3">回答模板</div>
          <div className="p-4">
            <div className="space-y-1.5 text-[11.5px] text-[#55665f]">
              {['【结论】', '【关键数据依据】', '【分析】', '【建议】', '【风险与限制】', '【决策状态】'].map((t, i) => (
                <div key={t} className="flex items-center gap-2">
                  <span className="w-4 h-4 rounded bg-[#eef2f0] text-[#6b7d76] flex items-center justify-center text-[9.5px]">{i + 1}</span>
                  {t}
                </div>
              ))}
            </div>
          </div>
        </div>

        <Alert type="info">
          <div className="text-[11.5px] leading-relaxed">
            会员姓名、手机号、身份证号等个人身份信息不得发送给外部大模型。
            AI 只读取匿名化数据、聚合数据与算法结果。
          </div>
        </Alert>
      </div>
    </div>
  )
}

function AnswerBlock({ a, onItemClick }: { a: any; onItemClick: (n: string) => void }) {
  const [openExtra, setOpenExtra] = useState(false)
  const isGap = a.decision_status === '数据不足'

  return (
    <div className="max-w-[92%]">
      {/* 结论 */}
      <div className={`rounded-lg border p-4 ${isGap ? 'bg-[#fff8ec] border-[#f2dfb8]' : 'bg-white border-[#e3e8e6]'}`}>
        <div className="text-[11.5px] font-semibold text-brand-700 mb-1.5">【结论】</div>
        <div className={`text-[14px] leading-relaxed ${isGap ? 'text-[#8a6212]' : 'text-[#1a2b24] font-medium'}`}>
          {a.conclusion}
        </div>
      </div>

      {/* 关键数据依据 */}
      {a.key_basis?.length > 0 && (
        <div className="mt-2.5 rounded-lg border border-[#e3e8e6] bg-white p-4">
          <div className="text-[11.5px] font-semibold text-brand-700 mb-2">【关键数据依据】</div>
          <ol className="space-y-1.5">
            {a.key_basis.map((b: string, i: number) => (
              <li key={i} className="flex items-start gap-2 text-[12.5px] text-[#3d5049] leading-relaxed">
                <span className="w-4 h-4 rounded-full bg-[#eef2f0] text-[#6b7d76] flex items-center justify-center text-[9.5px] flex-shrink-0 mt-0.5">
                  {i + 1}
                </span>
                <span>{b}</span>
              </li>
            ))}
          </ol>
        </div>
      )}

      {/* 分析 */}
      {a.analysis && (
        <div className="mt-2.5 rounded-lg border border-[#e3e8e6] bg-white p-4">
          <div className="text-[11.5px] font-semibold text-brand-700 mb-1.5">【分析】</div>
          <div className="text-[12.5px] text-[#3d5049] leading-relaxed">{a.analysis}</div>
        </div>
      )}

      {/* 建议 */}
      {a.advice && (
        <div className="mt-2.5 rounded-lg border border-brand-200 bg-brand-50 p-4">
          <div className="text-[11.5px] font-semibold text-brand-700 mb-1.5">【建议】</div>
          <div className="text-[12.5px] text-brand-900/90 leading-relaxed whitespace-pre-line">{a.advice}</div>
        </div>
      )}

      {/* 风险与限制 */}
      <div className="mt-2.5 rounded-lg border border-[#f2dfb8] bg-[#fffaf0] p-4">
        <div className="text-[11.5px] font-semibold text-[#8a6212] mb-1.5">【风险与限制】</div>
        <div className="text-[12.5px] text-[#8a6212]/90 leading-relaxed">{a.risk_limit}</div>
      </div>

      {/* 决策状态 */}
      <div className="mt-2.5 flex items-center gap-2 flex-wrap">
        <span className="text-[11.5px] text-[#8b9a94]">【决策状态】</span>
        <span
          className={`tag ${
            a.decision_status === '数据不足'
              ? 'bg-[#fdf0f0] text-[#c13f3f] border border-[#f0cccc]'
              : a.decision_status.includes('审批')
                ? 'bg-[#fff8ec] text-[#a3700f] border border-[#f2dfb8]'
                : 'bg-brand-50 text-brand-700 border border-brand-200'
          }`}
        >
          {a.decision_status}
        </span>
        {a.tools_used?.length > 0 && (
          <span className="text-[11px] text-[#a8b5b0] font-mono">工具：{a.tools_used.join(', ')}</span>
        )}
      </div>

      {a.demo_note && (
        <div className="mt-2 text-[11.5px] text-[#a3700f]">数据说明：{a.demo_note}</div>
      )}
      <div className="mt-1.5 text-[11.5px] text-[#a8b5b0]">{a.disclaimer}</div>

      {/* 关联结果预览 */}
      {a.extra?.association?.realtime_rules?.length > 0 && (
        <div className="mt-2.5 rounded-lg border border-[#e3e8e6] bg-white p-4">
          <div className="text-[11.5px] font-semibold text-brand-700 mb-2">关联规则明细（实时重算）</div>
          <div className="space-y-1.5">
            {a.extra.association.realtime_rules.slice(0, 5).map((r: any, i: number) => (
              <button
                key={i}
                onClick={() => onItemClick(r.consequent)}
                className="w-full flex items-center gap-2.5 px-2.5 py-1.5 rounded-md bg-[#f7faf9] hover:bg-brand-50 transition-colors text-left"
              >
                <span className="text-[12.5px] font-medium text-[#2c3d36]">{r.display_rule}</span>
                <span className="text-[11px] text-[#8b9a94] ml-auto tabular-nums">
                  提升度 {r.lift} ｜ 置信度 {(r.confidence * 100).toFixed(1)}%
                </span>
              </button>
            ))}
          </div>
          <button className="btn-ghost text-[12px] mt-2" onClick={() => setOpenExtra(!openExtra)}>
            {openExtra ? '收起' : '查看全部规则 →'}
          </button>
        </div>
      )}

      {/* 综合方案 */}
      {a.extra?.plan && (
        <div className="mt-2.5 rounded-lg border border-[#e3e8e6] bg-white p-4">
          <div className="text-[11.5px] font-semibold text-brand-700 mb-2.5">AI综合选品方案</div>
          <div className="space-y-3">
            {['优先扩充', '建议保持', '重点观察', '建议精简', '建议退出'].map((g) => {
              const items = a.extra.plan[g] || []
              const colorMap: Record<string, string> = {
                优先扩充: 'border-brand-300 bg-brand-50',
                建议保持: 'border-[#d3e2f5] bg-[#eef4fb]',
                重点观察: 'border-[#dde4e1] bg-[#f7faf9]',
                建议精简: 'border-[#f2dfb8] bg-[#fffaf0]',
                建议退出: 'border-[#f0cccc] bg-[#fdf0f0]',
              }
              return (
                <div key={g} className={`rounded-lg border p-3 ${colorMap[g]}`}>
                  <div className="text-[12.5px] font-semibold text-[#33473f] mb-1.5">{g}（{items.length}）</div>
                  {items.length === 0 ? (
                    <div className="text-[11.5px] text-[#a8b5b0]">无</div>
                  ) : (
                    <div className="space-y-1.5">
                      {items.map((it: any, i: number) => (
                        <details key={i} className="text-[12px]">
                          <summary className="cursor-pointer text-[#2c3d36] font-medium hover:text-brand-700">
                            {it.category} — {it.action}
                          </summary>
                          <div className="mt-1.5 pl-3 border-l-2 border-[#dde4e1] space-y-1">
                            <div className="text-[11.5px] text-[#55665f] leading-relaxed">{it.data_basis}</div>
                            <div className="text-[11px] text-[#8b9a94] leading-relaxed">多维判断：{it.multi_dimension}</div>
                          </div>
                        </details>
                      ))}
                    </div>
                  )}
                </div>
              )
            })}
          </div>
        </div>
      )}

      {/* 表格数据（健康度） */}
      {a.extra?.items?.length > 0 && a.extra.items[0]?.overall_score !== undefined && (
        <div className="mt-2.5 rounded-lg border border-[#e3e8e6] bg-white overflow-hidden">
          <div className="px-4 py-2.5 border-b border-[#eef2f0] text-[11.5px] font-semibold text-brand-700">
            品类健康度明细
          </div>
          <table className="w-full">
            <thead>
              <tr>
                <th className="table-th">品类</th>
                <th className="table-th text-right">综合分</th>
                <th className="table-th">等级</th>
                <th className="table-th text-right">销量贡献</th>
                <th className="table-th text-right">毛利贡献</th>
                <th className="table-th text-right">周转</th>
                <th className="table-th text-right">坪效</th>
              </tr>
            </thead>
            <tbody>
              {a.extra.items.map((r: any) => (
                <tr key={r.category}>
                  <td className="table-td font-medium">{r.category}</td>
                  <td className="table-td text-right tabular-nums">{r.overall_score}</td>
                  <td className="table-td text-[12px]">{r.grade} {r.stars}</td>
                  <td className="table-td text-right tabular-nums">{r.sales_contribution}%</td>
                  <td className="table-td text-right tabular-nums">{r.margin_contribution}%</td>
                  <td className="table-td text-right tabular-nums">{r.avg_turnover_days}天</td>
                  <td className="table-td text-right tabular-nums">{r.avg_sales_per_sqm}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* 风险预警 */}
      {a.extra?.alerts?.length > 0 && (
        <div className="mt-2.5 rounded-lg border border-[#e3e8e6] bg-white p-4">
          <div className="text-[11.5px] font-semibold text-brand-700 mb-2">风险预警明细</div>
          <div className="space-y-1.5 max-h-[280px] overflow-y-auto">
            {a.extra.alerts.slice(0, 12).map((al: any, i: number) => (
              <div key={i} className="flex items-start gap-2 text-[12px]">
                <span
                  className="tag flex-shrink-0"
                  style={{
                    background: al.level === '高' ? '#fdf0f0' : '#fff8ec',
                    color: al.level === '高' ? '#c13f3f' : '#a3700f',
                  }}
                >
                  {al.type}
                </span>
                <span className="text-[#3d5049]">
                  <b>{al.target}</b>：{al.value}
                  <span className="text-[#8b9a94]"> — {al.detail}</span>
                </span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* 数据缺口 */}
      {a.extra?.data_status?.length > 0 && (
        <div className="mt-2.5 rounded-lg border border-[#e3e8e6] bg-white p-4">
          <div className="text-[11.5px] font-semibold text-brand-700 mb-2">数据接入状态</div>
          <div className="space-y-1.5">
            {a.extra.data_status.map((d: any, i: number) => (
              <div key={i} className="flex items-center justify-between gap-3 text-[12px]">
                <span className="text-[#2c3d36] font-medium">{d.name}</span>
                <span
                  className="tag"
                  style={{
                    background: d.state === '已接入' ? '#f0f9f4' : d.state === '未接入' ? '#fdf0f0' : '#fffaf0',
                    color: d.state === '已接入' ? '#257354' : d.state === '未接入' ? '#c13f3f' : '#a3700f',
                  }}
                >
                  {d.state}
                </span>
                <span className="text-[11.5px] text-[#8b9a94] ml-auto text-right flex-1">{d.detail}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* 自有品牌 */}
      {a.extra?.private_label?.items?.length > 0 && (
        <div className="mt-2.5 rounded-lg border border-[#e3e8e6] bg-white p-4">
          <div className="text-[11.5px] font-semibold text-brand-700 mb-2">自有品牌机会（品类级）</div>
          <div className="space-y-1.5">
            {a.extra.private_label.items.slice(0, 5).map((p: any, i: number) => (
              <div key={i} className="flex items-center justify-between gap-2 text-[12px]">
                <span className="text-[#2c3d36] font-medium">{p.category}</span>
                <span className="text-[11.5px] text-[#8b9a94]">
                  毛利贡献 {p.margin_contribution}% ｜ 健康度 {p.overall_score} 分
                </span>
                <span
                  className="tag"
                  style={{
                    background: p.potential === '重点关注' ? '#f0f9f4' : p.potential === '可评估' ? '#fffaf0' : '#f7faf9',
                    color: p.potential === '重点关注' ? '#257354' : p.potential === '可评估' ? '#a3700f' : '#6b7d76',
                  }}
                >
                  {p.potential}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* 比较结果 */}
      {a.extra?.comparison?.items && (
        <div className="mt-2.5 rounded-lg border border-[#e3e8e6] bg-white overflow-hidden">
          <div className="px-4 py-2.5 border-b border-[#eef2f0] text-[11.5px] font-semibold text-brand-700">
            比较结果明细
          </div>
          <table className="w-full">
            <thead>
              <tr>
                <th className="table-th">优先级</th>
                <th className="table-th">名称</th>
                <th className="table-th text-right">综合分</th>
                <th className="table-th text-right">销量分</th>
                <th className="table-th text-right">毛利分</th>
                <th className="table-th text-right">周转分</th>
                <th className="table-th text-right">坪效分</th>
                <th className="table-th">建议</th>
              </tr>
            </thead>
            <tbody>
              {a.extra.comparison.items.map((r: any) => (
                <tr key={r.name}>
                  <td className="table-td">
                    <span className="w-5 h-5 rounded bg-brand-600 text-white text-[10.5px] flex items-center justify-center">
                      {r.priority}
                    </span>
                  </td>
                  <td className="table-td font-medium">{r.name}</td>
                  <td className="table-td text-right font-semibold text-brand-700 tabular-nums">{r.overall_score}</td>
                  {['sales', 'margin', 'turnover', 'space'].map((k) => (
                    <td key={k} className="table-td text-right tabular-nums text-[#55665f]">{r.scores[k]}</td>
                  ))}
                  <td className="table-td text-[12px]">{r.recommendation.action}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* 预测详情 */}
      {a.extra?.forecast && (
        <div className="mt-2.5 rounded-lg border border-[#e3e8e6] bg-white p-4">
          <div className="text-[11.5px] font-semibold text-brand-700 mb-2">
            {a.extra.forecast.category} 预测明细
          </div>
          <div className="space-y-1">
            {a.extra.forecast.series.map((s: any, i: number) => (
              <div key={i} className="flex items-center justify-between text-[12px] px-2 py-1 rounded bg-[#f7faf9]">
                <span className="text-[#55665f] w-20">{s.period}</span>
                {s.type === 'history' ? (
                  <span className="text-brand-700 tabular-nums">历史 {s.actual?.toLocaleString()} 件</span>
                ) : (
                  <span className="text-[#c96a1f] tabular-nums">
                    预测 {s.forecast?.toLocaleString()} 件
                    <span className="text-[#a8b5b0] ml-1.5 text-[11px]">
                      [{s.lower?.toLocaleString()} ~ {s.upper?.toLocaleString()}]
                    </span>
                  </span>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* 门店画像 */}
      {a.extra?.store?.store && (
        <div className="mt-2.5 rounded-lg border border-[#e3e8e6] bg-white p-4">
          <div className="text-[11.5px] font-semibold text-brand-700 mb-2">门店画像接入状态</div>
          <div className="grid grid-cols-2 gap-2 text-[12px]">
            {Object.entries(a.extra.store.profile).map(([k, v]: any) => (
              <div key={k} className="flex items-center justify-between px-2.5 py-1.5 rounded bg-[#f7faf9]">
                <span className="text-[#55665f]">{k}</span>
                <span className={v == null || v === '待接入' ? 'text-[#a3700f]' : 'text-[#2c3d36] font-medium'}>
                  {v == null || v === '' ? '待接入' : v}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
