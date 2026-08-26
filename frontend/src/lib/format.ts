/**
 * 展示层格式化工具。纯展示逻辑，不含任何风险判断。
 */

/** 空值统一显示 "-" */
export function fmtOrDash(v: unknown): string {
  if (v === null || v === undefined || v === '') return '-'
  return String(v)
}

/** 金额（元）→ 人民币格式化，null → "-" */
export function fmtMoney(v: number | null | undefined): string {
  if (v === null || v === undefined) return '-'
  return new Intl.NumberFormat('zh-CN', {
    style: 'currency',
    currency: 'CNY',
    maximumFractionDigits: 0,
  }).format(v)
}

/** 万元 → "xxx 万元" */
export function fmtWan(v: number | null | undefined): string {
  if (v === null || v === undefined) return '-'
  return `${new Intl.NumberFormat('zh-CN').format(v)} 万元`
}

/** 股权比例（0-1 小数）→ 百分比字符串，null → "-" */
export function fmtPercent(ratio: number | null | undefined): string {
  if (ratio === null || ratio === undefined) return '-'
  const pct = ratio * 100
  return `${pct % 1 === 0 ? pct.toFixed(0) : pct.toFixed(1)}%`
}

/** 秒 → "X 分 X 秒" / "X 秒" */
export function fmtDuration(seconds: number): string {
  const s = Math.max(0, Math.round(seconds))
  const m = Math.floor(s / 60)
  const rest = s % 60
  if (m <= 0) return `${rest} 秒`
  return `${m} 分 ${rest} 秒`
}

/** 毫秒时间差 → "X 分 X 秒"（用于分析等待计时） */
export function fmtElapsed(startedAt: number, now: number): string {
  const s = Math.max(0, Math.floor((now - startedAt) / 1000))
  const m = Math.floor(s / 60)
  const rest = s % 60
  if (m <= 0) return `${rest} 秒`
  return `${m} 分 ${rest} 秒`
}

/** 日期字符串截断为 YYYY-MM-DD（后端可能带时间） */
export function fmtDate(v: string | null | undefined): string {
  if (!v) return '-'
  return v.slice(0, 10)
}

/** 行业 / 经营状态等短字段截断 */
export function truncate(v: string | null | undefined, max = 24): string {
  if (!v) return '-'
  return v.length > max ? `${v.slice(0, max)}…` : v
}