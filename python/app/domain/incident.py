"""Domain models for incident diagnosis"""

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Optional


class IncidentStatus(Enum):
    OPEN = "OPEN"
    QUEUED = "QUEUED"
    INVESTIGATING = "INVESTIGATING"
    DIAGNOSED = "DIAGNOSED"
    INCONCLUSIVE = "INCONCLUSIVE"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class AlertType(Enum):
    P95_LATENCY_HIGH = "P95_LATENCY_HIGH"
    ERROR_RATE_HIGH = "ERROR_RATE_HIGH"
    THROUGHPUT_LOW = "THROUGHPUT_LOW"
    MQ_LAG_HIGH = "MQ_LAG_HIGH"


class ConfidenceLevel(Enum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


@dataclass
class Incident:
    incident_id: str
    service: str
    endpoint: Optional[str]
    alert_type: AlertType
    value: float
    threshold: float
    started_at: datetime
    status: IncidentStatus = IncidentStatus.OPEN


@dataclass
class PlanStep:
    tool: str
    purpose: str
    parameters: dict = field(default_factory=dict)


@dataclass
class InvestigationPlan:
    steps: list[PlanStep] = field(default_factory=list)


@dataclass
class Evidence:
    evidence_id: str
    source: str  # logs, metrics, deployments, runbooks
    content: dict
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    supports_hypothesis: bool = True
    query_window: Optional[dict] = None
    truncated: bool = False


@dataclass
class EvidenceDetail:
    evidence_id: str
    source: str
    summary: str
    query_window: Optional[dict] = None
    truncated: bool = False
    content: dict = field(default_factory=dict)


@dataclass
class Hypothesis:
    cause_code: str
    confidence: ConfidenceLevel = ConfidenceLevel.LOW
    supporting_evidence: list[str] = field(default_factory=list)
    contradicting_evidence: list[str] = field(default_factory=list)
    reasoning_summary: str = ""
    rank: int = 0


@dataclass
class DiagnosisReport:
    incident_id: str
    status: str = "INCONCLUSIVE"  # DIAGNOSED, INCONCLUSIVE, FAILED
    top_causes: list[Hypothesis] = field(default_factory=list)
    recommended_actions: list[str] = field(default_factory=list)
    missing_evidence: list[str] = field(default_factory=list)
    tool_failures: list[str] = field(default_factory=list)
    evidence_ids: list[str] = field(default_factory=list)
    evidence_details: list[EvidenceDetail] = field(default_factory=list)
    investigation_steps: int = 0
    total_tool_calls: int = 0
