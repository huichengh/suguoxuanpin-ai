import { useEffect, useRef, useState } from 'react'
import ReactECharts from 'echarts-for-react'

/** 图表统一封装：自带导出 PNG 按钮 */
export function Chart({
  option,
  height = 320,
  title,
  onExport,
  loading,
}: {
  option: any
  height?: number
  title?: string
  onExport?: () => void
  loading?: boolean
}) {
  const ref = useRef<any>(null)

  const exportPng = () => {
    const inst = ref.current?.getEchartsInstance?.()
    if (!inst) return
    const url = inst.getDataURL({ pixelRatio: 2, backgroundColor: '#fff' })
    const a = document.createElement('a')
    a.href = url
    a.download = `${title || 'chart'}.png`
    a.click()
  }

  return (
    <div className="relative">
      {(title || onExport) && (
        <div className="flex items-center justify-between mb-1 px-1">
          <span className="text-[12px] text-[#6b7d76]">{title}</span>
          {onExport && (
            <button
              onClick={exportPng}
              className="text-[11px] text-brand-600 hover:text-brand-700 hover:underline"
            >
              导出 PNG
            </button>
          )}
        </div>
      )}
      <ReactECharts
        ref={ref}
        option={option}
        notMerge
        style={{ height: `${height}px`, width: '100%' }}
        opts={{ renderer: 'canvas' }}
        showLoading={loading}
      />
    </div>
  )
}

export const AXIS_STYLE = {
  axisLine: { lineStyle: { color: '#d5ded9' } },
  axisLabel: { color: '#6b7d76', fontSize: 11 },
  splitLine: { lineStyle: { color: '#f0f3f2' } },
}

export const TOOLTIP = {
  trigger: 'axis' as const,
  axisPointer: { type: 'shadow' as const },
  backgroundColor: 'rgba(26,43,36,0.92)',
  borderWidth: 0,
  textStyle: { color: '#fff', fontSize: 12 },
}

export const PALETTE = ['#257354', '#e8833a', '#4a7fb5', '#8bcbaa', '#d9a520', '#7a6bbf']
