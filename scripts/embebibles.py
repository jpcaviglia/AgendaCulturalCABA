"""Qué dominios se dejan mostrar dentro de un iframe (el botón "+ info" de la web).

Un sitio que manda `X-Frame-Options: DENY/SAMEORIGIN` o `Content-Security-Policy: frame-ancestors` sin permitir
otros orígenes se ve en blanco dentro de un iframe, y el navegador no le avisa a la página. Por eso se prueba
de antemano un enlace por dominio y se guarda el resultado en data/embebibles.json (se vuelve a probar a los
DIAS_VALIDEZ días, o a los DIAS_REINTENTO si no se pudo leer). armar_agenda.py pone `embebible` en cada evento.

Uso directo (solo el informe): python scripts/embebibles.py
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
ORIGEN = "jpcaviglia.github.io"  # donde se publica la web
UA = "Mozilla/5.0 (compatible; AgendaCulturalCABA; prueba de iframe)"


def permite_iframe(url):
    """(True/False, motivo). Pide la página y mira las cabeceras de la respuesta final."""
    if not url.startswith("https://"):
        return False, "no es https (el navegador lo bloquea dentro de una página https)"
    try:
        r = urlopen(Request(url, headers={"User-Agent": UA}), timeout=15, context=ssl.create_default_context())
    except HTTPError as e:
        return False, f"HTTP {e.code}"
    except Exception as e:  # noqa: BLE001 - un sitio caído no frena el armado
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
    """Pone e['embebible'] en cada evento. Devuelve cuántos dominios se probaron."""
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
