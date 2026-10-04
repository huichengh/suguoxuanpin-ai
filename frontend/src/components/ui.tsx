import { ReactNode } from 'react'

export function DemoBadge({ text, className = '' }: { text?: string; className?: string }) {
  return <span className={`demo-label ${className}`}>⚠ {text || '模拟演示数据，不代表华润苏果真实经营数据'}</span>
}

export function SourceTag({ source }: { source: string }) {
  const isAttachment = source === 'attachment'
  return (
    <span
      className={`tag ${
        isAttachment
          ? 'bg-[#eef2fb] text-[#3a5a9a] border border-[#d3def5]'
          : 'bg-brand-50 text-brand-700 border border-brand-200'
      }`}
    >
      {isAttachment ? '附件参考结果' : '系统实时重算'}
    </span>
  )
}

export function Alert({ type = 'info', children }: { type?: 'info' | 'warn' | 'error' | 'success'; children: ReactNode }) {
  const map = {
    info: 'bg-[#eef4fb] border-[#d3e2f5] text-[#2d5588]',
    warn: 'bg-[#fff8ec] border-[#f2dfb8] text-[#8a6212]',
    error: 'bg-[#fdf0f0] border-[#f5d2d2] text-[#a33]',
    success: 'bg-brand-50 border-brand-200 text-brand-800',
  }
  return (
    <div className={`rounded-md border px-3.5 py-2.5 text-[12.5px] leading-relaxed ${map[type]}`}>
      {children}
    </div>
  )
}

export function Empty({ title, hint, action }: { title: string; hint?: string; action?: ReactNode }) {
  return (
    <div className="dashed-box">
      <div className="text-[14px] font-medium text-[#55665f]">{title}</div>
      {hint && <div className="text-[12.5px] text-[#8b9a94] mt-1.5 max-w-lg mx-auto leading-relaxed">{hint}</div>}
      {action && <div className="mt-3.5">{action}</div>}
    </div>
  )
}

export function Loading({ text = '加载中…' }: { text?: string }) {
  return (
    <div className="flex items-center justify-center py-16 text-[13px] text-[#8b9a94] gap-2">
      <span className="w-3.5 h-3.5 border-2 border-brand-200 border-t-brand-600 rounded-full animate-spin" />
      {text}
    </div>
  )
}

export function ErrorBox({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <Alert type="error">
      <div className="flex items-center justify-between gap-3">
        <span>{message}</span>
        {onRetry && (
          <button onClick={onRetry} className="text-[12px] underline hover:no-underline flex-shrink-0">
            重试
          </button>
        )}
      </div>
    </Alert>
  )
}

export function StatCard({
  label, value, unit, hint, tone = 'default', icon,
}: {
  label: string
  value: ReactNode
  unit?: string
  hint?: ReactNode
  tone?: 'default' | 'good' | 'warn' | 'bad' | 'brand'
  icon?: ReactNode
}) {
  const tones: Record<string, string> = {
    default: 'text-[#1a2b24]',
    good: 'text-brand-600',
    warn: 'text-[#d9a520]',
    bad: 'text-[#d94a4a]',
    brand: 'text-brand-700',
  }
  return (
    <div className="card p-4">
      <div className="flex items-start justify-between gap-2">
        <span className="text-[12px] text-[#6b7d76] leading-snug">{label}</span>
        {icon && <span className="text-brand-500 opacity-70 flex-shrink-0">{icon}</span>}
      </div>
      <div className={`mt-1.5 flex items-baseline gap-1 ${tones[tone]}`}>
        <span className="text-[26px] font-semibold leading-none tabular-nums">{value}</span>
        {unit && <span className="text-[12px] text-[#8b9a94]">{unit}</span>}
      </div>
      {hint && <div className="mt-1.5 text-[11.5px] text-[#8b9a94] leading-snug">{hint}</div>}
    </div>
  )
}

export function Tabs({
  items, active, onChange,
}: {
  items: { key: string; label: string; badge?: number | string }[]
  active: string
  onChange: (k: string) => void
}) {
  return (
    <div className="flex items-center gap-1 border-b border-[#e3e8e6] px-1">
      {items.map((t) => (
        <button
          key={t.key}
          onClick={() => onChange(t.key)}
          className={`px-3.5 py-2.5 text-[13px] font-medium border-b-2 -mb-px transition-colors flex items-center gap-1.5 ${
            active === t.key
              ? 'border-brand-600 text-brand-700'
              : 'border-transparent text-[#6b7d76] hover:text-[#33473f]'
          }`}
        >
          {t.label}
          {t.badge !== undefined && (
            <span className="px-1.5 py-0.5 rounded text-[10.5px] bg-[#eef2f0] text-[#6b7d76] tabular-nums">
              {t.badge}
            </span>
          )}
        </button>
      ))}
    </div>
  )
}

export function Modal({
  open, onClose, title, children, width = 'max-w-3xl',
}: {
  open: boolean; onClose: () => void; title: string; children: ReactNode; width?: string
}) {
  if (!open) return null
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-6 bg-black/35" onClick={onClose}>
      <div className={`card w-full ${width} max-h-[86vh] flex flex-col shadow-2xl`} onClick={(e) => e.stopPropagation()}>
        <div className="card-title flex-shrink-0">
          {title}
          <button onClick={onClose} className="text-[#8b9a94] hover:text-[#33473f] text-lg leading-none px-1">
            ×
          </button>
        </div>
        <div className="overflow-auto p-5">{children}</div>
      </div>
    </div>
  )
}

export function RiskBadge({ level }: { level: string }) {
  const map: Record<string, string> = {
    高: 'bg-[#fdf0f0] text-[#c13f3f] border border-[#f0cccc]',
    中: 'bg-[#fff8ec] text-[#a3700f] border border-[#f2dfb8]',
    低: 'bg-brand-50 text-brand-700 border border-brand-200',
  }
  return <span className={`tag ${map[level] || map['低']}`}>{level}风险</span>
}

export function PriorityBadge({ priority }: { priority: string }) {
  const map: Record<string, string> = {
    高: 'bg-[#fdf0f0] text-[#c13f3f] border border-[#f0cccc]',
    中: 'bg-[#fff8ec] text-[#a3700f] border border-[#f2dfb8]',
    低: 'bg-[#eef2f0] text-[#6b7d76] border border-[#dde4e1]',
  }
  return <span className={`tag ${map[priority] || map['低']}`}>{priority}优先级</span>
}

export function StatusBadge({ status }: { status: string }) {
  const map: Record<string, string> = {
    待审批: 'bg-[#fff8ec] text-[#a3700f] border border-[#f2dfb8]',
    已通过: 'bg-brand-50 text-brand-700 border border-brand-200',
    已驳回: 'bg-[#fdf0f0] text-[#c13f3f] border border-[#f0cccc]',
    已撤回: 'bg-[#eef2f0] text-[#6b7d76] border border-[#dde4e1]',
  }
  return <span className={`tag ${map[status] || map['已撤回']}`}>{status}</span>
}

export function SectionTitle({ children, extra }: { children: ReactNode; extra?: ReactNode }) {
  return (
    <div className="flex items-center justify-between mb-3">
      <h3 className="text-[14px] font-semibold text-[#1a2b24] flex items-center gap-2">
        <span className="w-1 h-3.5 bg-brand-600 rounded-full" />
        {children}
      </h3>
      {extra}
    </div>
  )
}
