import { useEffect, useState } from 'react'
import { Chart, AXIS_STYLE, TOOLTIP } from '../components/Chart'
import { Alert, DemoBadge, ErrorBox, Loading, SectionTitle } from '../components/ui'
import { api, scoreColor } from '../services/api'

export default function PrivateLabel() {
  const [data, setData] = useState<any>(null)
  const [err, setErr] = useState('')

  const load = () => {
    setErr('')
    api.privateLabel().then(setData).catch((e) => setErr(e.message))
  }
  useEffect(load, [])

  if (err) return <ErrorBox message={err} onRetry={load} />
  if (!data) return <Loading />

  const items = data.items

  const scatterOption = {
    grid: { left: 60, right: 40, top: 30, bottom: 50 },
    tooltip: {
      ...TOOLTIP,
      formatter: (p: any) => {
        const r = p.data.raw
        return `${r.category}<br/>毛利贡献 ${r.margin_contribution}%<br/>销量贡献 ${r.sales_contribution}%<br/>健康度 ${r.overall_score} 分`
      },
    },
    xAxis: { type: 'value', name: '销量贡献(%)', nameLocation: 'middle', nameGap: 30, ...AXIS_STYLE },
    yAxis: { type: 'value', name: '毛利贡献(%)', ...AXIS_STYLE },
    series: [{
      type: 'scatter',
      symbolSize: (v: any, p: any) => Math.max(14, (p.data.raw.overall_score / 100) * 28),
      data: items.map((r: any) => ({
        value: [r.sales_contribution, r.margin_contribution],
        raw: r,
        itemStyle: {
          color: r.potential === '重点关注' ? '#257354' : r.potential === '可评估' ? '#e8833a' : '#c3ceca',
          opacity: 0.85,
        },
      })),
      label: {
        show: true, position: 'right', fontSize: 11, color: '#55665f',
        formatter: (p: any) => p.data.raw.category,
      },
      markArea: {
        silent: true,
        itemStyle: { color: 'rgba(37,115,84,0.05)' },
        data: [[{ xAxis: 0, yAxis: 20, name: '重点关注区' }, { xAxis: 40, yAxis: 40 }]],
        label: { show: true, position: 'insideTopLeft', fontSize: 10, color: '#8b9a94' },
      },
    }],
  }

  return (
    <div className="space-y-4 max-w-[1680px]">
      <div className="flex items-center justify-between gap-4 flex-wrap">
        <div>
          <h1 className="text-[19px] font-semibold text-[#1a2b24]">自有品牌机会</h1>
          <p className="text-[12.5px] text-[#6b7d76] mt-0.5">
            判断层级：{data.level} ｜ 面向门店采购与品类经理的自有品牌渗透参考
          </p>
        </div>
        <DemoBadge />
      </div>

      <Alert type="warn">
        <div className="font-medium mb-1">当前结论为品类级，不是 SKU 级预测</div>
        <div className="text-[12px] leading-relaxed">{data.level_note}</div>
      </Alert>

      {data.focus?.length > 0 && (
        <div className="card border-brand-200 bg-brand-50">
          <div className="p-4">
            <div className="text-[12px] text-brand-700 font-medium mb-1.5">建议重点关注自有品牌渗透的品类</div>
            <div className="flex flex-wrap gap-2">
              {data.focus.map((c: string) => (
                <span key={c} className="px-3 py-1.5 rounded-lg bg-white border border-brand-300 text-[13px] font-medium text-brand-800">
                  {c}
                </span>
              ))}
            </div>
            <div className="text-[11.5px] text-brand-700/75 mt-2.5 leading-relaxed">
              判断依据：这些品类的毛利贡献较高，说明有利润承载空间；健康度处于中上水平，说明商品结构可承接自有品牌替换。
            </div>
          </div>
        </div>
      )}

      <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
        <div className="card">
          <div className="card-title">品类机会分布</div>
          <div className="p-4">
            <Chart
              option={scatterOption}
              height={340}
              title="销量贡献 × 毛利贡献（气泡=健康度）"
              onExport={() => {}}
            />
          </div>
        </div>

        <div className="card">
          <div className="card-title">自有品牌渗透空间对比</div>
          <div className="p-4">
            <Chart
              option={{
                grid: { left: 80, right: 40, top: 30, bottom: 30 },
                tooltip: { ...TOOLTIP },
                legend: { top: 0, itemWidth: 12, itemHeight: 8, textStyle: { fontSize: 11 } },
                xAxis: { type: 'value', ...AXIS_STYLE },
                yAxis: {
                  type: 'category',
                  data: [...items].reverse().map((i: any) => i.category),
                  ...AXIS_STYLE, splitLine: { show: false },
                },
                series: [
                  {
                    name: '毛利贡献(%)', type: 'bar', barWidth: 13,
                    data: [...items].reverse().map((i: any) => ({
                      value: i.margin_contribution,
                      itemStyle: { color: '#257354', borderRadius: [0, 4, 4, 0] },
                    })),
                  },
                  {
                    name: '销量贡献(%)', type: 'bar', barWidth: 13,
                    data: [...items].reverse().map((i: any) => ({
                      value: i.sales_contribution,
                      itemStyle: { color: '#8bcbaa', borderRadius: [0, 4, 4, 0] },
                    })),
                  },
                ],
              }}
              height={340}
              title="各品类毛利与销量贡献对比"
              onExport={() => {}}
            />
          </div>
        </div>
      </div>

      <div className="card overflow-hidden">
        <div className="card-title">品类级自有品牌机会清单</div>
        <div className="overflow-x-auto">
          <table className="w-full min-w-[880px]">
            <thead>
              <tr>
                <th className="table-th">品类</th>
                <th className="table-th">机会判断</th>
                <th className="table-th text-right">毛利贡献</th>
                <th className="table-th text-right">销量贡献</th>
                <th className="table-th text-right">健康度</th>
                <th className="table-th text-right">周转天数</th>
                <th className="table-th">判断依据</th>
              </tr>
            </thead>
            <tbody>
              {items.map((r: any) => (
                <tr key={r.category}>
                  <td className="table-td font-medium">{r.category}</td>
                  <td className="table-td">
                    <span
                      className="tag"
                      style={{
                        background: r.potential === '重点关注' ? '#f0f9f4' : r.potential === '可评估' ? '#fffaf0' : '#f7faf9',
                        color: r.potential === '重点关注' ? '#257354' : r.potential === '可评估' ? '#a3700f' : '#6b7d76',
                      }}
                    >
                      {r.potential}
                    </span>
                  </td>
                  <td className="table-td text-right tabular-nums font-medium">{r.margin_contribution}%</td>
                  <td className="table-td text-right tabular-nums">{r.sales_contribution}%</td>
                  <td className="table-td text-right">
                    <span className="tabular-nums" style={{ color: scoreColor(r.overall_score) }}>
                      {r.overall_score}
                    </span>
                  </td>
                  <td className="table-td text-right tabular-nums">{r.turnover_days}</td>
                  <td className="table-td text-[11.5px] text-[#55665f] leading-relaxed max-w-[380px]">{r.basis}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      <div className="card">
        <div className="card-title">SKU 级自有品牌替代模型：所需数据</div>
        <div className="p-4">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <SectionTitle>当前缺失的字段</SectionTitle>
              <div className="space-y-1.5">
                {data.missing_data.map((m: string, i: number) => (
                  <div key={i} className="flex items-start gap-2 text-[12.5px] text-[#3d5049]">
                    <span className="w-4 h-4 rounded-full bg-[#fdf0f0] text-[#c13f3f] flex items-center justify-center text-[9.5px] flex-shrink-0 mt-0.5">
                      !
                    </span>
                    <span>{m}</span>
                  </div>
                ))}
              </div>
              <div className="mt-3">
                <Alert type="info">
                  可在「数据中心」上传 SKU 级数据（模板含：SKU、品牌、是否自有品牌、品类、销量、销售额、毛利率、周转、零售价、竞品价格）。
                  导入后本模块会自动启用 SKU 级替代分析。
                </Alert>
              </div>
            </div>
            <div>
              <SectionTitle>SKU 级模型接入后将输出</SectionTitle>
              <div className="space-y-2">
                {[
                  ['适合自有品牌替代的品类', '按毛利率、周转、竞品价格带综合筛选'],
                  ['潜在替代商品', '同类目中毛利空间大、周转慢的具体 SKU'],
                  ['预计毛利改善', '替代前后的毛利额差额（基于实际数据计算）'],
                  ['风险提示', '品牌认知风险、供应稳定性、品质一致性风险'],
                ].map(([t, d]) => (
                  <div key={t} className="rounded-lg border border-[#e9eeec] bg-[#f7faf9] p-3">
                    <div className="text-[12.5px] font-medium text-[#2c3d36]">{t}</div>
                    <div className="text-[11.5px] text-[#8b9a94] mt-0.5 leading-relaxed">{d}</div>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
