"""Publicaciones «En interés»: las que Steve está tanteando sin haber ofertado.

- La lista vive en datos/busquedas.json, en la búsqueda especial «en-interes» (clave «seguir»). Así la tarea diaria
  se la pasa al navegador con las demás búsquedas y scripts/capturar_reverb.js consulta cada anuncio por su número,
  aunque ya no salga en la búsqueda.
- El estado del anuncio (activa, vendida, retirada) y su historial de precio van en datos/capturas/reverb-en-interes.json.
- Se agregan y quitan desde el sitio con un formulario de GitHub (un «issue») que procesa
  .github/workflows/en-interes.yml:
    «En interés: reverb <id>»       con las líneas clave: valor de la publicación
    «Quitar de interés: reverb <id>»
"""
from __future__ import annotations

import json
import re
from datetime import date
from pathlib import Path

SLUG = "en-interes"
ARCHIVO = f"reverb-{SLUG}.json"
PREFIJO_FOTO = "https://rvb-img.reverb.com/i/"
ETIQUETAS = {"live": "Activa", "sold": "Vendida", "ended": "Retirada", "suspended": "Suspendida",
             "no-encontrada": "No encontrada", "draft": "Retirada"}


def _leer(ruta: Path, defecto):
    try:
        return json.loads(ruta.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return defecto


def _escribir_busquedas(ruta: Path, d: dict) -> None:
    """Conserva el formato del archivo: una búsqueda por línea, para que se pueda editar a mano en GitHub."""
    lineas = [json.dumps(b, ensure_ascii=False) for b in d["busquedas"]]
    otros = {k: v for k, v in d.items() if k != "busquedas"}
    cuerpo = ",\n".join(f"  {json.dumps(k, ensure_ascii=False)}: {json.dumps(v, ensure_ascii=False)}" for k, v in otros.items())
    texto = "{\n" + (cuerpo + ",\n" if cuerpo else "") + '  "busquedas": [\n    ' + ",\n    ".join(lineas) + "\n  ]\n}\n"
    ruta.write_text(texto, encoding="utf-8")


def _busqueda(d: dict) -> dict:
    for b in d["busquedas"]:
        if b.get("slug") == SLUG:
            b.setdefault("seguir", [])
            return b
    b = {"slug": SLUG, "consulta": "Publicaciones en interés", "categoria": "guitarra", "seguir": []}
    d["busquedas"].append(b)
    return b


def _captura(datos: Path) -> dict:
    return _leer(datos / "capturas" / ARCHIVO, None) or {
        "fuente": "reverb", "consulta": "Publicaciones en interés", "categoria": "guitarra",
        "nota": "Publicaciones que Steve sigue sin haber ofertado; se revisan una por una cada día.", "publicaciones": []}


def _guardar_captura(datos: Path, cap: dict, hoy: date) -> None:
    cap["capturado"] = hoy.isoformat()
    (datos / "capturas").mkdir(parents=True, exist_ok=True)
    (datos / "capturas" / ARCHIVO).write_text(json.dumps(cap, ensure_ascii=False, indent=0) + "\n", encoding="utf-8")


def leer_cuerpo(texto: str) -> dict:
    """Líneas «clave: valor» del formulario; ignora comentarios y líneas vacías."""
    salida = {}
    for linea in (texto or "").splitlines():
        m = re.match(r"^\s*([a-z_]+)\s*:\s*(.*?)\s*$", linea)
        if m and not linea.lstrip().startswith("<!--"):
            salida[m.group(1)] = m.group(2)
    return salida


def _num(x, defecto=0.0) -> float:
    try:
        return float(str(x).replace(",", ""))
    except (TypeError, ValueError):
        return defecto


def agregar(datos: Path, c: dict, hoy: date) -> str:
    if c.get("plataforma", "reverb") != "reverb" or not re.fullmatch(r"\d+", c.get("id", "")):
        raise ValueError("Solo se pueden seguir publicaciones de Reverb con su número de anuncio")
    if not c.get("marca") or not c.get("modelo"):
        raise ValueError("Faltan la marca o el modelo")
    ruta = datos / "busquedas.json"
    d = _leer(ruta, {"busquedas": []})
    b = _busqueda(d)
    categoria = c.get("categoria") or "guitarra"
    entrada = {"id": c["id"], "marca": c["marca"], "modelo": c["modelo"], "categoria": categoria,
               "desde": hoy.isoformat(), "nota": c.get("nota", "")}
    previa = next((s for s in b["seguir"] if s["id"] == c["id"]), None)
    if previa:  # ya estaba: solo se actualiza la nota si viene una
        if c.get("nota"):
            previa["nota"] = c["nota"]
    else:
        b["seguir"].append(entrada)
    _escribir_busquedas(ruta, d)

    cap = _captura(datos)
    if not any(p["id"] == c["id"] for p in cap["publicaciones"]):
        precio = _num(c.get("precio_usd"))
        foto = c.get("foto", "")
        cap["publicaciones"].append({
            "id": c["id"], "titulo": c.get("titulo") or f"{c['marca']} {c['modelo']}", "url": f"https://reverb.com/item/{c['id']}",
            "precio_usd": precio, "envio_usd": _num(c.get("envio_usd")), "marca": c["marca"], "modelo": c["modelo"],
            "categoria": categoria, "estado": c.get("estado") or "good", "ofertas": str(c.get("ofertas", "")) in ("1", "true", "sí"),
            "publicada": c.get("publicada") or None, **({"foto": foto} if foto.startswith("http") else {}),
            "anuncio": "live", "revisada": hoy.isoformat(), "en_interes": {"desde": hoy.isoformat(), "nota": c.get("nota", "")},
            "historial": [{"fecha": hoy.isoformat(), "estado": "live", "precio_usd": precio}],
        })
        _guardar_captura(datos, cap, hoy)
    return f"Agregué {c['marca']} {c['modelo']} (Reverb {c['id']}) a En interés."


def quitar(datos: Path, id_: str, hoy: date) -> str:
    ruta = datos / "busquedas.json"
    d = _leer(ruta, {"busquedas": []})
    b = _busqueda(d)
    antes = len(b["seguir"])
    b["seguir"] = [s for s in b["seguir"] if s["id"] != id_]
    _escribir_busquedas(ruta, d)
    cap = _captura(datos)
    cap["publicaciones"] = [p for p in cap["publicaciones"] if p["id"] != id_]
    _guardar_captura(datos, cap, hoy)
    return f"Quité Reverb {id_} de En interés." if antes != len(b["seguir"]) else f"Reverb {id_} no estaba en En interés."


def desde_issue(datos: Path, titulo: str, cuerpo: str, hoy: date) -> str | None:
    """Procesa el título de un formulario de GitHub. None si no es un formulario de En interés."""
    m = re.match(r"^\s*(En interés|Quitar de interés)\s*:\s*reverb\s+(\d+)\s*$", titulo or "", re.I)
    if not m:
        return None
    id_ = m.group(2)
    if m.group(1).lower().startswith("quitar"):
        return quitar(datos, id_, hoy)
    c = leer_cuerpo(cuerpo)
    c["id"] = id_
    return agregar(datos, c, hoy)


def fusionar(bloque: dict, b: dict, modelos: dict, datos: Path, hoy: date) -> dict:
    """La captura diaria de las publicaciones en interés: estado del anuncio, precio e historial."""
    cap = _captura(datos)
    previas = {p["id"]: p for p in cap["publicaciones"]}
    filas = {str(f[0]): f for f in bloque.get("filas", [])}
    pubs = []
    for s in b.get("seguir", []):
        p = dict(previas.get(s["id"]) or {"id": s["id"], "url": f"https://reverb.com/item/{s['id']}", "titulo": f"{s['marca']} {s['modelo']}",
                                          "precio_usd": 0.0, "envio_usd": 0.0, "estado": "good", "historial": []})
        asignado = modelos.get(s["id"]) or [s["marca"], s["modelo"], s.get("categoria", "guitarra")]
        p.update(marca=str(asignado[0]).strip(), modelo=str(asignado[1]).strip(),
                 categoria=asignado[2] if len(asignado) > 2 else s.get("categoria", "guitarra"),
                 en_interes={"desde": s.get("desde") or hoy.isoformat(), "nota": s.get("nota", "")})
        f = filas.get(s["id"])
        if f is not None:
            estado = str(f[8]) if len(f) > 8 and f[8] else "live"
            if estado != "no-encontrada":
                foto = str(f[7] or "")
                p.update(titulo=f[1] or p["titulo"], precio_usd=float(f[2] or p["precio_usd"]), estado=f[3] or p["estado"],
                         ofertas=bool(f[4]), publicada=f[5] or p.get("publicada"), envio_usd=float(f[6] or 0))
                if foto:
                    p["foto"] = foto if foto.startswith("http") else PREFIJO_FOTO + foto
            p["anuncio"], p["revisada"] = estado, hoy.isoformat()
            hist = p.setdefault("historial", [])
            ultimo = hist[-1] if hist else None
            if not ultimo or ultimo["estado"] != estado or abs(ultimo["precio_usd"] - p["precio_usd"]) > 0.005:
                hist.append({"fecha": hoy.isoformat(), "estado": estado, "precio_usd": p["precio_usd"]})
        pubs.append(p)
    cap["publicaciones"] = pubs
    cap["nota"] = "Publicaciones que Steve sigue sin haber ofertado; se revisan una por una cada día."
    cap["capturado"] = hoy.isoformat()
    return cap


def lista(datos: Path) -> list[dict]:
    """Para el sitio: cada publicación en interés con su estado y el cambio de precio desde que se sigue."""
    cap = _captura(datos)
    salida = []
    for p in cap.get("publicaciones", []):
        hist = p.get("historial") or []
        inicial = hist[0]["precio_usd"] if hist else p.get("precio_usd")
        salida.append({**p, "etiqueta": ETIQUETAS.get(p.get("anuncio", "live"), p.get("anuncio", "")),
                       "activa": p.get("anuncio", "live") == "live",
                       "cambio_usd": (p.get("precio_usd") or 0) - (inicial or 0)})
    return salida


def main(argv: list[str]) -> int:
    """python -m radar interes "<título del formulario>" CUERPO.txt"""
    from .sitio import DATOS
    if len(argv) != 2:
        print(main.__doc__)
        return 1
    msg = desde_issue(DATOS, argv[0], Path(argv[1]).read_text(encoding="utf-8"), date.today())
    if msg is None:
        print("No es un formulario de En interés.")
        return 2
    print(msg)
    return 0
