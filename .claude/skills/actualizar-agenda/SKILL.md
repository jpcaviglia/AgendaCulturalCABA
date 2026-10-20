---
name: actualizar-agenda
description: Updates the Agenda Cultural CABA by crawling ALL the sites on the list with the browser (venue websites, galleries, museums, aggregators and Instagram), loads the events of the next 14 days, records how each site behaves for the next run, builds data/eventos.json and publishes. Use when asked to update the agenda, crawl or re-crawl the sites, or when the scheduled routine triggers it.
---

# Update the Agenda Cultural CABA

The data is collected **with the browser**, except for what some scripts read with plain HTTP: `sondear.py`
(sites that do not need a browser, section 1b), `biolinks.py` (Instagram Linktree, 1b), `saleplan.py`
(SalePlan, section 7) and, inside `armar_agenda.py`, the missing addresses, the map and which sites can be
shown on the website (section 6). `crawl.py` does not visit any site: it keeps the queue, validates what you
found and saves what was learned.

Work from start to finish without asking for confirmation. Talk and write in English, except for the data you
save (event titles, descriptions, categories, prices, site notes, `comportamiento` values and the run
report), which stay in Spanish as the sources show them. Field names, `estado` values and script messages
are Spanish identifiers: use them exactly.

## Rules that are not negotiable

1. **Every run goes through all the sites, except the ones crawled today or yesterday.** A site with a
   capture from today or yesterday in `data/crawl/capturas/` is not opened again: `crawl.py iniciar` marks it
   `reutilizado` and that capture stays published. For the rest, what happened in earlier runs (`ultimo`,
   `notas`, `comportamiento`) says *how* to crawl a site, never *whether* to crawl it. A site that had no
   events last time, or did not load, is opened again anyway. Do not use `iniciar --nueva` to "start from
   scratch": it resumes or builds the queue by itself; `--todos` (also crawl today's and yesterday's) only
   if the user asks.
2. **"There are no events" is a conclusion that must be proven.** Before marking `sin_eventos` or
   `sin_agenda` you must have opened every link to agenda, muestras, exposiciones, exhibiciones, cartelera,
   programación, actividades, ciclos, talleres, visitas or ticketing that appears on the site (menu, home
   page, footer), strong and weak, scrolled every listing to the end and pressed its "ver más" buttons. If
   the site **does** have events, the strong links are enough (section 3.2). `crawl.py guardar` rejects the
   result if any of that is missing.
3. **A slow site is not a dead site.** Wait up to 30 s, reload, try URL variants. Only after 3 failed
   attempts is it marked `no_carga`, and it is tried again in the next run.
4. **Do not make up data.** If the title, date or venue is missing, the event is not loaded. If the time or
   price is missing, leave it empty.
5. **Write down what you learned** about each site (where the agenda is, how long it takes, whether you
   have to scroll, which button expands, which new links you found). The next run starts from that. What is
   useful for more than one site, or for the process, goes into this skill at the end (section 7, "Lecciones
   de la corrida").

## Tools

- Browser: the Claude in Chrome tools (`navigate`, `javascript_tool`, `get_page_text`, `computer`, `find`,
  `tabs_context`…). If they do not show up, load them with ToolSearch (`chrome`). Use a single tab of your
  own for the whole crawl.
- Ready-made, tested JS tools: [navegador.md](navegador.md) says what each one does; read it at the start.
  The code is in `navegador.js` and is **not pasted**: first start `python scripts/crawl.py servir` in the
  background (it serves the file on 127.0.0.1; the auto-mode classifier denies the jsDelivr import as
  external code), then load it with the line that `crawl.py iniciar` prints (changing only the call at the end). The most used are `preparar()` (wait + cookies + scroll + "ver
  más" + classified links), `bloques()` (cards with a date) and `esperar()` (event pages). To read a listing
  use `bloques()` before `get_page_text`, and take screenshots only when the information is in an image or a
  notice cannot be closed.
- Log: `python scripts/crawl.py ...` (on Windows it may be `py` instead of `python`).

## 1. Start or resume

```bash
python scripts/crawl.py iniciar
```

`iniciar` builds the queue with all the sites in `data/crawl/sitios.json` and counts as done the ones with a
capture from today or yesterday. If there is an open run from the last 3 days, it resumes where it left off
(you do not start from scratch if the previous session was cut off). It also prints the line that loads the
browser tools: keep it, it is used on every page.

### 1b. Read without a browser whatever can be (always, before the browser)

```bash
python scripts/sondear.py --corrida
```

Requests the pending sites with plain HTTP (about 2 minutes, without spending browser tokens):

- **api / jsonld**: if they give events in the window, it saves them by itself (`con_eventos`) and they leave
  the queue. Before saving it opens each event's own page (up to 80 per site) to fill in the price, picture and
  time the listing lacks. Events whose JSON-LD has no `url` of their own stay without link, price or picture
  (the report counts them as `sin_enlace_propio` in `data/crawl/local/sondeo.json`); if the site's listing
  links an event page (`/eventos/<slug>`), open it and add the data by saving the site again.
- **html**: leaves the text of the home page and of the agenda pages in
  `data/crawl/local/textos/<id>.txt`.
- The rest (`needs_browser`, `unreachable`, `sin_agenda_vista`) goes to the browser as usual.

It never marks a site empty: if it found no events, the site stays in the queue. If the run is resumed on
another day, run it again (`siguiente` warns when a recent probe is missing).

Then look for the Instagram Linktrees (without opening Instagram, so it costs no quota):

```bash
python scripts/biolinks.py
```

It tries `linktr.ee/<account>` for every Instagram without an `enlace_bio` and saves the ones it finds. It
only tries the new ones (or the ones not tried for more than 60 days), so it is usually quick.

## 2. Go through the queue

**At most 20 sites per session.** A session crawls up to 20 items from the queue (websites and Instagram
profiles both count; sites saved by `sondear.py --corrida` and `reutilizado` ones do not), then publishes a
progress update (section 6, after writing down the lessons of the session and updating the docs) and stops. The next session runs `crawl.py iniciar` and resumes the open run
where it left off. Only the session that empties the queue goes on to section 7 and closes the run.

Repeat until the queue is empty or you have crawled 20 sites in this session:

```bash
python scripts/crawl.py siguiente 3
```

It shows the next sites with everything known about them: `web`, `instagram`, `enlace_bio`, `entradas`
(agenda pages that worked before), `comportamiento`, `notas`, `enlaces_pendientes` (links that were seen and
not opened), `enlaces_descartados` (already seen not to be useful, with the reason: do not open them) and
`ultimo`. Read it before opening the site. Notes saying "el script viejo lo marcó ... NO es confiable" come
from a checker that did not open the pages: ignore that conclusion and review the site thoroughly.

If the site has `sondeo`, follow its `pista` before opening the browser. With `clase: html`, read the
`texto` file (it has the site's links as `texto [url]`) and load the events from there; the `paginas_agenda`
read go in `urls_visitadas` and `enlaces_candidatos` (`visitado: true`). Open the browser only for what the
text does not solve: event pages with the closing date, posters in images, or a site where the text shows no
events (to mark it empty you have to review it in the browser, rule 2).

**Reading other pages without a browser.** The probe's text has the home page and up to 5 pages, cut at
~30,000 characters: often the complete agenda is on another page of the same site. Request it with

```bash
python scripts/sondear.py --leer <url> [--desde "<text>"] [--max N] [--timeout 45]
```

which prints the status, the page's JSON-LD events and the text with the links. What worked:

- the month filter or the full calendar (`?filtro=mes`, `/calendario/`), not the week view;
- pages per day (`funciones-AAAAMMDD.html`) when the listings only say "SÁB 20 HS";
- the page of each play or activity for days, time, premiere, last performance and price;
- The Events Calendar listing (`/eventos/`) carries JSON-LD even if the API is closed (403);
- dates in the event page URL (`…-jueves-22-de-octubre-21-h-2026/`);
- on ticketing sites like revamos.com, the dates of a play with several performances are in the page code
  (`ticketsByDate`);
- the pages of the ticketing platforms that venues link (Venti, Livepass, TicketHoy-like) carry JSON-LD with
  `startDate` (with its UTC offset), description, image and `Desde $` in the text: take the listing from the
  venue's own page and read each event page with `sondear.pedir` + `sondear.objetos_evento` in a Python
  one-off (Niceto Club: the venue's `/agenda/` HTML has day sections and cards, the price is on venti.live);
- `sondear.pedir` can decode a non-UTF-8 page (`centrocultural.coop`) with `�` in accents: fix the titles by hand before
  saving (`guardar` stores them as they are).
- Centro Cultural Borges: run `python scripts/borges.py` (reads its API, writes `data/crawl/tmp/centro-cultural-borges.json`) and save
  that file with `crawl.py guardar`; no browser needed.
- A calendar app whose cards have no links (Centro Cultural Borges: clicking a card goes to `/evento/<id>`) loads its data from a
  JSON API: read `performance.getEntriesByType('resource')` after clicking (print the names with `[?=&]` replaced), then request the API over
  HTTP with `Accept: application/json` and a `Referer` header. It gives every event's id, so each event links to its own page.
- a Venti organizer page (`venti.com.ar/organizadores/<slug>`, the `Eventos` link of Under Club) is empty over HTTP: open
  it in the browser, read it with `get_page_text` and `fetch()` each event page from there (JSON-LD `offers`, `image`);
- the Ministry of Culture museum platform (`museo<x>.cultura.gob.ar`: Rojas, Mitre, Sarmiento, Malvinas, Histórico
  Nacional) answers over HTTP: `/actividades/` lists the fichas and each ficha has `¿Cuándo?`, `Horario` and
  `Entrada`; `/exhibiciones/` mixes current, permanent and past, so only an exhibition with a closing date is
  loaded. Run `scripts/imagenes.py <id>` afterwards for the pictures (CSS background);
- the Buenos Aires City museums (`buenosaires.gob.ar/gcaba_historico/cultura/museos/...`) publish their
  activities as news cards whose links are not in the text: open the page in the browser and `fetch()` each
  news item from there, or search for the permanent guided tours (weekday and hour) in the "Información
  general" block and load them with `vigente_sin_fin: true`;
- a site where `sondear.py --leer` times out is retried with `--timeout 90`; inside a Python one-off set
  `sondear.TIMEOUT = 60` (Otra Historia, Museo Etnográfico).

If a JSON API answers over plain HTTP (Ticketek's `prod-cms-api.ticketek.com.ar`), do the fetching in a Python
one-off and use the browser only to render the pages that list the links; if the data only exists in the page,
send it out with the local receiver ("Getting a big result out of the page" in `navegador.md`) instead of
reading it back in ~1,000-character pieces.

Paginated listings are not always in date order: go through `page/2`, `page/3`… until everything falls after
the window. If the site is slow, `--timeout 45` (and note `espera_seg`). What does not come out this way
(dates only in Plateanet or another app, posters, press releases in images) is left for the browser: do not
save the site with half the agenda, because it leaves the queue.

If you save the same site twice in a day (to correct something), the new note replaces the previous one and
a link that becomes `visitado: true` is no longer discarded.

For each site: crawl it (section 3 or 4), write the result in `data/crawl/tmp/<id>.json` (format in section
5) and save it:

```bash
python scripts/crawl.py guardar data/crawl/tmp/<id>.json
```

If it answers **NO SE GUARDÓ**, go back to the browser and do what it says (open the missing links, scroll,
retry). Do not change the status to get around the validation.

Save each site as soon as you finish it: if the session is cut off, what was saved is not lost.

A site that needs one read per event and cannot be finished in reasonable time (Centro Cultural de la
Cooperación: monthly pages by discipline, weekday-only functions) is not saved half done: leave it in the
queue for the next session and say so in the progress update. Huge sources (Passline: ~1,100 pages) take
about 25 minutes of fetching, so count them as several sites of the session's time. A Bash heredoc with
accents and `¡«»` can fail: write the script with the Write tool and run it. If the browser JS tool or Bash
answers "no verdict" from the auto-mode classifier, retry once as-is; the `computer` `zoom` action on a
region of the page reads small widgets (day tabs, times) without JavaScript.

After the 20th site, do the "Lecciones de la corrida" review (section 7) for this session: move what you
learned to the skill, `navegador.md`, the scripts and the docs (`README.md`) as CLAUDE.md requires. Then publish
a progress update (section 6) with those changes in the same commit and end the session. That way the page,
the lessons and the docs are up to date after every session even if the run takes several.

## 3. Crawl a website

**Sites with no website or Instagram** (museums and galleries from the reference list, or venues that are
missing everything): `siguiente` shows them with a `tarea`. Search Google for `"<name>" Buenos Aires`,
confirm the official website (not a directory or an article), that it is in CABA and still open, and put
`web_nueva`, `instagram`, `barrio` and `direccion` in the result. Then crawl that website in the same turn
like any other (the rest of this section). On saving, the script adds it to `lugares.json` (and to
`galerias.json` if it is an art venue). If it does not exist, closed or is not in CABA, save
`{"id": ..., "descartar": "<reason>", "evidencia": "<what you searched and what you found>"}`: it is removed
from the lists and recorded in `data/crawl/descartados.json` so it is not added again. The same goes for any
site you confirmed closed.

### 3.1 Open and wait

1. Open the first URL in `entradas` if there is one; otherwise `web`. If there are `enlaces_pendientes`,
   open them too.
2. Run `preparar`. If `comportamiento.espera_seg` says the site is slow, wait that long first. `preparar`
   also closes cookie notices and newsletter, notification or age windows (it prefers "rechazar" or "solo
   necesarias"), and repeats this while it scrolls. Look at `popups` in the result: if it says `iframe de
   consentimiento`, or if the screenshot still shows something covering the page, close it with a click and
   run `preparar` again. Never mark a site as empty or down because a notice was covering the content.
3. If `largo_texto` is very small or the page shows an error:
   - attempt 2: reload, wait 10-15 s more and run `preparar` again;
   - attempt 3: try the variant (`www`/no `www`, `http`/`https`, the home page if you were on a section, or
     the agenda URL if you were on the home page);
   - if an attempt loads, continue normally and note in `comportamiento` how long it took;
   - if none loads: `no_carga` with `intentos: 3` and the `evidencia` (what it showed).
   - Domain that does not resolve, parked, for sale, suspended account or redirecting elsewhere:
     `dominio_caido`. First search Google for `"<name>" Buenos Aires` to find the new website or the
     Instagram; if you find it, crawl it in the same turn and put `web_nueva` or `instagram`.
   - Captcha, mandatory login or 403: `bloqueado` with `evidencia`. Do not try to solve it.
   - A `web` that is only a Facebook page: it shows "content isn't available" or one old post, and the rest
     needs login. Save `bloqueado` (or `sin_agenda` if it loads with stale posts) with that evidence and the
     Instagram channel gets queued by itself.
   - A site that moved (404 on a government page, `sites.google.com` 404, a blog that stopped years ago):
     search Google for the venue first; the new address is often on the venue's Alternativa Teatral page or
     in `baespacios.buenosaires.gob.ar`. Put it in `web_nueva`. A domain that changed hands (the page now
     talks about something else) is recorded in the `nota`.

### 3.2 Find all the listings

The home page is almost never enough: it usually shows a single exhibition or the next three events.

- `preparar` separates the agenda links of the same site into `secciones` (strong: agenda, cartelera,
  programación, eventos, actividades, muestras, exposiciones, shows, funciones, obras, próximas, talleres,
  cursos, clases, seminarios, visitas, recorridos…) and `debiles` (ciclos, actuales, temporada, festival,
  cine, inauguración). Talleres and visitas are strong because many sites publish them on their own page,
  which the agenda does not show. All go in `enlaces_candidatos`; the weak ones with `"debil": true`.
- The ones in the site's `enlaces_descartados` were already discarded in another run: do not open them (the
  script puts the saved reason on them). They are reviewed again by themselves every 6 months.
- **Strong: open each one** and run `preparar` on it. Inside each section, the tabs or filters "Actuales",
  "Próximas", "Este mes", "Hoy", "Semana" are more sections: open them.
- **Weak:** if the site already gave events through the strong links, there is no need to open them (they
  almost always repeat what is in the agenda). If in the end you found no events, open them all before
  marking `sin_eventos` or `sin_agenda`. Open a weak one anyway when its text makes clear that it has its
  own programming that the agenda does not show (for example a "Cine" with its own weekly listings).
- Also look at dropdown menus ("Más", "☰", "Programación ▾"): open them with a click and run `preparar`
  again if new links appear.
- Follow pagination ("siguiente", `?page=2`, next month's calendar) until the next 14 days are covered.
- If two links lead to the same listing (`/agenda` and `/eventos` show the same), open one and discard the
  other with "misma página que /agenda".
- A candidate can only be discarded with a concrete reason: "archivo de muestras pasadas", "es la tienda",
  "convocatoria, no evento", "es la colección", "es la misma página que /agenda". "Looked empty" is not a
  reason. Discards are remembered in the next run, so the reason has to still be true next week.

### 3.3 Read the events

- If `eventos_jsonld > 0`, use `jsonld()`.
- Otherwise, use `bloques()` on each listing (or `get_page_text` only if `bloques` does not capture the
  structure well).
- Enter the page of an event or exhibition (`fichas`, with `esperar()`) when the listing lacks the complete
  date (start and end of an exhibition), venue or room, time or price. In galleries and museums the closing
  date is often only on the event page: enter the ones for **current or upcoming** exhibitions (not the
  archive or the artists' pages).
- **Price and picture come from the event's own page.** Listings (and the `sondear.py --leer` text of an
  aggregator) usually show title, venue and date only, and the page has the price and the picture. Do not
  save `precio` and `imagen` empty because the listing lacks them: open every event page (in the browser, or
  over HTTP with `sondear.pedir` and `sondear.objetos_evento`: its JSON-LD has `offers.price` and `image`, and
  `og:image` is the fallback; Eventbrite pages give no price over HTTP: read the `ARS` amount in the browser text)
  and fill both in. An empty `precio` is only right when the page itself shows
  no price (or "Consultar"). When a listing has hundreds of events (Alternativa Teatral, Passline), do this
  at least for the ones in the next 7 days and say in the `nota` that the rest has no price yet.
- From an event page, follow the link to tickets or "más info" if the performances or the price are there.
  Maximum depth: 3 levels from the listing, same domain or ticketing site.
- If a listing has its information in images (posters) without text, take a screenshot and read it.
- Keep the list of URLs already visited to avoid repeating. They all go in `urls_visitadas`.

Which kinds of events: everything open to the public and of cultural or leisure interest, **including techno
and electronic parties, club parties, raves and open airs, festivals (music, film, theater, tango, jazz, art,
neighborhood) and fairs (design, art, books, vinyl, food, crafts, second-hand clothes)**, as well as theater,
music, film, exhibitions, dance and talks. **Talleres, open classes, seminars, courses and workshops on art
or culture** (painting, ceramics, writing, photography, theater, dance, music, film, etc.) and **guided
tours and walks** (of museums, exhibitions, buildings or neighborhoods) are also loaded, whether free or
paid and even if they require registration: look for them in their own section even if the site already gave
events in the agenda. A workshop or course that lasts weeks or months goes as a single event with
`fecha_inicio`, `fecha_fin` and `horarios`, if it starts within the window or has open registration in it
with published dates. Private events (visits for schools or groups that book, internal workshops),
commercial or business courses, and sports matches or competitions are not loaded.

When: whatever is ongoing or starts within the next 14 days (`siguiente` shows the window). An exhibition
that started in August and closes in December is current and is loaded. A play with performances every
Friday of October is a single event with `fecha_inicio`, `fecha_fin` and `horarios`. An opening with its own
day and time goes as a separate event.

- A play **on stage** that only gives the day of the week ("SÁBADOS 19 HS", no dates): `fecha_inicio` and
  `fecha_fin` are the first and last of those performances within the window, and `horarios` the original
  text. If it says "última función" without a date, it is not loaded.
- Permanent guided tours (every day, or "lunes 11 h" with no announced end): one event with
  `vigente_sin_fin: true`, `fecha_inicio` the premiere date if given or today's, and the times and prices.
- **Virtual** or online events: not loaded, even if the organizer is a CABA venue.
- **Recurring cycles** published only by periodicity ("3er martes de cada mes", "último sábado", "todas las
  semanas"): compute the dates that fall in the window and load one event per date, or one event with
  `horarios` if weekly. A cycle whose text names a past period ("todos los lunes de Marzo 2026") or a
  workshop list that says "programación definitiva a fin de marzo" is stale: do not load it, say so in the `nota`.
- **Cinemas and listings with a day selector** (one page per film with tabs by day): read every tab. Films
  differ: some open today and others only on Friday or Sunday, so never copy one film's dates to the rest.
- **A venue's own agenda is out of date but its ticketing page is not** (Casa Brandon: `/agenda/` stopped on
  the 18th, Passline had the next two weeks): load from the ticketing listing, with the venue as `lugar`, and
  say it in the `nota`. The Passline data already read for the Passline site can be reused for this.
- **Weekly bar programming** (trivias, bingos, "pizza y vino libre", Tinder Night, chess tournaments) is
  loaded only when it is cultural (talleres, charlas, degustaciones, karaoke, ciclos); say what was left out
  in `comportamiento`. A current exhibition with no closing date anywhere is not loaded.
- A listing or poster with a date but **no year** (`viernes 18/10`, `jueves 3/3`): check that the weekday matches 2026 (18/10/2026
  is a Sunday) and, on a blog, the year in the post URL (`/2016/09/…`); if it does not match, it is an old post: do not
  load it, and say in the `nota` that the agenda is stale.
- A museum whose home page or Instagram bio says "cerrado por montaje" and whose posts carry no dates is
  `sin_eventos` with that as `evidencia`.

### 3.4 New links

- `externos` from `preparar` that are another cultural venue in CABA (gallery, museum, theater, cultural
  center, cinema, club or nightclub with an agenda) and are not in the queue: add them in `sitios_nuevos`. A
  producer or itinerant party that changes venue goes with `"tipo": "agregador"`. The script adds them to
  `sitios.json` and to `lugares.json`/`galerias.json`, and puts them in the queue of this same run. Confirm
  they are in CABA; do not add venues from other cities.
- Pages of the same site that you did not get to open and could have events: `enlaces_nuevos`.
- The pages where the events actually were: `entradas` (the next run starts there).

## 4. Crawl Instagram

Instagram is crawled for venues with no website, and for those with a website when the website gave no
events (the script queues them by itself). `siguiente` spreads the Instagram profiles evenly among the
websites, so the quota is spent along the whole run and there is no backlog of profiles at the end: when
`siguiente` returns an Instagram item, crawl it right then, like any other. Use the browser's already
logged-in session; do not log in or create accounts.

**Limits.** Instagram throttles accounts that open many pages in a row, so the script keeps a quota and not
all the profiles fit in each run: they rotate, the longest-unchecked first.

- Daily quota of Instagram pages (profile + each opened post), 150 by default. `siguiente` shows what is
  left; when it runs out, it leaves the remaining profiles as `pospuesto` (the websites go on) and they go
  first next time.
- If a profile is saved as `bloqueado`, Instagram is not opened for 24 h (cool-down): the pending profiles
  stay `pospuesto`. Do not try to continue with another profile.
- Every 25 pages, `guardar` asks for a 5-minute pause: take it (or continue with websites, if any remain).
- The limits are adjusted in `data/crawl/local/instagram_estado.json` (`limites`).

**Before opening Instagram, always: the bio link.** If the site has an `enlace_bio` (`biolinks.py` finds
most Linktrees, section 1b), read it without a browser: `python scripts/sondear.py --leer <enlace_bio>`. For
a Linktree it shows each link as `title [url]`; many list each show with the date in the title and the link
to the ticketing site, which is read the same way (`--leer <url>`). If the window's agenda is there, save
the `instagram` channel with those events, `enlaces_candidatos` = the visited bio link, `posts: []` and
`paginas_instagram: 0` (it spends no quota), and note in `comportamiento` that the agenda is in the bio. If
the site has no `web` and that page lists the venue's whole agenda (its ticketing page, own calendar or a
Linktree with dates), also put it in `web_nueva`: from the next run the site is crawled as a website and its
Instagram is only queued when that page gives no events, which saves quota for the profiles that publish only
on Instagram. Only if the bio is not enough, open the profile. The link is very often a ticketing page or the venue's own
calendar (list in `navegador.md`, "Ticketing platforms of a venue"): open it in the browser, because
`sondear.py --leer` gets 403 on Passline and cannot run JavaScript. In a run, about a third of the Linktrees
gave the whole window this way. A bio link with a stale agenda (old dates) or a login-gated Canva is not
enough: go on to the profile.

The bio link can also be the venue's page on All Access (`allaccess.com.ar/venue/<slug>`: every show with its
date, no hour or price) or on Alternativa Teatral (`/espacioNNN-<slug>`: current plays by weekday and
"Proximamente"; if it only lists "Archivo histórico" there is no current programming). Both are read with
`--leer`. Check where the bio link lands before trusting it: a domain can change hands (pasaje17.com.ar now
shows a casino page); save that website as `dominio_caido` with that evidence and keep crawling the Instagram.
A venue that only has an Instagram, and whose bio link is a working official website, goes in `web_nueva`.

**Budget.** A profile costs 3-6 pages (profile + 2-4 posts), so only ~25-30 profiles fit in a day. Spend the
quota first on bars, clubs, theaters and venues that announce shows on Instagram, and leave community
organizations (political groups, murgas, associations) for the end: their posts are usually communiqués.

**Posts already analyzed.** `data/crawl/local/instagram_posts.json` (only on this machine, not pushed to the
repository) holds every opened post with the events it had. Do not open them again:

1. Open `https://www.instagram.com/<usuario>/`, wait 3-5 s and run `instagram_perfil`. If a cookie dialog
   ("Rechazar cookies opcionales") or a notifications dialog ("Ahora no") appears, run `popups` or close it
   with a click. If `pide_login` is true or a captcha appears: `bloqueado` and move on to the next one. If
   it says "Sorry, this page isn't available" the username is probably wrong: look the venue up on Google
   and correct `instagram` in `sitios.json` and `lugares.json` (the handle `@ba.gops` of 14 city cultural
   centers was `@gops.ba`); if the account was really closed and the venue too, `descartar` it with the
   evidence. Do not mark a site down because of a wrong handle.
2. Pass the `posts` URLs to the script: `python scripts/crawl.py ig-vistos <id> <url1> <url2> ...`
   Open **only the NEW ones** (up to ~9) and the "Agenda", "Cartelera", "Programación" highlights if there
   are any. Run `instagram_post` on each. Use `publicado` to deduce the year of dates like "sábado 18". If a
   new post is more than 2 months old and the earlier ones too, there is no need to keep going down.
3. If the text has no date, look at the poster (screenshot). A post that is a carousel ("Este finde", "Octubre") usually has the
   agenda on the 2nd image: click the arrow and read the screenshot. If a screenshot or JS call times out, the tab's renderer is
   frozen: open a new tab (`tabs_create_mcp`, then `tabs_context_mcp`) and continue there.
4. Follow the bio link (`bio` or `enlace_bio`): Linktree, ticketing site or website. Apply section 3.
5. In the result put:
   - `posts`: **all** the grid post URLs you considered, new and already seen, with `publicado` if you know
     it: `[{"url": "...", "publicado": "2026-10-10"}]`. The script adds by itself the current events from
     the posts already seen, so do not copy them.
   - in each event, `"post": "<post url>"` where it came from (so it can be reused).
   - `paginas_instagram`: how many Instagram pages you opened on this profile (profile + posts +
     highlights). If you leave it out, it counts as 1 + the new posts.
6. Pace: wait 4-10 s at random between actions and between profiles. Natural scrolling, no bursts, no
   opening internal endpoints. At the first "intentá de nuevo más tarde", action limit or captcha, save
   that profile as `bloqueado` (with `evidencia`) and continue only with websites.
7. To find posts without logging in: Google `site:instagram.com/p/ "<venue>"`.

On Instagram, `scroll_completo: true` means you saw the last ~9 posts (new or already seen); the
`enlaces_candidatos` are the bio and the agenda highlights.

## 4b. Aggregators and discovery sources

- **Turismo BA**: use `turismo()`. It returns the events already in the result format (with
  `vigente_sin_fin` set): copy its `eventos` as is into the file, without rewriting them. Without the
  browser, the same array (`[{"orden"...`) is in the HTML that `sondear.pedir` returns: parse it with
  `json.JSONDecoder().raw_decode` and apply the same mapping.
- **SalePlan**: **it is not opened in the browser.** It is read at the end with
  `python scripts/saleplan.py` (section 7): it reads the listings over HTTP and saves only what no other
  source brought, with no venue. If `siguiente` shows it, skip it. Only if the script says it could not
  read the listing, open the `entradas` with `preparar`. Cards with no neighborhood or time are left in
  `data/crawl/tmp/saleplan_fichas.txt`: if there is time left, open those pages to find out the venue.
- **Resident Advisor**: parties and electronic agenda. Go through the 14 days, open the pages with no club
  and add new clubs and producers in `sitios_nuevos`.
- **Discovery** (Arte al Día, Gallery, Indiehoy, Time Out, Meridiano): useful to find venues and
  exhibitions that are not on the list. Load the CABA exhibitions that appear with dates, and add the new
  venues in `sitios_nuevos`.
- **Searches** (techno and electronic parties, festivals, fairs, missing museums and galleries): the four
  `busqueda-*` entries in `sitios.json` are marked `"rastrear": false` because their sites were already
  collected, so they are not in the queue. To run one again, set its `rastrear` back to true. They are Google
  searches; `comportamiento.consultas` has the queries: add the month and year,
  open the first useful results, load the window's events with their `lugar`, and add in `sitios_nuevos`
  the clubs, organizers, festivals, fairs, museums and galleries that publish their own agenda, so they are
  crawled directly from then on. Before adding one, check with `crawl.py ver <name>` that it is not already
  there.
- **Ticketing sites and agendas** (Alternativa Teatral, Eventbrite, Ticketek, Passline, Indiehoy, Time Out):
  follow the `entradas` and `comportamiento` of each. Load only events in CABA, cultural, within the window.
  Go at a human pace (pauses of 2-4 s between pages); on captcha or 403, `bloqueado`. CABA theaters or
  venues that appear and are not on the list go in `sitios_nuevos`.
- **Cover the whole window.** In a listing ordered by date (Passline, for example, lists the whole
  country), continue until the dates pass the last day of the window: do not cut by number of pages or out
  of tiredness. If you have to cut, save what you read anyway but say so in the `nota` ("leído hasta el
  17/10") so the next run continues from there. Never write "N eventos en la ventana" if you did not cover
  it.
- If a venue has its own page on a ticketing site (`passline.com/sitio/<id>-<venue>`), that page is the best
  `web` for that venue: it lists only its events.
- In aggregators and discovery sources the `lugar` of each event is mandatory: the name of the venue where
  it takes place, identical to the one in `data/lugares.json` if it is there.
- A site with `"rastrear": false` in `sitios.json` does not enter the queue. It is only marked that way if
  the user asks (today: Paseo La Plaza, whose programming arrives through the aggregators, the four
  `busqueda-*` Google searches, whose sites were already collected, and the theatres whose programming is
  published on Alternativa Teatral, which is crawled as an aggregator: Teatro del Pueblo, Cervantes, Picadero,
  Timbre 4, UPB, Caras y Caretas, Fray Mocho, Cultura Faro, Eureka, IMPA, El Deseo and El Método Kairos). A theatre
  found later whose notes say its programming is on Alternativa Teatral is not added to the queue either.
  Also marked on 2026-10-20, at the user's request: 78 sites (44 + 34 later) whose every channel (website and Instagram) was
  crawled in the open run and had no events (`sin_eventos`, `no_carga`, `sin_agenda`, `no_cultural`,
  `descartado` or `dominio_caido`). A site whose website came up empty (`sin_eventos`, `sin_agenda`, `dominio_caido`) and that has an Instagram is marked `"rastrear_web": false` (user's request, 2026-10-20): the run queues only its Instagram, and `sondear.py` skips its website. Set it back to true if the website changes.

## 5. Result format

One JSON object per site and channel in `data/crawl/tmp/<id>.json`:

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
    {"texto": "Archivo", "url": "/es/archivo", "descartado": "archivo de muestras pasadas"},
    {"texto": "Visitas", "url": "/es/visitas", "debil": true}
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

- `estado`: `con_eventos`, `sin_eventos` (there is an agenda but nothing current or in the window),
  `sin_agenda` (does not publish programming on this channel), `no_cultural`, `no_carga`, `dominio_caido`,
  `bloqueado`. (`pospuesto` is set by the script on the Instagram profiles that did not fit in the quota.)
- Instagram only: `posts`, `paginas_instagram` and `post` in each event (section 4).
- `enlaces_candidatos`: each with `visitado: true`, `descartado: "<reason>"` or, if weak and there were
  events, `debil: true` without opening. The `url` can be the path `preparar` returned (`/agenda/`).
- `evidencia`: mandatory for `sin_eventos`, `sin_agenda`, `no_cultural` and failures. Example: "/muestras
  lista 14 muestras, la más reciente cerró el 2026-09-30; /agenda vacía; sin próximas".
- `eventos[].lugar`: empty only if the site has a single venue (it fills in by itself). On sites with
  several venues, aggregators and third-party Instagram accounts it always goes. Same name as in
  `data/lugares.json` or `data/galerias.json` so they deduplicate well. If the event is in another room,
  `"<Lugar> · <Sala>"`.
- Dates `AAAA-MM-DD`; `hora` `HH:MM` (just one; if there are several, in `horarios`).
  `horarios` is how the website decides which days an event runs: write the weekdays first and the hours next to them
  (`Jueves a domingo 19:00 y 20:45`, `Jue y vie 21 h. Sáb 20 h`, `Martes a sábados de 11 a 19 h`); text with only specific dates
  (`Sábados 10, 17 y 24 de octubre`) is read as one event that starts on `fecha_inicio`. If it does not give
  the year, assume the current one only if the date does not end up in the past; if in doubt, do not load
  it.
- `categoria`: copy the label, genre or category the source shows ("Cine", "Teatro", "Rock", "Stand up",
  "Géneros: teatro"), even if it is not one of the categories: the script translates it. Empty only if the
  source shows none and it is not obvious. For galleries, `Artes visuales`. Without a label, the event stays
  as "Evento" unless the title or description say otherwise: do not leave the description empty or with
  generic text.
- `precio`: "Gratis", "$ 8000", "Desde $ 5000", or empty only if the event's page shows none (section 3.3). `url`: the event's own page (the link of its card
  in the listing) or its tickets page; the Instagram post only if there is no other. Never the listing, agenda
  or home page: `guardar` rejects the result when at least half of the different events (by title; several
  dates of one play may share a page) share the same URL, with 3 or more events for any page, or 2 or more if
  it is the site's website or a page you visited. If it rejects, the crawl did not go deep enough: open each
  event's page, do not just add `sin_fichas`. Take each card's link from `bloques()` (it returns the `url` of every card) and
  open the event pages: they often have the hour, the real venue (another room, another city) or say the
  event is online, which the listing does not show. Only if the source has no page per event (a PDF, a
  Linktree, an article listing several shows, a ticketing page without links per show), say so once in
  `comportamiento`: `"sin_fichas": "<reason>"`. It is saved for the site and the check is not applied again.
- `imagen`: absolute https URL of the event's picture, shown next to it on the website (it is linked,
  not downloaded). Copy it from `bloques()` (the card's picture), `jsonld()` or `esperar()` (`og:image`), never
  invent it. Look for it on every web result: if the page is a JavaScript app, find the platform's JSON API in
  `performance.getEntriesByType('resource')` (it often has `poster`, `image` or `og:image`). `guardar` warns when a web result
  with 4 or more events has none. Leave it empty only if the source has no picture of its own: not the venue's logo, a generic banner or an
  icon. Instagram post pictures are not used (their URLs expire). `guardar` ignores any that is not https.
- `vigente_sin_fin: true` only when the source publishes it as current with no closing date.
- `comportamiento`: short keys and values that help the next run (`espera_seg`, `scroll`, `ver_mas`,
  `paginacion`, `menu`, `cookies` (which notice appears and how it is closed), `popups`, `plataforma`,
  `fichas`, `extraccion`, `bloqueos`). It is merged with what was already there; set a key to `null` to
  delete it if it stopped being true.
- `nota`: one or two sentences with what was learned. They accumulate in the site's `notas`.
- `web_nueva`, `instagram`, `enlace_bio`: only if you discovered they changed or were missing. `barrio` and
  `direccion`: for sites being confirmed (the ones that had a `tarea`).
- `descartar` + `evidencia`: instead of everything else, to remove a site that does not exist, closed or is
  not in CABA.

**Large results** (Turismo BA, Passline, a theater with 60 performances): shorten the descriptions to ~200
characters and write the file in one go. Do not split it into several saves of the same `id` and channel:
each save replaces the previous capture of that site.

## 6. Publish (progress updates and final)

```bash
python scripts/armar_agenda.py
git add data/ .claude/ scripts/ README.md
git commit -m "Agenda <date>: crawl progress (<done>/<total> sites)"
git pull --rebase --autostash && git push
```

`armar_agenda.py` takes the latest capture of each site (those more than 10 days old are ignored), filters
the 14-day window, classifies, removes duplicates (and applies the pairs you decided in
`data/crawl/duplicados.json`, section 7), fills in missing addresses (`direcciones.py`: other lists, other
events at the same venue and Alternativa Teatral pages), places new addresses on the map (redoes the ones
that land far from their neighborhood), marks which sites can be shown inside the website (`embebibles.py`),
gives each event a stable `id` (the website saves favorites with it) and updates the status of each venue in
`data/lugares.json`. It uses the network: if there is no connection, `--sin-geo` builds anyway with what is
already saved. If the push fails twice, leave the commit local and report it.

## 7. Close

When `siguiente` says the queue is empty (or only SalePlan is left):

```bash
python scripts/saleplan.py
python scripts/armar_agenda.py
python scripts/duplicados.py candidatos
```

**Review the possible duplicates.** Automatic deduplication only merges what is certain; `candidatos` lists
doubtful pairs (overlapping dates and similar title or venue), numbered, with venue, address, dates, sources
and link of each one. Decide each pair and record it:

```bash
python scripts/duplicados.py iguales 3 8 15     # the same event (merged at every build)
python scripts/duplicados.py distintos 1 2 4    # different events (never asked about again)
```

- **Iguales** (same): the same play, exhibition, show or party, even if the title changes ("Ningyō:
  tradición y actualidad de las muñecas japonesas" / "Ningyō, muñecas japonesas"), the name of the venue or
  the room, or one source brings only some of the performances. If in doubt, open both links.
- **Distintos** (different): an exhibition and the guided tour of that exhibition; two different plays in
  the same room; two parties on the same day at the same club with a different line-up; fairs of the same
  network in different squares.
- When merging, the data (title, venue, time, link, description) comes from the venue's **own source** (its
  website and then its Instagram, marked "(fuente propia)" in the list); aggregators only fill in what is
  missing. There is no need to choose which one stays: just decide whether they are the same event.
- Decide all of the list (if it is long, `--max 200`; with more than ~100 pairs, read the first ones by hand and
  treat pairs whose titles share almost all their words as `iguales` and the rest as `distintos`, leaving the
  doubtful ones undecided). The decisions are saved in
  `data/crawl/duplicados.json` and hold for future runs, so the list shrinks over time.

Check the pictures: `python scripts/crawl.py sin-imagen` lists the venues with 4 or more events and none with an `imagen`.
For each one that is not an Instagram-only or PDF source, first run `python scripts/imagenes.py <id>` (reads the event
pages over HTTP: og:image, known `<img>` patterns, Ministry of Culture CSS backgrounds, JSON-LD) and save the
`data/crawl/tmp/<id>.reimage.json` it writes with `crawl.py guardar`. What it cannot read (403 pages, single-page apps)
is read from the browser: see "Where the picture is" in `navegador.md`. A picture that repeats in 3 or more events of a
site is the venue's generic photo, not the event's: leave it out. If the source really has no pictures, say so in the `nota`.

Then build again and close the run:

```bash
python scripts/armar_agenda.py
python scripts/crawl.py cerrar
```

### Lecciones de la corrida

After every 20-site session (before its progress commit, section 6) and again before the closing commit, read
the report (`data/crawl/informes/<date>.md`) and review what was crawled since the last review: what was
costly, what failed, what you had to solve without the skill saying how. Each useful thing goes to its place:

- **About one site** (where its agenda is, which button expands, that it does not load without waiting): it
  was already saved in `sitios.json` when you saved it. If not, correct that site's `comportamiento` or
  `nota`.
- **About several sites or a platform** (a technique to get dates, how Wix, Passline or a type of ticketing
  site behaves, a URL pattern that worked): add it to the section of this skill where it belongs (3, 4 or
  4b), or to `navegador.md` if it is about the browser tools.
- **About the process** (a step that was confusing or missing, a criterion you had to decide about what to
  load, an order that should change): fix the skill. If it contradicts something written, replace it; do not
  leave two versions.
- **About a script** (a bug, a case it does not handle, a confusing warning): fix it if it is small and
  safe, and update its docstring and the `README.md`; if not, describe it in a `## Para revisar` section that
  you add at the end of the report.

Write how it is done **today**, in the place where an agent will look for it, not as a list of lessons at the
end. If you learned nothing new, do not touch the skill. Then publish everything together:

```bash
git add data/ .claude/ scripts/ README.md
git commit -m "Agenda <date>: <N> events, <S> sites crawled"
git pull --rebase --autostash && git push
```

In the commit message, one line for each change in the skill, the scripts or the README.

If the run was cut off by a block or a browser error that cannot be solved, close with
`crawl.py cerrar --forzar`: what was left uncrawled goes first next time.

Final report (3-6 lines, in English): events published, sites crawled by status, new sites, failures
(`no_carga`, `dominio_caido`, `bloqueado`), what changed in the skill or the scripts, and what is worth
reviewing by hand. The detail stays in `data/crawl/informes/<date>.md` (in Spanish).

## Limits

- Do not log in, do not create accounts, do not follow, do not like, do not send messages, do not buy
  tickets.
- Do not edit `data/eventos.json` by hand or the captures in `data/crawl/capturas/`: the scripts write them.
  Duplicate decisions are recorded with `duplicados.py`, not by editing `data/crawl/duplicados.json`.
- You may edit by hand in `data/crawl/sitios.json` a site's data that is wrong (website, Instagram, venues)
  when you confirmed it in the browser.
