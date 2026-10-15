"""Agrega lat/lng a los eventos usando Nominatim (OpenStreetMap), con caché local.

La caché (data/geocache.json) evita repetir pedidos: solo se consultan direcciones nuevas,
a razón de 1 por segundo (límite de Nominatim). Los resultados fuera de CABA se descartan.
"""
import json
import re
import time
import urllib.parse
import urllib.request

from comun import DATOS

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


def geocodificar_eventos(eventos, lugares=()):
    """Completa e['lat'], e['lng'] (o '' si no se pudo ubicar). Devuelve cuántas direcciones consultó."""
    try:
        cache = json.loads(CACHE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        cache = {}
    domicilios = {l["nombre"]: l.get("domicilio", "") for l in lugares}
    consultadas = 0
    for e in eventos:
        texto = e.get("direccion") or domicilios.get(e.get("lugar", ""), "")
        if not texto:
            e["lat"] = e["lng"] = ""
            continue
        q = _consulta(texto)
        if q not in cache:
            try:
                cache[q] = _pedir(q)
            except Exception as ex:  # sin red o bloqueo: no se cachea, se reintenta la próxima
                print(f"  Geocodificación falló ({ex}); se reintenta en la próxima corrida")
                e["lat"] = e["lng"] = ""
                continue
            consultadas += 1
            time.sleep(1.1)
        pos = cache[q]
        e["lat"], e["lng"] = (pos[0], pos[1]) if pos else ("", "")
    CACHE.write_text(json.dumps(cache, ensure_ascii=False, indent=1), encoding="utf-8")
    return consultadas
