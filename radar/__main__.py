"""Uso:  python -m radar correr [--prueba] | web | modelos | probar-telegram"""
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
    modelo = Modelo(modelo=aj.nim_model, api_key=aj.nim_api_key)
    avisos = _notificador(aj, con)
    oculto = not db.parametros(con).get("navegador_visible", 1)
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
    orden = {"correr": correr, "web": web, "modelos": modelos, "probar-telegram": probar_telegram}
    if len(argv) < 2 or argv[1] not in orden:
        print(__doc__)
        return 1
    if argv[1] == "correr":
        return correr(prueba="--prueba" in argv[2:])
    return orden[argv[1]]()


if __name__ == "__main__":
    sys.exit(main(sys.argv))
