# Browser tools

The tools are in [navegador.js](navegador.js) and are loaded into the tab with **a single line** (in Claude in
Chrome, with `javascript_tool`). There is no need to read or paste the code.

`python scripts/crawl.py iniciar` prints the line, with the jsDelivr URL pinned to the last commit of
`navegador.js` (`crawl.py herramientas` shows it again, and `siguiente` repeats the URL):

```js
(async () => { window.__agt || await import("https://cdn.jsdelivr.net/gh/<repo>@<commit>/.claude/skills/actualizar-agenda/navegador.js"); return window.__agt.preparar(); })()
```

To use another tool, change only the end: `window.__agt.esperar()`, `window.__agt.bloques()`, etc.
Every time you navigate to another page you must use the full line (the `window.__agt ||` avoids downloading
the file again while you stay on the same page). All tools return a JSON text and also leave it in
`window.__ag`: if a tool returns an empty promise or `{}`, wait a few seconds and run
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
run pastes it directly. If `crawl.py` says `navegador.js` has unpushed changes, the same applies: paste it
inline (or commit and push before starting).

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

What to know about the grid: it mixes the profile's own posts with posts of other accounts that tag it
(bands, producers, collaborators; their URLs start with another username), and many venues announce their
shows only there. The recent post ids start with `De` (October 2026): older ones (`Dd`, `Dc`, `DT`...) are
months old. Flyers without a caption are images: use `zoom` on the viewer (x 420-830) and, in a carousel,
click the arrow (about x 808, y 299) to see each day. "Sorry, this page isn't available" usually means a
wrong username (look the venue up on Google, correct `instagram` in `sitios.json` and `lugares.json`) and
sometimes a closed account.

## Patterns of known sites

- **WordPress + The Events Calendar** (`tribe-events` in the HTML): open
  `<sitio>/wp-json/tribe/events/v1/events?per_page=50&start_date=<from>&end_date=<to>` in the tab. It is JSON
  with `title`, `start_date`, `end_date`, `venue`, `cost`, `url`. If it responds 404, use `/eventos/` or
  `/events/` with `preparar`.
- **Wix**: loads slowly and in parts; `preparar` already waits, but if `largo_texto` stays low, wait 10 s
  more and repeat. Menus are sometimes in a "Más" dropdown: open it by hand and look at its links.
- **Linktree / Taplink** (Instagram bio): every button is a link. Open the ones that say agenda, cartelera,
  entradas, eventos, programación, or that go to a ticketing site.
- **Alternativa Teatral**: a venue's page lists its plays on stage with days and times; enter each play to
  see performance dates and price.
- **Ticketing platforms of a venue** (the link in the Instagram bio is usually one of these, and it lists every
  show with date and time, so there is no need to open Instagram):
  - Passline: `passline.com/sitio/<id-or-slug>` and `/productora/<id>` (the text lists "title, date, hour,
    venue" and the price). `sondear.py --leer` gets 403 here: open it in the browser.
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
- **Calendars by month** (`?mes=`, `/2026/10/`, "siguiente" arrows): go through the current month and the
  next one if the 14-day window crosses into it.
- **"Actuales / Próximas / Anteriores" tabs**: open "Actuales" and "Próximas"; "Anteriores" can be discarded
  with the reason "archivo de muestras pasadas".

## If you change `navegador.js`

Commit and push before the run: the jsDelivr URL is pinned to the commit, so the new version is only used
once it is on GitHub. Test the cases it already covers: slow loading, infinite scroll, "cargar más" button,
cookie notices (known managers, shadow DOM, notices that appear late), newsletter and age windows, and links
to exhibitions inside the menu.
