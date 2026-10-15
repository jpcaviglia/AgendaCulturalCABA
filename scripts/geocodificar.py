"""Adds lat/lng to the events using Nominatim (OpenStreetMap), with a local cache.

The cache (data/geocache.json) avoids repeating requests: only new addresses are queried,
at 1 per second (Nominatim's limit). Results outside CABA are discarded.
"""
import json
import math
import re
import time
import urllib.parse
import urllib.request

from comun import DATOS, sin_tildes

CACHE = DATOS / "geocache.json"
VIEWBOX = "-58.532,-34.526,-58.334,-34.706"  # CABA: left,top,right,bottom
UA = "AgendaCulturalCABA/1.0 (https://github.com/jpcaviglia/AgendaCulturalCABA)"


def _consulta(texto):
    q = re.sub(r"\bC\d{4}[A-Z]{0,3}\b,?", "", texto)  # postal codes like C1123
    q = re.sub(r"\b(CABA|Argentina|Ciudad Autónoma de Buenos Aires)\b,?\s*", "", q, flags=re.I).strip(" ,")
    return f"{q}, Ciudad Autónoma de Buenos Aires, Argentina"


def _pedir(q):
    url = "https://nominatim.openstreetmap.org/search?" + urllib.parse.urlencode({
        "q": q, "format": "json", "limit": 1, "countrycodes": "ar", "viewbox": VIEWBOX, "bounded": 1})
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=20) as r:
        datos = json.load(r)
    return [round(float(datos[0]["lat"]), 6), round(float(datos[0]["lon"]), 6)] if datos else None


# Official neighborhood boundaries (data.buenosaires.gob.ar). They detect a point that landed on a homonymous street
# far from the neighborhood the event says (Av. Pedro de Mendoza 1929, La Boca, ended up in Villa Lugano).
BARRIOS = DATOS / "barrios.json"
LEJOS_KM, CERCA_KM = 3.0, 1.0
_ALIAS = {"la boca": "boca", "montserrat": "monserrat", "la paternal": "paternal", "villa gral.mitre": "villa gral. mitre"}


def _norm_barrio(b):
    b = sin_tildes(b).strip()
    return _ALIAS.get(b, b)


def _poligonos():
    try:
        datos = json.loads(BARRIOS.read_text(encoding="utf-8"))["barrios"]
    except (OSError, ValueError, KeyError):
        return {}
    return {_norm_barrio(n): ([g["coordenadas"]] if g["tipo"] == "Polygon" else g["coordenadas"]) for n, g in datos.items()}


def _dentro(lng, lat, anillo):
    c, j = False, len(anillo) - 1
    for i in range(len(anillo)):
        (xi, yi), (xj, yj) = anillo[i][:2], anillo[j][:2]
        if (yi > lat) != (yj > lat) and lng < (xj - xi) * (lat - yi) / (yj - yi) + xi:
            c = not c
        j = i
    return c


def distancia_barrio_km(pos, poligonos):
    """0 if the point is inside the neighborhood; otherwise the distance in km to the nearest edge."""
    lat, lng = pos
    if any(_dentro(lng, lat, p[0]) and not any(_dentro(lng, lat, h) for h in p[1:]) for p in poligonos):
        return 0.0
    kx, ky, mejor = 111.32 * math.cos(math.radians(lat)), 110.57, float("inf")
    for p in poligonos:
        for anillo in p:
            for (x1, y1), (x2, y2) in zip(anillo, anillo[1:]):
                ax, ay, bx, by = (x1 - lng) * kx, (y1 - lat) * ky, (x2 - lng) * kx, (y2 - lat) * ky
                dx, dy = bx - ax, by - ay
                t = max(0.0, min(1.0, -(ax * dx + ay * dy) / ((dx * dx + dy * dy) or 1)))
                mejor = min(mejor, math.hypot(ax + t * dx, ay + t * dy))
    return mejor


def ubicar_con_cache(eventos, lugares=()):
    """Like geocodificar_eventos, but only with the cache (no network)."""
    return geocodificar_eventos(eventos, lugares, consultar=False)


def geocodificar_eventos(eventos, lugares=(), consultar=True):
    """Fills in e['lat'], e['lng'] (or '' if it could not be located). Returns how many addresses it queried."""
    try:
        cache = json.loads(CACHE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        cache = {}
    domicilios = {l["nombre"]: l.get("domicilio", "") for l in lugares}
    poligonos = _poligonos()
    resueltas = {}
    consultadas = 0

    def buscar(q):
        """Position from the cache or from Nominatim. None if there is none; 'error' if the query failed."""
        nonlocal consultadas
        if q in cache:
            return cache[q]
        if not consultar:
            return "sin_red"
        try:
            cache[q] = _pedir(q)
        except Exception as ex:  # no network or block: it is not cached, it is retried next time
            print(f"  Geocodificación falló ({ex}); se reintenta en la próxima corrida")
            return "error"
        consultadas += 1
        time.sleep(1.1)
        return cache[q]

    for e in eventos:
        texto = e.get("direccion") or domicilios.get(e.get("lugar", ""), "")
        if not texto:
            e["lat"] = e["lng"] = ""
            continue
        pos = buscar(_consulta(texto))
        if pos in ("sin_red", "error"):
            e["lat"] = e["lng"] = ""
            continue
        # Far from the neighborhood the event says: repeated with the neighborhood in the query. If that lands in the neighborhood
        # (or next to it), it wins; otherwise the first one stays (the neighborhood may be the wrong one, not the point).
        nombre_barrio = _norm_barrio(e.get("barrio", ""))
        barrio = poligonos.get(nombre_barrio)
        if pos and barrio:
            # The same address and neighborhood repeat in many events: it is resolved only once.
            k = (texto, nombre_barrio)
            if k not in resueltas:
                resueltas[k] = pos
                if distancia_barrio_km(pos, barrio) > LEJOS_KM:
                    otra = buscar(_consulta(f"{texto}, {e['barrio']}"))
                    if otra not in (None, "sin_red", "error") and distancia_barrio_km(otra, barrio) <= CERCA_KM:
                        resueltas[k] = otra
            pos = resueltas[k]
        e["lat"], e["lng"] = (pos[0], pos[1]) if pos else ("", "")
    if consultadas:
        CACHE.write_text(json.dumps(cache, ensure_ascii=False, indent=1), encoding="utf-8")
    return consultadas
