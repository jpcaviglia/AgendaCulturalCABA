"""Genera data/eventos.json con las actividades de las próximas 2 semanas.

Uso:
    python scripts/actualizar_eventos.py

Fuente: agenda semanal oficial de Turismo BA. Cada actividad enlaza al sitio
del organizador, y las que coinciden con un lugar de data/lugares.json se
asocian a ese lugar.

Pensado para correr una vez por semana (ver scripts/README.md).
"""
import json
from datetime import timedelta

from comun import AGENDA_TURISMO_NOMBRE, AGENDA_TURISMO_URL, DATOS, hoy, leer_agenda_turismo

VENTANA_DIAS = 14
SALIDA = DATOS / "eventos.json"
LUGARES = DATOS / "lugares.json"


def cargar_lugares_por_dominio():
    """Mapa dominio -> nombre del lugar, sin redes ni agregadores (su sitio no es del lugar)."""
    if not LUGARES.exists():
        return {}
    lugares = json.loads(LUGARES.read_text(encoding="utf-8"))
    return {
        l["dominio"]: l["nombre"]
        for l in lugares
        if l.get("dominio") and l.get("tipo_web") not in ("Agregador", "Red social o enlace")
    }


def main():
    desde = hoy()
    hasta = desde + timedelta(days=VENTANA_DIAS)
    por_dominio = cargar_lugares_por_dominio()

    eventos = []
    for a in leer_agenda_turismo():
        # La agenda trae fecha de inicio, no de fin. Se incluye lo que empieza antes
        # del cierre de la ventana; lo que ya empezó se marca "En curso".
        if not a["fecha_inicio"] or a["fecha_inicio"] > hasta.isoformat():
            continue
        proximo = a["fecha_inicio"] >= desde.isoformat()
        a["estado"] = "Próximo" if proximo else "En curso"
        a["lugar_verificado"] = por_dominio.get(a["dominio"], "")
        eventos.append(a)

    eventos.sort(key=lambda e: (e["fecha_inicio"], e["titulo"]))
    salida = {
        "generado": desde.isoformat(),
        "ventana": {"desde": desde.isoformat(), "hasta": hasta.isoformat()},
        "fuente": {"nombre": AGENDA_TURISMO_NOMBRE, "url": AGENDA_TURISMO_URL},
        "eventos": eventos,
    }
    SALIDA.write_text(json.dumps(salida, ensure_ascii=False, indent=1), encoding="utf-8")
    proximos = sum(1 for e in eventos if e["estado"] == "Próximo")
    print(f"Ventana {desde} a {hasta}: {len(eventos)} actividades ({proximos} próximas) -> {SALIDA.name}")


if __name__ == "__main__":
    main()
