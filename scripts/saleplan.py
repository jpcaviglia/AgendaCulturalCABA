"""SalePlan without a browser: reads the listings, keeps what no other source brought and saves it.

The SalePlan listings (/buenos-aires/eventos?page=N) are read with plain HTTP; the event pages are not (Cloudflare).
Each card has title, date, time, the SalePlan category and the neighborhood (in the URL), but not the venue.
Since 3 out of 4 SalePlan events are already brought by another source, the script discards the cards that
match (same day, similar title) the captures of the other sources and saves the rest, without a venue
("Lugar a confirmar" on the website).

That is why it goes at the end of the run, after all the other sources and before armar_agenda.py.

Usage:
    python scripts/saleplan.py [--simular] [--max-paginas N]

    --simular       reads and compares, but does not save (shows the summary)
    --max-paginas   cap on listing pages (150 by default)

Cards with neither neighborhood nor time are listed in data/crawl/tmp/saleplan_fichas.txt: they are the
only ones worth opening in the browser (to find out where they are).
"""
import html as html_lib
import json
import re
import subprocess
import sys
import time
from collections import defaultdict
from datetime import date, timedelta

from comun import CAPTURAS, CRAWL, DATOS, RAIZ, escribir_json, hoy, leer_json, sin_tildes, ventana
from deduplicar import _parecidos, norm_titulo
from sondear import PAUSA, pedir

ID = "saleplan-agenda-de-ciudad-de-buenos-aires"
LISTADO = "https://saleplan.ar/buenos-aires/eventos?page={}"
# The "Destacados" (guided tours, tango shows, tours: ongoing things) do not appear in /eventos, only above
# each weekly agenda page: the first one is enough.
DESTACADOS = "https://saleplan.ar/buenos-aires/que-hacer-esta-semana?page=1"
TMP = CRAWL / "tmp"
REINTENTOS, ESPERA_REINTENTO = 4, 15
MAX_EDAD_DIAS = 10  # same as armar_agenda.py: older captures do not count as "already covered"
MESES = {"ene": 1, "feb": 2, "mar": 3, "abr": 4, "may": 5, "jun": 6, "jul": 7, "ago": 8, "sep": 9, "set": 9,
         "oct": 10, "nov": 11, "dic": 12}
SIN_BARRIO = {"ciudad-de-buenos-aires", ""}
BARRIOS_EXTRA = {"boca": "La Boca", "nunez": "Núñez"}


def texto(fragmento):
    sin = re.sub(r"<(script|style|svg)\b.*?</\1>", " ", fragmento, flags=re.S | re.I)
    return [t.strip() for t in html_lib.unescape(re.sub(r"<[^>]+>", "\n", sin)).split("\n") if t.strip()]


def fecha_de(linea):
    """'Hoy · 17:00 hs', 'Mañana · 20:00 hs', 'sáb. 17 oct. · 00:00 hs' -> ('AAAA-MM-DD', 'HH:MM' or '')."""
    h = re.search(r"(\d{1,2}):(\d{2})", linea)
    hora = f"{int(h.group(1)):02d}:{h.group(2)}" if h else ""
    if hora == "00:00":  # SalePlan puts 00:00 when there is no time
        hora = ""
    l = sin_tildes(linea)
    if l.startswith("hoy"):
        return hoy().isoformat(), hora
    if l.startswith("manana"):
        return (hoy() + timedelta(days=1)).isoformat(), hora
    m = re.search(r"(\d{1,2}) ([a-z]{3})", l)
    if not m or m.group(2) not in MESES:
        return "", hora
    anio = hoy().year
    try:
        d = date(anio, MESES[m.group(2)], int(m.group(1)))
    except ValueError:
        return "", hora
    if (hoy() - d).days > 180:  # December -> January
        d = d.replace(year=anio + 1)
    return d.isoformat(), hora


def tarjetas(pagina):
    """The cards of one listing page."""
    out = []
    for bloque in pagina.split("data-event-card")[1:]:
        bloque = bloque[:8000]
        ident = re.search(r'data-event-id="(\w+)"', bloque)
        url = re.search(r'href="(https://saleplan\.ar/[^"]*/planes/[^"]+)"', bloque)
        t = texto(bloque)
        if not ident or not url or "Fecha y horario" not in t:
            continue
        i = t.index("Fecha y horario")
        if i < 3 or i + 1 >= len(t):
            continue
        fecha, hora = fecha_de(t[i + 1])
        partes = url.group(1).split("/")
        out.append({"id": ident.group(1), "url": url.group(1), "categoria": t[i - 3], "titulo": t[i - 2],
                    "localidad": t[i - 1], "fecha": fecha, "hora": hora, "terminada": "Función terminada" in t,
                    "barrio_slug": partes[4] if len(partes) > 4 and partes[3] == "ciudad-autonoma-de-buenos-aires" else ""})
    return out


def leer_listado(desde, hasta, max_paginas):
    """Goes through the listing until it passes the end of the window or no new cards appear."""
    vistas, urls = {}, []
    est, _, html, nota = pedir(DESTACADOS)
    if est == 200 and html:
        urls.append(DESTACADOS)
        for c in tarjetas(html):
            vistas[c["id"]] = c
    else:
        print(f"  destacados: {est} {nota} (se sigue sin ellos)")
    time.sleep(PAUSA)
    for n in range(1, max_paginas + 1):
        url = LISTADO.format(n)
        for intento in range(REINTENTOS):
            est, _, html, nota = pedir(url)
            if (est == 200 and html) or est == 404:
                break
            print(f"  página {n}: {est} {nota}; reintento en {ESPERA_REINTENTO} s")
            time.sleep(ESPERA_REINTENTO)
        if est == 404 and n > 1:  # the listing ended
            break
        if est != 200 or not html:
            # A cut in the middle of the listing is not the end: saving what was read would replace the capture with a part.
            sys.exit(f"No se pudo leer la página {n} del listado de SalePlan ({est} {nota}): no se guarda nada. "
                     "Volver a correrlo más tarde (o, si sigue fallando, abrir las entradas en el navegador).")
        urls.append(url)
        nuevas = [c for c in tarjetas(html) if c["id"] not in vistas]
        for c in nuevas:
            vistas[c["id"]] = c
        fechas = [c["fecha"] for c in nuevas if c["fecha"]]
        if not nuevas or (fechas and min(fechas) > hasta):
            break
        time.sleep(PAUSA)
    return list(vistas.values()), urls


def nombres_barrio():
    """slug -> name with accents, from the neighborhoods lugares.json already uses."""
    nombres = dict(BARRIOS_EXTRA)
    for l in leer_json(DATOS / "lugares.json", []):
        if l.get("barrio"):
            nombres.setdefault(re.sub(r"[^a-z0-9]+", "-", sin_tildes(l["barrio"])).strip("-"), l["barrio"])
    return nombres


def indice_otras_fuentes(desde, hasta):
    """date -> normalized titles of the events of all recent captures except the SalePlan one."""
    idx = defaultdict(set)
    tope = date.fromisoformat(hasta)
    for ruta in CAPTURAS.glob("*.json"):
        cap = leer_json(ruta) or {}
        if cap.get("id") == ID or not cap.get("fecha"):
            continue
        if (hoy() - date.fromisoformat(cap["fecha"])).days > MAX_EDAD_DIAS:
            continue
        for e in cap.get("eventos", []):
            try:
                d = date.fromisoformat(e["fecha_inicio"])
                fin = min(date.fromisoformat(e.get("fecha_fin") or e["fecha_inicio"]), tope)
            except (KeyError, ValueError):
                continue
            d = max(d, date.fromisoformat(desde))
            while d <= fin:
                idx[d.isoformat()].add(norm_titulo(e.get("titulo", "")))
                d += timedelta(days=1)
    return idx


def _id_plan(url):
    m = re.search(r"/planes/(\w+)/", url)
    return m.group(1) if m else ""


def _contenido(a, b):
    """All the words of the shorter title are in the other ("Gruesome en Argentina" in
    "GRUESOME - Unico Show en Argentina"). Requires 2 words or more so that one-word titles are not merged."""
    pa, pb = set(a.split()), set(b.split())
    corto, largo = (pa, pb) if len(pa) <= len(pb) else (pb, pa)
    genericas = {"argentina", "buenos", "aires", "caba", "the", "and"}
    return len(corto) >= 2 and bool(corto - genericas) and corto - genericas <= largo


def cubierto(tarjeta, idx):
    t = norm_titulo(tarjeta["titulo"])
    return any(_parecidos(t, otro, 0.85) or _contenido(t, otro) for otro in idx.get(tarjeta["fecha"], ()))


def main():
    simular = "--simular" in sys.argv
    max_paginas = int(sys.argv[sys.argv.index("--max-paginas") + 1]) if "--max-paginas" in sys.argv else 150
    desde, hasta = ventana()
    todas, urls = leer_listado(desde, hasta, max_paginas)
    # A card with a date before today and without "Función terminada" is something ongoing (guided tours, exhibitions,
    # daily shows): SalePlan puts the day it started listing it. It counts as current today.
    caba = [c for c in todas if c["localidad"] == "CABA" and c["fecha"] and c["fecha"] <= hasta and not c["terminada"]]
    for c in caba:
        c["en_curso"] = c["fecha"] < desde
    idx = indice_otras_fuentes(desde, hasta)
    nuevas = [c for c in caba if not cubierto({**c, "fecha": max(c["fecha"], desde)}, idx)]
    barrios = nombres_barrio()
    # What was already known from event pages opened before (venue, address, price) is kept by URL.
    previa = {_id_plan(e.get("url", "")): e for e in (leer_json(CAPTURAS / f"{ID}.web.json") or {}).get("eventos", [])}

    eventos, fichas = [], []
    for c in nuevas:
        b = c["barrio_slug"]
        barrio = "" if b in SIN_BARRIO else barrios.get(b, b.replace("-", " ").title())
        e = {"titulo": c["titulo"], "fecha_inicio": c["fecha"], "fecha_fin": desde if c["en_curso"] else c["fecha"],
             "hora": "" if c["en_curso"] else c["hora"], "lugar": "", "barrio": barrio, "categoria": c["categoria"],
             "url": c["url"], "descripcion": f"{c['categoria']}. Listado en SalePlan; el lugar figura en la ficha."}
        vieja = previa.get(c["id"])
        if vieja and vieja.get("lugar"):
            for k in ("lugar", "direccion", "barrio", "precio", "descripcion", "hora", "horarios"):
                if vieja.get(k):
                    e[k] = vieja[k]
            # The event page has the real range of what is ongoing (the card, only the first day).
            if c["en_curso"] and (vieja.get("fecha_fin") or "") >= desde:
                e["fecha_inicio"], e["fecha_fin"] = vieja["fecha_inicio"], vieja["fecha_fin"]
        elif not barrio and not c["hora"]:
            fichas.append(c["url"])
        eventos.append(e)

    # Long-running exhibitions and performances that started before today: the card is left outside the window,
    # but the previous capture (from event pages) had the range. They are kept while they are still current.
    guardados = {c["id"] for c in nuevas}
    for pid, e in previa.items():
        fin = e.get("fecha_fin") or e["fecha_inicio"]
        if (pid and pid not in guardados and e.get("lugar") and fin >= desde and fin > e["fecha_inicio"]
                and not cubierto({"titulo": e["titulo"], "fecha": max(e["fecha_inicio"], desde)}, idx)):
            eventos.append(e)

    print(f"SalePlan: {len(urls)} páginas, {len(todas)} tarjetas, {len(caba)} de CABA en la ventana "
          f"({desde} a {hasta}); {len(caba) - len(nuevas)} ya las trae otra fuente, {len(eventos)} nuevas "
          f"({sum(1 for e in eventos if e['lugar'])} con el lugar de una ficha ya leída, {len(fichas)} sin barrio ni hora).")
    TMP.mkdir(parents=True, exist_ok=True)
    (TMP / "saleplan_fichas.txt").write_text("".join(u + "\n" for u in fichas), encoding="utf-8")
    if simular or not eventos:
        return
    res = {"id": ID, "canal": "web", "estado": "con_eventos", "urls_visitadas": urls, "intentos": 1,
           "scroll_completo": True, "evidencia": "",
           "enlaces_candidatos": [{"texto": "listado de eventos", "url": urls[0], "visitado": True}],
           "eventos": eventos, "entradas": [LISTADO.format(1)],
           "comportamiento": {
               "extraccion": "sin navegador: scripts/saleplan.py al final de la corrida (listados por HTTP; "
                             "se descartan las tarjetas que ya trae otra fuente). No abrir en el navegador.",
               "limite": None},
           "nota": f"scripts/saleplan.py: {len(caba)} tarjetas de CABA en la ventana, {len(caba) - len(eventos)} ya "
                   f"cubiertas por otras fuentes, {len(eventos)} guardadas sin lugar."}
    ruta = TMP / f"{ID}.json"
    escribir_json(ruta, res)
    p = subprocess.run([sys.executable, str(RAIZ / "scripts" / "crawl.py"), "guardar", str(ruta)])
    sys.exit(p.returncode)


if __name__ == "__main__":
    main()
