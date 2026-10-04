import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../services/api'

const DEMO_ACCOUNTS = [
  { u: 'admin', p: 'admin123', role: '管理员', desc: '全部权限' },
  { u: 'buyer', p: 'buyer123', role: '采购经理', desc: '商品比较、选品建议、新品、审批' },
  { u: 'category', p: 'category123', role: '品类经理', desc: '品类诊断、关联规则、需求预测' },
  { u: 'store', p: 'store123', role: '门店店长', desc: '查看本门店分析与建议' },
  { u: 'viewer', p: 'viewer123', role: '普通查看', desc: '只读' },
]

export default function Login() {
  const nav = useNavigate()
  const [username, setUsername] = useState('admin')
  const [password, setPassword] = useState('admin123')
  const [err, setErr] = useState('')
  const [busy, setBusy] = useState(false)

  const submit = async (e: React.FormEvent) => {
    e.preventDefault()
    setErr('')
    setBusy(true)
    try {
      const d = await api.login(username, password)
      localStorage.setItem('suguo_token', d.access_token)
      localStorage.setItem('suguo_user', JSON.stringify(d.user))
      nav('/')
    } catch (e: any) {
      setErr(e.message || '登录失败')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-gradient-to-br from-[#0f2e24] via-[#17402f] to-[#1d5240] p-6">
      <div className="w-full max-w-[880px] grid grid-cols-1 lg:grid-cols-2 gap-0 rounded-xl overflow-hidden shadow-2xl">
        {/* 左侧介绍 */}
        <div className="bg-[#123a2c] text-white p-9">
          <div className="flex items-center gap-2.5 mb-6">
            <div className="w-10 h-10 rounded-lg bg-brand-500 flex items-center justify-center font-bold text-lg">
              苏
            </div>
            <div>
              <div className="text-[19px] font-semibold leading-tight">苏果智选</div>
              <div className="text-[11px] text-white/50">Suguo AI Assortment Intelligence</div>
            </div>
          </div>

          <h1 className="text-[17px] font-semibold mb-3 leading-relaxed">
            AI 社区商超智能选品<br />与品类优化平台
          </h1>
          <p className="text-[12.5px] text-white/60 leading-relaxed mb-6">
            面向社区商超采购人员、品类经理、门店店长的智能选品决策平台。
            核心价值不是替代采购人员，而是「AI 辅助决策 + 数据驱动选品 + 人工最终确认」。
          </p>

          <div className="space-y-2.5 text-[12px] text-white/70">
            {[
              '品类健康度评分 · Apriori 购物篮 · 需求预测',
              '选品比较中心 · 关联陈列分析 · AI 综合选品方案',
              '三级审批机制 · 完整权限体系 · 全链路可追溯',
            ].map((t) => (
              <div key={t} className="flex items-start gap-2">
                <span className="text-brand-400 mt-0.5">▸</span>
                <span>{t}</span>
              </div>
            ))}
          </div>

          <div className="mt-7 pt-5 border-t border-white/10">
            <div className="text-[11px] text-amber-300/90 leading-relaxed">
              ⚠ 演示数据说明
            </div>
            <div className="text-[11px] text-white/45 leading-relaxed mt-1">
              平台当前数据为基于公开行业数据构造的模拟演示数据，不代表华润苏果真实经营数据。
              附件参考结果与系统实时重算结果分别标注来源。
            </div>
          </div>
        </div>

        {/* 右侧登录 */}
        <div className="bg-white p-9">
          <h2 className="text-[17px] font-semibold mb-1.5">登录平台</h2>
          <p className="text-[12.5px] text-[#6b7d76] mb-6">
            请使用下方演示账号登录，不同角色对应不同权限范围。
          </p>

          <form onSubmit={submit}>
            <div className="mb-3.5">
              <label className="label">用户名</label>
              <input
                className="input"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                autoComplete="username"
              />
            </div>
            <div className="mb-4">
              <label className="label">密码</label>
              <input
                className="input"
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                autoComplete="current-password"
              />
            </div>

            {err && (
              <div className="mb-3.5 rounded-md border border-[#f0cccc] bg-[#fdf0f0] px-3 py-2 text-[12.5px] text-[#c13f3f]">
                {err}
              </div>
            )}

            <button type="submit" disabled={busy} className="btn-primary w-full py-2.5">
              {busy ? '登录中…' : '登 录'}
            </button>
          </form>

          <div className="mt-6 pt-5 border-t border-[#eef2f0]">
            <div className="text-[12px] font-medium text-[#55665f] mb-2.5">演示账号（点击自动填充）</div>
            <div className="space-y-1.5">
              {DEMO_ACCOUNTS.map((a) => (
                <button
                  key={a.u}
                  onClick={() => {
                    setUsername(a.u)
                    setPassword(a.p)
                  }}
                  className={`w-full text-left px-3 py-2 rounded-md border text-[12px] transition-colors ${
                    username === a.u
                      ? 'border-brand-400 bg-brand-50'
                      : 'border-[#e3e8e6] hover:border-brand-300 hover:bg-[#f7faf9]'
                  }`}
                >
                  <div className="flex items-center justify-between gap-2">
                    <span className="font-medium text-[#2c3d36]">{a.role}</span>
                    <span className="text-[11px] text-[#8b9a94] font-mono">{a.u} / {a.p}</span>
                  </div>
                  <div className="text-[11px] text-[#8b9a94] mt-0.5">{a.desc}</div>
                </button>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
