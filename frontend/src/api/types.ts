/**
 * 与后端 API 契约严格一致的类型定义。
 * 契约来源：backend/app/models.py（system-orchestrator 提供的版本）。
 */

// ------------------------------------------------------------
// 统一错误格式：{"detail": {"code": string, "message": string}}
// ------------------------------------------------------------
export interface ApiErrorDetail {
  code: string
  message: string
}

export interface ApiErrorBody {
  detail?: ApiErrorDetail
}

// ------------------------------------------------------------
// GET /api/companies/search?keyword=xxx
// ------------------------------------------------------------
export interface SearchItem {
  company_id: string
  company_name: string
  credit_code: string | null
  legal_rep: string | null
  industry: string | null
  business_status: string | null
  data_type: string
}

export interface SearchResponse {
  keyword: string
  total: number
  items: SearchItem[]
}

// ------------------------------------------------------------
// GET /api/companies/{company_id}
// ------------------------------------------------------------
export interface CompanyProfile {
  company_id: string
  data_type: string
  company_name: string
  credit_code: string | null
  legal_rep: string | null
  reg_capital: number | null // 注册资本（万元）
  paid_capital: number | null // 实缴资本（万元）
  established_date: string | null
  company_type: string | null
  industry: string | null
  reg_address: string | null
  business_scope: string | null
  reg_authority: string | null
  business_status: string | null
  listed_status: string | null
  contact_phone: string | null
  contact_email: string | null
  website: string | null
  update_date: string | null
}

export interface ProfileResponse {
  company_id: string
  profile: CompanyProfile
}

// ------------------------------------------------------------
// GET /api/companies/{company_id}/business-events
// ------------------------------------------------------------
export interface BusinessEvent {
  event_id: string
  company_id: string
  event_type: string
  event_date: string | null
  old_value: string | null
  new_value: string | null
  detail: string | null
  authority: string | null
  penalty_amount: number | null // 处罚金额（元）
  status: string | null
  source: string | null
  create_time: string | null
}

export interface BusinessEventsResponse {
  company_id: string
  total: number
  items: BusinessEvent[]
}

// ------------------------------------------------------------
// GET /api/companies/{company_id}/judicial-events
// ------------------------------------------------------------
export interface JudicialEvent {
  event_id: string
  company_id: string
  case_type: string
  case_number: string | null
  court: string | null
  filing_date: string | null
  close_date: string | null
  cause: string | null
  role: string | null // 企业在本案中的角色：原告/被告/被执行人/担保人等
  amount: number | null // 涉案金额（元）
  result: string | null
  status: string | null
  source: string | null
}

export interface JudicialEventsResponse {
  company_id: string
  total: number
  items: JudicialEvent[]
}

// ------------------------------------------------------------
// GET /api/companies/{company_id}/relations（一跳）
// ------------------------------------------------------------
export interface Relation {
  relation_id: string
  from_company_id: string
  to_company_id: string
  relation_type: string
  relation_detail: string | null
  equity_ratio: number | null // 股权比例（0-1 小数，0.55 = 55%）
  amount: number | null // 涉及金额（元）
  start_date: string | null
  end_date: string | null
  status: string | null
  source: string | null
  update_time: string | null
  from_company_name: string | null
  to_company_name: string | null
}

export interface RelationsResponse {
  company_id: string
  total: number
  items: Relation[]
}

// ------------------------------------------------------------
// POST /api/analysis
// ------------------------------------------------------------
export interface AnalysisResponse {
  company_id: string
  status: string // 恒为 completed
  report: string // Markdown 全文
  verification_status: string | null // PASS / UNRESOLVED
  risk_level: string | null // 风险等级字符串（可能为 null）
  summary: string | null
  evidence_ids: string[] // Bxxx 工商 / Jxxx 司法 / Rxxx 关系
  related_companies: string[] // 报告涉及的关联企业ID（不含目标企业）
  report_path: string | null
  duration_seconds: number
}

// ============================================================
// POST /api/analysis/tasks  异步分析任务
// ============================================================
export interface TaskResponse {
  task_id: string
  company_id: string
  status: 'queued' | 'running' | 'completed' | 'failed' | 'cancelled'
  created_at: string
  started_at: string | null
  finished_at: string | null
  error: string | null
  result: AnalysisResponse | null
  event_count?: number
  last_event_at?: string | null
  current_stage?: string | null
  cancel_reason?: string | null
  replacement_task_id?: string | null
  process_pid?: number | null
  process_alive?: boolean
}

// ============================================================
// V1.1 新增：企业关联关系网络
// ============================================================

export interface NetworkNode {
  company_id: string
  company_name: string
  industry: string | null
  business_status: string | null
  depth: number
}

export interface NetworkEdge {
  relation_id: string
  source: string
  target: string
  relation_type: string
  equity_ratio: number | null
  amount: number | null
  status: string | null
}

export interface RelationNetworkResponse {
  root_company_id: string
  nodes: NetworkNode[]
  edges: NetworkEdge[]
  truncated: boolean
}

// ============================================================
// V1.3 新增：Investigation Trace API
// ============================================================
export interface TraceEvent {
  event_id: string
  sequence: number
  timestamp: string
  type: string
  agent: string
  title: string
  description: string
  company_id: string | null
  company_name: string | null
  tool: string | null
  evidence_ids: string[]
  status: string
}

export interface TraceResponse {
  task_id: string
  company_id: string
  task_status: string
  event_count: number
  events: TraceEvent[]
}

// ============================================================
// V1.4 新增：System Status API
// ============================================================
export interface ActiveTaskInfo {
  task_id: string
  company_id: string
  status: string
  process_pid: number | null
  process_pgid: number | null
  process_alive: boolean
  started_at: string | null
}

export interface SystemStatusResponse {
  active_task: ActiveTaskInfo | null
  harness_process_alive: boolean
  pid: number | null
  project_root: string
}
