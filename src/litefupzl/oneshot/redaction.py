"""Redaction helpers for public litefupzl logs and artifacts."""

from __future__ import annotations

import re

COOKIE_PATTERN = re.compile(r"(?i)(_t=)([^;,\s]+)")
URL_PATTERN = re.compile(r"https?://[^\s]+")
USER_PATH_PATTERN = re.compile(r"/u/[A-Za-z0-9_\-]+")
TOPIC_PATH_PATTERN = re.compile(r"/t/[^/\s]+/\d+")
POST_ID_PATTERN = re.compile(r"\bpost\s+\d+\b", re.IGNORECASE)
TOPIC_ID_PATTERN = re.compile(r"\btopic\s+\d+\b", re.IGNORECASE)


def slot_alias(slot_index: int) -> str:
    """Return a stable public alias for a cookie slot."""
    return f"slot-{slot_index:03d}"


def mask_cookie(cookie: str) -> str:
    """Mask cookie values for internal debug use."""
    return COOKIE_PATTERN.sub(r"\1<redacted>", cookie)


def redact_text(value: str) -> str:
    """Redact common sensitive tokens from arbitrary text."""
    text = value or ""
    text = COOKIE_PATTERN.sub(r"\1<redacted>", text)
    text = URL_PATTERN.sub("<redacted-url>", text)
    text = USER_PATH_PATTERN.sub("/u/<redacted-user>", text)
    text = TOPIC_PATH_PATTERN.sub("/t/<redacted-topic>", text)
    text = POST_ID_PATTERN.sub("post <redacted>", text)
    text = TOPIC_ID_PATTERN.sub("topic <redacted>", text)
    return text
