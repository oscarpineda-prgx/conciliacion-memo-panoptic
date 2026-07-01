from __future__ import annotations
import os
import tempfile
from pathlib import Path
from typing import Any
from playwright.sync_api import BrowserContext, Playwright  

from ..settings import PanopticSettings


def _candidate_browser_paths() -> list[Path]:
    roots = [
        Path(root)
        for root in [
            os.environ.get("ProgramFiles"),
            os.environ.get("ProgramFiles(x86)"),
            os.environ.get("LocalAppData"),
        ]
        if root
    ]
    chrome_candidates = [
        root / "Google" / "Chrome" / "Application" / "chrome.exe" for root in roots
    ]
    edge_candidates = [
        root / "Microsoft" / "Edge" / "Application" / "msedge.exe" for root in roots
    ]
    return edge_candidates + chrome_candidates


def make_unique_profile_dir(base_dir: Path) -> Path:
    base_dir.parent.mkdir(parents=True, exist_ok=True)
    return Path(tempfile.mkdtemp(prefix=f"{base_dir.name}-", dir=base_dir.parent))


def resolve_browser_executable(settings: PanopticSettings) -> Path | None:
    if settings.browser_executable_path:
        if not settings.browser_executable_path.exists():
            raise FileNotFoundError(
                f"No existe browser_executable_path: {settings.browser_executable_path}"
            )
        return settings.browser_executable_path
    for candidate in _candidate_browser_paths():
        if candidate.exists():
            return candidate
    return None


def launch_browser_context(                         
    playwright: Playwright, settings: PanopticSettings
) -> BrowserContext:
    profile_dir = make_unique_profile_dir(settings.browser_profile_dir)
    settings.download_dir.mkdir(parents=True, exist_ok=True)

    launch_kwargs: dict[str, Any] = {
        "headless": settings.headless,
        "chromium_sandbox": settings.chromium_sandbox,
    }

    if settings.browser_channel:
        launch_kwargs["channel"] = settings.browser_channel
        print(f"Usando canal de navegador Playwright: {settings.browser_channel}")
    else:
        browser_executable = resolve_browser_executable(settings)
        if browser_executable:
            launch_kwargs["executable_path"] = str(browser_executable)
            print(f"Usando navegador local: {browser_executable}")

    context = playwright.chromium.launch_persistent_context(
        user_data_dir=str(profile_dir),
        accept_downloads=True,
        downloads_path=str(settings.download_dir),
        viewport={"width": 1440, "height": 900},
        **launch_kwargs,
    )

    print(f"Perfil aislado para esta ejecucion: {profile_dir}")
    context.set_default_timeout(settings.default_timeout_ms)
    return context