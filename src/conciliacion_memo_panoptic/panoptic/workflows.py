from __future__ import annotations

import threading
from pathlib import Path

from playwright.sync_api import sync_playwright

from ..settings import PanopticSettings
from .browser import launch_browser_context
from .session import prepare_claims_view


def open_claims_view(settings: PanopticSettings, view_name: str, keep_open: bool = True) -> None:
    if settings.headless and keep_open:
        print("Aviso: el modo headless no permite inspeccionar el navegador al terminar.")

    with sync_playwright() as playwright:
        context = launch_browser_context(playwright, settings)
        page = context.pages[0] if context.pages else context.new_page()

        try:
            prepare_claims_view(page, settings, view_name)
            print(f"Vista seleccionada: {view_name}")
            if keep_open:
                input("Presiona Enter para cerrar el navegador...")
        finally:
            context.close()


def upload_claim_updates(
    settings: PanopticSettings,
    file_path: Path,
    view_name: str = "MONICA_3",
    cancel_event: threading.Event | None = None,
) -> None:
    """Navega a Panoptic, selecciona la vista e importa el archivo de bulk update."""
    if not file_path.exists():
        raise FileNotFoundError(f"Archivo de bulk update no encontrado: {file_path}")

    with sync_playwright() as playwright:
        context = launch_browser_context(playwright, settings)
        page = context.pages[0] if context.pages else context.new_page()

        try:
            navigator = prepare_claims_view(page, settings, view_name,
                                            cancel_event=cancel_event)
            if cancel_event and cancel_event.is_set():
                return
            navigator.import_claim_updates(file_path)
            print(f"Importacion completada: {file_path.name}")
        finally:
            context.close()


def upload_recoveries_clearing_data(
    settings: PanopticSettings,
    file_path: Path,
    view_name: str = "MONICA_3",
    cancel_event: threading.Event | None = None,
) -> None:
    """Navega a Panoptic y sube el archivo de recoveries / clearing data."""
    if not file_path.exists():
        raise FileNotFoundError(f"Archivo de recoveries no encontrado: {file_path}")

    with sync_playwright() as playwright:
        context = launch_browser_context(playwright, settings)
        page = context.pages[0] if context.pages else context.new_page()

        try:
            navigator = prepare_claims_view(page, settings, view_name,
                                            cancel_event=cancel_event)
            if cancel_event and cancel_event.is_set():
                return
            navigator.import_recoveries_clearing_data(file_path)
            print(f"Importacion completada: {file_path.name}")
        finally:
            context.close()
