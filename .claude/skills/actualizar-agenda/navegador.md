# Herramientas para el navegador

Las herramientas están en [navegador.js](navegador.js) y se cargan en la pestaña con **una sola línea**
(en Claude in Chrome, con `javascript_tool`). No hace falta leer ni pegar el código.

`python scripts/crawl.py iniciar` imprime la línea, con la URL de jsDelivr fijada al último commit de
`navegador.js` (`crawl.py herramientas` la vuelve a mostrar, y `siguiente` repite la URL):

```js
(async () => { window.__agt || await import("https://cdn.jsdelivr.net/gh/<repo>@<commit>/.claude/skills/actualizar-agenda/navegador.js"); return window.__agt.preparar(); })()
```

Para otra herramienta se cambia solo el final: `window.__agt.esperar()`, `window.__agt.bloques()`, etc.
Cada vez que se navega a otra página hay que usar la línea completa (el `window.__agt ||` evita volver a
descargar el archivo mientras se siga en la misma página). Todas devuelven un texto JSON y además lo
dejan en `window.__ag`: si la herramienta devuelve una promesa vacía o `{}`, esperá unos segundos y
ejecutá `JSON.stringify(window.__ag)`.

**Si el import falla** ("Failed to fetch dynamically imported module" o un error de Content Security
Policy): el sitio bloquea scripts de otros dominios. Leé `navegador.js`, pegalo entero seguido de la
llamada (`window.__agt.preparar()`) y anotá `"comportamiento": {"herramientas": "pegar inline (CSP)"}`
para que la próxima corrida lo pegue directo. Si `crawl.py` dice que `navegador.js` tiene cambios sin
subir, pasa lo mismo: pegalo inline (o commiteá y subí antes de empezar).

Los enlaces del mismo sitio vuelven como **ruta** (`/agenda/`) para no repetir el dominio: la URL
completa es `base` + ruta. En el resultado (`urls_visitadas`, `entradas`, `eventos[].url`) van completas;
en `enlaces_candidatos` puede ir la ruta.

## `preparar(opciones)`: esperar, scrollear, expandir y listar enlaces

Correrla **en cada página de listado** (agenda, muestras, cartelera, programación, portada), apenas
termina de navegar. Hace, en orden:

1. Espera hasta 30 s a que el texto de la página deje de cambiar (sitios lentos, apps con JavaScript).
2. Cierra avisos de cookies y ventanas que tapan la página (ver `popups`), y lo repite en cada paso del
   scroll, porque hay avisos que aparecen a los segundos o al bajar.
3. Scrollea hasta el final, una y otra vez, hasta que la página deja de crecer, y aprieta los botones
   "ver más / cargar más / load more" que no navegan a otra página.
4. Devuelve los enlaces clasificados y datos de la página.

Qué devuelve:

- `secciones`: enlaces **fuertes** del mismo sitio, los que suelen ser la agenda: agenda, cartelera,
  programación, eventos, actividades, muestras, exposiciones, exhibiciones, shows, funciones, obras,
  conciertos, calendario, próximas, upcoming. Hay que abrirlos todos (o descartarlos con motivo).
- `debiles`: subprogramas que la agenda casi siempre ya incluye: ciclos, talleres, cursos, visitas,
  actuales, temporada, festival, cine, películas, inauguración. Ver la regla en la skill (3.2). Si una
  página no tiene ninguna sección fuerte, las débiles pasan a `secciones`.
- `fichas`: páginas de un evento o muestra (enlaces con fecha en la tarjeta, o de agenda pero profundos).
- `ticketeras`, `externos`: otros sitios (posibles espacios nuevos).
- `largo_texto`, `espera_ms`, `pasos_scroll`, `clics_ver_mas`, `popups`, `fechas_en_texto`,
  `eventos_jsonld`, `plataforma`.
- Si una lista se cortó, aparece `<lista>_total` con cuántos había. Para ver más:
  `preparar({fichas: 150})` (también `secciones`, `debiles`, `ticketeras`, `externos`).

Ya filtra los cambios de idioma (`EN`, `/lang/pt/`) y las URLs repetidas (barra final, `utm_`).

Cómo leer el resultado:

- `largo_texto` muy chico (< 300) después de 30 s: la página no cargó. Recargá y volvé a correr
  `preparar` (eso es un intento); ver "Abrir y esperar" en la skill.
- `eventos_jsonld > 0`: usá `jsonld()`, es más rápido y exacto.
- `fechas_en_texto` alto y pocas `fichas`: las fechas están en el texto; usá `bloques()`.
- `externos`: si parecen un espacio cultural de CABA que no está en la cola, sumalo en `sitios_nuevos`.

## `esperar(opciones)`: fichas

Para la página de un evento o una muestra: espera a que cargue, cierra avisos y devuelve el texto
principal sin menú, pie, barras laterales ni "compartir". Devuelve hasta 2500 caracteres; si hay más,
aparece `texto_total`. Si lo que falta (fecha de cierre, precio) no está en lo que volvió, pedí más:
`esperar({max: 6000})`.

## `popups()`: avisos de cookies y ventanas que tapan la página

`preparar` y `esperar` ya lo hacen solas (devuelven en `popups` lo que cerraron). Esta sirve cuando
aparece un aviso después, por ejemplo al abrir un menú.

Qué cierra, en orden:

1. Gestores de consentimiento conocidos (OneTrust, Didomi, Cookiebot, Usercentrics, CookieYes,
   Complianz, Cookie Notice, Iubenda, CookieFirst, Google, Borlabs, Cookie Consent), incluso dentro de
   shadow DOM. Si hay opción, **rechaza** o elige "solo necesarias"; si no, acepta.
2. Avisos de cookies propios del sitio: un botón "Rechazar / Aceptar / Entendido / OK / Cerrar" dentro de
   un aviso fijo o un diálogo que habla de cookies o privacidad. Nunca aprieta un "OK" suelto.
3. Ventanas que tapan al menos un cuarto de la pantalla y hablan de newsletter, suscripción,
   notificaciones, promociones, descargar la app o edad: usa la ✕ o "No, gracias / Ahora no / Cerrar";
   en un control de edad, "Sí / Soy mayor". Si no hay botón, manda Escape. Cada ventana se intenta una
   sola vez.
4. Si el aviso está en un iframe de otro dominio, JS no puede tocarlo: lo informa como
   `iframe de consentimiento`. Sacá una captura y cerralo con un clic (herramienta `computer`).
5. Si después de cerrar algo la página quedó sin scroll (`overflow: hidden`), la destraba.

Si `popups` muestra un aviso que se repite en cada página del sitio, anotalo en
`comportamiento.cookies` (por ejemplo "OneTrust, se rechaza"). Si una ventana no se pudo cerrar y tapa
el contenido, cerrala a mano con un clic y anotá cómo en `comportamiento`.

## `bloques(opciones)`: tarjetas con fecha de un listado

Devuelve cada tarjeta, fila o ítem que tenga una fecha, con su enlace (hasta 300 caracteres cada uno,
120 tarjetas; `bloques({max: 200})` para más). Sirve para leer un listado entero sin pedir el texto de
toda la página: **usalo en vez de `get_page_text`**, que devuelve la página completa con menú y pie.
Correrla después de `preparar` (que ya scrolleó y expandió).

## `jsonld(opciones)`: eventos con datos estructurados

Devuelve los eventos del JSON-LD (título, inicio, fin, lugar, dirección, precio, url, descripción de
hasta 200 caracteres). `jsonld({descripcion: 400})` para descripciones más largas.

## `turismo()`: Turismo BA (agenda "Qué hacer esta semana")

La página trae todas las actividades en un arreglo JSON dentro de un script. `turismo()` lo lee y
devuelve los eventos **ya en el formato del resultado** (sección 5 de la skill): las actividades que ya
empezaron vienen con `vigente_sin_fin: true`, las que no tienen `lugar` se descartan (cuenta en
`descartados_sin_lugar`) y las descripciones van cortadas a 200 caracteres. Copiá `eventos` tal cual al
archivo de resultado, sin reescribirlos uno por uno.

## Instagram

En el perfil (`https://www.instagram.com/<usuario>/`), después de esperar y scrollear un poco a mano:
`instagram_perfil()` devuelve `posts` (hasta 12), `bio`, `destacadas` y `pide_login`.

En cada post: `instagram_post()` devuelve `publicado` (la fecha del post: sirve para saber de qué año
habla un "sábado 18"; si el post es de hace meses, el evento probablemente ya pasó) y `texto`.

## Patrones de sitios conocidos

- **WordPress + The Events Calendar** (`tribe-events` en el HTML): abrir
  `<sitio>/wp-json/tribe/events/v1/events?per_page=50&start_date=<desde>&end_date=<hasta>` en la pestaña.
  Es JSON con `title`, `start_date`, `end_date`, `venue`, `cost`, `url`. Si responde 404, usar `/eventos/`
  o `/events/` con `preparar`.
- **Wix**: carga lento y por partes; `preparar` ya espera, pero si `largo_texto` queda bajo, esperar 10 s
  más y repetir. Los menús a veces están en un desplegable "Más": abrirlo a mano y mirar sus enlaces.
- **Linktree / Taplink** (bio de Instagram): cada botón es un enlace. Abrir los que digan agenda,
  cartelera, entradas, eventos, programación, o que vayan a una ticketera.
- **Alternativa Teatral**: la ficha de un espacio lista sus obras en cartel con días y horarios; entrar a
  cada obra para ver fechas de función y precio.
- **Calendarios por mes** (`?mes=`, `/2026/10/`, flechas "siguiente"): recorrer el mes actual y el
  siguiente si la ventana de 14 días lo cruza.
- **Pestañas "Actuales / Próximas / Anteriores"**: abrir "Actuales" y "Próximas"; "Anteriores" se puede
  descartar con motivo "archivo de muestras pasadas".

## Si cambiás `navegador.js`

Commiteá y subí antes de la corrida: la URL de jsDelivr se fija al commit, así que la versión nueva se usa
recién cuando está en GitHub. Probá los casos que ya cubre: carga lenta, scroll infinito, botón "cargar
más", avisos de cookies (gestores conocidos, shadow DOM, avisos que aparecen tarde), ventanas de
newsletter y de edad, y enlaces a muestras dentro del menú.
