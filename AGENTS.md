# AGENTS.md · reglas del proyecto para agentes (OpenCode, Claude, etc.)

## Qué es
- Radar de guitarras, bajos, pedales y cuerdas usados en EE. UU.
- Calcula el costo puesto en Bogotá y propone una oferta y un precio de venta.
- Se publica como sitio estático en GitHub Pages y tiene un tablero local en FastAPI.
- Usa las mismas plantillas Jinja2 en los dos (`radar/web/templates/`).

## Antes de tocar nada
1. Lee `DESIGN.md` (diseño) y `PRODUCT.md` (producto). Si hay un plan en `docs/`, síguelo al pie de la letra.
2. Activa el entorno y corre las pruebas:
   - `source .venv/bin/activate`
   - `pytest -q`
   
   Todo debe quedar en verde antes y después de cada cambio.
3. En esta Mac, Python es `python3`.

## Reglas
- **Ramas y commits:**
  - trabaja en una rama, nunca directo en `main`;
  - un commit por tarea, con mensaje en español (`feat:`, `fix:`, `datos:`).
- **Pruebas:**
  - escribe primero la prueba que falla y luego el código;
  - no cambies una prueba para que pase, salvo que el plan lo diga.
- **La cuenta es sagrada:**
  - `radar/costing.py` y `radar/web/templates/_cuentas.js` deben dar lo mismo; hay una prueba de paridad;
  - no los cambies sin pedirlo.
- **No tocar:**
  - `datos/` (lo escribe la captura diaria);
  - `.github/workflows/` (publica el sitio y procesa los issues de «En interés»).
- **Atributos que usa el JavaScript; no los renombres:** `data-op`, `data-panel`, `data-estuche`, `data-copiar`, `data-elegir-com`, `data-con-com`, `.esc[data-c]`, `.panel`, `.velo`, `#cerrar` y los ids de «Con tus números».
- **Formato es-CO:**
  - `$1.234.000` y `US$1.250` (`US$1.250,00` en la guía);
  - `25&nbsp;%`;
  - fechas como `20 nov 2026, 6:54 a. m.`
- **Copy:** español de Colombia, en sentence case. Botones con verbo y objeto («Copiar oferta de US$1.402»).
- **Plataformas:** solo lectura. Nada de enviar ofertas ni mensajes, nada de cuentas múltiples ni de evadir bloqueos. Ante una verificación o un bloqueo, se detiene y se reporta.
- **Secretos:** solo en `~/.radar/.env`. Nunca en el repo.

## Ver el sitio en local
- **Rápido** (sin tiendas de Colombia):
  - `python3 -m radar sitio --salida _site --sin-colombia`
  - `python3 -m http.server 8000 -d _site`
- **Completo** (unos 20 minutos): quita `--sin-colombia`.
