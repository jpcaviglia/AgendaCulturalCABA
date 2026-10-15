"""Agrega eventos hallados con el navegador, de a uno o por tandas, apenas se leen.

Cada evento se escribe en data/fuente/eventos_manuales.csv (para que sobreviva a la próxima corrida completa)
y se inserta ya clasificado y sin duplicados en data/eventos.json. No hace commit: eso lo hace rutina_agenda.py.

Uso:
    python scripts/agregar_evento.py evento.json        # un objeto o una lista de objetos
    python scripts/agregar_evento.py - < eventos.json   # desde stdin
Campos: titulo, fecha_inicio (AAAA-MM-DD) obligatorios; fecha_fin, hora, lugar, barrio, direccion, categoria,
horarios, precio, url, descripcion opcionales.
"""
import csv
import json
import re
import sys
from datetime import timedelta

import fuentes_eventos as fe
from clasificar import clasificar
from comun import DATOS, hoy
from deduplicar import norm_titulo, son_duplicados
from rutina_agenda import CAMPOS_PUBLICOS, SALIDA, VENTANA_DIAS, en_ventana

CAMPOS_CSV = ["titulo", "fecha_inicio", "fecha_fin", "hora", "lugar", "barrio", "direccion", "categoria",
              "horarios", "precio", "url", "descripcion"]
FECHA = re.compile(r"\d{4}-\d{2}-\d{2}$")


def _clave(e):
    return (norm_titulo(e.get("titulo", "")), e.get("fecha_inicio", ""), (e.get("lugar") or "").strip().lower())


def _en_csv():
    if not fe.MANUAL.exists():
        return set()
    with fe.MANUAL.open(encoding="utf-8-sig", newline="") as f:
        return {_clave(fila) for fila in csv.DictReader(f)}


def _anexar_csv(fila):
    nuevo = not fe.MANUAL.exists() or fe.MANUAL.stat().st_size == 0
    if not nuevo and not fe.MANUAL.read_bytes().endswith(b"\n"):
        with fe.MANUAL.open("ab") as f:
            f.write(b"\n")
    with fe.MANUAL.open("a", encoding="utf-8-sig" if nuevo else "utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=CAMPOS_CSV, extrasaction="ignore")
        if nuevo:
            w.writeheader()
        w.writerow(fila)


def _validar(e):
    if not e.get("titulo", "").strip():
        return "falta título"
    if not FECHA.match(e.get("fecha_inicio", "")):
        return "fecha_inicio inválida"
    if e.get("fecha_fin") and not FECHA.match(e["fecha_fin"]):
        return "fecha_fin inválida"
    if not e.get("lugar", "").strip():
        return "falta lugar"
    return ""


def agregar(entrantes):
    desde, hasta = hoy().isoformat(), (hoy() + timedelta(days=VENTANA_DIAS)).isoformat()
    doc = json.loads(SALIDA.read_text(encoding="utf-8"))
    eventos = doc["eventos"]
    lugares = json.loads((DATOS / "lugares.json").read_text(encoding="utf-8"))
    por_dominio = {l["dominio"]: l["nombre"] for l in lugares
                   if l.get("dominio") and l.get("tipo_web") not in ("Agregador", "Red social o enlace")}
    en_csv = _en_csv()
    resumen = {"agregados": 0, "duplicados": 0, "fuera_de_ventana": 0, "invalidos": 0}

    for raw in entrantes:
        motivo = _validar(raw)
        if motivo:
            print(f"  descartado ({motivo}): {raw.get('titulo', '?')}")
            resumen["invalidos"] += 1
            continue
        e = fe.evento(raw["titulo"], raw["fecha_inicio"], "Carga manual", "manual", **{
            k: raw.get(k, "") for k in ("categoria", "lugar", "barrio", "direccion", "horarios", "precio",
                                        "descripcion", "url", "fecha_fin", "hora")})
        if not en_ventana(e, desde, hasta):
            print(f"  fuera de ventana: {e['titulo']} ({e['fecha_inicio']})")
            resumen["fuera_de_ventana"] += 1
            continue
        if _clave(e) not in en_csv:
            _anexar_csv({k: e.get(k, "") for k in CAMPOS_CSV} | {"precio": raw.get("precio", "")})
            en_csv.add(_clave(e))
        e["categoria"] = clasificar(e.get("categoria", ""), e["titulo"], e.get("descripcion", ""))
        e["estado"] = "Próximo" if e["fecha_inicio"] >= desde else "En curso"
        e["lugar_verificado"] = por_dominio.get(e.get("dominio", ""), "")
        previo = next((x for x in eventos if son_duplicados(x, e)), None)
        if previo:
            for campo in ("categoria", "lugar", "barrio", "direccion", "horarios", "descripcion", "url", "fecha_fin", "hora"):
                if not previo.get(campo) and e.get(campo):
                    previo[campo] = e[campo]
            print(f"  duplicado (se completaron campos vacíos): {e['titulo']}")
            resumen["duplicados"] += 1
            continue
        eventos.append({k: e.get(k, "") for k in CAMPOS_PUBLICOS})
        print(f"  agregado: {e['titulo']} · {e['lugar']} · {e['fecha_inicio']}")
        resumen["agregados"] += 1

    eventos.sort(key=lambda x: (x["fecha_inicio"], x["titulo"]))
    doc["eventos"] = eventos
    doc["fuentes"] = sorted({f for x in eventos for f in x["fuentes"]})
    SALIDA.write_text(json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8")
    print(resumen, f"-> {len(eventos)} eventos en total")
    return resumen


def main():
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    texto = sys.stdin.read() if sys.argv[1] == "-" else open(sys.argv[1], encoding="utf-8").read()
    datos = json.loads(texto)
    agregar(datos if isinstance(datos, list) else [datos])


if __name__ == "__main__":
    main()
