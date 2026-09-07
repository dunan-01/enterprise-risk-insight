import { useCallback, useEffect, useState } from 'react'
import { api, ApiError } from '../../api/client'
import type { PublicOpinionEvent } from '../../api/types'
import { EvidenceTag } from '../../components/Badges'
import { EmptyState, ErrorBlock, LoadingState } from '../../components/States'
import { fmtDate } from '../../lib/format'

/** 舆情事件标签颜色 */
function SentimentTag({ raw }: { raw: string | null }) {
  if (!raw) return <span className="tag tone-muted">-</span>
  const colorMap: Record<string, string> = {
    positive: '#10b981',
    neutral: '#6b7280',
    negative: '#ef4444',
  }
  const labelMap: Record<string, string> = {
    positive: '正面',
    neutral: '中性',
    negative: '负面',
  }
  return (
    <span
      className="tag"
      style={{
        background: `${colorMap[raw] ?? '#6b7280'}18`,
        color: colorMap[raw] ?? '#6b7280',
        border: `1px solid ${colorMap[raw] ?? '#6b7280'}40`,
      }}
    >
      {labelMap[raw] ?? raw}
    </span>
  )
}

/** 核实状态标签颜色 */
function VerificationStatusTag({ raw }: { raw: string | null }) {
  if (!raw) return <span className="tag tone-muted">-</span>
  const colorMap: Record<string, string> = {
    verified: '#10b981',
    partially_verified: '#f59e0b',
    unverified: '#ef4444',
  }
  const labelMap: Record<string, string> = {
    verified: '已核实',
    partially_verified: '部分核实',
    unverified: '未核实',
  }
  return (
    <span
      className="tag"
      style={{
        background: `${colorMap[raw] ?? '#6b7280'}18`,
        color: colorMap[raw] ?? '#6b7280',
        border: `1px solid ${colorMap[raw] ?? '#6b7280'}40`,
      }}
    >
      {labelMap[raw] ?? raw}
    </span>
  )
}

/** 舆情信息 Tab */
export default function PublicOpinionTab({
  companyId,
  onEvidenceClick,
}: {
  companyId: string
  onEvidenceClick?: (id: string) => void
}) {
  const [state, setState] = useState<'loading' | 'done' | 'error'>('loading')
  const [error, setError] = useState<ApiError | null>(null)
  const [events, setEvents] = useState<PublicOpinionEvent[]>([])

  const load = useCallback(async () => {
    setState('loading')
    setError(null)
    try {
      const res = await api.publicOpinion(companyId)
      setEvents(res.items)
      setState('done')
    } catch (e) {
      setError(e as ApiError)
      setState('error')
    }
  }, [companyId])

  useEffect(() => {
    void load()
  }, [load])

  const negativeCount = events.filter((e) => e.sentiment === 'negative').length

  return (
    <div className="card">
      <div className="card-head">
        <h2>舆情信息</h2>
        <span className="hint">
          媒体报道 / 舆情监测 · GET /api/companies/{companyId}/public-opinion
        </span>
      </div>

      {state === 'loading' && <LoadingState text="舆情信息加载中…" />}

      {state === 'error' && (
        <div className="card-body">
          <ErrorBlock
            title="舆情信息加载失败"
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
              共 <b>{events.length}</b> 条舆情事件
            </span>
            {negativeCount > 0 && (
              <span style={{ color: '#ef4444' }}>
                ▲ <b>{negativeCount}</b> 条负面舆情
              </span>
            )}
          </div>
          {events.length === 0 ? (
            <EmptyState title="暂无舆情信息" desc="该企业目前没有舆情监测记录。" />
          ) : (
            <div className="table-wrap">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>发布日期</th>
                    <th>标题</th>
                    <th>主题</th>
                    <th>情感倾向</th>
                    <th>核实状态</th>
                    <th>来源</th>
                    <th>Evidence</th>
                  </tr>
                </thead>
                <tbody>
                  {events.map((ev) => (
                    <tr
                      key={ev.event_id}
                      className={ev.sentiment === 'negative' ? 'row-emphasis' : undefined}
                    >
                      <td className="mono muted">{fmtDate(ev.publish_date)}</td>
                      <td style={{ maxWidth: 260 }}>{ev.title ?? '-'}</td>
                      <td>{ev.topic ?? '-'}</td>
                      <td>
                        <SentimentTag raw={ev.sentiment} />
                      </td>
                      <td>
                        <VerificationStatusTag raw={ev.verification_status} />
                      </td>
                      <td className="muted">
                        {ev.source_name ?? ev.source_type ?? '-'}
                      </td>
                      <td>
                        <EvidenceTag id={ev.event_id} onClick={onEvidenceClick} />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}
    </div>
  )
}
