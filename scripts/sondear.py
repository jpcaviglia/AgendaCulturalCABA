"""Sondeo de solo lectura: qué sitios de data/crawl/sitios.json se podrían leer sin navegador.

Hace pedidos HTTP simples (sin JavaScript) a la portada de cada web y a sus 3 enlaces de agenda más
probables, y clasifica cada sitio. No escribe nada en data/: el informe queda en data/crawl/local/sondeo.json
(se sube al repo, para usarlo desde otra máquina) y el resumen se imprime. No saca conclusiones de "no hay eventos": lo que no
se puede leer así sigue yendo al navegador.

Clases:
    api             la API de The Events Calendar (WordPress) devuelve eventos
    jsonld          la portada o una página de agenda trae eventos en JSON-LD
    html            la agenda trae el listado en el HTML (varias fechas en el texto), pero hay que leerlo
    needs_browser   el HTML casi no tiene texto o parece una app de JavaScript
    sin_agenda_vista  carga, pero no se encontró página de agenda ni fechas (no es prueba de que no haya)
    unreachable     no cargó (DNS, timeout, error HTTP, bloqueo); el motivo queda en el informe

Uso:
    python scripts/sondear.py [--limite N] [--id ID ...] [--hilos N]   # solo el informe
    python scripts/sondear.py --corrida [--id ID ...]                  # paso 1b de la skill actualizar-agenda

Con --corrida sondea solo las webs pendientes de la corrida abierta y además:
    api / jsonld    si hay eventos en la ventana, los guarda con `crawl.py guardar` (con_eventos); esos sitios
                    ya no se abren en el navegador. Nunca guarda "sin eventos".
    html            deja el texto de la portada y las páginas de agenda en data/crawl/local/textos/<id>.txt;
                    `crawl.py siguiente` lo muestra para leerlo en vez de abrir el navegador.
El informe se fusiona con el anterior (por sitio, con su fecha).
"""
import gzip
import html as html_lib
import json
import re
import socket
import ssl
import subprocess
import sys
import time
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen

from comun import CORRIDA, CRAWL, RAIZ, SITIOS, ZONA_BA, dominio, escribir_json, leer_json

SALIDA = CRAWL / "local" / "sondeo.json"
TEXTOS = CRAWL / "local" / "textos"
TMP = CRAWL / "tmp"
UA = "Mozilla/5.0 (compatible; AgendaCulturalCABA-sondeo; lectura de agenda pública)"
TIMEOUT, MAX_BYTES, PAUSA = 15, 1_500_000, 1.0
MESES = "ene|feb|mar|abr|may|jun|jul|ago|sep|set|oct|nov|dic|jan|apr|aug|dec"
RE_FECHA = re.compile(rf"\b\d{{1,2}}\s*(de\s+)?({MESES})[a-záéíóú]*\.?\b|\b({MESES})[a-z]*\.?\s+\d{{1,2}}\b|\b\d{{1,2}}[/.]\d{{1,2}}([/.]\d{{2,4}})?\b", re.I)
RE_AGENDA = re.compile(r"agenda|cartelera|programaci|\beventos?\b|\bevents?\b|actividades|muestras?|exposici|exhibici|exhibitions?|funciones|conciertos|calendario|calendar|en-cartel|pr[oó]xim|upcoming", re.I)
RE_IGNORAR_RUTA = re.compile(r"\.(jpe?g|png|gif|webp|svg|css|js|zip|mp3|mp4|pdf)$|/lang/|[?&](lang|hl)=|/(en|pt)/?$", re.I)
SPA = re.compile(r'id="(root|__next|app)"|__NEXT_DATA__|ng-version|data-reactroot|window\.__NUXT__|wixui|id="comp-', re.I)
CONTEXTO = ssl.create_default_context()
SIN_VERIFICAR = ssl._create_unverified_context()  # solo para leer páginas públicas cuando el certificado está mal


def pedir(url):
    """(estado, url_final, texto, nota). estado = código HTTP, o 0 si falló (la nota dice por qué)."""
    nota = ""
    for ctx in (CONTEXTO, SIN_VERIFICAR):
        try:
            req = Request(url, headers={"User-Agent": UA, "Accept": "text/html,application/json;q=0.9,*/*;q=0.5",
                                        "Accept-Language": "es-AR,es;q=0.9", "Accept-Encoding": "gzip"})
            with urlopen(req, timeout=TIMEOUT, context=ctx) as r:
                datos = r.read(MAX_BYTES)
                if r.headers.get("Content-Encoding") == "gzip":
                    datos = gzip.decompress(datos)
                cs = r.headers.get_content_charset() or "utf-8"
                return r.status, r.geturl(), datos.decode(cs, "replace"), nota
        except HTTPError as e:
            return e.code, url, "", f"HTTP {e.code}"
        except ssl.SSLError as e:
            nota = "certificado inválido"
            continue
        except URLError as e:
            if isinstance(e.reason, ssl.SSLError) or "CERTIFICATE" in str(e.reason).upper():
                nota = "certificado inválido"
                continue
            return 0, url, "", f"{type(e.reason).__name__}: {e.reason}"[:120]
        except (socket.timeout, TimeoutError):
            return 0, url, "", "timeout"
        except Exception as e:  # noqa: BLE001 - un sitio roto no debe frenar el sondeo
            return 0, url, "", f"{type(e).__name__}: {e}"[:120]
    return 0, url, "", nota or "error"


def texto_visible(html):
    t = re.sub(r"<(script|style|noscript|svg)\b.*?</\1>", " ", html, flags=re.S | re.I)
    t = re.sub(r"<[^>]+>", " ", t)
    return re.sub(r"\s+", " ", t)


def objetos_evento(html):
    """Los objetos Event de los JSON-LD de la página."""
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
    """Cantidad de objetos Event en los JSON-LD de la página, y hasta 3 ejemplos."""
    objs = objetos_evento(html)
    return len(objs), [{"titulo": str(x.get("name", ""))[:60], "inicio": str(x.get("startDate", ""))[:25]} for x in objs[:3]]


def enlaces_agenda(html, base):
    """Hasta 3 enlaces del mismo sitio que parecen la agenda, los del menú primero."""
    host = dominio(base)
    vistos, fuertes = set(), []
    for m in re.finditer(r'<a\b[^>]*?href=["\']([^"\'#]+)["\'][^>]*>(.*?)</a>', html, re.S | re.I):
        u = urljoin(base, m.group(1).strip())
        p = urlparse(u)
        if p.scheme not in ("http", "https") or dominio(u) != host or RE_IGNORAR_RUTA.search(p.path + "?" + p.query):
            continue
        clave = (p.path.rstrip("/").lower(), p.query)
        if clave in vistos or p.path.rstrip("/") == urlparse(base).path.rstrip("/"):
            continue
        texto = re.sub(r"<[^>]+>", " ", m.group(2))
        if RE_AGENDA.search(p.path) or RE_AGENDA.search(texto[:60]):
            vistos.add(clave)
            fuertes.append((len([s for s in p.path.split("/") if s]), u))  # rutas cortas = secciones, no fichas
    return [u for _, u in sorted(fuertes, key=lambda x: x[0])[:3]]


def plataforma(html):
    return [n for n, rx in (("wordpress", r"wp-content|wp-json"), ("tribe", r"tribe-events|wp-json/tribe"),
                            ("wix", r"wixstatic|wix\.com"), ("squarespace", r"squarespace"),
                            ("shopify", r"cdn\.shopify"), ("tiendanube", r"tiendanube|nuvem")) if re.search(rx, html, re.I)]


# --- lectura sin navegador (--corrida) ------------------------------------------------
# Solo sirve para confirmar que HAY eventos. Si no aparece ninguno, el sitio sigue yendo al navegador.

MAX_TEXTO_PAGINA, MAX_TEXTO = 12_000, 30_000


def limpiar(t):
    return re.sub(r"\s+", " ", html_lib.unescape(re.sub(r"<[^>]+>", " ", t or ""))).strip()


def texto_legible(html, base):
    """Texto de la página con saltos de línea y los enlaces del mismo sitio como 'texto [url]'."""
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
    """('AAAA-MM-DD', 'HH:MM' o '') desde '2026-10-16T21:15:00-03:00', '2026-10-17T15:00:00Z' o '2026-10-16 20:00:00'."""
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
    """leer = {"desde", "hasta", "con_lugar"}: además de clasificar, junta eventos (API/JSON-LD) o el texto de la
    agenda en out['_eventos'] / out['_paginas']."""
    out = {"id": s["id"], "web": s["web"], "plataforma": [], "pedidos": 0}
    est, final, html, nota = pedir(s["web"])
    out["pedidos"] += 1
    if est != 200 or not html:
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
            # Solo listados (2 o más eventos en la página): una ficha suelta no dice qué más hay en la agenda.
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


def guardar_eventos(r):
    """Guarda con `crawl.py guardar` los eventos que dio la API o el JSON-LD. Solo con_eventos: si no hay eventos,
    o la validación los rechaza, el sitio queda para leer el texto o abrir el navegador (r['error'])."""
    eventos, urls, entradas = r.pop("_eventos", None), r.pop("_urls", []), r.pop("_entradas", None)
    if r.pop("_sin_listado", False):
        r["error"] = "el JSON-LD está solo en fichas sueltas, no en un listado: puede faltar parte de la agenda"
        return False
    if not eventos:
        if r["clase"] in ("api", "jsonld"):
            r["error"] = "no dio eventos en la ventana"
        return False
    fuente = "la API de The Events Calendar" if r["clase"] == "api" else "el JSON-LD de la página"
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


def main():
    args = sys.argv[1:]
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
    # Un hilo por dominio: no se le piden dos páginas a la vez al mismo sitio.
    por_dominio = defaultdict(list)
    for s in sitios:
        por_dominio[dominio(s["web"])].append(s)

    def grupo(lista):
        res = []
        for s in lista:
            if corrida_modo:  # el lugar de cada evento solo hace falta en agregadores y sitios con varios lugares
                leer_s = {"desde": desde, "hasta": hasta,
                          "con_lugar": s.get("tipo") in ("agregador", "descubrimiento") or len(s.get("lugares", [])) != 1}
            try:
                r = sondear_sitio(s, leer_s if corrida_modo else None)
            except Exception as e:  # noqa: BLE001
                r = {"id": s["id"], "web": s["web"], "clase": "unreachable", "motivo": f"error del sondeo: {e}"[:120]}
            paginas = r.pop("_paginas", None)
            if paginas:  # el texto queda en disco; el HTML no se guarda en memoria
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
    if corrida_modo:  # uno por uno: `guardar` escribe sitios.json y corrida.json
        guardados = [r["id"] for r in resultados if guardar_eventos(r)]
        print(f"\nGuardados sin navegador ({len(guardados)}): {', '.join(guardados) or 'ninguno'}")
    # Se fusiona con el informe anterior: un sondeo parcial no borra lo que se sabía de los demás sitios.
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
