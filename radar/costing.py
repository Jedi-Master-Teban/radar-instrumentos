"""Costo puesto en Colombia, margen y flete máximo. Funciones puras."""
from __future__ import annotations

from .models import Costo


def _factor_cop(trm: float, p: dict) -> float:
    """COP por cada USD de precio+envío, antes de impuestos colombianos."""
    return (1 + p["sales_tax_us"]) * trm * (1 + p["margen_cambiario"])


def costo_puesto(precio_usd: float, envio_us_usd: float, trm: float, p: dict) -> Costo:
    base = (precio_usd + envio_us_usd) * _factor_cop(trm, p)
    arancel = base * p["arancel"]
    iva = (base + arancel) * p["iva"]
    return Costo(base_cop=base, arancel_cop=arancel, iva_cop=iva, total_cop=base + arancel + iva)


def ingreso_neto(ref_co_cop: float, p: dict) -> float:
    return ref_co_cop * (1 - p["comision_canal"])


def margen(ingreso_cop: float, costo_cop: float, flete_cop: float) -> float:
    total = costo_cop + flete_cop
    if total <= 0:
        return 0.0
    return (ingreso_cop - total) / total


def flete_maximo(ingreso_cop: float, costo_cop: float, p: dict) -> float:
    """Flete (COP) que deja exactamente el margen objetivo. Negativo = no hay margen."""
    return ingreso_cop / (1 + p["margen_objetivo"]) - costo_cop
