from types import SimpleNamespace

import pytest

from litefupzl.oneshot.models import SlotConfig, SlotStatus, WarningCode


class Recorder:
    def __init__(self):
        self.events = []

    def emit(self, slot, step, status, **kwargs):
        self.events.append({"slot": slot, "step": step, "status": status, **kwargs})


class AsyncClosable:
    async def close(self):
        return None

    async def stop(self):
        return None


@pytest.mark.asyncio
async def test_missing_linux_device_is_warning_not_cookie_invalid(monkeypatch):
    from litefupzl.oneshot import session

    async def fake_create_browser_context(*, temp_profile, config):
        return AsyncClosable(), AsyncClosable(), object(), AsyncClosable()

    async def fake_get_browser_user_agent(_page):
        return "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/148.0.0.0 Safari/537.36"

    async def fake_ensure_logged_in(*args, **kwargs):
        return "ok"

    async def fake_extract_username(_page):
        return "redacted-user"

    async def fake_probe_security(_page, _username):
        return "ok"

    async def fake_probe_device(_page, _username):
        return "unknown"

    async def fake_build_topic_queue(*args, **kwargs):
        return []

    monkeypatch.setattr(session, "_create_browser_context", fake_create_browser_context)
    monkeypatch.setattr(session, "attach_topics_timing_observer", lambda *args, **kwargs: None)
    monkeypatch.setattr(session, "_get_browser_user_agent", fake_get_browser_user_agent)
    monkeypatch.setattr(session, "_ensure_logged_in", fake_ensure_logged_in)
    monkeypatch.setattr(session, "_extract_username", fake_extract_username)
    monkeypatch.setattr(session, "_probe_security_preferences_via_browser", fake_probe_security)
    monkeypatch.setattr(session, "_probe_security_preferences_device_list_via_browser", fake_probe_device)
    monkeypatch.setattr(session, "get_user_info_via_http", lambda *args, **kwargs: SimpleNamespace(suspended_till=None, silenced_till=None))
    monkeypatch.setattr(session, "_build_topic_queue", fake_build_topic_queue)

    config = SimpleNamespace(browser_name="chromium", cookie_refresh_enabled=False)
    slot = SlotConfig(slot_index=1, slot_alias="slot-001", cookie="_t=redacted", duration_minutes=1)
    recorder = Recorder()

    result = await session.run_slot_session(slot, config, recorder)

    assert result.status is SlotStatus.WARNING
    assert result.login_ok is True
    assert result.security_preferences_ok is True
    assert result.active_linux_device_ok is False
    assert WarningCode.LOGIN_DEVICE_PROOF_INCONCLUSIVE.value in result.warning_codes
    assert not any(event.get("code") == "COOKIE_INVALID" for event in recorder.events)
    assert any(
        event["step"] == "login-check"
        and event["status"] == "warning"
        and event.get("code") == WarningCode.LOGIN_DEVICE_PROOF_INCONCLUSIVE.value
        for event in recorder.events
    )


def test_auth_probe_success_does_not_require_active_linux_device():
    from apps.litefupzl.auth_probe import _is_auth_probe_success

    browser_probe = {
        "username_probe": {"present": True},
        "security_preferences_state": "ok",
        "security_preferences_fetch": {
            "status_code": 200,
            "security_preferences_path": True,
            "username_path_ok": True,
            "login_path_like": False,
            "logged_out_like": False,
            "cf_like": False,
        },
        "security_device_state": "unknown",
        "security_device_probe": {
            "auth_tokens_section_present": True,
            "device_row_count": 2,
            "linux_row_count": 1,
            "linux_active_like_count": 0,
            "logged_out_like": False,
            "cf_like": False,
        },
    }

    assert _is_auth_probe_success(browser_probe) is True


@pytest.mark.asyncio
async def test_login_proof_accepts_security_page_when_device_proof_is_inconclusive(monkeypatch):
    from litefupzl.oneshot import session

    async def fake_extract_username(_page):
        return "redacted-user"

    async def fake_probe_security(_page, _username):
        return "ok"

    async def fake_probe_device(_page, _username):
        return "unknown"

    monkeypatch.setattr(session, "_extract_username", fake_extract_username)
    monkeypatch.setattr(session, "_probe_security_preferences_via_browser", fake_probe_security)
    monkeypatch.setattr(session, "_probe_security_preferences_device_list_via_browser", fake_probe_device)

    state = await session._require_authenticated_login_proof(object(), [{"name": "_t", "value": "redacted"}], "ok")

    assert state == "ok"
