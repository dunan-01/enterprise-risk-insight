import type { CompanyProfile } from '../../api/types'
import { fmtDate, fmtWan } from '../../lib/format'

/** 企业概况 Tab：完整工商信息展示（未提供字段显示 "-"） */
export default function OverviewTab({ profile }: { profile: CompanyProfile }) {
  const items: Array<{ k: string; v: string; full?: boolean }> = [
    { k: '企业 ID', v: profile.company_id },
    { k: '数据来源', v: profile.data_type },
    { k: '统一社会信用代码', v: profile.credit_code ?? '-' },
    { k: '法定代表人', v: profile.legal_rep ?? '-' },
    { k: '注册资本（万元）', v: fmtWan(profile.reg_capital) },
    { k: '实缴资本（万元）', v: fmtWan(profile.paid_capital) },
    { k: '成立日期', v: fmtDate(profile.established_date) },
    { k: '企业类型', v: profile.company_type ?? '-' },
    { k: '所属行业', v: profile.industry ?? '-' },
    { k: '登记机关', v: profile.reg_authority ?? '-' },
    { k: '经营状态', v: profile.business_status ?? '-' },
    { k: '上市状态', v: profile.listed_status ?? '-' },
    { k: '联系电话', v: profile.contact_phone ?? '-' },
    { k: '联系邮箱', v: profile.contact_email ?? '-' },
    { k: '企业官网', v: profile.website ?? '-' },
    { k: '数据更新时间', v: fmtDate(profile.update_date) },
    { k: '注册地址', v: profile.reg_address ?? '-', full: true },
    { k: '经营范围', v: profile.business_scope ?? '-', full: true },
  ]

  return (
    <div className="card">
      <div className="card-head">
        <h2>企业概况</h2>
        <span className="hint">GET /api/companies/{profile.company_id} · 完整工商登记信息</span>
      </div>
      <div className="info-grid">
        {items.map((it) => (
          <div key={it.k} className={`info-item ${it.full ? 'full' : ''}`}>
            <div className="k">{it.k}</div>
            <div className="v">{it.v}</div>
          </div>
        ))}
      </div>
    </div>
  )
}