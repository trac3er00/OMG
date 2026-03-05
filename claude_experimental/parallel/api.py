from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from enum import Enum
from typing import cast

from claude_experimental.parallel.executor import ParallelExecutor


type AggregatedValue = str | list[str] | None
type SummaryValue = str | int | list[str]
type ExecutionSummary = dict[str, SummaryValue]


def _to_int(value: object, default: int) -> int:
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return default
    return default


class DistributionMode(str, Enum):
    BROADCAST = "BROADCAST"
    SHARD = "SHARD"
    ROUTED = "ROUTED"


class AggregationMode(str, Enum):
    BEST_RESULT = "BEST_RESULT"
    ALL_RESULTS = "ALL_RESULTS"
    FIRST_SUCCESS = "FIRST_SUCCESS"


@dataclass
class SendObject:
    recipient: str
    content: str
    priority: int = 0
    dependencies: list[str] = field(default_factory=list)
    timeout: int = 300


@dataclass
class IndividualResult:
    recipient: str
    content: str
    exit_code: int
    duration_ms: int


@dataclass
class ParallelResult:
    results: list[IndividualResult]
    aggregated: AggregatedValue
    execution_summary: ExecutionSummary
    partial: bool


def _coerce_distribution(value: DistributionMode | str) -> DistributionMode:
    if isinstance(value, DistributionMode):
        return value
    return DistributionMode(str(value).upper())


def _coerce_aggregation(value: AggregationMode | str) -> AggregationMode:
    if isinstance(value, AggregationMode):
        return value
    return AggregationMode(str(value).upper())


def _split_content(content: str, shard_count: int) -> list[str]:
    if shard_count <= 0:
        return []
    words = content.split()
    if not words:
        return ["" for _ in range(shard_count)]
    chunk_size = (len(words) + shard_count - 1) // shard_count
    shards: list[str] = []
    for idx in range(shard_count):
        start = idx * chunk_size
        end = start + chunk_size
        shards.append(" ".join(words[start:end]))
    return shards


def _build_send_objects(
    recipients: Sequence[str] | Sequence[SendObject],
    content: str | Sequence[str] | dict[str, str],
    distribution: DistributionMode,
) -> list[SendObject]:
    if all(isinstance(recipient, SendObject) for recipient in recipients):
        return [recipient for recipient in recipients if isinstance(recipient, SendObject)]

    recipient_list = [str(recipient) for recipient in recipients]

    if distribution is DistributionMode.BROADCAST:
        payload = content if isinstance(content, str) else str(content)
        return [SendObject(recipient=recipient, content=payload) for recipient in recipient_list]

    if distribution is DistributionMode.SHARD:
        if isinstance(content, str):
            shards = _split_content(content, len(recipient_list))
        elif isinstance(content, Sequence):
            shards = [str(chunk) for chunk in content]
        else:
            shards = [str(content)]

        return [
            SendObject(recipient=recipient, content=shards[idx] if idx < len(shards) else "")
            for idx, recipient in enumerate(recipient_list)
        ]

    routed_payload = content if isinstance(content, dict) else {}
    return [
        SendObject(recipient=recipient, content=str(routed_payload.get(recipient, "")))
        for recipient in recipient_list
    ]


def _extract_individual_result(recipient: str, record: dict[str, object]) -> IndividualResult:
    artifact: dict[str, object] | None = None
    artifacts_obj = record.get("artifacts")
    if isinstance(artifacts_obj, list) and artifacts_obj:
        artifacts_list = cast(list[object], artifacts_obj)
        candidate = artifacts_list[-1]
        if isinstance(candidate, dict):
            artifact = cast(dict[str, object], candidate)

    if artifact:
        return IndividualResult(
            recipient=recipient,
            content=str(artifact.get("content", "")),
            exit_code=_to_int(artifact.get("exit_code"), 1),
            duration_ms=_to_int(artifact.get("duration_ms"), 0),
        )

    status = record.get("status")
    fallback_code = 0 if status == "completed" else 1
    fallback_content = str(record.get("error") or "")
    return IndividualResult(
        recipient=recipient,
        content=fallback_content,
        exit_code=fallback_code,
        duration_ms=0,
    )


def _aggregate(results: list[IndividualResult], mode: AggregationMode) -> AggregatedValue:
    if mode is AggregationMode.ALL_RESULTS:
        return [result.content for result in results]

    successful = [result for result in results if result.exit_code == 0]
    if mode is AggregationMode.FIRST_SUCCESS:
        return successful[0].content if successful else None

    if successful:
        best = max(successful, key=lambda result: len(result.content))
        return best.content
    return results[0].content if results else None


def send_parallel(
    recipients: Sequence[str] | Sequence[SendObject],
    content: str | Sequence[str] | dict[str, str],
    distribution: DistributionMode | str,
    aggregation: AggregationMode | str,
) -> ParallelResult:
    import claude_experimental.parallel as parallel_module

    require_enabled = cast(Callable[[], None], getattr(parallel_module, "_require_enabled"))
    require_enabled()

    from claude_experimental._flags import get_feature_flag

    if not get_feature_flag("PARALLEL_DISPATCH", default=False):
        require_enabled()

    distribution_mode = _coerce_distribution(distribution)
    aggregation_mode = _coerce_aggregation(aggregation)
    send_objects = _build_send_objects(recipients, content, distribution_mode)

    if not send_objects:
        return ParallelResult(
            results=[],
            aggregated=[] if aggregation_mode is AggregationMode.ALL_RESULTS else None,
            execution_summary={
                "distribution": distribution_mode.value,
                "aggregation": aggregation_mode.value,
                "total": 0,
                "succeeded": 0,
                "failed": 0,
            },
            partial=False,
        )

    executor = ParallelExecutor()
    tasks = [
        {
            "agent_name": send_obj.recipient,
            "prompt": send_obj.content,
            "timeout": send_obj.timeout,
        }
        for send_obj in send_objects
    ]

    job_ids = executor.submit_many(tasks)
    wait_timeout = max(1, sum(send_obj.timeout for send_obj in send_objects))
    records = executor.wait_all(job_ids, timeout=wait_timeout)

    results = [
        _extract_individual_result(send_obj.recipient, record)
        for send_obj, record in zip(send_objects, records)
    ]
    succeeded = sum(1 for result in results if result.exit_code == 0)
    failed = len(results) - succeeded

    return ParallelResult(
        results=results,
        aggregated=_aggregate(results, aggregation_mode),
        execution_summary={
            "distribution": distribution_mode.value,
            "aggregation": aggregation_mode.value,
            "total": len(results),
            "succeeded": succeeded,
            "failed": failed,
            "job_ids": job_ids,
        },
        partial=failed > 0,
    )


__all__ = [
    "AggregationMode",
    "DistributionMode",
    "IndividualResult",
    "ParallelResult",
    "SendObject",
    "send_parallel",
]
