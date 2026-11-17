# Capturas

La tarea programada de cada mañana reemplaza `reverb-<slug>.json` por cada búsqueda de `busquedas.json`
(edita esa lista desde GitHub para cambiar qué se busca). Si una búsqueda falla, se conserva la del día anterior.

Cada archivo `datos/capturas/*.json` es una tanda de publicaciones leídas con un navegador normal y **ya
identificadas** (marca, modelo, estado). El tablero las importa solo al abrir "Publicaciones" y las evalúa al
instante, sin modelo de lenguaje: los comparables de EE. UU. salen de las propias capturas (mismo `marca` +
`modelo`), así que conviene capturar todas las publicaciones de una búsqueda, no solo las baratas.

Nombre sugerido: `AAAA-MM-DD-<fuente>-<búsqueda>.json`. Para actualizar una búsqueda, reemplaza su archivo.

```json
{
  "fuente": "reverb",
  "consulta": "strandberg",
  "capturado": "2026-11-16",
  "categoria": "guitarra",
  "publicaciones": [
    {"id": "103867952", "titulo": "Strandberg Boden Neck-Thru 6 Tremolo Orange",
     "url": "https://reverb.com/item/103867952", "precio_usd": 1900, "envio_usd": 0,
     "marca": "Strandberg", "modelo": "Boden Neck-Thru 6", "estado": "excellent",
     "ofertas": true, "publicada": "2026-11-07", "senales": []}
  ],
  "precios_nuevos": [
    {"marca": "Strandberg", "modelo": "Boden Essential 6", "precio_usd": 1149}
  ]
}
```

- `estado`: nuevo, excelente, bueno, regular, para_reparar; o los de Reverb (mint, excellent, very-good, good, fair).
- `modelo`: el mismo texto exacto para publicaciones del mismo modelo; de eso depende la comparación.
- `categoria` por publicación es opcional (guitarra, bajo, pedal, cuerdas); si falta, usa la del archivo.
- `senales`: frases del vendedor que indiquen urgencia ("must sell", "OBO").
- Solo publicaciones de vendedores en EE. UU. con envío.

# Otros archivos de datos

- `parametros.json`: valores que usa el sitio publicado. Las claves que empiezan por `_` son notas.
- `referencias_co.json`: precios de venta en Colombia que tú conoces, por modelo exacto (mismo texto que en
  las capturas). Mandan sobre la estimación automática:
  `[{"marca": "Strandberg", "modelo": "Boden Prog NX 6", "usado_cop": 7500000}]`
