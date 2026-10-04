import { useEffect, useRef, useState } from 'react'
import { Alert, DemoBadge, ErrorBox, Loading, SectionTitle, Tabs } from '../components/ui'
import { api, fmt } from '../services/api'

export default function DataCenter() {
  const [data, setData] = useState<any>(null)
  const [quality, setQuality] = useState<any>(null)
  const [err, setErr] = useState('')
  const [msg, setMsg] = useState('')
  const [uploading, setUploading] = useState(false)
  const [uploadType, setUploadType] = useState('category_sales')
  const [lastResult, setLastResult] = useState<any>(null)
  const [tab, setTab] = useState('datasets')
  const fileRef = useRef<HTMLInputElement>(null)

  const isAdmin = (() => {
    const u = localStorage.getItem('suguo_user')
    return u ? JSON.parse(u).role_code === 'admin' : false
  })()

  const load = () => {
    setErr('')
    Promise.all([api.datasets(), api.dataQuality()])
      .then(([d, q]) => { setData(d); setQuality(q) })
      .catch((e) => setErr(e.message))
  }
  useEffect(load, [])

  const onFile = async (f: File) => {
    setUploading(true)
    setMsg('')
    setLastResult(null)
    try {
      const d = await api.upload(f, uploadType)
      setLastResult(d)
      setMsg(d.message)
      load()
    } catch (e: any) {
      setErr(e.message)
    } finally {
      setUploading(false)
      if (fileRef.current) fileRef.current.value = ''
    }
  }

  const doImport = async (strategy: string) => {
    if (!lastResult) return
    try {
      const d = await api.importDataset({
        upload_id: lastResult.upload_id,
        dataset_type: uploadType,
        strategy,
      })
      setMsg(d.message)
      setLastResult(null)
      load()
    } catch (e: any) {
      setErr(e.message)
    }
  }

  if (err && !data) return <ErrorBox message={err} onRetry={load} />
  if (!data) return <Loading />

  const gradeColor = (s: number) =>
    s >= 90 ? '#257354' : s >= 75 ? '#57ad84' : s >= 60 ? '#d9a520' : '#d94a4a'

  return (
    <div className="space-y-4 max-w-[1680px]">
      <div className="flex items-center justify-between gap-4 flex-wrap">
        <div>
          <h1 className="text-[19px] font-semibold text-[#1a2b24]">数据中心</h1>
          <p className="text-[12.5px] text-[#6b7d76] mt-0.5">
            数据上传、质量检查与版本管理 ｜ 发现问题不静默修复，由用户选择处理方式
          </p>
        </div>
        <DemoBadge text="平台数据为基于公开行业数据构造的模拟演示数据" />
      </div>

      {msg && <Alert type="success">{msg}</Alert>}
      {err && <Alert type="error">{err}</Alert>}

      <Tabs
        active={tab}
        onChange={setTab}
        items={[
          { key: 'datasets', label: '数据集管理', badge: data.items.length },
          { key: 'quality', label: '数据质量报告', badge: quality?.items?.length || 0 },
          { key: 'upload', label: '上传数据' },
        ]}
      />

      {tab === 'datasets' && (
        <div className="card overflow-hidden">
          <div className="card-title">已导入的数据集</div>
          <div className="overflow-x-auto">
            <table className="w-full min-w-[1080px]">
              <thead>
                <tr>
                  <th className="table-th">数据集</th>
                  <th className="table-th">类型</th>
                  <th className="table-th">版本</th>
                  <th className="table-th text-right">原始行数</th>
                  <th className="table-th text-right">库内行数</th>
                  <th className="table-th text-right">质量分</th>
                  <th className="table-th">上传人</th>
                  <th className="table-th">上传时间</th>
                  <th className="table-th">数据来源</th>
                  <th className="table-th"></th>
                </tr>
              </thead>
              <tbody>
                {data.items.map((d: any) => (
                  <tr key={d.id}>
                    <td className="table-td font-medium">
                      {d.label}
                      {d.is_demo && (
                        <span className="tag bg-[#fff4e8] text-[#a35d16] border border-[#f5d9b8] ml-1.5">演示数据</span>
                      )}
                    </td>
                    <td className="table-td font-mono text-[11.5px] text-[#8b9a94]">{d.dataset_type}</td>
                    <td className="table-td font-mono text-[11.5px]">{d.version}</td>
                    <td className="table-td text-right tabular-nums">{fmt.n(d.row_count)}</td>
                    <td className="table-td text-right tabular-nums">{fmt.n(d.db_rows)}</td>
                    <td className="table-td text-right">
                      {d.quality ? (
                        <span className="font-semibold tabular-nums" style={{ color: gradeColor(d.quality.overall_score) }}>
                          {d.quality.overall_score}
                        </span>
                      ) : '—'}
                    </td>
                    <td className="table-td text-[12px]">{d.uploaded_by}</td>
                    <td className="table-td text-[11.5px] text-[#8b9a94]">
                      {d.uploaded_at?.replace('T', ' ').slice(0, 16)}
                    </td>
                    <td className="table-td text-[11.5px] text-[#6b7d76] max-w-[220px]">{d.source_note}</td>
                    <td className="table-td">
                      <a
                        href={api.templateUrl(d.dataset_type)}
                        className="text-[12px] text-brand-600 hover:underline whitespace-nowrap"
                      >
                        下载模板
                      </a>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {tab === 'quality' && (
        <div className="space-y-3">
          <Alert type="info">
            质量检查覆盖完整性、一致性、有效性、唯一性、时效性五个维度。
            平台发现问题后<b>不静默修复</b>，只展示问题字段、问题数量与处理建议，
            由用户选择「自动清洗 / 人工确认 / 保留原始值」。
          </Alert>

          {quality?.items?.map((q: any) => (
            <div key={q.dataset_type} className="card">
              <div className="card-title">
                <div className="flex items-center gap-2.5">
                  <span>{q.label}</span>
                  <span className="font-mono text-[11.5px] text-[#8b9a94]">{q.version}</span>
                </div>
                <div className="flex items-center gap-3">
                  <span className="text-[12px] text-[#6b7d76] font-normal">
                    {fmt.n(q.total_rows)} 行 ｜ 检查于 {q.checked_at?.replace('T', ' ').slice(0, 16)}
                  </span>
                  <span
                    className="tag"
                    style={{ background: `${gradeColor(q.overall_score)}18`, color: gradeColor(q.overall_score) }}
                  >
                    综合 {q.overall_score} 分 · {q.grade}
                  </span>
                </div>
              </div>
              <div className="p-4">
                <div className="grid grid-cols-5 gap-2.5 mb-3.5">
                  {[
                    ['完整性', q.completeness],
                    ['一致性', q.consistency],
                    ['有效性', q.validity],
                    ['唯一性', q.uniqueness],
                    ['时效性', q.timeliness],
                  ].map(([label, v]: any) => (
                    <div key={label} className="rounded-lg border border-[#e9eeec] p-2.5">
                      <div className="text-[11px] text-[#8b9a94]">{label}</div>
                      <div className="text-[17px] font-semibold tabular-nums mt-0.5" style={{ color: gradeColor(v) }}>
                        {v}
                      </div>
                      <div className="h-1 rounded-full bg-[#eef2f0] overflow-hidden mt-1.5">
                        <div className="h-full rounded-full" style={{ width: `${v}%`, background: gradeColor(v) }} />
                      </div>
                    </div>
                  ))}
                </div>

                {q.issues?.length > 0 ? (
                  <div>
                    <SectionTitle>发现的问题（{q.issues.length}）</SectionTitle>
                    <div className="space-y-1.5">
                      {q.issues.map((is: any, i: number) => (
                        <div key={i} className="flex items-start gap-2.5 px-3 py-2 rounded-lg bg-[#f7faf9] border border-[#eef2f0]">
                          <span
                            className="tag flex-shrink-0"
                            style={{
                              background: is.severity === '高' ? '#fdf0f0' : is.severity === '中' ? '#fffaf0' : '#f7faf9',
                              color: is.severity === '高' ? '#c13f3f' : is.severity === '中' ? '#a3700f' : '#6b7d76',
                            }}
                          >
                            {is.severity}
                          </span>
                          <span className="tag bg-white text-[#55665f] border border-[#dde4e1] flex-shrink-0">
                            {is.issue_type}
                          </span>
                          <div className="text-[12.5px] min-w-0">
                            <div className="text-[#2c3d36]">
                              字段 <b>{is.field}</b>，问题数量 <b>{is.count}</b>
                            </div>
                            <div className="text-[11.5px] text-[#8b9a94] mt-0.5 leading-relaxed">{is.suggestion}</div>
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                ) : (
                  <Alert type="success">未发现数据质量问题。</Alert>
                )}
              </div>
            </div>
          ))}
        </div>
      )}

      {tab === 'upload' && (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          <div className="card">
            <div className="card-title">上传数据集</div>
            <div className="p-4 space-y-3.5">
              {!isAdmin && (
                <Alert type="warn">当前角色无上传权限，该功能仅管理员可用。您仍可查看已导入的数据集与质量报告。</Alert>
              )}
              <div>
                <label className="label">数据集类型</label>
                <select className="input" value={uploadType} onChange={(e) => setUploadType(e.target.value)}>
                  {data.supported_types.map((t: any) => (
                    <option key={t.type} value={t.type}>{t.label}</option>
                  ))}
                </select>
              </div>

              <div>
                <label className="label">选择 CSV 文件</label>
                <input
                  ref={fileRef}
                  type="file"
                  accept=".csv"
                  disabled={!isAdmin || uploading}
                  onChange={(e) => e.target.files?.[0] && onFile(e.target.files[0])}
                  className="input file:mr-3 file:py-1.5 file:px-3 file:rounded file:border-0 file:bg-brand-50 file:text-brand-700 file:text-[12px] file:cursor-pointer"
                />
              </div>

              {uploading && <Loading text="上传并检查中…" />}

              <div className="rounded-lg bg-[#f7faf9] border border-[#eef2f0] p-3.5">
                <div className="text-[12.5px] font-medium text-[#33473f] mb-1.5">
                  「{data.supported_types.find((t: any) => t.type === uploadType)?.label}」必需字段
                </div>
                <div className="flex flex-wrap gap-1.5">
                  {data.supported_types.find((t: any) => t.type === uploadType)?.required_fields.map((f: string) => (
                    <span key={f} className="tag bg-white text-[#55665f] border border-[#dde4e1] font-mono text-[11px]">
                      {f}
                    </span>
                  ))}
                </div>
                <a
                  href={api.templateUrl(uploadType)}
                  className="inline-block mt-2.5 text-[12px] text-brand-600 hover:underline"
                >
                  下载该类型的 CSV 模板（含示例行）→
                </a>
              </div>
            </div>
          </div>

          <div className="card">
            <div className="card-title">上传结果与问题处理</div>
            <div className="p-4 space-y-3.5">
              {!lastResult ? (
                <div className="text-[13px] text-[#8b9a94] py-8 text-center">
                  上传文件后，这里会显示质量检查结果与问题处理选项
                </div>
              ) : (
                <>
                  <div className="grid grid-cols-2 gap-2.5">
                    {[
                      ['行数', fmt.n(lastResult.row_count)],
                      ['综合质量分', lastResult.quality.overall_score],
                      ['完整性', lastResult.quality.completeness],
                      ['一致性', lastResult.quality.consistency],
                      ['有效性', lastResult.quality.validity],
                      ['唯一性', lastResult.quality.uniqueness],
                    ].map(([k, v]: any) => (
                      <div key={k} className="rounded-lg border border-[#e9eeec] bg-[#f7faf9] px-3 py-2">
                        <div className="text-[11px] text-[#8b9a94]">{k}</div>
                        <div className="text-[16px] font-semibold tabular-nums text-[#2c3d36] mt-0.5">{v}</div>
                      </div>
                    ))}
                  </div>

                  {lastResult.quality.issues?.length > 0 && (
                    <div>
                      <SectionTitle>发现的问题</SectionTitle>
                      <div className="space-y-1.5">
                        {lastResult.quality.issues.map((is: any, i: number) => (
                          <div key={i} className="text-[12px] px-2.5 py-1.5 rounded bg-[#f7faf9]">
                            <b>{is.field}</b> · {is.issue_type} · {is.count} 处
                            <div className="text-[11px] text-[#8b9a94] mt-0.5">{is.suggestion}</div>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}

                  {uploadType === 'sku_products' || uploadType === 'store_profile' ? (
                    <>
                      <SectionTitle>选择问题处理方式</SectionTitle>
                      <div className="space-y-2">
                        {[
                          ['auto_clean', '自动清洗', '去除全空行与重复行后导入'],
                          ['manual_confirm', '人工确认', '保留原样导入，由业务人员后续核对'],
                          ['keep_raw', '保留原始值', '仅保存文件，不导入业务表'],
                        ].map(([k, t, d]) => (
                          <button
                            key={k}
                            onClick={() => doImport(k)}
                            className="w-full text-left px-3 py-2.5 rounded-lg border border-[#d5ded9] hover:border-brand-300 hover:bg-brand-50 transition-colors"
                          >
                            <div className="text-[13px] font-medium text-[#2c3d36]">{t}</div>
                            <div className="text-[11.5px] text-[#8b9a94] mt-0.5">{d}</div>
                          </button>
                        ))}
                      </div>
                    </>
                  ) : (
                    <Alert type="info">
                      该数据集类型的业务表导入请使用对应模块入口（如品类销售数据请在「品类健康诊断」页点击重算）。
                      文件已完整保存并生成质量报告，可在数据集管理中查看版本与检查结果。
                    </Alert>
                  )}
                </>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
