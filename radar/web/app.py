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
             "ciudades_fb_por_dia", "navegador_visible",
             "precio_nuevo_min_usd", "precio_nuevo_max_usd", "ganga_descuento_min", "sospecha_bajo"]
ENTEROS = {"ciudades_fb_por_dia", "navegador_visible", "min_refs_co", "min_comparables_us", "cache_co_dias", "cache_us_dias", "max_alertas_dia",
           "max_normalizar_dia"}


def _lanzar_corrida(aj: config.Ajustes, prueba: bool) -> int:
    """Arranca `python -m radar correr` en segundo plano; la salida va a ~/.radar/corrida.log."""
    import subprocess
    import sys

    raiz = Path(__file__).resolve().parents[2]
    args = [sys.executable, "-u", "-m", "radar", "correr"] + (["--prueba"] if prueba else [])
    with open(aj.home / "corrida.log", "w") as salida:
        proc = subprocess.Popen(args, cwd=raiz, stdout=salida, stderr=subprocess.STDOUT, start_new_session=True)
    return proc.pid


def _vivo(pid: int) -> bool:
    import os

    try:
        terminado, _ = os.waitpid(pid, os.WNOHANG)  # recoge el proceso si ya terminó (evita "zombis")
        if terminado == pid:
            return False
    except ChildProcessError:
        pass  # no es hijo de este proceso (p. ej. tras recargar el tablero)
    except OSError:
        return False
    try:
        os.kill(pid, 0)
        return True
    except (OSError, ValueError):
        return False


def crear_app(aj: config.Ajustes, lanzar=_lanzar_corrida, vivo=_vivo, carpeta_capturas=None) -> FastAPI:
    app = FastAPI(title="Radar de instrumentos", docs_url=None, redoc_url=None)

    def corrida_activa() -> bool:
        ruta = aj.home / "corrida.pid"
        try:
            return vivo(int(ruta.read_text()))
        except (OSError, ValueError):
            return False

    @app.get("/corrida", response_class=HTMLResponse)
    def ver_corrida(request: Request):
        ruta = aj.home / "corrida.log"
        registro = "\n".join(ruta.read_text(errors="replace").splitlines()[-120:]) if ruta.exists() else ""
        c = con()
        ult = c.execute("select id, fecha, tipo, detalle from eventos where tipo in ('corrida', 'importacion') "
                        "order by id desc limit 1").fetchone()
        resumen, problemas = None, []
        if ult:
            try:
                resumen = json.loads(ult["detalle"]) | {"fecha": ult["fecha"], "origen": ult["tipo"]}
            except ValueError:
                resumen = None
            previa = c.execute("select coalesce(max(id), 0) from eventos where tipo in ('corrida', 'importacion') "
                               "and id < ?", (ult["id"],)).fetchone()[0]
            vistos = set()
            for e in c.execute("select tipo, detalle from eventos where id > ? and id < ? and tipo in "
                               "('lector_bloqueado', 'lector_error', 'lector_sin_resultados', "
                               "'modelo_respuesta_invalida', 'telegram_error')", (previa, ult["id"])):
                fuente = e["detalle"].split(":")[0][:40]
                if (e["tipo"], fuente) not in vistos:
                    vistos.add((e["tipo"], fuente))
                    problemas.append({"tipo": e["tipo"], "fuente": fuente})
        avance = None
        if registro:
            import re
            m = re.findall(r"^\[(\d+)/(\d+)\]", registro, flags=re.M)
            if m:
                avance = (int(m[-1][0]), int(m[-1][1]))
        return PLANTILLAS.TemplateResponse(request, "corrida.html", {
            "activa": corrida_activa(), "registro": registro, "nim": bool(config.cargar(None).nim_api_key),
            "resumen": resumen, "problemas": problemas, "avance": avance})

    @app.post("/corrida")
    def iniciar_corrida(modo: str = Form("prueba")):
        if modo not in ("prueba", "completa"):
            raise HTTPException(422, "Modo no válido")
        if not corrida_activa():
            (aj.home / "corrida.pid").write_text(str(lanzar(aj, modo == "prueba")))
        return RedirectResponse("/corrida", status_code=303)

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

    def _importar_capturas(c) -> None:
        """Si hay capturas nuevas en datos/capturas/, las evalúa antes de mostrar la lista."""
        from ..capturas import CARPETA, importar
        from ..trm import trm_del_dia

        carpeta = carpeta_capturas or CARPETA
        try:
            if not any(carpeta.glob("*.json")):
                return
            hoy = date.today()
            importar(c, carpeta, trm_del_dia(c, hoy), hoy)
        except Exception as e:  # el tablero nunca debe caerse por una captura
            db.evento(c, "importacion_error", f"{type(e).__name__}: {e}")

    ORDEN_TIPO = {"reventa": 0, "ganga": 1, "observacion": 2}
    NOMBRE_CATEGORIA = {"guitarra": "Guitarras", "bajo": "Bajos", "pedal": "Pedales", "cuerdas": "Cuerdas"}

    @app.get("/", response_class=HTMLResponse)
    def lista(request: Request, plataforma: str = "", marca: str = "", tipo: str = "", estado: str = "nueva",
              ver: str = "todas"):
        c = con()
        _importar_capturas(c)
        ops, todas = [], []
        for f in c.execute("select * from oportunidades"):
            d = json.loads(f["datos"])
            o = {"id": f["id"], "tipo": f["tipo"], "puntaje": f["puntaje"], "estado": f["estado"], **d}
            todas.append(o)
            if plataforma and d["listing"]["plataforma"] != plataforma:
                continue
            if marca and d["normalizado"]["marca"].lower() != marca.lower():
                continue
            if tipo and f["tipo"] != tipo or estado and f["estado"] != estado:
                continue
            if ver == "oportunidades" and f["tipo"] == "observacion":
                continue
            ops.append(o)
        ops.sort(key=lambda o: (ORDEN_TIPO.get(o["tipo"], 9), -o["puntaje"], -bool(o.get("prioritario")),
                                o.get("descuento_us") is None, -(o.get("descuento_us") or 0)))
        grupos = [(NOMBRE_CATEGORIA[cat], [o for o in ops if o["normalizado"]["categoria"] == cat])
                  for cat in NOMBRE_CATEGORIA]
        vivas = [o for o in todas if o["estado"] == "nueva"]
        resumen = {
            "reventa": sum(o["tipo"] == "reventa" for o in vivas),
            "ganga": sum(o["tipo"] == "ganga" for o in vivas),
            "bajo": sum(o["tipo"] == "observacion" and (o.get("descuento_us") or 0) >= 0.10 for o in vivas),
            "evaluadas": len(vivas),
            "prioritarias": sum(bool(o.get("prioritario")) for o in vivas),
        }
        ultima = c.execute("select fecha from eventos where tipo in ('corrida', 'importacion') "
                           "order by id desc limit 1").fetchone()
        return PLANTILLAS.TemplateResponse(request, "lista.html", {
            "grupos": [g for g in grupos if g[1]], "total": len(ops), "resumen": resumen,
            "marcas": sorted({o["normalizado"]["marca"] for o in todas}),
            "plataformas": sorted({o["listing"]["plataforma"] for o in todas}),
            "f": dict(plataforma=plataforma, marca=marca, tipo=tipo, estado=estado, ver=ver),
            "estados": ESTADOS_OPORTUNIDAD, "ultima": ultima["fecha"] if ultima else None,
            "corridas": c.execute("select count(*) from eventos where tipo in ('corrida', 'importacion')").fetchone()[0]})

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
            if "palabras_prioritarias" in form:
                db.set_parametro(c, "palabras_prioritarias",
                                 [x.strip().lower() for x in str(form["palabras_prioritarias"]).split(",") if x.strip()])
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


def app_desde_entorno() -> FastAPI:
    """Fábrica para uvicorn con recarga automática."""
    return crear_app(config.cargar())
