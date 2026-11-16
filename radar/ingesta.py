"""Ingesta: publicaciones y precios capturados con un navegador normal y guardados en ~/.radar/ingesta/.

Archivos:
  listings.json   {"ebay": [[id, titulo, precio_texto, "fila|fila|...", subtitulo, foto], ...]}
  precios_us.json [{"fuente", "titulo", "precio", "condicion": "usado"|"nuevo", "url"}, ...]
  precios_co.json igual, con precios en COP (opcional)
"""
from __future__ import annotations

import html
import json
import re
from pathlib import Path

from .collectors import ebay
from .models import Listing, PrecioTienda

_PALABRA = re.compile(r"[a-z0-9]+")


def _leer(ruta: Path):
    try:
        return json.loads(ruta.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _tarjeta_ebay(f: list) -> str:
    lid, titulo, precio, filas, sub, foto = (list(f) + [""] * 6)[:6]
    e = html.escape
    filas_html = "".join(f'<div class="s-card__attribute-row">{e(x)}</div>' for x in str(filas).split("|") if x.strip())
    return (f'<li class="s-card" data-listingid="{e(str(lid))}"><a class="s-card__link" href="https://www.ebay.com/itm/{e(str(lid))}">'
            f'<div class="s-card__title"><span class="su-styled-text">{e(str(titulo))}</span></div></a>'
            f'<div class="s-card__subtitle">{e(str(sub))}</div><img src="{e(str(foto))}">'
            f'<span class="s-card__price">{e(str(precio))}</span>{filas_html}</li>')


def cargar_listings(carpeta: Path, trm: float) -> list[Listing]:
    datos = _leer(carpeta / "listings.json") or {}
    filas = datos.get("ebay") or []
    return ebay.parse_activos("<ul>" + "".join(_tarjeta_ebay(f) for f in filas if f) + "</ul>", trm)


def _fichas(texto: str) -> set[str]:
    return set(_PALABRA.findall(texto.lower()))


class FuentePrecios:
    """Devuelve los precios capturados cuyo título contiene todas las palabras del modelo buscado."""

    def __init__(self, ruta: Path, extra: list[PrecioTienda] | None = None):
        self.items = [PrecioTienda(str(d.get("fuente", "")), str(d.get("titulo", "")), float(d["precio"]),
                                   d.get("condicion", "usado"), str(d.get("url", "")))
                      for d in (_leer(ruta) or []) if isinstance(d, dict) and d.get("precio")]
        self.items += extra or []

    def __call__(self, consulta: str, condicion: str | None = None) -> list[PrecioTienda]:
        necesarias = _fichas(consulta)
        return [i for i in self.items
                if (condicion is None or i.condicion == condicion) and necesarias <= _fichas(i.titulo)][:40]
