import json

import pytest


def test_env_loader_requires_only_cookie_and_no_like_lottery(monkeypatch):
    from litefupzl.oneshot.env_loader import load_oneshot_env

    monkeypatch.setenv("LITEFUPZL_COOKIES_JSON", json.dumps(["_t=redacted"]))
    monkeypatch.delenv("FUCKPZL_ONESHOT_LOTTERY_TEXTS_JSON", raising=False)
    monkeypatch.delenv("FUCKPZL_ONESHOT_LOTTERY_EMOJIS_JSON", raising=False)
    monkeypatch.delenv("FUCKPZL_ONESHOT_LIKE_ENABLED", raising=False)
    monkeypatch.delenv("FUCKPZL_ONESHOT_LOTTERY_ENABLED", raising=False)

    config = load_oneshot_env()

    assert config.cookies == ["_t=redacted"]
    assert config.duration_minutes == 40
    assert config.cookie_refresh_enabled is True
    assert not hasattr(config, "like_enabled")
    assert not hasattr(config, "lottery_enabled")
    assert not hasattr(config, "lottery_texts")
    assert not hasattr(config, "lottery_emojis")


def test_scheduled_cookie_refresh_can_opt_in_via_same_env(monkeypatch):
    from litefupzl.oneshot.env_loader import load_oneshot_env

    monkeypatch.setenv("LITEFUPZL_COOKIES_JSON", json.dumps(["_t=redacted"]))
    monkeypatch.setenv("LITEFUPZL_COOKIE_REFRESH_ENABLED", "true")
    monkeypatch.setenv("GITHUB_EVENT_NAME", "schedule")

    config = load_oneshot_env()

    assert config.cookie_refresh_enabled is True


def test_manual_cookie_refresh_can_opt_in(monkeypatch):
    from litefupzl.oneshot.env_loader import load_oneshot_env

    monkeypatch.setenv("LITEFUPZL_COOKIES_JSON", json.dumps(["_t=redacted"]))
    monkeypatch.setenv("LITEFUPZL_COOKIE_REFRESH_ENABLED", "true")
    monkeypatch.setenv("GITHUB_EVENT_NAME", "workflow_dispatch")

    config = load_oneshot_env()

    assert config.cookie_refresh_enabled is True


def test_cookie_refresh_default_is_enabled_for_schedule(monkeypatch):
    from litefupzl.oneshot.env_loader import load_oneshot_env

    monkeypatch.setenv("LITEFUPZL_COOKIES_JSON", json.dumps(["_t=redacted"]))
    monkeypatch.delenv("LITEFUPZL_COOKIE_REFRESH_ENABLED", raising=False)
    monkeypatch.delenv("FUCKPZL_ONESHOT_COOKIE_REFRESH_ENABLED", raising=False)
    monkeypatch.setenv("GITHUB_EVENT_NAME", "schedule")

    config = load_oneshot_env()

    assert config.cookie_refresh_enabled is True


def test_cookie_refresh_can_still_be_disabled_explicitly(monkeypatch):
    from litefupzl.oneshot.env_loader import load_oneshot_env

    monkeypatch.setenv("LITEFUPZL_COOKIES_JSON", json.dumps(["_t=redacted"]))
    monkeypatch.setenv("LITEFUPZL_COOKIE_REFRESH_ENABLED", "false")
    monkeypatch.setenv("GITHUB_EVENT_NAME", "schedule")

    config = load_oneshot_env()

    assert config.cookie_refresh_enabled is False


def test_legacy_cookie_env_alias_is_still_supported(monkeypatch):
    from litefupzl.oneshot.env_loader import load_oneshot_env

    monkeypatch.delenv("LITEFUPZL_COOKIES_JSON", raising=False)
    monkeypatch.setenv("FUCKPZL_ONESHOT_COOKIES_JSON", json.dumps(["_t=legacy-redacted"]))

    config = load_oneshot_env()

    assert config.cookies == ["_t=legacy-redacted"]


def test_mutual_like_users_default_to_empty_when_unset(monkeypatch):
    from litefupzl.oneshot.env_loader import load_oneshot_env

    monkeypatch.setenv("LITEFUPZL_COOKIES_JSON", json.dumps(["_t=redacted"]))
    monkeypatch.delenv("LITEFUPZL_MUTUAL_LIKE_USERS_JSON", raising=False)

    config = load_oneshot_env()

    assert config.mutual_like_users == []


def test_mutual_like_users_are_deduped_and_blank_values_removed(monkeypatch):
    from litefupzl.oneshot.env_loader import load_oneshot_env

    monkeypatch.setenv("LITEFUPZL_COOKIES_JSON", json.dumps(["_t=redacted"]))
    monkeypatch.setenv("LITEFUPZL_MUTUAL_LIKE_USERS_JSON", json.dumps([" alice ", "", "bob", "alice"]))

    config = load_oneshot_env()

    assert config.mutual_like_users == ["alice", "bob"]


def test_mutual_like_users_malformed_json_skips_feature(monkeypatch):
    from litefupzl.oneshot.env_loader import load_oneshot_env

    monkeypatch.setenv("LITEFUPZL_COOKIES_JSON", json.dumps(["_t=redacted"]))
    monkeypatch.setenv("LITEFUPZL_MUTUAL_LIKE_USERS_JSON", "not-json")

    config = load_oneshot_env()

    assert config.mutual_like_users == []
