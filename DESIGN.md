# DESIGN.md · Radar de instrumentos

Dirección **B «Road case MIA → BOG»**, elegida el 20 nov 2026. Reemplaza a «Estuche abierto».
- Maquetas: https://claude.ai/artifact/QTKR5fwAsgNVb2hzCMVyx7 (tableros «B · Hoy» y «B · Ficha en el móvil»).
- Auditoría que motivó el cambio: `claude/analisis/auditoria-diseno-radar-2026-11-20.md` (en el proyecto de Claude).

> Cada guitarra viaja en un road case de Miami a Bogotá. Su guía de embarque dice, tramo por tramo, lo que se paga en dólares y en pesos hasta el neto; la cinta gaffer marca hasta dónde ofertar.

## Tokens

| Token | Valor | Uso | Contraste |
|---|---|---|---|
| `--estuche` | `#1A1B1E` | fondo de la página | — |
| `--laminado` | `#25272B` | superficies: estuche, tablas, fila elegida | — |
| `--laminado2` | `#2C2F34` | hover de filas | — |
| `--aluminio` | `#AEB4BB` | texto secundario, bordes de 1 px, esquineras | 8,24:1 sobre estuche · 7,16:1 sobre laminado |
| `--cinta` | `#ECE5D2` | texto principal; fondo de la guía y de la cinta gaffer | 13,70:1 · 11,90:1 |
| `--tinta` | `#16181D` | texto sobre cinta y sobre naranja; bordes de la guía | 14,13:1 sobre cinta |
| `--tinta2` | `#4A4E57` | texto secundario sobre cinta | 6,63:1 sobre cinta |
| `--raya` | `#C9C0A8` | divisores finos dentro de la guía (no lleva texto) | — |
| `--total` | `#E2D9C2` | fondo de la fila «Costo puesto en Bogotá» | tinta 12,63:1 |
| `--naranja` | `#FF6B1A` | acción principal, ganancia (+), ruta | 6,04:1 · 5,25:1; tinta sobre naranja 6,23:1 |
| `--fragil` | `#FF5A5F` | pérdida (−), vendida | 5,64:1 · 4,90:1 |

- **El color nunca va solo:** toda ganancia o pérdida lleva signo (+/−).
- **Tipografía:**
  - **Big Shoulders Stencil** (peso 800, en mayúsculas por CSS): marca, h1, h2, títulos de tramo, MIA/BOG y la cinta gaffer. Nunca en cifras de tabla ni en texto corrido.
  - **Schibsted Grotesk** (400–700): todo lo demás, con `font-variant-numeric: tabular-nums`. Si sus cifras no resultan tabulares (ver el plan, tarea 1), se usa **Public Sans**.
  - **IBM Plex Mono**: solo para el número de la publicación en la guía.
  - **Escala de app:** 11 · 12 · 13 · 14 · 15 · 16 · 18 · 20 · 26 · 34 · 40 px.
- **Superficie:** bordes de 1 px en aluminio y sin sombras, salvo la de la hoja del móvil. Las esquineras de road case van solo en el estuche principal. La guía lleva un borde de 2 px en tinta.
- **Radios:** 0 en todo; 2 px en las etiquetas; 16 px arriba en la hoja del móvil.
- **Espaciado:** base de 4 px (4, 8, 12, 16, 24, 32, 48).
- **Motion:**
  - curvas: `--ease-out` cubic-bezier(0.23,1,0.32,1) y `--ease-drawer` cubic-bezier(0.32,0.72,0,1);
  - duraciones: 140 ms al pulsar, 200 ms en cambios de estado y 280 ms en la hoja del móvil;
  - solo se animan `transform`, `opacity` y `background-color`;
  - con `prefers-reduced-motion` no hay transiciones.

## La guía de embarque (la cuenta)

La guía reemplaza a la antigua cascada. El orden sigue el recorrido del dinero:

| Tramo | Rubros | Se paga en |
|---|---|---|
| 1 · Compra en Miami | Precio pedido (y envío en EE. UU. si lo hay), impuesto de ventas | dólares |
| 2 · Envío a Bogotá | Flete del casillero, seguro, inspección, recargo de la tarjeta | dólares |
| 3 · Aduana en Bogotá | Arancel, IVA | pesos |
| 4 · Puesta a punto | Ajuste del luthier (no aparece si es 0) | pesos |
| **Costo puesto en Bogotá** | suma de los tramos | — |
| N · Venta en Bogotá | Cierre esperado − comisión − costo puesto = **Neto** (y % sobre el costo) | pesos |

Reglas:
1. **Columnas fijas:** USD a la izquierda y COP a la derecha, en todas las filas.
2. **Negrita para la moneda en que se paga el tramo;** la otra va en `--tinta2`.
3. **Cada impuesto o porcentaje muestra su base** en la columna «Cómo se calcula». En el móvil, la base va debajo del concepto.
4. **Los montos cuadran a la vista:**
   - USD con centavos (`US$1.650,00`) y COP redondeados a miles;
   - los redondeos se reparten con el método del mayor resto, así que la suma de las líneas mostradas da exactamente el subtotal y el costo puesto;
   - el neto es el mismo que muestran la lista de Hoy y Explorar.
5. **Un tramo de una sola línea no repite subtotal.**
6. **La venta resta el costo puesto,** para que el neto salga de una resta visible.

## Moneda y formato es-CO
- **Montos:** `$1.234.000` (pesos redondeados a miles), `US$1.250` en listas y `US$1.250,00` en la guía.
- **Porcentajes:** `25 %` con espacio duro (`&nbsp;`) entre la cifra y el %.
- **Fechas:** `20 nov 2026, 6:54 a. m.`; si no hay hora, `20 nov 2026`.

## Comisión del vendedor
- **Escenarios:** 0, 5 y 10 %. Los veredictos usan el 5 % (`comision_canal`).
- **Selector:** el mismo en todas las páginas; se guarda en `?comision=` y en el navegador.
- **Render:** cada cifra que depende de la comisión se escribe una vez por escenario (`.esc[data-c]`) y el CSS muestra solo la elegida. La lista de Hoy se ordena con `order: var(--o<k>)`.

## Pantallas
- **Hoy:**
  - encabezado «Radar · MIA → BOG»;
  - «¿Qué ofertar hoy?» con el selector;
  - a la izquierda, un **manifiesto** de hasta 12 filas, cada una con miniatura de 56 px, modelo, plataforma, estado, precio pedido y neto;
  - a la derecha, el estuche de la elegida: foto, cinta gaffer con techo y apertura, botones y guía;
  - en el móvil, el estuche se abre como hoja desde abajo.
- **Detalle:** el estuche completo (h1 para el modelo, h2 para la guía), «Con tus números», los comparables y el mensaje de oferta.
- **Explorar:** tabla con filtros, en la misma paleta.
- **Estado:** fuentes y supuestos.

## Estados
- **Sin foto:** queda el nombre del modelo en el recuadro; en la miniatura, el recuadro vacío.
- **Sin oferta con esta comisión:** la cinta dice «Sin oferta con esta comisión» y el botón de copiar queda deshabilitado.
- **Pérdida:** el neto va en `--fragil` y con signo −.
- **Referencia de Colombia estimada:** etiqueta en el estuche (no en cada fila de la lista) y «estimado» en la base del cierre.

## Rechaza
Neón sobre negro, glass, degradados, sombras de brillo, bordes laterales de color, la cinta gaffer repetida (va una por publicación), texturas falsas de chapa o madera, píldoras de radio completo, Inter y emojis como íconos.
