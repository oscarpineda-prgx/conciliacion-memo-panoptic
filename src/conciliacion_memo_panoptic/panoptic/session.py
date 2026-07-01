from __future__ import annotations
import threading
from playwright.sync_api import Error as PlaywrightError, Page
from ..settings import PanopticSettings
from .login import submit_email_if_present
from .navigation import PanopticNavigator


def _cancelled(cancel_event: threading.Event | None) -> bool:
    return cancel_event is not None and cancel_event.is_set()


def open_start_page(page: Page, settings: PanopticSettings) -> None:
    try:
        page.goto(settings.start_url, wait_until="domcontentloaded")
    except PlaywrightError as exc:
        raise RuntimeError(f"No se pudo abrir Panoptic: {exc}") from exc


def submit_login_email(page: Page, settings: PanopticSettings) -> bool:
    if not settings.login_email:
        return False
    submitted = submit_email_if_present(page, settings.login_email)
    if submitted:
        print(f"Correo ingresado en login: {settings.login_email}")
    else:
        print("No se encontro pantalla de correo; puede que la sesion ya este iniciada.")
    return submitted


def prepare_claims_view(
    page: Page,
    settings: PanopticSettings,
    view_name: str,
    cancel_event: threading.Event | None = None,
) -> PanopticNavigator:
    navigator = PanopticNavigator(
        page,
        app_base_url=settings.app_base_url,
        timeout_ms=settings.default_timeout_ms,
        action_timeout_ms=settings.action_timeout_ms,
        locator_probe_timeout_ms=settings.locator_probe_timeout_ms,
        post_click_wait_ms=settings.post_click_wait_ms,
    )
    open_start_page(page, settings)
    if _cancelled(cancel_event):
        return navigator
    submit_login_email(page, settings)
    reach_claims_page(page, settings, navigator)
    if _cancelled(cancel_event):
        return navigator
    navigator.log("Abriendo menu View: Assigned to you")
    navigator.open_views_menu()
    if _cancelled(cancel_event):
        return navigator
    navigator.log("Seleccionando All views")
    navigator.open_all_views()
    if _cancelled(cancel_event):
        return navigator
    navigator.log("Seleccionando Other Views")
    navigator.open_other_views()
    if _cancelled(cancel_event):
        return navigator
    navigator.log(f"Seleccionando vista {view_name}")
    navigator.select_view(view_name)
    return navigator


def reach_claims_page(
    page: Page,
    settings: PanopticSettings,
    navigator: PanopticNavigator,
    attempts: int = 3,
) -> None:
    for attempt in range(1, attempts + 1):
        print(f"[Panoptic] Abriendo Claims (intento {attempt})")
        if navigator.wait_for_claims_page(timeout_ms=1_000):
            return
        submitted = submit_login_email(page, settings)
        if submitted and navigator.wait_for_claims_page(timeout_ms=15_000):
            return
        try:
            navigator.go_to_claims()
        except RuntimeError:
            submitted = submit_login_email(page, settings)
            if not submitted:
                continue
        if navigator.wait_for_claims_page(timeout_ms=10_000):
            return
        submitted = submit_login_email(page, settings)
        if submitted and navigator.wait_for_claims_page(timeout_ms=15_000):
            return
    raise RuntimeError(
        "No se pudo llegar a Claims. La pagina parece seguir en login o en una pantalla "
        "intermedia de autenticacion."
    )