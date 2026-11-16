"""Puntaje de oportunidad."""
from __future__ import annotations


def _senales(senales: list[str], dias_publicado: int | None) -> float:
    k = len(senales) + (1 if dias_publicado is not None and dias_publicado >= 30 else 0)
    return 1 + 0.15 * min(k, 3)


def puntaje(margen_esperado: float, n_us: int, n_co: int, ref_manual: bool,
            senales: list[str], dias_publicado: int | None) -> float:
    """Reventa: margen validado en Colombia × confianza en ambos países × señales del vendedor."""
    conf_co = 1.0 if ref_manual else min(n_co, 5) / 5
    confianza = min(n_us, 5) / 5 * conf_co
    return max(margen_esperado, 0) * confianza * _senales(senales, dias_publicado)


def puntaje_ganga(descuento_us: float, n_us: int, senales: list[str], dias_publicado: int | None) -> float:
    """Ganga sin referencia en Colombia: descuento frente al usado de EE. UU. × confianza × señales."""
    return max(descuento_us, 0) * (min(n_us, 5) / 5) * _senales(senales, dias_publicado)
