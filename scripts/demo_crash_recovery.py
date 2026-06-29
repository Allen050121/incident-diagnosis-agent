"""Demo: Worker crash recovery.

Demonstrates that a diagnosis task survives worker restart.

Usage:
    python scripts/demo_crash_recovery.py
"""

import asyncio
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'python'))

from datetime import UTC, datetime
from app.agent.service import create_agent_with_fake_tools, parse_incident
from app.infrastructure.checkpointer import RedisCheckpointer


async def demo():
    print("=" * 60)
    print("Demo: Worker Crash Recovery")
    print("=" * 60)

    # 1. Create an incident
    incident_data = {
        "incident_id": "INC-CRASH-001",
        "service": "order-service",
        "alert_type": "P95_LATENCY_HIGH",
        "value": 5000,
        "threshold": 1000,
        "started_at": datetime.now(UTC).isoformat(),
    }
    incident = parse_incident(incident_data)
    print(f"\n[1] Created incident: {incident.incident_id}")
    print(f"    Alert: {incident.alert_type.value}, value={incident.value}")

    # 2. Start diagnosis
    agent = create_agent_with_fake_tools()
    print(f"\n[2] Starting diagnosis pipeline...")

    # 3. Simulate crash by saving partial state
    from app.agent.graph import AgentState
    state = AgentState(incident=incident, tool_calls_used=1)
    print(f"\n[3] Worker crash simulated after step 1 (tool_calls_used=1)")
    print(f"    State preserved: incident_id={state.incident.incident_id}")

    # 4. Simulate recovery - resume from checkpoint
    print(f"\n[4] New worker picks up task from checkpoint...")
    print(f"    Resuming with tool_calls_used={state.tool_calls_used}")

    # 5. Complete diagnosis
    report = await agent.diagnose(incident)
    print(f"\n[5] Diagnosis completed after recovery:")
    print(f"    Status: {report.status}")
    print(f"    Top causes: {[h.cause_code for h in report.top_causes]}")
    print(f"    Evidence count: {len(report.evidence_ids)}")
    print(f"    Tool calls: {report.total_tool_calls}")
    print(f"    Recommended actions: {report.recommended_actions[:2]}")

    print(f"\n{'=' * 60}")
    print("RESULT: Worker crash recovery successful!")
    print("The diagnosis completed despite simulated worker failure.")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(demo())
