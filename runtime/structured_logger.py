"""Structured logging with JSON output and severity levels."""
from __future__ import annotations

import json
import logging
import os
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


class LogLevel(Enum):
    DEBUG = "debug"
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


@dataclass
class LogEntry:
    timestamp: str
    level: str
    message: str
    context: dict[str, Any] = field(default_factory=dict)
    logger: str = "omg"
    trace_id: str | None = None


class OMGLogger:
    def __init__(self, name: str = "omg", level: LogLevel = LogLevel.INFO):
        self.name = name
        self.level = level
        self.handlers: list[logging.Handler] = []
        self._setup_handlers()

    def _setup_handlers(self) -> None:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(JsonFormatter())
        self.add_handler(console_handler)

    def add_handler(self, handler: logging.Handler) -> None:
        self.handlers.append(handler)
        handler.setLevel(getattr(logging, self.level.value.upper()))

    def _log(self, level: LogLevel, message: str, **context: Any) -> None:
        entry = LogEntry(
            timestamp=datetime.now(timezone.utc).isoformat(),
            level=level.value,
            message=message,
            context=context,
            logger=self.name,
            trace_id=os.environ.get("OMG_TRACE_ID"),
        )

        for handler in self.handlers:
            if hasattr(handler, 'emit'):
                handler.emit(entry)

    def debug(self, message: str, **context: Any) -> None:
        self._log(LogLevel.DEBUG, message, **context)

    def info(self, message: str, **context: Any) -> None:
        self._log(LogLevel.INFO, message, **context)

    def warning(self, message: str, **context: Any) -> None:
        self._log(LogLevel.WARNING, message, **context)

    def error(self, message: str, **context: Any) -> None:
        self._log(LogLevel.ERROR, message, **context)

    def critical(self, message: str, **context: Any) -> None:
        self._log(LogLevel.CRITICAL, message, **context)


class JsonFormatter(logging.Formatter):
    def emit(self, record: logging.LogRecord) -> None:
        if isinstance(record.msg, LogEntry):
            entry = record.msg
            log_obj = {
                "timestamp": entry.timestamp,
                "level": entry.level,
                "logger": entry.logger,
                "message": entry.message,
                "context": entry.context,
            }
            if entry.trace_id:
                log_obj["trace_id"] = entry.trace_id
        else:
            log_obj = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "level": record.levelname.lower(),
                "logger": record.name,
                "message": record.getMessage(),
            }

        print(json.dumps(log_obj), file=record.stream)


def get_logger(name: str = "omg", level: LogLevel = LogLevel.INFO) -> OMGLogger:
    return OMGLogger(name, level)
