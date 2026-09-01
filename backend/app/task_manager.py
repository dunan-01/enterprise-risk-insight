"""
企业关联风险智能洞察系统 —— 异步任务管理器（V1.4 Single Active Harness Invariant）。

SINGLE ACTIVE HARNESS INVARIANT:
任何时刻，由本 risk-api 创建的 opencode run --agent risk-orchestrator ... 最多只能存在一个。
每次用户真正启动一次新的 AI 风险分析之前，必须先检查并清理此前遗留的 Risk Harness process，
确认旧进程完全退出之后，才能创建新的 OpenCode subprocess。

关键设计：
- PID/PGID 持久化到 task metadata（独立 process group）
- 统一 terminate_harness_process() 管理进程生命周期
- startup reconciliation：启动时清理 orphan process
- 每次启动新分析前 double-check：reconcile_existing_harness()
- cancelled 状态：区分 "用户主动替换" vs "系统失败"
- 同企业双击防护：已有 running task 时返回 existing（不创建新 task）
- 跨企业替换：终止旧 process group → cancelled → 启动新 task

设计约束：
- 不修改 harness_adapter / analysis_service / risk.db
- 复用 deps.company_exists 做企业存在性检查
- 后台线程使用 threading.Thread(daemon=True) 启动
"""

from __future__ import annotations

import json
import logging
import os
import signal
import subprocess
import threading
import time
import uuid
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from . import deps
from .analysis_service import analyze_company
from .harness_adapter import (
    CompanyNotFoundError,
    HarnessError,
)

logger = logging.getLogger("risk-api")

# ------------------------------------------------------------
# 任务状态与信息模型
# ------------------------------------------------------------


class TaskStatus(str, Enum):
    """任务状态枚举。"""

    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class TaskInfo:
    """任务信息数据类。

    Attributes:
        task_id: 任务唯一ID，格式 task-{uuid4前8位}-{时间戳}
        company_id: 目标企业ID
        status: 任务状态（queued / running / completed / failed / cancelled）
        created_at: 创建时间（ISO 8601）
        started_at: 开始执行时间（ISO 8601），queued 时为 None
        finished_at: 完成时间（ISO 8601），未完成时为 None
        error: 失败时的错误信息，其他状态为 None
        result: 完成时的分析结果 dict，其他状态为 None
        event_count: 已收到的事件数（V1.3 新增）
        last_event_at: 最后一个事件的时间（V1.3 新增）
        current_stage: 当前阶段（V1.3 新增）
        process_pid: OpenCode subprocess PID（V1.4 新增）
        process_pgid: OpenCode process group ID（V1.4 新增）
        process_alive: 进程是否仍然存活（V1.4 新增）
        cancel_reason: 取消原因（V1.4 新增）
        replacement_task_id: 替换此任务的新任务ID（V1.4 新增）
    """

    def __init__(
        self,
        task_id: str,
        company_id: str,
        status: TaskStatus,
        created_at: str,
        started_at: Optional[str] = None,
        finished_at: Optional[str] = None,
        error: Optional[str] = None,
        result: Optional[Dict[str, Any]] = None,
        event_count: int = 0,
        last_event_at: Optional[str] = None,
        current_stage: Optional[str] = None,
        process_pid: Optional[int] = None,
        process_pgid: Optional[int] = None,
        process_alive: bool = False,
        cancel_reason: Optional[str] = None,
        replacement_task_id: Optional[str] = None,
    ) -> None:
        self.task_id = task_id
        self.company_id = company_id
        self.status = status
        self.created_at = created_at
        self.started_at = started_at
        self.finished_at = finished_at
        self.error = error
        self.result = result
        self.event_count = event_count
        self.last_event_at = last_event_at
        self.current_stage = current_stage
        self.process_pid = process_pid
        self.process_pgid = process_pgid
        self.process_alive = process_alive
        self.cancel_reason = cancel_reason
        self.replacement_task_id = replacement_task_id

    def to_dict(self) -> Dict[str, Any]:
        """序列化为 JSON 可存储的 dict。"""
        return {
            "task_id": self.task_id,
            "company_id": self.company_id,
            "status": self.status.value,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "error": self.error,
            "result": self.result,
            "event_count": self.event_count,
            "last_event_at": self.last_event_at,
            "current_stage": self.current_stage,
            "process_pid": self.process_pid,
            "process_pgid": self.process_pgid,
            "process_alive": self.process_alive,
            "cancel_reason": self.cancel_reason,
            "replacement_task_id": self.replacement_task_id,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TaskInfo":
        """从 dict 反序列化。"""
        return cls(
            task_id=data["task_id"],
            company_id=data["company_id"],
            status=TaskStatus(data["status"]),
            created_at=data["created_at"],
            started_at=data.get("started_at"),
            finished_at=data.get("finished_at"),
            error=data.get("error"),
            result=data.get("result"),
            event_count=data.get("event_count", 0),
            last_event_at=data.get("last_event_at"),
            current_stage=data.get("current_stage"),
            process_pid=data.get("process_pid"),
            process_pgid=data.get("process_pgid"),
            process_alive=data.get("process_alive", False),
            cancel_reason=data.get("cancel_reason"),
            replacement_task_id=data.get("replacement_task_id"),
        )


# ------------------------------------------------------------
# 持久化路径
# ------------------------------------------------------------

# 任务持久化目录：runs/web/tasks/
_PROJECT_ROOT = deps.PROJECT_ROOT
_TASKS_DIR = _PROJECT_ROOT / "runs" / "web" / "tasks"

# Watchdog 超时：任务最长运行时间（秒）。
# 默认 40 分钟（2400 秒），覆盖 Harness 自身的 20 分钟超时 + 重试时间。
# 可通过环境变量 TASK_TIMEOUT_SECONDS 覆盖。
DEFAULT_TASK_TIMEOUT = 2400
TASK_TIMEOUT_ENV = "TASK_TIMEOUT_SECONDS"

# 清理相关常量
CLEANUP_SIGTERM_WAIT_SECONDS = 3.0  # SIGTERM 后等待时间
CLEANUP_VERIFY_INTERVAL = 0.5       # 验证进程不存在的轮询间隔
CLEANUP_VERIFY_MAX_RETRIES = 6      # 最多重试 6 次（共 3 秒）


def _now_iso() -> str:
    """返回当前 UTC 时间的 ISO 8601 字符串。"""
    return datetime.now(timezone.utc).isoformat()


def _generate_task_id() -> str:
    """生成 task_id，格式：task-{uuid4前8位}-{时间戳}。"""
    short_uuid = uuid.uuid4().hex[:8]
    timestamp = int(time.time())
    return f"task-{short_uuid}-{timestamp}"


def _resolve_task_timeout() -> int:
    """解析任务超时时间（秒）。"""
    raw = os.environ.get(TASK_TIMEOUT_ENV)
    if raw:
        try:
            value = int(raw)
            if value > 0:
                return value
        except ValueError:
            pass
    return DEFAULT_TASK_TIMEOUT


# ------------------------------------------------------------
# 进程管理工具函数
# ------------------------------------------------------------


def _is_pid_alive(pid: int) -> bool:
    """检查指定 PID 是否存活。"""
    try:
        os.kill(pid, 0)  # signal 0 = 只检查存在性，不发信号
        return True
    except (ProcessLookupError, PermissionError):
        return False


def _verify_process_command_line(pid: int) -> bool:
    """验证 PID 对应进程的 command line 是否包含 risk-orchestrator。

    防止误杀 opencode --port 等正常进程。
    在 macOS 上使用 ps 命令检查。
    """
    if not _is_pid_alive(pid):
        return False
    try:
        result = subprocess.run(
            ["ps", "-p", str(pid), "-o", "command="],
            capture_output=True,
            text=True,
            timeout=3,
        )
        cmdline = result.stdout.strip()
        if "opencode" in cmdline and "risk-orchestrator" in cmdline:
            return True
        if "opencode" in cmdline and "run" in cmdline:
            return True
        logger.warning(
            "[HarnessGuard] PID %d command line does not match risk-orchestrator: %s",
            pid, cmdline[:200],
        )
        return False
    except (subprocess.TimeoutExpired, OSError) as exc:
        logger.warning("[HarnessGuard] 无法读取 PID %d 的 command line: %s", pid, exc)
        return False


def _verify_project_dir(pid: int) -> bool:
    """验证 PID 对应进程的 working directory 是否为本项目目录。"""
    if not _is_pid_alive(pid):
        return False
    try:
        # macOS: lsof -p PID -d cwd -Fn
        result = subprocess.run(
            ["lsof", "-p", str(pid), "-d", "cwd", "-Fn"],
            capture_output=True,
            text=True,
            timeout=3,
        )
        for line in result.stdout.splitlines():
            if line.startswith("n"):
                cwd = line[1:]
                if str(_PROJECT_ROOT) in cwd:
                    return True
                logger.warning(
                    "[HarnessGuard] PID %d cwd=%s 不匹配项目目录 %s",
                    pid, cwd, _PROJECT_ROOT,
                )
                return False
        # lsof 没有输出 cwd —— 进程可能已退出
        return not _is_pid_alive(pid)
    except (subprocess.TimeoutExpired, OSError) as exc:
        logger.warning("[HarnessGuard] 无法读取 PID %d 的 cwd: %s", pid, exc)
        return False


def _terminate_process_group(pgid: int, pid: int, reason: str) -> bool:
    """终止整个 process group：SIGTERM → 等待 → SIGKILL。

    返回 True 表示成功清理（进程已不存在）。
    """
    logger.info(
        "[HarnessCleanup] terminating process group pgid=%s pid=%s reason=%s",
        pgid, pid, reason,
    )

    # 1. 尝试 SIGTERM 整个 process group
    try:
        os.killpg(pgid, signal.SIGTERM)
        logger.info("[HarnessCleanup] SIGTERM sent to pgid=%s", pgid)
    except (ProcessLookupError, PermissionError):
        # Process group 不存在或无权限，尝试单进程
        try:
            os.kill(pid, signal.SIGTERM)
        except (ProcessLookupError, PermissionError):
            pass

    # 2. 等待进程退出
    for _ in range(CLEANUP_VERIFY_MAX_RETRIES):
        time.sleep(CLEANUP_SIGTERM_WAIT_SECONDS / CLEANUP_VERIFY_MAX_RETRIES)
        if not _is_pid_alive(pid):
            logger.info("[HarnessCleanup] process exited after SIGTERM pid=%s", pid)
            return True

    # 3. SIGTERM 超时，发送 SIGKILL
    logger.warning(
        "[HarnessCleanup] SIGTERM timeout, sending SIGKILL pgid=%s pid=%s",
        pgid, pid,
    )
    try:
        os.killpg(pgid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError):
        try:
            os.kill(pid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            pass

    # 4. waitpid reap
    try:
        os.waitpid(pid, os.WNOHANG)
    except (ChildProcessError, OSError):
        pass

    # 5. 再次验证
    for _ in range(3):
        time.sleep(0.5)
        if not _is_pid_alive(pid):
            logger.info("[HarnessCleanup] process reaped after SIGKILL pid=%s", pid)
            return True

    return not _is_pid_alive(pid)


# ------------------------------------------------------------
# TaskManager 单例
# ------------------------------------------------------------


class TaskManager:
    """后台任务管理器（单例）。

    职责：
    1. 创建任务（立即返回 task_id）
    2. 后台线程执行 harness
    3. 持久化任务状态到 runs/web/tasks/{task_id}/task.json
    4. 去重：同一企业有 running/queued 任务时不创建重复
    5. Watchdog 超时保护：防止任务永久 running
    6. SINGLE ACTIVE HARNESS INVARIANT：任何时刻最多一个 harness process
    """

    _instance: Optional["TaskManager"] = None
    _init_lock = threading.Lock()

    def __new__(cls) -> "TaskManager":
        """单例模式。"""
        if cls._instance is None:
            with cls._init_lock:
                if cls._instance is None:
                    instance = super().__new__(cls)
                    instance._tasks: Dict[str, TaskInfo] = {}
                    instance._memory_lock = threading.Lock()
                    instance._cancel_events: Dict[str, threading.Event] = {}
                    cls._instance = instance
        return cls._instance

    # ============================================================
    # SINGLE ACTIVE HARNESS: 核心方法
    # ============================================================

    def get_active_task(self) -> Optional[TaskInfo]:
        """获取当前唯一的活跃任务（queued/running）。

        扫描内存中的任务，查找任何企业的活跃任务。
        """
        with self._memory_lock:
            for task in self._tasks.values():
                if task.status in (TaskStatus.QUEUED, TaskStatus.RUNNING):
                    return task
        return None

    def get_latest_completed_task_for_company(self, company_id: str) -> Optional[TaskInfo]:
        """获取企业最新已完成的任务（completed）。

        扫描内存中的任务，查找同一企业的最新已完成任务。
        同时从磁盘加载未缓存的任务进行检查（覆盖重启场景）。
        """
        cid = company_id.strip().upper()
        candidates: list[TaskInfo] = []

        # 扫描内存中的已完成任务
        with self._memory_lock:
            for task in self._tasks.values():
                if task.company_id == cid and task.status == TaskStatus.COMPLETED:
                    candidates.append(task)

        # 扫描磁盘上的任务文件（进程重启后可能内存为空）
        if not candidates:
            self._load_all_tasks_from_disk()
            with self._memory_lock:
                for task in self._tasks.values():
                    if task.company_id == cid and task.status == TaskStatus.COMPLETED:
                        candidates.append(task)

        if not candidates:
            return None

        # 按创建时间排序，返回最新的
        candidates.sort(key=lambda t: t.created_at, reverse=True)
        return candidates[0]

    def get_active_task_for_company(self, company_id: str) -> Optional[TaskInfo]:
        """获取企业当前活跃任务（queued/running）。

        扫描内存中的任务，查找同一企业的活跃任务。
        同时从磁盘加载未缓存的任务进行检查（覆盖重启场景）。
        """
        cid = company_id.strip().upper()

        # 扫描内存中的活跃任务
        with self._memory_lock:
            for task in self._tasks.values():
                if (
                    task.company_id == cid
                    and task.status in (TaskStatus.QUEUED, TaskStatus.RUNNING)
                ):
                    return task

        # 扫描磁盘上的任务文件（进程重启后可能内存为空）
        self._load_all_tasks_from_disk()
        with self._memory_lock:
            for task in self._tasks.values():
                if (
                    task.company_id == cid
                    and task.status in (TaskStatus.QUEUED, TaskStatus.RUNNING)
                ):
                    return task

        return None

    def terminate_harness_process(self, task: TaskInfo, reason: str) -> bool:
        """统一的进程清理函数。

        行为：
        1. 获取该 task 的 PID/PGID
        2. 检查进程是否仍然存在
        3. 验证 command line 确实是 risk-orchestrator
        4. 向整个 process group 发送 SIGTERM → 等待 → SIGKILL
        5. wait/reap
        6. 确认 PID 不存在
        7. 更新 process_alive = false
        8. 写日志
        """
        pid = task.process_pid
        pgid = task.process_pgid

        if pid is None:
            logger.info(
                "[HarnessCleanup] task %s 无 PID 记录，跳过进程清理",
                task.task_id,
            )
            return True

        # 检查进程是否仍然存在
        alive = _is_pid_alive(pid)
        logger.info(
            "[HarnessCleanup] task=%s pid=%s pgid=%s alive=%s reason=%s",
            task.task_id, pid, pgid, alive, reason,
        )

        if not alive:
            # 进程已不存在
            self._mark_process_cleaned(task)
            logger.info(
                "[HarnessCleanup] cleanup_verified=true task=%s pid=%s "
                "(process already exited)",
                task.task_id, pid,
            )
            return True

        # 进程存在 —— 验证归属
        if not _verify_process_command_line(pid):
            logger.warning(
                "[HarnessGuard] PID %s 的 command line 不匹配 risk-orchestrator，"
                "跳过清理以避免误杀",
                pid,
            )
            return False

        # 清理进程
        if pgid is None:
            pgid = pid  # fallback: 使用 PID 作为 PGID

        success = _terminate_process_group(pgid, pid, reason)

        # 更新 task metadata
        self._mark_process_cleaned(task)

        # 再次验证
        final_alive = _is_pid_alive(pid)
        logger.info(
            "[HarnessCleanup] cleanup_verified=%s task=%s pid=%s reason=%s",
            str(not final_alive).lower(), task.task_id, pid, reason,
        )

        return not final_alive

    def _mark_process_cleaned(self, task: TaskInfo) -> None:
        """标记 task 的进程已清理并持久化。"""
        task.process_alive = False
        self._persist_task(task)

    def reconcile_existing_harness(self, reason: str = "pre_analysis") -> Optional[str]:
        """检查并清理当前唯一的活跃 harness process。

        返回被终止的 task_id（如果有的话），否则返回 None。

        这是 SINGLE ACTIVE HARNESS INVARIANT 的核心保障：
        每次启动新分析之前必须调用。
        """
        logger.info("[HarnessGuard] checking previous harness reason=%s", reason)

        # 1. 从磁盘加载所有任务（覆盖重启场景）
        self._load_all_tasks_from_disk()

        # 2. 查找所有 active 任务
        active_tasks: List[TaskInfo] = []
        with self._memory_lock:
            for task in self._tasks.values():
                if task.status in (TaskStatus.QUEUED, TaskStatus.RUNNING):
                    active_tasks.append(task)

        if not active_tasks:
            logger.info("[HarnessGuard] no active harness found")
            return None

        # 3. 终止所有 active 任务（正常情况下最多一个）
        cancelled_task_id = None
        for task in active_tasks:
            logger.info(
                "[HarnessGuard] old task found task_id=%s company=%s pid=%s status=%s",
                task.task_id, task.company_id,
                task.process_pid, task.status.value,
            )

            # 尝试清理进程
            self.terminate_harness_process(task, reason=reason)

            # 标记为 cancelled
            task.status = TaskStatus.CANCELLED
            task.finished_at = _now_iso()
            task.cancel_reason = reason
            self._persist_task(task)
            cancelled_task_id = task.task_id

            logger.info(
                "[Task] old task → cancelled task_id=%s company=%s reason=%s",
                task.task_id, task.company_id, reason,
            )

        return cancelled_task_id

    def cancel_task(self, task_id: str, reason: str = "user_cancelled") -> TaskInfo:
        """用户主动取消指定任务。
        
        行为：
        - queued → 直接 cancelled（无需杀进程）
        - running → terminate_harness_process → cancelled
        - completed/failed/cancelled → 返回幂等结果（不修改已有状态）
        
        返回 cancel 后的 TaskInfo。
        """
        logger.info("[Cancel] request received: task_id=%s reason=%s", task_id, reason)
        
        # 1. 先从内存或磁盘加载 task（复用 get_task()）
        task = self.get_task(task_id)
        if task is None:
            logger.warning("[Cancel] task not found: %s", task_id)
            raise ValueError("TASK_NOT_FOUND")
        
        logger.info("[Cancel] task loaded: task_id=%s status=%s company=%s pid=%s alive=%s",
                     task_id, task.status.value, task.company_id,
                     task.process_pid, task.process_alive)
        
        # 2. 如果 task 不存在 → 抛出 ValueError("TASK_NOT_FOUND")
        # 已在上方处理
        
        # 3. 如果 status == COMPLETED → 抛出 ValueError("TASK_ALREADY_COMPLETED")
        if task.status == TaskStatus.COMPLETED:
            raise ValueError("TASK_ALREADY_COMPLETED")
        
        # 4. 如果 status == FAILED → 抛出 ValueError("TASK_ALREADY_FINISHED")
        if task.status == TaskStatus.FAILED:
            raise ValueError("TASK_ALREADY_FINISHED")
        
        # 5. 如果 status == CANCELLED → 直接返回当前 task（幂等）
        if task.status == TaskStatus.CANCELLED:
            return task
        
        # 6. 如果 status == QUEUED:
        if task.status == TaskStatus.QUEUED:
            task.status = TaskStatus.CANCELLED
            task.finished_at = _now_iso()
            task.cancel_reason = reason
            task.process_alive = False
            self._persist_task(task)
            logger.info(
                "[Task] queued → cancelled: task_id=%s company=%s reason=%s",
                task.task_id, task.company_id, reason,
            )
            return task
        
        # 7. 如果 status == RUNNING:
        if task.status == TaskStatus.RUNNING:
            logger.info("[Cancel] terminating running task: task_id=%s pid=%s pgid=%s",
                         task_id, task.process_pid, task.process_pgid)
            # 设置取消信号事件（通知后台线程停止）
            cancel_event = self._cancel_events.get(task_id)
            if cancel_event:
                cancel_event.set()
                logger.info("[Cancel] cancel_event set for task %s", task_id)
            
            # 终止 harness 进程
            self.terminate_harness_process(task, reason=reason)
            
            # 更新任务状态
            task.status = TaskStatus.CANCELLED
            task.finished_at = _now_iso()
            task.cancel_reason = reason
            task.process_alive = False
            self._persist_task(task)
            
            # 生成 trace.json（保留取消前的调查轨迹）
            task_dir = _TASKS_DIR / task.task_id
            if task_dir.exists():
                self._generate_trace_json(task, task_dir)
            
            logger.info(
                "[Task] running → cancelled: task_id=%s company=%s reason=%s",
                task.task_id, task.company_id, reason,
            )
            logger.info("[Cancel] completed: task_id=%s status=cancelled", task_id)
            return task
        
        # 理论上不会到这里
        logger.info("[Cancel] completed (no-op): task_id=%s status=%s", task_id, task.status.value)
        return task

    def assert_single_harness_invariant(self) -> None:
        """启动新任务前的硬性检查：确认系统中不存在旧的 risk-orchestrator process。

        如果发现由本系统管理的 risk-orchestrator 仍然 alive，则先清理。
        清理失败时抛出 HarnessError。
        """
        self._load_all_tasks_from_disk()

        with self._memory_lock:
            for task in self._tasks.values():
                if task.status in (TaskStatus.QUEUED, TaskStatus.RUNNING):
                    if task.process_pid is not None and task.process_alive:
                        # 验证进程是否真的存在
                        if _is_pid_alive(task.process_pid):
                            logger.warning(
                                "[HarnessInvariant] active harness found: "
                                "task=%s pid=%s pgid=%s company=%s",
                                task.task_id, task.process_pid,
                                task.process_pgid, task.company_id,
                            )
                            # 尝试清理
                            success = self.terminate_harness_process(
                                task, reason="invariant_violation",
                            )
                            if not success:
                                raise HarnessError(
                                    f"无法清理旧的 Harness 进程 "
                                    f"(task={task.task_id}, pid={task.process_pid})，"
                                    f"请手动终止后重试"
                                )
                        else:
                            # 进程已不存在，标记为 cancelled
                            task.status = TaskStatus.CANCELLED
                            task.finished_at = _now_iso()
                            task.cancel_reason = "process_already_exited"
                            task.process_alive = False
                            self._persist_task(task)

    def startup_reconcile_harness_processes(self) -> int:
        """Backend 启动时执行 orphan reconciliation。

        读取持久化 task metadata，对 status=running 但对应进程已失效的任务：
        1. 检查 process_pid / process_pgid 是否仍存在
        2. 如果存在且确认属于本 risk-api 创建的 risk-orchestrator：
           终止整个 process group
        3. 任务标记为 cancelled，reason = backend_restart_recovery

        返回被清理的任务数量。
        """
        _TASKS_DIR.mkdir(parents=True, exist_ok=True)
        cleaned = 0

        # V1.3 格式：每个 task 是一个目录，task.json 在子目录中
        for task_dir in _TASKS_DIR.iterdir():
            if not task_dir.is_dir():
                continue
            task_file = task_dir / "task.json"
            if not task_file.exists():
                continue
            try:
                raw = task_file.read_text(encoding="utf-8")
                data = json.loads(raw)
                status = TaskStatus(data["status"])
                if status in (TaskStatus.QUEUED, TaskStatus.RUNNING):
                    task = TaskInfo.from_dict(data)

                    # 尝试清理进程
                    if task.process_pid is not None:
                        alive = _is_pid_alive(task.process_pid)
                        if alive:
                            # 验证归属
                            if _verify_process_command_line(task.process_pid):
                                logger.info(
                                    "[StartupReconcile] orphan harness found: "
                                    "task=%s pid=%s company=%s",
                                    task.task_id, task.process_pid, task.company_id,
                                )
                                self.terminate_harness_process(
                                    task, reason="backend_restart_recovery",
                                )
                            else:
                                logger.warning(
                                    "[StartupReconcile] PID %s 不是 risk-orchestrator，跳过",
                                    task.process_pid,
                                )

                    # 标记为 cancelled
                    task.status = TaskStatus.CANCELLED
                    task.finished_at = _now_iso()
                    task.cancel_reason = "backend_restart_recovery"
                    task.process_alive = False
                    self._persist_task(task)
                    with self._memory_lock:
                        self._tasks[task.task_id] = task
                    cleaned += 1
                    logger.info(
                        "[StartupReconcile] task %s（企业 %s）→ cancelled",
                        task.task_id, task.company_id,
                    )
            except (json.JSONDecodeError, KeyError, ValueError) as exc:
                logger.warning(
                    "[StartupReconcile] 加载任务文件 %s 失败: %s", task_file, exc
                )

        # V1.2 兼容：旧格式的平文件
        for task_file in _TASKS_DIR.glob("*.json"):
            try:
                raw = task_file.read_text(encoding="utf-8")
                data = json.loads(raw)
                status = TaskStatus(data["status"])
                if status in (TaskStatus.QUEUED, TaskStatus.RUNNING):
                    task = TaskInfo.from_dict(data)
                    if task.process_pid is not None and _is_pid_alive(task.process_pid):
                        if _verify_process_command_line(task.process_pid):
                            self.terminate_harness_process(
                                task, reason="backend_restart_recovery",
                            )
                    task.status = TaskStatus.CANCELLED
                    task.finished_at = _now_iso()
                    task.cancel_reason = "backend_restart_recovery"
                    task.process_alive = False
                    self._persist_task(task)
                    with self._memory_lock:
                        self._tasks[task.task_id] = task
                    cleaned += 1
                    logger.info(
                        "[StartupReconcile] task %s（企业 %s）→ cancelled",
                        task.task_id, task.company_id,
                    )
            except (json.JSONDecodeError, KeyError, ValueError) as exc:
                logger.warning(
                    "[StartupReconcile] 加载任务文件 %s 失败: %s", task_file.name, exc
                )

        if cleaned > 0:
            logger.info(
                "[StartupReconcile] done: %d orphan tasks cleaned", cleaned
            )
        return cleaned

    # ============================================================
    # 公共方法
    # ============================================================

    def create_task(self, company_id: str, force_new: bool = False) -> TaskInfo:
        """创建分析任务。

        SINGLE ACTIVE HARNESS 流程：
        1. 企业是否存在
        2. reconcile_existing_harness() —— 清理旧 active / orphan Harness
        3. 确认系统中不存在旧 risk-orchestrator
        4. 同企业双击防护：已有 running task 时返回 existing
        5. 创建新 task
        6. 启动后台线程

        参数：
            company_id: 企业ID
            force_new: 是否强制创建新任务（替换旧任务）。用于"重新分析"按钮。
        """
        cid = company_id.strip().upper()

        # 1. 企业存在性检查
        if not deps.company_exists(cid):
            raise CompanyNotFoundError(cid)

        # 2. reconcile: 清理旧 active / orphan Harness
        self.reconcile_existing_harness(reason="replaced_by_new_analysis")

        # 3. 同企业双击防护：已有 running task 时返回 existing
        if not force_new:
            existing = self.get_active_task_for_company(cid)
            if existing is not None:
                logger.info(
                    "[Task] 企业 %s 已有活跃任务 %s（状态: %s），返回现有任务",
                    cid, existing.task_id, existing.status.value,
                )
                return existing

        # 4. 确认单 harness invariant
        self.assert_single_harness_invariant()

        # 5. 创建新任务
        task_id = _generate_task_id()
        now = _now_iso()
        task = TaskInfo(
            task_id=task_id,
            company_id=cid,
            status=TaskStatus.QUEUED,
            created_at=now,
        )

        # 6. 存入内存
        with self._memory_lock:
            self._tasks[task_id] = task

        # 7. 持久化
        self._persist_task(task)

        logger.info(
            "[Task] new task created: task_id=%s company_id=%s", task_id, cid
        )

        # 8. 启动后台线程
        thread = threading.Thread(
            target=self._run_task_background,
            args=(task_id,),
            daemon=True,
            name=f"harness-task-{task_id}",
        )
        thread.start()
        logger.info("[Task] background thread started: %s", task_id)

        return task

    def get_task(self, task_id: str) -> Optional[TaskInfo]:
        """获取任务状态。

        先查内存，内存未命中则从文件加载（支持进程重启后查询历史任务）。
        """
        # 1. 内存查询
        with self._memory_lock:
            if task_id in self._tasks:
                return self._tasks[task_id]

        # 2. 文件加载
        return self._load_task(task_id)

    # ------------------------------------------------------------
    # 内部方法
    # ------------------------------------------------------------

    def _persist_task(self, task: TaskInfo) -> None:
        """持久化任务到 runs/web/tasks/{task_id}/task.json。"""
        task_dir = _TASKS_DIR / task.task_id
        task_dir.mkdir(parents=True, exist_ok=True)
        task_file = task_dir / "task.json"
        try:
            data = task.to_dict()
            task_file.write_text(
                json.dumps(data, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except OSError as exc:
            logger.error("[Task] 持久化任务 %s 失败: %s", task.task_id, exc)

    def _load_task(self, task_id: str) -> Optional[TaskInfo]:
        """从文件加载任务（兼容 V1.2 单文件格式和 V1.3 per-task 目录格式）。"""
        # V1.3 格式：runs/web/tasks/{task_id}/task.json
        task_file_v13 = _TASKS_DIR / task_id / "task.json"
        # V1.2 格式：runs/web/tasks/{task_id}.json
        task_file_v12 = _TASKS_DIR / f"{task_id}.json"

        task_file = task_file_v13 if task_file_v13.exists() else task_file_v12
        if not task_file.exists():
            return None
        try:
            raw = task_file.read_text(encoding="utf-8")
            data = json.loads(raw)
            task = TaskInfo.from_dict(data)
            # 缓存到内存
            with self._memory_lock:
                self._tasks[task_id] = task
            return task
        except (json.JSONDecodeError, KeyError, ValueError, OSError) as exc:
            logger.warning("[Task] 加载任务文件 %s 失败: %s", task_id, exc)
            return None

    def _load_all_tasks_from_disk(self) -> None:
        """扫描磁盘加载所有任务到内存（去重），兼容 V1.2 和 V1.3 格式。"""
        _TASKS_DIR.mkdir(parents=True, exist_ok=True)
        # V1.3 格式：每个 task 是一个目录
        for task_dir in _TASKS_DIR.iterdir():
            if not task_dir.is_dir():
                continue
            task_id = task_dir.name
            with self._memory_lock:
                if task_id in self._tasks:
                    continue
            self._load_task(task_id)
        # V1.2 兼容：旧格式的 JSON 文件
        for task_file in _TASKS_DIR.glob("*.json"):
            task_id = task_file.stem
            with self._memory_lock:
                if task_id in self._tasks:
                    continue
            self._load_task(task_id)

    def _update_task_status(
        self,
        task: TaskInfo,
        status: TaskStatus,
        error: Optional[str] = None,
        result: Optional[Dict[str, Any]] = None,
    ) -> None:
        """更新任务状态并持久化（原子操作）。"""
        task.status = status
        if status == TaskStatus.RUNNING:
            task.started_at = _now_iso()
        elif status in (TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED):
            task.finished_at = _now_iso()
        if error is not None:
            task.error = error
        if result is not None:
            task.result = result
        self._persist_task(task)
        logger.info(
            "[Task] status → %s: %s 企业: %s",
            status.value, task.task_id, task.company_id,
        )

    def _run_task_background(self, task_id: str) -> None:
        """后台线程执行 harness 分析。

        SINGLE ACTIVE HARNESS 设计：
        - 记录 PID/PGID 并持久化
        - watchdog 超时保护
        - 所有异常路径都执行 terminate_harness_process
        - 正常 completed 后也验证进程已消失
        """
        with self._memory_lock:
            task = self._tasks.get(task_id)
        if task is None:
            logger.error("[Task] background: %s 在内存中未找到，终止", task_id)
            return

        logger.info(
            "[Task] background coroutine entered: %s 企业: %s",
            task_id, task.company_id,
        )

        # 更新状态为 running
        self._update_task_status(task, TaskStatus.RUNNING)

        # 创建 per-task 输出目录（V1.3）
        task_dir = _TASKS_DIR / task_id
        task_dir.mkdir(parents=True, exist_ok=True)

        # V1.3：实时事件回调，更新 task metadata 并持久化
        def _on_event(event_dict: dict, event_count: int) -> None:
            """实时回调：每收到一个 JSONL event 就更新 task metadata。"""
            try:
                task.event_count = event_count
                task.last_event_at = _now_iso()
                # 简单推断 current_stage
                ev_type = event_dict.get("type", "")
                if ev_type == "tool_use":
                    tool = event_dict.get("part", {}).get("tool", "")
                    if "coverage" in str(tool).lower():
                        task.current_stage = "coverage_audit"
                    elif "verif" in str(tool).lower():
                        task.current_stage = "verification"
                    else:
                        task.current_stage = "investigation"
                elif ev_type == "text":
                    text = str(event_dict.get("part", {}).get("text", ""))
                    if "COVERAGE_STATUS" in text:
                        task.current_stage = "coverage_audit"
                    elif "VERIFICATION_STATUS" in text or "VERDICT" in text:
                        task.current_stage = "verification"
                self._persist_task(task)
            except Exception as exc:
                logger.debug("[Task] on_event 更新 metadata 失败: %s", exc)

        # 启动 watchdog 超时保护线程
        task_timeout = _resolve_task_timeout()
        watchdog_cancelled = threading.Event()

        # V1.5: 创建取消信号事件，传递给 harness_adapter 和 watchdog
        cancel_event = threading.Event()
        self._cancel_events[task_id] = cancel_event

        def _watchdog():
            """Watchdog：超时后终止进程并标记为 failed。"""
            if watchdog_cancelled.wait(timeout=task_timeout):
                return  # 正常取消
            # 超时！终止进程并标记为 failed
            logger.warning(
                "[Task] watchdog timeout (%ss): %s 企业: %s → terminate + failed",
                task_timeout, task_id, task.company_id,
            )
            # 终止 harness process
            self.terminate_harness_process(task, reason="analysis_timeout")
            # V1.5: 设置取消信号，防止后台线程覆盖状态
            cancel_event.set()
            with self._memory_lock:
                current = self._tasks.get(task_id)
                if current and current.status in (TaskStatus.QUEUED, TaskStatus.RUNNING):
                    self._update_task_status(
                        current,
                        TaskStatus.FAILED,
                        error=f"任务超时（{task_timeout}s），已自动终止",
                    )

        watchdog_thread = threading.Thread(
            target=_watchdog,
            daemon=True,
            name=f"watchdog-{task_id}",
        )
        watchdog_thread.start()

        # V1.5: on_process_start 回调：从 Popen 获取准确 PID，替代不可靠的 pgrep
        def _on_process_start(pid: int, pgid: int) -> None:
            """subprocess 启动回调：直接从 Popen.pid 获取 PID。"""
            task.process_pid = pid
            task.process_pgid = pgid
            task.process_alive = True
            self._persist_task(task)
            logger.info(
                "[Task] harness process started (via callback): "
                "task=%s pid=%s pgid=%s",
                task_id, pid, pgid,
            )

        process = None
        try:
            # 调用分析服务
            logger.info(
                "[Task] about to call analyze_company: %s 企业: %s",
                task_id, task.company_id,
            )

            result = analyze_company(
                task.company_id,
                task_dir=task_dir,
                on_event=_on_event,
                task_id=task_id,
                cancelled_event=cancel_event,
                on_process_start=_on_process_start,
            )

            # 取消 watchdog
            watchdog_cancelled.set()

            # V1.5: 检查是否已被取消（cancel_task 可能已经设置了状态）
            if cancel_event.is_set():
                logger.info(
                    "[Task] 取消信号已设置，跳过 completed 状态更新: %s",
                    task_id,
                )
                return

            # 即使 return_code=0，也需要确认进程已消失
            if task.process_pid and _is_pid_alive(task.process_pid):
                logger.warning(
                    "[Task] process still alive after completed: task=%s pid=%s, "
                    "attempting cleanup",
                    task_id, task.process_pid,
                )
                self.terminate_harness_process(task, reason="post_completion_cleanup")

            # 成功：更新为 completed
            task.event_count = task.event_count
            task.current_stage = "completed"
            self._update_task_status(task, TaskStatus.COMPLETED, result=result)

            # V1.4: 生成 trace.json（source of truth）
            self._generate_trace_json(task, task_dir)

            logger.info(
                "[Task] ✓ completed: %s 企业: %s 风险等级=%s 耗时=%ss",
                task_id, task.company_id,
                result.get("risk_level"),
                result.get("duration_seconds"),
            )

        except CompanyNotFoundError as exc:
            watchdog_cancelled.set()
            self.terminate_harness_process(task, reason="company_not_found")
            # V1.5: 检查是否已被取消
            if not cancel_event.is_set():
                self._update_task_status(
                    task,
                    TaskStatus.FAILED,
                    error=f"企业不存在: {exc.company_id}",
                )
            logger.error(
                "[Task] ✗ failed (company not found): %s 企业: %s",
                task_id, task.company_id,
            )

        except HarnessError as exc:
            watchdog_cancelled.set()
            self.terminate_harness_process(task, reason="harness_error")
            # V1.5: 被取消的 HarnessError 不标记为 failed
            if cancel_event.is_set():
                logger.info(
                    "[Task] HarnessError after cancel (ignored): %s %s", task_id, exc
                )
            else:
                self._update_task_status(
                    task,
                    TaskStatus.FAILED,
                    error=f"Harness 分析失败: {exc}",
                )
                logger.error("[Task] ✗ failed (harness error): %s %s", task_id, exc)

        except Exception as exc:
            watchdog_cancelled.set()
            self.terminate_harness_process(task, reason="task_exception")
            # V1.5: 检查是否已被取消
            if not cancel_event.is_set():
                self._update_task_status(
                    task,
                    TaskStatus.FAILED,
                    error=f"分析过程异常: {exc}",
                )
            logger.exception("[Task] ✗ failed (exception): %s %s", task_id, exc)

        finally:
            # 确保 watchdog 被取消
            watchdog_cancelled.set()

            # V1.5: 清理 cancel_event
            self._cancel_events.pop(task_id, None)

            # 确保进程已清理（双重保险）
            if task.process_pid and task.process_alive:
                self.terminate_harness_process(task, reason="finally_cleanup")

            logger.info(
                "[Task] background execution ended: %s 状态: %s",
                task_id, task.status.value,
            )

    def _load_raw_events_from_task_dir(self, task_dir: Path) -> List[Dict[str, Any]]:
        """从 per-task 目录的 session_events.jsonl 加载 raw events。"""
        events_file = task_dir / "session_events.jsonl"
        if not events_file.exists():
            return []
        events: List[Dict[str, Any]] = []
        try:
            with open(events_file, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        events.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue
        except OSError:
            pass
        return events

    def _generate_trace_json(self, task: TaskInfo, task_dir: Path) -> None:
        """任务 completed 后生成 trace.json（结构化调查轨迹）。

        从 session_events.jsonl 读取 raw events，调用 trace parser 生成结构化 trace，
        保存到 task 目录作为历史访问的 source of truth。
        """
        try:
            from .trace_service import parse_trace_events

            raw_events = self._load_raw_events_from_task_dir(task_dir)
            if not raw_events:
                logger.warning(
                    "[Task] trace.json 生成跳过：无 raw events task=%s",
                    task.task_id,
                )
                return

            trace_events = parse_trace_events(raw_events, task_status=task.status.value)

            trace_data = {
                "task_id": task.task_id,
                "company_id": task.company_id,
                "task_status": task.status.value,
                "event_count": len(trace_events),
                "events": trace_events,
            }

            trace_file = task_dir / "trace.json"
            trace_file.write_text(
                json.dumps(trace_data, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

            logger.info(
                "[Task] trace.json generated: task=%s events=%d",
                task.task_id, len(trace_events),
            )
        except Exception as exc:
            # trace.json 生成失败不阻断主流程
            logger.warning(
                "[Task] trace.json 生成失败（非致命）: task=%s error=%s",
                task.task_id, exc,
            )
