"""Agent trace observability - structured tracing for diagnosis pipeline.

Records every step of the diagnosis pipeline with timing, token usage,
and evidence references for debugging and replay.
"""

import uuid
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from typing import Optional


@dataclass
class TraceSpan:
    """A single span in the diagnosis trace."""
    span_id: str
    parent_span_id: Optional[str]
    trace_id: str
    incident_id: str
    operation: str  # graph_node, model_call, tool_call
    name: str
    started_at: str
    finished_at: str = ""
    duration_ms: float = 0.0
    status: str = "ok"  # ok, error
    attributes: dict = field(default_factory=dict)
    error: str = ""


@dataclass
class AgentTrace:
    """Full trace of a diagnosis run."""
    trace_id: str
    incident_id: str
    diagnosis_task_id: str
    started_at: str
    finished_at: str = ""
    total_duration_ms: float = 0.0
    spans: list[TraceSpan] = field(default_factory=list)
    total_tokens: int = 0
    total_cost_usd: float = 0.0
    final_status: str = ""

    def add_span(self, operation: str, name: str, attributes: dict | None = None,
                 status: str = "ok", error: str = "") -> TraceSpan:
        span = TraceSpan(
            span_id=uuid.uuid4().hex[:12],
            parent_span_id=self.spans[-1].span_id if self.spans else None,
            trace_id=self.trace_id,
            incident_id=self.incident_id,
            operation=operation,
            name=name,
            started_at=datetime.now(UTC).isoformat(),
            attributes=attributes or {},
            status=status,
            error=error,
        )
        self.spans.append(span)
        return span

    def finish_span(self, span: TraceSpan) -> None:
        span.finished_at = datetime.now(UTC).isoformat()
        started = datetime.fromisoformat(span.started_at)
        finished = datetime.fromisoformat(span.finished_at)
        span.duration_ms = (finished - started).total_seconds() * 1000

    def to_dict(self) -> dict:
        return {
            "trace_id": self.trace_id,
            "incident_id": self.incident_id,
            "diagnosis_task_id": self.diagnosis_task_id,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "total_duration_ms": self.total_duration_ms,
            "total_tokens": self.total_tokens,
            "total_cost_usd": round(self.total_cost_usd, 6),
            "final_status": self.final_status,
            "spans": [asdict(s) for s in self.spans],
        }


class TraceRecorder:
    """Records agent traces for observability and replay."""

    def __init__(self):
        self._traces: dict[str, AgentTrace] = {}

    def start_trace(self, incident_id: str, task_id: str = "") -> AgentTrace:
        trace = AgentTrace(
            trace_id=uuid.uuid4().hex[:16],
            incident_id=incident_id,
            diagnosis_task_id=task_id or uuid.uuid4().hex[:8],
            started_at=datetime.now(UTC).isoformat(),
        )
        self._traces[trace.trace_id] = trace
        return trace

    def finish_trace(self, trace: AgentTrace, status: str = "") -> None:
        trace.finished_at = datetime.now(UTC).isoformat()
        trace.final_status = status
        started = datetime.fromisoformat(trace.started_at)
        finished = datetime.fromisoformat(trace.finished_at)
        trace.total_duration_ms = (finished - started).total_seconds() * 1000

    def get_trace(self, trace_id: str) -> Optional[AgentTrace]:
        return self._traces.get(trace_id)

    def get_traces_for_incident(self, incident_id: str) -> list[AgentTrace]:
        return [t for t in self._traces.values() if t.incident_id == incident_id]

    def list_traces(self) -> list[dict]:
        return [
            {
                "trace_id": t.trace_id,
                "incident_id": t.incident_id,
                "status": t.final_status,
                "duration_ms": t.total_duration_ms,
                "spans": len(t.spans),
                "tokens": t.total_tokens,
            }
            for t in self._traces.values()
        ]


# Global recorder instance
recorder = TraceRecorder()
