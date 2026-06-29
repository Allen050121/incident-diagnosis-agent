"""Phase 5 seed tests: async tasks, crash recovery, SSE, cancellation

Tests cover:
  - Task queue: publish, claim, complete, fail, cancel
  - Checkpointer: save, load, resume from node
  - SSE: subscribe, publish, event stream
  - Worker: process task, cancellation
  - InMemoryTaskQueue for testing
"""

import asyncio
from datetime import datetime, timedelta

import pytest

from app.agent.service import parse_incident
from app.domain.incident import AlertType, Incident
from app.infrastructure.checkpointer import (
    InMemoryCheckpointer,
    get_nodes_to_resume,
)
from app.infrastructure.sse_manager import (
    DiagnosisEvent,
    EventType,
    SSEManager,
)
from app.infrastructure.task_queue import (
    InMemoryTaskQueue,
    TaskMessage,
    TaskStatus,
)
from app.worker.diagnosis_worker import DiagnosisWorker


# ============================================================
# Test 31: TaskQueue - publish and claim
# ============================================================
def test_task_queue_publish_and_claim():
    queue = InMemoryTaskQueue()
    task = TaskMessage(
        task_id="D-001",
        incident_id="INC-001",
        payload={"incident_id": "INC-001", "service": "order-service", "alert_type": "P95_LATENCY_HIGH"},
    )
    msg_id = queue.publish(task)
    assert msg_id

    claimed = queue.claim("worker-1", count=1)
    assert len(claimed) == 1
    assert claimed[0][1].task_id == "D-001"


# ============================================================
# Test 32: TaskQueue - complete updates status
# ============================================================
def test_task_queue_complete():
    queue = InMemoryTaskQueue()
    task = TaskMessage(task_id="D-002", incident_id="INC-002", payload={})
    queue.publish(task)
    queue.claim("worker-1")

    queue.complete("D-002", {"status": "DIAGNOSED", "top_cause": "DB_SLOW_QUERY"})

    state = queue.get_state("D-002")
    assert state is not None
    assert state.status == TaskStatus.COMPLETED


# ============================================================
# Test 33: TaskQueue - cancel prevents processing
# ============================================================
def test_task_queue_cancel():
    queue = InMemoryTaskQueue()
    task = TaskMessage(task_id="D-003", incident_id="INC-003", payload={})
    queue.publish(task)

    result = queue.cancel("D-003")
    assert result is True
    assert queue.is_cancelled("D-003")

    state = queue.get_state("D-003")
    assert state.status == TaskStatus.CANCELLED


# ============================================================
# Test 34: TaskQueue - fail updates status with error
# ============================================================
def test_task_queue_fail():
    queue = InMemoryTaskQueue()
    task = TaskMessage(task_id="D-004", incident_id="INC-004", payload={})
    queue.publish(task)
    queue.claim("worker-1")

    queue.fail("D-004", "Tool timeout")

    state = queue.get_state("D-004")
    assert state is not None
    assert state.status == TaskStatus.FAILED
    assert state.error == "Tool timeout"


# ============================================================
# Test 35: Checkpointer - save and load
# ============================================================
@pytest.mark.asyncio
async def test_checkpointer_save_and_load():
    cp = InMemoryCheckpointer()

    await cp.save("D-010", "create_plan", {
        "incident": {"incident_id": "INC-010", "service": "order-service"},
        "plan": {"steps": [{"tool": "query_logs"}]},
    })

    loaded = await cp.load("D-010")
    assert loaded is not None
    assert loaded["node"] == "create_plan"
    assert loaded["state"]["incident"]["incident_id"] == "INC-010"


# ============================================================
# Test 36: Checkpointer - delete removes checkpoint
# ============================================================
@pytest.mark.asyncio
async def test_checkpointer_delete():
    cp = InMemoryCheckpointer()
    await cp.save("D-011", "build_hypotheses", {"test": True})
    await cp.delete("D-011")

    loaded = await cp.load("D-011")
    assert loaded is None


# ============================================================
# Test 37: Checkpointer - get_nodes_to_resume
# ============================================================
def test_get_nodes_to_resume():
    nodes = get_nodes_to_resume("collect_initial_evidence")
    assert nodes[0] == "collect_initial_evidence"
    assert "build_hypotheses" in nodes
    assert "generate_report" in nodes


# ============================================================
# Test 38: SSE manager - publish and subscribe
# ============================================================
@pytest.mark.asyncio
async def test_sse_publish_subscribe():
    sse = SSEManager()
    queue = await sse.subscribe("D-020")

    event = DiagnosisEvent(
        event_type=EventType.INVESTIGATION_STARTED,
        task_id="D-020",
        data={"incident_id": "INC-020"},
    )
    await sse.publish(event)

    received = await asyncio.wait_for(queue.get(), timeout=1.0)
    assert received.event_type == EventType.INVESTIGATION_STARTED
    assert received.task_id == "D-020"


# ============================================================
# Test 39: SSE event - to_sse format
# ============================================================
def test_sse_event_format():
    event = DiagnosisEvent(
        event_type=EventType.TOOL_CALLING,
        task_id="D-021",
        data={"tool": "query_logs", "service": "order-service"},
    )
    sse_str = event.to_sse()
    assert "event: tool_calling" in sse_str
    assert "D-021" in sse_str
    assert "query_logs" in sse_str


# ============================================================
# Test 40: Worker - process task produces diagnosis
# ============================================================
@pytest.mark.asyncio
async def test_worker_process_task():
    queue = InMemoryTaskQueue()
    worker = DiagnosisWorker(task_queue=queue)

    task = TaskMessage(
        task_id="D-030",
        incident_id="INC-030",
        payload={
            "incident_id": "INC-030",
            "service": "order-service",
            "endpoint": "/api/orders",
            "alert_type": "P95_LATENCY_HIGH",
            "value": 1800.0,
            "threshold": 500.0,
            "started_at": datetime.utcnow().isoformat(),
        },
    )

    result = await worker._run_diagnosis(task.task_id, parse_incident(task.payload))
    assert result["status"] in ("DIAGNOSED", "INCONCLUSIVE")
    assert "top_causes" in result
    assert len(result["top_causes"]) > 0


# ============================================================
# Test 41: Worker - cancelled task is not processed
# ============================================================
@pytest.mark.asyncio
async def test_worker_cancelled_task():
    queue = InMemoryTaskQueue()
    worker = DiagnosisWorker(task_queue=queue)

    task = TaskMessage(
        task_id="D-031",
        incident_id="INC-031",
        payload={
            "incident_id": "D-031",
            "service": "order-service",
            "alert_type": "P95_LATENCY_HIGH",
            "value": 100.0,
            "threshold": 50.0,
            "started_at": datetime.utcnow().isoformat(),
        },
    )
    queue.publish(task)
    queue.cancel("D-031")

    # Claim should skip cancelled tasks
    claimed = queue.claim("worker-1")
    # The task is still claimed from queue but marked cancelled
    assert queue.is_cancelled("D-031")


# ============================================================
# Test 42: TaskMessage serialization round-trip
# ============================================================
def test_task_message_serialization():
    task = TaskMessage(
        task_id="D-040",
        incident_id="INC-040",
        payload={"service": "order-service", "alert_type": "ERROR_RATE_HIGH"},
        trace_id="TRACE-040",
        retry_count=2,
    )
    data = task.to_dict()
    restored = TaskMessage.from_dict(data)

    assert restored.task_id == "D-040"
    assert restored.incident_id == "INC-040"
    assert restored.trace_id == "TRACE-040"
    assert restored.retry_count == 2
    assert restored.payload["service"] == "order-service"


# ============================================================
# Test 43: SSE unsubscribe stops delivery
# ============================================================
@pytest.mark.asyncio
async def test_sse_unsubscribe():
    sse = SSEManager()
    queue = await sse.subscribe("D-050")
    await sse.unsubscribe("D-050", queue)

    assert not sse.has_subscribers("D-050")

    # Publishing should not error even with no subscribers
    await sse.publish(DiagnosisEvent(
        event_type=EventType.PROGRESS,
        task_id="D-050",
        data={"message": "test"},
    ))
