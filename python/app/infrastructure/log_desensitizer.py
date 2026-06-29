"""Log desensitization - strip sensitive data from logs before LLM processing.

Handles: phone numbers, API tokens, passwords, auth headers, emails, IP addresses.
"""

import re
from typing import Optional


# Pre-compiled patterns for performance
# Order matters: match structured tokens (JWT, API keys, auth headers) BEFORE
# generic patterns (phone, credit card) to avoid partial matches on token strings.
_PATTERNS = [
    # JWT tokens (must be before generic token/auth patterns)
    (re.compile(r'eyJ[a-zA-Z0-9_-]{10,}\.[a-zA-Z0-9_-]{10,}\.[a-zA-Z0-9_-]{10,}'), '[JWT_REDACTED]'),
    # sk- style API keys (DeepSeek, OpenAI, etc.) — before phone pattern
    (re.compile(r'sk-[a-zA-Z0-9]{20,}'), '[API_KEY_REDACTED]'),
    # Auth headers (before token key-value to avoid partial matches)
    (re.compile(r'(?i)(authorization|cookie|set-cookie)\s*[:=]\s*[^\s,;]+'), r'\1=[REDACTED]'),
    # API tokens / bearer tokens
    (re.compile(r'(?i)(bearer|api[_-]?key)\s*[:=]\s*[a-zA-Z0-9_\-\.]{8,}'), r'\1=[REDACTED]'),
    # Passwords in URLs or key-value
    (re.compile(r'(?i)(password|passwd|pwd|secret)\s*[:=]\s*\S+'), r'\1=[REDACTED]'),
    # Email addresses
    (re.compile(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}'), '[EMAIL_REDACTED]'),
    # Credit card numbers (basic pattern)
    (re.compile(r'\b\d{4}[-\s]?\d{4}[-\s]?\d{4}[-\s]?\d{4}\b'), '[CARD_REDACTED]'),
    # Phone numbers (international format) — after structured token patterns
    (re.compile(r'\+?\d{1,3}[-.\s]?\(?\d{3}\)?[-.\s]?\d{3,4}[-.\s]?\d{4}'), '[PHONE_REDACTED]'),
    # Internal IP addresses (private ranges)
    (re.compile(r'\b(?:10\.\d{1,3}\.\d{1,3}\.\d{1,3}|172\.(?:1[6-9]|2\d|3[01])\.\d{1,3}\.\d{1,3}|192\.168\.\d{1,3}\.\d{1,3})\b'), '[IP_REDACTED]'),
]


def desensitize(text: str) -> str:
    """Remove sensitive data from a log message.

    Replaces phone numbers, API keys, passwords, auth tokens, emails,
    JWTs, credit cards, and private IP addresses with redaction markers.
    """
    if not text:
        return text

    result = text
    for pattern, replacement in _PATTERNS:
        result = pattern.sub(replacement, result)
    return result


def desensitize_log_entry(log_entry: dict) -> dict:
    """Desensitize a single log entry dict.

    Processes 'message', 'trace_id', and any string values.
    Preserves structure and non-string fields.
    """
    sanitized = {}
    for key, value in log_entry.items():
        if isinstance(value, str):
            sanitized[key] = desensitize(value)
        else:
            sanitized[key] = value
    return sanitized


def desensitize_logs(logs: list[dict]) -> list[dict]:
    """Desensitize a list of log entries."""
    return [desensitize_log_entry(log) for log in logs]
