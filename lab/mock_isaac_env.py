from __future__ import annotations

import random
from typing import Any


class MockIsaacEnv:
    metadata = {"render_modes": ["human", "ansi"], "name": "MockIsaacEnv-v1"}

    def __init__(self, *, max_steps: int = 32, reward_scale: float = 1.0) -> None:
        self.max_steps = max(1, int(max_steps))
        self.reward_scale = float(reward_scale)
        self._rng = random.Random(0)
        self._seed = 0
        self._step_count = 0
        self._state = 0.0
        self._closed = False

    def reset(self, *, seed: int | None = None, options: dict[str, Any] | None = None) -> tuple[list[float], dict[str, Any]]:
        del options
        if seed is not None:
            self._seed = int(seed)
        self._rng = random.Random(self._seed)
        self._step_count = 0
        self._state = round(self._rng.uniform(-0.25, 0.25), 6)
        return [self._state], {"seed": self._seed, "step": self._step_count}

    def step(self, action: Any) -> tuple[list[float], float, bool, bool, dict[str, Any]]:
        if self._closed:
            raise RuntimeError("environment is closed")
        action_value = float(action) if isinstance(action, (int, float)) else 0.0
        drift = self._rng.uniform(-0.1, 0.1)
        self._state = round(self._state + drift + (0.01 * action_value), 6)
        reward = round((1.0 - abs(self._state)) * self.reward_scale, 6)
        self._step_count += 1
        terminated = self._step_count >= self.max_steps
        truncated = False
        info = {"seed": self._seed, "step": self._step_count}
        return [self._state], reward, terminated, truncated, info

    def render(self, mode: str = "human") -> str | None:
        if mode == "ansi":
            return f"MockIsaacEnv(step={self._step_count}, state={self._state:.4f})"
        return None

    def close(self) -> None:
        self._closed = True
