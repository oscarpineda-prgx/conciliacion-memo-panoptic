from __future__ import annotations

from pathlib import Path

from openpyxl.drawing.image import Image as XLImage
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

# ---------------------------------------------------------------------------
# Constantes de diseño
# ---------------------------------------------------------------------------

HEADER_ROWS = 6  # filas reservadas para logo + título antes de la fila de encabezados

_FILL_GREEN = PatternFill(fill_type="solid", fgColor="00FD28")
_FONT_BOLD = Font(bold=True, color="000000")
_BORDER_THIN = Side(style="thin", color="000000")
_FULL_BORDER = Border(
    left=_BORDER_THIN, right=_BORDER_THIN,
    top=_BORDER_THIN, bottom=_BORDER_THIN,
)
_ALIGN_CENTER = Alignment(horizontal="center", vertical="center")
_ALIGN_HEADER = Alignment(horizontal="center", vertical="center", wrap_text=True)

_ASSETS_DIR = Path(__file__).parent.parent / "assets"
DEFAULT_LOGO: Path = _ASSETS_DIR / "Soriana-Logo.png"

SHEET_SUBTITLES: dict[str, str] = {
    # Etapa 1 — Conciliación MEMO vs Panoptic
    "Resumen":              "Resumen Conciliación Memo - Panoptic",
    "P1 Actualizados":      "P1 — Proveedores Asignados al Memo (Monto Coincide)",
    "P1 Diferencias":       "P1 — Proveedores con Diferencia de Monto",
    "Incons Proveedores":    "P2 — Inconsistencias de Proveedor",
    "Incons DuplicadosxMemo":    "P2b — Proveedores Duplicados en Múltiples Memos",
    "Incons Montos":             "P3 — Inconsistencias de Monto",
    "Incons DiferenciasXMonto":  "P3b — Claims que Generan la Diferencia de Monto por Proveedor",
    "Incons Concepto-Año":  "P4 — Duplicados Concepto / Año en MEMO",
    "Cruce Resumen":        "Cruce Resumen Proveedores",
    "Cruce Detalle":        "Cruce Detalle Concepto - Año",
    # Etapa 2 — Cruce con Estado de Cuenta (Folios Compensatorios)
    "Cruce Exitoso":        "Etapa 2 — Proveedores con Folio Compensatorio Coincidente",
    "Sin Coincidencia":     "Etapa 2 — Proveedores EC sin Coincidencia en Panoptic",
    "Panoptic Sin Folio":   "Etapa 2 — Proveedores Panoptic sin Folio Compensatorio",
}


# ---------------------------------------------------------------------------
# API pública
# ---------------------------------------------------------------------------

def write_sheet(writer, df, sheet_name: str) -> None:
    """Escribe un DataFrame dejando HEADER_ROWS filas libres arriba para el encabezado."""
    df.to_excel(writer, sheet_name=sheet_name, index=False, startrow=HEADER_ROWS)


def style_workbook(wb, logo_path: Path | None = None) -> None:
    """Aplica logo, título y estilo de columnas a todas las hojas del workbook."""
    resolved_logo = logo_path or DEFAULT_LOGO
    logo_exists = resolved_logo.exists()

    for ws in wb.worksheets:
        subtitle = SHEET_SUBTITLES.get(ws.title, ws.title)
        _style_sheet(ws, subtitle, resolved_logo if logo_exists else None)


# ---------------------------------------------------------------------------
# Interno
# ---------------------------------------------------------------------------

def _style_sheet(ws, subtitle: str, logo_path: Path | None) -> None:
    max_col = ws.max_column or 1
    max_row = ws.max_row or HEADER_ROWS + 1
    header_row = HEADER_ROWS + 1  # fila 7

    # Sin cuadrícula global: solo aparecerán los bordes que agreguemos manualmente
    ws.sheet_view.showGridLines = False

    # --- Logo (A2, desplazado hacia abajo para quedar centrado en el bloque) ---
    if logo_path:
        img = XLImage(str(logo_path))
        img.width = 206
        img.height = 55
        img.anchor = "B2"
        ws.add_image(img)

    # --- Título empresa (fila 3, cols C:G — más a la izquierda) ---
    ws.merge_cells("C3:G3")
    cell_title = ws["C3"]
    cell_title.value = "Tiendas Soriana, S.A. de C.V."
    cell_title.font = Font(bold=True, size=14, color="000000")
    cell_title.alignment = _ALIGN_CENTER

    # --- Subtítulo de la hoja (fila 4, cols C:G — más a la izquierda) ---
    ws.merge_cells("C4:G4")
    cell_sub = ws["C4"]
    cell_sub.value = subtitle
    cell_sub.font = Font(bold=True, size=12, color="000000")
    cell_sub.alignment = _ALIGN_CENTER

    # --- Encabezados de columna (fila 7): fondo verde, negrita, borde negro ---
    for col in range(1, max_col + 1):
        cell = ws.cell(row=header_row, column=col)
        cell.fill = _FILL_GREEN
        cell.font = _FONT_BOLD
        cell.border = _FULL_BORDER
        cell.alignment = _ALIGN_HEADER

    # --- Bordes en filas de datos (solo la tabla, no el área de encabezado) ---
    for row in range(header_row + 1, max_row + 1):
        for col in range(1, max_col + 1):
            ws.cell(row=row, column=col).border = _FULL_BORDER

    # --- Congelar debajo de los encabezados de columna ---
    ws.freeze_panes = ws.cell(row=header_row + 1, column=1)

    # --- Altura de filas del bloque logo/título ---
    for r in range(1, HEADER_ROWS + 1):
        ws.row_dimensions[r].height = 18
    ws.row_dimensions[header_row].height = 30

    # --- Auto-ancho de columnas basado en el contenido más largo ---
    for col_idx in range(1, max_col + 1):
        col_letter = get_column_letter(col_idx)
        max_len = 0
        for row in range(header_row, max_row + 1):
            val = ws.cell(row=row, column=col_idx).value
            if val is not None:
                max_len = max(max_len, len(str(val)))
        # Mínimo 12, máximo 55 caracteres de ancho
        ws.column_dimensions[col_letter].width = min(max(max_len + 4, 12), 55)
