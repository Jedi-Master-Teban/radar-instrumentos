"""Valoración en EE. UU. y referencia de precios en Colombia, con caché por modelo."""
from __future__ import annotations

import json
from dataclasses import asdict
from datetime import date
from statistics import median, quantiles

from . import db
from .collectors.base import LectorBloqueado
from .models import Normalizado, PrecioTienda, ReferenciaCO, ValoracionUS


def _limpiar(precios: list[float]) -> list[float]:
    """Quita atípicos (accesorios, copias, errores): fuera de [0,4×, 2,5×] la mediana."""
    precios = [x for x in precios if x and x > 0]
    if len(precios) < 3:
        return precios
    m = median(precios)
    return [x for x in precios if 0.4 * m <= x <= 2.5 * m]


def calcular_valoracion_us(usados: list[PrecioTienda], nuevos: list[PrecioTienda], p: dict) -> ValoracionUS | None:
    """Los comparables son precios PEDIDOS (los vendidos de eBay exigen sesión): se descuenta la negociación."""
    pu = _limpiar([x.precio for x in usados])
    if len(pu) < p["min_comparables_us"]:
        return None
    f = 1 - p["descuento_negociacion_us"]
    if len(pu) >= 4:
        q1, _, q3 = quantiles(pu, n=4)
    else:
        q1, q3 = min(pu), max(pu)
    pn = _limpiar([x.precio for x in nuevos])
    return ValoracionUS(mediana_usd=median(pu) * f, p25_usd=q1 * f, p75_usd=q3 * f, n=len(pu),
                        nuevo_usd=median(pn) if pn else None)


def calcular_referencia_co(items: list[PrecioTienda], hoy: date, p: dict) -> ReferenciaCO:
    usados = _limpiar([x.precio for x in items if x.condicion == "usado"])
    nuevos = _limpiar([x.precio for x in items if x.condicion == "nuevo"])
    return ReferenciaCO(
        usado_cop=median(usados) * (1 - p["descuento_negociacion_co"]) if usados else None,
        nuevo_cop=median(nuevos) if nuevos else None,  # precio de tienda: no se negocia
        n_usado=len(usados), n_nuevo=len(nuevos), fecha=hoy, manual=False)


def precio_reventa_co(ref: ReferenciaCO, p: dict) -> tuple[float, int, str] | None:
    """(precio de venta esperado en COP, tamaño de evidencia, origen). None = sin evidencia suficiente."""
    if ref.manual and ref.usado_cop:
        return ref.usado_cop, 5, "manual"
    if ref.usado_cop and ref.n_usado >= p["min_refs_co"]:
        return ref.usado_cop, ref.n_usado, "usados en Colombia"
    if ref.nuevo_cop and ref.n_nuevo >= 1:
        # sin usados suficientes: se estima desde el precio nuevo de tienda
        return ref.nuevo_cop * p["factor_usado_sobre_nuevo_co"], min(ref.n_nuevo * 2, 5), "estimado desde el nuevo"
    return None


def _recolectar(con, fuentes: dict, consulta: str, *args) -> list[PrecioTienda]:
    salida: list[PrecioTienda] = []
    for nombre, fuente in fuentes.items():
        try:
            salida.extend(fuente(consulta, *args))
        except LectorBloqueado as e:
            db.evento(con, "lector_bloqueado", f"{nombre}: {e}")
        except Exception as e:  # un sitio caído no detiene la valoración
            db.evento(con, "lector_error", f"{nombre}: {type(e).__name__}: {e}")
    return salida


def _filtrar(modelo, n: Normalizado, items: list[PrecioTienda]) -> list[PrecioTienda]:
    if not items:
        return []
    marcas = modelo.mismo_articulo(n, [i.titulo for i in items])
    return [i for i, ok in zip(items, marcas) if ok]


def _vigente(fecha_iso: str, hoy: date, dias: int) -> bool:
    return (hoy - date.fromisoformat(fecha_iso)).days < dias


def referencia_us(con, fuentes_us: dict, modelo, n: Normalizado, hoy: date) -> tuple[ValoracionUS | None, list[dict]]:
    """fuentes_us: nombre -> callable(consulta, condicion) -> list[PrecioTienda]."""
    p = db.parametros(con)
    fila = con.execute("select datos, fecha, detalle from referencias_us where marca=? and modelo=?",
                       (n.marca, n.modelo)).fetchone()
    if fila and _vigente(fila["fecha"], hoy, p["cache_us_dias"]):
        d = json.loads(fila["datos"])
        return (ValoracionUS(**d) if d else None), json.loads(fila["detalle"] or "[]")
    consulta = f"{n.marca} {n.modelo}"
    usados = _filtrar(modelo, n, _recolectar(con, fuentes_us, consulta, "usado"))
    nuevos = _filtrar(modelo, n, _recolectar(con, fuentes_us, consulta, "nuevo"))
    val = calcular_valoracion_us(usados, nuevos, p)
    detalle = [asdict(x) for x in (usados + nuevos)[:12]]
    con.execute("insert into referencias_us(marca, modelo, datos, fecha, detalle) values(?,?,?,?,?) "
                "on conflict(marca, modelo) do update set datos=excluded.datos, fecha=excluded.fecha, "
                "detalle=excluded.detalle",
                (n.marca, n.modelo, json.dumps(asdict(val) if val else None), hoy.isoformat(), json.dumps(detalle)))
    con.commit()
    return val, detalle


def _ref_de_fila(f) -> ReferenciaCO:
    return ReferenciaCO(f["usado_cop"], f["nuevo_cop"], f["n_usado"] or 0, f["n_nuevo"] or 0,
                        date.fromisoformat(f["fecha"]), bool(f["manual"]))


def referencia_co(con, fuentes_co: dict, modelo, n: Normalizado, hoy: date) -> tuple[ReferenciaCO, list[dict]]:
    """fuentes_co: nombre -> callable(consulta) -> list[PrecioTienda]. El valor manual manda."""
    p = db.parametros(con)
    fila = con.execute("select * from referencias_co where marca=? and modelo=?", (n.marca, n.modelo)).fetchone()
    if fila and (fila["manual"] or _vigente(fila["fecha"], hoy, p["cache_co_dias"])):
        return _ref_de_fila(fila), json.loads(fila["detalle"] or "[]")
    items = _filtrar(modelo, n, _recolectar(con, fuentes_co, f"{n.marca} {n.modelo}"))
    ref = calcular_referencia_co(items, hoy, p)
    if fila and not items:  # todo bloqueado o vacío: se conserva la referencia vencida
        return _ref_de_fila(fila), json.loads(fila["detalle"] or "[]")
    detalle = [asdict(x) for x in items[:12]]
    con.execute("insert into referencias_co(marca, modelo, usado_cop, nuevo_cop, n_usado, n_nuevo, fecha, manual, detalle)"
                " values(?,?,?,?,?,?,?,0,?) on conflict(marca, modelo) do update set usado_cop=excluded.usado_cop,"
                " nuevo_cop=excluded.nuevo_cop, n_usado=excluded.n_usado, n_nuevo=excluded.n_nuevo,"
                " fecha=excluded.fecha, detalle=excluded.detalle",
                (n.marca, n.modelo, ref.usado_cop, ref.nuevo_cop, ref.n_usado, ref.n_nuevo, hoy.isoformat(),
                 json.dumps(detalle)))
    con.commit()
    return ref, detalle


def fijar_referencia_manual(con, marca: str, modelo: str, usado_cop: float, hoy: date) -> None:
    con.execute("insert into referencias_co(marca, modelo, usado_cop, n_usado, n_nuevo, fecha, manual) "
                "values(?,?,?,0,0,?,1) on conflict(marca, modelo) do update set usado_cop=excluded.usado_cop, "
                "manual=1, fecha=excluded.fecha", (marca, modelo, usado_cop, hoy.isoformat()))
    con.commit()
