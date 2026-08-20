"""
企业风险报告 PDF 生成服务。

将已有的 Markdown 报告转换为 PDF 文件。
使用 fpdf2 纯 Python 方案，无需系统依赖。
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger("risk-api")

# 项目根目录
BACKEND_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = BACKEND_ROOT.parent
RUNS_WEB_ROOT = PROJECT_ROOT / "runs" / "web"


def generate_report_pdf(company_id: str) -> Optional[Path]:
    """
    为指定企业生成风险报告 PDF。

    从 runs/web/<company_id>/ 读取已有分析结果，
    生成 report_final.pdf 并返回文件路径。

    Args:
        company_id: 企业ID

    Returns:
        PDF 文件路径，如果无法生成则返回 None
    """
    cid = company_id.strip().upper()
    run_dir = RUNS_WEB_ROOT / cid

    # 检查分析结果是否存在
    result_path = run_dir / "analysis_result.json"
    if not result_path.exists():
        return None

    # 读取分析结果
    try:
        result: Dict[str, Any] = json.loads(result_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("读取分析结果失败: %s", exc)
        return None

    # 读取报告内容
    report = result.get("report") or ""
    if not report.strip():
        report_path = run_dir / "report_final.md"
        if report_path.exists():
            try:
                report = report_path.read_text(encoding="utf-8")
            except OSError as exc:
                logger.warning("读取报告文件失败: %s", exc)
                return None

    if not report.strip():
        return None

    # 生成 PDF
    pdf_path = run_dir / "report_final.pdf"
    try:
        _convert_md_to_pdf(report, result, pdf_path)
        return pdf_path
    except ImportError as exc:
        logger.error("PDF 生成依赖未安装: %s", exc)
        return None
    except Exception as exc:
        logger.exception("PDF 生成失败: %s", exc)
        return None


def _convert_md_to_pdf(
    markdown_content: str, analysis_result: Dict[str, Any], output_path: Path
) -> None:
    """
    将 Markdown 内容转换为 PDF。

    使用 fpdf2 纯 Python 方案。
    """
    from fpdf import FPDF

    # 提取元数据
    company_id = analysis_result.get("company_id", "")
    company_name = _extract_company_name(analysis_result, markdown_content)
    risk_level = analysis_result.get("risk_level", "未知")
    verification_status = analysis_result.get("verification_status", "未知")
    evidence_ids = analysis_result.get("evidence_ids", [])
    related_companies = analysis_result.get("related_companies", [])

    # 创建 PDF
    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)

    # 添加内置字体（支持 ASCII）
    pdf.add_font("SimHei", "", "/System/Library/Fonts/STHeiti Light.ttc", uni=True)

    # 添加第一页：封面
    pdf.add_page()
    pdf.set_font("SimHei", size=24)
    pdf.cell(0, 20, "企业风险调查报告", ln=True, align="C")
    pdf.ln(10)

    pdf.set_font("SimHei", size=16)
    pdf.cell(0, 12, company_name, ln=True, align="C")
    pdf.ln(5)

    pdf.set_font("SimHei", size=12)
    pdf.cell(0, 8, f"企业ID: {company_id}", ln=True, align="C")
    pdf.ln(20)

    # 摘要信息
    pdf.set_font("SimHei", size=14)
    pdf.cell(0, 10, "摘要信息", ln=True)
    pdf.ln(5)

    pdf.set_font("SimHei", size=11)
    pdf.cell(50, 8, "风险等级:", ln=False)
    pdf.cell(0, 8, risk_level, ln=True)
    pdf.cell(50, 8, "审核状态:", ln=False)
    pdf.cell(0, 8, verification_status, ln=True)
    pdf.cell(50, 8, "关键证据:", ln=False)
    pdf.cell(0, 8, ", ".join(evidence_ids) if evidence_ids else "无", ln=True)
    pdf.cell(50, 8, "关联企业:", ln=False)
    pdf.cell(0, 8, ", ".join(related_companies) if related_companies else "无", ln=True)
    pdf.ln(10)

    # 分隔线
    pdf.line(10, pdf.get_y(), 200, pdf.get_y())
    pdf.ln(10)

    # 解析并渲染 Markdown 内容
    _render_markdown_to_pdf(pdf, markdown_content)

    # 保存 PDF
    pdf.output(str(output_path))


def _render_markdown_to_pdf(pdf: Any, markdown_content: str) -> None:
    """
    将 Markdown 内容渲染到 PDF。
    """
    lines = markdown_content.split("\n")
    i = 0
    while i < len(lines):
        line = lines[i].rstrip()

        # 跳过空行
        if not line:
            pdf.ln(3)
            i += 1
            continue

        # 标题
        if line.startswith("# "):
            pdf.set_font("SimHei", size=18)
            pdf.ln(5)
            pdf.cell(0, 10, line[2:].strip(), ln=True)
            pdf.ln(3)
            i += 1
            continue

        if line.startswith("## "):
            pdf.set_font("SimHei", size=15)
            pdf.ln(4)
            pdf.cell(0, 8, line[3:].strip(), ln=True)
            pdf.ln(2)
            i += 1
            continue

        if line.startswith("### "):
            pdf.set_font("SimHei", size=13)
            pdf.ln(3)
            pdf.cell(0, 7, line[4:].strip(), ln=True)
            pdf.ln(2)
            i += 1
            continue

        # 表格
        if line.startswith("|"):
            table_lines = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                table_lines.append(lines[i].strip())
                i += 1
            _render_table(pdf, table_lines)
            continue

        # 列表项
        if line.startswith("- ") or line.startswith("* "):
            pdf.set_font("SimHei", size=11)
            pdf.cell(10, 7, "", ln=False)
            pdf.cell(0, 7, f"• {line[2:].strip()}", ln=True)
            i += 1
            continue

        # 普通段落
        pdf.set_font("SimHei", size=11)
        # 清理 Markdown 格式
        clean_text = _clean_markdown(line)
        pdf.multi_cell(0, 7, clean_text)
        pdf.ln(2)
        i += 1


def _render_table(pdf: Any, table_lines: list[str]) -> None:
    """
    渲染 Markdown 表格到 PDF。
    """
    if len(table_lines) < 2:
        return

    # 解析表头
    headers = [cell.strip() for cell in table_lines[0].split("|")[1:-1]]

    # 跳过分隔行（第二行）
    data_rows = []
    for line in table_lines[2:]:
        row = [cell.strip() for cell in line.split("|")[1:-1]]
        if row:
            data_rows.append(row)

    if not headers:
        return

    # 计算列宽
    num_cols = len(headers)
    col_width = 180 / num_cols

    # 绘制表头
    pdf.set_font("SimHei", size=10)
    pdf.set_fill_color(240, 240, 240)
    for header in headers:
        pdf.cell(col_width, 7, _clean_markdown(header), border=1, fill=True)
    pdf.ln()

    # 绘制数据行
    for row in data_rows:
        for j, cell in enumerate(row):
            if j < num_cols:
                pdf.cell(col_width, 7, _clean_markdown(cell), border=1)
        pdf.ln()

    pdf.ln(3)


def _clean_markdown(text: str) -> str:
    """
    清理 Markdown 格式符号。
    """
    # 移除加粗
    text = re.sub(r'\*\*(.*?)\*\*', r'\1', text)
    # 移除斜体
    text = re.sub(r'\*(.*?)\*', r'\1', text)
    # 移除代码
    text = re.sub(r'`(.*?)`', r'\1', text)
    # 移除链接
    text = re.sub(r'\[(.*?)\]\(.*?\)', r'\1', text)
    return text.strip()


def _extract_company_name(analysis_result: Dict[str, Any], report: str) -> str:
    """从分析结果或报告中提取企业名称。"""
    # 尝试从报告中提取
    match = re.search(r'企业名称[：:]\s*(.+?)[\n\r]', report)
    if match:
        return match.group(1).strip()

    # 尝试从报告标题中提取
    match = re.search(r'^#\s+(.+?)[\n\r]', report, re.MULTILINE)
    if match:
        return match.group(1).strip()

    return analysis_result.get("company_id", "未知企业")
