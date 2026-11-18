/* Copia en el navegador de radar/costing.py y vistas.cuentas: cada cifra en USD y en COP.
   Una prueba (tests/test_sitio.py) verifica con Node que da lo mismo que Python. */
function costoRadar(dg, precio, flete) {
  var producto = precio + dg.envio, imp = producto * dg.sales_tax_us;
  var seguro = Math.max(dg.seguro_pct * producto, dg.seguro_min_usd);
  var logistica = flete + seguro + dg.inspeccion_usd;
  var recargo = (producto + imp + logistica) * dg.margen_cambiario;
  var cif = producto + flete + seguro, arancel = cif * dg.arancel, iva = (cif + arancel) * dg.iva;
  var filas = [['Precio y envío en EE. UU.', producto], ['Impuesto de ventas en EE. UU.', imp],
    ['Flete, seguro e inspección', logistica], ['Recargo de la tarjeta', recargo], ['Arancel', arancel], ['IVA', iva],
    ['Ajuste del luthier', dg.ajuste_cop / dg.trm]];
  var lineas = filas.map(function (f) { return {concepto: f[0], usd: f[1], cop: f[1] * dg.trm}; });
  lineas[lineas.length - 1].cop = dg.ajuste_cop;
  var total = lineas.reduce(function (a, l) { return a + l.cop; }, 0);
  return {lineas: lineas, total_cop: total, total_usd: total / dg.trm};
}
function ventaRadar(ref, costo, com) {
  var c = ref * com, neto = ref - c - costo.total_cop;
  return {comision_cop: c, neto_cop: neto, margen: costo.total_cop > 0 ? neto / costo.total_cop : 0};
}
function biseccionRadar(f, lo, hi) {
  if (f(lo) < 0) return lo - 1;
  for (var i = 0; i < 80; i++) { var mid = (lo + hi) / 2; if (f(mid) >= 0) lo = mid; else hi = mid; }
  return lo;
}
function cuentasRadar(dg, flete, ref, com) {
  if (flete === null || flete === undefined) flete = dg.flete;
  if (ref === null || ref === undefined) ref = dg.ref;
  if (com === null || com === undefined) com = dg.comision;
  var trm = dg.trm;
  var techo = biseccionRadar(function (x) { return ventaRadar(ref, costoRadar(dg, x, flete), com).margen - dg.mo; }, 0, 50000);
  var retiro = Math.min(techo, dg.mediana, dg.pedido), hay = retiro > 0 && retiro >= dg.brecha * dg.pedido;
  var compra = hay ? retiro : dg.pedido;
  var apertura = hay ? Math.min(dg.apertura_sobre_retiro * retiro, dg.apertura_sobre_pedido * dg.pedido) : null;
  var c = costoRadar(dg, compra, flete), v = ventaRadar(ref, c, com);
  var cp = costoRadar(dg, dg.pedido, flete), vp = ventaRadar(ref, cp, com);
  var va = apertura ? ventaRadar(ref, costoRadar(dg, apertura, flete), com) : null;
  var lista = ref / (1 - dg.regateo), piso = c.total_cop * (1 + dg.mo) / (1 - com);
  var fmax = biseccionRadar(function (x) { return ventaRadar(ref, costoRadar(dg, compra, x), com).margen - dg.mo; }, 0, 50000);
  return {techo: techo, retiro: hay ? retiro : null, apertura: apertura, compra: compra, hay_oferta: hay, comision: com,
    flete: flete, ref: ref, lineas: c.lineas, total_usd: c.total_usd, total_cop: c.total_cop,
    lineas_pedido: cp.lineas, total_pedido_usd: cp.total_usd, total_pedido_cop: cp.total_cop,
    lista_cop: lista, lista_usd: lista / trm, objetivo_cop: ref, objetivo_usd: ref / trm, piso_cop: piso, piso_usd: piso / trm,
    comision_cop: v.comision_cop, comision_usd: v.comision_cop / trm, neto_cop: v.neto_cop, neto_usd: v.neto_cop / trm,
    margen: v.margen, hay_margen: hay && v.margen >= dg.mo - 1e-9 && compra >= (1 - dg.rebaja_max) * dg.pedido - 1e-9,
    neto_pedido_cop: vp.neto_cop, neto_pedido_usd: vp.neto_cop / trm, margen_pedido: vp.margen,
    neto_apertura_cop: va ? va.neto_cop : null, neto_apertura_usd: va ? va.neto_cop / trm : null,
    margen_apertura: va ? va.margen : null, flete_max_usd: fmax};
}
