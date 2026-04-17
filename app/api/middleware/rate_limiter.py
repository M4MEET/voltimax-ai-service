from __future__ import annotations

import logging
import time
from collections import defaultdict

from app.config import get_config

logger = logging.getLogger(__name__)

MAX_MESSAGE_CHARS = 5000
WARN_MESSAGE_CHARS = 2000
RAPID_FIRE_COUNT = 10
RAPID_FIRE_WINDOW = 30.0
SESSION_FLOOD_LIMIT = 5
SESSION_FLOOD_WINDOW = 3600.0


class AbuseError(Exception):
    """Raised when a request is blocked for abuse."""


class RateLimiter:
    """In-memory rate limiter + abuse detector for Server B."""

    def __init__(self):
        self._message_counts: dict[str, list[float]] = defaultdict(list)
        self._session_counts: dict[str, int] = defaultdict(int)
        self._customer_session_times: dict[str, list[float]] = defaultdict(list)
        self._daily_tokens: int = 0
        self._daily_reset: float = time.time()

    def check_message_rate(self, session_id: str) -> bool:
        """Return True if allowed, False if per-minute limit exceeded."""
        config = get_config()
        now = time.time()
        window = 60.0
        self._message_counts[session_id] = [
            t for t in self._message_counts[session_id] if now - t < window
        ]
        if len(self._message_counts[session_id]) >= config.rate_limiting.max_messages_per_minute:
            return False
        self._message_counts[session_id].append(now)
        return True

    def check_session_limit(self, session_id: str) -> bool:
        """Return True if session hasn't exceeded max messages per session."""
        config = get_config()
        return self._session_counts.get(session_id, 0) < config.rate_limiting.max_messages_per_session

    def increment_session(self, session_id: str) -> None:
        self._session_counts[session_id] = self._session_counts.get(session_id, 0) + 1

    def add_tokens(self, count: int) -> bool:
        """Add tokens to daily count. Returns False if cap exceeded."""
        config = get_config()
        now = time.time()
        if now - self._daily_reset >= 86400:
            self._daily_tokens = 0
            self._daily_reset = now
        cap = config.rate_limiting.daily_token_cap
        if cap > 0 and self._daily_tokens + count > cap:
            return False
        self._daily_tokens += count
        return True

    def get_daily_token_usage(self) -> int:
        return self._daily_tokens

    def check_message_content(self, message: str) -> str:
        """
        Validate message content. Returns the message if OK.
        Raises AbuseError if message should be rejected.
        """
        length = len(message)
        if length > MAX_MESSAGE_CHARS:
            raise AbuseError(
                f"Message too long ({length} chars). Maximum allowed: {MAX_MESSAGE_CHARS}."
            )
        if length > WARN_MESSAGE_CHARS:
            logger.warning("Long message detected: %d chars", length)

        lower = message.lower()
        injection_patterns = [
            "ignore previous instructions",
            "ignore all instructions",
            "disregard your instructions",
            "pretend you are",
            "system prompt:",
            "###instruction",
        ]
        for pattern in injection_patterns:
            if pattern in lower:
                logger.warning("Potential prompt injection blocked: %r", pattern)
                raise AbuseError("Message contains disallowed content.")

        return message

    def check_rapid_fire(self, session_id: str) -> bool:
        """Return True if OK, False if sending too fast."""
        now = time.time()
        recent = [
            t for t in self._message_counts.get(session_id, [])
            if now - t < RAPID_FIRE_WINDOW
        ]
        return len(recent) < RAPID_FIRE_COUNT

    def check_session_flooding(self, customer_email: str) -> bool:
        """Return True if OK, False if customer is opening too many sessions."""
        now = time.time()
        self._customer_session_times[customer_email] = [
            t for t in self._customer_session_times[customer_email]
            if now - t < SESSION_FLOOD_WINDOW
        ]
        return len(self._customer_session_times[customer_email]) < SESSION_FLOOD_LIMIT

    def record_new_session(self, customer_email: str) -> None:
        self._customer_session_times[customer_email].append(time.time())


_rate_limiter: RateLimiter | None = None


def get_rate_limiter() -> RateLimiter:
    global _rate_limiter
    if _rate_limiter is None:
        _rate_limiter = RateLimiter()
    return _rate_limiter
