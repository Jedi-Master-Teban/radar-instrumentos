// Se ejecuta en una pestaña de reverb.com (el navegador integrado) con:
//   (<contenido de este archivo>)(<busquedas de datos/busquedas.json>)
// Lee el mismo JSON que usa la página de Reverb y devuelve filas compactas. Solo lectura.
async function capturar(busquedas) {
  const H = {'Accept': 'application/hal+json', 'Accept-Version': '3.0', 'Content-Type': 'application/hal+json'};
  const pausa = ms => new Promise(r => setTimeout(r, ms));
  const salida = [];
  for (const b of busquedas) {
    const filas = [], vistos = new Set();
    let estado = 'ok';
    for (let p = 1; p <= (b.paginas || 1); p++) {
      const q = '/api/listings?query=' + encodeURIComponent(b.consulta) + '&condition=used&item_region=US&per_page=50&page=' + p +
                (b.precio_max ? '&price_max=' + b.precio_max : '') + (b.precio_min ? '&price_min=' + b.precio_min : '');
      const r = await fetch(q, {headers: H});
      if (!r.ok) { estado = 'HTTP ' + r.status; break; }
      const j = await r.json();
      for (const l of (j.listings || [])) {
        const pr = l.price || {};
        if (pr.currency !== 'USD' || vistos.has(l.id) || ((l.state || {}).slug || 'live') !== 'live') continue;
        const monto = parseFloat(pr.amount);
        if (!(monto > 0) || (b.precio_max && monto > b.precio_max)) continue;
        const tarifas = (l.shipping || {}).rates || [];
        if (!tarifas.length) continue;  // solo publicaciones que envían
        let envio = 0;
        for (const t of tarifas) if (t.region_code === 'US_CON' && t.rate) envio = parseFloat(t.rate.amount) || 0;
        const foto = (((((l.photos || [])[0] || {})._links || {}).large_crop || {}).href || '').replace('https://rvb-img.reverb.com/i/', '');
        vistos.add(l.id);
        // [id, título, precio, estado, acepta ofertas, publicada, envío en EE. UU., foto sin el prefijo del CDN]
        filas.push([String(l.id), (l.title || '').replace(/\s+/g, ' ').trim().slice(0, 90), monto, (l.condition || {}).slug || '',
                    l.offers_enabled ? 1 : 0, (l.published_at || l.created_at || '').slice(0, 10), envio, foto]);
      }
      if ((j.listings || []).length < 50) break;
      await pausa(1500);
    }
    salida.push({slug: b.slug, estado, filas});
    await pausa(1500);
  }
  return salida;
}
