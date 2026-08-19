import { useCallback, useEffect, useState } from 'react'
import { api, ApiError } from '../../api/client'
import type { JudicialEvent } from '../../api/types'
import { CaseTypeTag, JudicialRoleTag } from '../../components/Badges'
import { EmptyState, ErrorBlock, LoadingState } from '../../components/States'
import { fmtDate, fmtMoney } from '../../lib/format'
import { isJudicialRiskRole } from '../../lib/presentation'

/** 司法风险 Tab：案件表格，企业角色醒目标签，被执行/失信等行级强调 */
export default function JudicialEventsTab({ companyId }: { companyId: string }) {
  const [state, setState] = useState<'loading' | 'done' | 'error'>('loading')
  const [error, setError] = useState<ApiError | null>(null)
  const [events, setEvents] = useState<JudicialEvent[]>([])

  const load = useCallback(async () => {
    setState('loading')
    setError(null)
    try {
      const res = await api.judicialEvents(companyId)
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

  const riskCount = events.filter((e) => isJudicialRiskRole(e.role) || isJudicialRiskRole(e.case_type)).length

  return (
    <div className="card">
      <div className="card-head">
        <h2>司法风险</h2>
        <span className="hint">诉讼 / 被执行 / 失信 / 限高 / 股权冻结等 · GET /api/companies/{companyId}/judicial-events</span>
      </div>

      {state === 'loading' && <LoadingState text="司法事件加载中…" />}

      {state === 'error' && (
        <div className="card-body">
          <ErrorBlock
            title="司法事件加载失败"
            message={error?.message ?? '未知错误'}
            code={error?.code}
            onRetry={() => void load()}
          />
        </div>
      )}

      {state === 'done' && (
        <>
          <div className="card-body" style={{ paddingBottom: 0 }}>
            <div className="note" style={{ marginBottom: 12 }}>
              <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="note-icon">
                <circle cx="12" cy="12" r="9" />
                <path d="M12 8v5M12 16.5v.5" strokeLinecap="round" />
              </svg>
              <span>
                说明：企业角色为「原告」的案件通常不代表企业自身风险，仅记录企业作为当事人的诉讼活动。
                被执行人 / 失信被执行人 / 限制消费 / 股权冻结等角色对应的案件需重点关注（表格左侧红色标记）。
              </span>
            </div>
          </div>
          <div className="stat-bar">
            <span>
              共 <b>{events.length}</b> 条司法事件
            </span>
            {riskCount > 0 && (
              <span style={{ color: 'var(--risk-high)' }}>
                ▲ <b>{riskCount}</b> 条被执行 / 失信 / 限高类记录
              </span>
            )}
          </div>
          {events.length === 0 ? (
            <EmptyState title="暂无司法事件" desc="该企业目前没有诉讼、被执行、失信等司法记录。" />
          ) : (
            <div className="table-wrap">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>案件类型</th>
                    <th>案号</th>
                    <th>法院</th>
                    <th>立案日期</th>
                    <th>案由</th>
                    <th>企业角色</th>
                    <th>涉案金额</th>
                    <th>案件状态</th>
                    <th>审理结果 / 执行情况</th>
                  </tr>
                </thead>
                <tbody>
                  {events.map((ev) => {
                    const risk = isJudicialRiskRole(ev.role) || isJudicialRiskRole(ev.case_type)
                    return (
                      <tr key={ev.event_id} className={risk ? 'row-emphasis' : undefined}>
                        <td>
                          <CaseTypeTag raw={ev.case_type} />
                        </td>
                        <td className="mono" style={{ whiteSpace: 'nowrap' }}>
                          {ev.case_number ?? '-'}
                        </td>
                        <td className="muted">{ev.court ?? '-'}</td>
                        <td className="mono muted">{fmtDate(ev.filing_date)}</td>
                        <td>{ev.cause ?? '-'}</td>
                        <td>
                          <JudicialRoleTag raw={ev.role} />
                        </td>
                        <td className="num" style={ev.amount ? { fontWeight: 600 } : undefined}>
                          {fmtMoney(ev.amount)}
                        </td>
                        <td>{ev.status ?? '-'}</td>
                        <td style={{ maxWidth: 260 }}>{ev.result ?? '-'}</td>
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