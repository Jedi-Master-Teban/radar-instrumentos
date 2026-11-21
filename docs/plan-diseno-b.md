# Rediseño B «Road case MIA → BOG»: plan de implementación

> **Para quien ejecute (OpenCode u otro agente):** sigue las tareas en orden, una por una, y marca cada paso (`- [ ]` → `- [x]`). No improvises diseño: todo lo visual está decidido en `DESIGN.md` y aquí va el código exacto. Si un paso no da el resultado esperado, **detente y reporta** qué salió (comando y salida); no «arregles» cambiando las pruebas.

**Objetivo:** cambiar la apariencia del sitio a la dirección B y reemplazar la cascada de costos por la **guía de embarque**: cinco tramos en el orden del dinero, con USD y COP en columnas fijas y montos que cuadran a la vista.

**Arquitectura:**
- La cuenta no cambia (`radar/costing.py` y `_cuentas.js` no se tocan).
- Se agrega un modelo de vista, `guia()` en `radar/vistas.py`, que reparte los redondeos para que las sumas mostradas cuadren.
- Las plantillas Jinja2 lo dibujan.
- El CSS vive en `radar/web/templates/base.html`.

**Stack:** Python 3 y pytest; Jinja2; FastAPI para el tablero local; sitio estático en GitHub Pages.

**Especificación:** `DESIGN.md` (raíz del repo). Las maquetas aprobadas están en https://claude.ai/artifact/QTKR5fwAsgNVb2hzCMVyx7 (tableros «B · Hoy» y «B · Ficha en el móvil»).

**Solución de referencia:** `docs/diseno-b-referencia.patch` contiene todos estos cambios ya probados (152 pruebas en verde). Úsala solo para comparar si te atascas, con `git diff` contra tu trabajo. No la apliques de entrada: el objetivo es construir tarea por tarea, con pruebas.

## Restricciones globales
- **Rama:** trabaja en `diseno-b`. Nunca hagas commit ni push en `main`.
- **Comandos:** en esta Mac, Python es `python3`. Primero activa el entorno con `source .venv/bin/activate` y luego usa `pytest -q`.
- **No tocar:**
  - `radar/costing.py`, `radar/pipeline.py`, `radar/web/templates/_cuentas.js` y `datos/`;
  - nada de `.github/`.
- **No romper los nombres que usa el JavaScript:** `data-op`, `data-panel`, `data-estuche`, `data-copiar`, `data-elegir-com`, `data-con-com`, `class="esc"` con `data-c="0|5|10"`, los ids de «Con tus números» y `.panel`, `.velo`, `#cerrar`.
- **Sin dependencias nuevas.** Las tipografías se cargan desde Google Fonts, como hoy.
- **Copy en español de Colombia, en sentence case.** Las mayúsculas de los rótulos en esténcil las pone el CSS (`text-transform`); en el HTML van en minúsculas normales.
- **Espacio duro antes del %:** `25&nbsp;%` en plantillas y `" %"` en Python.
- **Un commit por tarea,** con el mensaje indicado. Termina cada mensaje con la línea `Co-Authored-By:` que use tu herramienta, si la tiene.

## Foco de revisión (casos que las pruebas no cubren del todo)
1. **Pérdida.** El neto negativo va en `--fragil` (clase `neg`) y con signo −, tanto en la guía como en la lista.
2. **Pedal.** Sin ajuste del luthier no aparece el tramo 4 y la venta pasa a llamarse «4 · Venta en Bogotá». Si hay envío dentro de EE. UU., el primer concepto dice «Precio pedido y envío en EE. UU.».
3. **Comisión 0 %.** La fila «Comisión del vendedor» no aparece.
4. **Publicación sin cuenta** (`o.esc` vacío). Se sigue viendo el aviso de antes, sin guía.
5. **Cifras grandes en el móvil,** como un bajo de $20.000.000. Las celdas `.n` no se parten (`white-space:nowrap`) y la página no se desborda a 390 px.

---

### Tarea 0 · Preparar

- [ ] **Paso 1.** Trae la rama y activa el entorno:
```bash
git fetch origin && git checkout diseno-b && git pull
source .venv/bin/activate
```
- [ ] **Paso 2.** Corre la línea base:
```bash
pytest -q
```
**Esperado:** `144 passed`. Si sale otro número, detente y reporta.

---

### Tarea 1 · Formatos es-CO (dólares con centavos, % con espacio duro, fechas)

**Archivos:**
- Crear `tests/test_formato.py`.
- Modificar `radar/vistas.py`.

**Interfaces que produce** (`radar/vistas.py`):
- `usd_cent(x) -> str`, por ejemplo `"US$1.650,00"`;
- `fecha_es(s) -> str`;
- filtros Jinja nuevos: `usd2` y `susd2`;
- el filtro `fecha` pasa a usar `fecha_es`;
- `pct`, `pct1` y `spct` devuelven el % con espacio duro.

- [ ] **Paso 1.** Escribe la prueba `tests/test_formato.py`:
```python
"""Formatos es-CO: dólares con centavos, % con espacio duro y fechas legibles."""
from radar.vistas import entorno, fecha_es, pct


def test_formatos_es_co():
    f = entorno().filters
    assert f["usd2"](1650) == "US$1.650,00" and f["usd2"](-197.61) == "−US$197,61"
    assert f["susd2"](1056.27) == "+US$1.056,27"
    assert pct(0.25) == "25 %" and f["spct"](0.39) == "+39 %" and f["pct1"](0.035) == "3,5 %"
    assert fecha_es("2026-11-20T06:54:00") == "20 nov 2026, 6:54 a. m."
    assert fecha_es("2026-11-20T18:05") == "20 nov 2026, 6:05 p. m." and fecha_es("2026-11-20") == "20 nov 2026"
    assert fecha_es(None) == "—"
```
- [ ] **Paso 2.** Ejecútala con `pytest -q tests/test_formato.py`.
**Esperado:** FALLA con `ImportError: cannot import name 'fecha_es'`.
- [ ] **Paso 3.** En `radar/vistas.py`, cambia las importaciones del principio.
Buscar:
```python
import json
from pathlib import Path
```
Reemplazar por:
```python
import json
import math
from datetime import datetime
from pathlib import Path
```
- [ ] **Paso 4.** Reemplaza las funciones `pct1` y `pct`, desde `def pct1(x)` hasta justo antes de `def millones(x)`, por este bloque:
```python
def pct1(x) -> str:
    return "—" if x is None else f"{x * 100:.1f}\u00a0%".replace(".", ",").replace(",0\u00a0%", "\u00a0%")


def pct(x) -> str:
    return "—" if x is None else f"{x * 100:.0f}\u00a0%"


def usd_cent(x) -> str:
    """Dólares con centavos en formato es-CO: US$1.650,00."""
    if x is None:
        return "—"
    s = f"{abs(x):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return ("−" if x < 0 else "") + "US$" + s


MESES = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"]


def fecha_es(s) -> str:
    """'2026-11-20T06:54:00' -> '20 nov 2026, 6:54 a. m.'; '2026-11-20' -> '20 nov 2026'."""
    if not s:
        return "—"
    s = str(s)
    try:
        d = datetime.fromisoformat(s[:19])
    except ValueError:
        return s[:16]
    txt = f"{d.day} {MESES[d.month - 1]} {d.year}"
    if len(s) > 10:
        h = d.hour % 12 or 12
        txt += f", {h}:{d.minute:02d}\u00a0{'a.' if d.hour < 12 else 'p.'}\u00a0m."
    return txt
```
- [ ] **Paso 5.** En `entorno()`, dentro de `env.filters.update(...)`, haz dos cambios.

  **5a.** Buscar:
```python
usdes=lambda x: usd_es(x), spct=lambda x: "—" if x is None else ("−" if x < 0 else "+") + f"{abs(x) * 100:.0f} %",
```
  Reemplazar por:
```python
usdes=lambda x: usd_es(x), spct=lambda x: "—" if x is None else ("−" if x < 0 else "+") + f"{abs(x) * 100:.0f} %",
                       usd2=usd_cent, susd2=lambda x: "—" if x is None else ("−" if x < 0 else "+") + usd_cent(abs(x)),
```
  **5b.** Buscar:
```python
fecha=lambda s: "—" if not s else str(s)[:16].replace("T", " "))
```
  Reemplazar por:
```python
fecha=fecha_es)
```
- [ ] **Paso 6.** Corre `pytest -q`.
**Esperado:** `145 passed`.
- [ ] **Paso 7.** Haz el commit:
```bash
git add radar/vistas.py tests/test_formato.py
git commit -m "feat: formatos es-CO (US$ con centavos, % con espacio duro, fechas legibles)"
```

---

### Tarea 2 · Modelo de vista de la guía de embarque

**Archivos:**
- Crear `tests/test_guia.py`.
- Modificar `radar/vistas.py`.

**Interfaces:**
- **Consume:**
  - `d["costo_pedido"]`, un `asdict(Costo)` con `lineas` (7 líneas en este orden: precio, impuesto, flete+seguro+inspección, recargo, arancel, IVA, luthier), `total_usd`, `total_cop`, `flete_usd` y `seguro_usd`;
  - `d["trm"]`, `d["precio_co_cop"]` y `d["listing"]["envio_us_usd"]`.
- **Produce:**
  - `repartir(valores: list[float], unidad: float) -> list` (con `unidad` 1000 para pesos o 0.01 para dólares);
  - `guia(d, p, comision, neto_cop) -> dict`, con esta forma:
    `{"tramos": [{"n", "titulo", "paga", "moneda": "usd"|"cop", "lineas": [{"concepto", "base", "usd", "cop"}], "subtotal": {"usd", "cop"}}], "costo": {"usd", "cop"}, "n_venta": int, "venta": {"cierre", "comision", "neto": {"usd", "cop"}, "comision_pct": float, "margen": float}}`;
  - `escenarios_vista(d, p=None)`, que ahora incluye `"guia"` en cada escenario.

- [ ] **Paso 1.** Escribe la prueba `tests/test_guia.py`:
```python
"""Guía de embarque: los tramos del costo y la venta cuadran a la vista, en USD y COP."""
from dataclasses import asdict

from radar import costing, db
from radar.vistas import guia, repartir

P = dict(db.PARAMETROS_DEFECTO)


def _caso(precio=1650.0, envio=0.0, cat="bajo", ref=13_149_000, trm=3327.0, com=0.05):
    c = costing.cuenta(precio, envio, cat, trm, P)
    d = {"costo_pedido": asdict(c), "trm": trm, "precio_co_cop": ref, "listing": {"envio_us_usd": envio}}
    neto = costing.venta(ref, c, com, P).neto_cop
    return guia(d, P, com, neto), c, neto


def test_repartir_cuadra_con_el_total():
    assert repartir([1.4, 1.4, 1.2], 1) == [2, 1, 1]
    assert repartir([665_400, 192_134, 33_270, 101_469], 1000) == [665_000, 192_000, 33_000, 102_000]
    assert repartir([190.775, 398.71975], 0.01) == [190.77, 398.72]


def test_tramos_en_orden_y_con_su_base():
    g, _, _ = _caso()
    assert [t["titulo"] for t in g["tramos"]] == ["Compra en Miami", "Envío a Bogotá", "Aduana en Bogotá", "Puesta a punto"]
    assert [t["moneda"] for t in g["tramos"]] == ["usd", "usd", "cop", "cop"]
    conceptos = [l["concepto"] for t in g["tramos"] for l in t["lineas"]]
    assert conceptos == ["Precio pedido", "Impuesto de ventas", "Flete del casillero", "Seguro", "Inspección",
                         "Recargo de la tarjeta", "Arancel", "IVA", "Ajuste del luthier"]
    linea = {l["concepto"]: l for t in g["tramos"] for l in t["lineas"]}
    assert linea["Precio pedido"]["usd"] == 1650.0 and linea["Flete del casillero"]["usd"] == 200.0
    assert linea["Seguro"]["usd"] == 57.75 and linea["Inspección"]["usd"] == 10.0
    assert linea["Arancel"]["base"].startswith("10") and linea["IVA"]["base"].startswith("19")
    assert g["n_venta"] == 5


def test_todo_cuadra_a_la_vista():
    g, c, neto = _caso()
    for t in g["tramos"]:
        assert t["subtotal"]["cop"] == sum(l["cop"] for l in t["lineas"])
        assert abs(t["subtotal"]["usd"] - sum(l["usd"] for l in t["lineas"])) < 0.005
    assert g["costo"]["cop"] == sum(t["subtotal"]["cop"] for t in g["tramos"]) == round(c.total_cop, -3)
    assert abs(g["costo"]["usd"] - round(c.total_usd, 2)) < 0.005
    v = g["venta"]
    assert v["cierre"]["cop"] == 13_149_000 and v["neto"]["cop"] == round(neto, -3)
    assert v["cierre"]["cop"] - v["comision"]["cop"] - g["costo"]["cop"] == v["neto"]["cop"]
    assert abs(v["comision"]["cop"] - 13_149_000 * 0.05) <= 1000  # la comisión absorbe el redondeo
    assert abs(v["margen"] - neto / c.total_cop) < 1e-9


def test_pedal_sin_luthier_y_con_envio_en_eeuu():
    g, _, _ = _caso(precio=120.0, envio=10.0, cat="pedal", ref=900_000, com=0.10)
    assert [t["n"] for t in g["tramos"]] == [1, 2, 3] and g["n_venta"] == 4
    assert g["tramos"][0]["lineas"][0]["concepto"] == "Precio pedido y envío en EE. UU."


def test_sin_comision_la_fila_vale_cero():
    g, _, _ = _caso(com=0.0)
    assert g["venta"]["comision"]["cop"] == 0 and g["venta"]["comision_pct"] == 0.0


def test_perdida_lleva_neto_negativo():
    g, _, neto = _caso(ref=5_000_000)
    assert neto < 0 and g["venta"]["neto"]["cop"] == round(neto, -3) and g["venta"]["margen"] < 0
```
- [ ] **Paso 2.** Ejecútala con `pytest -q tests/test_guia.py`.
**Esperado:** FALLA con `ImportError: cannot import name 'guia'`.
- [ ] **Paso 3.** En `radar/vistas.py`, pega este bloque justo **antes** de `def escenarios_vista(`. El algoritmo de reparto, el mayor resto, va completo porque las pruebas fijan su resultado exacto:
```python
def repartir(valores: list[float], unidad: float) -> list:
    """Redondea cada valor a `unidad` (1000 para pesos, 0.01 para dólares) de modo que la suma de lo
    redondeado sea exactamente el total redondeado (método del mayor resto). Valores >= 0."""
    escalados = [v / unidad for v in valores]
    base = [math.floor(x + 1e-9) for x in escalados]
    faltan = round(sum(escalados)) - sum(base)
    orden = sorted(range(len(valores)), key=lambda i: escalados[i] - base[i], reverse=True)
    for i in orden[:max(faltan, 0)]:
        base[i] += 1
    return [round(b * unidad, 2) if unidad < 1 else int(b * unidad) for b in base]


TRAMOS = [(1, "Compra en Miami", "Pagas en dólares", "usd"),
          (2, "Envío a Bogotá", "Pagas en dólares", "usd"),
          (3, "Aduana en Bogotá", "Pagas en pesos", "cop"),
          (4, "Puesta a punto", "Pagas en pesos", "cop")]


def guia(d: dict, p: dict, comision: float, neto_cop: float) -> dict:
    """Guía de embarque al precio pedido: tramos de costo en USD y COP que cuadran a la vista,
    y la venta con la comisión dada. `neto_cop` es el neto exacto del escenario (el de la lista)."""
    c, trm, ref = d["costo_pedido"], d["trm"], d["precio_co_cop"]
    L = c["lineas"]
    flete, seguro = c["flete_usd"], c["seguro_usd"]
    inspeccion = L[2]["usd"] - flete - seguro
    envio_us = d["listing"].get("envio_us_usd") or 0
    crudas = [  # (tramo, concepto, cómo se calcula, usd exacto)
        (1, "Precio pedido y envío en EE. UU." if envio_us else "Precio pedido", "", L[0]["usd"]),
        (1, "Impuesto de ventas", f"{pct(p.get('sales_tax_us', 0.07))} del precio", L[1]["usd"]),
        (2, "Flete del casillero", "", flete),
        (2, "Seguro", f"{pct1(p.get('seguro_pct', 0.035))} del precio", seguro),
        (2, "Inspección", "", inspeccion),
        (2, "Recargo de la tarjeta", f"{pct1(p.get('margen_cambiario', 0.015))} de compra y envío", L[3]["usd"]),
        (3, "Arancel", f"{pct(p.get('arancel', 0.10))} de precio + flete + seguro", L[4]["usd"]),
        (3, "IVA", f"{pct(p.get('iva', 0.19))} de lo anterior + arancel", L[5]["usd"]),
        (4, "Ajuste del luthier", "", L[6]["usd"]),
    ]
    crudas = [x for x in crudas if x[3] > 0.004]
    usd_r = repartir([x[3] for x in crudas], 0.01)
    cop_r = repartir([x[3] * trm for x in crudas], 1000)
    tramos = []
    for n, titulo, paga, moneda in TRAMOS:
        filas = [{"concepto": x[1], "base": x[2], "usd": u, "cop": k}
                 for x, u, k in zip(crudas, usd_r, cop_r) if x[0] == n]
        if filas:
            tramos.append({"n": n, "titulo": titulo, "paga": paga, "moneda": moneda, "lineas": filas,
                           "subtotal": {"usd": round(sum(f["usd"] for f in filas), 2),
                                        "cop": sum(f["cop"] for f in filas)}})
    costo = {"usd": round(sum(usd_r), 2), "cop": sum(cop_r)}
    cierre = {"usd": round(ref / trm, 2), "cop": int(round(ref, -3))}
    neto = {"usd": round(neto_cop / trm, 2), "cop": int(round(neto_cop, -3))}
    # la comisión absorbe el residuo del redondeo (a lo sumo $1.000 o US$0,01)
    com = {"usd": round(cierre["usd"] - costo["usd"] - neto["usd"], 2), "cop": cierre["cop"] - costo["cop"] - neto["cop"]}
    return {"tramos": tramos, "costo": costo, "n_venta": len(tramos) + 1,
            "venta": {"cierre": cierre, "comision": com, "neto": neto, "comision_pct": comision,
                      "margen": neto_cop / c["total_cop"] if c["total_cop"] else 0}}
```
- [ ] **Paso 4.** Conecta la guía con los escenarios, en tres cambios dentro de `radar/vistas.py`.

  **4a.** Cambia la firma de `def escenarios_vista(d: dict) -> dict:` a `def escenarios_vista(d: dict, p: dict | None = None) -> dict:`.

  **4b.** Justo después de la línea `trm, ref = d["trm"], d["precio_co_cop"]` de esa función, agrega:
```python
    p = p or db.PARAMETROS_DEFECTO
```
  **4c.** Después de la línea `"pasos": _pasos(cp["lineas"], comision_cop, e["neto_pedido_cop"], trm, com),`, agrega:
```python
            "guia": guia(d, p, com, e["neto_pedido_cop"]),
```
  Por último, en `cargar_ops`, cambia `o["esc"] = escenarios_vista(d)` por `o["esc"] = escenarios_vista(d, p)`.
- [ ] **Paso 5.** Corre `pytest -q`.
**Esperado:** `151 passed`.
- [ ] **Paso 6.** Haz el commit:
```bash
git add radar/vistas.py tests/test_guia.py
git commit -m "feat: guía de embarque por tramos con montos que cuadran a la vista"
```

---

### Tarea 3 · Paleta, tipografías y CSS de la guía

**Archivos:**
- Modificar `radar/web/templates/base.html`.
- Modificar `tests/test_web.py`.

- [ ] **Paso 1.** Agrega esta prueba al **final** de `tests/test_web.py`:
```python
def test_paleta_road_case(cliente):
    c, _ = cliente
    t = c.get("/").text
    assert "Big+Shoulders+Stencil" in t and "Schibsted+Grotesk" in t and "Archivo" not in t
    assert "--naranja:#FF6B1A" in t and "--tolex" not in t and "Radar · MIA → BOG" in t
```
- [ ] **Paso 2.** Ejecútala con `pytest -q tests/test_web.py::test_paleta_road_case`.
**Esperado:** FALLA en la primera aserción.
- [ ] **Paso 3.** En `base.html`, reemplaza la línea que carga las tipografías.
Buscar:
```html
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Archivo:wdth,wght@62..125,400..700&display=swap">
```
Reemplazar por:
```html
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Big+Shoulders+Stencil:opsz,wght@10..72,500..900&family=Schibsted+Grotesk:wght@400..800&family=IBM+Plex+Mono:wght@400;500&display=swap">
```
- [ ] **Paso 4.** Reemplaza **todo** el bloque `<style>…</style>` de `base.html` (desde `<style>` hasta `</style>`, ambos incluidos) por este. Trae:
  - la paleta nueva con variables renombradas;
  - bordes de 1 px en aluminio;
  - el manifiesto (`.mini`);
  - la guía (`.guia`, `.tramo`, `.guia-fila`), la cinta (`.gaffer`) y la versión móvil.
```html
<style>
/* Dirección B «Road case MIA → BOG» (ver DESIGN.md). Bordes de 1 px en aluminio; sombra solo en la hoja móvil. */
:root{--estuche:#1A1B1E;--laminado:#25272B;--laminado2:#2C2F34;--aluminio:#AEB4BB;--cinta:#ECE5D2;--tinta:#16181D;--tinta2:#4A4E57;
--raya:#C9C0A8;--total:#E2D9C2;--naranja:#FF6B1A;--fragil:#FF5A5F;
--ease-out:cubic-bezier(0.23,1,0.32,1);--ease-drawer:cubic-bezier(0.32,0.72,0,1);--t-press:140ms;--t-estado:200ms;--t-hoja:280ms;
--r:0;--r2:0}
*{box-sizing:border-box}html{color-scheme:dark;-webkit-text-size-adjust:100%}
body{margin:0;background:var(--estuche);color:var(--cinta);font:16px/1.5 "Schibsted Grotesk",system-ui,sans-serif;font-variant-numeric:tabular-nums;-webkit-font-smoothing:antialiased}
a{color:var(--naranja)}a:hover{color:var(--cinta)}
h1,h2,h3{margin:0;line-height:1.1;text-wrap:balance}
h1,h2,.sten{font-family:"Big Shoulders Stencil","Schibsted Grotesk",sans-serif;font-weight:800;letter-spacing:.01em;text-transform:uppercase}
h1{font-size:40px}h2{font-size:26px}h3{font-size:17px;font-weight:700}
p{text-wrap:pretty}
.envol{max-width:1376px;margin:0 auto;padding:0 32px}
.suave{color:var(--aluminio)}.pequeno{font-size:13px}.chico{font-size:12px}.angosto{}
.pos{color:var(--naranja)}.neg{color:var(--fragil)}
.oculto{display:none!important}
button{font-family:inherit}
:focus-visible{outline:2px solid var(--naranja);outline-offset:2px}
.pulsar{transition:transform var(--t-press) var(--ease-out)}.pulsar:active{transform:scale(0.97)}
@media (prefers-reduced-motion:reduce){*{transition:none!important}}

.cab .envol{display:flex;flex-wrap:wrap;align-items:baseline;justify-content:space-between;gap:12px 32px;padding-top:24px;padding-bottom:8px}
.cab .izq{display:flex;flex-wrap:wrap;align-items:baseline;gap:8px 24px}
.marca{font-size:26px;color:var(--cinta);text-decoration:none}
.cab nav{display:flex;flex-wrap:wrap;gap:4px 20px;font-size:15px}
.cab nav a{color:var(--aluminio);text-decoration:none;padding:8px 0}
.cab nav a:hover,.cab nav a[aria-current="page"]{color:var(--cinta)}.cab nav a[aria-current="page"]{font-weight:600}
.cab .meta{font-size:13px;color:var(--aluminio)}
main.envol{padding-top:24px;padding-bottom:48px;display:flex;flex-direction:column;gap:32px}

.pregunta{display:flex;flex-wrap:wrap;align-items:flex-end;justify-content:space-between;gap:16px 32px}
.pregunta p{margin:6px 0 0;color:var(--aluminio);max-width:70ch}
.selector{display:flex;align-items:center;gap:12px}
.selector>span{font-size:13px;color:var(--aluminio)}
.segmentos{display:flex;border:1.5px solid var(--aluminio)}
.segmentos button{border:0;border-radius:4px;padding:8px 14px;min-height:40px;min-width:56px;font-size:14px;font-weight:600;cursor:pointer;background:transparent;color:var(--aluminio)}
.segmentos button[aria-pressed="true"]{background:var(--naranja);color:var(--tinta)}

/* Una cifra por escenario de comisión; solo se ve la elegida */
{% for k in comisiones %}html[data-com="{{ k }}"] .esc:not([data-c="{{ k }}"]){display:none!important}
html[data-com="{{ k }}"] .ord{order:var(--o{{ k }})}
{% endfor %}

.dinero{display:inline-flex;flex-direction:column;align-items:flex-end;line-height:1.25}
.dinero .usd{font-size:12px;color:var(--aluminio);font-weight:400}

.chips{display:flex;flex-wrap:wrap;gap:6px}
.chip{display:inline-block;font-size:12px;border-radius:2px;padding:2px 10px;white-space:nowrap;background:var(--estuche);color:var(--cinta);border:1px solid var(--laminado)}
.chip.reventa,.chip.ganga{background:var(--naranja);color:var(--tinta);border-color:var(--naranja);font-weight:600}
.chip.posible,.chip.bajo{border-color:var(--naranja);color:var(--naranja)}
.chip.estimada,.chip.revisar{border-color:var(--aluminio);color:var(--cinta)}
.chip.encima,.chip.sinmargen{color:var(--fragil);border-color:var(--laminado)}
.chip.interes{border-color:var(--cinta);color:var(--cinta);font-weight:600}
.seguida{display:grid;grid-template-columns:minmax(0,2fr) minmax(120px,1fr) minmax(150px,1fr) auto;gap:16px;align-items:center;padding:16px 20px;border-top:1px solid var(--estuche)}
.seguida:first-child{border-top:0}
.seguida .nom{display:flex;flex-direction:column;gap:4px;min-width:0}
.seguida .nom b{font-size:16px}
.historial{margin:0;padding:0;list-style:none;display:flex;flex-direction:column;gap:6px;font-size:14px}
.historial li{display:flex;gap:12px}.historial time{color:var(--aluminio);min-width:7em}

.foto{position:relative;overflow:hidden;background:var(--estuche);border:1px solid var(--aluminio);display:flex;align-items:center;justify-content:center;text-align:center;padding:16px;color:var(--aluminio);font-size:14px}
.foto img{position:absolute;inset:0;width:100%;height:100%;object-fit:cover;}

.boton{display:inline-flex;align-items:center;justify-content:center;gap:8px;min-height:44px;padding:0 16px;border-radius:0;border:1px solid var(--aluminio);background:transparent;color:var(--cinta);font-size:15px;font-weight:600;text-decoration:none;cursor:pointer;transition:background-color var(--t-estado) var(--ease-out)}
.boton:hover{background:var(--laminado2);color:var(--cinta)}
.boton.prim{background:var(--naranja);border-color:var(--naranja);color:var(--tinta);font-weight:700}.boton.prim:hover{background:#FF8240}
.boton:disabled{opacity:.5;cursor:not-allowed}
.botones{display:flex;flex-wrap:wrap;gap:10px}

/* Estuche: el detalle de una publicación */
.estuche{position:relative;background:var(--laminado);border:1px solid var(--aluminio);padding:28px;display:flex;flex-direction:column;gap:24px;min-width:0}
.estuche:before,.estuche:after{content:"";position:absolute;top:-1px;width:20px;height:20px;border:1px solid var(--aluminio);background:var(--laminado2)}
.estuche:before{left:-1px;border-radius:0 0 8px 0}.estuche:after{right:-1px;border-radius:0 0 0 8px}
.estuche .cabeza{display:flex;flex-wrap:wrap;gap:24px}
.estuche .foto{flex:0 0 240px;height:180px}
.estuche .datos{flex:1 1 280px;display:flex;flex-direction:column;gap:14px;min-width:0}
.tres{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px}
.cifra{display:flex;flex-direction:column;gap:2px;min-width:0}
.cifra .k{font-size:12px;color:var(--aluminio)}
.cifra .v{font-size:22px;font-weight:700}
.cifra .s{font-size:12px;color:var(--aluminio)}
.cascada{display:grid;grid-template-columns:minmax(150px,200px) minmax(0,1fr) 84px 120px;grid-auto-flow:row dense;gap:10px 16px;align-items:center}
.cascada .et{grid-column:1}.cascada .barra{grid-column:2}.cascada .u{grid-column:3}.cascada .c{grid-column:4}
.cascada .tit{font-size:12px;color:var(--aluminio);text-align:right}
.cascada .et{font-size:14px}
.cascada .barra{position:relative;height:16px;background:var(--estuche);border-radius:2px}
.cascada .barra i{position:absolute;top:0;height:100%;border-radius:2px;background:var(--aluminio)}
.cascada .barra i.comision,.cascada .barra i.perdida{background:var(--fragil)}.cascada .barra i.ganancia{background:var(--naranja)}
.cascada .u{text-align:right;font-size:13px;color:var(--aluminio)}.cascada .c{text-align:right;font-size:14px}
.cascada .fuerte{font-weight:700}
.neto{display:flex;flex-wrap:wrap;align-items:baseline;gap:8px 16px}
.neto .grande{font-size:26px;font-weight:700}
.nota{margin:0;font-size:13px;color:var(--aluminio);max-width:72ch}
.aviso{margin:0;font-size:14px;color:var(--cinta);background:var(--estuche);border-radius:var(--r);padding:10px 14px}

/* Guía de embarque: la cuenta por tramos (ver DESIGN.md) */
.guia{background:var(--cinta);color:var(--tinta);border:2px solid var(--tinta);overflow:hidden}
.guia-cab{display:flex;justify-content:space-between;align-items:baseline;gap:8px;padding:8px 12px 0;font-size:11px;font-weight:700;color:var(--tinta2)}
.guia-num{font-family:"IBM Plex Mono",monospace;font-weight:400;color:var(--tinta)}
.ruta{display:grid;grid-template-columns:auto minmax(0,1fr) auto minmax(0,1fr) auto;align-items:center;gap:8px;padding:12px 12px 10px}
.ruta .sten{font-size:40px;line-height:1}
.ruta i{display:block;border-top:3px dashed var(--tinta)}
.ruta .escala{font-size:11px;font-weight:700;text-align:center;line-height:1.2}
.guia-fila{display:grid;grid-template-columns:minmax(0,1.6fr) minmax(0,1.3fr) 110px 130px;gap:10px;padding:7px 12px;border-top:1px solid var(--raya);font-size:15px;align-items:baseline}
.guia-fila .n{text-align:right;white-space:nowrap}
.guia-fila .base{font-size:12px;color:var(--tinta2)}
.guia-fila .con small{display:none}
.guia-tit{font-size:11px;font-weight:700;color:var(--tinta2);border-top:0;padding-top:0}
.tramo{border-top:2px solid var(--tinta)}
.tramo-cab{display:flex;justify-content:space-between;align-items:baseline;gap:12px;padding:8px 12px 4px}
.tramo-cab .sten{font-size:20px}
.tramo-cab .paga{font-size:11px;font-weight:700;color:var(--tinta2)}
.tramo[data-paga="usd"] .guia-fila .usd,.tramo[data-paga="cop"] .guia-fila .cop{font-weight:700}
.tramo[data-paga="usd"] .guia-fila .cop,.tramo[data-paga="cop"] .guia-fila .usd{color:var(--tinta2)}
.guia-fila.sub{border-top:1.5px dashed var(--tinta);font-weight:700}
.tramo .guia-fila.sub .n{color:var(--tinta);font-weight:700}
.guia-fila.total{border-top:2px solid var(--tinta);background:var(--total);font-weight:700}
.tramo.venta{margin-top:12px}
.guia-fila.neto{background:var(--tinta);color:var(--cinta);border-top:2px solid var(--tinta);padding:10px 12px;font-weight:700}
.guia-fila.neto .base{color:var(--aluminio)}
.tramo .guia-fila.neto .usd{color:var(--cinta)}
.guia-fila.neto .cop{font-size:18px;font-weight:800;color:var(--naranja)}.guia-fila.neto .cop.neg{color:var(--fragil)}
.gaffer{display:inline-block;align-self:flex-start;background:var(--cinta);color:var(--tinta);padding:6px 14px 5px;font-size:22px;line-height:1.1;clip-path:polygon(0 4%,3% 0,97% 6%,100% 0,99% 96%,96% 100%,4% 94%,0 100%)}
.modelo{font-size:34px;line-height:1}

/* Hoy: lista y estuche */
.mesa{display:flex;flex-wrap:wrap;gap:24px;align-items:flex-start}
.lista{flex:1 1 420px;min-width:0;display:flex;flex-direction:column;gap:2px}
.lista .cols{display:flex;justify-content:space-between;font-size:12px;color:var(--aluminio);padding:8px 12px}
.lista{border:1px solid var(--aluminio)}
.item{display:grid;grid-template-columns:56px minmax(0,1fr) auto;align-items:center;gap:14px;padding:10px 12px;min-height:76px;border-top:1px solid var(--laminado2);color:inherit;text-decoration:none;transition:background-color var(--t-estado) var(--ease-out)}
.mini{width:56px;height:56px;border:1px solid var(--aluminio);background:var(--estuche);overflow:hidden}.mini img{display:block;width:100%;height:100%;object-fit:cover}
.item:hover{background:var(--laminado2);color:inherit}.item[aria-current="true"]{background:var(--laminado)}
.item .nom{display:flex;flex-direction:column;gap:3px;min-width:0}
.item .nom b{font-size:15px;font-weight:700;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.item .nom span{font-size:13px;color:var(--aluminio)}
.item .monto{font-size:17px;font-weight:700}
.panel{flex:999 1 560px;min-width:0;position:sticky;top:16px}
.panel .cerrar{display:none}

/* Tablas */
.caja{background:var(--laminado);border:1px solid var(--aluminio)}
.tabla{overflow-x:auto}
table{width:100%;border-collapse:collapse;font-size:14px}
.tabla table{min-width:1120px}
th{padding:12px;text-align:left;font-size:12px;font-weight:500;color:var(--aluminio);white-space:nowrap}
td{padding:12px;border-top:1px solid var(--estuche);vertical-align:top}
td.n,th.n{text-align:right}
td small,th small{display:block;font-size:12px;color:var(--aluminio);font-weight:400}
td .t{color:var(--cinta);font-weight:600;text-decoration:none}td .t:hover{color:var(--naranja)}
th button{min-height:0;padding:0;border:0;color:inherit;font-size:12px;font-weight:500;background:none;cursor:pointer}
th button:hover{color:var(--cinta)}

.filtros{display:flex;flex-wrap:wrap;gap:12px;align-items:flex-end}
label{display:flex;flex-direction:column;gap:6px;font-size:13px;color:var(--aluminio)}
input,select{font:inherit;font-size:16px;color:var(--cinta);background:var(--estuche);border:1px solid var(--laminado);border-radius:var(--r);padding:10px 12px;min-height:44px}
.forro input,.forro select,.estuche input{background:var(--estuche);border-color:var(--estuche)}
.vacio{border:1px dashed var(--aluminio);padding:24px;color:var(--aluminio)}
.seccion{display:flex;flex-direction:column;gap:14px}
.seccion-cab{display:flex;flex-wrap:wrap;justify-content:space-between;align-items:baseline;gap:8px 16px}
.rejilla{display:grid;grid-template-columns:repeat(auto-fit,minmax(320px,1fr));gap:24px}
.pares{display:flex;flex-direction:column;gap:8px}
.par{display:flex;justify-content:space-between;gap:12px;align-items:baseline}
.par>span:first-child{font-size:14px;color:var(--aluminio)}.par>span:last-child{text-align:right}
pre{white-space:pre-wrap;background:var(--estuche);padding:12px;border-radius:var(--r);font-size:13px;color:var(--aluminio);max-height:420px;overflow:auto}
details summary{cursor:pointer;color:var(--aluminio)}
.progreso{height:8px;background:var(--estuche);border-radius:4px;overflow:hidden;max-width:420px}.progreso i{display:block;height:100%;background:var(--naranja)}
.pie{border-top:1px solid var(--laminado);padding-top:16px;padding-bottom:32px;font-size:12px;color:var(--aluminio)}
.pie p{margin:0 0 6px;max-width:110ch}

@media (max-width:900px){
  .envol{padding:0 16px}
  .estuche{padding:16px}
  .estuche .guia{margin:0 -16px;border-left:0;border-right:0}
  .guia-fila{grid-template-columns:minmax(0,1fr) 96px 88px;gap:8px;padding:7px 12px;font-size:14px}
  .tramo-cab .sten{font-size:18px}.tramo-cab .paga{white-space:nowrap}
  .guia-fila .base{display:none}
  .guia-fila .con small{display:block;font-size:11px;font-weight:400;color:var(--tinta2)}
  .guia-fila.neto{grid-template-columns:minmax(0,1fr) auto}
  .guia-fila.neto .cop{grid-row:1;grid-column:2}
  .guia-fila.neto .usd{grid-row:2;grid-column:1 / -1;font-size:12px;font-weight:400;color:var(--aluminio)}
  .guia-fila.neto .con small{color:var(--aluminio)}
  .ruta .sten{font-size:30px}
  .modelo{font-size:28px}
  h1{font-size:30px}
  .tres{gap:10px}.cifra .v{font-size:18px}
  .seguida{grid-template-columns:minmax(0,1fr) auto;padding:14px 16px}
  .seguida .nom,.seguida .botones{grid-column:1 / -1}.seguida .botones{justify-content:flex-start!important}.neto .grande{font-size:22px}
  .lineas td,.lineas th{padding:10px 6px}.lineas th{white-space:normal}.caja{padding:16px!important}
  .estuche .foto{flex-basis:100%;height:200px}
  .cascada{grid-template-columns:minmax(0,1fr) auto;gap:4px 12px}
  .cascada .et{grid-column:1}.cascada .c{grid-column:2}
  .cascada .barra{grid-column:1 / -1;height:10px;margin-bottom:6px}
  .cascada .u,.cascada .tit{display:none}
  .cascada .c .ux{display:inline}
  /* En el móvil, el estuche de Hoy se abre como hoja desde abajo */
  .panel{position:fixed;top:auto;left:0;right:0;bottom:0;max-height:88vh;overflow-y:auto;z-index:20;transform:translateY(105%);visibility:hidden;transition:transform var(--t-hoja) var(--ease-drawer),visibility 0s linear var(--t-hoja);padding-bottom:env(safe-area-inset-bottom)}
  .panel.abierto{transform:none;visibility:visible;transition:transform var(--t-hoja) var(--ease-drawer)}
  .panel .estuche:before,.panel .estuche:after{display:none}
  .panel .estuche{border-radius:16px 16px 0 0;border-bottom:0;box-shadow:0 -1px 0 rgba(0,0,0,.3),0 -12px 32px rgba(0,0,0,.45)}
  .panel .cerrar{display:flex;position:sticky;top:12px;height:0;justify-content:flex-end;z-index:2;padding-right:12px}
  .panel .cerrar .boton{width:44px;padding:0;border-radius:22px;background:var(--estuche)}
  .velo{position:fixed;inset:0;background:rgba(0,0,0,.45);z-index:19;opacity:0;pointer-events:none;transition:opacity var(--t-hoja) var(--ease-out)}
  .velo.abierto{opacity:1;pointer-events:auto}
}
.cascada .c .ux{display:none;color:var(--aluminio);font-size:12px}
</style>
```
- [ ] **Paso 5.** En el encabezado de `base.html`, cambia la marca.
Buscar:
```html
<a class="marca" href="{{ e('hoy') }}" data-con-com>Radar de instrumentos</a>
```
Reemplazar por:
```html
<a class="marca sten" href="{{ e('hoy') }}" data-con-com>Radar · MIA → BOG</a>
```
- [ ] **Paso 6.** Corre `pytest -q`.
**Esperado:** `152 passed`. Las demás pruebas siguen en verde porque el CSS nuevo todavía no tiene marcado que lo use.
- [ ] **Paso 7.** Haz el commit:
```bash
git add radar/web/templates/base.html tests/test_web.py
git commit -m "feat: paleta y tipografías road case (naranja, aluminio, cinta; esténcil y grotesca)"
```

---

### Tarea 4 · Estuche con cinta gaffer y guía; manifiesto con miniaturas; % con espacio duro

**Archivos:**
- Modificar `radar/web/templates/_macros.html`, `hoy.html`, `detalle.html`, `explorar.html`, `estado.html` y `parametros.html`.
- Modificar `tests/test_web.py`.

**Interfaces:**
- **Consume:** `v.guia`, de la tarea 2, y los filtros `usd2` y `susd2`, de la tarea 1.
- **Produce:**
  - la macro `guia(o, v)`;
  - en el estuche, el bloque «De dónde sale el neto»: `h2` en el detalle y `h3` en Hoy;
  - en el ítem de la lista de Hoy, `<span class="mini">`.

- [ ] **Paso 1.** Cambia la prueba de Hoy en `tests/test_web.py`.
Buscar:
```python
    assert "A dónde va cada peso de la venta" in r.text and ">USD<" in r.text and ">COP<" in r.text and "US$" in r.text
```
Reemplazar por:
```python
    assert "De dónde sale el neto" in r.text and ">USD<" in r.text and ">COP<" in r.text and "US$" in r.text
    # la guía de embarque: tramos en orden, costo puesto y neto
    assert 'class="guia"' in r.text and "Costo puesto en Bogotá" in r.text and 'class="guia-fila neto"' in r.text
    assert r.text.index("Compra en Miami") < r.text.index("Envío a Bogotá") < r.text.index("Aduana en Bogotá")
    assert r.text.count('class="mini"') == 2
```
- [ ] **Paso 2.** Ejecútala con `pytest -q tests/test_web.py::test_hoy_muestra_lista_y_estuche_en_dos_monedas`.
**Esperado:** FALLA en `"De dónde sale el neto"`.
- [ ] **Paso 3.** Reemplaza **todo** el contenido de `radar/web/templates/_macros.html` por el que sigue. Respecto del actual:
  - agrega la macro `guia`;
  - en el estuche, cambia el bloque «tres» de abre/pide/techo por la cinta gaffer;
  - cambia la cascada por la guía y quita el bloque `.neto`, que se repetía;
  - pone el título del modelo en esténcil;
  - en el ítem, agrega la miniatura y quita la etiqueta «Referencia estimada», que ahora solo va en el estuche.
```html
{% macro foto(o, estilo="", perezosa=True) -%}
<div class="foto"{% if estilo %} style="{{ estilo }}"{% endif %}><span class="respaldo">{{ o.normalizado.marca }} {{ o.normalizado.modelo }}</span>{% if o.listing.fotos %}<img src="{{ o.listing.fotos[0] }}" alt="" referrerpolicy="no-referrer"{% if perezosa %} loading="lazy"{% endif %} onerror="this.remove()">{% endif %}</div>
{%- endmacro %}

{% macro chips(o) -%}
{% set seguida = o.listing.plataforma == 'reverb' and o.listing.id_externo in interes_ids %}
<div class="chips"><span class="chip {{ o.clase }}">{{ o.corto }}</span>{% if seguida %}<span class="chip interes">En interés</span>{% endif %}{% if o.prioritario %}<span class="chip posible">Neck-thru</span>{% endif %}{% if o.confianza_co == 'baja' %}<span class="chip estimada">Referencia de Colombia estimada</span>{% endif %}{% if o.banderas %}<span class="chip revisar">Revisar</span>{% endif %}{% if o.estado != 'nueva' %}<span class="chip">{{ o.estado|plataforma }}</span>{% endif %}</div>
{%- endmacro %}

{% macro sub(o) -%}
{{ o.listing.plataforma|plataforma }} · {{ o.normalizado.estado }}{% if o.normalizado.anio %} · {{ o.normalizado.anio }}{% endif %}{% if o.dias_publicado is not none %} · {{ o.dias_publicado }} días publicada{% endif %}{% if o.listing.acepta_ofertas %} · acepta ofertas{% endif %}
{%- endmacro %}

{# Una cifra en pesos con su equivalente en dólares debajo #}
{% macro dinero(cop, usd, signo=False, clase="") -%}
<span class="dinero {{ clase }}">{% if signo %}<span>{{ cop|scop }}</span><span class="usd">{{ usd|susd }}</span>{% else %}<span>{{ cop|cop }}</span><span class="usd">{{ usd|usd }}</span>{% endif %}</span>
{%- endmacro %}

{# Fila de la lista de Hoy: neto al precio pedido para cada comisión #}
{% macro item(o, e, sel=False) -%}
<a class="item ord" href="{{ e('detalle', o.id) }}" data-con-com data-op="{{ o.id }}" aria-current="{{ 'true' if sel else 'false' }}" style="{% for k, v in o.esc.items() %}--o{{ k }}:{{ (-v.neto_pedido_cop / 1000)|round|int }};{% endfor %}{% if not o.esc %}--o0:99999;--o5:99999;--o10:99999{% endif %}">
<span class="mini">{% if o.listing.fotos %}<img src="{{ o.listing.fotos[0] }}" alt="" referrerpolicy="no-referrer" loading="lazy" onerror="this.remove()">{% endif %}</span>
<span class="nom"><b>{{ o.normalizado.marca }} {{ o.normalizado.modelo }}</b><span>{{ o.listing.plataforma|plataforma }} · {{ o.normalizado.estado }} · pide {{ o.listing.precio_usd|usd }}</span>{% if o.prioritario or (o.listing.plataforma == 'reverb' and o.listing.id_externo in interes_ids) %}<span class="chips" style="margin-top:3px">{% if o.listing.plataforma == 'reverb' and o.listing.id_externo in interes_ids %}<span class="chip interes">En interés</span>{% endif %}{% if o.prioritario %}<span class="chip posible">Neck-thru</span>{% endif %}</span>{% endif %}</span>
{% if o.esc %}{% for k, v in o.esc.items() %}<span class="esc dinero" data-c="{{ k }}"><span class="monto {{ 'pos' if v.neto_pedido_cop >= 0 else 'neg' }}">{{ v.neto_pedido_cop|scop }}</span><span class="usd">{{ v.neto_pedido_usd|susd }} · {{ v.margen_pedido|spct }}</span></span>{% endfor %}
{% else %}<span class="dinero"><span class="monto suave">—</span><span class="usd">sin cuenta</span></span>{% endif %}
</a>
{%- endmacro %}

{# Guía de embarque: costo por tramos y venta, en USD y COP (ver DESIGN.md) #}
{% macro guia(o, v) -%}
{% set g = v.guia %}
<div class="guia" role="group" aria-label="Guía de embarque: de dónde sale el neto">
<div class="guia-cab"><span>Guía de embarque · TRM {{ o.trm|trm }} · comisión {{ (v.comision * 100)|round|int }}&nbsp;%</span><span class="guia-num" translate="no">{{ (o.listing.plataforma|plataforma)|upper }} {{ o.listing.id_externo }}</span></div>
<div class="ruta" aria-hidden="true"><span class="sten">MIA</span><i></i><span class="escala">casillero<br>y vuelo</span><i></i><span class="sten">BOG</span></div>
<div class="guia-fila guia-tit"><span>Concepto</span><span class="base">Cómo se calcula</span><span class="n">USD</span><span class="n">COP</span></div>
{% for t in g.tramos %}<div class="tramo" data-paga="{{ t.moneda }}">
<div class="tramo-cab"><span class="sten">{{ t.n }} · {{ t.titulo }}</span><span class="paga">{{ t.paga }}</span></div>
{% for l in t.lineas %}<div class="guia-fila"><span class="con">{{ l.concepto }}{% if l.base %}<small>{{ l.base }}</small>{% endif %}</span><span class="base">{{ l.base }}</span><span class="n usd">{{ l.usd|usd2 }}</span><span class="n cop">{{ l.cop|cop }}</span></div>
{% endfor %}{% if t.lineas|length > 1 %}<div class="guia-fila sub"><span class="con">Subtotal</span><span class="base"></span><span class="n">{{ t.subtotal.usd|usd2 }}</span><span class="n">{{ t.subtotal.cop|cop }}</span></div>{% endif %}
</div>
{% endfor %}<div class="guia-fila total"><span class="con">Costo puesto en Bogotá</span><span class="base">{{ g.tramos|map(attribute='n')|join(' + ') }}</span><span class="n">{{ g.costo.usd|usd2 }}</span><span class="n">{{ g.costo.cop|cop }}</span></div>
<div class="tramo venta" data-paga="cop">
<div class="tramo-cab"><span class="sten">{{ g.n_venta }} · Venta en Bogotá</span><span class="paga">Cobras en pesos</span></div>
<div class="guia-fila"><span class="con">Cierre esperado<small>{{ 'estimado' if o.confianza_co == 'baja' else 'con tiendas de Colombia' }}</small></span><span class="base">{{ 'estimado' if o.confianza_co == 'baja' else 'con tiendas de Colombia' }}</span><span class="n usd">{{ g.venta.cierre.usd|usd2 }}</span><span class="n cop">{{ g.venta.cierre.cop|cop }}</span></div>
{% if g.venta.comision_pct > 0 %}<div class="guia-fila"><span class="con">Comisión del vendedor<small>{{ g.venta.comision_pct|pct }} del cierre</small></span><span class="base">{{ g.venta.comision_pct|pct }} del cierre</span><span class="n usd">{{ (-g.venta.comision.usd)|usd2 }}</span><span class="n cop">{{ (-g.venta.comision.cop)|scop }}</span></div>{% endif %}
<div class="guia-fila"><span class="con">Costo puesto<small>viene de arriba</small></span><span class="base">viene de arriba</span><span class="n usd">{{ (-g.costo.usd)|usd2 }}</span><span class="n cop">{{ (-g.costo.cop)|scop }}</span></div>
<div class="guia-fila neto"><span class="con">Neto<small>{{ g.venta.margen|spct }} sobre el costo puesto</small></span><span class="base">{{ g.venta.margen|spct }} sobre el costo puesto</span><span class="n usd">{{ g.venta.neto.usd|susd2 }}</span><span class="n cop{{ ' neg' if g.venta.neto.cop < 0 }}">{{ g.venta.neto.cop|scop }}</span></div>
</div></div>
{%- endmacro %}

{# Estuche: cinta con la oferta, botones y guía de embarque, en USD y COP para cada comisión #}
{% macro estuche(o, e, completo=False, titulo_h="h2") -%}
<section class="estuche" aria-label="Estuche de {{ o.normalizado.marca }} {{ o.normalizado.modelo }}" data-estuche="{{ o.id }}">
<div class="cabeza">
{{ foto(o, perezosa=not completo) }}
<div class="datos">
{{ chips(o) }}
<div><{{ titulo_h }} class="sten modelo">{{ o.normalizado.marca }} {{ o.normalizado.modelo }}</{{ titulo_h }}>
<p class="suave pequeno" style="margin:6px 0 0">{{ sub(o) }}</p></div>
{% if o.esc %}{% for k, v in o.esc.items() %}<div class="esc" data-c="{{ k }}" style="display:flex;flex-direction:column;gap:6px">
{% if v.apertura %}<span class="gaffer sten">Techo {{ v.techo|usd }} · abre {{ v.apertura|usd }}</span>{% else %}<span class="gaffer sten">Sin oferta con esta comisión</span>{% endif %}
<span class="suave pequeno">Pide {{ o.listing.precio_usd|usd }} ≈ {{ (o.listing.precio_usd * o.trm)|millones }}{% if v.apertura %} · abre ≈ {{ (v.apertura * o.trm)|millones }} · el techo deja el {{ p.margen_objetivo|pct }} neto{% endif %}</span>
</div>{% endfor %}{% endif %}
<div class="botones">
{% if o.mensajes %}{% for k, v in o.esc.items() %}<button type="button" class="boton prim pulsar esc" data-c="{{ k }}" data-copiar="{{ o.id }}"{% if not v.apertura %} disabled{% endif %}>{{ ('Copiar oferta de ' ~ (v.apertura|usd)) if v.apertura else 'Sin oferta con esta comisión' }}</button>{% endfor %}{% endif %}
<a class="boton" href="{{ o.listing.url }}" target="_blank" rel="noopener">Abrir en {{ o.listing.plataforma|plataforma }}</a>
{% if repo and o.listing.plataforma == 'reverb' %}{% if o.listing.id_externo in interes_ids %}<a class="boton" href="{{ url_quitar(repo, o.listing.id_externo) }}" target="_blank" rel="noopener">Quitar de interés</a>{% else %}<a class="boton" href="{{ url_seguir(repo, o) }}" target="_blank" rel="noopener" title="Abre un formulario de GitHub ya lleno: envíalo y el radar la vigilará cada día">Seguir en interés</a>{% endif %}{% endif %}
{% if not completo %}<a class="boton" href="{{ e('detalle', o.id) }}" data-con-com>Ver cuentas y comparables</a>{% endif %}
</div>
{% for k, txt in o.mensajes.items() %}<p class="oculto" id="msg-{{ o.id }}-{{ k }}">{{ txt }}</p>{% endfor %}{% if o.mensajes %}<span class="suave chico" aria-live="polite" data-copiado="{{ o.id }}"></span>{% endif %}
</div></div>
{% for b in o.banderas %}<p class="aviso">{{ b }}</p>{% endfor %}
{% if o.esc %}{% for k, v in o.esc.items() %}<div class="esc" data-c="{{ k }}" style="display:flex;flex-direction:column;gap:14px">
{% set hsub = 'h2' if titulo_h == 'h1' else 'h3' %}
<div class="seccion-cab"><{{ hsub }}>De dónde sale el neto</{{ hsub }}><span class="suave pequeno">Comprando al precio pedido, {{ o.listing.precio_usd|usd }} · TRM {{ o.trm|trm }}</span></div>
{{ guia(o, v) }}
<div class="tres">
<div class="cifra"><span class="k">Publica en</span><span class="v" style="font-size:18px">{{ o.venta.lista_cop|cop }}</span><span class="s">{{ (o.venta.lista_cop / o.trm)|usd }}</span></div>
<div class="cifra"><span class="k">Cierre esperado</span><span class="v" style="font-size:18px">{{ o.venta.objetivo_cop|cop }}</span><span class="s">{{ (o.venta.objetivo_cop / o.trm)|usd }} · {{ 'estimada' if o.confianza_co == 'baja' else o.origen_co }}</span></div>
<div class="cifra"><span class="k">Piso ({{ p.margen_objetivo|pct }} neto)</span><span class="v" style="font-size:18px">{{ v.piso_cop|cop }}</span><span class="s">{{ v.piso_usd|usd }}</span></div>
</div>

<p class="nota">{% if v.hay_oferta %}Si el vendedor acepta {{ v.apertura|usd }}: {{ v.neto_apertura_cop|scop }} · {{ v.neto_apertura_usd|susd }} ({{ v.margen_apertura|spct }}). {% if v.techo >= o.listing.precio_usd %}El techo ({{ v.techo|usd }}) está por encima de lo que piden: aun pagando el precio pedido queda más del {{ p.margen_objetivo|pct }}.{% else %}Pagando el techo de {{ v.techo|usd }}: {{ v.neto_techo_cop|scop }} · {{ v.neto_techo_usd|susd }} ({{ p.margen_objetivo|pct }}).{% endif %}{% else %}Con esta comisión no hay una oferta razonable que deje el {{ p.margen_objetivo|pct }}: el techo queda por debajo del 60&nbsp;% del precio pedido.{% endif %}{% if o.confianza_co == 'baja' %} La referencia de Colombia es estimada: confírmala con tu vendedor antes de ofertar.{% endif %}</p>
</div>{% endfor %}
{% else %}<p class="aviso">{% if not o.valoracion_us %}Hay menos de 3 publicaciones del mismo modelo en EE. UU.: no hay mediana para valorarla ni oferta sugerida. Puesta en Bogotá al precio pedido costaría {{ o.costo.total_cop|cop }} · {{ o.costo.total_usd|usd }}.{% else %}Sin cuenta de compra y venta para esta publicación.{% endif %}</p>{% endif %}
</section>
{%- endmacro %}

{# Fila de Explorar #}
{% macro fila(o, e) -%}
<tr data-cat="{{ o.categoria }}" data-clase="{{ o.clase }}" data-marca="{{ o.normalizado.marca }}" data-plat="{{ o.listing.plataforma }}" data-estado="{{ o.estado }}" data-texto="{{ (o.normalizado.marca ~ ' ' ~ o.normalizado.modelo ~ ' ' ~ o.listing.titulo)|lower }}"
 data-precio="{{ o.listing.precio_usd }}" data-desc="{{ o.descuento_us if o.descuento_us is not none else -9 }}" data-orden="{{ o.orden }}" data-pri="{{ 1 if o.prioritario else 0 }}"{% for k, v in o.esc.items() %} data-neto{{ k }}="{{ v.neto_pedido_cop|round|int }}"{% endfor %}>
<td><a class="t" href="{{ e('detalle', o.id) }}" data-con-com>{{ o.normalizado.marca }} {{ o.normalizado.modelo }}</a><small>{{ o.listing.titulo[:64] }} · <a href="{{ o.listing.url }}" target="_blank" rel="noopener">{{ o.listing.plataforma|plataforma }}</a></small></td>
<td>{{ chips(o) }}</td>
<td class="n">{{ o.listing.precio_usd|usd }}<small>≈ {{ (o.listing.precio_usd * o.trm)|millones }}</small></td>
<td class="n">{% if o.valoracion_us %}{{ o.valoracion_us.mediana_usd|usd }}<small>{{ o.valoracion_us.n }} refs · {% if o.descuento_us >= 0 %}pide {{ o.descuento_us|pct }} menos{% else %}pide {{ (-o.descuento_us)|pct }} más{% endif %}</small>{% else %}<span class="suave">—</span><small>menos de 3 refs</small>{% endif %}</td>
<td class="n">{% if o.precio_co_cop is defined %}{{ o.precio_co_cop|cop }}<small>{{ (o.precio_co_cop / o.trm)|usd }} · {{ 'estimada' if o.confianza_co == 'baja' else 'tiendas' }}</small>{% else %}<span class="suave">—</span>{% endif %}</td>
<td class="n">{% if o.esc %}{% for k, v in o.esc.items() %}<span class="esc" data-c="{{ k }}">{% if v.apertura %}{{ v.apertura|usd }} → {{ v.techo|usd }}{% else %}<span class="suave">—</span>{% endif %}</span>{% endfor %}{% else %}<span class="suave">—</span>{% endif %}</td>
<td class="n">{% if o.esc %}{% for k, v in o.esc.items() %}<span class="esc" data-c="{{ k }}"><span class="{{ 'pos' if v.neto_pedido_cop >= 0 else 'neg' }}" style="font-weight:600">{{ v.neto_pedido_cop|scop }}</span><small>{{ v.neto_pedido_usd|susd }} · {{ v.margen_pedido|spct }}</small></span>{% endfor %}{% else %}<span class="suave">—</span>{% endif %}</td>
</tr>
{%- endmacro %}

{% macro cabecera_tabla(ordenable=False) -%}
<tr>
<th>Publicación</th><th>Veredicto</th>
<th class="n">{% if ordenable %}<button type="button" data-orden="precio">Pide</button>{% else %}Pide{% endif %}<small>USD · ≈ COP</small></th>
<th class="n">{% if ordenable %}<button type="button" data-orden="desc">EE. UU. usado</button>{% else %}EE. UU. usado{% endif %}<small>mediana ajustada</small></th>
<th class="n">Colombia<small>cierre esperado</small></th>
<th class="n">Oferta<small>abre → techo</small></th>
<th class="n">{% if ordenable %}<button type="button" data-orden="neto">Neto al precio pedido</button>{% else %}Neto al precio pedido{% endif %}<small>COP · USD · margen</small></th>
</tr>
{%- endmacro %}


{# Una publicación «En interés»: estado del anuncio, precio y neto por comisión #}
{% macro fila_interes(x, e) -%}
{% set o = x.o %}
<div class="seguida">
<div class="nom">
<b>{% if o %}<a class="t" href="{{ e('detalle', o.id) }}" data-con-com>{{ x.marca }} {{ x.modelo }}</a>{% else %}{{ x.marca }} {{ x.modelo }}{% endif %}</b>
<span class="suave pequeno">{{ x.titulo[:70] }}</span>
<span class="chips"><span class="chip {{ 'interes' if x.activa else 'sinmargen' }}">{{ x.etiqueta }}</span><span class="chip">Sigues desde {{ x.en_interes.desde|fecha }}</span>{% if x.revisada %}<span class="chip">Revisada {{ x.revisada|fecha }}</span>{% endif %}</span>
{% if x.en_interes.nota %}<span class="suave chico">{{ x.en_interes.nota }}</span>{% endif %}
</div>
<div class="cifra" style="align-items:flex-end;text-align:right"><span class="k">Pide</span><span class="v" style="font-size:18px">{{ x.precio_usd|usd }}</span>
<span class="s">{% if x.cambio_usd < -0.5 %}<span class="pos">bajó {{ (-x.cambio_usd)|usd }}</span>{% elif x.cambio_usd > 0.5 %}<span class="neg">subió {{ x.cambio_usd|usd }}</span>{% else %}sin cambios{% endif %}{% if trm %} · ≈ {{ (x.precio_usd * trm)|millones }}{% endif %}</span></div>
<div class="cifra" style="align-items:flex-end;text-align:right"><span class="k">Neto al precio pedido</span>
{% if o and o.esc %}{% for k, v in o.esc.items() %}<span class="esc dinero" data-c="{{ k }}"><span class="v {{ 'pos' if v.neto_pedido_cop >= 0 else 'neg' }}" style="font-size:18px">{{ v.neto_pedido_cop|scop }}</span><span class="usd">{{ v.neto_pedido_usd|susd }} · {{ v.margen_pedido|spct }}</span></span>{% endfor %}
{% else %}<span class="v suave" style="font-size:18px">—</span><span class="s">{{ 'ya no se evalúa' if not x.activa else 'sin cuenta' }}</span>{% endif %}</div>
<div class="botones" style="justify-content:flex-end"><a class="boton" href="{{ x.url }}" target="_blank" rel="noopener">Ver en Reverb</a>{% if repo %}<a class="boton" href="{{ url_quitar(repo, x.id) }}" target="_blank" rel="noopener">Quitar</a>{% endif %}</div>
</div>
{%- endmacro %}
```
- [ ] **Paso 4.** Pon el espacio duro antes del % en el texto visible de las plantillas. En cada archivo, cambia **solo** estas ocurrencias:
  - `hoy.html` (2):
    - en el párrafo de la pregunta, `con comisión del {{ k }} %` → `con comisión del {{ k }}&nbsp;%`;
    - en el botón del selector, `{{ k }} %</button>` → `{{ k }}&nbsp;%</button>`.
  - `detalle.html` (2):
    - en el botón del selector, `{{ k }} %</button>` → `{{ k }}&nbsp;%</button>`;
    - en «Mismo modelo en EE. UU.», `(−10 % por negociación)` → `(−10&nbsp;% por negociación)`.
  - `explorar.html` (1): la misma del botón del selector.
  - `estado.html` (1): `{{ k }} %{{ ', ' if not loop.last }}` → `{{ k }}&nbsp;%{{ ', ' if not loop.last }}`.
  - `parametros.html` (1): `0.25 es 25 %.` → `0.25 es 25&nbsp;%.`

  **Cuidado:** no toques `%}` (son etiquetas de Jinja) ni el `' %'` del JavaScript.
- [ ] **Paso 5.** Corre `pytest -q`.
**Esperado:** `152 passed`.
- [ ] **Paso 6.** Haz el commit:
```bash
git add radar/web/templates tests/test_web.py
git commit -m "feat: guía de embarque y cinta gaffer en el estuche; manifiesto con miniaturas"
```

---

### Tarea 5 · Verificación en el navegador

- [ ] **Paso 1.** Arma el sitio rápido, sin consultar tiendas de Colombia; usa estimaciones:
```bash
python3 -m radar sitio --salida _site --sin-colombia
python3 -m http.server 8000 -d _site
```
**Esperado:** termina sin errores y abre http://localhost:8000.
- [ ] **Paso 2.** Revisa **Hoy** a 1440 px (ventana completa):
  - el manifiesto a la izquierda, con miniaturas;
  - a la derecha, el estuche con esquineras, la cinta «TECHO … · ABRE …» y la guía con MIA - - - BOG;
  - los tramos en el orden 1 a 5;
  - la fila «Costo puesto en Bogotá» con fondo claro y la fila «Neto» oscura, con la cifra en naranja.
- [ ] **Paso 3.** Cambia la comisión a 0, 5 y 10 %.
**Esperado:**
  - con 0 % desaparece la fila «Comisión del vendedor»;
  - el neto de la guía coincide con el de la fila de la lista;
  - el orden de la lista cambia.
- [ ] **Paso 4.** Abre las herramientas de desarrollo y ajusta el ancho a 390 px (iPhone).
**Esperado:**
  - al tocar una fila, la guía se abre en la hoja de abajo;
  - en cada concepto, la base va debajo, en gris pequeño;
  - el neto se lee en dos líneas: pesos arriba y dólares abajo;
  - no hay desplazamiento horizontal (`document.documentElement.scrollWidth` en la consola debe dar `390`).
- [ ] **Paso 5.** Repite a 768 px.
**Esperado:** sin desbordes.
- [ ] **Paso 6.** Comprueba que las cifras son tabulares. En la consola del navegador, pega:
```js
(() => { const s = document.createElement('span'); s.style.cssText = 'font:16px "Schibsted Grotesk";font-variant-numeric:tabular-nums;position:absolute'; document.body.append(s); s.textContent = '1111'; const a = s.offsetWidth; s.textContent = '8888'; const b = s.offsetWidth; s.remove(); return a === b; })()
```
**Esperado:** `true`. Si da `false`, en el link de Google Fonts cambia `family=Schibsted+Grotesk:wght@400..800` por `family=Public+Sans:wght@400..800`, y en el CSS, `"Schibsted Grotesk"` por `"Public Sans"`. Avisa en el commit.
- [ ] **Paso 7.** Abre un **detalle** (por ejemplo, haz clic en «Ver cuentas y comparables»).
**Esperado:**
  - el modelo va en h1 y «De dónde sale el neto» en h2, sin saltos de nivel;
  - «Con tus números» sigue recalculando al cambiar el flete.
- [ ] **Paso 8.** Si `npx` está disponible, corre la revisión anti-slop (es opcional y solo informa):
```bash
npx impeccable@4.10.0 detect _site/index.html
```
- [ ] **Paso 9.** Sube la rama:
```bash
git push -u origin diseno-b
```
Después, Steve revisa las capturas y une la rama a `main`; el sitio se publica solo.

## Qué queda fuera de este plan
- Rediseñar la tabla de Explorar más allá de los colores (hereda la paleta).
- La pared con fotos de la dirección A.
- Cambios en la cuenta, en los textos de los avisos o en «Con tus números».
