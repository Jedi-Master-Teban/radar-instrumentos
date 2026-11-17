"""Valoración en EE. UU. y referencia de precios en Colombia, con caché por modelo."""
from __future__ import annotations

import json
from dataclasses import asdict
from datetime import date
from statistics import median, quantiles

from . import db
from .costing import costo_puesto
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
    salida = []
    for a in range(0, len(items), 40):  # en bloques, para no pasarle listas enormes al modelo
        bloque = items[a:a + 40]
        marcas = modelo.mismo_articulo(n, [i.titulo for i in bloque])
        salida += [i for i, ok in zip(bloque, marcas) if ok]
    return salida


def _vigente(fecha_iso: str, hoy: date, dias: int) -> bool:
    return (hoy - date.fromisoformat(fecha_iso)).days < dias


def referencia_us(con, fuentes_us: dict, modelo, n: Normalizado, hoy: date,
                  usar_cache: bool = True) -> tuple[ValoracionUS | None, list[dict]]:
    """fuentes_us: nombre -> callable(consulta, condicion) -> list[PrecioTienda]."""
    p = db.parametros(con)
    fila = con.execute("select datos, fecha, detalle from referencias_us where marca=? and modelo=?",
                       (n.marca, n.modelo)).fetchone()
    if usar_cache and fila and _vigente(fila["fecha"], hoy, p["cache_us_dias"]):
        d = json.loads(fila["datos"])
        return (ValoracionUS(**d) if d else None), json.loads(fila["detalle"] or "[]")
    consulta = f"{n.marca} {n.modelo}"
    usados = _filtrar(modelo, n, _recolectar(con, fuentes_us, consulta, "usado"))
    nuevos = _filtrar(modelo, n, _recolectar(con, fuentes_us, consulta, "nuevo"))
    val = calcular_valoracion_us(usados, nuevos, p)
    detalle = [asdict(x) for x in (usados + nuevos)[:12]]
    if val is None:
        return None, detalle  # no se guarda un "sin datos": se reintenta en la siguiente corrida
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
    if not items:  # todo bloqueado o vacío: se conserva la referencia vencida y no se guarda un "sin datos"
        if fila:
            return _ref_de_fila(fila), json.loads(fila["detalle"] or "[]")
        return ref, []
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


def sobreprecio_marca(con, marca: str, trm: float) -> tuple[float, int, str] | None:
    """Cuántas veces vale en Colombia un modelo nuevo frente a su precio nuevo en EE. UU. convertido a pesos.

    Usa los modelos que tienen precio nuevo en ambos países: primero los de la marca, si no los de todas.
    """
    de_marca, todas = [], []
    for f in con.execute("select c.marca, c.nuevo_cop, u.datos from referencias_co c join referencias_us u "
                         "on u.marca = c.marca and u.modelo = c.modelo where c.nuevo_cop is not null"):
        nuevo_usd = (json.loads(f["datos"]) or {}).get("nuevo_usd")
        if not nuevo_usd:
            continue
        r = f["nuevo_cop"] / (nuevo_usd * trm)
        if 0.8 <= r <= 4:  # fuera de eso, casi seguro es otro artículo
            todas.append(r)
            if f["marca"].lower() == marca.lower():
                de_marca.append(r)
    if de_marca:
        return median(de_marca), len(de_marca), marca
    if len(todas) >= 3:
        return median(todas), len(todas), "todas las marcas"
    return None


def estimar_co(con, n: Normalizado, val: ValoracionUS, trm: float, p: dict) -> tuple[float, int, str]:
    """Precio de venta estimado en Colombia para un modelo que no aparece allí. Siempre devuelve algo."""
    f = p["factor_usado_sobre_nuevo_co"]
    flete = p["flete_supuesto_usd"].get(n.categoria, 0) * trm
    if val.nuevo_usd:
        sp = sobreprecio_marca(con, n.marca, trm)
        if sp:
            return val.nuevo_usd * trm * sp[0] * f, min(sp[1], 3), f"estimado: sobreprecio de {sp[2]} ×{sp[0]:.2f}"
        return ((costo_puesto(val.nuevo_usd, 0, trm, p).total_cop + flete) * f, 1,
                "estimado: paridad de importación del nuevo")
    return (costo_puesto(val.mediana_usd, 0, trm, p).total_cop + flete, 1,
            "estimado: costo de traer una usada")


def _sin_tildes(t: str) -> str:
    import unicodedata

    return "".join(c for c in unicodedata.normalize("NFD", t.lower()) if unicodedata.category(c) != "Mn")


class ModeloPorPalabras:
    """Decide si un título es el mismo artículo sin modelo de lenguaje: debe contener todas las palabras."""

    @staticmethod
    def _fichas(t: str) -> set[str]:
        import re

        return set(re.findall(r"[a-z0-9]+", _sin_tildes(t)))

    @staticmethod
    def _lista(t: str) -> list[str]:
        import re

        return re.findall(r"[a-z0-9]+", _sin_tildes(t))

    def mismo_articulo(self, objetivo: Normalizado, candidatos: list[str]) -> list[bool]:
        """La marca puede ir en cualquier parte; las palabras del modelo deben ir seguidas y en orden.

        Así "Player Stratocaster HSS Plus Top" no se confunde con "Player Plus Stratocaster HSS",
        ni "Les Paul Studio" con "Les Paul Modern Studio".
        """
        marca = self._fichas(objetivo.marca)
        modelo = self._lista(objetivo.modelo)
        n = len(modelo)

        def seguidas(palabras: list[str]) -> bool:
            return any(palabras[i:i + n] == modelo for i in range(len(palabras) - n + 1))
        return [marca <= self._fichas(c) and seguidas(self._lista(c)) for c in candidatos]


def actualizar_colombia(con, fuentes_co: dict, hoy: date, log=lambda m: None) -> dict:
    """Consulta las tiendas de Colombia para cada modelo evaluado y deja las capturas listas para reevaluar."""
    modelos = {}
    for f in con.execute("select datos from oportunidades"):
        n = json.loads(f["datos"])["normalizado"]
        modelos[(n["marca"], n["modelo"])] = n["categoria"]
    encontrados = 0
    for (marca, modelo), categoria in sorted(modelos.items()):
        ref, _ = referencia_co(con, fuentes_co, ModeloPorPalabras(), Normalizado(marca, modelo, categoria, "bueno"), hoy)
        if ref.n_usado or ref.n_nuevo:
            encontrados += 1
            log(f"{marca} {modelo}: {ref.n_nuevo} nuevos, {ref.n_usado} usados en Colombia")
    db.set_parametro(con, "capturas_importadas", {})  # fuerza la reevaluación al abrir el tablero
    resumen = {"modelos": len(modelos), "con_precio_en_colombia": encontrados}
    db.evento(con, "colombia", json.dumps(resumen))
    return resumen
