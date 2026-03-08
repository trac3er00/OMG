from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from collections.abc import Mapping
from typing import Callable, Protocol, TypedDict

from runtime.runtime_profile import resolve_parallel_workers


def _resolve_parallel_workers(project_dir: str, requested_workers: int) -> int:
    return resolve_parallel_workers(project_dir, requested_workers=requested_workers)


class WorkerTask(TypedDict, total=False):
    agent_name: str
    prompt: str
    order: int


class ResultFuture(Protocol):
    def result(self, timeout: int | None = None) -> dict[str, object]:
        ...


def _default_as_completed(
    futures: dict[ResultFuture, tuple[int, int, WorkerTask]],
) -> list[ResultFuture]:
    return list(futures.keys())


def _status_from_result(result: Mapping[str, object]) -> str:
    if result.get("fallback") == "claude":
        return "fallback-claude"
    if "error" in result:
        return "error"
    return "completed" if result.get("exit_code") == 0 else "failed"


def _execute_workers_sequential(
    workers: list[WorkerTask],
    *,
    project_dir: str,
    dispatch_fn: Callable[[str, str, str], dict[str, object]],
) -> list[dict[str, object]]:
    sorted_workers = sorted(workers, key=lambda x: x.get("order", 0))
    results: list[dict[str, object]] = []
    for worker in sorted_workers:
        agent_name = str(worker.get("agent_name", "executor"))
        prompt = str(worker.get("prompt", ""))
        result = dispatch_fn(agent_name, prompt, project_dir)
        results.append(
            {
                "agent": agent_name,
                "order": worker.get("order", 0),
                "status": _status_from_result(result),
                **result,
            }
        )
    return results


def _execute_workers_parallel(
    workers: list[WorkerTask],
    *,
    project_dir: str,
    dispatch_fn: Callable[[str, str, str], dict[str, object]],
    timeout_per_worker: int,
    resolve_workers_fn: Callable[[str, int], int],
    thread_pool_cls: type[ThreadPoolExecutor],
    as_completed_fn: Callable[..., list[ResultFuture]],
) -> list[dict[str, object]]:
    indexed_workers: list[tuple[int, int, WorkerTask]] = [
        (idx, int(worker.get("order", 0)), worker) for idx, worker in enumerate(workers)
    ]
    sorted_workers = sorted(indexed_workers, key=lambda x: (x[1], x[0]))
    if not sorted_workers:
        return []

    max_workers = resolve_workers_fn(project_dir, min(len(sorted_workers), 5))
    results_by_index: dict[int, dict[str, object]] = {}

    with thread_pool_cls(max_workers=max_workers) as pool:
        future_map: dict[ResultFuture, tuple[int, int, WorkerTask]] = {
            pool.submit(
                dispatch_fn,
                str(worker_info[2].get("agent_name", "executor")),
                str(worker_info[2].get("prompt", "")),
                project_dir,
            ): worker_info
            for worker_info in sorted_workers
        }

        for future in as_completed_fn(future_map):
            worker_info = future_map[future]
            worker = worker_info[2]
            order = worker_info[1]
            worker_index = worker_info[0]
            agent_name = str(worker.get("agent_name", "executor"))

            try:
                result = future.result(timeout=timeout_per_worker)
            except Exception as exc:
                result = {"error": str(exc), "fallback": "claude"}

            results_by_index[worker_index] = {
                "agent": agent_name,
                "order": order,
                "status": _status_from_result(result),
                **result,
            }

    return [results_by_index[worker_info[0]] for worker_info in sorted_workers]


def execute_workers(
    workers: list[WorkerTask],
    parallel: bool,
    *,
    project_dir: str = ".",
    dispatch_fn: Callable[[str, str, str], dict[str, object]] | None = None,
    timeout_per_worker: int = 120,
    resolve_workers_fn: Callable[[str, int], int] = _resolve_parallel_workers,
    thread_pool_cls: type[ThreadPoolExecutor] = ThreadPoolExecutor,
    as_completed_fn: Callable[..., list[ResultFuture]] = _default_as_completed,
) -> list[dict[str, object]]:
    if dispatch_fn is None:
        raise ValueError("dispatch_fn is required")
    if parallel:
        return _execute_workers_parallel(
            workers,
            project_dir=project_dir,
            dispatch_fn=dispatch_fn,
            timeout_per_worker=timeout_per_worker,
            resolve_workers_fn=resolve_workers_fn,
            thread_pool_cls=thread_pool_cls,
            as_completed_fn=as_completed_fn,
        )
    return _execute_workers_sequential(
        workers,
        project_dir=project_dir,
        dispatch_fn=dispatch_fn,
    )
