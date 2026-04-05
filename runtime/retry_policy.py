"""Retry policy with exponential backoff and circuit breaker."""
from __future__ import annotations

import random
import time
from dataclasses import dataclass, field
from enum import Enum
from functools import wraps
from typing import Any, Callable, TypeVar

T = TypeVar('T')


class RetryStrategy(Enum):
    FIXED = "fixed"
    LINEAR = "linear"
    EXPONENTIAL = "exponential"
    EXPONENTIAL_WITH_JITTER = "exponential_with_jitter"


@dataclass
class RetryConfig:
    max_attempts: int = 3
    initial_delay: float = 1.0
    max_delay: float = 60.0
    strategy: RetryStrategy = RetryStrategy.EXPONENTIAL_WITH_JITTER
    timeout: float = 120.0


@dataclass
class CircuitState:
    failures: int = 0
    last_failure_time: float = 0
    state: str = "closed"
    last_success_time: float = 0


_circuit_breakers: dict[str, CircuitState] = {}


def calculate_delay(attempt: int, config: RetryConfig) -> float:
    if config.strategy == RetryStrategy.FIXED:
        delay = config.initial_delay
    elif config.strategy == RetryStrategy.LINEAR:
        delay = config.initial_delay * attempt
    elif config.strategy == RetryStrategy.EXPONENTIAL:
        delay = config.initial_delay * (2 ** (attempt - 1))
    elif config.strategy == RetryStrategy.EXPONENTIAL_WITH_JITTER:
        base = config.initial_delay * (2 ** (attempt - 1))
        jitter = base * random.uniform(0, 0.3)
        delay = base + jitter
    else:
        delay = config.initial_delay

    return min(delay, config.max_delay)


def with_retry(config: RetryConfig | None = None):
    if config is None:
        config = RetryConfig()

    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> T:
            last_exception = None

            for attempt in range(1, config.max_attempts + 1):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    last_exception = e

                    if attempt == config.max_attempts:
                        break

                    delay = calculate_delay(attempt, config)
                    time.sleep(delay)

            if last_exception:
                raise last_exception

            raise RuntimeError("Retry logic error")

        return wrapper
    return decorator


def circuit_breaker(
    name: str,
    failure_threshold: int = 5,
    recovery_timeout: float = 60.0,
    half_open_attempts: int = 1,
):
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> T:
            if name not in _circuit_breakers:
                _circuit_breakers[name] = CircuitState()

            cb = _circuit_breakers[name]

            if cb.state == "open":
                if time.time() - cb.last_failure_time > recovery_timeout:
                    cb.state = "half_open"
                else:
                    raise CircuitOpenError(f"Circuit '{name}' is open")

            if cb.state == "half_open" and half_open_attempts > 1:
                pass

            try:
                result = func(*args, **kwargs)
                cb.failures = 0
                cb.last_success_time = time.time()
                if cb.state == "half_open":
                    cb.state = "closed"
                return result
            except Exception as e:
                cb.failures += 1
                cb.last_failure_time = time.time()

                if cb.failures >= failure_threshold:
                    cb.state = "open"

                raise

        return wrapper
    return decorator


def get_circuit_state(name: str) -> str | None:
    return _circuit_breakers.get(name, {}).state


def reset_circuit(name: str) -> None:
    if name in _circuit_breakers:
        _circuit_breakers[name] = CircuitState()


class CircuitOpenError(Exception):
    pass
