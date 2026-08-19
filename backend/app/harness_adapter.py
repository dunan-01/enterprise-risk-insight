"""
企业关联风险智能洞察系统 —— Risk Harness Adapter（Harness 调用层）。

通过 headless OpenCode CLI（opencode run）真实触发 Risk Harness：
- primary agent：risk-orchestrator（.opencode/agents/risk-orchestrator.md）
- 子 agent 审核：coverage-auditor / risk-verifier（由 orchestrator 自行调度）

本模块只负责「调用 Harness 并解析 JSONL 事件流」，
不包含任何风险判断逻辑（风险判断全部由 Harness 内 agent 完成）。

调用方式（已验证可行）：
    opencode run --agent risk-orchestrator --format json --dir <PROJECT_ROOT> "<prompt>"

输出为 JSONL 事件流（每行一个 JSON 事件），关键事件：
- {"type": "text", "part": {"type": "text", "text": "..."}}  → assistant 文本
- {"type": "tool_use", "part": {"tool": "..."}}              → 工具调用记录
- {"type": "step_finish", "part": {"reason": "..."}}         → 步骤结束

异常约定：超时 / opencode 缺失 / 多次尝试仍无 VERIFICATION_STATUS 时
抛出 HarnessError（message 含可读说明），不得让裸异常穿透到 API 层。
"""

from __future__ import annotations

import json
import logging
import os
import re
import shutil
import signal
import subprocess
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("risk-api")

# ------------------------------------------------------------
# 路径与常量
# ------------------------------------------------------------

BACKEND_ROOT = Path(__file__).resolve().parents[1]  # backend/
PROJECT_ROOT = BACKEND_ROOT.parent                  # 项目根目录（risk/）

# opencode CLI 可执行文件名（启动时通过 shutil.which 在 PATH 中查找）
OPENCODE_BIN = "opencode"

# 报告生成 prompt 模板（已实测可稳定产出 VERIFICATION_STATUS + 完整报告，
# 核心要求保持不变，仅按 company_id 格式化）。
ANALYSIS_PROMPT_TEMPLATE = (
    "请对 {company_id} 完成一次完整的企业风险调查，遵循你的标准流程："
    "1) 使用 risk_* 工具调查目标企业及其值得调查的关联企业（含多跳）；"
    "2) 生成初稿后调用 coverage-auditor 检查覆盖完整性，INCOMPLETE 则补充调查后再次调用；"
    "3) 调用 risk-verifier 审核，REVISE 则修订后再次送审，最多3轮；"
    "4) 最终先输出一行 VERIFICATION_STATUS: PASS 或 UNRESOLVED，"
    "再输出通过审核的最终企业风险调查报告全文。"
    "硬性要求：禁止使用 edit/write/bash 等文件写入工具，不要写任何文件，"
    "报告直接在对话中输出；中间过程说明尽量简短；"
    "最终报告必须包含企业基本信息、企业自身风险、直接关联企业风险、多跳关联风险、"
    "风险总结（含风险等级评定）和关键证据引用（Bxxx/Jxxx/Rxxx）。"
)

# 审核状态正则（取最后一个匹配：agent 可能在过程中提前提及该行）
VERIFICATION_STATUS_PATTERN = re.compile(r"VERIFICATION_STATUS:\s*(PASS|UNRESOLVED)")

# 最多尝试次数：首次 + 未提取到状态 / 超时时自动重试 1 次
MAX_ATTEMPTS = 2
RETRY_SLEEP_SECONDS = 2.0

# 单次 opencode 调用的默认超时（秒）：20 分钟。
# 复杂案例（如 C005 需要 2 轮 risk-verifier 复核）总耗时可达 10-20 分钟，
# 实测 600s 会在 verifier 复核阶段被强杀，故提高默认值。
DEFAULT_HARNESS_TIMEOUT = 1200
# 环境变量覆盖：HARNESS_TIMEOUT=<秒>，读取失败/非法时回退默认值
HARNESS_TIMEOUT_ENV = "HARNESS_TIMEOUT"

# 串行化 Harness 调用：同一时间只允许一个分析任务，避免 opencode 并发冲突
_HARNESS_LOCK = threading.Lock()


class HarnessError(Exception):
    """Harness 调用失败（opencode 缺失 / 超时 / 重试后仍无审核状态）。"""


class CompanyNotFoundError(Exception):
    """企业不存在（由服务层存在性检查时抛出，与数据库无关）。"""

    def __init__(self, company_id: str) -> None:
        super().__init__(f"未找到企业 {company_id}")
        self.company_id = company_id


# ------------------------------------------------------------
# opencode 可执行文件解析
# ------------------------------------------------------------


def _find_opencode_binary() -> str:
    """
    在 PATH 中查找 opencode 可执行文件，找不到抛 HarnessError。
    """
    path = shutil.which(OPENCODE_BIN)
    if not path:
        raise HarnessError(
            "未找到 opencode 可执行文件，请确认其已加入 PATH"
            "（如 /Users/dujiangli/.opencode/bin/opencode）"
        )
    return path


def _build_env(opencode_bin: str) -> Dict[str, str]:
    """
    构造子进程环境：确保 opencode 所在目录在 PATH 中，
    避免其内部子进程（bun 等运行时）找不到可执行文件。
    """
    env = os.environ.copy()
    bin_dir = str(Path(opencode_bin).resolve().parent)
    if bin_dir not in env.get("PATH", ""):
        env["PATH"] = bin_dir + os.pathsep + env.get("PATH", "")
    return env


def _resolve_timeout(timeout_seconds: Optional[int]) -> int:
    """
    解析单次 Harness 调用的超时时间（秒）。

    优先级：显式参数 > 环境变量 HARNESS_TIMEOUT > 默认 1200。
    环境变量非法（非数字 / 非正数）时回退默认值，并记录警告。
    """
    if timeout_seconds is not None:
        if timeout_seconds > 0:
            return timeout_seconds
        logger.warning("timeout_seconds 非法（%s），回退默认值", timeout_seconds)
        return DEFAULT_HARNESS_TIMEOUT

    raw = os.environ.get(HARNESS_TIMEOUT_ENV)
    if raw:
        try:
            value = int(raw)
            if value > 0:
                return value
            logger.warning(
                "%s=%s 非法（必须为正整数），回退默认值 %s",
                HARNESS_TIMEOUT_ENV, raw, DEFAULT_HARNESS_TIMEOUT,
            )
        except ValueError:
            logger.warning(
                "%s=%s 非法（无法解析为整数），回退默认值 %s",
                HARNESS_TIMEOUT_ENV, raw, DEFAULT_HARNESS_TIMEOUT,
            )
    return DEFAULT_HARNESS_TIMEOUT


# ------------------------------------------------------------
# JSONL 事件流解析
# ------------------------------------------------------------


def _parse_event(line: str) -> Optional[Dict[str, Any]]:
    """
    解析单行 JSON 事件；无法解析的行返回 None（容错跳过，不中断流程）。
    """
    line = line.strip()
    if not line:
        return None
    try:
        obj = json.loads(line)
    except (json.JSONDecodeError, ValueError):
        logger.warning("跳过无法解析的 Harness 事件行: %s", line[:200])
        return None
    return obj if isinstance(obj, dict) else None


def _extract_texts(events: List[Dict[str, Any]]) -> List[str]:
    """
    从事件流中提取全部 assistant 文本（{"type": "text", "part": {"text": ...}}）。
    """
    texts: List[str] = []
    for ev in events:
        if ev.get("type") != "text":
            continue
        part = ev.get("part")
        if isinstance(part, dict) and part.get("type") == "text":
            text = part.get("text")
            if isinstance(text, str) and text.strip():
                texts.append(text)
    return texts


def _split_report(full_text: str) -> Tuple[str, str]:
    """
    按最后一个 VERIFICATION_STATUS 行切分：

    返回 (final_report, process_text)：
    - final_report：该行之后的部分（去掉分隔符，即最终报告全文）
    - process_text：该行之前的部分（即分析过程文本）

    未匹配到状态行时返回 ("", full_text)。
    """
    matches = list(VERIFICATION_STATUS_PATTERN.finditer(full_text))
    if not matches:
        return "", full_text

    last = matches[-1]
    report = full_text[last.end():]
    # 去掉状态行与报告之间可能出现的分隔符（如 "---"、空行）
    report = re.sub(r"^\s*(?:-{3,}\s*)+", "", report).strip()
    process_text = full_text[: last.start()].strip()
    return report, process_text


def _parse_stdout(events: List[Dict[str, Any]], stdout_text: str) -> None:
    """
    按行解析 stdout（JSONL），合法事件追加到 events 列表。
    """
    for line in stdout_text.splitlines():
        ev = _parse_event(line)
        if ev is not None:
            events.append(ev)


# ------------------------------------------------------------
# Harness 调用入口
# ------------------------------------------------------------


def run_harness_analysis(
    company_id: str, timeout_seconds: Optional[int] = None
) -> Dict[str, Any]:
    """
    调用 Risk Harness 对指定企业完成一次完整风险分析（同步阻塞）。

    参数：
        company_id: 企业ID（内部会 strip + upper 规范化）
        timeout_seconds: 单次 opencode 调用的超时时间（秒），可选。
            未传入时按 _resolve_timeout() 解析：
            环境变量 HARNESS_TIMEOUT > 默认 1200 秒（20 分钟）。
            复杂案例（多轮 verifier 复核，如 C005）可能耗时 10-20 分钟，
            客户端/HTTP 超时建议设置 ≥ 20 分钟。

    返回结构化结果：
        {
            "company_id": str,
            "verification_status": "PASS" | "UNRESOLVED" | None,
            "report": str,              # VERIFICATION_STATUS 之后的最终报告
            "process_text": str,        # 分析过程文本（报告之前的部分）
            "raw_events": List[dict],   # 完整 JSONL 事件流
            "attempts": int,            # 实际尝试次数（最多 2 次）
            "duration_seconds": float,  # 总耗时（含重试等待）
        }

    异常：
        HarnessError —— opencode 缺失 / 启动失败 / 超时重试后仍超时 /
                        进程完成但重试后仍未提取到 VERIFICATION_STATUS。
        超时与"无状态"均会重试 1 次（共最多 2 次尝试）。
    """
    cid = company_id.strip().upper()
    timeout_seconds = _resolve_timeout(timeout_seconds)
    opencode_bin = _find_opencode_binary()
    prompt = ANALYSIS_PROMPT_TEMPLATE.format(company_id=cid)
    env = _build_env(opencode_bin)

    command = [
        opencode_bin,
        "run",
        "--agent", "risk-orchestrator",
        "--format", "json",
        "--dir", str(PROJECT_ROOT),
        prompt,
    ]

    start = time.monotonic()
    attempts = 0
    raw_events: List[Dict[str, Any]] = []
    last_stderr = ""

    with _HARNESS_LOCK:
        while True:
            attempts += 1
            logger.info(
                "Harness 分析第 %d/%d 次尝试: %s", attempts, MAX_ATTEMPTS, cid
            )
            try:
                proc = subprocess.Popen(
                    command,
                    cwd=str(PROJECT_ROOT),
                    env=env,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    start_new_session=True,  # 独立进程组，便于超时后整体清理
                )
                try:
                    stdout_bytes, stderr_bytes = proc.communicate(
                        timeout=timeout_seconds
                    )
                except subprocess.TimeoutExpired:
                    # 杀掉整个进程组，避免 opencode 子进程残留
                    try:
                        os.killpg(proc.pid, signal.SIGKILL)
                    except (ProcessLookupError, PermissionError):
                        proc.kill()
                    proc.communicate()
                    if attempts < MAX_ATTEMPTS:
                        # 超时纳入自动重试：未达最大尝试次数则重试
                        logger.warning(
                            "第 %d 次尝试超时（%ss），%ss 后重试: %s",
                            attempts, timeout_seconds, RETRY_SLEEP_SECONDS, cid,
                        )
                        time.sleep(RETRY_SLEEP_SECONDS)
                        continue
                    raise HarnessError(
                        f"Harness 分析超时（{timeout_seconds}s，"
                        f"尝试 {attempts} 次）：{cid}"
                    ) from None
            except OSError as exc:
                # FileNotFoundError / PermissionError 等底层启动失败
                raise HarnessError(f"opencode 启动失败：{exc}") from exc

            stderr_text = stderr_bytes.decode("utf-8", errors="replace").strip()
            if stderr_text:
                last_stderr = stderr_text
                logger.warning("opencode stderr: %s", stderr_text[:500])
            if proc.returncode != 0:
                logger.warning(
                    "opencode 退出码非 0: %s（stderr: %s）",
                    proc.returncode, last_stderr[:300],
                )

            stdout_text = stdout_bytes.decode("utf-8", errors="replace")
            _parse_stdout(raw_events, stdout_text)

            full_text = "\n\n".join(_extract_texts(raw_events))
            report, process_text = _split_report(full_text)
            matches = list(VERIFICATION_STATUS_PATTERN.finditer(full_text))
            verification_status = matches[-1].group(1) if matches else None

            if verification_status is not None:
                break

            if attempts >= MAX_ATTEMPTS:
                detail = last_stderr or "进程正常结束但无有效输出"
                raise HarnessError(
                    f"Harness 分析完成但未输出 VERIFICATION_STATUS"
                    f"（尝试 {attempts} 次）：{cid}。stderr: {detail[:300]}"
                )

            logger.warning(
                "未提取到 VERIFICATION_STATUS，%ss 后重试", RETRY_SLEEP_SECONDS
            )
            time.sleep(RETRY_SLEEP_SECONDS)

    duration_seconds = round(time.monotonic() - start, 2)
    logger.info("Harness 分析完成: %s status=%s 耗时=%ss", cid, verification_status, duration_seconds)

    return {
        "company_id": cid,
        "verification_status": verification_status,
        "report": report,
        "process_text": process_text,
        "raw_events": raw_events,
        "attempts": attempts,
        "duration_seconds": duration_seconds,
    }
