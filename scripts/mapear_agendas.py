"""Mapea dónde está la agenda de cada sitio (lugares y galerías) y qué método hace falta para leerla.

Uso:
    python scripts/mapear_agendas.py

Genera data/fuente/mapa_agendas.json. Cada entrada tiene:
  agenda_url  página de la agenda (si se encontró), para que la rutina entre directo ahí
  metodo      jsonld | html | ticketera | navegador (JS, bloqueo o error) | sin_agenda
  detalle     evidencia (cantidad de fechas, ticketeras enlazadas, motivo del error)
Los sitios con metodo "navegador" se revisan con Chrome (ver rutinas/actualizar_agenda.md).
"""
import json
import re
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urljoin

from comun import DATOS, dominio, obtener
from fuentes_eventos import RE_ENLACE_AGENDA, eventos_jsonld, limpiar
import html as _html

TICKETERAS = ("passline", "alternativateatral", "eventbrite", "ticketek", "tuentrada", "universe.com",
              "entradauno", "plateanet", "bonoentrada", "boleteria", "ticketportal", "teatrix")
MESES = r"(?:ene|feb|mar|abr|may|jun|jul|ago|sep|set|oct|nov|dic)[a-z]*"
RE_FECHA = re.compile(rf"\b\d{{1,2}}\s*(?:de\s+)?{MESES}\b|\b\d{{1,2}}/\d{{1,2}}(?:/\d{{2,4}})?\b", re.I)
RE_SOLO_ANCLA = re.compile(r"agenda|eventos?|programaci|cartelera|calendario|funciones|conciertos|muestras?|exposicion|exhibicion", re.I)


def _texto(html):
    return limpiar(re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", html, flags=re.S | re.I))


def _candidatos(html, base):
    """Enlaces del mismo dominio que parecen de agenda: por ruta y por texto del enlace."""
    vistos = []
    for h in RE_ENLACE_AGENDA.findall(html):
        vistos.append(urljoin(base, _html.unescape(h)))
    for h, t in re.findall(r'<a[^>]+href=["\']([^"\']+)["\'][^>]*>(.*?)</a>', html, flags=re.S | re.I):
        if RE_SOLO_ANCLA.search(limpiar(t)) and len(limpiar(t)) < 40:
            vistos.append(urljoin(base, _html.unescape(h)))
    out = []
    for u in vistos:
        u = u.split("#")[0]
        if dominio(u) == dominio(base) and u != base and u not in out and not re.search(r"\.(jpg|png|pdf|css|js)$", u, re.I):
            out.append(u)
    return out


def analizar(item):
    nombre, web = item["nombre"], item["web"]
    res = {"nombre": nombre, "web": web, "agenda_url": "", "metodo": "navegador", "detalle": ""}
    try:
        _, final, html = obtener(web, timeout=12)
    except Exception as e:
        res["detalle"] = f"No respondió al script ({type(e).__name__}); abrir en el navegador"
        return res
    paginas = [(final, html)]
    for u in _candidatos(html, final)[:3]:
        try:
            _, f2, h2 = obtener(u, timeout=12)
            paginas.append((f2, h2))
        except Exception:
            pass
    mejor = None
    for url, h in paginas:
        n_ld = len(eventos_jsonld(h, url, nombre, "sitio"))
        texto = _texto(h)
        n_f = len(RE_FECHA.findall(texto))
        tick = sorted({t for t in TICKETERAS if t in h.lower()})
        puntaje = (n_ld > 0, n_f, len(texto))
        if mejor is None or puntaje > mejor[0]:
            mejor = (puntaje, url, n_ld, n_f, tick, len(texto))
    _, url, n_ld, n_f, tick, largo = mejor
    res["agenda_url"] = url if url != final else (paginas[0][0] if len(paginas) == 1 else url)
    if n_ld:
        res["metodo"], res["detalle"] = "jsonld", f"{n_ld} eventos con datos estructurados"
    elif n_f >= 3:
        res["metodo"], res["detalle"] = "html", f"{n_f} fechas en el HTML"
    elif tick:
        res["metodo"], res["detalle"] = "ticketera", "enlaza a " + ", ".join(tick)
    elif largo < 1500:
        res["detalle"] = "casi sin texto en el HTML (probable sitio con JavaScript)"
    else:
        res["metodo"], res["detalle"] = "sin_agenda", "no se detectan fechas ni ticketeras en la portada ni en enlaces de agenda"
    return res


def main():
    corregidos = json.loads((DATOS / "fuente" / "sitios_corregidos.json").read_text(encoding="utf-8"))         if (DATOS / "fuente" / "sitios_corregidos.json").exists() else {}
    lugares = json.loads((DATOS / "lugares.json").read_text(encoding="utf-8"))
    galerias = json.loads((DATOS / "galerias.json").read_text(encoding="utf-8"))["galerias"]
    items = [{"nombre": g["nombre"], "web": g["web"], "origen": "galeria"} for g in galerias if g.get("web")]
    vistos = {dominio(i["web"]) for i in items}
    for l in lugares:
        d = dominio(l["web"])
        if l.get("web") and d and d not in vistos and "instagram.com" not in d and l.get("tipo_web") != "Agregador":
            vistos.add(d)
            items.append({"nombre": l["nombre"], "web": l["web"], "origen": "lugar"})
    for i in items:  # sitios cuyo dominio original cayó y se encontró el actual (data/fuente/sitios_corregidos.json)
        c = corregidos.get(i["nombre"], {})
        if "web" in c:
            i["web"] = c["web"]
    items = [i for i in items if i["web"]]
    with ThreadPoolExecutor(8) as ex:
        resultados = [{**i, **r} for i, r in zip(items, ex.map(analizar, items))]
    (DATOS / "fuente" / "mapa_agendas.json").write_text(json.dumps(resultados, ensure_ascii=False, indent=1), encoding="utf-8")
    cuenta = {}
    for r in resultados:
        cuenta[r["metodo"]] = cuenta.get(r["metodo"], 0) + 1
    print(f"{len(resultados)} sitios:", cuenta)


if __name__ == "__main__":
    main()
