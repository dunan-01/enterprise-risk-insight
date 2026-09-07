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
from typing import Any, Callable, Dict, List, Optional, Tuple

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
# 报告必须严格遵循 templates/risk_report_template.md 的固定结构。
# 报告必须是风险导向的：只写与风险判断实质相关的信息，
# 不得罗列企业档案、完整数据表、全部舆情/招聘列表。
#
# V2.1 重要变更：风险等级和风险评分由确定性 Risk Rule Engine 确定，
# LLM 不允许自由指定风险等级或评分。LLM 只负责发现风险事实、
# 绑定 Evidence ID、给出风险解释。
ANALYSIS_PROMPT_TEMPLATE = (
    "请对 {company_id} 完成一次完整的企业风险调查，遵循你的标准流程："
    "1) 使用 risk_* 工具调查目标企业及其值得调查的关联企业（含多跳）；"
    "2) 生成初稿后调用 coverage-auditor 检查覆盖完整性，INCOMPLETE 则补充调查后再次调用；"
    "3) 调用 risk-verifier 审核，REVISE 则修订后再次送审，最多3轮；"
    "4) 输出最终企业风险调查报告全文（用 FINAL_REPORT_BEGIN / FINAL_REPORT_END 包裹）。"
    "5) 标记结束后，另起一行必须且只能输出：VERIFICATION_STATUS: PASS 或 VERIFICATION_STATUS: UNRESOLVED。"
    "硬性要求：禁止使用 edit/write/bash 等文件写入工具，不要写任何文件，"
    "报告直接在对话中输出；中间过程说明尽量简短，且一律放在标记之外（进入 Investigation Trace）。"
    "最终报告必须严格遵循 templates/risk_report_template.md 的固定结构，"
    "必须体现风险导向原则：只写与风险判断实质相关的信息，"
    "不得罗列企业档案、完整数据表、全部舆情或全部招聘列表。"
    "报告结构必须按模板顺序：一、风险结论摘要 → 二、企业自身主要风险 → "
    "三、关联企业及风险传导 → 四、多源证据综合分析 → 五、风险缓释因素与矛盾信号 → "
    "六、综合风险判断 → 七、证据限制与不确定性 → 八、关键证据引用。"
    "第二章二级小节动态生成：仅为存在 Material 风险的类别生成小节；"
    "自身无显著风险时只保留一段简洁结论，禁止输出五个'未发现……'空章节；"
    "正常信号（财务稳定、招聘扩张、正面舆情）不得在本章展开，有缓释意义才写入第五章。"
    "企业基本信息必须极度压缩，仅保留企业名称、企业ID、调查时间、分析版本、数据源。"
    "财务信息必须提炼风险趋势，严禁直接展示完整三年财务数据表。"
    "关键证据引用只列真正支撑最终风险判断的 Evidence。"
    "输出顺序必须是：FINAL_REPORT_BEGIN → 报告正文（第一行为 # 企业关联风险调查报告）"
    "→ FINAL_REPORT_END → VERIFICATION_STATUS 行。"
    "重要：风险等级和风险评分由确定性 Risk Rule Engine 自动计算，"
    "LLM 不需要也不允许在报告中自行指定风险等级或评分，"
    "只需如实陈述风险事实和分析依据。"
)

# 审核状态正则（取最后一个匹配：agent 可能在过程中提前提及该行）
VERIFICATION_STATUS_PATTERN = re.compile(r"VERIFICATION_STATUS:\s*(PASS|UNRESOLVED)")

# 最多尝试次数：首次 + 未提取到状态 / 超时时自动重试 1 次
MAX_ATTEMPTS = 2
RETRY_SLEEP_SECONDS = 2.0

# 单次 opencode 调用的默认超时（秒）：60 分钟。
# 风险导向报告模板需要更多时间进行多源证据综合分析和报告质量检查。
# 复杂案例（如 C007 需要 2 轮 risk-verifier 复核）总耗时可达 30-50 分钟。
DEFAULT_HARNESS_TIMEOUT = 3600
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


FINAL_REPORT_BEGIN_PATTERN = re.compile(r"FINAL_REPORT_BEGIN")
FINAL_REPORT_END_PATTERN = re.compile(r"FINAL_REPORT_END")

REPORT_TITLE_PATTERN = re.compile(r"#\s*企业关联风险调查报告")


def _extract_marked_report(full_text: str) -> Optional[str]:
    """优先按 FINAL_REPORT_BEGIN / FINAL_REPORT_END 确定性边界提取报告。

    返回标记内 Markdown（含标题），无标记时返回 None。
    """
    begins = list(FINAL_REPORT_BEGIN_PATTERN.finditer(full_text))
    ends = list(FINAL_REPORT_END_PATTERN.finditer(full_text))
    if not begins or not ends:
        return None
    start = begins[0].end()
    # 取开始标记之后出现的第一个结束标记
    end_match = next((m for m in ends if m.start() >= start), None)
    if end_match is None:
        return None
    return full_text[start:end_match.start()].strip()


def _strip_preamble(report: str) -> str:
    """兜底：报告必须从 `# 企业关联风险调查报告` 开始。

    若 Agent 未使用标记导致过程文本混入，从第一个报告标题处截断。
    标记内文本不再需要此处理，但保留作双保险。
    """
    m = REPORT_TITLE_PATTERN.search(report)
    if m is None:
        return report.strip()
    return report[m.start():].strip()


def _split_report(full_text: str) -> Tuple[str, str]:
    """
    按 VERIFICATION_STATUS 行切分报告正文。

    返回 (final_report, process_text)：
    - final_report：仅 FINAL_REPORT_BEGIN/END 之间的 Markdown（优先）；
      无标记时回退到原有新旧格式兼容逻辑，并做标题兜底截断。
    - process_text：分析过程文本（标记外全部文本）。

    未匹配到状态行时返回 ("", full_text)。
    """
    matches = list(VERIFICATION_STATUS_PATTERN.finditer(full_text))
    if not matches:
        return "", full_text

    marked = _extract_marked_report(full_text)

    # 取第一个匹配作为状态行
    first = matches[0]
    status_start = first.start()
    status_end = first.end()

    if marked is not None:
        report = _strip_preamble(marked)
        # process_text = 标记外文本（状态行文本保留在外，不污染报告）
        process_text = (
            full_text[: full_text.find("FINAL_REPORT_BEGIN")].strip()
            + "\n\n"
            + full_text[full_text.find("FINAL_REPORT_END") + len("FINAL_REPORT_END"):].strip()
        ).strip()
        return report, process_text

    # 判断状态行位置：如果状态行在文本前10%以内，认为是旧格式（状态行在前）
    # 否则认为是新格式（报告在前，状态行在后）
    text_len = len(full_text)
    if text_len > 0 and status_start / text_len < 0.1:
        # 旧格式：VERIFICATION_STATUS 在开头，报告在后面
        report = full_text[status_end:]
        report = re.sub(r"^\s*(?:-{3,}\s*)+", "", report).strip()
        process_text = full_text[:status_start].strip()
    else:
        # 新格式：报告在前，VERIFICATION_STATUS 在末尾
        # 取状态行之前的文本作为报告，去除末尾分隔符
        report = full_text[:status_start].strip()
        report = re.sub(r"\s*\n\s*$", "", report).strip()
        # 去掉报告末尾可能重复出现的 VERIFICATION_STATUS 引用行
        report = re.sub(r"\n\s*VERIFICATION_STATUS:\s*(PASS|UNRESOLVED)\s*$", "", report).strip()
        process_text = full_text[status_end:].strip()

    return _strip_preamble(report), process_text


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
    company_id: str,
    timeout_seconds: Optional[int] = None,
    task_dir: Optional[Path] = None,
    on_event: Optional[Callable[[Dict[str, Any], int], None]] = None,
    cancelled_event: Optional[threading.Event] = None,
    on_process_start: Optional[Callable[[int, int], None]] = None,
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
        task_dir: per-task 输出目录，可选。提供时将 session_events.jsonl 和 stderr.log 写入该目录。
        on_event: 实时事件回调，可选。每收到一个有效 JSONL event 就调用 on_event(event_dict, event_count)。
        cancelled_event: 取消信号事件，可选。被 set() 时终止当前分析且不重试。
        on_process_start: subprocess 启动回调，可选。调用 on_process_start(pid, pgid) 通知调用方进程已启动。

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
    logger.info("[Harness] run_harness_analysis entered company_id=%s", cid)

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

    logger.info("[Harness] project_root=%s", PROJECT_ROOT)
    logger.info("[Harness] cwd=%s", PROJECT_ROOT)
    logger.info("[Harness] command=%s", " ".join(command[:6]) + " ...")
    logger.info("[Harness] timeout_seconds=%s", timeout_seconds)

    start = time.monotonic()
    attempts = 0
    raw_events: List[Dict[str, Any]] = []
    last_stderr = ""

    # 创建 per-task 输出目录（如果提供）
    if task_dir is not None:
        task_dir.mkdir(parents=True, exist_ok=True)

    with _HARNESS_LOCK:
        logger.info("[Harness] _HARNESS_LOCK acquired")
        while True:
            attempts += 1
            logger.info(
                "[Harness] 第 %d/%d 次尝试: %s", attempts, MAX_ATTEMPTS, cid
            )
            try:
                logger.info("[Harness] subprocess about to start: %s", cid)
                proc = subprocess.Popen(
                    command,
                    cwd=str(PROJECT_ROOT),
                    env=env,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    start_new_session=True,  # 独立进程组，便于超时后整体清理
                )
                logger.info("[Harness] subprocess started pid=%s company=%s", proc.pid, cid)

                # 通知调用方进程已启动（PID/PGID）
                if on_process_start:
                    try:
                        on_process_start(proc.pid, proc.pid)  # start_new_session=True → PGID = PID
                    except Exception as cb_err:
                        logger.warning("[Harness] on_process_start 回调异常: %s", cb_err)

                # --------------------------------------------------------
                # 流式 stdout / stderr 消费（V1.3 改造）
                # --------------------------------------------------------
                events_count = 0
                stderr_lines: List[str] = []

                def _read_stdout():
                    """持续读取 stdout JSONL 行，实时解析并回调。"""
                    nonlocal events_count
                    assert proc.stdout is not None
                    for raw_line in iter(proc.stdout.readline, b""):
                        if not raw_line:
                            break
                        ev = _parse_event(raw_line.decode("utf-8", errors="replace"))
                        if ev:
                            # 注意：不在此处获取 _HARNESS_LOCK
                            # raw_events 仅由 stdout 线程写入，主线程在 stdout_thread.join() 后才读取
                            raw_events.append(ev)
                            events_count += 1
                            # 实时写入 session_events.jsonl
                            if task_dir:
                                try:
                                    with open(
                                        task_dir / "session_events.jsonl",
                                        "a",
                                        encoding="utf-8",
                                    ) as f:
                                        f.write(json.dumps(ev, ensure_ascii=False) + "\n")
                                except OSError as write_err:
                                    logger.warning(
                                        "[Harness] 写入 session_events.jsonl 失败: %s",
                                        write_err,
                                    )
                            # 回调
                            if on_event:
                                try:
                                    on_event(ev, events_count)
                                except Exception as cb_err:
                                    logger.warning(
                                        "[Harness] on_event 回调异常: %s", cb_err
                                    )

                def _read_stderr():
                    """持续读取 stderr 行，写入 stderr.log。"""
                    assert proc.stderr is not None
                    for raw_line in iter(proc.stderr.readline, b""):
                        if not raw_line:
                            break
                        text = raw_line.decode("utf-8", errors="replace")
                        stderr_lines.append(text)
                        if task_dir:
                            try:
                                with open(
                                    task_dir / "stderr.log",
                                    "a",
                                    encoding="utf-8",
                                ) as f:
                                    f.write(text)
                            except OSError as write_err:
                                logger.warning(
                                    "[Harness] 写入 stderr.log 失败: %s",
                                    write_err,
                                )

                stdout_thread = threading.Thread(
                    target=_read_stdout,
                    daemon=True,
                    name=f"harness-stdout-{cid}",
                )
                stderr_thread = threading.Thread(
                    target=_read_stderr,
                    daemon=True,
                    name=f"harness-stderr-{cid}",
                )
                stdout_thread.start()
                stderr_thread.start()

                # 主线程等待进程退出（超时用 os.killpg 杀进程组）
                try:
                    proc.wait(timeout=timeout_seconds)
                except subprocess.TimeoutExpired:
                    try:
                        os.killpg(proc.pid, signal.SIGKILL)
                    except (ProcessLookupError, PermissionError):
                        proc.kill()
                    proc.wait()
                    # V1.5: 超时后检查是否已被用户取消
                    if cancelled_event and cancelled_event.is_set():
                        logger.info("[Harness] 超时但已取消，不重试: %s", cid)
                        raise HarnessError(
                            f"Harness 分析被取消（超时检测时发现取消信号）：{cid}"
                        ) from None
                    if attempts < MAX_ATTEMPTS:
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

                # 等待读取线程结束（进程已退出，管道 EOF 会终止线程）
                stdout_thread.join(timeout=30)
                stderr_thread.join(timeout=30)

            except OSError as exc:
                # FileNotFoundError / PermissionError 等底层启动失败
                raise HarnessError(f"opencode 启动失败：{exc}") from exc

            logger.info(
                "[Harness] subprocess exited pid=%s return_code=%s company=%s",
                proc.pid, proc.returncode, cid,
            )

            # V1.5: 进程退出后检查是否已被用户取消（SIGTERM = -15 或被 kill）
            if cancelled_event and cancelled_event.is_set():
                logger.info("[Harness] 进程退出但已取消，不重试: %s", cid)
                raise HarnessError(
                    f"Harness 分析被取消：{cid}"
                ) from None

            stderr_text = "\n".join(stderr_lines).strip()
            if stderr_text:
                last_stderr = stderr_text
                logger.warning("[Harness] opencode stderr: %s", stderr_text[:500])
            if proc.returncode != 0:
                logger.warning(
                    "[Harness] opencode 退出码非 0: %s（stderr: %s）",
                    proc.returncode, last_stderr[:300],
                )

            logger.info(
                "[Harness] events streamed=%d company=%s",
                events_count, cid,
            )

            full_text = "\n\n".join(_extract_texts(raw_events))
            report, process_text = _split_report(full_text)
            matches = list(VERIFICATION_STATUS_PATTERN.finditer(full_text))
            # 取第一个匹配（真正的状态行总是在报告开头）
            verification_status = matches[0].group(1) if matches else None

            logger.info(
                "[Harness] verification_status=%s report_len=%d company=%s",
                verification_status, len(report), cid,
            )

            if verification_status is not None:
                break

            if attempts >= MAX_ATTEMPTS:
                detail = last_stderr or "进程正常结束但无有效输出"
                raise HarnessError(
                    f"Harness 分析完成但未输出 VERIFICATION_STATUS"
                    f"（尝试 {attempts} 次）：{cid}。stderr: {detail[:300]}"
                )

            # V1.5: 重试前检查是否已被用户取消
            if cancelled_event and cancelled_event.is_set():
                logger.info("[Harness] 无验证状态但已取消，不重试: %s", cid)
                raise HarnessError(
                    f"Harness 分析被取消：{cid}"
                ) from None

            logger.warning(
                "[Harness] 未提取到 VERIFICATION_STATUS，%ss 后重试", RETRY_SLEEP_SECONDS
            )
            time.sleep(RETRY_SLEEP_SECONDS)

    duration_seconds = round(time.monotonic() - start, 2)
    logger.info("[Harness] ✓ run_harness_analysis returned company=%s status=%s 耗时=%ss", cid, verification_status, duration_seconds)

    return {
        "company_id": cid,
        "verification_status": verification_status,
        "report": report,
        "process_text": process_text,
        "raw_events": raw_events,
        "attempts": attempts,
        "duration_seconds": duration_seconds,
    }
