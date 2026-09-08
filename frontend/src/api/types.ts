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
// GET /api/companies/{company_id}/public-opinion
// ------------------------------------------------------------
export interface PublicOpinionEvent {
  event_id: string
  company_id: string
  publish_date: string | null
  topic: string | null
  sentiment: string | null // positive / neutral / negative
  source_type: string | null
  source_name: string | null
  title: string | null
  summary: string | null
  verification_status: string | null // verified / partially_verified / unverified
  response_status: string | null
  data_type: string
}

export interface PublicOpinionEventsResponse {
  company_id: string
  total: number
  items: PublicOpinionEvent[]
}

// ------------------------------------------------------------
// GET /api/companies/{company_id}/financial-reports
// ------------------------------------------------------------
export interface FinancialReport {
  report_id: string
  company_id: string
  period: string | null // e.g. "2023FY"
  report_date: string | null
  revenue: number | null
  net_profit: number | null
  total_assets: number | null
  total_liabilities: number | null
  current_assets: number | null
  current_liabilities: number | null
  operating_cash_flow: number | null
  accounts_receivable: number | null
  audit_opinion: string | null // unqualified / qualified
  currency: string | null
  data_type: string
  // 计算指标
  debt_ratio: number | null
  current_ratio: number | null
  net_margin: number | null
  revenue_yoy: number | null
  profit_yoy: number | null
}

export interface FinancialReportsResponse {
  company_id: string
  total: number
  items: FinancialReport[]
}

// ------------------------------------------------------------
// GET /api/companies/{company_id}/recruitment-events
// ------------------------------------------------------------
export interface RecruitmentEvent {
  event_id: string
  company_id: string
  publish_date: string | null
  event_type: string | null
  position_category: string | null
  position_name: string | null
  planned_headcount: number | null
  salary_min: number | null
  salary_max: number | null
  location: string | null
  status: string | null
  description: string | null
  data_type: string
}

export interface RecruitmentEventsResponse {
  company_id: string
  total: number
  items: RecruitmentEvent[]
}

// ------------------------------------------------------------
// POST /api/analysis
// ------------------------------------------------------------
/** RiskScoring 中 own_risk 的结构 */
export interface OwnRisk {
  score: number | null
  level: string | null
  level_status: string
}

/** RiskScoring 中 comprehensive_risk 的结构 */
export interface ComprehensiveRisk {
  score: number | null
  level: string | null
}

/** RiskScoring 结构（V2.1 新增，V2.3B.2 扩展） */
export interface RiskScoringData {
  risk_score: number
  risk_level: string
  triggered_rules: Record<string, any>[]
  hard_rule_hits: Record<string, any>[]
  dimension_scores: Record<string, number>
  evidence_ids: string[]
  total_evidence_count: number
  own_risk?: OwnRisk | null
  relationship_exposure?: RelationshipExposure | null
  comprehensive_risk?: ComprehensiveRisk | null
}

export interface AnalysisResponse {
    task_id?: string | null
    company_id: string
    status: string // 恒为 completed
    report: string // Markdown 全文
    verification_status: string | null // PASS / UNRESOLVED
    risk_level: string | null // 风险等级字符串（可能为 null）
    summary: string | null
    evidence_ids: string[] // Bxxx 工商 / Jxxx 司法 / Rxxx 关系 / Pxxx 舆情 / Fxxx 财务 / Hxxx 招聘
    related_companies: string[] // 报告涉及的关联企业ID（不含目标企业）
    report_path: string | null
    duration_seconds: number
    analysis_version: string | null // 分析版本（如 "v2-multisource"）
    data_sources: string[] // 使用的数据源列表
    risk_scoring?: RiskScoringData | null
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

// ============================================================
// V1.4 新增：Evidence Detail API
// ============================================================
export interface EvidenceResponse {
  evidence_id: string
  evidence_type:
    | 'business'
    | 'judicial'
    | 'relation'
    | 'public_opinion'
    | 'financial'
    | 'recruitment'
  company_id: string | null
  company_name: string | null
  from_company_id?: string | null
  from_company_name?: string | null
  to_company_id?: string | null
  to_company_name?: string | null
  data: Record<string, any>
  source: string | null
}

// ============================================================
// V1.6 新增：Investigation Network API
// ============================================================

export interface InvestigationNode {
  company_id: string
  company_name: string
  industry: string | null
  business_status: string | null
  depth: number
  is_root: boolean
  investigation_status: 'root' | 'investigated' | 'discovered' | 'not_investigated'
  investigation_order: number | null
  first_investigated_at: string | null
  evidence_ids: string[]
  evidence_count: number
  supplementary: boolean
  risk_level: string | null
  risk_tags: string[]
}

export interface InvestigationEdge {
  relation_id: string
  source: string
  target: string
  relation_type: string
  equity_ratio: number | null
  amount: number | null
  status: string | null
  investigation_status: 'traversed' | 'discovered' | 'not_used'
  first_used_at: string | null
  supplementary: boolean
  evidence_referenced: boolean
  investigation_reason: string | null
}

export interface InvestigationNetworkStats {
  total_network_nodes: number
  investigated_nodes: number
  discovered_nodes: number
  uninvestigated_nodes: number
  investigated_edges: number
  total_evidence: number
}

export interface InvestigationNetworkResponse {
  task_id: string | null
  company_id: string
  task_status: string
  nodes: InvestigationNode[]
  edges: InvestigationEdge[]
  stats: InvestigationNetworkStats
}

// ============================================================
// V2.3B.2 新增：Relationship Exposure 传导风险类型
// ============================================================

/** 单条传导路径信息 */
export interface TransmissionPath {
  path: string[]
  depth: number
  relation_ids: string[]
  relation_types: string[]
  transmitted_score: number
  relation_type_factor: number
  target_role_factor: number
  depth_factor: number
  target_role: string | null
  transmission_reasons: string[]
}

/** 单个关联企业的 Exposure Contribution */
export interface CompanyExposureContribution {
  company_id: string
  company_name: string
  own_score: number
  own_level: string
  strongest_path: TransmissionPath | null
  transmitted_score: number
  transmission_factors: {
    relation_type_factor: number
    target_role_factor: number
    depth_factor: number
  } | Record<string, never>
  all_paths: TransmissionPath[]
  transmission_reasons: string[]
}

/** Relationship Exposure 结构 */
export interface RelationshipExposure {
  status: string // "CALIBRATED_V1" | "NOT_CALIBRATED"
  score: number | null
  level: string | null
  level_status: string // "CALIBRATED" | "NOT_CALIBRATED"
  company_contributions: CompanyExposureContribution[]
  transmission_version: string | null
  transmission_config_hash: string | null
  related_company_profiles?: Record<string, any>[] // V2.3B.1 兼容
}
