"""SalePlan sin navegador: lee los listados, se queda con lo que ninguna otra fuente trajo y lo guarda.

Los listados de SalePlan (/buenos-aires/eventos?page=N) se leen con HTTP simple; las fichas no (Cloudflare).
Cada tarjeta trae título, fecha, hora, la categoría de SalePlan y el barrio (en la URL), pero no el lugar.
Como 3 de cada 4 eventos de SalePlan ya los trae otra fuente, el script descarta las tarjetas que coinciden
(mismo día, título parecido) con las capturas de las demás fuentes y guarda el resto, sin lugar
("Lugar a confirmar" en la web).

Por eso va al final de la corrida, después de todas las demás fuentes y antes de armar_agenda.py.

Uso:
    python scripts/saleplan.py [--simular] [--max-paginas N]

    --simular       lee y compara, pero no guarda (muestra el resumen)
    --max-paginas   tope de páginas del listado (por defecto 150)

Las tarjetas que no tienen ni barrio ni hora quedan listadas en data/crawl/tmp/saleplan_fichas.txt: son las
únicas que vale la pena abrir en el navegador (para saber dónde son).
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
# Los "Destacados" (visitas guiadas, shows de tango, tours: cosas en curso) no salen en /eventos, solo arriba de
# cada página de la agenda semanal: alcanza con la primera.
DESTACADOS = "https://saleplan.ar/buenos-aires/que-hacer-esta-semana?page=1"
TMP = CRAWL / "tmp"
REINTENTOS, ESPERA_REINTENTO = 4, 15
MAX_EDAD_DIAS = 10  # igual que armar_agenda.py: capturas más viejas no cuentan como "ya cubierto"
MESES = {"ene": 1, "feb": 2, "mar": 3, "abr": 4, "may": 5, "jun": 6, "jul": 7, "ago": 8, "sep": 9, "set": 9,
         "oct": 10, "nov": 11, "dic": 12}
SIN_BARRIO = {"ciudad-de-buenos-aires", ""}
BARRIOS_EXTRA = {"boca": "La Boca", "nunez": "Núñez"}


def texto(fragmento):
    sin = re.sub(r"<(script|style|svg)\b.*?</\1>", " ", fragmento, flags=re.S | re.I)
    return [t.strip() for t in html_lib.unescape(re.sub(r"<[^>]+>", "\n", sin)).split("\n") if t.strip()]


def fecha_de(linea):
    """'Hoy · 17:00 hs', 'Mañana · 20:00 hs', 'sáb. 17 oct. · 00:00 hs' -> ('AAAA-MM-DD', 'HH:MM' o '')."""
    h = re.search(r"(\d{1,2}):(\d{2})", linea)
    hora = f"{int(h.group(1)):02d}:{h.group(2)}" if h else ""
    if hora == "00:00":  # SalePlan pone 00:00 cuando no hay hora
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
    if (hoy() - d).days > 180:  # diciembre -> enero
        d = d.replace(year=anio + 1)
    return d.isoformat(), hora


def tarjetas(pagina):
    """Las tarjetas de una página del listado."""
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
    """Recorre el listado hasta pasar el fin de la ventana o hasta que no aparezcan tarjetas nuevas."""
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
        if est == 404 and n > 1:  # se terminó el listado
            break
        if est != 200 or not html:
            # Un corte a mitad del listado no es el final: guardar lo leído reemplazaría la captura con una parte.
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
    """slug -> nombre con tildes, a partir de los barrios que ya usa lugares.json."""
    nombres = dict(BARRIOS_EXTRA)
    for l in leer_json(DATOS / "lugares.json", []):
        if l.get("barrio"):
            nombres.setdefault(re.sub(r"[^a-z0-9]+", "-", sin_tildes(l["barrio"])).strip("-"), l["barrio"])
    return nombres


def indice_otras_fuentes(desde, hasta):
    """fecha -> títulos normalizados de los eventos de todas las capturas recientes menos la de SalePlan."""
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
    """Todas las palabras del título más corto están en el otro ("Gruesome en Argentina" en
    "GRUESOME - Unico Show en Argentina"). Pide 2 palabras o más para no unir títulos de una palabra."""
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
    # Una tarjeta con fecha anterior a hoy y sin "Función terminada" es algo en curso (visitas guiadas, muestras,
    # shows diarios): SalePlan le pone el día en que empezó a listarla. Cuenta como vigente hoy.
    caba = [c for c in todas if c["localidad"] == "CABA" and c["fecha"] and c["fecha"] <= hasta and not c["terminada"]]
    for c in caba:
        c["en_curso"] = c["fecha"] < desde
    idx = indice_otras_fuentes(desde, hasta)
    nuevas = [c for c in caba if not cubierto({**c, "fecha": max(c["fecha"], desde)}, idx)]
    barrios = nombres_barrio()
    # Lo que ya se sabía de fichas abiertas antes (lugar, dirección, precio) se conserva por URL.
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
            # La ficha trae el rango real de lo que está en curso (la tarjeta, solo el primer día).
            if c["en_curso"] and (vieja.get("fecha_fin") or "") >= desde:
                e["fecha_inicio"], e["fecha_fin"] = vieja["fecha_inicio"], vieja["fecha_fin"]
        elif not barrio and not c["hora"]:
            fichas.append(c["url"])
        eventos.append(e)

    # Muestras y funciones de larga duración que empezaron antes de hoy: la tarjeta queda fuera de la ventana,
    # pero la captura anterior (de fichas) traía el rango. Se conservan mientras sigan vigentes.
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
