"""Busca el sitio web de los lugares de la planilla que no tienen uno.

Uso:
    python scripts/buscar_sitios.py [ruta_csv]

Para cada lugar sin web busca en DuckDuckGo, descarga los primeros resultados y
acepta uno solo si la página confirma el lugar: menciona su usuario de Instagram,
o su dirección, o la mayoría de las palabras distintivas del nombre.

Genera data/fuente/sitios_encontrados.json. verificar_lugares.py lo usa para
completar los lugares que no tienen web en la planilla.
"""
import csv
import json
import re
import time
import unicodedata
import urllib.error
import urllib.parse
from concurrent.futures import ThreadPoolExecutor

from comun import DATOS, dominio, obtener
from verificar_lugares import FUENTE_DEFAULT, leer_planilla, url_de

SALIDA = DATOS / "fuente" / "sitios_encontrados.json"

# Dominios que no son el sitio del lugar: redes, directorios, agregadores, mapas.
NO_SON_SITIO = {
    "instagram.com", "facebook.com", "yelp.com", "tripadvisor.com", "tripadvisor.com.ar",
    "infobel.com", "unilocal.com", "unilocal.es", "unilocal.co.uk", "near-place.com", "indiehoy.com",
    "meca.ar", "alternativateatral.com", "timeout.com", "eventbrite.com", "eventbrite.com.ar",
    "google.com", "google.com.ar", "maps.google.com", "wikipedia.org", "es.wikipedia.org",
    "mapcarta.com", "tiendeo.com.ar", "paginasamarillas.com.ar", "foursquare.com", "booking.com",
    "airbnb.com", "mercadolibre.com.ar", "linktr.ee", "taplink.bio", "linkedin.com", "youtube.com",
    "tiktok.com", "pinterest.com", "x.com", "twitter.com", "wa.me", "guiaoleo.com.ar", "clarin.com",
    "lanacion.com.ar", "pagina12.com.ar", "infobae.com", "perfil.com", "buenosaires.gob.ar",
    "turismo.buenosaires.gob.ar", "data.buenosaires.gob.ar", "bairessecreta.com", "forbesargentina.com",
    "ticketek.com.ar", "passline.com", "plateanet.com", "ubereats.com", "rappi.com.ar", "pedidosya.com.ar",
    "sites.google.com", "blogspot.com", "wordpress.com", "wixsite.com", "campsite.bio", "g.page",
    "duckduckgo.com", "bing.com", "mapa.buenosaires.gob.ar", "cultura.buenosaires.gob.ar",
}
STOPWORDS = {
    "centro", "cultural", "culturales", "espacio", "casa", "club", "de", "del", "la", "las", "los",
    "el", "en", "y", "por", "arte", "artes", "teatro", "bar", "sala", "ciudad", "buenos", "aires",
    "the", "al", "a", "o",
}
MAX_CANDIDATOS = 5


def sin_acentos(texto):
    return unicodedata.normalize("NFD", texto).encode("ascii", "ignore").decode().lower()


def buscar(consulta):
    """URLs de los primeros resultados de DuckDuckGo (HTML).

    DuckDuckGo limita las consultas seguidas: si responde con error, espera y reintenta.
    """
    url = "https://html.duckduckgo.com/html/?q=" + urllib.parse.quote(consulta)
    for intento in range(4):
        try:
            _, _, html = obtener(url, timeout=20)
            break
        except urllib.error.HTTPError:
            if intento == 3:
                raise
            time.sleep(20 * (intento + 1))
    crudas = re.findall(r'class="result__a"[^>]*href="([^"]+)"', html)
    urls = []
    for cruda in crudas:
        m = re.search(r"uddg=([^&]+)", cruda)
        if m:
            urls.append(urllib.parse.unquote(m.group(1)))
    return urls


def es_sitio_posible(url):
    d = dominio(url)
    if not d or any(d == x or d.endswith("." + x) for x in NO_SON_SITIO):
        return False
    return d.endswith((".ar", ".org", ".com", ".net", ".blog", ".cc", ".co", ".es", ".gob.ar", ".uba.ar", ".edu.ar")) or "." in d


def puntuar(lugar, url):
    """Devuelve (aceptado, evidencia) según cuánto de la página confirma el lugar."""
    try:
        _, final, html = obtener(url, timeout=12)
    except Exception as e:
        return False, f"no se pudo abrir ({type(e).__name__})"
    texto = sin_acentos(re.sub(r"<[^>]+>", " ", html))
    texto = re.sub(r"\s+", " ", texto)

    ig = lugar["instagram"].lstrip("@").lower()
    if ig and len(ig) >= 4 and re.search(r"(?<![a-z0-9_.])" + re.escape(ig) + r"(?![a-z0-9_])", texto):
        return True, f"menciona su Instagram @{ig}"

    numero = re.search(r"\d+", lugar["domicilio"] or "")
    calle = re.sub(r"\d+.*", "", sin_acentos(lugar["domicilio"] or "")).strip(" ,.")
    calle = re.sub(r"\b(av|avenida|pres|tte|gral|dr|cnel|cnel)\b\.?", "", calle).strip(" ,.")
    if numero and calle and len(calle) >= 4 and calle.split()[0] in texto and numero.group(0) in texto:
        return True, f"muestra la dirección ({calle} {numero.group(0)})"

    palabras = [w for w in re.findall(r"[a-z0-9]+", sin_acentos(lugar["nombre"])) if len(w) >= 4 and w not in STOPWORDS]
    if palabras:
        encontradas = sum(1 for w in palabras if re.search(r"\b" + re.escape(w) + r"\b", texto))
        if encontradas == len(palabras) and len(palabras) >= 2:
            return True, f"nombre completo en la página ({', '.join(palabras)})"
    return False, "no confirma el lugar"


def buscar_lugar(lugar):
    partes = [f'"{lugar["nombre"]}"']
    if lugar["domicilio"]:
        partes.append(lugar["domicilio"])
    partes.append(lugar["barrio"] or "")
    partes.append("Buenos Aires")
    consulta = " ".join(p for p in partes if p)
    try:
        candidatos = []
        for url in buscar(consulta):
            if es_sitio_posible(url) and dominio(url) not in [dominio(c) for c in candidatos]:
                candidatos.append(url)
            if len(candidatos) >= MAX_CANDIDATOS:
                break
        time.sleep(3)
    except Exception as e:
        return {**lugar, "url": "", "evidencia": f"búsqueda fallida ({type(e).__name__})", "confianza": "ninguna"}

    for url in candidatos:
        aceptado, evidencia = puntuar(lugar, url)
        if aceptado:
            return {**lugar, "url": url, "evidencia": evidencia,
                    "confianza": "alta" if "Instagram" in evidencia or "dirección" in evidencia else "media"}
    return {**lugar, "url": "", "evidencia": f"sin coincidencia ({len(candidatos)} candidatos revisados)", "confianza": "ninguna"}


def main():
    import sys
    from pathlib import Path
    ruta = Path(sys.argv[1]) if len(sys.argv) > 1 else FUENTE_DEFAULT
    pendientes = []
    vistos = set()
    for r in leer_planilla(ruta):
        if url_de(r["Página web"]):
            continue
        nombre = r["Centro / espacio / sede"].strip()
        clave = (nombre, r["Barrio"].strip(), r["Domicilio de referencia"].strip())
        if not nombre or clave in vistos:
            continue
        vistos.add(clave)
        pendientes.append({
            "nombre": nombre,
            "barrio": re.sub(r"\s*\(.*?\)", "", r["Barrio"]).strip(),
            "domicilio": r["Domicilio de referencia"].strip(),
            "instagram": r["Instagram"].strip(),
        })
    print(f"{len(pendientes)} lugares sin web para buscar")

    with ThreadPoolExecutor(max_workers=1) as ex:
        resultados = list(ex.map(buscar_lugar, pendientes))

    SALIDA.write_text(json.dumps(resultados, ensure_ascii=False, indent=1), encoding="utf-8")
    encontrados = [r for r in resultados if r["url"]]
    print(f"Encontrados: {len(encontrados)} de {len(resultados)} ({sum(r['confianza']=='alta' for r in encontrados)} con confianza alta)")
    print(f"Escrito: {SALIDA.name}")


if __name__ == "__main__":
    main()
