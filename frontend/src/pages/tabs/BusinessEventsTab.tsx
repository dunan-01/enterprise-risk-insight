import { useCallback, useEffect, useState } from 'react'
import { api, ApiError } from '../../api/client'
import type { BusinessEvent } from '../../api/types'
import { EventTypeTag } from '../../components/Badges'
import { EmptyState, ErrorBlock, LoadingState } from '../../components/States'
import { fmtDate, fmtMoney } from '../../lib/format'
import { isEmphasizedEvent } from '../../lib/presentation'

/** 工商动态 Tab：经营/工商事件表格，行政处罚、经营异常等做视觉强调 */
export default function BusinessEventsTab({ companyId }: { companyId: string }) {
  const [state, setState] = useState<'loading' | 'done' | 'error'>('loading')
  const [error, setError] = useState<ApiError | null>(null)
  const [events, setEvents] = useState<BusinessEvent[]>([])

  const load = useCallback(async () => {
    setState('loading')
    setError(null)
    try {
      const res = await api.businessEvents(companyId)
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

  return (
    <div className="card">
      <div className="card-head">
        <h2>工商动态</h2>
        <span className="hint">经营异常 / 行政处罚 / 变更记录等 · GET /api/companies/{companyId}/business-events</span>
      </div>

      {state === 'loading' && <LoadingState text="工商动态加载中…" />}

      {state === 'error' && (
        <div className="card-body">
          <ErrorBlock
            title="工商动态加载失败"
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
              共 <b>{events.length}</b> 条工商动态事件
            </span>
            {events.some((e) => e.event_type.includes('经营异常') || e.event_type.includes('行政处罚')) && (
              <span style={{ color: 'var(--risk-mid)' }}>▲ 含经营异常 / 行政处罚记录</span>
            )}
          </div>
          {events.length === 0 ? (
            <EmptyState title="暂无工商动态" desc="该企业目前没有经营与工商变更事件记录。" />
          ) : (
            <div className="table-wrap">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>事件类型</th>
                    <th>日期</th>
                    <th>变更前</th>
                    <th>变更后</th>
                    <th>详情</th>
                    <th>处罚金额</th>
                    <th>状态</th>
                    <th>来源</th>
                  </tr>
                </thead>
                <tbody>
                  {events.map((ev) => {
                    const emph = isEmphasizedEvent(ev.event_type)
                    const isPunish = ev.event_type.includes('行政处罚') || ev.event_type.includes('处罚')
                    return (
                      <tr
                        key={ev.event_id}
                        className={emph ? (isPunish || ev.event_type.includes('吊销') ? 'row-emphasis' : 'row-emphasis-mid') : undefined}
                      >
                        <td>
                          <EventTypeTag raw={ev.event_type} />
                        </td>
                        <td className="mono muted">{fmtDate(ev.event_date)}</td>
                        <td className="muted" style={{ maxWidth: 180 }}>
                          {ev.old_value ?? '-'}
                        </td>
                        <td style={{ maxWidth: 180 }}>{ev.new_value ?? '-'}</td>
                        <td style={{ minWidth: 200 }}>{ev.detail ?? '-'}</td>
                        <td className="num" style={isPunish && ev.penalty_amount ? { color: 'var(--risk-high)', fontWeight: 700 } : undefined}>
                          {isPunish && ev.penalty_amount ? fmtMoney(ev.penalty_amount) : fmtMoney(ev.penalty_amount)}
                        </td>
                        <td>{ev.status ?? '-'}</td>
                        <td className="muted">{ev.source ?? '-'}</td>
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
  )
}