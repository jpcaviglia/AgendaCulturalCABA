"""Revisión de posibles duplicados que la deduplicación automática no unió.

deduplicar.py une solo lo seguro (mismo día, título casi igual, mismo lugar). Este script lista pares
*posibles* con reglas más flojas, para que el agente decida con criterio, y guarda la decisión en
data/crawl/duplicados.json. armar_agenda.py aplica esas decisiones en cada armado: los pares "iguales" se
unen, y ningún par decidido vuelve a aparecer en la lista. Las decisiones se guardan por título y lugar (no
por fecha), así que valen también para las próximas funciones de la misma obra.

Uso:
    python scripts/duplicados.py candidatos [--max N]   # lista numerada (sobre data/eventos.json)
    python scripts/duplicados.py iguales 3 7 12         # esos pares son el mismo evento
    python scripts/duplicados.py distintos 4 5          # esos pares son eventos distintos
"""
import json
import re
import sys
from datetime import date

from comun import CRAWL, DATOS, escribir_json, hoy, leer_json, sin_tildes
from deduplicar import _parecidos, norm_lugar, norm_titulo

DECISIONES = CRAWL / "duplicados.json"
ULTIMA_LISTA = CRAWL / "tmp" / "duplicados_candidatos.json"
GENERICAS = {"argentina", "buenos", "aires", "caba", "the", "and", "show", "en", "vivo", "presenta", "fiesta", "mas",
             "lunes", "martes", "miercoles", "jueves", "viernes", "sabado", "domingo", "visita", "visitas", "guiada",
             "guiadas", "recorrido", "recorridos", "ciclo", "noche", "edicion", "vol", "feria", "ferias", "taller",
             "por", "para", "exposicion", "muestra", "funcion", "teatro", "club", "fest", "festival", "tour"}


def clave(e):
    """Identifica un evento entre corridas: título y lugar normalizados, sin fecha."""
    return f"{norm_titulo(e.get('titulo', ''))} @ {norm_lugar(e.get('lugar', ''))}"


def clave_par(a, b):
    return " || ".join(sorted((a, b)))


def cargar_decisiones():
    return leer_json(DECISIONES, {"iguales": {}, "distintos": {}}) or {"iguales": {}, "distintos": {}}


def _rango(e):
    return e["fecha_inicio"], e.get("fecha_fin") or e["fecha_inicio"]


def _se_superponen(a, b):
    (ia, fa), (ib, fb) = _rango(a), _rango(b)
    return ia <= fb and ib <= fa


def _palabras(t):
    return set(norm_titulo(t).split()) - GENERICAS


def motivo(a, b):
    """Por qué podrían ser el mismo evento, o '' si no hay razón para sospechar."""
    if not _se_superponen(a, b):
        return ""
    fa, fb = a.get("fuentes", []), b.get("fuentes", [])
    misma_fuente = len(fa) == 1 and fa == fb
    # Una fuente casi nunca lista dos veces lo mismo: dentro de una misma fuente solo se sospecha si es el
    # mismo día en el mismo lugar (Passline a veces publica dos fichas de la misma fiesta).
    if misma_fuente and not (a["fecha_inicio"] == b["fecha_inicio"]
                             and norm_lugar(a.get("lugar", "")) == norm_lugar(b.get("lugar", ""))
                             and ((a.get("hora") and a.get("hora") == b.get("hora"))
                                  or _parecidos(norm_titulo(a["titulo"]), norm_titulo(b["titulo"]), 0.5))):
        return ""
    ta, tb = norm_titulo(a["titulo"]), norm_titulo(b["titulo"])
    # Una misma URL sola no alcanza: muchos sitios usan la página del listado para todos sus eventos.
    if (a.get("url") and a.get("url") == b.get("url") and "instagram.com" not in a["url"]
            and (_palabras(a["titulo"]) & _palabras(b["titulo"]))):
        return "misma URL, título parecido"
    la, lb = norm_lugar(a.get("lugar", "")), norm_lugar(b.get("lugar", ""))
    mismo_lugar = bool(la and lb and (_parecidos(la, lb, 0.7) or
                                      (a.get("direccion") and a.get("direccion") == b.get("direccion"))))
    pa, pb = _palabras(a["titulo"]), _palabras(b["titulo"])
    comunes = pa & pb
    corto = min(len(pa), len(pb)) or 1
    if mismo_lugar and (_parecidos(ta, tb, 0.5) or (len(comunes) >= 2 and len(comunes) / corto >= 0.5)
                        or (len(comunes) == 1 and corto == 1)):
        return "mismo lugar, título parecido"
    if a["fecha_inicio"] == b["fecha_inicio"] and (_parecidos(ta, tb, 0.7) or
                                                   (len(comunes) >= 2 and len(comunes) / corto >= 0.67)):
        return "mismo día, título parecido" + ("" if mismo_lugar else " (lugar distinto o sin lugar)")
    return ""


def candidatos(eventos, decisiones):
    """Solo se comparan eventos que comparten algo (una palabra del título, el lugar o la URL): compararlos
    todos contra todos tarda demasiado con las muestras largas, que se superponen con casi todo."""
    ya = set(decisiones["iguales"]) | set(decisiones["distintos"])
    indice = {}
    for i, e in enumerate(eventos):
        llaves = {f"p:{p}" for p in _palabras(e["titulo"]) if len(p) >= 4}
        if norm_lugar(e.get("lugar", "")):
            llaves.add(f"l:{norm_lugar(e['lugar'])}")
        if e.get("url") and "instagram.com" not in e["url"]:
            llaves.add(f"u:{e['url']}")
        for k in llaves:
            indice.setdefault(k, []).append(i)
    vistos, pares = set(), []
    for grupo in indice.values():
        if len(grupo) > 300:  # una palabra muy común no ayuda a encontrar duplicados
            continue
        for x, i in enumerate(grupo):
            for j in grupo[x + 1:]:
                if (i, j) in vistos:
                    continue
                vistos.add((i, j))
                a, b = eventos[i], eventos[j]
                if clave(a) == clave(b):
                    continue  # mismo título y lugar en otra fecha: son funciones distintas
                m = motivo(a, b)
                if m and clave_par(clave(a), clave(b)) not in ya:
                    pares.append((m, a, b))
    pares.sort(key=lambda p: (p[1]["fecha_inicio"], p[1]["titulo"]))
    return pares


def _linea(e):
    fecha = e["fecha_inicio"] + (f"..{e['fecha_fin']}" if e.get("fecha_fin") and e["fecha_fin"] != e["fecha_inicio"] else "")
    hora = f" {e['hora']}" if e.get("hora") else ""
    return (f"{e['titulo']} | {e.get('lugar') or '(sin lugar)'} | {e.get('direccion') or '-'} | {fecha}{hora} | "
            f"{', '.join(e.get('fuentes', []))} | {e.get('url', '')}")


def cmd_candidatos(args):
    maximo = int(args[args.index("--max") + 1]) if "--max" in args else 80
    eventos = (leer_json(DATOS / "eventos.json", {}) or {}).get("eventos", [])
    pares = candidatos(eventos, cargar_decisiones())
    lista = [{"a": clave(a), "b": clave(b), "titulos": [a["titulo"], b["titulo"]]} for _, a, b in pares[:maximo]]
    escribir_json(ULTIMA_LISTA, lista)
    print(f"{len(pares)} pares posibles (se muestran {len(lista)}). Decidí con "
          "`duplicados.py iguales N...` y `duplicados.py distintos N...`.\n")
    for n, (m, a, b) in enumerate(pares[:maximo], 1):
        print(f"{n}. [{m}]\n   A: {_linea(a)}\n   B: {_linea(b)}")


def cmd_decidir(tipo, args):
    lista = leer_json(ULTIMA_LISTA)
    if not lista:
        sys.exit("Primero: python scripts/duplicados.py candidatos")
    dec = cargar_decisiones()
    hechos = []
    for n in args:
        if not n.isdigit() or not 1 <= int(n) <= len(lista):
            sys.exit(f"número fuera de la lista: {n}")
        p = lista[int(n) - 1]
        k = clave_par(p["a"], p["b"])
        otro = "distintos" if tipo == "iguales" else "iguales"
        dec[otro].pop(k, None)
        dec[tipo][k] = {"titulos": p["titulos"], "fecha": hoy().isoformat()}
        hechos.append(n)
    escribir_json(DECISIONES, dec)
    print(f"Anotados como {tipo}: {', '.join(hechos)}. Se aplican en el próximo armar_agenda.py.")


def aplicar_iguales(eventos, fusionar):
    """Une los eventos que el agente marcó como iguales (si sus fechas se superponen). Devuelve (eventos, unidos)."""
    iguales = set(cargar_decisiones()["iguales"])
    if not iguales:
        return eventos, 0
    claves = [clave(e) for e in eventos]
    grupo = list(range(len(eventos)))  # unión de conjuntos

    def raiz(i):
        while grupo[i] != i:
            grupo[i] = grupo[grupo[i]]
            i = grupo[i]
        return i

    por_clave = {}
    for i, k in enumerate(claves):
        por_clave.setdefault(k, []).append(i)
    for par in iguales:
        ka, kb = par.split(" || ")
        for i in por_clave.get(ka, []):
            for j in por_clave.get(kb, []):
                if _se_superponen(eventos[i], eventos[j]):
                    grupo[raiz(i)] = raiz(j)
    grupos = {}
    for i in range(len(eventos)):
        grupos.setdefault(raiz(i), []).append(eventos[i])
    unidos = [fusionar(g) if len(g) > 1 else g[0] for g in grupos.values()]
    return unidos, len(eventos) - len(unidos)


if __name__ == "__main__":
    a = sys.argv[1:]
    if not a or a[0] not in ("candidatos", "iguales", "distintos"):
        sys.exit(__doc__)
    cmd_candidatos(a[1:]) if a[0] == "candidatos" else cmd_decidir(a[0], a[1:])
