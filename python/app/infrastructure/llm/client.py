"""LLM client wrapper for DeepSeek API (OpenAI-compatible)

Handles reasoning model response parsing, token tracking, and cost estimation.
"""

import json
import time
from dataclasses import dataclass, field
from typing import Optional

from openai import OpenAI


@dataclass
class LLMUsage:
    """Token usage from a single LLM call"""
    prompt_tokens: int = 0
    completion_tokens: int = 0
    reasoning_tokens: int = 0
    total_tokens: int = 0


@dataclass
class LLMResponse:
    """Parsed LLM response"""
    content: str = ""
    reasoning_content: str = ""
    tool_calls: list[dict] = field(default_factory=list)
    usage: LLMUsage = field(default_factory=LLMUsage)
    latency_ms: float = 0.0
    model: str = ""


@dataclass
class LLMAccumulatedUsage:
    """Accumulated token usage across multiple LLM calls"""
    total_prompt_tokens: int = 0
    total_completion_tokens: int = 0
    total_reasoning_tokens: int = 0
    total_tokens: int = 0
    call_count: int = 0
    total_latency_ms: float = 0.0

    def add(self, usage: LLMUsage, latency_ms: float) -> None:
        self.total_prompt_tokens += usage.prompt_tokens
        self.total_completion_tokens += usage.completion_tokens
        self.total_reasoning_tokens += usage.reasoning_tokens
        self.total_tokens += usage.total_tokens
        self.call_count += 1
        self.total_latency_ms += latency_ms

    @property
    def avg_latency_ms(self) -> float:
        return self.total_latency_ms / self.call_count if self.call_count else 0.0

    def estimated_cost_usd(self, price_per_1m_input: float = 0.27,
                           price_per_1m_output: float = 1.10) -> float:
        """Estimate cost based on DeepSeek V4 Flash pricing (USD per 1M tokens)."""
        input_cost = self.total_prompt_tokens * price_per_1m_input / 1_000_000
        output_cost = self.total_completion_tokens * price_per_1m_output / 1_000_000
        return input_cost + output_cost


class LLMClient:
    """OpenAI-compatible LLM client with reasoning model support.

    Supports DeepSeek V4 Flash which returns both `content` (final answer)
    and `reasoning_content` (thinking process).
    """

    def __init__(self, api_key: str, base_url: str = "https://api.deepseek.com",
                 model: str = "deepseek-v4-flash", timeout: float = 30.0):
        self._model = model
        self._timeout = timeout
        self._client: Optional[OpenAI] = None
        if api_key:
            self._client = OpenAI(api_key=api_key, base_url=base_url, timeout=timeout)
        self._accumulated = LLMAccumulatedUsage()

    @property
    def is_available(self) -> bool:
        return self._client is not None

    @property
    def accumulated_usage(self) -> LLMAccumulatedUsage:
        return self._accumulated

    def chat(self, messages: list[dict], tools: list[dict] | None = None,
             tool_choice: str = "auto", max_tokens: int = 4096,
             temperature: float = 0.7) -> LLMResponse:
        """Send a chat completion request and parse the response.

        Args:
            messages: List of message dicts with role/content.
            tools: Optional list of tool definitions for function calling.
            tool_choice: "auto", "none", or "required".
            max_tokens: Maximum response tokens.
            temperature: Sampling temperature.

        Returns:
            LLMResponse with content, reasoning, tool calls, and usage.
        """
        if not self._client:
            return LLMResponse(content="")

        kwargs: dict = {
            "model": self._model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = tool_choice

        start = time.monotonic()
        resp = self._client.chat.completions.create(**kwargs)
        latency_ms = (time.monotonic() - start) * 1000

        # Parse response
        choice = resp.choices[0] if resp.choices else None
        msg = choice.message if choice else None

        content = msg.content or "" if msg else ""
        reasoning = ""
        if msg and hasattr(msg, "reasoning_content"):
            reasoning = msg.reasoning_content or ""

        tool_calls = []
        if msg and msg.tool_calls:
            for tc in msg.tool_calls:
                tool_calls.append({
                    "id": tc.id,
                    "name": tc.function.name,
                    "arguments": tc.function.arguments,
                })

        usage = LLMUsage(
            prompt_tokens=resp.usage.prompt_tokens if resp.usage else 0,
            completion_tokens=resp.usage.completion_tokens if resp.usage else 0,
            reasoning_tokens=(
                resp.usage.completion_tokens_details.reasoning_tokens
                if resp.usage and resp.usage.completion_tokens_details
                else 0
            ),
            total_tokens=resp.usage.total_tokens if resp.usage else 0,
        )

        self._accumulated.add(usage, latency_ms)

        return LLMResponse(
            content=content,
            reasoning_content=reasoning,
            tool_calls=tool_calls,
            usage=usage,
            latency_ms=latency_ms,
            model=resp.model,
        )

    def chat_json(self, messages: list[dict], max_tokens: int = 4096,
                  temperature: float = 0.3) -> dict:
        """Send a chat request expecting JSON in the content.

        Parses the content as JSON. If parsing fails, attempts to extract
        JSON from markdown code blocks.

        Returns:
            Parsed dict, or empty dict on failure.
        """
        response = self.chat(messages, max_tokens=max_tokens, temperature=temperature)
        text = response.content.strip()

        # Try direct parse
        try:
            return json.loads(text)
        except (json.JSONDecodeError, TypeError):
            pass

        # Try extracting from markdown code block
        if "```" in text:
            # Extract between ```json ... ``` or ``` ... ```
            parts = text.split("```")
            for i, part in enumerate(parts):
                stripped = part.strip()
                if stripped.startswith("json"):
                    stripped = stripped[4:].strip()
                try:
                    return json.loads(stripped)
                except (json.JSONDecodeError, TypeError):
                    continue

        return {}
