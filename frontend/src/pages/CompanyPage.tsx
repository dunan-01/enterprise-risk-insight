import { useCallback, useEffect, useRef, useState } from 'react'
import { Link, useParams, useSearchParams } from 'react-router-dom'
import { api, ApiError } from '../api/client'
import type { AnalysisResponse, CompanyProfile } from '../api/types'
import { BusinessStatusTag } from '../components/Badges'
import { ErrorBlock, SkeletonBlock } from '../components/States'
import { fmtDate, fmtWan } from '../lib/format'
import AnalysisTab from './tabs/AnalysisTab'
import BusinessEventsTab from './tabs/BusinessEventsTab'
import JudicialEventsTab from './tabs/JudicialEventsTab'
import OverviewTab from './tabs/OverviewTab'
import RelationsTab from './tabs/RelationsTab'

/** AI 分析状态机：loading-history → (done | not-analyzed) → loading → (done | error) */
export type AnalysisState =
  | { status: 'loading-history' }
  | { status: 'not-analyzed' }
  | { status: 'loading'; startedAt: number }
  | { status: 'done'; startedAt: number; result: AnalysisResponse }
  | { status: 'error'; startedAt: number; error: ApiError }

const TABS = [
  { key: 'overview', label: '企业概况' },
  { key: 'business', label: '工商动态' },
  { key: 'judicial', label: '司法风险' },
  { key: 'relations', label: '关联关系' },
  { key: 'analysis', label: 'AI 风险洞察' },
] as const

type TabKey = (typeof TABS)[number]['key']

export default function CompanyPage() {
  const { companyId = '' } = useParams<{ companyId: string }>()
  const [searchParams, setSearchParams] = useSearchParams()
  const activeTab = (searchParams.get('tab') as TabKey | null) ?? 'overview'

  const [profile, setProfile] = useState<CompanyProfile | null>(null)
  const [profileState, setProfileState] = useState<'loading' | 'done' | 'error'>('loading')
  const [profileError, setProfileError] = useState<ApiError | null>(null)

  // AI 分析状态提升到页面级：切换 Tab 不中断分析请求
  const [analysis, setAnalysis] = useState<AnalysisState>({ status: 'loading-history' })
  const analysisRunningRef = useRef(false)

  const loadProfile = useCallback(async () => {
    setProfileState('loading')
    setProfileError(null)
    try {
      const res = await api.profile(companyId)
      setProfile(res.profile)
      setProfileState('done')
    } catch (e) {
      setProfileError(e as ApiError)
      setProfileState('error')
    }
  }, [companyId])

  /** 加载已有分析结果（不触发 Harness） */
  const loadHistory = useCallback(async () => {
    setAnalysis({ status: 'loading-history' })
    try {
      const result = await api.latestAnalysis(companyId)
      if (result) {
        setAnalysis({ status: 'done', startedAt: Date.now(), result })
      } else {
        setAnalysis({ status: 'not-analyzed' })
      }
    } catch {
      // 网络错误等不影响页面，当作未分析
      setAnalysis({ status: 'not-analyzed' })
    }
  }, [companyId])

  useEffect(() => {
    // 切换企业时重置分析状态与页面
    analysisRunningRef.current = false
    void loadProfile()
    void loadHistory()
  }, [companyId, loadProfile, loadHistory])

  const startAnalysis = useCallback(() => {
    if (analysisRunningRef.current) return
    analysisRunningRef.current = true
    const startedAt = Date.now()
    setAnalysis({ status: 'loading', startedAt })
    api
      .analyze(companyId)
      .then((result) => {
        analysisRunningRef.current = false
        setAnalysis({ status: 'done', startedAt, result })
      })
      .catch((e: ApiError) => {
        analysisRunningRef.current = false
        setAnalysis({ status: 'error', startedAt, error: e })
      })
  }, [companyId])

  const switchTab = (key: TabKey) => {
    setSearchParams(key === 'overview' ? {} : { tab: key }, { replace: true })
  }

  const notFound = profileState === 'error' && profileError?.status === 404

  return (
    <div className="page">
      <div className="crumbs">
        <Link to="/">企业搜索</Link>
        <span className="sep">/</span>
        <span>{notFound ? '未找到企业' : companyId}</span>
      </div>

      {/* 企业概览卡片 */}
      {profileState === 'loading' && (
        <div className="card">
          <SkeletonBlock rows={4} />
        </div>
      )}

      {profileState === 'error' && (
        <div className="card">
          <div className="card-body">
            <ErrorBlock
              title={notFound ? `企业 ${companyId} 不存在` : '企业信息加载失败'}
              message={
                notFound
                  ? '未找到该企业，请确认企业 ID 是否正确，或返回搜索页重新查询。'
                  : (profileError?.message ?? '未知错误')
              }
              code={profileError?.code}
              onRetry={() => void loadProfile()}
            />
            {notFound && (
              <div style={{ marginTop: 12 }}>
                <Link to="/" className="btn btn-primary" style={{ textDecoration: 'none' }}>
                  ← 返回企业搜索
                </Link>
              </div>
            )}
          </div>
        </div>
      )}

      {profileState === 'done' && profile && (
        <>
          <section className="company-hero">
            <div className="logo-box">{profile.company_name.slice(0, 1)}</div>
            <div className="info">
              <div className="name-row">
                <h1>{profile.company_name}</h1>
                <span className="cid">{profile.company_id}</span>
                <BusinessStatusTag raw={profile.business_status} />
              </div>
              <div className="meta">
                <span>
                  法定代表人 <b>{profile.legal_rep ?? '-'}</b>
                </span>
                <span>
                  注册资本 <b>{fmtWan(profile.reg_capital)}</b>
                </span>
                <span>
                  成立日期 <b>{fmtDate(profile.established_date)}</b>
                </span>
                <span>
                  所属行业 <b>{profile.industry ?? '-'}</b>
                </span>
                <span>
                  企业类型 <b>{profile.company_type ?? '-'}</b>
                </span>
              </div>
              <div className="addr">
                注册地址：{profile.reg_address ?? '-'} · 数据更新：{fmtDate(profile.update_date)}
              </div>
            </div>
          </section>

          {/* Tab 导航 */}
          <nav className="tabs">
            {TABS.map((t) => (
              <button
                key={t.key}
                className={`tab ${activeTab === t.key ? 'active' : ''}`}
                onClick={() => switchTab(t.key)}
              >
                {t.key === 'analysis' && (analysis.status === 'loading' || analysis.status === 'loading-history') && (
                  <span className="spin-dot" title="AI 分析进行中" />
                )}
                {t.label}
              </button>
            ))}
          </nav>

          {/* Tab 内容（各 Tab 独立加载数据；AI 分析状态提升在页面级，切 Tab 不中断） */}
          {activeTab === 'overview' && <OverviewTab profile={profile} />}
          {activeTab === 'business' && <BusinessEventsTab companyId={companyId} />}
          {activeTab === 'judicial' && <JudicialEventsTab companyId={companyId} />}
          {activeTab === 'relations' && (
            <RelationsTab companyId={companyId} companyName={profile.company_name} />
          )}
          {activeTab === 'analysis' && (
            <AnalysisTab
              companyId={companyId}
              companyName={profile.company_name}
              state={analysis}
              onStart={startAnalysis}
            />
          )}
        </>
      )}
    </div>
  )
}