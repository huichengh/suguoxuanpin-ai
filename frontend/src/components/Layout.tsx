import { useEffect, useState } from 'react'
import { NavLink, useNavigate } from 'react-router-dom'
import { api } from '../services/api'
import DemoPlayer from './DemoPlayer'
import { DemoBadge } from './ui'
interface NavItem {
  path: string
  label: string
  icon: string
  desc: string
  key?: string
}

const NAV: { group: string; items: NavItem[] }[] = [
  {
    group: '总览',
    items: [{ path: '/', label: 'AI经营驾驶舱', icon: '◎', desc: '门店核心指标与AI今日建议' }],
  },
  {
    group: '核心业务',
    items: [
      { path: '/compare', label: '选品比较中心', icon: '⇄', desc: '品类/小类/SKU 多维加权比较', key: 'compare' },
      { path: '/category-health', label: '品类健康诊断', icon: '❤', desc: 'ECR品类评估与四维评分' },
      { path: '/abc-shelf', label: '小类结构分析', icon: '▦', desc: 'ABC分类与货架空间优化' },
      { path: '/association', label: '关联陈列分析', icon: '⇗', desc: 'Apriori购物篮与关联网络' },
      { path: '/forecast', label: '需求预测', icon: '◷', desc: '历史/预测趋势与置信区间' },
    ],
  },
  {
    group: '扩展模块',
    items: [
      { path: '/stores', label: '千店千面', icon: '⌂', desc: '门店画像配置（数据待接入）' },
      { path: '/private-label', label: '自有品牌机会', icon: '◈', desc: '品类级渗透机会判断' },
      { path: '/new-products', label: '新品评估', icon: '✦', desc: '候选池与试销潜力评估' },
    ],
  },
  {
    group: 'AI与数据',
    items: [
      { path: '/agent', label: 'AI选品助手', icon: '◉', desc: '苏果智选AI对话与工具调用' },
      { path: '/data', label: '数据中心', icon: '▤', desc: '数据上传与质量检查' },
      { path: '/approvals', label: '审批中心', icon: '✓', desc: '人机协同审批流程' },
      { path: '/admin', label: '系统管理', icon: '⚙', desc: '参数、用户、权限与日志' },
    ],
  },
]

export default function Layout({ children }: { children: React.ReactNode }) {
  const nav = useNavigate()
  const [user, setUser] = useState<any>(null)
  const [store, setStore] = useState<any>(null)
  const [collapsed, setCollapsed] = useState(false)
  // 演示器挂在 Layout 层，路由切换时不会被卸载
  const [demoOpen, setDemoOpen] = useState(false)

  // 页面内的按钮通过自定义事件打开演示器
  useEffect(() => {
    const open = () => setDemoOpen(true)
    window.addEventListener('suguo:open-demo', open)
    return () => window.removeEventListener('suguo:open-demo', open)
  }, [])

  useEffect(() => {
    const u = localStorage.getItem('suguo_user')
    if (u) setUser(JSON.parse(u))
    api.stores().then((d) => {
      const list = d.items || []
      setStore(list[0])
      // 缓存门店列表供顶部选择器使用
      localStorage.setItem('suguo_stores', JSON.stringify(list))
    }).catch(() => {})
  }, [])

  const logout = () => {
    localStorage.removeItem('suguo_token')
    localStorage.removeItem('suguo_user')
    nav('/login')
  }

  return (
    <div className="flex h-screen overflow-hidden">
      {/* 侧边导航 */}
      <aside
        className={`bg-[#123a2c] text-white flex flex-col flex-shrink-0 transition-all duration-200 ${
          collapsed ? 'w-[62px]' : 'w-[218px]'
        }`}
      >
        <div className="px-4 py-4 border-b border-white/10 flex items-center gap-2.5 min-h-[61px]">
          <div className="w-8 h-8 rounded-md bg-brand-500 flex items-center justify-center font-bold text-[15px] flex-shrink-0">
            苏
          </div>
          {!collapsed && (
            <div className="min-w-0">
              <div className="text-[14px] font-semibold leading-tight">苏果智选</div>
              <div className="text-[10px] text-white/50 leading-tight truncate">
                Suguo AI Assortment
              </div>
            </div>
          )}
        </div>

        <nav className="flex-1 overflow-y-auto py-2">
          {NAV.map((g) => (
            <div key={g.group} className="mb-1">
              {!collapsed && (
                <div className="px-4 py-1.5 text-[10.5px] text-white/35 font-medium tracking-wider">
                  {g.group}
                </div>
              )}
              {g.items.map((it) => (
                <NavLink
                  key={it.path}
                  to={it.path}
                  end={it.path === '/'}
                  title={collapsed ? it.label : undefined}
                  className={({ isActive }) =>
                    `flex items-center gap-2.5 mx-2 px-2.5 py-2 rounded-md text-[13px] transition-colors ${
                      isActive
                        ? 'bg-brand-600 text-white font-medium'
                        : 'text-white/70 hover:bg-white/10 hover:text-white'
                    }`
                  }
                >
                  <span className="w-4 text-center flex-shrink-0 text-[14px]">{it.icon}</span>
                  {!collapsed && <span className="truncate">{it.label}</span>}
                </NavLink>
              ))}
            </div>
          ))}
        </nav>

        <div className="px-3 py-2.5 border-t border-white/10">
          {!collapsed && user && (
            <div className="mb-2">
              <div className="text-[12px] text-white/90 truncate">{user.full_name || user.username}</div>
              <div className="text-[10.5px] text-white/45">{user.role}</div>
            </div>
          )}
          <button
            onClick={logout}
            className="w-full text-[11.5px] text-white/50 hover:text-white/90 py-1.5 rounded hover:bg-white/10 transition-colors"
          >
            退出登录
          </button>
        </div>
      </aside>

      {/* 主区域 */}
      <div className="flex-1 flex flex-col overflow-hidden min-w-0">
        <header className="h-[61px] bg-white border-b border-[#e3e8e6] flex items-center gap-4 px-5 flex-shrink-0">
          <button
            onClick={() => setCollapsed(!collapsed)}
            className="w-7 h-7 rounded hover:bg-[#f0f4f2] text-[#55665f] flex items-center justify-center flex-shrink-0"
            title="折叠导航"
          >
            ☰
          </button>
          <div className="min-w-0">
            <div className="text-[15px] font-semibold text-[#1a2b24] leading-tight">
              苏果智选 · AI 社区商超智能选品与品类优化平台
            </div>
          </div>

          <div className="ml-auto flex items-center gap-3">
            <button
              onClick={() => setDemoOpen(true)}
              className="btn-primary text-[12px] px-3 py-1.5"
              title="自动播放 8 步完整业务闭环"
            >
              ▶ 2 分钟自动演示
            </button>
            {store && (
              <div className="flex items-center gap-1.5 text-[12px] text-[#55665f]">
                <span className="text-[#8b9a94]">当前门店</span>
                <select
                  className="input py-1 text-[12px] w-auto max-w-[200px]"
                  value={store.id}
                  onChange={(e) => {
                    const s = (JSON.parse(localStorage.getItem('suguo_stores') || '[]')).find(
                      (x: any) => String(x.id) === e.target.value,
                    )
                    if (s) setStore(s)
                  }}
                >
                  {(JSON.parse(localStorage.getItem('suguo_stores') || '[]').length
                    ? JSON.parse(localStorage.getItem('suguo_stores') || '[]')
                    : [store]
                  ).map((s: any) => (
                    <option key={s.id} value={s.id}>{s.name}</option>
                  ))}
                </select>
              </div>
            )}
            <DemoBadge />
          </div>
        </header>

        <main className="flex-1 overflow-auto p-5 bg-[#f5f7f6]">{children}</main>
      </div>

      {demoOpen && <DemoPlayer onClose={() => setDemoOpen(false)} />}
    </div>
  )
}
