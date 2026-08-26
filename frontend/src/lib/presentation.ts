/**
 * 展示层分类映射：为后端返回的原始字符串提供颜色/样式标签。
 *
 * ⚠️ 重要约束：本文件只做「展示分类」，绝不推导/计算风险等级。
 * 风险等级一律展示后端返回的 risk_level 原值，这里仅按已知关键词
 * 选择徽标颜色（未知值回退中性灰并原样展示）。
 */

export interface Tone {
  className: string
  label: string
}

// ------------------------------------------------------------
// 风险等级徽标（仅按后端返回字符串匹配颜色，未知值原样展示）
// ------------------------------------------------------------
export function riskLevelTone(raw: string | null): Tone {
  if (!raw) return { className: 'tone-muted', label: '未解析' }
  if (raw.includes('严重')) return { className: 'tone-severe', label: raw }
  if (raw.includes('高')) return { className: 'tone-high', label: raw }
  if (raw.includes('中')) return { className: 'tone-mid', label: raw }
  if (raw.includes('低')) return { className: 'tone-low', label: raw }
  return { className: 'tone-muted', label: raw }
}

// ------------------------------------------------------------
// Verification 状态徽标：必须如实展示后端返回的值
// ------------------------------------------------------------
export function verificationTone(raw: string | null): Tone {
  if (!raw) return { className: 'tone-muted', label: '未返回' }
  if (raw === 'PASS') return { className: 'tone-pass', label: raw }
  if (raw === 'UNRESOLVED') return { className: 'tone-unresolved', label: raw }
  // 其他任何值：如实展示，用警示色
  return { className: 'tone-unresolved', label: raw }
}

// ------------------------------------------------------------
// 司法案件角色标签（原告/被告/被执行人/失信被执行人/担保人等）
// ------------------------------------------------------------
export function judicialRoleTone(raw: string | null): Tone {
  if (!raw) return { className: 'tone-muted', label: '-' }
  if (raw.includes('失信')) return { className: 'tone-severe', label: raw }
  if (raw.includes('被执行')) return { className: 'tone-high', label: raw }
  if (raw.includes('限制消费')) return { className: 'tone-high', label: raw }
  if (raw.includes('冻结')) return { className: 'tone-high', label: raw }
  if (raw.includes('担保') || raw.includes('保证')) return { className: 'tone-purple', label: raw }
  if (raw.includes('债务')) return { className: 'tone-high', label: raw }
  if (raw.includes('被告')) return { className: 'tone-mid', label: raw }
  if (raw.includes('原告')) return { className: 'tone-brand', label: raw }
  return { className: 'tone-muted', label: raw }
}

/** 案件类型标签（失信/被执行/限高等红色系） */
export function caseTypeTone(raw: string): Tone {
  if (raw.includes('失信')) return { className: 'tone-severe', label: raw }
  if (raw.includes('被执行') || raw.includes('限制消费') || raw.includes('冻结') || raw.includes('破产'))
    return { className: 'tone-high', label: raw }
  if (raw.includes('开庭') || raw.includes('裁判')) return { className: 'tone-brand', label: raw }
  return { className: 'tone-neutral', label: raw }
}

/** 是否为高风险类司法角色（用于行级视觉强调） */
export function isJudicialRiskRole(raw: string | null): boolean {
  if (!raw) return false
  return /失信|被执行|限制消费|冻结|破产/.test(raw)
}

// ------------------------------------------------------------
// 工商事件类型标签（经营异常/行政处罚红色系，变更类蓝色系）
// ------------------------------------------------------------
export function eventTypeTone(raw: string): Tone {
  if (raw.includes('行政处罚') || raw.includes('处罚')) return { className: 'tone-high', label: raw }
  if (raw.includes('经营异常')) return { className: 'tone-mid', label: raw }
  if (raw.includes('吊销')) return { className: 'tone-severe', label: raw }
  if (raw.includes('注销')) return { className: 'tone-muted', label: raw }
  if (raw.includes('变更')) return { className: 'tone-brand', label: raw }
  return { className: 'tone-neutral', label: raw }
}

/** 是否为需强调的工商事件（行政处罚/经营异常/吊销/注销） */
export function isEmphasizedEvent(raw: string): boolean {
  return /行政处罚|经营异常|吊销|注销/.test(raw)
}

// ------------------------------------------------------------
// 关联关系类型：颜色（供表格标签与关系图边共用）
// ------------------------------------------------------------
export const RELATION_TYPE_COLORS: Record<string, string> = {
  股权: '#2563eb',
  对外投资: '#0ea5e9',
  担保: '#f59e0b',
  共同法人: '#8b5cf6',
  共同股东: '#10b981',
  母子公司: '#06b6d4',
  实控人: '#ec4899',
}

export function relationTone(raw: string): Tone {
  if (raw.includes('担保')) return { className: 'tone-mid', label: raw }
  if (raw.includes('股权') || raw.includes('母子公司') || raw.includes('实控'))
    return { className: 'tone-brand', label: raw }
  if (raw.includes('投资')) return { className: 'tone-cyan', label: raw }
  if (raw.includes('共同法人')) return { className: 'tone-purple', label: raw }
  if (raw.includes('共同股东')) return { className: 'tone-low', label: raw }
  return { className: 'tone-neutral', label: raw }
}

export function relationColor(raw: string): string {
  return RELATION_TYPE_COLORS[raw] ?? '#64748b'
}

// ------------------------------------------------------------
// 证据编号前缀：B=工商 / J=司法 / R=关系
// ------------------------------------------------------------
export function evidenceTone(id: string): Tone {
  const prefix = id.slice(0, 1).toUpperCase()
  if (prefix === 'B') return { className: 'tone-brand', label: `${id} 工商` }
  if (prefix === 'J') return { className: 'tone-high', label: `${id} 司法` }
  if (prefix === 'R') return { className: 'tone-purple', label: `${id} 关系` }
  return { className: 'tone-muted', label: id }
}

// ------------------------------------------------------------
// 经营状态（存续/在业/吊销/注销/迁出）—— 仅状态着色，与风险无关
// ------------------------------------------------------------
export function businessStatusTone(raw: string | null): Tone {
  if (!raw) return { className: 'tone-muted', label: '-' }
  if (raw.includes('存续') || raw.includes('在业')) return { className: 'tone-low', label: raw }
  if (raw.includes('吊销')) return { className: 'tone-severe', label: raw }
  if (raw.includes('注销')) return { className: 'tone-muted', label: raw }
  if (raw.includes('迁出')) return { className: 'tone-mid', label: raw }
  return { className: 'tone-neutral', label: raw }
}