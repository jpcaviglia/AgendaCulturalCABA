"""Detection and merging of duplicate events between sources (standard library only)."""
import re
from datetime import date, timedelta
from difflib import SequenceMatcher

from clasificar import sin_tildes

# Lower = more reliable. When merging duplicates, the base data (title, venue, time, link, description) comes from the
# most reliable source: the venue's own website, then its Instagram and only then the aggregators (which copy,
# summarize or change titles). Aggregators only fill in the fields the own source left empty.
PRIORIDAD = {"sitio": 0, "instagram": 1, "agregador": 2}
VACIOS_FUSIONABLES = ("categoria", "lugar", "barrio", "direccion", "horarios", "descripcion", "url", "fecha_fin", "hora", "imagen")
STOP = {"el", "la", "los", "las", "de", "del", "y", "en", "a", "un", "una", "con", "al"}


def norm_titulo(t):
    t = re.sub(r"[^a-z0-9 ]+", " ", sin_tildes(t))
    return " ".join(p for p in t.split() if p not in STOP)


def norm_lugar(t):
    t = (t or "").split(" · ")[0]  # the room does not count: "Malba · Nivel 2" is Malba
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
    # real_quick_ratio and quick_ratio are cheap upper bounds of ratio(): they quickly discard most
    # pairs without changing the result.
    return s.real_quick_ratio() >= umbral and s.quick_ratio() >= umbral and s.ratio() >= umbral


def son_duplicados(x, y):
    """Same day and same title; the venue must match unless it is missing in one of them."""
    if x["fecha_inicio"] != y["fecha_inicio"]:
        # Each source dates an after-midnight show on a different day. Only 1 day is tolerated between different
        # sources; within the same source, consecutive days are different performances.
        if abs((date.fromisoformat(x["fecha_inicio"]) - date.fromisoformat(y["fecha_inicio"])).days) != 1:
            return False
        if set(x.get("fuentes", [])) & set(y.get("fuentes", [])):
            return False
    tx, ty = norm_titulo(x["titulo"]), norm_titulo(y["titulo"])
    # Same page and moderately similar titles. The URL alone is not enough: several exhibitions
    # or performances can share the organizer's home page.
    if x.get("url") and x.get("url") == y.get("url") and "instagram.com" not in x["url"] and _parecidos(tx, ty, 0.6):
        return True
    if not _parecidos(tx, ty, 0.85):
        return False
    lx, ly = norm_lugar(x.get("lugar", "")), norm_lugar(y.get("lugar", ""))
    if not lx or not ly:
        return True
    return _parecidos(lx, ly, 0.7) or (x.get("dominio") and x.get("dominio") == y.get("dominio"))


def fusionar(grupo):
    """Merges a group of duplicates: base = the most reliable source; fills in empty fields."""
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
        # "Evento" is the fallback category: another source that classified it better wins.
        if base.get("categoria") == "Evento" and e.get("categoria") not in ("", "Evento", None):
            base["categoria"] = e["categoria"]
        # The organizer's own URL is better than an Instagram post.
        if "instagram.com" in base.get("url", "") and e.get("url") and "instagram.com" not in e["url"]:
            base["url"], base["dominio"] = e["url"], e.get("dominio", "")
    base["fuentes"] = fuentes
    return base


def deduplicar(eventos):
    """Returns (unique_events, number_of_duplicates_removed)."""
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
