from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest


def test_quota_math_per_slot():
    from litefupzl.actions.mutual_like import per_target_quota

    assert per_target_quota([]) == 0
    assert per_target_quota(["alice"]) == 25
    assert per_target_quota(["alice", "bob", "carol"]) == 8
    assert per_target_quota([f"user{i}" for i in range(26)]) == 0


def test_candidate_collection_merges_replies_and_topics_oldest_first(monkeypatch):
    from litefupzl.actions import mutual_like

    now = datetime(2026, 5, 28, tzinfo=timezone.utc)
    observed = []

    def fake_fetch(cookies, base_url, username, *, action_filter, offset, user_agent=None):
        observed.append((username, action_filter, offset, user_agent))
        if action_filter == mutual_like.USER_ACTION_FILTER_REPLIES:
            return [
                {
                    "post_id": 20,
                    "topic_id": 200,
                    "slug": "reply-topic",
                    "created_at": (now - timedelta(days=2)).isoformat(),
                },
                {
                    "post_id": 99,
                    "topic_id": 999,
                    "slug": "old-topic",
                    "created_at": (now - timedelta(days=31)).isoformat(),
                },
            ]
        if action_filter == mutual_like.USER_ACTION_FILTER_TOPICS:
            return [
                {
                    "post_id": 10,
                    "topic_id": 100,
                    "slug": "first-topic",
                    "created_at": (now - timedelta(days=5)).isoformat(),
                },
                {
                    "post_id": 20,
                    "topic_id": 200,
                    "slug": "reply-topic",
                    "created_at": (now - timedelta(days=2)).isoformat(),
                },
            ]
        raise AssertionError(action_filter)

    monkeypatch.setattr(mutual_like, "fetch_user_actions_via_http", fake_fetch)

    candidates = mutual_like.collect_candidates_for_target(
        [{"name": "_t", "value": "redacted"}],
        "https://linux.do",
        "alice",
        target_alias="target-001",
        now=now,
        user_agent="test-agent",
    )

    assert observed == [
        ("alice", mutual_like.USER_ACTION_FILTER_REPLIES, 0, "test-agent"),
        ("alice", mutual_like.USER_ACTION_FILTER_TOPICS, 0, "test-agent"),
    ]
    assert [(candidate.kind, candidate.post_id) for candidate in candidates] == [
        ("topic", 10),
        ("reply", 20),
    ]


def test_like_pass_skips_already_liked_and_likes_likeable_candidates(monkeypatch, tmp_path):
    from litefupzl.actions import mutual_like
    from litefupzl.oneshot.logging import PublicRecorder

    now = datetime(2026, 5, 28, tzinfo=timezone.utc)
    candidates = [
        mutual_like.MutualLikeCandidate(
            target_alias="target-001",
            candidate_alias="candidate-0001",
            kind="reply",
            created_at=now,
            post_id=1,
            topic_id=11,
            topic_slug="one",
        ),
        mutual_like.MutualLikeCandidate(
            target_alias="target-001",
            candidate_alias="candidate-0002",
            kind="reply",
            created_at=now,
            post_id=2,
            topic_id=22,
            topic_slug="two",
        ),
    ]

    monkeypatch.setattr(mutual_like, "collect_candidates_for_target", lambda *args, **kwargs: candidates)
    states = {
        1: mutual_like.PostLikeState(already_liked=True, likeable=False, status_code=200),
        2: mutual_like.PostLikeState(already_liked=False, likeable=True, status_code=200),
    }
    monkeypatch.setattr(mutual_like, "get_post_like_state_via_http", lambda *args, post_id, **kwargs: states[post_id])

    liked_posts = []

    def fake_like(*args, post_id, **kwargs):
        liked_posts.append(post_id)
        return mutual_like.PostActionResult(ok=True, already_acted=False, status_code=200)

    monkeypatch.setattr(mutual_like, "like_post_via_post_actions", fake_like)

    recorder = PublicRecorder(tmp_path)
    result = mutual_like.run_mutual_like_pass(
        [{"name": "_t", "value": "redacted"}],
        "https://linux.do",
        ["alice"],
        actor_username="reader",
        recorder=recorder,
        slot_alias="slot-001",
        user_agent="test-agent",
        now=now,
    )

    assert result.enabled is True
    assert result.liked_count == 1
    assert liked_posts == [2]
    assert result.artifacts[0]["skip_reason"] == "already_liked"
    assert result.artifacts[1]["phase"] == "post_actions"


def test_like_pass_stops_on_rate_limit_without_raising(monkeypatch, tmp_path):
    from litefupzl.actions import mutual_like
    from litefupzl.oneshot.logging import PublicRecorder

    now = datetime(2026, 5, 28, tzinfo=timezone.utc)
    candidates = [
        mutual_like.MutualLikeCandidate(
            target_alias="target-001",
            candidate_alias="candidate-0001",
            kind="reply",
            created_at=now,
            post_id=1,
            topic_id=11,
            topic_slug="one",
        ),
        mutual_like.MutualLikeCandidate(
            target_alias="target-001",
            candidate_alias="candidate-0002",
            kind="reply",
            created_at=now,
            post_id=2,
            topic_id=22,
            topic_slug="two",
        ),
    ]

    monkeypatch.setattr(mutual_like, "collect_candidates_for_target", lambda *args, **kwargs: candidates)
    monkeypatch.setattr(
        mutual_like,
        "get_post_like_state_via_http",
        lambda *args, **kwargs: mutual_like.PostLikeState(already_liked=False, likeable=True, status_code=200),
    )
    monkeypatch.setattr(
        mutual_like,
        "like_post_via_post_actions",
        lambda *args, **kwargs: mutual_like.PostActionResult(ok=False, already_acted=False, status_code=429, detail="rate limit"),
    )

    recorder = PublicRecorder(tmp_path)
    result = mutual_like.run_mutual_like_pass(
        [{"name": "_t", "value": "redacted"}],
        "https://linux.do",
        ["alice"],
        actor_username="reader",
        recorder=recorder,
        slot_alias="slot-001",
        user_agent="test-agent",
        now=now,
    )

    assert result.liked_count == 0
    assert result.stopped is True
    assert result.warning_code == "MUTUAL_LIKE_RATE_LIMITED"
    assert len(result.artifacts) == 1
    assert result.artifacts[0]["rate_limited"] is True


def test_like_pass_stops_when_candidate_fetch_is_rate_limited(monkeypatch, tmp_path):
    from litefupzl.actions import mutual_like
    from litefupzl.oneshot.logging import PublicRecorder

    def fake_collect(*args, **kwargs):
        raise RuntimeError("HTTP 429 for redacted")

    monkeypatch.setattr(mutual_like, "collect_candidates_for_target", fake_collect)

    recorder = PublicRecorder(tmp_path)
    result = mutual_like.run_mutual_like_pass(
        [{"name": "_t", "value": "redacted"}],
        "https://linux.do",
        ["alice"],
        actor_username="reader",
        recorder=recorder,
        slot_alias="slot-001",
        user_agent="test-agent",
    )

    assert result.stopped is True
    assert result.warning_code == "MUTUAL_LIKE_RATE_LIMITED"
    assert result.artifacts == [
        {
            "ts": result.artifacts[0]["ts"],
            "slot": "slot-001",
            "target_alias": "target-001",
            "candidate_alias": None,
            "kind": None,
            "phase": "user_actions",
            "status_code": 429,
            "skip_reason": "rate_limited",
            "already_liked": False,
            "rate_limited": True,
            "stopped": True,
        }
    ]


def test_like_pass_stops_when_candidate_fetch_hits_challenge(monkeypatch, tmp_path):
    from litefupzl.actions import mutual_like
    from litefupzl.oneshot.logging import PublicRecorder

    def fake_collect(*args, **kwargs):
        raise RuntimeError("Cloudflare challenge detected")

    monkeypatch.setattr(mutual_like, "collect_candidates_for_target", fake_collect)

    recorder = PublicRecorder(tmp_path)
    result = mutual_like.run_mutual_like_pass(
        [{"name": "_t", "value": "redacted"}],
        "https://linux.do",
        ["alice"],
        actor_username="reader",
        recorder=recorder,
        slot_alias="slot-001",
        user_agent="test-agent",
    )

    assert result.stopped is True
    assert result.warning_code == "MUTUAL_LIKE_WARNING"
    assert result.artifacts[0]["phase"] == "user_actions"
    assert result.artifacts[0]["skip_reason"] == "challenge"


def test_public_logs_and_artifacts_do_not_include_sensitive_targets(monkeypatch, tmp_path, capsys):
    from litefupzl.actions import mutual_like
    from litefupzl.oneshot.logging import PublicRecorder, configure_public_logger

    now = datetime(2026, 5, 28, tzinfo=timezone.utc)
    candidate = mutual_like.MutualLikeCandidate(
        target_alias="target-001",
        candidate_alias="candidate-0001",
        kind="topic",
        created_at=now,
        post_id=123456,
        topic_id=654321,
        topic_slug="sensitive-title",
    )

    monkeypatch.setattr(mutual_like, "collect_candidates_for_target", lambda *args, **kwargs: [candidate])
    monkeypatch.setattr(
        mutual_like,
        "get_post_like_state_via_http",
        lambda *args, **kwargs: mutual_like.PostLikeState(already_liked=False, likeable=True, status_code=200),
    )
    monkeypatch.setattr(
        mutual_like,
        "like_post_via_post_actions",
        lambda *args, **kwargs: mutual_like.PostActionResult(ok=True, already_acted=False, status_code=200),
    )

    recorder = PublicRecorder(tmp_path)
    with configure_public_logger():
        result = mutual_like.run_mutual_like_pass(
            [{"name": "_t", "value": "redacted"}],
            "https://linux.do",
            ["sensitive_user"],
            actor_username="reader",
            recorder=recorder,
            slot_alias="slot-001",
            user_agent="test-agent",
            now=now,
        )

    output = capsys.readouterr().err
    artifact_text = "\n".join(str(item) for item in result.artifacts)
    combined = output + artifact_text
    assert result.liked_count == 1
    assert "sensitive_user" not in combined
    assert "123456" not in combined
    assert "654321" not in combined
    assert "sensitive-title" not in combined
    assert "target-001" in artifact_text
    assert "candidate-0001" in artifact_text


def test_mutual_like_artifact_file_contains_only_redacted_aliases(tmp_path):
    from litefupzl.oneshot.logging import PublicRecorder
    from litefupzl.oneshot.models import RunResult, utc_now_iso

    recorder = PublicRecorder(tmp_path)
    recorder.record_mutual_like_artifact(
        {
            "slot": "slot-001",
            "target_alias": "target-001",
            "candidate_alias": "candidate-0001",
            "phase": "post_actions",
            "status_code": 200,
            "skip_reason": None,
            "already_liked": False,
            "rate_limited": False,
            "username": "sensitive_user",
            "post_id": 123456,
            "topic_id": 654321,
            "title": "sensitive-title",
        }
    )

    recorder.write_artifacts(RunResult(started_at=utc_now_iso()))

    artifact_text = (tmp_path / "mutual_like_artifacts.jsonl").read_text(encoding="utf-8")
    assert "target-001" in artifact_text
    assert "candidate-0001" in artifact_text
    assert "sensitive_user" not in artifact_text
    assert "123456" not in artifact_text
    assert "654321" not in artifact_text
    assert "sensitive-title" not in artifact_text
