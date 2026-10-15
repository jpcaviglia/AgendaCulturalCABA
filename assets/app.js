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
    const pintar = () => {
      const si = esFavorito(e);
      b.textContent = si ? "★ Guardado" : "☆ Guardar";
      b.setAttribute("aria-pressed", String(si));
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
    $("lista-favoritos").replaceChildren(...items.map(({ e, aviso }) => tarjetaEvento(e, aviso)));
    pintarVacio("vacio-favoritos", "lista-favoritos", items.length === 0);
    const terminados = items.filter((x) => x.termino).length;
    $("borrar-terminados").hidden = terminados === 0;
    $("resumen-favoritos").textContent = items.length
      ? `${items.length} ${items.length === 1 ? "evento guardado" : "eventos guardados"} en este navegador` +
        (terminados ? ` (${terminados} ya ${terminados === 1 ? "terminó" : "terminaron"}).` : ".")
      : "Los eventos que guardes con ☆ aparecen acá. Se guardan en este navegador.";
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

  function tarjetaEvento(e, aviso = "") {
    const etiquetas = crear("div", { class: "etiquetas" }, [
      aviso ? crear("span", { class: "etiqueta aviso" }, [document.createTextNode(aviso)]) : null,
      e.categoria ? crear("span", { class: "etiqueta categoria" }, [document.createTextNode(e.categoria)]) : null,
      e.precio === "Gratis" ? crear("span", { class: "etiqueta gratis" }, [document.createTextNode("Gratis")]) : null,
      e.estado === "En curso" ? crear("span", { class: "etiqueta" }, [document.createTextNode("En cartel")]) : null,
      e.lugar_verificado ? crear("span", { class: "etiqueta confirmado" }, [document.createTextNode("Lugar verificado")]) : null,
    ]);

    const titulo = crear("h2", {}, [document.createTextNode(e.titulo)]);
    // El nombre del lugar filtra la agenda por ese lugar.
    const nombreLugar = e.lugar
      ? boton(e.lugar, "enlace-lugar", () => {
          $("lugar-evento").value = lugarBase(e.lugar);
          if (!$("vista-favoritos").hidden) location.hash = "#eventos"; // desde Favoritos, se va a la agenda
          renderEventos();
          $("filtros-eventos").scrollIntoView({ behavior: "smooth", block: "start" });
        })
      : crear("strong", {}, [document.createTextNode("Lugar a confirmar")]);
    if (e.lugar) nombreLugar.title = `Ver solo los eventos de ${lugarBase(e.lugar)}`;
    const lugar = crear("p", { class: "dato" }, [nombreLugar]);
    const direccion = [e.direccion, e.barrio].filter(Boolean).join(" · ");
    const ubicacion = direccion ? crear("p", { class: "dato" }, [document.createTextNode(direccion)]) : null;
    const horario = e.horarios ? crear("p", { class: "dato" }, [document.createTextNode(e.horarios)]) : null;
    let fechas;
    if (e.fecha_fin && e.fecha_fin !== e.fecha_inicio) {
      fechas = `Del ${fechaIso(e.fecha_inicio)} al ${fechaIso(e.fecha_fin)}`;
    } else if (e.estado === "Próximo" || e.fecha_fin) {
      fechas = `El ${fechaIso(e.fecha_inicio)}`;
    } else {
      fechas = `Desde el ${fechaIso(e.fecha_inicio)}`;
    }
    if (e.hora && !e.horarios) fechas += ` · ${e.hora} h`;
    const cuando = crear("p", { class: "dato" }, [document.createTextNode(fechas)]);

    const sinPrecio = !e.precio || e.precio === "Consultar";
    const textoPrecio = e.precio === "Gratis" ? "Entrada libre" : sinPrecio ? "Consultar precio" : e.precio;
    const masInfo = e.url || e.descripcion ? boton("+ info", "boton", () => abrirPanel(e, fechas)) : null;
    const pie = crear("div", { class: "pie-tarjeta" }, [
      crear("span", { class: "dato" }, [document.createTextNode(textoPrecio)]),
      crear("div", { class: "acciones" }, [e.id ? botonFavorito(e) : null, menuCalendario(e), masInfo]),
    ]);

    return crear("li", { class: "tarjeta" }, [etiquetas, titulo, lugar, ubicacion, cuando, horario, pie]);
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

  function renderEventos() {
    const q = normalizar($("buscar-evento").value.trim());
    const barrio = $("barrio-evento").value;
    const lugarBuscado = normalizar($("lugar-evento").value.trim());
    const categoria = $("categoria-evento").value;
    const soloGratis = $("solo-gratis").checked;
    const desde = $("fecha-desde").value;
    $("fecha-hasta").min = desde || $("fecha-hasta").dataset.min || "";
    // Un "Hasta" anterior al "Desde" no tiene sentido: se corrige solo.
    if (desde && $("fecha-hasta").value && $("fecha-hasta").value < desde) $("fecha-hasta").value = desde;
    const hasta = $("fecha-hasta").value;
    const horaDesde = $("hora-desde").value;
    const [hh, mm] = horaDesde ? horaDesde.split(":").map(Number) : [0, 0];
    const minDesde = hh * 60 + mm;
    const sinHorario = horaDesde ? eventos.filter((e) => !horasDe(e).length).length : 0;
    $("nota-hora").hidden = !sinHorario;
    $("nota-hora").textContent = sinHorario
      ? `${sinHorario} eventos no publican horario y no se muestran con este filtro.`
      : "";

    const filtrados = eventos.filter((e) => {
      // Con "Desde la hora" entra si alguna de sus horas publicadas es esa o más tarde.
      if (horaDesde && !horasDe(e).some((m) => m >= minDesde)) return false;
      // Entra si el evento está activo en algún día del rango (las muestras en curso, también).
      if (desde || hasta) {
        const fin = e.fecha_fin || (e.estado === "En curso" ? "9999-12-31" : e.fecha_inicio);
        if (desde && fin < desde) return false;
        if (hasta && e.fecha_inicio > hasta) return false;
      }
      if (barrio && e.barrio !== barrio) return false;
      // Coincidencia parcial: "proa" encuentra "Fundación PROA" y "Fundación Proa".
      if (lugarBuscado && !normalizar(lugarBase(e.lugar)).includes(lugarBuscado)) return false;
      if (categoria && e.categoria !== categoria) return false;
      if (soloGratis && e.precio !== "Gratis") return false;
      if (q) {
        const todo = normalizar([e.titulo, e.lugar, e.barrio, e.direccion, e.descripcion].join(" "));
        if (!todo.includes(q)) return false;
      }
      return true;
    });

    $("lista-eventos").replaceChildren(...filtrados.map(tarjetaEvento));
    pintarVacio("vacio-eventos", "lista-eventos", filtrados.length === 0);
    eventosFiltrados = filtrados;
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
    llenarSelect($("categoria-evento"), unicos(eventos, "categoria"), "Todas");
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

    const { desde, hasta } = datos.ventana;
    $("resumen-ventana").textContent =
      `${eventos.length} actividades entre el ${fechaIso(desde)} y el ${fechaIso(hasta)}.`;
    $("actualizado").textContent = datos.generado
      ? `Última actualización: ${fechaIso(datos.generado)}.`
      : "";

    // El calendario solo ofrece los días de la ventana publicada.
    for (const id of ["fecha-desde", "fecha-hasta"]) {
      $(id).min = desde;
      $(id).max = hasta;
    }
    $("fecha-hasta").dataset.min = desde;

    for (const id of ["buscar-evento", "lugar-evento", "barrio-evento", "categoria-evento", "solo-gratis", "fecha-desde", "fecha-hasta", "hora-desde"]) {
      $(id).addEventListener(["buscar-evento", "lugar-evento"].includes(id) ? "input" : "change", renderEventos);
    }
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
