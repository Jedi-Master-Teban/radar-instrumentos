"""Conecta los lectores reales con la tubería."""
from __future__ import annotations

from pathlib import Path

from . import db
from .collectors import ebay, facebook, mercadolibre, reverb, tiendas
from .collectors.base import Navegador
from .config import Ajustes


def hay_perfil(aj: Ajustes) -> bool:
    return Path(aj.perfil_fb).exists() and any(Path(aj.perfil_fb).iterdir())


def armar(con, aj: Ajustes, nav: Navegador, nav_sesion: Navegador | None, trm: float):
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
            for ciudad in p["ciudades_fb"]:
                for l in facebook.buscar_us(nav_sesion, c, ciudad):
                    vistos.setdefault(l.id_externo, l)
            return list(vistos.values())
        lectores["facebook"] = fb
        fuentes_co["Facebook Marketplace CO"] = lambda c: facebook.buscar_co(nav_sesion, c)
        fuentes_co["MercadoLibre"] = lambda c: mercadolibre.buscar(nav_sesion, c)
    return lectores, fuentes_us, fuentes_co
