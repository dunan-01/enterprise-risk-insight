# RISK-FOCUSED REPORT TEMPLATE — Verification Report

Date: 2026-09-04
Scope: STANDARDIZE RISK-FOCUSED REPORT TEMPLATE (B/J/R/P/F/H)
Constraint: risk.db / P-F-H seed data / relation network / task lifecycle / investigation trace untouched.
Changed only: Final Report Template + risk-orchestrator report requirements + risk-verifier quality checks
(+ harness_adapter prompt + _split_report fix + timeout 1200s→3600s as supporting change).

## 1. Deliverables

1. `templates/risk_report_template.md` (new, 5.3K)
   Fixed 8-section structure:
   一、风险结论摘要 / 二、企业自身主要风险 / 三、关联企业及风险传导 /
   四、多源证据综合分析 / 五、风险缓释因素与矛盾信号 /
   六、综合风险判断 / 七、证据限制与不确定性 / 八、关键证据引用
2. `.opencode/agents/risk-orchestrator.md`
   - Added INVESTIGATION COVERAGE ≠ REPORT CONTENT VOLUME decoupling principle
   - Added A/B/C/D risk-relevance filter (Material / Supporting-Mitigating / Context / Irrelevant)
   - Step 2 mandates strict template order, compressed basic info (name+ID+time+version+sources only),
     trend-only finance, screened opinion/recruitment, Multi-Source Reasoning (not Listing)
   - Coverage-auditor scope clarified: checks missing investigation only, never demands listing everything
3. `.opencode/agents/risk-verifier.md`
   - Added Rule 10 REPORT_FOCUS with 7 sub-checks (10.1–10.7):
     archive-info bloat, raw-table copy, opinion/recruitment listing,
     normal-change-as-risk, missing-Evidence, duplication, conclusion-evidence mismatch, template deviation
   - FAIL on any REPORT_FOCUS item forces VERDICT: REVISE; SUMMARY gains `REPORT_FOCUS: PASS/FAIL`
4. `backend/app/harness_adapter.py` (supporting)
   - ANALYSIS_PROMPT_TEMPLATE now mandates template order, compressed basic info,
     trend-only finance, key-evidence-only, and VERIFICATION_STATUS as final line
   - `_split_report` fixed to handle VERIFICATION_STATUS-at-end (new orchestrator output order);
     previously it returned empty report when status was last line
   - DEFAULT_HARNESS_TIMEOUT 1200→3600 (template + verifier rounds need 30–50 min for complex cases)

## 2. Validation runs (new template)

### C001 (low-self-risk, association-driven) — task-860c59ce-1788488533
- status: completed, verification_status: PASS, duration: 146.85s, events: 62
- risk_level: 中高风险 (self clean, C002-driven)
- report_final.md: 8.9K, analysis_version: v2-multisource, 6 sources present
- Sec 2 correctly short-circuits: 2.1/2.2/2.3/2.4/2.5 each state 未发现… (6× 未发现, no forced risks)
- Normal B001/B002 changes explicitly de-risked, not listed as risks
- Finance as trend language + F001/F002/F003 bindings, no year-by-year raw table
- P: 6 IDs (negatives P004/P006/P008 + mitigating P003/P009/P029), not full listing
- H: 5 IDs (C002 freeze/withdraw H026/H005/H004 + mitigating expansion H001/H003)
- C007-style B012 handling N/A (0 mentions); order of 8 headings verified in-order

### C007 (high-risk) — task-e1491ebe-1788488533
- status: completed, verification_status: PASS, duration: 340.69s, events: 60
- risk_level: 高风险
- report_final.md: 11K, analysis_version: v2-multisource, 6 sources present
- B012 explicitly: 注册地址变更（B012）为普通工商变更，不单独作为风险 → PASS
- J008/J010 same-amount same-court: explicitly NOT merged, no causal overclaim (verifier REVISE round applied)
- J012/J013 plaintiff cases correctly excluded from negative risk
- Finance as trend (持续下降/由盈转亏/由正转负) + F019/F020/F021, no raw table
- P: 7 IDs (P017/P018/P019 negatives + P030 unverified-as-signal-only + mitigating P015/P020/P021)
- H: 4 IDs (H015/H016 main contraction + H027 weak-aux + H017 remediation in mitigation)
- Order of 8 headings verified in-order; trend language present

## 3. Metric-by-metric verdicts

- FIXED_REPORT_TEMPLATE: both reports contain all 8 headings in exact order → PASS
- RISK_RELEVANCE_FILTER: A/B/C/D applied (B012 de-risked, plaintiff J excluded, H027 weak-aux, P030 signal-only) → PASS
- BASIC_INFO_MINIMIZED: no 联系电话/邮箱/注册资本/成立日期/信用代码/经营范围 leaks in either report → PASS
- RAW_FINANCIAL_TABLE_REMOVED: trend-only language, no year-by-year full table (regex check negative) → PASS
- RAW_OPINION_LIST_REMOVED: C001 6 P / C007 7 P, negatives + mitigating only → PASS
- RAW_RECRUITMENT_LIST_REMOVED: C001 5 H / C007 4 H, freeze/reduction + mitigating only → PASS
- MULTISOURCE_REASONING: Sec 四 present in both, 相互支持/印证/补充 language, no B/J/P/F/H re-listing → PASS
- MITIGATING_EVIDENCE_SUPPORTED: Sec 五 present in both (C001: F001-3/P003/H001/P029; C007: C006/C008/P020/H017) → PASS
- KEY_EVIDENCE_ONLY: Sec 八 selective (C001 14 items vs 38 queried evidence_ids; C007 16 items vs 36 queried) → PASS
- REPORT_FOCUS_VERIFIER: risk-verifier.md contains 12× REPORT_FOCUS hits incl. 10.1–10.7 + SUMMARY field; orchestrator references template → PASS
- EVIDENCE_CLICK_REGRESSION: 12/12 HTTP 200 via /api/evidence — B011, J008, R007, P019, F021, H015, B004, J001, R001, P003, F001, H001 (all six types B/J/R/P/F/H, both companies) → PASS

## 4. Known minor impurity (non-blocking)

- report/report_final.md for these two runs include ~150–190 chars of orchestrator process chatter
  before `# 企业关联风险调查报告` (pre-existing harness behavior: process_text mixed into report field).
  All 8 template sections from `#` onward are intact and in order; no metric affected.
  Optional follow-up: strip preamble in _save_run_records (out of scope for this task).

## 5. Final output (required)

FIXED_REPORT_TEMPLATE: PASS
RISK_RELEVANCE_FILTER: PASS
BASIC_INFO_MINIMIZED: PASS
RAW_FINANCIAL_TABLE_REMOVED: PASS
RAW_OPINION_LIST_REMOVED: PASS
RAW_RECRUITMENT_LIST_REMOVED: PASS
MULTISOURCE_REASONING: PASS
MITIGATING_EVIDENCE_SUPPORTED: PASS
KEY_EVIDENCE_ONLY: PASS
REPORT_FOCUS_VERIFIER: PASS
EVIDENCE_CLICK_REGRESSION: PASS
