# Contexto del Proyecto: Conciliación Memo Panoptic

## 1. Objetivo del Proyecto

Automatizar la descarga de datos desde **Panoptic** (plataforma Verigon) y realizar una
conciliación (cruce de información) contra los archivos **MEMO** de SAP. Esto permite
validar recuperaciones de auditoría, detectar inconsistencias de montos y proveedores,
y preparar actualizaciones masivas de estados de reclamaciones en Panoptic.

---

## 2. Fuentes de Datos

### Panoptic (Entrada)
- **Archivo**: `Soriana_Retail_*.xlsx` descargado automáticamente por el módulo `panoptic/`.
- **Filtro principal**: `Posting reference number` == `"M030"` (o el número de memo que corresponda).
- **Columnas clave**:

| Columna Panoptic          | Descripción                                     |
|---------------------------|-------------------------------------------------|
| `Vendor number`           | Clave del proveedor                             |
| `Vendor name`             | Nombre del proveedor                            |
| `Net claim amount`        | Monto sin impuestos                             |
| `Claim amount`            | Monto con impuestos                             |
| `Total tax amount`        | Impuesto (si no existe se calcula: Claim - Net) |
| `Posting reference number`| Identifica el MEMO, ej. `M030`                  |
| `Financial year of origin`| Año fiscal del cargo (para cruce concepto/año)  |
| `Client claim type`       | Concepto del cargo (equivalente a "Concepto" en MEMO) |

### MEMO (Entrada)
- **Archivo**: `Memo_030_varios.xlsx` (o el número correspondiente).
- **Ubicación ejemplo**: `X:\Soriana\00 - AUDITORIA 2020 - 2024\00 - Auditores\Oscar\Proyectos Python\Conciliacion_Memo_Panoptic\Memo_030_varios.xlsx`
- **Hojas utilizadas**:

#### Hoja `MontoxProveedorxFase`
- **Encabezado real**: fila 7 (índice 6 en base-0 para pandas `header=6`).
- **Columnas clave**:

| Columna MEMO               | Columna Panoptic equivalente |
|----------------------------|------------------------------|
| `Num Proveedor`            | `Vendor number`              |
| `Proveedor`                | `Vendor name`                |
| `Fase`                     | (clasificación interna)      |
| `Monto antes impuestos`    | `Net claim amount`           |
| `IEPS`                     | parte de `Total tax amount`  |
| `IVA`                      | parte de `Total tax amount`  |
| `Monto Total`              | `Gross claim amount`         |

#### Hoja `MontoxConceptoxAño` (nombre con posible espacio al final)
- **Encabezado real**: fila 2 (índice 1 en base-0 para pandas `header=1`).
- **Columnas clave**:

| Columna MEMO         | Columna Panoptic equivalente      |
|----------------------|-----------------------------------|
| `Num Proveedor`      | `Vendor number`                   |
| `Año`                | `Financial year of origin`        |
| `Concepto`           | `Client claim type`               |

---

## 3. Lógica de Negocio y Reglas de Conciliación

### 3.1 Agrupación de Panoptic (`process-panoptic`)
- Group by `Vendor number` + `Vendor name`.
- Suma de `Net claim amount` y `Total tax amount`.
- Columna calculada: `Gross claim amount` = Net + Tax.
- Sin filas de totales al final (tabla limpia para cruces).

### 3.2 Cruce Panoptic vs MEMO (`reconcile`)

**Paso 0 – Filtrado**  
Filtrar Panoptic donde `Posting reference number == memo_id` (ej. `"M030"`).

**Validación 1 – Existencia de proveedores**  
Outer join por `Vendor number`. Se detectan:
- `Missing in MEMO`: proveedor existe en Panoptic pero no en MEMO.
- `Missing in Panoptic`: proveedor existe en MEMO pero no en Panoptic.

**Validación 2 – Diferencia de montos**  
Comparar `Gross claim amount (Panoptic)` vs `Monto Total (MEMO)` a nivel proveedor.  
Tolerancia: ±0.01.

**Validación 3 – Concepto y Año faltantes**  
Outer join por `Vendor number` + `Año` + `Concepto` (usando las hojas de detalle).  
Se detectan combinaciones que existen en una fuente pero no en la otra.

**Validación 4 – Duplicados de Concepto/Año**  
Dentro de cada fuente, se marcan filas donde la combinación
`Vendor number` + `Año` + `Concepto` aparece más de una vez.

### 3.3 Campos de actualización en Panoptic (post-conciliación)
Según el archivo `docs/reglas_negocio.md`:

| Campo MEMO                  | Campo Panoptic              |
|-----------------------------|-----------------------------|
| `Document Number`           | `Batch number`              |
| `Document Date`             | `Posting submission date`   |
| `Clearing Document`         | `Last recovery number`      |
| `Clearing date`             | `Last recovery date`        |

Regla especial: si `Clearing date` > fecha actual → `Last cleared date` = `Clearing date`, `Last recovery date` = fecha actual.

---

## 4. Arquitectura del Software

```
src/conciliacion_memo_panoptic/
├── cli.py                   ← Punto de entrada, define todos los comandos
├── settings.py              ← Carga configuración del entorno
├── paths.py                 ← Rutas del proyecto
├── panoptic/                ← Automatización de UI con Playwright
│   ├── browser.py
│   ├── login.py
│   ├── navigation.py
│   ├── downloader.py
│   ├── session.py
│   ├── workflows.py
│   └── filenames.py
└── conciliation/            ← Procesamiento de datos con Pandas
    └── processing.py        ← Agrupación y conciliación
```

### Comandos CLI disponibles (`cmp`)

| Comando               | Descripción                                                          |
|-----------------------|----------------------------------------------------------------------|
| `download-panoptic`   | Descarga XLSX de Panoptic con filtros de memo/proveedor              |
| `export-panoptic-xlsx`| Exporta XLSX sin filtros                                             |
| `open-panoptic-view`  | Abre la vista de Claims en el navegador                              |
| `process-panoptic`    | Genera resumen agrupado por proveedor                                |
| `reconcile`           | Cruza Panoptic vs UN archivo MEMO individual                         |
| `reconcile-all`       | Carga Panoptic una vez y concilia contra **todos** los Memo_*.xlsx   |

---

### Flujo recomendado (todos los memos de una carpeta)

**Paso 1 — Descargar Panoptic una sola vez:**
```powershell
cmp export-panoptic-xlsx --download-dir "data/raw/panoptic"
```

**Paso 2 — Conciliar todos los memos de la carpeta Cargos:**
```powershell
cmp reconcile-all `
  --raw-panoptic "data/raw/panoptic/Soriana_Retail_Export.xlsx" `
  --memo-dir "X:/Soriana/00 - AUDITORIA 2020 - 2024/01 - Cargos" `
  --output-dir "outputs"
```

El comando detecta automáticamente todos los `Memo_*.xlsx` de `--memo-dir`,
extrae el ID del nombre del archivo (`Memo_030_varios.xlsx` → `M030`),
filtra el DataFrame de Panoptic en memoria y genera un reporte por memo.

**Salida esperada en consola:**
```
Cargando Panoptic: data/raw/panoptic/Soriana_Retail_Export.xlsx
Buscando MEMOs en: X:/Soriana/.../Cargos

  OK  M001  ->  outputs/conciliacion_M001.xlsx
  OK  M002  ->  outputs/conciliacion_M002.xlsx
  --  M003  (sin registros en Panoptic, omitido)
  OK  M030  ->  outputs/conciliacion_M030.xlsx

Completados: 3 | Omitidos: 1 | Errores: 0
Reportes guardados en: X:\...\outputs
```

---

### Uso individual (un solo memo)

```powershell
cmp reconcile `
  --raw-panoptic "data/raw/panoptic/Soriana_Retail_Export.xlsx" `
  --memo "Memo_030_varios.xlsx" `
  --memo-id "M030" `
  --output-dir "outputs"
```

### Archivo de salida por memo
`outputs/conciliacion_M030.xlsx` con 4 hojas:

| Hoja                    | Contenido                                               |
|-------------------------|---------------------------------------------------------|
| `Incons Proveedor-Monto`| Proveedores faltantes o con diferencia de montos        |
| `Incons Concepto-Año`   | Combinaciones faltantes o duplicadas por concepto/año   |
| `Cruce Resumen`         | Tabla completa del cruce a nivel proveedor              |
| `Cruce Detalle`         | Tabla completa del cruce a nivel concepto/año           |

---

## 5. Requisitos

```
pandas
openpyxl
playwright
```

Instalar: `pip install -r requirements.txt`  
Playwright: `playwright install chromium`

---

## 6. Bitácora de Cambios (Changelog)

### [2026-06-12] Automatización Base
- Creación de scripts de navegación para Panoptic con Playwright.
- Implementación de descarga de XLSX automática con filtros de memo y proveedor.
- Configuración de perfiles persistentes de navegador para evitar re-logueos.

### [2026-06-12] Módulo de Procesamiento de Datos
- **Qué**: Comando `process-panoptic` y módulo `conciliation/processing.py`.
- **Cómo**: Pandas para cargar Excel, agrupar por proveedor y calcular sumas.
- **Para qué**: Resumen ejecutivo por proveedor post-descarga.
- **Extra**: Si `Total tax amount` no existe en el Excel, se calcula como `Claim amount - Net claim amount`.

### [2026-06-12] Ajuste en Agrupación y Totales
- **Qué**: Se eliminó la fila "Grand Total" del resumen; se añadió columna `Gross claim amount`.
- **Cómo**: `Gross = Net + Tax`, sin concatenar fila extra.
- **Para qué**: Tabla limpia lista para cruces automáticos.

### [2026-06-16] Conciliación con MEMO — Estructura Real de Hojas
- **Qué**: Reescritura de `reconcile_with_memo` con la estructura real del archivo MEMO.
- **Cómo**:
  - `MontoxProveedorxFase`: encabezado en fila 7 (`header=6`). Se extrae la tabla izquierda ignorando la tabla de resumen por fase a la derecha.
  - `MontoxConceptoxAño`: encabezado en fila 2 (`header=1`). Nombre de hoja con posible espacio al final y codificación especial de `ñ` — se detecta dinámicamente.
  - CLI simplificado: `--memo-base-dir` reemplazado por `--memo` (ruta directa al archivo).
  - Exportación en 4 hojas: inconsistencias de proveedor/monto, inconsistencias de concepto/año, cruce resumen completo y cruce detalle completo.
- **Para qué**: Cumplir con los acuerdos de la reunión de equipo: detectar proveedores faltantes, errores de monto, combinaciones concepto/año faltantes y duplicados.

---

### [2026-06-16] Procesamiento en batch — comando reconcile-all
- **Qué**: Nuevo comando `reconcile-all` y refactorización de `processing.py`.
- **Cómo**:
  - `processing.py` separa la lógica en capas: `_load_panoptic`, helpers de MEMO, `_reconcile_memo_from_df` (lógica pura sin I/O), `reconcile_with_memo` (individual), `reconcile_all_memos` (batch).
  - `reconcile_all_memos` carga Panoptic una sola vez desde disco y reutiliza el DataFrame en memoria para cada memo.
  - El ID de memo se extrae automáticamente del nombre del archivo (`Memo_030_varios.xlsx` → `M030`).
  - Los memos sin registros en Panoptic se omiten silenciosamente (no son un error).
  - `MemoResult` dataclass encapsula el resultado de cada memo (ok / omitido / error).
  - CLI reporta resumen final: completados / omitidos / errores. Exit code 1 si hubo errores.
- **Para qué**: Procesar todos los memos de la carpeta Cargos con un solo comando sin releer Panoptic N veces.

---

*Actualizar este documento en cada hito importante del desarrollo.*
