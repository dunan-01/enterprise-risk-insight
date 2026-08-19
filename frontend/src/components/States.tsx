/** 加载状态块 */
export function LoadingState({ text = '数据加载中…' }: { text?: string }) {
  return (
    <div className="state-block">
      <div className="icon">
        <span className="spinner lg" />
      </div>
      <div className="title">{text}</div>
    </div>
  )
}

/** 骨架屏 */
export function SkeletonBlock({ rows = 5 }: { rows?: number }) {
  return (
    <div className="skeleton">
      {Array.from({ length: rows }).map((_, i) => (
        <div key={i} className="sk-line" style={{ width: `${92 - i * 8}%` }} />
      ))}
    </div>
  )
}

/** 错误提示块 */
export function ErrorBlock({
  title = '加载失败',
  message,
  code,
  onRetry,
}: {
  title?: string
  message: string
  code?: string | null
  onRetry?: () => void
}) {
  return (
    <div className="error-box">
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="note-icon" style={{ flex: 'none', marginTop: 2 }}>
        <circle cx="12" cy="12" r="9" />
        <path d="M12 8v5M12 16.5v.5" strokeLinecap="round" />
      </svg>
      <div style={{ flex: 1 }}>
        <b>{title}</b>
        {code && <span className="err-code">{code}</span>}
        <div>{message}</div>
        {onRetry && (
          <button className="btn btn-ghost" style={{ marginTop: 8, padding: '5px 14px', fontSize: 12.5 }} onClick={onRetry}>
            重试
          </button>
        )}
      </div>
    </div>
  )
}

/** 空状态 */
export function EmptyState({
  title = '暂无数据',
  desc,
}: {
  title?: string
  desc?: string
}) {
  return (
    <div className="state-block">
      <div className="icon">
        <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="#8a97ad" strokeWidth="1.8">
          <rect x="3" y="4" width="18" height="16" rx="2" />
          <path d="M3 9h18M8 14h8" strokeLinecap="round" />
        </svg>
      </div>
      <div className="title">{title}</div>
      {desc && <div className="desc">{desc}</div>}
    </div>
  )
}