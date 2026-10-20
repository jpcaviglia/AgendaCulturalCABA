# Agenda Cultural CABA

Static site with the cultural events in the City of Buenos Aires for the next two weeks (`index.html`,
`assets/`), a map and the list of cultural venues. The site is in Spanish. It reads `data/eventos.json` and
`data/lugares.json`.

On the site: events are listed day by day (an event appears on every day it runs, according to the weekdays in its `horarios`), each with its picture next to it when the source has one and the time(s) it has on that day, read from `horarios` (a play with several performances shows the times of that weekday; an exhibition open "de 14 a 20 h" shows that slot) (a strip of the 15 days shows how many activities each day has and
filters by day; what started before is grouped under **En cartel**), with filters by text, category (several
can be combined; each chip shows how many events it has with the other filters), free events and a
"Desde las" time selector, and under **Más filtros** by venue, neighborhood and date range;
**Agendar** (Google Calendar or an .ics file); **+ info** (the event's page inside the agenda, when the site
allows it); and **Favoritos** (the star), which are saved in the browser (localStorage) with a copy of the
event, so they are not lost when a run rebuilds `eventos.json`. On phones the sections move to a bottom bar.
The look is black and white with square corners, a dusty-rose accent and one muted color per category; the typefaces (Archivo and Space Mono) are loaded from Google Fonts and the map from unpkg and OpenStreetMap.

## How it is updated

The data is collected **with the browser**, using the Claude skill
[`actualizar-agenda`](.claude/skills/actualizar-agenda/SKILL.md), except for what can be read with plain HTTP
(sites without JavaScript, the Linktree of each Instagram account, the SalePlan listings). Each run crawls
every site again (venue websites, galleries and museums, aggregators and Instagram), waits for slow sites,
scrolls, expands the "ver más" buttons, enters every exhibition, agenda or listings section, and records how
each site behaved so the next run does better. At the end, possible duplicates between sources are reviewed.

To run it: open Claude Code in this folder with Claude in Chrome connected and ask for
`/actualizar-agenda` (or "update the agenda"). The scheduled routine should use that same request.

## Data

| File | What it is |
|---|---|
| `data/crawl/sitios.json` | All the sites to crawl and what was learned about each one: where its agenda is (`entradas`), how it behaves (`comportamiento`), notes, pending links and the results of the latest runs; `"rastrear": false` skips the site, `"rastrear_web": false` crawls only its Instagram. |
| `data/crawl/capturas/` | What was found on the last visit to each site (`<id>.web.json`, `<id>.instagram.json`). |
| `data/crawl/corrida.json` | Queue and progress of the current run (lets it resume if it is interrupted). |
| `data/crawl/informes/` | One report per run. |
| `data/eventos.json` | What the site publishes. Written by `scripts/armar_agenda.py`. |
| `data/lugares.json`, `data/galerias.json` | Cultural venues and galleries. The crawl adds the ones it discovers. |
| `data/crawl/duplicados.json` | Event pairs the agent reviewed: the same (they are merged) or different (they are not asked about again). |
| `data/geocache.json` | Coordinates already looked up for the map. |
| `data/barrios.json` | Official neighborhood boundaries: they detect locations that landed far from the event's neighborhood. |
| `data/direcciones.json` | Addresses of venues that are not in the lists (read from Alternativa Teatral). |
| `data/embebibles.json` | Which sites may be shown inside an iframe ("+ info" button). |
| `data/fuente/lugares_fuente.csv` | Original spreadsheet of venues. |

## Scripts

They use the Python 3.10+ standard library. `crawl.py` does not visit any site; the others that read from the
network do so with plain HTTP requests, at a slow pace.

- `scripts/crawl.py`: run queue (Instagram profiles are spread evenly among the websites so the daily quota
  is used along the run), validation of each result (rejects "sin eventos" if agenda links were left
  unopened or listings unscrolled, "no carga" with fewer than 3 attempts, and results where half or more of the events share one link (the
  listing page) instead of each having its own page, unless the site is marked `sin_fichas`) and a record of what was
  learned, including the discarded links so they are not reopened. `crawl.py herramientas` prints the line
  that loads `.claude/skills/actualizar-agenda/navegador.js` into the tab. `crawl.py sin-imagen` lists the venues whose published events have no picture, and `scripts/imagenes.py <id>` looks for them in the
  event pages (plain HTTP) and writes a result for `crawl.py guardar`. `crawl.py servir` (left running
  in the background) serves that file from the working tree on `127.0.0.1:8791`, and `herramientas` then prints
  a local import; without it the line uses jsDelivr, pinned to the last pushed commit of the file, which the
  browser tool's auto-mode classifier may deny as external code.
- `scripts/sondear.py`: reads without a browser the sites that allow it (`--corrida`) or a single page
  (`--leer <url>`, Linktree too); the events it saves are completed with the price, picture and time from each event's own page.
- `scripts/biolinks.py`: looks for the Linktree of each Instagram account without opening Instagram.
- `scripts/borges.py`: reads the Centro Cultural Borges agenda from the site's JSON API and writes the result file, with each event linked to its own page.
- `scripts/saleplan.py`: reads the SalePlan listings and saves only what no other source brought.
- `scripts/armar_agenda.py`: builds `data/eventos.json` (14-day window, classification, duplicates, missing
  addresses, map, stable id for each event). `--sin-geo` builds without querying the network. With no
  recent captures it leaves `eventos.json` untouched, unless `--vaciar` is given (then it writes it with no
  events).
- `scripts/duplicados.py`: lists possible duplicates for review and saves the decisions.
- `clasificar.py`, `deduplicar.py`, `direcciones.py`, `embebibles.py`, `geocodificar.py`, `comun.py`:
  shared functions.

## Documentation

`CLAUDE.md` has the rules for working in the repository: Claude works in English, while the website and the
data stay in Spanish; every change updates in the same commit the documents it affects (this README, the
skill, `navegador.md`, the docstrings), and what is learned in each run is written down in the skill or in
`sitios.json`.

## Viewing the site locally

```bash
python -m http.server 8000
```

and open `http://localhost:8000`.
