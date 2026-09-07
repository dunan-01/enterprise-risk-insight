import { useCallback, useEffect, useState } from 'react'
import { api, ApiError } from '../../api/client'
import type { FinancialReport } from '../../api/types'
import { EvidenceTag } from '../../components/Badges'
import { EmptyState, ErrorBlock, LoadingState } from '../../components/States'

/** 万元格式化 */
function fmtWan(value: number | null | undefined): string {
  if (value === null || value === undefined) return '-'
  return `${(value / 10000).toLocaleString('zh-CN', { maximumFractionDigits: 2 })} 万`
}

/** 审计意见标签颜色 */
function AuditOpinionTag({ raw }: { raw: string | null }) {
  if (!raw) return <span className="tag tone-muted">-</span>
  const color = raw === 'unqualified' ? '#10b981' : '#f59e0b'
  const label = raw === 'unqualified' ? '标准无保留' : '保留意见'
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

/** 财务信息 Tab */
export default function FinancialReportsTab({
  companyId,
  onEvidenceClick,
}: {
  companyId: string
  onEvidenceClick?: (id: string) => void
}) {
  const [state, setState] = useState<'loading' | 'done' | 'error'>('loading')
  const [error, setError] = useState<ApiError | null>(null)
  const [reports, setReports] = useState<FinancialReport[]>([])

  const load = useCallback(async () => {
    setState('loading')
    setError(null)
    try {
      const res = await api.financialReports(companyId)
      setReports(res.items)
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
        <h2>财务信息</h2>
        <span className="hint">
          财务报告 / 资产负债 · GET /api/companies/{companyId}/financial-reports
        </span>
      </div>

      {state === 'loading' && <LoadingState text="财务信息加载中…" />}

      {state === 'error' && (
        <div className="card-body">
          <ErrorBlock
            title="财务信息加载失败"
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
              共 <b>{reports.length}</b> 份财务报告
            </span>
          </div>
          {reports.length === 0 ? (
            <EmptyState title="暂无财务报告" desc="该企业目前没有财务报告数据。" />
          ) : (
            <div className="table-wrap">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>年份</th>
                    <th>营业收入</th>
                    <th>净利润</th>
                    <th>总资产</th>
                    <th>总负债</th>
                    <th>资产负债率</th>
                    <th>流动比率</th>
                    <th>净利率</th>
                    <th>经营现金流</th>
                    <th>审计意见</th>
                    <th>Evidence</th>
                  </tr>
                </thead>
                <tbody>
                  {reports.map((rp) => (
                    <tr key={rp.report_id}>
                      <td className="mono">{rp.period ?? '-'}</td>
                      <td className="num">{fmtWan(rp.revenue)}</td>
                      <td className="num" style={rp.net_profit != null && rp.net_profit < 0 ? { color: '#ef4444', fontWeight: 600 } : undefined}>
                        {fmtWan(rp.net_profit)}
                      </td>
                      <td className="num">{fmtWan(rp.total_assets)}</td>
                      <td className="num">{fmtWan(rp.total_liabilities)}</td>
                      <td className="num">
                        {rp.debt_ratio != null ? `${(rp.debt_ratio * 100).toFixed(1)}%` : '-'}
                      </td>
                      <td className="num">
                        {rp.current_ratio != null ? rp.current_ratio.toFixed(2) : '-'}
                      </td>
                      <td className="num">
                        {rp.net_margin != null ? `${(rp.net_margin * 100).toFixed(1)}%` : '-'}
                      </td>
                      <td className="num">{fmtWan(rp.operating_cash_flow)}</td>
                      <td>
                        <AuditOpinionTag raw={rp.audit_opinion} />
                      </td>
                      <td>
                        <EvidenceTag id={rp.report_id} onClick={onEvidenceClick} />
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
