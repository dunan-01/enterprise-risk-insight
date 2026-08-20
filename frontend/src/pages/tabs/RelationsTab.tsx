import { useCallback, useEffect, useState } from 'react'
import { api, ApiError } from '../../api/client'
import type { Relation, RelationNetworkResponse } from '../../api/types'
import { RelationTypeTag } from '../../components/Badges'
import RelationGraph from '../../components/RelationGraph'
import { EmptyState, ErrorBlock, LoadingState } from '../../components/States'
import { fmtDate, fmtMoney, fmtPercent } from '../../lib/format'

/** 关联关系 Tab：一跳关联关系表 + 完整关系网络图（多跳 BFS） */
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

  const load = useCallback(async () => {
    setState('loading')
    setError(null)
    try {
      // 并行加载一跳关系和完整网络
      const [relRes, netRes] = await Promise.all([
        api.relations(companyId),
        api.relationNetwork(companyId),
      ])
      setRelations(relRes.items)
      setNetworkData(netRes)
      setState('done')
    } catch (e) {
      setError(e as ApiError)
      setState('error')
    }
  }, [companyId])

  useEffect(() => {
    void load()
  }, [load])

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

  return (
    <>
      <div className="card">
        <div className="card-head">
          <h2>关联关系</h2>
          <span className="hint">
            一跳直接关联（股权 / 投资 / 担保 / 共同法人 / 共同股东等）· GET
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
                      <th>详情</th>
                      <th>起始日期</th>
                    </tr>
                  </thead>
                  <tbody>
                    {relations.map((r) => {
                      const cp = counterpart(r)
                      return (
                        <tr key={r.relation_id}>
                          <td style={{ minWidth: 180 }}>
                            <b>{cp.name}</b>
                            <div
                              className="mono muted"
                              style={{ fontSize: 12 }}
                            >
                              {cp.id}
                            </div>
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
                          <td style={{ maxWidth: 280 }}>
                            {r.relation_detail ?? '-'}
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
          <div className="card-body">
            <RelationGraph
              companyId={companyId}
              companyName={companyName}
              relations={relations}
              networkData={networkData ?? undefined}
            />
          </div>
        </div>
      )}
    </>
  )
}
