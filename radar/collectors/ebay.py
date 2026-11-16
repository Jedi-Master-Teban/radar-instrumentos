"""eBay: publicaciones activas usadas que aceptan ofertas. (Los vendidos exigen iniciar sesión: no se leen.)"""
from __future__ import annotations

import re
from urllib.parse import quote_plus

from bs4 import BeautifulSoup

from ..models import Listing
from .base import MAX_PAGINAS, Navegador, parse_precio_usd

_OFERTA = re.compile(r"best offer|mejor oferta", re.I)
_GRATIS = re.compile(r"free (shipping|delivery)|env[ií]o gratis", re.I)
_ENVIO = re.compile(r"\+\s*(.+?)\s*(?:por el env[ií]o|de env[ií]o|shipping|delivery)", re.I)
_SOLO_LOCAL = re.compile(r"local pickup|recolecci[oó]n local", re.I)
_OTRO_PAIS = re.compile(r"^(?:de|from)\s+(?!estados unidos|united states)(.+)$", re.I)


def url_busqueda(consulta: str, pagina: int = 1, precio_min: int = 0) -> str:
    u = (f"https://www.ebay.com/sch/i.html?_nkw={quote_plus(consulta)}"
         "&LH_ItemCondition=3000&LH_BO=1&LH_PrefLoc=1&_sop=10")
    if precio_min:
        u += f"&_udlo={precio_min}"
    if pagina > 1:
        u += f"&_pgn={pagina}"
    return u


def parse_activos(html: str, trm: float | None = None) -> list[Listing]:
    sopa = BeautifulSoup(html, "html.parser")
    salida: list[Listing] = []
    for li in sopa.select("li.s-card[data-listingid]"):
        enlace = li.select_one("a.s-card__link[href*='/itm/']")
        titulo_el = li.select_one(".s-card__title .su-styled-text") or li.select_one(".s-card__title")
        precio_el = li.select_one(".s-card__price")
        if not (enlace and titulo_el and precio_el):
            continue
        titulo = titulo_el.get_text(" ", strip=True)
        m = re.search(r"/itm/(\d{9,})", enlace["href"])
        if not m or titulo.lower() == "shop on ebay":
            continue
        filas = [f.get_text(" ", strip=True) for f in li.select(".s-card__attribute-row")]
        if any(_OTRO_PAIS.match(f) for f in filas):
            continue  # el artículo está fuera de EE. UU.
        precio = parse_precio_usd(precio_el.get_text(" ", strip=True), trm)
        if precio is None:
            continue
        envio, hace_envios = 0.0, True
        for f in filas:
            if _GRATIS.search(f):
                envio = 0.0
            elif (me := _ENVIO.search(f)):
                envio = parse_precio_usd(me.group(1), trm) or 0.0
            elif _SOLO_LOCAL.search(f):
                hace_envios = False
        img = li.select_one("img[src]")
        sub = li.select_one(".s-card__subtitle")
        salida.append(Listing(
            plataforma="ebay", id_externo=m.group(1), url=f"https://www.ebay.com/itm/{m.group(1)}",
            titulo=titulo, precio_usd=precio, envio_us_usd=envio,
            acepta_ofertas=any(_OFERTA.search(f) for f in filas), hace_envios=hace_envios,
            fotos=[img["src"]] if img else [], estado_declarado=sub.get_text(" ", strip=True) if sub else "",
        ))
    return salida


def buscar_activos(nav: Navegador, consulta: str, trm: float | None = None, precio_min: int = 0,
                   paginas: int = 1) -> list[Listing]:
    vistos: dict[str, Listing] = {}
    for p in range(1, min(paginas, MAX_PAGINAS) + 1):
        lote = parse_activos(nav.html(url_busqueda(consulta, p, precio_min)), trm)
        if not lote:
            break
        for l in lote:
            vistos.setdefault(l.id_externo, l)
    return list(vistos.values())
