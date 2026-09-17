"""
Etapa 3: Nivel de Servicio (NS-EneAgo25).

Dos validaciones por proveedor sobre los claims de Panoptic con
Posting reference = "NS-EneAgo25" y Status != "Rejected":

  1. PRIMARIA — Bitácora (auditor) vs Panoptic:
       la hoja 'Bitacora' tiene los montos VALIDADOS por el auditor con el proveedor,
       que Panoptic debió replicar. Por proveedor:
         Bitácora Final (antes imptos)  vs  Σ Panoptic Net claim amount
         Bitácora Final con imptos      vs  Σ Panoptic (Net + Tax)
       (Penalización con Imptos = Final con imptos + Soportado/reembolso con imptos.)

  2. SECUNDARIA — Panoptic vs Estado de Cuenta (bloques SAP):
       consolida los 4 BLOQUE*.xlsx, filtra líneas NS Ene-Ago 2025 y compara el neto
       EC vs Panoptic (bruto). Además enriquece y arma las plantillas de carga.

Fórmula del neto EC por proveedor (VALIDADA contra Bitacora.Final con imptos):
    Σ Amount in local currency donde
        (Clearing Document lleno  Y  Text es NS-penalización/parcialidad)
        OR (Payment Block == "L")            ← reembolsos (negativos, sin clearing)

Dos fases de filtro Panoptic:
    - Validación de montos: TODOS los claims NS no-Rejected.
    - Generación de plantillas: SOLO los claims cuyo Batch number venía vacío.

Salida (en output_dir/NS):
    etapa3_NS.xlsx                 — análisis (Cruce Exitoso, Sin Coincidencia,
                                     Panoptic Sin EC, Reembolsos, Resumen NS)
    etapa3_NS_PostingDate.xlsx     — plantilla "Import claim updates" (solo Batch vacío)
    etapa3_NS_Recoveries.xlsx      — plantilla "Import recoveries / clearing data"
"""
from __future__ import annotations

import glob
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

import numpy as np
import pandas as pd

from ..paths import PROJECT_ROOT
from .estado_cuenta import (
    _EC_ACCOUNT,
    _EC_AMOUNT,
    _EC_CLEARING_DATE,
    _EC_CLEARING_DOC,
    _EC_DOC_DATE,
    _EC_DOC_NUMBER,
    _EC_TEXT,
    _PAN_BATCH,
    _PAN_NET,
    _PAN_POSTING_REF,
    _PAN_TAX,
    _PAN_VENDOR,
    _ENRICHED_COLS,
    _apply_ec_to_rows,
    _merge_filled,
    _rows_updated_in,
    _POSTING_DATE_COLS,
    _RECOVERY_COLS,
    generate_posting_date_template,
    generate_recoveries_template,
)
from .formatting import style_workbook, write_sheet
from .processing import (
    _AMOUNT_TOLERANCE,
    _ensure_tax_column,
    _load_panoptic,
    _normalize_vendor,
)

# ---------------------------------------------------------------------------
# Configuración NS
# ---------------------------------------------------------------------------

_NS_POSTING_REF = "NS-EneAgo25"
_PAN_STATUS = "Status"
_STATUS_EXCLUDE = "Rejected"

# Corte de periodo: < cutoff = Ene-Ago 2025 (procesar); >= = Sep-Dic 2025 (excluir)
_NS_CUTOFF = datetime(2026, 6, 19)

# Text del EC (case-insensitive)
_NS_PENAL_SUBSTR = "NIVEL SERVICIO 2025"        # excluye 2026 / 1900
_NS_PARCIAL_PREFIX = "NS PARCIALIDAD"
_EC_PAYMENT_BLOCK = "Payment Block"
_EC_REEMBOLSO_PB = "L"

# Columnas del EC que se conservan al consolidar (streaming)
_EC_KEEP_COLS = [
    _EC_DOC_NUMBER, _EC_ACCOUNT, "Document Type", _EC_DOC_DATE, _EC_AMOUNT,
    "Local Currency", _EC_CLEARING_DOC, _EC_TEXT, _EC_PAYMENT_BLOCK,
    _EC_CLEARING_DATE, "Net due date", "Reference",
]

_REEMB_SHEET = "Reembolsos"
_REEMB_HEADER_ROW = 3            # encabezados reales en la fila 3 (0-based header=2)
_REEMB_VENDOR = "Proveedor"
_REEMB_NAME = "Nombre"
_REEMB_TOTAL = "Total reembolsar"

# Columnas curadas para la hoja de análisis
_CRUCE_COLS = [
    "Project name", "Claim number", _PAN_VENDOR, "Vendor name", _PAN_STATUS,
    "Client claim type", _PAN_NET, _PAN_TAX, _PAN_POSTING_REF,
    _PAN_BATCH, "Posting submission date", "Last recovery number",
    "Last recovery date", "Last cleared date", "Requiere carga",
]


# ---------------------------------------------------------------------------
# Predicados de texto NS
# ---------------------------------------------------------------------------

def _is_penal(text: object) -> bool:
    return text is not None and _NS_PENAL_SUBSTR in str(text).upper()


def _is_parcial(text: object) -> bool:
    return text is not None and str(text).strip().upper().startswith(_NS_PARCIAL_PREFIX)


def _is_reembolso_pb(pb: object) -> bool:
    return pb is not None and str(pb).strip().upper() == _EC_REEMBOLSO_PB


# ---------------------------------------------------------------------------
# Paso 0 — Consolidar los bloques del Estado de Cuenta
# ---------------------------------------------------------------------------

def _stream_ns_rows(path: Path, print_fn=print) -> list[dict]:
    """Lee un BLOQUE por streaming y devuelve solo las filas relevantes a NS.

    Relevante = Text penalización/parcialidad NS  OR  Payment Block == "L".
    Mantiene el archivo liviano en memoria (los bloques tienen 100k+ filas).
    """
    from openpyxl import load_workbook

    wb = load_workbook(path, data_only=True, read_only=True)
    ws = wb[wb.sheetnames[0]]
    rows_iter = ws.iter_rows(min_row=1, values_only=True)
    header = list(next(rows_iter))
    idx = {name: i for i, name in enumerate(header)}
    keep = {c: idx[c] for c in _EC_KEEP_COLS if c in idx}

    out: list[dict] = []
    for row in rows_iter:
        if row is None:
            continue
        text = row[idx[_EC_TEXT]] if _EC_TEXT in idx else None
        pb = row[idx[_EC_PAYMENT_BLOCK]] if _EC_PAYMENT_BLOCK in idx else None
        if _is_penal(text) or _is_parcial(text) or _is_reembolso_pb(pb):
            out.append({c: row[i] for c, i in keep.items()})
    wb.close()
    print_fn(f"      {path.name}: {len(out)} filas NS")
    return out


def consolidate_ec_blocks(blocks_dir: Path, print_fn=print) -> pd.DataFrame:
    """Consolida los BLOQUE*.xlsx de blocks_dir en un solo DataFrame de líneas NS.

    - Streaming por bloque (solo filas NS).
    - Concatena los 4 bloques tal cual (SIN deduplicar).
    - Normaliza Account (vendor) y parsea Document Date.
    """
    files = sorted(
        p for p in blocks_dir.glob("*.xlsx") if not p.name.startswith("~$")
    )
    if not files:
        raise FileNotFoundError(f"No se encontraron archivos .xlsx en {blocks_dir}")

    print_fn(f"    Consolidando {len(files)} bloque(s) de {blocks_dir}")
    all_rows: list[dict] = []
    for f in files:
        all_rows.extend(_stream_ns_rows(f, print_fn=print_fn))

    df = pd.DataFrame(all_rows).reset_index(drop=True)
    if df.empty:
        return df

    print_fn(f"    Total filas NS consolidadas (4 bloques, sin deduplicar): {len(df)}")

    df[_EC_ACCOUNT] = _normalize_vendor(df[_EC_ACCOUNT])
    df[_EC_AMOUNT] = pd.to_numeric(df[_EC_AMOUNT], errors="coerce").fillna(0.0)
    df["_date"] = pd.to_datetime(df[_EC_DOC_DATE], errors="coerce")
    df["_pb"] = df[_EC_PAYMENT_BLOCK].map(lambda v: str(v).strip().upper() if v is not None else "")
    df["_cd_filled"] = (
        df[_EC_CLEARING_DOC].notna()
        & (df[_EC_CLEARING_DOC].astype(str).str.strip() != "")
        & (df[_EC_CLEARING_DOC].astype(str).str.strip() != "0")
    )
    df["_is_penal"] = df[_EC_TEXT].map(_is_penal)
    df["_is_parcial"] = df[_EC_TEXT].map(_is_parcial)
    return df


def filter_ec_ns_ene_ago(df_ec: pd.DataFrame, print_fn=print) -> pd.DataFrame:
    """Filtra al periodo Ene-Ago 2025: Document Date < 19-jun-2026."""
    if df_ec.empty:
        return df_ec
    before = len(df_ec)
    out = df_ec[df_ec["_date"] < _NS_CUTOFF].copy()
    print_fn(
        f"    Corte de fecha < {_NS_CUTOFF.date()}: {before} -> {len(out)} filas "
        f"(excluidas Sep-Dic: {before - len(out)})"
    )
    return out


def filter_ec_ns_septdic(df_ec: pd.DataFrame, print_fn=print) -> pd.DataFrame:
    """Filtra al periodo Sep-Dic 2025: Document Date >= 19-jun-2026 (inverso de Ene-Ago)."""
    if df_ec.empty:
        return df_ec
    before = len(df_ec)
    out = df_ec[df_ec["_date"] >= _NS_CUTOFF].copy()
    print_fn(
        f"    Corte de fecha >= {_NS_CUTOFF.date()}: {before} -> {len(out)} filas "
        f"(excluidas Ene-Ago: {before - len(out)})"
    )
    return out


# ---------------------------------------------------------------------------
# Neto EC por proveedor
# ---------------------------------------------------------------------------

def _ec_net_by_vendor(df_ec_ns: pd.DataFrame) -> pd.DataFrame:
    """Neto EC por proveedor = Σ Amount donde (clearing lleno Y NS/parcial) OR PB='L'.

    Devuelve columnas: ec_net (el neto para comparar), ec_penal (solo penalización
    con clearing) y ec_reembolso_L (Σ líneas Payment Block='L', negativas).
    """
    include = (df_ec_ns["_cd_filled"] & (df_ec_ns["_is_penal"] | df_ec_ns["_is_parcial"])) | (
        df_ec_ns["_pb"] == _EC_REEMBOLSO_PB
    )
    ec_net = df_ec_ns[include].groupby(_EC_ACCOUNT)[_EC_AMOUNT].sum().rename("ec_net")
    ec_penal = (
        df_ec_ns[df_ec_ns["_cd_filled"] & df_ec_ns["_is_penal"]]
        .groupby(_EC_ACCOUNT)[_EC_AMOUNT].sum().rename("ec_penal")
    )
    ec_L = (
        df_ec_ns[df_ec_ns["_pb"] == _EC_REEMBOLSO_PB]
        .groupby(_EC_ACCOUNT)[_EC_AMOUNT].sum().rename("ec_reembolso_L")
    )
    out = pd.concat([ec_net, ec_penal, ec_L], axis=1).fillna(0.0)
    return out


def _representative_ec_row(vendor_rows: pd.DataFrame) -> pd.Series | None:
    """Fila EC representativa del proveedor para volcar clearing/batch a Panoptic.

    Se toma la línea de penalización/parcialidad con clearing y mayor monto absoluto
    (misma lógica de "mayor monto" que Etapa 2).
    """
    cand = vendor_rows[
        vendor_rows["_cd_filled"] & (vendor_rows["_is_penal"] | vendor_rows["_is_parcial"])
    ]
    if cand.empty:
        cand = vendor_rows[vendor_rows["_cd_filled"]]
    if cand.empty:
        return None
    return cand.loc[cand[_EC_AMOUNT].abs().idxmax()]


# ---------------------------------------------------------------------------
# Reembolsos de la bitácora
# ---------------------------------------------------------------------------

def load_reembolsos_bitacora(bitacora_path: Path, print_fn=print) -> pd.DataFrame:
    """Lee la hoja 'Reembolsos' y agrega Total reembolsar por proveedor.

    Fuente autoritativa de "¿tiene reembolso?" (la col M de la hoja Bitacora es
    poco confiable entre versiones). Devuelve columnas:
    Vendor number, Vendor name (Reembolsos), Reembolso Bitacora.
    """
    empty = pd.DataFrame(columns=[_PAN_VENDOR, "Vendor name (Reembolsos)", "Reembolso Bitacora"])
    if bitacora_path is None or not Path(bitacora_path).exists():
        print_fn(f"    [reembolsos] Bitácora no encontrada: {bitacora_path} — se omite cross-check.")
        return empty

    xl = pd.ExcelFile(bitacora_path)
    if _REEMB_SHEET not in xl.sheet_names:
        print_fn(f"    [reembolsos] hoja '{_REEMB_SHEET}' no existe en esta bitácora — se omite cross-check.")
        return empty
    df = pd.read_excel(xl, sheet_name=_REEMB_SHEET, header=_REEMB_HEADER_ROW - 1)
    if _REEMB_VENDOR not in df.columns or _REEMB_TOTAL not in df.columns:
        print_fn(f"    [reembolsos] Columnas {_REEMB_VENDOR!r}/{_REEMB_TOTAL!r} no encontradas.")
        return empty

    df = df[df[_REEMB_VENDOR].notna()].copy()
    df[_PAN_VENDOR] = _normalize_vendor(df[_REEMB_VENDOR])
    df[_REEMB_TOTAL] = pd.to_numeric(df[_REEMB_TOTAL], errors="coerce").fillna(0.0)
    name_col = _REEMB_NAME if _REEMB_NAME in df.columns else _REEMB_VENDOR

    agg = (
        df.groupby(_PAN_VENDOR)
        .agg(**{
            "Vendor name (Reembolsos)": (name_col, "first"),
            "Reembolso Bitacora": (_REEMB_TOTAL, "sum"),
        })
        .reset_index()
    )
    agg = agg[agg["Reembolso Bitacora"].abs() > _AMOUNT_TOLERANCE]
    print_fn(f"    [reembolsos] proveedores con reembolso en bitácora: {len(agg)}")
    return agg


def load_provider_blocks(path: Path | None, print_fn=print) -> dict:
    """Lee el archivo 'Proveedores por bloque' → dict {vendor_number: 'Bloque N'}.

    Cada columna del archivo es un bloque y sus valores son números de proveedor.
    Sirve para etiquetar cada proveedor con su bloque en la salida. Devuelve {} si no hay archivo.
    """
    if path is None or not Path(path).exists():
        return {}
    df = pd.read_excel(path, sheet_name=0)
    mapping: dict = {}
    for col in df.columns:
        label = str(col).strip()
        for v in _normalize_vendor(df[col].dropna().astype(str)):
            mapping.setdefault(v, label)  # si un proveedor aparece en 2 bloques, gana el primero
    print_fn(f"    [bloques] proveedores mapeados a bloque: {len(mapping)}")
    return mapping


# ---------------------------------------------------------------------------
# Bitácora (montos validados por el auditor) — hoja 'Bitacora'
# ---------------------------------------------------------------------------

_BITA_SHEET = "Bitacora"
_BITA_HEADER = 5  # encabezados en la fila 6 (0-based = 5)


def _find_col(cols, *subs) -> str | None:
    """Primera columna cuyo nombre contiene TODOS los substrings (case-insensitive)."""
    for c in cols:
        if isinstance(c, str) and all(s.lower() in c.lower() for s in subs):
            return c
    return None


_BITA_OUT_COLS = [
    _PAN_VENDOR, "Bita Nombre", "Bita Penalizacion c/imp", "Bita Final antes imptos",
    "Bita Final con imptos", "Bita Reembolso antes imptos", "Bita Reembolso con imptos",
]


def load_bitacora_montos(bitacora_path: Path | None, print_fn=print) -> pd.DataFrame:
    """Lee la hoja 'Bitacora' (montos VALIDADOS por el auditor) por proveedor.

    Devuelve por proveedor (Vendor number):
      - Penalización con Imptos (G)             → bruto sin descontar reembolso
      - Final (antes imptos)   (K)              → neto (penaliz. − reembolso), antes de imptos
      - Final con imptos       (N)              → neto final, con imptos
      - Soportado no procede antes impto (W)    → reembolso antes de imptos
      - Soportado con Imptos   (Z)              → reembolso con imptos
    """
    if bitacora_path is None or not Path(bitacora_path).exists():
        print_fn(f"    [bitacora] no encontrada: {bitacora_path}")
        return pd.DataFrame(columns=_BITA_OUT_COLS)

    df = pd.read_excel(bitacora_path, sheet_name=_BITA_SHEET, header=_BITA_HEADER)
    cols = list(df.columns)
    c_prov = _find_col(cols, "Proveedor")
    c_g = _find_col(cols, "Penaliz", "Imptos")
    c_k = _find_col(cols, "Final", "antes")
    c_n = _find_col(cols, "Final con imptos")
    c_w = _find_col(cols, "Soportado", "antes")
    c_z = _find_col(cols, "Soportado con Imptos")

    faltan = [n for n, c in [
        ("Proveedor", c_prov), ("Penalizacion c/imp", c_g), ("Final antes", c_k),
        ("Final con imptos", c_n), ("Soportado antes", c_w), ("Soportado c/imp", c_z),
    ] if c is None]
    if faltan:
        print_fn(f"    [bitacora] columnas no encontradas: {faltan} — se omite validación Bitácora.")
        return pd.DataFrame(columns=_BITA_OUT_COLS)

    df = df[df[c_prov].notna()].copy()
    # Nombre del proveedor: columna 'Nombre' (o la que sigue a 'Proveedor').
    c_name = _find_col(cols, "Nombre")
    if c_name is None:
        prov_pos = cols.index(c_prov)
        c_name = cols[prov_pos + 1] if prov_pos + 1 < len(cols) else None

    out = pd.DataFrame({
        _PAN_VENDOR: _normalize_vendor(df[c_prov]),
        "Bita Nombre": (
            df[c_name].fillna("").astype(str).str.strip() if c_name is not None else ""
        ),
        "Bita Penalizacion c/imp":     pd.to_numeric(df[c_g], errors="coerce").fillna(0.0),
        "Bita Final antes imptos":     pd.to_numeric(df[c_k], errors="coerce").fillna(0.0),
        "Bita Final con imptos":       pd.to_numeric(df[c_n], errors="coerce").fillna(0.0),
        "Bita Reembolso antes imptos": pd.to_numeric(df[c_w], errors="coerce").fillna(0.0),
        "Bita Reembolso con imptos":   pd.to_numeric(df[c_z], errors="coerce").fillna(0.0),
    })
    _num_cols = [c for c in out.columns if c not in (_PAN_VENDOR, "Bita Nombre")]
    out = out.groupby(_PAN_VENDOR, as_index=False).agg(
        {"Bita Nombre": "first", **{c: "sum" for c in _num_cols}}
    )
    print_fn(f"    [bitacora] proveedores: {len(out)}")
    return out


# Bitácora Sep-Dic ("resto 2025"): estructura DISTINTA a Ene-Ago.
# Hoja 'Bitacora Cargos NS resto 2025', header fila 4, sin columna "Final".
# Reembolso = Soportado (no procede): X (antes) / AA (con imptos). Final = Pen − Soportado.
_BITA_RESTO_HEADER = 3  # header en la fila 4 (0-based = 3)


def load_bitacora_montos_resto(bitacora_path: Path | None, print_fn=print) -> pd.DataFrame:
    """Lee la bitácora del formato 'resto 2025' (Sep-Dic) y devuelve las MISMAS columnas
    estandarizadas que `load_bitacora_montos`, para reutilizar `compare_bitacora_panoptic`.

    Mapeo (confirmado con Oscar): Penalización con imptos = 'Pen con Imptos';
    Penalización sin imptos = 'Pen sin Imptos'; Reembolso = 'Soportado (no procede)'
    (antes / con imptos); Final = Penalización − Soportado.
    """
    if bitacora_path is None or not Path(bitacora_path).exists():
        print_fn(f"    [bitacora resto] no encontrada: {bitacora_path}")
        return pd.DataFrame(columns=_BITA_OUT_COLS)

    xl = pd.ExcelFile(bitacora_path)
    sheet = (
        next((s for s in xl.sheet_names if "bitacora" in s.lower() and "resto" in s.lower()), None)
        or next((s for s in xl.sheet_names if s.lower().startswith("bitacora")), None)
    )
    if sheet is None:
        print_fn(f"    [bitacora resto] no se encontró hoja 'Bitacora...' en {bitacora_path}")
        return pd.DataFrame(columns=_BITA_OUT_COLS)

    df = pd.read_excel(xl, sheet_name=sheet, header=_BITA_RESTO_HEADER)
    cols = list(df.columns)
    c_prov = _find_col(cols, "Proveedor")
    c_pen_sin = _find_col(cols, "Pen sin Imptos")
    c_pen_con = _find_col(cols, "Pen con Imptos")
    c_sop_antes = _find_col(cols, "Soportado", "antes")
    c_sop_con = _find_col(cols, "Soportado con Imptos")

    faltan = [n for n, c in [
        ("Proveedor", c_prov), ("Pen sin Imptos", c_pen_sin), ("Pen con Imptos", c_pen_con),
        ("Soportado antes", c_sop_antes), ("Soportado con Imptos", c_sop_con),
    ] if c is None]
    if faltan:
        print_fn(f"    [bitacora resto] columnas no encontradas: {faltan} — se omite validación.")
        return pd.DataFrame(columns=_BITA_OUT_COLS)

    df = df[df[c_prov].notna()].copy()
    # Nombre del proveedor = la columna que sigue a 'Proveedor' (aquí se llama 'Prov').
    prov_pos = cols.index(c_prov)
    c_name = cols[prov_pos + 1] if prov_pos + 1 < len(cols) else None

    def num(c):
        return pd.to_numeric(df[c], errors="coerce").fillna(0.0)

    pen_sin, pen_con = num(c_pen_sin), num(c_pen_con)
    sop_antes, sop_con = num(c_sop_antes), num(c_sop_con)

    out = pd.DataFrame({
        _PAN_VENDOR: _normalize_vendor(df[c_prov]),
        "Bita Nombre": (df[c_name].fillna("").astype(str).str.strip() if c_name is not None else ""),
        "Bita Penalizacion c/imp":     pen_con,
        "Bita Final antes imptos":     pen_sin - sop_antes,
        "Bita Final con imptos":       pen_con - sop_con,
        "Bita Reembolso antes imptos": sop_antes,
        "Bita Reembolso con imptos":   sop_con,
    })
    _num_cols = [c for c in out.columns if c not in (_PAN_VENDOR, "Bita Nombre")]
    out = out.groupby(_PAN_VENDOR, as_index=False).agg(
        {"Bita Nombre": "first", **{c: "sum" for c in _num_cols}}
    )
    print_fn(f"    [bitacora resto] proveedores: {len(out)}")
    return out


def compare_bitacora_panoptic(
    ns: pd.DataFrame, bita: pd.DataFrame, print_fn=print
) -> tuple[pd.DataFrame, set[str]]:
    """VALIDACIÓN PRIMARIA — ¿Panoptic replica lo que el auditor validó en la Bitácora?

    Por proveedor compara:
      - Bitácora Final (antes imptos)  vs  Σ Panoptic Net claim amount
      - Bitácora Final con imptos      vs  Σ Panoptic (Net + Tax)
    y marca si el proveedor tiene reembolso (Soportado con Imptos > 0).
    Devuelve (tabla comparativa, set de proveedores que coinciden).
    """
    pan = ns.groupby(_PAN_VENDOR).agg(
        pan_net=(_PAN_NET, "sum"), pan_tax=(_PAN_TAX, "sum"),
    )
    pan["pan_net_tax"] = pan["pan_net"] + pan["pan_tax"]
    names = (
        ns.groupby(_PAN_VENDOR)["Vendor name"].first()
        if "Vendor name" in ns.columns else pd.Series(dtype=str)
    )
    bita_by = bita.set_index(_PAN_VENDOR) if not bita.empty else pd.DataFrame()

    all_vendors = set(pan.index.astype(str)) | set(bita_by.index.astype(str))
    rows: list[dict] = []
    matched: set[str] = set()

    for v in sorted(all_vendors):
        in_pan = v in pan.index
        in_bita = v in bita_by.index
        pan_net = float(pan.at[v, "pan_net"]) if in_pan else None
        pan_net_tax = float(pan.at[v, "pan_net_tax"]) if in_pan else None
        b = bita_by.loc[v] if in_bita else None
        b_final_antes = float(b["Bita Final antes imptos"]) if in_bita else None
        b_final_cimp = float(b["Bita Final con imptos"]) if in_bita else None
        b_reemb_cimp = float(b["Bita Reembolso con imptos"]) if in_bita else 0.0
        b_penal = float(b["Bita Penalizacion c/imp"]) if in_bita else None

        dif_antes = (pan_net - b_final_antes) if (in_pan and in_bita) else None
        dif_cimp = (pan_net_tax - b_final_cimp) if (in_pan and in_bita) else None

        if not in_bita:
            estado = "Solo en Panoptic (no en Bitácora)"
        elif not in_pan:
            estado = "Solo en Bitácora (no en Panoptic)"
        elif abs(dif_antes) <= _AMOUNT_TOLERANCE and abs(dif_cimp) <= _AMOUNT_TOLERANCE:
            estado = "Coincide"
            matched.add(v)
        else:
            estado = "NO coincide"

        # Nombre: preferir el de Panoptic; si el proveedor solo está en Bitácora, usar el de la bitácora.
        pn = names.get(v) if in_pan else None
        vname = "" if (pn is None or (isinstance(pn, float) and pd.isna(pn))) else str(pn).strip()
        if not vname and in_bita:
            vname = str(b.get("Bita Nombre", "") or "").strip()

        rows.append({
            _PAN_VENDOR: v,
            "Vendor name": vname,
            "Bita Penalización c/imp": b_penal,
            "Bita Final antes imptos": b_final_antes,
            "Panoptic Net claim": pan_net,
            "Dif antes imptos": dif_antes,
            "Bita Final con imptos": b_final_cimp,
            "Panoptic Net+Tax": pan_net_tax,
            "Dif con imptos": dif_cimp,
            "Bita Reembolso c/imp": b_reemb_cimp,
            "Tiene reembolso": "Sí" if abs(b_reemb_cimp) > _AMOUNT_TOLERANCE else "No",
            "Coincide": estado,
        })

    df = pd.DataFrame(rows)
    if not df.empty:
        # Ordenar: primero los que NO coinciden / faltantes, luego los que coinciden
        orden = {"NO coincide": 0, "Solo en Bitácora (no en Panoptic)": 1,
                 "Solo en Panoptic (no en Bitácora)": 2, "Coincide": 3}
        df = df.sort_values(by="Coincide", key=lambda s: s.map(orden)).reset_index(drop=True)
    print_fn(
        f"    [Bitácora vs Panoptic] coinciden: {len(matched)} | "
        f"total evaluados: {len(all_vendors)}"
    )
    return df, matched


# ---------------------------------------------------------------------------
# Cruce principal
# ---------------------------------------------------------------------------

@dataclass
class NivelServicioResult:
    output_path: Path | None = None
    posting_date_path: Path | None = None
    recoveries_path: Path | None = None
    matched_vendors: int = 0
    mismatched_vendors: int = 0
    panoptic_sin_ec: int = 0
    claims_para_carga: int = 0
    bita_coincide: int = 0
    bita_no_coincide: int = 0
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.error is None


def cross_nivel_servicio(
    df_pan_full: pd.DataFrame,
    blocks_dir: Path,
    bitacora_path: Path | None,
    output_dir: Path,
    solo_capa1: bool = False,
    print_fn=print,
    *,
    posting_ref: str = _NS_POSTING_REF,
    bitacora_loader=load_bitacora_montos,
    ec_period_filter=filter_ec_ns_ene_ago,
    out_subdir: str = "NS",
    out_prefix: str = "etapa3_NS",
    provider_block_map: dict | None = None,
    report_subtitles: dict | None = None,
) -> NivelServicioResult:
    """Cruza el EC consolidado de NS contra Panoptic y genera reporte + plantillas.

    Motor genérico usado por Etapa 3 (defaults) y Etapa 4 (parámetros):
    - posting_ref: valor de Posting reference a filtrar en Panoptic.
    - bitacora_loader: función que lee la bitácora → columnas estandarizadas.
    - ec_period_filter: filtro de periodo del EC (Ene-Ago `<` vs Sep-Dic `>=`).
    - out_subdir/out_prefix: carpeta y prefijo de los archivos de salida.
    - provider_block_map: {proveedor: 'Bloque N'} para etiquetar la salida (Etapa 4).

    solo_capa1=True → ejecuta SOLO la validación primaria Bitácora vs Panoptic
    (sin leer los bloques del EC, casi instantáneo) y termina.
    """
    # --- Panoptic NS: Posting reference = NS-EneAgo25 y Status != Rejected ---
    df_pan = df_pan_full.copy()
    _ensure_tax_column(df_pan)
    if _PAN_POSTING_REF not in df_pan.columns:
        raise ValueError(f"Panoptic no tiene la columna {_PAN_POSTING_REF!r}")

    ns = df_pan[df_pan[_PAN_POSTING_REF].astype(str).str.strip() == posting_ref].copy()
    print_fn(f"    Panoptic {posting_ref}: {len(ns)} filas")
    if _PAN_STATUS in ns.columns:
        ns = ns[ns[_PAN_STATUS].astype(str).str.strip() != _STATUS_EXCLUDE].copy()
    print_fn(f"    Panoptic NS no-Rejected: {len(ns)} filas ({ns[_PAN_VENDOR].nunique()} proveedores)")

    if ns.empty:
        raise ValueError(
            f"No hay claims con {posting_ref} (no-Rejected) en Panoptic. "
            f"¿El export es correcto?"
        )

    # Máscara ORIGINAL de Batch number vacío (antes de enriquecer)
    if _PAN_BATCH in ns.columns:
        batch_empty = ns[_PAN_BATCH].isna() | (
            ns[_PAN_BATCH].astype(str).str.strip().isin(["", "nan", "None", "NaT"])
        )
    else:
        ns[_PAN_BATCH] = None
        batch_empty = pd.Series(True, index=ns.index)
    ns["_batch_empty_orig"] = batch_empty
    print_fn(f"    Claims NS con Batch number vacío: {int(batch_empty.sum())} | con valor: {int((~batch_empty).sum())}")

    # --- VALIDACIÓN PRIMARIA: Bitácora (auditor) vs Panoptic ---
    # La bitácora tiene los montos VALIDADOS por el auditor; Panoptic debió replicarlos.
    bita = bitacora_loader(bitacora_path, print_fn=print_fn)
    df_bita_pan, bita_matched = compare_bitacora_panoptic(ns, bita, print_fn=print_fn)
    if provider_block_map and not df_bita_pan.empty:
        df_bita_pan.insert(1, "Bloque", df_bita_pan[_PAN_VENDOR].astype(str).map(provider_block_map))
    n_bita_no = (len(df_bita_pan) - len(bita_matched)) if not df_bita_pan.empty else 0
    n_pan_ns_total = int(ns[_PAN_VENDOR].nunique())

    # --- Modo SOLO CAPA 1: escribe solo la validación Bitácora vs Panoptic y termina ---
    # No lee los bloques del EC, así que es casi instantáneo.
    if solo_capa1:
        ns_dir = output_dir / out_subdir
        ns_dir.mkdir(parents=True, exist_ok=True)
        output_path = ns_dir / f"{out_prefix}_capa1.xlsx"
        resumen = pd.DataFrame([
            {"Métrica": "Proveedores Panoptic NS (no-Rejected)", "Valor": n_pan_ns_total},
            {"Métrica": "Capa 1 — Bitácora vs Panoptic: COINCIDEN", "Valor": len(bita_matched)},
            {"Métrica": "Capa 1 — Bitácora vs Panoptic: NO coinciden / faltantes", "Valor": n_bita_no},
            {"Métrica": "Capa 2 (EC / bloques)", "Valor": "NO EJECUTADA (--solo-capa1)"},
        ])
        with pd.ExcelWriter(output_path, engine="openpyxl") as writer:
            write_sheet(writer, resumen, "Resumen NS")
            write_sheet(writer, df_bita_pan, "Bitacora vs Panoptic")
            style_workbook(writer.book, subtitles=report_subtitles)
        print_fn(f"    Reporte Capa 1: {output_path}")
        return NivelServicioResult(
            output_path=output_path,
            bita_coincide=len(bita_matched),
            bita_no_coincide=n_bita_no,
        )

    # La CAPA 2 (EC) se evalúa SOLO sobre los proveedores que COINCIDIERON en la Capa 1.
    # (Si no hay bitácora, se evalúan todos, para no romper el flujo.)
    ec_scope = set(bita_matched) if not bita.empty else set(ns[_PAN_VENDOR].astype(str))
    print_fn(f"    Capa 2 (EC): se evaluarán {len(ec_scope)} proveedores (coincidentes de Capa 1).")

    # Asegurar columnas destino (object) para enriquecimiento
    for col in _ENRICHED_COLS:
        if col not in ns.columns:
            ns[col] = None
        ns[col] = ns[col].astype(object)

    # --- Consolidar y filtrar EC ---
    df_ec = consolidate_ec_blocks(blocks_dir, print_fn=print_fn)
    df_ec = ec_period_filter(df_ec, print_fn=print_fn)
    if df_ec.empty:
        raise ValueError("El EC consolidado quedó vacío tras filtros NS / fecha.")

    ec_net = _ec_net_by_vendor(df_ec)
    ec_vendors = set(df_ec[_EC_ACCOUNT].astype(str))

    # --- Cruce por proveedor: EC neto vs Panoptic bruto (Net + Tax) ---
    today = date.today()
    matched: set[str] = set()
    filled_by_row: dict = {}
    mismatch_rows: list[dict] = []

    ns_by_vendor = {v: idxs for v, idxs in ns.groupby(_PAN_VENDOR).groups.items()}

    for vendor, ec_row in ec_net.iterrows():
        vendor = str(vendor)
        if vendor not in ec_scope:
            continue  # fuera del alcance de Capa 2 (no coincidió en Capa 1)
        net_ec = float(ec_row["ec_net"])
        pan_idx = ns_by_vendor.get(vendor)
        if pan_idx is None:
            # Proveedor en EC pero no en Panoptic NS
            mismatch_rows.append({
                _PAN_VENDOR: vendor,
                "Vendor name": "",
                "EC Neto": net_ec,
                "EC Penalización": float(ec_row["ec_penal"]),
                "EC Reembolso (PB=L)": float(ec_row["ec_reembolso_L"]),
                "Panoptic Bruto (Net+Tax)": np.nan,
                "Diferencia": np.nan,
                "Motivo": "Proveedor en EC sin claims NS en Panoptic",
            })
            continue

        pan_idx = list(pan_idx)
        pan_gross = float(
            pd.to_numeric(ns.loc[pan_idx, _PAN_NET], errors="coerce").sum()
            + pd.to_numeric(ns.loc[pan_idx, _PAN_TAX], errors="coerce").sum()
        )
        diff = net_ec - pan_gross

        if abs(diff) <= _AMOUNT_TOLERANCE:
            matched.add(vendor)
            rep = _representative_ec_row(df_ec[df_ec[_EC_ACCOUNT] == vendor])
            # Rellena SOLO las columnas vacías de los claims del proveedor y rastrea
            # cuáles se actualizaron (para decidir qué claim va a cada plantilla).
            if rep is not None:
                _merge_filled(filled_by_row, _apply_ec_to_rows(ns, pan_idx, rep, today))
        else:
            vname = str(ns.loc[pan_idx, "Vendor name"].iloc[0]) if "Vendor name" in ns.columns else ""
            mismatch_rows.append({
                _PAN_VENDOR: vendor,
                "Vendor name": vname,
                "EC Neto": net_ec,
                "EC Penalización": float(ec_row["ec_penal"]),
                "EC Reembolso (PB=L)": float(ec_row["ec_reembolso_L"]),
                "Panoptic Bruto (Net+Tax)": pan_gross,
                "Diferencia": diff,
                "Motivo": "Monto EC distinto de Panoptic",
            })

    # --- Panoptic NS sin EC (solo dentro del alcance de Capa 2) ---
    ns_scope = ns[ns[_PAN_VENDOR].astype(str).isin(ec_scope)]
    _sinec_cols = [_PAN_VENDOR] + (["Vendor name"] if "Vendor name" in ns.columns else [])
    pan_sin_ec = (
        ns_scope[~ns_scope[_PAN_VENDOR].astype(str).isin(ec_vendors)]
        .drop_duplicates(subset=[_PAN_VENDOR])[_sinec_cols]
        .copy()
    )

    # --- Cruce exitoso ---
    # "Requiere carga" = se actualizó al menos una columna del claim con datos del EC.
    ns["Requiere carga"] = ns.index.map(lambda i: "Sí" if i in filled_by_row else "No")
    df_cruce_full = ns[ns[_PAN_VENDOR].astype(str).isin(matched)].copy()
    cruce_cols = [c for c in _CRUCE_COLS if c in df_cruce_full.columns]
    df_cruce_view = df_cruce_full[cruce_cols].copy()
    if provider_block_map and not df_cruce_view.empty:
        _pos = df_cruce_view.columns.get_loc(_PAN_VENDOR) + 1
        df_cruce_view.insert(_pos, "Bloque", df_cruce_view[_PAN_VENDOR].astype(str).map(provider_block_map))

    # --- Reembolsos cross-check ---
    df_reemb = load_reembolsos_bitacora(bitacora_path, print_fn=print_fn)
    if not df_reemb.empty:
        ec_L = (
            df_ec[df_ec["_pb"] == _EC_REEMBOLSO_PB]
            .groupby(_EC_ACCOUNT)[_EC_AMOUNT].sum()
        )
        pan_ns_vendors = set(ns[_PAN_VENDOR].astype(str))
        df_reemb = df_reemb.copy()
        df_reemb["EC Reembolso (PB=L)"] = df_reemb[_PAN_VENDOR].map(
            lambda v: float(ec_L.get(str(v), 0.0))
        )
        df_reemb["En Panoptic NS"] = df_reemb[_PAN_VENDOR].map(
            lambda v: "Sí" if str(v) in pan_ns_vendors else "No"
        )
        df_reemb["EC tiene línea PB=L"] = df_reemb["EC Reembolso (PB=L)"].map(
            lambda x: "Sí" if abs(x) > _AMOUNT_TOLERANCE else "No"
        )

    df_mismatch = pd.DataFrame(mismatch_rows)

    # --- Resumen ---
    claims_carga = int((df_cruce_full["Requiere carga"] == "Sí").sum()) if not df_cruce_full.empty else 0
    resumen = pd.DataFrame([
        {"Métrica": "Proveedores Panoptic NS (no-Rejected)", "Valor": n_pan_ns_total},
        {"Métrica": "Capa 1 — Bitácora vs Panoptic: COINCIDEN", "Valor": len(bita_matched)},
        {"Métrica": "Capa 1 — Bitácora vs Panoptic: NO coinciden / faltantes", "Valor": n_bita_no},
        {"Métrica": "Capa 2 — Proveedores evaluados (coincidentes de Capa 1)", "Valor": len(ec_scope)},
        {"Métrica": "Capa 2 — Proveedores EC (Ene-Ago)", "Valor": len(ec_vendors)},
        {"Métrica": "Capa 2 — EC vs Panoptic: coinciden", "Valor": len(matched)},
        {"Métrica": "Capa 2 — EC vs Panoptic: descuadre / sin match", "Valor": len(df_mismatch)},
        {"Métrica": "Capa 2 — Panoptic sin EC", "Valor": len(pan_sin_ec)},
        {"Métrica": "Claims para carga (con actualización)", "Valor": claims_carga},
        {"Métrica": "Proveedores con reembolso en bitácora", "Valor": len(df_reemb)},
    ])

    # --- Escribir salida ---
    ns_dir = output_dir / out_subdir
    ns_dir.mkdir(parents=True, exist_ok=True)
    output_path = ns_dir / f"{out_prefix}.xlsx"

    with pd.ExcelWriter(output_path, engine="openpyxl") as writer:
        write_sheet(writer, resumen, "Resumen NS")
        write_sheet(writer, df_bita_pan, "Bitacora vs Panoptic")
        write_sheet(writer, df_cruce_view, "Cruce Exitoso")
        write_sheet(writer, df_mismatch, "Sin Coincidencia")
        write_sheet(writer, pan_sin_ec, "Panoptic Sin EC")
        write_sheet(writer, df_reemb, "Reembolsos")
        style_workbook(writer.book, subtitles=report_subtitles)

    print_fn(f"    Reporte: {output_path}")

    # --- Plantillas: SOLO los claims donde se actualizó alguna columna de ESA plantilla ---
    posting_path = recoveries_path = None
    posting_idx = _rows_updated_in(filled_by_row, _POSTING_DATE_COLS)
    recov_idx   = _rows_updated_in(filled_by_row, _RECOVERY_COLS)
    if posting_idx:
        posting_path = generate_posting_date_template(
            ns.loc[posting_idx], ns_dir / f"{out_prefix}_PostingDate.xlsx"
        )
        print_fn(f"    Plantilla PostingDate: {len(posting_idx)} claims -> {posting_path}")
    if recov_idx:
        recoveries_path = generate_recoveries_template(
            ns.loc[recov_idx], ns_dir / f"{out_prefix}_Recoveries.xlsx"
        )
        print_fn(f"    Plantilla Recoveries:  {len(recov_idx)} claims -> {recoveries_path}")
    if not posting_idx and not recov_idx:
        print_fn("    (sin claims con actualización; no se generan plantillas)")

    return NivelServicioResult(
        output_path=output_path,
        posting_date_path=posting_path,
        recoveries_path=recoveries_path,
        matched_vendors=len(matched),
        mismatched_vendors=len(df_mismatch),
        panoptic_sin_ec=len(pan_sin_ec),
        claims_para_carga=claims_carga,
        bita_coincide=len(bita_matched),
        bita_no_coincide=n_bita_no,
    )


# ---------------------------------------------------------------------------
# API pública
# ---------------------------------------------------------------------------

_DEFAULT_BLOCKS_DIR = Path(r"X:\Soriana\00 - AUDITORIA 2020 - 2024\BLOQUES ESTADO CUENTA")
_DEFAULT_BITACORA = PROJECT_ROOT / "data" / "referencias" / "BITACORA_ACLARACIONES_NS 2025 (2).xlsx"


def run_nivel_servicio_from_file(
    raw_panoptic_path: Path,
    blocks_dir: Path,
    bitacora_path: Path | None,
    output_dir: Path,
    solo_capa1: bool = False,
    print_fn=print,
) -> NivelServicioResult:
    """Carga un Panoptic ya descargado y ejecuta el cruce de Etapa 3."""
    print_fn(f"  Cargando Panoptic: {raw_panoptic_path}")
    df_pan = _load_panoptic(raw_panoptic_path)
    return cross_nivel_servicio(
        df_pan, blocks_dir, bitacora_path, output_dir,
        solo_capa1=solo_capa1, print_fn=print_fn,
    )


# ---------------------------------------------------------------------------
# Etapa 4 — Nivel de Servicio Sep-Dic 2025 (clon parametrizado de Etapa 3)
# ---------------------------------------------------------------------------

_SEPTDIC_POSTING_REF = "NS-SeptDic 2025"
_DEFAULT_BITACORA_SEPTDIC = Path(
    r"X:\Soriana\00 - AUDITORIA 2020 - 2024\BLOQUES ESTADO CUENTA\BITACORAS\BITACORA NS resto 2025.xlsx"
)
_DEFAULT_PROVIDER_BLOCKS = PROJECT_ROOT / "data" / "referencias" / "Proveedores_bloque_Sep-Dic 25.xlsx"


def run_nivel_servicio_septdic_from_file(
    raw_panoptic_path: Path,
    blocks_dir: Path,
    bitacora_path: Path | None,
    output_dir: Path,
    provider_blocks_path: Path | None = None,
    solo_capa1: bool = False,
    print_fn=print,
) -> NivelServicioResult:
    """Etapa 4 (Sep-Dic 2025): reutiliza el motor de Etapa 3 con parámetros distintos.

    Posting reference `NS-SeptDic 2025`, bitácora formato 'resto', EC filtrado a
    Document Date >= 19-jun-2026, y etiqueta cada proveedor con su bloque (1-6).
    """
    print_fn(f"  Cargando Panoptic: {raw_panoptic_path}")
    df_pan = _load_panoptic(raw_panoptic_path)
    block_map = load_provider_blocks(provider_blocks_path, print_fn=print_fn)
    subtitles = {
        "Resumen NS":           "Etapa 4 — Nivel de Servicio (NS-SeptDic 2025) — Resumen",
        "Bitacora vs Panoptic": "Etapa 4 — Bitácora (auditor) vs Panoptic  [validación primaria]",
        "Cruce Exitoso":        "Etapa 4 — Cruce Exitoso (EC vs Panoptic)",
        "Sin Coincidencia":     "Etapa 4 — Sin Coincidencia (EC vs Panoptic)",
        "Panoptic Sin EC":      "Etapa 4 — Proveedores Panoptic sin Estado de Cuenta",
        "Reembolsos":           "Etapa 4 — Reembolsos (cross-check)",
    }
    return cross_nivel_servicio(
        df_pan, blocks_dir, bitacora_path, output_dir,
        solo_capa1=solo_capa1, print_fn=print_fn,
        posting_ref=_SEPTDIC_POSTING_REF,
        bitacora_loader=load_bitacora_montos_resto,
        ec_period_filter=filter_ec_ns_septdic,
        out_subdir="NS_SeptDic",
        out_prefix="etapa4_NS_SeptDic",
        provider_block_map=block_map,
        report_subtitles=subtitles,
    )
