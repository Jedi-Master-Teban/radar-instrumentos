"""Reverb: lee el mismo JSON que usa su página de resultados (sin token, solo lectura)."""
from __future__ import annotations

import re
from datetime import date
from urllib.parse import quote

from ..models import Listing, PrecioTienda
from .base import Navegador

ORIGEN = "https://reverb.com"
CABECERAS = {"Accept": "application/hal+json", "Accept-Version": "3.0", "Content-Type": "application/hal+json"}
_HTML = re.compile(r"<[^>]+>")


def ruta_busqueda(consulta: str, condicion: str = "used", ofertas: bool = True, por_pagina: int = 50,
                  pagina: int = 1) -> str:
    r = f"/api/listings?query={quote(consulta)}&condition={condicion}&item_region=US&per_page={por_pagina}&page={pagina}"
    return r + ("&accepts_offers=true" if ofertas else "")


def parse_listings(datos: dict | None) -> list[Listing]:
    salida = []
    for l in (datos or {}).get("listings", []) or []:
        try:
            precio = l["price"]
            if precio.get("currency") != "USD":
                continue
            monto = float(precio["amount"])
            if monto <= 0 or (l.get("state") or {}).get("slug", "live") != "live":
                continue
            tarifas = (l.get("shipping") or {}).get("rates") or []
            envio = 0.0
            for t in tarifas:
                if t.get("region_code") == "US_CON" and isinstance(t.get("rate"), dict):
                    envio = float(t["rate"].get("amount", 0) or 0)
            fotos = [f["_links"]["large_crop"]["href"] for f in (l.get("photos") or [])[:3]
                     if f.get("_links", {}).get("large_crop")]
            publicado = (l.get("published_at") or l.get("created_at") or "")[:10]
            salida.append(Listing(
                plataforma="reverb", id_externo=str(l["id"]), url=l["_links"]["web"]["href"],
                titulo=l.get("title", "").strip(), precio_usd=monto, envio_us_usd=envio,
                descripcion=_HTML.sub(" ", l.get("description") or "")[:1500].strip(),
                acepta_ofertas=bool(l.get("offers_enabled")), hace_envios=bool(tarifas),
                fecha_publicacion=date.fromisoformat(publicado) if publicado else None,
                fotos=fotos, estado_declarado=(l.get("condition") or {}).get("slug", ""),
            ))
        except (KeyError, TypeError, ValueError):
            continue
    return salida


def buscar(nav: Navegador, consulta: str, paginas: int = 1) -> list[Listing]:
    salida: dict[str, Listing] = {}
    for p in range(1, paginas + 1):
        lote = parse_listings(nav.json(ORIGEN, ruta_busqueda(consulta, pagina=p), CABECERAS))
        if not lote:
            break
        for l in lote:
            salida.setdefault(l.id_externo, l)
    return list(salida.values())


def precios(nav: Navegador, consulta: str, condicion: str) -> list[PrecioTienda]:
    """Precios pedidos en Reverb para valorar: condicion 'used' o 'new'."""
    datos = nav.json(ORIGEN, ruta_busqueda(consulta, condicion=condicion, ofertas=False, por_pagina=40), CABECERAS)
    cond = "usado" if condicion == "used" else "nuevo"
    return [PrecioTienda("reverb", l.titulo, l.precio_usd, cond, l.url) for l in parse_listings(datos)]
