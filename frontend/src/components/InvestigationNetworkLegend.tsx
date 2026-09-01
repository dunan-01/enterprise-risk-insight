/**
 * InvestigationNetworkLegend — 调查网络图例组件（V2.0）
 *
 * 展示调查网络的节点/边含义、统计摘要和调查路径。
 */

import type { InvestigationNetworkStats, InvestigationNode } from '../api/types'

/** 节点状态配色 */
const NODE_COLORS = {
  root: '#1d4ed8',
  investigated: '#0891b2',
  discovered: '#94a3b8',
  not_investigated: '#cbd5e1',
}

export default function InvestigationNetworkLegend({
  stats,
  nodes,
}: {
  stats: InvestigationNetworkStats
  nodes?: InvestigationNode[]
}) {
  // 按调查顺序排序节点
  const sortedNodes = nodes
    ?.filter(n => n.investigation_status === 'root' || n.investigation_status === 'investigated')
    .sort((a, b) => {
      if (a.investigation_status === 'root') return -1
      if (b.investigation_status === 'root') return 1
      return (a.investigation_order || 0) - (b.investigation_order || 0)
    }) || []

  return (
    <div className="inv-legend">
      <div className="inv-legend-section">
        <span className="inv-legend-label">节点状态：</span>
        <div className="inv-legend-item">
          <span
            className="inv-legend-dot"
            style={{ backgroundColor: NODE_COLORS.root }}
          />
          目标企业
        </div>
        <div className="inv-legend-item">
          <span
            className="inv-legend-dot"
            style={{ backgroundColor: NODE_COLORS.investigated }}
          />
          已调查
        </div>
        <div className="inv-legend-item">
          <span
            className="inv-legend-dot inv-legend-dot-hollow"
            style={{ borderColor: NODE_COLORS.discovered }}
          />
          已发现
        </div>
        <div className="inv-legend-item">
          <span
            className="inv-legend-dot inv-legend-dot-faint"
            style={{ backgroundColor: NODE_COLORS.not_investigated }}
          />
          未调查
        </div>
      </div>
      <div className="inv-legend-divider" />
      <div className="inv-legend-section">
        <span className="inv-legend-label">边类型：</span>
        <div className="inv-legend-item">
          <span className="inv-legend-line inv-legend-line-thick" style={{ background: '#2563eb' }} />
          实际调查路径
        </div>
        <div className="inv-legend-item">
          <span className="inv-legend-line" style={{ background: '#94a3b8' }} />
          其他关系
        </div>
        <div className="inv-legend-item">
          <span
            className="inv-legend-dot"
            style={{ border: '2px solid #e8730c', backgroundColor: '#fff', width: 10, height: 10 }}
          />
          补查节点
        </div>
      </div>
      <div className="inv-legend-divider" />
      <div className="inv-legend-stats">
        <span>完整网络 <b>{stats.total_network_nodes}</b> 家</span>
        <span>实际调查 <b>{stats.investigated_nodes}</b> 家</span>
        <span>发现未查 <b>{stats.discovered_nodes}</b> 家</span>
        <span>调查关系 <b>{stats.investigated_edges}</b> 条</span>
        <span>Evidence <b>{stats.total_evidence}</b> 条</span>
      </div>

      {/* V2.0: 调查路径展示 */}
      {sortedNodes.length > 1 && (
        <div className="inv-legend-divider" />
      )}
      {sortedNodes.length > 1 && (
        <div className="inv-legend-section" style={{ flexDirection: 'column', alignItems: 'flex-start', gap: 8 }}>
          <span className="inv-legend-label">调查路径：</span>
          <div style={{ 
            display: 'flex', 
            flexDirection: 'column', 
            gap: 4,
            paddingLeft: 12,
            borderLeft: '2px solid #e2e8f0',
            marginLeft: 4,
          }}>
            {sortedNodes.map((node, idx) => (
              <div key={node.company_id} style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <span
                  style={{
                    width: 24,
                    height: 24,
                    borderRadius: '50%',
                    backgroundColor: node.is_root ? NODE_COLORS.root : NODE_COLORS.investigated,
                    color: '#fff',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    fontSize: 11,
                    fontWeight: 600,
                    flexShrink: 0,
                  }}
                >
                  {node.investigation_order || 0}
                </span>
                <span style={{ fontSize: 12, color: '#1e293b', fontWeight: node.is_root ? 600 : 400 }}>
                  {node.company_id}
                </span>
                <span style={{ fontSize: 11, color: '#64748b' }}>
                  {node.company_name}
                </span>
                {node.evidence_count > 0 && (
                  <span style={{ 
                    fontSize: 10, 
                    color: '#0891b2', 
                    backgroundColor: '#cffafe',
                    padding: '1px 6px',
                    borderRadius: 4,
                  }}>
                    📎{node.evidence_count}
                  </span>
                )}
                {idx < sortedNodes.length - 1 && (
                  <span style={{ color: '#94a3b8', marginLeft: 4 }}>↓</span>
                )}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
