"""Tablero web local. Escucha solo en 127.0.0.1."""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from .. import config, db, vistas
from ..models import ESTADOS_OPORTUNIDAD
from ..valuation import fijar_referencia_manual

ENTORNO = vistas.entorno()
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
    if prueba == "colombia":
        args = [sys.executable, "-u", "-m", "radar", "colombia"]
    else:
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

    def html(conexion, plantilla: str, activa: str, **ctx) -> HTMLResponse:
        return HTMLResponse(ENTORNO.get_template(plantilla).render(vistas.contexto(conexion, "local", activa, **ctx)))

    def problemas_de(c, ult) -> list[dict]:
        if not ult:
            return []
        previa = c.execute("select coalesce(max(id), 0) from eventos where tipo in ('corrida', 'importacion') "
                           "and id < ?", (ult["id"],)).fetchone()[0]
        vistos, salida = set(), []
        for e in c.execute("select tipo, detalle from eventos where id > ? and id < ? and tipo in "
                           "('lector_bloqueado', 'lector_error', 'lector_sin_resultados', "
                           "'modelo_respuesta_invalida', 'telegram_error')", (previa, ult["id"])):
            fuente = e["detalle"].split(":")[0][:40]
            if (e["tipo"], fuente) not in vistos:
                vistos.add((e["tipo"], fuente))
                salida.append({"tipo": e["tipo"], "fuente": fuente})
        return salida

    @app.get("/corrida", response_class=HTMLResponse)
    def ver_corrida():
        import re

        from ..capturas import CARPETA

        ruta = aj.home / "corrida.log"
        registro = "\n".join(ruta.read_text(errors="replace").splitlines()[-120:]) if ruta.exists() else ""
        c = con()
        m = re.findall(r"^\[(\d+)/(\d+)\]", registro, flags=re.M)
        p = db.parametros(c)
        return html(c, "estado.html", "estado", activa_corrida=corrida_activa(), registro=registro,
                    avance=(int(m[-1][0]), int(m[-1][1])) if m else None,
                    nim=bool(config.cargar(None).nim_api_key), problemas=problemas_de(c, vistas.ultima_actualizacion(c)),
                    capturas=vistas.capturas_info(carpeta_capturas or CARPETA), colombia=vistas.colombia_info(c),
                    tiendas=[t["nombre"] for t in p["tiendas_co"]], p=p)

    @app.post("/corrida")
    def iniciar_corrida(modo: str = Form("prueba")):
        if modo not in ("prueba", "completa", "colombia"):
            raise HTTPException(422, "Modo no válido")
        if not corrida_activa():
            (aj.home / "corrida.pid").write_text(str(lanzar(aj, "colombia" if modo == "colombia" else modo == "prueba")))
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

    @app.get("/", response_class=HTMLResponse)
    def hoy():
        c = con()
        _importar_capturas(c)
        ops = vistas.cargar_ops(c)
        dest = vistas.destacadas(ops)
        ids = {o["id"] for o in dest}
        resto = [o for o in ops if o["id"] not in ids and o["estado"] != "descartada"][:10]
        return html(c, "hoy.html", "hoy", resumen=vistas.resumen(ops), destacadas=dest, resto=resto,
                    total=len(ops), categorias=vistas.por_categoria(ops))

    @app.get("/explorar", response_class=HTMLResponse)
    def explorar():
        c = con()
        _importar_capturas(c)
        ops = vistas.cargar_ops(c)
        return html(c, "explorar.html", "explorar", ops=ops, categorias=vistas.por_categoria(ops),
                    marcas=sorted({o["normalizado"]["marca"] for o in ops}),
                    plataformas=sorted({o["listing"]["plataforma"] for o in ops}), estados=ESTADOS_OPORTUNIDAD)

    @app.get("/oportunidad/{oid}", response_class=HTMLResponse)
    def detalle(oid: int):
        c = con()
        o = next((x for x in vistas.cargar_ops(c) if x["id"] == oid), None)
        if o is None:
            raise HTTPException(404, "Oportunidad no encontrada")
        dg = o["desglose"]
        cuentas = vistas.cuentas(dg, o["flete_real_usd"]) if dg else None
        return html(c, "detalle.html", "", o=o, dg=dg, c=cuentas)

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
    def fijar_flete(oid: int, flete_real_usd: float = Form(...)):
        if flete_real_usd < 0:
            raise HTTPException(422, "El flete no puede ser negativo")
        c = con()
        _op(c, oid)
        c.execute("update oportunidades set flete_real_usd=? where id=?", (flete_real_usd, oid))
        c.commit()
        return RedirectResponse(f"/oportunidad/{oid}", status_code=303)

    @app.get("/parametros", response_class=HTMLResponse)
    def ver_parametros():
        c = con()
        p = db.parametros(c)
        return html(c, "parametros.html", "parametros", p=p, numericos=NUMERICOS,
                    tiendas_json=json.dumps(p["tiendas_co"], ensure_ascii=False, indent=1))

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
    def ver_watchlist():
        c = con()
        return html(c, "watchlist.html", "seguimiento",
                    items=c.execute("select * from watchlist order by categoria, marca").fetchall(),
                    refs=c.execute("select * from referencias_co order by marca, modelo").fetchall())

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
    def referencia_manual(request: Request, marca: str = Form(...), modelo: str = Form(...),
                          usado_cop: float = Form(...)):
        if usado_cop <= 0 or not marca.strip() or not modelo.strip():
            raise HTTPException(422, "Datos no válidos")
        c = con()
        fijar_referencia_manual(c, marca.strip(), modelo.strip(), usado_cop, date.today())
        db.set_parametro(c, "capturas_importadas", {})  # reevalúa con la nueva referencia
        _importar_capturas(c)
        volver = request.headers.get("referer") or ""
        return RedirectResponse("/oportunidad/" + volver.rsplit("/oportunidad/", 1)[1] if "/oportunidad/" in volver
                                else "/watchlist", status_code=303)

    @app.get("/ajustes", response_class=HTMLResponse)
    def ver_ajustes():
        a = config.cargar(None)
        return html(con(), "ajustes.html", "ajustes", nim=bool(a.nim_api_key), modelo=a.nim_model,
                    tg=bool(a.telegram_bot_token), chat=a.telegram_chat_id, perfil=Path(aj.perfil_fb).exists())

    @app.post("/ajustes")
    def guardar_ajustes(nim_api_key: str = Form(""), nim_model: str = Form(""), telegram_bot_token: str = Form(""),
                        telegram_chat_id: str = Form("")):
        config.guardar_secretos(aj.home, {"NIM_API_KEY": nim_api_key, "NIM_MODEL": nim_model,
                                          "TELEGRAM_BOT_TOKEN": telegram_bot_token,
                                          "TELEGRAM_CHAT_ID": telegram_chat_id})
        return RedirectResponse("/ajustes", status_code=303)

    @app.get("/eventos", response_class=HTMLResponse)
    def eventos():
        c = con()
        return html(c, "eventos.html", "", eventos=c.execute("select * from eventos order by id desc limit 200").fetchall())

    return app


def app_desde_entorno() -> FastAPI:
    """Fábrica para uvicorn con recarga automática."""
    return crear_app(config.cargar())
