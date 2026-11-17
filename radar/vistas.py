"""Datos listos para mostrar: los usan el tablero local y el sitio estático, con las mismas plantillas."""
from __future__ import annotations

import json
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from . import db
from .notify import cop, usd

PLANTILLAS = Path(__file__).parent / "web" / "templates"

CATEGORIAS = [("guitarra", "Guitarras"), ("bajo", "Bajos"), ("pedal", "Pedales"), ("cuerdas", "Cuerdas")]

# veredicto -> (clase visual, orden en las listas)
CLASES = {
    "Reventa con margen": ("reventa", 0),
    "Ganga (no está en Colombia)": ("ganga", 1),
    "Posible reventa (precio de Colombia estimado)": ("posible", 2),
    "Por debajo del mercado, sin llegar a ganga": ("bajo", 3),
    "A precio de mercado": ("mercado", 5),
    "Sin margen para Colombia": ("sinmargen", 5),
    "Por encima del mercado": ("encima", 6),
    "Sin comparables suficientes": ("sincomp", 7),
}
CORTOS = {"reventa": "Reventa", "ganga": "Ganga", "posible": "Posible reventa", "bajo": "Bajo el mercado",
          "mercado": "A precio de mercado", "sinmargen": "Sin margen", "encima": "Sobre el mercado",
          "sincomp": "Sin comparables"}

RUTAS_LOCAL = {"hoy": "/", "explorar": "/explorar", "estado": "/corrida", "detalle": "/oportunidad/{}",
               "seguimiento": "/watchlist", "parametros": "/parametros", "ajustes": "/ajustes", "eventos": "/eventos"}
RUTAS_ESTATICO = {"hoy": "index.html", "explorar": "explorar.html", "estado": "estado.html",
                  "detalle": "o-{}.html"}


def pct(x) -> str:
    return "—" if x is None else f"{x * 100:.0f} %"


def millones(x) -> str:
    return "—" if x is None else f"${x / 1e6:,.2f} M".replace(",", "X").replace(".", ",").replace("X", ".")


def entorno() -> Environment:
    env = Environment(loader=FileSystemLoader(str(PLANTILLAS)), autoescape=select_autoescape(["html"]))
    env.filters.update(cop=cop, usd=usd, pct=pct, millones=millones,
                       fecha=lambda s: "—" if not s else str(s)[:16].replace("T", " "))
    return env


def enlazador(modo: str):
    rutas = RUTAS_LOCAL if modo == "local" else RUTAS_ESTATICO

    def e(nombre: str, id_=None) -> str:
        r = rutas.get(nombre)
        if r is None:
            return ""
        return r.format(id_) if id_ is not None else r
    return e


def _desglose(d: dict, p: dict) -> dict | None:
    """Parámetros para que la página recalcule en el navegador (flete real, precio de referencia propio)."""
    v = d.get("venta")
    if not v or not d.get("valoracion_us"):
        return None
    l = d["listing"]
    trm = d["trm"]
    base_k = (1 + p["sales_tax_us"]) * trm * (1 + p["margen_cambiario"])
    return {
        "compra": d["compra_supuesta_usd"], "envio": l["envio_us_usd"], "pedido": l["precio_usd"], "trm": trm,
        "base_k": base_k, "arancel": p["arancel"], "iva": p["iva"], "flete": d.get("flete_supuesto_cop", 0),
        "mo": p["margen_objetivo"], "comision": p["comision_canal"], "regateo": p["regateo_co"],
        "ref": d["precio_co_cop"], "mediana": d["valoracion_us"]["mediana_usd"],
        "apertura_sobre_retiro": 0.85, "apertura_sobre_pedido": 0.90,
    }


def mensaje(d: dict) -> str | None:
    if d.get("mensaje"):
        return d["mensaje"]
    o, v, n = d.get("oferta"), d.get("valoracion_us"), d["normalizado"]
    if not o or not v:
        return None
    return (f"Hi! I'm interested in your {n['marca']} {n['modelo']}. Similar used ones are listed around "
            f"${v['p25_usd']:,.0f}-${v['p75_usd']:,.0f}. Would you accept ${o['apertura_usd']:,.0f}? "
            "I can pay right away. Thanks!")


def cargar_ops(con) -> list[dict]:
    p = db.parametros(con)
    ops = []
    for f in con.execute("select o.*, l.plataforma from oportunidades o join listings l on l.id = o.listing_id"):
        d = json.loads(f["datos"])
        ver = d.get("veredicto") or ("Reventa con margen" if f["tipo"] == "reventa" else
                                     "Ganga (no está en Colombia)" if f["tipo"] == "ganga" else "A precio de mercado")
        clase, orden = CLASES.get(ver, ("mercado", 5))
        o = {"id": f["id"], "tipo": f["tipo"], "puntaje": f["puntaje"], "estado": f["estado"],
             "flete_real_cop": f["flete_real_cop"], **d, "veredicto": ver, "clase": clase, "corto": CORTOS[clase],
             "orden": orden, "categoria": d["normalizado"]["categoria"]}
        o["destacable"] = clase in ("reventa", "ganga", "posible", "bajo") or bool(o.get("prioritario"))
        o["desglose"] = _desglose(d, p)
        o["texto_mensaje"] = mensaje(d)
        ops.append(o)
    ops.sort(key=lambda o: (o["orden"], -o["puntaje"], -bool(o.get("prioritario")),
                            o.get("descuento_us") is None, -(o.get("descuento_us") or 0)))
    return ops


def resumen(ops: list[dict]) -> dict:
    vivas = [o for o in ops if o["estado"] != "descartada"]
    cuenta = lambda c: sum(o["clase"] == c for o in vivas)
    return {"reventa": cuenta("reventa"), "ganga": cuenta("ganga"), "posible": cuenta("posible"),
            "bajo": cuenta("bajo"), "prioritarias": sum(bool(o.get("prioritario")) for o in vivas),
            "evaluadas": len(vivas)}


def destacadas(ops: list[dict], n: int = 6) -> list[dict]:
    return [o for o in ops if o["destacable"] and o["estado"] != "descartada"][:n]


def por_categoria(ops: list[dict]) -> list[tuple[str, str, int]]:
    return [(c, nombre, sum(o["categoria"] == c for o in ops)) for c, nombre in CATEGORIAS]


def ultima_actualizacion(con) -> dict | None:
    f = con.execute("select id, fecha, tipo, detalle from eventos where tipo in ('corrida', 'importacion') "
                    "order by id desc limit 1").fetchone()
    if not f:
        return None
    try:
        d = json.loads(f["detalle"])
    except ValueError:
        d = {}
    return {"id": f["id"], "fecha": f["fecha"], "origen": f["tipo"], **d}


def colombia_info(con) -> dict | None:
    f = con.execute("select fecha, detalle from eventos where tipo = 'colombia' order by id desc limit 1").fetchone()
    if not f:
        return None
    try:
        return {"fecha": f["fecha"], **json.loads(f["detalle"])}
    except ValueError:
        return None


def capturas_info(carpeta: Path) -> list[dict]:
    salida = []
    for a in sorted(carpeta.glob("*.json"), reverse=True):
        try:
            d = json.loads(a.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            salida.append({"archivo": a.name, "error": True})
            continue
        salida.append({"archivo": a.name, "fuente": d.get("fuente", ""), "consulta": d.get("consulta", ""),
                       "capturado": d.get("capturado", ""), "n": len(d.get("publicaciones", [])),
                       "nota": d.get("nota", "")})
    return salida


def contexto(con, modo: str, activa: str, **extra) -> dict:
    p = db.parametros(con)
    ult = ultima_actualizacion(con)
    trm = (p.get("trm_cache") or {}).get("valor") or p.get("trm_manual")
    return {"modo": modo, "e": enlazador(modo), "activa": activa, "ultima": ult, "trm": trm,
            "repo": p.get("repo_github", ""), **extra}


def cuentas(dg: dict, flete: float | None = None, ref: float | None = None) -> dict:
    """La misma cuenta que hace el navegador al cambiar el flete o el precio de referencia (ver detalle.html)."""
    flete = dg["flete"] if flete is None else flete
    ref = dg["ref"] if ref is None else ref
    ingreso = ref * (1 - dg["comision"])
    k = dg["base_k"] * (1 + dg["arancel"]) * (1 + dg["iva"])
    techo = (ingreso / (1 + dg["mo"]) - flete) / k - dg["envio"]
    retiro = min(techo, dg["mediana"], dg["pedido"])
    hay_oferta = retiro > 0 and retiro >= 0.6 * dg["pedido"]
    compra = retiro if hay_oferta else dg["pedido"]
    apertura = min(dg["apertura_sobre_retiro"] * retiro, dg["apertura_sobre_pedido"] * dg["pedido"]) if hay_oferta else None
    base = (compra + dg["envio"]) * dg["base_k"]
    arancel = base * dg["arancel"]
    iva = (base + arancel) * dg["iva"]
    total = base + arancel + iva + flete
    return {"techo": techo, "retiro": retiro if hay_oferta else None, "apertura": apertura, "compra": compra,
            "precio": base, "arancel": arancel, "iva": iva, "flete": flete, "total": total, "ingreso": ingreso,
            "margen": ingreso / total - 1, "ganancia": ingreso - total, "lista": ref / (1 - dg["regateo"]),
            "objetivo": ref, "piso": total * (1 + dg["mo"]), "flete_max": ingreso / (1 + dg["mo"]) - (base + arancel + iva)}
