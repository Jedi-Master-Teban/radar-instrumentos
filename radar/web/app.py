"""Tablero web local. Escucha solo en 127.0.0.1."""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from .. import config, db
from ..costing import ingreso_neto, margen
from ..models import ESTADOS_OPORTUNIDAD
from ..notify import cop, usd
from ..valuation import fijar_referencia_manual

PLANTILLAS = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))
PLANTILLAS.env.filters.update(cop=cop, usd=usd, pct=lambda x: "—" if x is None else f"{x * 100:.0f} %")
NUMERICOS = ["margen_objetivo", "arancel", "iva", "sales_tax_us", "margen_cambiario", "descuento_negociacion_co",
             "descuento_negociacion_us", "factor_usado_sobre_nuevo_co", "comision_canal", "min_refs_co",
             "min_comparables_us", "cache_co_dias", "cache_us_dias", "max_alertas_dia", "max_normalizar_dia",
             "precio_nuevo_min_usd", "precio_nuevo_max_usd", "ganga_descuento_min", "sospecha_bajo"]
ENTEROS = {"min_refs_co", "min_comparables_us", "cache_co_dias", "cache_us_dias", "max_alertas_dia",
           "max_normalizar_dia"}


def crear_app(aj: config.Ajustes) -> FastAPI:
    app = FastAPI(title="Radar de instrumentos", docs_url=None, redoc_url=None)

    @app.middleware("http")
    async def solo_formularios_propios(request: Request, call_next):
        """Rechaza envíos de formularios que vengan de otra página web (protección local básica)."""
        if request.method == "POST":
            from urllib.parse import urlparse

            origen = request.headers.get("origin") or request.headers.get("referer") or ""
            if origen and urlparse(origen).hostname not in ("127.0.0.1", "localhost", "testserver"):
                from fastapi.responses import PlainTextResponse

                return PlainTextResponse("Origen no permitido", status_code=403)
        return await call_next(request)

    def con():
        return db.conectar(aj.ruta_db)

    def _op(c, oid: int):
        f = c.execute("select * from oportunidades where id=?", (oid,)).fetchone()
        if f is None:
            raise HTTPException(404, "Oportunidad no encontrada")
        return f

    @app.get("/", response_class=HTMLResponse)
    def lista(request: Request, plataforma: str = "", marca: str = "", tipo: str = "", estado: str = "nueva"):
        c = con()
        ops = []
        for f in c.execute("select * from oportunidades order by puntaje desc"):
            d = json.loads(f["datos"])
            if plataforma and d["listing"]["plataforma"] != plataforma:
                continue
            if marca and d["normalizado"]["marca"].lower() != marca.lower():
                continue
            if tipo and f["tipo"] != tipo or estado and f["estado"] != estado:
                continue
            ops.append({"id": f["id"], "tipo": f["tipo"], "puntaje": f["puntaje"], "estado": f["estado"], **d})
        marcas = sorted({json.loads(r[0])["normalizado"]["marca"] for r in c.execute("select datos from oportunidades")})
        return PLANTILLAS.TemplateResponse(request, "lista.html", {
            "ops": ops, "marcas": marcas, "f": dict(plataforma=plataforma, marca=marca, tipo=tipo, estado=estado),
            "estados": ESTADOS_OPORTUNIDAD})

    @app.get("/oportunidad/{oid}", response_class=HTMLResponse)
    def detalle(request: Request, oid: int):
        c = con()
        f = _op(c, oid)
        d = json.loads(f["datos"])
        p = db.parametros(c)
        real = None
        if f["flete_real_cop"] is not None and d.get("precio_co_cop"):
            from ..costing import costo_puesto
            costo_retiro = costo_puesto(d["oferta"]["retiro_usd"], d["listing"]["envio_us_usd"], d["trm"], p)
            real = margen(ingreso_neto(d["precio_co_cop"], p), costo_retiro.total_cop, f["flete_real_cop"])
        return PLANTILLAS.TemplateResponse(request, "detalle.html", {
            "o": {"id": f["id"], "tipo": f["tipo"], "puntaje": f["puntaje"], "estado": f["estado"], **d},
            "flete_real": f["flete_real_cop"], "margen_real": real, "estados": ESTADOS_OPORTUNIDAD})

    @app.post("/oportunidad/{oid}/estado")
    def cambiar_estado(oid: int, estado: str = Form(...)):
        if estado not in ESTADOS_OPORTUNIDAD:
            raise HTTPException(422, "Estado no válido")
        c = con()
        _op(c, oid)
        c.execute("update oportunidades set estado=? where id=?", (estado, oid))
        c.commit()
        return RedirectResponse(f"/oportunidad/{oid}", status_code=303)

    @app.post("/oportunidad/{oid}/flete")
    def fijar_flete(oid: int, flete_real_cop: float = Form(...)):
        if flete_real_cop < 0:
            raise HTTPException(422, "El flete no puede ser negativo")
        c = con()
        _op(c, oid)
        c.execute("update oportunidades set flete_real_cop=? where id=?", (flete_real_cop, oid))
        c.commit()
        return RedirectResponse(f"/oportunidad/{oid}", status_code=303)

    @app.get("/parametros", response_class=HTMLResponse)
    def ver_parametros(request: Request):
        p = db.parametros(con())
        return PLANTILLAS.TemplateResponse(request, "parametros.html", {
            "p": p, "numericos": NUMERICOS, "tiendas_json": json.dumps(p["tiendas_co"], ensure_ascii=False, indent=1)})

    @app.post("/parametros")
    async def guardar_parametros(request: Request):
        form = await request.form()
        c = con()
        try:
            for k in NUMERICOS:
                if k in form and str(form[k]).strip() != "":
                    v = float(str(form[k]).replace(",", "."))
                    if v < 0:
                        raise ValueError(k)
                    db.set_parametro(c, k, int(v) if k in ENTEROS else v)
            if str(form.get("trm_manual", "")).strip():
                db.set_parametro(c, "trm_manual", float(form["trm_manual"]))
            fletes = {cat: float(form[f"flete_{cat}"]) for cat in ("guitarra", "bajo", "pedal", "cuerdas")
                      if str(form.get(f"flete_{cat}", "")).strip()}
            if fletes:
                db.set_parametro(c, "flete_supuesto_usd", db.parametros(c)["flete_supuesto_usd"] | fletes)
            if str(form.get("ciudades_fb", "")).strip():
                db.set_parametro(c, "ciudades_fb", [x.strip().lower() for x in str(form["ciudades_fb"]).split(",") if x.strip()])
            if str(form.get("tiendas_co", "")).strip():
                tiendas = json.loads(str(form["tiendas_co"]))
                for t in tiendas:
                    if t["plataforma"] not in ("shopify", "woocommerce") or not str(t["origen"]).startswith("https://"):
                        raise ValueError("tienda")
                    t["nombre"] = str(t["nombre"])
                db.set_parametro(c, "tiendas_co", tiendas)
        except (ValueError, KeyError, TypeError) as e:
            raise HTTPException(422, f"Valor no válido: {e}")
        return RedirectResponse("/parametros", status_code=303)

    @app.get("/watchlist", response_class=HTMLResponse)
    def ver_watchlist(request: Request):
        c = con()
        return PLANTILLAS.TemplateResponse(request, "watchlist.html", {
            "items": c.execute("select * from watchlist order by categoria, marca").fetchall(),
            "refs": c.execute("select * from referencias_co order by marca, modelo").fetchall()})

    @app.post("/watchlist")
    def agregar(categoria: str = Form(...), marca: str = Form(...), consulta: str = Form(...)):
        if categoria not in ("guitarra", "bajo", "pedal", "cuerdas") or not consulta.strip():
            raise HTTPException(422, "Datos no válidos")
        c = con()
        c.execute("insert or ignore into watchlist(categoria, marca, consulta) values(?,?,?)",
                  (categoria, marca.strip(), consulta.strip()))
        c.commit()
        return RedirectResponse("/watchlist", status_code=303)

    @app.post("/watchlist/{wid}/activo")
    def alternar(wid: int):
        c = con()
        c.execute("update watchlist set activo = 1 - activo where id=?", (wid,))
        c.commit()
        return RedirectResponse("/watchlist", status_code=303)

    @app.post("/referencia")
    def referencia_manual(marca: str = Form(...), modelo: str = Form(...), usado_cop: float = Form(...)):
        if usado_cop <= 0 or not marca.strip() or not modelo.strip():
            raise HTTPException(422, "Datos no válidos")
        fijar_referencia_manual(con(), marca.strip(), modelo.strip(), usado_cop, date.today())
        return RedirectResponse("/watchlist", status_code=303)

    @app.get("/ajustes", response_class=HTMLResponse)
    def ver_ajustes(request: Request):
        a = config.cargar(None)
        return PLANTILLAS.TemplateResponse(request, "ajustes.html", {
            "nim": bool(a.nim_api_key), "modelo": a.nim_model, "tg": bool(a.telegram_bot_token),
            "chat": a.telegram_chat_id, "perfil": Path(aj.perfil_fb).exists()})

    @app.post("/ajustes")
    def guardar_ajustes(nim_api_key: str = Form(""), nim_model: str = Form(""), telegram_bot_token: str = Form(""),
                        telegram_chat_id: str = Form("")):
        config.guardar_secretos(aj.home, {"NIM_API_KEY": nim_api_key, "NIM_MODEL": nim_model,
                                          "TELEGRAM_BOT_TOKEN": telegram_bot_token,
                                          "TELEGRAM_CHAT_ID": telegram_chat_id})
        return RedirectResponse("/ajustes", status_code=303)

    @app.get("/eventos", response_class=HTMLResponse)
    def eventos(request: Request):
        filas = con().execute("select * from eventos order by id desc limit 200").fetchall()
        return PLANTILLAS.TemplateResponse(request, "eventos.html", {"eventos": filas})

    return app
