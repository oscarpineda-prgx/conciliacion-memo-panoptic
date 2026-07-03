"""Tests de la lógica de conciliación MEMO × Panoptic.

Cubre las 5 funciones internas críticas de processing.py:
  - _p1_filter_mask          → los 5 filtros de P1 + extensiones
  - _paso1_asignar_memo      → asignación de memo_id, bulk update, validación cruzada
  - _paso1_reejecutar_diferencias → segunda pasada con Stage/Status Invoice
  - _cruce_resumen           → P2 + P3 (vendor status, amount status)
  - _paso4_duplicados        → duplicados en MEMO por clave de 7 campos

Cómo correr los tests:
    .venv\\Scripts\\python.exe -m pytest tests/test_processing.py -v
"""
from __future__ import annotations

import pandas as pd
import pytest

from conciliacion_memo_panoptic.conciliation.processing import (
    _agregar_periodos_incon_montos,
    _compute_duplicados_x_memo,
    _cruce_resumen,
    _identificar_diferencias_x_monto,
    _p1_filter_mask,
    _paso1_asignar_memo,
    _paso1_reejecutar_diferencias,
    _paso4_duplicados,
)


# ---------------------------------------------------------------------------
# Helpers — constructores de filas mínimas
# ---------------------------------------------------------------------------

def _pan(**overrides) -> dict:
    """Fila de Panoptic con valores válidos por defecto."""
    row = {
        "Vendor number":            "1001",
        "Vendor name":              "Proveedor Test SA",
        "Project name":             "MEX_SORIANA_Scope_2020",
        "Posting reference number": "",
        "Claim cause description":  "Descuento comercial",
        "Stage":                    "Posting",
        "Status":                   "In Review",
        "Net claim amount":         100.0,
        "Total tax amount":         16.0,
        "Financial year of origin": 2023,
        "Claim number":             "CLM-001",
        "Assigned to":              "oscar",
    }
    row.update(overrides)
    return row


def _memo_ca(**overrides) -> dict:
    """Fila de MontoxConceptoxAño con valores por defecto."""
    row = {
        "Num Proveedor":         "1001",
        "Año":                   2023,
        "Proveedor":             "Proveedor Test SA",
        "Concepto":              "MERMA DE ORIGEN",
        "Num Categoria":         "CAT001",
        "Monto antes impuestos": 100.0,
        "IEPS":                  0.0,
        "IVA":                   16.0,
    }
    row.update(overrides)
    return row


def _memo_pf(**overrides) -> dict:
    """Fila de MontoxProveedorxFase con valores por defecto."""
    row = {
        "Num Proveedor":         "1001",
        "Proveedor":             "Proveedor Test SA",
        "Monto antes impuestos": 100.0,
        "IEPS":                  0.0,
        "IVA":                   16.0,
        "Monto Total":           116.0,
    }
    row.update(overrides)
    return row


def _df_pan(*rows) -> pd.DataFrame:
    return pd.DataFrame(rows if rows else [_pan()])


def _df_ca(*rows) -> pd.DataFrame:
    return pd.DataFrame(rows if rows else [_memo_ca()])


def _df_pf(*rows) -> pd.DataFrame:
    return pd.DataFrame(rows if rows else [_memo_pf()])


# ---------------------------------------------------------------------------
# _p1_filter_mask
# ---------------------------------------------------------------------------

class TestP1FilterMask:

    def test_fila_valida_pasa(self):
        mask = _p1_filter_mask(_df_pan(_pan()))
        assert mask.all()

    def test_excluye_project_name_scope_2019(self):
        df = _df_pan(_pan(**{"Project name": "MEX_SORIANA_Scope_2019"}))
        assert not _p1_filter_mask(df).any()

    def test_excluye_posting_reference_ns_eneago25(self):
        df = _df_pan(_pan(**{"Posting reference number": "NS-EneAgo25"}))
        assert not _p1_filter_mask(df).any()

    def test_excluye_claim_cause_limitation(self):
        df = _df_pan(_pan(**{"Claim cause description": "Limitation in a systems functionality"}))
        assert not _p1_filter_mask(df).any()

    def test_excluye_stage_invalido(self):
        df = _df_pan(_pan(**{"Stage": "Invoice"}))
        assert not _p1_filter_mask(df).any()

    def test_excluye_status_invalido(self):
        df = _df_pan(_pan(**{"Status": "Closed"}))
        assert not _p1_filter_mask(df).any()

    def test_stage_vendor_pasa(self):
        df = _df_pan(_pan(**{"Stage": "Vendor"}))
        assert _p1_filter_mask(df).all()

    def test_status_posted_pasa(self):
        df = _df_pan(_pan(**{"Status": "Posted"}))
        assert _p1_filter_mask(df).all()

    def test_extra_stages_agrega_invoice(self):
        df = _df_pan(_pan(**{"Stage": "Invoice"}))
        # Sin extra_stages: Invoice no pasa
        assert not _p1_filter_mask(df).any()
        # Con extra_stages={"Invoice"}: sí pasa
        assert _p1_filter_mask(df, extra_stages={"Invoice"}).all()

    def test_extra_statuses_agrega_invoice_ready(self):
        df = _df_pan(_pan(**{"Stage": "Invoice", "Status": "Invoice ready"}))
        mask_base = _p1_filter_mask(df, extra_stages={"Invoice"})
        assert not mask_base.any()  # Status "Invoice ready" aún excluido

        mask_ext = _p1_filter_mask(
            df,
            extra_stages={"Invoice"},
            extra_statuses={"Invoice ready", "Invoiced"},
        )
        assert mask_ext.all()

    def test_extra_statuses_agrega_invoiced(self):
        df = _df_pan(_pan(**{"Stage": "Invoice", "Status": "Invoiced"}))
        mask = _p1_filter_mask(
            df,
            extra_stages={"Invoice"},
            extra_statuses={"Invoice ready", "Invoiced"},
        )
        assert mask.all()

    def test_mix_validas_e_invalidas(self):
        df = _df_pan(
            _pan(),                                                        # válida
            _pan(**{"Project name": "MEX_SORIANA_Scope_2019"}),            # inválida
            _pan(**{"Stage": "Vendor", "Status": "Posted"}),               # válida
            _pan(**{"Claim cause description": "Limitation in a systems functionality"}),  # inválida
        )
        mask = _p1_filter_mask(df)
        assert mask.tolist() == [True, False, True, False]


# ---------------------------------------------------------------------------
# _paso1_asignar_memo
# ---------------------------------------------------------------------------

class TestPaso1AsignarMemo:

    def _run(self, pan_rows, ca_rows, memo_id="M040", vendor_sets=None):
        df = pd.DataFrame(pan_rows)
        ca  = pd.DataFrame(ca_rows)
        actualizados, diferencias, claims = _paso1_asignar_memo(
            df, ca, memo_id, vendor_sets or {}
        )
        return df, actualizados, diferencias, claims

    def test_proveedor_que_cuadra_va_a_actualizados(self):
        # Panoptic: vendor 1001, año 2023, Net=100, Tax=16 → Gross=116
        # MEMO CA:  vendor 1001, año 2023, Total = 100+0+16 = 116
        df, act, dif, _ = self._run(
            [_pan(**{"Net claim amount": 100.0, "Total tax amount": 16.0})],
            [_memo_ca(**{"Monto antes impuestos": 100.0, "IEPS": 0.0, "IVA": 16.0})],
        )
        assert len(act) == 1
        assert len(dif) == 0
        assert df.loc[0, "Posting reference number"] == "M040"

    def test_proveedor_que_no_cuadra_va_a_diferencias(self):
        # MEMO dice 200 pero Panoptic tiene 116
        _, act, dif, _ = self._run(
            [_pan(**{"Net claim amount": 100.0, "Total tax amount": 16.0})],
            [_memo_ca(**{"Monto antes impuestos": 180.0, "IEPS": 0.0, "IVA": 20.0})],
        )
        assert len(act) == 0
        assert len(dif) == 1

    def test_proveedor_en_memo_pero_no_en_panoptic_va_a_diferencias(self):
        # Panoptic tiene vendor 9999, MEMO pide vendor 1001
        _, act, dif, _ = self._run(
            [_pan(**{"Vendor number": "9999"})],
            [_memo_ca(**{"Num Proveedor": "1001"})],
        )
        assert len(dif) == 1
        assert dif.iloc[0]["Vendor number"] == "1001"

    def test_ya_tiene_memo_correcto_no_se_toca(self):
        # Ya tiene M040 asignado correctamente
        df, act, _, _ = self._run(
            [_pan(**{"Posting reference number": "M040"})],
            [_memo_ca()],
        )
        # Sigue con M040 (no fue borrado ni reasignado)
        assert df.loc[0, "Posting reference number"] == "M040"

    def test_memo_incorrecto_vendor_no_esta_en_ese_memo_se_sobreescribe(self):
        # Tiene M041 asignado, pero vendor 1001 NO está en M041 → corregir a M040
        df, act, _, _ = self._run(
            [_pan(**{"Posting reference number": "M041"})],
            [_memo_ca()],
            vendor_sets={"M041": {"9999"}},  # M041 tiene vendor 9999, NO el 1001
        )
        assert df.loc[0, "Posting reference number"] == "M040"
        assert len(act) == 1

    def test_memo_incorrecto_vendor_si_esta_en_ese_memo_no_se_toca(self):
        # Tiene M041 asignado, y vendor 1001 SÍ está en M041 → conservar M041
        df, _, dif, _ = self._run(
            [_pan(**{"Posting reference number": "M041"})],
            [_memo_ca()],
            vendor_sets={"M041": {"1001"}},  # M041 sí tiene vendor 1001
        )
        assert df.loc[0, "Posting reference number"] == "M041"

    def test_tolerancia_exactamente_1_peso_actualiza(self):
        # Gross Panoptic = 115, MEMO = 116 → diferencia = 1.0 → dentro de tolerancia
        _, act, dif, _ = self._run(
            [_pan(**{"Net claim amount": 99.0, "Total tax amount": 16.0})],
            [_memo_ca(**{"Monto antes impuestos": 100.0, "IVA": 16.0})],
        )
        assert len(act) == 1
        assert len(dif) == 0

    def test_diferencia_mayor_a_1_peso_va_a_diferencias(self):
        # Gross Panoptic = 114.99, MEMO = 116 → diferencia = 1.01 → fuera de tolerancia
        _, act, dif, _ = self._run(
            [_pan(**{"Net claim amount": 98.99, "Total tax amount": 16.0})],
            [_memo_ca(**{"Monto antes impuestos": 100.0, "IVA": 16.0})],
        )
        assert len(act) == 0
        assert len(dif) == 1

    def test_genera_filas_para_bulk_update(self):
        _, _, _, claims = self._run(
            [_pan(**{"Posting reference number": "", "Claim number": "CLM-999"})],
            [_memo_ca()],
        )
        assert len(claims) == 1
        assert "Claim number" in claims.columns

    def test_varios_años_mismo_vendor_se_cruzan_por_año(self):
        # Vendor 1001 tiene claims en 2022 y 2023
        # MEMO solo tiene año 2023 → solo se asigna el de 2023
        _, act, dif, _ = self._run(
            [
                _pan(**{"Financial year of origin": 2022, "Net claim amount": 50.0, "Total tax amount": 8.0}),
                _pan(**{"Financial year of origin": 2023, "Net claim amount": 100.0, "Total tax amount": 16.0}),
            ],
            [_memo_ca(**{"Año": 2023, "Monto antes impuestos": 100.0, "IVA": 16.0})],
        )
        assert len(act) == 1
        assert act.iloc[0]["Año"] == 2023
        assert len(dif) == 0  # el año 2022 no está en el MEMO, no va a diferencias


# ---------------------------------------------------------------------------
# _paso1_reejecutar_diferencias
# ---------------------------------------------------------------------------

class TestPaso1ReejecutarDiferencias:

    def _diferencias(self, vendor="1001", ano=2023, pan_gross=0.0, memo_total=116.0):
        """Crea un df_diferencias mínimo (output de _paso1_asignar_memo)."""
        return pd.DataFrame([{
            "Vendor number":         vendor,
            "Proveedor (MEMO)":      "Proveedor Test SA",
            "Año":                   ano,
            "Net claim amount":      0.0,
            "Total tax amount":      0.0,
            "Gross Panoptic (P1)":   pan_gross,
            "Monto antes impuestos": 100.0,
            "IEPS":                  0.0,
            "IVA":                   16.0,
            "Monto Total (MEMO)":    memo_total,
            "Diferencia":            memo_total - pan_gross,
        }])

    def test_cuadra_con_stage_invoice_y_status_invoice_ready(self):
        df_pan = _df_pan(_pan(**{
            "Stage": "Invoice", "Status": "Invoice ready",
            "Net claim amount": 100.0, "Total tax amount": 16.0,
        }))
        dif = self._diferencias(memo_total=116.0)
        result = _paso1_reejecutar_diferencias(df_pan, _df_ca(), dif)
        assert len(result) == 1
        assert result.iloc[0]["Estado"] == "Cruce exitoso"

    def test_cuadra_con_status_invoiced(self):
        df_pan = _df_pan(_pan(**{
            "Stage": "Invoice", "Status": "Invoiced",
            "Net claim amount": 100.0, "Total tax amount": 16.0,
        }))
        dif = self._diferencias(memo_total=116.0)
        result = _paso1_reejecutar_diferencias(df_pan, _df_ca(), dif)
        assert len(result) == 1

    def test_no_cuadra_aunque_agrega_invoice_retorna_vacio(self):
        df_pan = _df_pan(_pan(**{
            "Stage": "Invoice", "Status": "Invoice ready",
            "Net claim amount": 50.0, "Total tax amount": 8.0,  # Gross=58, MEMO=116
        }))
        dif = self._diferencias(memo_total=116.0)
        result = _paso1_reejecutar_diferencias(df_pan, _df_ca(), dif)
        assert len(result) == 0

    def test_diferencias_vacias_retorna_dataframe_vacio(self):
        dif_vacio = pd.DataFrame()
        result = _paso1_reejecutar_diferencias(_df_pan(), _df_ca(), dif_vacio)
        assert result.empty

    def test_no_modifica_df_pan(self):
        df_pan = _df_pan(_pan(**{
            "Stage": "Invoice", "Status": "Invoice ready",
            "Posting reference number": "",
        }))
        posting_antes = df_pan["Posting reference number"].copy()
        dif = self._diferencias(memo_total=116.0)
        _paso1_reejecutar_diferencias(df_pan, _df_ca(), dif)
        # df_pan no debe haber sido modificado
        pd.testing.assert_series_equal(df_pan["Posting reference number"], posting_antes)

    def test_stage_posting_con_status_invoice_ready_si_pasa(self):
        # Stage=Posting + Status=Invoice ready: el filtro extendido amplía stages Y statuses
        # de forma independiente, así que Posting+Invoice ready también se captura.
        df_pan = _df_pan(_pan(**{
            "Stage": "Posting", "Status": "Invoice ready",
            "Net claim amount": 100.0, "Total tax amount": 16.0,
        }))
        dif = self._diferencias(memo_total=116.0)
        result = _paso1_reejecutar_diferencias(df_pan, _df_ca(), dif)
        assert len(result) == 1

    def test_status_closed_no_pasa_aunque_stage_sea_invoice(self):
        # Status desconocido (Closed) no está en ninguna lista → no pasa
        df_pan = _df_pan(_pan(**{
            "Stage": "Invoice", "Status": "Closed",
            "Net claim amount": 100.0, "Total tax amount": 16.0,
        }))
        dif = self._diferencias(memo_total=116.0)
        result = _paso1_reejecutar_diferencias(df_pan, _df_ca(), dif)
        assert len(result) == 0


# ---------------------------------------------------------------------------
# _cruce_resumen
# ---------------------------------------------------------------------------

class TestCruceResumen:

    def test_match_monto_ok(self):
        # Panoptic Gross = 116, MEMO Total = 116 → Match + OK
        pan  = _df_pan(_pan(**{"Net claim amount": 100.0, "Total tax amount": 16.0}))
        memo = _df_pf(_memo_pf(**{"Monto Total": 116.0}))
        cruce = _cruce_resumen(pan, memo)
        row = cruce[cruce["Vendor number"] == "1001"].iloc[0]
        assert row["Vendor Status"] == "Match"
        assert row["Amount Status"] == "OK"

    def test_match_monto_mismatch(self):
        # Panoptic Gross = 116, MEMO Total = 200 → Match + Mismatch
        pan  = _df_pan(_pan(**{"Net claim amount": 100.0, "Total tax amount": 16.0}))
        memo = _df_pf(_memo_pf(**{"Monto Total": 200.0}))
        cruce = _cruce_resumen(pan, memo)
        row = cruce[cruce["Vendor number"] == "1001"].iloc[0]
        assert row["Vendor Status"] == "Match"
        assert row["Amount Status"] == "Mismatch"

    def test_missing_in_memo(self):
        # Vendor 1001 en Panoptic pero NO en MEMO
        pan  = _df_pan(_pan(**{"Vendor number": "1001"}))
        memo = _df_pf(_memo_pf(**{"Num Proveedor": "9999"}))
        cruce = _cruce_resumen(pan, memo)
        row_1001 = cruce[cruce["Vendor number"] == "1001"].iloc[0]
        assert row_1001["Vendor Status"] == "Missing in MEMO"

    def test_missing_in_panoptic(self):
        # Vendor 9999 en MEMO pero NO en Panoptic
        pan  = _df_pan(_pan(**{"Vendor number": "1001"}))
        memo = _df_pf(_memo_pf(**{"Num Proveedor": "9999"}))
        cruce = _cruce_resumen(pan, memo)
        row_9999 = cruce[cruce["Vendor number"] == "9999"].iloc[0]
        assert row_9999["Vendor Status"] == "Missing in Panoptic"

    def test_limitation_excluida_del_calculo_de_monto(self):
        # Panoptic: dos filas para vendor 1001
        #   Fila A: Net=100, Tax=16 → válida
        #   Fila B: Net=500, Tax=80, Claim cause = Limitation → excluida
        # MEMO: Monto Total = 116 → debe cuadrar solo con fila A
        pan = _df_pan(
            _pan(**{"Net claim amount": 100.0, "Total tax amount": 16.0,
                    "Claim cause description": "Descuento comercial"}),
            _pan(**{"Net claim amount": 500.0, "Total tax amount": 80.0,
                    "Claim cause description": "Limitation in a systems functionality"}),
        )
        memo = _df_pf(_memo_pf(**{"Monto Total": 116.0}))
        cruce = _cruce_resumen(pan, memo)
        row = cruce[cruce["Vendor number"] == "1001"].iloc[0]
        assert row["Amount Status"] == "OK"
        assert abs(row["Gross claim amount (Panoptic)"] - 116.0) < 0.01

    def test_tolerancia_exactamente_1_peso_es_ok(self):
        pan  = _df_pan(_pan(**{"Net claim amount": 99.0, "Total tax amount": 16.0}))  # Gross=115
        memo = _df_pf(_memo_pf(**{"Monto Total": 116.0}))  # diferencia = 1.0
        cruce = _cruce_resumen(pan, memo)
        assert cruce.iloc[0]["Amount Status"] == "OK"

    def test_diferencia_mayor_a_1_peso_es_mismatch(self):
        pan  = _df_pan(_pan(**{"Net claim amount": 98.99, "Total tax amount": 16.0}))  # Gross=114.99
        memo = _df_pf(_memo_pf(**{"Monto Total": 116.0}))  # diferencia = 1.01
        cruce = _cruce_resumen(pan, memo)
        assert cruce.iloc[0]["Amount Status"] == "Mismatch"

    def test_multiples_vendors(self):
        pan = _df_pan(
            _pan(**{"Vendor number": "1001", "Net claim amount": 100.0, "Total tax amount": 16.0}),
            _pan(**{"Vendor number": "2002", "Net claim amount": 200.0, "Total tax amount": 32.0}),
        )
        memo = _df_pf(
            _memo_pf(**{"Num Proveedor": "1001", "Monto Total": 116.0}),
            _memo_pf(**{"Num Proveedor": "2002", "Monto Total": 999.0}),  # Mismatch
        )
        cruce = _cruce_resumen(pan, memo)
        assert cruce[cruce["Vendor number"] == "1001"].iloc[0]["Amount Status"] == "OK"
        assert cruce[cruce["Vendor number"] == "2002"].iloc[0]["Amount Status"] == "Mismatch"


# ---------------------------------------------------------------------------
# _paso4_duplicados
# ---------------------------------------------------------------------------

class TestPaso4Duplicados:

    def test_detecta_duplicado_exacto(self):
        # Misma clave de 7 campos aparece 2 veces
        df = pd.DataFrame([_memo_ca(), _memo_ca()])
        _, incon = _paso4_duplicados(df)
        assert len(incon) == 1
        assert incon.iloc[0]["Veces en MEMO"] == 2

    def test_sin_duplicados_incon_vacio(self):
        df = pd.DataFrame([
            _memo_ca(**{"Num Proveedor": "1001", "Año": 2023, "Monto antes impuestos": 100.0}),
            _memo_ca(**{"Num Proveedor": "2002", "Año": 2023, "Monto antes impuestos": 200.0}),
        ])
        _, incon = _paso4_duplicados(df)
        assert incon.empty

    def test_mismo_vendor_diferente_monto_no_es_duplicado(self):
        # Misma clave de proveedor/año/concepto pero diferente monto → NO duplicado
        df = pd.DataFrame([
            _memo_ca(**{"Monto antes impuestos": 100.0}),
            _memo_ca(**{"Monto antes impuestos": 200.0}),  # monto diferente
        ])
        _, incon = _paso4_duplicados(df)
        assert incon.empty

    def test_mismo_vendor_diferente_ieps_no_es_duplicado(self):
        df = pd.DataFrame([
            _memo_ca(**{"IEPS": 0.0}),
            _memo_ca(**{"IEPS": 15.0}),
        ])
        _, incon = _paso4_duplicados(df)
        assert incon.empty

    def test_cruce_detalle_contiene_todas_las_filas(self):
        # cruce_detalle debe tener TODAS las combinaciones, no solo duplicadas
        df = pd.DataFrame([
            _memo_ca(**{"Num Proveedor": "1001"}),
            _memo_ca(**{"Num Proveedor": "1001"}),  # duplicado
            _memo_ca(**{"Num Proveedor": "2002"}),  # único
        ])
        detalle, incon = _paso4_duplicados(df)
        # detalle tiene 2 filas: una por combinación única de 7 campos
        assert len(detalle) == 2
        # incon tiene solo 1 (la del vendor 1001)
        assert len(incon) == 1

    def test_triplicado_reporta_count_3(self):
        df = pd.DataFrame([_memo_ca(), _memo_ca(), _memo_ca()])
        _, incon = _paso4_duplicados(df)
        assert incon.iloc[0]["Veces en MEMO"] == 3


# ---------------------------------------------------------------------------
# _compute_duplicados_x_memo
# ---------------------------------------------------------------------------

def _make_ca_df(vendor: str, rows: list[dict]) -> pd.DataFrame:
    """Construye un DataFrame de MontoxConceptoxAño para un vendor."""
    base = {
        "Num Proveedor": vendor, "Año": 2023,
        "Concepto": "MERMA DE ORIGEN", "Num Categoria": "CAT01",
        "Monto antes impuestos": 100.0, "IEPS": 0.0, "IVA": 16.0,
    }
    return pd.DataFrame([{**base, **r} for r in rows])


class TestComputeDuplicadosXMemo:

    def _vendor_sets(self, mapping: dict[str, list[str]]) -> dict[str, set[str]]:
        """mapping: {memo_id: [vendor1, vendor2, ...]}"""
        return {mid: set(vendors) for mid, vendors in mapping.items()}

    def test_filas_identicas_en_dos_memos_es_duplicado(self):
        # Proveedor 1001 tiene las mismas 2 filas en M043 y M049
        row_a = {"Año": 2022, "Concepto": "MERMA", "Num Categoria": "C1",
                 "Monto antes impuestos": 100.0, "IEPS": 0.0, "IVA": 16.0}
        row_b = {"Año": 2023, "Concepto": "MERMA", "Num Categoria": "C1",
                 "Monto antes impuestos": 200.0, "IEPS": 0.0, "IVA": 32.0}
        sets = self._vendor_sets({"M043": ["1001"], "M049": ["1001"]})
        ca_dfs = {
            "M043": _make_ca_df("1001", [row_a, row_b]),
            "M049": _make_ca_df("1001", [row_a, row_b]),
        }
        result = _compute_duplicados_x_memo(sets, {}, ca_dfs)
        assert len(result) == 1
        assert result.iloc[0]["Vendor number"] == "1001"
        assert result.iloc[0]["Filas duplicadas"] == 2

    def test_una_sola_fila_identica_ya_es_duplicado(self):
        # Con 1 fila idéntica entre memos ya es suficiente para marcar duplicado
        row_a = {"Año": 2022, "Concepto": "MERMA", "Num Categoria": "C1",
                 "Monto antes impuestos": 100.0, "IEPS": 0.0, "IVA": 16.0}
        row_b_m043 = {"Año": 2023, "Concepto": "OTROS", "Num Categoria": "C2",
                      "Monto antes impuestos": 500.0, "IEPS": 0.0, "IVA": 80.0}
        row_b_m049 = {"Año": 2023, "Concepto": "DIFERENTE", "Num Categoria": "C3",
                      "Monto antes impuestos": 999.0, "IEPS": 0.0, "IVA": 0.0}
        sets = self._vendor_sets({"M043": ["1001"], "M049": ["1001"]})
        ca_dfs = {
            "M043": _make_ca_df("1001", [row_a, row_b_m043]),
            "M049": _make_ca_df("1001", [row_a, row_b_m049]),
        }
        result = _compute_duplicados_x_memo(sets, {}, ca_dfs)
        assert len(result) == 1
        assert result.iloc[0]["Filas duplicadas"] == 1

    def test_informacion_diferente_no_es_duplicado(self):
        # Mismo vendor en 2 memos pero filas completamente distintas
        sets = self._vendor_sets({"M043": ["1001"], "M049": ["1001"]})
        ca_dfs = {
            "M043": _make_ca_df("1001", [{"Año": 2020, "Concepto": "A", "Monto antes impuestos": 100.0}]),
            "M049": _make_ca_df("1001", [{"Año": 2022, "Concepto": "B", "Monto antes impuestos": 999.0}]),
        }
        result = _compute_duplicados_x_memo(sets, {}, ca_dfs)
        assert len(result) == 0

    def test_vendor_en_solo_un_memo_no_aparece(self):
        sets = self._vendor_sets({"M043": ["1001"], "M049": ["2002"]})
        row = {"Año": 2023, "Concepto": "MERMA", "Num Categoria": "C1",
               "Monto antes impuestos": 100.0, "IEPS": 0.0, "IVA": 16.0}
        ca_dfs = {
            "M043": _make_ca_df("1001", [row, row]),
            "M049": _make_ca_df("2002", [row, row]),
        }
        result = _compute_duplicados_x_memo(sets, {}, ca_dfs)
        assert len(result) == 0

    def test_sin_memo_ca_dfs_retorna_vacio(self):
        sets = self._vendor_sets({"M043": ["1001"], "M049": ["1001"]})
        result = _compute_duplicados_x_memo(sets, {}, None)
        assert len(result) == 0
        assert "Filas duplicadas" in result.columns

    def test_memos_involucrados_son_solo_los_duplicados(self):
        # Vendor en M043, M049, M055 — solo M043 y M049 tienen filas iguales
        row_dup = {"Año": 2022, "Concepto": "MERMA", "Num Categoria": "C1",
                   "Monto antes impuestos": 100.0, "IEPS": 0.0, "IVA": 16.0}
        row_dup2 = {"Año": 2023, "Concepto": "FILL RATE", "Num Categoria": "C2",
                    "Monto antes impuestos": 200.0, "IEPS": 0.0, "IVA": 32.0}
        row_distinto = {"Año": 2024, "Concepto": "APERTURA", "Num Categoria": "C9",
                        "Monto antes impuestos": 999.0, "IEPS": 0.0, "IVA": 0.0}
        sets = self._vendor_sets({"M043": ["1001"], "M049": ["1001"], "M055": ["1001"]})
        ca_dfs = {
            "M043": _make_ca_df("1001", [row_dup, row_dup2]),
            "M049": _make_ca_df("1001", [row_dup, row_dup2]),
            "M055": _make_ca_df("1001", [row_distinto]),
        }
        result = _compute_duplicados_x_memo(sets, {}, ca_dfs)
        assert len(result) == 1
        assert "M043" in result.iloc[0]["Memos"]
        assert "M049" in result.iloc[0]["Memos"]
        assert "M055" not in result.iloc[0]["Memos"]


# ---------------------------------------------------------------------------
# _agregar_periodos_incon_montos
# ---------------------------------------------------------------------------

class TestAgregarPeriodosInconMontos:

    def _incon_row(self, vendor="1001", **kwargs) -> dict:
        row = {"Vendor number": vendor, "Vendor name": "Test SA"}
        row.update(kwargs)
        return row

    def test_periodos_panoptic_correctos(self):
        pan = _df_pan_memo(
            _pan(**{"Financial year of origin": 2022}),
            _pan(**{"Financial year of origin": 2023}),
        )
        memo_ca = pd.DataFrame([_memo_ca(**{"Año": 2023})])
        incon = pd.DataFrame([self._incon_row()])
        result = _agregar_periodos_incon_montos(incon, pan, memo_ca)
        assert result.iloc[0]["Periodos Panoptic"] == "2022 - 2023"

    def test_periodos_memo_correctos(self):
        pan = _df_pan_memo(_pan(**{"Financial year of origin": 2023}))
        memo_ca = pd.DataFrame([
            _memo_ca(**{"Año": 2021}),
            _memo_ca(**{"Año": 2022}),
        ])
        incon = pd.DataFrame([self._incon_row()])
        result = _agregar_periodos_incon_montos(incon, pan, memo_ca)
        assert result.iloc[0]["Periodos Memo"] == "2021 - 2022"

    def test_periodos_diferencia_detecta_anio_extra_en_panoptic(self):
        pan = _df_pan_memo(
            _pan(**{"Financial year of origin": 2022}),
            _pan(**{"Financial year of origin": 2024}),
        )
        memo_ca = pd.DataFrame([_memo_ca(**{"Año": 2022})])
        incon = pd.DataFrame([self._incon_row()])
        result = _agregar_periodos_incon_montos(incon, pan, memo_ca)
        assert "2024" in result.iloc[0]["Periodos Diferencia"]
        assert "2022" not in result.iloc[0]["Periodos Diferencia"]

    def test_periodos_diferencia_detecta_anio_solo_en_memo(self):
        pan = _df_pan_memo(_pan(**{"Financial year of origin": 2023}))
        memo_ca = pd.DataFrame([
            _memo_ca(**{"Año": 2023}),
            _memo_ca(**{"Num Proveedor": "1001", "Año": 2020}),
        ])
        incon = pd.DataFrame([self._incon_row()])
        result = _agregar_periodos_incon_montos(incon, pan, memo_ca)
        assert "2020" in result.iloc[0]["Periodos Diferencia"]

    def test_sin_diferencia_cuando_mismos_anios(self):
        pan = _df_pan_memo(_pan(**{"Financial year of origin": 2023}))
        memo_ca = pd.DataFrame([_memo_ca(**{"Año": 2023})])
        incon = pd.DataFrame([self._incon_row()])
        result = _agregar_periodos_incon_montos(incon, pan, memo_ca)
        assert result.iloc[0]["Periodos Diferencia"] == ""

    def test_incon_vacio_retorna_columnas_vacias(self):
        pan = _df_pan_memo(_pan())
        memo_ca = pd.DataFrame([_memo_ca()])
        incon = pd.DataFrame(columns=["Vendor number"])
        result = _agregar_periodos_incon_montos(incon, pan, memo_ca)
        assert len(result) == 0
        assert "Periodos Panoptic" in result.columns
        assert "Periodos Memo" in result.columns
        assert "Periodos Diferencia" in result.columns

    def test_orden_de_anios_es_ascendente(self):
        pan = _df_pan_memo(
            _pan(**{"Financial year of origin": 2024}),
            _pan(**{"Financial year of origin": 2021}),
            _pan(**{"Financial year of origin": 2022}),
        )
        memo_ca = pd.DataFrame([_memo_ca(**{"Año": 2023})])
        incon = pd.DataFrame([self._incon_row()])
        result = _agregar_periodos_incon_montos(incon, pan, memo_ca)
        assert result.iloc[0]["Periodos Panoptic"] == "2021 - 2022 - 2024"


# ---------------------------------------------------------------------------
# _identificar_diferencias_x_monto
# ---------------------------------------------------------------------------

def _df_pan_memo(*rows) -> pd.DataFrame:
    """DataFrame de Panoptic ya filtrado por memo_id (simula df_pan_memo)."""
    return pd.DataFrame(list(rows))


def _incon_montos_row(**overrides) -> dict:
    row = {
        "Vendor number": "1001",
        "Vendor name":   "Proveedor Test SA",
    }
    row.update(overrides)
    return row


class TestIdentificarDiferenciasXMonto:

    def test_concepto_solo_en_panoptic_aparece_con_memo_cero(self):
        # "PROMOCION COMPRA" existe en Panoptic pero NO en MEMO → MEMO=0, Dif Neta > 0
        pan = _df_pan_memo(_pan(**{
            "Claim cause description": "PROMOCION COMPRA",
            "Net claim amount": 6628.48, "Total tax amount": 0.0,
            "Posting reference number": "M043",
        }))
        memo_ca = pd.DataFrame([_memo_ca(**{"Concepto": "OTRO CONCEPTO",
                                             "Monto antes impuestos": 100.0, "IVA": 0.0})])
        incon = pd.DataFrame([_incon_montos_row()])
        result = _identificar_diferencias_x_monto(pan, memo_ca, incon, "M043")
        assert len(result) >= 1
        row = result[result["Concepto"] == "PROMOCION COMPRA"].iloc[0]
        assert row["Panoptic (Neto)"] == pytest.approx(6628.48)
        assert row["MEMO (Antes Impuestos)"] == pytest.approx(0.0)
        assert row["Dif Neta"] == pytest.approx(6628.48)

    def test_concepto_solo_en_memo_aparece_con_panoptic_cero(self):
        # "FILL RATE" solo en MEMO → Panoptic=0, diferencia positiva (MEMO > Panoptic)
        pan = _df_pan_memo(_pan(**{
            "Claim cause description": "OTRO CONCEPTO",
            "Net claim amount": 50.0, "Total tax amount": 0.0,
            "Posting reference number": "M043",
        }))
        memo_ca = pd.DataFrame([
            _memo_ca(**{"Concepto": "OTRO CONCEPTO",  "Monto antes impuestos": 50.0}),
            _memo_ca(**{"Concepto": "FILL RATE",       "Monto antes impuestos": 200.0}),
        ])
        incon = pd.DataFrame([_incon_montos_row()])
        result = _identificar_diferencias_x_monto(pan, memo_ca, incon, "M043")
        row = result[result["Concepto"] == "FILL RATE"].iloc[0]
        assert row["Panoptic (Neto)"] == pytest.approx(0.0)
        assert row["MEMO (Antes Impuestos)"] == pytest.approx(200.0)
        assert row["Dif Neta"] == pytest.approx(-200.0)

    def test_concepto_en_ambos_sin_diferencia_no_aparece(self):
        # "MERMA DE ORIGEN": Panoptic Net=100 Gross=100, MEMO Antes Imp=100 Total=100 → no diferencia
        pan = _df_pan_memo(_pan(**{
            "Claim cause description": "MERMA DE ORIGEN",
            "Net claim amount": 100.0, "Total tax amount": 0.0,
            "Posting reference number": "M043",
        }))
        memo_ca = pd.DataFrame([_memo_ca(**{
            "Concepto": "MERMA DE ORIGEN",
            "Monto antes impuestos": 100.0, "IEPS": 0.0, "IVA": 0.0,
        })])
        incon = pd.DataFrame([_incon_montos_row()])
        result = _identificar_diferencias_x_monto(pan, memo_ca, incon, "M043")
        assert len(result) == 0

    def test_concepto_en_ambos_con_diferencia_aparece(self):
        # "DESCUENTO": Panoptic Net=500, MEMO=300 → diferencia de 200
        pan = _df_pan_memo(_pan(**{
            "Claim cause description": "DESCUENTO",
            "Net claim amount": 500.0, "Total tax amount": 0.0,
            "Posting reference number": "M043",
        }))
        memo_ca = pd.DataFrame([_memo_ca(**{
            "Concepto": "DESCUENTO", "Monto antes impuestos": 300.0,
        })])
        incon = pd.DataFrame([_incon_montos_row()])
        result = _identificar_diferencias_x_monto(pan, memo_ca, incon, "M043")
        assert len(result) == 1
        assert result.iloc[0]["Dif Neta"] == pytest.approx(200.0)

    def test_limitation_excluida_del_agrupado(self):
        # "Limitation in a systems functionality" nunca debe aparecer
        pan = _df_pan_memo(
            _pan(**{"Claim cause description": "Limitation in a systems functionality",
                    "Net claim amount": 9999.0, "Total tax amount": 0.0,
                    "Posting reference number": "M043"}),
            _pan(**{"Claim cause description": "DESCUENTO",
                    "Net claim amount": 500.0,  "Total tax amount": 0.0,
                    "Posting reference number": "M043"}),
        )
        memo_ca = pd.DataFrame([_memo_ca(**{
            "Concepto": "DESCUENTO", "Monto antes impuestos": 200.0,
        })])
        incon = pd.DataFrame([_incon_montos_row()])
        result = _identificar_diferencias_x_monto(pan, memo_ca, incon, "M043")
        assert "LIMITATION IN A SYSTEMS FUNCTIONALITY" not in result["Concepto"].values
        row = result[result["Concepto"] == "DESCUENTO"].iloc[0]
        assert row["Panoptic (Neto)"] == pytest.approx(500.0)

    def test_bruto_incluye_impuestos(self):
        # Panoptic: Net=100, Tax=16 → Gross=116; MEMO: Antes Imp=100, IEPS=0, IVA=16 → Total=116
        # Dif Neta: 100-100=0, Dif Total: 116-116=0 → no aparece
        pan = _df_pan_memo(_pan(**{
            "Claim cause description": "MERMA DE ORIGEN",
            "Net claim amount": 100.0, "Total tax amount": 16.0,
            "Posting reference number": "M043",
        }))
        memo_ca = pd.DataFrame([_memo_ca(**{
            "Concepto": "MERMA DE ORIGEN",
            "Monto antes impuestos": 100.0, "IEPS": 0.0, "IVA": 16.0,
        })])
        incon = pd.DataFrame([_incon_montos_row()])
        result = _identificar_diferencias_x_monto(pan, memo_ca, incon, "M043")
        assert len(result) == 0

    def test_incon_montos_vacio_retorna_vacio(self):
        pan = _df_pan_memo(_pan())
        memo_ca = pd.DataFrame([_memo_ca()])
        incon = pd.DataFrame(columns=["Vendor number", "Vendor name"])
        result = _identificar_diferencias_x_monto(pan, memo_ca, incon, "M049")
        assert len(result) == 0

    def test_columnas_de_salida_correctas(self):
        pan = _df_pan_memo(_pan(**{
            "Claim cause description": "PROMOCION COMPRA",
            "Net claim amount": 500.0, "Total tax amount": 0.0,
            "Posting reference number": "M049",
        }))
        memo_ca = pd.DataFrame([_memo_ca(**{"Concepto": "OTRO", "Monto antes impuestos": 0.0})])
        incon = pd.DataFrame([_incon_montos_row()])
        result = _identificar_diferencias_x_monto(pan, memo_ca, incon, "M049")
        for col in ["Memo", "Vendor number", "Vendor name", "Concepto",
                    "Panoptic (Neto)", "MEMO (Antes Impuestos)", "Dif Neta",
                    "Panoptic (Bruto)", "MEMO (Total)", "Dif Total"]:
            assert col in result.columns


