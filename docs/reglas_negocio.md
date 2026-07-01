# Reglas del proyecto

## Archivos

- El archivo `MEMO-###.xlsx` es el estado de cuenta.
- El archivo `Soriana_Retail_*.xlsx` es la extraccion de Panoptic.

## Panoptic

- `Net claim amount`: monto sin impuestos.
- `Claim amount`: monto con impuestos.
- En el ejemplo MEMO 030 ambos importes son iguales porque el impuesto es cero.
- El login inicia con el correo configurado localmente: `oscar.pineda@prgx.com`.

## Cruce MEMO vs Panoptic

- `Account` del MEMO se relaciona con `Vendor number` en Panoptic.
- `Text` del MEMO identifica el memorandum, por ejemplo `AUDITORIA PRGX MEMO_030`.
- `Posting reference number` en Panoptic identifica el memo, por ejemplo `M030`.
- La suma de `Amount in local currency` filtrada en MEMO debe cuadrar contra la suma de Panoptic usando el monto que corresponda con o sin impuestos.

## Campos de actualizacion en Panoptic

- `Document Number` del MEMO -> `Batch number` en Panoptic.
- `Document Date` del MEMO -> `Posting submission date` en Panoptic.
- `Clearing Document` del MEMO -> `Last recovery number` en Panoptic.
- `Clearing date` del MEMO -> `Last recovery date` en Panoptic.

Regla especial:

- Si `Clearing date` es mayor a la fecha actual:
  - `Last cleared date` toma el valor original de `Clearing date`.
  - `Last recovery date` toma la fecha actual.

## Document Number principal

Despues de filtrar el MEMO por proveedor y memorandum, se toma el mayor valor positivo de `Amount in local currency`.
El `Document Number` de esa fila se considera el documento principal del memo y se valida contra `Batch number` en Panoptic.

En el ejemplo:

- Mayor monto MEMO: `124,356.72`.
- `Document Number`: `1700048721`.
- En Panoptic aparece como `Batch number` del claim `SORIANA_ MX_02652`.
