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

  function tarjetaEvento(e) {
    const etiquetas = crear("div", { class: "etiquetas" }, [
      e.categoria ? crear("span", { class: "etiqueta categoria" }, [document.createTextNode(e.categoria)]) : null,
      e.precio === "Gratis" ? crear("span", { class: "etiqueta gratis" }, [document.createTextNode("Gratis")]) : null,
      e.estado === "En curso" ? crear("span", { class: "etiqueta" }, [document.createTextNode("En cartel")]) : null,
      e.lugar_verificado ? crear("span", { class: "etiqueta confirmado" }, [document.createTextNode("Lugar verificado")]) : null,
    ]);

    const titulo = crear("h2", {}, [document.createTextNode(e.titulo)]);
    const lugar = crear("p", { class: "dato" }, [
      crear("strong", {}, [document.createTextNode(e.lugar || "Lugar a confirmar")]),
    ]);
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
    const pie = crear("div", { class: "pie-tarjeta" }, [
      crear("span", { class: "dato" }, [document.createTextNode(textoPrecio)]),
      e.url ? enlaceExterno(e.url, "Ver en el sitio →") : null,
    ]);

    const detalle = e.descripcion
      ? crear("details", { class: "detalle" }, [
          crear("summary", {}, [document.createTextNode("Más información")]),
          crear("p", {}, [document.createTextNode(e.descripcion)]),
        ])
      : null;

    return crear("li", { class: "tarjeta" }, [etiquetas, titulo, lugar, ubicacion, cuando, horario, detalle, pie]);
  }

  function renderEventos() {
    const q = normalizar($("buscar-evento").value.trim());
    const barrio = $("barrio-evento").value;
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

    for (const id of ["buscar-evento", "barrio-evento", "categoria-evento", "solo-gratis", "fecha-desde", "fecha-hasta", "hora-desde"]) {
      $(id).addEventListener(id === "buscar-evento" ? "input" : "change", renderEventos);
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
    const vista = ["#lugares", "#mapa"].includes(location.hash) ? location.hash.slice(1) : "eventos";
    $("vista-eventos").hidden = vista !== "eventos";
    $("vista-lugares").hidden = vista !== "lugares";
    $("vista-mapa").hidden = vista !== "mapa";
    // Los filtros de eventos son los mismos en Eventos y en Mapa: se mueve el mismo formulario.
    if (vista !== "lugares") {
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
    } catch (error) {
      $("resumen-ventana").textContent = "No se pudo cargar la agenda. Intentá de nuevo más tarde.";
      console.error(error);
    }
  }

  iniciar();
})();
