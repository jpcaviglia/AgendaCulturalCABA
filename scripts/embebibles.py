"""Which domains may be shown inside an iframe (the website's "+ info" button).

A site that sends `X-Frame-Options: DENY/SAMEORIGIN` or `Content-Security-Policy: frame-ancestors` without
allowing other origins shows up blank inside an iframe, and the browser does not tell the page. That is why
one link per domain is tested beforehand and the result is saved in data/embebibles.json (tested again after
DIAS_VALIDEZ days, or after DIAS_REINTENTO if it could not be read). armar_agenda.py sets `embebible` on
each event.

Direct use (report only): python scripts/embebibles.py
"""
import re
import ssl
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from comun import DATOS, dominio, escribir_json, hoy, leer_json

CACHE = DATOS / "embebibles.json"
DIAS_VALIDEZ, DIAS_REINTENTO = 30, 7
ORIGEN = "jpcaviglia.github.io"  # where the website is published
UA = "Mozilla/5.0 (compatible; AgendaCulturalCABA; prueba de iframe)"


def permite_iframe(url):
    """(True/False, reason). Requests the page and looks at the headers of the final response."""
    if not url.startswith("https://"):
        return False, "no es https (el navegador lo bloquea dentro de una página https)"
    try:
        r = urlopen(Request(url, headers={"User-Agent": UA}), timeout=15, context=ssl.create_default_context())
    except HTTPError as e:
        return False, f"HTTP {e.code}"
    except Exception as e:  # noqa: BLE001 - a down site does not stop the build
        return False, f"{type(e).__name__}"
    with r:
        xfo = (r.headers.get("X-Frame-Options") or "").strip().lower()
        csp = " ".join(r.headers.get_all("Content-Security-Policy") or []).lower()
    m = re.search(r"frame-ancestors([^;]*)", csp)
    if m:
        fuentes = m.group(1).split()
        if "*" in fuentes or "https:" in fuentes or any(ORIGEN in f for f in fuentes):
            return True, "frame-ancestors lo permite"
        return False, f"frame-ancestors {m.group(1).strip()}"
    if xfo in ("deny", "sameorigin") or xfo.startswith("allow-from"):
        return False, f"X-Frame-Options {xfo}"
    return True, ""


def vigente(entrada):
    try:
        edad = (hoy() - date.fromisoformat(entrada["fecha"])).days
    except (KeyError, ValueError):
        return False
    motivo = entrada.get("motivo", "")
    fallo_red = motivo.startswith("HTTP 5") or (motivo and not motivo.startswith(("HTTP", "X-Frame", "frame", "no es")))
    return edad < (DIAS_REINTENTO if fallo_red else DIAS_VALIDEZ)


def marcar(eventos):
    """Sets e['embebible'] on each event. Returns how many domains were tested."""
    cache = leer_json(CACHE, {})
    ejemplo = {}
    for e in eventos:
        d = dominio(e.get("url", ""))
        if d:
            ejemplo.setdefault(d, e["url"])
    probar = [d for d in ejemplo if not vigente(cache.get(d, {}))]
    with ThreadPoolExecutor(8) as hilos:
        for d, (ok, motivo) in zip(probar, hilos.map(lambda d: permite_iframe(ejemplo[d]), probar)):
            cache[d] = {"ok": ok, "motivo": motivo, "fecha": hoy().isoformat(), "url": ejemplo[d]}
    if probar:
        escribir_json(CACHE, dict(sorted(cache.items())))
    for e in eventos:
        e["embebible"] = bool(cache.get(dominio(e.get("url", "")), {}).get("ok"))
    return len(probar)


if __name__ == "__main__":
    evs = (leer_json(DATOS / "eventos.json", {}) or {}).get("eventos", [])
    n = marcar(evs)
    si = sum(1 for e in evs if e["embebible"])
    print(f"{n} dominios probados; {si} de {len(evs)} eventos se pueden mostrar en un iframe.")
