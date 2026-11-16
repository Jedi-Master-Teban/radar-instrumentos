"""Cliente del modelo de NVIDIA NIM (endpoint compatible con OpenAI).

El modelo solo lee y redacta: identifica el artículo y escribe el mensaje. Los precios tope se calculan en código.
"""
from __future__ import annotations

import json
import re

from .config import NIM_BASE_URL
from .models import CATEGORIAS, ESTADOS, Listing, Normalizado, Oferta, ValoracionUS

MODELO_DEFECTO = "meta/llama-3.3-70b-instruct"  # confirmar con `python -m radar modelos`

_SIS_NORMALIZAR = (
    "Eres un experto en instrumentos musicales usados. Devuelve SOLO un objeto JSON con las claves: "
    'marca (string), modelo (string, serie y modelo sin color ni año, p. ej. "Player Stratocaster"), '
    "anio (entero o null), categoria (una de: guitarra, bajo, pedal, cuerdas), "
    "estado (una de: nuevo, excelente, bueno, regular, para_reparar), defectos (lista de strings), "
    "modificaciones (lista de strings), senales_motivado (lista con frases literales del texto que indiquen "
    'urgencia por vender, p. ej. "must sell", "OBO", "moving", "price drop"; vacía si no hay). '
    "Usa solo lo que dice el texto; no inventes defectos. Si es una pieza suelta (mástil, cuerpo, pastillas) "
    "o no es un instrumento completo, usa estado para_reparar."
)
_SIS_MISMO = (
    "Te doy un artículo objetivo y una lista numerada de títulos de publicaciones. Devuelve SOLO un arreglo JSON "
    "de booleanos, uno por título y en el mismo orden: true si el título es el MISMO modelo completo "
    "(misma marca, serie y modelo; el color y el año pueden variar), false si es otra serie, una copia, "
    "un accesorio, un repuesto o un paquete distinto."
)
_SIS_MENSAJE = (
    "Write a short, polite message in English from a buyer to a private seller making one offer. "
    "Maximum 80 words. State the offer amount exactly as given. Mention the comparable range given as the reason. "
    "Mention only defects the listing itself states. Never claim other buyers, other offers, or urgency that "
    "was not given. No emojis. Output only the message."
)
_PROHIBIDO = re.compile(r"another buyer|other buyers?|other offers?|someone else", re.I)


def _extraer_json(texto: str):
    texto = re.sub(r"^```(?:json)?|```$", "", (texto or "").strip(), flags=re.M).strip()
    try:
        return json.loads(texto)
    except ValueError:
        m = re.search(r"(\{.*\}|\[.*\])", texto, re.S)
        if m:
            try:
                return json.loads(m.group(1))
            except ValueError:
                return None
    return None


class Modelo:
    def __init__(self, cliente=None, modelo: str = "", api_key: str = ""):
        if cliente is None:
            from openai import OpenAI

            cliente = OpenAI(base_url=NIM_BASE_URL, api_key=api_key)
        self.cliente, self.modelo = cliente, modelo or MODELO_DEFECTO

    def _chat(self, sistema: str, usuario: str, max_tokens: int = 500) -> str:
        r = self.cliente.chat.completions.create(
            model=self.modelo, temperature=0, max_tokens=max_tokens,
            messages=[{"role": "system", "content": sistema}, {"role": "user", "content": usuario}],
        )
        return r.choices[0].message.content or ""

    def normalizar(self, titulo: str, descripcion: str) -> Normalizado | None:
        usuario = f"TÍTULO: {titulo}\nDESCRIPCIÓN: {(descripcion or '')[:1500]}"
        for _ in range(2):  # un reintento ante JSON inválido
            try:
                d = _extraer_json(self._chat(_SIS_NORMALIZAR, usuario))
            except Exception:
                d = None
            n = self._validar(d)
            if n is not None:
                return n
        return None

    @staticmethod
    def _validar(d) -> Normalizado | None:
        if not isinstance(d, dict):
            return None
        marca, modelo = str(d.get("marca") or "").strip(), str(d.get("modelo") or "").strip()
        if not marca or not modelo or d.get("categoria") not in CATEGORIAS or d.get("estado") not in ESTADOS:
            return None
        anio = d.get("anio")
        lista = lambda k: [str(x) for x in d.get(k) or [] if x] if isinstance(d.get(k) or [], list) else []
        return Normalizado(marca=marca, modelo=modelo, categoria=d["categoria"], estado=d["estado"],
                           anio=anio if isinstance(anio, int) and 1930 <= anio <= 2100 else None,
                           defectos=lista("defectos"), modificaciones=lista("modificaciones"),
                           senales_motivado=lista("senales_motivado"))

    def mismo_articulo(self, objetivo: Normalizado, candidatos: list[str]) -> list[bool]:
        if not candidatos:
            return []
        usuario = (f"OBJETIVO: {objetivo.marca} {objetivo.modelo} ({objetivo.categoria})\nTÍTULOS:\n"
                   + "\n".join(f"{i + 1}. {t[:160]}" for i, t in enumerate(candidatos)))
        try:
            r = _extraer_json(self._chat(_SIS_MISMO, usuario, max_tokens=400))
        except Exception:
            r = None
        if not isinstance(r, list) or len(r) != len(candidatos):
            return [False] * len(candidatos)  # ante la duda, no se usa el comparable
        return [x is True for x in r]

    def mensaje_oferta(self, l: Listing, n: Normalizado, o: Oferta, val: ValoracionUS) -> str:
        respaldo = (f"Hi! I'm interested in your {n.marca} {n.modelo}. Similar used ones are listed around "
                    f"${val.p25_usd:,.0f}-${val.p75_usd:,.0f}. Would you accept ${o.apertura_usd:,.0f}? "
                    "I can pay right away. Thanks!")
        usuario = (f"Item: {l.titulo}\nAsking price: ${l.precio_usd:,.0f}\nOffer amount: ${o.apertura_usd:,.0f}\n"
                   f"Comparable used range: ${val.p25_usd:,.0f}-${val.p75_usd:,.0f} ({val.n} listings)\n"
                   f"Defects stated in listing: {', '.join(n.defectos) or 'none'}")
        try:
            texto = self._chat(_SIS_MENSAJE, usuario, max_tokens=200).strip()
        except Exception:
            return respaldo
        if not texto or _PROHIBIDO.search(texto) or f"{o.apertura_usd:,.0f}" not in texto:
            return respaldo
        return texto
