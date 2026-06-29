"""Tool definitions for the diagnosis agent"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


# Whitelisted metrics
ALLOWED_METRICS = [
    "request_rate",
    "error_rate",
    "latency_p50",
    "latency_p95",
    "jvm_threads_active",
    "db_pool_active_ratio",
    "redis_latency_p95",
    "downstream_latency_p95",
    "mq_lag",
]

# Allowed tools
ALLOWED_TOOLS = ["query_logs", "query_metrics", "query_deployments", "search_runbooks"]


@dataclass
class ToolInput:
    tool: str
    parameters: dict
    evidence_id_prefix: str = ""
    timeout_seconds: int = 10


@dataclass
class ToolResult:
    tool: str
    evidence_id: str
    data: dict
    success: bool = True
    error: Optional[str] = None
    truncated: bool = False
    query_window: Optional[dict] = None
    timestamp: datetime = field(default_factory=datetime.utcnow)


def validate_tool_input(tool_input: ToolInput) -> Optional[str]:
    """Validate tool input against whitelist. Returns error message or None if valid."""
    if tool_input.tool not in ALLOWED_TOOLS:
        return f"Tool '{tool_input.tool}' not in allowed list: {ALLOWED_TOOLS}"

    if tool_input.tool == "query_metrics":
        metric = tool_input.parameters.get("metric", "")
        if metric not in ALLOWED_METRICS:
            return f"Metric '{metric}' not in whitelist: {ALLOWED_METRICS}"

    return None
