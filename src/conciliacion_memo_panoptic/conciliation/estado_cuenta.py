"""
Etapa 2: Cruce con Estado de Cuenta (Folios Compensatorios).

Lee archivos MEMO_0XX.XLSX de la carpeta de Folios Compensatorios, aplica
filtros de color + texto, cruza con Panoptic (bajo filtros P1) y enriquece
el DataFrame de Panoptic con los campos del Estado de Cuenta.

Salida por memo (en output_dir):
  etapa2_M0XX.xlsx               — análisis (3 hojas)
  etapa2_M0XX_PostingDate.xlsx   — plantilla para 'Import claim updates'
  etapa2_M0XX_Recoveries.xlsx    — plantilla para 'Import recoveries / clearing data'
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

import pandas as pd

from .formatting import style_workbook, write_sheet
from .processing import (
    _AMOUNT_TOLERANCE,
    _ensure_tax_column,
    _load_panoptic,
    _normalize_vendor,
)

# ---------------------------------------------------------------------------
# Columnas Estado de Cuenta
# ---------------------------------------------------------------------------

_EC_DOC_NUMBER    = "Document Number"
_EC_ACCOUNT       = "Account"
_EC_DOC_DATE      = "Document Date"
_EC_AMOUNT        = "Amount in local currency"
_EC_TEXT          = "Text"
_EC_CLEARING_DOC  = "Clearing Document"
_EC_CLEARING_DATE = "Clearing date"

# Columnas de Panoptic a rellenar
_PAN_VENDOR       = "Vendor number"
_PAN_NET          = "Net claim amount"
_PAN_TAX          = "Total tax amount"
_PAN_POSTING_REF  = "Posting reference number"
_PAN_BATCH        = "Batch number"
_PAN_POST_DATE    = "Posting submission date"
_PAN_LAST_REC_NO  = "Last recovery number"
_PAN_LAST_REC_DT  = "Last recovery date"
_PAN_LAST_CLR_DT  = "Last cleared date"

_ENRICHED_COLS = (_PAN_BATCH, _PAN_POST_DATE, _PAN_LAST_REC_NO, _PAN_LAST_REC_DT, _PAN_LAST_CLR_DT)

# Columnas adicionales para lógica de Batch number
_EC_REFERENCE         = "Reference"
_AUDIT_PROJECT_COL    = "Audit project"   # columna en Panoptic (búsqueda case-insensitive)
_BATCH_AMOUNT_TOL     = 2.0               # tolerancia ±2 pesos para cruce de Batch number
_COSTOS_PAGOS_RE      = re.compile(r"costos?|pagos?", re.IGNORECASE)
_FILL_RATE_RE         = re.compile(r"fill\s*rate", re.IGNORECASE)
_CLIENT_CLAIM_TYPE_COL = "Client claim type"  # columna en Panoptic (búsqueda case-insensitive)

# Rutas de plantillas
from ..paths import PROJECT_ROOT as _PROJECT_ROOT
_TEMPLATE_POSTING_DATE = _PROJECT_ROOT / "data" / "templates" / "Claim_Bulk_Update_Template_2.xlsx"
_TEMPLATE_RECOVERIES   = _PROJECT_ROOT / "data" / "templates" / "Claims_Import_Recovery_Template.xlsx"

# Formato de fecha requerido por Panoptic
_DATE_FMT = "%Y-%m-%d"


# ---------------------------------------------------------------------------
# Detección de celdas sin relleno
# ---------------------------------------------------------------------------

def _is_no_fill(fill) -> bool:
    """True si la celda openpyxl no tiene color de fondo (No Fill)."""
    if fill is None:
        return True
    return getattr(fill, "fill_type", None) in (None, "none", "")


def _no_fill_row_indices(path: Path, col_name: str) -> set[int]:
    """Índices pandas (0-based) de filas donde col_name no tiene relleno de color."""
    from openpyxl import load_workbook

    wb = load_workbook(path, data_only=True)
    ws = wb.active

    header = next(ws.iter_rows(min_row=1, max_row=1, values_only=False), [])
    col_idx = next((c.column for c in header if c.value == col_name), None)
    if col_idx is None:
        raise ValueError(f"Columna '{col_name}' no encontrada en {path.name}")

    return {
        pandas_idx
        for pandas_idx, row in enumerate(ws.iter_rows(min_row=2))
        if _is_no_fill(row[col_idx - 1].fill)
    }


# ---------------------------------------------------------------------------
# Carga y filtrado del archivo de Folios Compensatorios
# ---------------------------------------------------------------------------

def _memo_num_pattern(memo_id: str) -> str:
    """Regex que coincide con el número de memo en cualquier formato (048, 48, 0048…).

    Usa lookaround en lugar de \\b porque '_' cuenta como carácter de palabra
    y MEMO_046 no tiene word-boundary entre '_' y '0'.
    """
    m = re.search(r"\d+", memo_id)
    return rf"(?<!\d)0*{int(m.group())}(?!\d)" if m else re.escape(memo_id)


def load_estado_cuenta(folio_path: Path, memo_id: str, print_fn=print) -> pd.DataFrame:
    """Carga el Estado de Cuenta aplicando los 3 filtros requeridos:

    1. Filas sin relleno de color en Document Number (filtro de color).
    2. Columna Text contiene la palabra 'MEMO'.
    3. Columna Text contiene el número de este memo (048, 48, etc.).
    """
    no_fill_idx = _no_fill_row_indices(folio_path, _EC_DOC_NUMBER)
    print_fn(f"      [filtro color]  filas sin relleno: {len(no_fill_idx)}")

    df = pd.read_excel(folio_path)
    print_fn(f"      [excel total]   filas totales: {len(df)}  |  columnas: {list(df.columns)}")
    df = df.iloc[sorted(no_fill_idx)].copy().reset_index(drop=True)

    if _EC_TEXT in df.columns:
        text = df[_EC_TEXT].fillna("").astype(str).str.upper()
        df_memo_word = df[text.str.contains("MEMO", regex=False)]
        print_fn(f"      [filtro MEMO]   filas con 'MEMO': {len(df_memo_word)}")
        if not df_memo_word.empty:
            pattern = _memo_num_pattern(memo_id)
            df_memo_num = df_memo_word[
                text.loc[df_memo_word.index].str.contains(pattern, regex=True)
            ]
            print_fn(f"      [filtro número] filas con '{memo_id}' (patrón {pattern!r}): {len(df_memo_num)}")
            if df_memo_word.empty or df_memo_num.empty:
                sample = text.loc[df_memo_word.index].head(5).tolist() if not df_memo_word.empty else text.head(5).tolist()
                print_fn(f"      [muestra Text]  {sample}")
            df = df_memo_num.reset_index(drop=True)
        else:
            sample = text.head(5).tolist()
            print_fn(f"      [muestra Text]  {sample}")
            df = df_memo_word.reset_index(drop=True)
    else:
        print_fn(f"      ADVERTENCIA: columna '{_EC_TEXT}' no encontrada. Columnas disponibles: {list(df.columns)}")

    if _EC_ACCOUNT in df.columns:
        df[_EC_ACCOUNT] = _normalize_vendor(df[_EC_ACCOUNT])

    return df


# ---------------------------------------------------------------------------
# Descubrimiento de archivos de folios
# ---------------------------------------------------------------------------

def _folio_memo_id(stem: str) -> str | None:
    m = re.search(r"MEMO_(\d+)", stem, re.IGNORECASE)
    return f"M{int(m.group(1)):03d}" if m else None


def discover_folio_entries(folios_dir: Path) -> list[tuple[str, Path]]:
    """Lista ordenada de (memo_id, path) para archivos MEMO_*.xlsx."""
    entries: dict[str, Path] = {}
    for p in folios_dir.glob("MEMO_*.xlsx"):
        if p.name.startswith("~$"):
            continue
        memo_id = _folio_memo_id(p.stem)
        if memo_id:
            entries[memo_id] = p
    return sorted(entries.items())


# ---------------------------------------------------------------------------
# Enriquecimiento in-place de filas de Panoptic
# ---------------------------------------------------------------------------

def _apply_ec_to_rows(
    df: pd.DataFrame,
    idx: list,
    ec_row: pd.Series,
    today: date,
) -> None:
    """Escribe los campos del Estado de Cuenta en las filas indicadas de Panoptic."""
    clearing_raw = ec_row.get(_EC_CLEARING_DATE)
    clearing_dt = (
        pd.to_datetime(clearing_raw, errors="coerce").date()
        if pd.notna(clearing_raw)
        else None
    )

    df.loc[idx, _PAN_BATCH]       = ec_row.get(_EC_DOC_NUMBER)
    df.loc[idx, _PAN_POST_DATE]   = ec_row.get(_EC_DOC_DATE)
    df.loc[idx, _PAN_LAST_REC_NO] = ec_row.get(_EC_CLEARING_DOC)

    if clearing_dt and clearing_dt > today:
        # Fecha de compensación futura: Last recovery date = hoy, Last cleared date = clearing_dt
        df.loc[idx, _PAN_LAST_REC_DT] = today
        df.loc[idx, _PAN_LAST_CLR_DT] = clearing_dt
    else:
        df.loc[idx, _PAN_LAST_REC_DT] = clearing_dt
        df.loc[idx, _PAN_LAST_CLR_DT] = None


# ---------------------------------------------------------------------------
# Formateo de fechas
# ---------------------------------------------------------------------------

def _fmt_date(val) -> str | None:
    """Convierte cualquier valor de fecha a string 'yyyy-mm-dd', o None si está vacío."""
    if val is None:
        return None
    if isinstance(val, float) and pd.isna(val):
        return None
    if isinstance(val, (date, datetime)):
        return val.strftime(_DATE_FMT)
    if isinstance(val, str) and val.strip():
        try:
            return pd.to_datetime(val).strftime(_DATE_FMT)
        except Exception:
            return val.strip() or None
    try:
        return pd.to_datetime(val).strftime(_DATE_FMT)
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Lógica de Batch number — 3 condiciones por Audit project
# ---------------------------------------------------------------------------

def _is_costos_pagos(val) -> bool:
    """True si Audit project contiene 'costo(s)' o 'pago(s)' (mayúsculas/minúsculas)."""
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return False
    return bool(_COSTOS_PAGOS_RE.search(str(val)))


def _is_fill_rate(val) -> bool:
    """True si Audit project contiene 'fill rate' (mayúsculas/minúsculas)."""
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return False
    return bool(_FILL_RATE_RE.search(str(val)))


def _reference_is_alphabetic(val) -> bool:
    """True si Reference no contiene ningún dígito (ej. FILL RATE, APORTACIONES, MERMA).

    Las referencias alfanuméricas/numéricas (NVA19017, 0000228704, FAC633280)
    devuelven False.
    """
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return False
    s = str(val).strip()
    return bool(s) and not bool(re.search(r"\d", s))


def _normalize_ref(val) -> str:
    """Normaliza Reference/Client claim type para comparación: strip + upper + espacios simples."""
    return re.sub(r"\s+", " ", str(val).strip().upper())


def _batch_from_cond1(
    sub_idx: list,
    df_pan: pd.DataFrame,
    df_ec_vendor: pd.DataFrame,
) -> dict:
    """Condición 1 — Audit project contiene FILL RATE.

    Divide los claims en dos grupos:
      Grupo A (tax == 0): sum(Net claim amount)
      Grupo B (tax != 0): sum(Net claim amount + Total tax amount)

    Cruza cada suma contra EC filtrado a Reference alfabética (±2 pesos).
    Devuelve {panoptic_index: Document Number}.
    """
    if _EC_REFERENCE not in df_ec_vendor.columns:
        return {}

    ec_alpha = df_ec_vendor[df_ec_vendor[_EC_REFERENCE].map(_reference_is_alphabetic)]
    if ec_alpha.empty:
        return {}

    ec_amounts = pd.to_numeric(ec_alpha[_EC_AMOUNT], errors="coerce").abs()

    def _find_doc(target: float):
        diff = (ec_amounts - target).abs()
        pos = diff.idxmin() if not diff.empty else None
        return ec_alpha.at[pos, _EC_DOC_NUMBER] if pos is not None and diff[pos] <= _BATCH_AMOUNT_TOL else None

    result: dict = {}

    zero_tax = [
        i for i in sub_idx
        if abs(pd.to_numeric(df_pan.at[i, _PAN_TAX], errors="coerce") or 0.0) < 0.001
    ]
    nonzero_tax = [i for i in sub_idx if i not in set(zero_tax)]

    if zero_tax:
        s = pd.to_numeric(df_pan.loc[zero_tax, _PAN_NET], errors="coerce").sum()
        batch = _find_doc(float(s))
        if batch is not None:
            result.update({i: batch for i in zero_tax})

    if nonzero_tax:
        s = (
            pd.to_numeric(df_pan.loc[nonzero_tax, _PAN_NET], errors="coerce").sum()
            + pd.to_numeric(df_pan.loc[nonzero_tax, _PAN_TAX], errors="coerce").sum()
        )
        batch = _find_doc(float(s))
        if batch is not None:
            result.update({i: batch for i in nonzero_tax})

    return result


def _batch_from_cond2(
    sub_idx: list,
    df_ec_vendor: pd.DataFrame,
) -> dict:
    """Condición 2 — Audit project = COSTOS/PAGOS.

    Filtra EC a Reference alfanumérica (con dígitos).
    Toma el Document Number de la fila con mayor Amount in local currency.
    Devuelve {panoptic_index: Document Number}.
    """
    if _EC_REFERENCE not in df_ec_vendor.columns:
        return {}

    ec_num = df_ec_vendor[
        ~df_ec_vendor[_EC_REFERENCE].map(_reference_is_alphabetic)
    ].copy()
    if ec_num.empty:
        return {}

    ec_num["_abs_amt"] = pd.to_numeric(ec_num[_EC_AMOUNT], errors="coerce").abs()
    batch = ec_num.at[ec_num["_abs_amt"].idxmax(), _EC_DOC_NUMBER]
    return {i: batch for i in sub_idx}


def _batch_from_cond3(
    sub_idx: list,
    df_pan: pd.DataFrame,
    df_ec_vendor: pd.DataFrame,
) -> dict:
    """Condición 3 — Audit project ≠ FILL RATE y ≠ COSTOS/PAGOS (ej. APERTURA, APORTACIONES, MERMA).

    Agrupa los claims por 'Client claim type'. Para cada grupo:
      1. Normaliza Client claim type y busca filas EC con Reference alfabética coincidente.
      2. Suma (Net claim amount + Total tax amount) del grupo.
      3. Compara suma vs Amount in local currency del EC (±2 pesos).
      4. El Document Number del EC coincidente es el Batch number del grupo.

    Devuelve {panoptic_index: Document Number}.
    """
    if _EC_REFERENCE not in df_ec_vendor.columns:
        return {}

    cct_col = next(
        (c for c in df_pan.columns if c.lower() == _CLIENT_CLAIM_TYPE_COL.lower()),
        None,
    )
    if cct_col is None:
        return {}

    ec_alpha = df_ec_vendor[
        df_ec_vendor[_EC_REFERENCE].map(_reference_is_alphabetic)
    ].copy()
    if ec_alpha.empty:
        return {}

    ec_alpha["_ref_norm"] = ec_alpha[_EC_REFERENCE].map(_normalize_ref)
    ec_alpha["_abs_amt"]  = pd.to_numeric(ec_alpha[_EC_AMOUNT], errors="coerce").abs()

    pan_sub = df_pan.loc[sub_idx, [cct_col, _PAN_NET, _PAN_TAX]].copy()
    pan_sub["_net"]      = pd.to_numeric(pan_sub[_PAN_NET], errors="coerce").fillna(0.0)
    pan_sub["_tax"]      = pd.to_numeric(pan_sub[_PAN_TAX], errors="coerce").fillna(0.0)
    pan_sub["_cct_norm"] = pan_sub[cct_col].map(_normalize_ref)

    result: dict = {}

    for cct_norm, group in pan_sub.groupby("_cct_norm", dropna=False):
        pan_sum = (group["_net"] + group["_tax"]).sum()

        ec_ref = ec_alpha[ec_alpha["_ref_norm"] == cct_norm]
        if ec_ref.empty:
            continue

        diff = (ec_ref["_abs_amt"] - pan_sum).abs()
        best = diff.idxmin()
        if diff[best] <= _BATCH_AMOUNT_TOL:
            batch = ec_alpha.at[best, _EC_DOC_NUMBER]
            result.update({i: batch for i in group.index})

    return result


def _assign_batch_number(
    vendor_idx: list,
    df_pan: pd.DataFrame,
    df_ec_vendor: pd.DataFrame,
) -> None:
    """Sobreescribe Batch number procesando por grupo de Audit project.

    Condición 1 (FILL RATE):     split por tax==0 / tax!=0, cruza vs EC Reference alfabética.
    Condición 2 (COSTOS/PAGOS):  EC Reference alfanumérica, toma el de mayor monto.
    Condición 3 (cualquier otro): agrupa por Client claim type, cruza vs EC Reference alfabética.

    Un vendor puede tener filas de distintas condiciones; cada grupo de Audit project
    se procesa de forma independiente.
    """
    audit_col = next(
        (c for c in df_pan.columns if c.lower() == _AUDIT_PROJECT_COL.lower()),
        None,
    )

    if audit_col is None:
        for idx, val in _batch_from_cond1(vendor_idx, df_pan, df_ec_vendor).items():
            df_pan.at[idx, _PAN_BATCH] = val
        return

    for audit_val, sub_group in df_pan.loc[vendor_idx].groupby(audit_col, dropna=False):
        sub_idx = list(sub_group.index)

        if _is_fill_rate(audit_val):
            batch_map = _batch_from_cond1(sub_idx, df_pan, df_ec_vendor)
        elif _is_costos_pagos(audit_val):
            batch_map = _batch_from_cond2(sub_idx, df_ec_vendor)
        else:
            batch_map = _batch_from_cond3(sub_idx, df_pan, df_ec_vendor)

        for idx, val in batch_map.items():
            df_pan.at[idx, _PAN_BATCH] = val


# ---------------------------------------------------------------------------
# Generadores de plantillas de carga a Panoptic
# ---------------------------------------------------------------------------

def _write_template(template_path: Path, output_path: Path, rows: list[list]) -> Path:
    """Escribe `rows` en la primera hoja de la plantilla a partir de la fila 2."""
    from openpyxl import load_workbook

    wb = load_workbook(template_path)
    ws = wb.worksheets[0]

    for row in ws.iter_rows(min_row=2, max_row=ws.max_row):
        for cell in row:
            cell.value = None

    for r_idx, row_data in enumerate(rows, start=2):
        for c_idx, val in enumerate(row_data, start=1):
            ws.cell(row=r_idx, column=c_idx).value = val

    output_path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(output_path)
    return output_path


def generate_posting_date_template(df_cruce: pd.DataFrame, output_path: Path) -> Path:
    """Genera plantilla 'Import claim updates' con Posting submission date y Batch number.

    Columnas: Project name | Claim number | Posting submission date (yyyy-mm-dd) | Batch number
    Solo incluye filas donde Posting submission date no es nulo.
    """
    rows = [
        [
            row["Project name"],
            row["Claim number"],
            _fmt_date(row[_PAN_POST_DATE]),
            row.get(_PAN_BATCH),
        ]
        for _, row in df_cruce.iterrows()
        if pd.notna(row.get(_PAN_POST_DATE))
    ]
    return _write_template(_TEMPLATE_POSTING_DATE, output_path, rows)


def generate_recoveries_template(df_cruce: pd.DataFrame, output_path: Path) -> Path:
    """Genera plantilla 'Import recoveries / clearing data'.

    Columnas: Project Name | Claim Number | Recovery type | Recovery amount |
              Recovery date | Reference number | Cleared date | Cleared reference number | Note
    Recovery type es siempre 'Client authorization'.
    Cleared date solo se rellena si Last cleared date tiene valor.
    """
    rows = [
        [
            row["Project name"],
            row["Claim number"],
            "Client authorization",
            row.get(_PAN_NET),
            _fmt_date(row[_PAN_LAST_REC_DT]),
            row.get(_PAN_LAST_REC_NO),
            _fmt_date(row.get(_PAN_LAST_CLR_DT)),
        ]
        for _, row in df_cruce.iterrows()
        if pd.notna(row.get(_PAN_LAST_REC_DT))
    ]
    return _write_template(_TEMPLATE_RECOVERIES, output_path, rows)


# ---------------------------------------------------------------------------
# Cruce por memo
# ---------------------------------------------------------------------------

def cross_estado_cuenta_memo(
    df_pan_full: pd.DataFrame,
    folio_path: Path,
    memo_id: str,
    output_dir: Path,
    print_fn=print,
) -> Path:
    """Cruza el Estado de Cuenta de un memo contra Panoptic.

    Para cada proveedor en el EC cuyo monto coincide (±1 peso) con la suma
    de sus registros en Panoptic, escribe las columnas de compensación.

    Genera outputs/etapa2_M0XX.xlsx con 3 hojas:
      - Cruce Exitoso     : filas Panoptic enriquecidas con datos EC.
      - Sin Coincidencia  : proveedores EC sin match en Panoptic (monto distinto o ausente).
      - Panoptic Sin Folio: proveedores Panoptic del memo sin fila en EC.
    """
    df_ec = load_estado_cuenta(folio_path, memo_id, print_fn=print_fn)
    print_fn(f"    EC cargado:            {len(df_ec)} filas  (archivo: {folio_path.name})")

    if df_ec.empty:
        print_fn(f"    ADVERTENCIA: El EC no tiene filas para {memo_id}. Verifica filtros de color/texto.")

    df_pan = df_pan_full.copy()
    _ensure_tax_column(df_pan)

    df_pan_memo = df_pan[
        df_pan[_PAN_POSTING_REF] == memo_id
    ].copy()
    print_fn(f"    Panoptic con {memo_id}:     {len(df_pan_memo)} filas")

    if df_pan_memo.empty:
        print_fn(
            f"    ADVERTENCIA: No hay claims con Posting reference = '{memo_id}' en Panoptic.\n"
            f"    ¿Ya subiste el Bulk Update de Etapa 1 a Panoptic?\n"
            f"    Valores únicos de Posting reference en Panoptic:\n"
            f"      {sorted(df_pan[_PAN_POSTING_REF].dropna().unique()[:20])}"
        )

    # Asegurar que las columnas destino existan y sean object para aceptar strings/fechas/None
    for col in _ENRICHED_COLS:
        if col not in df_pan_memo.columns:
            df_pan_memo[col] = None
        df_pan_memo[col] = df_pan_memo[col].astype(object)

    today = date.today()
    matched_vendors: set[str] = set()
    unmatched_ec: list[dict] = []

    for vendor, ec_group in df_ec.groupby(_EC_ACCOUNT):
        ec_amount = pd.to_numeric(ec_group[_EC_AMOUNT], errors="coerce").abs().sum()

        vendor_idx = df_pan_memo.index[df_pan_memo[_PAN_VENDOR] == vendor].tolist()
        if not vendor_idx:
            unmatched_ec.extend(ec_group.to_dict("records"))
            continue

        pan_gross = (
            df_pan_memo.loc[vendor_idx, _PAN_NET].sum()
            + df_pan_memo.loc[vendor_idx, _PAN_TAX].sum()
        )

        if abs(ec_amount - pan_gross) <= _AMOUNT_TOLERANCE:
            _apply_ec_to_rows(df_pan_memo, vendor_idx, ec_group.iloc[0], today)
            _assign_batch_number(vendor_idx, df_pan_memo, ec_group)
            matched_vendors.add(vendor)
        else:
            for _, row in ec_group.iterrows():
                unmatched_ec.append({**row.to_dict(), "Gross Panoptic": pan_gross, "Diferencia": ec_amount - pan_gross})

    ec_vendors = set(df_ec[_EC_ACCOUNT].astype(str))
    summary_cols = [_PAN_VENDOR] + (["Vendor name"] if "Vendor name" in df_pan_memo.columns else [])
    df_pan_sin_folio = (
        df_pan_memo[~df_pan_memo[_PAN_VENDOR].isin(ec_vendors)]
        .drop_duplicates(subset=[_PAN_VENDOR])[summary_cols]
        .copy()
    )

    df_cruce     = df_pan_memo[df_pan_memo[_PAN_VENDOR].isin(matched_vendors)].copy()
    df_sin_match = pd.DataFrame(unmatched_ec)

    print_fn(f"    Proveedores EC:        {df_ec[_EC_ACCOUNT].nunique() if not df_ec.empty else 0}")
    print_fn(f"    Coincidencias:         {len(matched_vendors)}")
    print_fn(f"    Sin coincidencia EC:   {len(unmatched_ec)}")
    print_fn(f"    Panoptic sin folio:    {len(df_pan_sin_folio)}")
    if not matched_vendors:
        pan_vendors  = set(df_pan_memo[_PAN_VENDOR].astype(str)) if not df_pan_memo.empty else set()
        ec_vend_list = sorted(ec_vendors)[:10]
        pan_vend_list = sorted(pan_vendors)[:10]
        print_fn(f"    Vendors EC  (primeros 10): {ec_vend_list}")
        print_fn(f"    Vendors Pan (primeros 10): {pan_vend_list}")

    # Archivos por memo van en output_dir/M0XX/
    memo_dir = output_dir / memo_id
    memo_dir.mkdir(parents=True, exist_ok=True)
    output_path = memo_dir / f"etapa2_{memo_id}.xlsx"

    with pd.ExcelWriter(output_path, engine="openpyxl") as writer:
        write_sheet(writer, df_cruce,          "Cruce Exitoso")
        write_sheet(writer, df_sin_match,      "Sin Coincidencia")
        write_sheet(writer, df_pan_sin_folio,  "Panoptic Sin Folio")
        style_workbook(writer.book)

    # Generar plantillas de carga solo si hubo coincidencias
    if not df_cruce.empty:
        generate_posting_date_template(
            df_cruce, memo_dir / f"etapa2_{memo_id}_PostingDate.xlsx"
        )
        generate_recoveries_template(
            df_cruce, memo_dir / f"etapa2_{memo_id}_Recoveries.xlsx"
        )

    return output_path


# ---------------------------------------------------------------------------
# API pública — procesar todos los folios
# ---------------------------------------------------------------------------

@dataclass
class CrossResult:
    memo_id: str
    folio_path: Path
    output_path: Path | None = None
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.error is None


def cross_all_estados_cuenta(
    raw_panoptic_path: Path,
    folios_dir: Path,
    output_dir: Path,
    memo_from: int | None = None,
    memo_to: int | None = None,
    print_fn=print,
) -> list[CrossResult]:
    """Carga Panoptic una vez y cruza contra todos los MEMO_*.xlsx de folios_dir."""
    df_pan = _load_panoptic(raw_panoptic_path)
    print_fn(f"  Panoptic total filas: {len(df_pan)}")

    entries = discover_folio_entries(folios_dir)
    if not entries:
        raise FileNotFoundError(f"No se encontraron archivos MEMO_*.xlsx en {folios_dir}")

    if memo_from is not None or memo_to is not None:
        entries = [
            (mid, p) for mid, p in entries
            if _memo_in_range(mid, memo_from, memo_to)
        ]

    results: list[CrossResult] = []
    for memo_id, folio_path in entries:
        print_fn(f"\n  [{memo_id}] {folio_path.name}")
        result = CrossResult(memo_id=memo_id, folio_path=folio_path)
        try:
            result.output_path = cross_estado_cuenta_memo(
                df_pan, folio_path, memo_id, output_dir, print_fn=print_fn
            )
        except Exception as exc:
            result.error = str(exc)
            print_fn(f"    ERROR: {exc}")
        results.append(result)

    return results


def _memo_in_range(memo_id: str, memo_from: int | None, memo_to: int | None) -> bool:
    m = re.search(r"\d+", memo_id)
    if not m:
        return False
    num = int(m.group())
    if memo_from is not None and num < memo_from:
        return False
    if memo_to is not None and num > memo_to:
        return False
    return True


def run_etapa2(
    folios_dir: Path,
    output_dir: Path,
    memo_from: int | None = None,
    memo_to: int | None = None,
    download_dir: Path | None = None,
    panoptic_settings=None,
    view_name: str = "MONICA_3",
    print_fn=print,
) -> list[CrossResult]:
    """Descarga Panoptic y cruza contra todos los Folios Compensatorios (Etapa 2 completa)."""
    from ..panoptic.downloader import download_xlsx

    if download_dir is None:
        download_dir = output_dir / "panoptic"
    download_dir.mkdir(parents=True, exist_ok=True)

    print_fn("Paso 1/2 — Descargando Panoptic...")
    raw_path = download_xlsx(panoptic_settings, view_name=view_name)
    print_fn(f"  Panoptic descargado: {raw_path}")

    print_fn()
    print_fn("Paso 2/2 — Cruzando con Estados de Cuenta...")
    results = cross_all_estados_cuenta(
        raw_path, folios_dir, output_dir,
        memo_from=memo_from, memo_to=memo_to,
        print_fn=print_fn,
    )

    ok     = [r for r in results if r.ok]
    failed = [r for r in results if not r.ok]
    for r in ok:
        print_fn(f"  OK  {r.memo_id}  ->  {r.output_path}")
    for r in failed:
        print_fn(f"  ERR {r.memo_id}  {r.error}")
    print_fn(f"  Completados: {len(ok)} | Errores: {len(failed)}")

    return results
