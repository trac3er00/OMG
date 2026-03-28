"""Sub-agent lifecycle management - spawn, track, cleanup."""
from __future__ import annotations

import json
import os
import subprocess
import threading
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Callable

_agents: dict[str, dict[str, Any]] = {}
_lock = threading.RLock()


class AgentState(Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    ORPHANED = "orphaned"


@dataclass
class AgentConfig:
    name: str
    category: str
    prompt: str
    skills: list[str] = field(default_factory=list)
    timeout: int = 300
    max_retries: int = 2
    subagent_type: str | None = None


def spawn_subagent(
    config: AgentConfig,
    project_dir: str = ".",
    on_complete: Callable[[dict], None] | None = None,
) -> str:
    agent_id = f"subagent-{uuid.uuid4().hex[:12]}"
    timestamp = datetime.now(timezone.utc).isoformat()

    with _lock:
        _agents[agent_id] = {
            "id": agent_id,
            "config": {
                "name": config.name,
                "category": config.category,
                "prompt": config.prompt,
                "skills": config.skills,
                "timeout": config.timeout,
                "max_retries": config.max_retries,
                "subagent_type": config.subagent_type,
            },
            "state": AgentState.PENDING.value,
            "project_dir": project_dir,
            "created_at": timestamp,
            "started_at": None,
            "completed_at": None,
            "result": None,
            "error": None,
            "pid": None,
            "on_complete": on_complete,
        }

    thread = threading.Thread(
        target=_run_agent,
        args=(agent_id, config, project_dir),
        daemon=True,
    )
    thread.start()

    return agent_id


def _run_agent(agent_id: str, config: AgentConfig, project_dir: str) -> None:
    with _lock:
        agent = _agents.get(agent_id)
        if not agent:
            return

    try:
        start_time = time.time()
        with _lock:
            _agents[agent_id]["state"] = AgentState.RUNNING.value
            _agents[agent_id]["started_at"] = datetime.now(timezone.utc).isoformat()
            _agents[agent_id]["pid"] = os.getpid()

        cmd = _build_agent_command(config, project_dir)
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=config.timeout,
            cwd=project_dir,
        )

        elapsed = time.time() - start_time
        with _lock:
            _agents[agent_id]["result"] = {
                "returncode": result.returncode,
                "stdout": result.stdout,
                "stderr": result.stderr,
                "elapsed_seconds": elapsed,
            }
            if result.returncode == 0:
                _agents[agent_id]["state"] = AgentState.COMPLETED.value
            else:
                _agents[agent_id]["state"] = AgentState.FAILED.value

    except subprocess.TimeoutExpired:
        with _lock:
            _agents[agent_id]["state"] = AgentState.FAILED.value
            _agents[agent_id]["error"] = f"Timeout after {config.timeout}s"
    except Exception as e:
        with _lock:
            _agents[agent_id]["state"] = AgentState.FAILED.value
            _agents[agent_id]["error"] = str(e)
    finally:
        with _lock:
            _agents[agent_id]["completed_at"] = datetime.now(timezone.utc).isoformat()

            callback = _agents[agent_id].get("on_complete")
            if callback:
                try:
                    callback(_agents[agent_id])
                except Exception:
                    pass


def _build_agent_command(config: AgentConfig, project_dir: str) -> list[str]:
    python_path = os.environ.get("OMG_PYTHON", "python3")
    scripts_dir = Path(__file__).parent.parent.parent / "scripts"
    omg_script = scripts_dir / "omg.py"

    cmd = [python_path, str(omg_script), "task"]

    if config.category:
        cmd.extend(["--category", config.category])

    if config.skills:
        cmd.extend(["--skills", ",".join(config.skills)])

    if config.subagent_type:
        cmd.extend(["--subagent-type", config.subagent_type])

    return cmd


def track_agent(agent_id: str) -> dict[str, Any] | None:
    with _lock:
        return _agents.get(agent_id, {}).copy()


def cleanup_agent(agent_id: str, force: bool = False) -> bool:
    with _lock:
        agent = _agents.get(agent_id)
        if not agent:
            return False

        state = agent.get("state")
        if state == AgentState.RUNNING.value and not force:
            return False

        if agent.get("pid"):
            try:
                kill_process_tree(agent["pid"])
            except Exception:
                pass

        del _agents[agent_id]
        return True


def get_agent_status(agent_id: str) -> str | None:
    with _lock:
        agent = _agents.get(agent_id)
        return agent.get("state") if agent else None


def list_active_agents() -> list[dict[str, Any]]:
    with _lock:
        return [
            {"id": aid, "state": a.get("state"), "name": a.get("config", {}).get("name")}
            for aid, a in _agents.items()
        ]


def cleanup_stale_agents(max_age_seconds: int = 3600) -> int:
    cleaned = 0
    now = datetime.now(timezone.utc).timestamp()

    with _lock:
        stale_ids = []
        for agent_id, agent in _agents.items():
            created = agent.get("created_at")
            if created:
                try:
                    ts = datetime.fromisoformat(created.replace("Z", "+00:00")).timestamp()
                    if now - ts > max_age_seconds:
                        stale_ids.append(agent_id)
                except Exception:
                    pass

        for agent_id in stale_ids:
            if cleanup_agent(agent_id, force=True):
                cleaned += 1

    return cleaned
