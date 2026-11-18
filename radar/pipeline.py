"""Corrida diaria: recolectar → normalizar → valorar (EE. UU. y Colombia) → costear → puntuar → avisar."""
from __future__ import annotations

import json
from dataclasses import asdict
from datetime import date

from . import db
from .collectors.base import LectorBloqueado
from .costing import cuenta, flete_maximo, precio_techo, venta
from .models import ESTADOS_ACEPTADOS, Listing
from .offer import proponer
from .scoring import puntaje, puntaje_ganga
from .valuation import estimar_co, precio_reventa_co, referencia_co, referencia_us

PRECIO_MIN_PREFILTRO = {"guitarra": 150, "bajo": 150, "pedal": 15, "cuerdas": 5}


def _marcar(con, lid: int, proceso: str) -> None:
    con.execute("update listings set proceso=? where id=?", (proceso, lid))
    con.commit()


def _recolectar(con, lectores: dict, p: dict, hoy: date, notificador, max_consultas: int | None = None,
                max_por_lector: int | None = None, log=lambda m: None) -> tuple[list[tuple[int, Listing, str]], int, int]:
    pendientes, total, errores = [], 0, 0
    conteo = {n: 0 for n in lectores}
    bloqueados: set[str] = set()
    consultas = con.execute("select categoria, consulta from watchlist where activo=1 order by id").fetchall()
    for w in consultas[:max_consultas]:
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
            log(f"{nombre}: {len(lote)} publicaciones para '{w['consulta']}'")
            for l in lote[:max_por_lector]:
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
             hoy: date, usar_cache: bool = True) -> str:
    n = modelo.normalizar(l.titulo, l.descripcion)
    if n is None:
        return "sin_normalizar"
    con.execute("insert or replace into normalizados(listing_id, datos) values(?,?)", (lid, json.dumps(asdict(n))))
    if n.estado not in ESTADOS_ACEPTADOS:
        return "descartado_estado"
    val, comps_us = referencia_us(con, fuentes_us, modelo, n, hoy, usar_cache)
    if val is None:
        db.evento(con, "sin_valoracion_us", f"{n.marca} | {n.modelo} | {len(comps_us)} comparables aceptados")
        texto = f"{l.titulo} {l.descripcion}".lower()
        prioritarias = [w for w in p.get("palabras_prioritarias", []) if w.lower() in texto]
        datos = dict(
            listing=asdict(l) | {"fecha_publicacion": l.fecha_publicacion.isoformat() if l.fecha_publicacion else None},
            normalizado=asdict(n), valoracion_us=None, referencia_co=None, oferta=None, descuento_us=None,
            costo=asdict(cuenta(l.precio_usd, l.envio_us_usd, n.categoria, trm, p)), senales=list(n.senales_motivado),
            dias_publicado=(hoy - l.fecha_publicacion).days if l.fecha_publicacion else None,
            veredicto="Sin comparables suficientes", prioritario=bool(prioritarias), banderas=[], comps_us=comps_us,
            comps_co=[], trm=trm)
        con.execute(
            "insert into oportunidades(listing_id, tipo, puntaje, datos, creada) values(?,?,?,?,?) "
            "on conflict(listing_id) do update set tipo=excluded.tipo, puntaje=excluded.puntaje, datos=excluded.datos",
            (lid, "observacion", 0.0, json.dumps(datos), hoy.isoformat()))
        con.commit()
        return "sin_valoracion_us"
    if n.categoria in ("guitarra", "bajo") and val.nuevo_usd is not None and not (
            p["precio_nuevo_min_usd"] <= val.nuevo_usd <= p["precio_nuevo_max_usd"]):
        return "fuera_de_rango"
    ref, comps_co = referencia_co(con, fuentes_co, modelo, n, hoy)

    senales = list(n.senales_motivado) + (["rebajado"] if db.rebajas(con, lid) else [])
    dias = (hoy - l.fecha_publicacion).days if l.fecha_publicacion else None
    costo = cuenta(l.precio_usd, l.envio_us_usd, n.categoria, trm, p)
    descuento_us = 1 - l.precio_usd / val.mediana_usd
    reventa = precio_reventa_co(ref, p)
    if reventa is not None:
        confianza = "alta" if reventa[2] in ("manual", "usados en Colombia") else "media"
    else:  # el modelo no aparece en Colombia: se estima un precio de referencia y se marca como tal
        reventa, confianza = estimar_co(con, n, val, trm, p), "baja"

    tipo = None
    precio_co, n_co, origen = reventa
    escenarios = {str(round(c * 100)): _escenario(precio_co, l, n.categoria, val, trm, p, c)
                  for c in sorted(set(p.get("comisiones_escenario", []) + [p["comision_canal"]]))}
    e = escenarios[str(round(p["comision_canal"] * 100))]
    oferta = e["oferta"]
    m, hay_margen, compra = e["margen"], e["hay_margen"], e["compra_usd"]
    datos: dict = dict(
        precio_co_cop=precio_co, origen_co=origen, confianza_co=confianza, margen_en_retiro=m, hay_margen=hay_margen,
        compra_supuesta_usd=compra, rebaja_necesaria=1 - compra / l.precio_usd, margen_al_pedido=e["margen_pedido"],
        flete_maximo_usd=e["flete_maximo_usd"], comision=p["comision_canal"],
        escenarios={k: {**v, "oferta": asdict(v["oferta"]) if v["oferta"] else None} for k, v in escenarios.items()},
        # precios para venderla en Colombia: publicar en "lista", cerrar cerca de "objetivo", nunca bajo "piso"
        venta=dict(lista_cop=precio_co / (1 - p["regateo_co"]), objetivo_cop=precio_co, piso_cop=e["piso_cop"]))
    if hay_margen and confianza != "baja":
        tipo = "reventa"
        punt = puntaje(m, val.n, n_co, ref.manual, senales, dias)
    elif confianza == "baja" and descuento_us >= p["ganga_descuento_min"]:
        # No está en Colombia y está muy por debajo del mercado de EE. UU.: ganga, no se descarta.
        oferta = oferta or proponer(l.precio_usd, None, val)
        if oferta is not None:
            tipo = "ganga"
            punt = puntaje_ganga(descuento_us, val.n, senales, dias)
    resultado = "oportunidad"
    if tipo is None:
        # No es oportunidad, pero se guarda como "observacion" para verla en el tablero con su comparación
        tipo, punt, resultado = "observacion", 0.0, "sin_margen"
        oferta = oferta or proponer(l.precio_usd, None, val)
    texto = f"{l.titulo} {l.descripcion}".lower()
    prioritarias = [w for w in p.get("palabras_prioritarias", []) if w.lower() in texto]
    if prioritarias:
        punt *= 1.25
        senales.append("prioritario: " + prioritarias[0])
    if tipo == "reventa":
        veredicto = "Reventa con margen"
    elif tipo == "ganga":
        veredicto = "Ganga (no está en Colombia)"
    elif confianza != "baja":
        veredicto = "Sin margen para Colombia"
    elif hay_margen:
        veredicto = "Posible reventa (precio de Colombia estimado)"
    elif descuento_us >= 0.10:
        veredicto = "Por debajo del mercado, sin llegar a ganga"
    elif descuento_us > -0.20:  # la mediana ya descuenta la negociación: un precio pedido típico queda en −11 %
        veredicto = "A precio de mercado"
    else:
        veredicto = "Por encima del mercado"

    banderas = []
    if l.precio_usd < p["sospecha_bajo"] * val.mediana_usd:
        banderas.append("Precio inusualmente bajo: verifica autenticidad y vendedor antes de pagar")
    if tipo == "reventa" and datos.get("origen_co") == "estimado desde el nuevo":
        banderas.append("Sin usados comparables en Colombia: precio de reventa estimado desde el nuevo de tienda")
    datos.update(
        listing=asdict(l) | {"fecha_publicacion": l.fecha_publicacion.isoformat() if l.fecha_publicacion else None},
        normalizado=asdict(n), valoracion_us=asdict(val), referencia_co=asdict(ref) | {"fecha": ref.fecha.isoformat()},
        costo=asdict(cuenta(compra, l.envio_us_usd, n.categoria, trm, p)), costo_pedido=asdict(costo),
        oferta=asdict(oferta) if oferta else None, descuento_us=descuento_us, senales=senales,
        dias_publicado=dias, veredicto=veredicto, prioritario=bool(prioritarias),
        banderas=banderas, comps_us=comps_us, comps_co=comps_co, trm=trm, flete_supuesto_usd=costo.flete_usd)
    con.execute(
        "insert into oportunidades(listing_id, tipo, puntaje, datos, creada) values(?,?,?,?,?) "
        "on conflict(listing_id) do update set tipo=excluded.tipo, puntaje=excluded.puntaje, datos=excluded.datos, "
        "alertada=0", (lid, tipo, punt, json.dumps(datos), hoy.isoformat()))
    con.commit()
    return resultado



def _escenario(precio_co: float, l: Listing, categoria: str, val, trm: float, p: dict, com: float) -> dict:
    """Techo, oferta y ganancia con una comisión del vendedor en Colombia. Cifras en USD y COP."""
    techo = precio_techo(precio_co, l.envio_us_usd, categoria, trm, p, com)
    oferta = proponer(l.precio_usd, techo, val)
    compra = oferta.retiro_usd if oferta else l.precio_usd  # precio al que se supone la compra
    c_compra = cuenta(compra, l.envio_us_usd, categoria, trm, p)
    v = venta(precio_co, c_compra, com, p)
    v_pedido = venta(precio_co, cuenta(l.precio_usd, l.envio_us_usd, categoria, trm, p), com, p)
    v_apertura = (venta(precio_co, cuenta(oferta.apertura_usd, l.envio_us_usd, categoria, trm, p), com, p)
                  if oferta else None)
    # Solo cuenta si el margen se alcanza con una rebaja realista sobre el precio pedido
    hay = (oferta is not None and v.margen >= p["margen_objetivo"] - 1e-9
           and oferta.retiro_usd >= (1 - p["rebaja_maxima_esperada"]) * l.precio_usd - 1e-9)
    # piso: el menor precio de venta que conserva el margen objetivo pagando la comisión
    piso = c_compra.total_cop * (1 + p["margen_objetivo"]) / (1 - com)
    return dict(comision=com, techo_usd=techo, oferta=oferta, compra_usd=compra, costo_cop=c_compra.total_cop,
                lineas=[asdict(x) for x in c_compra.lineas],
                costo_usd=c_compra.total_usd, comision_cop=v.comision_cop, comision_usd=v.comision_usd,
                neto_cop=v.neto_cop, neto_usd=v.neto_usd, margen=v.margen, hay_margen=hay,
                neto_pedido_cop=v_pedido.neto_cop, neto_pedido_usd=v_pedido.neto_usd, margen_pedido=v_pedido.margen,
                neto_apertura_cop=v_apertura.neto_cop if v_apertura else None,
                neto_apertura_usd=v_apertura.neto_usd if v_apertura else None,
                margen_apertura=v_apertura.margen if v_apertura else None, piso_cop=piso, piso_usd=piso / trm,
                flete_maximo_usd=flete_maximo(precio_co, compra, l.envio_us_usd, categoria, trm, p, com))

def _alertar(con, modelo, notificador, p: dict) -> int:
    from .models import Listing as L, Normalizado, Oferta, ValoracionUS

    filas = con.execute("select id, datos, tipo, puntaje from oportunidades where alertada=0 and estado='nueva' "
                        "and puntaje > 0 and tipo != 'observacion' order by puntaje desc limit ?", (int(p["max_alertas_dia"]),)).fetchall()
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
           hoy: date, max_consultas: int | None = None, max_por_lector: int | None = None,
           log=lambda m: None, alertar: bool = True, reintentar: bool = True, usar_cache: bool = True) -> dict:
    """lectores: nombre -> callable(consulta) -> list[Listing]. max_* limitan una corrida de prueba."""
    p = db.parametros(con)
    pendientes, total, errores = _recolectar(con, lectores, p, hoy, notificador, max_consultas, max_por_lector, log)
    ya = {lid for lid, _l, _c in pendientes}
    if reintentar:
        pendientes += [(lid, l, "") for lid, l in db.reintentables(con) if lid not in ya]
    log(f"{total} publicaciones dentro de rango; {len(pendientes)} por evaluar (nuevas, rebajadas o reintentos)")
    estados: dict[str, int] = {}
    for i, (lid, l, _cat) in enumerate(pendientes[: int(p["max_normalizar_dia"])], 1):
        try:
            r = _evaluar(con, lid, l, modelo, fuentes_us, fuentes_co, trm, p, hoy, usar_cache)
        except Exception as e:
            errores += 1
            r = "error"
            db.evento(con, "error_evaluacion", f"{l.plataforma}:{l.id_externo}: {type(e).__name__}: {e}")
        _marcar(con, lid, r)
        estados[r] = estados.get(r, 0) + 1
        log(f"[{i}/{len(pendientes)}] {r}: {l.plataforma} {l.precio_usd:.0f} USD — {l.titulo[:70]}")
    alertas = _alertar(con, modelo, notificador, p) if alertar else 0
    resumen = {"listings": total, "nuevos_o_rebajados": len(pendientes), "oportunidades": estados.get("oportunidad", 0),
               "alertas": alertas, "errores": errores, "detalle": estados}
    db.evento(con, "corrida", json.dumps(resumen))
    return resumen
