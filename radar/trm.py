"""TRM (tasa representativa del mercado, USD/COP)."""
from __future__ import annotations

import httpx

from . import db

URL_TRM = "https://www.datos.gov.co/resource/32sa-8pi3.json"


def trm_hoy(con, cliente: httpx.Client | None = None) -> float:
    propio = cliente is None
    cliente = cliente or httpx.Client(timeout=15)
    try:
        r = cliente.get(URL_TRM, params={"$order": "vigenciadesde DESC", "$limit": 1})
        r.raise_for_status()
        valor = float(r.json()[0]["valor"])
        if valor <= 0:
            raise ValueError("TRM no válida")
        return valor
    except Exception as e:  # red caída, formato inesperado
        manual = db.parametros(con).get("trm_manual")
        if manual:
            db.evento(con, "trm_respaldo", f"se usó trm_manual={manual}: {e}")
            return float(manual)
        raise RuntimeError("No se pudo obtener la TRM y no hay trm_manual configurada") from e
    finally:
        if propio:
            cliente.close()
