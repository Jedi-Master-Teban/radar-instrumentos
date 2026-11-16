"""Estructuras compartidas por toda la tubería."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

CATEGORIAS = ("guitarra", "bajo", "pedal", "cuerdas")
ESTADOS = ("nuevo", "excelente", "bueno", "regular", "para_reparar")
ESTADOS_ACEPTADOS = ("nuevo", "excelente", "bueno")  # "buenas condiciones"
ESTADOS_OPORTUNIDAD = ("nueva", "ofertada", "comprada", "descartada")
TIPOS_OPORTUNIDAD = ("reventa", "ganga")


@dataclass
class Listing:
    plataforma: str  # "ebay" | "reverb" | "facebook"
    id_externo: str
    url: str
    titulo: str
    precio_usd: float
    descripcion: str = ""
    envio_us_usd: float = 0.0
    acepta_ofertas: bool = False
    hace_envios: bool = True
    fecha_publicacion: date | None = None
    fotos: list[str] = field(default_factory=list)
    estado_declarado: str = ""


@dataclass
class Normalizado:
    marca: str
    modelo: str
    categoria: str
    estado: str
    anio: int | None = None
    defectos: list[str] = field(default_factory=list)
    modificaciones: list[str] = field(default_factory=list)
    senales_motivado: list[str] = field(default_factory=list)


@dataclass
class ValoracionUS:
    mediana_usd: float
    p25_usd: float
    p75_usd: float
    n: int
    nuevo_usd: float | None = None


@dataclass
class ReferenciaCO:
    usado_cop: float | None
    nuevo_cop: float | None
    n_usado: int
    n_nuevo: int
    fecha: date
    manual: bool = False


@dataclass
class Costo:
    base_cop: float
    arancel_cop: float
    iva_cop: float
    total_cop: float


@dataclass
class Oferta:
    techo_usd: float
    apertura_usd: float
    retiro_usd: float


@dataclass
class PrecioTienda:
    """Un precio visto en una tienda o mercado (EE. UU. o Colombia)."""
    fuente: str
    titulo: str
    precio: float  # USD o COP según el país de la fuente
    condicion: str  # "nuevo" | "usado"
    url: str = ""
