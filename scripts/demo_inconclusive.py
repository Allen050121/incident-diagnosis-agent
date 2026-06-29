"""Demo: Evidence insufficient returns INCONCLUSIVE.

Demonstrates that the agent correctly reports INCONCLUSIVE
when evidence is insufficient rather than guessing.

Usage:
    python scripts/demo_inconclusive.py
"""

import asyncio
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'python'))

from datetime import datetime
from app.agent.graph import DiagnosisAgent, AgentState
from app.agent.service import parse_incident
from app.domain.incident import (
    ConfidenceLevel, Evidence, Hypothesis, IncidentStatus,
)
from app.infrastructure.tool_definitions import ToolInput, ToolResult
from app.infrastructure.tool_executor import ToolExecutor


class FailingToolProvider:
    """Tool provider that always fails - simulates unavailable services."""

    async def execute(self, parameters: dict) -> dict:
        raise ConnectionError("Service unavailable - simulating infrastructure failure")


async def demo():
    print("=" * 60)
    print("Demo: Evidence Insufficient -> INCONCLUSIVE")
    print("=" * 60)

    # 1. Create incident
    incident_data = {
        "incident_id": "INC-INCONCLUSIVE-001",
        "service": "order-service",
        "alert_type": "ERROR_RATE_HIGH",
        "value": 0.15,
        "threshold": 0.05,
        "started_at": datetime.utcnow().isoformat(),
    }
    incident = parse_incident(incident_data)
    print(f"\n[1] Created incident: {incident.incident_id}")
    print(f"    Alert: {incident.alert_type.value}, error_rate={incident.value:.1%}")

    # 2. Create agent with ALL tools failing
    executor = ToolExecutor()
    failing = FailingToolProvider()
    executor.register("query_logs", failing)
    executor.register("query_metrics", failing)
    executor.register("query_deployments", failing)
    executor.register("search_runbooks", failing)

    agent = DiagnosisAgent(tool_executor=executor, max_tool_calls=10)
    print(f"\n[2] All 4 tools configured to FAIL (simulating infrastructure outage)")

    # 3. Run diagnosis
    print(f"\n[3] Running diagnosis...")
    report = await agent.diagnose(incident)

    print(f"\n[4] Diagnosis result:")
    print(f"    Status: {report.status}")
    print(f"    Top causes: {[h.cause_code for h in report.top_causes]}")
    print(f"    Evidence count: {len(report.evidence_ids)}")
    print(f"    Tool failures: {len(report.tool_failures)}")
    for failure in report.tool_failures[:3]:
        print(f"      - {failure[:80]}")

    # 5. Verify INCONCLUSIVE
    is_inconclusive = report.status == "INCONCLUSIVE"
    no_real_causes = all(
        h.confidence == ConfidenceLevel.LOW for h in report.top_causes
    )

    print(f"\n[5] Validation:")
    print(f"    Status is INCONCLUSIVE: {is_inconclusive}")
    print(f"    No confident causes: {no_real_causes}")

    if is_inconclusive:
        print(f"\n{'=' * 60}")
        print("RESULT: Agent correctly returned INCONCLUSIVE!")
        print("It did NOT guess a root cause without evidence.")
        print("This demonstrates stability over forced answers.")
        print("=" * 60)
    else:
        print(f"\n{'=' * 60}")
        print(f"UNEXPECTED: Status was '{report.status}' instead of INCONCLUSIVE")
        print("=" * 60)


if __name__ == "__main__":
    asyncio.run(demo())
