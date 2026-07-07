from __future__ import annotations

import re
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

from playwright.sync_api import (
    Error as PlaywrightError,
    Locator,
    Page,
    TimeoutError as PlaywrightTimeoutError,
)

from ..paths import PROJECT_ROOT

LocatorFactory = Callable[[Page], Locator]


class PanopticNavigator:
    def __init__(
        self,
        page: Page,
        app_base_url: str = "https://verigon.prgx.com",
        timeout_ms: int = 30_000,
        action_timeout_ms: int = 8_000,
        locator_probe_timeout_ms: int = 1_500,
        post_click_wait_ms: int = 300,
    ) -> None:
        self.page = page
        self.app_base_url = app_base_url.rstrip("/")
        self.timeout_ms = timeout_ms
        self.action_timeout_ms = action_timeout_ms
        self.locator_probe_timeout_ms = locator_probe_timeout_ms
        self.post_click_wait_ms = post_click_wait_ms

    def select_claims_view(self, view_name: str) -> None:
        self.log("Abriendo Claims")
        self.open_claims()
        self.log("Abriendo menu View: Assigned to you")
        self.open_views_menu()
        self.log("Seleccionando All views")
        self.open_all_views()
        self.log("Seleccionando Other Views")
        self.open_other_views()
        self.log(f"Seleccionando vista {view_name}")
        self.select_view(view_name)

    def export_claims_xlsx(self) -> None:
        self.log("Abriendo menu de acciones")
        self.open_actions_menu()
        self.log("Abriendo submenu Export")
        self.open_export_submenu()
        self.log("Seleccionando XLSX")
        self.click_export_xlsx()

    def import_claim_updates(self, file_path: Path) -> None:
        """Importa un archivo de actualización masiva de claims via el menu de Panoptic."""
        self.log("Abriendo menu de acciones")
        self.open_actions_menu()
        self.log("Seleccionando 'Import claim updates'")
        self._click_import_claim_updates()
        self.log(f"Cargando archivo: {file_path.name}")
        self._upload_import_file(file_path)
        self.log("Guardando importacion")
        self._click_import_save()
        self.log("Importacion completada")

    def open_claims(self) -> None:
        self.go_to_claims()
        if not self.wait_for_claims_page():
            raise RuntimeError("No se pudo abrir la pagina de Claims.")

    def dismiss_feature_announcement(self) -> bool:
        """Cierra el panel lateral de anuncio de nuevos features si está visible.

        Panoptic muestra ocasionalmente un panel deslizante en el lado derecho
        anunciando nuevas funcionalidades. Este método lo detecta y lo cierra
        antes de continuar con cualquier navegación.
        """
        try:
            self.page.get_by_text(
                re.compile(r"New Features are Coming", re.I)
            ).first.wait_for(state="visible", timeout=3_000)
        except PlaywrightTimeoutError:
            return False

        self.log("Panel de anuncio de nuevos features detectado — cerrando")

        def _panel_gone() -> bool:
            try:
                self.page.get_by_text(
                    re.compile(r"New Features are Coming", re.I)
                ).first.wait_for(state="hidden", timeout=1_500)
                return True
            except PlaywrightTimeoutError:
                return False

        # Estrategia 1: Escape (más confiable en Angular Material)
        try:
            self.page.keyboard.press("Escape")
            self._wait_after_click()
            if _panel_gone():
                self.log("Panel de anuncios cerrado con Escape")
                return True
        except PlaywrightError:
            pass

        # Estrategia 2: botones de cierre con timeout corto
        for selector in [
            'button:has(mat-icon:has-text("close"))',
            '[aria-label*="close" i]',
            'button:has-text("×")',
        ]:
            try:
                self.page.locator(selector).first.click(timeout=1_000)
                self._wait_after_click()
                if _panel_gone():
                    self.log("Panel de anuncios cerrado con botón")
                    return True
            except (PlaywrightTimeoutError, PlaywrightError):
                continue

        # Estrategia 3: navegar directo a Claims (evita el panel completamente)
        self.log("No se pudo cerrar el panel — navegando directo a Claims")
        try:
            self.page.goto(
                self._claims_url(),
                wait_until="domcontentloaded",
                timeout=self.timeout_ms,
            )
            return True
        except PlaywrightError:
            pass

        return False

    def go_to_claims(self) -> None:
        if self.is_claims_page():
            return
        self.dismiss_feature_announcement()
        self.click_claims_button()
        if not self.wait_for_claims_page(timeout_ms=5_000):
            self.click_claims_task_link()

    def click_claims_task_link(self) -> bool:
        self._click_first(
            [
                lambda page: page.get_by_text(
                    re.compile(r"Claims to send to the vendor", re.I)
                ),
                lambda page: page.get_by_text(
                    re.compile(r"Claims requiring vendor approval", re.I)
                ),
                lambda page: page.get_by_text(re.compile(r"Claims", re.I)),
            ],
            "liga de Claims en Home",
            timeout_ms=5_000,
        )
        return True

    def click_claims_button(self, timeout_ms: int | None = None) -> bool:  # noqa: ARG002
        self.page.mouse.click(40, 122)
        self._wait_after_click()
        return True

    def is_claims_page(self) -> bool:
        current = urlparse(self.page.url)
        expected = urlparse(self._claims_url())
        return current.netloc == expected.netloc and current.path == expected.path

    def wait_for_claims_page(self, timeout_ms: int | None = None) -> bool:
        timeout = timeout_ms if timeout_ms is not None else self.timeout_ms
        try:
            self.page.wait_for_url(self._claims_url_pattern(), timeout=timeout)
        except PlaywrightTimeoutError:
            pass

        if self.is_claims_page():
            return True

        try:
            self.page.get_by_role(
                "button", name=re.compile(r"View:\s*Assigned to you", re.I)
            ).wait_for(state="visible", timeout=1_000)
            return True
        except PlaywrightTimeoutError:
            return False

    def open_views_menu(self) -> None:
        self._click_first(
            [
                lambda page: page.get_by_role(
                    "button", name=re.compile(r"View:\s*Assigned to you", re.I)
                ),
                lambda page: page.locator('button:has-text("View: Assigned to you")'),
                lambda page: page.locator('button:has-text("Assigned to you")'),
                lambda page: page.get_by_text(re.compile(r"^View:\s*Assigned to you", re.I)),
            ],
            "menu View: Assigned to you",
        )

    def open_all_views(self) -> None:
        self._click_first(
            [
                lambda page: page.get_by_role("menuitem", name=re.compile(r"All views", re.I)),
                lambda page: page.get_by_text(re.compile(r"^All views$", re.I)),
            ],
            "opcion All views",
        )
        self._wait_for_text("Your Views")

    def open_other_views(self) -> None:
        self._click_first(
            [
                lambda page: page.get_by_role("tab", name=re.compile(r"Other Views", re.I)),
                lambda page: page.get_by_text(re.compile(r"^Other Views$", re.I)),
            ],
            "pestana Other Views",
        )
        self._wait_for_text("Other Views")

    def open_actions_menu(self) -> None:
        if self._actions_menu_is_open(timeout_ms=300):
            return

        selectors = [
            "button:has(mat-icon:has-text('more_vert'))",
            "button:has-text('more_vert')",
            "button[aria-label*='More' i]",
            "button[aria-label*='options' i]",
        ]
        for selector in selectors:
            if self._click_top_right_button(selector):
                if self._actions_menu_is_open(timeout_ms=self.action_timeout_ms):
                    return

        self._click_actions_menu_by_coordinates()
        if not self._actions_menu_is_open(timeout_ms=self.action_timeout_ms):
            self._write_export_debug_dump("open_actions_menu")
            raise RuntimeError("No se pudo abrir el menu de acciones de Claims.")

    def open_export_submenu(self) -> None:
        export_item = self._export_menu_item()
        export_item.hover()
        self.page.wait_for_timeout(self.post_click_wait_ms)

        if self._export_options_are_visible(timeout_ms=1_000):
            return

        export_item.click()
        if not self._export_options_are_visible(timeout_ms=self.action_timeout_ms):
            self._write_export_debug_dump("open_export_submenu")
            raise RuntimeError("No se pudo abrir el submenu Export.")

    def click_export_xlsx(self) -> None:
        try:
            self._click_first(
                [
                    lambda page: page.get_by_role(
                        "menuitem", name=re.compile(r"^XLSX$", re.I)
                    ),
                    lambda page: page.locator(
                        ".mat-mdc-menu-item, [role='menuitem']",
                        has_text=re.compile(r"^\s*XLSX\s*$", re.I),
                    ),
                    lambda page: page.get_by_text(re.compile(r"^XLSX$", re.I)),
                ],
                "opcion XLSX de Export",
                timeout_ms=self.action_timeout_ms,
            )
        except RuntimeError:
            self._write_export_debug_dump("click_export_xlsx")
            raise

    def write_export_debug_dump(self, reason: str = "export_xlsx") -> Path:
        return self._write_export_debug_dump(reason)

    def select_view(self, view_name: str) -> None:
        before_url = self.page.url

        view = self._view_name_locator(view_name)
        view.scroll_into_view_if_needed()
        view.wait_for(state="visible", timeout=self.action_timeout_ms)

        self._click_view_locator(view)

        if self._view_dialog_is_open(timeout_ms=2_000):
            self._click_view_locator(view, double=True)

        if self._view_dialog_is_open(timeout_ms=2_000):
            self._click_view_by_coordinates(view)

        try:
            self._wait_until_view_applied(view_name, before_url)
        except RuntimeError:
            self._write_view_debug_dump(view_name)
            raise

    def _view_name_locator(self, view_name: str) -> Locator:
        # El span dentro del <td> tiene un espacio al inicio (" MONICA_3"), por eso
        # el patrón permite whitespace en los extremos: ^\s*NOMBRE\s*$
        escaped_name = re.escape(view_name)
        pattern = re.compile(rf"^\s*{escaped_name}\s*$", re.I)
        dialog = self.page.locator(".mat-mdc-dialog-container, mat-dialog-container").last
        candidates = [
            dialog.locator("td[role='gridcell'].clickable", has_text=pattern),
            dialog.locator("td[role='gridcell']", has_text=pattern),
            dialog.get_by_role("link", name=pattern),
            dialog.locator(f"a:has-text('{view_name}')"),
            dialog.get_by_text(pattern),
            self.page.locator("td[role='gridcell'].clickable", has_text=pattern),
            self.page.locator("td[role='gridcell']", has_text=pattern),
            self.page.get_by_role("link", name=pattern),
            self.page.locator(f"a:has-text('{view_name}')"),
            self.page.get_by_text(pattern),
        ]

        for locator in candidates:
            try:
                locator.first.wait_for(state="attached", timeout=self.locator_probe_timeout_ms)
                return locator.first
            except PlaywrightTimeoutError:
                continue

        self._write_dialog_html_dump(view_name)
        raise RuntimeError(f"No se encontro la vista '{view_name}' en el dialogo.")

    def _click_top_right_button(self, selector: str) -> bool:
        buttons = self.page.locator(selector)
        viewport = self.page.viewport_size or {"width": 1440, "height": 900}
        matches: list[tuple[float, float, int, Locator]] = []

        try:
            count = min(buttons.count(), 80)
        except PlaywrightError:
            return False

        for index in range(count):
            button = buttons.nth(index)
            try:
                box = button.bounding_box()
            except PlaywrightError:
                continue

            if not box:
                continue

            is_top_toolbar = box["y"] <= 180
            is_right_side = box["x"] >= viewport["width"] * 0.65
            if is_top_toolbar and is_right_side:
                matches.append((-box["x"], box["y"], index, button))

        for _, _, _, button in sorted(matches):
            try:
                button.click(force=True)
                self._wait_after_click()
                return True
            except PlaywrightError:
                continue

        return False

    def _click_actions_menu_by_coordinates(self) -> None:
        viewport = self.page.viewport_size or {"width": 1440, "height": 900}
        self.page.mouse.click(viewport["width"] - 28, 104)
        self._wait_after_click()

    def _actions_menu_is_open(self, timeout_ms: int = 500) -> bool:
        try:
            self.page.get_by_text("Select / order columns").first.wait_for(
                state="visible", timeout=timeout_ms
            )
            return True
        except PlaywrightTimeoutError:
            return False

    def _export_menu_item(self) -> Locator:
        candidates = [
            self.page.get_by_role("menuitem", name=re.compile(r"^Export$", re.I)),
            self.page.locator(
                ".mat-mdc-menu-item, [role='menuitem']",
                has_text=re.compile(r"^\s*Export\s*$", re.I),
            ),
            self.page.get_by_text(re.compile(r"^Export$", re.I)),
        ]

        for locator in candidates:
            try:
                locator.first.wait_for(
                    state="visible", timeout=self.locator_probe_timeout_ms
                )
                return locator.first
            except PlaywrightTimeoutError:
                continue

        self._write_export_debug_dump("export_menu_item")
        raise RuntimeError("No se encontro la opcion Export.")

    def _export_options_are_visible(self, timeout_ms: int = 500) -> bool:
        try:
            self.page.get_by_text(re.compile(r"^XLSX$", re.I)).first.wait_for(
                state="visible", timeout=timeout_ms
            )
            return True
        except PlaywrightTimeoutError:
            return False

    def _click_view_locator(self, locator: Locator, double: bool = False) -> None:
        try:
            if double:
                locator.dblclick(force=True)
            else:
                locator.click(force=True)
            self._wait_after_click()
        except PlaywrightError:
            try:
                locator.evaluate(
                    """element => {
                        const target = element.closest('td, a, button, [role="gridcell"]') || element;
                        target.dispatchEvent(new MouseEvent('click', {
                            bubbles: true,
                            cancelable: true,
                            view: window
                        }));
                    }"""
                )
                self._wait_after_click()
            except PlaywrightError:
                pass

    def _click_view_by_coordinates(self, locator: Locator) -> None:
        box = locator.bounding_box()
        if not box:
            raise RuntimeError("La vista esta visible, pero no se pudo obtener su posicion.")

        self.page.mouse.click(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
        self._wait_after_click()

    def _view_dialog_is_open(self, timeout_ms: int = 500) -> bool:
        try:
            self.page.get_by_text("Other Views").first.wait_for(
                state="visible", timeout=timeout_ms
            )
            return True
        except PlaywrightTimeoutError:
            return False

    def _wait_until_view_applied(self, view_name: str, before_url: str) -> None:
        try:
            self.page.wait_for_function(
                """({ viewName, beforeUrl }) => {
                    const bodyText = document.body?.innerText || '';
                    const dialogOpen = bodyText.includes('Other Views') && bodyText.includes(viewName);
                    return !dialogOpen || window.location.href !== beforeUrl;
                }""",
                arg={"viewName": view_name, "beforeUrl": before_url},
                timeout=10_000,
            )
        except PlaywrightTimeoutError:
            if self._view_dialog_is_open(timeout_ms=500):
                raise RuntimeError(f"No se pudo seleccionar la vista {view_name}.")

    def import_recoveries_clearing_data(self, file_path: Path) -> None:
        """Importa un archivo de recoveries / clearing data via el menu de Panoptic."""
        self.log("Abriendo menu de acciones")
        self.open_actions_menu()
        self.log("Seleccionando 'Import recoveries / clearing data'")
        self._click_import_recoveries()
        self.log(f"Cargando archivo: {file_path.name}")
        self._upload_import_file(file_path)
        self.log("Guardando importacion")
        self._click_import_save()
        self.log("Importacion completada")

    def _click_import_recoveries(self) -> None:
        self._click_first(
            [
                lambda page: page.get_by_role("menuitem", name=re.compile(r"Import recoveries", re.I)),
                lambda page: page.locator('[role="menuitem"]', has_text=re.compile(r"Import recoveries", re.I)),
                lambda page: page.get_by_text(re.compile(r"Import recoveries", re.I)),
            ],
            "opcion Import recoveries / clearing data",
        )
        try:
            self.page.get_by_text(re.compile(r"Browse file", re.I)).first.wait_for(
                state="visible", timeout=self.action_timeout_ms
            )
        except PlaywrightTimeoutError:
            raise RuntimeError("El dialogo de 'Import Recoveries / Clearing Data' no se abrio.")

    def _click_import_claim_updates(self) -> None:
        self._click_first(
            [
                lambda page: page.get_by_role("menuitem", name=re.compile(r"Import claim updates", re.I)),
                lambda page: page.locator('[role="menuitem"]', has_text=re.compile(r"Import claim updates", re.I)),
                lambda page: page.get_by_text(re.compile(r"Import claim updates", re.I)),
            ],
            "opcion Import claim updates",
        )
        try:
            self.page.get_by_text(re.compile(r"Browse file", re.I)).first.wait_for(
                state="visible", timeout=self.action_timeout_ms
            )
        except PlaywrightTimeoutError:
            raise RuntimeError("El dialogo de 'Import Claim Updates' no se abrio.")

    def _upload_import_file(self, file_path: Path) -> None:
        browse_btn = None
        for make_locator in [
            lambda page: page.get_by_role("button", name=re.compile(r"Browse file", re.I)),
            lambda page: page.locator('button:has-text("Browse file")'),
            lambda page: page.get_by_text(re.compile(r"Browse file", re.I)),
        ]:
            try:
                loc = make_locator(self.page).first
                loc.wait_for(state="visible", timeout=self.action_timeout_ms)
                browse_btn = loc
                break
            except PlaywrightTimeoutError:
                continue

        if browse_btn is None:
            raise RuntimeError("No se encontro el boton 'Browse file' en el dialogo.")

        with self.page.expect_file_chooser() as fc_info:
            browse_btn.click()
        fc_info.value.set_files(str(file_path))
        # Espera a que el nombre del archivo aparezca en la lista del dialogo
        try:
            self.page.get_by_text(file_path.name).first.wait_for(
                state="visible", timeout=self.action_timeout_ms
            )
        except PlaywrightTimeoutError:
            self.page.wait_for_timeout(2_000)

    def _click_import_save(self) -> None:
        dialog = self.page.locator(
            ".mat-mdc-dialog-container, mat-dialog-container, [role='dialog']"
        ).last
        save_btn = None
        for make_locator in [
            lambda d: d.get_by_role("button", name=re.compile(r"^Save$", re.I)),
            lambda d: d.locator('button:has-text("Save")'),
        ]:
            try:
                loc = make_locator(dialog).first
                loc.wait_for(state="visible", timeout=self.action_timeout_ms)
                save_btn = loc
                break
            except PlaywrightTimeoutError:
                continue

        if save_btn is None:
            raise RuntimeError("No se encontro el boton 'Save' en el dialogo de importacion.")

        save_btn.click()
        self._wait_after_click()
        # Espera a que el dialogo cierre o que la importacion confirme
        try:
            self.page.get_by_text(re.compile(r"Browse file", re.I)).first.wait_for(
                state="hidden", timeout=self.timeout_ms
            )
        except PlaywrightTimeoutError:
            pass
        self.page.wait_for_timeout(500)

    def _write_dialog_html_dump(self, view_name: str) -> None:
        """Guarda el HTML interno del diálogo para diagnosticar selectores fallidos."""
        debug_dir = PROJECT_ROOT / "outputs" / "panoptic_debug"
        debug_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_view = re.sub(r"[^A-Za-z0-9_.-]+", "_", view_name)
        base = debug_dir / f"dialog_html_{safe_view}_{stamp}"

        try:
            self.page.screenshot(path=str(base.with_suffix(".png")), full_page=True)
        except PlaywrightError:
            pass

        try:
            dialog = self.page.locator(".mat-mdc-dialog-container, mat-dialog-container").last
            html = dialog.inner_html(timeout=3_000)
        except PlaywrightError:
            html = self.page.content()

        base.with_suffix(".html").write_text(html, encoding="utf-8")
        print(f"[Panoptic] Debug HTML guardado en: {base.with_suffix('.html')}")

    def _write_view_debug_dump(self, view_name: str) -> None:
        debug_dir = PROJECT_ROOT / "outputs" / "panoptic_debug"
        debug_dir.mkdir(parents=True, exist_ok=True)

        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_view = re.sub(r"[^A-Za-z0-9_.-]+", "_", view_name)
        base_path = debug_dir / f"select_view_{safe_view}_{stamp}"

        try:
            self.page.screenshot(path=str(base_path.with_suffix(".png")), full_page=True)
        except PlaywrightError:
            pass

        try:
            body_text = self.page.locator("body").inner_text(timeout=2_000)
        except PlaywrightError:
            body_text = ""

        base_path.with_suffix(".txt").write_text(
            f"url={self.page.url}\nview_name={view_name}\n\n{body_text}",
            encoding="utf-8",
        )

    def _write_export_debug_dump(self, reason: str = "export_xlsx") -> Path:
        debug_dir = PROJECT_ROOT / "outputs" / "panoptic_debug"
        debug_dir.mkdir(parents=True, exist_ok=True)

        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_reason = re.sub(r"[^A-Za-z0-9_.-]+", "_", reason)
        base_path = debug_dir / f"{safe_reason}_{stamp}"

        try:
            self.page.screenshot(path=str(base_path.with_suffix(".png")), full_page=True)
        except PlaywrightError:
            pass

        try:
            body_text = self.page.locator("body").inner_text(timeout=2_000)
        except PlaywrightError:
            body_text = ""

        base_path.with_suffix(".txt").write_text(
            f"url={self.page.url}\n\n{body_text}",
            encoding="utf-8",
        )
        return base_path

    # ---------------------------------------------------------------------------
    # Adjust Status — actualización masiva de Status (Etapa 2)
    # ---------------------------------------------------------------------------

    def adjust_claim_status_batch(
        self,
        claim_numbers: list[str],
        status: str,
        remind_date: str,
    ) -> None:
        """Actualiza el Status de un lote de Claim numbers en Panoptic.

        Flujo:
        1. Filtra Claim number usando el filtro 'In'
        2. Espera a que los resultados carguen
        3. Selecciona todos los claims ('Select this page')
        4. Abre 'Adjust status', selecciona status y fecha, guarda
        5. Navega de vuelta a Claims para limpiar filtros de columna

        Args:
            claim_numbers: lista de Claim number (máx 50 recomendado)
            status: valor a asignar (ej. "Invoice ready" o "Posted")
            remind_date: fecha en formato MM/DD/YYYY (ej. "07/03/2026")
        """
        self.log(f"Ajustando status '{status}' para {len(claim_numbers)} claims")
        self._apply_in_filter_on_claim_number(claim_numbers)
        self._wait_for_in_filter_results()
        self._select_page_claims()
        self._open_adjust_status_dialog()
        self._fill_and_save_adjust_status(status, remind_date)
        self.log(f"Status '{status}' aplicado — limpiando filtros")
        try:
            self.page.goto(
                self._claims_url(),
                wait_until="domcontentloaded",
                timeout=self.timeout_ms,
            )
        except PlaywrightError:
            pass
        self.page.wait_for_timeout(1_000)

    def _find_column_header(self, column_name: str) -> "Locator":
        """Devuelve el Locator del encabezado de la columna indicada."""
        for make_loc in [
            lambda page: page.locator(
                f'[role="columnheader"]:has-text("{column_name}")'
            ).first,
            lambda page: page.locator(f'th:has-text("{column_name}")').first,
            lambda page: page.get_by_role(
                "columnheader",
                name=re.compile(re.escape(column_name), re.I),
            ).first,
        ]:
            try:
                loc = make_loc(self.page)
                loc.wait_for(state="visible", timeout=self.action_timeout_ms)
                return loc
            except PlaywrightTimeoutError:
                continue
        raise RuntimeError(
            f"No se encontró el encabezado de columna '{column_name}'."
        )

    def _apply_in_filter_on_claim_number(self, claim_numbers: list[str]) -> None:
        """Abre el filtro 'In' de la columna Claim number y pega los claim numbers."""
        col_header = self._find_column_header("Claim number")

        # Hover para activar el botón de filtro (≡)
        col_header.hover()
        self.page.wait_for_timeout(500)

        # Hacer clic en el botón de filtro dentro del encabezado
        filter_opened = False
        for make_btn in [
            lambda h: h.locator("button:has(mat-icon)").last,
            lambda h: h.locator("button").last,
            lambda h: h.locator("[class*='filter']").first,
        ]:
            try:
                btn = make_btn(col_header)
                btn.wait_for(state="visible", timeout=1_000)
                btn.click()
                self._wait_after_click()
                self.page.get_by_text(
                    re.compile(r"Is equal to", re.I)
                ).first.wait_for(state="visible", timeout=2_000)
                filter_opened = True
                break
            except (PlaywrightTimeoutError, PlaywrightError):
                continue

        if not filter_opened:
            raise RuntimeError(
                "No se pudo abrir el menú de filtro de la columna 'Claim number'. "
                "Verifica que estás en la vista de Claims con la columna visible."
            )

        # Seleccionar la opción "In" (evitar capturar "Not in")
        in_clicked = False
        for make_loc in [
            lambda page: page.locator('[role="menuitem"]').filter(
                has_text=re.compile(r"^\s*In\s*$")
            ).first,
            lambda page: page.get_by_role(
                "menuitem", name=re.compile(r"^\s*In\s*$")
            ).first,
            lambda page: page.locator('[role="option"]').filter(
                has_text=re.compile(r"^\s*In\s*$")
            ).first,
        ]:
            try:
                loc = make_loc(self.page)
                loc.wait_for(state="visible", timeout=self.locator_probe_timeout_ms)
                loc.click()
                self._wait_after_click()
                in_clicked = True
                break
            except (PlaywrightTimeoutError, PlaywrightError):
                continue

        if not in_clicked:
            raise RuntimeError(
                "No se encontró la opción 'In' en el menú de filtro de Claim number."
            )

        # Rellenar el textarea con un Claim number por línea
        textarea = None
        for make_loc in [
            lambda page: page.locator('[role="dialog"] textarea').first,
            lambda page: page.get_by_role("dialog").locator("textarea").first,
            lambda page: page.locator("textarea").first,
        ]:
            try:
                loc = make_loc(self.page)
                loc.wait_for(state="visible", timeout=self.action_timeout_ms)
                textarea = loc
                break
            except PlaywrightTimeoutError:
                continue

        if textarea is None:
            raise RuntimeError(
                "No se encontró el textarea del filtro 'In' de Claim number."
            )

        textarea.click()
        textarea.fill("\n".join(claim_numbers))
        self._wait_after_click()

        # Hacer clic en Apply
        self._click_first(
            [
                lambda page: page.locator('[role="dialog"]').get_by_role(
                    "button", name=re.compile(r"^Apply$", re.I)
                ),
                lambda page: page.locator(
                    '[role="dialog"] button:has-text("Apply")'
                ).first,
            ],
            "botón Apply del filtro In",
        )

    def _wait_for_in_filter_results(self) -> None:
        """Espera a que el filtro 'In' se aplique y los claims filtrados carguen."""
        # Esperar a que el diálogo del filtro se cierre
        try:
            self.page.locator('[role="dialog"]').first.wait_for(
                state="hidden", timeout=5_000
            )
        except PlaywrightTimeoutError:
            pass
        # Esperar a que la red se estabilice tras la búsqueda
        try:
            self.page.wait_for_load_state("networkidle", timeout=15_000)
        except PlaywrightTimeoutError:
            pass
        # Pausa adicional: Panoptic puede tardar en activar el checkbox de selección
        self.page.wait_for_timeout(2_500)

    def _select_page_claims(self) -> None:
        """Selecciona todos los claims de la página actual via 'Select this page'."""
        checkbox = None
        for make_loc in [
            lambda page: page.locator("thead input[type='checkbox']").first,
            lambda page: page.locator("th input[type='checkbox']").first,
            lambda page: page.locator(
                "[role='columnheader'] input[type='checkbox']"
            ).first,
        ]:
            try:
                loc = make_loc(self.page)
                loc.wait_for(state="visible", timeout=self.action_timeout_ms)
                checkbox = loc
                break
            except PlaywrightTimeoutError:
                continue

        if checkbox is None:
            raise RuntimeError(
                "No se encontró el checkbox de selección de claims en la tabla."
            )

        checkbox.click()
        self._wait_after_click()

        # Hacer clic en "Select this page" si aparece el menú desplegable
        try:
            opt = self.page.get_by_text(
                re.compile(r"Select this page", re.I)
            ).first
            opt.wait_for(state="visible", timeout=self.action_timeout_ms)
            opt.click()
            self._wait_after_click()
        except PlaywrightTimeoutError:
            # El checkbox ya seleccionó todo directamente sin mostrar el menú
            pass

        # Verificar que la barra azul de acciones apareció
        try:
            self.page.get_by_text(
                re.compile(r"\d+\s*selected", re.I)
            ).first.wait_for(state="visible", timeout=self.action_timeout_ms)
        except PlaywrightTimeoutError:
            raise RuntimeError(
                "No aparecieron claims seleccionados tras 'Select this page'. "
                "¿Los claims están en distintos Stage/Status? "
                "'Adjust status' requiere que todos tengan el mismo Stage y Status."
            )

    def _open_adjust_status_dialog(self) -> None:
        """Hace clic en 'Adjust status' en la barra de acciones azul."""
        self._click_first(
            [
                lambda page: page.get_by_role(
                    "button", name=re.compile(r"Adjust\s*status", re.I)
                ),
                lambda page: page.locator(
                    'button:has-text("Adjust status")'
                ).first,
            ],
            "botón Adjust status",
            timeout_ms=self.action_timeout_ms,
        )
        try:
            self.page.get_by_role("dialog").first.wait_for(
                state="visible", timeout=self.action_timeout_ms
            )
        except PlaywrightTimeoutError:
            raise RuntimeError(
                "El diálogo 'Adjust Status' no se abrió. "
                "Verifica que todos los claims tengan el mismo Stage y Status."
            )

    def _fill_and_save_adjust_status(self, status: str, remind_date: str) -> None:
        """Selecciona el Status, ingresa la Claim remind date y guarda el diálogo."""
        dialog = self.page.get_by_role("dialog").first

        # --- Seleccionar Status ---
        status_sel = None
        for make_loc in [
            lambda d: d.locator("mat-select").first,
            lambda d: d.locator('[role="combobox"]').first,
            lambda d: d.locator("select").first,
        ]:
            try:
                loc = make_loc(dialog)
                loc.wait_for(state="visible", timeout=self.action_timeout_ms)
                status_sel = loc
                break
            except PlaywrightTimeoutError:
                continue

        if status_sel is None:
            raise RuntimeError(
                "No se encontró el dropdown de Status en el diálogo 'Adjust Status'."
            )

        status_sel.click()
        self._wait_after_click()

        # Las opciones de Angular Material aparecen fuera del DOM del dialog
        self._click_first(
            [
                lambda page: page.get_by_role(
                    "option", name=re.compile(re.escape(status), re.I)
                ),
                lambda page: page.locator(
                    "mat-option",
                    has_text=re.compile(re.escape(status), re.I),
                ).first,
                lambda page: page.locator(
                    '[role="option"]',
                    has_text=re.compile(re.escape(status), re.I),
                ).first,
            ],
            f"opción '{status}' en el dropdown de Status",
        )
        self._wait_after_click()

        # --- Claim remind date ---
        date_input = None
        for make_loc in [
            lambda d: d.locator('input[placeholder*="MM/DD/YYYY" i]').first,
            lambda d: d.locator('input[placeholder*="date" i]').first,
            lambda d: d.locator("input").last,
        ]:
            try:
                loc = make_loc(dialog)
                loc.wait_for(state="visible", timeout=self.action_timeout_ms)
                date_input = loc
                break
            except PlaywrightTimeoutError:
                continue

        if date_input is not None:
            date_input.click()
            # Usar Ctrl+A + type para simular tipeo real (trigger Angular change detection)
            date_input.press("Control+A")
            date_input.type(remind_date)
            # Tab para confirmar y cerrar el datepicker sin cerrar el diálogo
            date_input.press("Tab")
            self._wait_after_click()

        # --- Guardar ---
        save_btn = None
        for make_loc in [
            lambda d: d.get_by_role("button", name=re.compile(r"^Save$", re.I)),
            lambda d: d.locator('button:has-text("Save")').first,
        ]:
            try:
                loc = make_loc(dialog)
                loc.wait_for(state="visible", timeout=self.action_timeout_ms)
                save_btn = loc
                break
            except PlaywrightTimeoutError:
                continue

        if save_btn is None:
            raise RuntimeError(
                "No se encontró el botón Save en el diálogo 'Adjust Status'."
            )

        save_btn.click()
        self._wait_after_click()

        # Esperar a que el diálogo se cierre y la actualización se aplique
        try:
            self.page.get_by_role("dialog").first.wait_for(
                state="hidden", timeout=self.timeout_ms
            )
        except PlaywrightTimeoutError:
            pass
        self.page.wait_for_timeout(1_000)

    def _click_first(
        self,
        candidates: list[LocatorFactory],
        description: str,
        *,
        required: bool = True,
        timeout_ms: int | None = None,
    ) -> bool:
        timeout = timeout_ms if timeout_ms is not None else self.locator_probe_timeout_ms

        for candidate in candidates:
            locator = candidate(self.page).first
            try:
                locator.wait_for(state="visible", timeout=timeout)
                locator.click()
                self._wait_after_click()
                return True
            except PlaywrightTimeoutError:
                continue

        if required:
            raise RuntimeError(f"No se encontro {description}.")
        return False

    def _claims_url(self) -> str:
        return f"{self.app_base_url}/ui/c3p/claims/list"

    def _claims_url_pattern(self) -> re.Pattern[str]:
        return re.compile(rf"^{re.escape(self._claims_url())}(?:[?#].*)?$")

    def _wait_for_text(self, text: str) -> None:
        self.page.get_by_text(text).first.wait_for(
            state="visible", timeout=self.action_timeout_ms
        )

    def _wait_after_click(self) -> None:
        self.page.wait_for_timeout(self.post_click_wait_ms)

    def log(self, message: str) -> None:
        print(f"[Panoptic] {message}")