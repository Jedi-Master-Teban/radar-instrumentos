"""Costo puesto en Bogotá y venta en Colombia, con cada cifra en dólares y en pesos. Funciones puras.

Se compra en dólares y se vende en pesos, así que cada concepto lleva las dos monedas a la TRM del día:
- lo que se paga con tarjeta (precio, envío e impuesto en EE. UU., flete, seguro, inspección) más el
  recargo cambiario de la tarjeta;
- arancel e IVA, que la DIAN liquida sobre producto + flete + seguro (base CIF);
- el ajuste del luthier en Bogotá, que se paga en pesos.
"""
from __future__ import annotations

from .models import Costo, Linea, Venta


def _p(p: dict, clave: str, defecto: float) -> float:
    v = p.get(clave)
    return defecto if v is None else v


def cuenta(precio_usd: float, envio_us_usd: float, categoria: str, trm: float, p: dict,
           flete_usd: float | None = None) -> Costo:
    """Todo lo que cuesta tener el artículo listo para vender en Bogotá."""
    producto = precio_usd + envio_us_usd
    impuesto_us = producto * p["sales_tax_us"]
    flete = p["flete_supuesto_usd"].get(categoria, 0) if flete_usd is None else flete_usd
    seguro = max(_p(p, "seguro_pct", 0.035) * producto, _p(p, "seguro_min_usd", 10))
    logistica = flete + seguro + _p(p, "inspeccion_usd", 10)
    recargo = (producto + impuesto_us + logistica) * p["margen_cambiario"]
    cif = producto + flete + seguro
    arancel = cif * p["arancel"]
    iva = (cif + arancel) * p["iva"]
    aj = p.get("ajuste_luthier_cop", 150_000)
    ajuste_cop = (aj.get(categoria, 0) if isinstance(aj, dict) else aj) or 0
    filas = [("Precio y envío en EE. UU.", producto), ("Impuesto de ventas en EE. UU.", impuesto_us),
             ("Flete, seguro e inspección", logistica), ("Recargo de la tarjeta", recargo),
             ("Arancel", arancel), ("IVA", iva), ("Ajuste del luthier", ajuste_cop / trm)]
    lineas = [Linea(concepto=c, usd=u, cop=u * trm) for c, u in filas]
    lineas[-1].cop = ajuste_cop  # se paga en pesos: la cifra exacta es la de pesos
    total_cop = sum(l.cop for l in lineas)
    return Costo(lineas=lineas, total_usd=total_cop / trm, total_cop=total_cop, trm=trm, flete_usd=flete,
                 seguro_usd=seguro)


def venta(precio_cop: float, costo: Costo, comision: float, p: dict) -> Venta:
    """Lo que queda al vender en pesos, pagando la comisión del vendedor sobre el precio de venta."""
    trm = costo.trm
    com = precio_cop * comision
    neto = precio_cop - com - costo.total_cop
    return Venta(precio_cop=precio_cop, precio_usd=precio_cop / trm, comision=comision, comision_cop=com,
                 comision_usd=com / trm, neto_cop=neto, neto_usd=neto / trm,
                 margen=neto / costo.total_cop if costo.total_cop > 0 else 0.0)


def _biseccion(f, lo: float, hi: float) -> float:
    """Mayor x en [lo, hi] con f(x) >= 0, para f decreciente."""
    if f(lo) < 0:
        return lo - 1
    for _ in range(80):
        mid = (lo + hi) / 2
        lo, hi = (mid, hi) if f(mid) >= 0 else (lo, mid)
    return lo


def precio_techo(precio_venta_cop: float, envio_us_usd: float, categoria: str, trm: float, p: dict,
                 comision: float | None = None, flete_usd: float | None = None) -> float:
    """Mayor precio pedido en USD que conserva el margen objetivo. Negativo: ni regalado hay margen."""
    com = p["comision_canal"] if comision is None else comision
    mo = p["margen_objetivo"]
    f = lambda x: venta(precio_venta_cop, cuenta(x, envio_us_usd, categoria, trm, p, flete_usd), com, p).margen - mo
    return _biseccion(f, 0.0, 50_000.0)


def flete_maximo(precio_venta_cop: float, precio_usd: float, envio_us_usd: float, categoria: str, trm: float,
                 p: dict, comision: float | None = None) -> float:
    """Flete internacional (USD) que deja exactamente el margen objetivo. Negativo = no hay margen."""
    com = p["comision_canal"] if comision is None else comision
    mo = p["margen_objetivo"]
    f = lambda x: venta(precio_venta_cop, cuenta(precio_usd, envio_us_usd, categoria, trm, p, x), com, p).margen - mo
    return _biseccion(f, 0.0, 50_000.0)
