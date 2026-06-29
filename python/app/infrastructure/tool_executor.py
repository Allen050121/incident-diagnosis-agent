"""Tool executor - unified execution pipeline for all diagnosis tools"""

import uuid
from datetime import datetime, timedelta
from typing import Protocol

from app.infrastructure.tool_definitions import ToolInput, ToolResult, validate_tool_input


class ToolProvider(Protocol):
    """Protocol for tool implementations"""
    async def execute(self, parameters: dict) -> dict:
        ...


class ToolExecutor:
    """Unified tool executor with evidence ID tracking, timeout, and error normalization"""

    def __init__(self, providers: dict[str, ToolProvider] | None = None):
        self._providers: dict[str, ToolProvider] = providers or {}

    def register(self, tool_name: str, provider: ToolProvider):
        self._providers[tool_name] = provider

    def _generate_evidence_id(self, prefix: str, tool: str) -> str:
        source_map = {
            "query_logs": "LOG",
            "query_metrics": "METRIC",
            "query_deployments": "DEPLOY",
            "search_runbooks": "RUNBOOK",
        }
        source = source_map.get(tool, "EVD")
        seq = uuid.uuid4().hex[:6].upper()
        return f"{source}-{seq}"

    async def execute(self, tool_input: ToolInput) -> ToolResult:
        # 1. Validate parameters and whitelist
        validation_error = validate_tool_input(tool_input)
        if validation_error:
            return ToolResult(
                tool=tool_input.tool,
                evidence_id=self._generate_evidence_id(tool_input.evidence_id_prefix, tool_input.tool),
                data={},
                success=False,
                error=validation_error,
            )

        # 2. Check provider exists
        provider = self._providers.get(tool_input.tool)
        if provider is None:
            return ToolResult(
                tool=tool_input.tool,
                evidence_id=self._generate_evidence_id(tool_input.evidence_id_prefix, tool_input.tool),
                data={},
                success=False,
                error=f"No provider registered for tool '{tool_input.tool}'",
            )

        # 3. Execute with timeout
        try:
            import asyncio
            data = await asyncio.wait_for(
                provider.execute(tool_input.parameters),
                timeout=tool_input.timeout_seconds,
            )
        except asyncio.TimeoutError:
            return ToolResult(
                tool=tool_input.tool,
                evidence_id=self._generate_evidence_id(tool_input.evidence_id_prefix, tool_input.tool),
                data={},
                success=False,
                error=f"Tool '{tool_input.tool}' timed out after {tool_input.timeout_seconds}s",
            )
        except Exception as e:
            return ToolResult(
                tool=tool_input.tool,
                evidence_id=self._generate_evidence_id(tool_input.evidence_id_prefix, tool_input.tool),
                data={},
                success=False,
                error=f"Tool '{tool_input.tool}' failed: {str(e)}",
            )

        # 4. Build result with evidence ID
        evidence_id = self._generate_evidence_id(tool_input.evidence_id_prefix, tool_input.tool)
        now = datetime.utcnow()
        query_window = {
            "from": tool_input.parameters.get("start_time", (now - timedelta(minutes=15)).isoformat()),
            "to": tool_input.parameters.get("end_time", now.isoformat()),
        }

        return ToolResult(
            tool=tool_input.tool,
            evidence_id=evidence_id,
            data=data,
            success=True,
            query_window=query_window,
            truncated=data.get("truncated", False),
        )
