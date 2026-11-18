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


def cop_redondo(x) -> str:
    """Pesos redondeados a miles: los precios estimados no tienen precisión de pesos sueltos."""
    return cop(None if x is None else round(x, -3))


def usd_es(x) -> str:
    """Dólares con separador de miles colombiano: US$1.250."""
    return "—" if x is None else ("−" if x < 0 else "") + "US$" + f"{round(abs(x)):,}".replace(",", ".")


def pct1(x) -> str:
    return "—" if x is None else f"{x * 100:.1f} %".replace(".", ",").replace(",0 %", " %")


def pct(x) -> str:
    return "—" if x is None else f"{x * 100:.0f} %"


def millones(x) -> str:
    return "—" if x is None else f"${x / 1e6:,.2f} M".replace(",", "X").replace(".", ",").replace("X", ".")


def entorno() -> Environment:
    env = Environment(loader=FileSystemLoader(str(PLANTILLAS)), autoescape=select_autoescape(["html"]))
    env.filters.update(plataforma=lambda x: {"ebay": "eBay", "reverb": "Reverb", "facebook": "Facebook", "gc": "Guitar Center"}.get(str(x).lower(), str(x).capitalize()),
                       cop=cop_redondo, usd=usd_es, pct=pct, millones=millones, pct1=pct1, trm=lambda x: f"{x:,.1f}".replace(",", "X").replace(".", ",").replace("X", "."),
                       scop=lambda x: "—" if x is None else ("−" if x < 0 else "+") + cop_redondo(abs(x)),
                       susd=lambda x: "—" if x is None else ("−" if x < 0 else "+") + usd_es(abs(x)),
                       usdes=lambda x: usd_es(x), spct=lambda x: "—" if x is None else ("−" if x < 0 else "+") + f"{abs(x) * 100:.0f} %",
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
    """Parámetros para que la página recalcule en el navegador (flete real, precio de venta, comisión)."""
    v = d.get("venta")
    if not v or not d.get("valoracion_us"):
        return None
    l = d["listing"]
    cat = d["normalizado"]["categoria"]
    aj = p.get("ajuste_luthier_cop", 150_000)
    return {
        "pedido": l["precio_usd"], "envio": l["envio_us_usd"], "categoria": cat, "trm": d["trm"],
        "sales_tax_us": p["sales_tax_us"], "margen_cambiario": p["margen_cambiario"],
        "seguro_pct": p.get("seguro_pct", 0.035), "seguro_min_usd": p.get("seguro_min_usd", 10),
        "inspeccion_usd": p.get("inspeccion_usd", 10), "arancel": p["arancel"], "iva": p["iva"],
        "ajuste_cop": (aj.get(cat, 0) if isinstance(aj, dict) else aj) or 0,
        "flete": d.get("flete_supuesto_usd", p["flete_supuesto_usd"].get(cat, 0)),
        "mo": p["margen_objetivo"], "comision": d.get("comision", p["comision_canal"]),
        "comisiones": sorted({round(float(k) / 100, 4) for k in (d.get("escenarios") or {})}) or [p["comision_canal"]],
        "regateo": p["regateo_co"], "rebaja_max": p["rebaja_maxima_esperada"],
        "ref": d["precio_co_cop"], "mediana": d["valoracion_us"]["mediana_usd"],
        "apertura_sobre_retiro": 0.85, "apertura_sobre_pedido": 0.90, "brecha": 0.60,
    }


def _p_de(dg: dict, flete: float) -> dict:
    return {"sales_tax_us": dg["sales_tax_us"], "margen_cambiario": dg["margen_cambiario"],
            "seguro_pct": dg["seguro_pct"], "seguro_min_usd": dg["seguro_min_usd"],
            "inspeccion_usd": dg["inspeccion_usd"], "arancel": dg["arancel"], "iva": dg["iva"],
            "ajuste_luthier_cop": dg["ajuste_cop"], "flete_supuesto_usd": {dg["categoria"]: flete},
            "margen_objetivo": dg["mo"], "comision_canal": dg["comision"]}


def cuentas(dg: dict, flete: float | None = None, ref: float | None = None, comision: float | None = None) -> dict:
    """La misma cuenta que hace el navegador (_cuentas.js): todo en USD y en COP."""
    from .costing import cuenta, flete_maximo, precio_techo, venta
    flete = dg["flete"] if flete is None else flete
    ref = dg["ref"] if ref is None else ref
    com = dg["comision"] if comision is None else comision
    p, cat, trm, env = _p_de(dg, flete), dg["categoria"], dg["trm"], dg["envio"]
    techo = precio_techo(ref, env, cat, trm, p, com)
    retiro = min(techo, dg["mediana"], dg["pedido"])
    hay_oferta = retiro > 0 and retiro >= dg["brecha"] * dg["pedido"]
    compra = retiro if hay_oferta else dg["pedido"]
    apertura = min(dg["apertura_sobre_retiro"] * retiro, dg["apertura_sobre_pedido"] * dg["pedido"]) if hay_oferta else None
    c = cuenta(compra, env, cat, trm, p)
    v = venta(ref, c, com, p)
    cp = cuenta(dg["pedido"], env, cat, trm, p)
    vp = venta(ref, cp, com, p)
    va = venta(ref, cuenta(apertura, env, cat, trm, p), com, p) if apertura else None
    lista = ref / (1 - dg["regateo"])
    piso = c.total_cop * (1 + dg["mo"]) / (1 - com)
    return {"techo": techo, "retiro": retiro if hay_oferta else None, "apertura": apertura, "compra": compra,
            "hay_oferta": hay_oferta, "comision": com, "flete": flete, "ref": ref,
            "lineas": [{"concepto": x.concepto, "usd": x.usd, "cop": x.cop} for x in c.lineas],
            "total_usd": c.total_usd, "total_cop": c.total_cop,
            "lineas_pedido": [{"concepto": x.concepto, "usd": x.usd, "cop": x.cop} for x in cp.lineas],
            "total_pedido_usd": cp.total_usd, "total_pedido_cop": cp.total_cop,
            "lista_cop": lista, "lista_usd": lista / trm, "objetivo_cop": ref, "objetivo_usd": ref / trm,
            "piso_cop": piso, "piso_usd": piso / trm, "comision_cop": v.comision_cop, "comision_usd": v.comision_usd,
            "neto_cop": v.neto_cop, "neto_usd": v.neto_usd, "margen": v.margen,
            "hay_margen": hay_oferta and v.margen >= dg["mo"] - 1e-9 and compra >= (1 - dg["rebaja_max"]) * dg["pedido"] - 1e-9,
            "neto_pedido_cop": vp.neto_cop, "neto_pedido_usd": vp.neto_usd, "margen_pedido": vp.margen,
            "neto_apertura_cop": va.neto_cop if va else None, "neto_apertura_usd": va.neto_usd if va else None,
            "margen_apertura": va.margen if va else None,
            "flete_max_usd": flete_maximo(ref, compra, env, cat, trm, p, com)}



def _pasos(lineas: list[dict], comision_cop: float, neto_cop: float, trm: float, com: float) -> list[dict]:
    """Cascada «a dónde va cada peso» al precio pedido: tramos con su posición en % del total."""
    grupos = [("Compra en EE. UU.", lineas[0:2], "costo"), ("Flete, seguro e inspección", lineas[2:4], "costo"),
              ("Arancel e IVA", lineas[4:6], "costo"), ("Ajuste del luthier", lineas[6:7], "costo")]
    tramos = [(n, sum(x["cop"] for x in ls), tipo) for n, ls, tipo in grupos if sum(x["cop"] for x in ls) > 0]
    if com > 0:
        tramos.append((f"Comisión {com * 100:.0f} %", comision_cop, "comision"))
    tramos.append(("Ganancia" if neto_cop >= 0 else "Pérdida", neto_cop, "ganancia" if neto_cop >= 0 else "perdida"))
    escala = max(sum(abs(v) for _, v, _ in tramos), 1)
    salida, acum = [], 0.0
    for n, v, tipo in tramos:
        ancho = abs(v) / escala * 100
        salida.append({"etiqueta": n, "cop": v, "usd": v / trm, "tipo": tipo, "izq": round(acum, 2), "ancho": round(max(ancho, 0.4), 2)})
        acum += ancho
    return salida


def escenarios_vista(d: dict) -> dict:
    """Cifras por comisión, en USD y COP, para la lista, el estuche y la tabla."""
    esc, cp, v = d.get("escenarios") or {}, d.get("costo_pedido"), d.get("venta")
    if not esc or not cp or not v:
        return {}
    trm, ref = d["trm"], d["precio_co_cop"]
    salida = {}
    for k, e in esc.items():
        com = e["comision"]
        comision_cop = ref * com
        o = e.get("oferta") or {}
        salida[k] = {
            "comision": com, "hay_margen": e["hay_margen"], "techo": e["techo_usd"], "hay_oferta": bool(o),
            "apertura": o.get("apertura_usd"), "neto_pedido_cop": e["neto_pedido_cop"], "neto_pedido_usd": e["neto_pedido_usd"],
            "margen_pedido": e["margen_pedido"], "neto_apertura_cop": e.get("neto_apertura_cop"),
            "neto_apertura_usd": e.get("neto_apertura_usd"), "margen_apertura": e.get("margen_apertura"),
            "neto_techo_cop": e["neto_cop"], "neto_techo_usd": e["neto_usd"], "compra": e["compra_usd"],
            "comision_cop": comision_cop, "comision_usd": comision_cop / trm, "piso_cop": e["piso_cop"],
            "piso_usd": e["piso_usd"], "flete_max_usd": e.get("flete_maximo_usd"),
            "pasos": _pasos(cp["lineas"], comision_cop, e["neto_pedido_cop"], trm, com),
        }
    return salida

def mensaje(d: dict, apertura: float | None = None) -> str | None:
    """Mensaje de oferta en inglés; apertura=None usa la oferta guardada (comisión por defecto)."""
    o, v, n = d.get("oferta"), d.get("valoracion_us"), d["normalizado"]
    if apertura is None:
        if d.get("mensaje"):
            return d["mensaje"]
        apertura = o["apertura_usd"] if o else None
    if not apertura or not v:
        return None
    return (f"Hi! I'm interested in your {n['marca']} {n['modelo']}. Similar used ones are listed around "
            f"${v['p25_usd']:,.0f}-${v['p75_usd']:,.0f}. Would you accept ${apertura:,.0f}? "
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
             "flete_real_usd": f["flete_real_usd"], **d, "veredicto": ver, "clase": clase, "corto": CORTOS[clase],
             "orden": orden, "categoria": d["normalizado"]["categoria"]}
        o["destacable"] = clase in ("reventa", "ganga", "posible", "bajo") or bool(o.get("prioritario"))
        o["desglose"] = _desglose(d, p)
        o["esc"] = escenarios_vista(d)
        o["com_def"] = str(round(d.get("comision", p["comision_canal"]) * 100))
        o["texto_mensaje"] = mensaje(d)
        o["mensajes"] = {k: mensaje(d, x["apertura"]) for k, x in o["esc"].items() if x["apertura"]}
        ops.append(o)
    ops.sort(key=lambda o: (o["orden"], -o["puntaje"], -bool(o.get("prioritario")),
                            o.get("descuento_us") is None, -(o.get("descuento_us") or 0)))
    return ops


def resumen(ops: list[dict]) -> dict:
    vivas = [o for o in ops if o["estado"] != "descartada"]
    cuenta = lambda c: sum(o["clase"] == c for o in vivas)
    return {"reventa": cuenta("reventa"), "ganga": cuenta("ganga"), "posible": cuenta("posible"),
            "bajo": sum((o.get("descuento_us") or 0) >= 0.10 for o in vivas), "prioritarias": sum(bool(o.get("prioritario")) for o in vivas),
            "evaluadas": len(vivas),
            "margen_por_com": {k: sum(bool((o.get("esc") or {}).get(k, {}).get("hay_margen")) for o in destacadas(ops))
                               for k in {k for o in vivas for k in (o.get("esc") or {})}}}


def destacadas(ops: list[dict], n: int = 12) -> list[dict]:
    """Las de mejor veredicto, ordenadas por el neto al precio pedido con la comisión por defecto."""
    sel = [o for o in ops if o["destacable"] and o["estado"] != "descartada"][:n]
    neto = lambda o: ((o.get("esc") or {}).get(o.get("com_def", "5")) or {}).get("neto_pedido_cop", float("-inf"))
    return sorted(sel, key=neto, reverse=True)


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
        info = {"fecha": f["fecha"], **json.loads(f["detalle"])}
    except ValueError:
        return None
    t = con.execute("select detalle from eventos where tipo = 'colombia_tiendas' order by id desc limit 1").fetchone()
    try:
        info["tiendas"] = json.loads(t["detalle"]) if t else {}
    except ValueError:
        info["tiendas"] = {}
    return info


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
    comisiones = sorted(set(p.get("comisiones_escenario") or []) | {p["comision_canal"]})
    return {"modo": modo, "e": enlazador(modo), "activa": activa, "ultima": ult, "trm": trm,
            "repo": p.get("repo_github", ""), "p": p, "comisiones": [str(round(c * 100)) for c in comisiones],
            "com_def": str(round(p["comision_canal"] * 100)), **extra}
