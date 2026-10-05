import axios from 'axios'

export const API_BASE = '/api'

export const http = axios.create({ baseURL: API_BASE, timeout: 60000 })

// 令牌同时放在两个位置，两个位置都能被服务端读到：
//   Authorization —— 标准做法，本地与直连部署时使用
//   X-Auth-Token   —— 自定义头。部分网关会改写 Authorization 头（追加自己的凭据），
//                     导致服务端截取到的令牌被污染而验签失败；自定义头不受此影响。
// 服务端优先读 X-Auth-Token，缺失时回退到 Authorization。
http.interceptors.request.use((cfg) => {
  const token = localStorage.getItem('suguo_token')
  if (token) {
    cfg.headers.Authorization = `Bearer ${token}`
    cfg.headers['X-Auth-Token'] = token
  }
  return cfg
})

http.interceptors.response.use(
  (r) => r,
  (err) => {
    if (err.response?.status === 401) {
      localStorage.removeItem('suguo_token')
      localStorage.removeItem('suguo_user')
      if (!location.hash.includes('/login')) location.hash = '#/login'
    }
    const msg = err.response?.data?.detail || err.message || '请求失败'
    return Promise.reject(new Error(typeof msg === 'string' ? msg : JSON.stringify(msg)))
  },
)

export const api = {
  // 认证
  login: (username: string, password: string) =>
    http.post('/auth/login', { username, password }).then((r) => r.data),
  me: () => http.get('/auth/me').then((r) => r.data),

  // 驾驶舱
  dashboard: (storeId?: number) =>
    http.get('/dashboard/summary', { params: { store_id: storeId } }).then((r) => r.data),
  categories: () => http.get('/categories').then((r) => r.data),
  allCategoryHealth: () => http.get('/categories/health-all').then((r) => r.data),
  categoryHealth: (id: number) => http.get(`/categories/${id}/health`).then((r) => r.data),
  recalcHealth: () => http.post('/categories/recalculate').then((r) => r.data),

  // 比较
  compareOptions: (mode: string) => http.get('/compare/options', { params: { mode } }).then((r) => r.data),
  compare: (payload: any) => http.post('/compare', payload).then((r) => r.data),

  // 多门店管理
  allStores: () => http.get('/stores-ops/all').then((r) => r.data),
  createStore: (payload: any) => http.post('/stores-ops', payload).then((r) => r.data),
  updateStore: (payload: any) => http.patch(`/stores-ops/${payload.store_id}`, payload).then((r) => r.data),
  compareStores: (ids: number[]) => http.post('/stores-ops/compare', { store_ids: ids }).then((r) => r.data),

  // 小类分析
  subcategories: (categoryId?: number, keyword?: string) =>
    http.get('/subcategories', {
      params: { category_id: categoryId, keyword },
    }).then((r) => r.data),
  rebuildSubcategories: () => http.post('/subcategories/rebuild').then((r) => r.data),
  subCompareOptions: () => http.get('/subcategories/compare/options').then((r) => r.data),
  compareSubcategories: (payload: { ids: number[]; weights?: any }) =>
    http.post('/subcategories/compare', payload).then((r) => r.data),
  abc: () => http.get('/subcategories/abc').then((r) => r.data),
  recalcAbc: (payload: any) => http.post('/subcategories/abc/recalculate', payload).then((r) => r.data),
  optimizeShelf: (payload: any) => http.post('/subcategories/shelf', payload).then((r) => r.data),
  shelfByCategory: (totalArea: number) =>
    http.get('/subcategories/shelf/categories', { params: { total_area: totalArea } }).then((r) => r.data),

  // 关联
  association: (source?: string) =>
    http.get('/association-rules', { params: source ? { source } : {} }).then((r) => r.data),
  recalcAssociation: (payload: any) =>
    http.post('/association-rules/recalculate', payload).then((r) => r.data),
  itemProfile: (name: string) =>
    http.get(`/association-rules/item/${encodeURIComponent(name)}`).then((r) => r.data),

  // 预测
  forecast: (category?: string) =>
    http.get('/forecast', { params: category ? { category } : {} }).then((r) => r.data),
  runForecast: (payload: any) => http.post('/forecast/run', payload).then((r) => r.data),

  // 扩展模块
  stores: () => http.get('/stores').then((r) => r.data),
  privateLabel: () => http.get('/private-label/opportunities').then((r) => r.data),
  newProducts: () => http.get('/new-products/candidates').then((r) => r.data),
  evaluateNewProduct: (payload: any) => http.post('/new-products/evaluate', payload).then((r) => r.data),
  deleteCandidate: (id: number) => http.delete(`/new-products/candidates/${id}`).then((r) => r.data),

  // AI
  agentTools: () => http.get('/agent/tools').then((r) => r.data),
  chat: (question: string, sessionId?: string) =>
    http.post('/agent/chat', { question, session_id: sessionId }).then((r) => r.data),
  chatHistory: (sessionId?: string) =>
    http.get('/agent/history', { params: sessionId ? { session_id: sessionId } : {} }).then((r) => r.data),

  // 数据中心
  datasets: () => http.get('/data/datasets').then((r) => r.data),
  dataQuality: (type?: string) =>
    http.get('/data/quality', { params: type ? { dataset_type: type } : {} }).then((r) => r.data),
  upload: (file: File, datasetType: string) => {
    const fd = new FormData()
    fd.append('file', file)
    fd.append('dataset_type', datasetType)
    return http.post('/data/upload', fd, { timeout: 120000 }).then((r) => r.data)
  },
  importDataset: (payload: any) => http.post('/data/import', payload).then((r) => r.data),
  templateUrl: (t: string) => `${API_BASE}/data/template/${t}`,

  // 审批
  approvals: (status?: string) =>
    http.get('/approvals', { params: status ? { status } : {} }).then((r) => r.data),
  createApproval: (payload: any) => http.post('/approvals', payload).then((r) => r.data),
  decideApproval: (id: number, action: string, comment?: string) =>
    http.patch(`/approvals/${id}`, { action, comment }).then((r) => r.data),
  recommendations: () => http.get('/approvals/recommendations').then((r) => r.data),

  // 管理
  modelSettings: () => http.get('/admin/model-settings').then((r) => r.data),
  updateModelSetting: (key: string, value: any, reason?: string) =>
    http.put('/admin/model-settings', { key, value, reason }).then((r) => r.data),
  users: () => http.get('/admin/users').then((r) => r.data),
  roles: () => http.get('/admin/roles').then((r) => r.data),
  adminStores: () => http.get('/admin/stores').then((r) => r.data),
  updateAdminStore: (id: number, payload: any) =>
    http.patch(`/admin/stores/${id}`, payload).then((r) => r.data),
  knowledge: () => http.get('/admin/knowledge').then((r) => r.data),
  createKnowledge: (payload: any) => http.post('/admin/knowledge', payload).then((r) => r.data),
  auditLogs: () => http.get('/admin/audit-logs').then((r) => r.data),
  modelLogs: () => http.get('/admin/model-logs').then((r) => r.data),
  analysisHistory: () => http.get('/analysis-history').then((r) => r.data),

  report: () => http.get('/report/diagnosis', { responseType: 'text' }).then((r) => r.data),
}

export const fmt = {
  n: (v: number | null | undefined, d = 0) =>
    v === null || v === undefined || Number.isNaN(v) ? '—' : v.toLocaleString('zh-CN', { maximumFractionDigits: d }),
  money: (v: number | null | undefined) => (v === null || v === undefined ? '—' : `¥${fmt.n(v, 0)}`),
  pct: (v: number | null | undefined, d = 1) =>
    v === null || v === undefined ? '—' : `${v.toFixed(d)}%`,
  signPct: (v: number | null | undefined, d = 1) =>
    v === null || v === undefined ? '—' : `${v >= 0 ? '+' : ''}${v.toFixed(d)}%`,
}

export const ALERT_COLOR: Record<string, string> = {
  绿灯: '#338f68',
  黄灯: '#d9a520',
  橙灯: '#e8833a',
  红灯: '#d94a4a',
}

export function scoreColor(score: number) {
  if (score >= 85) return '#257354'
  if (score >= 70) return '#57ad84'
  if (score >= 55) return '#d9a520'
  if (score >= 40) return '#e8833a'
  return '#d94a4a'
}

export function scoreLabel(score: number) {
  if (score >= 85) return '优秀'
  if (score >= 70) return '良好'
  if (score >= 55) return '一般'
  if (score >= 40) return '较差'
  return '差'
}
