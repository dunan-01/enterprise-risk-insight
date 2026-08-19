import { useEffect, useState } from 'react'
import { Link, useLocation } from 'react-router-dom'

/** 顶部深色导航栏（品牌区 + 导航 + 系统状态） */
export default function Layout({ children }: { children: React.ReactNode }) {
  const location = useLocation()
  const [backendOk, setBackendOk] = useState<boolean | null>(null)

  // 轻量健康检查（仅用于顶栏状态提示，失败不影响页面功能）
  useEffect(() => {
    let alive = true
    fetch('/health', { signal: AbortSignal.timeout(4000) })
      .then((r) => {
        if (alive) setBackendOk(r.ok)
      })
      .catch(() => {
        if (alive) setBackendOk(false)
      })
    return () => {
      alive = false
    }
  }, [])

  return (
    <>
      <header className="topbar">
        <Link to="/" className="brand" style={{ textDecoration: 'none' }}>
          <span className="brand-mark">
            <svg width="20" height="20" viewBox="0 0 32 32" fill="none">
              <path
                d="M16 3l11 4v9c0 6.8-4.7 11.8-11 14-6.3-2.2-11-7.2-11-14V7l11-4z"
                fill="rgba(255,255,255,0.12)"
                stroke="#fff"
                strokeWidth="2"
              />
              <path
                d="M12 16l3 3 5-5.5"
                stroke="#fff"
                strokeWidth="2.4"
                strokeLinecap="round"
                strokeLinejoin="round"
              />
            </svg>
          </span>
          <span>
            <div className="brand-title">企业关联风险智能洞察系统</div>
            <div className="brand-sub">Risk Intelligence Insight</div>
          </span>
        </Link>

        <nav className="nav-links">
          <Link to="/" className={`nav-link ${location.pathname === '/' ? 'active' : ''}`}>
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <circle cx="11" cy="11" r="7" />
              <path d="M20 20l-3.2-3.2" strokeLinecap="round" />
            </svg>
            企业搜索
          </Link>
          <div className="sys-status" title="后端服务连接状态">
            <span className={`dot ${backendOk === false ? 'err' : ''}`} />
            {backendOk === null ? '连接检测中…' : backendOk ? '后端服务正常' : '后端服务不可达'}
          </div>
        </nav>
      </header>
      {children}
      <footer className="footer">
        企业关联风险智能洞察系统 · 数据来源：模拟工商/司法/关系数据库（risk.db） · AI 分析由 Risk Harness 真实执行
      </footer>
    </>
  )
}