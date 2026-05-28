"""Environment loading for litefupzl oneshot mode."""

from __future__ import annotations

import json
import os
from pathlib import Path

from litefupzl.config.defaults import SESSION_DURATION_MINUTES
from litefupzl.oneshot.env_schema import OneShotEnvConfig

_ENV_FILE_CANDIDATES = (".env.local", ".env")
DEFAULT_ONESHOT_DURATION_MINUTES = SESSION_DURATION_MINUTES


def _parse_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if value and len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
            value = value[1:-1]
        values[key] = value
    return values


def _load_repo_env_files() -> None:
    for filename in _ENV_FILE_CANDIDATES:
        path = Path(filename)
        if not path.exists():
            continue
        for key, value in _parse_env_file(path).items():
            os.environ.setdefault(key, value)


def _load_json_array(primary_key: str, alias_keys: tuple[str, ...] = (), default: list[str] | None = None) -> list[str]:
    for key in (primary_key, *alias_keys):
        raw = os.environ.get(key)
        if not raw:
            continue
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ValueError(f"{key} must be valid JSON array") from exc
        if not isinstance(parsed, list):
            raise ValueError(f"{key} must be a JSON array")
        return [str(item) for item in parsed]
    if default is not None:
        return list(default)
    raise ValueError(f"Missing required environment variable: {primary_key}")


def _load_optional_json_array(primary_key: str, alias_keys: tuple[str, ...] = ()) -> list[str]:
    """Load an optional JSON string array, returning [] when absent or malformed.

    Mutual-like is intentionally opt-in and fail-closed: a malformed target list
    disables the feature instead of failing the read flow.
    """
    for key in (primary_key, *alias_keys):
        raw = os.environ.get(key)
        if not raw:
            continue
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            return []
        if not isinstance(parsed, list):
            return []
        return [str(item) for item in parsed]
    return []


def _load_int(primary_key: str, default: int, alias_keys: tuple[str, ...] = ()) -> int:
    for key in (primary_key, *alias_keys):
        raw = os.environ.get(key)
        if raw is None or raw == "":
            continue
        return int(raw)
    return default


def _load_bool(primary_key: str, default: bool, alias_keys: tuple[str, ...] = ()) -> bool:
    for key in (primary_key, *alias_keys):
        raw = os.environ.get(key)
        if raw is None or raw == "":
            continue
        return raw.lower() in ("1", "true", "yes")
    return default


def _cookie_refresh_enabled_from_env() -> bool:
    return _load_bool(
        "LITEFUPZL_COOKIE_REFRESH_ENABLED",
        True,
        alias_keys=("FUCKPZL_ONESHOT_COOKIE_REFRESH_ENABLED",),
    )


def load_oneshot_env() -> OneShotEnvConfig:
    """Load oneshot config from environment variables only."""
    _load_repo_env_files()

    config = {
        "site": os.environ.get("LITEFUPZL_SITE") or os.environ.get("FUCKPZL_ONESHOT_SITE", "linux.do"),
        "cookies": _load_json_array("LITEFUPZL_COOKIES_JSON", alias_keys=("FUCKPZL_ONESHOT_COOKIES_JSON",)),
        "duration_minutes": _load_int(
            "LITEFUPZL_DURATION_MINUTES",
            DEFAULT_ONESHOT_DURATION_MINUTES,
            alias_keys=("FUCKPZL_ONESHOT_DURATION_MINUTES", "RUN_TIME_LIMIT_MINUTES"),
        ),
        "headless": _load_bool("LITEFUPZL_HEADLESS", True, alias_keys=("FUCKPZL_ONESHOT_HEADLESS",)),
        "output_dir": os.environ.get("LITEFUPZL_OUTPUT_DIR") or os.environ.get("FUCKPZL_ONESHOT_OUTPUT_DIR", "output/litefupzl"),
        "browser_name": os.environ.get("LITEFUPZL_BROWSER") or os.environ.get("FUCKPZL_ONESHOT_BROWSER") or "chromium",
        "proxy_server": os.environ.get("LITEFUPZL_PROXY_SERVER") or os.environ.get("FUCKPZL_ONESHOT_PROXY_SERVER") or None,
        "virtual_display": _load_bool("LITEFUPZL_VIRTUAL_DISPLAY", True, alias_keys=("FUCKPZL_ONESHOT_VIRTUAL_DISPLAY",)),
        "cookie_refresh_enabled": _cookie_refresh_enabled_from_env(),
        "mutual_like_users": _load_optional_json_array("LITEFUPZL_MUTUAL_LIKE_USERS_JSON"),
    }
    return OneShotEnvConfig.model_validate(config)
