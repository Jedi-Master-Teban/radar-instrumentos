"""Conecta los lectores reales con la tubería."""
from __future__ import annotations

from datetime import date
from pathlib import Path

from . import db
from .collectors import ebay, facebook, mercadolibre, reverb, tiendas
from .collectors.base import Navegador
from .config import Ajustes


def hay_perfil(aj: Ajustes) -> bool:
    return Path(aj.perfil_fb).exists() and any(Path(aj.perfil_fb).iterdir())


def ciudades_de_hoy(ciudades: list[str], por_dia: int, hoy: date) -> list[str]:
    """Rota la lista: cada día toma el siguiente bloque, para cubrir todas sin cargar la cuenta."""
    if not ciudades:
        return []
    por_dia = max(1, min(int(por_dia), len(ciudades)))
    inicio = (hoy.toordinal() * por_dia) % len(ciudades)
    return [ciudades[(inicio + i) % len(ciudades)] for i in range(por_dia)]


def armar(con, aj: Ajustes, nav: Navegador, nav_sesion: Navegador | None, trm: float, hoy: date | None = None):
    """Devuelve (lectores, fuentes_us, fuentes_co). nav_sesion = navegador con el perfil que inició sesión."""
    p = db.parametros(con)
    lectores = {
        "ebay": lambda c: ebay.buscar_activos(nav, c, trm),
        "reverb": lambda c: reverb.buscar(nav, c),
    }
    fuentes_us = {
        "reverb": lambda c, cond: reverb.precios(nav, c, "used" if cond == "usado" else "new"),
        "guitar_center": lambda c, cond: tiendas.buscar_guitar_center(nav, c, cond),
    }
    fuentes_co = {t["nombre"]: (lambda c, t=t: tiendas.buscar_tienda_co(nav, t, c)) for t in p["tiendas_co"]}
    if nav_sesion is not None:
        def fb(c):
            vistos = {}
            for ciudad in ciudades_de_hoy(p["ciudades_fb"], p["ciudades_fb_por_dia"], hoy or date.today()):
                for l in facebook.buscar_us(nav_sesion, c, ciudad):
                    vistos.setdefault(l.id_externo, l)
            return list(vistos.values())
        lectores["facebook"] = fb
        fuentes_co["Facebook Marketplace CO"] = lambda c: facebook.buscar_co(nav_sesion, c)
        fuentes_co["MercadoLibre"] = lambda c: mercadolibre.buscar(nav_sesion, c)
    return lectores, fuentes_us, fuentes_co
