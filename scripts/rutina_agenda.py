"""Rutina completa: agrega eventos de todas las fuentes, los clasifica, quita duplicados,
actualiza data/eventos.json y publica el cambio en git.

Uso (desde cualquier carpeta):
    python scripts/rutina_agenda.py              # corre todo, hace commit y push
    python scripts/rutina_agenda.py --sin-push   # actualiza y hace commit local
    python scripts/rutina_agenda.py --simular    # no escribe archivos ni toca git

Si una fuente falla, se conservan los eventos que esa fuente aportó en la corrida anterior.
"""
import argparse
import json
import subprocess
from datetime import timedelta

import fuentes_eventos as fe
from clasificar import clasificar
from comun import AGENDA_TURISMO_NOMBRE, AGENDA_TURISMO_URL, DATOS, RAIZ, hoy
from deduplicar import deduplicar
from geocodificar import geocodificar_eventos

VENTANA_DIAS = 14
SALIDA = DATOS / "eventos.json"
REVISION = DATOS / "fuente" / "revision_pendiente.json"
CAMPOS_PUBLICOS = ("titulo", "categoria", "lugar", "barrio", "direccion", "fecha_inicio", "fecha_fin", "hora",
                   "horarios", "precio", "descripcion", "url", "dominio", "estado", "lugar_verificado", "fuentes", "lat", "lng")


def en_ventana(e, desde, hasta):
    ini, fin = e["fecha_inicio"], e.get("fecha_fin") or ""
    if ini > hasta:
        return False
    if ini >= desde:
        return True
    # Ya empezó: solo se acepta si hay fecha de fin vigente, o si viene de Turismo BA (que no informa fin).
    return fin >= desde if fin else bool(e.get("_en_curso_ok"))


def cargar_previos():
    try:
        return json.loads(SALIDA.read_text(encoding="utf-8")).get("eventos", [])
    except (OSError, ValueError):
        return []


def recolectar():
    """Devuelve (eventos_crudos, fuentes_fallidas, revision)."""
    crudos, fallidas, revision = [], [], {"sitios_sin_datos": [], "galerias_sin_datos": [], "solo_instagram": []}

    def intentar(nombre, fn):
        try:
            res = fn()
            print(f"  {nombre}: {len(res)} eventos")
            return res
        except Exception as ex:
            print(f"  {nombre}: FALLÓ ({type(ex).__name__}: {ex})")
            fallidas.append(nombre)
            return []

    crudos += intentar(AGENDA_TURISMO_NOMBRE, fe.turismo)
    try:
        evs, sin_datos = fe.sitios_de_lugares()
        print(f"  Sitios de lugares: {len(evs)} eventos, {len(sin_datos)} sitios sin datos estructurados")
        crudos += evs
        revision["sitios_sin_datos"] = sin_datos
    except Exception as ex:
        print(f"  Sitios de lugares: FALLÓ ({ex})")
        fallidas.append("Sitios de lugares")
    try:
        evs, hallados = fe.sitemaps()
        print(f"  Sitemaps de sitios: {len(evs)} eventos en {len(hallados)} sitios")
        crudos += evs
    except Exception as ex:
        print(f"  Sitemaps: FALLÓ ({ex})")
        fallidas.append("Sitemaps de sitios")
    try:
        evs, sin_datos = fe.galerias()
        print(f"  Galerías: {len(evs)} eventos, {len(sin_datos)} sin datos estructurados")
        crudos += evs
        revision["galerias_sin_datos"] = sin_datos
    except Exception as ex:
        print(f"  Galerías: FALLÓ ({ex})")
        fallidas.append("Galerías")
    for src in fe.agregadores_habilitados():
        crudos += intentar(src["nombre"], lambda s=src: fe.ADAPTADORES[s["adaptador"]](s))
    crudos += intentar("Carga manual", fe.manuales)
    revision["solo_instagram"] = fe.lugares_solo_instagram()
    return crudos, fallidas, revision


def git(*args, check=True):
    r = subprocess.run(["git", *args], cwd=RAIZ, capture_output=True, text=True, encoding="utf-8")
    if check and r.returncode:
        raise RuntimeError(f"git {' '.join(args)}: {r.stderr.strip() or r.stdout.strip()}")
    return r.stdout.strip()


def publicar(resumen, push):
    # eventos_manuales.csv y revision_estado.json los mantiene la rutina del navegador (rutinas/actualizar_agenda.md)
    archivos = [SALIDA, REVISION, DATOS / "lugares.json", DATOS / "galerias.json", DATOS / "fuente" / "mapa_agendas.json", DATOS / "fuente" / "sitios_corregidos.json", DATOS / "fuente" / "eventos_manuales.csv", DATOS / "fuente" / "revision_estado.json"]
    git("add", *[str(a.relative_to(RAIZ)) for a in archivos if a.exists()])
    if not git("diff", "--cached", "--name-only"):
        print("Git: sin cambios para publicar.")
        return
    git("commit", "-m", f"Actualizar agenda {hoy().isoformat()}: {resumen}")
    print("Git: commit creado.")
    if push:
        git("pull", "--rebase", "--autostash", check=False)
        git("push", "origin", "HEAD")
        print("Git: push realizado.")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--simular", action="store_true", help="no escribe archivos ni usa git")
    ap.add_argument("--sin-push", action="store_true", help="hace commit pero no push")
    args = ap.parse_args()

    desde, hasta = hoy().isoformat(), (hoy() + timedelta(days=VENTANA_DIAS)).isoformat()
    print(f"Ventana {desde} a {hasta}\nRecolectando:")
    crudos, fallidas, revision = recolectar()

    previos = cargar_previos()
    for e in previos:  # si una fuente cayó, se conserva lo que aportó antes
        if any(f in fallidas for f in e.get("fuentes", [])):
            e["_tipo"] = "turismo" if AGENDA_TURISMO_NOMBRE in e["fuentes"] else "sitio"
            e["_en_curso_ok"] = e.get("estado") == "En curso"
            crudos.append(dict(e))

    crudos = [e for e in crudos if en_ventana(e, desde, hasta)]
    for e in crudos:
        e["categoria"] = clasificar(e.get("categoria", ""), e["titulo"], e.get("descripcion", ""))
    eventos, duplicados = deduplicar(crudos)

    lugares = json.loads((DATOS / "lugares.json").read_text(encoding="utf-8"))
    por_dominio = {l["dominio"]: l["nombre"] for l in lugares
                   if l.get("dominio") and l.get("tipo_web") not in ("Agregador", "Red social o enlace")}
    for e in eventos:
        e["estado"] = "Próximo" if e["fecha_inicio"] >= desde else "En curso"
        e["lugar_verificado"] = por_dominio.get(e.get("dominio", ""), "")
    eventos.sort(key=lambda e: (e["fecha_inicio"], e["titulo"]))
    if not args.simular:
        nuevas = geocodificar_eventos(eventos, lugares)
        print(f"Mapa: {sum(1 for e in eventos if e['lat'] != '')} de {len(eventos)} eventos ubicados ({nuevas} direcciones nuevas consultadas)")
    eventos = [{k: e.get(k, "") for k in CAMPOS_PUBLICOS} for e in eventos]

    por_cat = {}
    for e in eventos:
        por_cat[e["categoria"]] = por_cat.get(e["categoria"], 0) + 1
    print(f"\n{len(crudos)} registros -> {duplicados} duplicados quitados -> {len(eventos)} eventos")
    print("Por categoría:", ", ".join(f"{k} {v}" for k, v in sorted(por_cat.items(), key=lambda x: -x[1])))
    if fallidas:
        print("Fuentes con error (se conservaron sus datos previos):", ", ".join(fallidas))
    print(f"Pendientes de revisión: {len(revision['sitios_sin_datos'])} sitios sin datos, "
          f"{len(revision['solo_instagram'])} lugares solo Instagram")
    if args.simular:
        return

    anteriores = [{k: e.get(k, "") for k in CAMPOS_PUBLICOS} for e in previos]
    if eventos != anteriores:
        SALIDA.write_text(json.dumps({
            "generado": hoy().isoformat(), "ventana": {"desde": desde, "hasta": hasta},
            "fuente": {"nombre": AGENDA_TURISMO_NOMBRE, "url": AGENDA_TURISMO_URL},
            "fuentes": sorted({f for e in eventos for f in e["fuentes"]}),
            "eventos": eventos}, ensure_ascii=False, indent=1), encoding="utf-8")
    REVISION.write_text(json.dumps(revision, ensure_ascii=False, indent=1), encoding="utf-8")
    publicar(f"{len(eventos)} eventos ({duplicados} duplicados quitados)", push=not args.sin_push)


if __name__ == "__main__":
    main()
