# Herramientas para el navegador

Fragmentos de JavaScript para pegar en la herramienta que ejecuta JS en la pestaña (en Claude in Chrome,
`javascript_tool`). Todos devuelven un texto JSON y además lo dejan en `window.__ag`. Si la herramienta
devuelve una promesa vacía o `{}` en vez del resultado, esperá unos segundos y ejecutá
`JSON.stringify(window.__ag)` para leerlo.

Están probados en Chromium con páginas de prueba: carga lenta, scroll infinito, botón "cargar más",
banner de cookies y enlaces a muestras dentro del menú. Si cambiás uno, mantené esos casos funcionando.

## `preparar`: esperar, scrollear, expandir y listar enlaces

Correrlo **en cada página de listado** (agenda, muestras, cartelera, programación, portada), apenas
termina de navegar. Hace, en orden:

1. Espera hasta 30 s a que el texto de la página deje de cambiar (sitios lentos, apps con JavaScript).
2. Acepta el banner de cookies si hay uno.
3. Scrollea hasta el final, una y otra vez, hasta que la página deja de crecer (carga diferida y scroll
   infinito), y aprieta los botones "ver más / cargar más / load more" que no navegan a otra página.
4. Devuelve los enlaces separados en: `secciones` (agenda, muestras, exposiciones, cartelera, etc. del
   mismo sitio), `fichas` (páginas de un evento o muestra), `ticketeras`, `externos` (otros sitios, posibles
   espacios nuevos), y datos de la página: cuánto tardó, cuánto scrolleó, cuántas fechas hay en el texto,
   eventos en JSON-LD y la plataforma (WordPress con The Events Calendar, Wix, etc.).

```js preparar
(async () => {
  const dormir = (ms) => new Promise((r) => setTimeout(r, ms));
  const t0 = Date.now();
  const largoTexto = () => (document.body ? document.body.innerText.length : 0);
  let largo = -1, estables = 0;
  while (Date.now() - t0 < 30000 && estables < 3) {
    await dormir(1000);
    const n = largoTexto();
    estables = n === largo && n > 150 ? estables + 1 : 0;
    largo = n;
  }
  const espera_ms = Date.now() - t0;
  const visible = (b) => b.offsetParent !== null || getComputedStyle(b).position === "fixed";
  const RE_COOKIES = /^(aceptar|acepto|accept|accept all|aceptar todo|aceptar todas|allow all|entendido|got it|ok|de acuerdo)$/i;
  for (const b of document.querySelectorAll("button, [role=button], a")) {
    if (visible(b) && RE_COOKIES.test((b.innerText || "").trim())) { b.click(); break; }
  }
  const RE_MAS = /^\+?\s*((ver|cargar|mostrar) m[aá]s|load more|show more|see more|view more|m[aá]s (eventos|muestras|actividades|resultados|fechas|funciones)|ver todos|ver todas|siguientes)\b/i;
  const noNavega = (b) => b.tagName !== "A" || !b.getAttribute("href") || /^(#|javascript:)/i.test(b.getAttribute("href"));
  let alto = 0, quietos = 0, pasos = 0, clics = 0;
  while (pasos < 60 && quietos < 3) {
    window.scrollTo(0, document.documentElement.scrollHeight);
    pasos++;
    await dormir(1200);
    const boton = [...document.querySelectorAll("button, [role=button], a")].find((b) =>
      visible(b) && !b.dataset.agClic && noNavega(b) && (b.innerText || "").trim().length < 40 && RE_MAS.test((b.innerText || "").trim()));
    if (boton && clics < 20) {
      boton.dataset.agClic = "1"; boton.click(); clics++; quietos = 0;
      await dormir(2000);
      continue;
    }
    const h = document.documentElement.scrollHeight;
    quietos = h === alto ? quietos + 1 : 0;
    alto = h;
  }
  window.scrollTo(0, 0);
  const MESES = "ene|feb|mar|abr|may|jun|jul|ago|sep|set|oct|nov|dic|jan|apr|aug|dec";
  const RE_FECHA = new RegExp(`\\b\\d{1,2}\\s*(de\\s+)?(${MESES})[a-záéíóú]*\\.?\\b|\\b(${MESES})[a-z]*\\.?\\s+\\d{1,2}\\b|\\b\\d{1,2}[/.]\\d{1,2}([/.]\\d{2,4})?\\b`, "gi");
  const RE_AGENDA = /agenda|cartelera|programaci|\beventos?\b|\bevents?\b|actividades|muestras?|exposici|exhibici|exhibitions?|\bshows?\b|funciones|espect[aá]culo|\bobras\b|\bciclos?\b|conciertos|calendario|calendar|talleres|cursos|visitas|en cartel|pr[oó]xim|actuales?|current|upcoming|temporada|festival|\bcine\b|pel[ií]culas|\bexpos?\b|inauguraci|what'?s on/i;
  const RE_TICKET = /alternativateatral|passline|eventbrite|ticketek|tuentrada|entradauno|plateanet|bonoentrada|ticketportal|universe\.com|allaccess|livepass|entradaweb|tickethoy|eventim|sympla|venti|linktr\.ee|taplink/i;
  const RE_IGNORAR = /instagram|facebook|twitter|x\.com|youtube|youtu\.be|whatsapp|wa\.me|tiktok|spotify|google\.|goo\.gl|wikipedia|linkedin|mailto|apple\.com|wix\.com|wordpress\.(com|org)|mercadopago|pinterest|flickr|vimeo|soundcloud/i;
  const aqui = location.hostname.replace(/^www\./, "");
  const mismo = (h) => h === aqui || h.endsWith("." + aqui) || aqui.endsWith("." + h);
  const vistos = new Set();
  const out = { secciones: [], fichas: [], ticketeras: [], externos: [] };
  for (const a of document.querySelectorAll("a[href]")) {
    let u;
    try { u = new URL(a.href); } catch { continue; }
    if (!/^https?:$/.test(u.protocol)) continue;
    const url = u.href.split("#")[0];
    if (vistos.has(url) || url === location.href.split("#")[0]) continue;
    if (/\.(jpe?g|png|gif|webp|svg|css|js|zip|mp3|mp4)$/i.test(u.pathname)) continue;
    vistos.add(url);
    const texto = (a.innerText || a.title || a.getAttribute("aria-label") || "").trim().replace(/\s+/g, " ").slice(0, 80);
    const host = u.hostname.replace(/^www\./, "");
    const ruta = decodeURIComponent(u.pathname + u.search);
    if (RE_TICKET.test(host)) { out.ticketeras.push([texto, url]); continue; }
    if (!mismo(host)) { if (!RE_IGNORAR.test(host)) out.externos.push([texto, url]); continue; }
    const enMenu = !!a.closest("nav, header, [class*=menu], [id*=menu], [role=navigation]");
    const segmentos = u.pathname.replace(/^\/(es|en|pt|es-ar)(\/|$)/i, "/").split("/").filter(Boolean).length;
    const tarjeta = (a.closest("article, li, [class*=card], [class*=item], [class*=event], [class*=evento], [class*=muestra], [class*=expo], tr") || a).innerText || "";
    const conFecha = tarjeta.length < 600 && RE_FECHA.test(tarjeta);
    RE_FECHA.lastIndex = 0;
    const agenda = RE_AGENDA.test(ruta) || RE_AGENDA.test(texto);
    if (agenda && (enMenu || segmentos <= 1) && !conFecha) out.secciones.push([texto, url]);
    else if (agenda || conFecha) out.fichas.push([texto, url]);
  }
  const jsonld = [...document.querySelectorAll('script[type="application/ld+json"]')].map((s) => s.textContent).join(" ");
  const html = document.documentElement.outerHTML;
  const plataforma = [
    /tribe-events|wp-json\/tribe/.test(html) && "WordPress + The Events Calendar (probar /wp-json/tribe/events/v1/events)",
    /wp-content/.test(html) && "WordPress",
    /wix\.com|wixstatic/.test(html) && "Wix",
    /squarespace/.test(html) && "Squarespace",
    /cdn\.shopify/.test(html) && "Shopify",
  ].filter(Boolean);
  window.__ag = JSON.stringify({
    url: location.href, titulo: document.title, espera_ms, largo_texto: largoTexto(), pasos_scroll: pasos,
    clics_ver_mas: clics, fechas_en_texto: (document.body.innerText.match(RE_FECHA) || []).length,
    eventos_jsonld: (jsonld.match(/"@type"\s*:\s*"[A-Za-z]*Event"/g) || []).length, plataforma,
    secciones: out.secciones.slice(0, 40), fichas: out.fichas.slice(0, 120),
    ticketeras: out.ticketeras.slice(0, 20), externos: out.externos.slice(0, 30),
  });
  return window.__ag;
})()
```

Cómo leer el resultado:

- `largo_texto` muy chico (< 300) después de 30 s: la página no cargó. Recargá y volvé a correr
  `preparar` (eso es un intento); ver "Sitios que no cargan" en la skill.
- `secciones`: son los `enlaces_candidatos` del sitio. Abrí **todas** antes de decidir que no hay eventos.
- `fichas`: eventos o muestras. Abrí las que no tengan en el listado las fechas completas, el lugar o el
  precio. Si hay muchas (teatro con 60 obras), alcanza con el listado cuando ahí están título y fechas.
- `externos`: otros espacios o fuentes. Si parecen un espacio cultural de CABA que no está en la cola,
  sumalo en `sitios_nuevos`.
- `eventos_jsonld > 0`: usá `jsonld` (abajo), es más rápido y exacto.
- `fechas_en_texto` alto y pocas `fichas`: las fechas están en el texto; usá `bloques`.

## `esperar`: versión corta para fichas

Para la página de un evento o una muestra: espera a que cargue y devuelve el texto principal.

```js esperar
(async () => {
  const dormir = (ms) => new Promise((r) => setTimeout(r, ms));
  const t0 = Date.now();
  let largo = -1, estables = 0;
  while (Date.now() - t0 < 25000 && estables < 2) {
    await dormir(1000);
    const n = document.body ? document.body.innerText.length : 0;
    estables = n === largo && n > 150 ? estables + 1 : 0;
    largo = n;
  }
  const raiz = document.querySelector("main, article, [role=main], #content, .content") || document.body;
  window.__ag = JSON.stringify({ url: location.href, titulo: document.title, espera_ms: Date.now() - t0,
    texto: raiz.innerText.replace(/\n{3,}/g, "\n\n").slice(0, 6000) });
  return window.__ag;
})()
```

## `bloques`: tarjetas con fecha de un listado

Devuelve cada tarjeta, fila o ítem que tenga una fecha, con su enlace. Sirve para leer un listado entero
sin pedir el texto de toda la página. Correrlo después de `preparar` (que ya scrolleó y expandió).

```js bloques
(() => {
  const MESES = "ene|feb|mar|abr|may|jun|jul|ago|sep|set|oct|nov|dic|jan|apr|aug|dec";
  const RE_FECHA = new RegExp(`\\b\\d{1,2}\\s*(de\\s+)?(${MESES})[a-záéíóú]*\\.?\\b|\\b(${MESES})[a-z]*\\.?\\s+\\d{1,2}\\b|\\b\\d{1,2}[/.]\\d{1,2}([/.]\\d{2,4})?\\b|\\b(hoy|mañana|lunes|martes|miércoles|jueves|viernes|sábado|domingo)s?\\b`, "i");
  const SEL = "article, li, tr, [class*=card], [class*=item], [class*=event], [class*=evento], [class*=muestra], [class*=expo], [class*=show], [class*=obra], [class*=post]";
  const cand = [...document.querySelectorAll(SEL)].filter((el) => {
    const t = el.innerText || "";
    return t.length >= 15 && t.length <= 900 && RE_FECHA.test(t) && !el.closest("nav, footer, header");
  });
  const hojas = cand.filter((el) => !cand.some((o) => o !== el && el.contains(o)));
  const vistos = new Set();
  const bloques = [];
  for (const el of hojas) {
    const texto = el.innerText.trim().replace(/\s*\n\s*/g, " | ").replace(/\s+/g, " ");
    if (vistos.has(texto)) continue;
    vistos.add(texto);
    const a = el.querySelector("a[href]") || el.closest("a[href]");
    bloques.push({ texto: texto.slice(0, 400), url: a ? a.href : "" });
  }
  window.__ag = JSON.stringify({ url: location.href, total: bloques.length, bloques: bloques.slice(0, 150) });
  return window.__ag;
})()
```

## `jsonld`: eventos con datos estructurados

```js jsonld
(() => {
  const out = [];
  const recorrer = (n) => {
    if (Array.isArray(n)) return n.forEach(recorrer);
    if (!n || typeof n !== "object") return;
    const t = [].concat(n["@type"] || []);
    if (t.some((x) => /Event$/.test(x))) {
      const loc = [].concat(n.location || [])[0] || {};
      const dir = loc.address || {};
      const of = [].concat(n.offers || [])[0] || {};
      out.push({ titulo: n.name, inicio: n.startDate, fin: n.endDate, lugar: loc.name || "",
        direccion: typeof dir === "string" ? dir : [dir.streetAddress, dir.addressLocality].filter(Boolean).join(", "),
        precio: of.price !== undefined ? `${of.priceCurrency || ""} ${of.price}`.trim() : "", url: n.url || location.href,
        descripcion: (n.description || "").slice(0, 400) });
    }
    ["@graph", "itemListElement", "item", "subEvent"].forEach((k) => n[k] && recorrer(n[k]));
  };
  document.querySelectorAll('script[type="application/ld+json"]').forEach((s) => { try { recorrer(JSON.parse(s.textContent)); } catch {} });
  window.__ag = JSON.stringify({ url: location.href, total: out.length, eventos: out.slice(0, 150) });
  return window.__ag;
})()
```

## Turismo BA (agenda "Qué hacer esta semana")

La página trae todas las actividades en un arreglo JSON dentro de un script. Abrí la página, esperá que
cargue y corré:

```js turismo
(() => {
  const html = document.documentElement.innerHTML;
  const i = html.indexOf('[{"orden"');
  if (i < 0) return JSON.stringify({ error: "no está el arreglo [{\"orden\"...; leer las tarjetas a mano" });
  let prof = 0, fin = i, enTexto = false, escape = false;
  for (let j = i; j < html.length; j++) {
    const c = html[j];
    if (enTexto) { if (escape) escape = false; else if (c === "\\") escape = true; else if (c === '"') enTexto = false; continue; }
    if (c === '"') enTexto = true;
    else if (c === "[" || c === "{") prof++;
    else if (c === "]" || c === "}") { prof--; if (prof === 0) { fin = j + 1; break; } }
  }
  const acts = JSON.parse(html.slice(i, fin));
  const eventos = acts.filter((a) => a.fecha_inicio).map((a) => ({
    titulo: (a.nombre_actividad || "").trim(), fecha_inicio: a.fecha_inicio, categoria: a.categoria_actividad_filtro || "",
    lugar: (a.proveedor || "").trim(), barrio: a.barrio || "", direccion: a.calle_altura || "", horarios: a.dias_horarios || "",
    precio: String(a.precio_filtro).trim() === "0" ? "Gratis" : "", descripcion: (a.descripcion || "").replace(/<[^>]+>/g, " ").slice(0, 600),
    url: a.url_boton || location.href }));
  window.__ag = JSON.stringify({ total: eventos.length, eventos });
  return window.__ag;
})()
```

Las actividades que ya empezaron no traen fecha de fin: ponerles `"vigente_sin_fin": true`. Las que no
tengan `lugar` se descartan (no inventar). Este resultado puede ser largo: guardarlo directo en el archivo
de resultado en vez de copiarlo a mano evento por evento (ver "Resultados grandes" en la skill).

## Instagram

En el perfil (`https://www.instagram.com/<usuario>/`), después de esperar y scrollear un poco a mano:

```js instagram_perfil
(() => {
  const posts = [...new Set([...document.querySelectorAll('a[href*="/p/"], a[href*="/reel/"]')].map((a) => a.href.split("?")[0]))];
  const bio = [...document.querySelectorAll("header a[href]")].map((a) => a.href).filter((h) => !/instagram\.com/.test(h));
  const destacadas = [...document.querySelectorAll('a[href*="/stories/highlights/"]')].map((a) => [a.innerText.trim(), a.href]);
  const login = /inici[aá] sesi[oó]n|log in|iniciar sesión/i.test(document.body.innerText.slice(0, 3000)) && posts.length === 0;
  window.__ag = JSON.stringify({ posts: posts.slice(0, 12), bio, destacadas, pide_login: login });
  return window.__ag;
})()
```

En cada post:

```js instagram_post
(() => {
  const t = document.querySelector("time[datetime]");
  const texto = [...document.querySelectorAll("h1, article span, [role=dialog] span")].map((s) => s.innerText).filter((x) => x && x.length > 20);
  window.__ag = JSON.stringify({ url: location.href.split("?")[0], publicado: t ? t.getAttribute("datetime") : "",
    texto: (texto.sort((a, b) => b.length - a.length)[0] || document.querySelector('meta[property="og:description"]')?.content || "").slice(0, 2500) });
  return window.__ag;
})()
```

`publicado` es la fecha del post: sirve para saber de qué año habla un "sábado 18". Si el post es de hace
meses, el evento probablemente ya pasó.

## Patrones de sitios conocidos

- **WordPress + The Events Calendar** (`tribe-events` en el HTML): abrir
  `<sitio>/wp-json/tribe/events/v1/events?per_page=50&start_date=<desde>&end_date=<hasta>` en la pestaña.
  Es JSON con `title`, `start_date`, `end_date`, `venue`, `cost`, `url`. Si responde 404, usar `/eventos/`
  o `/events/` con `preparar`.
- **Wix**: carga lento y por partes; `preparar` ya espera, pero si `largo_texto` queda bajo, esperar 10 s
  más y repetir. Los menús a veces están en un desplegable "Más": abrirlo a mano y mirar sus enlaces.
- **Linktree / Taplink** (bio de Instagram): cada botón es un enlace. Abrir los que digan agenda,
  cartelera, entradas, eventos, programación, o que vayan a una ticketera.
- **Alternativa Teatral**: la ficha de un espacio lista sus obras en cartel con días y horarios; entrar a
  cada obra para ver fechas de función y precio.
- **Calendarios por mes** (`?mes=`, `/2026/10/`, flechas "siguiente"): recorrer el mes actual y el
  siguiente si la ventana de 14 días lo cruza.
- **Pestañas "Actuales / Próximas / Anteriores"**: abrir "Actuales" y "Próximas"; "Anteriores" se puede
  descartar con motivo "archivo de muestras pasadas".
