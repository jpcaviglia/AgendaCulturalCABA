// Herramientas para el navegador de la skill actualizar-agenda (ver navegador.md).
// Se cargan en la página con una línea (la imprime `crawl.py iniciar`):
//   (async () => { window.__agt || await import("https://cdn.jsdelivr.net/gh/<repo>@<commit>/.claude/skills/actualizar-agenda/navegador.js"); return window.__agt.preparar(); })()
// Si la página bloquea el import (CSP), pegar este archivo entero seguido de la llamada.
// Cada función devuelve un texto JSON y además lo deja en window.__ag.
(() => {
  const dormir = (ms) => new Promise((r) => setTimeout(r, ms));
  const largoTexto = () => (document.body ? document.body.innerText.length : 0);
  const fin = (o) => (window.__ag = JSON.stringify(o));

  // Espera a que el texto de la página deje de cambiar (sitios lentos, apps con JavaScript).
  const esperarCarga = async (maxMs, establesMin) => {
    const t0 = Date.now();
    let largo = -1, estables = 0;
    while (Date.now() - t0 < maxMs && estables < establesMin) {
      await dormir(1000);
      const n = largoTexto();
      estables = n === largo && n > 150 ? estables + 1 : 0;
      largo = n;
    }
    return Date.now() - t0;
  };

  // --- avisos de cookies y ventanas que tapan la página ---
  const noNavega = (b) => b.tagName !== "A" || !b.getAttribute("href") || /^(#|javascript:)/i.test(b.getAttribute("href"));
  const CMP = ["#onetrust-reject-all-handler", "#onetrust-accept-btn-handler", "#didomi-notice-disagree-button",
    "#didomi-notice-agree-button", "#CybotCookiebotDialogBodyButtonDecline", "#CybotCookiebotDialogBodyLevelButtonLevelOptinAllowAll",
    "[data-testid=uc-deny-all-button]", "[data-testid=uc-accept-all-button]", ".cky-btn-reject", ".cky-btn-accept",
    ".cmplz-deny", ".cmplz-accept", "#cn-refuse-cookie", "#cn-accept-cookie", "#wt-cli-reject-btn", "#wt-cli-accept-all-btn",
    ".iubenda-cs-reject-btn", ".iubenda-cs-accept-btn", "[data-cookiefirst-action=reject]", "[data-cookiefirst-action=accept]",
    ".fc-cta-do-not-consent", ".fc-cta-consent", "._brlbs-refuse-btn", "._brlbs-btn-accept-all", ".cc-deny", ".cc-allow", ".cc-dismiss"];
  const RE_AVISO = /cookie|privacidad|privacy|consent|datos personales/i;
  const RE_NO = /^(rechazar|denegar|no acepto|decline|reject|deny|solo (las )?(cookies )?(necesarias|esenciales)|only (necessary|essential)|usar solo)/i;
  const RE_SI = /^(aceptar|acepto|accept|allow|permitir|entendido|de acuerdo|estoy de acuerdo|agree|ok\b|okay|got it|continuar|cerrar|close|×|✕)/i;
  const RE_MODAL = /suscrib|newsletter|bolet[ií]n|notificaci|descuento|oferta|promo|mayor de (edad|18)|\+18|registrate|sign ?up|whatsapp|descarg[aá] la app/i;
  const RE_CERRAR = /^(×|✕|✖|x|cerrar|close|no,? gracias|no thanks|ahora no|not now|m[aá]s tarde|omitir|saltar|skip|continuar sin)/i;
  const RE_EDAD = /^(s[ií](?![a-z])|soy mayor|tengo (m[aá]s de )?18|ingresar|entrar|enter|yes)/i;

  const cerrarPopups = (popups) => {
    const vis = (e) => { const r = e.getBoundingClientRect(), s = getComputedStyle(e);
      return r.width > 2 && r.height > 2 && s.visibility !== "hidden" && s.display !== "none" && s.opacity !== "0"; };
    const txt = (e) => (e.innerText || e.value || e.getAttribute("aria-label") || "").trim().replace(/\s+/g, " ");
    const raices = [document];
    for (const e of document.querySelectorAll("*")) if (e.shadowRoot) raices.push(e.shadowRoot);
    const todos = (sel) => raices.flatMap((r) => [...r.querySelectorAll(sel)]).filter(vis);
    const clic = (b, que) => { b.click(); popups.push(`${que}: ${txt(b).slice(0, 40) || b.id || b.className}`); return true; };
    // 1. Gestores de consentimiento conocidos; se prefiere rechazar (o "solo necesarias") antes que aceptar.
    for (const sel of CMP) { const b = todos(sel)[0]; if (b) return clic(b, "cookies"); }
    // 2. Avisos de cookies propios del sitio: botón dentro de un aviso que habla de cookies o privacidad.
    const enAviso = (b) => {
      let c = b.closest("[class*=cookie i], [id*=cookie i], [class*=consent i], [id*=consent i], [class*=gdpr i], [class*=privacy i], [role=dialog], [aria-modal=true], [class*=banner i], [class*=notice i], [class*=aviso i]");
      for (let e = b.parentElement, k = 0; !c && e && k < 8; e = e.parentElement, k++)
        if (/fixed|sticky/.test(getComputedStyle(e).position)) c = e;
      return !!c && (c.innerText || "").length < 2500 && RE_AVISO.test(c.innerText || "");
    };
    const botones = todos("button, [role=button], a, input[type=button], input[type=submit]").filter((b) => txt(b).length < 45 && noNavega(b) && enAviso(b));
    const b2 = botones.find((b) => RE_NO.test(txt(b))) || botones.find((b) => RE_SI.test(txt(b)));
    if (b2) return clic(b2, "cookies");
    // 3. Ventanas que tapan la página: newsletter, notificaciones, promociones, control de edad.
    const area = innerWidth * innerHeight;
    for (const m of [...document.querySelectorAll("*")].filter((e) => getComputedStyle(e).position === "fixed" && vis(e))) {
      const r = m.getBoundingClientRect(), t = m.innerText || "";
      if (m.dataset.agPopup || r.width * r.height < area * 0.25 || t.length > 2500 || !RE_MODAL.test(t)) continue;
      m.dataset.agPopup = "1";
      const cand = [...m.querySelectorAll("button, [role=button], a, [aria-label], [class*=close i]")].filter(vis);
      const b = cand.find((e) => /cerrar|close/i.test(e.getAttribute("aria-label") || "") || /close|cerrar/i.test(String(e.className)))
        || cand.find((e) => RE_CERRAR.test(txt(e))) || (/edad|18/.test(t) && cand.find((e) => RE_EDAD.test(txt(e))));
      if (b && noNavega(b)) return clic(b, "ventana");
      document.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true }));
      popups.push("ventana: Escape");
      return true;
    }
    // 4. Consentimiento en un iframe de otro dominio: JS no lo puede tocar.
    const marco = todos("iframe").find((f) => /consent|cmp|sourcepoint|privacy-mgmt|cookie/i.test(f.src || f.id || ""));
    if (marco && !popups.some((p) => p.startsWith("iframe"))) popups.push("iframe de consentimiento: cerrarlo con un clic (captura)");
    // 5. Si se cerró algo y la página quedó trabada sin scroll, destrabarla.
    if (popups.length) for (const e of [document.documentElement, document.body])
      if (getComputedStyle(e).overflow === "hidden") e.style.setProperty("overflow", "auto", "important");
    return false;
  };
  const despejar = async (popups) => { for (let k = 0; k < 4 && cerrarPopups(popups); k++) await dormir(800); };

  // --- clasificación de enlaces ---
  const MESES = "ene|feb|mar|abr|may|jun|jul|ago|sep|set|oct|nov|dic|jan|apr|aug|dec";
  const RE_FECHA = new RegExp(`\\b\\d{1,2}\\s*(de\\s+)?(${MESES})[a-záéíóú]*\\.?\\b|\\b(${MESES})[a-z]*\\.?\\s+\\d{1,2}\\b|\\b\\d{1,2}[/.]\\d{1,2}([/.]\\d{2,4})?\\b`, "gi");
  // Fuertes: suelen ser LA agenda del sitio. Débiles: subprogramas que la agenda casi siempre ya incluye.
  const RE_FUERTE = /agenda|cartelera|programaci|\beventos?\b|\bevents?\b|actividades|muestras?|exposici|exhibici|exhibitions?|\bshows?\b|funciones|espect[aá]culo|\bobras\b|conciertos|calendario|calendar|en cartel|pr[oó]xim|upcoming|what'?s on/i;
  const RE_DEBIL = /\bciclos?\b|talleres|cursos|visitas|actuales?|current|temporada|festival|\bcine\b|pel[ií]culas|\bexpos?\b|inauguraci/i;
  const RE_TICKET = /alternativateatral|passline|eventbrite|ticketek|tuentrada|entradauno|plateanet|bonoentrada|ticketportal|universe\.com|allaccess|livepass|entradaweb|tickethoy|eventim|sympla|venti|linktr\.ee|taplink/i;
  const RE_IGNORAR = /instagram|facebook|twitter|x\.com|youtube|youtu\.be|whatsapp|wa\.me|tiktok|spotify|google\.|goo\.gl|wikipedia|linkedin|mailto|apple\.com|wix\.com|wordpress\.(com|org)|mercadopago|pinterest|flickr|vimeo|soundcloud/i;
  // Misma página aunque cambie la barra final, el idioma o los parámetros de seguimiento.
  const normal = (u) => (u.origin + u.pathname).replace(/\/+$/, "").toLowerCase()
    + u.search.replace(/[?&](utm_[^&]*|fbclid=[^&]*|gclid=[^&]*)/g, "").replace(/^&/, "?");

  // preparar: esperar, despejar, scrollear y expandir, y listar los enlaces clasificados.
  // Opciones: {fichas: 50, externos: 15} para cambiar cuántos enlaces devuelve.
  const preparar = async (op = {}) => {
    const lim = { secciones: 25, debiles: 15, fichas: 50, ticketeras: 10, externos: 15, ...op };
    const espera_ms = await esperarCarga(30000, 3);
    const popups = [];
    await despejar(popups);
    const visible = (b) => b.offsetParent !== null || getComputedStyle(b).position === "fixed";
    const RE_MAS = /^\+?\s*((ver|cargar|mostrar) m[aá]s|load more|show more|see more|view more|m[aá]s (eventos|muestras|actividades|resultados|fechas|funciones)|ver todos|ver todas|siguientes)\b/i;
    let alto = 0, quietos = 0, pasos = 0, clics = 0;
    while (pasos < 60 && quietos < 3) {
      window.scrollTo(0, document.documentElement.scrollHeight);
      pasos++;
      await dormir(1200);
      await despejar(popups); // hay avisos que aparecen a los segundos o al scrollear
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
    const aqui = location.hostname.replace(/^www\./, "");
    const mismo = (h) => h === aqui || h.endsWith("." + aqui) || aqui.endsWith("." + h);
    const vistos = new Set([normal(new URL(location.href))]);
    const out = { secciones: [], debiles: [], fichas: [], ticketeras: [], externos: [] };
    for (const a of document.querySelectorAll("a[href]")) {
      let u;
      try { u = new URL(a.href); } catch { continue; }
      if (!/^https?:$/.test(u.protocol)) continue;
      if (/\.(jpe?g|png|gif|webp|svg|css|js|zip|mp3|mp4|pdf)$/i.test(u.pathname)) continue;
      const clave = normal(u);
      if (vistos.has(clave)) continue;
      vistos.add(clave);
      const url = u.href.split("#")[0];
      const texto = (a.innerText || a.title || a.getAttribute("aria-label") || a.querySelector("img[alt]")?.alt
        || decodeURIComponent(u.pathname.split("/").filter(Boolean).pop() || "")).trim().replace(/\s+/g, " ").slice(0, 50);
      const host = u.hostname.replace(/^www\./, "");
      if (RE_TICKET.test(host)) { out.ticketeras.push([texto, url]); continue; }
      if (!mismo(host)) { if (!RE_IGNORAR.test(host)) out.externos.push([texto, url]); continue; }
      // Cambio de idioma: es la misma página en otra lengua.
      if (/^(es|en|pt|fr|it|de|esp|eng|español|english|português|portugues)$/i.test(texto) || /\/lang\/|[?&](lang|hl)=/i.test(u.pathname + u.search)) continue;
      const ruta = decodeURIComponent(u.pathname + u.search);
      const enMenu = !!a.closest("nav, header, [class*=menu], [id*=menu], [role=navigation]");
      const segmentos = u.pathname.replace(/^\/(es|en|pt|es-ar)(\/|$)/i, "/").split("/").filter(Boolean).length;
      const tarjeta = (a.closest("article, li, [class*=card], [class*=item], [class*=event], [class*=evento], [class*=muestra], [class*=expo], tr") || a).innerText || "";
      const conFecha = tarjeta.length < 600 && RE_FECHA.test(tarjeta);
      RE_FECHA.lastIndex = 0;
      const fuerte = RE_FUERTE.test(ruta) || RE_FUERTE.test(texto);
      const debil = !fuerte && (RE_DEBIL.test(ruta) || RE_DEBIL.test(texto));
      // Mismo sitio: se devuelve la ruta sola para no repetir el dominio en cada enlace.
      const corto = [texto, u.pathname + u.search];
      if ((fuerte || debil) && (enMenu || segmentos <= 1) && !conFecha) (fuerte ? out.secciones : out.debiles).push(corto);
      else if (fuerte || debil || conFecha) out.fichas.push(corto);
    }
    // Sin secciones fuertes, las débiles son lo único que hay: pasan a ser obligatorias.
    if (!out.secciones.length) { out.secciones = out.debiles; out.debiles = []; }
    const jsonld = [...document.querySelectorAll('script[type="application/ld+json"]')].map((s) => s.textContent).join(" ");
    const html = document.documentElement.outerHTML;
    const plataforma = [
      /tribe-events|wp-json\/tribe/.test(html) && "WordPress + The Events Calendar (probar /wp-json/tribe/events/v1/events)",
      !/tribe-events/.test(html) && /wp-content/.test(html) && "WordPress",
      /wix\.com|wixstatic/.test(html) && "Wix",
      /squarespace/.test(html) && "Squarespace",
      /cdn\.shopify/.test(html) && "Shopify",
    ].filter(Boolean);
    const total = (k) => out[k].length > lim[k] ? { [`${k}_total`]: out[k].length } : {};
    return fin({
      url: location.href, base: location.origin, titulo: document.title.slice(0, 80), espera_ms, largo_texto: largoTexto(),
      pasos_scroll: pasos, clics_ver_mas: clics, popups,
      fechas_en_texto: (document.body.innerText.match(RE_FECHA) || []).length,
      eventos_jsonld: (jsonld.match(/"@type"\s*:\s*"[A-Za-z]*Event"/g) || []).length, plataforma,
      secciones: out.secciones.slice(0, lim.secciones), debiles: out.debiles.slice(0, lim.debiles),
      fichas: out.fichas.slice(0, lim.fichas), ticketeras: out.ticketeras.slice(0, lim.ticketeras),
      externos: out.externos.slice(0, lim.externos),
      ...total("secciones"), ...total("debiles"), ...total("fichas"), ...total("externos"),
    });
  };

  // esperar: para la ficha de un evento o muestra. Opciones: {max: 2500} caracteres de texto.
  const esperar = async (op = {}) => {
    const max = op.max || 2500;
    const espera_ms = await esperarCarga(25000, 2);
    const popups = [];
    await despejar(popups);
    const raiz = document.querySelector("main, article, [role=main], #content, .content") || document.body;
    // Se sacan menú, pie y barras laterales: repiten lo mismo en cada ficha.
    const copia = raiz.cloneNode(true);
    copia.querySelectorAll("nav, footer, header, aside, script, style, form, [class*=share i], [class*=related i], [class*=newsletter i]").forEach((e) => e.remove());
    const texto = (copia.innerText || raiz.innerText).replace(/[ \t]+/g, " ").replace(/ ?\n[\s]*/g, "\n").trim();
    return fin({ url: location.href, espera_ms, popups, texto: texto.slice(0, max), ...(texto.length > max ? { texto_total: texto.length } : {}) });
  };

  // popups: solo cerrar avisos (cuando aparece uno después, por ejemplo al abrir un menú).
  const popups = async () => {
    const lista = [];
    await despejar(lista);
    return fin({ url: location.href, popups: lista });
  };

  // bloques: cada tarjeta, fila o ítem de un listado que tenga una fecha, con su enlace.
  const bloques = (op = {}) => {
    const max = op.max || 120;
    const RE = new RegExp(`\\b\\d{1,2}\\s*(de\\s+)?(${MESES})[a-záéíóú]*\\.?\\b|\\b(${MESES})[a-z]*\\.?\\s+\\d{1,2}\\b|\\b\\d{1,2}[/.]\\d{1,2}([/.]\\d{2,4})?\\b|\\b(hoy|mañana|lunes|martes|miércoles|jueves|viernes|sábado|domingo)s?\\b`, "i");
    const SEL = "article, li, tr, [class*=card], [class*=item], [class*=event], [class*=evento], [class*=muestra], [class*=expo], [class*=show], [class*=obra], [class*=post]";
    const cand = [...document.querySelectorAll(SEL)].filter((el) => {
      const t = el.innerText || "";
      return t.length >= 15 && t.length <= 900 && RE.test(t) && !el.closest("nav, footer, header");
    });
    const hojas = cand.filter((el) => !cand.some((o) => o !== el && el.contains(o)));
    const vistos = new Set();
    const lista = [];
    for (const el of hojas) {
      const texto = el.innerText.trim().replace(/\s*\n\s*/g, " | ").replace(/\s+/g, " ");
      if (vistos.has(texto)) continue;
      vistos.add(texto);
      const a = el.querySelector("a[href]") || el.closest("a[href]");
      let url = "";
      if (a) { const u = new URL(a.href); url = u.origin === location.origin ? u.pathname + u.search : u.href; }
      lista.push({ texto: texto.slice(0, 300), url });
    }
    return fin({ url: location.href, base: location.origin, total: lista.length, bloques: lista.slice(0, max) });
  };

  // jsonld: eventos con datos estructurados.
  const jsonld = (op = {}) => {
    const max = op.max || 150, largoDesc = op.descripcion ?? 200;
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
          descripcion: (n.description || "").replace(/\s+/g, " ").slice(0, largoDesc) });
      }
      ["@graph", "itemListElement", "item", "subEvent"].forEach((k) => n[k] && recorrer(n[k]));
    };
    document.querySelectorAll('script[type="application/ld+json"]').forEach((s) => { try { recorrer(JSON.parse(s.textContent)); } catch {} });
    return fin({ url: location.href, total: out.length, eventos: out.slice(0, max) });
  };

  // turismo: agenda "Qué hacer esta semana" de Turismo BA (arreglo JSON dentro de un script).
  // Devuelve los eventos ya en el formato del resultado; las que ya empezaron van con vigente_sin_fin.
  const turismo = (op = {}) => {
    const largoDesc = op.descripcion ?? 200;
    const html = document.documentElement.innerHTML;
    const i = html.indexOf('[{"orden"');
    if (i < 0) return fin({ error: "no está el arreglo [{\"orden\"...; leer las tarjetas a mano" });
    let prof = 0, final = i, enTexto = false, escape = false;
    for (let j = i; j < html.length; j++) {
      const c = html[j];
      if (enTexto) { if (escape) escape = false; else if (c === "\\") escape = true; else if (c === '"') enTexto = false; continue; }
      if (c === '"') enTexto = true;
      else if (c === "[" || c === "{") prof++;
      else if (c === "]" || c === "}") { prof--; if (prof === 0) { final = j + 1; break; } }
    }
    const hoyIso = new Date().toLocaleDateString("sv"); // AAAA-MM-DD en la hora local
    const sinLugar = [];
    const eventos = JSON.parse(html.slice(i, final)).filter((a) => a.fecha_inicio).flatMap((a) => {
      const titulo = (a.nombre_actividad || "").trim(), lugar = (a.proveedor || "").trim();
      if (!lugar) { sinLugar.push(titulo); return []; }
      const e = { titulo, fecha_inicio: a.fecha_inicio, categoria: a.categoria_actividad_filtro || "", lugar,
        barrio: a.barrio || "", direccion: a.calle_altura || "", horarios: a.dias_horarios || "",
        precio: String(a.precio_filtro).trim() === "0" ? "Gratis" : "",
        descripcion: (a.descripcion || "").replace(/<[^>]+>/g, " ").replace(/\s+/g, " ").trim().slice(0, largoDesc),
        url: a.url_boton || location.href };
      if (a.fecha_inicio < hoyIso) e.vigente_sin_fin = true;
      return [e];
    });
    return fin({ total: eventos.length, descartados_sin_lugar: sinLugar.length, eventos });
  };

  // instagram_perfil: posts de la grilla, enlaces de la bio y destacadas.
  const instagram_perfil = () => {
    const posts = [...new Set([...document.querySelectorAll('a[href*="/p/"], a[href*="/reel/"]')].map((a) => a.href.split("?")[0]))];
    const bio = [...document.querySelectorAll("header a[href]")].map((a) => a.href).filter((h) => !/instagram\.com/.test(h));
    const destacadas = [...document.querySelectorAll('a[href*="/stories/highlights/"]')].map((a) => [a.innerText.trim(), a.href]);
    const login = /inici[aá] sesi[oó]n|log in|iniciar sesión/i.test(document.body.innerText.slice(0, 3000)) && posts.length === 0;
    return fin({ posts: posts.slice(0, 12), bio, destacadas, pide_login: login });
  };

  // instagram_post: fecha de publicación y texto del post.
  const instagram_post = () => {
    const t = document.querySelector("time[datetime]");
    const texto = [...document.querySelectorAll("h1, article span, [role=dialog] span")].map((s) => s.innerText).filter((x) => x && x.length > 20);
    return fin({ url: location.href.split("?")[0], publicado: t ? t.getAttribute("datetime") : "",
      texto: (texto.sort((a, b) => b.length - a.length)[0] || document.querySelector('meta[property="og:description"]')?.content || "").slice(0, 2000) });
  };

  window.__agt = { preparar, esperar, popups, bloques, jsonld, turismo, instagram_perfil, instagram_post };
})();
