"""Log processor - aggregation, deduplication, and trimming

Processing pipeline:
  限定服务与时间窗口
    -> 按 Trace ID/异常级别筛选
    -> 模板化去重
    -> 聚合错误计数
    -> 保留代表性样本
    -> 限制最大字符数
"""

import re
from dataclasses import dataclass, field
from typing import Optional


# Patterns to normalize for deduplication
_NORMALIZE_PATTERNS = [
    (re.compile(r'\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b', re.I), '<UUID>'),
    (re.compile(r'\b\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}[.\d]*[Z]?\b'), '<TIMESTAMP>'),
    (re.compile(r'\b\d+\.\d+\.\d+\.\d+\b'), '<IP>'),
    (re.compile(r'\btrace-[a-z0-9-]+\b', re.I), '<TRACE_ID>'),
    (re.compile(r'\b\d+ms\b'), '<DURATION>'),
    (re.compile(r'\b\d{4,}\b'), '<NUM>'),
    (re.compile(r'\b0x[0-9a-fA-F]+\b'), '<HEX>'),
]


@dataclass
class LogEntry:
    timestamp: str
    level: str
    message: str
    service: str = ""
    trace_id: str = ""
    raw: str = ""


@dataclass
class ProcessedLogs:
    """Result of log processing"""
    entries: list[LogEntry] = field(default_factory=list)
    error_stats: dict[str, int] = field(default_factory=dict)
    total_count: int = 0
    dedup_count: int = 0
    truncated: bool = False
    max_chars: int = 0
    current_chars: int = 0


def normalize_message(message: str) -> str:
    """Normalize a log message for template-based deduplication.

    Replaces variable parts (UUIDs, timestamps, IPs, numbers) with placeholders
    so that similar messages are recognized as duplicates.
    """
    normalized = message
    for pattern, replacement in _NORMALIZE_PATTERNS:
        normalized = pattern.sub(replacement, normalized)
    return normalized


def _template_key(entry: LogEntry) -> str:
    """Generate a template key for deduplication"""
    normalized = normalize_message(entry.message)
    return f"{entry.level}:{normalized}"


def deduplicate_logs(entries: list[LogEntry]) -> list[LogEntry]:
    """Remove duplicate logs based on template similarity.

    Keeps the first occurrence of each unique template.
    """
    seen: dict[str, LogEntry] = {}
    for entry in entries:
        key = _template_key(entry)
        if key not in seen:
            seen[key] = entry
    return list(seen.values())


def aggregate_errors(entries: list[LogEntry]) -> dict[str, int]:
    """Count log entries by level"""
    stats: dict[str, int] = {}
    for entry in entries:
        level = entry.level.upper()
        stats[level] = stats.get(level, 0) + 1
    return stats


def filter_by_level(entries: list[LogEntry], min_level: str = "WARN") -> list[LogEntry]:
    """Filter logs by minimum severity level"""
    level_order = {"DEBUG": 0, "INFO": 1, "WARN": 2, "ERROR": 3, "FATAL": 4}
    min_val = level_order.get(min_level.upper(), 0)
    return [e for e in entries if level_order.get(e.level.upper(), 0) >= min_val]


def filter_by_trace_id(entries: list[LogEntry], trace_id: str) -> list[LogEntry]:
    """Filter logs by trace ID"""
    return [e for e in entries if e.trace_id == trace_id or trace_id in e.message]


def trim_logs(
    entries: list[LogEntry],
    max_entries: int = 20,
    max_chars: int = 5000,
) -> tuple[list[LogEntry], bool]:
    """Trim logs to fit within budget constraints.

    Returns (trimmed_entries, was_truncated).
    """
    if len(entries) <= max_entries:
        # Still check char limit
        total_chars = sum(len(e.message) for e in entries)
        if total_chars <= max_chars:
            return entries, False

    # Prioritize ERROR > WARN > INFO
    priority_order = {"ERROR": 0, "FATAL": 0, "WARN": 1, "INFO": 2, "DEBUG": 3}
    sorted_entries = sorted(entries, key=lambda e: priority_order.get(e.level.upper(), 3))

    result = []
    current_chars = 0
    for entry in sorted_entries[:max_entries]:
        if current_chars + len(entry.message) > max_chars:
            break
        result.append(entry)
        current_chars += len(entry.message)

    truncated = len(result) < len(entries) or current_chars < sum(len(e.message) for e in entries)
    return result, truncated


def process_logs(
    raw_entries: list[dict],
    min_level: str = "WARN",
    trace_id: Optional[str] = None,
    max_entries: int = 20,
    max_chars: int = 5000,
) -> ProcessedLogs:
    """Full log processing pipeline.

    1. Parse raw entries
    2. Filter by level
    3. Filter by trace ID (if provided)
    4. Deduplicate by template
    5. Aggregate error counts
    6. Trim to budget
    """
    # 1. Parse
    entries = [
        LogEntry(
            timestamp=e.get("timestamp", ""),
            level=e.get("level", "INFO"),
            message=e.get("message", ""),
            service=e.get("service", ""),
            trace_id=e.get("trace_id", ""),
            raw=str(e),
        )
        for e in raw_entries
    ]
    total_count = len(entries)

    # 2. Filter by level
    if min_level:
        entries = filter_by_level(entries, min_level)

    # 3. Filter by trace ID
    if trace_id:
        entries = filter_by_trace_id(entries, trace_id)

    # 4. Deduplicate
    deduped = deduplicate_logs(entries)
    dedup_count = total_count - len(deduped)

    # 5. Aggregate
    error_stats = aggregate_errors(entries)

    # 6. Trim
    trimmed, truncated = trim_logs(deduped, max_entries=max_entries, max_chars=max_chars)

    current_chars = sum(len(e.message) for e in trimmed)

    return ProcessedLogs(
        entries=trimmed,
        error_stats=error_stats,
        total_count=total_count,
        dedup_count=dedup_count,
        truncated=truncated,
        max_chars=max_chars,
        current_chars=current_chars,
    )
