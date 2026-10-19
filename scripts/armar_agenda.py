"""Builds data/eventos.json from the browser crawl captures (data/crawl/capturas). It does not crawl anything.

Usage:
    python scripts/armar_agenda.py            # builds eventos.json (and places new addresses on the map)
    python scripts/armar_agenda.py --sin-geo  # without querying new addresses on OpenStreetMap
    python scripts/armar_agenda.py --simular  # shows the result without writing

It takes the latest capture of each site and channel, keeps what falls inside the 14-day window, classifies,
removes duplicates between sources and updates the status of each venue in data/lugares.json according to
the crawl. Captures older than MAX_EDAD_DIAS are ignored: if a site could not be crawled again, its old
events are kept for a few days and then drop out by themselves.
"""
import hashlib
import sys
from datetime import date

from clasificar import clasificar
from comun import CAPTURAS, DATOS, SITIOS, dominio, escribir_json, hoy, leer_json, sin_tildes, ventana
from deduplicar import deduplicar

SALIDA = DATOS / "eventos.json"
MAX_EDAD_DIAS = 10
# Instagram is rotated between runs because of its rate limit, so its captures last longer.
MAX_EDAD_DIAS_INSTAGRAM = 21
CAMPOS_PUBLICOS = ("id", "titulo", "categoria", "lugar", "barrio", "direccion", "fecha_inicio", "fecha_fin", "hora",
                   "horarios", "precio", "descripcion", "url", "dominio", "estado", "lugar_verificado", "fuentes", "lat", "lng", "embebible",
                   "imagen")
TIPO_DEDUP = {"lugar": "sitio", "galeria": "sitio", "agregador": "agregador", "descubrimiento": "agregador"}
# Web crawl status -> status shown in the Lugares tab (assets/app.js).
ESTADO_LUGAR = {
    "con_eventos": "Tiene sección de agenda",
    "sin_eventos": "Tiene sección de agenda",
    "sin_agenda": "No se detectan eventos",
    "no_cultural": "No se detectan eventos",
    "no_carga": "Inaccesible desde la verificación",
    "dominio_caido": "Inaccesible desde la verificación",
    "bloqueado": "No verificable (bloquea o redirige)",
}


def en_ventana(e, desde, hasta):
    ini, fin = e["fecha_inicio"], e.get("fecha_fin") or ""
    if ini > hasta:
        return False
    if ini >= desde:
        return True
    # Already started: continues if it has a current end date, or if the source publishes it as current with no end date.
    return fin >= desde if fin else bool(e.get("vigente_sin_fin"))


def leer_capturas():
    """Returns (raw_events, captures_used, old_captures)."""
    crudos, usadas, viejas = [], [], []
    for ruta in sorted(CAPTURAS.glob("*.json")):
        cap = leer_json(ruta)
        if not cap:
            print(f"  captura ilegible: {ruta.name}")
            continue
        edad = (hoy() - date.fromisoformat(cap["fecha"])).days
        if edad > (MAX_EDAD_DIAS_INSTAGRAM if cap.get("canal") == "instagram" else MAX_EDAD_DIAS):
            viejas.append(ruta.name)
            continue
        usadas.append(cap)
        for e in cap.get("eventos", []):
            e = dict(e)
            e["fuentes"] = [cap["fuente"]]
            # A venue's Instagram is its own source; an aggregator's Instagram is still an aggregator.
            tipo = TIPO_DEDUP.get(cap.get("tipo"), "sitio")
            e["_tipo"] = "instagram" if cap["canal"] == "instagram" and tipo == "sitio" else tipo
            e["_tipo_sitio"] = cap.get("tipo")
            e["dominio"] = dominio(e.get("url", ""))
            crudos.append(e)
    return crudos, usadas, viejas


def id_estable(e):
    """Identifier that stays the same between runs (the website saves favorites with it). It comes from the title
    and the venue; for a single-day event also from the date (two concerts of the same series are different
    events), but not for a play or exhibition with several dates, which remain the same one even if the
    first date changes."""
    from deduplicar import norm_lugar, norm_titulo
    # Up to 2 days counts as a single day: a party that ends at dawn comes as "del 20 al 21".
    fin = e.get("fecha_fin") or e["fecha_inicio"]
    un_dia = (date.fromisoformat(fin) - date.fromisoformat(e["fecha_inicio"])).days <= 1
    base = f"{norm_titulo(e['titulo'])}|{norm_lugar(e.get('lugar', ''))}|{e['fecha_inicio'] if un_dia else ''}"
    return hashlib.sha1(base.encode("utf-8")).hexdigest()[:12]


def unir_temporadas(eventos, fusionar):
    """Merges the same play or exhibition (same title and venue, overlapping dates) that two sources publish with
    a different start day ("Santos Vega" from 3/9 and from 15/10): per-day deduplication does not join them.
    The first day and the last one are kept. Returns (events, merged)."""
    grupos = {}
    for e in eventos:
        if e.get("fecha_fin") and (date.fromisoformat(e["fecha_fin"]) - date.fromisoformat(e["fecha_inicio"])).days > 1:
            grupos.setdefault(id_estable(e), []).append(e)
    sobran = set()
    for g in grupos.values():
        if len(g) < 2:
            continue
        g.sort(key=lambda e: e["fecha_inicio"])
        actual = [g[0]]
        for e in g[1:]:
            if e["fecha_inicio"] <= max(x["fecha_fin"] for x in actual):
                actual.append(e)
                continue
            _unir(actual, fusionar, sobran)
            actual = [e]
        _unir(actual, fusionar, sobran)
    unidos = [e for e in eventos if id(e) not in sobran]
    return unidos, len(eventos) - len(unidos)


def _unir(grupo, fusionar, sobran):
    if len(grupo) < 2:
        return
    u = fusionar(grupo)
    u["fecha_inicio"] = min(e["fecha_inicio"] for e in grupo)
    u["fecha_fin"] = max(e["fecha_fin"] for e in grupo)
    grupo[0].clear()
    grupo[0].update(u)
    sobran.update(id(e) for e in grupo[1:])


def completar_lugar(e, lugares_por_nombre):
    """Neighborhood and address from lugares.json when the event does not bring them."""
    l = lugares_por_nombre.get(sin_tildes(e.get("lugar", "")))
    if l:
        e["barrio"] = e.get("barrio") or l.get("barrio", "")
        e["direccion"] = e.get("direccion") or l.get("domicilio", "")


def actualizar_lugares(lugares, sitios, usadas):
    """The status of each venue in the Lugares tab comes from the last crawl of its website."""
    por_id = {s["id"]: s for s in sitios}
    cambios = 0
    estado_por_lugar = {}
    for cap in usadas:
        if cap["canal"] != "web" or cap["estado"] not in ESTADO_LUGAR or cap["id"] not in por_id:
            continue
        for nombre in por_id[cap["id"]].get("lugares", []):
            estado_por_lugar[sin_tildes(nombre)] = ESTADO_LUGAR[cap["estado"]]
    for l in lugares:
        nuevo = estado_por_lugar.get(sin_tildes(l["nombre"]))
        if nuevo and l.get("web") and l.get("estado") != nuevo:
            l["estado"] = nuevo
            l["evidencia"] = f"Rastreo con navegador del {hoy().isoformat()}"
            cambios += 1
    return cambios


def main():
    simular = "--simular" in sys.argv
    desde, hasta = ventana()
    crudos, usadas, viejas = leer_capturas()
    print(f"Ventana {desde} a {hasta}. {len(usadas)} capturas ({len(viejas)} ignoradas por viejas), {len(crudos)} eventos crudos.")
    if not usadas:
        sys.exit("No hay capturas recientes: no se toca eventos.json.")

    lugares = leer_json(DATOS / "lugares.json", [])
    lugares_por_nombre = {sin_tildes(l["nombre"]): l for l in lugares}
    crudos = [e for e in crudos if en_ventana(e, desde, hasta)]
    for e in crudos:
        completar_lugar(e, lugares_por_nombre)
        categoria = e.get("categoria", "") or ("Artes visuales" if e["_tipo_sitio"] == "galeria" else "")
        e["categoria"] = clasificar(categoria, e["titulo"], e.get("descripcion", ""), e.get("url", ""))
        e["precio"] = e.get("precio") or "Consultar"
    eventos, duplicados = deduplicar(crudos)
    # Pairs the agent reviewed and marked as the same event (scripts/duplicados.py).
    from deduplicar import fusionar
    from duplicados import aplicar_iguales
    eventos, revisados = aplicar_iguales(eventos, fusionar)
    duplicados += revisados
    eventos, mismas_temporadas = unir_temporadas(eventos, fusionar)
    duplicados += mismas_temporadas
    from direcciones import completar
    sin_dir = sum(1 for e in eventos if e.get("lugar") and not e.get("direccion"))
    completados, fichas = completar(eventos, consultar=not simular and "--sin-geo" not in sys.argv)
    print(f"Direcciones: {completados} de {sin_dir} eventos sin dirección completados ({fichas} fichas consultadas)")

    por_dominio = {l["dominio"]: l["nombre"] for l in lugares
                   if l.get("dominio") and l.get("tipo_web") not in ("Agregador", "Red social o enlace")}
    for e in eventos:
        e["estado"] = "Próximo" if e["fecha_inicio"] >= desde else "En curso"
        e["lugar_verificado"] = por_dominio.get(e.get("dominio", ""), "")
    eventos.sort(key=lambda e: (e["fecha_inicio"], e["titulo"]))

    if not simular and "--sin-geo" not in sys.argv:
        from geocodificar import geocodificar_eventos
        nuevas = geocodificar_eventos(eventos, lugares)
        print(f"Mapa: {sum(1 for e in eventos if e.get('lat') != '')} de {len(eventos)} eventos ubicados "
              f"({nuevas} direcciones nuevas consultadas)")
    else:
        from geocodificar import ubicar_con_cache
        ubicar_con_cache(eventos, lugares)
    if not simular and "--sin-geo" not in sys.argv:
        from embebibles import marcar
        probados = marcar(eventos)
        print(f"Iframe: {sum(1 for e in eventos if e['embebible'])} de {len(eventos)} eventos se pueden abrir en la página "
              f"({probados} dominios probados)")
    else:
        from embebibles import CACHE
        cache = leer_json(CACHE, {})
        for e in eventos:
            e["embebible"] = bool(cache.get(e.get("dominio", ""), {}).get("ok"))
    for e in eventos:
        e["id"] = id_estable(e)
    eventos = [{k: e.get(k, "") for k in CAMPOS_PUBLICOS} for e in eventos]

    por_cat = {}
    for e in eventos:
        por_cat[e["categoria"]] = por_cat.get(e["categoria"], 0) + 1
    print(f"{len(crudos)} en ventana -> {duplicados} duplicados quitados -> {len(eventos)} eventos")
    print("Por categoría:", ", ".join(f"{k} {v}" for k, v in sorted(por_cat.items(), key=lambda x: -x[1])))
    if simular:
        return

    sitios = (leer_json(SITIOS) or {}).get("sitios", [])
    cambios = actualizar_lugares(lugares, sitios, usadas)
    if cambios:
        escribir_json(DATOS / "lugares.json", lugares)
        print(f"Lugares: {cambios} estados actualizados según el rastreo")
    escribir_json(SALIDA, {
        "generado": hoy().isoformat(), "ventana": {"desde": desde, "hasta": hasta},
        "rastreo": {"capturas": len(usadas), "con_eventos": sum(1 for c in usadas if c["eventos"])},
        "fuentes": sorted({f for e in eventos for f in e["fuentes"]}),
        "eventos": eventos})
    print(f"Escrito {SALIDA.relative_to(DATOS.parent)}")


if __name__ == "__main__":
    main()
