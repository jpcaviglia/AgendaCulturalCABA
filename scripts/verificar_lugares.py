"""Verifica si el sitio web de cada lugar es donde publica sus eventos.

Uso:
    python scripts/verificar_lugares.py [ruta_csv]

Por defecto lee data/fuente/lugares_fuente.csv (export de la planilla de lugares).
Genera:
    data/lugares_verificacion.csv  auditoría completa, una fila por fila de la planilla
    data/lugares.json              lugares únicos que usa el sitio

La verificación es automática y tiene límites: no entra a Instagram (requiere
login) ni lee sitios que bloquean bots. Esos casos quedan marcados como
"No verificable" para revisarlos a mano.
"""
import csv
import json
import re
import sys
import unicodedata
import urllib.error
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from comun import DATOS, dominio, leer_agenda_turismo, obtener

FUENTE_DEFAULT = DATOS / "fuente" / "lugares_fuente.csv"
SITIOS_INSTAGRAM = DATOS / "fuente" / "sitios_instagram.json"
SALIDA_CSV = DATOS / "lugares_verificacion.csv"
SALIDA_JSON = DATOS / "lugares.json"

CONFIRMADO = "Tiene sección de agenda"
PROBABLE = "Probable: menciona eventos"
SIN_EVENTOS = "No se detectan eventos"
INACCESIBLE = "Inaccesible desde la verificación"
NO_VERIFICABLE = "No verificable (bloquea o redirige)"
SIN_WEB = "Sin web"

AGREGADORES = {
    "alternativateatral.com", "timeout.com", "eventbrite.com.ar", "indiehoy.com",
    "turismo.buenosaires.gob.ar", "ticketek.com.ar", "passline.com", "plateanet.com",
    "meca.ar", "data.buenosaires.gob.ar",
}
REDES = {
    "instagram.com", "facebook.com", "linktr.ee", "taplink.bio", "campsite.bio",
    "g.page", "blogspot.com", "sites.google.com",
}

# Enlaces a páginas de eventos dentro del HTML: /agenda, /eventos, /cartelera, etc.
PATRON_LINKS = re.compile(
    r'href="[^"]*/(agenda|eventos?|programaci[oó]n|cartelera|calendario|shows?|funciones|conciertos|events?)/?[^"]*"',
    re.IGNORECASE,
)
PATRON_EVENTO_SCHEMA = re.compile(r'schema\.org/(music)?event|"@type"\s*:\s*"(music)?event"', re.IGNORECASE)
PATRON_PALABRAS = re.compile(r"\b(agenda|eventos?|cartelera|programaci[oó]n)\b", re.IGNORECASE)


def tipo_web(url):
    d = dominio(url)
    if not d:
        return ""
    if d in AGREGADORES:
        return "Agregador"
    if any(d == r or d.endswith("." + r) for r in REDES):
        return "Red social o enlace"
    if d.endswith((".gob.ar", ".gov.ar", ".uba.ar", ".edu.ar")):
        return "Gobierno o universidad"
    return "Sitio propio"


def url_de(web):
    """Convierte lo que escribió la planilla en una URL usable, o '' si no hay sitio."""
    web = web.strip()
    if web.startswith("http"):
        return web
    if "." in web and " " not in web:
        return "https://" + web
    return ""


def revisar_url(url):
    """Descarga la página y decide si lista eventos. Devuelve un dict con estado y evidencia."""
    try:
        status, final, html = obtener(url)
    except urllib.error.HTTPError as e:
        if e.code in (404, 410):
            return {"estado": INACCESIBLE, "evidencia": f"HTTP {e.code}: página no encontrada", "url_final": ""}
        return {"estado": NO_VERIFICABLE, "evidencia": f"HTTP {e.code}", "url_final": ""}
    except Exception as e:  # DNS, SSL, timeout, conexión rechazada
        return {"estado": INACCESIBLE, "evidencia": f"Error de conexión ({type(e).__name__})", "url_final": ""}

    if status >= 400:
        return {"estado": NO_VERIFICABLE, "evidencia": f"HTTP {status}", "url_final": final}

    if PATRON_EVENTO_SCHEMA.search(html):
        return {"estado": CONFIRMADO, "evidencia": "Marcado schema.org de eventos", "url_final": final}
    enlaces = len(PATRON_LINKS.findall(html))
    if enlaces:
        return {"estado": CONFIRMADO, "evidencia": f"{enlaces} enlaces a agenda/eventos", "url_final": final}
    palabras = len(PATRON_PALABRAS.findall(html))
    if palabras:
        return {"estado": PROBABLE, "evidencia": f"Menciona agenda/eventos ({palabras} veces), sin enlace claro", "url_final": final}
    return {"estado": SIN_EVENTOS, "evidencia": "No aparecen palabras ni enlaces de agenda", "url_final": final}


def leer_planilla(ruta):
    with open(ruta, encoding="utf-8", newline="") as f:
        filas = list(csv.reader(f))
    inicio = next(i for i, f in enumerate(filas) if f and f[0].strip() == "Centro / espacio / sede")
    cabecera = filas[inicio]
    registros = []
    for fila in filas[inicio + 1:]:
        if not any(c.strip() for c in fila):
            continue
        fila = fila + [""] * (len(cabecera) - len(fila))
        registros.append(dict(zip(cabecera, fila)))
    return registros


def corroborar_con_agenda():
    """Dominios de sitios propios que la agenda oficial enlaza como lugar de sus actividades."""
    try:
        actividades = leer_agenda_turismo()
    except Exception as e:
        print(f"Aviso: no se pudo leer la agenda de Turismo BA ({e}); se omite la corroboración.")
        return set()
    return {a["dominio"] for a in actividades if a["dominio"] and a["dominio"] not in AGREGADORES | REDES}


def clave_barrio(barrio):
    """Sin acentos, minúsculas y sin aclaraciones entre paréntesis: 'Villa Ortúzar (según MECA)' -> 'villa ortuzar'."""
    sin_aclaracion = re.sub(r"\(.*?\)", "", barrio).strip()
    return unicodedata.normalize("NFD", sin_aclaracion).encode("ascii", "ignore").decode().lower()


def unificar_barrios(lugares):
    """Une variantes de escritura de un mismo barrio y usa la forma más frecuente."""
    formas = {}
    for l in lugares:
        formas.setdefault(clave_barrio(l["barrio"]), Counter())[re.sub(r"\s*\(.*?\)", "", l["barrio"]).strip()] += 1
    for l in lugares:
        if l["barrio"]:
            l["barrio"] = formas[clave_barrio(l["barrio"])].most_common(1)[0][0]


def leer_sitios_instagram():
    """Webs de la bio de Instagram para lugares que la planilla no tiene, por nombre."""
    if not SITIOS_INSTAGRAM.exists():
        return {}
    return {s["nombre"]: s for s in json.loads(SITIOS_INSTAGRAM.read_text(encoding="utf-8"))}


def main():
    ruta =Path(sys.argv[1]) if len(sys.argv) > 1 else FUENTE_DEFAULT
    registros = leer_planilla(ruta)
    print(f"{len(registros)} filas en la planilla")

    extra = leer_sitios_instagram()
    for r in registros:
        nombre = r["Centro / espacio / sede"].strip()
        if not url_de(r["Página web"]) and nombre in extra:
            r["Página web"] = extra[nombre]["web"]

    urls = sorted({url_de(r["Página web"]) for r in registros} - {""})
    print(f"{len(urls)} sitios distintos para revisar")
    with ThreadPoolExecutor(max_workers=16) as ex:
        resultados = dict(zip(urls, ex.map(revisar_url, urls)))

    dominios_agenda = corroborar_con_agenda()

    filas_salida = []
    lugares = {}
    for r in registros:
        nombre = r["Centro / espacio / sede"].strip()
        web_planilla = r["Página web"].strip()
        url = url_de(web_planilla)
        info = resultados.get(url, {"estado": SIN_WEB, "evidencia": "", "url_final": ""})
        tipo = tipo_web(url)
        d = dominio(url)
        corroborado = bool(d and d in dominios_agenda and tipo in ("Sitio propio", "Gobierno o universidad"))
        estado = info["estado"]
        evidencia = info["evidencia"]
        if corroborado and estado != CONFIRMADO:
            estado = CONFIRMADO
            evidencia = "Enlazado desde la agenda oficial de Turismo BA" + (f" (la web no respondió: {info['evidencia']})" if info["estado"] == INACCESIBLE else "")
        elif corroborado:
            evidencia += "; enlazado desde la agenda oficial de Turismo BA"

        ig = r["Instagram"].strip()
        if estado == CONFIRMADO:
            canal = "Sitio web"
        elif ig.startswith("@"):
            canal = "Instagram (sin listado confirmado en la web)"
        else:
            canal = "Revisar a mano"

        fila = {
            "Centro / espacio / sede": nombre,
            "Barrio": r["Barrio"].strip(),
            "Domicilio": r["Domicilio de referencia"].strip(),
            "Página web (planilla o Instagram)": web_planilla,
            "Tipo de web": tipo,
            "Estado (automático)": estado,
            "Evidencia": evidencia,
            "Corroborado por agenda oficial": "Sí" if corroborado else "No",
            "URL final": info["url_final"],
            "Instagram (planilla)": ig,
            "Revisión Instagram (planilla)": r["Revisión de Instagram"].strip(),
            "Canal de eventos sugerido": canal,
            "Ficha MECA": r["Ficha en MECA"].strip(),
        }
        filas_salida.append(fila)

        clave = (nombre, fila["Barrio"], fila["Domicilio"])
        if nombre and clave not in lugares:
            lugares[clave] = {
                "nombre": nombre,
                "barrio": fila["Barrio"],
                "domicilio": fila["Domicilio"],
                "web": url,
                "dominio": d,
                "tipo_web": tipo,
                "instagram": ig if ig.startswith("@") else "",
                "estado": estado,
                "evidencia": evidencia,
                "canal": canal,
            }

    with open(SALIDA_CSV, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(filas_salida[0].keys()))
        w.writeheader()
        w.writerows(filas_salida)

    unificar_barrios(lugares.values())
    SALIDA_JSON.write_text(
        json.dumps(sorted(lugares.values(), key=lambda l: (l["barrio"], l["nombre"])), ensure_ascii=False, indent=1),
        encoding="utf-8",
    )

    print("Resumen por estado:")
    for estado, n in Counter(f["Estado (automático)"] for f in filas_salida).most_common():
        print(f"  {n:4d}  {estado}")
    print(f"Escrito: {SALIDA_CSV.name} ({len(filas_salida)} filas) y {SALIDA_JSON.name} ({len(lugares)} lugares)")


if __name__ == "__main__":
    main()
