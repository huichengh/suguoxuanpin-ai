import { useEffect, useState } from 'react'
import { Alert, DemoBadge, Empty, ErrorBox, Loading, SectionTitle, StatusBadge, Tabs } from '../components/ui'
import { api } from '../services/api'

export default function Approvals() {
  const [data, setData] = useState<any>(null)
  const [recs, setRecs] = useState<any>(null)
  const [err, setErr] = useState('')
  const [status, setStatus] = useState('')
  const [tab, setTab] = useState('pending')
  const [msg, setMsg] = useState('')
  const [acting, setActing] = useState<number | null>(null)

  const load = () => {
    setErr('')
    Promise.all([api.approvals(status || undefined), api.recommendations()])
      .then(([d, r]) => { setData(d); setRecs(r) })
      .catch((e) => setErr(e.message))
  }
  useEffect(load, [status])

  const decide = async (id: number, action: string) => {
    const comments: Record<string, string> = {
      approve: '同意该建议，按流程执行。',
      reject: '不同意该建议，请补充数据后重新评估。',
      withdraw: '申请人主动撤回。',
    }
    setActing(id)
    setMsg('')
    try {
      const d = await api.decideApproval(id, action, comments[action])
      setMsg(`审批记录 ${d.code} 已更新为「${d.status}」`)
      load()
    } catch (e: any) {
      setErr(e.message)
    } finally {
      setActing(null)
    }
  }

  if (err && !data) return <ErrorBox message={err} onRetry={load} />
  if (!data) return <Loading />

  const filtered = data.items.filter((a: any) =>
    tab === 'pending' ? a.status === '待审批'
      : tab === 'done' ? a.status !== '待审批'
        : true
  )

  return (
    <div className="space-y-4 max-w-[1680px]">
      <div className="flex items-center justify-between gap-4 flex-wrap">
        <div>
          <h1 className="text-[19px] font-semibold text-[#1a2b24]">审批中心</h1>
          <p className="text-[12.5px] text-[#6b7d76] mt-0.5">
            人机协同：AI 只形成待审批建议，不自动执行任何不可逆操作
          </p>
        </div>
        <DemoBadge />
      </div>

      {msg && <Alert type="success">{msg}</Alert>}
      {err && <Alert type="error">{err}</Alert>}

      {/* 分级说明 */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
        {data.levels.map((l: any) => (
          <div
            key={l.level}
            className={`card p-4 ${
              l.level === 'Level 3' ? 'border-[#f0cccc] bg-[#fdf8f8]' : l.level === 'Level 2' ? 'border-[#f2dfb8] bg-[#fffdf8]' : ''
            }`}
          >
            <div className="flex items-center justify-between mb-1.5">
              <span className="text-[13px] font-semibold text-[#1a2b24]">{l.level} · {l.name}</span>
              <span
                className="tag"
                style={{
                  background: l.need_approval ? '#fdf0f0' : '#f0f9f4',
                  color: l.need_approval ? '#c13f3f' : '#257354',
                }}
              >
                {l.need_approval ? '需人工审批' : '无需审批'}
              </span>
            </div>
            <div className="text-[11.5px] text-[#6b7d76] leading-relaxed">{l.desc}</div>
          </div>
        ))}
      </div>

      {/* 统计 */}
      <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
        {[
          ['全部记录', data.count, 'default'],
          ['待审批', data.stats.待审批, 'warn'],
          ['已通过', data.stats.已通过, 'good'],
          ['已驳回', data.stats.已驳回, 'bad'],
          ['已撤回', data.stats.已撤回, 'default'],
        ].map(([label, v, tone]: any) => (
          <div key={label} className="card p-3.5">
            <div className="text-[12px] text-[#6b7d76]">{label}</div>
            <div
              className="text-[22px] font-semibold tabular-nums mt-1"
              style={{
                color: tone === 'warn' ? '#a3700f' : tone === 'good' ? '#257354' : tone === 'bad' ? '#c13f3f' : '#1a2b24',
              }}
            >
              {v}
            </div>
          </div>
        ))}
      </div>

      <Tabs
        active={tab}
        onChange={setTab}
        items={[
          { key: 'pending', label: '待审批', badge: data.stats.待审批 },
          { key: 'done', label: '已处理', badge: data.count - data.stats.待审批 },
          { key: 'all', label: '全部记录', badge: data.count },
          { key: 'recs', label: 'AI建议记录', badge: recs?.count || 0 },
        ]}
      />

      {tab !== 'recs' && (
        <>
          <div className="flex items-center gap-2">
            <select className="input w-auto" value={status} onChange={(e) => setStatus(e.target.value)}>
              <option value="">全部状态</option>
              <option value="待审批">待审批</option>
              <option value="已通过">已通过</option>
              <option value="已驳回">已驳回</option>
              <option value="已撤回">已撤回</option>
            </select>
          </div>

          {filtered.length === 0 ? (
            <Empty
              title="暂无审批记录"
              hint="可在「选品比较中心」提交一条 Level 3 建议，或在「AI选品助手」中提问后提交建议进入审批流程。"
            />
          ) : (
            <div className="space-y-3">
              {filtered.map((a: any) => (
                <div key={a.id} className="card">
                  <div className="p-4">
                    <div className="flex items-start justify-between gap-3 mb-2.5 flex-wrap">
                      <div className="flex items-center gap-2 flex-wrap">
                        <span className="font-mono text-[12px] text-[#8b9a94]">{a.code}</span>
                        <span className="tag bg-[#eef2f0] text-[#55665f] border border-[#dde4e1]">
                          来源：{a.source_module}
                        </span>
                        <span
                          className="tag"
                          style={{
                            background: a.risk_level === 'Level 3' ? '#fdf0f0' : a.risk_level === 'Level 2' ? '#fffaf0' : '#f0f9f4',
                            color: a.risk_level === 'Level 3' ? '#c13f3f' : a.risk_level === 'Level 2' ? '#a3700f' : '#257354',
                          }}
                        >
                          {a.risk_level}
                          {a.risk_level === 'Level 3' ? ' 必须人工审批' : ''}
                        </span>
                      </div>
                      <StatusBadge status={a.status} />
                    </div>

                    <div className="text-[13.5px] text-[#1a2b24] leading-relaxed whitespace-pre-line mb-2.5">
                      {a.ai_suggestion}
                    </div>

                    {a.data_basis && (
                      <div className="bg-[#f7faf9] rounded-md px-3 py-2 text-[12px] text-[#55665f] leading-relaxed mb-2.5">
                        <span className="font-medium text-[#33473f]">数据依据：</span>{a.data_basis}
                      </div>
                    )}

                    <div className="flex items-center gap-4 text-[11.5px] text-[#8b9a94] flex-wrap">
                      <span>申请人：{a.applicant}</span>
                      <span>提交时间：{a.submitted_at?.replace('T', ' ').slice(0, 16)}</span>
                      {a.approver && <span>审批人：{a.approver}</span>}
                      {a.decided_at && <span>处理时间：{a.decided_at.replace('T', ' ').slice(0, 16)}</span>}
                    </div>

                    {a.approval_comment && (
                      <div className="mt-2 text-[12px] text-[#55665f]">
                        <span className="font-medium">审批意见：</span>{a.approval_comment}
                      </div>
                    )}

                    {a.status === '待审批' && (
                      <div className="flex items-center gap-2 mt-3 pt-3 border-t border-[#eef2f0]">
                        <button className="btn-primary" disabled={acting === a.id} onClick={() => decide(a.id, 'approve')}>
                          通过
                        </button>
                        <button className="btn-secondary" disabled={acting === a.id} onClick={() => decide(a.id, 'reject')}>
                          驳回
                        </button>
                        <button className="btn-ghost" disabled={acting === a.id} onClick={() => decide(a.id, 'withdraw')}>
                          撤回
                        </button>
                        <span className="text-[11.5px] text-[#8b9a94] ml-auto">
                          Level 3 建议必须由人工决策，AI 不会自动执行
                        </span>
                      </div>
                    )}
                  </div>
                </div>
              ))}
            </div>
          )}
        </>
      )}

      {tab === 'recs' && (
        <div className="card overflow-hidden">
          <div className="card-title">AI 建议记录（最近 {recs?.count || 0} 条）</div>
          {!recs?.count ? (
            <div className="p-8 text-center text-[13px] text-[#8b9a94]">暂无 AI 建议记录</div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full min-w-[1080px]">
                <thead>
                  <tr>
                    <th className="table-th">编号</th>
                    <th className="table-th">来源模块</th>
                    <th className="table-th">建议标题</th>
                    <th className="table-th">影响品类</th>
                    <th className="table-th">风险等级</th>
                    <th className="table-th">优先级</th>
                    <th className="table-th">状态</th>
                    <th className="table-th">生成时间</th>
                  </tr>
                </thead>
                <tbody>
                  {recs.items.map((r: any) => (
                    <tr key={r.id}>
                      <td className="table-td font-mono text-[11.5px] text-[#8b9a94]">{r.code}</td>
                      <td className="table-td text-[12px]">{r.source_module}</td>
                      <td className="table-td max-w-[300px]">
                        <div className="font-medium text-[13px]">{r.title}</div>
                        <div className="text-[11px] text-[#8b9a94] mt-0.5 leading-relaxed">{r.content?.slice(0, 80)}</div>
                      </td>
                      <td className="table-td text-[12px]">{r.affected_categories || '—'}</td>
                      <td className="table-td">
                        <span
                          className="tag"
                          style={{
                            background: r.risk_level === 'Level 3' ? '#fdf0f0' : '#fffaf0',
                            color: r.risk_level === 'Level 3' ? '#c13f3f' : '#a3700f',
                          }}
                        >
                          {r.risk_level}
                        </span>
                      </td>
                      <td className="table-td text-[12px]">{r.priority}</td>
                      <td className="table-td text-[12px]">{r.decision_status}</td>
                      <td className="table-td text-[11.5px] text-[#8b9a94]">
                        {r.created_at?.replace('T', ' ').slice(0, 16)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
