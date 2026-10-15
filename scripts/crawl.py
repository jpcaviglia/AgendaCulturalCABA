"""Registro del rastreo con navegador (skill .claude/skills/actualizar-agenda). No usa la red.

El navegador junta los datos; este script solo lleva la cola de la corrida, valida lo que se encontró,
guarda la captura de cada sitio y anota lo aprendido sobre cada sitio para la próxima corrida.

Uso:
    python scripts/crawl.py iniciar [--nueva] [--todos]   # arma la cola (o retoma la corrida abierta); salvo
                                                  # --todos, saltea los sitios con captura de hoy o de ayer
    python scripts/crawl.py siguiente [n]         # muestra los próximos n sitios pendientes con sus notas
    python scripts/crawl.py ver <id>              # muestra todo lo que se sabe de un sitio
    python scripts/crawl.py guardar <archivo.json|->   # registra el resultado de un sitio (ver formato en la skill)
    python scripts/crawl.py ig-vistos <id> <url_post>...   # qué posts de Instagram ya se analizaron (no reabrirlos)
    python scripts/crawl.py estado                # avance de la corrida y cupo de Instagram
    python scripts/crawl.py cerrar [--forzar]     # cierra la corrida y escribe el informe
    python scripts/crawl.py herramientas [llamada]   # la línea que carga navegador.js en la pestaña

Archivos:
    data/crawl/sitios.json          qué rastrear y cómo se comporta cada sitio (se enriquece en cada corrida)
    data/crawl/capturas/<id>.<canal>.json   lo encontrado en la última visita a cada sitio
    data/crawl/corrida.json         cola y avance de la corrida en curso
    data/crawl/informes/<fecha>.md  informe de cada corrida
    data/crawl/local/               solo en esta máquina (no se sube): posts de Instagram ya analizados y
                                    cupo diario / enfriamiento de Instagram; sondeo.json sí se sube
"""
import json
import re
import subprocess
import sys
from datetime import date, datetime, timedelta
from urllib.parse import urljoin

from comun import (CAPTURAS, CORRIDA, CRAWL, DATOS, INFORMES, RAIZ, SITIOS, ZONA_BA, dominio, escribir_json, hoy,
                   leer_json, sin_tildes, slug, ventana)

CANALES = ("web", "instagram")
ESTADOS = {
    "con_eventos": "encontró eventos vigentes o próximos",
    "sin_eventos": "tiene agenda o listado, pero nada vigente ni próximo",
    "sin_agenda": "no publica programación en este canal",
    "no_cultural": "no es un espacio con actividades públicas",
    "no_carga": "no cargó después de 3 intentos",
    "dominio_caido": "dominio que no resuelve, estacionado, suspendido o que redirige a otra cosa",
    "bloqueado": "captcha, login obligatorio, 403 o límite de Instagram",
}
TAREA_BUSCAR = ("No tiene web ni Instagram: buscar en Google la web oficial (y el Instagram), confirmar que está en "
                "CABA y abierto, ponerlos en web_nueva / instagram (y barrio, direccion) y rastrear la web en este mismo "
                "turno. Si no existe, cerró o no está en CABA: 'descartar': '<motivo>' con 'evidencia'.")
# Estados que afirman que no hay nada: exigen haber recorrido todo.
NEGATIVOS = ("sin_eventos", "sin_agenda", "no_cultural")
# Estados de falla: exigen evidencia y vuelven a probarse en la próxima corrida.
FALLAS = ("no_carga", "dominio_caido", "bloqueado")
FASES = {"agregador": 0, "descubrimiento": 1, "galeria": 2, "lugar": 3}
CAMPOS_EVENTO = ("titulo", "fecha_inicio", "fecha_fin", "hora", "horarios", "lugar", "barrio", "direccion",
                 "categoria", "precio", "url", "descripcion", "vigente_sin_fin", "post")
FECHA = re.compile(r"^\d{4}-\d{2}-\d{2}$")
HORA = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")
GRATIS = re.compile(r"\b(gratis|gratuit[oa]|entrada libre|libre y gratuit[oa]|sin cargo|free)\b", re.I)
MAX_NOTAS, MAX_HISTORIAL, MAX_ENTRADAS = 12, 10, 8
# Enlaces descartados con motivo: no se vuelven a abrir hasta que pase este plazo.
MAX_DESCARTADOS, DIAS_RECORDAR_DESCARTE = 30, 180
# Un sitio con captura de hoy o de ayer no se vuelve a abrir: se reutiliza esa captura (pedido del usuario).
DIAS_REUTILIZAR = 1
HERRAMIENTAS = ".claude/skills/actualizar-agenda/navegador.js"
# Sondeo sin navegador (scripts/sondear.py): se muestra en `siguiente` si tiene a lo sumo estos días.
SONDEO = CRAWL / "local" / "sondeo.json"
DIAS_SONDEO = 3

# --- Instagram: cupo, enfriamiento y posts ya analizados (solo local, ver .gitignore) ---
DESCARTADOS = CRAWL / "descartados.json"
LOCAL = CRAWL / "local"
IG_POSTS = LOCAL / "instagram_posts.json"
IG_ESTADO = LOCAL / "instagram_estado.json"
# Límites conservadores; Instagram no publica los suyos. Se pueden ajustar en data/crawl/local/instagram_estado.json.
IG_LIMITES = {"max_paginas_dia": 150, "min_paginas_perfil": 10, "pausa_cada": 25, "pausa_minutos": 5,
              "enfriamiento_horas": 24, "dias_recordar_posts": 180}


def ig_estado():
    est = leer_json(IG_ESTADO, {}) or {}
    est["limites"] = {**IG_LIMITES, **est.get("limites", {})}
    est.setdefault("paginas", {})
    return est


def ig_cupo(est):
    """(páginas que quedan hoy, enfriado_hasta o '')."""
    restantes = est["limites"]["max_paginas_dia"] - est["paginas"].get(hoy().isoformat(), 0)
    hasta = est.get("enfriado_hasta", "")
    if hasta and hasta <= ahora():
        hasta = ""
    return max(restantes, 0), hasta


def ig_registrar_uso(est, paginas, bloqueado, avisos):
    dia = hoy().isoformat()
    antes = est["paginas"].get(dia, 0)
    est["paginas"] = {d: n for d, n in est["paginas"].items() if d >= (hoy() - timedelta(days=7)).isoformat()}
    est["paginas"][dia] = antes + paginas
    lim = est["limites"]
    if bloqueado:
        est["enfriado_hasta"] = (datetime.now(ZONA_BA) + timedelta(hours=lim["enfriamiento_horas"])).strftime("%Y-%m-%d %H:%M")
        avisos.append(f"Instagram bloqueó: no se abre Instagram hasta {est['enfriado_hasta']}. Seguir solo con webs.")
    elif antes // lim["pausa_cada"] < (antes + paginas) // lim["pausa_cada"]:
        avisos.append(f"van {antes + paginas} páginas de Instagram hoy: pausa de {lim['pausa_minutos']} minutos "
                      "antes del próximo perfil (o seguir con webs mientras tanto)")
    escribir_json(IG_ESTADO, est)


def ultima_ig(s):
    return (s.get("ultimo") or {}).get("instagram", {}).get("fecha", "")


# --- herramientas del navegador ---------------------------------------------------

def _git(*args):
    try:
        r = subprocess.run(["git", *args], cwd=RAIZ, capture_output=True, text=True, encoding="utf-8")
        return r.stdout.strip() if r.returncode == 0 else ""
    except OSError:
        return ""


def url_herramientas():
    """(URL de navegador.js en jsDelivr fijada al último commit que lo tocó, motivo si no se puede)."""
    m = re.search(r"github\.com[/:]([^/]+/[^/]+?)(\.git)?$", _git("remote", "get-url", "origin"))
    commit = _git("log", "-1", "--format=%h", "--", HERRAMIENTAS)
    if not m or not commit:
        return "", "no se encontró el repositorio de GitHub o el commit de navegador.js"
    if _git("status", "--porcelain", "--", HERRAMIENTAS):
        return "", "navegador.js tiene cambios sin commitear ni subir"
    if not _git("branch", "-r", "--contains", commit):
        return "", f"el commit {commit} de navegador.js no está subido (git push)"
    return f"https://cdn.jsdelivr.net/gh/{m.group(1)}@{commit}/{HERRAMIENTAS}", ""


def linea_herramientas(llamada="preparar()"):
    url, motivo = url_herramientas()
    if not url:
        return f"({motivo}) Pegar {HERRAMIENTAS} entero seguido de `window.__agt.{llamada}` en cada página."
    return f'(async () => {{ window.__agt || await import("{url}"); return window.__agt.{llamada}; }})()'


def cmd_herramientas(args):
    print(linea_herramientas(args[0] if args else "preparar()"))


# --- carga y guardado -----------------------------------------------------------

def cargar_sitios():
    doc = leer_json(SITIOS)
    if not doc:
        sys.exit(f"No existe {SITIOS}.")
    return doc


def guardar_sitios(doc):
    doc["actualizado"] = hoy().isoformat()
    escribir_json(SITIOS, doc)


def por_id(doc):
    return {s["id"]: s for s in doc["sitios"]}


def item(sid, canal):
    return f"{sid}|{canal}"


def ahora():
    return datetime.now(ZONA_BA).strftime("%Y-%m-%d %H:%M")


# --- cola -----------------------------------------------------------------------

def tuvo_eventos(s):
    return any(u.get("estado") == "con_eventos" for u in (s.get("ultimo") or {}).values())


def armar_cola(doc, previa=None):
    """Todos los sitios, todas las corridas. Orden: agregadores, descubrimiento, galerías, lugares con web,
    y al final Instagram de los que no tienen web. Dentro de cada fase, primero lo que quedó sin rastrear
    en la corrida anterior y lo que ya tuvo eventos."""
    pendientes_previos = set()
    if previa and not previa.get("fin_ok"):
        pendientes_previos = {i for i in previa.get("cola", []) if i not in previa.get("hechos", {})}

    def orden(s, canal):
        previo = item(s["id"], canal) not in pendientes_previos
        if canal == "instagram":  # rotación: primero los perfiles revisados hace más tiempo
            return (9, previo, ultima_ig(s), not tuvo_eventos(s), sin_tildes(s["nombre"]))
        return (FASES.get(s.get("tipo"), 3), previo, not tuvo_eventos(s), sin_tildes(s["nombre"]))

    elegidos = []
    for s in doc["sitios"]:
        if s.get("rastrear") is False:
            continue
        if s.get("web"):
            elegidos.append((orden(s, "web"), item(s["id"], "web")))
        elif s.get("instagram"):
            elegidos.append((orden(s, "instagram"), item(s["id"], "instagram")))
        else:  # sin web ni Instagram: se busca su web oficial
            elegidos.append((orden(s, "web"), item(s["id"], "web")))
    return [i for _, i in sorted(elegidos)]


def cargar_corrida():
    return leer_json(CORRIDA)


def pendientes(corrida, sitios=None):
    """Webs en el orden de la cola y después Instagram, primero los perfiles revisados hace más tiempo."""
    pend = [i for i in corrida["cola"] if i not in corrida["hechos"]]
    if sitios is None:
        return pend
    webs = [i for i in pend if i.endswith("|web")]
    igs = sorted((i for i in pend if i.endswith("|instagram")),
                 key=lambda i: (ultima_ig(sitios.get(i.split("|")[0], {})), corrida["cola"].index(i)))
    return webs + igs


def posponer_instagram(corrida, motivo):
    """Deja los perfiles de Instagram pendientes para la próxima corrida (no es una falla del sitio)."""
    pend = [i for i in pendientes(corrida) if i.endswith("|instagram")]
    for i in pend:
        corrida["hechos"][i] = "pospuesto"
    corrida.setdefault("motivo_pospuesto", motivo)
    escribir_json(CORRIDA, corrida)
    return len(pend)


def captura_reciente(sid, canal):
    """(fecha, estado) de la captura de <id>.<canal> si es de los últimos DIAS_REUTILIZAR días, o None."""
    cap = leer_json(CAPTURAS / f"{sid}.{canal}.json")
    corte = (hoy() - timedelta(days=DIAS_REUTILIZAR)).isoformat()
    if cap and cap.get("fecha", "") >= corte:
        return cap["fecha"], cap.get("estado", "")
    return None


def marcar_reutilizados(corrida, sitios):
    """Da por hechos los ítems pendientes con captura reciente. Si la web reutilizada no tuvo eventos y el sitio
    tiene Instagram, encola el Instagram (como haría `guardar`). Devuelve cuántos marcó."""
    n = 0
    for i in list(corrida["cola"]):
        if i in corrida["hechos"]:
            continue
        sid, canal = i.split("|")
        rec = captura_reciente(sid, canal)
        if not rec:
            continue
        corrida["hechos"][i] = "reutilizado"
        n += 1
        ig = item(sid, "instagram")
        if (canal == "web" and rec[1] != "con_eventos" and sitios.get(sid, {}).get("instagram")
                and ig not in corrida["cola"]):
            corrida["cola"].append(ig)
    return n


def cmd_iniciar(args):
    doc = cargar_sitios()
    previa = cargar_corrida()
    todos = "--todos" in args
    if previa and not previa.get("fin") and "--nueva" not in args:
        inicio = date.fromisoformat(previa["id"][:10])
        if (hoy() - inicio).days <= 3:
            print(f"Se retoma la corrida {previa['id']} (iniciada {previa['inicio']}).")
            if not todos:
                n = marcar_reutilizados(previa, por_id(doc))
                if n:
                    escribir_json(CORRIDA, previa)
                    print(f"{n} sitios con captura de hoy o de ayer: se reutilizan, no se vuelven a abrir.")
            return cmd_estado([])
        print(f"La corrida {previa['id']} quedó abierta hace más de 3 días: se empieza una nueva.")
        previa["fin"], previa["fin_ok"] = ahora(), False
    desde, hasta = ventana()
    cola = armar_cola(doc, previa)
    corrida = {"id": hoy().isoformat(), "inicio": ahora(), "fin": None, "ventana": {"desde": desde, "hasta": hasta},
               "cola": cola, "hechos": {}, "sitios_nuevos": [], "eventos": 0}
    reutilizados = 0 if todos else marcar_reutilizados(corrida, por_id(doc))
    escribir_json(CORRIDA, corrida)
    omitidos = [s["nombre"] for s in doc["sitios"] if s.get("rastrear") is False]
    sin_canal = [s["nombre"] for s in doc["sitios"] if s.get("rastrear") is not False and not s.get("web") and not s.get("instagram")]
    print(f"Corrida {corrida['id']}: {len(corrida['cola'])} sitios en cola, {len(pendientes(corrida))} por rastrear. "
          f"Ventana {desde} a {hasta}.")
    if reutilizados:
        print(f"{reutilizados} sitios con captura de hoy o de ayer: se reutilizan, no se vuelven a abrir "
              "(`iniciar --nueva --todos` para rastrear todo).")
    print("Antes de abrir el navegador: `python scripts/sondear.py --corrida` (lee sin navegador lo que se pueda).")
    if omitidos:
        print(f"No se rastrean por decisión ({len(omitidos)}): {', '.join(omitidos)}")
    if sin_canal:
        print(f"Sin web ni Instagram ({len(sin_canal)}): están en la cola para buscar su web oficial.")
    print("Herramientas del navegador, en cada página:\n  " + linea_herramientas())


PISTAS_SONDEO = {
    "html": "La agenda se lee sin navegador: leé `texto` (Read) y cargá los eventos desde ahí, con urls_visitadas = "
            "paginas_agenda y enlaces_candidatos = esas páginas como visitadas. Abrí el navegador solo si el texto "
            "no alcanza (faltan fechas o fichas) o si no aparece ningún evento (para marcar vacío hay que verificar "
            "en el navegador). Otras páginas del sitio (mes completo, fichas, página 2) se leen con "
            "`python scripts/sondear.py --leer <url>`.",
    "needs_browser": "El HTML no trae la agenda (app de JavaScript): navegador.",
    "sin_agenda_vista": "Sin pedidos simples no se vio agenda; no es prueba de que no haya: navegador.",
    "unreachable": "No cargó con un pedido simple (motivo en `motivo`). Si es DNS, probá una vez en el navegador; "
                   "si tampoco resuelve, dominio_caido con esa evidencia. Si es 403/400, el sitio bloquea "
                   "pedidos simples: navegador normal.",
    "api": "La API no se pudo guardar sola (ver `error`). Si hay `texto`, leelo como en html; si no, navegador.",
    "jsonld": "El JSON-LD no se pudo guardar solo (ver `error`). Si hay `texto`, leelo como en html; si no, navegador.",
}


def cargar_sondeo():
    doc = leer_json(SONDEO, {}) or {}
    corte = (hoy() - timedelta(days=DIAS_SONDEO)).isoformat()
    return {s["id"]: s for s in doc.get("sitios", []) if s.get("fecha", doc.get("fecha", ""))[:10] >= corte}


def resumen_sondeo(r):
    out = {k: r[k] for k in ("clase", "fecha", "motivo", "plataforma", "paginas_agenda", "texto", "error") if r.get(k)}
    out["pista"] = PISTAS_SONDEO.get(r.get("clase"), "")
    return out


def resumen_sitio(s, canal=None, sondeo=None):
    claves = ("id", "nombre", "tipo", "lugares", "web", "instagram", "enlace_bio", "entradas", "comportamiento",
              "enlaces_pendientes", "ultimo")
    out = {k: s[k] for k in claves if s.get(k)}
    if canal:
        out = {"item": item(s["id"], canal), "canal": canal, **out}
    descartados = descartes_vigentes(s)
    if descartados:  # ya se vio que no sirven: no abrirlos
        out["enlaces_descartados"] = [[d["url"], d["motivo"]] for d in descartados.values()]
    out["notas"] = s.get("notas", [])[-6:]
    out["historial"] = s.get("historial", [])[-4:]
    if canal == "web" and not s.get("web") and not s.get("instagram"):
        out["tarea"] = TAREA_BUSCAR
    if canal == "web" and sondeo and s["id"] in sondeo:
        out["sondeo"] = resumen_sondeo(sondeo[s["id"]])
    return out


def cmd_siguiente(args):
    n = int(args[0]) if args else 1
    corrida = cargar_corrida()
    if not corrida or corrida.get("fin"):
        sys.exit("No hay corrida abierta: correr primero `python scripts/crawl.py iniciar`.")
    sitios = por_id(cargar_sitios())
    pend = pendientes(corrida, sitios)
    if pend and pend[0].endswith("|instagram"):
        est = ig_estado()
        restantes, enfriado = ig_cupo(est)
        if enfriado or restantes < est["limites"]["min_paginas_perfil"]:
            motivo = f"enfriamiento hasta {enfriado}" if enfriado else "cupo diario de páginas agotado"
            n_pos = posponer_instagram(corrida, motivo)
            print(f"Instagram: {motivo}. {n_pos} perfiles quedan para la próxima corrida (van primeros).")
            pend = pendientes(corrida, sitios)
        else:
            print(f"Instagram: quedan {restantes} páginas de cupo hoy. Antes de abrir posts, consultar "
                  "`crawl.py ig-vistos <id> <urls>` y abrir solo los nuevos.")
    hechos = len(corrida["hechos"])
    url, _ = url_herramientas()
    if url:
        print(f"Herramientas: {url}")
    print(f"Avance: {hechos} de {len(corrida['cola'])} hechos. Ventana {corrida['ventana']['desde']} a {corrida['ventana']['hasta']}.")
    if not pend:
        print("Cola vacía: correr armar_agenda.py y `crawl.py cerrar`.")
        return
    sondeo = cargar_sondeo()
    if not sondeo and any(i.endswith("|web") for i in pend):
        print("Sin sondeo reciente: correr `python scripts/sondear.py --corrida` antes de seguir con las webs.")
    salida = []
    for i in pend[:n]:
        sid, canal = i.split("|")
        if sid in sitios:
            salida.append(resumen_sitio(sitios[sid], canal, sondeo))
    print(json.dumps(salida, ensure_ascii=False, indent=1))


def cmd_ver(args):
    if not args:
        sys.exit("Uso: crawl.py ver <id>")
    sitios = por_id(cargar_sitios())
    s = sitios.get(args[0])
    if not s:
        cand = [k for k in sitios if args[0].lower() in k or args[0].lower() in sin_tildes(sitios[k]["nombre"])]
        sys.exit(f"No existe el id {args[0]!r}. Parecidos: {', '.join(cand[:10]) or 'ninguno'}")
    print(json.dumps(s, ensure_ascii=False, indent=1))


# --- validación del resultado -----------------------------------------------------

def _fecha_ok(v):
    if not FECHA.match(v or ""):
        return False
    try:
        date.fromisoformat(v)
        return True
    except ValueError:
        return False


def normalizar_evento(raw, sitio, errores, avisos):
    """Devuelve el evento limpio, o None si se descarta (con el motivo en errores o avisos)."""
    if not isinstance(raw, dict):
        errores.append(f"evento que no es un objeto: {raw!r}")
        return None
    e = {k: (raw.get(k) or "") if k != "vigente_sin_fin" else bool(raw.get(k)) for k in CAMPOS_EVENTO}
    for k, v in e.items():
        if isinstance(v, str):
            e[k] = re.sub(r"\s+", " ", v).strip()
    extra = set(raw) - set(CAMPOS_EVENTO)
    if extra:
        avisos.append(f"campos ignorados en {e['titulo'] or '?'}: {', '.join(sorted(extra))}")
    nombre = e["titulo"] or "(sin título)"
    if not e["titulo"]:
        errores.append("evento sin título")
        return None
    if not _fecha_ok(e["fecha_inicio"]):
        errores.append(f"{nombre}: fecha_inicio {e['fecha_inicio']!r} no es AAAA-MM-DD válida")
        return None
    if e["fecha_fin"] and not _fecha_ok(e["fecha_fin"]):
        errores.append(f"{nombre}: fecha_fin {e['fecha_fin']!r} no es AAAA-MM-DD válida")
        return None
    if e["fecha_fin"] and e["fecha_fin"] < e["fecha_inicio"]:
        errores.append(f"{nombre}: fecha_fin anterior a fecha_inicio")
        return None
    if e["hora"] and not HORA.match(e["hora"]):
        errores.append(f"{nombre}: hora {e['hora']!r} debe ser HH:MM (si hay varias, ponerlas en 'horarios')")
        return None
    anio = int(e["fecha_inicio"][:4])
    if not hoy().year - 2 <= anio <= hoy().year + 1:
        errores.append(f"{nombre}: año {anio} poco plausible (¿se asumió mal el año?)")
        return None
    if not e["lugar"] and not sitio.get("lugar_opcional"):  # lugar_opcional: listados sin lugar (scripts/saleplan.py)
        if len(sitio.get("lugares", [])) == 1:
            e["lugar"] = sitio["lugares"][0]
        else:
            errores.append(f"{nombre}: falta 'lugar' (obligatorio en agregadores, descubrimiento y sitios con varios "
                           f"lugares: {', '.join(sitio.get('lugares', []))})")
            return None
    fin = e["fecha_fin"] or e["fecha_inicio"]
    if fin < hoy().isoformat() and not e["vigente_sin_fin"]:
        avisos.append(f"{nombre}: ya terminó ({fin}), no se guarda")
        return None
    if e["precio"] and GRATIS.search(e["precio"]) and not re.search(r"\$\s*\d", e["precio"]):
        e["precio"] = "Gratis"
    e["descripcion"] = e["descripcion"][:700]
    if not e["url"] and e["post"]:  # sin ficha ni entradas: se enlaza el post de Instagram
        e["url"] = e["post"]
    if e["url"] and not e["url"].startswith("http"):
        errores.append(f"{nombre}: url {e['url']!r} debe ser absoluta (https://...)")
        return None
    return e


def validar(res, sitios):
    """Devuelve (sitio, canal, eventos, errores, avisos)."""
    errores, avisos = [], []
    sitio = sitios.get(res.get("id", ""))
    if not sitio:
        return None, None, [], [f"id {res.get('id')!r} no existe en sitios.json (ver `crawl.py ver <texto>`)"], []
    canal = res.get("canal", "web")
    if canal not in CANALES:
        errores.append(f"canal debe ser uno de {CANALES}")
    if canal == "web" and not sitio.get("web") and not sitio.get("instagram") and not (res.get("web_nueva") or res.get("instagram")):
        errores.append("este sitio no tenía web ni Instagram: poner web_nueva o instagram con lo que encontraste, "
                       "o 'descartar' si no existe, cerró o no está en CABA")
    estado = res.get("estado")
    if estado not in ESTADOS:
        errores.append(f"estado {estado!r} inválido; opciones: {', '.join(ESTADOS)}")
    visitadas = res.get("urls_visitadas") or []
    candidatos = res.get("enlaces_candidatos")
    evidencia = (res.get("evidencia") or "").strip()

    if estado in NEGATIVOS or estado == "con_eventos":
        if not visitadas:
            errores.append("faltan urls_visitadas: listar todas las páginas abiertas")
        if candidatos is None:
            errores.append("falta enlaces_candidatos: los enlaces a agenda, muestras, exposiciones, cartelera, "
                           "programación, actividades, ticketera, etc. que se encontraron (lista vacía si no hay ninguno)")
        else:
            recordados = descartes_vigentes(sitio)
            sin_ver, debiles = [], []
            for c in candidatos:
                if not isinstance(c, dict) or c.get("visitado") or c.get("descartado"):
                    continue
                previo = recordados.get(_norm_url(url_absoluta(sitio, c.get("url"))))
                if previo:  # descartado con motivo en una corrida anterior: no hace falta reabrirlo
                    c["descartado"] = previo["motivo"]
                elif c.get("debil") and estado == "con_eventos":
                    debiles.append(c)
                else:
                    sin_ver.append(c)
            if debiles:
                avisos.append(f"{len(debiles)} enlaces débiles sin abrir (se acepta porque hubo eventos): "
                              + ", ".join(c.get("texto") or c.get("url", "") for c in debiles))
            if sin_ver:
                pista = (" (con eventos, solo los marcados 'debil': true pueden quedar sin abrir)"
                         if estado == "con_eventos" else "")
                errores.append(f"hay enlaces candidatos sin abrir. Abrirlos o poner 'descartado': '<motivo concreto>'{pista}:\n    "
                               + "\n    ".join(f"{c.get('texto', '')} -> {c.get('url', '')}" for c in sin_ver))
    if estado in NEGATIVOS:
        if not res.get("scroll_completo"):
            errores.append(f"para marcar {estado} hay que haber scrolleado hasta el final de cada listado y "
                           "expandido los 'ver más' (scroll_completo: true)")
        if not evidencia:
            errores.append(f"para marcar {estado} hace falta 'evidencia': qué se vio en cada página revisada")
        if res.get("eventos"):
            errores.append(f"estado {estado} pero hay eventos: usar con_eventos")
    if estado == "no_carga" and int(res.get("intentos") or 0) < 3:
        errores.append("no_carga exige intentos >= 3 (esperar hasta 30 s, recargar, probar sin www/con http, "
                       "probar la portada o una ficha). Si un intento cargó, no es no_carga")
    if estado in FALLAS and not evidencia:
        errores.append(f"{estado} exige 'evidencia' (mensaje de error, qué mostró la página)")
    if estado == "con_eventos" and not res.get("eventos"):
        errores.append("con_eventos sin eventos")

    eventos, vistos = [], set()
    for raw in res.get("eventos") or []:
        e = normalizar_evento(raw, sitio, errores, avisos)
        if not e:
            continue
        clave = (sin_tildes(e["titulo"]), e["fecha_inicio"], sin_tildes(e["lugar"]))
        if clave in vistos:
            avisos.append(f"repetido en el mismo resultado: {e['titulo']} {e['fecha_inicio']}")
            continue
        vistos.add(clave)
        eventos.append(e)
    if estado == "con_eventos" and res.get("eventos") and not eventos and not errores:
        avisos.append("todos los eventos ya terminaron: se registra como sin_eventos")
        res["estado"] = "sin_eventos"
    return sitio, canal, eventos, errores, avisos


# --- registro -----------------------------------------------------------------------

def _agregar_unico(lista, valores, maximo):
    for v in reversed(valores):
        if v in lista:
            lista.remove(v)
        lista.insert(0, v)
    del lista[maximo:]


def aprender(sitio, canal, res, eventos):
    """Guarda en el sitio lo aprendido: cómo se comporta, dónde está la agenda y qué quedó por ver."""
    fecha = hoy().isoformat()
    estado = res["estado"]
    if res.get("web_nueva"):
        sitio.setdefault("notas", []).append(f"{fecha}: la web cambió de {sitio.get('web')} a {res['web_nueva']}")
        sitio["web"] = res["web_nueva"]
    for campo in ("instagram", "enlace_bio"):
        if res.get(campo) and res[campo] != sitio.get(campo):
            sitio[campo] = res[campo]
    entradas = [u for u in res.get("entradas") or [] if isinstance(u, str) and u.startswith("http")]
    if entradas and canal == "web":
        _agregar_unico(sitio.setdefault("entradas", []), entradas, MAX_ENTRADAS)
    comp = sitio.setdefault("comportamiento", {})
    for k, v in (res.get("comportamiento") or {}).items():
        if v is None:
            comp.pop(k, None)
        else:
            comp[k] = v
    if res.get("nota"):  # si el sitio se vuelve a guardar el mismo día, la nota nueva reemplaza a la anterior
        notas = [n for n in sitio.get("notas", []) if not n.startswith(f"{fecha} [{canal}] ")]
        sitio["notas"] = notas + [f"{fecha} [{canal}] {res['nota'].strip()}"]
    del sitio.setdefault("notas", [])[:-MAX_NOTAS]
    # Enlaces vistos pero no recorridos: la próxima corrida empieza por ellos.
    visitadas = set(res.get("urls_visitadas") or [])
    pend = [p for p in sitio.get("enlaces_pendientes", []) if p.get("url") not in visitadas]
    descartados = descartes_vigentes(sitio)
    for c in res.get("enlaces_candidatos") or []:
        if not isinstance(c, dict) or not c.get("url"):
            continue
        url = url_absoluta(sitio, c["url"])
        if c.get("descartado"):
            descartados[_norm_url(url)] = {"url": url, "texto": c.get("texto", ""), "motivo": c["descartado"], "fecha": fecha}
        elif c.get("visitado"):  # se abrió esta vez: un descarte anterior del mismo enlace ya no vale
            descartados.pop(_norm_url(url), None)
        elif not c.get("debil"):  # los débiles se vuelven a encontrar solos
            if url not in {p["url"] for p in pend}:
                pend.append({"url": url, "texto": c.get("texto", ""), "desde": fecha})
    if descartados:
        sitio["enlaces_descartados"] = sorted(descartados.values(), key=lambda d: d["fecha"])[-MAX_DESCARTADOS:]
    else:
        sitio.pop("enlaces_descartados", None)
    for u in res.get("enlaces_nuevos") or []:
        u = u if isinstance(u, dict) else {"url": u}
        if u.get("url") and u["url"] not in visitadas and u["url"] not in {p["url"] for p in pend}:
            pend.append({"url": u["url"], "texto": u.get("texto", ""), "desde": fecha})
    if pend:
        sitio["enlaces_pendientes"] = pend[-20:]
    else:
        sitio.pop("enlaces_pendientes", None)
    sitio.setdefault("ultimo", {})[canal] = {"fecha": fecha, "estado": estado, "eventos": len(eventos),
                                             "paginas": len(visitadas)}
    sitio.setdefault("historial", []).append({"fecha": fecha, "canal": canal, "estado": estado, "eventos": len(eventos)})
    del sitio["historial"][:-MAX_HISTORIAL]


def _norm_url(u):
    u = re.sub(r"^https?://(www\.)?", "", (u or "").strip().lower())
    return u.split("#")[0].rstrip("/")


def url_absoluta(sitio, u):
    """Las herramientas devuelven rutas sueltas (/agenda) para los enlaces del mismo sitio."""
    u = (u or "").strip()
    return urljoin(sitio["web"], u) if u.startswith("/") and sitio.get("web") else u


def descartes_vigentes(sitio):
    """Enlaces descartados con motivo en los últimos DIAS_RECORDAR_DESCARTE días, por URL normalizada."""
    corte = (hoy() - timedelta(days=DIAS_RECORDAR_DESCARTE)).isoformat()
    return {_norm_url(d["url"]): d for d in sitio.get("enlaces_descartados", []) if d.get("fecha", "") >= corte}


DOMINIOS_COMPARTIDOS = ("instagram.com", "facebook.com", "linktr.ee", "alternativateatral.com", "buenosaires.gob.ar",
                        "blogspot.com", "wordpress.com", "sites.google.com", "wixsite.com", "passline.com",
                        "eventbrite.com.ar", "eventbrite.com")


def buscar_existente(doc, nuevo):
    web, ig = _norm_url(nuevo.get("web")), (nuevo.get("instagram") or "").lower().lstrip("@")
    d = dominio(nuevo.get("web", ""))
    nombre = slug(nuevo.get("nombre", ""))
    for s in doc["sitios"]:
        if web and _norm_url(s.get("web")) == web:
            return s
        if web and d and not any(d.endswith(x) for x in DOMINIOS_COMPARTIDOS) and dominio(s.get("web", "")) == d:
            return s
        if ig and (s.get("instagram") or "").lower().lstrip("@") == ig:
            return s
        if nombre and (s["id"] == nombre or nombre in {slug(x) for x in s.get("lugares", [])}):
            return s
    return None


def dar_de_alta(s, lugares, galerias, barrio="", direccion=""):
    """Suma un sitio confirmado a galerias.json (si es galería o museo de arte) y a lugares.json."""
    nombre, web, ig = s["nombre"], s.get("web", ""), s.get("instagram", "")
    if s.get("tipo") == "galeria" and not any(sin_tildes(g["nombre"]) == sin_tildes(nombre) for g in galerias["galerias"]):
        galerias["galerias"].append({"nombre": nombre, "web": web, "tipo": "Galería o museo", "verificada": bool(web)})
    if s.get("tipo") in ("lugar", "galeria") and not any(sin_tildes(l["nombre"]) == sin_tildes(nombre) for l in lugares):
        lugares.append({"nombre": nombre, "barrio": barrio, "domicilio": direccion, "web": web, "dominio": dominio(web),
                        "tipo_web": "Sitio propio" if web else "", "instagram": ig,
                        "estado": "Probable: menciona eventos" if web else "Sin web", "evidencia": s.get("origen", ""),
                        "canal": "Sitio web" if web else "Instagram (sin listado confirmado en la web)"})


def agregar_sitios_nuevos(doc, nuevos, origen, corrida, avisos):
    """Suma a sitios.json (y a lugares.json o galerias.json) los espacios descubiertos, y los encola en esta corrida."""
    agregados = []
    lugares = leer_json(DATOS / "lugares.json", [])
    galerias = leer_json(DATOS / "galerias.json", {"galerias": []})
    ids = {s["id"] for s in doc["sitios"]}
    for n in nuevos or []:
        if not isinstance(n, dict) or not n.get("nombre") or not (n.get("web") or n.get("instagram")):
            avisos.append(f"sitio nuevo ignorado (falta nombre y web o instagram): {n!r}")
            continue
        previo = buscar_existente(doc, n)
        if previo:
            avisos.append(f"sitio ya conocido: {n['nombre']} = {previo['id']}")
            continue
        baja = buscar_existente({"sitios": leer_json(DESCARTADOS, [])}, n)
        if baja:
            avisos.append(f"{n['nombre']} se descartó el {baja.get('fecha')} ({baja.get('motivo')}); si reabrió, "
                          "sacarlo de data/crawl/descartados.json y volver a sumarlo")
            continue
        tipo = n.get("tipo") if n.get("tipo") in FASES else "lugar"
        sid = slug(n["nombre"])
        while sid in ids:
            sid += "-2"
        ids.add(sid)
        ig = n.get("instagram", "")
        if ig and not ig.startswith("@"):
            ig = "@" + ig.rstrip("/").split("/")[-1]
        s = {"id": sid, "nombre": n["nombre"], "tipo": tipo, "lugares": [n["nombre"]], "web": n.get("web", ""),
             "instagram": ig, "origen": f"descubierto en {origen} el {hoy().isoformat()}"}
        if n.get("motivo"):
            s["notas"] = [f"{hoy().isoformat()}: {n['motivo']}"]
        doc["sitios"].append(s)
        dar_de_alta(s, lugares, galerias, n.get("barrio", ""), n.get("direccion", ""))
        if corrida and not corrida.get("fin"):
            corrida["cola"].append(item(sid, "web" if s["web"] else "instagram"))
            corrida["sitios_nuevos"].append(sid)
        agregados.append(sid)
    if agregados:
        escribir_json(DATOS / "lugares.json", lugares)
        escribir_json(DATOS / "galerias.json", galerias)
    return agregados


def url_post(u):
    u = (u.get("url") if isinstance(u, dict) else u) or ""
    return u.split("?")[0].split("#")[0].rstrip("/") + "/" if u else ""


def reusar_posts(res):
    """Suma al resultado los eventos vigentes de posts que ya se analizaron en otra corrida y siguen en el perfil."""
    registro = leer_json(IG_POSTS, {}) or {}
    ya = {url_post(e.get("post")) for e in res.get("eventos") or [] if isinstance(e, dict) and e.get("post")}
    sumados = []
    for p in res.get("posts") or []:
        u = url_post(p)
        if not u or u in ya or u not in registro:
            continue
        for e in registro[u].get("eventos", []):
            if (e.get("fecha_fin") or e.get("fecha_inicio", "")) >= hoy().isoformat() or e.get("vigente_sin_fin"):
                sumados.append({**e, "post": u})
    if sumados:
        res.setdefault("eventos", []).extend(sumados)
        if res.get("estado") in NEGATIVOS:
            res["estado"] = "con_eventos"
    return len(sumados)


def registrar_posts(sitio, res, eventos, avisos):
    """Anota localmente cada post visto con sus eventos, y descuenta el cupo diario de Instagram."""
    registro = leer_json(IG_POSTS, {}) or {}
    est = ig_estado()
    nuevos = 0
    for p in res.get("posts") or []:
        u = url_post(p)
        if not u:
            continue
        previo = registro.get(u, {})
        nuevos += not previo
        registro[u] = {"id": sitio["id"], "visto": hoy().isoformat(),
                       "publicado": (p.get("publicado") if isinstance(p, dict) else "") or previo.get("publicado", ""),
                       "eventos": [{k: v for k, v in e.items() if k != "post"} for e in eventos if url_post(e.get("post")) == u]}
    sin_post = sum(1 for e in eventos if not e.get("post"))
    if sin_post and res.get("posts"):
        avisos.append(f"{sin_post} eventos sin 'post': no se van a poder reutilizar en la próxima corrida")
    corte = (hoy() - timedelta(days=est["limites"]["dias_recordar_posts"])).isoformat()
    escribir_json(IG_POSTS, {u: r for u, r in registro.items() if r.get("visto", "") >= corte})
    paginas = int(res.get("paginas_instagram") or (1 + nuevos))
    ig_registrar_uso(est, paginas, res.get("estado") == "bloqueado", avisos)


def cmd_ig_vistos(args):
    if len(args) < 2:
        sys.exit("Uso: crawl.py ig-vistos <id> <url_post> [<url_post>...]")
    registro = leer_json(IG_POSTS, {}) or {}
    restantes, enfriado = ig_cupo(ig_estado())
    nuevos = []
    for u in map(url_post, args[1:]):
        r = registro.get(u)
        if r:
            print(f"visto   {u} (el {r['visto']}, {len(r.get('eventos', []))} eventos): no abrir, poner en 'posts'")
        else:
            nuevos.append(u)
            print(f"NUEVO   {u}")
    print(f"{len(nuevos)} nuevos para abrir. Cupo de Instagram hoy: {restantes} páginas"
          + (f". EN ENFRIAMIENTO hasta {enfriado}: no abrir Instagram" if enfriado else "."))


def descartar(doc, sitios, res):
    """Saca un sitio que no existe, cerró o no está en CABA (de sitios.json, lugares.json, galerias.json y capturas)."""
    sitio = sitios.get(res.get("id", ""))
    if not sitio:
        sys.exit(f"NO SE GUARDÓ: id {res.get('id')!r} no existe")
    if not (res.get("evidencia") or "").strip():
        print("NO SE GUARDÓ. Para descartar un sitio hace falta 'evidencia' (qué se buscó y qué se encontró).")
        sys.exit(2)
    nombres = {sin_tildes(n) for n in [sitio["nombre"], *sitio.get("lugares", [])]}
    doc["sitios"] = [s for s in doc["sitios"] if s["id"] != sitio["id"]]
    lugares = [l for l in leer_json(DATOS / "lugares.json", []) if sin_tildes(l["nombre"]) not in nombres]
    galerias = leer_json(DATOS / "galerias.json", {"galerias": []})
    galerias["galerias"] = [g for g in galerias["galerias"] if sin_tildes(g["nombre"]) not in nombres]
    escribir_json(DATOS / "lugares.json", lugares)
    escribir_json(DATOS / "galerias.json", galerias)
    for ruta in CAPTURAS.glob(f"{sitio['id']}.*.json"):
        ruta.unlink()
    bajas = leer_json(DESCARTADOS, [])
    bajas.append({"id": sitio["id"], "nombre": sitio["nombre"], "web": sitio.get("web", ""), "instagram": sitio.get("instagram", ""),
                  "lugares": sitio.get("lugares", []), "fecha": hoy().isoformat(), "motivo": res["descartar"],
                  "evidencia": res["evidencia"]})
    escribir_json(DESCARTADOS, bajas)
    guardar_sitios(doc)
    corrida = cargar_corrida()
    if corrida and not corrida.get("fin"):
        for canal in CANALES:
            if item(sitio["id"], canal) in corrida["cola"]:
                corrida["hechos"][item(sitio["id"], canal)] = "descartado"
        escribir_json(CORRIDA, corrida)
    print(f"Descartado {sitio['nombre']}: {res['descartar']}. Queda registrado en data/crawl/descartados.json.")


def cmd_guardar(args):
    if not args:
        sys.exit("Uso: crawl.py guardar <archivo.json|->")
    texto = sys.stdin.read() if args[0] == "-" else open(args[0], encoding="utf-8-sig").read()
    try:
        res = json.loads(texto)
    except ValueError as ex:
        sys.exit(f"JSON inválido: {ex}")
    doc = cargar_sitios()
    sitios = por_id(doc)
    if res.get("descartar"):
        return descartar(doc, sitios, res)
    reusados = reusar_posts(res) if res.get("canal") == "instagram" else 0
    sitio, canal, eventos, errores, avisos = validar(res, sitios)
    if reusados:
        avisos.insert(0, f"{reusados} eventos reutilizados de posts ya analizados (no hizo falta reabrirlos)")
    if errores:
        print("NO SE GUARDÓ. Corregir y volver a guardar:")
        for e in errores:
            print("  - " + e)
        sys.exit(2)
    corrida = cargar_corrida()
    if corrida and corrida.get("fin"):
        corrida = None
    estado = res["estado"]
    desde, hasta = ventana()
    en_ventana = sum(1 for e in eventos if e["fecha_inicio"] <= hasta)

    escribir_json(CAPTURAS / f"{sitio['id']}.{canal}.json", {
        "id": sitio["id"], "canal": canal, "fuente": sitio["nombre"], "tipo": sitio.get("tipo", "lugar"),
        "fecha": hoy().isoformat(), "estado": estado, "urls_visitadas": res.get("urls_visitadas") or [],
        "eventos": eventos})
    aprender(sitio, canal, res, eventos)
    if sitio.get("pendiente_alta") and (sitio.get("web") or sitio.get("instagram")) and estado != "dominio_caido":
        lugares, galerias = leer_json(DATOS / "lugares.json", []), leer_json(DATOS / "galerias.json", {"galerias": []})
        for campo in ("barrio", "direccion"):
            if res.get(campo):
                sitio[campo] = res[campo]
        dar_de_alta(sitio, lugares, galerias, sitio.get("barrio", ""), sitio.get("direccion", ""))
        escribir_json(DATOS / "lugares.json", lugares)
        escribir_json(DATOS / "galerias.json", galerias)
        sitio.pop("pendiente_alta")
        avisos.append(f"{sitio['nombre']} confirmado: agregado a lugares.json" + (" y galerias.json" if sitio["tipo"] == "galeria" else ""))
    if canal == "instagram":
        registrar_posts(sitio, res, eventos, avisos)
    nuevos = agregar_sitios_nuevos(doc, res.get("sitios_nuevos"), sitio["nombre"], corrida, avisos)

    if corrida:
        corrida["hechos"][item(sitio["id"], canal)] = estado
        corrida["eventos"] = corrida.get("eventos", 0) + len(eventos)
        # La web no alcanzó: se revisa también Instagram en esta corrida.
        ig_item = item(sitio["id"], "instagram")
        if canal == "web" and estado != "con_eventos" and sitio.get("instagram") and ig_item not in corrida["cola"]:
            corrida["cola"].append(ig_item)
            avisos.append(f"se encoló también {ig_item} porque la web quedó en {estado}")
    guardar_sitios(doc)
    if corrida:
        escribir_json(CORRIDA, corrida)

    for a in avisos:
        print("  aviso: " + a)
    print(f"Guardado {sitio['id']} [{canal}] {estado}: {len(eventos)} eventos ({en_ventana} empiezan antes del {hasta}).")
    if nuevos:
        print(f"Sitios nuevos agregados y encolados: {', '.join(nuevos)}")
    if corrida:
        print(f"Faltan {len(pendientes(corrida))} de {len(corrida['cola'])}.")


# --- estado e informe ---------------------------------------------------------------

def contar(valores):
    out = {}
    for v in valores:
        out[v] = out.get(v, 0) + 1
    return dict(sorted(out.items(), key=lambda x: -x[1]))


def cmd_estado(args):
    corrida = cargar_corrida()
    if not corrida:
        sys.exit("No hay corrida registrada.")
    pend = pendientes(corrida)
    print(f"Corrida {corrida['id']} ({'cerrada ' + corrida['fin'] if corrida.get('fin') else 'abierta'}): "
          f"{len(corrida['hechos'])} de {len(corrida['cola'])} hechos, {len(pend)} pendientes, "
          f"{corrida.get('eventos', 0)} eventos registrados.")
    print("Por estado:", contar(corrida["hechos"].values()))
    restantes, enfriado = ig_cupo(ig_estado())
    print(f"Instagram: {restantes} páginas de cupo hoy" + (f", en enfriamiento hasta {enfriado}" if enfriado else ""))
    if pend:
        print("Próximos:", ", ".join(pend[:8]))


def cmd_cerrar(args):
    corrida = cargar_corrida()
    if not corrida or corrida.get("fin"):
        sys.exit("No hay corrida abierta.")
    pend = pendientes(corrida)
    if pend and "--forzar" not in args:
        sys.exit(f"Quedan {len(pend)} sitios sin rastrear (p. ej. {', '.join(pend[:5])}). Rastrearlos, o cerrar con "
                 "--forzar si se cortó por un bloqueo o error del navegador (quedan primeros en la próxima).")
    corrida["fin"], corrida["fin_ok"] = ahora(), not pend
    escribir_json(CORRIDA, corrida)
    sitios = por_id(cargar_sitios())
    nombre = lambda i: sitios.get(i.split("|")[0], {}).get("nombre", i)
    lineas = [f"# Corrida {corrida['id']}", "",
              f"- Inicio {corrida['inicio']}, fin {corrida['fin']}. Ventana {corrida['ventana']['desde']} a {corrida['ventana']['hasta']}.",
              f"- {len(corrida['hechos'])} de {len(corrida['cola'])} sitios rastreados; {corrida.get('eventos', 0)} eventos registrados.",
              f"- Por estado: {contar(corrida['hechos'].values())}", ""]
    for titulo, filtro in (("Fallas (se reintentan la próxima corrida)", FALLAS), ("Sin eventos", NEGATIVOS)):
        items = [i for i, e in corrida["hechos"].items() if e in filtro]
        if items:
            lineas += [f"## {titulo}", ""] + [f"- {nombre(i)} ({i.split('|')[1]}): {corrida['hechos'][i]}" for i in items] + [""]
    bajas = [i for i, e in corrida["hechos"].items() if e == "descartado"]
    if bajas:
        lineas += ["## Descartados (no existen, cerraron o no están en CABA)", "",
                   ", ".join(i.split("|")[0] for i in bajas), ""]
    pospuestos = [i for i, e in corrida["hechos"].items() if e == "pospuesto"]
    if pospuestos:
        lineas += [f"## Instagram pospuesto ({corrida.get('motivo_pospuesto', '')}; van primeros la próxima corrida)", "",
                   ", ".join(nombre(i) for i in pospuestos), ""]
    if corrida.get("sitios_nuevos"):
        lineas += ["## Sitios nuevos", ""] + [f"- {nombre(i)}" for i in corrida["sitios_nuevos"]] + [""]
    if pend:
        lineas += ["## Sin rastrear (la corrida se cortó)", ""] + [f"- {nombre(i)} ({i.split('|')[1]})" for i in pend] + [""]
    INFORMES.mkdir(parents=True, exist_ok=True)
    ruta = INFORMES / f"{corrida['id']}.md"
    ruta.write_text("\n".join(lineas), encoding="utf-8")
    print("\n".join(lineas[:6]))
    print(f"Informe: {ruta.relative_to(DATOS.parent)}")


COMANDOS = {"iniciar": cmd_iniciar, "siguiente": cmd_siguiente, "ver": cmd_ver, "guardar": cmd_guardar, "ig-vistos": cmd_ig_vistos,
            "estado": cmd_estado, "cerrar": cmd_cerrar, "herramientas": cmd_herramientas}


def main():
    if len(sys.argv) < 2 or sys.argv[1] not in COMANDOS:
        sys.exit(__doc__)
    COMANDOS[sys.argv[1]](sys.argv[2:])


if __name__ == "__main__":
    main()
