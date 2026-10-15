"""Classification of events into canonical categories (standard library only)."""
import re
import unicodedata

CATEGORIAS = [
    "Teatro", "Música", "Danza", "Cine", "Artes visuales", "Literatura y charlas",
    "Taller", "Visita guiada", "Infantil", "Feria", "Festival", "Fiestas y electrónica", "Gastronomía", "Deporte",
    "Evento",
]


def sin_tildes(texto):
    t = unicodedata.normalize("NFD", texto or "")
    return "".join(c for c in t if unicodedata.category(c) != "Mn").lower()


# Categories the sources bring -> canonical category. If a source uses a generic
# label ("Evento", "Otros") it falls back to the keyword rules.
MAPA_FUENTE = {
    # Most specific labels first: the substring search goes through the dictionary in order.
    "festival": "Festival", "festivales": "Festival",
    "musica electronica": "Fiestas y electrónica", "electronica": "Fiestas y electrónica",
    "techno": "Fiestas y electrónica", "fiesta": "Fiestas y electrónica", "fiestas": "Fiestas y electrónica",
    "party": "Fiestas y electrónica", "nightlife": "Fiestas y electrónica", "vida nocturna": "Fiestas y electrónica",
    "club": "Fiestas y electrónica", "dj": "Fiestas y electrónica",
    "teatro": "Teatro", "obra": "Teatro", "stand up": "Teatro", "humor": "Teatro", "circo": "Teatro",
    "musica": "Música", "recital": "Música", "concierto": "Música", "jazz": "Música", "tango": "Música",
    "opera": "Música", "clasica": "Música", "rock": "Música", "popular": "Música", "folclore": "Música",
    "latinoamericana": "Música",
    "performance": "Teatro", "variete": "Teatro",
    "danza": "Danza", "baile": "Danza",
    "cine": "Cine", "audiovisual": "Cine",
    "artes visuales": "Artes visuales", "exposicion": "Artes visuales", "muestra": "Artes visuales",
    "arte": "Artes visuales", "fotografia": "Artes visuales",
    "literatura": "Literatura y charlas", "charla": "Literatura y charlas", "conferencia": "Literatura y charlas",
    "taller": "Taller", "curso": "Taller",
    "visita guiada": "Visita guiada", "turismo y visitas": "Visita guiada", "recorrido": "Visita guiada", "paseo": "Visita guiada",
    "infantil": "Infantil", "ninos": "Infantil", "familia": "Infantil",
    "feria": "Feria", "mercado": "Feria",
    "gastronomia": "Gastronomía", "gastronomico": "Gastronomía",
    "deporte": "Deporte", "deportes": "Deporte",
}

# Keyword rules over title + description, in priority order.
REGLAS = [
    ("Infantil", r"\b(infantil(es)?|para chicos|para ninos|en familia|titeres|ninas y ninos)\b"),
    ("Festival", r"\b(festival(es)?|fest)\b"),
    ("Visita guiada", r"\b(visita guiada|recorrido|city tour|caminata cultural)\b"),
    ("Cine", r"\b(cine|pelicula|proyeccion|documental|cortometraje|ciclo de cine|film|screening)\b|\bdir\. "),
    ("Fiestas y electrónica", r"\b(techno|tecno|hard techno|musica electronica|electronica|electronic music|rave|dj( set)?|djs|"
                              r"b2b|after ?party|club night|boiler room|open air|trance|psytrance|drum (and|&|n) bass|dnb|"
                              r"deep house|tech ?house|house music|party|fiestas?)\b"),
    ("Danza", r"\b(danza|ballet|milonga|folklore|flamenco|bailarin|coreograf)\w*"),
    ("Teatro", r"\b(teatro|obra|stand ?up|comedia|monologo|impro|clown|funcion|dramaturgia|unipersonal)\b"),
    ("Música", r"\b(musica|recital|concierto|banda|show en vivo|jazz|tango|orquesta|coro|cantante|trio|cuarteto|quinteto|quartet|tributo|jam|blues|soul band)\b"),
    ("Artes visuales", r"\b(muestra|exposicion|exhibicion|galeria|fotografia|pintura|escultura|instalacion|vernissage)\b"),
    ("Feria", r"\b(feria|mercado|bazar|ferial)\b"),
    ("Literatura y charlas", r"\b(charla|conferencia|presentacion de libro|libro|poesia|lectura|conversatorio|debate|panel|clase magistral)\b"),
    ("Taller", r"\b(taller|curso|seminario|workshop|clase)\b"),
    ("Gastronomía", r"\b(gastronomi\w*|degustacion|cata|cena show|brunch|food)\b"),
    ("Deporte", r"\b(deporte|futbol|maraton|torneo|yoga|running|ciclismo)\b"),
]
REGLAS = [(c, re.compile(p)) for c, p in REGLAS]


def _texto_url(url):
    """URL path as words (/teatro/1263-casa-que-arde.html -> "teatro 1263 casa que arde html")."""
    ruta = re.sub(r"^[a-z]+://[^/]+", "", sin_tildes(url))
    return re.sub(r"[^a-z0-9]+", " ", ruta)


def clasificar(categoria_fuente, titulo="", descripcion="", url=""):
    """Returns one of CATEGORIAS. The URL is only used if title and description are not enough."""
    c = sin_tildes(categoria_fuente).strip()
    if c in MAPA_FUENTE:
        return MAPA_FUENTE[c]
    for clave, canon in MAPA_FUENTE.items():
        if clave in c and len(clave) > 4:
            return canon
    # The title weighs more than the description: it is searched alone first.
    for texto in (sin_tildes(titulo), sin_tildes(f"{titulo} {descripcion[:400]}"), _texto_url(url)):
        for canon, patron in REGLAS:
            if patron.search(texto):
                return canon
    return "Evento"
