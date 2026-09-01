import { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api, ApiError } from '../../api/client'
import type {
  InvestigationNetworkResponse,
  Relation,
  RelationNetworkResponse,
} from '../../api/types'
import { RelationTypeTag } from '../../components/Badges'
import EvidenceDetailDrawer from '../../components/EvidenceDetailDrawer'
import EvidenceDetailPanel from '../../components/EvidenceDetailPanel'
import InvestigationNetworkLegend from '../../components/InvestigationNetworkLegend'
import RelationGraph from '../../components/RelationGraph'
import { EmptyState, ErrorBlock, LoadingState } from '../../components/States'
import { fmtDate, fmtMoney, fmtPercent } from '../../lib/format'

/** 关联关系 Tab：一跳关联关系表 + 完整关系网络图（多跳 BFS） + AI调查网络（V1.6） */
export default function RelationsTab({
  companyId,
  companyName,
}: {
  companyId: string
  companyName: string
}) {
  const [state, setState] = useState<'loading' | 'done' | 'error'>('loading')
  const [error, setError] = useState<ApiError | null>(null)
  const [relations, setRelations] = useState<Relation[]>([])
  const [networkData, setNetworkData] = useState<RelationNetworkResponse | null>(
    null,
  )
  const [drawerEvidenceId, setDrawerEvidenceId] = useState<string | null>(null)

  // V1.6: 调查网络模式
  const [viewMode, setViewMode] = useState<'complete' | 'investigation'>('complete')
  const [investigationData, setInvestigationData] = useState<InvestigationNetworkResponse | null>(null)
  const [investigationLoading, setInvestigationLoading] = useState(false)
  const [investigationError, setInvestigationError] = useState<string | null>(null)
  const [completedTaskId, setCompletedTaskId] = useState<string | null>(null)

  // V2.0: 节点证据面板
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null)
  const [selectedNodeEvidenceIds, setSelectedNodeEvidenceIds] = useState<string[]>([])

  const load = useCallback(async () => {
    setState('loading')
    setError(null)
    try {
      // 并行加载一跳关系、完整网络、以及检查是否有已完成的分析任务
      const [relRes, netRes, activeTask] = await Promise.all([
        api.relations(companyId),
        api.relationNetwork(companyId),
        api.getCompanyActiveTask(companyId),
      ])
      setRelations(relRes.items)
      setNetworkData(netRes)

      // 检查已完成的任务（用于调查网络）
      if (activeTask && (activeTask.status === 'completed')) {
        setCompletedTaskId(activeTask.task_id)
      } else if (activeTask && (activeTask.status === 'queued' || activeTask.status === 'running')) {
        // 有活跃任务但未完成，也记录 taskId 以便后续查询
        setCompletedTaskId(activeTask.task_id)
      } else {
        // 没有活跃任务，尝试加载历史分析结果获取 task_id
        try {
          const latestAnalysis = await api.latestAnalysis(companyId)
          if (latestAnalysis?.task_id) {
            setCompletedTaskId(latestAnalysis.task_id)
          }
        } catch {
          // 历史分析不存在，忽略错误
        }
      }

      setState('done')
    } catch (e) {
      setError(e as ApiError)
      setState('error')
    }
  }, [companyId])

  useEffect(() => {
    void load()
  }, [load])

  /** 加载调查网络数据 */
  const loadInvestigationNetwork = useCallback(async (taskId: string | null) => {
    setInvestigationLoading(true)
    setInvestigationError(null)
    try {
      let data: InvestigationNetworkResponse
      if (taskId) {
        // 有 task_id，使用任务调查网络 API
        data = await api.getInvestigationNetwork(taskId)
      } else {
        // 没有 task_id，尝试从 session_events.jsonl 加载历史分析
        data = await api.getCompanyInvestigationNetwork(companyId)
      }
      setInvestigationData(data)
    } catch (e) {
      const err = e as ApiError
      setInvestigationError(err.message ?? '加载调查网络失败')
      setInvestigationData(null)
    } finally {
      setInvestigationLoading(false)
    }
  }, [companyId])

  // 当切换到调查模式时自动加载
  useEffect(() => {
    if (viewMode === 'investigation' && !investigationData) {
      void loadInvestigationNetwork(completedTaskId)
    }
  }, [viewMode, completedTaskId, investigationData, loadInvestigationNetwork])

  const counterpart = (
    r: Relation,
  ): { id: string; name: string; direction: string } => {
    if (r.from_company_id === companyId) {
      return {
        id: r.to_company_id,
        name: r.to_company_name ?? r.to_company_id,
        direction: '本企业 → 对方',
      }
    }
    return {
      id: r.from_company_id,
      name: r.from_company_name ?? r.from_company_id,
      direction: '对方 → 本企业',
    }
  }

  // V2.0: 处理节点点击，打开证据面板
  const handleNodeClick = (nodeId: string, evidenceIds: string[]) => {
    setSelectedNodeId(nodeId)
    setSelectedNodeEvidenceIds(evidenceIds)
  }

  // 获取节点企业名称
  const getNodeName = (nodeId: string): string => {
    if (nodeId === companyId) return companyName
    const node = investigationData?.nodes.find(n => n.company_id === nodeId)
    return node?.company_name || nodeId
  }

  return (
    <>
      <div className="card">
        <div className="card-head">
          <h2>关联关系</h2>
          <span className="hint">
            一跳直接关联（股权 / 投资 / 担保 / 共同法人 / 共同等）· GET
            /api/companies/{companyId}/relations
          </span>
        </div>

        {state === 'loading' && <LoadingState text="关联关系加载中…" />}

        {state === 'error' && (
          <div className="card-body">
            <ErrorBlock
              title="关联关系加载失败"
              message={error?.message ?? '未知错误'}
              code={error?.code}
              onRetry={() => void load()}
            />
          </div>
        )}

        {state === 'done' && (
          <>
            <div className="stat-bar">
              <span>
                共 <b>{relations.length}</b> 条关联关系
              </span>
              <span>
                数据说明：equity_ratio 为 0-1 小数，页面已转换为百分比展示
              </span>
            </div>
            {relations.length === 0 ? (
              <EmptyState
                title="暂无关联关系"
                desc="该企业目前没有一跳直接关联企业。"
              />
            ) : (
              <div className="table-wrap">
                <table className="data-table">
                  <thead>
                    <tr>
                      <th>关联企业</th>
                      <th>关系方向</th>
                      <th>关系类型</th>
                      <th>股权比例</th>
                      <th>涉及金额</th>
                      <th>状态</th>
                      <th>证据</th>
                      <th>起始日期</th>
                    </tr>
                  </thead>
                  <tbody>
                    {relations.map((r) => {
                      const cp = counterpart(r)
                      return (
                        <tr key={r.relation_id}>
                          <td style={{ minWidth: 180 }}>
                            <Link
                              to={`/company/${cp.id}`}
                              className="company-link"
                            >
                              <span className="company-link-name">{cp.name}</span>
                              <span className="company-link-id">{cp.id}</span>
                              <span className="company-link-arrow">→</span>
                            </Link>
                          </td>
                          <td
                            className="muted"
                            style={{ whiteSpace: 'nowrap' }}
                          >
                            {cp.direction}
                          </td>
                          <td>
                            <RelationTypeTag raw={r.relation_type} />
                          </td>
                          <td className="num" style={{ fontWeight: 600 }}>
                            {fmtPercent(r.equity_ratio)}
                          </td>
                          <td className="num">{fmtMoney(r.amount)}</td>
                          <td>{r.status ?? '-'}</td>
                          <td>
                            <span
                              className="ev-badge ev-badge-relation"
                              onClick={() => setDrawerEvidenceId(r.relation_id)}
                              title="查看原始事实"
                              style={{ cursor: 'pointer' }}
                            >
                              {r.relation_id}
                            </span>
                          </td>
                          <td className="mono muted">
                            {fmtDate(r.start_date)}
                          </td>
                        </tr>
                      )
                    })}
                  </tbody>
                </table>
              </div>
            )}
          </>
        )}
      </div>

      {/* 关系网络图 */}
      {state === 'done' && relations.length > 0 && (
        <div className="card">
          <div className="card-head">
            <h2>企业关系网络图</h2>
            <span className="hint">
              中心节点 = 当前企业 · 外围 = 关联企业 · 共{' '}
              {networkData?.nodes.length ?? 0} 个节点 /{' '}
              {networkData?.edges.length ?? 0} 条关系
              {networkData?.truncated && (
                <span style={{ color: '#f59e0b' }}>（网络较大，已截断）</span>
              )}
            </span>
          </div>

          {/* V1.6: 模式切换 */}
          <div style={{ padding: '12px 18px 0', display: 'flex', gap: 8 }}>
            <button
              className={viewMode === 'complete' ? 'btn btn-primary' : 'btn btn-ghost'}
              style={{ padding: '6px 16px', fontSize: 13 }}
              onClick={() => setViewMode('complete')}
            >
              完整关系网络
            </button>
            <button
              className={viewMode === 'investigation' ? 'btn btn-primary' : 'btn btn-ghost'}
              style={{ padding: '6px 16px', fontSize: 13 }}
              onClick={() => setViewMode('investigation')}
            >
              AI 调查网络
            </button>
          </div>

          <div className="card-body">
            {/* 调查网络加载中 */}
            {viewMode === 'investigation' && investigationLoading && (
              <div style={{ textAlign: 'center', padding: '32px 0' }}>
                <div style={{ display: 'inline-flex', alignItems: 'center', gap: 12 }}>
                  <span className="spinner" />
                  <span style={{ fontSize: 14, color: 'var(--text-3)' }}>
                    正在加载 AI 调查网络数据…
                  </span>
                </div>
              </div>
            )}

            {/* 调查网络错误 */}
            {viewMode === 'investigation' && investigationError && (
              <div className="note warn" style={{ marginBottom: 12 }}>
                <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <circle cx="12" cy="12" r="10" />
                  <line x1="12" y1="8" x2="12" y2="12" />
                  <line x1="12" y1="16" x2="12.01" y2="16" />
                </svg>
                {investigationError}
              </div>
            )}

            {/* 调查网络无数据提示 */}
            {viewMode === 'investigation' && !investigationLoading && !investigationError && !investigationData && (
              <div style={{ textAlign: 'center', padding: '32px 0', color: 'var(--text-3)' }}>
                <div style={{ fontSize: 14, marginBottom: 8 }}>
                  尚未执行 AI 风险调查
                </div>
                <div style={{ fontSize: 12, color: 'var(--text-3)' }}>
                  切换到「AI 风险洞察」Tab 启动分析后，此处将显示调查路径网络
                </div>
              </div>
            )}

            {/* V1.6: 调查网络图例 + 统计摘要 */}
            {viewMode === 'investigation' && investigationData && investigationData.stats && (
              <InvestigationNetworkLegend stats={investigationData.stats} nodes={investigationData.nodes} />
            )}

            {/* 关系图 */}
            <RelationGraph
              companyId={companyId}
              companyName={companyName}
              relations={relations}
              networkData={viewMode === 'complete' ? (networkData ?? undefined) : undefined}
              investigationData={viewMode === 'investigation' ? (investigationData ?? undefined) : undefined}
              onNodeClick={viewMode === 'investigation' ? handleNodeClick : undefined}
            />
          </div>
        </div>
      )}

      {/* Evidence Detail Drawer */}
      <EvidenceDetailDrawer
        evidenceId={drawerEvidenceId}
        onClose={() => setDrawerEvidenceId(null)}
      />

      {/* V2.0: 节点证据面板 */}
      {selectedNodeId && (
        <EvidenceDetailPanel
          companyId={selectedNodeId}
          companyName={getNodeName(selectedNodeId)}
          evidenceIds={selectedNodeEvidenceIds}
          onClose={() => {
            setSelectedNodeId(null)
            setSelectedNodeEvidenceIds([])
          }}
        />
      )}
    </>
  )
}
