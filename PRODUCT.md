# PRODUCT.md · Radar de instrumentos

**Qué es:** un radar que encuentra guitarras, bajos, pedales y cuerdas usados en EE. UU. (Reverb y eBay) para comprarlos negociando y revenderlos en Bogotá por WhatsApp y contactos.

**Para quién:** Esteban, que compra y decide, y su vendedor en Bogotá, que cobra una comisión del 0, 5 o 10 %.

**Escena de uso:** a las 7 a. m. llega el aviso de la tarea diaria. Primero se revisa en el móvil y luego se decide en el portátil.

**La pregunta de la pantalla:** ¿qué ofertar hoy, hasta cuánto, y cuánto me deja neto en pesos y en dólares?

**Restricciones:**
- **Alojamiento:** sitio estático en GitHub Pages, armado con Jinja2 y con poco JavaScript.
- **Captura:** la hace Claude cada día en el navegador integrado del Mac del usuario.
- **Solo lectura en las plataformas:** las ofertas las envía el usuario.

**Las cuentas** (en `radar/costing.py`, con una copia en el navegador en `_cuentas.js`):

```
costo puesto (USD)  = precio + envío en EE. UU.
                    + impuesto de ventas de EE. UU. (7 %)
                    + flete del casillero (US$200 por guitarra) + seguro (3,5 %, mínimo US$10) + inspección (US$10)
                    + recargo de la tarjeta (1,5 % de todo lo anterior)
                    + arancel 10 % e IVA 19 % sobre (producto + flete + seguro)
                    + ajuste del luthier ($150.000 en guitarras y bajos)
neto (COP)          = cierre esperado en Bogotá × (1 − comisión) − costo puesto
techo (USD)         = mayor precio pedido que deja el 25 % neto después de la comisión
piso (COP)          = costo puesto pagando el techo × 1,25 ÷ (1 − comisión)
```

Todo en COP se convierte a USD con la TRM del día (datos.gov.co).
