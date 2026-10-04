import { useEffect, useState } from 'react'
import { Alert, DemoBadge, ErrorBox, Loading, SectionTitle, Tabs } from '../components/ui'
import { api } from '../services/api'

const PARAM_META: Record<string, { label: string; type: 'number' | 'weights'; min?: number; max?: number; step?: number; desc: string }> = {
  category_health_weights: { label: '品类健康度权重', type: 'weights', desc: '销量/毛利/周转/坪效，合计必须为 1' },
  compare_weights: { label: '选品比较权重', type: 'weights', desc: '销量/毛利/周转/坪效，合计必须为 1' },
  apriori_min_support: { label: 'Apriori 最小支持度', type: 'number', min: 0.001, max: 1, step: 0.005, desc: '频繁项集的支持度下限' },
  apriori_min_confidence: { label: 'Apriori 最小置信度', type: 'number', min: 0.05, max: 1, step: 0.05, desc: '规则可信度下限' },
  apriori_min_lift: { label: 'Apriori 最小提升度', type: 'number', min: 1, max: 30, step: 0.1, desc: '提升度下限，1 表示无关联' },
  apriori_top_n: { label: 'TopN 规则数', type: 'number', min: 1, max: 200, step: 1, desc: '显示的规则数量' },
  forecast_horizon: { label: '预测期数', type: 'number', min: 1, max: 12, step: 1, desc: '未来预测的期数' },
  risk_turnover_threshold: { label: '周转天数风险阈值', type: 'number', min: 5, max: 200, step: 1, desc: '超过则触发高库存预警' },
  risk_space_threshold: { label: '坪效风险阈值', type: 'number', min: 100, max: 3000, step: 10, desc: '低于则触发低坪效预警' },
  risk_stockout_threshold: { label: '缺货次数风险阈值', type: 'number', min: 1, max: 100, step: 1, desc: '达到则触发缺货预警' },
  risk_score_threshold: { label: '健康度预警分数线', type: 'number', min: 0, max: 100, step: 1, desc: '低于则标记需重点优化' },
}

export default function Admin() {
  const [tab, setTab] = useState('params')
  const [settings, setSettings] = useState<any>(null)
  const [users, setUsers] = useState<any>(null)
  const [roles, setRoles] = useState<any>(null)
  const [logs, setLogs] = useState<any>(null)
  const [modelLogs, setModelLogs] = useState<any>(null)
  const [history, setHistory] = useState<any>(null)
  const [knowledge, setKnowledge] = useState<any>(null)
  const [err, setErr] = useState('')
  const [msg, setMsg] = useState('')
  const [editing, setEditing] = useState<any>(null)
  const [draft, setDraft] = useState<any>({});
  const [reason, setReason] = useState('')
  const [report, setReport] = useState('')

  const isAdmin = (() => {
    const u = localStorage.getItem('suguo_user')
    return u ? JSON.parse(u).role_code === 'admin' : false
  })()

  const load = () => {
    setErr('')
    Promise.all([
      api.modelSettings().catch(() => null),
      api.users().catch(() => null),
      api.roles().catch(() => null),
      api.auditLogs().catch(() => null),
      api.modelLogs().catch(() => null),
      api.analysisHistory().catch(() => null),
      api.knowledge().catch(() => null),
    ]).then(([s, u, r, l, m, h, k]) => {
      setSettings(s); setUsers(u); setRoles(r); setLogs(l); setModelLogs(m); setHistory(h); setKnowledge(k)
    })
  }
  useEffect(load, [])

  const startEdit = (s: any) => {
    setEditing(s)
    setDraft(typeof s.value === 'object' ? { ...s.value } : { v: s.value })
    setReason('')
    setMsg('')
  }

  const save = async () => {
    let value: any
    if (PARAM_META[editing.key]?.type === 'weights') value = draft
    else if (PARAM_META[editing.key]?.type === 'number') value = Number(draft.v)
    else value = draft.v

    try {
      const d = await api.updateModelSetting(editing.key, value, reason)
      setMsg(d.message)
      setEditing(null)
      load()
    } catch (e: any) {
      setErr(e.message)
    }
  }

  const genReport = async () => {
    try {
      const txt = await api.report()
      setReport(txt)
    } catch (e: any) {
      setErr(e.message)
    }
  }

  const downloadReport = () => {
    const blob = new Blob([report], { type: 'text/plain;charset=utf-8' })
    const a = document.createElement('a')
    a.href = URL.createObjectURL(blob)
    a.download = '门店AI选品诊断报告.txt'
    a.click()
  }

  const downloadCsv = async (type: string) => {
    try {
      const res = await fetch(`/api/data/datasets/${type}/download`, {
        headers: { Authorization: `Bearer ${localStorage.getItem('suguo_token')}` },
      })
      const blob = await res.blob()
      const a = document.createElement('a')
      a.href = URL.createObjectURL(blob)
      a.download = `export_${type}.csv`
      a.click()
    } catch (e: any) {
      setErr(e.message)
    }
  }

  return (
    <div className="space-y-4 max-w-[1680px]">
      <div className="flex items-center justify-between gap-4 flex-wrap">
        <div>
          <h1 className="text-[19px] font-semibold text-[#1a2b24]">系统管理</h1>
          <p className="text-[12.5px] text-[#6b7d76] mt-0.5">
            算法参数、评分权重、用户角色、知识库、日志与报告导出
          </p>
        </div>
        <DemoBadge />
      </div>

      {!isAdmin && (
        <Alert type="warn">
          当前角色为只读或业务角色，算法参数与用户管理仅管理员可修改。您仍可查看参数、角色说明与日志。
        </Alert>
      )}
      {msg && <Alert type="success">{msg}</Alert>}
      {err && <Alert type="error">{err}</Alert>}

      <Tabs
        active={tab}
        onChange={setTab}
        items={[
          { key: 'params', label: '算法参数' },
          { key: 'users', label: '用户与角色' },
          { key: 'knowledge', label: 'AI知识库', badge: knowledge?.items?.length || 0 },
          { key: 'logs', label: '操作日志', badge: logs?.items?.length || 0 },
          { key: 'model', label: '模型运行日志', badge: modelLogs?.items?.length || 0 },
          { key: 'history', label: 'AI分析记录' },
          { key: 'report', label: '报告导出' },
        ]}
      />

      {tab === 'params' && (
        <div className="space-y-3">
          <Alert type="info">{settings?.note}</Alert>
          {!settings ? <Loading /> : (
            <div className="card overflow-hidden">
              <div className="card-title">算法参数与评分权重</div>
              <div className="overflow-x-auto">
                <table className="w-full min-w-[1020px]">
                  <thead>
                    <tr>
                      <th className="table-th">参数</th>
                      <th className="table-th">当前值</th>
                      <th className="table-th">说明</th>
                      <th className="table-th">最近修改</th>
                      <th className="table-th">修改原因</th>
                      <th className="table-th"></th>
                    </tr>
                  </thead>
                  <tbody>
                    {settings.items.map((s: any) => {
                      const meta = PARAM_META[s.key]
                      return (
                        <tr key={s.key}>
                          <td className="table-td">
                            <div className="font-medium text-[13px]">{meta?.label || s.key}</div>
                            <div className="font-mono text-[11px] text-[#a8b5b0]">{s.key}</div>
                          </td>
                          <td className="table-td">
                            {typeof s.value === 'object' ? (
                              <div className="flex flex-wrap gap-1.5">
                                {Object.entries(s.value).map(([k, v]: any) => (
                                  <span key={k} className="tag bg-white text-[#55665f] border border-[#dde4e1]">
                                    {k} <b className="text-brand-700 ml-0.5">{v}</b>
                                  </span>
                                ))}
                              </div>
                            ) : (
                              <span className="text-[14px] font-semibold text-brand-700 tabular-nums">{s.value}</span>
                            )}
                          </td>
                          <td className="table-td text-[12px] text-[#55665f] max-w-[280px]">
                            {meta?.desc || s.description}
                          </td>
                          <td className="table-td text-[11.5px] text-[#8b9a94]">
                            {s.updated_by ? (
                              <>
                                <div>{s.updated_by}</div>
                                <div>{s.updated_at?.replace('T', ' ').slice(0, 16)}</div>
                              </>
                            ) : '未修改'}
                          </td>
                          <td className="table-td text-[11.5px] text-[#8b9a94] max-w-[200px]">
                            {s.change_reason || '—'}
                          </td>
                          <td className="table-td">
                            {isAdmin ? (
                              <button className="btn-secondary" onClick={() => startEdit(s)}>修改</button>
                            ) : (
                              <span className="text-[11.5px] text-[#a8b5b0]">只读</span>
                            )}
                          </td>
                        </tr>
                      )
                    })}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </div>
      )}

      {tab === 'users' && (
        <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
          <div className="card overflow-hidden">
            <div className="card-title">用户列表（{users?.items?.length || 0}）</div>
            <div className="overflow-x-auto">
              <table className="w-full">
                <thead>
                  <tr>
                    <th className="table-th">用户名</th>
                    <th className="table-th">姓名</th>
                    <th className="table-th">角色</th>
                    <th className="table-th">门店</th>
                    <th className="table-th">最近登录</th>
                  </tr>
                </thead>
                <tbody>
                  {users?.items?.map((u: any) => (
                    <tr key={u.id}>
                      <td className="table-td font-mono text-[12px]">{u.username}</td>
                      <td className="table-td">{u.full_name}</td>
                      <td className="table-td">
                        <span className="tag bg-brand-50 text-brand-700 border border-brand-200">{u.role}</span>
                      </td>
                      <td className="table-td text-[12px]">{u.store || '—'}</td>
                      <td className="table-td text-[11.5px] text-[#8b9a94]">
                        {u.last_login_at?.replace('T', ' ').slice(0, 16) || '未登录'}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          <div className="card">
            <div className="card-title">角色与权限</div>
            <div className="p-4 space-y-2.5">
              {roles?.items?.map((r: any) => (
                <div key={r.id} className="rounded-lg border border-[#e9eeec] p-3.5">
                  <div className="flex items-center justify-between mb-1">
                    <span className="text-[13px] font-medium text-[#2c3d36]">{r.name}</span>
                    <span className="text-[11.5px] text-[#8b9a94]">{r.user_count} 个用户</span>
                  </div>
                  <div className="text-[11.5px] text-[#8b9a94] leading-relaxed mb-2">{r.description}</div>
                  <div className="flex flex-wrap gap-1.5">
                    {r.permissions.includes('*') ? (
                      <span className="tag bg-brand-600 text-white border border-brand-600">全部权限</span>
                    ) : (
                      r.permissions.map((p: string) => (
                        <span key={p} className="tag bg-[#eef2f0] text-[#55665f] border border-[#dde4e1] font-mono text-[10.5px]">
                          {p}
                        </span>
                      ))
                    )}
                  </div>
                </div>
              ))}
              <Alert type="info">
                权限采用最小化原则：采购经理不能修改算法参数，品类经理不能提交采购审批，
                普通查看人员只读。密码使用 bcrypt 哈希存储，绝不明文。
              </Alert>
            </div>
          </div>
        </div>
      )}

      {tab === 'knowledge' && (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
          {knowledge?.items?.map((k: any) => (
            <div key={k.id} className="card">
              <div className="card-title py-3">
                <div>
                  <div className="text-[13.5px] font-semibold">{k.title}</div>
                  <div className="text-[11px] text-[#8b9a94] font-normal mt-0.5">
                    {k.category}
                    {k.tags && ` ｜ ${k.tags}`}
                  </div>
                </div>
              </div>
              <div className="p-4">
                <div className="text-[12.5px] text-[#3d5049] leading-relaxed">{k.content}</div>
              </div>
            </div>
          ))}
        </div>
      )}

      {tab === 'logs' && (
        <div className="card overflow-hidden">
          <div className="card-title">操作日志（最近 {logs?.items?.length || 0} 条）</div>
          <div className="overflow-x-auto max-h-[620px]">
            <table className="w-full min-w-[880px]">
              <thead className="sticky top-0">
                <tr>
                  <th className="table-th">时间</th>
                  <th className="table-th">用户</th>
                  <th className="table-th">操作</th>
                  <th className="table-th">对象</th>
                  <th className="table-th">详情</th>
                </tr>
              </thead>
              <tbody>
                {logs?.items?.map((l: any) => (
                  <tr key={l.id}>
                    <td className="table-td text-[11.5px] text-[#8b9a94] whitespace-nowrap">
                      {l.created_at?.replace('T', ' ').slice(0, 19)}
                    </td>
                    <td className="table-td text-[12px]">{l.user}</td>
                    <td className="table-td">
                      <span className="font-mono text-[11.5px] text-brand-700">{l.action}</span>
                    </td>
                    <td className="table-td text-[12px]">{l.target}</td>
                    <td className="table-td text-[11.5px] text-[#8b9a94] max-w-[380px] leading-relaxed">{l.detail}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {tab === 'model' && (
        <div className="card overflow-hidden">
          <div className="card-title">模型运行日志（{modelLogs?.items?.length || 0}）</div>
          <div className="overflow-x-auto">
            <table className="w-full min-w-[880px]">
              <thead>
                <tr>
                  <th className="table-th">时间</th>
                  <th className="table-th">算法</th>
                  <th className="table-th">数据集</th>
                  <th className="table-th">参数</th>
                  <th className="table-th">输出</th>
                  <th className="table-th text-right">耗时</th>
                  <th className="table-th">状态</th>
                </tr>
              </thead>
              <tbody>
                {modelLogs?.items?.map((m: any) => (
                  <tr key={m.id}>
                    <td className="table-td text-[11.5px] text-[#8b9a94] whitespace-nowrap">
                      {m.created_at?.replace('T', ' ').slice(0, 19)}
                    </td>
                    <td className="table-td text-[12.5px] font-medium">{m.algorithm}</td>
                    <td className="table-td text-[12px]">{m.dataset}</td>
                    <td className="table-td font-mono text-[11px] text-[#8b9a94] max-w-[280px] truncate">
                      {JSON.stringify(m.parameters)}
                    </td>
                    <td className="table-td text-[12px]">{m.output}</td>
                    <td className="table-td text-right tabular-nums text-[12px]">{m.duration_ms}ms</td>
                    <td className="table-td">
                      <span className="tag bg-brand-50 text-brand-700 border border-brand-200">{m.status}</span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {tab === 'history' && (
        <div className="space-y-4">
          <Alert type="info">{history?.note}</Alert>
          <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
            <div className="card overflow-hidden">
              <div className="card-title">分析任务（{history?.jobs?.length || 0}）</div>
              <div className="overflow-x-auto">
                <table className="w-full">
                  <thead>
                    <tr>
                      <th className="table-th">时间</th>
                      <th className="table-th">任务类型</th>
                      <th className="table-th">算法</th>
                      <th className="table-th">结果摘要</th>
                      <th className="table-th text-right">耗时</th>
                    </tr>
                  </thead>
                  <tbody>
                    {history?.jobs?.length === 0 ? (
                      <tr><td colSpan={5} className="table-td text-center text-[#8b9a94] py-6">暂无分析任务记录</td></tr>
                    ) : history?.jobs?.map((j: any) => (
                      <tr key={j.id}>
                        <td className="table-td text-[11.5px] text-[#8b9a94] whitespace-nowrap">
                          {j.created_at?.replace('T', ' ').slice(0, 19)}
                        </td>
                        <td className="table-td text-[12px]">{j.job_type}</td>
                        <td className="table-td text-[12px]">{j.algorithm}</td>
                        <td className="table-td font-mono text-[11px] text-[#8b9a94]">
                          {JSON.stringify(j.result_summary)}
                        </td>
                        <td className="table-td text-right tabular-nums text-[12px]">{j.duration_ms}ms</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
            <div className="card overflow-hidden">
              <div className="card-title">模型运行记录（{history?.runs?.length || 0}）</div>
              <div className="overflow-x-auto">
                <table className="w-full">
                  <thead>
                    <tr>
                      <th className="table-th">时间</th>
                      <th className="table-th">算法</th>
                      <th className="table-th">数据集</th>
                      <th className="table-th">输出</th>
                    </tr>
                  </thead>
                  <tbody>
                    {history?.runs?.map((r: any) => (
                      <tr key={r.id}>
                        <td className="table-td text-[11.5px] text-[#8b9a94] whitespace-nowrap">
                          {r.created_at?.replace('T', ' ').slice(0, 19)}
                        </td>
                        <td className="table-td text-[12px]">{r.algorithm}</td>
                        <td className="table-td text-[12px]">{r.dataset}</td>
                        <td className="table-td text-[12px]">{r.output}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        </div>
      )}

      {tab === 'report' && (
        <div className="space-y-3">
          <div className="card">
            <div className="card-title">
              《门店AI选品诊断报告》
              <div className="flex items-center gap-2">
                {report && (
                  <>
                    <button className="btn-secondary" onClick={() => { void downloadCsv('category_health') }}>
                      导出健康度 CSV
                    </button>
                    <button className="btn-secondary" onClick={() => { void downloadCsv('association_rules') }}>
                      导出关联规则 CSV
                    </button>
                    <button className="btn-secondary" onClick={() => { void downloadCsv('category_sales') }}>
                      导出销售数据 CSV
                    </button>
                    <button className="btn-primary" onClick={downloadReport}>下载报告</button>
                  </>
                )}
                {!report && (
                  <button className="btn-primary" onClick={genReport}>生成报告</button>
                )}
              </div>
            </div>
            <div className="p-4">
              {!report ? (
                <div className="text-[13px] text-[#8b9a94] text-center py-10">
                  点击「生成报告」，系统会汇总门店概况、核心指标、品类健康度、选品比较结果、
                  关联陈列机会、需求预测、风险预警、AI优化建议、待审批事项、数据来源与模型参数、免责声明，
                  生成完整报告文本。
                </div>
              ) : (
                <>
                  <Alert type="info">
                    报告为纯文本格式，可直接下载后用 Word 另存为 PDF。
                    如需 PDF，可在 Word 中「文件 → 另存为 → PDF」；或浏览器打印时选择「另存为 PDF」。
                  </Alert>
                  <pre className="mt-3 bg-[#fbfcfc] border border-[#e3e8e6] rounded-lg p-4 text-[12px] leading-relaxed whitespace-pre-wrap font-mono max-h-[600px] overflow-auto">
                    {report}
                  </pre>
                </>
              )}
            </div>
          </div>
        </div>
      )}

      {/* 参数编辑弹窗 */}
      {editing && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-6 bg-black/35" onClick={() => setEditing(null)}>
          <div className="card w-full max-w-lg shadow-2xl" onClick={(e) => e.stopPropagation()}>
            <div className="card-title">
              修改参数：{PARAM_META[editing.key]?.label || editing.key}
              <button onClick={() => setEditing(null)} className="text-[#8b9a94] text-lg">×</button>
            </div>
            <div className="p-5 space-y-4">
              <div>
                <div className="text-[12px] text-[#8b9a94] mb-2">修改前</div>
                <div className="rounded-md bg-[#f7faf9] border border-[#eef2f0] px-3 py-2 font-mono text-[12px]">
                  {typeof editing.value === 'object' ? JSON.stringify(editing.value) : editing.value}
                </div>
              </div>

              <div>
                <label className="label">修改为</label>
                {PARAM_META[editing.key]?.type === 'weights' ? (
                  <div className="space-y-2.5">
                    {Object.keys(draft).map((k) => (
                      <div key={k} className="flex items-center gap-3">
                        <span className="text-[12.5px] text-[#55665f] w-20">{k}</span>
                        <input
                          type="number" step="0.05" min="0" max="1"
                          className="input flex-1"
                          value={draft[k]}
                          onChange={(e) => setDraft({ ...draft, [k]: Number(e.target.value) })}
                        />
                        <span className="text-[12px] text-[#8b9a94] w-10 tabular-nums">
                          {(Number(draft[k]) * 100).toFixed(0)}%
                        </span>
                      </div>
                    ))}
                    <div className="text-[12px]">
                      合计：
                      <span
                        className={
                          Math.abs(Object.values(draft).reduce((a: number, b: any) => a + Number(b), 0) - 1) > 0.001
                            ? 'text-[#c13f3f]'
                            : 'text-brand-700'
                        }
                      >
                        {Object.values(draft).reduce((a: number, b: any) => a + Number(b), 0).toFixed(2)}
                      </span>
                      （必须为 1）
                    </div>
                  </div>
                ) : (
                  <input
                    type="number"
                    className="input"
                    min={PARAM_META[editing.key]?.min}
                    max={PARAM_META[editing.key]?.max}
                    step={PARAM_META[editing.key]?.step || 1}
                    value={draft.v}
                    onChange={(e) => setDraft({ v: Number(e.target.value) })}
                  />
                )}
              </div>

              <div>
                <label className="label">修改原因（必填，用于审计追溯）</label>
                <input
                  className="input"
                  value={reason}
                  onChange={(e) => setReason(e.target.value)}
                  placeholder="如：业务方反馈需提高毛利权重"
                />
              </div>

              <Alert type="info">
                参数修改会记录修改前后值、修改人员、修改时间与修改原因。
                修改后建议到对应模块点击「重新计算」使新参数生效。
              </Alert>
            </div>
            <div className="px-5 py-3.5 border-t border-[#eef2f0] flex justify-end gap-2">
              <button className="btn-secondary" onClick={() => setEditing(null)}>取消</button>
              <button className="btn-primary" onClick={save} disabled={!reason.trim()}>
                保存修改
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
