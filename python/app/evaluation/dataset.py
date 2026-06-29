"""Evaluation dataset generator

Generates 48 evaluation cases from 12 fault templates × 4 parameter variants.
Each case has a known root_cause for scoring.
"""

from dataclasses import dataclass, field
from typing import Optional

from app.domain.incident import AlertType


@dataclass
class EvalCase:
    """A single evaluation case with known ground truth."""
    case_id: str
    fault_id: str
    category: str
    root_cause: str
    affected_service: str
    alert_type: AlertType
    value: float
    threshold: float
    noise_ratio: float = 0.0
    has_unrelated_deploy: bool = False
    tool_unavailable: Optional[str] = None
    has_wrong_runbook: bool = False
    expected_cause_code: str = ""
    symptoms: list[str] = field(default_factory=list)
    contributing_factors: list[str] = field(default_factory=list)
    forbidden_conclusions: list[str] = field(default_factory=list)


# 12 fault templates with their ground truth
_FAULT_TEMPLATES = [
    {
        "fault_id": "mysql-slow-query",
        "category": "DATABASE",
        "root_cause": "MISSING_INDEX",
        "service": "order-service",
        "alert_type": AlertType.P95_LATENCY_HIGH,
        "expected_cause_code": "DATABASE_SLOW_QUERY",
        "symptoms": ["high latency", "slow query logs"],
        "forbidden": ["REDIS_TIMEOUT"],
        "variants": [
            {"value": 5000, "threshold": 1000, "noise_ratio": 0.0},
            {"value": 3000, "threshold": 1000, "noise_ratio": 0.2},
            {"value": 8000, "threshold": 1000, "has_unrelated_deploy": True},
            {"value": 4000, "threshold": 1000, "tool_unavailable": "search_runbooks"},
        ],
    },
    {
        "fault_id": "mysql-connection-pool",
        "category": "DATABASE",
        "root_cause": "CONNECTION_POOL_EXHAUSTED",
        "service": "order-service",
        "alert_type": AlertType.ERROR_RATE_HIGH,
        "expected_cause_code": "DATABASE_CONNECTION_POOL_EXHAUSTED",
        "symptoms": ["connection timeout", "pool exhausted"],
        "forbidden": ["REDIS_TIMEOUT"],
        "variants": [
            {"value": 0.95, "threshold": 0.8, "noise_ratio": 0.0},
            {"value": 0.98, "threshold": 0.8, "noise_ratio": 0.1},
            {"value": 1.0, "threshold": 0.8, "has_unrelated_deploy": True},
            {"value": 0.92, "threshold": 0.8, "has_wrong_runbook": True},
        ],
    },
    {
        "fault_id": "redis-timeout",
        "category": "CACHE",
        "root_cause": "REDIS_TIMEOUT",
        "service": "inventory-service",
        "alert_type": AlertType.P95_LATENCY_HIGH,
        "expected_cause_code": "REDIS_TIMEOUT",
        "symptoms": ["redis timeout", "cache miss"],
        "forbidden": ["DATABASE_SLOW_QUERY"],
        "variants": [
            {"value": 3000, "threshold": 500, "noise_ratio": 0.0},
            {"value": 5000, "threshold": 500, "noise_ratio": 0.3},
            {"value": 2000, "threshold": 500, "tool_unavailable": "query_deployments"},
            {"value": 4000, "threshold": 500, "has_unrelated_deploy": True},
        ],
    },
    {
        "fault_id": "redis-hot-key",
        "category": "CACHE",
        "root_cause": "REDIS_HOT_KEY",
        "service": "inventory-service",
        "alert_type": AlertType.P95_LATENCY_HIGH,
        "expected_cause_code": "REDIS_TIMEOUT",
        "symptoms": ["redis slow", "single key latency"],
        "forbidden": ["DATABASE_SLOW_QUERY"],
        "variants": [
            {"value": 800, "threshold": 200, "noise_ratio": 0.0},
            {"value": 1200, "threshold": 200, "noise_ratio": 0.2},
            {"value": 600, "threshold": 200, "has_wrong_runbook": True},
            {"value": 1000, "threshold": 200, "tool_unavailable": "search_runbooks"},
        ],
    },
    {
        "fault_id": "downstream-payment-timeout",
        "category": "DOWNSTREAM",
        "root_cause": "DOWNSTREAM_TIMEOUT",
        "service": "payment-mock-service",
        "alert_type": AlertType.P95_LATENCY_HIGH,
        "expected_cause_code": "DOWNSTREAM_SERVICE_FAILURE",
        "symptoms": ["payment timeout", "503"],
        "forbidden": ["DATABASE_SLOW_QUERY"],
        "variants": [
            {"value": 5000, "threshold": 1000, "noise_ratio": 0.0},
            {"value": 8000, "threshold": 1000, "noise_ratio": 0.2},
            {"value": 3000, "threshold": 1000, "has_unrelated_deploy": True},
            {"value": 6000, "threshold": 1000, "tool_unavailable": "query_logs"},
        ],
    },
    {
        "fault_id": "downstream-payment-5xx",
        "category": "DOWNSTREAM",
        "root_cause": "DOWNSTREAM_ERROR",
        "service": "payment-mock-service",
        "alert_type": AlertType.ERROR_RATE_HIGH,
        "expected_cause_code": "DOWNSTREAM_SERVICE_FAILURE",
        "symptoms": ["503 errors", "payment failure"],
        "forbidden": ["DATABASE_SLOW_QUERY"],
        "variants": [
            {"value": 0.25, "threshold": 0.05, "noise_ratio": 0.0},
            {"value": 0.40, "threshold": 0.05, "noise_ratio": 0.1},
            {"value": 0.15, "threshold": 0.05, "has_unrelated_deploy": True},
            {"value": 0.30, "threshold": 0.05, "has_wrong_runbook": True},
        ],
    },
    {
        "fault_id": "http-connection-pool",
        "category": "RESOURCE",
        "root_cause": "HTTP_CONNECTION_POOL_EXHAUSTED",
        "service": "order-service",
        "alert_type": AlertType.THROUGHPUT_LOW,
        "expected_cause_code": "RESOURCE_EXHAUSTION",
        "symptoms": ["connection refused", "pool full"],
        "forbidden": ["REDIS_TIMEOUT"],
        "variants": [
            {"value": 0.95, "threshold": 0.8, "noise_ratio": 0.0},
            {"value": 0.98, "threshold": 0.8, "noise_ratio": 0.2},
            {"value": 1.0, "threshold": 0.8, "tool_unavailable": "query_metrics"},
            {"value": 0.90, "threshold": 0.8, "has_unrelated_deploy": True},
        ],
    },
    {
        "fault_id": "thread-pool-full",
        "category": "RESOURCE",
        "root_cause": "THREAD_POOL_EXHAUSTED",
        "service": "inventory-service",
        "alert_type": AlertType.THROUGHPUT_LOW,
        "expected_cause_code": "RESOURCE_EXHAUSTION",
        "symptoms": ["thread pool full", "request queued"],
        "forbidden": ["DATABASE_SLOW_QUERY"],
        "variants": [
            {"value": 0.98, "threshold": 0.8, "noise_ratio": 0.0},
            {"value": 1.0, "threshold": 0.8, "noise_ratio": 0.1},
            {"value": 0.95, "threshold": 0.8, "has_wrong_runbook": True},
            {"value": 0.92, "threshold": 0.8, "tool_unavailable": "search_runbooks"},
        ],
    },
    {
        "fault_id": "config-error",
        "category": "CONFIG",
        "root_cause": "CONFIG_ERROR",
        "service": "order-service",
        "alert_type": AlertType.ERROR_RATE_HIGH,
        "expected_cause_code": "APPLICATION_ERROR_SPIKE",
        "symptoms": ["NullPointerException", "config missing"],
        "forbidden": ["REDIS_TIMEOUT"],
        "variants": [
            {"value": 0.30, "threshold": 0.05, "noise_ratio": 0.0},
            {"value": 0.50, "threshold": 0.05, "noise_ratio": 0.2},
            {"value": 0.20, "threshold": 0.05, "has_unrelated_deploy": True},
            {"value": 0.40, "threshold": 0.05, "tool_unavailable": "query_deployments"},
        ],
    },
    {
        "fault_id": "deployment-npe",
        "category": "DEPLOYMENT",
        "root_cause": "NULL_POINTER_EXCEPTION",
        "service": "order-service",
        "alert_type": AlertType.ERROR_RATE_HIGH,
        "expected_cause_code": "RECENT_DEPLOYMENT_REGRESSION",
        "symptoms": ["NPE after deploy", "new version error"],
        "forbidden": ["DATABASE_SLOW_QUERY"],
        "variants": [
            {"value": 0.35, "threshold": 0.05, "noise_ratio": 0.0},
            {"value": 0.60, "threshold": 0.05, "noise_ratio": 0.1},
            {"value": 0.25, "threshold": 0.05, "has_wrong_runbook": True},
            {"value": 0.45, "threshold": 0.05, "tool_unavailable": "query_logs"},
        ],
    },
    {
        "fault_id": "rate-limit-triggered",
        "category": "RESILIENCE",
        "root_cause": "CIRCUIT_BREAKER_TRIGGERED",
        "service": "order-service",
        "alert_type": AlertType.THROUGHPUT_LOW,
        "expected_cause_code": "RESOURCE_EXHAUSTION",
        "symptoms": ["circuit breaker open", "rate limited"],
        "forbidden": ["REDIS_TIMEOUT"],
        "variants": [
            {"value": 0.80, "threshold": 0.5, "noise_ratio": 0.0},
            {"value": 0.95, "threshold": 0.5, "noise_ratio": 0.2},
            {"value": 0.70, "threshold": 0.5, "has_unrelated_deploy": True},
            {"value": 0.85, "threshold": 0.5, "tool_unavailable": "query_metrics"},
        ],
    },
    {
        "fault_id": "mq-consumer-lag",
        "category": "MESSAGING",
        "root_cause": "CONSUMER_LAG",
        "service": "inventory-service",
        "alert_type": AlertType.MQ_LAG_HIGH,
        "expected_cause_code": "MQ_CONSUMER_ERROR",
        "symptoms": ["consumer lag", "message backlog"],
        "forbidden": ["DATABASE_SLOW_QUERY"],
        "variants": [
            {"value": 15000, "threshold": 5000, "noise_ratio": 0.0},
            {"value": 25000, "threshold": 5000, "noise_ratio": 0.1},
            {"value": 10000, "threshold": 5000, "has_wrong_runbook": True},
            {"value": 20000, "threshold": 5000, "tool_unavailable": "search_runbooks"},
        ],
    },
]


def generate_dataset() -> list[EvalCase]:
    """Generate the full evaluation dataset (48 cases)."""
    cases = []
    for tmpl in _FAULT_TEMPLATES:
        for i, variant in enumerate(tmpl["variants"]):
            case_id = f"EVAL-{tmpl['fault_id']}-{i+1:02d}"
            cases.append(EvalCase(
                case_id=case_id,
                fault_id=tmpl["fault_id"],
                category=tmpl["category"],
                root_cause=tmpl["root_cause"],
                affected_service=tmpl["service"],
                alert_type=tmpl["alert_type"],
                value=variant["value"],
                threshold=variant["threshold"],
                noise_ratio=variant.get("noise_ratio", 0.0),
                has_unrelated_deploy=variant.get("has_unrelated_deploy", False),
                tool_unavailable=variant.get("tool_unavailable"),
                has_wrong_runbook=variant.get("has_wrong_runbook", False),
                expected_cause_code=tmpl["expected_cause_code"],
                symptoms=tmpl.get("symptoms", []),
                forbidden_conclusions=tmpl.get("forbidden", []),
            ))
    return cases


def dataset_summary(cases: list[EvalCase]) -> dict:
    """Summarize the evaluation dataset."""
    by_category = {}
    by_variant = {"clean": 0, "noisy": 0, "unrelated_deploy": 0,
                  "tool_unavailable": 0, "wrong_runbook": 0}

    for c in cases:
        by_category[c.category] = by_category.get(c.category, 0) + 1
        if c.tool_unavailable:
            by_variant["tool_unavailable"] += 1
        elif c.has_wrong_runbook:
            by_variant["wrong_runbook"] += 1
        elif c.has_unrelated_deploy:
            by_variant["unrelated_deploy"] += 1
        elif c.noise_ratio > 0:
            by_variant["noisy"] += 1
        else:
            by_variant["clean"] += 1

    return {
        "total_cases": len(cases),
        "by_category": by_category,
        "by_variant": by_variant,
        "faults_covered": len(set(c.fault_id for c in cases)),
    }
