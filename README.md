# Radar de instrumentos usados (EE. UU. → Colombia)

Cada día lee eBay, Reverb y Facebook Marketplace, identifica guitarras, bajos, pedales y cuerdas en oferta,
los compara con precios usados y nuevos de EE. UU. y de Colombia, calcula el costo puesto en pesos y te avisa
por Telegram con una oferta sugerida. **Tú** envías la oferta: la herramienta solo lee.

## Puesta en marcha

```bash
cd ~/Código/radar-instrumentos
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
playwright install chromium
pytest -q                      # 95 pruebas, sin red
python -m radar web            # tablero en http://127.0.0.1:8000
```

1. En el tablero, pestaña **Ajustes**: pega tu clave de NVIDIA NIM, el token del bot de Telegram y el ID del chat.
   Se guardan en `~/.radar/.env` (permisos 600), fuera del repositorio.
2. `python -m radar modelos` lista los modelos que tu clave puede usar. Elige uno de texto, rápido, y ponlo en
   Ajustes. El valor por defecto (`meta/llama-3.3-70b-instruct`) **no está verificado** contra el catálogo actual.
3. `python -m radar probar-telegram` debe hacerte llegar un mensaje.
4. Opcional, para Facebook y MercadoLibre: `python scripts/login_facebook.py` (y luego
   `python scripts/login_facebook.py mercadolibre`). Se abre una ventana aparte; inicias sesión a mano y la
   cierras. La contraseña nunca pasa por el código.
5. En el tablero, pestaña **Correr**: lanza primero una **corrida de prueba** (1 búsqueda, 12 publicaciones por
   sitio) y mira el registro. Guardar la clave no busca nada por sí solo. En la terminal equivale a
   `python -m radar correr --prueba`; sin `--prueba` hace la corrida completa.

Corrida diaria a las 7:00: edita `deploy/com.radar.diario.plist` (reemplaza `RUTA_DEL_PROYECTO`), cópialo a
`~/Library/LaunchAgents/` y ejecuta `launchctl load ~/Library/LaunchAgents/com.radar.diario.plist`.

## Cómo decide

1. **Recolecta** publicaciones usadas con envío (eBay y Reverb: las que aceptan ofertas).
2. **Normaliza** con el modelo de NIM: marca, modelo, estado, defectos y señales de vendedor motivado.
   Solo siguen las que están en estado nuevo, excelente o bueno.
3. **Valora en EE. UU.**: mediana de precios pedidos de usados (Reverb y Guitar Center) menos 10 % de
   negociación; precio nuevo de referencia. Guitarras y bajos cuyo nuevo esté fuera de USD 600–3.500 se descartan.
4. **Valora en Colombia**: tiendas (nuevo) y, con sesión, MercadoLibre y Facebook (usado). Con 3 o más usados
   usa su mediana menos 10 %; si no, estima la reventa como 70 % del precio nuevo de tienda y lo advierte.
   Puedes fijar un precio manual por modelo en **Lista de seguimiento**.
5. **Costea**: (precio + envío interno) × (1 + impuesto a las ventas) × TRM × (1 + margen cambiario), más
   arancel e IVA. El flete internacional lo cotizas tú; la alerta muestra el **flete máximo tolerable**.
6. **Clasifica**:
   - `reventa`: existe referencia en Colombia y a un precio negociable queda el margen objetivo.
   - `ganga`: el modelo **no aparece en Colombia** pero está 30 % o más por debajo del usado de EE. UU.
     No se descarta: sirve para colección o para vender con precio propio.
   - Si el precio está por debajo de la mitad del usado de EE. UU., se marca "verifica autenticidad".
7. **Propone** apertura, techo y punto de retiro, y redacta un mensaje honesto en inglés.
8. **Avisa** las 5 mejores del día por Telegram. Todo queda en el tablero.

Todos los porcentajes y topes se editan en **Parámetros**.

## Estado de cada lector (15 nov 2026)

| Fuente | Estado |
|---|---|
| eBay (activos) | Analizador probado con la estructura real de la página. Visto desde Colombia, eBay muestra precios en COP: se convierten a USD con la TRM (aproximado), y el envío que muestra es hacia Colombia, no hacia un casillero. Los **vendidos exigen iniciar sesión** y no se leen. |
| Reverb | Probado con una respuesta real del JSON que usa su propia página. La guía de precios responde 403 y no se usa. |
| Guitar Center | Probado con datos reales de la página (JSON-LD). |
| Tiendas Shopify (Ortizo, La Colonial, TMS Music) | Probado con respuesta real de Ortizo. La Colonial y TMS Music usan la misma plataforma, sin verificar una a una. |
| Tiendas WooCommerce (Music Head Store, Duosonic) | Probado con respuesta real de Music Head Store. Duosonic sin verificar. |
| MercadoLibre Colombia | Exige iniciar sesión. Analizador **sin calibrar** con una página real. |
| Facebook Marketplace | Requiere tu sesión. Analizador **sin calibrar** con una página real. |
| Musical Cedar, AudioCentro, ProMúsica | Sin agregar: falta confirmar su sitio y plataforma. Se añaden en Parámetros → Tiendas. |
| Sweetwater | No incluida. |

La navegación real con Playwright (`radar/collectors/base.py`) **no se ha ejecutado todavía**: las pruebas usan
muestras guardadas. La primera corrida real es la verificación pendiente; si un lector devuelve cero
resultados, recibes el aviso `lector_sin_resultados` y hay que ajustar sus selectores.

## Ventana del navegador

La corrida abre una ventana visible de tu Chrome (parámetro `navegador_visible = 1`). En modo oculto, eBay y
Reverb rechazaron la primera página el 15 nov 2026. Es un navegador normal: no se altera su identificación ni se
usan proxies. Si aun así un sitio pide verificación, el lector se detiene y lo registra en Eventos.

## Ciudades de Facebook

La lista trae 24 ciudades (5 de Florida y 19 de otros estados) y se edita en Parámetros. Cada día se leen solo
`ciudades_fb_por_dia` (4 por defecto), rotando, para no multiplicar las visitas con tu cuenta. Los nombres de
ciudad siguen el formato de las direcciones de Marketplace y **no están verificados uno a uno**. eBay, Reverb y
las tiendas no dependen de la ciudad: ya cubren todo EE. UU.

## Límites que la herramienta respeta

- Solo lectura: no envía mensajes, ofertas ni formularios.
- Una sola sesión de Facebook, iniciada por ti. Sin rotación de cuentas ni de proxies, sin resolver CAPTCHA.
- Ante un bloqueo o una verificación, el lector se detiene, lo registra en **Eventos** y te avisa.
- Leer estos sitios de forma automática va contra sus términos de uso; el riesgo (bloqueo temporal de tu IP o
  restricción de la cuenta de Facebook) lo aceptaste al diseñar la herramienta.

## Estructura

```
radar/costing.py      costo puesto, margen, flete máximo
radar/offer.py        techo, apertura y retiro (el tope vive en código, no en el modelo)
radar/scoring.py      puntaje
radar/valuation.py    valoración en EE. UU. y Colombia con caché de 7 días
radar/pipeline.py     corrida diaria
radar/llm.py          cliente de NVIDIA NIM
radar/collectors/     un lector por sitio
radar/web/            tablero local
```
