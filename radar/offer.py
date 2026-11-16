"""Precio techo, oferta de apertura y punto de retiro. El tope vive en código, no en el modelo."""
from __future__ import annotations

from .costing import _factor_cop, ingreso_neto
from .models import Oferta, ValoracionUS

BRECHA_MAXIMA = 0.60  # si el retiro queda por debajo del 60 % del precio pedido, no se propone
APERTURA_SOBRE_RETIRO = 0.85
APERTURA_SOBRE_PEDIDO = 0.90


def precio_techo(ref_co_cop: float, envio_us_usd: float, categoria: str, trm: float, p: dict) -> float:
    """Mayor precio USD que conserva el margen objetivo con el flete supuesto de la categoría."""
    flete_cop = p["flete_supuesto_usd"].get(categoria, 0) * trm
    costo_max = ingreso_neto(ref_co_cop, p) / (1 + p["margen_objetivo"]) - flete_cop
    k = _factor_cop(trm, p) * (1 + p["arancel"]) * (1 + p["iva"])
    return costo_max / k - envio_us_usd


def proponer(precio_pedido_usd: float, techo_usd: float | None, val: ValoracionUS) -> Oferta | None:
    """techo_usd=None cuando no hay referencia en Colombia: se negocia solo contra el mercado de EE. UU."""
    retiro = val.mediana_usd if techo_usd is None else min(techo_usd, val.mediana_usd)
    retiro = min(retiro, precio_pedido_usd)
    if retiro <= 0 or retiro < BRECHA_MAXIMA * precio_pedido_usd:
        return None
    apertura = min(APERTURA_SOBRE_RETIRO * retiro, APERTURA_SOBRE_PEDIDO * precio_pedido_usd)
    return Oferta(techo_usd=techo_usd if techo_usd is not None else retiro,
                  apertura_usd=round(apertura, 2), retiro_usd=retiro)
