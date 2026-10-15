"""Utilidades compartidas por los scripts de la agenda (solo biblioteca estándar)."""
import json
import re
import ssl
import sys
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlparse

sys.stdout.reconfigure(encoding="utf-8")

RAIZ = Path(__file__).resolve().parent.parent
DATOS = RAIZ / "data"

ZONA_BA = timezone(timedelta(hours=-3))  # Argentina no usa horario de verano
UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)

AGENDA_TURISMO_URL = "https://turismo.buenosaires.gob.ar/es/article/que-hacer-esta-semana"
AGENDA_TURISMO_NOMBRE = "Turismo Buenos Aires: Qué hacer esta semana"


def hoy():
    return datetime.now(ZONA_BA).date()


def obtener(url, timeout=15):
    """Devuelve (status, url_final, texto). Lanza excepción si falla la conexión."""
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Language": "es-AR,es;q=0.9"})
    with urllib.request.urlopen(req, timeout=timeout, context=ssl.create_default_context()) as r:
        return r.status, r.geturl(), r.read(3_000_000).decode("utf-8", errors="replace")


def dominio(url):
    """Dominio sin 'www.', o '' si la URL no es válida."""
    if not url:
        return ""
    if not url.startswith("http"):
        url = "https://" + url
    return urlparse(url).netloc.lower().removeprefix("www.")


def leer_agenda_turismo():
    """Actividades de la agenda semanal de Turismo BA.

    La página incrusta el listado como un arreglo JSON dentro de un script.
    Devuelve una lista de dicts normalizados (ver normalizar_actividad).
    """
    _, _, html = obtener(AGENDA_TURISMO_URL)
    inicio = html.find('[{"orden"')
    if inicio < 0:
        raise RuntimeError("No se encontró el listado de actividades en la agenda de Turismo BA")
    actividades, _ = json.JSONDecoder().raw_decode(html[inicio:])
    return [normalizar_actividad(a) for a in actividades]


def normalizar_actividad(a):
    precio = a.get("precio_filtro", "").strip()
    return {
        "titulo": a["nombre_actividad"].strip(),
        "categoria": a.get("categoria_actividad_filtro", "").strip(),
        "lugar": a.get("proveedor", "").strip(),
        "barrio": a.get("barrio", "").strip(),
        "direccion": a.get("calle_altura", "").strip(),
        "fecha_inicio": a.get("fecha_inicio", "").strip(),
        "horarios": a.get("dias_horarios", "").strip(),
        "precio": "Gratis" if precio == "0" else "Consultar",
        "descripcion": a.get("descripcion", "").strip(),
        "url": a.get("url_boton", "").strip(),
        "dominio": dominio(a.get("url_boton", "")),
    }
