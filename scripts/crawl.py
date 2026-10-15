"""Registro del rastreo con navegador (skill .claude/skills/actualizar-agenda). No usa la red.

El navegador junta los datos; este script solo lleva la cola de la corrida, valida lo que se encontró,
guarda la captura de cada sitio y anota lo aprendido sobre cada sitio para la próxima corrida.

Uso:
    python scripts/crawl.py iniciar [--nueva]     # arma la cola con TODOS los sitios (o retoma la corrida abierta)
    python scripts/crawl.py siguiente [n]         # muestra los próximos n sitios pendientes con sus notas
    python scripts/crawl.py ver <id>              # muestra todo lo que se sabe de un sitio
    python scripts/crawl.py guardar <archivo.json|->   # registra el resultado de un sitio (ver formato en la skill)
    python scripts/crawl.py estado                # avance de la corrida
    python scripts/crawl.py cerrar [--forzar]     # cierra la corrida y escribe el informe

Archivos:
    data/crawl/sitios.json          qué rastrear y cómo se comporta cada sitio (se enriquece en cada corrida)
    data/crawl/capturas/<id>.<canal>.json   lo encontrado en la última visita a cada sitio
    data/crawl/corrida.json         cola y avance de la corrida en curso
    data/crawl/informes/<fecha>.md  informe de cada corrida
"""
import json
import re
import sys
from datetime import date, datetime

from comun import (CAPTURAS, CORRIDA, DATOS, INFORMES, SITIOS, ZONA_BA, dominio, escribir_json, hoy, leer_json,
                   sin_tildes, slug, ventana)

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
# Estados que afirman que no hay nada: exigen haber recorrido todo.
NEGATIVOS = ("sin_eventos", "sin_agenda", "no_cultural")
# Estados de falla: exigen evidencia y vuelven a probarse en la próxima corrida.
FALLAS = ("no_carga", "dominio_caido", "bloqueado")
FASES = {"agregador": 0, "descubrimiento": 1, "galeria": 2, "lugar": 3}
CAMPOS_EVENTO = ("titulo", "fecha_inicio", "fecha_fin", "hora", "horarios", "lugar", "barrio", "direccion",
                 "categoria", "precio", "url", "descripcion", "vigente_sin_fin")
FECHA = re.compile(r"^\d{4}-\d{2}-\d{2}$")
HORA = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")
GRATIS = re.compile(r"\b(gratis|gratuit[oa]|entrada libre|libre y gratuit[oa]|sin cargo|free)\b", re.I)
MAX_NOTAS, MAX_HISTORIAL, MAX_ENTRADAS = 12, 10, 8


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
        fase = FASES.get(s.get("tipo"), 3) if canal == "web" else 9
        return (fase, item(s["id"], canal) not in pendientes_previos, not tuvo_eventos(s), sin_tildes(s["nombre"]))

    elegidos = []
    for s in doc["sitios"]:
        if s.get("rastrear") is False:
            continue
        if s.get("web"):
            elegidos.append((orden(s, "web"), item(s["id"], "web")))
        elif s.get("instagram"):
            elegidos.append((orden(s, "instagram"), item(s["id"], "instagram")))
    return [i for _, i in sorted(elegidos)]


def cargar_corrida():
    return leer_json(CORRIDA)


def pendientes(corrida):
    return [i for i in corrida["cola"] if i not in corrida["hechos"]]


def cmd_iniciar(args):
    doc = cargar_sitios()
    previa = cargar_corrida()
    if previa and not previa.get("fin") and "--nueva" not in args:
        inicio = date.fromisoformat(previa["id"][:10])
        if (hoy() - inicio).days <= 3:
            print(f"Se retoma la corrida {previa['id']} (iniciada {previa['inicio']}).")
            return cmd_estado([])
        print(f"La corrida {previa['id']} quedó abierta hace más de 3 días: se empieza una nueva.")
        previa["fin"], previa["fin_ok"] = ahora(), False
    desde, hasta = ventana()
    cola = armar_cola(doc, previa)
    corrida = {"id": hoy().isoformat(), "inicio": ahora(), "fin": None, "ventana": {"desde": desde, "hasta": hasta},
               "cola": cola, "hechos": {}, "sitios_nuevos": [], "eventos": 0}
    escribir_json(CORRIDA, corrida)
    omitidos = [s["nombre"] for s in doc["sitios"] if s.get("rastrear") is False]
    sin_canal = [s["nombre"] for s in doc["sitios"] if s.get("rastrear") is not False and not s.get("web") and not s.get("instagram")]
    print(f"Corrida {corrida['id']}: {len(cola)} sitios en cola. Ventana {desde} a {hasta}.")
    if omitidos:
        print(f"No se rastrean por decisión ({len(omitidos)}): {', '.join(omitidos)}")
    if sin_canal:
        print(f"Sin web ni Instagram ({len(sin_canal)}): buscar su web o Instagram si hay tiempo: {', '.join(sin_canal[:20])}")


def resumen_sitio(s, canal=None):
    claves = ("id", "nombre", "tipo", "lugares", "web", "instagram", "enlace_bio", "entradas", "comportamiento",
              "enlaces_pendientes", "ultimo")
    out = {k: s[k] for k in claves if s.get(k)}
    if canal:
        out = {"item": item(s["id"], canal), "canal": canal, **out}
    out["notas"] = s.get("notas", [])[-6:]
    out["historial"] = s.get("historial", [])[-4:]
    return out


def cmd_siguiente(args):
    n = int(args[0]) if args else 1
    corrida = cargar_corrida()
    if not corrida or corrida.get("fin"):
        sys.exit("No hay corrida abierta: correr primero `python scripts/crawl.py iniciar`.")
    sitios = por_id(cargar_sitios())
    pend = pendientes(corrida)
    hechos = len(corrida["hechos"])
    print(f"Avance: {hechos} de {len(corrida['cola'])} hechos. Ventana {corrida['ventana']['desde']} a {corrida['ventana']['hasta']}.")
    if not pend:
        print("Cola vacía: correr armar_agenda.py y `crawl.py cerrar`.")
        return
    salida = []
    for i in pend[:n]:
        sid, canal = i.split("|")
        if sid in sitios:
            salida.append(resumen_sitio(sitios[sid], canal))
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
    if not e["lugar"]:
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
            sin_ver = [c for c in candidatos if isinstance(c, dict) and not c.get("visitado") and not c.get("descartado")]
            if sin_ver:
                errores.append("hay enlaces candidatos sin abrir. Abrirlos o poner 'descartado': '<motivo concreto>':\n    "
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
    if res.get("nota"):
        sitio.setdefault("notas", []).append(f"{fecha} [{canal}] {res['nota'].strip()}")
    del sitio.setdefault("notas", [])[:-MAX_NOTAS]
    # Enlaces vistos pero no recorridos: la próxima corrida empieza por ellos.
    visitadas = set(res.get("urls_visitadas") or [])
    pend = [p for p in sitio.get("enlaces_pendientes", []) if p.get("url") not in visitadas]
    for c in res.get("enlaces_candidatos") or []:
        if isinstance(c, dict) and c.get("url") and not c.get("visitado") and c.get("descartado") is None:
            if c["url"] not in {p["url"] for p in pend}:
                pend.append({"url": c["url"], "texto": c.get("texto", ""), "desde": fecha})
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
        if tipo == "galeria":
            galerias["galerias"].append({"nombre": n["nombre"], "web": n.get("web", ""), "tipo": "Galería o museo",
                                         "verificada": bool(n.get("web"))})
        if tipo in ("lugar", "galeria") and not any(sin_tildes(l["nombre"]) == sin_tildes(n["nombre"]) for l in lugares):
            lugares.append({"nombre": n["nombre"], "barrio": n.get("barrio", ""), "domicilio": n.get("direccion", ""),
                            "web": n.get("web", ""), "dominio": dominio(n.get("web", "")),
                            "tipo_web": "Sitio propio" if n.get("web") else "", "instagram": ig,
                            "estado": "Probable: menciona eventos" if n.get("web") else "Sin web",
                            "evidencia": s["origen"],
                            "canal": "Sitio web" if n.get("web") else "Instagram (sin listado confirmado en la web)"})
        if corrida and not corrida.get("fin"):
            corrida["cola"].append(item(sid, "web" if s["web"] else "instagram"))
            corrida["sitios_nuevos"].append(sid)
        agregados.append(sid)
    if agregados:
        escribir_json(DATOS / "lugares.json", lugares)
        escribir_json(DATOS / "galerias.json", galerias)
    return agregados


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
    sitio, canal, eventos, errores, avisos = validar(res, sitios)
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
    if corrida.get("sitios_nuevos"):
        lineas += ["## Sitios nuevos", ""] + [f"- {nombre(i)}" for i in corrida["sitios_nuevos"]] + [""]
    if pend:
        lineas += ["## Sin rastrear (la corrida se cortó)", ""] + [f"- {nombre(i)} ({i.split('|')[1]})" for i in pend] + [""]
    INFORMES.mkdir(parents=True, exist_ok=True)
    ruta = INFORMES / f"{corrida['id']}.md"
    ruta.write_text("\n".join(lineas), encoding="utf-8")
    print("\n".join(lineas[:6]))
    print(f"Informe: {ruta.relative_to(DATOS.parent)}")


COMANDOS = {"iniciar": cmd_iniciar, "siguiente": cmd_siguiente, "ver": cmd_ver, "guardar": cmd_guardar,
            "estado": cmd_estado, "cerrar": cmd_cerrar}


def main():
    if len(sys.argv) < 2 or sys.argv[1] not in COMANDOS:
        sys.exit(__doc__)
    COMANDOS[sys.argv[1]](sys.argv[2:])


if __name__ == "__main__":
    main()
