"""Detección y fusión de eventos duplicados entre fuentes (solo biblioteca estándar)."""
import re
from datetime import date, timedelta
from difflib import SequenceMatcher

from clasificar import sin_tildes

# Menor = más confiable. Al unir duplicados, los datos de base (título, lugar, hora, enlace, descripción) salen de la
# fuente más confiable: la web del propio lugar, después su Instagram y recién después los agregadores (que copian,
# resumen o cambian los títulos). Los agregadores solo completan los campos que la fuente propia dejó vacíos.
PRIORIDAD = {"sitio": 0, "instagram": 1, "agregador": 2}
VACIOS_FUSIONABLES = ("categoria", "lugar", "barrio", "direccion", "horarios", "descripcion", "url", "fecha_fin", "hora")
STOP = {"el", "la", "los", "las", "de", "del", "y", "en", "a", "un", "una", "con", "al"}


def norm_titulo(t):
    t = re.sub(r"[^a-z0-9 ]+", " ", sin_tildes(t))
    return " ".join(p for p in t.split() if p not in STOP)


def norm_lugar(t):
    t = (t or "").split(" · ")[0]  # la sala no cuenta: "Malba · Nivel 2" es Malba
    t = re.sub(r"[^a-z0-9 ]+", " ", sin_tildes(t))
    t = re.sub(r"\b(centro cultural|espacio cultural|teatro|sala|cc)\b", " ", t)
    return " ".join(t.split())


def _parecidos(a, b, umbral):
    if not a or not b:
        return False
    if a == b:
        return True
    if min(len(a), len(b)) >= 8 and (a in b or b in a):
        return True
    s = SequenceMatcher(None, a, b)
    # real_quick_ratio y quick_ratio son cotas superiores baratas de ratio(): descartan rápido la mayoría
    # de los pares sin cambiar el resultado.
    return s.real_quick_ratio() >= umbral and s.quick_ratio() >= umbral and s.ratio() >= umbral


def son_duplicados(x, y):
    """Mismo día y mismo título; el lugar debe coincidir salvo que falte en alguno."""
    if x["fecha_inicio"] != y["fecha_inicio"]:
        # Una función de madrugada la fecha cada fuente un día distinto. Solo se tolera 1 día entre fuentes
        # distintas; en la misma fuente, días consecutivos son funciones distintas.
        if abs((date.fromisoformat(x["fecha_inicio"]) - date.fromisoformat(y["fecha_inicio"])).days) != 1:
            return False
        if set(x.get("fuentes", [])) & set(y.get("fuentes", [])):
            return False
    tx, ty = norm_titulo(x["titulo"]), norm_titulo(y["titulo"])
    # Misma ficha y títulos medianamente parecidos. Solo la URL no alcanza: varias muestras
    # o funciones pueden compartir la portada del organizador.
    if x.get("url") and x.get("url") == y.get("url") and "instagram.com" not in x["url"] and _parecidos(tx, ty, 0.6):
        return True
    if not _parecidos(tx, ty, 0.85):
        return False
    lx, ly = norm_lugar(x.get("lugar", "")), norm_lugar(y.get("lugar", ""))
    if not lx or not ly:
        return True
    return _parecidos(lx, ly, 0.7) or (x.get("dominio") and x.get("dominio") == y.get("dominio"))


def fusionar(grupo):
    """Une un grupo de duplicados: base = la fuente más confiable; completa campos vacíos."""
    grupo = sorted(grupo, key=lambda e: (PRIORIDAD.get(e.get("_tipo"), 9), -len(e.get("descripcion", ""))))
    base = dict(grupo[0])
    fuentes = []
    for e in grupo:
        for f in e.get("fuentes", []):
            if f not in fuentes:
                fuentes.append(f)
        for campo in VACIOS_FUSIONABLES:
            if not base.get(campo) and e.get(campo):
                base[campo] = e[campo]
        # "Evento" es la categoría de descarte: otra fuente que la clasificó mejor manda.
        if base.get("categoria") == "Evento" and e.get("categoria") not in ("", "Evento", None):
            base["categoria"] = e["categoria"]
        # Una URL propia del organizador es mejor que un post de Instagram.
        if "instagram.com" in base.get("url", "") and e.get("url") and "instagram.com" not in e["url"]:
            base["url"], base["dominio"] = e["url"], e.get("dominio", "")
    base["fuentes"] = fuentes
    return base


def deduplicar(eventos):
    """Devuelve (eventos_unicos, cantidad_de_duplicados_eliminados)."""
    grupos = []
    por_fecha = {}
    for e in eventos:
        d = date.fromisoformat(e["fecha_inicio"])
        vecinos = [g for k in (d, d - timedelta(days=1), d + timedelta(days=1)) for g in por_fecha.get(k.isoformat(), [])]
        for g in vecinos:
            if any(son_duplicados(e, m) for m in g):
                g.append(e)
                break
        else:
            g = [e]
            grupos.append(g)
            por_fecha.setdefault(e["fecha_inicio"], []).append(g)
    unicos = [fusionar(g) for g in grupos]
    return unicos, len(eventos) - len(unicos)
