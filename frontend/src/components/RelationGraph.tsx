import { useEffect, useRef, useState, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import * as echarts from 'echarts'
import type {
  InvestigationEdge,
  InvestigationNetworkResponse,
  InvestigationNode,
  NetworkEdge,
  Relation,
  RelationNetworkResponse,
} from '../api/types'
import { relationColor } from '../lib/presentation'

/**
 * 企业关系网络图（ECharts graph 系列）。
 *
 * V1.1.2: 修复拖拽问题，优化布局和配色，适配浅色背景。
 * V1.1.1: 修复 {b} 模板残留问题，优化配色和可读性。
 * V1.1: 支持完整多跳网络数据（从 /relation-network API）。
 * V1.0: 仅支持一跳关系数据（从 /relations API）。
 */

// ============================================================
// 节点接口
// ============================================================

interface GraphNode {
  id: string
  name: string
  symbolSize: number
  x?: number
  y?: number
  fixed?: boolean
  itemStyle: {
    color: string
    borderColor?: string
    borderWidth?: number
    shadowBlur?: number
    shadowColor?: string
    shadowOffsetX?: number
    shadowOffsetY?: number
  }
  label: {
    show: boolean
    formatter: (p: unknown) => string
    color: string
    fontSize?: number
    fontWeight?: string
    lineHeight?: number
    backgroundColor?: string
    borderRadius?: number
    padding?: number[]
    borderColor?: string
    borderWidth?: number
  }
  value: string
  companyName?: string
  industry?: string | null
  businessStatus?: string | null
  depth?: number
  riskLevel?: string
  riskTags?: string[]
  evidenceIds?: string[]
}

// ============================================================
// 颜色配置（浅色背景适配）
// ============================================================

const COLORS = {
  // 背景
  chartBg: '#f3f7fb',         // 图表区域背景：浅蓝灰

  // 节点颜色（深色系，与浅背景形成对比）
  root: '#1d4ed8',           // 根节点：深蓝色
  rootBorder: '#3b82f6',     // 根节点边框：中蓝色
  depth1: '#2563eb',         // 一级关联：蓝色
  depth1Border: '#60a5fa',   // 一级关联边框
  depth2: '#3b82f6',         // 二级关联：中蓝色
  depth2Border: '#93c5fd',   // 二级关联边框

  // 节点标签（深色背景上的白色文字）
  rootLabel: '#ffffff',
  nodeLabel: '#ffffff',
  nodeLabelBg: 'rgba(30,58,138,0.92)',  // 深蓝色半透明背景

  // 边标签（浅色背景适配）
  edgeLabel: '#1e293b',       // 深色文字
  edgeLabelBg: 'rgba(255,255,255,0.92)', // 半透明白色背景
  edgeLabelBorder: '#cbd5e1', // 浅灰色边框

  // 边颜色
  defaultEdge: '#94a3b8',
}

// ============================================================
// V1.6 调查网络专用颜色
// ============================================================

const INV_COLORS = {
  // 节点
  root: '#1d4ed8',
  rootBorder: '#3b82f6',
  investigated: '#0891b2',        // teal
  investigatedBorder: '#22d3ee',
  discovered: '#94a3b8',          // gray
  discoveredBorder: '#cbd5e1',
  notInvestigated: '#cbd5e1',     // faint gray
  notInvestigatedBorder: '#e2e8f0',
  supplementaryBorder: '#e8730c', // orange border for 补查

  // 边
  traversed: '#2563eb',           // thick blue
  discoveredEdge: '#94a3b8',      // normal gray
  notUsed: '#cbd5e1',             // thin faint

  // 标签
  nodeLabel: '#ffffff',
  nodeLabelBg: 'rgba(30,58,138,0.92)',
  dimLabel: '#64748b',
  dimLabelBg: 'rgba(255,255,255,0.85)',

  edgeLabel: '#1e293b',
  edgeLabelBg: 'rgba(255,255,255,0.92)',
  edgeLabelBorder: '#cbd5e1',
  dimEdgeLabel: '#94a3b8',
  dimEdgeLabelBg: 'rgba(245,247,251,0.8)',
  dimEdgeLabelBorder: '#e2e8f0',
}

// ============================================================
// 辅助函数
// ============================================================

/**
 * 截断过长的公司名称
 */
function truncateName(name: string, maxLen: number = 10): string {
  if (!name) return ''
  return name.length > maxLen ? name.slice(0, maxLen) + '...' : name
}

/**
 * 判断关系类型是否有方向性
 */
function isDirectedRelation(relationType: string | null | undefined): boolean {
  if (!relationType) return false
  // 有方向性的关系：股权、对外投资、担保
  return relationType.includes('股权') || 
         relationType.includes('投资') || 
         relationType.includes('担保')
}

/**
 * 格式化边标签（动作式）
 */
function formatEdgeLabel(edge: NetworkEdge): string {
  if (edge.relation_type) {
    // 股权比例
    if (edge.equity_ratio !== null && edge.equity_ratio !== undefined) {
      const percent = Math.round(edge.equity_ratio * 100)
      return `持股${percent}%`
    }
    // 金额
    if (edge.amount !== null && edge.amount !== undefined) {
      const amountStr =
        edge.amount >= 10000
          ? `${Math.round(edge.amount / 10000)}万`
          : `${edge.amount}`
      // 担保关系
      if (edge.relation_type.includes('担保')) {
        return `提供担保${amountStr}`
      }
      return `投资${amountStr}`
    }
    // 仅类型
    return edge.relation_type
  }
  return '关联'
}

/**
 * 获取节点颜色（根据深度）
 */
function getNodeColor(depth: number, isRoot: boolean): { fill: string; border: string } {
  if (isRoot) return { fill: COLORS.root, border: COLORS.rootBorder }
  if (depth === 1) return { fill: COLORS.depth1, border: COLORS.depth1Border }
  return { fill: COLORS.depth2, border: COLORS.depth2Border }
}

// ============================================================
// V1.6: 调查网络节点/边样式
// ============================================================

function getInvNodeStyle(node: InvestigationNode): {
  fill: string
  border: string
  borderWidth: number
  opacity: number
  symbolSize: number
} {
  const isRoot = node.is_root || node.investigation_status === 'root'
  const supp = node.supplementary

  if (isRoot) {
    return {
      fill: INV_COLORS.root,
      border: supp ? INV_COLORS.supplementaryBorder : INV_COLORS.rootBorder,
      borderWidth: supp ? 3 : 3,
      opacity: 1,
      symbolSize: 78,
    }
  }

  switch (node.investigation_status) {
    case 'investigated':
      return {
        fill: INV_COLORS.investigated,
        border: supp ? INV_COLORS.supplementaryBorder : INV_COLORS.investigatedBorder,
        borderWidth: supp ? 3 : 2,
        opacity: 1,
        symbolSize: 54,
      }
    case 'discovered':
      return {
        fill: INV_COLORS.discovered,
        border: supp ? INV_COLORS.supplementaryBorder : INV_COLORS.discoveredBorder,
        borderWidth: supp ? 3 : 2,
        opacity: 0.85,
        symbolSize: 44,
      }
    case 'not_investigated':
      return {
        fill: INV_COLORS.notInvestigated,
        border: supp ? INV_COLORS.supplementaryBorder : INV_COLORS.notInvestigatedBorder,
        borderWidth: supp ? 2 : 1,
        opacity: 0.45,
        symbolSize: 38,
      }
    default:
      return {
        fill: INV_COLORS.notInvestigated,
        border: INV_COLORS.notInvestigatedBorder,
        borderWidth: 1,
        opacity: 0.45,
        symbolSize: 38,
      }
  }
}

function getInvEdgeStyle(edge: InvestigationEdge): {
  color: string
  width: number
  type: 'solid' | 'dashed'
  opacity: number
} {
  if (edge.supplementary) {
    return {
      color: '#e8730c',
      width: edge.investigation_status === 'traversed' ? 3 : 2,
      type: edge.relation_type?.includes('担保') ? 'dashed' : 'solid',
      opacity: 0.9,
    }
  }

  switch (edge.investigation_status) {
    case 'traversed':
      return {
        color: INV_COLORS.traversed,
        width: 3.5,
        type: edge.relation_type?.includes('担保') ? 'dashed' : 'solid',
        opacity: 1,
      }
    case 'discovered':
      return {
        color: INV_COLORS.discoveredEdge,
        width: 2,
        type: 'solid',
        opacity: 0.7,
      }
    case 'not_used':
      return {
        color: INV_COLORS.notUsed,
        width: 1,
        type: 'solid',
        opacity: 0.35,
      }
    default:
      return {
        color: INV_COLORS.notUsed,
        width: 1,
        type: 'solid',
        opacity: 0.35,
      }
  }
}

// ============================================================
// 主组件
// ============================================================

export default function RelationGraph({
  companyId,
  companyName,
  relations,
  networkData,
  investigationData,
  height = 580,
  onNodeClick,
}: {
  companyId: string
  companyName: string
  relations?: Relation[]
  networkData?: RelationNetworkResponse
  investigationData?: InvestigationNetworkResponse
  height?: number
  onNodeClick?: (nodeId: string, evidenceIds: string[]) => void
}) {
  const containerRef = useRef<HTMLDivElement>(null)
  const chartRef = useRef<echarts.ECharts | null>(null)
  const [truncated, setTruncated] = useState(false)
  // 记录用户拖拽后的位置
  const draggedPositionsRef = useRef<Map<string, { x: number; y: number }>>(new Map())

  // 用于区分拖拽和点击
  const mouseDownRef = useRef<{ x: number; y: number; time: number } | null>(null)
  const isDraggingRef = useRef(false)
  const navigate = useNavigate()

  /**
   * 处理节点拖拽结束事件
   * 记录节点当前位置，防止 force layout 强行拉回
   */
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const handleDragEnd = useCallback((params: any) => {
    if (params?.data?.id && chartRef.current) {
      const chart = chartRef.current
      const option = chart.getOption() as any
      if (option?.series?.[0]?.data) {
        const seriesData = option.series[0].data
        const nodeData = seriesData.find((n: any) => n?.id === params.data.id)
        if (nodeData?.x !== undefined && nodeData?.y !== undefined) {
          draggedPositionsRef.current.set(params.data.id, {
            x: nodeData.x,
            y: nodeData.y,
          })
        }
      }
    }
  }, [])

  useEffect(() => {
    const el = containerRef.current
    if (!el) return
    const chart = echarts.init(el)
    chartRef.current = chart

    let nodes: GraphNode[] = []
    let edges: Array<{
      source: string
      target: string
      relationId?: string
      relationType?: string
      equityRatio?: number | null
      amount?: number | null
      investigationReason?: string | null
      symbol?: string[]
      symbolSize?: number
      label: {
        show: boolean
        formatter: string
        color: string
        backgroundColor: string
        borderRadius: number
        padding: number[]
        borderColor: string
        borderWidth: number
        rotate?: number
      }
      lineStyle: { color: string; width: number; type: 'solid' | 'dashed' }
    }> = []

    // ============================================================
    // V1.6: 最高优先 —— 调查网络数据（AI调查网络模式）
    // ============================================================
    if (investigationData && investigationData.nodes.length > 0) {
      setTruncated(false)

      // 构建节点
      const seenNodes = new Set<string>()
      for (const node of investigationData.nodes) {
        if (seenNodes.has(node.company_id)) continue
        seenNodes.add(node.company_id)

        const isRoot = node.is_root || node.investigation_status === 'root'
        const style = getInvNodeStyle(node)
        const draggedPos = draggedPositionsRef.current.get(node.company_id)

        // 是否显示证据 badge
        const showEvidenceBadge = node.evidence_count > 0
        const riskLevel = node.risk_level || '未评估'
        const riskTags = node.risk_tags || []

        nodes.push({
          id: node.company_id,
          name: node.company_name,
          symbolSize: style.symbolSize,
          x: draggedPos?.x,
          y: draggedPos?.y,
          fixed: draggedPos ? true : undefined,
          itemStyle: {
            color: style.fill,
            borderColor: style.border,
            borderWidth: style.borderWidth,
            shadowBlur: isRoot ? 12 : 6,
            shadowColor: isRoot ? 'rgba(29,78,216,0.35)' : 'rgba(37,99,235,0.15)',
            shadowOffsetX: 0,
            shadowOffsetY: 2,
          },
          label: {
            show: true,
            formatter: (p: unknown) => {
              const params = p as { data?: GraphNode }
              const data = params?.data
              const id = data?.id || node.company_id
              const name = data?.name || node.company_name
              const truncated = truncateName(name, isRoot ? 10 : 6)
              const badge = showEvidenceBadge ? ` 📎${node.evidence_count}` : ''
              // 风险等级标签
              const riskBadge = riskLevel !== '未评估' ? ` ⚠️${riskLevel}` : ''
              return `${id}\n${truncated}${riskBadge}${badge}`
            },
            color: node.investigation_status === 'not_investigated'
              ? INV_COLORS.dimLabel
              : isRoot
                ? INV_COLORS.nodeLabel
                : INV_COLORS.nodeLabel,
            fontSize: isRoot ? 12 : 10,
            fontWeight: isRoot ? 'bold' : 'normal',
            lineHeight: isRoot ? 16 : 13,
            backgroundColor: node.investigation_status === 'not_investigated'
              ? INV_COLORS.dimLabelBg
              : INV_COLORS.nodeLabelBg,
            borderRadius: 4,
            padding: [2, 4],
            borderColor: style.border,
            borderWidth: 1,
          },
          value: node.company_id,
          companyName: node.company_name,
          industry: node.industry,
          businessStatus: node.business_status,
          depth: node.depth,
          riskLevel: riskLevel,
          riskTags: riskTags,
          evidenceIds: node.evidence_ids,
        })
      }

      // 构建边
      for (const edge of investigationData.edges) {
        const edgeStyle = getInvEdgeStyle(edge)
        const isDim = edge.investigation_status === 'not_used'
        const hasDirection = isDirectedRelation(edge.relation_type)
        
        const formatInvEdgeLabel = (e: InvestigationEdge): string => {
          // 关系类型（动作式）
          let relationStr = ''
          if (e.relation_type) {
            if (e.amount !== null && e.amount !== undefined) {
              const s = e.amount >= 10000 ? `${Math.round(e.amount / 10000)}万` : `${e.amount}`
              if (e.relation_type.includes('担保')) {
                relationStr = `提供担保${s}`
              } else if (e.relation_type.includes('投资')) {
                relationStr = `投资${s}`
              } else if (e.equity_ratio !== null && e.equity_ratio !== undefined) {
                const percent = Math.round(e.equity_ratio * 100)
                relationStr = `持股${percent}%`
              } else {
                relationStr = e.relation_type
              }
            } else if (e.equity_ratio !== null && e.equity_ratio !== undefined) {
              const percent = Math.round(e.equity_ratio * 100)
              relationStr = `持股${percent}%`
            } else {
              relationStr = e.relation_type
            }
          } else {
            relationStr = '关联'
          }

          // 调查原因
          const reason = e.investigation_reason
          if (reason) {
            return `${relationStr}\n${reason}`
          }
          return relationStr
        }

        edges.push({
          source: edge.source,
          target: edge.target,
          relationId: edge.relation_id,
          relationType: edge.relation_type,
          equityRatio: edge.equity_ratio,
          amount: edge.amount,
          investigationReason: edge.investigation_reason,
          // 有方向性的关系添加箭头
          ...(hasDirection ? {
            symbol: ['none', 'arrow'],
            symbolSize: 8,
          } : {}),
          label: {
            show: !isDim,
            formatter: formatInvEdgeLabel(edge),
            color: isDim ? INV_COLORS.dimEdgeLabel : INV_COLORS.edgeLabel,
            backgroundColor: isDim ? INV_COLORS.dimEdgeLabelBg : INV_COLORS.edgeLabelBg,
            borderRadius: 4,
            padding: [3, 8],
            borderColor: isDim ? INV_COLORS.dimEdgeLabelBorder : INV_COLORS.edgeLabelBorder,
            borderWidth: 1,
            rotate: 0, // 保持水平
          },
          lineStyle: {
            color: edgeStyle.color,
            width: edgeStyle.width,
            type: edgeStyle.type,
          },
        })
      }
    }
    // ============================================================
    // 优先使用完整网络数据
    // ============================================================
    else if (networkData && networkData.nodes.length > 0) {
      setTruncated(networkData.truncated)

      // 构建节点
      const seenNodes = new Set<string>()
      for (const node of networkData.nodes) {
        if (seenNodes.has(node.company_id)) continue
        seenNodes.add(node.company_id)

        const isRoot = node.company_id === companyId
        const colors = getNodeColor(node.depth, isRoot)

        // 检查是否有用户拖拽后的位置
        const draggedPos = draggedPositionsRef.current.get(node.company_id)

        nodes.push({
          id: node.company_id,
          name: node.company_name,
          symbolSize: isRoot ? 65 : node.depth === 1 ? 48 : 36,
          x: draggedPos?.x,
          y: draggedPos?.y,
          fixed: draggedPos ? true : undefined,
          itemStyle: {
            color: colors.fill,
            borderColor: colors.border,
            borderWidth: isRoot ? 3 : 2,
            shadowBlur: isRoot ? 12 : 6,
            shadowColor: isRoot ? 'rgba(29,78,216,0.35)' : 'rgba(37,99,235,0.2)',
            shadowOffsetX: 0,
            shadowOffsetY: 2,
          },
          label: {
            show: true,
            formatter: (p: unknown) => {
              const params = p as { data?: GraphNode }
              const data = params?.data
              const id = data?.id || node.company_id
              const name = data?.name || node.company_name
              const truncated = truncateName(name, isRoot ? 12 : 8)
              return `${id}\n${truncated}`
            },
            color: isRoot ? COLORS.rootLabel : COLORS.nodeLabel,
            fontSize: isRoot ? 12 : 10,
            fontWeight: isRoot ? 'bold' : 'normal',
            lineHeight: isRoot ? 16 : 13,
            backgroundColor: COLORS.nodeLabelBg,
            borderRadius: 4,
            padding: [2, 4],
            borderColor: colors.border,
            borderWidth: 1,
          },
          value: node.company_id,
          companyName: node.company_name,
          industry: node.industry,
          businessStatus: node.business_status,
          depth: node.depth,
        })
      }

      // 构建边
      for (const edge of networkData.edges) {
        const color = relationColor(edge.relation_type)
        const isGuarantee = edge.relation_type?.includes('担保')
        const hasDirection = isDirectedRelation(edge.relation_type)

        edges.push({
          source: edge.source,
          target: edge.target,
          relationId: edge.relation_id,
          relationType: edge.relation_type,
          // 有方向性的关系添加箭头
          ...(hasDirection ? {
            symbol: ['none', 'arrow'],
            symbolSize: 8,
          } : {}),
          label: {
            show: true,
            formatter: formatEdgeLabel(edge),
            color: COLORS.edgeLabel,
            backgroundColor: COLORS.edgeLabelBg,
            borderRadius: 4,
            padding: [3, 8],
            borderColor: COLORS.edgeLabelBorder,
            borderWidth: 1,
            rotate: 0, // 保持水平
          },
          lineStyle: {
            color,
            width: isGuarantee ? 2.5 : 3,
            type: isGuarantee ? 'dashed' : 'solid',
          },
        })
      }
    }
    // ============================================================
    // 回退到一跳关系数据
    // ============================================================
    else if (relations && relations.length > 0) {
      setTruncated(false)

      const draggedPos = draggedPositionsRef.current.get(companyId)

      nodes = [
        {
          id: companyId,
          name: companyName,
          symbolSize: 65,
          x: draggedPos?.x,
          y: draggedPos?.y,
          fixed: draggedPos ? true : undefined,
          itemStyle: {
            color: COLORS.root,
            borderColor: COLORS.rootBorder,
            borderWidth: 3,
            shadowBlur: 12,
            shadowColor: 'rgba(29,78,216,0.35)',
            shadowOffsetX: 0,
            shadowOffsetY: 2,
          },
          label: {
            show: true,
            formatter: (p: unknown) => {
              const params = p as { data?: GraphNode }
              const data = params?.data
              const id = data?.id || companyId
              const name = data?.name || companyName
              const truncated = truncateName(name, 10)
              return `${id}\n${truncated}`
            },
            color: COLORS.rootLabel,
            fontSize: 12,
            fontWeight: 'bold',
            lineHeight: 16,
            backgroundColor: COLORS.nodeLabelBg,
            borderRadius: 4,
            padding: [2, 4],
            borderColor: COLORS.rootBorder,
            borderWidth: 1,
          },
          value: companyId,
          companyName,
        },
      ]

      const seen = new Set<string>([companyId])
      for (const r of relations) {
        const counter =
          r.from_company_id === companyId ? r.to_company_id : r.from_company_id
        const counterName =
          (r.from_company_id === companyId
            ? r.to_company_name
            : r.from_company_name) ?? counter

        if (!seen.has(counter)) {
          seen.add(counter)
          const colors = getNodeColor(1, false)
          const nodeDraggedPos = draggedPositionsRef.current.get(counter)

          nodes.push({
            id: counter,
            name: counterName,
            symbolSize: 48,
            x: nodeDraggedPos?.x,
            y: nodeDraggedPos?.y,
            fixed: nodeDraggedPos ? true : undefined,
            itemStyle: {
              color: colors.fill,
              borderColor: colors.border,
              borderWidth: 2,
              shadowBlur: 6,
              shadowColor: 'rgba(37,99,235,0.2)',
              shadowOffsetX: 0,
              shadowOffsetY: 2,
            },
            label: {
              show: true,
              formatter: (p: unknown) => {
                const params = p as { data?: GraphNode }
                const data = params?.data
                const id = data?.id || counter
                const name = data?.name || counterName
                const truncated = truncateName(name, 6)
                return `${id}\n${truncated}`
              },
              color: COLORS.nodeLabel,
              fontSize: 10,
              lineHeight: 13,
              backgroundColor: COLORS.nodeLabelBg,
              borderRadius: 4,
              padding: [2, 4],
              borderColor: colors.border,
              borderWidth: 1,
            },
            value: counter,
            companyName: counterName,
          })
        }

        const color = relationColor(r.relation_type)
        const isGuarantee = r.relation_type.includes('担保')
        const hasDirection = isDirectedRelation(r.relation_type)

        // 动作式标签
        let edgeLabel = r.relation_type
        if (r.amount !== null && r.amount !== undefined) {
          const amountStr = r.amount >= 10000 ? `${Math.round(r.amount / 10000)}万` : `${r.amount}`
          if (isGuarantee) {
            edgeLabel = `提供担保${amountStr}`
          } else if (r.relation_type.includes('投资')) {
            edgeLabel = `投资${amountStr}`
          } else if (r.equity_ratio !== null && r.equity_ratio !== undefined) {
            const percent = Math.round(r.equity_ratio * 100)
            edgeLabel = `持股${percent}%`
          }
        } else if (r.equity_ratio !== null && r.equity_ratio !== undefined) {
          const percent = Math.round(r.equity_ratio * 100)
          edgeLabel = `持股${percent}%`
        }

        edges.push({
          source: r.from_company_id,
          target: r.to_company_id,
          relationId: r.relation_id,
          relationType: r.relation_type,
          equityRatio: r.equity_ratio,
          amount: r.amount,
          // 有方向性的关系添加箭头
          ...(hasDirection ? {
            symbol: ['none', 'arrow'],
            symbolSize: 8,
          } : {}),
          label: {
            show: true,
            formatter: edgeLabel,
            color: COLORS.edgeLabel,
            backgroundColor: COLORS.edgeLabelBg,
            borderRadius: 4,
            padding: [3, 8],
            borderColor: COLORS.edgeLabelBorder,
            borderWidth: 1,
            rotate: 0, // 保持水平
          },
          lineStyle: {
            color,
            width: isGuarantee ? 2.5 : 3,
            type: isGuarantee ? 'dashed' : 'solid',
          },
        })
      }
    }

    // ============================================================
    // ECharts 配置
    // ============================================================
    chart.setOption({
      backgroundColor: COLORS.chartBg,
      tooltip: {
        trigger: 'item',
        backgroundColor: 'rgba(255,255,255,0.98)',
        borderColor: '#e2e8f0',
        textStyle: { color: '#1e293b', fontSize: 13 },
        extraCssText: 'box-shadow: 0 4px 20px rgba(0,0,0,0.12); border-radius: 8px;',
        formatter: (p: {
          dataType: string
          data: GraphNode
          value: string[]
        }) => {
          if (p.dataType === 'node') {
            const d = p.data
            const lines = [
              `<div style="font-weight:600;font-size:14px;color:#0f172a;margin-bottom:4px">${d.companyName || d.name}</div>`,
              `<div style="color:#64748b;font-size:12px">${d.id}</div>`,
            ]
            if (d.industry) lines.push(`<div style="color:#64748b;font-size:12px;margin-top:4px">行业: ${d.industry}</div>`)
            if (d.businessStatus) lines.push(`<div style="color:#64748b;font-size:12px">状态: ${d.businessStatus}</div>`)
            if (d.depth !== undefined && d.depth > 0) lines.push(`<div style="color:#2563eb;font-size:12px;margin-top:4px">距离: ${d.depth} 跳</div>`)
            // 风险信息
            if (d.riskLevel) lines.push(`<div style="color:#dc2626;font-size:12px;margin-top:4px">风险等级: ${d.riskLevel}</div>`)
            if (d.riskTags && d.riskTags.length > 0) lines.push(`<div style="color:#dc2626;font-size:12px">风险标签: ${d.riskTags.join('、')}</div>`)
            return lines.join('')
          }
          // 边 tooltip 显示详细关系信息
          const edgeData = p.data as any
          const relType = edgeData?.relationType ?? '关联关系'
          const relId = edgeData?.relationId ?? ''
          const equityRatio = edgeData?.equityRatio
          const amount = edgeData?.amount
          const investigationReason = edgeData?.investigationReason
          const badgeColor = relId.startsWith('R') ? '#0891b2' : '#64748b'
          
          // 构建关系说明
          let relationDesc = ''
          if (equityRatio !== null && equityRatio !== undefined) {
            const percent = Math.round(equityRatio * 100)
            relationDesc = `持股${percent}%`
          } else if (amount !== null && amount !== undefined) {
            const amountStr = amount >= 10000 ? `${Math.round(amount / 10000)}万` : `${amount}`
            if (relType.includes('担保')) {
              relationDesc = `提供担保${amountStr}`
            } else {
              relationDesc = `投资${amountStr}`
            }
          } else {
            relationDesc = relType
          }
          
          const lines = [
            `<div style="font-weight:600;font-size:13px;color:#0f172a;margin-bottom:8px">关系详情</div>`,
            `<div style="display:flex;gap:8px;margin-bottom:4px"><span style="color:#64748b;font-size:12px;min-width:60px">起点:</span><span style="font-size:12px">${p.value[0]}</span></div>`,
            `<div style="display:flex;gap:8px;margin-bottom:4px"><span style="color:#64748b;font-size:12px;min-width:60px">终点:</span><span style="font-size:12px">${p.value[1]}</span></div>`,
            `<div style="display:flex;gap:8px;margin-bottom:4px"><span style="color:#64748b;font-size:12px;min-width:60px">类型:</span><span style="font-size:12px">${relType}</span></div>`,
            `<div style="display:flex;gap:8px;margin-bottom:8px"><span style="color:#64748b;font-size:12px;min-width:60px">说明:</span><span style="font-size:12px">${relationDesc}</span></div>`,
          ]
          
          if (investigationReason) {
            lines.push(`<div style="padding:6px 8px;background:#f0f9ff;border-radius:4px;font-size:11px;color:#0369a1">💡 调查原因: ${investigationReason}</div>`)
          }
          
          if (relId) {
            lines.push(`<div style="margin-top:8px"><span style="display:inline-block;font-family:monospace;font-size:11px;font-weight:600;color:${badgeColor};background:${badgeColor}18;padding:1px 6px;border-radius:3px">${relId}</span></div>`)
          }
          
          return lines.join('')
        },
      },
      series: [
        {
          type: 'graph',
          layout: 'force',
          data: nodes,
          links: edges,
          roam: true,
          draggable: true,
          force: {
            repulsion: 1200,
            edgeLength: [300, 500],
            gravity: 0.03,
            friction: 0.4,
            layoutAnimation: true,
          },
          // 节点标签
          label: {
            show: true,
            fontSize: 11,
            lineHeight: 14,
            backgroundColor: COLORS.nodeLabelBg,
            borderRadius: 4,
            padding: [2, 4],
            borderColor: 'rgba(148,163,184,0.3)',
            borderWidth: 1,
            rotate: 0,
            formatter: (p: { data: GraphNode }) => {
              const data = p.data
              const id = data?.id || ''
              const name = data?.name || ''
              const truncated = truncateName(name, 8)
              return `${id}\n${truncated}`
            },
          },
          // 边标签
          edgeLabel: {
            show: true,
            fontSize: 11,
            fontWeight: 'bold',
            backgroundColor: COLORS.edgeLabelBg,
            borderRadius: 4,
            padding: [3, 8],
            borderColor: COLORS.edgeLabelBorder,
            borderWidth: 1,
            color: COLORS.edgeLabel,
            rotate: 0, // 保持水平
          },
          // 高亮效果
          emphasis: {
            focus: 'adjacency',
            lineStyle: { width: 4 },
            label: { fontSize: 14 },
          },
          // 默认边样式
          lineStyle: {
            color: COLORS.defaultEdge,
            curveness: 0.1,
          },
          animation: true,
          animationDuration: 1000,
          animationEasingUpdate: 'quinticInOut',
        },
      ],
    })

    // ============================================================
    // 绑定拖拽结束事件（使用 any 类型避免类型错误）
    // ============================================================
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    chart.on('graphNodesDragged', handleDragEnd as any)

    // ============================================================
    // 拖拽/点击区分逻辑
    // ============================================================
    const DRAG_THRESHOLD = 6 // 拖拽距离阈值（像素）

    const handleMouseDown = (e: MouseEvent) => {
      mouseDownRef.current = {
        x: e.clientX,
        y: e.clientY,
        time: Date.now(),
      }
      isDraggingRef.current = false
    }

    const handleMouseMove = (e: MouseEvent) => {
      if (!mouseDownRef.current) return
      const dx = e.clientX - mouseDownRef.current.x
      const dy = e.clientY - mouseDownRef.current.y
      if (Math.abs(dx) > DRAG_THRESHOLD || Math.abs(dy) > DRAG_THRESHOLD) {
        isDraggingRef.current = true
      }
    }

    const handleMouseUp = () => {
      mouseDownRef.current = null
      // 延迟重置 isDragging，让 click 事件能读取到状态
      setTimeout(() => {
        isDraggingRef.current = false
      }, 50)
    }

    // 绑定鼠标事件
    el.addEventListener('mousedown', handleMouseDown)
    el.addEventListener('mousemove', handleMouseMove)
    el.addEventListener('mouseup', handleMouseUp)

    // ============================================================
    // 节点点击事件：进入企业详情
    // ============================================================
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    chart.on('click', (params: any) => {
      // 只处理节点点击
      if (params.dataType !== 'node') return

      // 如果是拖拽操作，不触发导航
      if (isDraggingRef.current) return

      const nodeId = params.data?.id
      if (!nodeId) return

      // 当前企业节点不跳转
      if (nodeId === companyId) return

      // 如果在调查网络模式且有 onNodeClick 回调，打开证据面板
      if (investigationData && onNodeClick) {
        const evidenceIds = params.data?.evidenceIds || []
        onNodeClick(nodeId, evidenceIds)
        return
      }

      // 导航到企业详情页
      navigate(`/company/${nodeId}`)
    })

    // ============================================================
    // 事件处理
    // ============================================================
    const onResize = () => chart.resize()
    window.addEventListener('resize', onResize)
    return () => {
      window.removeEventListener('resize', onResize)
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      chart.off('graphNodesDragged', handleDragEnd as any)
      // 移除鼠标事件监听
      el.removeEventListener('mousedown', handleMouseDown)
      el.removeEventListener('mousemove', handleMouseMove)
      el.removeEventListener('mouseup', handleMouseUp)
      chart.dispose()
      chartRef.current = null
    }
  }, [companyId, companyName, relations, networkData, investigationData, handleDragEnd, navigate])

  const nodeCount = networkData?.nodes.length ?? relations?.length ?? 0
  const edgeCount = networkData?.edges.length ?? relations?.length ?? 0

  return (
    <div className="graph-panel" style={{ backgroundColor: COLORS.chartBg }}>
      {/* 图例 */}
      <div className="graph-legend">
        <div className="legend-section">
          <span className="legend-label">节点类型：</span>
          <div className="lg-item">
            <span className="lg-dot" style={{ backgroundColor: COLORS.root, width: 12, height: 12 }} />
            当前企业
          </div>
          <div className="lg-item">
            <span className="lg-dot" style={{ backgroundColor: COLORS.depth1, width: 10, height: 10 }} />
            关联企业
          </div>
        </div>
        <div className="legend-divider" />
        <div className="legend-section">
          <span className="legend-label">关系类型：</span>
          {['股权', '对外投资', '担保', '共同法人', '共同股东'].map((t) => (
            <div key={t} className="lg-item" style={{ color: relationColor(t) }}>
              <span className={`lg-line ${t === '担保' ? 'dashed' : ''}`} style={{ borderColor: relationColor(t) }} />
              {t}
            </div>
          ))}
        </div>
      </div>

      {/* 提示信息 */}
      <div className="graph-tip">
        <span>🖱️ 拖拽节点 · 滚轮缩放 · 双击居中 · 单击节点进入企业详情</span>
        <span className="graph-stat">共 {nodeCount} 个节点 / {edgeCount} 条关系</span>
        {truncated && (
          <span className="graph-truncated">
            网络较大，已截断
          </span>
        )}
      </div>

      {/* 图表容器 */}
      <div ref={containerRef} style={{ width: '100%', height }} />
    </div>
  )
}
