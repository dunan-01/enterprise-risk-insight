import { useEffect, useState } from 'react'
import type { AnalysisState } from '../CompanyPage'
import { EvidenceTag, RiskLevelBadge, VerificationBadge } from '../../components/Badges'
import MarkdownReport from '../../components/MarkdownReport'
import { ErrorBlock } from '../../components/States'
import { fmtDuration, fmtElapsed } from '../../lib/format'
import { api } from '../../api/client'

/**
 * AI 风险洞察 Tab。
 *
 * 交互状态机：
 *   loading-history → (done | not-analyzed) → loading → (done | error)
 * 状态由 CompanyPage 持有，分析期间切换 Tab 不会中断请求。
 *
 * - loading-history 期间展示「正在检查已有分析结果…」
 * - not-analyzed 展示启动引导
 * - loading 期间展示「静态流程示意 + 真实等待计时」，不伪造实时进度百分比
 * - 结果全部如实展示后端返回字段（risk_level / verification_status / evidence_ids …）
 */
const PIPELINE_STEPS = [
  {
    name: '企业调查',
    module: 'risk-orchestrator',
    desc: '收集企业基本工商信息、经营事件、司法事件与一跳关联关系，形成调查底稿。',
  },
  {
    name: '覆盖审核',
    module: 'coverage-auditor',
    desc: '对照数据清单审核调查覆盖度，确认证据是否足以支撑风险结论。',
  },
  {
    name: '风险核验',
    module: 'risk-verifier',
    desc: '核验风险证据链，复核报告结论并给出最终风险等级与审核状态。',
  },
]

export default function AnalysisTab({
  companyId,
  companyName,
  state,
  onStart,
}: {
  companyId: string
  companyName: string
  state: AnalysisState
  onStart: () => void
}) {
  // 等待计时（仅 task-running 期间运行；切走再切回会按 startedAt 重新对齐）
  const [now, setNow] = useState(() => Date.now())
  useEffect(() => {
    if (state.status !== 'task-running') return
    setNow(Date.now())
    const timer = setInterval(() => setNow(Date.now()), 1000)
    return () => clearInterval(timer)
  }, [state.status])

  const [pdfLoading, setPdfLoading] = useState(false)
  const [pdfError, setPdfError] = useState<string | null>(null)

  const handleExportPdf = async () => {
    setPdfLoading(true)
    setPdfError(null)
    try {
      await api.exportPdf(companyId)
    } catch (e) {
      const err = e as { message?: string }
      setPdfError(err.message ?? 'PDF 导出失败')
    } finally {
      setPdfLoading(false)
    }
  }

  const result = state.status === 'done' ? state.result : null
  const error = state.status === 'error' ? state.error : null

  return (
    <div className="card">
      <div className="card-head">
        <h2>AI 风险洞察</h2>
        <span className="hint">Risk Harness 真实分析（risk-orchestrator → coverage-auditor → risk-verifier）</span>
      </div>

      {/* ============ loading-history：检查已有分析结果 ============ */}
      {state.status === 'loading-history' && (
        <div className="card-body">
          <div style={{ textAlign: 'center', padding: '24px 0' }}>
            <div style={{ display: 'inline-flex', alignItems: 'center', gap: 12 }}>
              <span className="spinner" />
              <span style={{ fontSize: 14, color: 'var(--text-3)' }}>正在检查已有分析结果…</span>
            </div>
          </div>
        </div>
      )}

      {/* ============ not-analyzed：启动引导 ============ */}
      {state.status === 'not-analyzed' && (
        <div className="card-body">
          <div className="note" style={{ marginBottom: 16 }}>
            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="note-icon">
              <path d="M12 2v4M12 18v4M4.9 4.9l2.8 2.8M16.3 16.3l2.8 2.8M2 12h4M18 12h4M4.9 19.1l2.8-2.8M16.3 7.7l2.8-2.8" strokeLinecap="round" />
            </svg>
            <span>
              点击下方按钮将对 <b>{companyName}（{companyId}）</b>提交一次异步 AI 风险分析任务：
              后端 Risk Harness（risk-orchestrator 调查 → coverage-auditor 覆盖审核 → risk-verifier 核验）将在后台执行。
              分析期间可切换其他 Tab 查看数据，页面刷新后仍会自动恢复分析状态。
            </span>
          </div>

          {/* 静态流程示意 */}
          <div className="pipeline">
            {PIPELINE_STEPS.map((s, i) => (
              <div key={s.name} className="step">
                <span className="step-no">STEP {i + 1}</span>
                <div className="step-name">{s.name}</div>
                <div className="step-desc">{s.desc}</div>
                <div className="step-state">
                  <span className="bar-dots">
                    <i />
                    <i />
                    <i />
                  </span>
                  待启动
                </div>
              </div>
            ))}
          </div>

          <div style={{ marginTop: 22, textAlign: 'center' }}>
            <button className="btn btn-primary" onClick={onStart} style={{ padding: '12px 30px', fontSize: 15 }}>
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M13 2L4.5 13.5H11L9.5 22 19 10h-6.5L13 2z" strokeLinejoin="round" />
              </svg>
              启动 AI 风险分析
            </button>
            <div style={{ marginTop: 10, fontSize: 12.5, color: 'var(--text-3)' }}>
              提交异步任务后可自由切换 Tab，任务完成后会自动通知
            </div>
          </div>
        </div>
      )}

      {/* ============ task-running：异步任务运行中 ============ */}
      {state.status === 'task-running' && (
        <div className="card-body">
          <div style={{ textAlign: 'center', padding: '10px 0 4px' }}>
            <div style={{ display: 'inline-flex', alignItems: 'center', gap: 12 }}>
              <span className="spinner lg" />
              <div style={{ textAlign: 'left' }}>
                <div style={{ fontSize: 16, fontWeight: 700 }}>
                  AI 正在进行企业风险调查与关联分析…
                </div>
                <div style={{ fontSize: 12.5, color: 'var(--text-3)', marginTop: 2 }}>
                  对 {companyName}（{companyId}）· 已等待{' '}
                  <b style={{ color: 'var(--brand)' }}>{fmtElapsed(state.startedAt, now)}</b>
                </div>
              </div>
            </div>
          </div>

          <div className="wait-timer" style={{ margin: '16px auto 0', display: 'flex' }}>
            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <circle cx="12" cy="12" r="9" />
              <path d="M12 7v5l3.5 2" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
            已等待 {fmtElapsed(state.startedAt, now)}
          </div>

          {/* 静态流程示意 */}
          <div className="pipeline">
            {PIPELINE_STEPS.map((s, i) => (
              <div key={s.name} className="step">
                <span className="step-no">STEP {i + 1}</span>
                <div className="step-name">{s.name}</div>
                <div className="step-desc">{s.desc}</div>
                <div className="step-state">
                  <span className="bar-dots">
                    <i />
                    <i />
                    <i />
                  </span>
                  分析中…
                </div>
              </div>
            ))}
          </div>

          <div className="note" style={{ marginTop: 18 }}>
            <span>
              后台任务运行中，可自由切换 Tab 查看数据。页面刷新后仍会自动恢复分析状态。
            </span>
          </div>
        </div>
      )}

      {/* ============ error：错误处理 ============ */}
      {state.status === 'error' && error && (
        <div className="card-body">
          {error.status === 404 ? (
            <ErrorBlock
              title={`企业 ${companyId} 不存在`}
              message="无法对该企业执行 AI 风险分析，请确认企业 ID 后重试。"
              code={error.code}
              onRetry={onStart}
            />
          ) : error.status === 503 || error.status === 504 ? (
            <ErrorBlock
              title="AI 分析服务暂不可用"
              message={error.message || 'Risk Harness 分析失败，请稍后重试。'}
              code={error.code}
              onRetry={onStart}
            />
          ) : (
            <ErrorBlock
              title="AI 分析失败"
              message={error.message}
              code={error.code}
              onRetry={onStart}
            />
          )}
          <div style={{ marginTop: 14, fontSize: 12.5, color: 'var(--text-3)' }}>
            分析失败不会影响其他 Tab 数据；可直接重试，或切换到其他企业。
          </div>
        </div>
      )}

      {/* ============ done：完整结果展示 ============ */}
      {state.status === 'done' && result && (
        <div className="card-body">
          {/* 结果指标区 */}
          <div className="result-grid">
            <div className="result-cell">
              <div className="k">AI 风险等级（Risk Harness 判断）</div>
              <div className="v">
                <RiskLevelBadge raw={result.risk_level} big />
                {!result.risk_level && (
                  <span style={{ marginLeft: 8, fontSize: 12, color: 'var(--text-3)' }}>
                    后端未解析出风险等级字符串
                  </span>
                )}
              </div>
            </div>
            <div className="result-cell">
              <div className="k">Verification 审核状态（如实展示后端返回值）</div>
              <div className="v">
                <VerificationBadge raw={result.verification_status} big />
                <span style={{ marginLeft: 8, fontSize: 12, color: 'var(--text-3)' }}>
                  {result.verification_status === 'PASS'
                    ? '风险证据链已通过核验'
                    : result.verification_status === 'UNRESOLVED'
                      ? '存在未解决项，报告按原样保留'
                      : '后端未返回审核状态'}
                </span>
              </div>
            </div>
            <div className="result-cell">
              <div className="k">分析耗时</div>
              <div className="v">
                <b style={{ fontFamily: 'var(--mono)' }}>{fmtDuration(result.duration_seconds)}</b>
                <span style={{ marginLeft: 8, fontSize: 12, color: 'var(--text-3)' }}>
                  状态：{result.status}
                </span>
              </div>
            </div>
          </div>

          {/* AI 风险摘要 */}
          <div className="result-cell" style={{ marginTop: 14, background: '#f3f7ff', borderColor: '#c9d9f5' }}>
            <div className="k">AI 风险摘要（summary）</div>
            <div className="v">
              {result.summary ? (
                <MarkdownReport content={result.summary} />
              ) : (
                <span style={{ color: 'var(--text-3)' }}>后端未返回摘要文本。</span>
              )}
            </div>
          </div>

          {/* 关联企业 + 关键证据 */}
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 1fr))', gap: 14, marginTop: 14 }}>
            <div className="result-cell">
              <div className="k">报告涉及的关联企业（related_companies）</div>
              <div className="v">
                {result.related_companies.length === 0 ? (
                  <span style={{ color: 'var(--text-3)' }}>无</span>
                ) : (
                  <div className="chip-group">
                    {result.related_companies.map((id) => (
                      <span key={id} className="chip">
                        <span className="cid">{id}</span>
                      </span>
                    ))}
                  </div>
                )}
              </div>
            </div>
            <div className="result-cell">
              <div className="k">关键证据（evidence_ids · B 工商 / J 司法 / R 关系）</div>
              <div className="v">
                {result.evidence_ids.length === 0 ? (
                  <span style={{ color: 'var(--text-3)' }}>无</span>
                ) : (
                  <div className="chip-group">
                    {result.evidence_ids.map((id) => (
                      <EvidenceTag key={id} id={id} />
                    ))}
                  </div>
                )}
              </div>
            </div>
          </div>

          {/* 完整 AI 风险报告 */}
          <div style={{ marginTop: 16, border: '1px solid var(--border)', borderRadius: 'var(--radius)', overflow: 'hidden' }}>
            <div className="card-head" style={{ background: 'var(--surface-alt)' }}>
              <h3>完整 AI 风险报告</h3>
              <span className="hint">Markdown 全文 · 由 Risk Harness 生成（report_path: {result.report_path ?? '-'}）</span>
            </div>
            <div style={{ padding: '20px 24px' }}>
              <MarkdownReport content={result.report} />
            </div>
            <div className="card-head" style={{ borderTop: '1px solid var(--border)', borderBottom: 'none', background: 'var(--surface-alt)' }}>
              <span className="hint" style={{ margin: 0 }}>
                报告由 Risk Harness（risk-orchestrator → coverage-auditor → risk-verifier）生成，风险等级与审核状态均为后端返回的原始值。
              </span>
              <div style={{ marginLeft: 'auto', display: 'flex', gap: 8 }}>
                <button className="btn btn-ghost" style={{ padding: '6px 16px', fontSize: 13 }} onClick={onStart}>
                  重新分析
                </button>
                <button
                  className="btn btn-primary"
                  style={{ padding: '6px 16px', fontSize: 13 }}
                  onClick={handleExportPdf}
                  disabled={pdfLoading}
                >
                  {pdfLoading ? '导出中...' : '导出 PDF'}
                </button>
              </div>
            </div>
          </div>

          {pdfError && (
            <div className="note warn" style={{ marginTop: 12 }}>
              <span>{pdfError}</span>
            </div>
          )}
        </div>
      )}
    </div>
  )
}