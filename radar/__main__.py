"""Uso:  python -m radar captura conocidos|armar FILAS MODELOS | correr [--prueba] | colombia | sitio [--salida DIR] [--sin-colombia] [--repo DUEÑO/NOMBRE] | web | modelos | probar-telegram"""
from __future__ import annotations

import json
import sys
from datetime import date

from . import config, db
from .notify import SinAvisos, Telegram


def _notificador(aj, con):
    if aj.telegram_bot_token and aj.telegram_chat_id:
        return Telegram(aj.telegram_bot_token, aj.telegram_chat_id, registrar=lambda t, d: db.evento(con, t, d))
    print("Telegram sin configurar: las alertas solo quedan en el tablero.")
    return SinAvisos()


def correr(prueba: bool = False) -> int:
    from .collectors.base import Navegador
    from .llm import Modelo
    from .montaje import armar, hay_perfil
    from .pipeline import correr as tuberia
    from .trm import trm_hoy

    aj = config.cargar()
    if not aj.nim_api_key:
        print("Falta NIM_API_KEY (ponla en .env o en el tablero, pestaña Ajustes).")
        return 2
    con = db.conectar(aj.ruta_db)
    trm = trm_hoy(con)
    log = lambda m: print(m, flush=True)
    limites = dict(max_consultas=1, max_por_lector=12) if prueba else {}
    log(f"TRM {trm:,.2f} · modelo {aj.nim_model or 'por defecto'} · {'PRUEBA (1 búsqueda, 12 por sitio)' if prueba else 'corrida completa'}")
    modelo = Modelo(modelo=aj.nim_model, api_key=aj.nim_api_key, registrar=lambda t, d: db.evento(con, t, d))
    avisos = _notificador(aj, con)
    p = db.parametros(con)
    if not p.get("usar_playwright", 0):
        resumen = _correr_con_ingesta(con, aj, p, modelo, avisos, trm, log, limites)
    else:
        oculto = not p.get("navegador_visible", 1)
        with Navegador(headless=oculto) as nav:
            if hay_perfil(aj):
                with Navegador(perfil=aj.perfil_fb, headless=oculto) as nav_sesion:
                    resumen = tuberia(con, *armar(con, aj, nav, nav_sesion, trm), modelo, avisos, trm, date.today(),
                                      log=log, **limites)
            else:
                print("Sin sesión guardada: se omiten Facebook y MercadoLibre (ejecuta scripts/login_facebook.py).")
                resumen = tuberia(con, *armar(con, aj, nav, None, trm), modelo, avisos, trm, date.today(),
                                  log=log, **limites)
    print(json.dumps(resumen, ensure_ascii=False, indent=2))
    return 0


def _correr_con_ingesta(con, aj, p, modelo, avisos, trm, log, limites) -> dict:
    """Usa lo capturado en ~/.radar/ingesta/ y consulta las tiendas de Colombia por HTTP directo."""
    from .collectors import tiendas
    from .collectors.http import ClienteHttp
    from .ingesta import FuentePrecios, cargar_listings
    from .models import PrecioTienda
    from .pipeline import correr as tuberia

    carpeta = aj.home / "ingesta"
    listings = cargar_listings(carpeta, trm)
    log(f"Ingesta: {len(listings)} publicaciones capturadas en {carpeta}")
    entregado = []

    def lector(_consulta):
        if entregado:
            return []
        entregado.append(1)
        return listings

    # los precios pedidos de eBay capturados también sirven como comparables de usados
    propios = [PrecioTienda("ebay", l.titulo, l.precio_usd, "usado", l.url) for l in listings]
    http = ClienteHttp()
    fuentes_us = {"capturado": FuentePrecios(carpeta / "precios_us.json", propios)}
    fuentes_co = {t["nombre"]: (lambda c, t=t: tiendas.buscar_tienda_co(http, t, c)) for t in p["tiendas_co"]}
    fuentes_co["capturado"] = FuentePrecios(carpeta / "precios_co.json")
    limites = {k: v for k, v in limites.items() if k != "max_por_lector"}
    return tuberia(con, {"ingesta": lector}, fuentes_us, fuentes_co, modelo, avisos, trm, date.today(), log=log,
                   **limites)


def colombia() -> int:
    """Actualiza los precios de referencia de Colombia consultando las tiendas por HTTP directo."""
    from .collectors import tiendas
    from .collectors.http import ClienteHttp
    from .valuation import actualizar_colombia

    aj = config.cargar()
    con = db.conectar(aj.ruta_db)
    http = ClienteHttp()
    fuentes = {t["nombre"]: (lambda c, t=t: tiendas.buscar_tienda_co(http, t, c)) for t in db.parametros(con)["tiendas_co"]}
    print("Consultando tiendas de Colombia...", flush=True)
    print(json.dumps(actualizar_colombia(con, fuentes, date.today(), log=lambda m: print(m, flush=True)),
                     ensure_ascii=False, indent=2))
    return 0


def sitio(argv: list[str]) -> int:
    """Construye el sitio estático (GitHub Pages) a partir de datos/."""
    from pathlib import Path

    from .sitio import construir

    def opcion(nombre, defecto=""):
        return argv[argv.index(nombre) + 1] if nombre in argv and argv.index(nombre) + 1 < len(argv) else defecto

    construir(Path(opcion("--salida", "_site")), colombia="--sin-colombia" not in argv, repo=opcion("--repo"),
              log=lambda m: print(m, flush=True))
    return 0


def web() -> int:
    import uvicorn

    # reload=True: el tablero toma los cambios de código sin reiniciarlo a mano
    uvicorn.run("radar.web.app:app_desde_entorno", factory=True, host="127.0.0.1", port=8000, reload=True,
                reload_dirs=["radar"])
    return 0


def modelos() -> int:
    from openai import OpenAI

    aj = config.cargar()
    for m in OpenAI(base_url=config.NIM_BASE_URL, api_key=aj.nim_api_key).models.list().data:
        print(m.id)
    return 0


def probar_telegram() -> int:
    aj = config.cargar()
    con = db.conectar(aj.ruta_db)
    _notificador(aj, con).aviso("radar: mensaje de prueba ok")
    return 0


def main(argv: list[str]) -> int:
    orden = {"captura": None, "correr": correr, "sitio": sitio, "colombia": colombia, "web": web, "modelos": modelos, "probar-telegram": probar_telegram}
    if len(argv) < 2 or argv[1] not in orden:
        print(__doc__)
        return 1
    if argv[1] == "captura":
        from .captura_reverb import main as captura
        return captura(argv[2:])
    if argv[1] == "sitio":
        return sitio(argv[2:])
    if argv[1] == "correr":
        return correr(prueba="--prueba" in argv[2:])
    return orden[argv[1]]()


if __name__ == "__main__":
    sys.exit(main(sys.argv))
