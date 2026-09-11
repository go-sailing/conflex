"""进程内异步任务管理器（SDD 9.3）。

- 数据更新类 Job 全局互斥（防数据源限频）；回测类最多 2 并发，其余排队。
- 状态持久化到 job 表；进度/日志通过订阅者队列向 SSE/CLI 广播。
"""
from __future__ import annotations

import queue
import threading
import traceback
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable

from conflex.domain.models import JobStatus


@dataclass
class JobContext:
    job_id: int
    params: dict
    cancel_event: threading.Event
    _manager: "JobManager"

    def report_progress(self, progress: float, stage: str = ""):
        self._manager._update(self.job_id, progress=progress, stage=stage)

    def log(self, msg: str):
        self._manager._append_log(self.job_id, msg)

    @property
    def cancelled(self) -> bool:
        return self.cancel_event.is_set()


@dataclass
class _Job:
    id: int
    kind: str
    params: dict
    fn: Callable
    ctx: JobContext
    status: JobStatus = JobStatus.QUEUED
    progress: float = 0.0
    stage: str = "queued"
    error: str = ""
    result: Any = None
    logs: list[str] = field(default_factory=list)
    subscribers: list[queue.Queue] = field(default_factory=list)
    lock: threading.Lock = field(default_factory=threading.Lock)


_GLOBAL_KINDS = {"data_update", "data_repair", "bootstrap", "factor_analysis"}
_MAX_CONCURRENCY = {"backtest": 2}


def _safe(obj: Any) -> Any:
    """结果原样返回；持久化时用 json(default=str) 兜底序列化。"""
    return obj


class JobManager:
    def __init__(self, repo, max_workers: int = 4):
        self.repo = repo
        self.executor = ThreadPoolExecutor(max_workers=max_workers,
                                           thread_name_prefix="conflex-job")
        self._jobs: dict[int, _Job] = {}
        self._global_busy = threading.Lock()  # 数据类任务互斥
        self._kind_slots = threading.Semaphore(_MAX_CONCURRENCY["backtest"])
        self._lock = threading.Lock()

    def submit(self, kind: str, params: dict, fn: Callable,
               created_by: int | None = None) -> int:
        logs_file = ""
        job_id = self.repo.insert_job(kind, params, created_by, logs_file)
        cancel_event = threading.Event()
        ctx = JobContext(job_id, params, cancel_event, self)
        job = _Job(id=job_id, kind=kind, params=params, fn=fn, ctx=ctx)
        with self._lock:
            self._jobs[job_id] = job
        self.repo.update_job(job_id, status=JobStatus.QUEUED.value, stage="queued")
        self.executor.submit(self._run, job)
        return job_id

    def _run(self, job: _Job):
        if job.kind in _GLOBAL_KINDS:
            job.ctx.log("等待数据任务全局锁…")
            self._global_busy.acquire()
        if job.kind == "backtest":
            self._kind_slots.acquire()
        try:
            job.status = JobStatus.RUNNING
            self.repo.update_job(job.id, status=JobStatus.RUNNING.value,
                                 started_at=datetime.now().isoformat(timespec="seconds"),
                                 stage="running")
            self._publish(job, {"type": "status", "status": "running"})
            result = job.fn(job.ctx)
            job.result = result
            job.status = JobStatus.SUCCEEDED
            job.progress = 1.0
            self.repo.update_job(
                job.id, status=JobStatus.SUCCEEDED.value, progress=1.0, stage="succeeded",
                result_json=__import__("json").dumps(_safe(result), ensure_ascii=False, default=str),
                finished_at=datetime.now().isoformat(timespec="seconds"))
            self._publish(job, {"type": "finished", "result": _safe(result)})
        except Exception as exc:  # noqa: BLE001
            job.status = JobStatus.FAILED
            job.error = str(exc)
            tb = traceback.format_exc()
            job.logs.append(tb)
            self.repo.update_job(job.id, status=JobStatus.FAILED.value,
                                 error=str(exc), stage="failed",
                                 finished_at=datetime.now().isoformat(timespec="seconds"))
            self._publish(job, {"type": "error", "error": str(exc)})
        finally:
            if job.kind in _GLOBAL_KINDS:
                self._global_busy.release()
            if job.kind == "backtest":
                self._kind_slots.release()
            with self._lock:
                self._jobs.pop(job.id, None)

    # ---- 进度/日志/订阅 ----
    def _update(self, job_id: int, progress: float, stage: str):
        job = self._jobs.get(job_id)
        if not job:
            return
        job.progress = progress
        job.stage = stage
        self.repo.update_job(job_id, progress=progress, stage=stage)
        self._publish(job, {"type": "progress", "progress": progress, "stage": stage})

    def _append_log(self, job_id: int, msg: str):
        job = self._jobs.get(job_id)
        if not job:
            return
        line = f"[{datetime.now().strftime('%H:%M:%S')}] {msg}"
        job.logs.append(line)
        self._publish(job, {"type": "log", "line": line})

    def _publish(self, job: _Job, event: dict):
        with job.lock:
            dead = []
            for q in job.subscribers:
                try:
                    q.put_nowait(event)
                except queue.Full:
                    dead.append(q)
            for q in dead:
                job.subscribers.remove(q)

    def subscribe(self, job_id: int) -> queue.Queue:
        q: queue.Queue = queue.Queue(maxsize=1000)
        job = self._jobs.get(job_id)
        if job:
            with job.lock:
                job.subscribers.append(q)
        return q

    def unsubscribe(self, job_id: int, q: queue.Queue):
        job = self._jobs.get(job_id)
        if job and q in job.subscribers:
            job.subscribers.remove(q)

    def cancel(self, job_id: int):
        job = self._jobs.get(job_id)
        if job:
            job.cancel_event.set()
            self.repo.update_job(job_id, stage="cancelling")

    def get(self, job_id: int) -> dict:
        d = self.repo.get_job(job_id)
        if d is None:
            raise KeyError(job_id)
        job = self._jobs.get(job_id)
        if job:
            d["live_logs"] = list(job.logs[-200:])
        return d
