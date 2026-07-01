from __future__ import annotations

import threading
from pathlib import Path
from time import monotonic, sleep

from playwright.sync_api import Download, Page, sync_playwright

from ..settings import PanopticSettings
from .browser import launch_browser_context
from .filenames import build_target_path
from .session import prepare_claims_view


TEMP_DOWNLOAD_SUFFIXES = (".crdownload", ".download", ".part", ".tmp")


def download_xlsx(
    settings: PanopticSettings,
    memo: str | None = None,
    vendor: str | None = None,
    view_name: str = "MONICA_3",
    cancel_event: threading.Event | None = None,
) -> Path:
    settings.download_dir.mkdir(parents=True, exist_ok=True)

    if settings.headless:
        print("Aviso: el modo headless no sirve para login manual con MFA.")

    with sync_playwright() as playwright:
        context = launch_browser_context(playwright, settings)
        page = context.pages[0] if context.pages else context.new_page()

        try:
            navigator = prepare_claims_view(
                page, settings, view_name, cancel_event=cancel_event
            )
            if cancel_event and cancel_event.is_set():
                raise RuntimeError("Cancelado por el usuario.")

            print(f"Vista preparada: {view_name}")
            print("Exportando XLSX desde Panoptic...")

            known_downloads = _snapshot_download_dir(settings.download_dir)
            downloads: list[Download] = []
            page.on("download", lambda download: downloads.append(download))

            navigator.export_claims_xlsx()
            result = _wait_for_download_or_file(
                page,
                downloads,
                settings.download_dir,
                known_downloads,
                timeout_ms=settings.download_timeout_ms,
                cancel_event=cancel_event,
            )

            if cancel_event and cancel_event.is_set():
                raise RuntimeError("Cancelado por el usuario.")

            if isinstance(result, Download):
                return _save_playwright_download(
                    result, settings.download_dir, memo=memo, vendor=vendor,
                )
            if isinstance(result, Path):
                return _move_to_target(
                    result, settings.download_dir, memo=memo, vendor=vendor,
                )

            debug_base = navigator.write_export_debug_dump("download_timeout")
            timeout_seconds = settings.download_timeout_ms // 1000
            raise RuntimeError(
                "Se hizo clic en XLSX, pero Panoptic no entrego una descarga "
                f"en {timeout_seconds} segundos. Revise el estado capturado en "
                f"{debug_base.with_suffix('.png')} y {debug_base.with_suffix('.txt')}."
            )
        finally:
            context.close()


def _snapshot_download_dir(download_dir: Path) -> set[str]:
    if not download_dir.exists():
        return set()
    return {path.name for path in download_dir.iterdir() if path.is_file()}


def _wait_for_download_or_file(
    page: Page,
    downloads: list[Download],
    download_dir: Path,
    known_downloads: set[str],
    timeout_ms: int = 15_000,
    cancel_event: threading.Event | None = None,
) -> Download | Path | None:
    deadline = monotonic() + (timeout_ms / 1000)
    while monotonic() < deadline:
        if cancel_event and cancel_event.is_set():
            return None
        if downloads:
            return downloads.pop(0)
        downloaded_file = _find_new_completed_download(download_dir, known_downloads)
        if downloaded_file:
            return downloaded_file
        page.wait_for_timeout(300)
    return None


def _find_new_completed_download(download_dir: Path, known_downloads: set[str]) -> Path | None:
    for path in _new_download_candidates(download_dir, known_downloads):
        if _is_completed_download(path):
            return path
    return None


def _new_download_candidates(download_dir: Path, known_downloads: set[str]) -> list[Path]:
    if not download_dir.exists():
        return []

    candidates = [
        path
        for path in download_dir.iterdir()
        if path.is_file()
        and path.name not in known_downloads
        and path.name != ".gitkeep"
        and not _is_temp_download(path)
    ]
    candidates.sort(key=lambda path: path.stat().st_mtime, reverse=True)
    return candidates


def _is_temp_download(path: Path) -> bool:
    name = path.name.lower()
    return any(name.endswith(suffix) for suffix in TEMP_DOWNLOAD_SUFFIXES)


def _is_completed_download(path: Path) -> bool:
    try:
        first_size = path.stat().st_size
        if first_size <= 0:
            return False
        sleep(0.2)
        return path.exists() and path.stat().st_size == first_size
    except OSError:
        return False


def _move_to_target(
    downloaded_file: Path,
    download_dir: Path,
    memo: str | None = None,
    vendor: str | None = None,
) -> Path:
    target = build_target_path(
        download_dir,
        downloaded_file.name,
        memo=memo,
        vendor=vendor,
    )
    if downloaded_file.resolve() == target.resolve():
        return target

    downloaded_file.replace(target)
    return target


def _save_playwright_download(
    download: Download,
    download_dir: Path,
    memo: str | None = None,
    vendor: str | None = None,
) -> Path:
    failure = download.failure()
    if failure:
        raise RuntimeError(f"La descarga fallo: {failure}")

    target = build_target_path(
        download_dir,
        download.suggested_filename,
        memo=memo,
        vendor=vendor,
    )
    download.save_as(str(target))
    return target
