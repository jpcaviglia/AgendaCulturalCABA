"""Looks for the Linktree of each Instagram in data/crawl/sitios.json, without opening Instagram.

Opening an Instagram profile spends quota and the bio link is only visible there. But the Linktree is almost
always named like the account: linktr.ee/<account> is tried (and the account without dots or underscores,
which Linktree does not always accept). A user equal to the account is accepted; a variant, only if the page
names the Instagram account or the venue. What is found is saved in `enlace_bio` and the skill reads it before
opening Instagram (`sondear.py --leer <enlace_bio>`). What was not found is noted in `bio_probada` and is not
tried again until DIAS_REPROBAR days later.

Usage:
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
    """True if the Linktree belongs to the site: same user, or the page names the account or the venue."""
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
    """(Linktree url, text) or (None, reason)."""
    for usuario in candidatos(sitio["instagram"]):
        url = f"https://linktr.ee/{usuario}"
        est, _, html, nota = pedir(url)
        time.sleep(PAUSA)
        if est == 404:
            continue
        if est != 200 or not html:
            return None, f"{url}: {est} {nota}"  # network failure or block: it is retried next time
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
        elif texto:  # network failure: not noted, it is retried
            fallas += 1
            print(f"  {s['instagram']}: no se pudo probar ({texto})")
        else:
            s["bio_probada"] = hoy().isoformat()
        if not simular and i % 25 == 0:  # saved little by little: if it is cut off, what was done is not lost
            escribir_json(SITIOS, doc)
    if not simular:
        escribir_json(SITIOS, doc)
    print(f"Linktree encontrados: {encontrados} de {len(pendientes)} ({con_fechas} con fechas en los enlaces); "
          f"{fallas} no se pudieron probar.")


if __name__ == "__main__":
    main()
