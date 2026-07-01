from __future__ import annotations

import json
import os
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

from .paths import PROJECT_ROOT


def default_browser_profile_dir() -> Path:
    local_app_data = os.getenv("LOCALAPPDATA")
    if local_app_data:
        return (
            Path(local_app_data)
            / "ConciliacionMemoPanoptic"
            / "playwright"
            / "panoptic-profile-edge"
        )
    return PROJECT_ROOT / ".local" / "playwright" / "panoptic-profile-edge"


@dataclass(frozen=True)
class PanopticSettings:
    start_url: str = "https://verigon.prgx.com/"
    app_base_url: str = "https://verigon.prgx.com"
    download_dir: Path = PROJECT_ROOT / "data" / "raw" / "panoptic"
    browser_profile_dir: Path = field(default_factory=default_browser_profile_dir)
    login_email: str | None = None
    browser_channel: str | None = None
    browser_executable_path: Path | None = None
    chromium_sandbox: bool = True
    headless: bool = False
    default_timeout_ms: int = 60_000
    download_timeout_ms: int = 300_000
    action_timeout_ms: int = 8_000
    locator_probe_timeout_ms: int = 600
    post_click_wait_ms: int = 150

    def with_overrides(self, **kwargs: Any) -> "PanopticSettings":
        clean = {key: value for key, value in kwargs.items() if value is not None}
        return replace(self, **clean)


def _project_path(value: str | Path) -> Path:
    path = Path(os.path.expandvars(os.path.expanduser(str(value))))
    if path.is_absolute():
        return path
    return PROJECT_ROOT / path


def _optional_project_path(value: str | Path | None) -> Path | None:
    if value in (None, ""):
        return None
    return _project_path(value)


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def load_panoptic_settings(config_path: str | Path | None = None) -> PanopticSettings:
    default_config = PROJECT_ROOT / "config" / "panoptic.local.json"
    config = _load_json(_project_path(config_path) if config_path else default_config)
    defaults = PanopticSettings()

    settings = PanopticSettings(
        start_url=config.get("start_url", defaults.start_url),
        app_base_url=config.get("app_base_url", defaults.app_base_url).rstrip("/"),
        download_dir=_project_path(config.get("download_dir", defaults.download_dir)),
        browser_profile_dir=_project_path(
            config.get("browser_profile_dir", defaults.browser_profile_dir)
        ),
        login_email=config.get("login_email", defaults.login_email),
        browser_channel=config.get("browser_channel", defaults.browser_channel),
        browser_executable_path=_optional_project_path(
            config.get("browser_executable_path", defaults.browser_executable_path)
        ),
        chromium_sandbox=bool(config.get("chromium_sandbox", defaults.chromium_sandbox)),
        headless=bool(config.get("headless", defaults.headless)),
        default_timeout_ms=int(config.get("default_timeout_ms", defaults.default_timeout_ms)),
        download_timeout_ms=int(
            config.get("download_timeout_ms", defaults.download_timeout_ms)
        ),
        action_timeout_ms=int(config.get("action_timeout_ms", defaults.action_timeout_ms)),
        locator_probe_timeout_ms=int(
            config.get("locator_probe_timeout_ms", defaults.locator_probe_timeout_ms)
        ),
        post_click_wait_ms=int(config.get("post_click_wait_ms", defaults.post_click_wait_ms)),
    )

    return settings.with_overrides(
        start_url=os.getenv("PANOPTIC_START_URL"),
        app_base_url=os.getenv("PANOPTIC_APP_BASE_URL"),
        download_dir=_project_path(os.environ["PANOPTIC_DOWNLOAD_DIR"])
        if "PANOPTIC_DOWNLOAD_DIR" in os.environ
        else None,
        browser_profile_dir=_project_path(os.environ["PANOPTIC_PROFILE_DIR"])
        if "PANOPTIC_PROFILE_DIR" in os.environ
        else None,
        login_email=os.getenv("PANOPTIC_LOGIN_EMAIL"),
        browser_channel=os.getenv("PANOPTIC_BROWSER_CHANNEL"),
        browser_executable_path=_optional_project_path(os.getenv("PANOPTIC_BROWSER_EXECUTABLE")),
        chromium_sandbox=_env_bool("PANOPTIC_CHROMIUM_SANDBOX"),
        download_timeout_ms=_env_int("PANOPTIC_DOWNLOAD_TIMEOUT_MS"),
        action_timeout_ms=_env_int("PANOPTIC_ACTION_TIMEOUT_MS"),
        locator_probe_timeout_ms=_env_int("PANOPTIC_LOCATOR_PROBE_TIMEOUT_MS"),
        post_click_wait_ms=_env_int("PANOPTIC_POST_CLICK_WAIT_MS"),
    )


def _env_bool(name: str) -> bool | None:
    value = os.getenv(name)
    if value is None:
        return None
    return value.strip().lower() in {"1", "true", "yes", "y", "si", "sí"}


def _env_int(name: str) -> int | None:
    value = os.getenv(name)
    if value is None:
        return None
    return int(value)
