"""Redis Streams task queue - Outbox / Pending / Claim pattern

Streams:
  incident:diagnosis:tasks   - main task queue
  incident:diagnosis:retry   - retry queue
  incident:diagnosis:dlq     - dead letter queue (permanent failures)

Message format:
  {
    "taskId": "D1001",
    "incidentId": "INC-1001",
    "schemaVersion": 1,
    "traceId": "TRACE-1001",
    "deadlineAt": "2026-06-22T10:02:00+08:00",
    "payload": "{...}"  (JSON-encoded incident data)
  }
"""

import json
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from enum import Enum
from typing import Optional

import redis

from app.infrastructure.redis_client import get_redis


# Stream names
TASKS_STREAM = "incident:diagnosis:tasks"
RETRY_STREAM = "incident:diagnosis:retry"
DLQ_STREAM = "incident:diagnosis:dlq"

# Consumer groups
TASKS_GROUP = "diagnosis-workers"

# Redis keys for task state
TASK_STATE_PREFIX = "diagnosis:task:"  # + taskId
TASK_CLAIM_PREFIX = "diagnosis:claim:"  # + taskId


class TaskStatus(Enum):
    QUEUED = "QUEUED"
    CLAIMED = "CLAIMED"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    RETRYING = "RETRYING"


@dataclass
class TaskMessage:
    task_id: str
    incident_id: str
    payload: dict
    schema_version: int = 1
    trace_id: str = ""
    deadline_at: str = ""
    retry_count: int = 0
    max_retries: int = 3

    def to_dict(self) -> dict:
        return {
            "taskId": self.task_id,
            "incidentId": self.incident_id,
            "schemaVersion": self.schema_version,
            "traceId": self.trace_id or f"TRACE-{self.task_id}",
            "deadlineAt": self.deadline_at or (datetime.now(UTC) + timedelta(minutes=5)).isoformat(),
            "payload": json.dumps(self.payload),
            "retryCount": str(self.retry_count),
            "maxRetries": str(self.max_retries),
        }

    @staticmethod
    def from_dict(data: dict) -> "TaskMessage":
        return TaskMessage(
            task_id=data.get("taskId", data.get("task_id", "")),
            incident_id=data.get("incidentId", data.get("incident_id", "")),
            payload=json.loads(data.get("payload", "{}")) if isinstance(data.get("payload"), str) else data.get("payload", {}),
            schema_version=int(data.get("schemaVersion", 1)),
            trace_id=data.get("traceId", data.get("trace_id", "")),
            deadline_at=data.get("deadlineAt", data.get("deadline_at", "")),
            retry_count=int(data.get("retryCount", data.get("retry_count", 0))),
            max_retries=int(data.get("maxRetries", data.get("max_retries", 3))),
        )


@dataclass
class TaskState:
    task_id: str
    status: TaskStatus
    created_at: str = ""
    updated_at: str = ""
    claimed_by: str = ""
    claimed_at: str = ""
    result: dict = field(default_factory=dict)
    error: str = ""


class TaskQueue:
    """Redis Streams based task queue with claim/ack/retry"""

    def __init__(self, redis_client=None):
        self._redis = redis_client or get_redis()
        self._ensure_group()

    def _ensure_group(self):
        """Create consumer group if not exists"""
        try:
            self._redis.xgroup_create(TASKS_STREAM, TASKS_GROUP, id="0", mkstream=True)
        except redis.ResponseError as e:
            if "BUSYGROUP" not in str(e):
                raise

    def publish(self, task: TaskMessage) -> str:
        """Publish a task to the main stream"""
        now = datetime.now(UTC).isoformat()

        # Save task state
        state_key = f"{TASK_STATE_PREFIX}{task.task_id}"
        self._redis.hset(state_key, mapping={
            "task_id": task.task_id,
            "status": TaskStatus.QUEUED.value,
            "created_at": now,
            "updated_at": now,
            "incident_id": task.incident_id,
            "payload": json.dumps(task.payload),
        })
        self._redis.expire(state_key, 86400)  # 24h TTL

        # Publish to stream
        msg_id = self._redis.xadd(TASKS_STREAM, task.to_dict())
        return msg_id

    def claim(self, consumer_name: str, count: int = 1, block_ms: int = 5000) -> list[tuple[str, TaskMessage]]:
        """Claim tasks from the stream (consumer group read).

        Returns list of (message_id, TaskMessage) tuples.
        """
        # Use XREADGROUP to claim pending messages
        results = self._redis.xreadgroup(
            groupname=TASKS_GROUP,
            consumername=consumer_name,
            streams={TASKS_STREAM: ">"},
            count=count,
            block=block_ms,
        )

        claimed = []
        if results:
            for stream_name, messages in results:
                for msg_id, data in messages:
                    task = TaskMessage.from_dict(data)

                    # Check deadline
                    if task.deadline_at:
                        try:
                            deadline = datetime.fromisoformat(task.deadline_at)
                            if datetime.now(UTC) > deadline:
                                # Expired - send to DLQ
                                self._send_to_dlq(msg_id, task, "deadline exceeded")
                                self.ack(msg_id)
                                continue
                        except ValueError:
                            pass

                    # Update task state
                    claim_key = f"{TASK_CLAIM_PREFIX}{task.task_id}"
                    now = datetime.now(UTC).isoformat()
                    self._redis.hset(claim_key, mapping={
                        "claimed_by": consumer_name,
                        "claimed_at": now,
                        "msg_id": msg_id,
                    })
                    self._redis.expire(claim_key, 600)  # 10min TTL

                    state_key = f"{TASK_STATE_PREFIX}{task.task_id}"
                    self._redis.hset(state_key, mapping={
                        "status": TaskStatus.CLAIMED.value,
                        "claimed_by": consumer_name,
                        "claimed_at": now,
                        "updated_at": now,
                    })

                    claimed.append((msg_id, task))

        return claimed

    def ack(self, msg_id: str):
        """Acknowledge a message after successful processing"""
        self._redis.xack(TASKS_STREAM, TASKS_GROUP, msg_id)

    def complete(self, task_id: str, result: dict):
        """Mark task as completed"""
        state_key = f"{TASK_STATE_PREFIX}{task_id}"
        now = datetime.now(UTC).isoformat()
        self._redis.hset(state_key, mapping={
            "status": TaskStatus.COMPLETED.value,
            "updated_at": now,
            "result": json.dumps(result),
        })
        # Clean up claim
        self._redis.delete(f"{TASK_CLAIM_PREFIX}{task_id}")

    def fail(self, task_id: str, error: str, msg_id: str | None = None):
        """Mark task as failed, retry or send to DLQ"""
        state_key = f"{TASK_STATE_PREFIX}{task_id}"
        state = self._redis.hgetall(state_key)
        retry_count = int(state.get("retry_count", 0))
        max_retries = int(state.get("max_retries", 3))

        now = datetime.now(UTC).isoformat()

        if retry_count < max_retries:
            # Retry: re-publish to retry stream
            self._redis.hset(state_key, mapping={
                "status": TaskStatus.RETRYING.value,
                "updated_at": now,
                "error": error,
                "retry_count": str(retry_count + 1),
            })
            # Re-publish to main stream for retry
            payload = json.loads(state.get("payload", "{}"))
            task = TaskMessage(
                task_id=task_id,
                incident_id=state.get("incident_id", ""),
                payload=payload,
                retry_count=retry_count + 1,
            )
            self._redis.xadd(TASKS_STREAM, task.to_dict())
        else:
            # Max retries exceeded -> DLQ
            self._redis.hset(state_key, mapping={
                "status": TaskStatus.FAILED.value,
                "updated_at": now,
                "error": error,
            })
            if msg_id:
                self._send_to_dlq(msg_id, TaskMessage.from_dict(state), error)

        # Clean up claim
        self._redis.delete(f"{TASK_CLAIM_PREFIX}{task_id}")

    def cancel(self, task_id: str) -> bool:
        """Cancel a task"""
        state_key = f"{TASK_STATE_PREFIX}{task_id}"
        if not self._redis.exists(state_key):
            return False

        now = datetime.now(UTC).isoformat()
        self._redis.hset(state_key, mapping={
            "status": TaskStatus.CANCELLED.value,
            "updated_at": now,
        })
        self._redis.delete(f"{TASK_CLAIM_PREFIX}{task_id}")
        # Publish cancel event
        self._redis.publish(f"diagnosis:cancel:{task_id}", "CANCELLED")
        return True

    def get_state(self, task_id: str) -> Optional[TaskState]:
        """Get task state"""
        state_key = f"{TASK_STATE_PREFIX}{task_id}"
        data = self._redis.hgetall(state_key)
        if not data:
            return None

        return TaskState(
            task_id=data.get("task_id", task_id),
            status=TaskStatus(data.get("status", "QUEUED")),
            created_at=data.get("created_at", ""),
            updated_at=data.get("updated_at", ""),
            claimed_by=data.get("claimed_by", ""),
            claimed_at=data.get("claimed_at", ""),
            result=json.loads(data.get("result", "{}")) if data.get("result") else {},
            error=data.get("error", ""),
        )

    def is_cancelled(self, task_id: str) -> bool:
        """Check if a task has been cancelled"""
        state = self.get_state(task_id)
        return state is not None and state.status == TaskStatus.CANCELLED

    def _send_to_dlq(self, msg_id: str, task: TaskMessage, error: str):
        """Send a message to the dead letter queue"""
        dlq_data = task.to_dict()
        dlq_data["originalMsgId"] = msg_id
        dlq_data["error"] = error
        dlq_data["dlqAt"] = datetime.now(UTC).isoformat()
        self._redis.xadd(DLQ_STREAM, dlq_data)


class InMemoryTaskQueue:
    """In-memory task queue for testing (no Redis required)"""

    def __init__(self):
        self._tasks: dict[str, TaskState] = {}
        self._queue: list[tuple[str, TaskMessage]] = []
        self._cancelled: set[str] = set()

    def publish(self, task: TaskMessage) -> str:
        now = datetime.now(UTC).isoformat()
        self._tasks[task.task_id] = TaskState(
            task_id=task.task_id,
            status=TaskStatus.QUEUED,
            created_at=now,
            updated_at=now,
        )
        msg_id = f"msg-{uuid.uuid4().hex[:8]}"
        self._queue.append((msg_id, task))
        return msg_id

    def claim(self, consumer_name: str, count: int = 1, block_ms: int = 0) -> list[tuple[str, TaskMessage]]:
        claimed = []
        for _ in range(min(count, len(self._queue))):
            if self._queue:
                msg_id, task = self._queue.pop(0)
                if task.task_id in self._cancelled:
                    continue
                now = datetime.now(UTC).isoformat()
                state = self._tasks.get(task.task_id)
                if state:
                    state.status = TaskStatus.CLAIMED
                    state.claimed_by = consumer_name
                    state.claimed_at = now
                    state.updated_at = now
                claimed.append((msg_id, task))
        return claimed

    def ack(self, msg_id: str):
        pass  # No-op for in-memory

    def complete(self, task_id: str, result: dict):
        state = self._tasks.get(task_id)
        if state:
            state.status = TaskStatus.COMPLETED
            state.result = result
            state.updated_at = datetime.now(UTC).isoformat()

    def fail(self, task_id: str, error: str, msg_id: str | None = None):
        state = self._tasks.get(task_id)
        if state:
            state.status = TaskStatus.FAILED
            state.error = error
            state.updated_at = datetime.now(UTC).isoformat()

    def cancel(self, task_id: str) -> bool:
        self._cancelled.add(task_id)
        state = self._tasks.get(task_id)
        if state:
            state.status = TaskStatus.CANCELLED
            state.updated_at = datetime.now(UTC).isoformat()
            return True
        return False

    def get_state(self, task_id: str) -> Optional[TaskState]:
        return self._tasks.get(task_id)

    def is_cancelled(self, task_id: str) -> bool:
        return task_id in self._cancelled
