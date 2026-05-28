"""Top-level litefupzl oneshot orchestration."""

from __future__ import annotations

import asyncio
from typing import Awaitable, Callable

import click
from click.exceptions import Exit

from litefupzl.oneshot.env_loader import load_oneshot_env
from litefupzl.oneshot.logging import PublicRecorder, configure_public_logger, tally_run_result
from litefupzl.oneshot.models import RunResult, SlotConfig, SlotResult, SlotStatus, utc_now_iso
from litefupzl.oneshot.redaction import slot_alias
from litefupzl.oneshot.session import run_slot_session

SessionRunner = Callable[[SlotConfig, object, PublicRecorder], Awaitable[SlotResult]]


async def run_oneshot(*, session_runner: SessionRunner = run_slot_session) -> int:
    """Run the litefupzl oneshot flow and return process exit code."""
    config = load_oneshot_env()
    recorder = PublicRecorder(config.output_dir)
    run_result = RunResult(started_at=utc_now_iso())

    slots = [
        SlotConfig(
            slot_index=index,
            slot_alias=slot_alias(index),
            cookie=cookie,
            duration_minutes=config.duration_minutes,
        )
        for index, cookie in enumerate(config.cookies, start=1)
    ]

    with configure_public_logger():
        recorder.emit("system", "config", "loaded")
        for slot in slots:
            try:
                result = await session_runner(slot, config, recorder)
            except Exception:
                recorder.emit(slot.slot_alias, "slot", "failed", level="error", code="RUNTIME_ERROR")
                result = SlotResult(
                    slot_index=slot.slot_index,
                    slot_alias=slot.slot_alias,
                    started_at=utc_now_iso(),
                    finished_at=utc_now_iso(),
                    status=SlotStatus.RUNTIME_ERROR,
                    warning_codes=["RUNTIME_WARNING"],
                )
            run_result.slot_results.append(result)

        run_result.finished_at = utc_now_iso()
        tally_run_result(run_result)
        recorder.emit(
            "system",
            "artifacts",
            "written",
            code="oneshot_timeline.jsonl",
        )
        recorder.emit(
            "system",
            "summary",
            run_result.final_status,
            code="oneshot_summary.json",
        )
        timeline_path, summary_path = recorder.write_artifacts(run_result)

    if run_result.final_status == "success":
        return 0
    if run_result.final_status == "auth_failed":
        return 1
    return 2


def run_oneshot_sync() -> None:
    """CLI wrapper for oneshot mode."""
    try:
        raise Exit(asyncio.run(run_oneshot()))
    except Exit:
        raise
    except Exception:
        click.echo("litefupzl oneshot failed before execution", err=True)
        raise Exit(2)
