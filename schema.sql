-- ============================================================
-- risk.db 建表脚本（含表与字段说明）
-- 说明：SQLite 原生不支持 COMMENT ON，字段含义以 DDL 注释形式维护
-- ============================================================
PRAGMA foreign_keys = ON;

-- ------------------------------------------------------------
-- 1. companies 企业基本信息表：每家企业一条记录，全局主数据
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS companies (
    company_id       TEXT PRIMARY KEY,              -- 企业唯一ID（主键，如 C001）
    data_type        TEXT NOT NULL DEFAULT 'simulated', -- 数据来源类型（simulated=模拟构造 / real=真实公开数据）
    company_name     TEXT NOT NULL,                 -- 企业名称
    credit_code      TEXT UNIQUE,                   -- 统一社会信用代码（唯一）
    legal_rep        TEXT,                          -- 法定代表人
    reg_capital      REAL,                          -- 注册资本（万元）
    paid_capital     REAL,                          -- 实缴资本（万元）
    established_date TEXT,                          -- 成立日期（YYYY-MM-DD）
    company_type     TEXT,                          -- 企业类型（如 有限责任公司/有限合伙）
    industry         TEXT,                          -- 所属行业（国民经济行业分类）
    reg_address      TEXT,                          -- 注册地址
    business_scope   TEXT,                          -- 经营范围
    reg_authority    TEXT,                          -- 登记机关
    business_status  TEXT,                          -- 经营状态（存续/在业/吊销/注销/迁出）
    listed_status    TEXT,                          -- 上市状态（上市/未上市/新三板等）
    contact_phone    TEXT,                          -- 联系电话
    contact_email    TEXT,                          -- 联系邮箱
    website          TEXT,                          -- 企业官网
    update_date      TEXT                           -- 数据更新时间
);

-- ------------------------------------------------------------
-- 2. business_events 经营信息表：企业工商经营层面的动态事件
--    含：法人变更、股东变更、经营异常、行政处罚、地址变更、吊销等
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS business_events (
    event_id       TEXT PRIMARY KEY,                -- 事件唯一ID（主键）
    company_id     TEXT NOT NULL REFERENCES companies(company_id),  -- 所属企业ID（外键→companies）
    event_type     TEXT NOT NULL,                   -- 事件类型（法定代表人变更/股东变更/经营异常/行政处罚/注册地址变更/注册资本变更/吊销/注销等）
    event_date     TEXT,                            -- 事件发生日期
    old_value      TEXT,                            -- 变更前值 / 原记录内容（非变更类事件可空）
    new_value      TEXT,                            -- 变更后值 / 新记录内容（非变更类事件可空）
    detail         TEXT,                            -- 事件详细描述（原因、经过等）
    authority      TEXT,                            -- 登记机关 / 处罚机关
    penalty_amount REAL,                            -- 处罚金额（元，仅行政处罚类事件有值）
    status         TEXT,                            -- 处理状态（已完成/未处理/已移出/已缴纳等）
    source         TEXT,                            -- 数据来源（工商登记/信用公示系统/处罚公示等）
    create_time    TEXT                             -- 记录入库时间
);

-- ------------------------------------------------------------
-- 3. judicial_events 司法信息表：企业涉诉及司法执行事件
--    含：开庭公告、裁判文书、被执行人、失信、限高、股权冻结、破产等
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS judicial_events (
    event_id    TEXT PRIMARY KEY,                   -- 事件唯一ID（主键）
    company_id  TEXT NOT NULL REFERENCES companies(company_id),  -- 所属企业ID（外键→companies）
    case_type   TEXT NOT NULL,                      -- 案件类型（被执行人/失信被执行人/限制消费令/开庭公告/裁判文书/股权冻结/破产案件等）
    case_number TEXT,                               -- 案号（如 (2023)粤01执6789号）
    court       TEXT,                               -- 受理法院
    filing_date TEXT,                               -- 立案 / 公告日期
    close_date  TEXT,                               -- 结案日期（未结案为空）
    cause       TEXT,                               -- 案由（如 借款合同纠纷）
    role        TEXT,                               -- 企业在本案中的角色（原告/被告/被执行人/债务人/担保人等）
    amount      REAL,                               -- 涉案金额（元）
    result      TEXT,                               -- 审理结果 / 执行情况
    status      TEXT,                               -- 案件状态（已结案/执行中/已列入/冻结中/审查中等）
    source      TEXT                                -- 数据来源（裁判文书网/执行信息公开网/信用中国等）
);

-- ------------------------------------------------------------
-- 4. relations 企业关系表：企业之间的关联关系
--    含：股权、对外投资、共同法人、共同股东、担保、母子公司等
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS relations (
    relation_id     TEXT PRIMARY KEY,               -- 关系唯一ID（主键）
    from_company_id TEXT NOT NULL REFERENCES companies(company_id),  -- 关系主体企业ID（外键→companies）
    to_company_id   TEXT NOT NULL REFERENCES companies(company_id),  -- 关系客体企业ID（外键→companies）
    relation_type   TEXT NOT NULL,                  -- 关系类型（股权/对外投资/共同法人/共同股东/担保/母子公司等）
    relation_detail TEXT,                           -- 关系具体描述（如 某公司持有某公司55%股权）
    equity_ratio    REAL,                           -- 股权比例（统一使用 0-1 小数，如 0.55 表示 55%）
    amount          REAL,                           -- 涉及金额（元，投资额/担保额等）
    start_date      TEXT,                           -- 关系起始日期
    end_date        TEXT,                           -- 关系结束日期（担保到期日；存续中为空）
    status          TEXT,                           -- 关系状态（存续/已解除/担保中/已退出/股权已冻结等）
    source          TEXT,                           -- 数据来源（工商登记/公开数据交叉比对/信用公示等）
    update_time     TEXT                            -- 记录更新时间
);

-- 查询性能索引
CREATE INDEX IF NOT EXISTS idx_business_events_company ON business_events(company_id);
CREATE INDEX IF NOT EXISTS idx_business_events_type    ON business_events(event_type);
CREATE INDEX IF NOT EXISTS idx_judicial_events_company ON judicial_events(company_id);
CREATE INDEX IF NOT EXISTS idx_judicial_events_type    ON judicial_events(case_type);
CREATE INDEX IF NOT EXISTS idx_relations_from          ON relations(from_company_id);
CREATE INDEX IF NOT EXISTS idx_relations_to            ON relations(to_company_id);
CREATE INDEX IF NOT EXISTS idx_relations_type          ON relations(relation_type);

-- ------------------------------------------------------------
-- 5. public_opinion_events 舆情信息表：企业舆情事件
--    含：产品质量、合同纠纷、环境问题、劳动争议、融资消息、项目中标、市场传闻等
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public_opinion_events (
    event_id            TEXT PRIMARY KEY,               -- 事件唯一ID（Pxxx）
    company_id          TEXT NOT NULL REFERENCES companies(company_id),
    publish_date        TEXT,                              -- 发布日期
    topic               TEXT,                              -- 主题
    sentiment           TEXT,                              -- 情感倾向（positive/neutral/negative）
    source_type         TEXT,                              -- 媒体类型
    source_name         TEXT,                              -- 来源名称
    title               TEXT,                              -- 标题
    summary             TEXT,                              -- 摘要
    verification_status TEXT,                              -- 核实状态（verified/partially_verified/unverified）
    response_status     TEXT,                              -- 企业回应状态
    data_type           TEXT NOT NULL DEFAULT 'simulated'  -- 数据来源类型
);

-- ------------------------------------------------------------
-- 6. financial_reports 财务报告表：企业连续年度财务数据
--    含：营收、净利润、资产负债、现金流、审计意见及计算指标
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS financial_reports (
    report_id            TEXT PRIMARY KEY,               -- 报告唯一ID（Fxxx）
    company_id           TEXT NOT NULL REFERENCES companies(company_id),
    period               TEXT,                              -- 报告期（如 2023FY）
    report_date          TEXT,                              -- 报告日期
    revenue              REAL,                              -- 营业收入（元）
    net_profit           REAL,                              -- 净利润（元）
    total_assets         REAL,                              -- 总资产（元）
    total_liabilities    REAL,                              -- 总负债（元）
    current_assets       REAL,                              -- 流动资产（元）
    current_liabilities  REAL,                              -- 流动负债（元）
    operating_cash_flow  REAL,                              -- 经营现金流（元）
    accounts_receivable  REAL,                              -- 应收账款（元）
    audit_opinion        TEXT,                              -- 审计意见
    currency             TEXT DEFAULT 'CNY',                -- 币种
    data_type            TEXT NOT NULL DEFAULT 'simulated'  -- 数据来源类型
);

-- ------------------------------------------------------------
-- 7. recruitment_events 招聘信息表：企业招聘动态事件
--    含：招聘岗位、人数、薪资、状态、招聘类型等弱经营信号
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS recruitment_events (
    event_id           TEXT PRIMARY KEY,               -- 事件唯一ID（Hxxx）
    company_id         TEXT NOT NULL REFERENCES companies(company_id),
    publish_date       TEXT,                              -- 发布日期
    event_type         TEXT,                              -- 招聘事件类型
    position_category  TEXT,                              -- 岗位类别
    position_name      TEXT,                              -- 岗位名称
    planned_headcount  INTEGER,                           -- 计划招聘人数
    salary_min         REAL,                              -- 最低薪资（元）
    salary_max         REAL,                              -- 最高薪资（元）
    location           TEXT,                              -- 工作地点
    status             TEXT,                              -- 状态
    description        TEXT,                              -- 说明
    data_type          TEXT NOT NULL DEFAULT 'simulated'  -- 数据来源类型
);

-- 查询性能索引
CREATE INDEX IF NOT EXISTS idx_po_company ON public_opinion_events(company_id);
CREATE INDEX IF NOT EXISTS idx_po_sentiment ON public_opinion_events(sentiment);
CREATE INDEX IF NOT EXISTS idx_fr_company ON financial_reports(company_id);
CREATE INDEX IF NOT EXISTS idx_fr_period ON financial_reports(period);
CREATE INDEX IF NOT EXISTS idx_re_company ON recruitment_events(company_id);
CREATE INDEX IF NOT EXISTS idx_re_type ON recruitment_events(event_type);
