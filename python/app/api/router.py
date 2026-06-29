"""API router for diagnosis endpoints - sync, async, and SSE"""

import asyncio
import uuid
from datetime import datetime, timedelta

from fastapi import APIRouter, BackgroundTasks
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.agent.service import create_agent_with_fake_tools, parse_incident
from app.infrastructure.sse_manager import sse_manager
from app.infrastructure.task_queue import InMemoryTaskQueue, TaskMessage
from app.worker.diagnosis_worker import DiagnosisWorker

router = APIRouter()

# Shared in-memory task queue and worker state
_task_queue = InMemoryTaskQueue()
_workers: dict[str, DiagnosisWorker] = {}


class DiagnosisRequest(BaseModel):
    incident_id: str
    service: str
    endpoint: str | None = None
    alert_type: str
    value: float
    threshold: float
    started_at: str


class HypothesisResponse(BaseModel):
    rank: int
    cause_code: str
    confidence: str
    supporting_evidence: list[str]
    contradicting_evidence: list[str]
    reasoning_summary: str


class DiagnosisResponse(BaseModel):
    incident_id: str
    status: str
    top_causes: list[HypothesisResponse]
    recommended_actions: list[str]
    missing_evidence: list[str]
    tool_failures: list[str]
    evidence_ids: list[str]
    investigation_steps: int
    total_tool_calls: int


class AsyncDiagnosisResponse(BaseModel):
    task_id: str
    status: str
    message: str


class TaskStatusResponse(BaseModel):
    task_id: str
    status: str
    created_at: str = ""
    updated_at: str = ""
    result: dict = {}
    error: str = ""


# ============================================================
# Synchronous diagnosis (Phase 3 - backward compatible)
# ============================================================

@router.post("/diagnose", response_model=DiagnosisResponse)
async def start_diagnosis(request: DiagnosisRequest):
    """Start a synchronous diagnosis - runs the full agent pipeline"""
    incident = parse_incident(request.model_dump())
    agent = create_agent_with_fake_tools()
    report = await agent.diagnose(incident)

    return DiagnosisResponse(
        incident_id=report.incident_id,
        status=report.status,
        top_causes=[
            HypothesisResponse(
                rank=h.rank,
                cause_code=h.cause_code,
                confidence=h.confidence.value,
                supporting_evidence=h.supporting_evidence,
                contradicting_evidence=h.contradicting_evidence,
                reasoning_summary=h.reasoning_summary,
            )
            for h in report.top_causes
        ],
        recommended_actions=report.recommended_actions,
        missing_evidence=report.missing_evidence,
        tool_failures=report.tool_failures,
        evidence_ids=report.evidence_ids,
        investigation_steps=report.investigation_steps,
        total_tool_calls=report.total_tool_calls,
    )


# ============================================================
# Asynchronous diagnosis (Phase 5)
# ============================================================

@router.post("/diagnose/async", response_model=AsyncDiagnosisResponse)
async def start_async_diagnosis(request: DiagnosisRequest, background_tasks: BackgroundTasks):
    """Start an asynchronous diagnosis task.

    Returns a task_id immediately. Use GET /tasks/{task_id} to check status.
    Use GET /tasks/{task_id}/events for SSE streaming.
    """
    task_id = f"D-{uuid.uuid4().hex[:8].upper()}"

    # Create task message
    task_msg = TaskMessage(
        task_id=task_id,
        incident_id=request.incident_id,
        payload=request.model_dump(),
        deadline_at=(datetime.utcnow() + timedelta(minutes=5)).isoformat(),
    )

    # Publish to queue
    _task_queue.publish(task_msg)

    # Run in background
    background_tasks.add_task(_run_async_task, task_msg)

    return AsyncDiagnosisResponse(
        task_id=task_id,
        status="QUEUED",
        message="Diagnosis task created. Use GET /tasks/{task_id}/events for SSE stream.",
    )


async def _run_async_task(task_msg: TaskMessage):
    """Run diagnosis in background"""
    worker = DiagnosisWorker(task_queue=_task_queue, agent=create_agent_with_fake_tools())
    _workers[task_msg.task_id] = worker

    try:
        claimed = [(task_msg.task_id, task_msg)]  # Simulate claim
        await worker._run_diagnosis(task_msg.task_id, parse_incident(task_msg.payload))
        _task_queue.complete(task_msg.task_id, {"status": "completed"})
    except Exception as e:
        _task_queue.fail(task_msg.task_id, str(e))
    finally:
        _workers.pop(task_msg.task_id, None)


# ============================================================
# Task status and SSE
# ============================================================

@router.get("/tasks/{task_id}", response_model=TaskStatusResponse)
async def get_task_status(task_id: str):
    """Get the status of an async diagnosis task"""
    state = _task_queue.get_state(task_id)
    if state is None:
        return TaskStatusResponse(
            task_id=task_id,
            status="NOT_FOUND",
            error="Task not found",
        )

    return TaskStatusResponse(
        task_id=state.task_id,
        status=state.status.value,
        created_at=state.created_at,
        updated_at=state.updated_at,
        result=state.result,
        error=state.error,
    )


@router.get("/tasks/{task_id}/events")
async def get_task_events(task_id: str):
    """SSE event stream for a diagnosis task.

    Returns real-time events as Server-Sent Events.
    """
    return StreamingResponse(
        sse_manager.event_stream(task_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/tasks/{task_id}/cancel")
async def cancel_task(task_id: str):
    """Cancel a running diagnosis task"""
    success = _task_queue.cancel(task_id)
    if success:
        return {"task_id": task_id, "status": "CANCELLED", "message": "Task cancelled"}
    return {"task_id": task_id, "status": "NOT_FOUND", "message": "Task not found or already completed"}


@router.get("/diagnosis/{task_id}")
async def get_diagnosis_status(task_id: str):
    """Get diagnosis task status (backward compatible alias)"""
    return await get_task_status(task_id)
