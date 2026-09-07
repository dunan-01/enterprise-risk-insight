import { useCallback, useEffect, useState } from 'react'
import { api, ApiError } from '../../api/client'
import type { RecruitmentEvent } from '../../api/types'
import { EvidenceTag } from '../../components/Badges'
import { EmptyState, ErrorBlock, LoadingState } from '../../components/States'
import { fmtDate } from '../../lib/format'

/** 招聘类型标签颜色 */
function RecruitmentTypeTag({ raw }: { raw: string | null }) {
  if (!raw) return <span className="tag tone-muted">-</span>
  const config: Record<string, { color: string; label: string }> = {
    hiring_expansion: { color: '#10b981', label: '扩张' },
    hiring_freeze: { color: '#ef4444', label: '冻结' },
    posting_withdrawal: { color: '#f59e0b', label: '撤回' },
    mass_recruitment: { color: '#2563eb', label: '大规模招聘' },
    key_role_opening: { color: '#8b5cf6', label: '关键岗位' },
    recruitment_reduction: { color: '#f97316', label: '缩减' },
    job_posting: { color: '#6b7280', label: '常规招聘' },
  }
  const { color, label } = config[raw] ?? { color: '#6b7280', label: raw }
  return (
    <span
      className="tag"
      style={{
        background: `${color}18`,
        color,
        border: `1px solid ${color}40`,
      }}
    >
      {label}
    </span>
  )
}

/** 薪资格式化：元 → "15K-25K" */
function fmtSalaryRange(min: number | null, max: number | null): string {
  if (min === null && max === null) return '-'
  const parts: string[] = []
  if (min !== null) parts.push(`${(min / 1000).toFixed(0)}K`)
  if (max !== null) parts.push(`${(max / 1000).toFixed(0)}K`)
  return parts.join(' - ')
}

/** 招聘信息 Tab */
export default function RecruitmentTab({
  companyId,
  onEvidenceClick,
}: {
  companyId: string
  onEvidenceClick?: (id: string) => void
}) {
  const [state, setState] = useState<'loading' | 'done' | 'error'>('loading')
  const [error, setError] = useState<ApiError | null>(null)
  const [events, setEvents] = useState<RecruitmentEvent[]>([])

  const load = useCallback(async () => {
    setState('loading')
    setError(null)
    try {
      const res = await api.recruitmentEvents(companyId)
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
        <h2>招聘信息</h2>
        <span className="hint">
          招聘动态 / 岗位发布 · GET /api/companies/{companyId}/recruitment-events
        </span>
      </div>

      {state === 'loading' && <LoadingState text="招聘信息加载中…" />}

      {state === 'error' && (
        <div className="card-body">
          <ErrorBlock
            title="招聘信息加载失败"
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
              共 <b>{events.length}</b> 条招聘事件
            </span>
          </div>
          {events.length === 0 ? (
            <EmptyState title="暂无招聘信息" desc="该企业目前没有招聘事件记录。" />
          ) : (
            <div className="table-wrap">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>发布日期</th>
                    <th>招聘类型</th>
                    <th>岗位类别</th>
                    <th>岗位名称</th>
                    <th>计划人数</th>
                    <th>薪资范围</th>
                    <th>地点</th>
                    <th>状态</th>
                    <th>Evidence</th>
                  </tr>
                </thead>
                <tbody>
                  {events.map((ev) => (
                    <tr key={ev.event_id}>
                      <td className="mono muted">{fmtDate(ev.publish_date)}</td>
                      <td>
                        <RecruitmentTypeTag raw={ev.event_type} />
                      </td>
                      <td>{ev.position_category ?? '-'}</td>
                      <td style={{ maxWidth: 200 }}>{ev.position_name ?? '-'}</td>
                      <td className="num">{ev.planned_headcount ?? '-'}</td>
                      <td className="num">{fmtSalaryRange(ev.salary_min, ev.salary_max)}</td>
                      <td className="muted">{ev.location ?? '-'}</td>
                      <td>{ev.status ?? '-'}</td>
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
