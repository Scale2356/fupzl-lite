"""Environment schema for litefupzl oneshot mode."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator

from litefupzl.config.schema import FingerprintConfig
from litefupzl.config.defaults import FINGERPRINT_LOCALE, FINGERPRINT_TIMEZONE, FINGERPRINT_VIEWPORT


class OneShotEnvConfig(BaseModel):
    """Validated oneshot configuration loaded from environment variables."""

    site: Literal["linux.do"] = "linux.do"
    cookies: list[str] = Field(..., min_length=1)
    duration_minutes: int = Field(default=40, ge=1, le=240)
    headless: bool = True
    output_dir: str = "output/litefupzl"
    browser_name: Literal["camoufox", "chromium", "firefox", "patchright-chromium"] = "chromium"
    proxy_server: str | None = None
    virtual_display: bool = True
    cookie_refresh_enabled: bool = False
    mutual_like_users: list[str] = Field(default_factory=list)
    fingerprint: FingerprintConfig = Field(
        default_factory=lambda: FingerprintConfig(
            viewport=list(FINGERPRINT_VIEWPORT),
            timezone=FINGERPRINT_TIMEZONE,
            locale=FINGERPRINT_LOCALE,
        )
    )

    @field_validator("cookies")
    @classmethod
    def validate_non_empty_items(cls, values: list[str]) -> list[str]:
        cleaned = [value.strip() for value in values if value and value.strip()]
        if not cleaned:
            raise ValueError("list must contain at least one non-empty item")
        return cleaned

    @field_validator("mutual_like_users")
    @classmethod
    def validate_mutual_like_users(cls, values: list[str]) -> list[str]:
        cleaned: list[str] = []
        seen: set[str] = set()
        for value in values:
            username = str(value).strip()
            if not username:
                continue
            key = username.casefold()
            if key in seen:
                continue
            seen.add(key)
            cleaned.append(username)
        return cleaned
