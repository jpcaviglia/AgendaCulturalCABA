"""Arma data/eventos.json con las capturas del rastreo con navegador (data/crawl/capturas). No rastrea nada.

Uso:
    python scripts/armar_agenda.py            # arma eventos.json (y ubica en el mapa las direcciones nuevas)
    python scripts/armar_agenda.py --sin-geo  # sin consultar direcciones nuevas a OpenStreetMap
    python scripts/armar_agenda.py --simular  # muestra el resultado sin escribir

Toma la última captura de cada sitio y canal, se queda con lo que cae en la ventana de 14 días, clasifica,
quita duplicados entre fuentes y actualiza el estado de cada lugar en data/lugares.json según el rastreo.
Las capturas de más de MAX_EDAD_DIAS se ignoran: si un sitio no se pudo volver a rastrear, sus eventos
viejos se mantienen unos días y después se caen solos.
"""
import sys
from datetime import date

from clasificar import clasificar
from comun import CAPTURAS, DATOS, SITIOS, dominio, escribir_json, hoy, leer_json, sin_tildes, ventana
from deduplicar import deduplicar

SALIDA = DATOS / "eventos.json"
MAX_EDAD_DIAS = 10
# Instagram se rota entre corridas por su límite de ritmo, así que sus capturas duran más.
MAX_EDAD_DIAS_INSTAGRAM = 21
CAMPOS_PUBLICOS = ("titulo", "categoria", "lugar", "barrio", "direccion", "fecha_inicio", "fecha_fin", "hora",
                   "horarios", "precio", "descripcion", "url", "dominio", "estado", "lugar_verificado", "fuentes", "lat", "lng", "embebible")
TIPO_DEDUP = {"lugar": "sitio", "galeria": "sitio", "agregador": "agregador", "descubrimiento": "agregador"}
# Estado del rastreo web -> estado que muestra la pestaña Lugares (assets/app.js).
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
    # Ya empezó: sigue si tiene fin vigente, o si la fuente lo publica como vigente sin fecha de fin.
    return fin >= desde if fin else bool(e.get("vigente_sin_fin"))


def leer_capturas():
    """Devuelve (eventos_crudos, capturas_usadas, capturas_viejas)."""
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
            # El Instagram de un lugar es fuente propia; el de un agregador sigue siendo agregador.
            tipo = TIPO_DEDUP.get(cap.get("tipo"), "sitio")
            e["_tipo"] = "instagram" if cap["canal"] == "instagram" and tipo == "sitio" else tipo
            e["_tipo_sitio"] = cap.get("tipo")
            e["dominio"] = dominio(e.get("url", ""))
            crudos.append(e)
    return crudos, usadas, viejas


def completar_lugar(e, lugares_por_nombre):
    """Barrio y dirección desde lugares.json cuando el evento no los trae."""
    l = lugares_por_nombre.get(sin_tildes(e.get("lugar", "")))
    if l:
        e["barrio"] = e.get("barrio") or l.get("barrio", "")
        e["direccion"] = e.get("direccion") or l.get("domicilio", "")


def actualizar_lugares(lugares, sitios, usadas):
    """El estado de cada lugar en la pestaña Lugares sale del último rastreo de su web."""
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
    # Pares que el agente revisó y marcó como el mismo evento (scripts/duplicados.py).
    from deduplicar import fusionar
    from duplicados import aplicar_iguales
    eventos, revisados = aplicar_iguales(eventos, fusionar)
    duplicados += revisados
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
