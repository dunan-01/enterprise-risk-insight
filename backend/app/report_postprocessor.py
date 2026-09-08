"""
企业关联风险智能洞察系统 —— Report Post-Processing: 确定性风险等级注入。

将 Rule Engine 的风险等级和评分确定性注入 Final Report 正文，
不依赖 LLM 正确回填，不使用占位符。

唯一 Source of Truth: Risk Rule Engine 的 risk_scoring.level / risk_scoring.score。
"""

from __future__ import annotations

import re
from typing import Optional


# 匹配 "综合风险等级：" 及其后的内容（到下一空行或下一 ## 标题）
_RISK_LEVEL_IN_SECTION_PATTERN = re.compile(
    r"(综合风险等级[：:]\s*)\n?([^\n]*)",
    re.MULTILINE,
)

# 匹配 "风险评分：" 及其后的内容
_RISK_SCORE_IN_SECTION_PATTERN = re.compile(
    r"(风险评分[：:]\s*)\n?([^\n]*)",
    re.MULTILINE,
)



# 匹配模板占位符
_RISK_LEVEL_PLACEHOLDER_PATTERNS = [
    re.compile(r"\{risk_level\}"),
    re.compile(r"（由 Risk Rule Engine 自动计算）"),
    re.compile(r"待计算"),
    re.compile(r"待填充"),
    re.compile(r"\{\{risk_level\}\}"),
]


def inject_risk_level_into_report(
    report: str,
    risk_level: str,
    risk_score: int,
) -> str:
    """确定性后处理：将 Rule Engine 的风险等级和评分注入报告正文。

    处理三种情况：
    1. 报告中存在 "综合风险等级：xxx" → 替换为 Rule Engine 结果
    2. 报告中存在占位符 → 替换为 Rule Engine 结果
    3. 报告中完全不存在风险等级字段 → 在"六、综合风险判断"中插入

    同时处理"一、风险结论摘要"中的风险等级。

    参数：
        report: LLM 生成的原始报告文本。
        risk_level: Rule Engine 确定的风险等级。
        risk_score: Rule Engine 确定的风险评分。

    返回：
        注入后的报告文本。
    """
    if not report or not risk_level:
        return report

    # ============================================================
    # 1. 清理模板占位符（统一替换为正式值）
    # ============================================================
    for pattern in _RISK_LEVEL_PLACEHOLDER_PATTERNS:
        report = pattern.sub(risk_level, report)

    # ============================================================
    # 2. 替换"综合风险等级"行（如果存在）
    #    格式："综合风险等级：xxx" → "综合风险等级：{risk_level}"
    # ============================================================
    report = _RISK_LEVEL_IN_SECTION_PATTERN.sub(
        lambda m: f"综合风险等级：{risk_level}",
        report,
    )

    # ============================================================
    # 3. 替换或插入"风险评分"行
    # ============================================================
    if _RISK_SCORE_IN_SECTION_PATTERN.search(report):
        # 已存在风险评分行 → 替换
        report = _RISK_SCORE_IN_SECTION_PATTERN.sub(
            lambda m: f"风险评分：{risk_score}",
            report,
        )
    else:
        # 不存在 → 在"综合风险等级"行之后插入（只插入一次）
        def _insert_score_after_level(m: re.Match) -> str:
            return f"综合风险等级：{risk_level}\n\n风险评分：{risk_score}"

        report = _RISK_LEVEL_IN_SECTION_PATTERN.sub(
            _insert_score_after_level,
            report,
            count=1,
        )

    # ============================================================
    # 4. 兜底：如果"六、综合风险判断"章节存在但完全没有风险等级字段
    #    在该章节标题后插入
    # ============================================================
    section_six_pattern = re.compile(
        r"(##\s*六、综合风险判断\s*\n)",
        re.MULTILINE,
    )
    section_six_match = section_six_pattern.search(report)
    if section_six_match:
        # 检查该章节内是否已有"综合风险等级"
        section_start = section_six_match.end()
        # 找到下一个 ## 标题或文档结尾
        next_section = re.search(r"\n##\s", report[section_start:])
        section_end = (
            section_start + next_section.start()
            if next_section
            else len(report)
        )
        section_text = report[section_start:section_end]

        if "综合风险等级" not in section_text:
            # 在章节标题后插入风险等级和评分
            insert_pos = section_six_match.end()
            injection = f"\n综合风险等级：{risk_level}\n\n风险评分：{risk_score}\n\n"
            report = report[:insert_pos] + injection + report[insert_pos:]

    return report
