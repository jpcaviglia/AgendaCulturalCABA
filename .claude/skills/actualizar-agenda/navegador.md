# Browser tools

The tools are in [navegador.js](navegador.js) and are loaded into the tab with **a single line** (in Claude in
Chrome, with `javascript_tool`). There is no need to read or paste the code.

Start the local server once per session, in the background, **before** the first page:

```bash
python scripts/crawl.py servir      # serves navegador.js from the working tree on 127.0.0.1:8791
```

Then `python scripts/crawl.py iniciar` prints the line (`crawl.py herramientas` shows it again, and `siguiente`
repeats the URL):

```js
(async () => { window.__agt || await import("http://127.0.0.1:8791/navegador.js"); return window.__agt.preparar(); })()
```

Without the server the line uses the jsDelivr URL pinned to the last pushed commit of `navegador.js`, but the
browser tool's auto-mode classifier denies it as "Code from External": always start `servir` first. The server
serves the file as it is on disk, so edits to `navegador.js` apply without commit or push.

To use another tool, change only the end: `window.__agt.esperar()`, `window.__agt.bloques()`, etc.
Every time you navigate to another page you must use the full line (the `window.__agt ||` avoids downloading
the file again while you stay on the same page). All tools return a JSON text and also leave it in
`window.__ag` (a **string**: `JSON.parse(window.__ag)` before using it; `bloques()` leaves its cards in `.bloques`): if a tool returns an empty promise or `{}`, wait a few seconds and run
`JSON.stringify(window.__ag)`.

**Limits of the `javascript_tool` result.** A result that contains a URL with `?query` is replaced by
`[BLOCKED: Cookie/query string data]`: strip them before returning (`.replace(/\?[^"\s;]*/g,'')`, or
`replace(/[?=&]/g,' ')` on page text). Long results are cut at ~800-1,500 characters: return only what you
need (counts, dates, short titles, `slice`). The first call after `navigate` often answers `{}` or `1` because
the import is still running: import in one call, wait 2 s, and call the tool in the next one (they can go in
the same `browser_batch`). `window.__agt` is lost on every navigation, and the tab refuses to read a page that
changed domain while the script was running (read the tab state again and repeat).

**If the import fails** ("Failed to fetch dynamically imported module" or a Content Security Policy error):
the site blocks scripts from other domains. Read `navegador.js`, paste all of it followed by the call
(`window.__agt.preparar()`) and note `"comportamiento": {"herramientas": "pegar inline (CSP)"}` so the next
run pastes it directly. A site whose CSP or the browser's local-network rules block `127.0.0.1` fails the
same way. In a Claude in Chrome session the `import` can fail on every site with no error at all (the call returns `{}` and
`window.__agt` stays `undefined`, even though `curl http://127.0.0.1:8791/navegador.js` answers 200; a later `fetch` of that address
froze the tab). Do not retry it: pasting the 23 KB file on each page costs ~6,000 tokens per navigation, so work with small
snippets of your own instead: `document.body.innerText.replace(/\s+/g,' ')`, `[...document.querySelectorAll('a')]` for links and
`fetch(url)` from the same tab for each event page (price with a `$` regex, picture from `og:image` or the card's `<img>`).

Links to the same site come back as a **path** (`/agenda/`) so the domain is not repeated: the full URL is
`base` + path. In the result (`urls_visitadas`, `entradas`, `eventos[].url`) they go in full; in
`enlaces_candidatos` the path is fine.

## `preparar(opciones)`: wait, scroll, expand and list links

Run it on **every listing page** (agenda, exhibitions, listings, programming, home page), as soon as it
finishes navigating. In order, it:

1. Waits up to 30 s for the page text to stop changing (slow sites, JavaScript apps).
2. Closes cookie notices and windows that cover the page (see `popups`), and repeats this at every scroll
   step, because some notices appear after a few seconds or when scrolling down.
3. Scrolls to the bottom, over and over, until the page stops growing, and presses the "ver más / cargar más
   / load more" buttons that do not navigate to another page.
4. Returns the classified links and data about the page.

What it returns:

- `secciones`: **strong** links to the same site, the ones that are usually the agenda: agenda, cartelera,
  programación, eventos, actividades, muestras, exposiciones, exhibiciones, shows, funciones, obras,
  conciertos, calendario, próximas, upcoming, and also talleres, cursos, clases, seminarios, workshops,
  visitas and recorridos. All of them must be opened (or discarded with a reason).
- `debiles`: sub-programs that the agenda almost always already includes: ciclos, actuales, temporada,
  festival, cine, películas, inauguración. See the rule in the skill (3.2). If a page has no strong section,
  the weak ones move to `secciones`.
- `fichas`: pages of one event or exhibition (links with a date in the card, or agenda links that are deep).
- `ticketeras`, `externos`: other sites (possible new venues).
- `largo_texto`, `espera_ms`, `pasos_scroll`, `clics_ver_mas`, `popups`, `fechas_en_texto`,
  `eventos_jsonld`, `plataforma`.
- If a list was cut off, `<lista>_total` appears with how many there were. To see more:
  `preparar({fichas: 150})` (also `secciones`, `debiles`, `ticketeras`, `externos`).

It already filters out language switches (`EN`, `/lang/pt/`) and repeated URLs (trailing slash, `utm_`).

How to read the result:

- Very small `largo_texto` (< 300) after 30 s: the page did not load. Reload and run `preparar` again (that
  counts as one attempt); see "Abrir y esperar" in the skill.
- `eventos_jsonld > 0`: use `jsonld()`, it is faster and exact.
- High `fechas_en_texto` and few `fichas`: the dates are in the text; use `bloques()`.
- `externos`: if they look like a cultural venue in CABA that is not in the queue, add it in `sitios_nuevos`.

## `esperar(opciones)`: event pages

For the page of one event or exhibition: waits for it to load, closes notices and returns the main text
without menu, footer, sidebars or "share". It also returns `imagen` (the page's `og:image`, when it is an
https URL). It returns up to 2500 characters; if there is more, `texto_total` appears. If what is missing (closing date, price) is not in what came back, ask for more:
`esperar({max: 6000})`.

## `popups()`: cookie notices and windows that cover the page

`preparar` and `esperar` already do this on their own (they return what they closed in `popups`). Use this
one when a notice appears later, for example after opening a menu.

What it closes, in order:

1. Known consent managers (OneTrust, Didomi, Cookiebot, Usercentrics, CookieYes, Complianz, Cookie Notice,
   Iubenda, CookieFirst, Google, Borlabs, Cookie Consent), even inside shadow DOM. If there is an option, it
   **rejects** or picks "solo necesarias"; otherwise it accepts.
2. The site's own cookie notices: a "Rechazar / Aceptar / Entendido / OK / Cerrar" button inside a fixed
   notice or a dialog that talks about cookies or privacy. It never presses a loose "OK".
3. Windows that cover at least a quarter of the screen and talk about newsletter, subscription,
   notifications, promotions, downloading the app or age: it uses the ✕ or "No, gracias / Ahora no /
   Cerrar"; on an age check, "Sí / Soy mayor". If there is no button, it sends Escape. Each window is tried
   only once.
4. If the notice is in an iframe from another domain, JS cannot touch it: it reports it as
   `iframe de consentimiento`. Take a screenshot and close it with a click (`computer` tool).
5. If after closing something the page is left without scroll (`overflow: hidden`), it unlocks it.

If `popups` shows a notice that repeats on every page of the site, note it in `comportamiento.cookies` (for
example "OneTrust, se rechaza"). If a window could not be closed and covers the content, close it by hand
with a click and note how in `comportamiento`.

## `bloques(opciones)`: cards with a date from a listing

Returns every card, row or item that has a date, with its link and, when the card has one, its picture in
`imagen` (the largest https image of the card; logos, icons and SVGs are skipped) (up to 300 characters each, 120 cards;
`bloques({max: 200})` for more). It reads a whole listing without requesting the text of the entire page:
**use it instead of `get_page_text`**, which returns the whole page with menu and footer. Run it after
`preparar` (which already scrolled and expanded).

## `jsonld(opciones)`: events with structured data

Returns the JSON-LD events (title, start, end, venue, address, price, url, `imagen`, description of up to 200
characters). `jsonld({descripcion: 400})` for longer descriptions.

## `turismo()`: Turismo BA ("Qué hacer esta semana" agenda)

The page carries all the activities in a JSON array inside a script. `turismo()` reads it and returns the
events **already in the result format** (section 5 of the skill): activities that have already started come
with `vigente_sin_fin: true`, those without a `lugar` are dropped (counted in `descartados_sin_lugar`) and
descriptions are cut to 200 characters. Copy `eventos` as is into the result file, without rewriting them one
by one.

## Instagram

On the profile (`https://www.instagram.com/<usuario>/`), after waiting and scrolling a little by hand:
`instagram_perfil()` returns `posts` (up to 12), `bio`, `destacadas` and `pide_login`.

On each post: `instagram_post()` returns `publicado` (the post's date: it tells you which year a "sábado 18"
refers to; if the post is months old, the event has probably already happened) and `texto`.

instagram.com blocks the import (CSP), so in practice use these two inline snippets, which return the same
thing without loading anything:

- Profile: `[...new Set([...document.querySelectorAll('a[href*="/p/"],a[href*="/reel/"]')].map(a=>a.getAttribute('href').replace(/\?.*/,'')))].slice(0,9)`
  and `document.body.innerText.slice(0,300)` for the bio (the bio link is in the profile header).
- Post: `document.querySelector('time').dateTime.slice(0,10)` and
  `(document.querySelector('article')||document.body).innerText.replace(/\s+/g,' ').slice(0,700)`.

- Fastest: the `alt` of each grid thumbnail already holds the post's full caption (up to ~600 characters):
  `[...document.querySelectorAll('a[href*="/p/"],a[href*="/reel/"]')].slice(0,9).map(a=>a.href+' | '+a.querySelector('img').alt)`.
  Most profiles are covered with that, without opening any post (so 1 page of quota per profile).

What to know about the grid: it mixes the profile's own posts with posts of other accounts that tag it
(bands, producers, collaborators; their URLs start with another username), and many venues announce their
shows only there. The recent post ids start with `De` (October 2026): older ones (`Dd`, `Dc`, `DT`...) are
months old. Flyers without a caption are images: use `zoom` on the viewer (x 420-830) and, in a carousel,
click the arrow (about x 808, y 299) to see each day. "Sorry, this page isn't available" usually means a
wrong username (look the venue up on Google, correct `instagram` in `sitios.json` and `lugares.json`) and
sometimes a closed account.

## Getting a big result out of the page

`javascript_tool` returns a few KB; the clipboard is blocked when the tab is not focused. For hundreds of rows
(Alternativa Teatral, Jodify), store them in `window.__rows` and send them to a local receiver: run a tiny
`http.server` on `127.0.0.1` that writes the POST body to a file (with `Access-Control-Allow-Origin: *`), then in the page
`fetch('http://127.0.0.1:PORT/',{method:'POST',body:JSON.stringify(window.__rows)})` **without awaiting it** (awaiting a
large body freezes the call). Long loops (clicking "Ver más" 80 times) go in an async IIFE that sets `window.__done`;
poll it with calls under 40 s.

Gotchas: start the receiver as its own background command (`run_in_background`), not inside a `( ... &)` subshell,
and give it a few seconds before the first POST (the file shows up late); a test `curl -X POST` overwrites what the
page already sent. Start the receiver with a Windows path (`C:/...`), not the Git Bash `/c/...` one: Python cannot open it, the
handler raises, the browser's request hangs and, after six of them, Chrome stops connecting to that port (use a new
port). If the POST still does not arrive, put the text in a `<pre>` inside `<article>` and read it with
`get_page_text` (the `javascript_tool` result is cut at ~1,000 characters).

Use `ThreadingHTTPServer` for the receiver: a single-threaded one stays blocked on a request that never finishes
and every later POST hangs. A big POST from a heavy page sometimes arrives only after it is sent a second time (check
the file's size and time before trusting it). Some sites block `127.0.0.1` from their pages (Passline: every `fetch`
to it hangs, even a 5-byte one; Instagram blocks the `import` of `navegador.js` the same way): there, take the text out
with a fixed `<article style="position:fixed;inset:0;z-index:99999;white-space:pre-wrap">` appended to `document.body`
(not replacing the body) and read it with `get_page_text`, which only returns the first `article`/`main` of a page
(Time Out: `get_page_text` returns only the first item of the list, but the appended article carries the whole
`innerText`). To hand data *into* a page that blocks localhost, paste it in the `javascript_tool` text (slugs, not URLs).
When even a POST never arrives (Passline), an `<img>` GET does: split the JSON in ~4.5 KB chunks and request
`new Image().src='http://127.0.0.1:PORT/?i=N&d='+encodeURIComponent(chunk)` against a server that writes the `d`
parameter to `chunk_N.txt` (300 ms between chunks); join the chunks in Python. A page that keeps running a long
`fetch` loop must be the only tab and stay visible: Chrome throttles the timers of a background tab to a crawl, and
a `computer` `wait` in a batch keeps the tab busy while you wait.

**A frozen tab** (`CDP sendCommand "Runtime.evaluate" timed out after 45000ms`, usually after importing the tools
on a heavy single-page app): do not close the old tab first, because closing the only tab of the group drops the
group and the next call fails with "not in Claude's tab group". Call `tabs_context_mcp {createIfEmpty: true}`, use
the tab it returns and navigate again. Everything kept in `window` is lost; what was saved to `localStorage`
(per origin) survives a navigation inside the same site, so long collections can be stored there between pages.

## Patterns of known sites

- **WordPress + The Events Calendar** (`tribe-events` in the HTML): open
  `<sitio>/wp-json/tribe/events/v1/events?per_page=50&start_date=<from>&end_date=<to>` in the tab. It is JSON
  with `title`, `start_date`, `end_date`, `venue`, `cost`, `url`. If it responds 404, use `/eventos/` or
  `/events/` with `preparar`.
- **Wix**: loads slowly and in parts; `preparar` already waits, but if `largo_texto` stays low, wait 10 s
  more and repeat. Menus are sometimes in a "Más" dropdown: open it by hand and look at its links. Many Wix
  galleries answer 403 to `sondear.py --leer`: use the browser (`get_page_text`). Exhibition names are often
  links with no `href` in the DOM (click the card with a screenshot) and a gallery's "Galería"/"Ferias" pages can
  be only images: if the exhibition has no dates anywhere else, it is not loaded.
- **Linktree / Taplink** (Instagram bio): every button is a link. Open the ones that say agenda, cartelera,
  entradas, eventos, programación, or that go to a ticketing site.
- **Alternativa Teatral**: a venue's page lists its plays on stage with days and times; enter each play to
  see performance dates and price.
- **Ticketing platforms of a venue** (the link in the Instagram bio is usually one of these, and it lists every
  show with date and time, so there is no need to open Instagram):
  - Passline: `passline.com/sitio/<id-or-slug>` and `/productora/<id>` (the text lists "title, date, hour,
    venue" and the price). `sondear.py --leer` gets 403 here: open it in the browser. On a `/sitio/` page each
  show links to `/sitio-evento/<slug>` and on a `/productora/` page to `/eventos/<slug>`: from the same tab,
  `fetch` those URLs and read the prices in the text (`$ 6000`, the lowest is the "Desde"). The same text
  gives the day, so there is no need to open each page by hand.
  - Passline's full listing (`home.passline.com/eventos.php`): the button `#callEvents` ("VER MÁS EVENTOS") is
    a `<buttom>` that the generic "ver más" matcher does not find; click it from a JS loop (~3 clicks to pass the
    window, 1,181 cards). Each card is `div.row > div.col` with `a[href*="/eventos/"]` (desktop and mobile links
    repeat: dedupe by href). `fetch` of `www.passline.com/eventos/<slug>` works from the `home.passline.com` tab
    (4-5 in parallel, about 1 per second): `.donde` has venue, address and `C.A.B.A.`, and the lowest `$ N` in the
    text is the "Desde". The card title is cut with "...": `og:title` on the page has the full one.
  - Venti: `venti.com.ar/organizadores/<slug>` ("Próximos eventos", with date and hour).
  - Livepass `livepass.com.ar/taxons/<venue>`, Cafaccess `cafaccess.com/productora/<slug>` (date, title, price),
    Alpogo `alpogo.com/buscar?busqueda=<venue>`, Tickethoy (`bue.tickethoy.com` home lists all venues: filter
    by the venue line and press "ver más"), Evento Simple `compras.evento-simple.com/<venue>`, Enigma Tickets
    (one page per event).
  - Venues with their own ticketing site (culturalthames.com.ar, ccarmoza.com): weekly calendar plus an
    "Events" list that grows with "Load more" (click it until the last day passes the window).
- **Google Calendar embedded in a Google Site** (`iframe` `google.com/calendar/embed?src=<id>`): the public
  feed `https://calendar.google.com/calendar/ical/<id url-encoded>/public/basic.ics` is read with Python
  without the browser. A Canva "gacetilla" asks for login: it is not read.
- **Museums of the Ministry of Culture** (`museo*.cultura.gob.ar`, same platform for Casa de Ricardo Rojas,
  Mitre, Sarmiento, Malvinas, Histórico Nacional): `/actividades/` (cards with a date) and `/exhibiciones/`
  (current temporary, permanent), and each `/actividad/<slug>/` has "Horario" and "Entrada" (read them with
  `fetch` from the same tab). City museums (`buenosaires.gob.ar/gcaba_historico/cultura/museos/<slug>`)
  announce activities and openings as news on the home page, with day and hour in the body.
- **Venue whose own site is dead**: its page on Alternativa Teatral (`/espacioNNN-<slug>`) lists "Proximamente"
  with dates, and each play's page has day, hour and price.
- **Fanz ticketing sites** (culturalthames.com.ar, centroculturalmacedonia.fanz.com.ar): a weekly calendar with
  "Previous / Next" and an `Events` list. Click `Next` from JS (`[...document.querySelectorAll('a,button')].find(a=>/^next$/i.test(a.innerText.trim())).click()`,
  wait 2.5 s) for the next week, collect the `/event/<id>-<slug>` links from the `<a>` tags, and `fetch('/event/<slug>')`
  from the same tab: the HTML has the prices with `$` and `og:image`. An Instagram bio may write the domain as
  `.fanz.com` when it is `.fanz.com.ar`.
- **Fanz sites where the "Entradas" buttons are not links** (Club Cultural Matienzo): the home lists every event by date, but each
  button is a `<div>`: click it from JS (`[...document.querySelectorAll('*')].filter(e=>e.children.length===0&&/^\s*Entradas\s*$/.test(e.innerText))[i].click()`),
  wait 3 s and read `location.pathname` (`/event/<id>-<slug>`); navigate back to the home for the next one. Its `og:image` is the
  platform's logo (`white-label-logos-fanz`): never use it as the event's picture.
- **Tickethoy white-label sites** (tickets.congoclubcultural.com.ar, `/musica/<slug>`): a single-page app. Open each event in a hidden
  same-origin `iframe` (`f.src=h; await sleep(6000); f.contentDocument.body.innerText`) inside an async IIFE and poll `window.__done`;
  the page says `Entradas desde $X` (free events: `ENTRADA LIBRE Y GRATUITA`) and the photo is `api.tickethoy.org/images/eventos/<id>/imgn0000.jpg`.
  On the listing only the first cards have the picture in `src`; the rest are lazy (`data-src` holds the `<id>`): read `a.querySelector('img').dataset.src`
  after scrolling. Count on ~4 s per ficha (La Tangente: 12 events in two calls).
- **Bombo** (`wearebombo.app.link/<id>` redirects to `wearebombo.com/event/<id>`): 403 for Python; in the browser the page has the hours,
  the prices with `$` (they sometimes do not load) and `files.wearebombo.com/events/<blob>` as `og:image`.
- **Wix Events** (clubsocialcambalache.com): the home lists "Próximos eventos" with day and hour inside the title; each
  `/detalles-y-registro/<slug>` is rendered by JavaScript (`fetch` gives the shell); the picture is the `og:image` on wixstatic.
- **Instagram-only theatre whose posts are old**: find its page with `https://www.alternativateatral.com/teatros.asp?q=<name>` (the link is
  `/espacio<N>-<slug>`), read it with `sondear.py --leer` (current plays by weekday, "Proximamente") and put it in `web_nueva` (Zelaya).
- **Resident Advisor** (`ra.co/clubs/<id>`, `ra.co/events/<id>`): 403 over HTTP; in the browser `innerText` has the upcoming events, the date and
  hour of the ficha. Its `og:image` is an `imgproxy.ra.co/.../<base64>` URL: the base64 segment decodes to the real `https://images.ra.co/<hash>.png`.
- **Tiendanube** (La Ronda): `og:image` comes as `http://dcdn-us.mitiendanube.com/...`; `guardar` drops any picture that is not https, so change it to `https://`.
- **Alternativa Teatral venue page** (`/espacio<N>-<slug>`): lists the plays with links `/obra<N>-<slug>`; each one has `og:image`
  (`img.alternativateatral.com/scripts/es/fotos/obras/resumen/...`) but almost never the price over HTTP. Use it to get links and
  pictures when the venue's own site only shows days and hours (El Galpón de Guevara).
- **Programme as a JS page + HTTP fichas** (complejoteatral.gob.ar): `/agenda/` fills the cards with JavaScript, but the
  `/produccion/<slug>/` links read from the tab can be fetched with `sondear.pedir`: "Funciones", "Valor de las localidades", "Dónde" and `og:image`.
  Importing `navegador.js` hung that page for 45 s: use small snippets of your own.
- **Cinemas on Cinexo** (cinegaumont.ar): the day selector calls
  `https://apifront.cinexo.com.ar/mobile/consultas/peliculas/PeliculasConFuncionesYHorarios?idComplejo=<id>&fecha=DD/MM/AAAA`
  (the `idComplejo` shows in `performance.getEntriesByType('resource')`). `data.datos` are the films and
  `data.funciones` the showtimes (`codPelicula`, `hora`, `subtitulada`, `formato`). It is slow: run the loop over the days in
  an async IIFE that sets `window.__done` and poll it (a direct `await` of 14 days times out at 45 s). It has no prices.
- **Cinemas on GAF** (cineartecacodelphia.com.ar, a SPA that `fetch` cannot read): `https://apiv2.gaf.adro.studio/movie/<cine>/<id>` (both come from the
  film page URL `/pelicula/<cine>/<id>`) is JSON with `poster` (the picture), `descripcion`, `Duracion` and `showtimes`; read it with `sondear.pedir`,
  no browser needed. Check `imagen` is filled in before saving any cinema.
- **Passline `/sitio/<id>`**: the shows are in the text (title, date, hour) but the links to each show are
  `<a href="https://www.passline.com/sitio-evento/<slug>">`: read them from the `<a>` tags, then `fetch` each one for the lowest `$`.
- **Monthly agenda as a PDF** (Embajada del Japón: `AgendaCultural.html` redirects to `/files/<n>.pdf`): `get_page_text` finds no text and
  `curl`/Python get 403; open the PDF in the tab, scroll the viewer 9-10 ticks with `computer` `scroll` and read one screenshot per step (5 pages ≈ 8 screenshots).
  The viewer sometimes jumps back, so check the page number in the toolbar.
- **Calendars by month** (`?mes=`, `/2026/10/`, "siguiente" arrows): go through the current month and the
  next one if the 14-day window crosses into it.
- **"Actuales / Próximas / Anteriores" tabs**: open "Actuales" and "Próximas"; "Anteriores" can be discarded
  with the reason "archivo de muestras pasadas".

- **Month calendars where each day is clicked** (Centro Cultural Borges `/agenda`): loop over the day cells
  (`div.grid.grid-cols-7.gap-1 > *`), click each, wait ~800 ms and read `main.innerText` from the
  `MAR 20 OCT` heading on; one JS loop of ~10 s reads the whole window. The events have no link of their own:
  save the site with `"sin_fichas"` in `comportamiento`.
- **Pages `get_page_text` cannot read** (it returns only the footer or "no text"): wait ~10 s and read
  `document.body.innerText` with JS; for a long result, write it into `<article><pre>` and call `get_page_text`,
  which is not cut at ~1,000 characters.
- **Auto-mode classifier**: it denies a `javascript_tool` call that imports the toolkit from jsDelivr ("Code
  from External"), even with an allow rule for the tool. Importing from the local `crawl.py servir` server is
  accepted. If it denies that too, write small snippets of your own (or paste `navegador.js` inline) and
  ask the user before choosing, as the skill says for CSP.

## Where the picture is (`imagen`)

`scripts/imagenes.py` reads the pictures that are in the page's HTML. For the rest, in the browser (fetch each event
page from a tab of the same site, because Python gets 403 or only the app shell):

- **og:image in the page, 403 for Python**: Passline `/eventos/<slug>`, Fanz sites (Thames, Macedonia, Armoza), Malba is the
  exception (no og:image: take the first `<img>` that is not an SVG from `wp-content/uploads`), Fundación Andreani (first `<img>` of `/uploads/`).
- **Passline listing** (`/sitio/<id>`, `/productora/<id>`): each card has its `<img>`, `https://www.passline.com/imagenes/eventos/<slug>-<id>-rec.jpg`
  (the file name can be empty: `-788307-rec.jpg`); match it by the card's link.
- **Resident Advisor**: the og:image is an `imgproxy.ra.co` URL with the original in base64 after `quality:50/`:
  `atob(...)` gives `https://images.ra.co/<hash>.jpg|png`.
- **Tickethoy** (single-page app): open each event page and read the `<img>` `https://api.tickethoy.org/images/eventos/<id>/imgn0000.jpg`.
- **Museums of the Ministry of Culture** (`*.cultura.gob.ar`): the photo is a CSS background,
  `/media/uploads/site-N/destacados/.thumbnails/<name>/<name>-1500x0-no-upscale.jpg` (no og:image, no `<img>`). `imagenes.py` finds it.
- **Day-by-day calendars** (Centro Cultural Borges): clicking a day shows the cards of that day, each with its `<img src=/uploads/<uuid>.jpg>`
  and the title: go through the days and match by title (normalised, without accents).
- **Cinexo cinemas**: `https://firebasestorage.googleapis.com/v0/b/cinexo-lastipas.appspot.com/o/Peliculas%2F<idComplejo>%2F<codigo>%2Fprimario.png?alt=media`.
- **Not usable**: `http://` pictures (Centro Cultural Recoleta has no https; the website would block them), a venue's generic photo
  repeated in several events, and text-only sites (Casona Humahuaca's cycles, Feliza's agenda has no per-event image).

- **Passline `/sitio/<slug>` with `fetch`** (Cultural Morán, Club Conjura): each card's text has `"<title> #<tag> 24 de Octubre 2026 a las 21:00 <venue>"`;
  take the link from the `<a href*="/sitio-evento/">`, the picture from the `<img>` of the same card (`imagenes/eventos/<slug>-<id>-rec.jpg`),
  and `fetch` each page for the lowest `$ N >= 500` (no `og:` meta tags in that HTML). 17 pages take ~25 s.
- **Cinexo API from the tab** (Cine Gaumont): ~20-40 s per day and some days answer `Failed to fetch`; a second `fetch` while the loop runs
  froze the tab. Ask only for the days the site publishes (the selector shows ~9 days) and read `window.__out` with short calls.
- **Poster carousels as stacked images** (Torquato Tasso): scroll 5 ticks and `zoom` on the poster column (`region [320,0,1240,731]`, scale 0.45); posters
  come in date order, so stop at the first one past the window.
- **Wrong Instagram handle**: the profile page says "Sorry, this page isn't available": search Google for `<venue> instagram` (the result titles show
  the real handle: `lalala_ortuzar`, not `lalala.ortuzar`) and correct `sitios.json` and `lugares.json` too.

## If you change `navegador.js`

The local server (`crawl.py servir`) serves the file from disk, so the change applies on the next page load; the
jsDelivr fallback is pinned to the commit, so there the new version is only used once it is pushed. Test the cases it already covers: slow loading, infinite scroll, "cargar más" button,
cookie notices (known managers, shadow DOM, notices that appear late), newsletter and age windows, and links
to exhibitions inside the menu.
