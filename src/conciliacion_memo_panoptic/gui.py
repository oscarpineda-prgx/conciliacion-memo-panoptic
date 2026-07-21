"""GUI de Conciliación MEMO × Panoptic — PRGX Soriana Audit Suite."""
from __future__ import annotations

import queue
import threading
from datetime import datetime
from pathlib import Path
from tkinter import filedialog

import customtkinter as ctk
from PIL import Image

from .paths import PROJECT_ROOT

# ---------------------------------------------------------------------------
# Assets
# ---------------------------------------------------------------------------
_ASSETS       = Path(__file__).parent / "assets"
_ICON_PRGX    = _ASSETS / "prgx-icon.png"
_ICON_SORIANA = _ASSETS / "Soriana-Logo.png"

# ---------------------------------------------------------------------------
# Color palettes PRGX
# ---------------------------------------------------------------------------
_DARK: dict[str, str] = {
    "bg1":     "#21212C",
    "bg2":     "#191921",
    "card":    "#2C2C3A",
    "card2":   "#353545",
    "accent":  "#611EEC",
    "blue":    "#2E7FDB",
    "t1":      "#E8EDF2",
    "t2":      "#7A8490",
    "border":  "#3B2D68",
    "sep":     "#323244",
    "pbar_bg": "#21212C",
    "s_idle":  "#383855",
    "s_run":   "#2E7FDB",
    "s_ok":    "#00C820",
    "s_err":   "#E63350",
    "btn_h":   "#1A5FB4",
    "cta_h":   "#4A0FB0",
}

_LIGHT: dict[str, str] = {
    "bg1":     "#EEF2F7",
    "bg2":     "#E0E7F0",
    "card":    "#FFFFFF",
    "card2":   "#F3F6FA",
    "accent":  "#611EEC",
    "blue":    "#1A5FB4",
    "t1":      "#1C1C2E",
    "t2":      "#6B7280",
    "border":  "#C5BCE0",
    "sep":     "#DDE2EA",
    "pbar_bg": "#E0E7F0",
    "s_idle":  "#C8D0DA",
    "s_run":   "#1A5FB4",
    "s_ok":    "#008C1A",
    "s_err":   "#DC2626",
    "btn_h":   "#0D4A8A",
    "cta_h":   "#4A0FB0",
}

_MEMO_DIR_DEFAULT   = Path(r"X:\Soriana\00 - AUDITORIA 2020 - 2024\Cargos")
_FOLIOS_DIR_DEFAULT = Path(r"X:\Soriana\00 - AUDITORIA 2020 - 2024\FOLIOS COMPENSATORIOS")
_VIEW_NAME_DEFAULT  = "MONICA_3"

_ERR_TOKENS = ("error", "exception", "traceback")
_OK_TOKENS  = ("completad", " ok |", "ok.", "descargado", "actualizado", "generado")


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------
class ConciliacionApp(ctk.CTk):

    def __init__(self) -> None:
        super().__init__()
        self._theme          = "light"
        self._palette        = _LIGHT
        self._q:               queue.Queue[str]              = queue.Queue()
        self._running        = False
        self._cancel_event   = threading.Event()
        self._headless_var   = ctk.BooleanVar(value=False)
        self._manual_var     = ctk.BooleanVar(value=False)
        self._ec_file_paths:   list[Path]                    = []
        self._status_dots:     dict[str, ctk.CTkLabel]       = {}
        self._progress_bars:   dict[str, ctk.CTkProgressBar] = {}
        self._pulse_tasks:     dict[str, str]                 = {}
        self._panoptic_path:   Path | None                   = self._find_latest_panoptic()

        ctk.set_appearance_mode("light")
        ctk.set_default_color_theme("dark-blue")
        self._setup_window()
        self._build_ui()
        self._poll_queue()

    # ── Window ──────────────────────────────────────────────────────────────

    def _setup_window(self) -> None:
        self.title("Conciliación MEMO × Panoptic — PRGX")
        self.geometry("1160x940")
        self.minsize(1000, 760)
        self.configure(fg_color=self._c("bg1"))
        if _ICON_PRGX.exists():
            try:
                from PIL import ImageTk
                self._tk_icon = ImageTk.PhotoImage(Image.open(_ICON_PRGX).resize((32, 32)))
                self.iconphoto(True, self._tk_icon)
            except Exception:
                pass

    def _c(self, key: str) -> str:
        return self._palette[key]

    # ── Build ────────────────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        self.grid_rowconfigure(3, weight=3)   # área de tarjetas (scrollable)
        self.grid_rowconfigure(4, weight=2)   # log
        self.grid_columnconfigure(0, weight=1)
        self._build_header()          # row 0
        self._build_config_bar()      # row 1
        self._build_manual_panel()    # row 2 (oculto salvo en modo manual)
        self._build_main_area()       # row 3
        self._build_log_area()        # row 4

    # ── Header ───────────────────────────────────────────────────────────────

    def _build_header(self) -> None:
        hdr = ctk.CTkFrame(self, fg_color=self._c("bg2"), corner_radius=0, height=76)
        hdr.grid(row=0, column=0, sticky="ew")
        hdr.grid_propagate(False)
        hdr.grid_columnconfigure(1, weight=1)

        # Accent stripe at very top (PRGX signature line)
        ctk.CTkFrame(hdr, fg_color=self._c("accent"), height=3, corner_radius=0).grid(
            row=0, column=0, columnspan=6, sticky="ew",
        )

        # PRGX icon
        if _ICON_PRGX.exists():
            img = ctk.CTkImage(Image.open(_ICON_PRGX), size=(42, 42))
            ctk.CTkLabel(hdr, image=img, text="").grid(row=1, column=0, padx=(18, 10), pady=(10, 10))

        # Title block
        title_frame = ctk.CTkFrame(hdr, fg_color="transparent")
        title_frame.grid(row=1, column=1, sticky="w", pady=(10, 10))
        ctk.CTkLabel(
            title_frame, text="Conciliación MEMO × Panoptic",
            font=ctk.CTkFont("Segoe UI", 17, weight="bold"),
            text_color=self._c("t1"),
        ).pack(anchor="w")
        ctk.CTkLabel(
            title_frame, text="PRGX  ·  Soriana Audit Suite",
            font=ctk.CTkFont("Segoe UI", 10),
            text_color=self._c("t2"),
        ).pack(anchor="w")

        # Soriana logo
        if _ICON_SORIANA.exists():
            slogo = ctk.CTkImage(Image.open(_ICON_SORIANA), size=(140, 40))
            ctk.CTkLabel(hdr, image=slogo, text="").grid(row=1, column=2, padx=(0, 14), pady=(10, 10))

        # Thin vertical divider
        ctk.CTkFrame(hdr, fg_color=self._c("border"), width=1, height=34).grid(
            row=1, column=3, padx=8, pady=(10, 10),
        )

        # Theme toggle — text is the mode you'll switch TO
        theme_text = "🌙  Oscuro" if self._theme == "dark" else "☀  Claro"
        self._theme_btn = ctk.CTkButton(
            hdr, text=theme_text, width=96, height=30,
            font=ctk.CTkFont("Segoe UI", 11),
            fg_color=self._c("card"), hover_color=self._c("card2"),
            text_color=self._c("t2"), corner_radius=15,
            border_width=1, border_color=self._c("border"),
            command=self._toggle_theme,
        )
        self._theme_btn.grid(row=1, column=4, padx=(0, 18), pady=(10, 10))

    # ── Config bar ───────────────────────────────────────────────────────────

    def _build_config_bar(self) -> None:
        bar = ctk.CTkFrame(self, fg_color=self._c("card"), corner_radius=0, height=54)
        bar.grid(row=1, column=0, sticky="ew")
        bar.grid_propagate(False)

        kw = {"padx": 10, "pady": 14}
        ctk.CTkLabel(bar, text="Memos:", text_color=self._c("t2"),
                     font=ctk.CTkFont("Segoe UI", 12)).pack(side="left", **kw)
        self._memos_var = ctk.StringVar(value="40-56")
        ctk.CTkEntry(bar, textvariable=self._memos_var, width=130, height=30,
                     placeholder_text="40-56  o  48, 49, 50",
                     fg_color=self._c("bg1"), text_color=self._c("t1"),
                     border_color=self._c("border")).pack(side="left", padx=(0, 12), pady=14)

        ctk.CTkFrame(bar, fg_color=self._c("sep"), width=1, height=30).pack(side="left", padx=4, pady=14)

        ctk.CTkCheckBox(
            bar, text="Ejecución manual", variable=self._manual_var,
            command=self._toggle_manual,
            font=ctk.CTkFont("Segoe UI", 11, weight="bold"),
            text_color=self._c("accent"),
            fg_color=self._c("accent"), hover_color=self._c("cta_h"),
            checkmark_color="#FFFFFF", border_color=self._c("border"),
            width=20, height=20,
        ).pack(side="left", padx=(10, 14), pady=14)

        ctk.CTkFrame(bar, fg_color=self._c("sep"), width=1, height=30).pack(side="left", padx=4, pady=14)

        ctk.CTkLabel(bar, text="Panoptic XLSX:", text_color=self._c("t2"),
                     font=ctk.CTkFont("Segoe UI", 12)).pack(side="left", padx=(14, 8), pady=14)
        pan_text  = self._panoptic_path.name if self._panoptic_path else "— ninguno seleccionado —"
        pan_color = self._c("t1") if self._panoptic_path else self._c("s_err")
        self._pan_label = ctk.CTkLabel(
            bar, text=pan_text, text_color=pan_color,
            font=ctk.CTkFont("Segoe UI", 11), width=280, anchor="w",
        )
        self._pan_label.pack(side="left", padx=(0, 6), pady=14)
        ctk.CTkButton(
            bar, text="📂", width=34, height=30,
            fg_color=self._c("card2"), hover_color=self._c("bg1"),
            text_color=self._c("t1"), corner_radius=6,
            command=self._pick_panoptic,
        ).pack(side="left", padx=(0, 16), pady=14)

        # Headless toggle
        ctk.CTkFrame(bar, fg_color=self._c("sep"), width=1, height=30).pack(
            side="right", padx=4, pady=14,
        )
        ctk.CTkCheckBox(
            bar, text="Silencioso", variable=self._headless_var,
            font=ctk.CTkFont("Segoe UI", 11),
            text_color=self._c("t2"),
            fg_color=self._c("accent"), hover_color=self._c("cta_h"),
            checkmark_color="#FFFFFF", border_color=self._c("border"),
            width=20, height=20,
        ).pack(side="right", padx=(0, 10), pady=14)
        ctk.CTkLabel(
            bar, text="🔇",
            font=ctk.CTkFont("Segoe UI", 14),
            text_color=self._c("t2"),
        ).pack(side="right", padx=(8, 2), pady=14)

        # Stop button — right-aligned, disabled until an operation runs
        ctk.CTkFrame(bar, fg_color=self._c("sep"), width=1, height=30).pack(
            side="right", padx=4, pady=14,
        )
        self._stop_btn = ctk.CTkButton(
            bar, text="■  Detener", width=96, height=30,
            font=ctk.CTkFont("Segoe UI", 11, weight="bold"),
            fg_color="#CC1133", hover_color="#991022",
            text_color=("#FFFFFF", "#FFFFFF"),
            corner_radius=6, state="disabled",
            command=self._stop_operation,
        )
        self._stop_btn.pack(side="right", padx=(0, 16), pady=14)

    # ── Panel de modo manual (plegable) ───────────────────────────────────────

    def _build_manual_panel(self) -> None:
        panel = ctk.CTkFrame(self, fg_color=self._c("card2"), corner_radius=0)
        panel.grid(row=2, column=0, sticky="ew")
        panel.grid_columnconfigure(0, weight=1)
        self._manual_panel = panel

        ctk.CTkFrame(panel, fg_color=self._c("accent"), height=2, corner_radius=0).grid(
            row=0, column=0, columnspan=2, sticky="ew")
        ctk.CTkLabel(
            panel, text="⚙  Modo manual — corre solo los Memos/Proveedores indicados; EC en un archivo único (Etapa 2)",
            font=ctk.CTkFont("Segoe UI", 11, weight="bold"), text_color=self._c("accent"),
        ).grid(row=1, column=0, columnspan=2, sticky="w", padx=14, pady=(8, 2))

        # Izquierda: proveedores
        left = ctk.CTkFrame(panel, fg_color="transparent")
        left.grid(row=2, column=0, sticky="ew", padx=14, pady=(0, 10))
        left.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(left, text="Proveedores (Vendor number, uno por línea):",
                     font=ctk.CTkFont("Segoe UI", 11), text_color=self._c("t2")).grid(
            row=0, column=0, sticky="w")
        self._vendors_box = ctk.CTkTextbox(
            left, height=70, fg_color=self._c("bg1"), text_color=self._c("t1"),
            font=ctk.CTkFont("Consolas", 11), border_width=1,
            border_color=self._c("border"), corner_radius=6)
        self._vendors_box.grid(row=1, column=0, sticky="ew", pady=(3, 0))

        # Derecha: archivo EC
        right = ctk.CTkFrame(panel, fg_color="transparent")
        right.grid(row=2, column=1, sticky="nw", padx=(6, 14), pady=(0, 10))
        ctk.CTkLabel(right, text="Archivo(s) Estado de Cuenta (varios memos · solo Etapa 2):",
                     font=ctk.CTkFont("Segoe UI", 11), text_color=self._c("t2")).pack(anchor="w")
        picker = ctk.CTkFrame(right, fg_color="transparent")
        picker.pack(anchor="w", pady=(4, 0))
        self._ec_label = ctk.CTkLabel(
            picker, text=self._ec_label_text(), text_color=self._c("t1"),
            font=ctk.CTkFont("Segoe UI", 11), width=280, anchor="w")
        self._ec_label.pack(side="left", padx=(0, 6))
        ctk.CTkButton(picker, text="📂", width=34, height=30, fg_color=self._c("card"),
                      hover_color=self._c("bg1"), text_color=self._c("t1"), corner_radius=6,
                      command=self._pick_ec_file).pack(side="left")
        ctk.CTkButton(picker, text="✕", width=28, height=30, fg_color=self._c("card"),
                      hover_color=self._c("bg1"), text_color=self._c("t1"), corner_radius=6,
                      command=self._clear_ec_files).pack(side="left", padx=(4, 0))
        ctk.CTkLabel(right, text="Puedes seleccionar varios · la salida va a outputs/EtapaX_Manual/",
                     font=ctk.CTkFont("Segoe UI", 10), text_color=self._c("t2")).pack(
            anchor="w", pady=(6, 0))

        if not self._manual_var.get():
            panel.grid_remove()

    def _ec_label_text(self) -> str:
        n = len(self._ec_file_paths)
        if n == 0:
            return "— ninguno seleccionado —"
        if n == 1:
            return self._ec_file_paths[0].name
        return f"{n} archivos seleccionados"

    def _clear_ec_files(self) -> None:
        self._ec_file_paths = []
        self._ec_label.configure(text=self._ec_label_text(), text_color=self._c("t1"))
        self._log("Archivos EC (manual): selección limpiada.")

    def _toggle_manual(self) -> None:
        if self._manual_var.get():
            self._manual_panel.grid()
            self._log("Modo manual ACTIVADO — se filtra por Memos + Proveedores; salida a outputs/EtapaX_Manual/")
        else:
            self._manual_panel.grid_remove()
            self._log("Modo manual desactivado — ejecución normal.")

    def _pick_ec_file(self) -> None:
        paths = filedialog.askopenfilenames(
            title="Seleccionar archivo(s) de Estado de Cuenta (uno o varios)",
            filetypes=[("Excel", "*.xlsx *.xls"), ("Todos", "*.*")],
            initialdir=str(_FOLIOS_DIR_DEFAULT),
        )
        if paths:
            self._ec_file_paths = [Path(p) for p in paths]
            self._ec_label.configure(text=self._ec_label_text(), text_color=self._c("t1"))
            names = ", ".join(p.name for p in self._ec_file_paths)
            self._log(f"Archivo(s) EC (manual): {names}")

    # ── Main area ─────────────────────────────────────────────────────────────

    def _build_main_area(self) -> None:
        main = ctk.CTkScrollableFrame(self, fg_color=self._c("bg1"), corner_radius=0)
        main.grid(row=3, column=0, sticky="nsew", padx=0, pady=(2, 0))
        main.grid_columnconfigure((0, 1), weight=1, uniform="col")
        # Fila 0: Etapa 1 y 2  |  Fila 1: Etapa 3 y 4
        self._build_etapa1_card(main)
        self._build_etapa2_card(main)
        self._build_etapa3_card(main)
        self._build_etapa4_card(main)

    def _build_etapa1_card(self, parent: ctk.CTkFrame) -> None:
        card = self._make_card(parent, col=0)
        self._section_title(card, "ETAPA 1", "Conciliación MEMO vs Panoptic", "01")
        self._cta_button(card, "▶  Ejecutar Etapa 1 completa",  "e1_all",         self._run_etapa1_all)
        self._separator(card)
        self._step_button(card, "  ↓  Descargar Panoptic",          "e1_download",    self._run_download)
        self._step_button(card, "  ⊞  Conciliar todos los memos",   "e1_reconcile",   self._run_reconcile)
        self._step_button(card, "  ≡  Consolidar resultados",        "e1_consolidate", self._run_consolidate)
        self._separator(card)
        self._hint(card, "Sube el Bulk Update a Panoptic antes de continuar")
        self._step_button(card, "  ↑  Subir Posting Reference",      "e1_upload_ref",  self._run_upload_ref)

    def _build_etapa2_card(self, parent: ctk.CTkFrame) -> None:
        card = self._make_card(parent, col=1)
        self._section_title(card, "ETAPA 2", "Cruce con Estado de Cuenta", "02")
        self._cta_button(card, "▶  Ejecutar Etapa 2 completa",  "e2_all",          self._run_etapa2_all)
        self._separator(card)
        self._hint(card, "Usa el Panoptic seleccionado en la barra superior")
        self._step_button(card, "  ⇄  Cruzar Estado de Cuenta",     "e2_cross",        self._run_cross_ec)
        self._separator(card)
        self._hint(card, "Subir plantillas generadas a Panoptic")
        self._step_button(card, "  ↑  Subir Posting Date + Batch",  "e2_upload_post",  self._run_upload_posting)
        self._step_button(card, "  ↑  Subir Recoveries / Clearing", "e2_upload_rec",   self._run_upload_recoveries)
        self._separator(card)
        self._hint(card, "Validar y actualizar Status (Invoice ready / Posted)")
        self._step_button(card, "  ✦  Actualizar Status en Panoptic", "e2_update_status", self._run_update_status)

    def _build_etapa3_card(self, parent: ctk.CTkFrame) -> None:
        card = self._make_card(parent, col=0, row=1)
        self._section_title(card, "ETAPA 3", "Nivel de Servicio · Ene-Ago 2025", "03")
        self._cta_button(card, "▶  Ejecutar Etapa 3 completa", "e3_all", self._run_etapa3_all)
        self._separator(card)
        self._hint(card, "Usa el Panoptic de arriba · Bitácora + bloques EC (~7 min)")
        self._step_button(card, "  ⇄  Solo Capa 1 (Bitácora vs Panoptic)", "e3_capa1", self._run_etapa3_capa1)

    def _build_etapa4_card(self, parent: ctk.CTkFrame) -> None:
        card = self._make_card(parent, col=1, row=1)
        self._section_title(card, "ETAPA 4", "Nivel de Servicio · Sep-Dic 2025", "04")
        self._cta_button(card, "▶  Ejecutar Etapa 4 completa", "e4_all", self._run_etapa4_all)
        self._separator(card)
        self._hint(card, "Usa el Panoptic de arriba · Bitácora 'resto' + bloques (~7 min)")
        self._step_button(card, "  ⇄  Solo Capa 1 (Bitácora vs Panoptic)", "e4_capa1", self._run_etapa4_capa1)

    # ── Log area ──────────────────────────────────────────────────────────────

    def _build_log_area(self) -> None:
        frame = ctk.CTkFrame(self, fg_color=self._c("bg2"), corner_radius=0)
        frame.grid(row=4, column=0, sticky="nsew", padx=0, pady=(2, 0))
        frame.grid_columnconfigure(0, weight=1)
        frame.grid_rowconfigure(1, weight=1)

        hdr = ctk.CTkFrame(frame, fg_color="transparent")
        hdr.grid(row=0, column=0, sticky="ew", padx=16, pady=(8, 2))
        ctk.CTkLabel(hdr, text="LOG DE EJECUCIÓN",
                     font=ctk.CTkFont("Segoe UI", 9, weight="bold"),
                     text_color=self._c("t2")).pack(side="left")
        ctk.CTkButton(hdr, text="Limpiar", width=60, height=22,
                      font=ctk.CTkFont("Segoe UI", 10),
                      fg_color=self._c("card2"), hover_color=self._c("card"),
                      text_color=self._c("t2"), corner_radius=4,
                      command=self._clear_log).pack(side="right")

        self._log_box = ctk.CTkTextbox(
            frame, fg_color=self._c("bg2"), text_color=self._c("t1"),
            font=ctk.CTkFont("Consolas", 11),
            border_width=0, corner_radius=0,
        )
        self._log_box.grid(row=1, column=0, sticky="nsew")
        self._log_box.configure(state="disabled")

        # Colored tags on the underlying tk.Text
        tb = self._log_box._textbox
        tb.tag_configure("ts",    foreground=self._c("t2"))
        tb.tag_configure("info",  foreground=self._c("t1"))
        tb.tag_configure("ok",    foreground=self._c("s_ok"))
        tb.tag_configure("error", foreground=self._c("s_err"))

    # ── Widget helpers ────────────────────────────────────────────────────────

    def _make_card(self, parent: ctk.CTkFrame, col: int, row: int = 0) -> ctk.CTkFrame:
        px_l = 16 if col == 0 else 8
        px_r =  8 if col == 0 else 16
        card = ctk.CTkFrame(parent, fg_color=self._c("card"), corner_radius=12,
                            border_width=1, border_color=self._c("border"))
        card.grid(row=row, column=col, sticky="nsew",
                  padx=(px_l, px_r), pady=(14 if row == 0 else 6, 14))
        return card

    def _section_title(self, parent: ctk.CTkFrame, title: str, subtitle: str, badge: str) -> None:
        # Accent stripe at top of card
        ctk.CTkFrame(parent, fg_color=self._c("accent"), height=3, corner_radius=0).pack(
            fill="x", padx=0,
        )
        block = ctk.CTkFrame(parent, fg_color="transparent")
        block.pack(fill="x", padx=18, pady=(12, 6))

        title_row = ctk.CTkFrame(block, fg_color="transparent")
        title_row.pack(fill="x")

        # Number badge
        ctk.CTkLabel(
            title_row, text=badge,
            font=ctk.CTkFont("Segoe UI", 10, weight="bold"),
            text_color="#FFFFFF", fg_color=self._c("accent"),
            width=26, height=20, corner_radius=6,
        ).pack(side="left", padx=(0, 8))

        ctk.CTkLabel(
            title_row, text=title,
            font=ctk.CTkFont("Segoe UI", 14, weight="bold"),
            text_color=self._c("t1"),
        ).pack(side="left", anchor="w")

        ctk.CTkLabel(
            block, text=subtitle,
            font=ctk.CTkFont("Segoe UI", 11),
            text_color=self._c("t2"),
        ).pack(anchor="w", pady=(3, 0))

    def _cta_button(self, parent: ctk.CTkFrame, text: str, key: str, command) -> None:
        outer = ctk.CTkFrame(parent, fg_color="transparent")
        outer.pack(fill="x", padx=14, pady=(8, 2))

        row = ctk.CTkFrame(outer, fg_color="transparent")
        row.pack(fill="x")
        dot = ctk.CTkLabel(row, text="●", text_color=self._c("s_idle"),
                           font=ctk.CTkFont("Segoe UI", 8), width=12)
        dot.pack(side="left", padx=(0, 5))
        self._status_dots[key] = dot
        ctk.CTkButton(
            row, text=text,
            font=ctk.CTkFont("Segoe UI", 12, weight="bold"),
            fg_color=self._c("accent"), hover_color=self._c("cta_h"),
            text_color="#FFFFFF", height=38, corner_radius=8,
            command=command,
        ).pack(fill="x")

        pbar = ctk.CTkProgressBar(outer, height=3, corner_radius=2,
                                   fg_color=self._c("pbar_bg"),
                                   progress_color=self._c("s_idle"),
                                   indeterminate_speed=2.0)
        pbar.set(0)
        pbar.pack(fill="x", padx=18, pady=(2, 0))
        self._progress_bars[key] = pbar

    def _step_button(self, parent: ctk.CTkFrame, text: str, key: str, command) -> None:
        outer = ctk.CTkFrame(parent, fg_color="transparent")
        outer.pack(fill="x", padx=14, pady=2)

        row = ctk.CTkFrame(outer, fg_color="transparent")
        row.pack(fill="x")
        dot = ctk.CTkLabel(row, text="●", text_color=self._c("s_idle"),
                           font=ctk.CTkFont("Segoe UI", 7), width=12)
        dot.pack(side="left", padx=(0, 5))
        self._status_dots[key] = dot
        ctk.CTkButton(
            row, text=text,
            font=ctk.CTkFont("Segoe UI", 12),
            fg_color=self._c("blue"), hover_color=self._c("btn_h"),
            text_color="#FFFFFF", height=34, corner_radius=7, anchor="w",
            command=command,
        ).pack(fill="x")

        pbar = ctk.CTkProgressBar(outer, height=2, corner_radius=1,
                                   fg_color=self._c("pbar_bg"),
                                   progress_color=self._c("s_idle"),
                                   indeterminate_speed=2.5)
        pbar.set(0)
        pbar.pack(fill="x", padx=18, pady=(1, 0))
        self._progress_bars[key] = pbar

    def _separator(self, parent: ctk.CTkFrame) -> None:
        ctk.CTkFrame(parent, fg_color=self._c("sep"), height=1, corner_radius=0).pack(
            fill="x", padx=14, pady=8,
        )

    def _hint(self, parent: ctk.CTkFrame, text: str) -> None:
        ctk.CTkLabel(parent, text=f"  {text}",
                     font=ctk.CTkFont("Segoe UI", 10),
                     text_color=self._c("t2")).pack(anchor="w", padx=14, pady=(2, 1))

    # ── Theme ─────────────────────────────────────────────────────────────────

    def _toggle_theme(self) -> None:
        memos_text   = self._memos_var.get()
        vendors_text = self._vendors_box.get("1.0", "end-1c") if hasattr(self, "_vendors_box") else ""
        pan_path    = self._panoptic_path
        headless    = self._headless_var.get()
        log_content = self._log_box.get("1.0", "end-1c") if hasattr(self, "_log_box") else ""

        for key in list(self._pulse_tasks):
            self._stop_pulse(key)

        if self._theme == "dark":
            self._theme = "light"
            self._palette = _LIGHT
            ctk.set_appearance_mode("light")
        else:
            self._theme = "dark"
            self._palette = _DARK
            ctk.set_appearance_mode("dark")

        for w in self.winfo_children():
            w.destroy()
        self._status_dots.clear()
        self._progress_bars.clear()

        self.configure(fg_color=self._c("bg1"))
        self._build_ui()

        # Restore transient state
        self._memos_var.set(memos_text)
        if vendors_text.strip() and hasattr(self, "_vendors_box"):
            self._vendors_box.insert("1.0", vendors_text)
        self._headless_var.set(headless)
        self._panoptic_path = pan_path
        if pan_path:
            self._pan_label.configure(text=pan_path.name, text_color=self._c("t1"))
        if self._running:
            self._stop_btn.configure(state="normal")
        if log_content:
            self._log_box.configure(state="normal")
            self._log_box.insert("1.0", log_content)
            self._log_box.see("end")
            self._log_box.configure(state="disabled")

    # ── Pickers ───────────────────────────────────────────────────────────────

    def _pick_panoptic(self) -> None:
        path = filedialog.askopenfilename(
            title="Seleccionar archivo Panoptic XLSX",
            filetypes=[("Excel", "*.xlsx *.xls"), ("Todos", "*.*")],
            initialdir=str(PROJECT_ROOT / "data" / "raw" / "panoptic"),
        )
        if path:
            self._panoptic_path = Path(path)
            self._pan_label.configure(text=self._panoptic_path.name, text_color=self._c("t1"))
            self._log(f"Panoptic seleccionado: {self._panoptic_path.name}")

    def _pick_xlsx_file(self, title: str) -> Path | None:
        path = filedialog.askopenfilename(
            title=title,
            filetypes=[("Excel", "*.xlsx *.xls"), ("Todos", "*.*")],
            initialdir=str(PROJECT_ROOT / "outputs"),
        )
        return Path(path) if path else None

    # ── Logging ───────────────────────────────────────────────────────────────

    def _log(self, msg: str = "") -> None:
        if not msg:
            self._q.put("\n")
            return
        ts = datetime.now().strftime("%H:%M:%S")
        self._q.put(f"[{ts}]  {msg}\n")

    def _append_log(self, text: str) -> None:
        try:
            tb = self._log_box._textbox
            tb.configure(state="normal")
            if "]  " in text:
                ts_part, msg_part = text.split("]  ", 1)
                low = msg_part.lower()
                tag = ("error" if any(t in low for t in _ERR_TOKENS) else
                       "ok"    if any(t in low for t in _OK_TOKENS)  else
                       "info")
                tb.insert("end", ts_part + "]  ", "ts")
                tb.insert("end", msg_part, tag)
            else:
                tb.insert("end", text, "info")
            tb.see("end")
            tb.configure(state="disabled")
        except Exception:
            pass

    def _clear_log(self) -> None:
        self._log_box.configure(state="normal")
        self._log_box.delete("1.0", "end")
        self._log_box.configure(state="disabled")

    def _poll_queue(self) -> None:
        try:
            while True:
                self._append_log(self._q.get_nowait())
        except queue.Empty:
            pass
        self.after(80, self._poll_queue)

    # ── Status & animation ───────────────────────────────────────────────────

    def _set_status(self, key: str, state: str) -> None:
        dot_colors = {
            "idle": self._c("s_idle"), "running": self._c("s_run"),
            "ok":   self._c("s_ok"),   "error":   self._c("s_err"),
        }
        color = dot_colors.get(state, self._c("s_idle"))

        def _apply() -> None:
            if key in self._status_dots:
                self._status_dots[key].configure(text_color=color)
            if key in self._progress_bars:
                pbar = self._progress_bars[key]
                if state == "running":
                    pbar.configure(mode="indeterminate", progress_color=self._c("s_run"))
                    pbar.start()
                    self._start_pulse(key)
                elif state == "ok":
                    pbar.stop()
                    pbar.configure(mode="determinate", progress_color=self._c("s_ok"))
                    pbar.set(1.0)
                    self._stop_pulse(key)
                elif state == "error":
                    pbar.stop()
                    pbar.configure(mode="determinate", progress_color=self._c("s_err"))
                    pbar.set(1.0)
                    self._stop_pulse(key)
                else:
                    pbar.stop()
                    pbar.configure(mode="determinate", progress_color=self._c("s_idle"))
                    pbar.set(0.0)
                    self._stop_pulse(key)

        self.after(0, _apply)

    def _start_pulse(self, key: str) -> None:
        self._stop_pulse(key)
        self._do_pulse(key, bright=True)

    def _stop_pulse(self, key: str) -> None:
        task = self._pulse_tasks.pop(key, None)
        if task:
            try:
                self.after_cancel(task)
            except Exception:
                pass

    def _do_pulse(self, key: str, bright: bool) -> None:
        if key not in self._status_dots:
            return
        c = self._c("s_run") if bright else self._c("s_idle")
        self._status_dots[key].configure(text_color=c)
        self._pulse_tasks[key] = self.after(500, lambda: self._do_pulse(key, not bright))

    # ── Threading ────────────────────────────────────────────────────────────

    def _get_memos(self) -> set[int] | None:
        """Memos del campo (lista/rango, ej. '40-56' o '48, 49, 50'). None = todos."""
        from .conciliation.processing import parse_memo_numbers
        return parse_memo_numbers(self._memos_var.get()) or None

    def _get_vendors(self) -> set[str] | None:
        """Vendor numbers del textbox — solo en modo manual. None = sin filtro."""
        if not self._manual_var.get():
            return None
        from .conciliation.processing import parse_vendor_numbers
        text = self._vendors_box.get("1.0", "end-1c") if hasattr(self, "_vendors_box") else ""
        return parse_vendor_numbers(text) or None

    def _get_ec_file(self) -> list[Path] | None:
        """Archivo(s) EC — solo en modo manual. None = sin archivos (o modo normal)."""
        if not self._manual_var.get():
            return None
        return list(self._ec_file_paths) if self._ec_file_paths else None

    def _manual_output(self, base: str) -> Path:
        """outputs/{base}_Manual en modo manual; si no, outputs/{base}."""
        sub = f"{base}_Manual" if self._manual_var.get() else base
        return PROJECT_ROOT / "outputs" / sub

    def _run_in_thread(self, key: str, fn, *args) -> None:
        if self._running:
            self._log("Hay una operación en curso. Usa Detener si quieres cancelarla.")
            return
        self._running = True
        self._cancel_event.clear()
        self._set_status(key, "running")
        self.after(0, lambda: self._stop_btn.configure(state="normal"))

        def _wrapper() -> None:
            import traceback as _tb
            try:
                fn(*args)
                if self._cancel_event.is_set():
                    self._log("Operación detenida por el usuario.")
                    self._set_status(key, "idle")
                else:
                    self._set_status(key, "ok")
            except Exception as exc:
                if self._cancel_event.is_set():
                    self._log("Operación detenida.")
                    self._set_status(key, "idle")
                else:
                    self._log(f"ERROR: {exc!r}")
                    for line in _tb.format_exc().splitlines():
                        self._log(f"  {line}")
                    self._set_status(key, "error")
            finally:
                self._running = False
                self.after(0, lambda: self._stop_btn.configure(state="disabled"))

        threading.Thread(target=_wrapper, daemon=True).start()

    def _stop_operation(self) -> None:
        if not self._running:
            return
        self._cancel_event.set()
        self._log("Deteniendo... el paso actual terminará y luego se parará.")

    def _load_settings(self):
        from .settings import load_panoptic_settings
        settings = load_panoptic_settings()
        if self._headless_var.get():
            settings = settings.with_overrides(headless=True)
        return settings

    # ── Helpers ──────────────────────────────────────────────────────────────

    def _find_latest_panoptic(self) -> Path | None:
        pan_dir = PROJECT_ROOT / "data" / "raw" / "panoptic"
        if not pan_dir.exists():
            return None
        files = sorted(pan_dir.glob("*.xlsx"), key=lambda p: p.stat().st_mtime, reverse=True)
        return files[0] if files else None

    def _require_panoptic(self) -> Path | None:
        if not self._panoptic_path or not self._panoptic_path.exists():
            self._log("No hay archivo Panoptic seleccionado. Descarga primero o selecciona un archivo.")
            return None
        return self._panoptic_path

    # ── Etapa 1 ──────────────────────────────────────────────────────────────

    def _run_etapa1_all(self) -> None:
        self._run_in_thread("e1_all", self._etapa1_all_fn)

    def _etapa1_all_fn(self) -> None:
        from .conciliation.processing import reconcile_all_memos, consolidate_results
        from .panoptic.downloader import download_xlsx
        memos    = self._get_memos()
        vendors  = self._get_vendors()
        settings = self._load_settings()
        output   = self._manual_output("Etapa1")

        self._log("ETAPA 1 — Descargando Panoptic...")
        self._set_status("e1_download", "running")
        raw = download_xlsx(settings, view_name=_VIEW_NAME_DEFAULT,
                            cancel_event=self._cancel_event)
        self._panoptic_path = raw
        self.after(0, lambda: self._pan_label.configure(text=raw.name, text_color=self._c("t1")))
        self._log(f"Panoptic descargado: {raw.name}")
        self._set_status("e1_download", "ok")
        if self._cancel_event.is_set():
            return

        self._log("ETAPA 1 — Conciliando memos...")
        self._set_status("e1_reconcile", "running")
        reconcile_all_memos(raw, _MEMO_DIR_DEFAULT, output, memos=memos, vendors=vendors,
                            cancel_event=self._cancel_event)
        self._set_status("e1_reconcile", "ok")
        if self._cancel_event.is_set():
            return

        self._log("ETAPA 1 — Consolidando resultados...")
        self._set_status("e1_consolidate", "running")
        consolidate_results(output)
        self._set_status("e1_consolidate", "ok")

        self._log(f"ETAPA 1 completada. Revisa {output} antes de subir a Panoptic.")

    def _run_download(self) -> None:
        self._run_in_thread("e1_download", self._download_fn)

    def _download_fn(self) -> None:
        from .panoptic.downloader import download_xlsx
        settings = self._load_settings()
        self._log("Descargando Panoptic...")
        raw = download_xlsx(settings, view_name=_VIEW_NAME_DEFAULT,
                            cancel_event=self._cancel_event)
        self._panoptic_path = raw
        self.after(0, lambda: self._pan_label.configure(text=raw.name, text_color=self._c("t1")))
        self._log(f"Descarga completada: {raw.name}")

    def _run_reconcile(self) -> None:
        self._run_in_thread("e1_reconcile", self._reconcile_fn)

    def _reconcile_fn(self) -> None:
        from .conciliation.processing import reconcile_all_memos
        raw = self._require_panoptic()
        if not raw:
            return
        memos   = self._get_memos()
        vendors = self._get_vendors()
        output  = self._manual_output("Etapa1")
        self._log(
            f"Conciliando memos {sorted(memos) if memos else 'todos'} con {raw.name}"
            + (f" · {len(vendors)} proveedores" if vendors else "") + "..."
        )
        reconcile_all_memos(raw, _MEMO_DIR_DEFAULT, output, memos=memos, vendors=vendors,
                            cancel_event=self._cancel_event)
        self._log(f"Conciliación completada. Salida: {output}")

    def _run_consolidate(self) -> None:
        self._run_in_thread("e1_consolidate", self._consolidate_fn)

    def _consolidate_fn(self) -> None:
        from .conciliation.processing import consolidate_results
        output = self._manual_output("Etapa1")
        self._log(f"Consolidando resultados desde {output}...")
        consolidate_results(output)
        self._log("Consolidado generado.")

    def _run_upload_ref(self) -> None:
        file = self._pick_xlsx_file("Seleccionar Claim_Bulk_Update_*.xlsx")
        if file:
            self._run_in_thread("e1_upload_ref", self._upload_ref_fn, file)

    def _upload_ref_fn(self, file: Path) -> None:
        from .panoptic.workflows import upload_claim_updates
        settings = self._load_settings()
        self._log(f"Subiendo Posting Reference: {file.name}...")
        upload_claim_updates(settings, file, view_name=_VIEW_NAME_DEFAULT,
                             cancel_event=self._cancel_event)
        self._log("Posting Reference actualizado en Panoptic.")

    # ── Etapa 2 ──────────────────────────────────────────────────────────────

    def _run_etapa2_all(self) -> None:
        self._run_in_thread("e2_all", self._etapa2_all_fn)

    def _etapa2_all_fn(self) -> None:
        from .conciliation.estado_cuenta import run_etapa2
        memos    = self._get_memos()
        vendors  = self._get_vendors()
        folio    = self._get_ec_file()
        if self._manual_var.get() and folio is None:
            self._log("Modo manual: selecciona el Archivo de Estado de Cuenta (📂 en el panel).")
            return
        settings = self._load_settings()
        output   = self._manual_output("Etapa2")
        self._log("ETAPA 2 — Descargando Panoptic y cruzando con EC...")
        self._set_status("e2_cross", "running")

        def _pf(msg: str = "") -> None:
            self._log(msg)

        results = run_etapa2(
            folios_dir=_FOLIOS_DIR_DEFAULT, output_dir=output,
            panoptic_settings=settings, view_name=_VIEW_NAME_DEFAULT,
            print_fn=_pf, memos=memos, vendors=vendors, folio_file=folio,
        )
        ok  = sum(1 for r in results if r.ok)
        err = sum(1 for r in results if not r.ok)
        self._set_status("e2_cross", "ok" if err == 0 else "error")
        self._log(f"ETAPA 2 completada — {ok} OK | {err} errores. Salida: {output}")

    def _run_cross_ec(self) -> None:
        self._run_in_thread("e2_cross", self._cross_ec_fn)

    def _cross_ec_fn(self) -> None:
        from .conciliation.estado_cuenta import cross_all_estados_cuenta
        raw = self._require_panoptic()
        if not raw:
            return
        memos   = self._get_memos()
        vendors = self._get_vendors()
        folio   = self._get_ec_file()
        if self._manual_var.get() and folio is None:
            self._log("Modo manual: selecciona el Archivo de Estado de Cuenta (📂 en el panel).")
            return
        output  = self._manual_output("Etapa2")
        self._log(
            f"Cruzando EC contra {raw.name} (memos {sorted(memos) if memos else 'todos'})"
            + (f" · {len(vendors)} proveedores" if vendors else "") + "..."
        )
        results = cross_all_estados_cuenta(
            raw, _FOLIOS_DIR_DEFAULT, output,
            print_fn=self._log, memos=memos, vendors=vendors, folio_file=folio,
        )
        ok  = sum(1 for r in results if r.ok)
        err = sum(1 for r in results if not r.ok)
        self._log(f"Cruce completado — {ok} OK | {err} errores. Salida: {output}")

    def _run_upload_posting(self) -> None:
        file = self._pick_xlsx_file("Seleccionar etapa2_M*_PostingDate.xlsx")
        if file:
            self._run_in_thread("e2_upload_post", self._upload_posting_fn, file)

    def _upload_posting_fn(self, file: Path) -> None:
        from .panoptic.workflows import upload_claim_updates
        settings = self._load_settings()
        self._log(f"Subiendo Posting Date + Batch: {file.name}...")
        upload_claim_updates(settings, file, view_name=_VIEW_NAME_DEFAULT,
                             cancel_event=self._cancel_event)
        self._log("Posting submission date y Batch number actualizados en Panoptic.")

    def _run_upload_recoveries(self) -> None:
        file = self._pick_xlsx_file("Seleccionar etapa2_M*_Recoveries.xlsx")
        if file:
            self._run_in_thread("e2_upload_rec", self._upload_rec_fn, file)

    def _upload_rec_fn(self, file: Path) -> None:
        from .panoptic.workflows import upload_recoveries_clearing_data
        settings = self._load_settings()
        self._log(f"Subiendo Recoveries: {file.name}...")
        upload_recoveries_clearing_data(settings, file, view_name=_VIEW_NAME_DEFAULT,
                                        cancel_event=self._cancel_event)
        self._log("Recoveries / Clearing data actualizado en Panoptic.")

    # ── Etapa 2 — Actualizar Status ───────────────────────────────────────────

    def _run_update_status(self) -> None:
        """Abre picker de archivo Etapa 2, lee los claims y muestra el diálogo de previsualización."""
        path = filedialog.askopenfilename(
            title="Seleccionar archivo Etapa 2 (etapa2_M*.xlsx)",
            filetypes=[("Excel", "*.xlsx *.xls"), ("Todos", "*.*")],
            initialdir=str(PROJECT_ROOT / "outputs" / "Etapa2"),
        )
        if not path:
            return
        file = Path(path)

        self._set_status("e2_update_status", "running")
        self._log(f"Leyendo claims de {file.name}...")
        from .conciliation.estado_cuenta import get_status_update_claims
        try:
            invoice_ready, posted = get_status_update_claims(file)
        except Exception as exc:
            self._log(f"Error al leer {file.name}: {exc}")
            self._set_status("e2_update_status", "error")
            return

        self._set_status("e2_update_status", "idle")

        if not invoice_ready and not posted:
            self._log("No hay claims para actualizar en el archivo seleccionado.")
            return

        self._log(
            f"Previsualización lista: {len(invoice_ready)} Invoice ready | "
            f"{len(posted)} Posted"
        )
        self._show_status_preview_dialog(file, invoice_ready, posted)

    def _show_status_preview_dialog(
        self,
        file: Path,
        invoice_ready: list[str],
        posted: list[str],
    ) -> None:
        """Abre un diálogo modal con la previsualización de los cambios de Status."""
        import datetime as _dt

        dlg = ctk.CTkToplevel(self)
        dlg.title("Previsualización — Actualizar Status")
        dlg.geometry("640x560")
        dlg.minsize(520, 460)
        dlg.configure(fg_color=self._c("bg1"))
        dlg.grab_set()
        dlg.focus_set()
        dlg.lift()

        # Accent stripe
        ctk.CTkFrame(dlg, fg_color=self._c("accent"), height=3, corner_radius=0).pack(fill="x")

        # Header
        hdr = ctk.CTkFrame(dlg, fg_color=self._c("card"), corner_radius=0)
        hdr.pack(fill="x")
        ctk.CTkLabel(
            hdr,
            text="Previsualización — Actualizar Status en Panoptic",
            font=ctk.CTkFont("Segoe UI", 13, weight="bold"),
            text_color=self._c("t1"),
        ).pack(side="left", padx=16, pady=12)

        # Body scrollable
        body = ctk.CTkScrollableFrame(dlg, fg_color=self._c("bg1"), corner_radius=0)
        body.pack(fill="both", expand=True)

        # File + date info bar
        info_bar = ctk.CTkFrame(body, fg_color=self._c("card2"), corner_radius=8)
        info_bar.pack(fill="x", padx=16, pady=(12, 8))
        ctk.CTkLabel(
            info_bar,
            text=f"📄  {file.name}",
            font=ctk.CTkFont("Segoe UI", 11),
            text_color=self._c("t1"),
        ).pack(side="left", padx=12, pady=8)
        today_str = _dt.date.today().strftime("%m/%d/%Y")
        ctk.CTkLabel(
            info_bar,
            text=f"Remind date: {today_str}  •  Lote máx: 50",
            font=ctk.CTkFont("Segoe UI", 10),
            text_color=self._c("t2"),
        ).pack(side="right", padx=12, pady=8)

        def _render_group(label: str, dot_color: str, claims: list[str]) -> None:
            grp = ctk.CTkFrame(
                body, fg_color=self._c("card"), corner_radius=8,
                border_width=1, border_color=self._c("border"),
            )
            grp.pack(fill="x", padx=16, pady=(2, 8))

            title_row = ctk.CTkFrame(grp, fg_color="transparent")
            title_row.pack(fill="x", padx=12, pady=(10, 4))
            ctk.CTkLabel(
                title_row, text="●", text_color=dot_color,
                font=ctk.CTkFont("Segoe UI", 10),
            ).pack(side="left", padx=(0, 6))
            ctk.CTkLabel(
                title_row, text=label,
                font=ctk.CTkFont("Segoe UI", 12, weight="bold"),
                text_color=self._c("t1"),
            ).pack(side="left")
            ctk.CTkLabel(
                title_row, text=f"{len(claims)} claims",
                font=ctk.CTkFont("Segoe UI", 11),
                text_color=self._c("t2"),
            ).pack(side="right")

            MAX_SHOW = 40
            shown = claims[:MAX_SHOW]
            rest  = len(claims) - len(shown)
            content = "  ".join(shown)
            if rest > 0:
                content += f"\n  ... y {rest} más"

            txt = ctk.CTkTextbox(
                grp,
                height=min(100, max(36, (len(shown) // 5 + 1) * 18 + 10)),
                fg_color=self._c("bg2"),
                text_color=self._c("t1"),
                font=ctk.CTkFont("Consolas", 10),
                border_width=0, corner_radius=6,
            )
            txt.pack(fill="x", padx=12, pady=(0, 10))
            txt.insert("1.0", content)
            txt.configure(state="disabled")

        if invoice_ready:
            _render_group("Invoice ready", self._c("s_ok"), invoice_ready)
        if posted:
            _render_group("Posted", self._c("blue"), posted)

        # Footer with buttons
        foot = ctk.CTkFrame(dlg, fg_color=self._c("card"), corner_radius=0)
        foot.pack(fill="x", side="bottom")

        total = len(invoice_ready) + len(posted)
        ctk.CTkLabel(
            foot,
            text=f"Total a actualizar: {total} claims",
            font=ctk.CTkFont("Segoe UI", 10),
            text_color=self._c("t2"),
        ).pack(side="left", padx=16, pady=12)

        def _cancel() -> None:
            dlg.destroy()

        def _confirm() -> None:
            dlg.destroy()
            self._run_in_thread(
                "e2_update_status",
                self._update_status_fn,
                invoice_ready,
                posted,
            )

        ctk.CTkButton(
            foot, text="Cancelar",
            width=100, height=32,
            font=ctk.CTkFont("Segoe UI", 11),
            fg_color=self._c("card2"), hover_color=self._c("bg1"),
            text_color=self._c("t2"), corner_radius=7,
            border_width=1, border_color=self._c("border"),
            command=_cancel,
        ).pack(side="right", padx=(6, 16), pady=12)

        ctk.CTkButton(
            foot, text="✔  Confirmar y actualizar",
            width=210, height=32,
            font=ctk.CTkFont("Segoe UI", 11, weight="bold"),
            fg_color=self._c("accent"), hover_color=self._c("cta_h"),
            text_color="#FFFFFF", corner_radius=7,
            command=_confirm,
        ).pack(side="right", padx=6, pady=12)

    def _update_status_fn(self, invoice_ready: list[str], posted: list[str]) -> None:
        from .panoptic.workflows import update_claim_statuses
        settings = self._load_settings()
        self._log("Iniciando actualización de Status en Panoptic...")
        update_claim_statuses(
            settings,
            invoice_ready_claims=invoice_ready,
            posted_claims=posted,
            view_name=_VIEW_NAME_DEFAULT,
            cancel_event=self._cancel_event,
            print_fn=self._log,
        )
        self._log("Actualización de Status completada.")

    # ── Etapa 3 — Nivel de Servicio Ene-Ago ───────────────────────────────────

    def _run_etapa3_all(self) -> None:
        self._run_in_thread("e3_all", self._etapa3_fn, False)

    def _run_etapa3_capa1(self) -> None:
        self._run_in_thread("e3_capa1", self._etapa3_fn, True)

    def _etapa3_fn(self, solo_capa1: bool) -> None:
        from .conciliation.nivel_servicio import (
            run_nivel_servicio_from_file, _DEFAULT_BLOCKS_DIR, _DEFAULT_BITACORA,
        )
        raw = self._require_panoptic()
        if not raw:
            return
        output = PROJECT_ROOT / "outputs" / "Etapa3"
        tag = "Solo Capa 1" if solo_capa1 else "completa"
        self._log(f"ETAPA 3 ({tag}) — Nivel de Servicio Ene-Ago...")
        res = run_nivel_servicio_from_file(
            raw, _DEFAULT_BLOCKS_DIR, _DEFAULT_BITACORA, output,
            solo_capa1=solo_capa1, print_fn=self._log,
        )
        self._log(f"ETAPA 3 completada. Reporte: {res.output_path}")

    # ── Etapa 4 — Nivel de Servicio Sep-Dic ───────────────────────────────────

    def _run_etapa4_all(self) -> None:
        self._run_in_thread("e4_all", self._etapa4_fn, False)

    def _run_etapa4_capa1(self) -> None:
        self._run_in_thread("e4_capa1", self._etapa4_fn, True)

    def _etapa4_fn(self, solo_capa1: bool) -> None:
        from .conciliation.nivel_servicio import (
            run_nivel_servicio_septdic_from_file, _DEFAULT_BLOCKS_DIR,
            _DEFAULT_BITACORA_SEPTDIC, _DEFAULT_PROVIDER_BLOCKS,
        )
        raw = self._require_panoptic()
        if not raw:
            return
        output = PROJECT_ROOT / "outputs" / "Etapa4"
        tag = "Solo Capa 1" if solo_capa1 else "completa"
        self._log(f"ETAPA 4 ({tag}) — Nivel de Servicio Sep-Dic...")
        res = run_nivel_servicio_septdic_from_file(
            raw, _DEFAULT_BLOCKS_DIR, _DEFAULT_BITACORA_SEPTDIC, output,
            provider_blocks_path=_DEFAULT_PROVIDER_BLOCKS,
            solo_capa1=solo_capa1, print_fn=self._log,
        )
        self._log(f"ETAPA 4 completada. Reporte: {res.output_path}")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
def main() -> None:
    app = ConciliacionApp()
    app.mainloop()


if __name__ == "__main__":
    main()
