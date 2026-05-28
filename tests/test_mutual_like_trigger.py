from __future__ import annotations

from types import SimpleNamespace

import pytest


def test_midpoint_trigger_helper_fires_only_after_halfway():
    from litefupzl.oneshot.session import _should_run_mutual_like_pass

    assert _should_run_mutual_like_pass(
        mutual_like_done=False,
        mutual_like_enabled=True,
        slot_start=100.0,
        duration_seconds=600.0,
        now=399.9,
    ) is False
    assert _should_run_mutual_like_pass(
        mutual_like_done=False,
        mutual_like_enabled=True,
        slot_start=100.0,
        duration_seconds=600.0,
        now=400.0,
    ) is True
    assert _should_run_mutual_like_pass(
        mutual_like_done=True,
        mutual_like_enabled=True,
        slot_start=100.0,
        duration_seconds=600.0,
        now=500.0,
    ) is False
    assert _should_run_mutual_like_pass(
        mutual_like_done=False,
        mutual_like_enabled=False,
        slot_start=100.0,
        duration_seconds=600.0,
        now=500.0,
    ) is False


@pytest.mark.asyncio
async def test_run_midpoint_mutual_like_pass_records_warning_without_breaking_read(monkeypatch, tmp_path):
    from litefupzl.oneshot import session
    from litefupzl.oneshot.logging import PublicRecorder
    from litefupzl.oneshot.models import SlotResult, utc_now_iso

    calls = []

    def fake_run_pass(*args, **kwargs):
        calls.append(kwargs)
        return session.MutualLikeResult(
            enabled=True,
            target_count=1,
            quota_per_target=25,
            liked_count=0,
            stopped=True,
            warning_code="MUTUAL_LIKE_RATE_LIMITED",
            artifacts=[{"target_alias": "target-001", "candidate_alias": "candidate-0001", "status_code": 429}],
        )

    monkeypatch.setattr(session, "run_mutual_like_pass", fake_run_pass)

    recorder = PublicRecorder(tmp_path)
    result = SlotResult(slot_index=1, slot_alias="slot-001", started_at=utc_now_iso())
    config = SimpleNamespace(mutual_like_users=["alice"])

    await session._run_midpoint_mutual_like_pass(
        slot_cookies=[{"name": "_t", "value": "redacted"}],
        config=config,
        result=result,
        recorder=recorder,
        slot_alias="slot-001",
        actor_username="reader",
        user_agent="test-agent",
    )

    assert calls
    assert result.mutual_like_enabled is True
    assert result.mutual_like_target_count == 1
    assert result.mutual_like_liked_count == 0
    assert "MUTUAL_LIKE_RATE_LIMITED" in result.warning_codes
    assert recorder.mutual_like_artifacts == [
        {"target_alias": "target-001", "candidate_alias": "candidate-0001", "status_code": 429}
    ]
    assert recorder.timeline[-2].step == "mutual-like-detail"
    assert recorder.timeline[-2].public is False
    assert recorder.timeline[-1].step == "mutual-like"
    assert recorder.timeline[-1].status == "warning"
