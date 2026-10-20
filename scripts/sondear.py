"""Read-only probe: which sites in data/crawl/sitios.json could be read without a browser.

It makes plain HTTP requests (no JavaScript) to each website's home page and its 3 most likely agenda links
(plus 2 for talleres or visitas), and classifies each site. It writes nothing in data/: the report goes to
data/crawl/local/sondeo.json (pushed to the repo, to be used from another machine) and the summary is
printed. It draws no "no events" conclusions: what cannot be read this way still goes to the browser.

Classes:
    api             The Events Calendar (WordPress) API returns events
    jsonld          the home page or an agenda page brings events in JSON-LD
    html            the agenda has the listing in the HTML (several dates in the text), but it must be read
    needs_browser   the HTML has almost no text or looks like a JavaScript app
    sin_agenda_vista  loads, but no agenda page or dates were found (not proof that there are none)
    unreachable     did not load (DNS, timeout, HTTP error, block); the reason goes in the report

Usage:
    python scripts/sondear.py [--limite N] [--id ID ...] [--hilos N]   # report only
    python scripts/sondear.py --corrida [--id ID ...]                  # step 1b of the actualizar-agenda skill
    python scripts/sondear.py --leer URL [--desde TEXTO] [--max N] [--timeout S]  # text of a page, to read it without a browser

With --corrida it probes only the pending websites of the open run and also:
    api / jsonld    if there are events in the window, it saves them with `crawl.py guardar` (con_eventos); those
                    sites are no longer opened in the browser. It never saves "sin eventos".
                    Before saving, it opens each event's own page (up to MAX_FICHAS per site) to fill in the price, picture
                    and time the listing lacks; events without a `url` of their own stay as the listing gave them
                    (`sin_enlace_propio` in the report).
    html            leaves the text of the home page and the agenda pages in data/crawl/local/textos/<id>.txt;
                    `crawl.py siguiente` shows it so it can be read instead of opening the browser.
The report is merged with the previous one (per site, with its date).
"""
import html as html_lib
import http.client
import json
import re
import socket
import ssl
import subprocess
import sys
import time
import zlib
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from http.cookiejar import CookieJar
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlparse
from urllib.request import HTTPCookieProcessor, HTTPSHandler, Request, build_opener

from comun import CORRIDA, CRAWL, RAIZ, SITIOS, ZONA_BA, dominio, escribir_json, leer_json

SALIDA = CRAWL / "local" / "sondeo.json"
TEXTOS = CRAWL / "local" / "textos"
TMP = CRAWL / "tmp"
UA = "Mozilla/5.0 (compatible; AgendaCulturalCABA-sondeo; lectura de agenda pública)"
TIMEOUT, MAX_BYTES, PAUSA = 15, 1_500_000, 1.0
REINTENTABLES, MAX_ESPERA = {429, 500, 502, 503, 504}, 30  # retried once, waiting up to 30 s
MESES = "ene|feb|mar|abr|may|jun|jul|ago|sep|set|oct|nov|dic|jan|apr|aug|dec"
RE_FECHA = re.compile(rf"\b\d{{1,2}}\s*(de\s+)?({MESES})[a-záéíóú]*\.?\b|\b({MESES})[a-z]*\.?\s+\d{{1,2}}\b|\b\d{{1,2}}[/.]\d{{1,2}}([/.]\d{{2,4}})?\b", re.I)
RE_AGENDA = re.compile(r"agenda|cartelera|programaci|\beventos?\b|\bevents?\b|actividades|muestras?|exposici|exhibici|exhibitions?|funciones|conciertos|calendario|calendar|en-cartel|pr[oó]xim|upcoming", re.I)
RE_IGNORAR_RUTA = re.compile(r"\.(jpe?g|png|gif|webp|svg|css|js|zip|mp3|mp4|pdf)(?=\?|$)|/lang/|[?&](lang|hl)=|/(en|pt)/?$", re.I)
RE_PROGRAMAS = re.compile(r"talleres|\btaller\b|cursos|\bclases\b|seminarios?|workshops?|visitas|recorridos|guided tours?", re.I)
SPA = re.compile(r'id="(root|__next|app)"|__NEXT_DATA__|ng-version|data-reactroot|window\.__NUXT__|wixui|id="comp-', re.I)
CONTEXTO = ssl.create_default_context()
SIN_VERIFICAR = ssl._create_unverified_context()  # only to read public pages when the certificate is wrong
# Python only announces HTTP/1.1 (ALPN) with its default context; with its own one it has to be requested. Without that, some
# CDNs (Linktree, on Fastly) answer 403.
for _ctx in (CONTEXTO, SIN_VERIFICAR):
    _ctx.set_alpn_protocols(["http/1.1"])


def descomprimir(datos, codificacion):
    """Decompresses whatever was downloaded. Tolerates files cut by MAX_BYTES or by the server."""
    if codificacion in ("", "identity"):
        return datos, ""
    if codificacion not in ("gzip", "x-gzip", "deflate"):
        return b"", f"respuesta comprimida con {codificacion}, que no se puede leer"
    for wbits in (zlib.MAX_WBITS | 32, -zlib.MAX_WBITS):  # gzip or zlib (auto-detected), and deflate without a header
        try:
            return zlib.decompressobj(wbits).decompress(datos, MAX_BYTES * 2), ""
        except zlib.error:
            continue
    return b"", "la compresión de la respuesta está rota"


def decodificar(datos, charset):
    if not charset:
        m = re.search(rb'<meta[^>]+charset=["\']?([\w-]+)', datos[:4096], re.I)
        charset = m.group(1).decode("ascii") if m else "utf-8"
    try:
        return datos.decode(charset, "replace")
    except LookupError:  # the site declares a charset that does not exist
        return datos.decode("utf-8", "replace")


def motivo_error(e):
    """A short, stable reason for the report, from the exception."""
    r = e.reason if isinstance(e, URLError) and not isinstance(e, HTTPError) else e
    if isinstance(r, (socket.timeout, TimeoutError)) or "timed out" in str(r).lower():
        return "timeout"
    if isinstance(r, ssl.SSLError) or "CERTIFICATE" in str(r).upper():
        return "certificado inválido"
    if isinstance(r, socket.gaierror):
        return "el dominio no resuelve (DNS)"
    if isinstance(r, ConnectionRefusedError):
        return "conexión rechazada"
    if isinstance(r, (ConnectionResetError, ConnectionAbortedError, http.client.RemoteDisconnected,
                      http.client.IncompleteRead, EOFError)):
        return "conexión cortada"
    return f"{type(r).__name__}: {r}"[:120]


def abrir(url, ctx):
    """One request. Cookies are kept during the request: some sites redirect until they are sent back."""
    abridor = build_opener(HTTPCookieProcessor(CookieJar()), HTTPSHandler(context=ctx))
    req = Request(url, headers={"User-Agent": UA, "Accept": "text/html,application/json;q=0.9,*/*;q=0.5",
                                "Accept-Language": "es-AR,es;q=0.9", "Accept-Encoding": "gzip, deflate"})
    with abridor.open(req, timeout=TIMEOUT) as r:
        tipo = (r.headers.get_content_type() or "").lower()
        if not re.search(r"html|json|xml|text", tipo):  # a PDF or an image is not a page to read
            return r.status, r.geturl(), "", f"no es una página ({tipo})"
        try:
            datos = r.read(MAX_BYTES)
        except http.client.IncompleteRead as e:  # the server cut off before finishing: what arrived is used
            datos = e.partial
        datos, nota = descomprimir(datos, (r.headers.get("Content-Encoding") or "").strip().lower())
        return r.status, r.geturl(), decodificar(datos, r.headers.get_content_charset()), nota


def espera_reintento(e):
    try:
        return min(float(e.headers.get("Retry-After", "")), MAX_ESPERA)
    except (TypeError, ValueError):
        return PAUSA * 5


def pedir(url):
    """(status, final_url, text, note). status = HTTP code, or 0 if it failed (the note says why).
    If the certificate is wrong, it requests again without verifying it. It retries once, after a pause, what is
    usually temporary: timeout, dropped connection, 429 (too many requests) and 5xx server errors."""
    ctx, nota, reintento = CONTEXTO, "", True
    while True:
        try:
            est, final, texto, aviso = abrir(url, ctx)
            nota = "; ".join(x for x in (nota, aviso) if x)
            if not texto.strip():
                nota = nota or "la respuesta llegó vacía"
            return est, final, texto, nota
        except HTTPError as e:
            if e.code in REINTENTABLES and reintento:
                reintento = False
                time.sleep(espera_reintento(e))
                continue
            return e.code, url, "", f"HTTP {e.code}" + (" (demasiados pedidos)" if e.code == 429 else "")
        except Exception as e:  # noqa: BLE001 - a broken site must not stop the probe
            motivo = motivo_error(e)
            if motivo == "certificado inválido" and ctx is CONTEXTO:
                ctx, nota = SIN_VERIFICAR, motivo
                continue
            if motivo in ("timeout", "conexión cortada") and reintento:
                reintento = False
                time.sleep(PAUSA * 3)
                continue
            return 0, url, "", motivo


def texto_visible(html):
    t = re.sub(r"<(script|style|noscript|svg)\b.*?</\1>", " ", html, flags=re.S | re.I)
    t = re.sub(r"<[^>]+>", " ", t)
    return re.sub(r"\s+", " ", t)


def objetos_evento(html):
    """The Event objects of the page JSON-LD."""
    encontrados = []

    def recorrer(x):
        if isinstance(x, list):
            for i in x:
                recorrer(i)
        elif isinstance(x, dict):
            tipos = x.get("@type")
            tipos = [tipos] if isinstance(tipos, str) else (tipos or [])
            if any(isinstance(t, str) and t.endswith("Event") for t in tipos):
                encontrados.append(x)
            for k in ("@graph", "itemListElement", "item", "subEvent"):
                if k in x:
                    recorrer(x[k])

    for m in re.finditer(r'<script[^>]+application/ld\+json[^>]*>(.*?)</script>', html, re.S | re.I):
        try:
            recorrer(json.loads(m.group(1).strip()))
        except ValueError:
            pass
    return encontrados


def eventos_jsonld(html):
    """Number of Event objects in the page JSON-LD, and up to 3 examples."""
    objs = objetos_evento(html)
    return len(objs), [{"titulo": str(x.get("name", ""))[:60], "inicio": str(x.get("startDate", ""))[:25]} for x in objs[:3]]


def enlaces_agenda(html, base):
    """Up to 3 links of the same site that look like the agenda and 2 for talleres or visitas (they usually have
    their own page, outside the agenda); short paths first."""
    host = dominio(base)
    vistos, fuertes, programas = set(), [], []
    for m in re.finditer(r'<a\b[^>]*?href=["\']([^"\'#]+)["\'][^>]*>(.*?)</a>', html, re.S | re.I):
        u = urljoin(base, m.group(1).strip())
        p = urlparse(u)
        if p.scheme not in ("http", "https") or dominio(u) != host or RE_IGNORAR_RUTA.search(p.path + "?" + p.query):
            continue
        clave = (p.path.rstrip("/").lower(), p.query)
        if clave in vistos or p.path.rstrip("/") == urlparse(base).path.rstrip("/"):
            continue
        texto = re.sub(r"<[^>]+>", " ", m.group(2))
        prof = len([s for s in p.path.split("/") if s])  # short paths = sections, not event pages
        if RE_AGENDA.search(p.path) or RE_AGENDA.search(texto[:60]):
            vistos.add(clave)
            fuertes.append((prof, u))
        elif RE_PROGRAMAS.search(p.path) or RE_PROGRAMAS.search(texto[:60]):
            vistos.add(clave)
            programas.append((prof, u))
    orden = lambda x: x[0]  # noqa: E731
    return [u for _, u in sorted(fuertes, key=orden)[:3] + sorted(programas, key=orden)[:2]]


def plataforma(html):
    return [n for n, rx in (("wordpress", r"wp-content|wp-json"), ("tribe", r"tribe-events|wp-json/tribe"),
                            ("wix", r"wixstatic|wix\.com"), ("squarespace", r"squarespace"),
                            ("shopify", r"cdn\.shopify"), ("tiendanube", r"tiendanube|nuvem")) if re.search(rx, html, re.I)]


# --- reading without a browser (--corrida) ------------------------------------------------
# It only serves to confirm that there ARE events. If none appears, the site still goes to the browser.

MAX_TEXTO_PAGINA, MAX_TEXTO = 12_000, 30_000


def limpiar(t):
    return re.sub(r"\s+", " ", html_lib.unescape(re.sub(r"<[^>]+>", " ", t or ""))).strip()


def texto_linktree(html):
    """The links of a Linktree as 'title [url]' (they come in the page JSON, not in the HTML), or ''."""
    m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', html, re.S)
    try:
        props = json.loads(m.group(1))["props"]["pageProps"]
    except (AttributeError, ValueError, KeyError, TypeError):
        return ""
    cuenta = props.get("account") or {}
    lineas = [f"Linktree @{cuenta.get('username', '')}: {limpiar(cuenta.get('pageTitle') or '')}",
              limpiar(cuenta.get("description") or "")]
    for l in props.get("links") or []:
        if l.get("title") or l.get("url"):
            lineas.append(f"{limpiar(l.get('title') or '')} [{l.get('url') or ''}]")
    return "\n".join(x for x in lineas if x)


def texto_legible(html, base):
    """Page text with line breaks and the links to the same site as 'text [url]'."""
    if dominio(base) in ("linktr.ee", "linktree.com"):
        lt = texto_linktree(html)
        if lt:
            return lt
    t = re.sub(r"<(script|style|noscript|svg|head)\b.*?</\1>|<!--.*?-->", " ", html, flags=re.S | re.I)
    host = dominio(base)

    def enlace(m):
        u, txt = urljoin(base, html_lib.unescape(m.group(1).strip())), limpiar(m.group(2))
        if not txt or dominio(u) != host or RE_IGNORAR_RUTA.search(urlparse(u).path):
            return f" {txt} "
        return f" {txt} [{u}] "

    t = re.sub(r'<a\b[^>]*?href=["\']([^"\'#]+)["\'][^>]*>(.*?)</a>', enlace, t, flags=re.S | re.I)
    t = re.sub(r"<br\s*/?>|</(p|div|li|h\d|tr|article|section|header|footer)>", "\n", t, flags=re.I)
    t = html_lib.unescape(re.sub(r"<[^>]+>", " ", t))
    lineas, previa = [], None
    for ln in t.splitlines():
        ln = re.sub(r"\s+", " ", ln).strip()
        if ln and ln != previa:
            lineas.append(ln)
        previa = ln or previa
    return "\n".join(lineas)


def guardar_texto(sid, paginas):
    partes, total = [], 0
    for u, h in paginas.items():
        bloque = f"=== {u} ===\n{texto_legible(h, u)[:MAX_TEXTO_PAGINA]}"
        if total + len(bloque) > MAX_TEXTO:
            bloque = bloque[:MAX_TEXTO - total]
        partes.append(bloque)
        total += len(bloque)
        if total >= MAX_TEXTO:
            break
    ruta = TEXTOS / f"{sid}.txt"
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text("\n\n".join(partes), encoding="utf-8")
    return ruta.relative_to(RAIZ).as_posix()


def fecha_hora(v):
    """('AAAA-MM-DD', 'HH:MM' or '') from '2026-10-16T21:15:00-03:00', '2026-10-17T15:00:00Z' or '2026-10-16 20:00:00'."""
    v = str(v or "").strip()
    try:
        d = datetime.fromisoformat(v.replace(" ", "T", 1) if re.match(r"\d{4}-\d\d-\d\d \d", v) else v)
    except ValueError:
        return (v[:10], "") if re.match(r"\d{4}-\d\d-\d\d", v) else ("", "")
    if d.tzinfo:
        d = d.astimezone(ZONA_BA)
    con_hora = "T" in v or " " in v
    return d.date().isoformat(), (d.strftime("%H:%M") if con_hora and (d.hour, d.minute) != (0, 0) else "")


def precio_de(costo, gratis=False):
    costo = limpiar(str(costo or ""))
    if gratis or re.fullmatch(r"(0+([.,]0+)?|free|gratis|gratuito)", costo, re.I):
        return "Gratis"
    if re.fullmatch(r"\d+([.,]\d+)?", costo):
        return f"$ {costo}"
    return costo[:40]


def evento_api(e, con_lugar):
    ini, hora = fecha_hora(e.get("start_date"))
    fin, _ = fecha_hora(e.get("end_date"))
    venue = e.get("venue") if isinstance(e.get("venue"), dict) else {}
    return {"titulo": limpiar(e.get("title")), "fecha_inicio": ini, "fecha_fin": fin if fin and fin != ini else "",
            "hora": "" if e.get("all_day") else hora, "lugar": limpiar(venue.get("venue")) if con_lugar else "",
            "direccion": limpiar(venue.get("address")), "precio": precio_de(e.get("cost")),
            "url": e.get("url", ""), "descripcion": limpiar(e.get("description"))[:400]}


def evento_ld(x, con_lugar):
    ini, hora = fecha_hora(x.get("startDate"))
    fin, _ = fecha_hora(x.get("endDate"))
    loc = x.get("location")
    loc = loc[0] if isinstance(loc, list) and loc else loc
    loc = loc if isinstance(loc, dict) else {}
    dire = loc.get("address")
    dire = dire.get("streetAddress", "") if isinstance(dire, dict) else dire
    oferta = x.get("offers")
    oferta = oferta[0] if isinstance(oferta, list) and oferta else oferta
    oferta = oferta if isinstance(oferta, dict) else {}
    return {"titulo": limpiar(x.get("name")), "fecha_inicio": ini, "fecha_fin": fin if fin and fin != ini else "",
            "hora": hora, "lugar": limpiar(loc.get("name")) if con_lugar else "", "direccion": limpiar(dire),
            "precio": precio_de(oferta.get("price", oferta.get("lowPrice")), x.get("isAccessibleForFree") is True),
            "url": x.get("url", "") if str(x.get("url", "")).startswith("http") else "",
            "descripcion": limpiar(x.get("description"))[:400]}


def en_ventana(eventos, desde, hasta):
    vistos, out = set(), []
    for e in eventos:
        clave = (e["titulo"].lower(), e["fecha_inicio"])
        if e["titulo"] and e["fecha_inicio"] and clave not in vistos and \
                (e["fecha_fin"] or e["fecha_inicio"]) >= desde and e["fecha_inicio"] <= hasta:
            vistos.add(clave)
            out.append(e)
    return out


def sondear_sitio(s, leer=None):
    """leer = {"desde", "hasta", "con_lugar"}: besides classifying, it collects events (API/JSON-LD) or the agenda
    text in out['_eventos'] / out['_paginas']."""
    out = {"id": s["id"], "web": s["web"], "plataforma": [], "pedidos": 0}
    est, final, html, nota = pedir(s["web"])
    out["pedidos"] += 1
    if not 200 <= est < 300 or not html.strip():
        out.update(clase="unreachable", motivo=nota or f"HTTP {est}")
        return out
    out["url_final"] = final
    if dominio(final) != dominio(s["web"]):
        out["redirige_a"] = dominio(final)
    out["plataforma"] = plataforma(html)
    paginas = {final: html}

    if "tribe" in out["plataforma"]:
        time.sleep(PAUSA)
        base = f"{urlparse(final).scheme}://{urlparse(final).netloc}"
        e2, _, cuerpo, _ = pedir(f"{base}/wp-json/tribe/events/v1/events?per_page=5")
        out["pedidos"] += 1
        try:
            api = json.loads(cuerpo) if e2 == 200 else {}
            if api.get("events"):
                out.update(clase="api", eventos_api=api.get("total", len(api["events"])),
                           ejemplos=[{"titulo": e.get("title", "")[:60], "inicio": e.get("start_date", "")[:16]} for e in api["events"][:3]])
                if not leer:
                    return out
                crudos, url_api = [], (f"{base}/wp-json/tribe/events/v1/events?per_page=50"
                                       f"&start_date={leer['desde']}&end_date={leer['hasta']}%2023:59:59")
                for pagina in range(1, 5):
                    time.sleep(PAUSA)
                    e3, _, c3, _ = pedir(f"{url_api}&page={pagina}")
                    out["pedidos"] += 1
                    lote = json.loads(c3).get("events", []) if e3 == 200 else []
                    crudos += lote
                    if len(lote) < 50:
                        break
                out["_eventos"] = en_ventana([evento_api(e, leer["con_lugar"]) for e in crudos], leer["desde"], leer["hasta"])
                out["_urls"] = [final, url_api]
                if out["_eventos"]:
                    return out
        except ValueError:
            pass

    for u in enlaces_agenda(html, final):
        time.sleep(PAUSA)
        e2, f2, h2, _ = pedir(u)
        out["pedidos"] += 1
        if e2 == 200 and h2:
            paginas[f2] = h2
    out["paginas_agenda"] = [u for u in paginas if u != final]

    n_ld, ej, mejor = 0, [], 0
    for u, h in paginas.items():
        n, e = eventos_jsonld(h)
        n_ld += n
        ej = ej or e
        mejor = max(mejor, len(RE_FECHA.findall(texto_visible(h))))
    out["jsonld_eventos"], out["fechas_en_texto"] = n_ld, mejor
    out["texto_portada"] = len(texto_visible(html))
    if n_ld:
        out.update(clase="jsonld", ejemplos=ej)
    elif out["texto_portada"] < 400 or (SPA.search(html) and mejor < 3 and not paginas.keys() - {final}):
        out["clase"] = "needs_browser"
    elif mejor >= 3:
        out["clase"] = "html"
    else:
        out["clase"] = "sin_agenda_vista" if not out["paginas_agenda"] else "needs_browser"
    if leer:
        if out["clase"] == "jsonld":
            # Listings only (2 or more events on the page): a single event page does not say what else is in the agenda.
            listados = {u: objs for u, objs in ((u, objetos_evento(h)) for u, h in paginas.items()) if len(objs) >= 2}
            objs = [x for lista in listados.values() for x in lista]
            out["_eventos"] = en_ventana([evento_ld(x, leer["con_lugar"]) for x in objs], leer["desde"], leer["hasta"])
            out["_urls"] = list(paginas)
            out["_entradas"] = list(listados)
            if not listados:
                out["_sin_listado"] = True
        if out["clase"] in ("html", "jsonld", "api"):
            out["_paginas"] = paginas
    return out


def imagen_de(x):
    """https URL of the picture of a JSON-LD object (string, list or ImageObject), or ''."""
    img = x.get("image")
    img = img[0] if isinstance(img, list) and img else img
    img = img.get("url", "") if isinstance(img, dict) else img
    return img if isinstance(img, str) and img.startswith("https://") else ""


MAX_FICHAS = 80  # event pages opened per site to fill in what the listing lacks


def completar_desde_fichas(eventos):
    """The listing's JSON-LD often has no price, picture or time: they are on each event's own page. Opens the page
    of every event that has a `url` and lacks one of them (up to MAX_FICHAS per site, with a pause between pages)
    and fills in `precio`, `imagen`, `hora` and `descripcion` from its JSON-LD. Returns how many events have no
    `url` of their own (they stay as the listing gave them)."""
    abiertas = 0
    for e in eventos:
        falta = not e.get("precio") or not e.get("imagen") or not e.get("hora")
        if not e.get("url") or not falta or abiertas >= MAX_FICHAS:
            continue
        abiertas += 1
        est, _, html, _ = pedir(e["url"])
        time.sleep(PAUSA)
        objs = objetos_evento(html) if est == 200 else []
        if not objs:
            continue
        x = next((o for o in objs if fecha_hora(o.get("startDate"))[0] == e["fecha_inicio"]), objs[0])
        ficha = evento_ld(x, False)
        e["precio"] = e.get("precio") or ficha["precio"]
        e["hora"] = e.get("hora") or ficha["hora"]
        e["imagen"] = e.get("imagen") or imagen_de(x)
        if len(e.get("descripcion", "")) < 40:
            e["descripcion"] = ficha["descripcion"] or e.get("descripcion", "")
    return sum(1 for e in eventos if not e.get("url"))


def guardar_eventos(r):
    """Saves with `crawl.py guardar` the events the API or JSON-LD gave. Only con_eventos: if there are no events,
    or validation rejects them, the site is left to read the text or open the browser (r['error'])."""
    eventos, urls, entradas = r.pop("_eventos", None), r.pop("_urls", []), r.pop("_entradas", None)
    if r.pop("_sin_listado", False):
        r["error"] = "el JSON-LD está solo en fichas sueltas, no en un listado: puede faltar parte de la agenda"
        return False
    if not eventos:
        if r["clase"] in ("api", "jsonld"):
            r["error"] = "no dio eventos en la ventana"
        return False
    fuente = "la API de The Events Calendar" if r["clase"] == "api" else "el JSON-LD de la página"
    sin_url = completar_desde_fichas(eventos)
    if sin_url:
        r["sin_enlace_propio"] = sin_url  # no page of their own to open: price and picture stay as the listing gave them
    res = {"id": r["id"], "canal": "web", "estado": "con_eventos", "urls_visitadas": urls, "intentos": 1,
           "scroll_completo": False, "evidencia": "",
           "enlaces_candidatos": [{"texto": "página leída por el sondeo", "url": u, "visitado": True} for u in urls],
           "eventos": eventos, "entradas": entradas if entradas is not None else urls[:1],
           "comportamiento": {"extraccion": f"sin navegador: {fuente} (scripts/sondear.py --corrida)"},
           "nota": f"Leído sin navegador desde {fuente}: {len(eventos)} eventos en la ventana."}
    ruta = TMP / f"{r['id']}.json"
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    p = subprocess.run([sys.executable, str(RAIZ / "scripts" / "crawl.py"), "guardar", str(ruta)],
                       capture_output=True, text=True, encoding="utf-8")
    if p.returncode != 0:
        r["error"] = (p.stdout + p.stderr).strip()[-600:]
        print(f"  no se guardó {r['id']}: {r['error'][:200]}")
        return False
    r["guardado"] = len(eventos)
    (TEXTOS / f"{r['id']}.txt").unlink(missing_ok=True)
    r.pop("texto", None)
    return True


def leer_pagina(args):
    """Prints a page as the probe sees it: status, JSON-LD events and the text with links as 'text [url]'."""
    url = args[args.index("--leer") + 1]
    desde = args[args.index("--desde") + 1] if "--desde" in args else ""
    maximo = int(args[args.index("--max") + 1]) if "--max" in args else 20_000
    global TIMEOUT
    TIMEOUT = int(args[args.index("--timeout") + 1]) if "--timeout" in args else TIMEOUT
    est, final, html, nota = pedir(url)
    print(f"# {est} {final}" + (f" ({nota})" if nota else ""))
    for x in objetos_evento(html)[:60]:
        lugar = x.get("location") if isinstance(x.get("location"), dict) else {}
        print(f"# JSON-LD: {str(x.get('startDate', ''))[:16]} | {limpiar(x.get('name'))} | {limpiar(lugar.get('name'))}")
    texto = texto_legible(html, final) if html else ""
    i = texto.find(desde) if desde else 0
    print(texto[max(i, 0):max(i, 0) + maximo])


def main():
    args = sys.argv[1:]
    if "--leer" in args:
        return leer_pagina(args)
    ids = {args[i + 1] for i, a in enumerate(args) if a == "--id"}
    limite = int(args[args.index("--limite") + 1]) if "--limite" in args else 0
    hilos = int(args[args.index("--hilos") + 1]) if "--hilos" in args else 8
    corrida_modo = "--corrida" in args
    doc = leer_json(SITIOS)
    sitios = [s for s in doc["sitios"] if s.get("web") and s.get("rastrear") is not False and (not ids or s["id"] in ids)]
    if corrida_modo:
        corrida = leer_json(CORRIDA)
        if not corrida or corrida.get("fin"):
            sys.exit("No hay corrida abierta: correr primero `python scripts/crawl.py iniciar`.")
        pend = {i.split("|")[0] for i in corrida["cola"] if i.endswith("|web") and i not in corrida["hechos"]}
        sitios = [s for s in sitios if s["id"] in pend]
        desde, hasta = corrida["ventana"]["desde"], corrida["ventana"]["hasta"]
    if limite:
        sitios = sitios[:limite]
    # One thread per domain: two pages are not requested at once from the same site.
    por_dominio = defaultdict(list)
    for s in sitios:
        por_dominio[dominio(s["web"])].append(s)

    def grupo(lista):
        res = []
        for s in lista:
            if corrida_modo:  # the venue of each event is only needed in aggregators and sites with several venues
                leer_s = {"desde": desde, "hasta": hasta,
                          "con_lugar": s.get("tipo") in ("agregador", "descubrimiento") or len(s.get("lugares", [])) != 1}
            try:
                r = sondear_sitio(s, leer_s if corrida_modo else None)
            except Exception as e:  # noqa: BLE001
                r = {"id": s["id"], "web": s["web"], "clase": "unreachable", "motivo": f"error del sondeo: {e}"[:120]}
            paginas = r.pop("_paginas", None)
            if paginas:  # the text stays on disk; the HTML is not kept in memory
                r["texto"] = guardar_texto(s["id"], paginas)
            r["fecha"] = time.strftime("%Y-%m-%d %H:%M")
            res.append(r)
            print(f"  {r['clase']:<16} {s['id']}", flush=True)
            time.sleep(PAUSA)
        return res

    print(f"Sondeando {len(sitios)} webs en {len(por_dominio)} dominios con {hilos} hilos…", flush=True)
    t0 = time.time()
    with ThreadPoolExecutor(hilos) as ex:
        resultados = [r for lote in ex.map(grupo, por_dominio.values()) for r in lote]
    previo = {s["id"]: ((s.get("ultimo") or {}).get("web") or {}).get("estado", "sin_dato") for s in doc["sitios"]}
    for r in resultados:
        r["estado_corrida_anterior"] = previo.get(r["id"], "sin_dato")
    if corrida_modo:  # one by one: `guardar` writes sitios.json and corrida.json
        guardados = [r["id"] for r in resultados if guardar_eventos(r)]
        print(f"\nGuardados sin navegador ({len(guardados)}): {', '.join(guardados) or 'ninguno'}")
    # It is merged with the previous report: a partial probe does not erase what was known about the other sites.
    anterior = leer_json(SALIDA, {}) or {}
    nuevos_ids = {r["id"] for r in resultados}
    todos = [{**r, "fecha": r.get("fecha", anterior.get("fecha", ""))} for r in anterior.get("sitios", [])
             if r["id"] not in nuevos_ids] + resultados
    escribir_json(SALIDA, {"fecha": time.strftime("%Y-%m-%d %H:%M"), "segundos": round(time.time() - t0), "sitios": todos})

    print(f"\n{len(resultados)} sitios en {round(time.time() - t0)} s. Informe: {SALIDA}")
    print("Por clase:", dict(Counter(r["clase"] for r in resultados).most_common()))
    cruce = Counter((r["estado_corrida_anterior"], r["clase"]) for r in resultados)
    print("Contra lo que encontró el navegador la corrida anterior (estado → clase del sondeo):")
    for (est, clase), n in sorted(cruce.items()):
        print(f"  {est:<14} → {clase:<16} {n}")
    print("Motivos de unreachable:", dict(Counter(r.get("motivo", "")[:40] for r in resultados if r["clase"] == "unreachable").most_common(8)))


if __name__ == "__main__":
    main()
