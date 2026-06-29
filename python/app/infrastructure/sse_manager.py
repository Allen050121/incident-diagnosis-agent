"""SSE event manager - real-time diagnosis progress push

Events pushed:
  - investigation_started
  - tool_calling
  - tool_completed
  - evidence_received
  - hypothesis_formed
  - hypothesis_verified
  - diagnosis_complete
  - diagnosis_inconclusive
  - task_cancelled
  - error
"""

import asyncio
import json
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import AsyncGenerator, Optional


class EventType(Enum):
    INVESTIGATION_STARTED = "investigation_started"
    TOOL_CALLING = "tool_calling"
    TOOL_COMPLETED = "tool_completed"
    EVIDENCE_RECEIVED = "evidence_received"
    HYPOTHESIS_FORMED = "hypothesis_formed"
    HYPOTHESIS_VERIFIED = "hypothesis_verified"
    DIAGNOSIS_COMPLETE = "diagnosis_complete"
    DIAGNOSIS_INCONCLUSIVE = "diagnosis_inconclusive"
    TASK_CANCELLED = "task_cancelled"
    ERROR = "error"
    PROGRESS = "progress"


@dataclass
class DiagnosisEvent:
    event_type: EventType
    task_id: str
    data: dict = field(default_factory=dict)
    timestamp: str = ""

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.utcnow().isoformat()

    def to_sse(self) -> str:
        """Format as SSE data"""
        payload = {
            "eventType": self.event_type.value,
            "taskId": self.task_id,
            "data": self.data,
            "timestamp": self.timestamp,
        }
        return f"event: {self.event_type.value}\ndata: {json.dumps(payload)}\n\n"


class SSEManager:
    """Manages SSE connections and event broadcasting per task"""

    def __init__(self):
        self._queues: dict[str, list[asyncio.Queue]] = {}
        self._lock = asyncio.Lock()

    async def subscribe(self, task_id: str) -> asyncio.Queue:
        """Subscribe to events for a specific task"""
        async with self._lock:
            if task_id not in self._queues:
                self._queues[task_id] = []
            queue = asyncio.Queue()
            self._queues[task_id].append(queue)
            return queue

    async def unsubscribe(self, task_id: str, queue: asyncio.Queue):
        """Unsubscribe from task events"""
        async with self._lock:
            if task_id in self._queues:
                try:
                    self._queues[task_id].remove(queue)
                except ValueError:
                    pass
                if not self._queues[task_id]:
                    del self._queues[task_id]

    async def publish(self, event: DiagnosisEvent):
        """Publish an event to all subscribers of a task"""
        async with self._lock:
            queues = self._queues.get(event.task_id, [])
            for queue in queues:
                try:
                    queue.put_nowait(event)
                except asyncio.QueueFull:
                    pass  # Drop event if queue is full

    async def event_stream(self, task_id: str) -> AsyncGenerator[str, None]:
        """Generate SSE events for a task"""
        queue = await self.subscribe(task_id)
        try:
            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=30.0)
                    yield event.to_sse()

                    # Stop stream on terminal events
                    if event.event_type in (
                        EventType.DIAGNOSIS_COMPLETE,
                        EventType.DIAGNOSIS_INCONCLUSIVE,
                        EventType.TASK_CANCELLED,
                        EventType.ERROR,
                    ):
                        break
                except asyncio.TimeoutError:
                    # Send keepalive comment
                    yield ": keepalive\n\n"
        finally:
            await self.unsubscribe(task_id, queue)

    def has_subscribers(self, task_id: str) -> bool:
        """Check if a task has active subscribers"""
        return task_id in self._queues and len(self._queues[task_id]) > 0


# Global SSE manager instance
sse_manager = SSEManager()
