"""Precio techo, oferta de apertura y punto de retiro. El tope vive en código, no en el modelo."""
from __future__ import annotations

from .models import Oferta, ValoracionUS

BRECHA_MAXIMA = 0.60  # si el retiro queda por debajo del 60 % del precio pedido, no se propone
APERTURA_SOBRE_RETIRO = 0.85
APERTURA_SOBRE_PEDIDO = 0.90


def proponer(precio_pedido_usd: float, techo_usd: float | None, val: ValoracionUS) -> Oferta | None:
    """techo_usd=None cuando no hay referencia en Colombia: se negocia solo contra el mercado de EE. UU."""
    retiro = val.mediana_usd if techo_usd is None else min(techo_usd, val.mediana_usd)
    retiro = min(retiro, precio_pedido_usd)
    if retiro <= 0 or retiro < BRECHA_MAXIMA * precio_pedido_usd:
        return None
    apertura = min(APERTURA_SOBRE_RETIRO * retiro, APERTURA_SOBRE_PEDIDO * precio_pedido_usd)
    return Oferta(techo_usd=techo_usd if techo_usd is not None else retiro,
                  apertura_usd=round(apertura, 2), retiro_usd=retiro)
