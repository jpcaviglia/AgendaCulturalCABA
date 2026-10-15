---
name: actualizar-agenda
description: Actualiza la Agenda Cultural CABA rastreando con el navegador TODOS los sitios de la lista (webs de lugares, galerías, museos, agregadores e Instagram), carga los eventos de los próximos 14 días, anota cómo se comporta cada sitio para la próxima corrida, arma data/eventos.json y publica. Usar cuando se pida actualizar la agenda, rastrear o recrawlear los sitios, o cuando lo dispare la rutina programada.
---

# Actualizar la Agenda Cultural CABA

Todos los datos se juntan **con el navegador**. Los scripts de `scripts/` no entran a ningún sitio: solo
llevan la cola, validan lo que encontraste, guardan lo aprendido y arman `data/eventos.json`.

Trabajá de principio a fin sin pedir confirmación. Hablá y escribí los datos en español.

## Reglas que no se negocian

1. **Cada corrida recorre todos los sitios.** Lo que pasó en corridas anteriores (`ultimo`, `notas`,
   `comportamiento`) dice *cómo* rastrear un sitio, nunca *si* rastrearlo. Un sitio que la vez pasada no
   tenía eventos, o no cargó, se vuelve a abrir igual.
2. **"No hay eventos" es una conclusión que hay que probar.** Antes de marcar `sin_eventos` o `sin_agenda`
   tenés que haber abierto cada enlace a agenda, muestras, exposiciones, exhibiciones, cartelera,
   programación, actividades, ciclos o ticketera que aparezca en el sitio (menú, portada, pie), haber
   scrolleado cada listado hasta el final y apretado sus "ver más". `crawl.py guardar` rechaza el
   resultado si falta algo de eso.
3. **Un sitio lento no es un sitio caído.** Esperá hasta 30 s, recargá, probá variantes de la URL. Solo
   después de 3 intentos fallidos se marca `no_carga`, y se vuelve a probar en la próxima corrida.
4. **No inventes datos.** Si falta título, fecha o lugar, el evento no se carga. Si falta hora o precio,
   va vacío.
5. **Anotá lo que aprendiste** de cada sitio (dónde está la agenda, cuánto tarda, si hay que scrollear,
   qué botón expande, qué enlaces nuevos encontraste). La próxima corrida empieza con eso.

## Herramientas

- Navegador: las herramientas de Claude in Chrome (`navigate`, `javascript_tool`, `get_page_text`,
  `computer`, `find`, `tabs_context`…). Si no aparecen, cargalas con ToolSearch (`chrome`). Usá una sola
  pestaña propia para todo el rastreo.
- Fragmentos de JS listos y probados: [navegador.md](navegador.md). Leelo al empezar. Los más usados son
  `preparar` (esperar + cookies + scroll + "ver más" + enlaces clasificados), `bloques` (tarjetas con
  fecha) y `esperar` (fichas).
- Registro: `python scripts/crawl.py ...` (en Windows puede ser `py` en vez de `python`).

## 1. Empezar o retomar

```bash
git pull --rebase --autostash
python scripts/crawl.py iniciar
```

`iniciar` arma la cola con todos los sitios de `data/crawl/sitios.json`. Si hay una corrida abierta de
los últimos 3 días, la retoma donde quedó (no se empieza de cero si la sesión anterior se cortó).

## 2. Recorrer la cola

Repetir hasta que la cola quede vacía:

```bash
python scripts/crawl.py siguiente 3
```

Muestra los próximos sitios con todo lo que se sabe de ellos: `web`, `instagram`, `enlace_bio`,
`entradas` (páginas de agenda que funcionaron antes), `comportamiento`, `notas`, `enlaces_pendientes`
(enlaces que se vieron y no se abrieron) y `ultimo`. Leelo antes de abrir el sitio. Las notas que dicen
"el script viejo lo marcó ... NO es confiable" vienen de un verificador que no abría las páginas: ignorá
esa conclusión y revisá el sitio a fondo.

Para cada sitio: rastrearlo (sección 3 o 4), escribir el resultado en `data/crawl/tmp/<id>.json`
(formato en la sección 5) y guardarlo:

```bash
python scripts/crawl.py guardar data/crawl/tmp/<id>.json
```

Si responde **NO SE GUARDÓ**, volvé al navegador y hacé lo que dice (abrir los enlaces que faltan,
scrollear, reintentar). No cambies el estado para esquivar la validación.

Guardá cada sitio apenas lo terminás: si la sesión se corta, lo guardado no se pierde.

Cada ~40 sitios, publicá un avance (sección 6). Así la página se actualiza aunque la corrida se corte.

## 3. Rastrear una web

### 3.1 Abrir y esperar

1. Abrí la primera URL de `entradas` si hay; si no, `web`. Si hay `enlaces_pendientes`, abrilos también.
2. Corré `preparar`. Si `comportamiento.espera_seg` dice que el sitio es lento, esperá eso antes.
   `preparar` también cierra avisos de cookies y ventanas de newsletter, notificaciones o edad
   (prefiere "rechazar" o "solo necesarias"), y lo repite mientras scrollea. Mirá `popups` en el
   resultado: si dice `iframe de consentimiento`, o si en la captura sigue habiendo algo tapando la
   página, cerralo con un clic y volvé a correr `preparar`. Nunca marques un sitio como vacío o caído
   porque un aviso tapaba el contenido.
3. Si `largo_texto` es muy chico o la página muestra un error:
   - intento 2: recargá, esperá 10-15 s más y corré `preparar` otra vez;
   - intento 3: probá la variante (`www`/sin `www`, `http`/`https`, la portada si estabas en una sección,
     o la URL de la agenda si estabas en la portada);
   - si un intento carga, seguí normal y anotá en `comportamiento` cuánto tardó;
   - si ninguno carga: `no_carga` con `intentos: 3` y la `evidencia` (qué mostró).
   - Dominio que no resuelve, estacionado, en venta, cuenta suspendida o que redirige a otra cosa:
     `dominio_caido`. Antes, buscá en Google `"<nombre>" Buenos Aires` la web nueva o el Instagram; si
     la encontrás, rastreala en el mismo turno y poné `web_nueva` o `instagram`.
   - Captcha, login obligatorio o 403: `bloqueado` con `evidencia`. No intentes resolverlo.

### 3.2 Encontrar todos los listados

La portada casi nunca alcanza: suele mostrar una sola muestra o los próximos tres eventos.

- Tomá `secciones` de `preparar` (menú, portada y pie). Esos son los `enlaces_candidatos`.
- Mirá también los menús desplegables ("Más", "☰", "Programación ▾"): abrilos con un clic y volvé a
  correr `preparar` si aparecen enlaces nuevos.
- Abrí **cada** sección candidata y corré `preparar` en ella. Dentro de cada sección, las pestañas o
  filtros "Actuales", "Próximas", "Este mes", "Hoy", "Semana" son más secciones: abrilas.
- Seguí la paginación ("siguiente", `?page=2`, calendario del mes siguiente) hasta cubrir los próximos
  14 días.
- Solo se puede descartar un candidato con un motivo concreto: "archivo de muestras pasadas",
  "es la tienda", "convocatoria, no evento", "es la misma página que /agenda". "Parecía vacío" no es un
  motivo.

### 3.3 Leer los eventos

- Si `eventos_jsonld > 0`, usá `jsonld`.
- Si no, usá `bloques` sobre cada listado (o `get_page_text` si `bloques` no captura bien la estructura).
- Entrá a la ficha de un evento o muestra (`fichas`) cuando el listado no tenga fecha completa (inicio
  y fin de una muestra), lugar o sala, horario o precio. Para muestras de galerías y museos entrá
  siempre: la fecha de cierre suele estar solo en la ficha.
- Desde una ficha seguí el enlace a entradas o "más info" si ahí están las funciones o el precio.
  Profundidad máxima: 3 niveles desde el listado, mismo dominio o ticketera.
- Si un listado tiene la información en imágenes (afiches) sin texto, sacá una captura y leela.
- Llevá la lista de URLs ya visitadas para no repetir. Van todas en `urls_visitadas`.

Qué cargar: lo que esté en curso o empiece dentro de los próximos 14 días (la ventana la muestra
`siguiente`). Una muestra que empezó en agosto y cierra en diciembre está vigente y se carga. Una obra con
funciones todos los viernes de octubre es un solo evento con `fecha_inicio`, `fecha_fin` y `horarios`.
Una inauguración con día y hora propios va como evento aparte.

### 3.4 Enlaces nuevos

- `externos` de `preparar` que sean otro espacio cultural de CABA (galería, sala, centro cultural,
  museo, cine) y no estén en la cola: sumalos en `sitios_nuevos`. El script los agrega a
  `sitios.json` y a `lugares.json`/`galerias.json`, y los pone en la cola de esta misma corrida.
  Confirmá que estén en CABA; no agregues espacios de otras ciudades.
- Páginas del mismo sitio que no llegaste a abrir y podrían tener eventos: `enlaces_nuevos`.
- Las páginas donde efectivamente estaban los eventos: `entradas` (la próxima corrida empieza ahí).

## 4. Rastrear Instagram

Se rastrea Instagram de los lugares sin web, y de los que tienen web cuando la web no dio eventos (el
script los encola solo, después de todas las webs). Usá la sesión ya iniciada del navegador; no inicies
sesión ni crees cuentas.

**Límites.** Instagram frena las cuentas que abren muchas páginas seguidas, así que el script lleva un
cupo y no todos los perfiles entran en cada corrida: se rotan, primero los revisados hace más tiempo.

- Cupo diario de páginas de Instagram (perfil + cada post abierto), por defecto 150. `siguiente` muestra
  lo que queda; cuando se agota, deja los perfiles restantes como `pospuesto` y van primeros la próxima.
- Si un perfil se guarda como `bloqueado`, no se abre Instagram por 24 h (enfriamiento): los perfiles
  pendientes quedan `pospuesto`. No intentes seguir con otro perfil.
- Cada 25 páginas, `guardar` pide una pausa de 5 minutos: hacela (o seguí con webs, si quedan).
- Los límites se ajustan en `data/crawl/local/instagram_estado.json` (`limites`).

**Posts ya analizados.** En `data/crawl/local/instagram_posts.json` (solo en esta máquina, no se sube
al repositorio) queda cada post abierto con los eventos que tenía. No vuelvas a abrirlos:

1. Abrí `https://www.instagram.com/<usuario>/`, esperá 3-5 s y corré `instagram_perfil`.
   Si aparece un diálogo de cookies ("Rechazar cookies opcionales") o de notificaciones ("Ahora no"),
   corré `popups` o cerralo con un clic. Si `pide_login` es verdadero o aparece un captcha:
   `bloqueado` y pasá al siguiente.
2. Pasá las URLs de `posts` al script:
   `python scripts/crawl.py ig-vistos <id> <url1> <url2> ...`
   Abrí **solo los NUEVOS** (hasta ~9) y las destacadas "Agenda", "Cartelera", "Programación" si hay.
   Corré `instagram_post` en cada uno. Usá `publicado` para deducir el año de fechas como "sábado 18".
   Si un post nuevo es de hace más de 2 meses y los anteriores también, no hace falta seguir bajando.
3. Si el texto no tiene la fecha, mirá el afiche (captura).
4. Seguí el enlace de la bio (`bio` o `enlace_bio`): Linktree, ticketera o web. Aplicá la sección 3.
5. En el resultado poné:
   - `posts`: **todas** las URLs de posts de la grilla que consideraste, nuevas y ya vistas, con
     `publicado` si lo sabés: `[{"url": "...", "publicado": "2026-10-10"}]`. El script agrega solo los
     eventos vigentes de los posts ya vistos, así que no los copies.
   - en cada evento, `"post": "<url del post>"` de donde salió (para poder reutilizarlo).
   - `paginas_instagram`: cuántas páginas de Instagram abriste en este perfil (perfil + posts +
     destacadas). Si no lo ponés, se cuenta 1 + los posts nuevos.
6. Ritmo: esperá 4-10 s al azar entre acciones y entre perfiles. Scroll natural, sin ráfagas, sin abrir
   endpoints internos. Al primer "intentá de nuevo más tarde", límite de acciones o captcha, guardá ese
   perfil como `bloqueado` (con `evidencia`) y seguí solo con webs.
7. Para encontrar posts sin login: Google `site:instagram.com/p/ "<lugar>"`.

En Instagram, `scroll_completo: true` significa que viste los últimos ~9 posts (nuevos o ya vistos); los
`enlaces_candidatos` son la bio y las destacadas de agenda.

## 4b. Agregadores y fuentes de descubrimiento

- **Turismo BA**: usar el fragmento `turismo` de navegador.md. Las actividades que ya empezaron van con
  `vigente_sin_fin: true`.
- **SalePlan**: recorrer las `entradas` (hoy, semana, fin de semana, eventos) con `preparar`, abrir las
  fichas y leer `jsonld`. Hacer pausas de 1-2 s entre fichas.
- **Descubrimiento** (Arte al Día, Gallery, Indiehoy, Time Out, Meridiano): sirven para encontrar
  espacios y muestras que no están en la lista. Cargá las muestras de CABA que figuren con fechas, y
  sumá los espacios nuevos en `sitios_nuevos`.
- **Ticketeras y agendas** (Alternativa Teatral, Eventbrite, Ticketek, Passline, Indiehoy, Time Out):
  seguir `entradas` y `comportamiento` de cada una. Cargar solo eventos en CABA, culturales, dentro de la
  ventana. Ir al ritmo de una persona (pausas de 2-4 s entre páginas); ante captcha o 403, `bloqueado`.
  Las salas o espacios de CABA que aparezcan y no estén en la lista van en `sitios_nuevos`.
- En agregadores y descubrimiento el `lugar` de cada evento es obligatorio: el nombre del espacio
  donde ocurre, igual al de `data/lugares.json` si está ahí.
- Un sitio con `"rastrear": false` en `sitios.json` no entra en la cola. Hoy no hay ninguno; solo se
  marca así si el usuario lo pide.

## 5. Formato del resultado

Un objeto JSON por sitio y canal en `data/crawl/tmp/<id>.json`:

```json
{
  "id": "galeria-barro",
  "canal": "web",
  "estado": "con_eventos",
  "urls_visitadas": ["https://barro.cc/es/gallery", "https://barro.cc/es/muestras", "https://barro.cc/es/muestras/x"],
  "intentos": 1,
  "scroll_completo": true,
  "enlaces_candidatos": [
    {"texto": "Muestras", "url": "https://barro.cc/es/muestras", "visitado": true},
    {"texto": "Archivo", "url": "https://barro.cc/es/archivo", "descartado": "archivo de muestras pasadas"}
  ],
  "evidencia": "",
  "eventos": [
    {"titulo": "Nombre de la muestra", "fecha_inicio": "2026-09-12", "fecha_fin": "2026-11-15",
     "hora": "", "horarios": "Martes a sábados de 11 a 19 h", "lugar": "", "barrio": "", "direccion": "",
     "categoria": "Artes visuales", "precio": "Gratis", "url": "https://barro.cc/es/muestras/x",
     "descripcion": "Artista, curaduría, de qué trata (hasta ~400 caracteres)."}
  ],
  "entradas": ["https://barro.cc/es/muestras"],
  "comportamiento": {"espera_seg": 6, "scroll": "carga más al scrollear", "fichas": "la fecha de cierre está solo en la ficha"},
  "nota": "La portada muestra solo la muestra principal; el listado completo está en /es/muestras.",
  "enlaces_nuevos": [],
  "sitios_nuevos": [
    {"nombre": "Galería X", "web": "https://galeriax.com.ar", "instagram": "@galeriax", "tipo": "galeria",
     "barrio": "San Telmo", "direccion": "Defensa 1000", "motivo": "enlazada desde Barro como galería vecina"}
  ]
}
```

- `estado`: `con_eventos`, `sin_eventos` (hay agenda pero nada vigente ni en la ventana), `sin_agenda`
  (no publica programación en este canal), `no_cultural`, `no_carga`, `dominio_caido`, `bloqueado`.
  (`pospuesto` lo pone el script a los perfiles de Instagram que no entraron en el cupo.)
- Solo Instagram: `posts`, `paginas_instagram` y `post` en cada evento (sección 4).
- `evidencia`: obligatoria en `sin_eventos`, `sin_agenda`, `no_cultural` y en las fallas. Ejemplo:
  "/muestras lista 14 muestras, la más reciente cerró el 2026-09-30; /agenda vacía; sin próximas".
- `eventos[].lugar`: vacío solo si el sitio tiene un único lugar (se completa solo). En sitios con
  varios lugares, agregadores e Instagram de terceros va siempre. Mismo nombre que en
  `data/lugares.json` o `data/galerias.json` para que se dedupliquen bien. Si el evento es en otra sala,
  `"<Lugar> · <Sala>"`.
- Fechas `AAAA-MM-DD`; `hora` `HH:MM` (una sola; si hay varias, en `horarios`). Si no dice el año,
  asumí el actual solo si la fecha no queda en el pasado; si hay duda, no lo cargues.
- `categoria`: vacía si no es obvia (la clasifica el script). En galerías, `Artes visuales`.
- `precio`: "Gratis", "$ 8000", "Desde $ 5000", o vacío. `url`: la ficha del evento o de las
  entradas; el post de Instagram solo si no hay otra.
- `vigente_sin_fin: true` solo cuando la fuente lo publica como vigente sin fecha de cierre.
- `comportamiento`: claves y valores cortos que le sirvan a la próxima corrida (`espera_seg`, `scroll`,
  `ver_mas`, `paginacion`, `menu`, `cookies` (qué aviso aparece y cómo se cierra), `popups`,
  `plataforma`, `fichas`, `extraccion`, `bloqueos`).
  Se fusiona con lo que ya había; poné una clave en `null` para borrarla si dejó de ser cierta.
- `nota`: una o dos frases con lo aprendido. Se acumulan en `notas` del sitio.
- `web_nueva`, `instagram`, `enlace_bio`: solo si descubriste que cambiaron o faltaban.

**Resultados grandes** (Turismo BA, SalePlan, un teatro con 60 funciones): acortá las descripciones a
~200 caracteres y escribí el archivo de una vez. No lo partas en varios guardados del mismo `id` y
canal: cada guardado reemplaza la captura anterior de ese sitio.

## 6. Publicar (avances y final)

```bash
python scripts/armar_agenda.py
git add data/
git commit -m "Agenda <fecha>: avance del rastreo (<hechos>/<total> sitios)"
git pull --rebase --autostash && git push
```

`armar_agenda.py` toma la última captura de cada sitio (las de más de 10 días se ignoran), filtra la
ventana de 14 días, clasifica, quita duplicados, ubica en el mapa las direcciones nuevas y actualiza el
estado de cada lugar en `data/lugares.json`. Si el push falla dos veces, dejá el commit local e informalo.

## 7. Cerrar

Cuando `siguiente` diga que la cola está vacía:

```bash
python scripts/armar_agenda.py
python scripts/crawl.py cerrar
git add data/ && git commit -m "Agenda <fecha>: <N> eventos, <S> sitios rastreados" && git pull --rebase --autostash && git push
```

Si la corrida se cortó por un bloqueo o un error del navegador que no se resuelve, cerrá con
`crawl.py cerrar --forzar`: lo que quedó sin rastrear va primero la próxima vez.

Informe final (3-6 líneas): eventos publicados, sitios rastreados por estado, sitios nuevos, fallas
(`no_carga`, `dominio_caido`, `bloqueado`) y qué conviene revisar a mano. El detalle queda en
`data/crawl/informes/<fecha>.md`.

## Límites

- No iniciar sesión, no crear cuentas, no seguir, no dar likes, no mandar mensajes, no comprar entradas.
- No editar `data/eventos.json` a mano ni las capturas de `data/crawl/capturas/`: los escriben los scripts.
- Sí se pueden editar a mano en `data/crawl/sitios.json` datos de un sitio que estén mal (web, instagram,
  lugares) cuando lo confirmaste en el navegador.
