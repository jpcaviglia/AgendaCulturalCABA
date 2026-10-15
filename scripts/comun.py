"""Utilidades compartidas por los scripts de la agenda (solo biblioteca estándar, sin red)."""
import json
import re
import sys
import unicodedata
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlparse

sys.stdout.reconfigure(encoding="utf-8")

RAIZ = Path(__file__).resolve().parent.parent
DATOS = RAIZ / "data"
CRAWL = DATOS / "crawl"
SITIOS = CRAWL / "sitios.json"
CAPTURAS = CRAWL / "capturas"
CORRIDA = CRAWL / "corrida.json"
INFORMES = CRAWL / "informes"

ZONA_BA = timezone(timedelta(hours=-3))  # Argentina no usa horario de verano
VENTANA_DIAS = 14


def hoy():
    return datetime.now(ZONA_BA).date()


def ventana():
    """(desde, hasta) en AAAA-MM-DD: hoy y hoy + VENTANA_DIAS."""
    return hoy().isoformat(), (hoy() + timedelta(days=VENTANA_DIAS)).isoformat()


def dominio(url):
    """Dominio sin 'www.', o '' si la URL no es válida."""
    if not url:
        return ""
    if not url.startswith("http"):
        url = "https://" + url
    return urlparse(url).netloc.lower().removeprefix("www.")


def sin_tildes(texto):
    t = unicodedata.normalize("NFD", texto or "")
    return "".join(c for c in t if unicodedata.category(c) != "Mn").lower()


def slug(texto):
    return re.sub(r"[^a-z0-9]+", "-", sin_tildes(texto)).strip("-")[:60] or "sitio"


def leer_json(ruta, defecto=None):
    try:
        return json.loads(Path(ruta).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return defecto


def escribir_json(ruta, datos):
    ruta = Path(ruta)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    tmp = ruta.with_suffix(ruta.suffix + ".tmp")
    tmp.write_text(json.dumps(datos, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    tmp.replace(ruta)
