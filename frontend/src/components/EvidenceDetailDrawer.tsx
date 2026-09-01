import { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api, ApiError } from '../api/client'
import type { EvidenceResponse } from '../api/types'

/**
 * Evidence Detail Drawer（V1.4）。
 *
 * 右侧抽屉组件，展示确定性数据库事实。
 * 支持 Bxxx（工商）/ Jxxx（司法）/ Rxxx（关系）三类 Evidence。
 *
 * 设计原则：
 * - 只展示数据库原始事实，不包含模型判断
 * - 企业名称可点击跳转
 * - Loading / Error 状态友好处理
 */

// ------------------------------------------------------------
// 格式化工具
// ------------------------------------------------------------

function fmtMoney(amount: number | null | undefined): string {
  if (amount === null || amount === undefined) return '-'
  if (amount >= 10000) return `¥${(amount / 10000).toLocaleString()}万`
  return `¥${amount.toLocaleString()}`
}

function fmtPercent(ratio: number | null | undefined): string {
  if (ratio === null || ratio === undefined) return '-'
  return `${Math.round(ratio * 100)}%`
}

function fmtDate(date: string | null | undefined): string {
  if (!date) return '-'
  return date
}

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  if (children === null || children === undefined || children === '' || children === '-') {
    return null
  }
  return (
    <div className="ev-row">
      <span className="ev-label">{label}</span>
      <span className="ev-value">{children}</span>
    </div>
  )
}

// ------------------------------------------------------------
// 企业链接
// ------------------------------------------------------------

function CompanyLink({ companyId, companyName }: { companyId: string; companyName?: string | null }) {
  return (
    <Link to={`/company/${companyId}`} className="ev-company-link">
      <span className="ev-company-name">{companyName || companyId}</span>
      <span className="ev-company-id">{companyId}</span>
    </Link>
  )
}

// ------------------------------------------------------------
// Evidence 内容渲染
// ------------------------------------------------------------

function BusinessEvidence({ data }: { data: Record<string, any> }) {
  return (
    <>
      <Row label="事件类型">{data.event_type}</Row>
      <Row label="事件日期">{fmtDate(data.event_date)}</Row>
      <Row label="变更前值">{data.old_value}</Row>
      <Row label="变更后值">{data.new_value}</Row>
      <Row label="详情">{data.detail}</Row>
      <Row label="状态">{data.status}</Row>
      <Row label="处罚金额">{data.penalty_amount != null ? fmtMoney(data.penalty_amount) : null}</Row>
      <Row label="登记机关">{data.authority}</Row>
    </>
  )
}

function JudicialEvidence({ data }: { data: Record<string, any> }) {
  return (
    <>
      <Row label="案件类型">{data.case_type}</Row>
      <Row label="司法角色">{data.role}</Row>
      <Row label="案号">{data.case_number}</Row>
      <Row label="法院">{data.court}</Row>
      <Row label="案由">{data.cause}</Row>
      <Row label="涉案金额">{data.amount != null ? fmtMoney(data.amount) : null}</Row>
      <Row label="立案日期">{fmtDate(data.filing_date)}</Row>
      <Row label="结案日期">{fmtDate(data.close_date)}</Row>
      <Row label="状态">{data.status}</Row>
      <Row label="结果">{data.result}</Row>
    </>
  )
}

function RelationEvidence({ data }: { data: Record<string, any> }) {
  return (
    <>
      <Row label="关系类型">{data.relation_type}</Row>
      <Row label="股权比例">{fmtPercent(data.equity_ratio)}</Row>
      <Row label="涉及金额">{data.amount != null ? fmtMoney(data.amount) : null}</Row>
      <Row label="关系详情">{data.relation_detail}</Row>
      <Row label="起始日期">{fmtDate(data.start_date)}</Row>
      <Row label="终止日期">{fmtDate(data.end_date)}</Row>
      <Row label="状态">{data.status}</Row>
    </>
  )
}

// ------------------------------------------------------------
// 主组件
// ------------------------------------------------------------

export default function EvidenceDetailDrawer({
  evidenceId,
  onClose,
}: {
  evidenceId: string | null
  onClose: () => void
}) {
  const [evidence, setEvidence] = useState<EvidenceResponse | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const fetchEvidence = useCallback(async (id: string) => {
    setLoading(true)
    setError(null)
    setEvidence(null)
    try {
      const res = await api.getEvidence(id)
      setEvidence(res)
    } catch (e) {
      if (e instanceof ApiError) {
        if (e.status === 404) {
          setError(`证据 ${id} 不存在或已不可用`)
        } else if (e.status === 400) {
          setError(`证据 ${id} 格式无效（${e.message}）`)
        } else {
          setError(`加载失败（HTTP ${e.status}）：${e.message}`)
        }
      } else {
        const err = e as { message?: string }
        setError(err.message ?? '加载证据详情失败')
      }
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    if (evidenceId) {
      void fetchEvidence(evidenceId)
    } else {
      setEvidence(null)
      setError(null)
      setLoading(false)
    }
  }, [evidenceId, fetchEvidence])

  // ESC 关闭
  useEffect(() => {
    if (!evidenceId) return
    const handleKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', handleKey)
    return () => window.removeEventListener('keydown', handleKey)
  }, [evidenceId, onClose])

  if (!evidenceId) return null

  const typeLabel = evidence?.evidence_type === 'business' ? '工商事件'
    : evidence?.evidence_type === 'judicial' ? '司法事件'
    : evidence?.evidence_type === 'relation' ? '企业关系'
    : '证据'

  const typeColor = evidence?.evidence_type === 'business' ? '#2563eb'
    : evidence?.evidence_type === 'judicial' ? '#7c3aed'
    : '#0891b2'

  return (
    <>
      {/* 遮罩层 */}
      <div
        className="ev-overlay"
        onClick={onClose}
        style={{ opacity: evidenceId ? 1 : 0, pointerEvents: evidenceId ? 'auto' : 'none' }}
      />

      {/* Drawer */}
      <div className={`ev-drawer ${evidenceId ? 'ev-drawer-open' : ''}`}>
        {/* Header */}
        <div className="ev-header">
          <div className="ev-header-top">
            <h3>证据详情</h3>
            <button className="ev-close" onClick={onClose} title="关闭">
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <line x1="18" y1="6" x2="6" y2="18" />
                <line x1="6" y1="6" x2="18" y2="18" />
              </svg>
            </button>
          </div>
          {evidence && (
            <div className="ev-header-info">
              <span className="ev-id" style={{ borderLeftColor: typeColor }}>
                {evidence.evidence_id}
              </span>
              <span className="ev-type" style={{ color: typeColor }}>{typeLabel}</span>
            </div>
          )}
        </div>

        {/* Body */}
        <div className="ev-body">
          {loading && (
            <div className="ev-loading">
              <span className="spinner" />
              <span>正在加载证据…</span>
            </div>
          )}

          {error && (
            <div className="ev-error">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <circle cx="12" cy="12" r="10" />
                <line x1="12" y1="8" x2="12" y2="12" />
                <line x1="12" y1="16" x2="12.01" y2="16" />
              </svg>
              {error}
            </div>
          )}

          {evidence && (
            <>
              {/* 企业信息 */}
              <div className="ev-section">
                <div className="ev-section-title">企业</div>
                {evidence.evidence_type === 'relation' ? (
                  <div className="ev-relation-companies">
                    <div className="ev-relation-pair">
                      <span className="ev-relation-label">From</span>
                      <CompanyLink
                        companyId={evidence.from_company_id!}
                        companyName={evidence.from_company_name}
                      />
                    </div>
                    <div className="ev-relation-arrow">→</div>
                    <div className="ev-relation-pair">
                      <span className="ev-relation-label">To</span>
                      <CompanyLink
                        companyId={evidence.to_company_id!}
                        companyName={evidence.to_company_name}
                      />
                    </div>
                  </div>
                ) : (
                  <CompanyLink
                    companyId={evidence.company_id!}
                    companyName={evidence.company_name}
                  />
                )}
              </div>

              {/* 数据详情 */}
              <div className="ev-section">
                <div className="ev-section-title">原始事实</div>
                <div className="ev-fields">
                  {evidence.evidence_type === 'business' && <BusinessEvidence data={evidence.data} />}
                  {evidence.evidence_type === 'judicial' && <JudicialEvidence data={evidence.data} />}
                  {evidence.evidence_type === 'relation' && <RelationEvidence data={evidence.data} />}
                </div>
              </div>

              {/* 数据来源 */}
              <div className="ev-section ev-source">
                <div className="ev-section-title">来源</div>
                <span className="ev-source-value">
                  {evidence.source === 'simulated' ? '模拟数据' : evidence.source || '未知'}
                </span>
              </div>
            </>
          )}
        </div>
      </div>
    </>
  )
}
