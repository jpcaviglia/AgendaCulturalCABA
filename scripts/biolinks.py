"""Busca el Linktree de cada Instagram de data/crawl/sitios.json, sin abrir Instagram.

Abrir un perfil de Instagram gasta cupo y el enlace de la bio recién se ve ahí. Pero casi siempre el Linktree
se llama como la cuenta: se prueba linktr.ee/<cuenta> (y la cuenta sin puntos ni guiones bajos, que Linktree
no siempre acepta). Un usuario igual a la cuenta se acepta; una variante, solo si la página nombra la cuenta de
Instagram o el lugar. Lo encontrado queda en `enlace_bio` y la skill lo lee antes de abrir Instagram
(`sondear.py --leer <enlace_bio>`). Lo que no se encontró se anota en `bio_probada` y no se vuelve a probar
hasta DIAS_REPROBAR días después.

Uso:
    python scripts/biolinks.py [--simular] [--id ID ...]
"""
import json
import re
import sys
import time
from datetime import date

from comun import escribir_json, hoy, leer_json, sin_tildes, SITIOS
from sondear import PAUSA, RE_FECHA, pedir, texto_linktree

DIAS_REPROBAR = 60
GENERICAS = {"espacio", "cultural", "centro", "teatro", "club", "casa", "galeria", "bar", "arte", "sala", "buenos",
             "aires", "ciudad", "museo", "fundacion", "estudio", "complejo"}


def candidatos(cuenta):
    c = cuenta.lstrip("@").strip().lower()
    out = [c]
    for v in (c.replace(".", ""), c.replace(".", "").replace("_", ""), c.replace(".", "_")):
        if v and v not in out:
            out.append(v)
    return out


def coincide(sitio, cuenta, usuario, html):
    """True si el Linktree es del sitio: mismo usuario, o la página nombra la cuenta o el lugar."""
    c = cuenta.lstrip("@").lower()
    if usuario == c:
        return True
    texto = sin_tildes(html)
    if f"instagram.com/{c}" in texto:
        return True
    palabras = [p for p in re.findall(r"[a-z0-9]{5,}", sin_tildes(sitio["nombre"])) if p not in GENERICAS]
    lt = sin_tildes(texto_linktree(html))
    return bool(palabras) and all(p in lt for p in palabras)


def probar(sitio):
    """(url del Linktree, texto) o (None, motivo)."""
    for usuario in candidatos(sitio["instagram"]):
        url = f"https://linktr.ee/{usuario}"
        est, _, html, nota = pedir(url)
        time.sleep(PAUSA)
        if est == 404:
            continue
        if est != 200 or not html:
            return None, f"{url}: {est} {nota}"  # falla de red o bloqueo: se reintenta la próxima vez
        if coincide(sitio, sitio["instagram"], usuario, html):
            return url, texto_linktree(html)
    return None, ""


def main():
    simular = "--simular" in sys.argv
    ids = set(sys.argv[sys.argv.index("--id") + 1:]) if "--id" in sys.argv else None
    doc = leer_json(SITIOS)
    pendientes = []
    for s in doc["sitios"]:
        if not s.get("instagram") or s.get("enlace_bio") or (ids and s["id"] not in ids):
            continue
        try:
            if (hoy() - date.fromisoformat(s.get("bio_probada", ""))).days < DIAS_REPROBAR:
                continue
        except ValueError:
            pass
        pendientes.append(s)
    print(f"{len(pendientes)} Instagram sin enlace de bio conocido; probando Linktree…")
    encontrados, con_fechas, fallas = 0, 0, 0
    for i, s in enumerate(pendientes, 1):
        url, texto = probar(s)
        if url:
            encontrados += 1
            fechas = len(RE_FECHA.findall(texto))
            con_fechas += bool(fechas)
            print(f"  {s['instagram']}: {url}" + (f" ({fechas} fechas en los enlaces)" if fechas else ""))
            s["enlace_bio"] = url
            s.setdefault("notas", []).append(f"{hoy().isoformat()} [instagram] Linktree encontrado sin abrir Instagram "
                                             f"(scripts/biolinks.py): {url}")
            s.pop("bio_probada", None)
        elif texto:  # falla de red: no se anota, se reintenta
            fallas += 1
            print(f"  {s['instagram']}: no se pudo probar ({texto})")
        else:
            s["bio_probada"] = hoy().isoformat()
        if not simular and i % 25 == 0:  # se guarda de a poco: si se corta, no se pierde lo hecho
            escribir_json(SITIOS, doc)
    if not simular:
        escribir_json(SITIOS, doc)
    print(f"Linktree encontrados: {encontrados} de {len(pendientes)} ({con_fechas} con fechas en los enlaces); "
          f"{fallas} no se pudieron probar.")


if __name__ == "__main__":
    main()
