from __future__ import annotations

import os
import queue
import uuid
from collections.abc import Iterable
from typing import TypedDict, cast

from claude_experimental._flags import get_feature_flag
from claude_experimental.parallel.aggregation import ResultAggregator, strategy_for_mode
from claude_experimental.parallel.api import IndividualResult, ParallelResult
from claude_experimental.parallel.executor import ParallelExecutor, TaskSpec
from claude_experimental.parallel.ralph_bridge import RalphBridge
from claude_experimental.parallel.scaling import DynamicPool


class TaskInfo(TypedDict):
    agent_name: str
    prompt: str
    timeout: int
    batch_id: str | None
    priority: int


class JobMeta(TypedDict):
    status: str
    task: TaskInfo
    executor_job_id: str | None
    record: dict[str, object] | None


def _coerce_int(value: object, default: int) -> int:
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return default
    return default


def _extract_individual_result(recipient: str, record: dict[str, object]) -> IndividualResult:
    artifact: dict[str, object] | None = None
    artifacts_obj = record.get("artifacts")
    if isinstance(artifacts_obj, list) and artifacts_obj:
        candidate = cast(object, artifacts_obj[-1])
        if isinstance(candidate, dict):
            artifact = cast(dict[str, object], candidate)

    if artifact is not None:
        exit_code = _coerce_int(artifact.get("exit_code", 1), 1)
        duration_ms = _coerce_int(artifact.get("duration_ms", 0), 0)
        content = str(artifact.get("content", ""))
    else:
        status = str(record.get("status", "failed"))
        exit_code = 0 if status == "completed" else 1
        duration_ms = 0
        content = str(record.get("error", ""))

    return IndividualResult(
        recipient=recipient,
        content=content,
        exit_code=exit_code,
        duration_ms=duration_ms,
    )


class UltraworkerRouter:

    def __init__(self, min_workers: int = 1, max_workers: int = 8) -> None:
        self._require_ultraworker()

        self._pool: DynamicPool = DynamicPool(min_workers=min_workers, max_workers=max_workers)
        self._executor: ParallelExecutor = ParallelExecutor()
        self._aggregator: ResultAggregator = ResultAggregator(strategy_for_mode("BEST_RESULT"))
        self._ralph_bridge: RalphBridge = RalphBridge()

        self._queue: queue.PriorityQueue[tuple[int, int, str, TaskInfo]] = queue.PriorityQueue()
        self._sequence_num: int = 0
        self._completed_count: int = 0
        self._total_cost_units: int = 0
        self._shutdown: bool = False

        self._jobs: dict[str, JobMeta] = {}

        _ = os.environ.setdefault("OMG_PARALLEL_DISPATCH_ENABLED", "1")

    def _require_ultraworker(self) -> None:
        if not get_feature_flag("ULTRAWORKER", default=False):
            raise RuntimeError(
                "Ultraworker is disabled. Enable with: OMG_ULTRAWORKER_ENABLED=1"
            )

    def _next_sequence(self) -> int:
        self._sequence_num += 1
        return self._sequence_num

    def submit(
        self,
        task_description: str,
        agent_name: str = "explore",
        priority: int = 1,
        batch_id: str | None = None,
    ) -> str:
        self._require_ultraworker()
        if self._shutdown:
            raise RuntimeError("UltraworkerRouter is shut down")

        normalized_priority = int(priority)
        job_id = str(uuid.uuid4())
        task_info: TaskInfo = {
            "agent_name": agent_name,
            "prompt": task_description,
            "timeout": 300,
            "batch_id": batch_id,
            "priority": normalized_priority,
        }

        self._jobs[job_id] = {
            "status": "queued",
            "task": task_info,
            "executor_job_id": None,
            "record": None,
        }
        self._queue.put((-normalized_priority, self._next_sequence(), job_id, task_info))
        self._total_cost_units += 1
        return job_id

    def submit_batch(self, tasks: list[dict[str, object]], batch_id: str | None = None) -> list[str]:
        self._require_ultraworker()
        if self._shutdown:
            raise RuntimeError("UltraworkerRouter is shut down")

        resolved_batch_id = batch_id or str(uuid.uuid4())
        if not tasks:
            return []

        job_ids: list[str] = []
        executor_tasks: list[TaskSpec] = []

        for task in tasks:
            description = str(task.get("task_description", task.get("prompt", "")))
            agent_name = str(task.get("agent_name", "explore"))
            timeout = _coerce_int(task.get("timeout", 300), 300)
            priority = _coerce_int(task.get("priority", 1), 1)

            job_id = str(uuid.uuid4())
            job_ids.append(job_id)

            task_info: TaskInfo = {
                "agent_name": agent_name,
                "prompt": description,
                "timeout": timeout,
                "batch_id": resolved_batch_id,
                "priority": priority,
            }
            self._jobs[job_id] = {
                "status": "submitted",
                "task": task_info,
                "executor_job_id": None,
                "record": None,
            }
            executor_tasks.append(
                {
                    "agent_name": agent_name,
                    "prompt": description,
                    "timeout": timeout,
                }
            )

        executor_job_ids = self._executor.submit_many(executor_tasks)
        for local_job_id, executor_job_id in zip(job_ids, executor_job_ids):
            self._jobs[local_job_id]["executor_job_id"] = executor_job_id

        self._total_cost_units += len(tasks)
        return job_ids

    def _dispatch_queued(self) -> None:
        pending: list[tuple[str, TaskInfo]] = []
        while not self._queue.empty():
            _, _, job_id, task_info = self._queue.get()
            pending.append((job_id, task_info))

        if not pending:
            return

        executor_tasks: list[TaskSpec] = [
            {
                "agent_name": task_info["agent_name"],
                "prompt": task_info["prompt"],
                "timeout": task_info["timeout"],
            }
            for _, task_info in pending
        ]
        executor_job_ids = self._executor.submit_many(executor_tasks)

        for (local_job_id, _), executor_job_id in zip(pending, executor_job_ids):
            self._jobs[local_job_id]["status"] = "submitted"
            self._jobs[local_job_id]["executor_job_id"] = executor_job_id

    def _executor_job_ids_for(self, job_ids: Iterable[str]) -> list[str]:
        self._dispatch_queued()

        executor_job_ids: list[str] = []
        for job_id in job_ids:
            meta = self._jobs.get(job_id)
            if meta is None:
                raise KeyError(f"Unknown job_id: {job_id}")
            executor_job_id = meta.get("executor_job_id")
            if not isinstance(executor_job_id, str) or not executor_job_id:
                raise RuntimeError(f"Job has not been dispatched: {job_id}")
            executor_job_ids.append(executor_job_id)
        return executor_job_ids

    def wait_for_results(
        self,
        job_ids: list[str],
        timeout: int = 300,
        aggregation: str = "BEST_RESULT",
    ) -> ParallelResult:
        self._require_ultraworker()
        if not job_ids:
            return ParallelResult(
                results=[],
                aggregated=None,
                execution_summary={
                    "aggregation": str(aggregation).upper(),
                    "total": 0,
                    "succeeded": 0,
                    "failed": 0,
                    "quality_ranking": [],
                },
                partial=False,
            )

        executor_job_ids = self._executor_job_ids_for(job_ids)
        raw_records = self._executor.wait_all(executor_job_ids, timeout=timeout)
        records = cast(list[dict[str, object]], raw_records)

        results: list[IndividualResult] = []
        for local_job_id, record in zip(job_ids, records):
            meta = self._jobs[local_job_id]
            task_info = meta["task"]
            recipient = str(task_info.get("agent_name", "explore"))
            result = _extract_individual_result(recipient, record)
            results.append(result)

            meta["status"] = str(record.get("status", "completed"))
            meta["record"] = record

            if self._ralph_bridge.is_ralph_active():
                artifacts_obj = record.get("artifacts")
                artifacts = cast(list[dict[str, object]] | None, artifacts_obj if isinstance(artifacts_obj, list) else None)
                _ = self._ralph_bridge.signal_completion(
                    job_id=local_job_id,
                    status=meta["status"],
                    artifacts=artifacts,
                )

        self._completed_count += len(records)

        self._aggregator = ResultAggregator(strategy_for_mode(aggregation))
        return self._aggregator.aggregate(results)

    def get_stats(self) -> dict[str, int]:
        self._require_ultraworker()
        pool_stats = self._pool.pool_stats()
        return {
            "pool_size": int(pool_stats.get("pool_size", 0)),
            "queued": int(self._queue.qsize()),
            "active": int(pool_stats.get("active", 0)),
            "completed": int(self._completed_count),
            "total_cost_units": int(self._total_cost_units),
        }

    def shutdown(self) -> None:
        self._require_ultraworker()
        if self._shutdown:
            return
        self._shutdown = True
        self._pool.shutdown(wait=True)


__all__ = ["UltraworkerRouter"]
