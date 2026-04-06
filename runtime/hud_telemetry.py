from __future__ import annotations
import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class HUDMetrics:
    session_id: str = ""
    tokens_used: int = 0
    cost_usd: float = 0.0
    api_calls: int = 0
    wall_time_secs: float = 0.0
    mode: str = "instant"
    model_id: str = ""
    failures: int = 0
    tool_calls: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "tokens_used": self.tokens_used,
            "cost_usd": round(self.cost_usd, 6),
            "api_calls": self.api_calls,
            "wall_time_secs": round(self.wall_time_secs, 1),
            "mode": self.mode,
            "model_id": self.model_id,
            "failures": self.failures,
            "tool_calls": self.tool_calls,
        }


class HUDTelemetry:
    def __init__(self, project_dir: str = ".", session_id: str = "") -> None:
        self.project_dir = project_dir
        self._metrics = HUDMetrics(session_id=session_id or f"ses_{int(time.time())}")
        self._start_time = time.time()
        self._telemetry_path = (
            Path(project_dir) / ".omg" / "state" / "hud-telemetry.jsonl"
        )
        self._telemetry_path.parent.mkdir(parents=True, exist_ok=True)

    def record_api_call(
        self,
        tokens_in: int = 0,
        tokens_out: int = 0,
        cost_usd: float | None = None,
        model_id: str = "",
    ) -> None:
        self._metrics.tokens_used += tokens_in + tokens_out
        self._metrics.cost_usd += cost_usd or (tokens_in + tokens_out) * 0.000003
        self._metrics.api_calls += 1
        if model_id:
            self._metrics.model_id = model_id
        self._metrics.wall_time_secs = time.time() - self._start_time

    def record_tool_call(self, tool: str = "", success: bool = True) -> None:
        self._metrics.tool_calls += 1
        if not success:
            self._metrics.failures += 1

    def update_mode(self, mode: str) -> None:
        self._metrics.mode = mode

    def snapshot(self) -> HUDMetrics:
        self._metrics.wall_time_secs = time.time() - self._start_time
        snap = HUDMetrics(**self._metrics.__dict__)
        try:
            with open(self._telemetry_path, "a", encoding="utf-8") as f:
                f.write(
                    json.dumps(
                        {
                            "timestamp": time.strftime(
                                "%Y-%m-%dT%H:%M:%SZ", time.gmtime()
                            ),
                            **snap.to_dict(),
                        }
                    )
                    + "\n"
                )
        except Exception:
            pass
        return snap

    def get_current(self) -> dict[str, Any]:
        self._metrics.wall_time_secs = time.time() - self._start_time
        return self._metrics.to_dict()
