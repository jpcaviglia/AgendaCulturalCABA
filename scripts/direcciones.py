"""Fills in the address and neighborhood of events that have a venue but no address.

Sources, in order:
    1. data/lugares.json (domicilio) and data/galerias.json (domicilio), by venue name. A venue with a room
       ("Malba · Auditorio") is looked up by the part before the "·".
    2. data/direcciones.json: cache of addresses of venues that are not in those lists.
    3. Other events at the same venue that do bring an address (the most repeated one).
    4. With network: the Alternativa Teatral page of some event at the venue has the space with its address
       and neighborhood. It is saved in the cache (also when nothing was found, so the request is not
       repeated before DIAS_REINTENTO days).

Direct use (report, without writing eventos.json): python scripts/direcciones.py
"""
import html as html_lib
import re
import time
from collections import Counter, defaultdict
from datetime import date

from comun import DATOS, dominio, escribir_json, hoy, leer_json, sin_tildes

CACHE = DATOS / "direcciones.json"
DIAS_REINTENTO = 30
PAUSA = 1.0


def clave(lugar):
    return re.sub(r"\s+", " ", sin_tildes((lugar or "").split(" · ")[0])).strip()


def _de_alternativa(html):
    """(name, address, neighborhood) of the venue block in an Alternativa Teatral page, or None."""
    m = re.search(r'href="[^"]*/espacio\d+[^"]*"', html)
    if not m:
        return None
    inicio = html.rfind("<", 0, m.start())
    bloque = html[inicio:inicio + 3000]
    bloque = re.sub(r"<(script|style)\b.*?</\1>", " ", bloque, flags=re.S | re.I)
    partes = [p.strip() for p in html_lib.unescape(re.sub(r"<[^>]+>", "\n", bloque)).split("\n") if p.strip()]
    # Order in the page: NAME · address · (map) · neighborhood · - · CABA
    if len(partes) < 4 or "(mapa)" not in partes[:4]:
        return None
    i = partes.index("(mapa)")
    nombre, direccion = partes[0], partes[i - 1] if i >= 2 else ""
    barrio = partes[i + 1] if i + 1 < len(partes) and partes[i + 1] not in ("-", "CABA") else ""
    if not re.search(r"\d", direccion):  # an address without a street number is no use for the map
        return None
    return nombre, direccion, barrio


def _consultar_alternativa(url):
    from sondear import pedir  # only needed with network
    est, _, html, _ = pedir(url)
    return _de_alternativa(html) if est == 200 and html else None


def completar(eventos, consultar=True):
    """Sets 'direccion' (and 'barrio' if missing) on events that have a venue and no address.
    Returns (completed, pages_queried)."""
    conocidas = {}
    for l in leer_json(DATOS / "lugares.json", []) + (leer_json(DATOS / "galerias.json", {}) or {}).get("galerias", []):
        if l.get("domicilio"):
            conocidas.setdefault(clave(l["nombre"]), (l["domicilio"], l.get("barrio", "")))
    cache = leer_json(CACHE, {}) or {}
    for k, v in cache.items():
        if v.get("direccion"):
            conocidas.setdefault(k, (v["direccion"], v.get("barrio", "")))
    otras = defaultdict(Counter)
    for e in eventos:
        if e.get("lugar") and e.get("direccion"):
            otras[clave(e["lugar"])][(e["direccion"], e.get("barrio", ""))] += 1
    for k, c in otras.items():
        conocidas.setdefault(k, c.most_common(1)[0][0])

    faltan = [e for e in eventos if e.get("lugar") and not e.get("direccion")]
    consultadas = 0
    if consultar:
        ficha = {}
        for e in faltan:
            k = clave(e["lugar"])
            if k not in conocidas and dominio(e.get("url", "")) == "alternativateatral.com":
                ficha.setdefault(k, e["url"])
        for k, url in ficha.items():
            previo = cache.get(k, {})
            if previo and not previo.get("direccion"):
                try:
                    if (hoy() - date.fromisoformat(previo["fecha"])).days < DIAS_REINTENTO:
                        continue
                except (KeyError, ValueError):
                    pass
            r = _consultar_alternativa(url)
            consultadas += 1
            cache[k] = {"lugar": r[0] if r else "", "direccion": r[1] if r else "", "barrio": r[2] if r else "",
                        "fuente": url, "fecha": hoy().isoformat()}
            if r:
                conocidas[k] = (r[1], r[2])
            time.sleep(PAUSA)
        if consultadas:
            escribir_json(CACHE, dict(sorted(cache.items())))

    completados = 0
    for e in faltan:
        d = conocidas.get(clave(e["lugar"]))
        if d:
            e["direccion"] = d[0]
            e["barrio"] = e.get("barrio") or d[1]
            completados += 1
    return completados, consultadas


if __name__ == "__main__":
    evs = (leer_json(DATOS / "eventos.json", {}) or {}).get("eventos", [])
    antes = sum(1 for e in evs if e.get("lugar") and not e.get("direccion"))
    n, c = completar(evs)
    print(f"{antes} eventos sin dirección; se completaron {n} ({c} fichas consultadas).")
