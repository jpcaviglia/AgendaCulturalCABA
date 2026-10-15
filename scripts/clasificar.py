"""Clasificación de eventos en categorías canónicas (solo biblioteca estándar)."""
import re
import unicodedata

CATEGORIAS = [
    "Teatro", "Música", "Danza", "Cine", "Artes visuales", "Literatura y charlas",
    "Taller", "Visita guiada", "Infantil", "Feria", "Gastronomía", "Deporte", "Evento",
]


def sin_tildes(texto):
    t = unicodedata.normalize("NFD", texto or "")
    return "".join(c for c in t if unicodedata.category(c) != "Mn").lower()


# Categorías que traen las fuentes -> categoría canónica. Si una fuente usa una
# etiqueta genérica ("Evento", "Otros") se cae a las reglas por palabras clave.
MAPA_FUENTE = {
    "teatro": "Teatro", "obra": "Teatro", "stand up": "Teatro", "humor": "Teatro", "circo": "Teatro",
    "musica": "Música", "recital": "Música", "concierto": "Música", "jazz": "Música", "tango": "Música",
    "danza": "Danza", "baile": "Danza",
    "cine": "Cine", "audiovisual": "Cine",
    "artes visuales": "Artes visuales", "exposicion": "Artes visuales", "muestra": "Artes visuales",
    "arte": "Artes visuales", "fotografia": "Artes visuales",
    "literatura": "Literatura y charlas", "charla": "Literatura y charlas", "conferencia": "Literatura y charlas",
    "taller": "Taller", "curso": "Taller",
    "visita guiada": "Visita guiada", "recorrido": "Visita guiada", "paseo": "Visita guiada",
    "infantil": "Infantil", "ninos": "Infantil", "familia": "Infantil",
    "feria": "Feria", "mercado": "Feria",
    "gastronomia": "Gastronomía", "gastronomico": "Gastronomía",
    "deporte": "Deporte", "deportes": "Deporte",
}

# Reglas por palabras clave sobre título + descripción, en orden de prioridad.
REGLAS = [
    ("Infantil", r"\b(infantil(es)?|para chicos|para ninos|en familia|titeres|ninas y ninos)\b"),
    ("Visita guiada", r"\b(visita guiada|recorrido|city tour|caminata cultural)\b"),
    ("Cine", r"\b(cine|pelicula|proyeccion|documental|cortometraje|ciclo de cine|festival de cine)\b"),
    ("Danza", r"\b(danza|ballet|milonga|folklore|flamenco|bailarin|coreograf)\w*"),
    ("Teatro", r"\b(teatro|obra|stand ?up|comedia|monologo|impro|clown|funcion|dramaturgia|unipersonal)\b"),
    ("Música", r"\b(musica|recital|concierto|banda|show en vivo|jazz|tango|orquesta|coro|dj|cantante|trio|cuarteto)\b"),
    ("Artes visuales", r"\b(muestra|exposicion|exhibicion|galeria|fotografia|pintura|escultura|instalacion|vernissage)\b"),
    ("Literatura y charlas", r"\b(charla|conferencia|presentacion de libro|libro|poesia|lectura|conversatorio|debate|panel|clase magistral)\b"),
    ("Taller", r"\b(taller|curso|seminario|workshop|clase)\b"),
    ("Feria", r"\b(feria|mercado|bazar|ferial)\b"),
    ("Gastronomía", r"\b(gastronomi\w*|degustacion|cata|cena show|brunch|food)\b"),
    ("Deporte", r"\b(deporte|futbol|maraton|torneo|yoga|running|ciclismo)\b"),
]
REGLAS = [(c, re.compile(p)) for c, p in REGLAS]


def clasificar(categoria_fuente, titulo="", descripcion=""):
    """Devuelve una de CATEGORIAS."""
    c = sin_tildes(categoria_fuente).strip()
    if c in MAPA_FUENTE:
        return MAPA_FUENTE[c]
    for clave, canon in MAPA_FUENTE.items():
        if clave in c and len(clave) > 4:
            return canon
    # El título pesa más que la descripción: primero se busca solo en él.
    for texto in (sin_tildes(titulo), sin_tildes(f"{titulo} {descripcion[:400]}")):
        for canon, patron in REGLAS:
            if patron.search(texto):
                return canon
    return "Evento"
