import type { Tone } from '../lib/presentation'
import {
  businessStatusTone,
  caseTypeTone,
  evidenceTone,
  eventTypeTone,
  judicialRoleTone,
  relationTone,
  riskLevelTone,
  verificationTone,
} from '../lib/presentation'

function Tag({ tone, big }: { tone: Tone; big?: boolean }) {
  return <span className={`tag ${tone.className} ${big ? 'big' : ''}`}>{tone.label}</span>
}

/** AI 风险等级徽标（只展示后端返回的 risk_level 原值） */
export function RiskLevelBadge({ raw, big }: { raw: string | null; big?: boolean }) {
  return <Tag tone={riskLevelTone(raw)} big={big} />
}

/** Verification 状态徽标（如实展示后端返回值：PASS=绿 / UNRESOLVED=橙 / 其他=警示） */
export function VerificationBadge({ raw, big }: { raw: string | null; big?: boolean }) {
  return <Tag tone={verificationTone(raw)} big={big} />
}

/** 证据编号徽标（B 工商 / J 司法 / R 关系，按前缀着色） */
export function EvidenceTag({ id }: { id: string }) {
  const tone = evidenceTone(id)
  const prefix = id.slice(0, 1).toUpperCase()
  return (
    <span className={`evidence-tag ${tone.className}`}>
      <span className="ev-prefix">{prefix}</span>
      {id.slice(1)}
      <span style={{ fontWeight: 400, fontSize: 11, opacity: 0.8 }}>
        {prefix === 'B' ? '工商' : prefix === 'J' ? '司法' : prefix === 'R' ? '关系' : ''}
      </span>
    </span>
  )
}

/** 司法案件企业角色标签（原告/被告/被执行人/失信被执行人/担保人…） */
export function JudicialRoleTag({ raw }: { raw: string | null }) {
  return <Tag tone={judicialRoleTone(raw)} />
}

/** 案件类型标签 */
export function CaseTypeTag({ raw }: { raw: string }) {
  return <Tag tone={caseTypeTone(raw)} />
}

/** 工商事件类型标签 */
export function EventTypeTag({ raw }: { raw: string }) {
  return <Tag tone={eventTypeTone(raw)} />
}

/** 关联关系类型标签 */
export function RelationTypeTag({ raw }: { raw: string }) {
  return <Tag tone={relationTone(raw)} />
}

/** 经营状态标签（仅状态着色） */
export function BusinessStatusTag({ raw }: { raw: string | null }) {
  return <Tag tone={businessStatusTone(raw)} />
}