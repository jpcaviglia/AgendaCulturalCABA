(() => {
  "use strict";

  const $ = (id) => document.getElementById(id);
  const FORMATO_FECHA = new Intl.DateTimeFormat("es-AR", { day: "numeric", month: "long" });

  // Estados que devuelve scripts/verificar_lugares.py, con su etiqueta visible.
  const ESTADOS = {
    "Tiene sección de agenda": { etiqueta: "Tiene sección de agenda", clase: "confirmado" },
    "Probable: menciona eventos": { etiqueta: "Probablemente lista eventos", clase: "probable" },
    "No se detectan eventos": { etiqueta: "Sin listado detectado", clase: "" },
    "Inaccesible desde la verificación": { etiqueta: "Web no accesible", clase: "" },
    "No verificable (bloquea o redirige)": { etiqueta: "No verificado", clase: "" },
    "Sin web": { etiqueta: "Sin web", clase: "" },
  };

  const normalizar = (texto) =>
    (texto || "").normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase();

  const fechaIso = (iso) => {
    const [a, m, d] = iso.split("-").map(Number);
    return FORMATO_FECHA.format(new Date(a, m - 1, d));
  };

  // Crea un elemento sin usar innerHTML: todo el texto entra con textContent.
  const crear = (tag, props = {}, hijos = []) => {
    const nodo = document.createElement(tag);
    for (const [clave, valor] of Object.entries(props)) {
      if (valor === undefined || valor === null) continue;
      if (clave === "class") nodo.className = valor;
      else if (clave === "href") nodo.href = valor;
      else nodo.setAttribute(clave, valor);
    }
    for (const hijo of hijos) {
      if (hijo) nodo.append(hijo);
    }
    return nodo;
  };

  const enlaceExterno = (href, etiqueta, clase = "enlace-accion") =>
    crear("a", { href, class: clase, target: "_blank", rel: "noopener" }, [document.createTextNode(etiqueta)]);

  const llenarSelect = (select, valores, etiquetaTodos) => {
    select.replaceChildren(crear("option", { value: "" }, [document.createTextNode(etiquetaTodos)]));
    for (const valor of valores) {
      select.append(crear("option", { value: valor }, [document.createTextNode(valor)]));
    }
  };

  const unicos = (lista, clave) =>
    [...new Set(lista.map((x) => x[clave]).filter(Boolean))].sort((a, b) => a.localeCompare(b, "es"));

  const pintarVacio = (idVacio, idLista, vacio) => {
    $(idVacio).hidden = !vacio;
    $(idLista).hidden = vacio;
  };

  // ---- Eventos ----
  let eventos = [];

  // Un lugar con sala ("Malba · Auditorio") se agrupa con el lugar ("Malba").
  const lugarBase = (lugar) => (lugar || "").split(" · ")[0].trim();

  const texto = (t) => document.createTextNode(t);

  // Cada categoría tiene su tono (grados de matiz) para el punto y el nombre; las que no figuran reciben uno fijo según su nombre.
  const TONOS = {
    "Teatro": 345, "Música": 262, "Evento": 215, "Fiestas y electrónica": 318, "Artes visuales": 32,
    "Cine": 190, "Visita guiada": 145, "Feria": 48, "Taller": 170, "Literatura y charlas": 285,
    "Festival": 335, "Danza": 72, "Infantil": 100, "Gastronomía": 12, "Deporte": 125,
  };
  const tonoCategoria = (c) => TONOS[c] ?? [...c].reduce((a, ch) => (a * 31 + ch.charCodeAt(0)) % 360, 7);

  const FORMATO_SEMANA = new Intl.DateTimeFormat("es-AR", { weekday: "long" });
  const FORMATO_SEMANA_CORTO = new Intl.DateTimeFormat("es-AR", { weekday: "short" });
  const FORMATO_MES = new Intl.DateTimeFormat("es-AR", { month: "long" });
  const fechaLocal = (iso) => {
    const [a, m, d] = iso.split("-").map(Number);
    return new Date(a, m - 1, d);
  };
  const finDe = (e) => e.fecha_fin || (e.estado === "En curso" ? "9999-12-31" : e.fecha_inicio);

  // Hora a mostrar al costado de un evento: la que publica ("hora") o la única que aparece en "horarios".
  const HORA = /\b([01]?\d|2[0-3]):([0-5]\d)\b/g;
  function horaPrincipal(e) {
    const horas = new Set([...`${e.hora || ""} | ${e.horarios || ""}`.matchAll(HORA)].map((m) => `${m[1].padStart(2, "0")}:${m[2]}`));
    const propia = [...(e.hora || "").matchAll(HORA)][0];
    if (propia) return `${propia[1].padStart(2, "0")}:${propia[2]}`;
    return horas.size === 1 ? [...horas][0] : "";
  }

  // ---- Favoritos (en este navegador) ----
  // Cada corrida rehace data/eventos.json, así que se guarda una copia del evento junto con su id (estable entre
  // corridas, ver id_estable en scripts/armar_agenda.py): si el evento sigue en la agenda se actualiza con los datos
  // nuevos; si salió, se sigue viendo con la copia guardada.
  const CLAVE_FAVORITOS = "agenda-cultural-caba:favoritos";
  let favoritos = {};
  try {
    favoritos = JSON.parse(localStorage.getItem(CLAVE_FAVORITOS) || "{}") || {};
  } catch {
    favoritos = {};
  }
  const guardarFavoritos = () => {
    try {
      localStorage.setItem(CLAVE_FAVORITOS, JSON.stringify(favoritos));
    } catch {
      // Navegador sin almacenamiento (modo privado, bloqueado): los favoritos duran solo esta visita.
    }
    const n = Object.keys(favoritos).length;
    $("cuenta-favoritos").textContent = n;
    $("cuenta-favoritos").hidden = n === 0;
  };
  const esFavorito = (e) => Boolean(e.id && favoritos[e.id]);

  function botonFavorito(e) {
    const b = boton("", "boton boton-favorito", () => {
      if (esFavorito(e)) delete favoritos[e.id];
      else favoritos[e.id] = { evento: e, guardado: new Date().toISOString() };
      guardarFavoritos();
      pintar();
      if (!$("vista-favoritos").hidden) renderFavoritos();
    });
    // La estrella la dibuja el CSS; acá solo el estado y el nombre accesible.
    const pintar = () => {
      const si = esFavorito(e);
      b.setAttribute("aria-pressed", String(si));
      b.setAttribute("aria-label", si ? "Quitar de favoritos" : "Guardar en favoritos");
      b.title = si ? "Quitar de favoritos" : "Guardar en favoritos";
    };
    pintar();
    return b;
  }

  function renderFavoritos() {
    const actuales = new Map(eventos.map((e) => [e.id, e]));
    const hoy = hoyIso();
    let cambio = false;
    const items = Object.entries(favoritos).map(([id, f]) => {
      const vivo = actuales.get(id);
      if (vivo && JSON.stringify(vivo) !== JSON.stringify(f.evento)) {
        f.evento = vivo; // datos al día
        cambio = true;
      }
      const e = vivo || f.evento;
      const termino = (e.fecha_fin || e.fecha_inicio) < hoy && e.estado !== "En curso";
      const aviso = vivo ? "" : termino ? "Terminó" : "Ya no figura en la agenda";
      return { e, aviso, termino: !vivo && termino };
    });
    if (cambio) guardarFavoritos();
    // Primero lo que sigue vigente, por fecha; al final lo que ya terminó.
    items.sort((a, b) => (a.termino - b.termino) || a.e.fecha_inicio.localeCompare(b.e.fecha_inicio));
    $("lista-favoritos").replaceChildren(...items.map(({ e, aviso }) => filaEvento(e, { aviso, conFecha: true })));
    pintarVacio("vacio-favoritos", "lista-favoritos", items.length === 0);
    const terminados = items.filter((x) => x.termino).length;
    $("borrar-terminados").hidden = terminados === 0;
    $("resumen-favoritos").textContent = items.length
      ? `${items.length} ${items.length === 1 ? "evento guardado" : "eventos guardados"} en este navegador` +
        (terminados ? ` (${terminados} ya ${terminados === 1 ? "terminó" : "terminaron"}).` : ".")
      : "Los eventos que guardes con la estrella aparecen acá. Se guardan en este navegador.";
  }

  function iniciarFavoritos() {
    guardarFavoritos();
    $("borrar-terminados").addEventListener("click", () => {
      const hoy = hoyIso();
      const vigentes = new Set(eventos.map((e) => e.id));
      for (const [id, f] of Object.entries(favoritos)) {
        const e = f.evento;
        if (!vigentes.has(id) && (e.fecha_fin || e.fecha_inicio) < hoy) delete favoritos[id];
      }
      guardarFavoritos();
      renderFavoritos();
    });
  }

  // Horas publicadas de un evento, en minutos desde la medianoche: "hora" ("20:30"), cada "HH:MM" de
  // "horarios" ("vie 20:30 | dom 19:30") y los rangos "de 11 a 19 h". Vacío si no publica ningún horario.
  const aMinutos = (h, m = 0) => (h <= 24 && m < 60 ? h * 60 + m : null);
  function horasDe(e) {
    if (e._horas) return e._horas;
    const minutos = [];
    const texto = `${e.hora || ""} | ${e.horarios || ""}`;
    for (const [, h, m] of texto.matchAll(/\b([01]?\d|2[0-3]):([0-5]\d)\b/g)) minutos.push(aMinutos(+h, +m));
    for (const [, a, b] of texto.matchAll(/\b(\d{1,2})\s*(?:a|–|-)\s*(\d{1,2})\s*(?:h|hs)\b/gi)) {
      minutos.push(aMinutos(+a), aMinutos(+b));
    }
    e._horas = minutos.filter((x) => x !== null);
    return e._horas;
  }

  // Fecha del evento en palabras. "Del 6 de noviembre al 31 de diciembre", "El 20 de octubre", "Desde el ...".
  function textoFechas(e) {
    if (e.fecha_fin && e.fecha_fin !== e.fecha_inicio) return `Del ${fechaIso(e.fecha_inicio)} al ${fechaIso(e.fecha_fin)}`;
    if (e.estado === "Próximo" || e.fecha_fin) return `El ${fechaIso(e.fecha_inicio)}`;
    return `Desde el ${fechaIso(e.fecha_inicio)}`;
  }

  // Una fila de la agenda. En la lista por día la fecha ya está en el título del día, así que solo se repite
  // cuando el evento dura varios días ("enCartel": hasta cuándo); fuera de esa lista (Favoritos) siempre va.
  function filaEvento(e, { aviso = "", conFecha = false, enCartel = false } = {}) {
    const categoria = e.categoria
      ? crear("p", { class: "categoria", style: `--h:${tonoCategoria(e.categoria)}` }, [texto(e.categoria)])
      : null;
    const etiquetas = [
      aviso ? crear("span", { class: "etiqueta aviso" }, [texto(aviso)]) : null,
      conFecha && e.estado === "En curso" ? crear("span", { class: "etiqueta" }, [texto("En cartel")]) : null,
      e.lugar_verificado ? crear("span", { class: "etiqueta confirmado" }, [texto("Lugar verificado")]) : null,
    ].filter(Boolean);

    const titulo = crear("h3", {}, [texto(e.titulo)]);
    // El nombre del lugar filtra la agenda por ese lugar.
    const nombreLugar = e.lugar
      ? boton(e.lugar, "enlace-lugar", () => {
          $("lugar-evento").value = lugarBase(e.lugar);
          abrirAvanzados(true);
          if (!$("vista-favoritos").hidden) location.hash = "#eventos"; // desde Favoritos, se va a la agenda
          renderEventos();
          $("filtros-eventos").scrollIntoView({ behavior: "smooth", block: "start" });
        })
      : crear("strong", {}, [texto("Lugar a confirmar")]);
    if (e.lugar) nombreLugar.title = `Ver solo los eventos de ${lugarBase(e.lugar)}`;
    // Hay lugares cuyo nombre es la dirección: no se repite.
    const direccion = [e.direccion && !(e.lugar || "").includes(e.direccion) ? e.direccion : "", e.barrio].filter(Boolean).join(", ");
    const lugar = crear("p", { class: "dato" }, [nombreLugar, direccion ? texto(` · ${direccion}`) : null]);

    const fechas = textoFechas(e) + (e.hora && !e.horarios ? ` · ${e.hora} h` : "");
    const multidia = Boolean(e.fecha_fin && e.fecha_fin !== e.fecha_inicio);
    let cuando = "";
    if (conFecha) cuando = textoFechas(e);
    else if (enCartel) cuando = e.fecha_fin ? `Hasta el ${fechaIso(e.fecha_fin)}` : "En cartel";
    else if (multidia) cuando = textoFechas(e);
    const horarios = [cuando, e.horarios].filter(Boolean);

    const sinPrecio = !e.precio || e.precio === "Consultar";
    const precio = crear("span", { class: `precio${e.precio === "Gratis" ? " gratis" : sinPrecio ? " sin-dato" : ""}` }, [
      texto(e.precio === "Gratis" ? "Entrada libre" : sinPrecio ? "Consultar precio" : e.precio),
    ]);

    const masInfo = e.url || e.descripcion ? boton("+ info", "boton", () => abrirPanel(e, fechas)) : null;
    const hora = horaPrincipal(e);
    return crear("li", { class: "fila" }, [
      crear("div", { class: hora ? "hora" : "hora sin" }, [texto(hora || (e.horarios ? "Ver horarios" : "Sin hora"))]),
      crear("div", { class: "cuerpo" }, [
        categoria,
        titulo,
        lugar,
        horarios.length ? crear("p", { class: "dato" }, [texto(horarios.join(" · "))]) : null,
        crear("p", { class: "dato" }, [precio]),
        etiquetas.length ? crear("div", { class: "etiquetas" }, etiquetas) : null,
      ]),
      crear("div", { class: "acciones" }, [e.id ? botonFavorito(e) : null, menuCalendario(e), masInfo]),
    ]);
  }

  const boton = (texto, clase, alHacerClic) => {
    const b = crear("button", { type: "button", class: clase }, [document.createTextNode(texto)]);
    b.addEventListener("click", alHacerClic);
    return b;
  };

  // ---- "+ info": la ficha del evento dentro de la página ----
  // Solo se usa el iframe con los sitios que lo permiten (scripts/embebibles.py los prueba al armar la agenda);
  // con los demás se ve en blanco, así que se muestra la descripción y el enlace.
  function abrirPanel(e, fechas) {
    $("panel-titulo").textContent = e.titulo;
    $("panel-datos").textContent = [e.lugar || "Lugar a confirmar", fechas].join(" · ");
    $("panel-descripcion").textContent = e.descripcion || "";
    $("panel-descripcion").hidden = !e.descripcion;
    const marco = $("panel-marco");
    marco.replaceChildren();
    if (e.url && e.embebible) {
      marco.append(crear("iframe", {
        src: e.url, title: `Sitio del evento: ${e.titulo}`, loading: "lazy", referrerpolicy: "no-referrer",
        sandbox: "allow-scripts allow-same-origin allow-forms allow-popups allow-popups-to-escape-sandbox",
      }));
    }
    marco.hidden = !(e.url && e.embebible);
    $("panel-aviso").textContent = !e.url ? ""
      : e.embebible ? "Si la página no carga, abrila en su sitio."
      : "Este sitio no se deja mostrar dentro de la agenda: abrilo en una pestaña nueva.";
    $("panel-aviso").hidden = !e.url;
    $("panel-pie").replaceChildren(
      menuCalendario(e),
      e.url ? enlaceExterno(e.url, "Abrir en el sitio ↗", "boton boton-principal") : null,
    );
    $("panel-info").classList.toggle("con-marco", Boolean(e.url && e.embebible));
    $("panel-info").showModal();
  }

  function cerrarPanel() {
    const panel = $("panel-info");
    if (panel.open) panel.close();
  }

  function iniciarPanel() {
    const panel = $("panel-info");
    $("panel-cerrar").addEventListener("click", cerrarPanel);
    // Clic en el fondo (fuera del cuadro) también cierra.
    panel.addEventListener("click", (ev) => { if (ev.target === panel) cerrarPanel(); });
    // Al cerrar se descarga la página del iframe (que no siga sonando un video, por ejemplo).
    panel.addEventListener("close", () => $("panel-marco").replaceChildren());
  }

  // ---- Agregar al calendario (Google Calendar o archivo .ics) ----
  // Horas en Buenos Aires (UTC-3 todo el año). Se agenda un solo día: el primero que no pasó (en obras con
  // varias funciones o muestras largas, todas las fechas van en la descripción). Con hora: 2 h; sin hora: día completo.
  const ZONA = "America/Argentina/Buenos_Aires";
  const compacta = (iso) => iso.replaceAll("-", "");
  const sumarDias = (iso, n) => {
    const [a, m, d] = iso.split("-").map(Number);
    const f = new Date(Date.UTC(a, m - 1, d + n));
    return f.toISOString().slice(0, 10);
  };
  const hoyIso = () => new Date(Date.now() - 3 * 3600e3).toISOString().slice(0, 10);

  function rangoCalendario(e) {
    const inicio = e.fecha_inicio > hoyIso() ? e.fecha_inicio : hoyIso();
    const primera = (e.hora || (e.horarios || "").match(/\b([01]?\d|2[0-3]):[0-5]\d\b/)?.[0] || "").padStart(5, "0");
    if (/^\d\d:\d\d$/.test(primera)) {
      const [h, m] = primera.split(":").map(Number);
      const desde = new Date(Date.UTC(...inicio.split("-").map((x, i) => (i === 1 ? x - 1 : +x)), h + 3, m));
      const hasta = new Date(desde.getTime() + 2 * 3600e3);
      const utc = (f) => f.toISOString().replace(/[-:]/g, "").replace(/\.\d{3}/, "");
      return { conHora: true, desde: utc(desde), hasta: utc(hasta) };
    }
    return { conHora: false, desde: compacta(inicio), hasta: compacta(sumarDias(inicio, 1)) };
  }

  const lugarCalendario = (e) =>
    [e.lugar, e.direccion, e.barrio, "Buenos Aires"].filter(Boolean).join(", ");
  const detalleCalendario = (e) =>
    [e.horarios, e.descripcion, e.url].filter(Boolean).join("\n\n");

  function enlaceGoogle(e) {
    const r = rangoCalendario(e);
    const p = new URLSearchParams({
      action: "TEMPLATE", text: e.titulo, dates: `${r.desde}/${r.hasta}`,
      details: detalleCalendario(e), location: lugarCalendario(e), ctz: ZONA,
    });
    return `https://calendar.google.com/calendar/render?${p}`;
  }

  // Texto de un campo .ics: se escapan \ ; , y los saltos de línea; las líneas largas se pliegan (RFC 5545).
  const escaparIcs = (t) => (t || "").replace(/\\/g, "\\\\").replace(/;/g, "\\;").replace(/,/g, "\\,").replace(/\r?\n/g, "\\n");
  const BYTES = new TextEncoder();
  const plegar = (linea) => {
    const partes = [];
    let actual = "";
    for (const c of linea) {
      if (BYTES.encode(actual + c).length > (partes.length ? 74 : 75)) { partes.push(actual); actual = ""; }
      actual += c;
    }
    return [...partes, actual].join("\r\n ");
  };

  function descargarIcs(e) {
    const r = rangoCalendario(e);
    const sello = new Date().toISOString().replace(/[-:]/g, "").replace(/\.\d{3}/, "");
    const uid = `${compacta(e.fecha_inicio)}-${normalizar(e.titulo).replace(/[^a-z0-9]+/g, "-").slice(0, 40)}@agenda-cultural-caba`;
    const fecha = (campo, valor) => (r.conHora ? `${campo}:${valor}` : `${campo};VALUE=DATE:${valor}`);
    const lineas = [
      "BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//Agenda Cultural CABA//ES", "CALSCALE:GREGORIAN",
      "BEGIN:VEVENT", `UID:${uid}`, `DTSTAMP:${sello}`, fecha("DTSTART", r.desde), fecha("DTEND", r.hasta),
      `SUMMARY:${escaparIcs(e.titulo)}`, `LOCATION:${escaparIcs(lugarCalendario(e))}`,
      `DESCRIPTION:${escaparIcs(detalleCalendario(e))}`, e.url ? `URL:${e.url}` : null,
      "END:VEVENT", "END:VCALENDAR",
    ].filter(Boolean).map(plegar);
    const archivo = new Blob([lineas.join("\r\n") + "\r\n"], { type: "text/calendar;charset=utf-8" });
    const enlace = crear("a", { href: URL.createObjectURL(archivo), download: `${uid.split("@")[0]}.ics` });
    document.body.append(enlace);
    enlace.click();
    enlace.remove();
    setTimeout(() => URL.revokeObjectURL(enlace.href), 1000);
  }

  function menuCalendario(e) {
    const ics = boton("Descargar .ics (Apple, Outlook…)", "opcion-menu", () => descargarIcs(e));
    const menu = crear("details", { class: "menu-calendario" }, [
      crear("summary", { class: "boton" }, [document.createTextNode("Agendar")]),
      crear("div", { class: "opciones-menu" }, [
        enlaceExterno(enlaceGoogle(e), "Google Calendar", "opcion-menu"),
        ics,
      ]),
    ]);
    // Elegir una opción cierra el menú.
    menu.addEventListener("click", (ev) => { if (ev.target.classList.contains("opcion-menu")) menu.open = false; });
    return menu;
  }

  // ---- Filtros y lista por día ----
  const LOTE = 80; // filas que se dibujan por vez; el resto se pide con "Mostrar más"
  let limite = LOTE;
  let grupos = [];
  let diasVentana = [];

  function leerFiltros() {
    const desde = $("fecha-desde").value;
    $("fecha-hasta").min = desde || $("fecha-hasta").dataset.min || "";
    // Un "Hasta" anterior al "Desde" no tiene sentido: se corrige solo.
    if (desde && $("fecha-hasta").value && $("fecha-hasta").value < desde) $("fecha-hasta").value = desde;
    return {
      q: normalizar($("buscar-evento").value.trim()),
      barrio: $("barrio-evento").value,
      lugar: normalizar($("lugar-evento").value.trim()),
      categoria: $("categoria-evento").value,
      gratis: $("solo-gratis").checked,
      horaDesde: $("hora-desde").value,
      desde,
      hasta: $("fecha-hasta").value,
    };
  }

  // Todo menos las fechas: con esto se cuentan las actividades de cada día de la tira.
  function pasaFiltros(e, f) {
    // Con "Desde la hora" entra si alguna de sus horas publicadas es esa o más tarde.
    if (f.horaDesde) {
      const [hh, mm] = f.horaDesde.split(":").map(Number);
      if (!horasDe(e).some((m) => m >= hh * 60 + mm)) return false;
    }
    if (f.barrio && e.barrio !== f.barrio) return false;
    // Coincidencia parcial: "proa" encuentra "Fundación PROA" y "Fundación Proa".
    if (f.lugar && !normalizar(lugarBase(e.lugar)).includes(f.lugar)) return false;
    if (f.categoria && e.categoria !== f.categoria) return false;
    if (f.gratis && e.precio !== "Gratis") return false;
    if (f.q) {
      e._texto ??= normalizar([e.titulo, e.lugar, e.barrio, e.direccion, e.descripcion].join(" "));
      if (!e._texto.includes(f.q)) return false;
    }
    return true;
  }

  // Entra si el evento está activo en algún día del rango (las muestras en curso, también).
  function pasaFechas(e, f) {
    // Sin un "Desde" elegido, lo que ya terminó no se muestra (los datos pueden tener algún día de atraso).
    if (!f.desde && finDe(e) < hoyIso()) return false;
    if (!f.desde && !f.hasta) return true;
    if (f.desde && finDe(e) < f.desde) return false;
    if (f.hasta && e.fecha_inicio > f.hasta) return false;
    return true;
  }

  // Orden dentro del día: por hora; lo de la madrugada (hasta las 6) va al final de la noche, no al principio.
  const minutosOrden = (e) => {
    const h = horaPrincipal(e);
    const m = h ? Number(h.slice(0, 2)) * 60 + Number(h.slice(3)) : horasDe(e).length ? Math.min(...horasDe(e)) : null;
    if (m === null) return 9999;
    return m < 6 * 60 ? m + 24 * 60 : m;
  };

  // Un grupo por día en que empieza algo y, al final, "En cartel": lo que empezó antes del primer día
  // que se mira (hoy, o el "Desde" elegido) y sigue.
  function agrupar(lista, f) {
    const hoy = hoyIso();
    const inicio = f.desde && f.desde > hoy ? f.desde : hoy;
    const porDia = new Map();
    const cartel = [];
    for (const e of lista) {
      if (e.fecha_inicio < inicio && finDe(e) >= inicio) cartel.push(e);
      else {
        if (!porDia.has(e.fecha_inicio)) porDia.set(e.fecha_inicio, []);
        porDia.get(e.fecha_inicio).push(e);
      }
    }
    const dias = [...porDia.keys()].sort().map((clave) => ({
      clave,
      eventos: porDia.get(clave).sort((a, b) => minutosOrden(a) - minutosOrden(b) || a.titulo.localeCompare(b.titulo, "es")),
    }));
    if (cartel.length) {
      cartel.sort((a, b) => (a.fecha_fin || "9999").localeCompare(b.fecha_fin || "9999") || a.titulo.localeCompare(b.titulo, "es"));
      dias.push({ clave: "cartel", cartel: true, eventos: cartel });
    }
    return dias;
  }

  const actividades = (n) => `${n} ${n === 1 ? "actividad" : "actividades"}`;

  function seccionDia(g, visibles) {
    const hoy = hoyIso();
    let cabecera;
    if (g.cartel) {
      cabecera = [
        crear("span", { class: "numero" }, [texto("En cartel")]),
        crear("span", { class: "mes" }, [texto("Ya empezaron y siguen")]),
      ];
    } else {
      const fecha = fechaLocal(g.clave);
      cabecera = [
        g.clave === hoy ? crear("span", { class: "hoy" }, [texto("Hoy")]) : null,
        crear("span", { class: "semana" }, [texto(FORMATO_SEMANA.format(fecha))]),
        crear("span", { class: "numero" }, [texto(String(fecha.getDate()))]),
        crear("span", { class: "mes" }, [texto(FORMATO_MES.format(fecha))]),
      ];
    }
    cabecera.push(crear("span", { class: "total" }, [texto(actividades(g.eventos.length))]));
    return crear("section", { class: g.cartel ? "dia en-cartel" : "dia" }, [
      crear("h2", { class: "dia-cab" }, cabecera),
      crear("ul", { class: "filas" }, visibles.map((e) => filaEvento(e, { enCartel: g.cartel }))),
    ]);
  }

  function dibujarAgenda() {
    let presupuesto = limite;
    let mostrados = 0;
    const secciones = [];
    for (const g of grupos) {
      if (presupuesto <= 0) break;
      const visibles = g.eventos.slice(0, presupuesto);
      presupuesto -= visibles.length;
      mostrados += visibles.length;
      secciones.push(seccionDia(g, visibles));
    }
    $("lista-eventos").replaceChildren(...secciones);
    const total = eventosFiltrados.length;
    const faltan = total - mostrados;
    $("mas-resultados").hidden = faltan <= 0;
    $("mas-resultados").textContent = `Mostrar ${Math.min(LOTE, faltan)} más (faltan ${faltan})`;
    pintarVacio("vacio-eventos", "lista-eventos", total === 0);
  }

  function abrirAvanzados(abrir) {
    $("avanzados").hidden = !abrir;
    $("mas-filtros").setAttribute("aria-expanded", String(abrir));
  }

  // La tira de días: un botón por día de la ventana, con la cantidad de actividades y una barra de volumen.
  function construirTira(desde, hasta) {
    diasVentana = [];
    for (let dia = desde; dia <= hasta; dia = sumarDias(dia, 1)) diasVentana.push(dia);
    const hoy = hoyIso();
    const todos = crear("button", { type: "button", class: "dia-boton todos", "data-dia": "" }, [
      crear("span", { class: "sem" }, [texto("todos")]),
      crear("span", { class: "num" }, [texto("los días")]),
      crear("span", { class: "cant" }),
      crear("span", { class: "barra" }),
    ]);
    const botones = diasVentana.map((dia, i) => {
      const fecha = fechaLocal(dia);
      const finde = fecha.getDay() === 0 || fecha.getDay() === 6;
      const corto = FORMATO_SEMANA_CORTO.format(fecha).replace(".", "");
      const b = crear("button", { type: "button", class: `dia-boton${finde ? " finde" : ""}`, "data-dia": dia, style: `--i:${i}` }, [
        crear("span", { class: "sem" }, [texto(dia === hoy ? "hoy" : corto)]),
        crear("span", { class: "num" }, [texto(String(fecha.getDate()))]),
        crear("span", { class: "cant" }),
        crear("span", { class: "barra" }),
      ]);
      b.dataset.nombre = `${FORMATO_SEMANA.format(fecha)} ${fecha.getDate()} de ${FORMATO_MES.format(fecha)}`;
      return b;
    });
    $("tira-dias").replaceChildren(todos, ...botones);
    $("tira-dias").addEventListener("click", (ev) => {
      const b = ev.target.closest(".dia-boton");
      if (!b) return;
      const dia = b.dataset.dia;
      const ya = dia && $("fecha-desde").value === dia && $("fecha-hasta").value === dia;
      $("fecha-desde").value = $("fecha-hasta").value = ya ? "" : dia;
      renderEventos();
    });
    $("tira-dias").classList.add("entrada");
    setTimeout(() => $("tira-dias").classList.remove("entrada"), 2000);
  }

  function actualizarTira(sinFechas, f) {
    const conteo = new Map(diasVentana.map((d) => [d, 0]));
    for (const e of sinFechas) {
      const fin = finDe(e);
      for (const d of diasVentana) if (e.fecha_inicio <= d && d <= fin) conteo.set(d, conteo.get(d) + 1);
    }
    const maximo = Math.max(1, ...conteo.values());
    const unDia = f.desde && f.desde === f.hasta ? f.desde : "";
    for (const b of $("tira-dias").querySelectorAll(".dia-boton")) {
      const dia = b.dataset.dia;
      const n = dia ? conteo.get(dia) : sinFechas.length;
      b.querySelector(".cant").textContent = String(n);
      b.style.setProperty("--p", dia ? String(n / maximo) : "1");
      b.setAttribute("aria-pressed", String(dia ? dia === unDia : !f.desde && !f.hasta));
      b.setAttribute("aria-label", dia ? `${b.dataset.nombre}: ${actividades(n)}` : `Todos los días: ${actividades(n)}`);
    }
  }

  // Lo que depende de los filtros: fichas activas, cuenta de "Más filtros" y botón para quitarlos.
  function actualizarControles(f) {
    $("solo-noche").checked = f.horaDesde === "20:00";
    for (const b of $("categorias").querySelectorAll(".ficha")) {
      b.setAttribute("aria-pressed", String((b.dataset.categoria || "") === f.categoria));
    }
    const unDia = f.desde && f.desde === f.hasta && diasVentana.includes(f.desde);
    const avanzados = [f.barrio, f.lugar, !unDia && (f.desde || f.hasta), f.horaDesde && f.horaDesde !== "20:00"].filter(Boolean).length;
    $("cuenta-avanzados").textContent = avanzados;
    $("cuenta-avanzados").hidden = avanzados === 0;
    const hay = Boolean(f.q || f.barrio || f.lugar || f.categoria || f.gratis || f.horaDesde || f.desde || f.hasta);
    $("limpiar-filtros").hidden = !hay;
    const total = eventosFiltrados.length;
    $("resumen-resultados").textContent = hay
      ? `${total} de ${actividades(eventos.length)} con estos filtros.`
      : `${actividades(total)}.`;
  }

  function limpiarFiltros() {
    for (const id of ["buscar-evento", "lugar-evento", "barrio-evento", "categoria-evento", "fecha-desde", "fecha-hasta", "hora-desde"]) {
      $(id).value = "";
    }
    $("solo-gratis").checked = false;
    renderEventos();
  }

  function renderEventos() {
    const f = leerFiltros();
    const sinHorario = f.horaDesde ? eventos.filter((e) => !horasDe(e).length).length : 0;
    $("nota-hora").hidden = !sinHorario;
    $("nota-hora").textContent = sinHorario
      ? `${sinHorario} eventos no publican horario y no se muestran con este filtro.`
      : "";

    const sinFechas = eventos.filter((e) => pasaFiltros(e, f));
    eventosFiltrados = sinFechas.filter((e) => pasaFechas(e, f));
    grupos = agrupar(eventosFiltrados, f);
    limite = LOTE;
    dibujarAgenda();
    actualizarTira(sinFechas, f);
    actualizarControles(f);
    renderMapa();
  }

  // ---- Mapa ----
  let eventosFiltrados = [];
  let mapa = null;
  let capaMarcadores = null;

  function renderMapa() {
    if (!mapa || typeof L === "undefined") return;
    capaMarcadores.clearLayers();
    const porPunto = new Map();
    for (const e of eventosFiltrados) {
      if (e.lat === "" || e.lat === undefined || e.lng === "" || e.lng === undefined) continue;
      const clave = `${e.lat},${e.lng}`;
      if (!porPunto.has(clave)) porPunto.set(clave, []);
      porPunto.get(clave).push(e);
    }
    for (const evs of porPunto.values()) {
      const popup = crear("div", { class: "popup-mapa" }, [
        crear("strong", {}, [document.createTextNode(evs[0].lugar || "Lugar a confirmar")]),
        crear("ul", {}, evs.slice(0, 8).map((e) =>
          crear("li", {}, [
            e.url ? enlaceExterno(e.url, e.titulo, "") : document.createTextNode(e.titulo),
            document.createTextNode(` · ${fechaIso(e.fecha_inicio)}`),
          ]))),
        evs.length > 8 ? crear("em", {}, [document.createTextNode(`y ${evs.length - 8} más`)]) : null,
      ]);
      L.marker([evs[0].lat, evs[0].lng]).bindPopup(popup).addTo(capaMarcadores);
    }
    const ubicados = [...porPunto.values()].reduce((n, v) => n + v.length, 0);
    $("resumen-mapa").textContent =
      `${porPunto.size} lugares con eventos activos (${ubicados} de ${eventosFiltrados.length} eventos ubicados). Son los mismos filtros que en la pestaña Eventos.`;
  }

  function iniciarMapa() {
    if (mapa || typeof L === "undefined") return;
    mapa = L.map("mapa").setView([-34.6037, -58.4], 12);
    L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
      maxZoom: 19,
      attribution: "© colaboradores de OpenStreetMap",
    }).addTo(mapa);
    capaMarcadores = L.layerGroup().addTo(mapa);
    renderMapa();
  }

  function iniciarEventos(datos) {
    eventos = datos.eventos || [];
    llenarSelect($("barrio-evento"), unicos(eventos, "barrio"), "Todos");
    // Sugerencias del campo Lugar: un nombre por lugar (sin la sala; entre "Fundación PROA" y
    // "Fundación Proa" queda la grafía más usada), con cuántos eventos tiene.
    const porLugar = new Map();
    for (const e of eventos) {
      const nombre = lugarBase(e.lugar);
      if (!nombre) continue;
      const clave = normalizar(nombre);
      if (!porLugar.has(clave)) porLugar.set(clave, { total: 0, grafias: new Map() });
      const l = porLugar.get(clave);
      l.total += 1;
      l.grafias.set(nombre, (l.grafias.get(nombre) || 0) + 1);
    }
    const opciones = [...porLugar.values()]
      .map((l) => ({ nombre: [...l.grafias].sort((a, b) => b[1] - a[1])[0][0], total: l.total }))
      .sort((a, b) => a.nombre.localeCompare(b.nombre, "es"));
    $("opciones-lugar-evento").replaceChildren(...opciones.map((o) =>
      crear("option", { value: o.nombre, label: `${o.total} ${o.total === 1 ? "evento" : "eventos"}` })));
    // Horas cada media hora, de 00:00 a 23:30 (el valor es "HH:MM").
    llenarSelect($("hora-desde"),
      Array.from({ length: 48 }, (_, i) => `${String(i >> 1).padStart(2, "0")}:${i % 2 ? "30" : "00"}`),
      "Cualquiera");

    // Categorías como fichas, de la más a la menos frecuente.
    const porCategoria = new Map();
    for (const e of eventos) if (e.categoria) porCategoria.set(e.categoria, (porCategoria.get(e.categoria) || 0) + 1);
    const ficha = (categoria, nombre, cantidad) => {
      const b = crear("button", { type: "button", class: "ficha ficha-categoria", "aria-pressed": "false", "data-categoria": categoria }, [
        texto(nombre),
        cantidad ? crear("span", { class: "n" }, [texto(String(cantidad))]) : null,
      ]);
      if (categoria) b.style.setProperty("--h", String(tonoCategoria(categoria)));
      else b.classList.add("todas");
      b.addEventListener("click", () => {
        $("categoria-evento").value = categoria && $("categoria-evento").value === categoria ? "" : categoria;
        renderEventos();
      });
      return b;
    };
    $("categorias").replaceChildren(
      ficha("", "Todas", 0),
      ...[...porCategoria].sort((a, b) => b[1] - a[1]).map(([nombre, n]) => ficha(nombre, nombre, n)),
    );

    const { desde, hasta } = datos.ventana;
    $("resumen-ventana").textContent =
      `${eventos.length} actividades entre el ${fechaIso(desde)} y el ${fechaIso(hasta)}.` +
      (datos.generado ? ` Última actualización: ${fechaIso(datos.generado)}.` : "");

    // El calendario solo ofrece los días de la ventana publicada.
    for (const id of ["fecha-desde", "fecha-hasta"]) {
      $(id).min = desde;
      $(id).max = hasta;
    }
    $("fecha-hasta").dataset.min = desde;
    construirTira(desde, hasta);

    for (const id of ["buscar-evento", "lugar-evento", "barrio-evento", "solo-gratis", "fecha-desde", "fecha-hasta", "hora-desde"]) {
      $(id).addEventListener(["buscar-evento", "lugar-evento"].includes(id) ? "input" : "change", renderEventos);
    }
    // "Desde las 20 h" es un atajo del campo "Desde la hora".
    $("solo-noche").addEventListener("change", () => {
      $("hora-desde").value = $("solo-noche").checked ? "20:00" : "";
      renderEventos();
    });
    $("mas-filtros").addEventListener("click", () => abrirAvanzados($("avanzados").hidden));
    $("limpiar-filtros").addEventListener("click", limpiarFiltros);
    $("vacio-limpiar").addEventListener("click", limpiarFiltros);
    $("mas-resultados").addEventListener("click", () => {
      limite += LOTE;
      dibujarAgenda();
    });
    renderEventos();
  }

  // ---- Lugares ----
  let lugares = [];

  function tarjetaLugar(l) {
    const estado = ESTADOS[l.estado] || { etiqueta: l.estado, clase: "" };
    const etiqueta = crear("span", { class: `etiqueta ${estado.clase}` }, [document.createTextNode(estado.etiqueta)]);

    const enlaces = [];
    if (l.web) enlaces.push(enlaceExterno(l.web, l.canal === "Sitio web" ? "Ver programación →" : "Sitio web →"));
    if (l.instagram) {
      const usuario = l.instagram.replace(/^@/, "");
      enlaces.push(enlaceExterno(`https://www.instagram.com/${usuario}/`, `Instagram ${l.instagram}`));
    }

    return crear("li", { class: "tarjeta" }, [
      crear("div", { class: "etiquetas" }, [etiqueta]),
      crear("h2", {}, [document.createTextNode(l.nombre)]),
      crear("p", { class: "dato" }, [document.createTextNode([l.domicilio, l.barrio].filter(Boolean).join(" · "))]),
      crear("div", { class: "pie-tarjeta" }, enlaces),
    ]);
  }

  function renderLugares() {
    const q = normalizar($("buscar-lugar").value.trim());
    const barrio = $("barrio-lugar").value;
    const estado = $("estado-lugar").value;

    const filtrados = lugares.filter((l) => {
      if (barrio && l.barrio !== barrio) return false;
      if (estado && l.estado !== estado) return false;
      if (q && !normalizar([l.nombre, l.domicilio, l.barrio].join(" ")).includes(q)) return false;
      return true;
    });

    const conEventos = lugares.filter((l) => l.estado === "Tiene sección de agenda").length;
    $("resumen-lugares").textContent =
      `${filtrados.length} de ${lugares.length} lugares. ${conEventos} tienen sección de agenda.`;
    $("lista-lugares").replaceChildren(...filtrados.map(tarjetaLugar));
    pintarVacio("vacio-lugares", "lista-lugares", filtrados.length === 0);
  }

  function iniciarLugares(datos) {
    lugares = datos;
    llenarSelect($("barrio-lugar"), unicos(lugares, "barrio"), "Todos");

    const estados = [...new Set(lugares.map((l) => l.estado))];
    $("estado-lugar").replaceChildren(crear("option", { value: "" }, [document.createTextNode("Todos")]));
    for (const clave of estados) {
      const etiqueta = (ESTADOS[clave] || { etiqueta: clave }).etiqueta;
      $("estado-lugar").append(crear("option", { value: clave }, [document.createTextNode(etiqueta)]));
    }

    for (const id of ["buscar-lugar", "barrio-lugar", "estado-lugar"]) {
      $(id).addEventListener(id === "buscar-lugar" ? "input" : "change", renderLugares);
    }
    renderLugares();
  }

  // ---- Navegación entre vistas ----
  function mostrarVista() {
    const vista = ["#lugares", "#mapa", "#favoritos"].includes(location.hash) ? location.hash.slice(1) : "eventos";
    $("vista-eventos").hidden = vista !== "eventos";
    $("vista-lugares").hidden = vista !== "lugares";
    $("vista-mapa").hidden = vista !== "mapa";
    $("vista-favoritos").hidden = vista !== "favoritos";
    if (vista === "favoritos" && eventos.length) renderFavoritos();
    // Los filtros de eventos son los mismos en Eventos y en Mapa: se mueve el mismo formulario.
    if (vista === "eventos" || vista === "mapa") {
      $(`vista-${vista}`).querySelector(".cabecera-vista").after($("filtros-eventos"));
      // La lista y el mapa se vuelven a dibujar con lo que dicen los campos, por si quedaron desfasados.
      if (eventos.length) renderEventos();
    }
    for (const enlace of document.querySelectorAll(".pestanas a")) {
      enlace.classList.toggle("activa", enlace.dataset.vista === vista);
    }
    if (vista === "mapa") {
      iniciarMapa();
      if (mapa) mapa.invalidateSize();
    }
    window.scrollTo({ top: 0 });
  }

  async function cargar(ruta) {
    const respuesta = await fetch(ruta, { cache: "no-store" });
    if (!respuesta.ok) throw new Error(`${ruta}: ${respuesta.status}`);
    return respuesta.json();
  }

  async function iniciar() {
    window.addEventListener("hashchange", mostrarVista);
    iniciarPanel();
    iniciarFavoritos();
    // Un menú "Agendar" abierto se cierra al tocar en otro lado.
    document.addEventListener("click", (ev) => {
      for (const m of document.querySelectorAll(".menu-calendario[open]")) if (!m.contains(ev.target)) m.open = false;
    });
    // Al volver con "atrás" o recargar, el navegador puede devolverle valores a los campos sin avisarle a la página.
    window.addEventListener("pageshow", () => { if (eventos.length) renderEventos(); });
    mostrarVista();
    try {
      const [eventosDatos, lugaresDatos] = await Promise.all([
        cargar("data/eventos.json"),
        cargar("data/lugares.json"),
      ]);
      iniciarEventos(eventosDatos);
      iniciarLugares(lugaresDatos);
      if (location.hash === "#favoritos") renderFavoritos();
    } catch (error) {
      $("resumen-ventana").textContent = "No se pudo cargar la agenda. Intentá de nuevo más tarde.";
      console.error(error);
    }
  }

  iniciar();
})();
