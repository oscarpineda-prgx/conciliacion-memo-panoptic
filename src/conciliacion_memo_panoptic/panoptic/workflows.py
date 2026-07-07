from __future__ import annotations

import datetime
import math
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


def update_claim_statuses(
    settings: PanopticSettings,
    invoice_ready_claims: list[str],
    posted_claims: list[str],
    view_name: str = "MONICA_3",
    batch_size: int = 50,
    cancel_event: threading.Event | None = None,
    print_fn=print,
) -> None:
    """Actualiza en Panoptic el Status de los claims de Etapa 2.

    - invoice_ready_claims → Status = "Invoice ready"
    - posted_claims        → Status = "Posted"

    Procesa en lotes de máx batch_size claims usando el filtro 'In' de
    Claim number + 'Adjust status'. Después de cada lote navega de vuelta
    a Claims para limpiar los filtros de columna.

    Args:
        settings: configuración de Panoptic (URL, credenciales, etc.)
        invoice_ready_claims: Claim numbers a marcar como "Invoice ready"
        posted_claims: Claim numbers a marcar como "Posted"
        view_name: nombre de la vista de Claims a usar
        batch_size: máximo de claims por lote (recomendado ≤ 50)
        cancel_event: si se activa, detiene el proceso entre lotes
        print_fn: función de salida (print o GUI logger)
    """
    remind_date = datetime.date.today().strftime("%m/%d/%Y")

    groups: list[tuple[str, list[str]]] = []
    if invoice_ready_claims:
        groups.append(("Invoice ready", invoice_ready_claims))
    if posted_claims:
        groups.append(("Posted", posted_claims))

    if not groups:
        print_fn("No hay claims para actualizar.")
        return

    with sync_playwright() as playwright:
        context = launch_browser_context(playwright, settings)
        page = context.pages[0] if context.pages else context.new_page()

        try:
            navigator = prepare_claims_view(page, settings, view_name,
                                            cancel_event=cancel_event)
            if cancel_event and cancel_event.is_set():
                return

            for status, claims in groups:
                n_batches = math.ceil(len(claims) / batch_size)
                print_fn(
                    f"\nActualizando Status='{status}' — "
                    f"{len(claims)} claims en {n_batches} lote(s)"
                )

                for batch_idx in range(n_batches):
                    if cancel_event and cancel_event.is_set():
                        print_fn("Proceso cancelado.")
                        return

                    batch = claims[batch_idx * batch_size : (batch_idx + 1) * batch_size]
                    print_fn(
                        f"  Lote {batch_idx + 1}/{n_batches} "
                        f"({len(batch)} claims)..."
                    )
                    navigator.adjust_claim_status_batch(batch, status, remind_date)
                    print_fn(f"  Lote {batch_idx + 1}/{n_batches} completado.")

            print_fn("\nActualizacion de Status finalizada.")
        finally:
            context.close()
