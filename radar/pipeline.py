"""Corrida diaria: recolectar → normalizar → valorar (EE. UU. y Colombia) → costear → puntuar → avisar."""
from __future__ import annotations

import json
from dataclasses import asdict
from datetime import date

from . import db
from .collectors.base import LectorBloqueado
from .costing import costo_puesto, flete_maximo, ingreso_neto, margen
from .models import ESTADOS_ACEPTADOS, Listing
from .offer import precio_techo, proponer
from .scoring import puntaje, puntaje_ganga
from .valuation import precio_reventa_co, referencia_co, referencia_us

PRECIO_MIN_PREFILTRO = {"guitarra": 150, "bajo": 150, "pedal": 15, "cuerdas": 5}


def _marcar(con, lid: int, proceso: str) -> None:
    con.execute("update listings set proceso=? where id=?", (proceso, lid))
    con.commit()


def _recolectar(con, lectores: dict, p: dict, hoy: date, notificador) -> tuple[list[tuple[int, Listing, str]], int, int]:
    pendientes, total, errores = [], 0, 0
    conteo = {n: 0 for n in lectores}
    bloqueados: set[str] = set()
    for w in con.execute("select categoria, consulta from watchlist where activo=1").fetchall():
        for nombre, lector in lectores.items():
            if nombre in bloqueados:
                continue
            try:
                lote = lector(w["consulta"])
            except LectorBloqueado as e:
                bloqueados.add(nombre)
                errores += 1
                db.evento(con, "lector_bloqueado", f"{nombre}: {e}")
                notificador.aviso(f"lector_bloqueado: {nombre} — revisa la sesión o espera a mañana")
                continue
            except Exception as e:
                errores += 1
                db.evento(con, "lector_error", f"{nombre} ({w['consulta']}): {type(e).__name__}: {e}")
                continue
            conteo[nombre] += len(lote)
            for l in lote:
                maximo = p["precio_nuevo_max_usd"] if w["categoria"] in ("guitarra", "bajo") else 10_000
                if not l.hace_envios or not (PRECIO_MIN_PREFILTRO[w["categoria"]] <= l.precio_usd <= maximo):
                    continue
                total += 1
                lid, cambio = db.guardar_listing(con, l, hoy)
                if cambio:
                    pendientes.append((lid, l, w["categoria"]))
    for nombre, n in conteo.items():
        if n == 0 and nombre not in bloqueados:
            db.evento(con, "lector_sin_resultados", nombre)
            notificador.aviso(f"lector_sin_resultados: {nombre} — puede haber cambiado el diseño del sitio")
    return pendientes, total, errores


def _evaluar(con, lid: int, l: Listing, modelo, fuentes_us: dict, fuentes_co: dict, trm: float, p: dict,
             hoy: date) -> str:
    n = modelo.normalizar(l.titulo, l.descripcion)
    if n is None:
        return "sin_normalizar"
    con.execute("insert or replace into normalizados(listing_id, datos) values(?,?)", (lid, json.dumps(asdict(n))))
    if n.estado not in ESTADOS_ACEPTADOS:
        return "descartado_estado"
    val, comps_us = referencia_us(con, fuentes_us, modelo, n, hoy)
    if val is None:
        return "sin_valoracion_us"
    if n.categoria in ("guitarra", "bajo") and val.nuevo_usd is not None and not (
            p["precio_nuevo_min_usd"] <= val.nuevo_usd <= p["precio_nuevo_max_usd"]):
        return "fuera_de_rango"
    ref, comps_co = referencia_co(con, fuentes_co, modelo, n, hoy)

    senales = list(n.senales_motivado) + (["rebajado"] if db.rebajas(con, lid) else [])
    dias = (hoy - l.fecha_publicacion).days if l.fecha_publicacion else None
    costo = costo_puesto(l.precio_usd, l.envio_us_usd, trm, p)
    descuento_us = 1 - l.precio_usd / val.mediana_usd
    flete_sup_cop = p["flete_supuesto_usd"].get(n.categoria, 0) * trm
    reventa = precio_reventa_co(ref, p)

    tipo = oferta = None
    datos: dict = {}
    if reventa is not None:
        precio_co, n_co, origen = reventa
        ingreso = ingreso_neto(precio_co, p)
        techo = precio_techo(precio_co, l.envio_us_usd, n.categoria, trm, p)
        oferta = proponer(l.precio_usd, techo, val)
        if oferta is not None:
            costo_retiro = costo_puesto(oferta.retiro_usd, l.envio_us_usd, trm, p)
            m = margen(ingreso, costo_retiro.total_cop, flete_sup_cop)
            if m >= p["margen_objetivo"] - 1e-9:
                tipo = "reventa"
                punt = puntaje(m, val.n, n_co, ref.manual, senales, dias)
                datos.update(precio_co_cop=precio_co, origen_co=origen, margen_en_retiro=m,
                             margen_al_pedido=margen(ingreso, costo.total_cop, flete_sup_cop),
                             flete_maximo_cop=flete_maximo(ingreso, costo_retiro.total_cop, p))
    else:
        # No está en Colombia: no se descarta. Si está muy por debajo del mercado de EE. UU., es una ganga.
        if descuento_us >= p["ganga_descuento_min"]:
            oferta = proponer(l.precio_usd, None, val)
            if oferta is not None:
                tipo = "ganga"
                punt = puntaje_ganga(descuento_us, val.n, senales, dias)
    if tipo is None:
        return "sin_margen"

    banderas = []
    if l.precio_usd < p["sospecha_bajo"] * val.mediana_usd:
        banderas.append("Precio inusualmente bajo: verifica autenticidad y vendedor antes de pagar")
    if tipo == "reventa" and datos.get("origen_co") == "estimado desde el nuevo":
        banderas.append("Sin usados comparables en Colombia: precio de reventa estimado desde el nuevo de tienda")
    datos.update(
        listing=asdict(l) | {"fecha_publicacion": l.fecha_publicacion.isoformat() if l.fecha_publicacion else None},
        normalizado=asdict(n), valoracion_us=asdict(val), referencia_co=asdict(ref) | {"fecha": ref.fecha.isoformat()},
        costo=asdict(costo), oferta=asdict(oferta), descuento_us=descuento_us, senales=senales, dias_publicado=dias,
        banderas=banderas, comps_us=comps_us, comps_co=comps_co, trm=trm, flete_supuesto_cop=flete_sup_cop)
    con.execute(
        "insert into oportunidades(listing_id, tipo, puntaje, datos, creada) values(?,?,?,?,?) "
        "on conflict(listing_id) do update set tipo=excluded.tipo, puntaje=excluded.puntaje, datos=excluded.datos, "
        "alertada=0", (lid, tipo, punt, json.dumps(datos), hoy.isoformat()))
    con.commit()
    return "oportunidad"


def _alertar(con, modelo, notificador, p: dict) -> int:
    from .models import Listing as L, Normalizado, Oferta, ValoracionUS

    filas = con.execute("select id, datos, tipo, puntaje from oportunidades where alertada=0 and estado='nueva' "
                        "and puntaje > 0 order by puntaje desc limit ?", (int(p["max_alertas_dia"]),)).fetchall()
    enviadas = 0
    for f in filas:
        d = json.loads(f["datos"])
        if "mensaje" not in d:
            ld = dict(d["listing"])
            ld["fecha_publicacion"] = date.fromisoformat(ld["fecha_publicacion"]) if ld["fecha_publicacion"] else None
            d["mensaje"] = modelo.mensaje_oferta(L(**ld), Normalizado(**d["normalizado"]), Oferta(**d["oferta"]),
                                                 ValoracionUS(**d["valoracion_us"]))
        notificador.alerta({"id": f["id"], "tipo": f["tipo"], "puntaje": f["puntaje"], **d})
        con.execute("update oportunidades set alertada=1, datos=? where id=?", (json.dumps(d), f["id"]))
        con.commit()
        enviadas += 1
    return enviadas


def correr(con, lectores: dict, fuentes_us: dict, fuentes_co: dict, modelo, notificador, trm: float,
           hoy: date) -> dict:
    """lectores: nombre -> callable(consulta) -> list[Listing]."""
    p = db.parametros(con)
    pendientes, total, errores = _recolectar(con, lectores, p, hoy, notificador)
    estados: dict[str, int] = {}
    for lid, l, _cat in pendientes[: int(p["max_normalizar_dia"])]:
        try:
            r = _evaluar(con, lid, l, modelo, fuentes_us, fuentes_co, trm, p, hoy)
        except Exception as e:
            errores += 1
            r = "error"
            db.evento(con, "error_evaluacion", f"{l.plataforma}:{l.id_externo}: {type(e).__name__}: {e}")
        _marcar(con, lid, r)
        estados[r] = estados.get(r, 0) + 1
    alertas = _alertar(con, modelo, notificador, p)
    resumen = {"listings": total, "nuevos_o_rebajados": len(pendientes), "oportunidades": estados.get("oportunidad", 0),
               "alertas": alertas, "errores": errores, "detalle": estados}
    db.evento(con, "corrida", json.dumps(resumen))
    return resumen
