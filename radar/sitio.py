"""Sitio estático para GitHub Pages: evalúa las capturas del repositorio y escribe HTML en una carpeta.

No necesita el modelo de NIM ni sesiones: todo sale de datos/ (capturas, parámetros y referencias propias).
"""
from __future__ import annotations

import json
import shutil
from datetime import date
from pathlib import Path

from . import db, vistas
from .capturas import importar
from .models import ESTADOS_OPORTUNIDAD
from .valuation import actualizar_colombia, fijar_referencia_manual

RAIZ = Path(__file__).resolve().parents[1]
DATOS = RAIZ / "datos"


def _leer_json(ruta: Path, defecto):
    try:
        return json.loads(ruta.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return defecto


def preparar(con, datos: Path, hoy: date, trm: float | None = None, colombia=None, log=lambda m: None) -> float:
    """Aplica parámetros y referencias del repositorio, evalúa las capturas y consulta Colombia.

    colombia: dict nombre -> callable(consulta) con las tiendas, o None para no consultarlas.
    """
    from .trm import trm_del_dia

    params = _leer_json(datos / "parametros.json", {})
    for k, v in params.items():
        if not k.startswith("_") and k in db.PARAMETROS_DEFECTO:
            db.set_parametro(con, k, v)
    for r in _leer_json(datos / "referencias_co.json", []):
        try:
            if float(r["usado_cop"]) > 0:
                fijar_referencia_manual(con, str(r["marca"]).strip(), str(r["modelo"]).strip(), float(r["usado_cop"]), hoy)
        except (KeyError, TypeError, ValueError):
            log(f"Referencia ignorada: {r!r}")
    if trm is None:
        trm = trm_del_dia(con, hoy)
    capturas = datos / "capturas"
    importar(con, capturas, trm, hoy, forzar=True)
    if colombia:
        log("Consultando tiendas de Colombia...")
        log(json.dumps(actualizar_colombia(con, colombia, hoy, log=log), ensure_ascii=False))
        importar(con, capturas, trm, hoy, forzar=True)
    return trm


def escribir(con, salida: Path, datos: Path, repo: str = "") -> int:
    """Escribe index.html, explorar.html, estado.html y una página por publicación. Devuelve cuántas páginas."""
    if salida.exists():
        shutil.rmtree(salida)
    salida.mkdir(parents=True)
    if repo:
        db.set_parametro(con, "repo_github", repo)
    env = vistas.entorno()
    ops = vistas.cargar_ops(con)
    p = db.parametros(con)

    def pagina(nombre: str, plantilla: str, activa: str, **ctx) -> None:
        html = env.get_template(plantilla).render(vistas.contexto(con, "estatico", activa, **ctx))
        (salida / nombre).write_text(html, encoding="utf-8")

    dest = vistas.destacadas(ops)
    ids = {o["id"] for o in dest}
    resto = [o for o in ops if o["id"] not in ids and o["estado"] != "descartada"][:10]
    pagina("index.html", "hoy.html", "hoy", resumen=vistas.resumen(ops), destacadas=dest, resto=resto,
           total=len(ops), categorias=vistas.por_categoria(ops))
    pagina("explorar.html", "explorar.html", "explorar", ops=ops, categorias=vistas.por_categoria(ops),
           marcas=sorted({o["normalizado"]["marca"] for o in ops}),
           plataformas=sorted({o["listing"]["plataforma"] for o in ops}), estados=ESTADOS_OPORTUNIDAD)
    pagina("estado.html", "estado.html", "estado", activa_corrida=False, registro="", avance=None, nim=False,
           problemas=[], capturas=vistas.capturas_info(datos / "capturas"), colombia=vistas.colombia_info(con),
           tiendas=[t["nombre"] for t in p["tiendas_co"]], p=p)
    for o in ops:
        dg = o["desglose"]
        pagina(f"o-{o['id']}.html", "detalle.html", "", o=o, dg=dg, c=vistas.cuentas(dg) if dg else None)
    (salida / ".nojekyll").write_text("")
    (salida / "robots.txt").write_text("User-agent: *\nDisallow: /\n")
    return len(ops) + 3


def vigilar(nombre: str, fuente, estado: dict):
    """Cuenta cómo responde cada tienda y deja de consultarla tras 3 errores sin ninguna respuesta buena."""
    from .collectors.base import LectorBloqueado

    st = estado.setdefault(nombre, {"con_resultados": 0, "sin_resultados": 0, "errores": 0, "ultimo_error": ""})

    def consultar(consulta):
        if st["errores"] >= 3 and st["con_resultados"] + st["sin_resultados"] == 0:
            raise LectorBloqueado(f"{nombre}: omitida tras 3 errores seguidos")
        try:
            r = fuente(consulta)
        except Exception as e:
            st["errores"] += 1
            st["ultimo_error"] = f"{type(e).__name__}: {e}"[:160]
            raise
        st["con_resultados" if r else "sin_resultados"] += 1
        return r
    consultar.__wrapped__ = fuente
    return consultar


def construir(salida: Path, datos: Path = DATOS, hoy: date | None = None, trm: float | None = None,
              colombia: bool = True, repo: str = "", log=lambda m: None) -> dict:
    hoy = hoy or date.today()
    con = db.conectar(":memory:")
    tiendas, estado_tiendas = None, {}
    if colombia:
        from .collectors import tiendas as t
        from .collectors.http import ClienteHttp

        import httpx

        from .collectors.http import AGENTE

        http = ClienteHttp(httpx.Client(timeout=10, follow_redirects=True, headers={"User-Agent": AGENTE}), pausa=1.0)
        lista = _leer_json(datos / "parametros.json", {}).get("tiendas_co") or db.PARAMETROS_DEFECTO["tiendas_co"]
        tiendas = {x["nombre"]: vigilar(x["nombre"], lambda c, x=x: t.buscar_tienda_co(http, x, c), estado_tiendas)
                   for x in lista}
    trm = preparar(con, datos, hoy, trm, tiendas, log)
    if estado_tiendas:
        db.evento(con, "colombia_tiendas", json.dumps(estado_tiendas, ensure_ascii=False))
        log("Tiendas: " + json.dumps(estado_tiendas, ensure_ascii=False))
    paginas = escribir(con, salida, datos, repo)
    ops = vistas.cargar_ops(con)
    r = vistas.resumen(ops) | {"paginas": paginas, "trm": trm,
                               "sin_foto": sum(1 for o in ops if not o["listing"].get("fotos"))}
    log(json.dumps(r, ensure_ascii=False))
    return r
