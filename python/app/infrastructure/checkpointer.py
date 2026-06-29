"""Checkpointer - save/restore agent state for crash recovery

Saves agent state at key nodes:
  - After incident parsing
  - After investigation plan creation
  - After each evidence collection
  - After hypothesis building
  - After report generation

State is stored in Redis with the incident_id as key.
Large log data is NOT stored - only references and summaries.
"""

import json
from datetime import UTC, datetime
from typing import Optional, Protocol

from app.infrastructure.redis_client import get_redis


CHECKPOINT_PREFIX = "diagnosis:checkpoint:"


class Checkpointer(Protocol):
    """Protocol for checkpoint implementations"""
    async def save(self, task_id: str, node: str, state: dict) -> None: ...
    async def load(self, task_id: str) -> Optional[dict]: ...
    async def delete(self, task_id: str) -> None: ...


class RedisCheckpointer:
    """Redis-based checkpointer for crash recovery"""

    def __init__(self, redis_client=None, ttl_seconds: int = 86400):
        self._redis = redis_client or get_redis()
        self._ttl = ttl_seconds

    async def save(self, task_id: str, node: str, state: dict) -> None:
        """Save checkpoint at a specific node"""
        key = f"{CHECKPOINT_PREFIX}{task_id}"

        # Serialize state - only save essential fields, not large data
        checkpoint = {
            "task_id": task_id,
            "node": node,
            "saved_at": datetime.now(UTC).isoformat(),
            "state": _serialize_state(state),
        }

        self._redis.set(key, json.dumps(checkpoint), ex=self._ttl)

    async def load(self, task_id: str) -> Optional[dict]:
        """Load the latest checkpoint for a task"""
        key = f"{CHECKPOINT_PREFIX}{task_id}"
        data = self._redis.get(key)
        if data is None:
            return None
        return json.loads(data)

    async def delete(self, task_id: str) -> None:
        """Delete checkpoint after task completion"""
        key = f"{CHECKPOINT_PREFIX}{task_id}"
        self._redis.delete(key)

    async def get_node(self, task_id: str) -> Optional[str]:
        """Get the last checkpointed node"""
        checkpoint = await self.load(task_id)
        if checkpoint:
            return checkpoint.get("node")
        return None


class InMemoryCheckpointer:
    """In-memory checkpointer for testing"""

    def __init__(self):
        self._store: dict[str, dict] = {}

    async def save(self, task_id: str, node: str, state: dict) -> None:
        self._store[task_id] = {
            "task_id": task_id,
            "node": node,
            "saved_at": datetime.now(UTC).isoformat(),
            "state": _serialize_state(state),
        }

    async def load(self, task_id: str) -> Optional[dict]:
        return self._store.get(task_id)

    async def delete(self, task_id: str) -> None:
        self._store.pop(task_id, None)

    async def get_node(self, task_id: str) -> Optional[str]:
        checkpoint = self._store.get(task_id)
        if checkpoint:
            return checkpoint.get("node")
        return None


def _serialize_state(state: dict) -> dict:
    """Serialize agent state for checkpoint storage.

    Rules:
    - Don't store large log content, only references
    - Don't store raw tool results, only evidence IDs
    - Keep: incident, plan, hypothesis, evidence IDs, budget, node position
    """
    serialized = {}

    for key, value in state.items():
        if key == "evidence" and isinstance(value, list):
            # Only store evidence IDs and summaries, not full content
            serialized[key] = [
                {
                    "evidence_id": e.get("evidence_id", ""),
                    "source": e.get("source", ""),
                    "summary": str(e.get("content", {}))[:200],  # Truncate
                }
                for e in value
            ]
        elif isinstance(value, (str, int, float, bool, type(None))):
            serialized[key] = value
        elif isinstance(value, (list, dict)):
            serialized[key] = value
        else:
            serialized[key] = str(value)

    return serialized


# Node ordering for resume logic
NODE_ORDER = [
    "load_incident",
    "classify_incident",
    "load_topology",
    "create_plan",
    "collect_initial_evidence",
    "build_hypotheses",
    "verify_hypotheses",
    "validate_evidence",
    "generate_report",
]


def get_nodes_to_resume(from_node: str) -> list[str]:
    """Get the list of nodes to execute when resuming from a checkpoint"""
    try:
        idx = NODE_ORDER.index(from_node)
        return NODE_ORDER[idx:]
    except ValueError:
        return NODE_ORDER
