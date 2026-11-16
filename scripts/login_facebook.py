"""Abre el perfil dedicado del radar para que inicies sesión a mano. No lee ni guarda contraseñas.

Uso:  python scripts/login_facebook.py            (Facebook)
      python scripts/login_facebook.py mercadolibre
"""
import sys

from playwright.sync_api import sync_playwright

from radar import config

SITIOS = {"facebook": "https://www.facebook.com/marketplace/",
          "mercadolibre": "https://www.mercadolibre.com.co/"}

if __name__ == "__main__":
    sitio = sys.argv[1] if len(sys.argv) > 1 else "facebook"
    aj = config.cargar()
    with sync_playwright() as pw:
        ctx = pw.chromium.launch_persistent_context(aj.perfil_fb, headless=False)
        pagina = ctx.pages[0] if ctx.pages else ctx.new_page()
        pagina.goto(SITIOS[sitio])
        print(f"Inicia sesión en {sitio} en la ventana que se abrió y luego CIÉRRALA para guardar la sesión.")
        try:
            pagina.wait_for_event("close", timeout=0)
        except Exception:
            pass
        ctx.close()
    print("Sesión guardada en", aj.perfil_fb)
