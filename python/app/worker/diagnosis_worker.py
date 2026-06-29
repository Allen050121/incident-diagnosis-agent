"""Diagnosis worker - background task processor

Consumes tasks from Redis Streams, runs the diagnosis agent,
and publishes progress events via SSE.

Features:
  - Crash recovery via Checkpointer
  - Task cancellation support
  - Deadline enforcement
  - SSE progress events
"""

import asyncio
import uuid
from datetime import datetime
from typing import Optional

from app.agent.graph import DiagnosisAgent
from app.agent.service import parse_incident
from app.domain.incident import Incident
from app.infrastructure.checkpointer import InMemoryCheckpointer, RedisCheckpointer, get_nodes_to_resume
from app.infrastructure.sse_manager import DiagnosisEvent, EventType, sse_manager
from app.infrastructure.task_queue import InMemoryTaskQueue, TaskMessage, TaskQueue, TaskStatus
from app.infrastructure.tool_executor import ToolExecutor


class DiagnosisWorker:
    """Background worker that processes diagnosis tasks"""

    def __init__(
        self,
        task_queue=None,
        checkpointer=None,
        agent: Optional[DiagnosisAgent] = None,
        consumer_name: str = "",
    ):
        self._queue = task_queue
        self._checkpointer = checkpointer
        self._agent = agent
        self._consumer_name = consumer_name or f"worker-{uuid.uuid4().hex[:8]}"
        self._running = False
        self._current_task: Optional[str] = None

    async def start(self):
        """Start the worker loop"""
        self._running = True
        while self._running:
            try:
                await self._process_one()
            except Exception as e:
                print(f"Worker error: {e}")
                await asyncio.sleep(1)

    async def stop(self):
        """Stop the worker"""
        self._running = False

    async def _process_one(self):
        """Claim and process one task"""
        if self._queue is None:
            return

        claimed = self._queue.claim(self._consumer_name, count=1, block_ms=2000)
        if not claimed:
            return

        msg_id, task_msg = claimed[0]
        self._current_task = task_msg.task_id

        try:
            # Check if already cancelled
            if self._queue.is_cancelled(task_msg.task_id):
                await sse_manager.publish(DiagnosisEvent(
                    event_type=EventType.TASK_CANCELLED,
                    task_id=task_msg.task_id,
                    data={"reason": "Task was cancelled before processing"},
                ))
                self._queue.ack(msg_id)
                return

            # Check deadline
            if task_msg.deadline_at:
                deadline = datetime.fromisoformat(task_msg.deadline_at)
                if datetime.utcnow() > deadline:
                    self._queue.fail(task_msg.task_id, "Deadline exceeded", msg_id)
                    return

            # Publish start event
            await sse_manager.publish(DiagnosisEvent(
                event_type=EventType.INVESTIGATION_STARTED,
                task_id=task_msg.task_id,
                data={"incident_id": task_msg.incident_id},
            ))

            # Parse incident
            incident = parse_incident(task_msg.payload)

            # Check for checkpoint recovery
            if self._checkpointer:
                checkpoint = await self._checkpointer.load(task_msg.task_id)
                if checkpoint:
                    # Resume from checkpoint
                    result = await self._run_with_checkpoint(task_msg.task_id, incident, checkpoint)
                else:
                    result = await self._run_diagnosis(task_msg.task_id, incident)
            else:
                result = await self._run_diagnosis(task_msg.task_id, incident)

            # Complete
            self._queue.complete(task_msg.task_id, result)
            self._queue.ack(msg_id)

            # Clean up checkpoint
            if self._checkpointer:
                await self._checkpointer.delete(task_msg.task_id)

        except asyncio.CancelledError:
            self._queue.fail(task_msg.task_id, "Task cancelled", msg_id)
        except Exception as e:
            self._queue.fail(task_msg.task_id, str(e), msg_id)
            await sse_manager.publish(DiagnosisEvent(
                event_type=EventType.ERROR,
                task_id=task_msg.task_id,
                data={"error": str(e)},
            ))
        finally:
            self._current_task = None

    async def _run_diagnosis(self, task_id: str, incident: Incident) -> dict:
        """Run the full diagnosis pipeline with SSE events"""
        if self._agent is None:
            from app.agent.service import create_agent_with_fake_tools
            agent = create_agent_with_fake_tools()
        else:
            agent = self._agent

        # Check cancellation before each major step
        if self._queue and self._queue.is_cancelled(task_id):
            raise asyncio.CancelledError("Task cancelled")

        # Run diagnosis
        report = await agent.diagnose(incident)

        # Publish completion event
        event_type = (
            EventType.DIAGNOSIS_COMPLETE if report.status == "DIAGNOSED"
            else EventType.DIAGNOSIS_INCONCLUSIVE
        )
        await sse_manager.publish(DiagnosisEvent(
            event_type=event_type,
            task_id=task_id,
            data={
                "status": report.status,
                "top_causes": [
                    {
                        "rank": h.rank,
                        "cause_code": h.cause_code,
                        "confidence": h.confidence.value,
                        "supporting_evidence": h.supporting_evidence,
                    }
                    for h in report.top_causes
                ],
                "recommended_actions": report.recommended_actions,
            },
        ))

        return {
            "incident_id": report.incident_id,
            "status": report.status,
            "top_causes": [
                {
                    "rank": h.rank,
                    "cause_code": h.cause_code,
                    "confidence": h.confidence.value,
                    "supporting_evidence": h.supporting_evidence,
                    "contradicting_evidence": h.contradicting_evidence,
                    "reasoning_summary": h.reasoning_summary,
                }
                for h in report.top_causes
            ],
            "recommended_actions": report.recommended_actions,
            "missing_evidence": report.missing_evidence,
            "tool_failures": report.tool_failures,
            "evidence_ids": report.evidence_ids,
            "total_tool_calls": report.total_tool_calls,
        }

    async def _run_with_checkpoint(self, task_id: str, incident: Incident, checkpoint: dict) -> dict:
        """Resume diagnosis from checkpoint"""
        # For MVP, just run full diagnosis
        # Future: skip completed nodes based on checkpoint
        return await self._run_diagnosis(task_id, incident)

    def process_task_sync(self, task_msg: TaskMessage) -> dict:
        """Process a single task synchronously (for testing)"""
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(self._run_diagnosis(task_msg.task_id, parse_incident(task_msg.payload)))
        finally:
            loop.close()


def create_worker(
    use_redis: bool = False,
    agent: Optional[DiagnosisAgent] = None,
) -> DiagnosisWorker:
    """Create a worker with appropriate backend"""
    if use_redis:
        queue = TaskQueue()
        checkpointer = RedisCheckpointer()
    else:
        queue = InMemoryTaskQueue()
        checkpointer = InMemoryCheckpointer()

    return DiagnosisWorker(
        task_queue=queue,
        checkpointer=checkpointer,
        agent=agent,
    )
