"""File-backed log provider for query_logs."""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from app.infrastructure.log_desensitizer import desensitize_logs


_LEVELS = ("ERROR", "WARN", "INFO", "DEBUG", "TRACE")
_SERVICE_LOG_FILES = {
    "order-service": "order-service.log",
    "inventory-service": "inventory-service.log",
    "payment-mock-service": "payment-mock-service.log",
}
_SPRING_LOG_PATTERN = re.compile(
    r"^(?P<timestamp>\d{4}-\d{2}-\d{2}[T\s]\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:?\d{2})?)"
    r"\s+(?P<level>ERROR|WARN|INFO|DEBUG|TRACE)\s+.*?---\s+"
    r"\[(?P<thread>[^\]]+)\]\s+(?P<logger>\S+)\s*:\s*(?P<message>.*)$"
)


@dataclass(frozen=True)
class FileLogProvider:
    """Read bounded, structured log evidence from service log files."""

    base_dir: str
    tail_lines: int = 1000

    async def execute(self, parameters: dict) -> dict:
        service = parameters.get("service", "order-service")
        keywords = [str(item).lower() for item in parameters.get("keywords", [])]
        max_results = int(parameters.get("max_results", 20))
        min_level = parameters.get("min_level")
        start_time = _parse_query_time(parameters.get("start_time"))
        end_time = _parse_query_time(parameters.get("end_time"))

        path = self._path_for_service(service)
        if not path.exists():
            return {
                "logs": [],
                "total_count": 0,
                "error_stats": {},
                "truncated": False,
                "source": "file",
                "path": str(path),
                "warning": f"log file not found for service '{service}'",
            }

        entries = [
            entry for entry in self._read_entries(path, service)
            if self._matches(entry, keywords, min_level)
            and _within_time_window(entry, start_time, end_time)
        ]
        entries = entries[-max_results:]
        safe_entries = desensitize_logs(entries)

        return {
            "logs": safe_entries,
            "total_count": len(entries),
            "error_stats": dict(Counter(entry["level"] for entry in entries)),
            "truncated": len(entries) >= max_results,
            "source": "file",
            "path": str(path),
        }

    def _path_for_service(self, service: str) -> Path:
        filename = _SERVICE_LOG_FILES.get(service, f"{service}.log")
        return Path(self.base_dir).expanduser().resolve() / filename

    def _read_entries(self, path: Path, service: str) -> list[dict]:
        lines = self._tail(path)
        entries = []
        previous = None
        for line in lines:
            parsed = self._parse_line(line, service)
            if parsed:
                entries.append(parsed)
                previous = parsed
            elif previous and line.strip():
                previous["message"] = f"{previous['message']} | {line.strip()}"
        return entries

    def _tail(self, path: Path) -> list[str]:
        with path.open("r", encoding="utf-8", errors="replace") as handle:
            lines = handle.readlines()
        return [line.rstrip("\n") for line in lines[-self.tail_lines:]]

    def _parse_line(self, line: str, service: str) -> dict | None:
        match = _SPRING_LOG_PATTERN.match(line)
        if match:
            data = match.groupdict()
            return {
                "timestamp": data["timestamp"].replace(" ", "T"),
                "level": data["level"],
                "message": data["message"],
                "thread": data["thread"].strip(),
                "logger": data["logger"],
                "trace_id": "",
                "service": service,
            }

        level = next((item for item in _LEVELS if item in line), None)
        if level is None:
            return None
        return {
            "timestamp": "",
            "level": level,
            "message": line.strip(),
            "thread": "",
            "logger": "",
            "trace_id": "",
            "service": service,
        }

    @staticmethod
    def _matches(entry: dict, keywords: list[str], min_level: str | None) -> bool:
        if min_level and _level_rank(entry["level"]) > _level_rank(min_level):
            return False
        if not keywords:
            return True
        message = entry.get("message", "").lower()
        return any(keyword in message for keyword in keywords)


def _level_rank(level: str) -> int:
    order = {"ERROR": 0, "WARN": 1, "INFO": 2, "DEBUG": 3, "TRACE": 4}
    return order.get(level.upper(), 5)


def _parse_query_time(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed
    return parsed.astimezone().replace(tzinfo=None)


def _parse_log_time(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).replace(tzinfo=None)
    except ValueError:
        return None


def _within_time_window(entry: dict, start_time: datetime | None, end_time: datetime | None) -> bool:
    timestamp = _parse_log_time(entry.get("timestamp"))
    if timestamp is None:
        return True
    if start_time and timestamp < start_time:
        return False
    if end_time and timestamp > end_time:
        return False
    return True
