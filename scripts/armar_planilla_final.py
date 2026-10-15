"""Arma la planilla final: una columna de enlace, una de Instagram, sin filas con solo enlaces descartables.

Uso:
    python scripts/armar_planilla_final.py

Lee data/planilla_actualizada.csv y escribe data/planilla_final.csv.
Descarta una fila si todos sus enlaces (web de la planilla y enlace de la bio)
son de WhatsApp, YouTube, Google Forms, Threads o documentos (Google Docs, Drive).
Las filas sin ningún enlace se conservan.
"""
import csv
import re
from collections import Counter

from comun import DATOS

ENTRADA = DATOS / "planilla_actualizada.csv"
SALIDA = DATOS / "planilla_final.csv"

PATRONES = [
    ("WhatsApp", re.compile(r"wa\.me|wa\.link|whatsapp\.com|api\.whatsapp", re.I)),
    ("YouTube", re.compile(r"youtube\.com|youtu\.be", re.I)),
    ("Google Form", re.compile(r"forms\.gle|docs\.google\.com/forms", re.I)),
    ("Threads", re.compile(r"threads\.(com|net)", re.I)),
    ("Documento", re.compile(r"docs\.google\.com|drive\.google\.com|dochub\.com", re.I)),
]
DESCARTABLES = {"WhatsApp", "YouTube", "Google Form", "Threads", "Documento"}


def tipo_enlace(url):
    for nombre, patron in PATRONES:
        if patron.search(url):
            return nombre
    return "otro"


def enlaces_de(fila):
    """Web de la planilla y enlace de la bio, sin duplicados ni vacíos."""
    candidatos = []
    for url in (fila["Página web (planilla o Instagram)"].strip(), fila["Instagram: enlace en la bio"].strip()):
        if url.startswith("http") and url not in candidatos:
            candidatos.append(url)
    return candidatos


def main():
    with open(ENTRADA, encoding="utf-8-sig", newline="") as f:
        filas = list(csv.DictReader(f))

    salida = []
    descartadas = Counter()
    for fila in filas:
        candidatos = enlaces_de(fila)
        utiles = [u for u in candidatos if tipo_enlace(u) not in DESCARTABLES]
        if candidatos and not utiles:
            descartadas[tipo_enlace(candidatos[0])] += 1
            continue
        instagram = fila["Instagram (planilla)"].strip()
        salida.append({
            "Centro / espacio / sede": fila["Centro / espacio / sede"].strip(),
            "Barrio": fila["Barrio"].strip(),
            "Domicilio": fila["Domicilio"].strip(),
            "Enlace": utiles[0] if utiles else "",
            "Instagram": instagram if instagram.startswith("@") else "",
            "Enlace a eventos": fila["Instagram: enlace a eventos"].strip(),
        })

    with open(SALIDA, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(salida[0].keys()))
        w.writeheader()
        w.writerows(salida)

    print(f"Filas de entrada: {len(filas)}")
    print(f"Descartadas: {sum(descartadas.values())} {dict(descartadas)}")
    print(f"Filas en {SALIDA.name}: {len(salida)}")


if __name__ == "__main__":
    main()
