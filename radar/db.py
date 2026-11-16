"""Esquema SQLite y acceso a datos."""
from __future__ import annotations

import json
import sqlite3
from datetime import date, datetime

from .models import Listing

PARAMETROS_DEFECTO: dict = {
    "arancel": 0.10,
    "iva": 0.19,
    "sales_tax_us": 0.07,
    "margen_cambiario": 0.015,
    "descuento_negociacion_co": 0.10,
    "comision_canal": 0.0,
    "min_refs_co": 3,
    "cache_co_dias": 7,
    "cache_us_dias": 7,
    "margen_objetivo": 0.25,
    "max_alertas_dia": 5,
    "flete_supuesto_usd": {"guitarra": 120, "bajo": 120, "pedal": 25, "cuerdas": 15},
    "precio_nuevo_min_usd": 600,
    "precio_nuevo_max_usd": 3500,
    "ganga_descuento_min": 0.30,
    "sospecha_bajo": 0.50,
    "descuento_negociacion_us": 0.10,
    "factor_usado_sobre_nuevo_co": 0.70,
    "min_comparables_us": 3,
    "max_normalizar_dia": 200,
    "trm_manual": None,
    "ciudades_fb": ["miami", "houston", "dallas", "atlanta", "nyc", "la"],
}

WATCHLIST_SEMILLA = [
    ("guitarra", "Gibson", "Gibson electric guitar"),
    ("guitarra", "Fender", "Fender electric guitar"),
    ("guitarra", "Jackson", "Jackson electric guitar"),
    ("guitarra", "PRS", "PRS electric guitar"),
    ("guitarra", "Strandberg", "Strandberg guitar"),
    ("guitarra", "Schecter", "Schecter electric guitar"),
    ("guitarra", "Ernie Ball Music Man", "Ernie Ball Music Man guitar"),
    ("guitarra", "Epiphone", "Epiphone electric guitar"),
    ("bajo", "Gibson", "Gibson bass"),
    ("bajo", "Fender", "Fender bass"),
    ("bajo", "Jackson", "Jackson bass"),
    ("bajo", "Schecter", "Schecter bass"),
    ("bajo", "Ernie Ball Music Man", "Ernie Ball Music Man bass"),
    ("bajo", "Epiphone", "Epiphone bass"),
    ("pedal", "Dunlop", "Dunlop Cry Baby wah"),
    ("pedal", "Vox", "Vox V847 wah"),
    ("pedal", "Boss", "Boss DS-1"),
    ("pedal", "Boss", "Boss SD-1"),
    ("pedal", "Ibanez", "Ibanez TS9 Tube Screamer"),
    ("pedal", "ProCo", "ProCo RAT 2"),
    ("pedal", "Electro-Harmonix", "EHX Big Muff Pi"),
    ("pedal", "Dunlop", "Dunlop Fuzz Face"),
    ("pedal", "Boss", "Boss DD-3"),
    ("cuerdas", "D'Addario", "D'Addario EXL110 10-pack"),
    ("cuerdas", "Ernie Ball", "Ernie Ball 2221 12-pack"),
]

ESQUEMA = """
create table if not exists listings(
  id integer primary key, plataforma text not null, id_externo text not null,
  url text, titulo text, descripcion text, precio_usd real, envio_us_usd real,
  acepta_ofertas integer, hace_envios integer, fecha_publicacion text, fotos text,
  estado_declarado text, primera_vez text, ultima_vez text, proceso text default 'pendiente',
  unique(plataforma, id_externo));
create table if not exists historial_precios(
  id integer primary key, listing_id integer not null, precio_usd real, fecha text);
create table if not exists normalizados(listing_id integer primary key, datos text);
create table if not exists referencias_co(
  id integer primary key, marca text, modelo text, usado_cop real, nuevo_cop real,
  n_usado integer, n_nuevo integer, fecha text, manual integer default 0, detalle text,
  unique(marca, modelo));
create table if not exists referencias_us(
  id integer primary key, marca text, modelo text, datos text, fecha text, detalle text,
  unique(marca, modelo));
create table if not exists oportunidades(
  id integer primary key, listing_id integer unique, tipo text, puntaje real,
  datos text, estado text default 'nueva', creada text, alertada integer default 0,
  flete_real_cop real);
create table if not exists parametros(clave text primary key, valor text);
create table if not exists watchlist(
  id integer primary key, categoria text, marca text, consulta text unique, activo integer default 1);
create table if not exists eventos(id integer primary key, fecha text, tipo text, detalle text);
"""


def conectar(ruta: str) -> sqlite3.Connection:
    con = sqlite3.connect(ruta)
    con.row_factory = sqlite3.Row
    con.executescript(ESQUEMA)
    for clave, valor in PARAMETROS_DEFECTO.items():
        con.execute("insert or ignore into parametros(clave, valor) values(?, ?)", (clave, json.dumps(valor)))
    if con.execute("select count(*) from watchlist").fetchone()[0] == 0:
        con.executemany("insert into watchlist(categoria, marca, consulta) values(?, ?, ?)", WATCHLIST_SEMILLA)
    con.commit()
    return con


def parametros(con) -> dict:
    return {r["clave"]: json.loads(r["valor"]) for r in con.execute("select clave, valor from parametros")}


def set_parametro(con, clave: str, valor) -> None:
    con.execute(
        "insert into parametros(clave, valor) values(?, ?) on conflict(clave) do update set valor=excluded.valor",
        (clave, json.dumps(valor)),
    )
    con.commit()


def guardar_listing(con, l: Listing, hoy: date | None = None) -> tuple[int, bool]:
    """Inserta o actualiza. Devuelve (id, True si es nuevo o cambió de precio)."""
    hoy_s = (hoy or date.today()).isoformat()
    fila = con.execute(
        "select id, precio_usd from listings where plataforma=? and id_externo=?", (l.plataforma, l.id_externo)
    ).fetchone()
    if fila is None:
        cur = con.execute(
            "insert into listings(plataforma, id_externo, url, titulo, descripcion, precio_usd, envio_us_usd,"
            " acepta_ofertas, hace_envios, fecha_publicacion, fotos, estado_declarado, primera_vez, ultima_vez)"
            " values(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (l.plataforma, l.id_externo, l.url, l.titulo, l.descripcion, l.precio_usd, l.envio_us_usd,
             int(l.acepta_ofertas), int(l.hace_envios),
             l.fecha_publicacion.isoformat() if l.fecha_publicacion else None,
             json.dumps(l.fotos), l.estado_declarado, hoy_s, hoy_s),
        )
        con.execute("insert into historial_precios(listing_id, precio_usd, fecha) values(?,?,?)",
                    (cur.lastrowid, l.precio_usd, hoy_s))
        con.commit()
        return cur.lastrowid, True
    cambio = abs(fila["precio_usd"] - l.precio_usd) > 0.005
    con.execute("update listings set ultima_vez=?, precio_usd=?, envio_us_usd=?, titulo=?, url=? where id=?",
                (hoy_s, l.precio_usd, l.envio_us_usd, l.titulo, l.url, fila["id"]))
    if cambio:
        con.execute("insert into historial_precios(listing_id, precio_usd, fecha) values(?,?,?)",
                    (fila["id"], l.precio_usd, hoy_s))
        con.execute("update listings set proceso='pendiente' where id=?", (fila["id"],))
    con.commit()
    return fila["id"], cambio


def rebajas(con, listing_id: int) -> int:
    """Cuántas veces bajó de precio la publicación."""
    precios = [r[0] for r in con.execute(
        "select precio_usd from historial_precios where listing_id=? order by id", (listing_id,))]
    return sum(1 for a, b in zip(precios, precios[1:]) if b < a)


def evento(con, tipo: str, detalle: str) -> None:
    con.execute("insert into eventos(fecha, tipo, detalle) values(?,?,?)",
                (datetime.now().isoformat(timespec="seconds"), tipo, detalle))
    con.commit()
