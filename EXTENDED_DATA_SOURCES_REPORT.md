# Extended Data Sources Report

**System:** 企业关联风险智能洞察系统 (Enterprise Risk Intelligence System)
**Version:** V2.0 — Extended Data Sources
**Date:** 2026-09-03
**Status:** PASS

---

## Summary

Extended the existing risk system (C001-C010) from 3 data source types (B/J/R) to 6 types (B/J/R/P/F/H):
- **B**usiness events (工商事件) — existing, unchanged
- **Judicial events (司法事件)** — existing, unchanged
- **Relations (企业关系)** — existing, unchanged
- **Public Opinion Events (舆情事件)** — **NEW**
- **Financial Reports (财务报告)** — **NEW**
- **Recruitment Events (招聘事件)** — **NEW**

---

## PUBLIC_OPINION_TABLE: PASS

| Metric | Value |
|--------|-------|
| Total records | 35 |
| Companies covered | C001–C010 (all) |
| Records per company | 2–5 |
| Sentiment distribution | positive / neutral / negative |
| Verification status distribution | verified / partially_verified / unverified |
| Data type | simulated |

### Key Design Points
- Not all negative: each company has a mix of positive/neutral/negative sentiment
- Contradictory signals included (e.g., C002 has high judicial risk but also won a major contract; C007 has multiple enforcement actions but also won a municipal project)
- Unverified rumors (e.g., P012 "市场传闻博远数字科技存在资金压力") explicitly marked as `unverified`
- All source names use simulated names only (模拟财经媒体01, 模拟行业媒体02, 模拟地方媒体03)

---

## FINANCIAL_REPORT_TABLE: PASS

| Metric | Value |
|--------|-------|
| Total records | 30 |
| Companies covered | C001–C010 (all) |
| Periods per company | 2023FY, 2024FY, 2025FY (3 years) |
| Calculated metrics | debt_ratio, current_ratio, net_margin, revenue_yoy, profit_yoy |
| Currency | CNY (元) |
| Data type | simulated |

### Trend Types Designed
| Type | Company | Description |
|------|---------|-------------|
| A (Stable Growth) | C001, C004, C006 | Revenue and profit grow steadily, cash flow normal |
| B (Revenue Up, Profit Down) | C003, C010 | Revenue grows but margins compress |
| C (Revenue Down, Loss) | C002 | Revenue declining, net profit negative |
| D (Profit Positive, Cash Flow Negative) | C005 | Revenue grows but receivables increase, operating cash flow negative |
| E (Decline + High Debt) | C007 | Revenue declining, net loss, debt ratio rising, cash flow negative |
| F (Growth + Rising Debt) | C008 | Revenue and profit grow but debt and receivables also increase |
| Startup | C009 | Small scale, rapid growth, recently turned profitable |

### Accounting Reasonableness
- `total_assets >= total_liabilities` for most companies
- `total_assets >= 0`, `total_liabilities >= 0`
- Audit opinions: mostly `unqualified`, `qualified` for stressed companies (C002, C005, C007)
- Division-by-zero safety: `revenue_yoy`/`profit_yoy` = `None` for first year

---

## RECRUITMENT_TABLE: PASS

| Metric | Value |
|--------|-------|
| Total records | 35 |
| Companies covered | C001–C010 (all) |
| Records per company | 2–5 |
| Event types | job_posting, hiring_expansion, mass_recruitment, key_role_opening, hiring_freeze, posting_withdrawal, recruitment_reduction |
| Data type | simulated |

### Key Design Points
- Recruitment treated as **weak operational signal**, not direct risk indicator
- Contradictory signals included:
  - C002 (high risk) still hiring key operational VP
  - C007 (enforcement actions) still hiring safety director for new project
  - C005 (cash flow rumors) still hiring large model engineers
  - C004 (environmental issues) still expanding with environmental engineers

---

## C001_C010_DATA_COVERAGE: PASS

| Company | P (Opinion) | F (Financial) | H (Recruitment) | Status |
|---------|-------------|---------------|-----------------|--------|
| C001 | 3 | 3 | 4 | OK |
| C002 | 4 | 3 | 4 | OK |
| C003 | 3 | 3 | 3 | OK |
| C004 | 3 | 3 | 3 | OK |
| C005 | 4 | 3 | 3 | OK |
| C006 | 2 | 3 | 3 | OK |
| C007 | 5 | 3 | 4 | OK |
| C008 | 3 | 3 | 3 | OK |
| C009 | 4 | 3 | 4 | OK |
| C010 | 4 | 3 | 4 | OK |

All 10 companies have ≥2 opinion events, exactly 3 financial reports (2023/2024/2025), and ≥2 recruitment events.

---

## PUBLIC_OPINION_TOOL: PASS

| Check | Result |
|-------|--------|
| `risk_get_public_opinion(C007)` | ✅ Returns 5 events |
| `get_public_opinion_events(company_id)` in risk_tools.py | ✅ Working |
| OpenCode Tool `risk_get_public_opinion` | ✅ Exposed in risk.ts |
| risk_bridge.py action `get_public_opinion_events` | ✅ Working |
| Evidence ID `P001` queryable via API | ✅ |

---

## FINANCIAL_TOOL: PASS

| Check | Result |
|-------|--------|
| `risk_get_financial_reports(C007)` | ✅ Returns 3 reports with calculated metrics |
| `get_financial_reports(company_id)` in risk_tools.py | ✅ Working |
| Calculated metrics: debt_ratio, current_ratio, net_margin, revenue_yoy, profit_yoy | ✅ |
| OpenCode Tool `risk_get_financial_reports` | ✅ Exposed in risk.ts |
| risk_bridge.py action `get_financial_reports` | ✅ Working |
| Evidence ID `F001` queryable via API | ✅ |
| Division-by-zero safety | ✅ (returns None for first year) |

---

## RECRUITMENT_TOOL: PASS

| Check | Result |
|-------|--------|
| `risk_get_recruitment_events(C007)` | ✅ Returns 4 events |
| `get_recruitment_events(company_id)` in risk_tools.py | ✅ Working |
| OpenCode Tool `risk_get_recruitment_events` | ✅ Exposed in risk.ts |
| risk_bridge.py action `get_recruitment_events` | ✅ Working |
| Evidence ID `H001` queryable via API | ✅ |

---

## PFH_EVIDENCE_LOOKUP: PASS

| Evidence ID | Type | Queryable |
|-------------|------|-----------|
| P001–P035 | public_opinion | ✅ via `GET /api/evidence/{Pxxx}` |
| F001–F030 | financial | ✅ via `GET /api/evidence/{Fxxx}` |
| H001–H035 | recruitment | ✅ via `GET /api/evidence/{Hxxx}` |
| B001–B016 | business | ✅ (existing, unchanged) |
| J001–J014 | judicial | ✅ (existing, unchanged) |
| R001–R010 | relation | ✅ (existing, unchanged) |
| **Total** | **140** | **All queryable** |

---

## EVIDENCE_DRAWER: PASS

| Feature | Status |
|---------|--------|
| P-type display (title, date, topic, sentiment, source, summary, verification, response) | ✅ |
| F-type display (period, revenue, profit, assets, liabilities, debt_ratio, current_ratio, net_margin, audit_opinion) | ✅ |
| H-type display (date, event_type, position, headcount, salary range, location, status, description) | ✅ |
| Evidence ID clickable → opens drawer | ✅ |
| "模拟数据" label displayed | ✅ |
| Existing B/J/R drawer display unchanged | ✅ |
| TypeScript compilation | ✅ (no errors) |
| Frontend build | ✅ (success) |

---

## RISK_ORCHESTRATOR_INTEGRATION: PASS

| Feature | Status |
|---------|--------|
| Orchestrator updated to query P/F/H for target company | ✅ |
| Evidence ID references expanded to Pxxx/Fxxx/Hxxx | ✅ |
| Coverage Auditor updated to check P/F/H for target company | ✅ |
| Verifier updated with P/F/H reasoning rules | ✅ |
| Existing B/J/R investigation unchanged | ✅ |
| Agent still uses risk_* tools (no direct DB access) | ✅ |

---

## RISK_VERIFIER_RULES: PASS

New hard constraints added to risk-verifier:
1. **Rule 7 (Pxxx)**: Negative sentiment ≠ confirmed fact; unverified rumors must use hedged language
2. **Rule 8 (Fxxx)**: Must use 3-year trend analysis; no single-year conclusions; no single metric for risk level
3. **Rule 9 (Hxxx)**: Recruitment is weak signal; never equate hiring freeze with cash chain break

Existing rules (1–6) unchanged and preserved.

---

## REPORT_TEMPLATE_EXTENSION: PASS

Final report template extended with three new sections:
- 四、舆情风险与外部关注 (Public Opinion Risk)
- 五、财务状况与经营趋势 (Financial Status)
- 六、招聘与经营活动信号 (Recruitment & Activity Signals)

All evidence references use unified B/J/R/P/F/H format.

---

## OLD_BJR_REGRESSION: PASS

| Check | Result |
|-------|--------|
| Existing business_events query | ✅ Unchanged |
| Existing judicial_events query | ✅ Unchanged |
| Existing relations query | ✅ Unchanged |
| Evidence Registry loads B/J/R | ✅ Unchanged |
| `get_evidence_by_id(Bxxx)` | ✅ Working |
| `get_evidence_by_id(Jxxx)` | ✅ Working |
| `get_evidence_by_id(Rxxx)` | ✅ Working |
| C007 parser regression test | ✅ PASSED |
| Gold cases (GC001–GC005) | ✅ Unchanged |
| `tests/gold_cases.json` | ✅ Unchanged |

---

## GOLD_CASES_UNCHANGED: PASS

- `tests/gold_cases.json` — not modified
- `tests/test_c007_parser.py` — PASSED
- `tests/evaluate_report.py` — unchanged, still works with existing B/J/R evidence IDs
- All existing required_evidence and forbidden_claims preserved

---

## Files Modified

### Database
- `risk.db` — added 3 tables + 100 records (35P + 30F + 35H)
- `risk_before_extended_sources.db` — backup of original database

### Data & Scripts
- `scripts/seed_extended_risk_data.py` — new seed script (idempotent, deterministic)

### Risk Tools
- `src/risk_tools.py` — added 6 new functions + updated `get_evidence_by_id`

### Backend
- `backend/app/models.py` — added PublicOpinionEvent, FinancialReport, RecruitmentEvent + Response models
- `backend/app/api.py` — added 3 new endpoints + updated evidence format validation
- `backend/app/deps.py` — re-exported new functions
- `backend/app/evidence_registry.py` — added P/F/H evidence loading

### OpenCode Tools
- `.opencode/tools/risk_bridge.py` — added 3 new actions
- `.opencode/tools/risk.ts` — added 3 new tool exports

### Frontend
- `frontend/src/api/types.ts` — added PublicOpinionEvent, FinancialReport, RecruitmentEvent types
- `frontend/src/api/client.ts` — added publicOpinion, financialReports, recruitmentEvents methods
- `frontend/src/pages/tabs/PublicOpinionTab.tsx` — new component
- `frontend/src/pages/tabs/FinancialReportsTab.tsx` — new component
- `frontend/src/pages/tabs/RecruitmentTab.tsx` — new component
- `frontend/src/pages/CompanyPage.tsx` — added 3 new tabs
- `frontend/src/components/EvidenceDetailDrawer.tsx` — added P/F/H rendering
- `frontend/src/components/Badges.tsx` — updated EvidenceTag for P/F/H
- `frontend/src/lib/presentation.ts` — added evidenceTone for P/F/H

### Agent Rules
- `.opencode/agents/risk-orchestrator.md` — added P/F/H investigation steps
- `.opencode/agents/risk-verifier.md` — added Rules 7–9 (P/F/H reasoning)
- `.opencode/agents/coverage-auditor.md` — added P/F/H coverage check for target company

---

## Final Status

```
PUBLIC_OPINION_TABLE:        PASS
FINANCIAL_REPORT_TABLE:      PASS
RECRUITMENT_TABLE:           PASS
C001_C010_DATA_COVERAGE:     PASS
PUBLIC_OPINION_TOOL:         PASS
FINANCIAL_TOOL:              PASS
RECRUITMENT_TOOL:            PASS
PFH_EVIDENCE_LOOKUP:         PASS
EVIDENCE_DRAWER:             PASS
RISK_ORCHESTRATOR_INTEGRATION: PASS
RISK_VERIFIER_RULES:         PASS
REPORT_TEMPLATE_EXTENSION:   PASS
OLD_BJR_REGRESSION:          PASS
GOLD_CASES_UNCHANGED:        PASS
```

**All checks PASS. Extended data sources integration complete.**
