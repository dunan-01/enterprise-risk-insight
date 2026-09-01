import { useCallback, useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../api/client'
import type { TraceEvent, TraceResponse } from '../api/types'
import { EvidenceTag } from './Badges'
import EvidenceDetailDrawer from './EvidenceDetailDrawer'

// ------------------------------------------------------------
// 时间格式化
// ------------------------------------------------------------
function fmtTime(iso: string): string {
  try {
    const d = new Date(iso)
    return d.toLocaleTimeString('zh-CN', { hour12: false, hour: '2-digit', minute: '2-digit', second: '2-digit' })
  } catch {
    return iso
  }
}

// ------------------------------------------------------------
// 事件类型 → 图标/样式映射
// ------------------------------------------------------------
interface EventTypeStyle {
  icon: 'circle' | 'diamond' | 'check' | 'alert' | 'spin'
  color: string
  bgColor: string
}

function eventTypeStyle(evt: TraceEvent): EventTypeStyle {
  const t = evt.type
  // 完成事件
  if (t === 'analysis_completed') {
    return { icon: 'check', color: '#0f9d58', bgColor: '#e3f6ea' }
  }
  if (t === 'analysis_failed') {
    return { icon: 'alert', color: '#d92d20', bgColor: '#fde8e7' }
  }
  // 取消事件
  if (t === 'analysis_cancelled') {
    return { icon: 'alert', color: '#d92d20', bgColor: '#fef2f2' }
  }
  // 审核事件（菱形）
  if (t === 'coverage_started' || t === 'coverage_result') {
    return { icon: 'diamond', color: '#7c3aed', bgColor: '#f1eafe' }
  }
  if (t === 'verification_started' || t === 'verification_result') {
    return { icon: 'diamond', color: '#0891b2', bgColor: '#e0f5f9' }
  }
  // 报告生成
  if (t === 'report_generated') {
    return { icon: 'check', color: '#2563eb', bgColor: '#e8effc' }
  }
  // 发现关联企业 / 发现证据
  if (t === 'company_discovered' || t === 'evidence_discovered') {
    return { icon: 'circle', color: '#e8730c', bgColor: '#fdf0e0' }
  }
  // 默认（普通事件）
  return { icon: 'circle', color: '#2563eb', bgColor: '#e8effc' }
}

// ------------------------------------------------------------
// 单个 Timeline Item
// ------------------------------------------------------------
function TimelineItem({ event, isLast, onEvidenceClick }: { event: TraceEvent; isLast: boolean; onEvidenceClick?: (id: string) => void }) {
  const style = eventTypeStyle(event)
  const time = fmtTime(event.timestamp)

  return (
    <div className={`trace-item ${isLast ? 'trace-item-last' : ''}`}>
      {/* 左侧时间 */}
      <div className="trace-time">{time}</div>

      {/* 中间连线 + 图标 */}
      <div className="trace-rail">
        <div
          className={`trace-icon trace-icon-${style.icon}`}
          style={{ color: style.color, background: style.bgColor }}
        >
          {style.icon === 'check' && (
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
              <polyline points="20 6 9 17 4 12" />
            </svg>
          )}
          {style.icon === 'alert' && (
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
              <path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z" />
              <line x1="12" y1="9" x2="12" y2="13" />
              <line x1="12" y1="17" x2="12.01" y2="17" />
            </svg>
          )}
          {style.icon === 'diamond' && (
            <svg width="12" height="12" viewBox="0 0 24 24" fill="currentColor">
              <rect x="12" y="2" width="14" height="14" rx="2" transform="rotate(45 12 2)" />
            </svg>
          )}
        </div>
        {!isLast && <div className="trace-line" />}
      </div>

      {/* 右侧内容 */}
      <div className="trace-content">
        <div className="trace-title">{event.title}</div>
        {event.description && (
          <div className="trace-desc">{event.description}</div>
        )}

        {/* Agent / Tool 标签 */}
        <div className="trace-tags">
          {event.agent && (
            <span className="trace-tag trace-tag-agent">{event.agent}</span>
          )}
          {event.tool && (
            <span className="trace-tag trace-tag-tool">{event.tool}</span>
          )}
          {event.status && event.status !== 'completed' && (
            <span className={`trace-tag trace-tag-status-${event.status}`}>{event.status}</span>
          )}
        </div>

        {/* 企业名称链接 */}
        {event.company_id && event.company_name && (
          <Link to={`/company/${event.company_id}`} className="trace-company-link">
            {event.company_name}
            <span className="trace-company-id">{event.company_id}</span>
          </Link>
        )}

        {/* Evidence Tags */}
        {event.evidence_ids.length > 0 && (
          <div className="trace-evidence">
            {event.evidence_ids.map((id) => (
              <EvidenceTag key={id} id={id} onClick={onEvidenceClick} />
            ))}
          </div>
        )}
      </div>
    </div>
  )
}

// ------------------------------------------------------------
// InvestigationTrace 组件
// ------------------------------------------------------------
export default function InvestigationTrace({
  taskId,
  taskStatus,
}: {
  taskId: string
  taskStatus: string
}) {
  const [trace, setTrace] = useState<TraceResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const [drawerEvidenceId, setDrawerEvidenceId] = useState<string | null>(null)

  const fetchTrace = useCallback(async () => {
    try {
      const res = await api.getAnalysisTaskTrace(taskId)
      setTrace(res)
      setError(null)
      setLoading(false)
    } catch (e) {
      const err = e as { message?: string }
      setError(err.message ?? '加载追踪数据失败')
      setLoading(false)
    }
  }, [taskId])

  useEffect(() => {
    // 初始加载
    void fetchTrace()

    // 轮询逻辑：running 时每 3 秒，completed/failed/cancelled 时停止
    if (taskStatus === 'running' || taskStatus === 'queued') {
      pollRef.current = setInterval(() => {
        void fetchTrace()
      }, 3000)
    }

    return () => {
      if (pollRef.current) {
        clearInterval(pollRef.current)
        pollRef.current = null
      }
    }
  }, [fetchTrace, taskStatus])

  // 当 taskStatus 变化时（如从 running 变为 completed/failed/cancelled），停止轮询
  useEffect(() => {
    if (taskStatus === 'completed' || taskStatus === 'failed' || taskStatus === 'cancelled') {
      if (pollRef.current) {
        clearInterval(pollRef.current)
        pollRef.current = null
      }
      // 最后一次拉取确保数据完整
      void fetchTrace()
    }
  }, [taskStatus, fetchTrace])

  if (loading) {
    return (
      <div className="trace-container">
        <div className="trace-loading">
          <span className="spinner" />
          <span>加载调查轨迹…</span>
        </div>
      </div>
    )
  }

  if (error) {
    return (
      <div className="trace-container">
        <div className="trace-error">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <circle cx="12" cy="12" r="10" />
            <line x1="12" y1="8" x2="12" y2="12" />
            <line x1="12" y1="16" x2="12.01" y2="16" />
          </svg>
          {error}
        </div>
      </div>
    )
  }

  if (!trace || trace.events.length === 0) {
    return (
      <div className="trace-container">
        <div className="trace-empty">暂无追踪事件</div>
      </div>
    )
  }

  return (
    <div className="trace-container">
      <div className="trace-header">
        <span className="trace-header-title">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <circle cx="12" cy="12" r="10" />
            <polyline points="12 6 12 12 16 14" />
          </svg>
          调查轨迹
        </span>
        <span className="trace-header-meta">
          {trace.event_count} 个事件
          {trace.task_status === 'running' && (
            <span className="trace-live-dot" />
          )}
        </span>
      </div>
      <div className="trace-body">
        {trace.events.map((evt, i) => (
          <TimelineItem
            key={evt.event_id}
            event={evt}
            isLast={i === trace.events.length - 1}
            onEvidenceClick={setDrawerEvidenceId}
          />
        ))}
      </div>
      <EvidenceDetailDrawer
        evidenceId={drawerEvidenceId}
        onClose={() => setDrawerEvidenceId(null)}
      />
    </div>
  )
}
