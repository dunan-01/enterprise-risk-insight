import { useEffect, useRef } from 'react'
import * as echarts from 'echarts'
import type { Relation } from '../api/types'
import { relationColor } from '../lib/presentation'

/**
 * 企业关系网络图（ECharts graph 系列）。
 * 中心节点 = 当前企业，外围节点 = 一跳直接关联企业，边 = 关系类型。
 * 只画一跳，不扩展。
 */

interface GraphNode {
  id: string
  name: string
  symbolSize: number
  itemStyle: { color: string }
  label: { show: boolean; formatter: (p: unknown) => string; color: string }
  value: string
}

export default function RelationGraph({
  companyId,
  companyName,
  relations,
  height = 480,
}: {
  companyId: string
  companyName: string
  relations: Relation[]
  height?: number
}) {
  const containerRef = useRef<HTMLDivElement>(null)
  const chartRef = useRef<echarts.ECharts | null>(null)

  useEffect(() => {
    const el = containerRef.current
    if (!el) return
    const chart = echarts.init(el)
    chartRef.current = chart

    const nodes: GraphNode[] = [
      {
        id: companyId,
        name: companyName,
        symbolSize: 58,
        itemStyle: { color: '#2563eb' },
        label: { show: true, formatter: () => `{b}\n${companyId}`, color: '#fff' },
        value: companyId,
      },
    ]
    const edges: Array<{
      source: string
      target: string
      label: { show: boolean; formatter: string; color: string }
      lineStyle: { color: string; width: number; type: 'solid' | 'dashed' }
    }> = []

    // 去重：同一关联企业可能有多条关系，节点只建一个，边全部保留
    const seen = new Set<string>([companyId])
    for (const r of relations) {
      const counter =
        r.from_company_id === companyId ? r.to_company_id : r.from_company_id
      const counterName =
        (r.from_company_id === companyId ? r.to_company_name : r.from_company_name) ??
        counter
      if (!seen.has(counter)) {
        seen.add(counter)
        nodes.push({
          id: counter,
          name: counterName,
          symbolSize: 34,
          itemStyle: { color: '#3b82f6' },
          label: { show: true, formatter: () => `{b}\n${counter}`, color: '#c7d6ee' },
          value: counter,
        })
      }
      const color = relationColor(r.relation_type)
      edges.push({
        source: r.from_company_id,
        target: r.to_company_id,
        label: {
          show: true,
          formatter: r.relation_type,
          color,
        },
        lineStyle: {
          color,
          width: r.relation_type.includes('担保') ? 2 : 2.4,
          type: r.relation_type.includes('担保') ? 'dashed' : 'solid',
        },
      })
    }

    chart.setOption({
      backgroundColor: 'transparent',
      tooltip: {
        trigger: 'item',
        backgroundColor: 'rgba(10,22,40,0.92)',
        borderColor: 'rgba(148,163,184,0.3)',
        textStyle: { color: '#e6edf7', fontSize: 12 },
        formatter: (p: { dataType: string; data: { name: string; value: string }; value: string[] }) => {
          if (p.dataType === 'node') {
            const d = p.data
            return `<b>${d.name}</b><br/><span style="color:#8ea3c4">${d.value}</span>`
          }
          return `<span style="color:#8ea3c4">关系</span> ${p.value[0]} → ${p.value[1]}`
        },
      },
      // 注意：不配置 legend 组件、data 不携带 category 字段 ——
      // echarts 5.6 中 graph 系列二者组合存在 bug（数据被处理为空导致无法渲染）
      series: [
        {
          type: 'graph',
          layout: 'force',
          data: nodes,
          links: edges,
          roam: true,
          draggable: true,
          force: {
            repulsion: 320,
            edgeLength: [110, 190],
            gravity: 0.12,
            friction: 0.6,
          },
          label: {
            show: true,
            fontSize: 11,
            lineHeight: 16,
            backgroundColor: 'rgba(10,22,40,0.6)',
            borderRadius: 4,
            padding: [3, 6],
            formatter: (p: { data: GraphNode }) => p.data.name,
          },
          edgeLabel: { show: true, fontSize: 10, backgroundColor: 'rgba(10,22,40,0.75)', borderRadius: 3, padding: [2, 5] },
          emphasis: {
            focus: 'adjacency',
            lineStyle: { width: 3 },
            label: { fontSize: 12 },
          },
          lineStyle: { color: '#64748b' },
          animation: true,
        },
      ],
    })

    const onResize = () => chart.resize()
    window.addEventListener('resize', onResize)
    return () => {
      window.removeEventListener('resize', onResize)
      chart.dispose()
      chartRef.current = null
    }
  }, [companyId, companyName, relations])

  return (
    <div className="graph-panel">
      <div className="graph-legend">
        {['股权', '对外投资', '担保', '共同法人', '共同股东'].map((t) => (
          <div key={t} className="lg-item" style={{ color: relationColor(t) }}>
            <span className={`lg-line ${t === '担保' ? 'dashed' : ''}`} />
            {t}
          </div>
        ))}
      </div>
      <div className="graph-tip">可拖拽节点 / 滚轮缩放 · 仅展示一跳直接关联</div>
      <div ref={containerRef} style={{ width: '100%', height }} />
    </div>
  )
}