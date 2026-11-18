# DESIGN.md · Radar de instrumentos

Dirección **B «Estuche abierto»**, aprobada el 18 nov 2026 (maqueta: https://claude.ai/artifact/QTKR5fwAsgNVb2hzCMVyx7).

> Cada guitarra se abre como un estuche: arriba lo que pides y ofreces; adentro, cada peso del costo puesto, apilado hasta la ganancia.

## Tokens

| Token | Valor | OKLCH | Uso | Contraste |
|---|---|---|---|---|
| `--tolex` | `#1E2024` | oklch(24% 0.008 264) | fondo | — |
| `--forro` | `#2A2D33` | oklch(30% 0.012 264) | superficies: estuche, tablas, fila elegida | — |
| `--hueso` | `#ECE7DE` | oklch(93% 0.013 82) | texto principal | 13,25:1 sobre tolex · 11,21:1 sobre forro |
| `--polvo` | `#A8A196` | oklch(71% 0.018 79) | texto secundario, barras de costo | 6,37:1 · 5,39:1 |
| `--laton` | `#D2AE5E` | oklch(77% 0.108 86) | ganancia (+), acción principal | 7,73:1 · 6,54:1 |
| `--felpa` | `#E0776A` | oklch(69% 0.133 28) | comisión, pérdida (−) | 5,45:1 · 4,61:1 |

- **Color nunca solo:** toda ganancia o pérdida lleva signo (+/−) además del color.
- **Tipografía:** Archivo variable, una sola familia. Ancho 112 en títulos y modelos; 100 en texto; 88 en tablas y cascadas. Escala de app 1,2: 12 · 13 · 14 · 16 · 17 · 22 · 26 · 34 px. Pesos 400, 500, 600 y 650. `tabular-nums` en todo el sitio.
- **Superficie:** sin bordes decorativos; el forro separa por superficie. Divisores de 1 px tolex solo entre filas de tabla. La única sombra es la de la hoja del móvil.
- **Radios:** 4 px en los controles internos; 6 px en botones y fotos; 10 px en el estuche y las cajas; 16 px arriba en la hoja móvil.
- **Espaciado:** base 4 px (4, 8, 12, 16, 24, 32, 48).
- **Motion:** `--ease-out` cubic-bezier(0.23,1,0.32,1) y `--ease-drawer` cubic-bezier(0.32,0.72,0,1). Duraciones: 140 ms (pulsar), 200 ms (cambio de estado) y 280 ms (hoja móvil). Solo `transform`, `opacity` y `background-color`. Con `prefers-reduced-motion` no hay transiciones.

## Moneda

Se compra en dólares y se vende en pesos, así que **cada cifra va en las dos monedas** a la TRM del día:
- **Lo que se paga en EE. UU.** (pedido, apertura, techo) va en USD y debajo "≈ $X M".
- **Lo que se cobra en Colombia** (venta, piso, neto) va en COP y debajo en USD.
- **La cascada** tiene una columna USD y otra COP. En el móvil, el USD va junto al COP.
- **Formato es-CO:** `$1.234.000` (pesos redondeados a miles), `US$1.250` y `25 %` con espacio duro.

## Comisión del vendedor

- **Escenarios:** 0, 5 y 10 %. Los veredictos y las alertas usan el 5 % (`comision_canal`).
- **Selector:** el mismo en todas las páginas. Se guarda en `?comision=` y en el navegador.
- **Cálculo:** cada cifra que depende de la comisión se renderiza una vez por escenario (`.esc[data-c]`), y el CSS muestra solo la elegida. En la lista de Hoy, el orden por neto se hace con `order: var(--o<k>)`.

## Pantallas

- **Hoy:** pregunta «¿Qué ofertar hoy?», selector de comisión, lista de hasta 12 publicaciones ordenadas por el neto al precio pedido y el estuche de la publicación elegida. En el móvil, el estuche se abre como hoja desde abajo y se cierra con ✕, con el velo o con Esc.
- **Detalle:**
  - el estuche completo;
  - «Con tus números»: flete en USD y precio de venta en COP, recalculados en el navegador con `_cuentas.js`;
  - comparables de EE. UU. y de Colombia;
  - el mensaje de oferta.
- **Explorar:** tabla con filtros. Se ordena por el neto de la comisión elegida.
- **Estado:** fuentes y supuestos de las cuentas.

## Estados

- **Sin foto:** queda el nombre del modelo en el recuadro.
- **Sin comparables en EE. UU.:** aviso con el costo puesto al precio pedido.
- **Referencia de Colombia estimada:** etiqueta, y una nota en el estuche.
- **Sin oferta con esta comisión:** el botón queda deshabilitado y se explica por qué.
- **Pérdida:** en felpa y con signo −.
- **Cero publicaciones o nada para mirar:** caja vacía con un enlace a Explorar.

## Rechaza

Inter, casi negro con un único acento verde, rejillas de tarjetas idénticas, métrica-héroe, glass, degradados y emojis como íconos.
