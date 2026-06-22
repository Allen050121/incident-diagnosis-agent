"""Domain models for incident diagnosis"""

from dataclasses import dataclass, field
from datetime import datetime
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
class Evidence:
    evidence_id: str
    source: str  # logs, metrics, deployments, runbooks
    content: dict
    timestamp: datetime
    supports_hypothesis: bool = True


@dataclass
class Hypothesis:
    cause_code: str
    confidence: str  # HIGH, MEDIUM, LOW
    supporting_evidence: list[str] = field(default_factory=list)
    contradicting_evidence: list[str] = field(default_factory=list)
    reasoning_summary: str = ""


@dataclass
class DiagnosisReport:
    incident_id: str
    top_causes: list[Hypothesis] = field(default_factory=list)
    recommended_actions: list[str] = field(default_factory=list)
    missing_evidence: list[str] = field(default_factory=list)
    tool_failures: list[str] = field(default_factory=list)
