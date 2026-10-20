"""Reads the Centro Cultural Borges agenda from the site's public JSON API (network, no browser) and writes the
result file for `crawl.py guardar`, with each event linked to its own page (/evento/<id>).

Usage:
    python scripts/borges.py [--dias 14]      # writes data/crawl/tmp/centro-cultural-borges.json
    python scripts/crawl.py guardar data/crawl/tmp/centro-cultural-borges.json

The calendar of centroculturalborges.gob.ar is an app whose cards have no links; it loads
/api/public/agenda?mes=M&anio=AAAA (every function with id, date, time, picture, area and room) and
/api/public/evento-detalle?id=N (`ficha` = price, description). The API answers over plain HTTP if the request
has `Accept: application/json` and a `Referer`.
"""
import argparse
import json
import re
import urllib.request
from datetime import date, timedelta
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
BASE = "https://centroculturalborges.gob.ar"
MESES = {"ENE": 1, "FEB": 2, "MAR": 3, "ABR": 4, "MAY": 5, "JUN": 6, "JUL": 7, "AGO": 8, "SEP": 9, "SET": 9,
         "OCT": 10, "NOV": 11, "DIC": 12}
CATEGORIAS = {"Laboratorio": "Talleres", "Centro abierto": "Evento"}


def api(ruta):
    pedido = urllib.request.Request(f"{BASE}/api/public/{ruta}", headers={
        "User-Agent": "Mozilla/5.0", "Accept": "application/json", "Referer": f"{BASE}/agenda"})
    return json.loads(urllib.request.urlopen(pedido, timeout=30).read().decode("utf-8"))


def titulo(t):
    """The site writes some titles in capitals: sentence case for those."""
    t = re.sub(r"\s+", " ", t).strip()
    letras = [c for c in t if c.isalpha()]
    if letras and sum(c.isupper() for c in letras) / len(letras) > 0.8:
        t = t.lower()
        t = t[:1].upper() + t[1:]
    return t


def funciones(desde, hasta):
    """(date, API item) of every function between the two dates, from the months that cover the window."""
    meses, d = [], desde.replace(day=1)
    while d <= hasta:
        meses.append((d.month, d.year))
        d = (d.replace(day=28) + timedelta(days=4)).replace(day=1)
    res = []
    for mes, anio in meses:
        for x in api(f"agenda?mes={mes}&anio={anio}"):
            m = re.search(r"(\d+)\s+([A-Z]{3})", x.get("fechaCalendario") or x.get("fecha") or "")
            if not m or not x.get("activo") or not x.get("mostrarEnAgenda"):
                continue
            f = date(anio, MESES[m.group(2)], int(m.group(1)))
            if desde <= f <= hasta:
                res.append((f, x))
    return sorted(res, key=lambda t: (t[0], t[1].get("hora") or ""))


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--dias", type=int, default=14, help="days of the window from today (default 14)")
    a = ap.parse_args()
    desde = date.today()
    hasta = desde + timedelta(days=a.dias)
    funcs = funciones(desde, hasta)
    detalles, eventos, vistos = {}, [], set()
    for f, x in funcs:
        if (x["id"], f) in vistos:
            continue
        vistos.add((x["id"], f))
        if x["id"] not in detalles:
            detalles[x["id"]] = api(f"evento-detalle?id={x['id']}")
        ficha = (detalles[x["id"]].get("ficha") or "").strip()
        precio = "Gratis" if re.search(r"gratuit|libre", ficha, re.I) else ficha[:60]
        sala = x.get("espacioNombre")
        eventos.append({
            "titulo": titulo(x["titulo"]), "fecha_inicio": f.isoformat(), "fecha_fin": f.isoformat(),
            "hora": x.get("hora") or "", "horarios": "",
            "lugar": "CENTRO CULTURAL BORGES" + (f" · {sala}" if sala else ""), "barrio": "San Nicolás",
            "direccion": "Viamonte 525", "categoria": CATEGORIAS.get(x.get("areaNombre"), x.get("areaNombre") or ""),
            "precio": precio, "url": f"{BASE}/evento/{x['id']}",
            "descripcion": (x.get("descripcion") or detalles[x["id"]].get("descripcion") or "").strip()[:400],
            "vigente_sin_fin": False, "post": "",
            "imagen": BASE + x["imagenUrl"] if x.get("imagenUrl") else ""})
    resultado = {
        "id": "centro-cultural-borges", "canal": "web", "estado": "con_eventos" if eventos else "sin_eventos",
        "urls_visitadas": [f"{BASE}/agenda"] + sorted({e["url"] for e in eventos}), "intentos": 1,
        "scroll_completo": True, "enlaces_candidatos": [{"texto": "Agenda", "url": "/agenda", "visitado": True}],
        "evidencia": "" if eventos else f"la API de la agenda no trae funciones entre {desde} y {hasta}",
        "eventos": eventos, "entradas": [f"{BASE}/agenda"],
        "comportamiento": {"extraccion": "scripts/borges.py lee la API pública JSON (ver el docstring)"},
        "nota": f"{date.today()}: agenda leída con scripts/borges.py (API); cada función enlaza a /evento/<id>.",
        "enlaces_nuevos": [], "sitios_nuevos": []}
    destino = RAIZ / "data" / "crawl" / "tmp" / "centro-cultural-borges.json"
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(json.dumps(resultado, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{len(eventos)} eventos ({desde} a {hasta}) -> {destino.relative_to(RAIZ)}")


if __name__ == "__main__":
    main()
