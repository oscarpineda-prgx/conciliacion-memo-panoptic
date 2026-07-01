# Conciliacion Memo Panoptic

Proyecto Python para automatizar la conciliación entre Panoptic (Verigon/PRGX) y los archivos MEMO de SAP para la auditoría de recuperaciones Soriana.

---

## Instalacion

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m pip install -e .
```

Copiar configuracion de ejemplo:

```powershell
Copy-Item config\panoptic.example.json config\panoptic.local.json
```

No es necesario ejecutar `playwright install chromium`. El proyecto usa Chrome instalado en Windows (Edge como respaldo).

---

## Estructura de carpetas

```
Conciliacion_Memo_Panoptic/
├── config/                          ← panoptic.local.json (credenciales, no en git)
├── data/
│   ├── raw/panoptic/                ← XLSX descargados de Panoptic
│   ├── raw/memo/                    ← Archivos MEMO SAP
│   └── templates/                   ← Plantillas de carga a Panoptic
├── outputs/                         ← Reportes y archivos generados
└── src/conciliacion_memo_panoptic/  ← Código fuente
```

**Rutas fijas del proyecto:**
- MEMOs SAP: `X:\Soriana\00 - AUDITORIA 2020 - 2024\Cargos\`
- Folios Compensatorios: `X:\Soriana\00 - AUDITORIA 2020 - 2024\FOLIOS COMPENSATORIOS\`

**Estructura de salida generada (`outputs/`):**

```
outputs/
├── Etapa1/
│   ├── Resumen_conciliacion_memo_panoptic.xlsx   <- consolidado de todos los memos
│   ├── Claim_Bulk_Update_YYYYMMDD.xlsx           <- plantilla Posting reference number
│   └── memos/
│       ├── conciliacion_M040.xlsx
│       ├── conciliacion_M041.xlsx
│       └── ...
└── Etapa2/
    ├── M048/
    │   ├── etapa2_M048.xlsx                      <- analisis del cruce
    │   ├── etapa2_M048_PostingDate.xlsx           <- plantilla Posting submission date
    │   └── etapa2_M048_Recoveries.xlsx            <- plantilla Recoveries / Clearing
    ├── M049/
    │   └── ...
    └── ...
```

---

## Flujo completo del proceso

```
ETAPA 1                                    ETAPA 2
───────────────────────────────────        ──────────────────────────────────
1. Descargar Panoptic (MONICA_3)           5. Cruzar con Folios Compensatorios
2. Conciliar MEMO vs Panoptic (P1-P4)         (genera plantillas automáticamente)
3. Revisar inconsistencias                 6. Revisar Cruce Exitoso
4. Subir Posting reference number          7. Subir Posting submission date
   (Bulk Update)                           8. Subir Recoveries / Clearing data
```

---

## ETAPA 1 — Conciliacion MEMO vs Panoptic

### Opcion A — Todo en uno (recomendado)

Descarga Panoptic, concilia todos los memos del rango y genera el consolidado en un solo paso:

```powershell
cmp run-all `
  --memo-dir "X:\Soriana\00 - AUDITORIA 2020 - 2024\Cargos" `
  --output-dir outputs `
  --memo-from 40 `
  --memo-to 56
```

Genera en `outputs/`:
- `conciliacion_M040.xlsx` ... `conciliacion_M056.xlsx` — reporte por memo (8 hojas)
- `Claim_Bulk_Update_YYYYMMDD.xlsx` — plantilla para actualizar Posting reference en Panoptic
- `Resumen_conciliacion_memo_panoptic.xlsx` — consolidado de todos los memos

---

### Opcion B — Paso a paso

**Paso 1 — Descargar Panoptic**

```powershell
cmp download-panoptic --view-name MONICA_3
```

Guarda el XLSX en `data/raw/panoptic/`.

**Paso 2 — Conciliar todos los memos**

```powershell
cmp reconcile-all `
  --raw-panoptic "data\raw\panoptic\20260623_MONICA_3.xlsx" `
  --memo-dir "X:\Soriana\00 - AUDITORIA 2020 - 2024\Cargos" `
  --output-dir outputs `
  --memo-from 40 `
  --memo-to 56
```

Genera `conciliacion_M0XX.xlsx` por memo con estas hojas:

| Hoja | Descripcion |
|---|---|
| `P1 Actualizados` | Pares proveedor+año asignados al memo automaticamente (monto coincidio con Stage Posting/Vendor) |
| `P1 Diferencias` | Pares proveedor+año con diferencia de monto en P1 — revisar con el auditor |
| `P1 Reejecución` | De los P1 Diferencias, los que cuadran al agregar Stage=Invoice al filtro — informativo |
| `Incons Proveedores` | Proveedores que no coinciden entre MEMO y Panoptic — revisar |
| `Incons Montos` | Montos que no cuadran — incluye IVA, IEPS y Monto antes de impuestos del MEMO |
| `Incons Concepto-Año` | Duplicados en el MEMO — informativo |
| `Cruce Resumen` | Tabla completa nivel proveedor |
| `Cruce Detalle` | Tabla completa nivel concepto/año |

Columnas de `Incons Montos`:

| Columna | Fuente |
|---|---|
| `Vendor number`, `Vendor name`, `Assigned to` | Panoptic |
| `Sum Net claim amount (Panoptic)`, `Sum Tax amount (Panoptic)`, `Gross claim amount (Panoptic)` | Panoptic (sumas) |
| `Monto antes de impuestos (MEMO)`, `IVA (MEMO)`, `IEPS (MEMO)`, `Monto Total (MEMO)` | MEMO (MontoxProveedorxFase) |
| `Amount Difference`, `Vendor Status`, `Amount Status` | Calculadas |

**Paso 3 — Consolidar resultados**

```powershell
cmp consolidate --output-dir outputs
```

Genera `outputs/Resumen_conciliacion_memo_panoptic.xlsx` con el resumen de todos los memos.

---

### Actualizar Posting reference number en Panoptic

Luego de revisar que las inconsistencias esten corregidas, subir el archivo de Bulk Update:

**Generar el archivo** (se genera automaticamente con `reconcile-all` o `run-all`)

Archivo generado: `outputs/Claim_Bulk_Update_YYYYMMDD.xlsx`

**Subir a Panoptic:**

```powershell
cmp upload-claim-updates `
  --file "outputs\Claim_Bulk_Update_20260623.xlsx"
```

El comando abre Panoptic, navega a la vista `MONICA_3`, abre el menu de tres puntos `(⋮)`, selecciona `Import claim updates`, carga el archivo y guarda.

---

## ETAPA 2 — Cruce con Estado de Cuenta (Folios Compensatorios)

Prerrequisito: la Etapa 1 debe estar limpia (inconsistencias corregidas por el auditor y Posting reference numbers actualizados en Panoptic).

### Opcion A — Todo en uno (recomendado)

Descarga Panoptic actualizado y cruza contra todos los folios compensatorios:

```powershell
cmp run-etapa2 `
  --folios-dir "X:\Soriana\00 - AUDITORIA 2020 - 2024\FOLIOS COMPENSATORIOS" `
  --output-dir outputs `
  --memo-from 40 `
  --memo-to 56
```

---

### Opcion B — Paso a paso

**Paso 1 — Cruzar con todos los folios compensatorios**

```powershell
cmp cross-all-estados `
  --raw-panoptic "data\raw\panoptic\20260623_MONICA_3.xlsx" `
  --folios-dir "X:\Soriana\00 - AUDITORIA 2020 - 2024\FOLIOS COMPENSATORIOS" `
  --output-dir outputs `
  --memo-from 40 `
  --memo-to 56
```

Por cada memo genera 3 archivos en `outputs/`:

| Archivo | Descripcion |
|---|---|
| `etapa2_M048.xlsx` | Analisis (3 hojas: Cruce Exitoso, Sin Coincidencia, Panoptic Sin Folio) |
| `etapa2_M048_PostingDate.xlsx` | Plantilla lista para subir a Panoptic (Posting submission date) |
| `etapa2_M048_Recoveries.xlsx` | Plantilla lista para subir a Panoptic (Recoveries / Clearing data) |

Hojas del archivo de analisis `etapa2_M048.xlsx`:

| Hoja | Descripcion |
|---|---|
| `Cruce Exitoso` | Proveedores con monto coincidente — datos EC escritos en Panoptic |
| `Sin Coincidencia` | Proveedores del EC sin match en Panoptic (monto distinto o ausente) |
| `Panoptic Sin Folio` | Proveedores en Panoptic que no aparecen en el EC |

---

### Actualizar Posting submission date en Panoptic

**Subir a Panoptic:**

```powershell
cmp upload-posting-dates `
  --file "outputs\etapa2_M048_PostingDate.xlsx"
```

El comando abre Panoptic, navega a `MONICA_3`, abre `(⋮)`, selecciona `Import claim updates`, carga el archivo y guarda.

---

### Actualizar Recoveries / Clearing data en Panoptic

**Subir a Panoptic:**

```powershell
cmp upload-recoveries `
  --file "outputs\etapa2_M048_Recoveries.xlsx"
```

El comando abre Panoptic, navega a `MONICA_3`, abre `(⋮)`, selecciona `Import recoveries / clearing data`, carga el archivo y guarda.

---

## Comandos individuales / utilitarios

### Abrir Panoptic en el navegador (sin descargar)

```powershell
cmp open-panoptic-view --view-name MONICA_3
```

### Exportar Panoptic sin filtros

```powershell
cmp export-panoptic-xlsx --view-name MONICA_3
```

### Conciliar un solo memo

```powershell
cmp reconcile `
  --raw-panoptic "data\raw\panoptic\20260623_MONICA_3.xlsx" `
  --memo "X:\Soriana\00 - AUDITORIA 2020 - 2024\Cargos\Memo_048\Memo_048.xlsx" `
  --memo-id M048 `
  --output-dir outputs
```

### Cruzar un solo memo con su folio compensatorio

```powershell
cmp cross-estado-cuenta `
  --raw-panoptic "data\raw\panoptic\20260623_MONICA_3.xlsx" `
  --folio "X:\Soriana\00 - AUDITORIA 2020 - 2024\FOLIOS COMPENSATORIOS\MEMO_048.XLSX" `
  --memo-id M048 `
  --output-dir outputs
```

### Generar resumen agrupado por proveedor de un XLSX de Panoptic

```powershell
cmp process-panoptic "data\raw\panoptic\20260623_MONICA_3.xlsx"
```

---

## Referencia de argumentos comunes

Todos los comandos que abren Panoptic aceptan estos argumentos opcionales:

| Argumento | Descripcion |
|---|---|
| `--config ruta.json` | Ruta alternativa al archivo de configuracion |
| `--email correo@prgx.com` | Correo para el login de Panoptic |
| `--headless` | Ejecutar el navegador sin interfaz grafica |
| `--view-name NOMBRE` | Vista de Claims a seleccionar (default: `MONICA_3`) |
| `--timeout-ms 60000` | Timeout general de Playwright en milisegundos |

---

## Velocidad / Configuracion

Parametros en `config/panoptic.local.json`:

| Parametro | Descripcion |
|---|---|
| `default_timeout_ms` | Timeout general para cargas y login |
| `action_timeout_ms` | Timeout para acciones importantes (clicks, menus) |
| `locator_probe_timeout_ms` | Tiempo por cada selector alternativo |
| `post_click_wait_ms` | Pausa corta despues de cada click |
| `download_timeout_ms` | Timeout para esperar la descarga del XLSX |
