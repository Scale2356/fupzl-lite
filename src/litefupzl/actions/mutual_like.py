"""Opt-in mutual-like support for configured target users.

Public logs and returned artifact events use aliases only. Raw usernames,
post ids, topic ids, slugs, titles, and URLs are intentionally not included in
artifacts produced by this module.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from litefupzl.discourse.http_bypass import (
    PostActionResult,
    fetch_user_actions_via_http,
    get_topic_detail_via_http,
    like_post_via_post_actions,
)
from litefupzl.oneshot.models import utc_now_iso

USER_ACTION_FILTER_TOPICS = "4"
USER_ACTION_FILTER_REPLIES = "5"
MAX_LIKES_PER_SLOT = 25
LOOKBACK_DAYS = 30
_PAGE_SIZE = 30
_MAX_USER_ACTION_PAGES = 20
_BLOCKING_STATUS_CODES = {403, 429}


@dataclass(frozen=True)
class MutualLikeCandidate:
    target_alias: str
    candidate_alias: str
    kind: str
    created_at: datetime
    post_id: int | None
    topic_id: int
    topic_slug: str


@dataclass(frozen=True)
class PostLikeState:
    already_liked: bool
    likeable: bool
    status_code: int
    resolved_post_id: int | None = None
    rate_limited: bool = False
    challenge_blocked: bool = False


@dataclass
class MutualLikeResult:
    enabled: bool
    target_count: int = 0
    quota_per_target: int = 0
    liked_count: int = 0
    stopped: bool = False
    warning_code: str | None = None
    artifacts: list[dict] = field(default_factory=list)


def per_target_quota(usernames: list[str]) -> int:
    """Return the per-target like quota for one slot."""
    count = len(usernames)
    if count <= 0:
        return 0
    return MAX_LIKES_PER_SLOT // count


def collect_candidates_for_target(
    cookies: list[dict],
    base_url: str,
    username: str,
    *,
    target_alias: str,
    now: datetime | None = None,
    user_agent: str | None = None,
) -> list[MutualLikeCandidate]:
    """Fetch recent replies and topic first-post candidates for one target."""
    reference_now = _as_utc(now or datetime.now(timezone.utc))
    cutoff = reference_now - timedelta(days=LOOKBACK_DAYS)
    candidates: list[MutualLikeCandidate] = []
    seen_posts: set[int] = set()
    seen_topic_first_posts: set[int] = set()

    for action_filter, kind in (
        (USER_ACTION_FILTER_REPLIES, "reply"),
        (USER_ACTION_FILTER_TOPICS, "topic"),
    ):
        offset = 0
        for _page in range(_MAX_USER_ACTION_PAGES):
            actions = fetch_user_actions_via_http(
                cookies,
                base_url,
                username,
                action_filter=action_filter,
                offset=offset,
                user_agent=user_agent,
            )
            if not actions:
                break

            oldest_seen: datetime | None = None
            for action in actions:
                created_at = _parse_action_datetime(action.get("created_at"))
                if created_at is None:
                    continue
                oldest_seen = created_at if oldest_seen is None else min(oldest_seen, created_at)
                if created_at < cutoff:
                    continue

                topic_id = _safe_int(action.get("topic_id"))
                if topic_id is None:
                    continue
                post_id = _safe_int(action.get("post_id"))
                if kind == "reply" and post_id is not None:
                    if post_id in seen_posts:
                        continue
                    seen_posts.add(post_id)
                if kind == "topic":
                    # Some Discourse payloads omit post_id for topic actions.
                    # Deduplicate topic first-posts by topic id in that case.
                    dedupe_key = post_id if post_id is not None else topic_id
                    if dedupe_key in seen_topic_first_posts:
                        continue
                    seen_topic_first_posts.add(dedupe_key)
                    if post_id is not None and post_id in seen_posts:
                        continue
                    if post_id is not None:
                        seen_posts.add(post_id)

                candidates.append(
                    MutualLikeCandidate(
                        target_alias=target_alias,
                        candidate_alias="",
                        kind=kind,
                        created_at=created_at,
                        post_id=post_id,
                        topic_id=topic_id,
                        topic_slug=str(action.get("slug") or "topic"),
                    )
                )

            if len(actions) < _PAGE_SIZE or (oldest_seen is not None and oldest_seen < cutoff):
                break
            offset += _PAGE_SIZE

    candidates.sort(key=lambda item: item.created_at)
    return [
        MutualLikeCandidate(
            target_alias=candidate.target_alias,
            candidate_alias=f"candidate-{index:04d}",
            kind=candidate.kind,
            created_at=candidate.created_at,
            post_id=candidate.post_id,
            topic_id=candidate.topic_id,
            topic_slug=candidate.topic_slug,
        )
        for index, candidate in enumerate(candidates, start=1)
    ]


def get_post_like_state_via_http(
    cookies: list[dict],
    base_url: str,
    *,
    topic_id: int,
    topic_slug: str,
    post_id: int | None,
    kind: str,
    actor_username: str | None = None,
    user_agent: str | None = None,
) -> PostLikeState:
    """Inspect topic detail and return whether a candidate post is likeable."""
    try:
        data = get_topic_detail_via_http(cookies, base_url, topic_id, slug=topic_slug, user_agent=user_agent)
    except Exception as exc:
        status = _status_from_exception(exc)
        is_challenge = _is_challenge_exception(exc)
        return PostLikeState(
            already_liked=False,
            likeable=False,
            status_code=status,
            resolved_post_id=post_id,
            rate_limited=status == 429,
            challenge_blocked=is_challenge,
        )

    posts = data.get("post_stream", {}).get("posts", [])
    if not isinstance(posts, list):
        return PostLikeState(already_liked=False, likeable=False, status_code=200, resolved_post_id=post_id)

    target_post = _find_target_post(posts, post_id=post_id, kind=kind)
    if not target_post:
        return PostLikeState(already_liked=False, likeable=False, status_code=200, resolved_post_id=post_id)

    resolved_post_id = _safe_int(target_post.get("id")) or post_id
    author = str(target_post.get("username") or "")
    if actor_username and author and author.casefold() == actor_username.casefold():
        return PostLikeState(already_liked=False, likeable=False, status_code=200, resolved_post_id=resolved_post_id)

    for action in target_post.get("actions_summary", []) or []:
        if action.get("id") != 2:
            continue
        return PostLikeState(
            already_liked=bool(action.get("acted")),
            likeable=bool(action.get("can_act")) and not bool(action.get("acted")),
            status_code=200,
            resolved_post_id=resolved_post_id,
        )
    return PostLikeState(already_liked=False, likeable=False, status_code=200, resolved_post_id=resolved_post_id)


def run_mutual_like_pass(
    cookies: list[dict],
    base_url: str,
    target_usernames: list[str],
    *,
    actor_username: str | None,
    recorder=None,
    slot_alias: str,
    user_agent: str | None = None,
    now: datetime | None = None,
) -> MutualLikeResult:
    """Run one bounded mutual-like pass for a single slot."""
    usernames = _normalize_usernames(target_usernames)
    quota = per_target_quota(usernames)
    if not usernames or quota <= 0:
        return MutualLikeResult(enabled=bool(usernames), target_count=len(usernames), quota_per_target=quota)

    reference_now = _as_utc(now or datetime.now(timezone.utc))
    result = MutualLikeResult(enabled=True, target_count=len(usernames), quota_per_target=quota)

    for target_index, username in enumerate(usernames, start=1):
        if actor_username and username.casefold() == actor_username.casefold():
            continue

        liked_for_target = 0
        target_alias = f"target-{target_index:03d}"
        try:
            candidates = collect_candidates_for_target(
                cookies,
                base_url,
                username,
                target_alias=target_alias,
                now=reference_now,
                user_agent=user_agent,
            )
        except Exception as exc:
            status = _status_from_exception(exc)
            is_challenge = _is_challenge_exception(exc)
            artifact = {
                "ts": utc_now_iso(),
                "slot": slot_alias,
                "target_alias": target_alias,
                "candidate_alias": None,
                "kind": None,
                "phase": "user_actions",
                "status_code": status,
                "skip_reason": "challenge" if is_challenge else "rate_limited" if status == 429 else "blocked" if status == 403 else "fetch_failed",
                "already_liked": False,
                "rate_limited": status == 429,
            }
            if status in _BLOCKING_STATUS_CODES or is_challenge:
                artifact["stopped"] = True
                result.artifacts.append(artifact)
                result.stopped = True
                result.warning_code = "MUTUAL_LIKE_RATE_LIMITED" if status == 429 else "MUTUAL_LIKE_WARNING"
                return result
            result.artifacts.append(artifact)
            result.warning_code = result.warning_code or "MUTUAL_LIKE_WARNING"
            continue

        for candidate in candidates:
            if liked_for_target >= quota or result.liked_count >= MAX_LIKES_PER_SLOT:
                break

            artifact = _base_artifact(slot_alias, candidate)
            state = get_post_like_state_via_http(
                cookies,
                base_url,
                topic_id=candidate.topic_id,
                topic_slug=candidate.topic_slug,
                post_id=candidate.post_id,
                kind=candidate.kind,
                actor_username=actor_username,
                user_agent=user_agent,
            )
            artifact.update(
                {
                    "phase": "topic_detail",
                    "status_code": state.status_code,
                    "already_liked": state.already_liked,
                    "rate_limited": state.rate_limited,
                }
            )
            post_id = state.resolved_post_id or candidate.post_id

            if state.status_code in _BLOCKING_STATUS_CODES or state.rate_limited or state.challenge_blocked:
                artifact["skip_reason"] = "challenge" if state.challenge_blocked else "rate_limited" if state.status_code == 429 or state.rate_limited else "blocked"
                artifact["stopped"] = True
                result.artifacts.append(artifact)
                result.stopped = True
                result.warning_code = "MUTUAL_LIKE_RATE_LIMITED" if artifact["skip_reason"] == "rate_limited" else "MUTUAL_LIKE_WARNING"
                return result
            if state.already_liked:
                artifact["skip_reason"] = "already_liked"
                result.artifacts.append(artifact)
                continue
            if not state.likeable or post_id is None:
                artifact["skip_reason"] = "not_likeable"
                result.artifacts.append(artifact)
                continue

            topic_url = f"{base_url}/t/{candidate.topic_slug}/{candidate.topic_id}"
            action_result = like_post_via_post_actions(
                cookies,
                post_id=post_id,
                topic_url=topic_url,
                user_agent=user_agent,
            )
            artifact.update(
                {
                    "phase": "post_actions",
                    "status_code": action_result.status_code,
                    "already_liked": action_result.already_acted,
                    "rate_limited": action_result.status_code == 429,
                }
            )
            if action_result.ok:
                if action_result.already_acted:
                    artifact["skip_reason"] = "already_liked"
                else:
                    liked_for_target += 1
                    result.liked_count += 1
                result.artifacts.append(artifact)
                continue

            if action_result.status_code in _BLOCKING_STATUS_CODES:
                artifact["skip_reason"] = "rate_limited" if action_result.status_code == 429 else "blocked"
                artifact["stopped"] = True
                result.artifacts.append(artifact)
                result.stopped = True
                result.warning_code = "MUTUAL_LIKE_RATE_LIMITED" if action_result.status_code == 429 else "MUTUAL_LIKE_WARNING"
                return result

            artifact["skip_reason"] = "post_action_failed"
            result.artifacts.append(artifact)

    return result


def _normalize_usernames(values: list[str]) -> list[str]:
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


def _base_artifact(slot_alias: str, candidate: MutualLikeCandidate) -> dict:
    return {
        "ts": utc_now_iso(),
        "slot": slot_alias,
        "target_alias": candidate.target_alias,
        "candidate_alias": candidate.candidate_alias,
        "kind": candidate.kind,
        "phase": "candidate",
        "status_code": None,
        "skip_reason": None,
        "already_liked": False,
        "rate_limited": False,
    }


def _find_target_post(posts: list[dict], *, post_id: int | None, kind: str) -> dict | None:
    if post_id is not None:
        for post in posts:
            if _safe_int(post.get("id")) == post_id:
                return post
    if kind == "topic" and posts:
        return posts[0]
    return None


def _parse_action_datetime(value) -> datetime | None:
    if not value:
        return None
    try:
        return _as_utc(datetime.fromisoformat(str(value).replace("Z", "+00:00")))
    except ValueError:
        return None


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _safe_int(value) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _status_from_exception(exc: Exception) -> int:
    match = re.search(r"HTTP\s+(\d{3})", str(exc))
    if not match:
        return 0
    return int(match.group(1))


def _is_challenge_exception(exc: Exception) -> bool:
    lowered = str(exc).lower()
    return (
        "cloudflare" in lowered
        or "cf-challenge" in lowered
        or "cf-turnstile" in lowered
        or "just a moment" in lowered
    )
