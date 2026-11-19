"""Arma los archivos de datos/capturas/ a partir de lo que leyó el navegador y de la identificación de cada modelo.

Uso (lo corre la tarea programada):
  python -m radar captura conocidos                 → modelos ya usados por marca, para nombrar igual
  python -m radar captura armar filas.json modelos.json
     filas.json   = lo que devolvió scripts/capturar_reverb.js
     modelos.json = {"<id>": ["Marca", "Modelo"]} ; los ids que falten se omiten (accesorios, repuestos, dudosos)
"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from .sitio import DATOS

CAMPOS = ("id", "titulo", "precio", "condicion", "ofertas", "publicada", "envio", "foto")
PREFIJO_FOTO = "https://rvb-img.reverb.com/i/"


def conocidos(datos: Path = DATOS) -> dict[str, list[str]]:
    salida: dict[str, set[str]] = {}
    for a in (datos / "capturas").glob("*.json"):
        try:
            d = json.loads(a.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        for p in d.get("publicaciones", []):
            salida.setdefault(str(p.get("marca", "")), set()).add(str(p.get("modelo", "")))
    return {m: sorted(v) for m, v in sorted(salida.items()) if m}


def armar(filas: list[dict], modelos: dict, datos: Path = DATOS, hoy: date | None = None) -> list[dict]:
    """Escribe datos/capturas/reverb-<slug>.json por búsqueda (reemplaza el del día anterior). Devuelve un resumen."""
    hoy = hoy or date.today()
    cfg = {b["slug"]: b for b in json.loads((datos / "busquedas.json").read_text(encoding="utf-8"))["busquedas"]}
    resumen = []
    for bloque in filas:
        slug = bloque["slug"]
        b = cfg.get(slug)
        if b is None:
            continue
        if bloque.get("estado", "ok") != "ok" and not bloque.get("filas"):
            resumen.append({"slug": slug, "estado": bloque.get("estado"), "guardadas": 0, "omitidas": 0})
            continue  # se conserva la captura anterior
        if "seguir" in b:  # publicaciones en interés: una por una, con su estado e historial
            from . import interes
            d = interes.fusionar(bloque, b, modelos, datos, hoy)
            (datos / "capturas" / f"reverb-{slug}.json").write_text(json.dumps(d, ensure_ascii=False, indent=0) + "\n",
                                                                     encoding="utf-8")
            resumen.append({"slug": slug, "estado": "ok", "guardadas": len(d["publicaciones"]), "omitidas": 0,
                            "vendidas_o_retiradas": sum(p.get("anuncio") not in ("live", None) for p in d["publicaciones"])})
            continue
        pubs, omitidas = [], 0
        for f in bloque.get("filas", []):
            x = dict(zip(CAMPOS, f))
            asignado = modelos.get(str(x["id"]))
            if not asignado or len(asignado) < 2 or not str(asignado[0]).strip() or not str(asignado[1]).strip():
                omitidas += 1
                continue
            pubs.append({
                "id": str(x["id"]), "titulo": x["titulo"], "url": f"https://reverb.com/item/{x['id']}",
                "precio_usd": float(x["precio"]), "envio_usd": float(x.get("envio") or 0),
                "marca": str(asignado[0]).strip(), "modelo": str(asignado[1]).strip(),
                "categoria": asignado[2] if len(asignado) > 2 else b["categoria"],
                "estado": x["condicion"], "ofertas": bool(x["ofertas"]), "publicada": x["publicada"] or None,
                **({"foto": x["foto"] if x["foto"].startswith("http") else PREFIJO_FOTO + x["foto"]}
                   if x.get("foto") else {}),
            })
        d = {"fuente": "reverb", "consulta": b["consulta"], "capturado": hoy.isoformat(), "categoria": b["categoria"],
             "nota": f"Usadas de vendedores en EE. UU. que envían, hasta USD {b.get('precio_max', '—')}. "
                     f"{omitidas} omitidas por no ser el instrumento completo o no identificarse el modelo.",
             "publicaciones": pubs}
        (datos / "capturas" / f"reverb-{slug}.json").write_text(json.dumps(d, ensure_ascii=False, indent=0) + "\n",
                                                                 encoding="utf-8")
        resumen.append({"slug": slug, "estado": "ok", "guardadas": len(pubs), "omitidas": omitidas})
    return resumen


def main(argv: list[str]) -> int:
    if argv[:1] == ["conocidos"]:
        print(json.dumps(conocidos(), ensure_ascii=False, indent=1))
        return 0
    if argv[:1] == ["armar"] and len(argv) == 3:
        filas = json.loads(Path(argv[1]).read_text(encoding="utf-8"))
        modelos = json.loads(Path(argv[2]).read_text(encoding="utf-8"))
        print(json.dumps(armar(filas, modelos), ensure_ascii=False, indent=1))
        return 0
    print(__doc__)
    return 1
