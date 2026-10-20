"""Looks for the picture of the events of a site that was saved without `imagen`. It uses the network (plain HTTP).

For every different event `url` in the site's last capture it reads the page and takes, in this order: og:image or
twitter:image, a few known `<img>` patterns of ticketing sites and museums, a CSS background of a Ministry of Culture
museum (`/media/uploads/site-N/destacados/...`) and the `image` of its JSON-LD. It never takes logos, icons, generic
building photos or an image shared by 3 or more events. It does not touch the capture: it writes a result file ready for
`crawl.py guardar`.

Usage:
    python scripts/imagenes.py <id> [<id>...]     # writes data/crawl/tmp/<id>.reimage.json and prints what it found
    python scripts/crawl.py guardar data/crawl/tmp/<id>.reimage.json

Pages that answer 403 (Passline, Resident Advisor, Malba, Fundación Andreani), single-page apps, pictures that only
exist in the page's JavaScript and `http://` pictures are not found here: read them from the browser (see navegador.md).
"""
import html
import json
import re
import sys
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urljoin

from comun import CAPTURAS, CRAWL, escribir_json, leer_json
from sondear import pedir

TMP = CRAWL / "tmp"
# Never a picture of the event: logos, icons, the museum's own generic photo, payment methods, theme assets.
GENERICAS = re.compile(r"logo|icon|sprite|\.svg|pixel|blank|avatar|flag|AECID_|maec_|CCE\.png|mnba-frente|opciones/|"
                       r"museosnacionales|ciudad-ba|vamos-ba|slogan|payment-methods|/static/", re.I)
# <img> patterns of platforms that have no og:image.
IMG_CONOCIDAS = re.compile(r"api\.alianzafrancesa\.org\.ar/uploads|cceba\.aecid\.es/documents/\d+/\d+/|"
                           r"proa\.org/images-exhibiciones|bucket\.tuentrada\.com.*/events/", re.I)
META = (r"<meta[^>]+property=[\"']og:image(?::secure_url)?[\"'][^>]+content=[\"']([^\"']+)",
        r"<meta[^>]+content=[\"']([^\"']+)[\"'][^>]+property=[\"']og:image",
        r"<meta[^>]+name=[\"']twitter:image[\"'][^>]+content=[\"']([^\"']+)")


def imagen_de(url):
    """(https url of the picture or "", how it was found or why not)."""
    try:
        codigo, _, cuerpo = pedir(url)[:3]
    except Exception:
        return "", "error de red"
    if codigo != 200:
        return "", f"HTTP {codigo}"
    cuerpo = cuerpo or ""
    for patron in META:
        m = re.search(patron, cuerpo, re.I)
        if m:
            u = urljoin(url, html.unescape(m.group(1)).strip())
            if GENERICAS.search(u):
                break
            return (u, "og") if u.startswith("https://") else ("", "solo http")
    for src in re.findall(r"<img[^>]+(?:data-src|src)=[\"']([^\"']+)", cuerpo):
        u = urljoin(url, html.unescape(src))
        if IMG_CONOCIDAS.search(u) and not GENERICAS.search(u) and u.startswith("https://"):
            return u, "img"
    for fondo in re.findall(r"url\(['\"]?([^)'\"]+)", cuerpo):
        if "/destacados/" in fondo and fondo.startswith("/media/"):
            return urljoin(url, fondo), "fondo css"
    m = re.search(r'"image"\s*:\s*"?(https://[^"\s,\]]+)', cuerpo)
    if m:
        return m.group(1).replace("\\/", "/"), "json-ld"
    return "", "sin imagen en la página"


def procesar(sid):
    cap = leer_json(CAPTURAS / f"{sid}.web.json")
    if not cap:
        print(f"{sid}: no hay captura web")
        return
    urls = sorted({e["url"] for e in cap["eventos"] if e.get("url") and not e["url"].lower().endswith(".pdf")})
    with ThreadPoolExecutor(6) as ex:
        halladas = dict(zip(urls, ex.map(imagen_de, urls)))
    repetidas = {u for u, n in Counter(g[0] for g in halladas.values() if g[0]).items() if n >= 3}
    n = 0
    for e in cap["eventos"]:
        img = (halladas.get(e.get("url")) or ("", ""))[0]
        if img and img not in repetidas:
            e["imagen"] = img
            n += 1
    motivos = Counter(g[1] for g in halladas.values())
    previo = leer_json(TMP / f"{sid}.json", {}) or {}
    res = {"id": sid, "canal": "web", "estado": cap.get("estado", "con_eventos"),
           "urls_visitadas": previo.get("urls_visitadas") or cap.get("urls_visitadas") or [], "intentos": 1,
           "scroll_completo": True, "enlaces_candidatos": previo.get("enlaces_candidatos", []), "evidencia": "",
           "eventos": cap["eventos"], "entradas": previo.get("entradas", []),
           "comportamiento": previo.get("comportamiento", {}),
           "nota": f"Imágenes agregadas desde las fichas ({n} de {len(cap['eventos'])} eventos).",
           "enlaces_nuevos": [], "sitios_nuevos": []}
    if previo.get("web_nueva"):
        res["web_nueva"] = previo["web_nueva"]
    escribir_json(TMP / f"{sid}.reimage.json", res)
    extra = f"; descartadas {len(repetidas)} imágenes repetidas en 3 o más eventos" if repetidas else ""
    print(f"{sid}: {n} de {len(cap['eventos'])} eventos con imagen {dict(motivos)}{extra}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    for sid in sys.argv[1:]:
        procesar(sid)
