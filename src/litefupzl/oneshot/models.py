"""Runtime models for litefupzl oneshot mode."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import StrEnum


class SlotStatus(StrEnum):
    SUCCESS = "success"
    WARNING = "warning"
    CF_BLOCKED = "cf_blocked"
    COOKIE_INVALID = "cookie_invalid"
    ACCOUNT_BLOCKED = "account_blocked"
    RUNTIME_ERROR = "runtime_error"


class WarningCode(StrEnum):
    CF_BLOCKED = "CF_BLOCKED"
    READ_FAILED = "READ_FAILED"
    USER_INFO_UNAVAILABLE = "USER_INFO_UNAVAILABLE"
    TOPIC_FETCH_FAILED = "TOPIC_FETCH_FAILED"
    COOKIE_REFRESH_FAILED = "COOKIE_REFRESH_FAILED"
    LOGIN_DEVICE_PROOF_INCONCLUSIVE = "LOGIN_DEVICE_PROOF_INCONCLUSIVE"
    MUTUAL_LIKE_WARNING = "MUTUAL_LIKE_WARNING"
    MUTUAL_LIKE_RATE_LIMITED = "MUTUAL_LIKE_RATE_LIMITED"
    RUNTIME_WARNING = "RUNTIME_WARNING"


@dataclass(slots=True)
class SlotConfig:
    slot_index: int
    slot_alias: str
    cookie: str
    duration_minutes: int


@dataclass(slots=True)
class SlotEvent:
    ts: str
    slot: str
    level: str
    step: str
    status: str
    code: str | None = None
    browser_core: str | None = None
    url_category: str | None = None
    status_code: int | None = None
    public: bool = True


@dataclass(slots=True)
class SlotResult:
    slot_index: int
    slot_alias: str
    started_at: str
    finished_at: str | None = None
    status: SlotStatus = SlotStatus.RUNTIME_ERROR
    login_ok: bool = False
    username_observed: bool = False
    security_preferences_ok: bool = False
    security_device_ok: bool = False
    active_linux_device_ok: bool = False
    same_context_login_proof_ok: bool = False
    browser_user_agent_linux_like: bool = False
    browser_user_agent_windows_like: bool = False
    read_ok: bool = False
    read_same_context_ok: bool = False
    mutual_like_enabled: bool = False
    mutual_like_target_count: int = 0
    mutual_like_liked_count: int = 0
    cookie_refresh_ok: bool = False
    cf_seen: bool = False
    warning_codes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(slots=True)
class RunResult:
    started_at: str
    finished_at: str | None = None
    total_slots: int = 0
    success_slots: int = 0
    warning_slots: int = 0
    cf_blocked_slots: int = 0
    cookie_invalid_slots: int = 0
    account_blocked_slots: int = 0
    runtime_error_slots: int = 0
    final_status: str = "runtime_error"
    slot_results: list[SlotResult] = field(default_factory=list)

    def to_summary_dict(self) -> dict:
        return {
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "total_slots": self.total_slots,
            "success_slots": self.success_slots,
            "warning_slots": self.warning_slots,
            "cf_blocked_slots": self.cf_blocked_slots,
            "cookie_invalid_slots": self.cookie_invalid_slots,
            "account_blocked_slots": self.account_blocked_slots,
            "runtime_error_slots": self.runtime_error_slots,
            "final_status": self.final_status,
            "slots": [slot.to_dict() for slot in self.slot_results],
        }


def utc_now_iso() -> str:
    """Return current UTC time in ISO-8601 seconds precision."""
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()
