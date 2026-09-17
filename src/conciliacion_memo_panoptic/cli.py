from __future__ import annotations

import argparse
from pathlib import Path

from .paths import PROJECT_ROOT
from .settings import load_panoptic_settings


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cmp",
        description="Herramientas para descargar Panoptic y conciliar contra MEMO.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    download = subparsers.add_parser(
        "download-panoptic",
        help="Abre Panoptic, selecciona la vista y exporta XLSX.",
    )
    download.add_argument("--config", help="Ruta a un JSON de configuracion.")
    download.add_argument("--url", help="URL inicial de Panoptic.")
    download.add_argument("--download-dir", type=Path, help="Carpeta destino de descargas.")
    download.add_argument("--profile-dir", type=Path, help="Perfil persistente del navegador.")
    download.add_argument("--timeout-ms", type=int, help="Timeout default de Playwright.")
    download.add_argument("--headless", action="store_true", help="Ejecutar navegador sin UI.")
    download.add_argument("--email", help="Correo a ingresar en la pantalla de login.")
    download.add_argument("--memo", help="Numero de memo, por ejemplo 030.")
    download.add_argument("--vendor", help="Numero de proveedor, por ejemplo 303452.")
    download.add_argument("--view-name", default="MONICA_3", help="Vista de Claims a seleccionar.")

    export = subparsers.add_parser(
        "export-panoptic-xlsx",
        help="Abre Panoptic, selecciona la vista y exporta XLSX sin aplicar filtros.",
    )
    export.add_argument("--config", help="Ruta a un JSON de configuracion.")
    export.add_argument("--url", help="URL inicial de Panoptic.")
    export.add_argument("--download-dir", type=Path, help="Carpeta destino de descargas.")
    export.add_argument("--profile-dir", type=Path, help="Perfil persistente del navegador.")
    export.add_argument("--timeout-ms", type=int, help="Timeout default de Playwright.")
    export.add_argument("--headless", action="store_true", help="Ejecutar navegador sin UI.")
    export.add_argument("--email", help="Correo a ingresar en la pantalla de login.")
    export.add_argument("--view-name", default="MONICA_3", help="Vista de Claims a seleccionar.")

    open_view = subparsers.add_parser(
        "open-panoptic-view",
        help="Abre Panoptic y selecciona una vista de Claims.",
    )
    open_view.add_argument("--config", help="Ruta a un JSON de configuracion.")
    open_view.add_argument("--url", help="URL inicial de Panoptic.")
    open_view.add_argument("--profile-dir", type=Path, help="Perfil persistente del navegador.")
    open_view.add_argument("--timeout-ms", type=int, help="Timeout default de Playwright.")
    open_view.add_argument("--headless", action="store_true", help="Ejecutar navegador sin UI.")
    open_view.add_argument("--email", help="Correo a ingresar en la pantalla de login.")
    open_view.add_argument("--view-name", default="MONICA_3", help="Vista de Claims a seleccionar.")
    open_view.add_argument(
        "--close-when-done",
        action="store_true",
        help="Cerrar el navegador inmediatamente despues de seleccionar la vista.",
    )

    process = subparsers.add_parser(
        "process-panoptic",
        help="Lee un XLSX de Panoptic y genera un resumen agrupado por proveedor.",
    )
    process.add_argument("input_file", type=Path, help="Ruta al archivo XLSX descargado.")
    process.add_argument(
        "--output-dir", type=Path, default=Path("data/processed"), help="Carpeta de salida."
    )

    reconcile = subparsers.add_parser(
        "reconcile",
        help="Cruza el archivo raw de Panoptic contra un archivo MEMO para hallar inconsistencias.",
    )
    reconcile.add_argument("--raw-panoptic", type=Path, required=True, help="Ruta al archivo XLSX raw de Panoptic.")
    reconcile.add_argument("--memo", type=Path, required=True, help="Ruta al archivo MEMO (ej. Memo_030_varios.xlsx).")
    reconcile.add_argument("--memo-id", type=str, required=True, help="ID del memo para filtrar Panoptic (ej. M030).")
    reconcile.add_argument(
        "--output-dir", type=Path, default=Path("outputs/Etapa1"), help="Carpeta de salida para el reporte."
    )

    reconcile_all = subparsers.add_parser(
        "reconcile-all",
        help=(
            "Carga Panoptic una sola vez y concilia contra todos los Memo_*.xlsx "
            "de una carpeta. Genera un archivo de salida por memo."
        ),
    )
    reconcile_all.add_argument(
        "--raw-panoptic", type=Path, required=True,
        help="Ruta al archivo XLSX descargado de Panoptic.",
    )
    reconcile_all.add_argument(
        "--memo-dir", type=Path, required=True,
        help="Carpeta que contiene los archivos Memo_*.xlsx (ej. X:/Soriana/.../Cargos).",
    )
    reconcile_all.add_argument(
        "--output-dir", type=Path, default=Path("outputs/Etapa1"),
        help="Carpeta de salida donde se guardan los reportes por memo.",
    )
    reconcile_all.add_argument(
        "--memo-from", type=int, default=None,
        help="Número de memo inicial del rango a procesar (ej. 40).",
    )
    reconcile_all.add_argument(
        "--memo-to", type=int, default=None,
        help="Número de memo final del rango a procesar (ej. 56).",
    )
    reconcile_all.add_argument(
        "--memos", type=str, default=None,
        help="Lista/rango de memos (ej. '48,49,50' o '40-56'). Tiene prioridad sobre --memo-from/--memo-to.",
    )
    reconcile_all.add_argument(
        "--vendors", type=str, default=None,
        help="Vendor numbers a filtrar (coma/espacio/línea). Ejecución manual.",
    )

    upload = subparsers.add_parser(
        "upload-claim-updates",
        help=(
            "Sube a Panoptic el archivo de bulk update generado por reconcile-all "
            "(Claim_Bulk_Update_YYYYMMDD.xlsx)."
        ),
    )
    upload.add_argument(
        "--file", type=Path, required=True,
        help="Ruta al archivo Claim_Bulk_Update_*.xlsx generado por reconcile-all.",
    )
    upload.add_argument("--config", help="Ruta a un JSON de configuracion de Panoptic.")
    upload.add_argument("--url", help="URL inicial de Panoptic.")
    upload.add_argument("--profile-dir", type=Path, help="Perfil persistente del navegador.")
    upload.add_argument("--timeout-ms", type=int, help="Timeout default de Playwright.")
    upload.add_argument("--headless", action="store_true", help="Ejecutar navegador sin UI.")
    upload.add_argument("--email", help="Correo para el login de Panoptic.")
    upload.add_argument("--view-name", default="MONICA_3", help="Vista de Claims a seleccionar.")

    upload_pd = subparsers.add_parser(
        "upload-posting-dates",
        help=(
            "Sube a Panoptic el archivo de Posting submission date generado por "
            "cross-all-estados (etapa2_M0XX_PostingDate.xlsx). "
            "Usa 'Import claim updates'."
        ),
    )
    upload_pd.add_argument(
        "--file", type=Path, required=True,
        help="Ruta al archivo etapa2_M0XX_PostingDate.xlsx.",
    )
    upload_pd.add_argument("--config", help="Ruta a un JSON de configuracion de Panoptic.")
    upload_pd.add_argument("--url", help="URL inicial de Panoptic.")
    upload_pd.add_argument("--profile-dir", type=Path, help="Perfil persistente del navegador.")
    upload_pd.add_argument("--timeout-ms", type=int, help="Timeout default de Playwright.")
    upload_pd.add_argument("--headless", action="store_true", help="Ejecutar navegador sin UI.")
    upload_pd.add_argument("--email", help="Correo para el login de Panoptic.")
    upload_pd.add_argument("--view-name", default="MONICA_3", help="Vista de Claims a seleccionar.")

    upload_rec = subparsers.add_parser(
        "upload-recoveries",
        help=(
            "Sube a Panoptic el archivo de recoveries / clearing data generado por "
            "cross-all-estados (etapa2_M0XX_Recoveries.xlsx). "
            "Usa 'Import recoveries / clearing data'."
        ),
    )
    upload_rec.add_argument(
        "--file", type=Path, required=True,
        help="Ruta al archivo etapa2_M0XX_Recoveries.xlsx.",
    )
    upload_rec.add_argument("--config", help="Ruta a un JSON de configuracion de Panoptic.")
    upload_rec.add_argument("--url", help="URL inicial de Panoptic.")
    upload_rec.add_argument("--profile-dir", type=Path, help="Perfil persistente del navegador.")
    upload_rec.add_argument("--timeout-ms", type=int, help="Timeout default de Playwright.")
    upload_rec.add_argument("--headless", action="store_true", help="Ejecutar navegador sin UI.")
    upload_rec.add_argument("--email", help="Correo para el login de Panoptic.")
    upload_rec.add_argument("--view-name", default="MONICA_3", help="Vista de Claims a seleccionar.")

    cross_single = subparsers.add_parser(
        "cross-estado-cuenta",
        help="Cruza un archivo de Folio Compensatorio (MEMO_0XX.xlsx) contra Panoptic (Etapa 2).",
    )
    cross_single.add_argument(
        "--raw-panoptic", type=Path, required=True,
        help="Ruta al XLSX de Panoptic actualizado (vista MONICA_3).",
    )
    cross_single.add_argument(
        "--folio", type=Path, required=True,
        help="Ruta al archivo MEMO_0XX.xlsx de Folios Compensatorios.",
    )
    cross_single.add_argument(
        "--memo-id", type=str, required=True,
        help="ID del memo, ej. M048.",
    )
    cross_single.add_argument(
        "--output-dir", type=Path, default=Path("outputs/Etapa2"),
        help="Carpeta de salida.",
    )

    cross_all = subparsers.add_parser(
        "cross-all-estados",
        help=(
            "Carga Panoptic una vez y cruza contra todos los MEMO_*.xlsx "
            "de la carpeta de Folios Compensatorios (Etapa 2)."
        ),
    )
    cross_all.add_argument(
        "--raw-panoptic", type=Path, required=True,
        help="Ruta al XLSX de Panoptic actualizado (vista MONICA_3).",
    )
    cross_all.add_argument(
        "--folios-dir",
        type=Path,
        default=Path(r"X:\Soriana\00 - AUDITORIA 2020 - 2024\FOLIOS COMPENSATORIOS"),
        help="Carpeta con archivos MEMO_*.xlsx de Folios Compensatorios.",
    )
    cross_all.add_argument(
        "--output-dir", type=Path, default=Path("outputs/Etapa2"),
        help="Carpeta de salida.",
    )
    cross_all.add_argument(
        "--memo-from", type=int, default=None,
        help="Número de memo inicial del rango a procesar (ej. 40).",
    )
    cross_all.add_argument(
        "--memo-to", type=int, default=None,
        help="Número de memo final del rango a procesar (ej. 56).",
    )
    cross_all.add_argument(
        "--memos", type=str, default=None,
        help="Lista/rango de memos (ej. '48,49,50' o '40-56'). Tiene prioridad sobre --memo-from/--memo-to.",
    )
    cross_all.add_argument(
        "--vendors", type=str, default=None,
        help="Vendor numbers a filtrar (coma/espacio/línea). Ejecución manual.",
    )
    cross_all.add_argument(
        "--folio-file", type=Path, default=None, nargs="+",
        help="Uno o varios archivos EC con varios memos (en vez de la carpeta de folios). Requiere --memos.",
    )

    cross_ns = subparsers.add_parser(
        "cross-nivel-servicio",
        help=(
            "Etapa 3 — Consolida los BLOQUE*.xlsx del Estado de Cuenta NS y los cruza "
            "contra Panoptic (Posting reference = NS-EneAgo25, Status != Rejected)."
        ),
    )
    cross_ns.add_argument(
        "--raw-panoptic", type=Path, required=True,
        help="Ruta al XLSX de Panoptic actualizado (vista MONICA_3).",
    )
    cross_ns.add_argument(
        "--blocks-dir", type=Path,
        default=Path(r"X:\Soriana\00 - AUDITORIA 2020 - 2024\BLOQUES ESTADO CUENTA"),
        help="Carpeta con los BLOQUE*.xlsx del Estado de Cuenta NS.",
    )
    cross_ns.add_argument(
        "--bitacora", type=Path,
        default=PROJECT_ROOT / "data" / "referencias" / "BITACORA_ACLARACIONES_NS 2025 (2).xlsx",
        help="Archivo de bitácora NS (hoja Reembolsos) para el cross-check.",
    )
    cross_ns.add_argument(
        "--output-dir", type=Path, default=Path("outputs/Etapa3"),
        help="Carpeta de salida.",
    )
    cross_ns.add_argument(
        "--solo-capa1", action="store_true",
        help=(
            "Ejecuta SOLO la Capa 1 (Bitácora vs Panoptic). No lee los bloques del EC, "
            "así que es casi instantáneo. Genera etapa3_NS_capa1.xlsx."
        ),
    )

    cross_sd = subparsers.add_parser(
        "cross-nivel-servicio-septdic",
        help=(
            "Etapa 4 — Nivel de Servicio Sep-Dic 2025. Igual que Etapa 3 pero con Posting "
            "reference 'NS-SeptDic 2025', bitácora 'resto' y EC filtrado a >= 19-jun-2026."
        ),
    )
    cross_sd.add_argument(
        "--raw-panoptic", type=Path, required=True,
        help="Ruta al XLSX de Panoptic actualizado (vista MONICA_3).",
    )
    cross_sd.add_argument(
        "--blocks-dir", type=Path,
        default=Path(r"X:\Soriana\00 - AUDITORIA 2020 - 2024\BLOQUES ESTADO CUENTA"),
        help="Carpeta con los BLOQUE*.xlsx del Estado de Cuenta.",
    )
    cross_sd.add_argument(
        "--bitacora", type=Path,
        default=Path(
            r"X:\Soriana\00 - AUDITORIA 2020 - 2024\BLOQUES ESTADO CUENTA\BITACORAS"
            r"\BITACORA NS resto 2025.xlsx"
        ),
        help="Bitácora Sep-Dic (formato 'resto').",
    )
    cross_sd.add_argument(
        "--provider-blocks", type=Path,
        default=PROJECT_ROOT / "data" / "referencias" / "Proveedores_bloque_Sep-Dic 25.xlsx",
        help="Archivo de proveedores por bloque (etiqueta cada proveedor con su bloque 1-6).",
    )
    cross_sd.add_argument(
        "--output-dir", type=Path, default=Path("outputs/Etapa4"),
        help="Carpeta de salida.",
    )
    cross_sd.add_argument(
        "--solo-capa1", action="store_true",
        help="Ejecuta SOLO la Capa 1 (Bitácora vs Panoptic), sin leer los bloques del EC.",
    )

    run_etapa2 = subparsers.add_parser(
        "run-etapa2",
        help=(
            "Todo en uno (Etapa 2): descarga Panoptic y cruza contra "
            "todos los Folios Compensatorios."
        ),
    )
    run_etapa2.add_argument("--config", help="Ruta a un JSON de configuracion de Panoptic.")
    run_etapa2.add_argument("--url", help="URL inicial de Panoptic.")
    run_etapa2.add_argument("--download-dir", type=Path, help="Carpeta destino de la descarga de Panoptic.")
    run_etapa2.add_argument("--profile-dir", type=Path, help="Perfil persistente del navegador.")
    run_etapa2.add_argument("--timeout-ms", type=int, help="Timeout default de Playwright.")
    run_etapa2.add_argument("--headless", action="store_true", help="Ejecutar navegador sin UI.")
    run_etapa2.add_argument("--email", help="Correo para el login de Panoptic.")
    run_etapa2.add_argument("--view-name", default="MONICA_3", help="Vista de Claims a seleccionar.")
    run_etapa2.add_argument(
        "--folios-dir",
        type=Path,
        default=Path(r"X:\Soriana\00 - AUDITORIA 2020 - 2024\FOLIOS COMPENSATORIOS"),
        help="Carpeta con archivos MEMO_*.xlsx de Folios Compensatorios.",
    )
    run_etapa2.add_argument(
        "--output-dir", type=Path, default=Path("outputs/Etapa2"),
        help="Carpeta de salida para los reportes etapa2_M*.xlsx.",
    )
    run_etapa2.add_argument("--memo-from", type=int, default=None, help="Número de memo inicial.")
    run_etapa2.add_argument("--memo-to",   type=int, default=None, help="Número de memo final.")

    consolidate = subparsers.add_parser(
        "consolidate",
        help="Consolida todos los conciliacion_M*.xlsx de una carpeta en un solo Excel.",
    )
    consolidate.add_argument(
        "--output-dir", type=Path, default=Path("outputs/Etapa1"),
        help="Carpeta que contiene los archivos conciliacion_M*.xlsx.",
    )
    consolidate.add_argument(
        "--out-file", type=Path, default=None,
        help="Ruta del archivo consolidado de salida (default: output-dir/consolidado_todos_los_memos.xlsx).",
    )

    run_all = subparsers.add_parser(
        "run-all",
        help=(
            "Todo en uno: descarga Panoptic, concilia los memos del rango indicado "
            "y genera el consolidado final."
        ),
    )
    run_all.add_argument("--config", help="Ruta a un JSON de configuracion de Panoptic.")
    run_all.add_argument("--url", help="URL inicial de Panoptic.")
    run_all.add_argument("--download-dir", type=Path, help="Carpeta destino de la descarga de Panoptic.")
    run_all.add_argument("--profile-dir", type=Path, help="Perfil persistente del navegador.")
    run_all.add_argument("--timeout-ms", type=int, help="Timeout default de Playwright.")
    run_all.add_argument("--headless", action="store_true", help="Ejecutar navegador sin UI.")
    run_all.add_argument("--email", help="Correo para el login de Panoptic.")
    run_all.add_argument("--view-name", default="MONICA_3", help="Vista de Claims a seleccionar.")
    run_all.add_argument(
        "--memo-dir", type=Path, required=True,
        help="Carpeta que contiene los archivos Memo_*.xlsx.",
    )
    run_all.add_argument(
        "--output-dir", type=Path, default=Path("outputs/Etapa1"),
        help="Carpeta de salida para reportes por memo y consolidado.",
    )
    run_all.add_argument(
        "--memo-from", type=int, default=None,
        help="Número de memo inicial del rango a procesar (ej. 40).",
    )
    run_all.add_argument(
        "--memo-to", type=int, default=None,
        help="Número de memo final del rango a procesar (ej. 56).",
    )

    update_status = subparsers.add_parser(
        "update-claim-statuses",
        help=(
            "Lee un archivo de Etapa 2 y actualiza el Status en Panoptic: "
            "'Invoice ready' (con Folio Compensatorio) o 'Posted' (con Batch number)."
        ),
    )
    update_status.add_argument(
        "--etapa2-file", type=Path, required=True,
        help=(
            "Ruta al archivo Excel de Etapa 2 (etapa2_M0XX.xlsx). "
            "Debe contener la hoja 'Cruce Exitoso'."
        ),
    )
    update_status.add_argument(
        "--batch-size", type=int, default=50,
        help="Máximo de claims por lote en el filtro 'In' de Panoptic (default: 50).",
    )
    update_status.add_argument("--config", help="Ruta a un JSON de configuracion de Panoptic.")
    update_status.add_argument("--url", help="URL inicial de Panoptic.")
    update_status.add_argument("--profile-dir", type=Path, help="Perfil persistente del navegador.")
    update_status.add_argument("--timeout-ms", type=int, help="Timeout default de Playwright.")
    update_status.add_argument("--headless", action="store_true", help="Ejecutar navegador sin UI.")
    update_status.add_argument("--email", help="Correo para el login de Panoptic.")
    update_status.add_argument("--view-name", default="MONICA_3", help="Vista de Claims a seleccionar.")

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "download-panoptic":
        try:
            from .panoptic.downloader import download_xlsx
        except ModuleNotFoundError as exc:
            if exc.name == "playwright":
                parser.exit(
                    1,
                    "Falta instalar Playwright. Ejecuta: "
                    "python -m pip install -r requirements.txt\n",
                )
            raise

        settings = load_panoptic_settings(args.config).with_overrides(
            start_url=args.url,
            download_dir=args.download_dir,
            browser_profile_dir=args.profile_dir,
            login_email=args.email,
            default_timeout_ms=args.timeout_ms,
            headless=True if args.headless else None,
        )
        saved_path = download_xlsx(
            settings,
            memo=args.memo,
            vendor=args.vendor,
            view_name=args.view_name,
        )
        print(f"Archivo guardado: {saved_path}")
        return 0

    if args.command == "export-panoptic-xlsx":
        try:
            from .panoptic.downloader import download_xlsx
        except ModuleNotFoundError as exc:
            if exc.name == "playwright":
                parser.exit(
                    1,
                    "Falta instalar Playwright. Ejecuta: "
                    "python -m pip install -r requirements.txt\n",
                )
            raise

        settings = load_panoptic_settings(args.config).with_overrides(
            start_url=args.url,
            download_dir=args.download_dir,
            browser_profile_dir=args.profile_dir,
            login_email=args.email,
            default_timeout_ms=args.timeout_ms,
            headless=True if args.headless else None,
        )
        saved_path = download_xlsx(settings, view_name=args.view_name)
        print(f"Archivo guardado: {saved_path}")
        return 0

    if args.command == "open-panoptic-view":
        try:
            from .panoptic.workflows import open_claims_view
        except ModuleNotFoundError as exc:
            if exc.name == "playwright":
                parser.exit(
                    1,
                    "Falta instalar Playwright. Ejecuta: "
                    "python -m pip install -r requirements.txt\n",
                )
            raise

        settings = load_panoptic_settings(args.config).with_overrides(
            start_url=args.url,
            browser_profile_dir=args.profile_dir,
            login_email=args.email,
            default_timeout_ms=args.timeout_ms,
            headless=True if args.headless else None,
        )

        open_claims_view(
            settings,
            view_name=args.view_name,
            keep_open=not args.close_when_done,
        )
        return 0

    if args.command == "process-panoptic":
        from .conciliation.processing import process_panoptic_grouping

        print(f"Procesando agrupado de: {args.input_file}")
        result_path = process_panoptic_grouping(args.input_file, args.output_dir)
        print(f"Resumen generado en: {result_path}")
        return 0

    if args.command == "reconcile":
        from .conciliation.processing import reconcile_with_memo

        print(f"Iniciando conciliación...")
        result_path = reconcile_with_memo(args.raw_panoptic, args.memo, args.memo_id, args.output_dir)
        print(f"Reporte generado en: {result_path}")
        return 0

    if args.command == "reconcile-all":
        from .conciliation.processing import (
            reconcile_all_memos, parse_memo_numbers, parse_vendor_numbers,
        )

        memos = parse_memo_numbers(args.memos) or None
        vendors = parse_vendor_numbers(args.vendors) or None

        print(f"Cargando Panoptic: {args.raw_panoptic}")
        print(f"Buscando MEMOs en: {args.memo_dir}")
        if memos:
            print(f"Memos (lista): {sorted(memos)}")
        if vendors:
            print(f"Proveedores filtrados: {sorted(vendors)}")
        print()

        results = reconcile_all_memos(
            args.raw_panoptic, args.memo_dir, args.output_dir,
            memo_from=args.memo_from, memo_to=args.memo_to,
            memos=memos, vendors=vendors,
        )

        ok = [r for r in results if r.ok]
        skipped = [r for r in results if not r.ok and "omitido" in (r.error or "")]
        failed = [r for r in results if not r.ok and "omitido" not in (r.error or "")]

        for r in ok:
            print(f"  OK  {r.memo_id}  ->  {r.output_path}")
        for r in skipped:
            print(f"  --  {r.memo_id}  (sin registros en Panoptic, omitido)")
        for r in failed:
            print(f"  ERR {r.memo_id}  {r.error}")

        print()
        print(f"Completados: {len(ok)} | Omitidos: {len(skipped)} | Errores: {len(failed)}")
        print(f"Reportes guardados en: {args.output_dir.resolve()}")

        return 1 if failed else 0

    if args.command == "upload-claim-updates":
        try:
            from .panoptic.workflows import upload_claim_updates
        except ModuleNotFoundError as exc:
            if exc.name == "playwright":
                parser.exit(
                    1,
                    "Falta instalar Playwright. Ejecuta: "
                    "python -m pip install -r requirements.txt\n",
                )
            raise

        settings = load_panoptic_settings(args.config).with_overrides(
            start_url=args.url,
            browser_profile_dir=args.profile_dir,
            login_email=args.email,
            default_timeout_ms=args.timeout_ms,
            headless=True if args.headless else None,
        )
        print(f"Subiendo archivo: {args.file}")
        upload_claim_updates(settings, args.file, view_name=args.view_name)
        return 0

    if args.command in ("upload-posting-dates", "upload-recoveries"):
        try:
            from .panoptic.workflows import upload_claim_updates, upload_recoveries_clearing_data
        except ModuleNotFoundError as exc:
            if exc.name == "playwright":
                parser.exit(
                    1,
                    "Falta instalar Playwright. Ejecuta: "
                    "python -m pip install -r requirements.txt\n",
                )
            raise

        settings = load_panoptic_settings(args.config).with_overrides(
            start_url=args.url,
            browser_profile_dir=args.profile_dir,
            login_email=args.email,
            default_timeout_ms=args.timeout_ms,
            headless=True if args.headless else None,
        )
        print(f"Subiendo archivo: {args.file}")
        if args.command == "upload-posting-dates":
            upload_claim_updates(settings, args.file, view_name=args.view_name)
        else:
            upload_recoveries_clearing_data(settings, args.file, view_name=args.view_name)
        return 0

    if args.command == "cross-estado-cuenta":
        from .conciliation.processing import _load_panoptic
        from .conciliation.estado_cuenta import cross_estado_cuenta_memo

        print(f"Cargando Panoptic: {args.raw_panoptic}")
        df_pan = _load_panoptic(args.raw_panoptic)
        result = cross_estado_cuenta_memo(df_pan, args.folio, args.memo_id, args.output_dir)
        print(f"Reporte generado: {result}")
        return 0

    if args.command == "cross-all-estados":
        from .conciliation.estado_cuenta import cross_all_estados_cuenta
        from .conciliation.processing import parse_memo_numbers, parse_vendor_numbers

        memos = parse_memo_numbers(args.memos) or None
        vendors = parse_vendor_numbers(args.vendors) or None
        folio_file = args.folio_file

        if folio_file is not None and not memos:
            print("ERROR: --folio-file requiere --memos (lista de memos dentro del archivo).")
            return 2

        print(f"Cargando Panoptic: {args.raw_panoptic}")
        if folio_file is not None:
            print(f"Archivo(s) EC ({len(folio_file)}): {', '.join(str(p) for p in folio_file)}")
        else:
            print(f"Buscando folios en: {args.folios_dir}")
        if memos:
            print(f"Memos (lista): {sorted(memos)}")
        if vendors:
            print(f"Proveedores filtrados: {sorted(vendors)}")
        print()

        results = cross_all_estados_cuenta(
            args.raw_panoptic, args.folios_dir, args.output_dir,
            memo_from=args.memo_from, memo_to=args.memo_to,
            print_fn=print,
            memos=memos, vendors=vendors, folio_file=folio_file,
        )

        ok     = [r for r in results if r.ok]
        failed = [r for r in results if not r.ok]

        for r in ok:
            print(f"  OK  {r.memo_id}  ->  {r.output_path}")
        for r in failed:
            print(f"  ERR {r.memo_id}  {r.error}")

        print()
        print(f"Completados: {len(ok)} | Errores: {len(failed)}")
        print(f"Reportes guardados en: {args.output_dir.resolve()}")
        return 1 if failed else 0

    if args.command == "cross-nivel-servicio":
        from .conciliation.nivel_servicio import run_nivel_servicio_from_file

        print(f"Cargando Panoptic: {args.raw_panoptic}")
        if args.solo_capa1:
            print("Modo: SOLO Capa 1 (Bitácora vs Panoptic) — no se leen los bloques del EC.")
        else:
            print(f"Bloques EC: {args.blocks_dir}")
        print()
        try:
            res = run_nivel_servicio_from_file(
                args.raw_panoptic, args.blocks_dir, args.bitacora, args.output_dir,
                solo_capa1=args.solo_capa1,
            )
        except Exception as exc:
            print(f"Error: {exc}")
            return 1

        print()
        print(f"  [Capa 1 - Bitacora vs Panoptic] coinciden:    {res.bita_coincide}")
        print(f"  [Capa 1 - Bitacora vs Panoptic] NO coinciden: {res.bita_no_coincide}")
        if not args.solo_capa1:
            print(f"  [Capa 2 - EC vs Panoptic] coincidentes:       {res.matched_vendors}")
            print(f"  [Capa 2 - EC vs Panoptic] descuadre/sin match:{res.mismatched_vendors}")
            print(f"  Panoptic NS sin EC:                           {res.panoptic_sin_ec}")
            print(f"  Claims para carga (actualizados):             {res.claims_para_carga}")
        print(f"  Reporte: {res.output_path}")
        if res.posting_date_path:
            print(f"  Plantilla PostingDate: {res.posting_date_path}")
            print(f"  Plantilla Recoveries:  {res.recoveries_path}")
            print("  NOTA: las plantillas SOLO se generaron en disco — NO se subieron a Panoptic.")
        return 0 if res.ok else 1

    if args.command == "cross-nivel-servicio-septdic":
        from .conciliation.nivel_servicio import run_nivel_servicio_septdic_from_file

        print(f"Cargando Panoptic: {args.raw_panoptic}")
        if args.solo_capa1:
            print("Modo: SOLO Capa 1 (Bitácora vs Panoptic) — no se leen los bloques del EC.")
        else:
            print(f"Bloques EC: {args.blocks_dir}")
        print()
        try:
            res = run_nivel_servicio_septdic_from_file(
                args.raw_panoptic, args.blocks_dir, args.bitacora, args.output_dir,
                provider_blocks_path=args.provider_blocks, solo_capa1=args.solo_capa1,
            )
        except Exception as exc:
            print(f"Error: {exc}")
            return 1

        print()
        print(f"  [Capa 1 - Bitacora vs Panoptic] coinciden:    {res.bita_coincide}")
        print(f"  [Capa 1 - Bitacora vs Panoptic] NO coinciden: {res.bita_no_coincide}")
        if not args.solo_capa1:
            print(f"  [Capa 2 - EC vs Panoptic] coincidentes:       {res.matched_vendors}")
            print(f"  [Capa 2 - EC vs Panoptic] descuadre/sin match:{res.mismatched_vendors}")
            print(f"  Panoptic NS sin EC:                           {res.panoptic_sin_ec}")
            print(f"  Claims para carga (actualizados):             {res.claims_para_carga}")
        print(f"  Reporte: {res.output_path}")
        if res.posting_date_path:
            print(f"  Plantilla PostingDate: {res.posting_date_path}")
            print(f"  Plantilla Recoveries:  {res.recoveries_path}")
            print("  NOTA: las plantillas SOLO se generaron en disco — NO se subieron a Panoptic.")
        return 0 if res.ok else 1

    if args.command == "run-etapa2":
        try:
            from .panoptic.downloader import download_xlsx  # noqa: F401 — valida dependencia
        except ModuleNotFoundError as exc:
            if exc.name == "playwright":
                parser.exit(
                    1,
                    "Falta instalar Playwright. Ejecuta: "
                    "python -m pip install -r requirements.txt\n",
                )
            raise

        from .conciliation.estado_cuenta import run_etapa2

        settings = load_panoptic_settings(args.config).with_overrides(
            start_url=args.url,
            download_dir=args.download_dir,
            browser_profile_dir=args.profile_dir,
            login_email=args.email,
            default_timeout_ms=args.timeout_ms,
            headless=True if args.headless else None,
        )

        try:
            results = run_etapa2(
                folios_dir=args.folios_dir,
                output_dir=args.output_dir,
                memo_from=args.memo_from,
                memo_to=args.memo_to,
                download_dir=args.download_dir,
                panoptic_settings=settings,
                view_name=args.view_name,
            )
        except Exception as exc:
            print(f"Error: {exc}")
            return 1

        failed = [r for r in results if not r.ok]
        print()
        print(f"Proceso Etapa 2 completo. Reportes en: {args.output_dir.resolve()}")
        return 1 if failed else 0

    if args.command == "consolidate":
        from .conciliation.processing import consolidate_results

        print(f"Consolidando archivos en: {args.output_dir}")
        result_path = consolidate_results(args.output_dir, args.out_file)
        print(f"Consolidado generado en: {result_path}")
        return 0

    if args.command == "run-all":
        try:
            from .panoptic.downloader import download_xlsx  # noqa: F401 — valida dependencia
        except ModuleNotFoundError as exc:
            if exc.name == "playwright":
                parser.exit(
                    1,
                    "Falta instalar Playwright. Ejecuta: "
                    "python -m pip install -r requirements.txt\n",
                )
            raise

        from .conciliation.processing import run_all

        settings = load_panoptic_settings(args.config).with_overrides(
            start_url=args.url,
            download_dir=args.download_dir,
            browser_profile_dir=args.profile_dir,
            login_email=args.email,
            default_timeout_ms=args.timeout_ms,
            headless=True if args.headless else None,
        )

        try:
            consolidated = run_all(
                memo_dir=args.memo_dir,
                output_dir=args.output_dir,
                memo_from=args.memo_from,
                memo_to=args.memo_to,
                download_dir=args.download_dir,
                panoptic_settings=settings,
                view_name=args.view_name,
            )
        except Exception as exc:
            print(f"Error: {exc}")
            return 1

        print()
        print(f"Proceso completo. Consolidado final: {consolidated}")
        return 0

    if args.command == "update-claim-statuses":
        from .conciliation.estado_cuenta import get_status_update_claims
        from .panoptic.workflows import update_claim_statuses

        etapa2_path: Path = args.etapa2_file
        if not etapa2_path.exists():
            print(f"Error: el archivo no existe: {etapa2_path}")
            return 1

        print(f"Leyendo claims de: {etapa2_path}")
        try:
            invoice_ready, posted = get_status_update_claims(etapa2_path)
        except Exception as exc:
            print(f"Error al leer el archivo de Etapa 2: {exc}")
            return 1

        print(f"  Invoice ready : {len(invoice_ready)} claims")
        print(f"  Posted        : {len(posted)} claims")

        if not invoice_ready and not posted:
            print("No hay claims para actualizar.")
            return 0

        settings = load_panoptic_settings(args.config).with_overrides(
            start_url=args.url,
            browser_profile_dir=args.profile_dir,
            login_email=args.email,
            default_timeout_ms=args.timeout_ms,
            headless=True if args.headless else None,
        )

        try:
            update_claim_statuses(
                settings,
                invoice_ready_claims=invoice_ready,
                posted_claims=posted,
                view_name=args.view_name,
                batch_size=args.batch_size,
            )
        except Exception as exc:
            print(f"Error al actualizar Status en Panoptic: {exc}")
            return 1

        return 0

    parser.error(f"Comando no soportado: {args.command}")
    return 2
