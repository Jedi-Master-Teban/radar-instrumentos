"""Uso:  python -m radar correr | web | modelos | probar-telegram"""
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


def correr() -> int:
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
    modelo = Modelo(modelo=aj.nim_model, api_key=aj.nim_api_key)
    avisos = _notificador(aj, con)
    with Navegador() as nav:
        if hay_perfil(aj):
            with Navegador(perfil=aj.perfil_fb) as nav_sesion:
                resumen = tuberia(con, *armar(con, aj, nav, nav_sesion, trm), modelo, avisos, trm, date.today())
        else:
            print("Sin sesión guardada: se omiten Facebook y MercadoLibre (ejecuta scripts/login_facebook.py).")
            resumen = tuberia(con, *armar(con, aj, nav, None, trm), modelo, avisos, trm, date.today())
    print(json.dumps(resumen, ensure_ascii=False, indent=2))
    return 0


def web() -> int:
    import uvicorn

    from .web.app import crear_app

    aj = config.cargar()
    uvicorn.run(crear_app(aj), host="127.0.0.1", port=8000)
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
    return orden[argv[1]]()


if __name__ == "__main__":
    sys.exit(main(sys.argv))
