"""Agrega lat/lng a los eventos usando Nominatim (OpenStreetMap), con caché local.

La caché (data/geocache.json) evita repetir pedidos: solo se consultan direcciones nuevas,
a razón de 1 por segundo (límite de Nominatim). Los resultados fuera de CABA se descartan.
"""
import json
import math
import re
import time
import urllib.parse
import urllib.request

from comun import DATOS, sin_tildes

CACHE = DATOS / "geocache.json"
VIEWBOX = "-58.532,-34.526,-58.334,-34.706"  # CABA: izquierda,arriba,derecha,abajo
UA = "AgendaCulturalCABA/1.0 (https://github.com/jpcaviglia/AgendaCulturalCABA)"


def _consulta(texto):
    q = re.sub(r"\bC\d{4}[A-Z]{0,3}\b,?", "", texto)  # códigos postales tipo C1123
    q = re.sub(r"\b(CABA|Argentina|Ciudad Autónoma de Buenos Aires)\b,?\s*", "", q, flags=re.I).strip(" ,")
    return f"{q}, Ciudad Autónoma de Buenos Aires, Argentina"


def _pedir(q):
    url = "https://nominatim.openstreetmap.org/search?" + urllib.parse.urlencode({
        "q": q, "format": "json", "limit": 1, "countrycodes": "ar", "viewbox": VIEWBOX, "bounded": 1})
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=20) as r:
        datos = json.load(r)
    return [round(float(datos[0]["lat"]), 6), round(float(datos[0]["lon"]), 6)] if datos else None


# Límites oficiales de los barrios (data.buenosaires.gob.ar). Sirven para detectar un punto que cayó en una calle
# homónima lejos del barrio que dice el evento (Av. Pedro de Mendoza 1929, La Boca, terminó en Villa Lugano).
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
    """0 si el punto está en el barrio; si no, la distancia en km al borde más cercano."""
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
    """Como geocodificar_eventos, pero solo con la caché (sin red)."""
    return geocodificar_eventos(eventos, lugares, consultar=False)


def geocodificar_eventos(eventos, lugares=(), consultar=True):
    """Completa e['lat'], e['lng'] (o '' si no se pudo ubicar). Devuelve cuántas direcciones consultó."""
    try:
        cache = json.loads(CACHE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        cache = {}
    domicilios = {l["nombre"]: l.get("domicilio", "") for l in lugares}
    poligonos = _poligonos()
    resueltas = {}
    consultadas = 0

    def buscar(q):
        """Posición de la caché o de Nominatim. None si no hay; 'error' si falló la consulta."""
        nonlocal consultadas
        if q in cache:
            return cache[q]
        if not consultar:
            return "sin_red"
        try:
            cache[q] = _pedir(q)
        except Exception as ex:  # sin red o bloqueo: no se cachea, se reintenta la próxima
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
        # Lejos del barrio que dice el evento: se repite con el barrio en la consulta. Si eso cae en el barrio
        # (o al lado), gana; si no, queda el primero (puede ser el barrio el que está mal, no el punto).
        nombre_barrio = _norm_barrio(e.get("barrio", ""))
        barrio = poligonos.get(nombre_barrio)
        if pos and barrio:
            # La misma dirección y barrio se repiten en muchos eventos: se resuelve una sola vez.
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
