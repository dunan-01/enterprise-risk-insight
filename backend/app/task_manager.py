"""
企业关联风险智能洞察系统 —— 异步任务管理器。

负责将同步阻塞的 Harness 分析（3-20分钟）封装为异步任务：
1. 创建任务（立即返回 task_id）
2. 后台线程执行 harness（复用 analysis_service.analyze_company）
3. 持久化任务状态到 runs/web/tasks/{task_id}.json
4. 单执行锁：同一时间只运行一个 harness（复用 harness_adapter._HARNESS_LOCK）
5. 去重：同一企业有 running/queued 任务时不创建重复任务

设计约束：
- 不修改 harness_adapter / analysis_service / risk.db
- 复用 deps.company_exists 做企业存在性检查
- 后台线程使用 threading.Thread(daemon=True) 启动
"""

from __future__ import annotations

import json
import logging
import threading
import time
import uuid
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Dict, Optional

from . import deps
from .analysis_service import analyze_company
from .harness_adapter import (
    CompanyNotFoundError,
    HarnessError,
    _HARNESS_LOCK,
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


class TaskInfo:
    """任务信息数据类。

    Attributes:
        task_id: 任务唯一ID，格式 task-{uuid4前8位}-{时间戳}
        company_id: 目标企业ID
        status: 任务状态（queued / running / completed / failed）
        created_at: 创建时间（ISO 8601）
        started_at: 开始执行时间（ISO 8601），queued 时为 None
        finished_at: 完成时间（ISO 8601），未完成时为 None
        error: 失败时的错误信息，其他状态为 None
        result: 完成时的分析结果 dict，其他状态为 None
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
    ) -> None:
        self.task_id = task_id
        self.company_id = company_id
        self.status = status
        self.created_at = created_at
        self.started_at = started_at
        self.finished_at = finished_at
        self.error = error
        self.result = result

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
        )


# ------------------------------------------------------------
# 持久化路径
# ------------------------------------------------------------

# 任务持久化目录：runs/web/tasks/
_PROJECT_ROOT = deps.PROJECT_ROOT
_TASKS_DIR = _PROJECT_ROOT / "runs" / "web" / "tasks"


def _now_iso() -> str:
    """返回当前 UTC 时间的 ISO 8601 字符串。"""
    return datetime.now(timezone.utc).isoformat()


def _generate_task_id() -> str:
    """生成 task_id，格式：task-{uuid4前8位}-{时间戳}。"""
    short_uuid = uuid.uuid4().hex[:8]
    timestamp = int(time.time())
    return f"task-{short_uuid}-{timestamp}"


# ------------------------------------------------------------
# TaskManager 单例
# ------------------------------------------------------------


class TaskManager:
    """后台任务管理器（单例）。

    职责：
    1. 创建任务（立即返回 task_id）
    2. 后台线程执行 harness
    3. 持久化任务状态到 runs/web/tasks/{task_id}.json
    4. 单执行锁：同一时间只运行一个 harness
    5. 去重：同一企业有 running/queued 任务时不创建重复
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
                    cls._instance = instance
        return cls._instance

    # ------------------------------------------------------------
    # 公共方法
    # ------------------------------------------------------------

    def create_task(self, company_id: str) -> TaskInfo:
        """创建分析任务。

        检查流程：
        1. 企业是否存在（复用 deps.company_exists）
        2. 是否已有 active 任务（queued/running）

        如果已有 active 任务：返回现有任务（不创建新的）
        否则：创建任务，持久化，启动后台线程，返回 task_id

        Args:
            company_id: 企业ID（内部会规范化）

        Returns:
            TaskInfo: 新创建或已有的任务信息

        Raises:
            CompanyNotFoundError: 企业不存在
        """
        cid = company_id.strip().upper()

        # 1. 企业存在性检查
        if not deps.company_exists(cid):
            raise CompanyNotFoundError(cid)

        # 2. 检查是否已有 active 任务
        existing = self.get_active_task_for_company(cid)
        if existing is not None:
            logger.info(
                "企业 %s 已有活跃任务 %s（状态: %s），返回现有任务",
                cid, existing.task_id, existing.status.value,
            )
            return existing

        # 3. 创建新任务
        task_id = _generate_task_id()
        now = _now_iso()
        task = TaskInfo(
            task_id=task_id,
            company_id=cid,
            status=TaskStatus.QUEUED,
            created_at=now,
        )

        # 4. 存入内存
        with self._memory_lock:
            self._tasks[task_id] = task

        # 5. 持久化
        self._persist_task(task)

        logger.info("创建分析任务: task_id=%s company_id=%s", task_id, cid)

        # 6. 启动后台线程
        thread = threading.Thread(
            target=self._run_task_background,
            args=(task_id,),
            daemon=True,
            name=f"harness-task-{task_id}",
        )
        thread.start()

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

    def startup_recovery(self) -> None:
        """服务启动时恢复：将 queued/running 的任务标记为 failed。

        进程重启后无法恢复后台线程执行，因此将未完成任务标记为失败。
        """
        _TASKS_DIR.mkdir(parents=True, exist_ok=True)

        recovered = 0
        for task_file in _TASKS_DIR.glob("*.json"):
            try:
                raw = task_file.read_text(encoding="utf-8")
                data = json.loads(raw)
                status = TaskStatus(data["status"])
                if status in (TaskStatus.QUEUED, TaskStatus.RUNNING):
                    # 标记为 failed
                    task = TaskInfo.from_dict(data)
                    task.status = TaskStatus.FAILED
                    task.finished_at = _now_iso()
                    task.error = "服务重启，未完成的任务已终止"
                    self._persist_task(task)
                    with self._memory_lock:
                        self._tasks[task.task_id] = task
                    recovered += 1
                    logger.info(
                        "启动恢复：任务 %s（企业 %s）已标记为 failed",
                        task.task_id, task.company_id,
                    )
            except (json.JSONDecodeError, KeyError, ValueError) as exc:
                logger.warning("加载任务文件 %s 失败: %s", task_file.name, exc)

        if recovered > 0:
            logger.info("启动恢复完成：共 %d 个未完成任务已标记为 failed", recovered)

    # ------------------------------------------------------------
    # 内部方法
    # ------------------------------------------------------------

    def _persist_task(self, task: TaskInfo) -> None:
        """持久化任务到 runs/web/tasks/{task_id}.json。"""
        _TASKS_DIR.mkdir(parents=True, exist_ok=True)
        task_file = _TASKS_DIR / f"{task.task_id}.json"
        try:
            data = task.to_dict()
            task_file.write_text(
                json.dumps(data, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except OSError as exc:
            logger.error("持久化任务 %s 失败: %s", task.task_id, exc)

    def _load_task(self, task_id: str) -> Optional[TaskInfo]:
        """从文件加载任务。"""
        task_file = _TASKS_DIR / f"{task_id}.json"
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
            logger.warning("加载任务文件 %s 失败: %s", task_id, exc)
            return None

    def _load_all_tasks_from_disk(self) -> None:
        """扫描磁盘加载所有任务到内存（去重）。"""
        _TASKS_DIR.mkdir(parents=True, exist_ok=True)
        for task_file in _TASKS_DIR.glob("*.json"):
            task_id = task_file.stem
            with self._memory_lock:
                if task_id in self._tasks:
                    continue
            self._load_task(task_id)

    def _run_task_background(self, task_id: str) -> None:
        """后台线程执行 harness 分析。

        流程：
        1. 从内存/磁盘加载任务
        2. 获取 _HARNESS_LOCK（串行化）
        3. 更新状态为 running，持久化
        4. 调用 analyze_company(company_id)
        5. 成功：更新为 completed，保存 result
        6. 失败：更新为 failed，保存 error
        7. 释放锁（由 with 语句自动处理）
        """
        with self._memory_lock:
            task = self._tasks.get(task_id)
        if task is None:
            logger.error("后台任务 %s 在内存中未找到，终止", task_id)
            return

        logger.info("后台任务开始执行: %s 企业: %s", task_id, task.company_id)

        # 获取 Harness 串行化锁
        with _HARNESS_LOCK:
            # 更新状态为 running
            task.status = TaskStatus.RUNNING
            task.started_at = _now_iso()
            self._persist_task(task)
            logger.info("任务 %s 状态更新为 running", task_id)

            try:
                # 调用分析服务
                result = analyze_company(task.company_id)

                # 成功：更新为 completed
                task.status = TaskStatus.COMPLETED
                task.finished_at = _now_iso()
                task.result = result
                self._persist_task(task)
                logger.info(
                    "任务 %s 完成: 企业 %s 风险等级=%s",
                    task_id, task.company_id,
                    result.get("risk_level"),
                )

            except CompanyNotFoundError as exc:
                # 企业不存在（理论上不会发生，创建时已检查）
                task.status = TaskStatus.FAILED
                task.finished_at = _now_iso()
                task.error = f"企业不存在: {exc.company_id}"
                self._persist_task(task)
                logger.error("任务 %s 失败: 企业不存在 %s", task_id, task.company_id)

            except HarnessError as exc:
                # Harness 调用失败
                task.status = TaskStatus.FAILED
                task.finished_at = _now_iso()
                task.error = f"Harness 分析失败: {exc}"
                self._persist_task(task)
                logger.error("任务 %s 失败: %s", task_id, exc)

            except Exception as exc:
                # 其他未预期异常
                task.status = TaskStatus.FAILED
                task.finished_at = _now_iso()
                task.error = f"分析过程异常: {exc}"
                self._persist_task(task)
                logger.exception("任务 %s 异常终止: %s", task_id, exc)

        logger.info(
            "后台任务执行结束: %s 状态: %s",
            task_id, task.status.value,
        )
