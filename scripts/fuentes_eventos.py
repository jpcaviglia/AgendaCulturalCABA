"""Adaptadores de fuentes de eventos. Cada uno devuelve eventos normalizados
con los campos extra "fuentes" y "_tipo" (turismo, sitio, agregador o manual)."""
import csv
import html
import json
import re
import time
import urllib.error
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urljoin, urlparse

from datetime import timedelta

from comun import AGENDA_TURISMO_NOMBRE, DATOS, dominio, hoy, leer_agenda_turismo, obtener

RE_JSONLD = re.compile(r'<script[^>]+application/ld\+json[^>]*>(.*?)</script>', re.S | re.I)
RE_ENLACE_AGENDA = re.compile(
    r'href=["\']([^"\']*/(?:agenda|eventos?|programaci[oó]n|cartelera|calendario|funciones|conciertos|events?)/?[^"\']*)["\']',
    re.I,
)
RE_CABA = re.compile(r"buenos aires|caba|capital federal|ciudad aut", re.I)
MANUAL = DATOS / "fuente" / "eventos_manuales.csv"


def limpiar(t):
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", t or ""))).strip()


def evento(titulo, fecha_inicio, fuente, tipo, **kw):
    return {
        "titulo": limpiar(titulo), "categoria": kw.get("categoria", ""), "lugar": limpiar(kw.get("lugar", "")),
        "barrio": kw.get("barrio", ""), "direccion": limpiar(kw.get("direccion", "")),
        "fecha_inicio": fecha_inicio, "fecha_fin": kw.get("fecha_fin", ""), "hora": kw.get("hora", ""),
        "horarios": limpiar(kw.get("horarios", "")), "precio": kw.get("precio") or "Consultar",
        "descripcion": limpiar(kw.get("descripcion", ""))[:500], "url": kw.get("url", ""),
        "dominio": dominio(kw.get("url", "")), "fuentes": [fuente], "_tipo": tipo,
    }


# --- Turismo BA --------------------------------------------------------------

def turismo():
    out = []
    for a in leer_agenda_turismo():
        if not a["fecha_inicio"]:
            continue
        e = evento(a["titulo"], a["fecha_inicio"], AGENDA_TURISMO_NOMBRE, "turismo", **{
            k: a[k] for k in ("categoria", "lugar", "barrio", "direccion", "horarios", "precio", "descripcion", "url")})
        e["_en_curso_ok"] = True  # la agenda no informa fecha de fin
        out.append(e)
    return out


# --- JSON-LD (schema.org/Event) ---------------------------------------------

def _tipos(nodo):
    t = nodo.get("@type", [])
    return [t] if isinstance(t, str) else list(t)


def _recorrer(nodo):
    if isinstance(nodo, list):
        for n in nodo:
            yield from _recorrer(n)
    elif isinstance(nodo, dict):
        if any(t.endswith("Event") for t in _tipos(nodo)):
            yield nodo
        for clave in ("@graph", "itemListElement", "item", "subEvent"):
            if clave in nodo:
                yield from _recorrer(nodo[clave])


def _fecha_hora(valor):
    m = re.match(r"(\d{4}-\d{2}-\d{2})(?:[T ](\d{2}:\d{2}))?", str(valor or ""))
    return (m.group(1), m.group(2) or "") if m else ("", "")


def _lugar(nombre_ficha, venue):
    """Si el sitio es de un lugar conocido, el lugar es ese (y la sala, si la ficha la indica: 'Konex · Patio').
    Así la búsqueda por nombre del lugar encuentra todos sus eventos, no solo los que mencionan el nombre."""
    if not venue:
        return nombre_ficha or ""
    venue = venue.title() if venue.isupper() else venue
    if not nombre_ficha or limpiar(nombre_ficha).lower() == venue.lower() or venue.lower() in limpiar(nombre_ficha).lower():
        return nombre_ficha or venue
    return f"{venue} · {limpiar(nombre_ficha)}"


def eventos_jsonld(html_texto, base_url, fuente, tipo, lugar_defecto="", barrio_defecto="", filtrar_caba=False):
    out = []
    for bloque in RE_JSONLD.findall(html_texto):
        try:
            datos = json.loads(html.unescape(bloque.strip()))
        except ValueError:
            continue
        for n in _recorrer(datos):
            f_ini, hora = _fecha_hora(n.get("startDate"))
            if not f_ini or not n.get("name"):
                continue
            loc = n.get("location") or {}
            if isinstance(loc, list):
                loc = loc[0] if loc else {}
            if not isinstance(loc, dict):
                loc = {}
            dir_ = loc.get("address", "")
            localidad = ""
            if isinstance(dir_, dict):
                localidad = f"{dir_.get('addressLocality', '')} {dir_.get('addressRegion', '')}"
                dir_ = dir_.get("streetAddress", "")
            if filtrar_caba and localidad.strip() and not RE_CABA.search(localidad):
                continue
            ofertas = n.get("offers") or {}
            if isinstance(ofertas, list):
                ofertas = ofertas[0] if ofertas else {}
            gratis = isinstance(ofertas, dict) and str(ofertas.get("price", "")) in ("0", "0.0", "0.00")
            tipo_ev = n.get("eventType")
            out.append(evento(
                n["name"], f_ini, fuente, tipo, hora=hora, fecha_fin=_fecha_hora(n.get("endDate"))[0],
                lugar=_lugar(loc.get("name"), lugar_defecto), direccion=dir_ if isinstance(dir_, str) else "",
                barrio=barrio_defecto, precio="Gratis" if gratis else "Consultar",
                descripcion=n.get("description", ""), url=urljoin(base_url, n.get("url") or base_url),
                categoria=tipo_ev if isinstance(tipo_ev, str) else "",
            ))
    return out


def agregador(src):
    _, final, texto = obtener(src["url"])
    return eventos_jsonld(texto, final, src["nombre"], "agregador", filtrar_caba=True)


def saleplan(src, max_detalles=200):
    """SalePlan: los listados solo traen nombre y enlace; fecha y lugar están en el JSON-LD de cada ficha.

    El paginado (?page=) lo resuelve el navegador, no el servidor, así que se recorren varias
    vistas ya filtradas por fecha (hoy, mañana, semana, fin de semana, agenda de la Ciudad).
    """
    vistas = ["https://saleplan.ar/buenos-aires/" + v for v in
              ("que-hacer-hoy", "que-hacer-manana", "que-hacer-esta-semana", "que-hacer-este-fin-de-semana", "eventos")]
    vistas += [src["url"], "https://saleplan.ar/agenda?provincia=02&localidad=02014010"]
    fichas = {}
    for v in vistas:
        try:
            _, _, texto = obtener(v)
        except Exception:
            continue
        for m in re.finditer(r'https://saleplan\.ar/[^"\s]+/planes/([A-Z0-9]+)/[^"\s]+', texto):
            fichas.setdefault(m.group(1), m.group(0))
    urls = list(fichas.values())[:max_detalles]

    def ficha(u):
        for intento in range(3):
            try:
                _, final, texto = obtener(u, timeout=12)
                return eventos_jsonld(texto, final, src["nombre"], "agregador", filtrar_caba=True)
            except urllib.error.HTTPError as e:
                if e.code != 429:
                    return []
                time.sleep(5 * (intento + 1))  # el sitio limita el ritmo: se espera y se reintenta
            except Exception:
                return []
        return []

    out = []
    for u in urls:  # en serie y con pausa, para respetar el límite del sitio
        out += ficha(u)
        time.sleep(0.7)
    return out


ADAPTADORES = {"jsonld": agregador, "saleplan": saleplan}


# --- Sitios de lugares ------------------------------------------------------

def _rastrear_lugar(l):
    """Devuelve (eventos, nota). Sin datos estructurados no se inventa nada: queda para revisión."""
    try:
        _, final, texto = obtener(l["web"], timeout=12)
    except Exception as e:
        return [], f"Inaccesible ({type(e).__name__})"
    paginas = [(final, texto)]
    enlaces = []
    for h in RE_ENLACE_AGENDA.findall(texto):
        u = urljoin(final, html.unescape(h))
        if dominio(u) == dominio(final) and u not in enlaces and u != final:
            enlaces.append(u)
    for u in enlaces[:2]:
        try:
            _, f2, t2 = obtener(u, timeout=12)
            paginas.append((f2, t2))
        except Exception:
            pass
    out = []
    for url, t in paginas:
        out += eventos_jsonld(t, url, l["nombre"], "sitio", lugar_defecto=l["nombre"], barrio_defecto=l.get("barrio", ""))
    if out:
        return out, ""
    return [], "Sin datos estructurados (revisar a mano)" if enlaces or l["estado"].startswith("Tiene") else "Sin agenda detectable"


def sitios_de_lugares(max_workers=8):
    """Rastrea los sitios propios de data/lugares.json que tienen o probablemente tienen agenda."""
    lugares = json.loads((DATOS / "lugares.json").read_text(encoding="utf-8"))
    objetivo = [l for l in lugares if l.get("web") and l["estado"].startswith(("Tiene", "Probable"))
                and l.get("tipo_web") in ("Sitio propio", "Gobierno o universidad")]
    eventos, sin_datos = [], []
    with ThreadPoolExecutor(max_workers) as ex:
        for l, (evs, nota) in zip(objetivo, ex.map(_rastrear_lugar, objetivo)):
            eventos += evs
            if nota:
                sin_datos.append({"lugar": l["nombre"], "web": l["web"], "motivo": nota})
    return eventos, sin_datos


# --- Sitemaps -----------------------------------------------------------------

RE_SITEMAP_EVENTOS = re.compile(r"espect|evento|event|agenda|show|funcion|cartelera|program|muestra|exposici|exhibici|actividad|obra|concierto|ciclo", re.I)
RE_SITEMAP_PASADO = re.compile(r"anterior|pasad|past|archiv|histor", re.I)
ESTADOS_SIN_SITEMAP = ("caido", "no_es_agenda", "desactualizado")


def _locs(xml):
    """(url, lastmod) de un sitemap."""
    out = []
    for bloque in re.findall(r"<(?:url|sitemap)>(.*?)</(?:url|sitemap)>", xml, flags=re.S):
        loc = re.search(r"<loc>\s*(.*?)\s*</loc>", bloque, flags=re.S)
        mod = re.search(r"<lastmod>\s*(.*?)\s*</lastmod>", bloque, flags=re.S)
        if loc:
            out.append((html.unescape(loc.group(1)), mod.group(1) if mod else ""))
    return out


def _sitemap_raices(web):
    base = "{0.scheme}://{0.netloc}".format(urlparse(web))
    raices = []
    try:
        _, _, robots = obtener(base + "/robots.txt", timeout=6)
        raices += re.findall(r"(?im)^sitemap:\s*(\S+)", robots)
    except Exception:
        pass
    return raices or [base + "/sitemap.xml", base + "/sitemap_index.xml", base + "/wp-sitemap.xml"]


def eventos_por_sitemap(item, max_fichas=25):
    """Descubre fichas de eventos en el sitemap del sitio (típico de WordPress) y lee su JSON-LD.
    Sirve cuando la agenda se arma con JavaScript y la portada no trae eventos. Devuelve (eventos, nota)."""
    nombre, web = item["nombre"], item["web"]
    fichas = []
    for raiz in _sitemap_raices(web):
        try:
            _, _, xml = obtener(raiz, timeout=6)
        except Exception:
            continue
        pendientes = _locs(xml)
        vistos = 0
        while pendientes and vistos < 40:
            url, mod = pendientes.pop(0)
            vistos += 1
            if url.endswith(".xml") or "sitemap" in url:
                if RE_SITEMAP_EVENTOS.search(url) and not RE_SITEMAP_PASADO.search(url):
                    try:
                        _, _, sub = obtener(url, timeout=6)
                        pendientes += _locs(sub)
                    except Exception:
                        pass
            elif RE_SITEMAP_EVENTOS.search(urlparse(url).path) and not RE_SITEMAP_PASADO.search(url):
                fichas.append((mod, url))
        if fichas:
            break
    if not fichas:
        return [], "sin sitemap de eventos"
    corte = (hoy() - timedelta(days=120)).isoformat()
    recientes = [(m, u) for m, u in set(fichas) if not m or m[:10] >= corte]
    fichas = [u for _, u in sorted(recientes, reverse=True)[:max_fichas]]
    out = []
    fallos = 0
    for u in fichas:
        try:
            _, final, texto = obtener(u, timeout=8)
        except Exception:
            fallos += 1
            if fallos >= 3:  # sitio lento o bloqueando: no insistir
                break
            continue
        out += eventos_jsonld(texto, final, nombre, "sitio", lugar_defecto=nombre, barrio_defecto=item.get("barrio", ""))
    return out, ("" if out else "fichas sin datos estructurados")


def sitemaps(max_workers=12):
    """Aplica eventos_por_sitemap a los sitios del mapa de agendas que no estén caídos ni descartados."""
    ruta = DATOS / "fuente" / "mapa_agendas.json"
    if not ruta.exists():
        return [], []
    barrios = {l["nombre"]: l.get("barrio", "") for l in json.loads((DATOS / "lugares.json").read_text(encoding="utf-8"))}
    sitios = [{**s, "barrio": barrios.get(s["nombre"], "")} for s in json.loads(ruta.read_text(encoding="utf-8"))
              if s.get("revision", {}).get("estado") not in ESTADOS_SIN_SITEMAP and s.get("web")]
    eventos, sin = [], []
    with ThreadPoolExecutor(max_workers) as ex:
        for s, (evs, nota) in zip(sitios, ex.map(eventos_por_sitemap, sitios)):
            eventos += evs
            if evs:
                sin.append({"lugar": s["nombre"], "eventos_sitemap": len(evs)})
    return eventos, sin


def galerias(max_workers=8):
    """Galerías y museos de arte de data/galerias.json. Sus muestras tienen fecha de fin, por eso
    las que ya empezaron siguen vigentes. Casi ninguna publica datos estructurados: lo que no se
    pueda leer acá queda en la cola de revisión con navegador."""
    ruta = DATOS / "galerias.json"
    if not ruta.exists():
        return [], []
    todas = [g for g in json.loads(ruta.read_text(encoding="utf-8"))["galerias"] if g.get("web")]
    eventos, sin_datos = [], []
    with ThreadPoolExecutor(max_workers) as ex:
        for g, (evs, nota) in zip(todas, ex.map(_rastrear_lugar, [{**g, "estado": "Tiene"} for g in todas])):
            for e in evs:
                e["categoria"] = e["categoria"] or "Artes visuales"
            eventos += evs
            if nota:
                sin_datos.append({"lugar": g["nombre"], "web": g["web"], "motivo": nota})
    return eventos, sin_datos


def lugares_solo_instagram():
    """Lugares sin sitio propio utilizable: Instagram pide login, así que van a la cola de carga manual."""
    lugares = json.loads((DATOS / "lugares.json").read_text(encoding="utf-8"))
    return [{"lugar": l["nombre"], "instagram": l["instagram"], "barrio": l.get("barrio", "")}
            for l in lugares if l.get("instagram") and l.get("tipo_web") in ("", "Red social o enlace")]


# --- Carga manual (Instagram u otras) -----------------------------------------

def manuales():
    """Eventos cargados a mano en data/fuente/eventos_manuales.csv (p. ej. leídos de Instagram)."""
    if not MANUAL.exists():
        return []
    out = []
    with MANUAL.open(encoding="utf-8-sig", newline="") as f:
        for fila in csv.DictReader(f):
            if not fila.get("titulo") or not re.match(r"\d{4}-\d{2}-\d{2}$", fila.get("fecha_inicio", "")):
                continue
            out.append(evento(fila["titulo"], fila["fecha_inicio"], "Carga manual", "manual", **{
                k: fila.get(k, "") for k in ("categoria", "lugar", "barrio", "direccion", "horarios", "precio",
                                             "descripcion", "url", "fecha_fin", "hora")}))
    return out


def agregadores_habilitados():
    fuentes = json.loads((DATOS / "fuentes.json").read_text(encoding="utf-8"))
    return [s for s in fuentes if s.get("adaptador") in ADAPTADORES and s.get("habilitada", True)]
