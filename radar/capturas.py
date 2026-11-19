"""Capturas: publicaciones ya identificadas (marca, modelo, estado) guardadas como JSON en datos/capturas/.

Las escribe quien navega (por ejemplo, una tarea programada de Claude con el navegador integrado). Como ya traen
marca y modelo, se evalúan al instante y sin modelo de lenguaje. El formato está en datos/README.md.
"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from . import db
from .llm import mensaje_plantilla
from .models import CATEGORIAS, ESTADOS, Listing, Normalizado, PrecioTienda
from .notify import SinAvisos
from .pipeline import correr

CARPETA = Path(__file__).resolve().parents[1] / "datos" / "capturas"
_ESTADOS_REVERB = {"mint": "excelente", "mint-inventory": "excelente", "excellent": "excelente", "very-good": "bueno",
                   "good": "bueno", "fair": "regular", "poor": "para_reparar", "non-functioning": "para_reparar",
                   "brand-new": "nuevo", "b-stock": "excelente"}


def _clave(marca: str, modelo: str) -> str:
    return f"{marca} {modelo}".strip().lower()


class ModeloCaptura:
    """Hace el papel del modelo de lenguaje usando lo que la captura ya trae resuelto."""

    def __init__(self):
        self.por_titulo: dict[str, Normalizado] = {}

    def normalizar(self, titulo, descripcion):
        return self.por_titulo.get(titulo)

    def mismo_articulo(self, objetivo, candidatos):
        return [c.strip().lower() == _clave(objetivo.marca, objetivo.modelo) for c in candidatos]

    def mensaje_oferta(self, l, n, o, val):
        return mensaje_plantilla(n, o, val)


class FuenteCapturas:
    def __init__(self):
        self.items: list[PrecioTienda] = []

    def __call__(self, consulta: str, condicion: str | None = None) -> list[PrecioTienda]:
        return [i for i in self.items if i.titulo.lower() == consulta.strip().lower()
                and (condicion is None or i.condicion == condicion)]


def leer_captura(ruta: Path) -> tuple[list[tuple[Listing, Normalizado]], list[PrecioTienda]]:
    d = json.loads(ruta.read_text(encoding="utf-8"))
    fuente = str(d.get("fuente", "captura"))
    pares, precios = [], []
    for x in d.get("publicaciones", []):
        if x.get("anuncio") not in (None, "live"):  # vendida, retirada o no encontrada: no se evalúa
            continue
        try:
            estado = x.get("estado", "bueno")
            estado = estado if estado in ESTADOS else _ESTADOS_REVERB.get(estado, "bueno")
            categoria = x.get("categoria", d.get("categoria", "guitarra"))
            marca, modelo, precio = str(x["marca"]).strip(), str(x["modelo"]).strip(), float(x["precio_usd"])
            if not marca or not modelo or precio <= 0 or categoria not in CATEGORIAS:
                continue
            l = Listing(plataforma=str(x.get("fuente") or fuente), id_externo=str(x["id"]), url=str(x["url"]), titulo=str(x["titulo"]).strip(),
                        precio_usd=precio, descripcion=str(x.get("descripcion", "")),
                        envio_us_usd=float(x.get("envio_usd") or 0), acepta_ofertas=bool(x.get("ofertas")),
                        hace_envios=x.get("envia", True) is not False,
                        fecha_publicacion=date.fromisoformat(x["publicada"]) if x.get("publicada") else None,
                        fotos=[x["foto"]] if x.get("foto") else [], estado_declarado=str(x.get("estado", "")))
            n = Normalizado(marca=marca, modelo=modelo, categoria=categoria, estado=estado,
                            senales_motivado=[str(s) for s in x.get("senales", [])])
        except (KeyError, TypeError, ValueError):
            continue
        pares.append((l, n))
        precios.append(PrecioTienda(fuente, f"{marca} {modelo}", precio, "usado", l.url))
    for x in d.get("precios_usados", []):  # comparables sin publicación propia (precios pedidos de usadas)
        try:
            precios.append(PrecioTienda(str(x.get("fuente", fuente)), f"{str(x['marca']).strip()} {str(x['modelo']).strip()}",
                                        float(x["precio_usd"]), "usado", str(x.get("url", ""))))
        except (KeyError, TypeError, ValueError):
            continue
    for x in d.get("precios_nuevos", []):
        try:
            precios.append(PrecioTienda(fuente, f"{str(x['marca']).strip()} {str(x['modelo']).strip()}",
                                        float(x["precio_usd"]), "nuevo", str(x.get("url", ""))))
        except (KeyError, TypeError, ValueError):
            continue
    return pares, precios


def _fecha_captura(ruta: Path) -> str:
    try:
        return str(json.loads(ruta.read_text(encoding="utf-8")).get("capturado") or "")
    except (OSError, ValueError):
        return ""


def importar(con, carpeta: Path, trm: float, hoy: date, forzar: bool = False) -> dict | None:
    """Evalúa las capturas nuevas o modificadas. Devuelve el resumen, o None si no había nada que importar."""
    if not carpeta.exists():
        return None
    vistas = db.parametros(con).get("capturas_importadas", {})
    archivos = sorted(carpeta.glob("*.json"))
    actuales = {a.name: a.stat().st_mtime for a in archivos}
    if not forzar and all(vistas.get(n) == m for n, m in actuales.items()):
        return None
    modelo, fuente = ModeloCaptura(), FuenteCapturas()
    leidos = []
    vigencia = int(db.parametros(con).get("dias_vigencia_captura", 14))
    for a in archivos:  # se leen todas: los comparables salen del conjunto completo
        fecha = _fecha_captura(a)
        try:
            if fecha and (hoy - date.fromisoformat(fecha)).days > vigencia:
                continue  # captura vieja: sus publicaciones probablemente ya se vendieron
        except ValueError:
            pass
        try:
            leidos.append((fecha, a.name, *leer_captura(a)))
        except (OSError, ValueError) as e:
            db.evento(con, "captura_invalida", f"{a.name}: {e}")
    # Si una publicación aparece en varias capturas, cuenta una sola vez: la de la captura más reciente.
    por_id: dict = {}
    precios: dict = {}
    for _fecha, _nombre, pares, pr in sorted(leidos, key=lambda x: (x[0], x[1])):
        for l, n in pares:
            por_id[(l.plataforma, l.id_externo)] = (l, n)
        for x in pr:
            precios[(x.condicion, x.url or f"{x.titulo}|{x.precio}")] = x
    fuente.items = list(precios.values())
    todos: list[Listing] = []
    for l, n in por_id.values():
        modelo.por_titulo[l.titulo] = n
        todos.append(l)
    entregado = []

    def lector(_consulta):
        if entregado:
            return []
        entregado.append(1)
        return todos

    # se marcan como pendientes para reevaluarlas con los comparables de hoy
    for l in todos:
        con.execute("update listings set proceso='pendiente' where plataforma=? and id_externo=?",
                    (l.plataforma, l.id_externo))
    con.commit()
    resumen = correr(con, {"capturas": lector}, {"capturas": fuente}, {}, modelo, SinAvisos(), trm, hoy,
                     max_consultas=1, alertar=False, reintentar=False, usar_cache=False)
    pend = {(l.plataforma, l.id_externo): l for l in todos}
    # las que ya existían sin cambio de precio también se reevalúan
    from .pipeline import _evaluar, _marcar
    p = db.parametros(con)
    for f in con.execute("select id, plataforma, id_externo from listings where proceso='pendiente'").fetchall():
        l = pend.get((f["plataforma"], f["id_externo"]))
        if l is not None:
            _marcar(con, f["id"], _evaluar(con, f["id"], l, modelo, {"capturas": fuente}, {}, trm, p, hoy, False))
    db.set_parametro(con, "capturas_importadas", actuales)
    resumen["archivos"] = len(archivos)
    db.evento(con, "importacion", json.dumps(resumen))
    return resumen
