"""Completa la dirección y el barrio de los eventos que tienen lugar pero no dirección.

Fuentes, en orden:
    1. data/lugares.json (domicilio) y data/galerias.json (domicilio), por nombre del lugar. Un lugar con sala
       ("Malba · Auditorio") se busca por la parte de antes del "·".
    2. data/direcciones.json: caché de direcciones de lugares que no están en esas listas.
    3. Otros eventos del mismo lugar que sí traen dirección (la más repetida).
    4. Con red: la ficha de Alternativa Teatral de algún evento del lugar trae el espacio con su dirección y
       barrio. Se guarda en la caché (también si no se encontró, para no repetir el pedido antes de
       DIAS_REINTENTO días).

Uso directo (informe, sin escribir eventos.json): python scripts/direcciones.py
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
    """(nombre, dirección, barrio) del bloque del espacio en una ficha de Alternativa Teatral, o None."""
    m = re.search(r'href="[^"]*/espacio\d+[^"]*"', html)
    if not m:
        return None
    inicio = html.rfind("<", 0, m.start())
    bloque = html[inicio:inicio + 3000]
    bloque = re.sub(r"<(script|style)\b.*?</\1>", " ", bloque, flags=re.S | re.I)
    partes = [p.strip() for p in html_lib.unescape(re.sub(r"<[^>]+>", "\n", bloque)).split("\n") if p.strip()]
    # Orden en la ficha: NOMBRE · dirección · (mapa) · barrio · - · CABA
    if len(partes) < 4 or "(mapa)" not in partes[:4]:
        return None
    i = partes.index("(mapa)")
    nombre, direccion = partes[0], partes[i - 1] if i >= 2 else ""
    barrio = partes[i + 1] if i + 1 < len(partes) and partes[i + 1] not in ("-", "CABA") else ""
    if not re.search(r"\d", direccion):  # una dirección sin altura no sirve para el mapa
        return None
    return nombre, direccion, barrio


def _consultar_alternativa(url):
    from sondear import pedir  # solo hace falta con red
    est, _, html, _ = pedir(url)
    return _de_alternativa(html) if est == 200 and html else None


def completar(eventos, consultar=True):
    """Pone 'direccion' (y 'barrio' si falta) en los eventos que tienen lugar y no dirección.
    Devuelve (completados, fichas_consultadas)."""
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
