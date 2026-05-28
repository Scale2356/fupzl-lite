"""Public-safe logging and artifact writing for litefupzl."""

from __future__ import annotations

import json
import sys
from dataclasses import asdict
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from loguru import logger

from litefupzl.oneshot.models import RunResult, SlotEvent, utc_now_iso
from litefupzl.oneshot.redaction import redact_text


def _public_sink(message):
    record = message.record
    extra = record.get("extra", {})
    if not extra.get("oneshot_public"):
        return
    print(message, end="", file=sys.stderr)


@contextmanager
def configure_public_logger() -> Iterator[None]:
    """Configure loguru so only public/redacted records reach stderr."""
    # Loguru installs a default stderr handler at import time. Remove any
    # pre-existing handlers before adding the public sink, otherwise each
    # recorder event is printed once by the default handler and once by our
    # public formatter.
    logger.remove()
    handler_id = logger.add(_public_sink, level="INFO", format="{time:YYYY-MM-DDTHH:mm:ssZ} | {level} | {message}")
    try:
        yield
    finally:
        try:
            logger.remove(handler_id)
        except ValueError:
            pass


class PublicRecorder:
    """Collect safe timeline events and write public artifacts."""

    def __init__(self, output_dir: str | Path):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.timeline: list[SlotEvent] = []
        self.mutual_like_artifacts: list[dict] = []

    def emit(
        self,
        slot: str,
        step: str,
        status: str,
        *,
        level: str = "info",
        code: str | None = None,
        browser_core: str | None = None,
        url_category: str | None = None,
        status_code: int | None = None,
        public: bool = True,
    ) -> None:
        """Emit a redacted event to the timeline, and optionally to stderr."""
        event = SlotEvent(
            ts=utc_now_iso(),
            slot=slot,
            level=level,
            step=step,
            status=status,
            code=code,
            browser_core=browser_core,
            url_category=url_category,
            status_code=status_code,
            public=public,
        )
        self.timeline.append(event)
        if not public:
            return
        parts = [slot, step, status]
        if browser_core:
            parts.append(f"browser={browser_core}")
        if url_category:
            parts.append(f"url_category={url_category}")
        if status_code is not None:
            parts.append(f"status_code={status_code}")
        if code:
            parts.append(code)
        safe_logger = logger.bind(
            oneshot_public=True,
            slot=slot,
            step=step,
            status=status,
            code=code,
            browser_core=browser_core,
            url_category=url_category,
            status_code=status_code,
        )
        getattr(safe_logger, level)(redact_text(" ".join(parts).strip()))

    def record_mutual_like_artifact(self, event: dict) -> None:
        """Record a redacted per-candidate mutual-like debug event."""
        allowed = {
            "ts",
            "slot",
            "target_alias",
            "candidate_alias",
            "kind",
            "phase",
            "status_code",
            "skip_reason",
            "already_liked",
            "rate_limited",
            "stopped",
        }
        safe_event = {key: value for key, value in event.items() if key in allowed}
        self.mutual_like_artifacts.append(safe_event)

    def write_artifacts(self, run_result: RunResult) -> tuple[Path, Path]:
        """Write public timeline and summary artifacts."""
        timeline_path = self.output_dir / "oneshot_timeline.jsonl"
        summary_path = self.output_dir / "oneshot_summary.json"
        mutual_like_path = self.output_dir / "mutual_like_artifacts.jsonl"

        timeline_path.write_text(
            "\n".join(json.dumps(asdict(event), ensure_ascii=False) for event in self.timeline) + ("\n" if self.timeline else ""),
            encoding="utf-8",
        )
        summary_path.write_text(
            json.dumps(run_result.to_summary_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        mutual_like_path.write_text(
            "\n".join(json.dumps(event, ensure_ascii=False) for event in self.mutual_like_artifacts)
            + ("\n" if self.mutual_like_artifacts else ""),
            encoding="utf-8",
        )
        return timeline_path, summary_path


def tally_run_result(run_result: RunResult) -> None:
    """Populate aggregate counters and final status from slot results."""
    run_result.total_slots = len(run_result.slot_results)
    for slot in run_result.slot_results:
        if slot.status == "success":
            run_result.success_slots += 1
        elif slot.status == "warning":
            run_result.warning_slots += 1
        elif slot.status == "cf_blocked":
            run_result.cf_blocked_slots += 1
        elif slot.status == "cookie_invalid":
            run_result.cookie_invalid_slots += 1
        elif slot.status == "account_blocked":
            run_result.account_blocked_slots += 1
        else:
            run_result.runtime_error_slots += 1

    if run_result.success_slots > 0 or run_result.warning_slots > 0:
        run_result.final_status = "success"
    elif run_result.cf_blocked_slots > 0:
        run_result.final_status = "cf_blocked"
    elif run_result.cookie_invalid_slots + run_result.account_blocked_slots == run_result.total_slots:
        run_result.final_status = "auth_failed"
    else:
        run_result.final_status = "runtime_error"
