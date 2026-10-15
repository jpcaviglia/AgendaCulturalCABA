# Agenda Cultural CABA

Static site with the cultural events in the City of Buenos Aires for the next two weeks (`index.html`,
`assets/`), a map and the list of cultural venues. The site is in Spanish. It reads `data/eventos.json` and
`data/lugares.json`.

On the site: filters by text, venue, neighborhood, category, dates, time and free events; **Agendar** (Google
Calendar or an .ics file); **+ info** (the event's page inside the agenda, when the site allows it); and
**Favoritos**, which are saved in the browser (localStorage) with a copy of the event, so they are not lost
when a run rebuilds `eventos.json`.

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
| `data/crawl/sitios.json` | All the sites to crawl and what was learned about each one: where its agenda is (`entradas`), how it behaves (`comportamiento`), notes, pending links and the results of the latest runs. |
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

- `scripts/crawl.py`: run queue, validation of each result (rejects "sin eventos" if agenda links were left
  unopened or listings unscrolled, and "no carga" with fewer than 3 attempts) and a record of what was
  learned, including the discarded links so they are not reopened. `crawl.py herramientas` prints the line
  that loads `.claude/skills/actualizar-agenda/navegador.js` into the tab (from jsDelivr, pinned to the last
  pushed commit of that file).
- `scripts/sondear.py`: reads without a browser the sites that allow it (`--corrida`) or a single page
  (`--leer <url>`, Linktree too).
- `scripts/biolinks.py`: looks for the Linktree of each Instagram account without opening Instagram.
- `scripts/saleplan.py`: reads the SalePlan listings and saves only what no other source brought.
- `scripts/armar_agenda.py`: builds `data/eventos.json` (14-day window, classification, duplicates, missing
  addresses, map, stable id for each event). `--sin-geo` builds without querying the network.
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
