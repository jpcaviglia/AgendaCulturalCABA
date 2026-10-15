# Agenda Cultural CABA: rules for working in this repository

Claude Code reads this file at the start of every session.

## Language

Claude works in **English**: chat replies, documentation (this file, `README.md`, the skill, `navegador.md`),
script docstrings, code comments and commit messages are all written in English.

Everything that ends up on the website or in the data stays in **Spanish**: the web UI (`index.html`,
`assets/`), event titles, descriptions, categories and prices, the notes and `comportamiento` values in
`data/crawl/sitios.json`, and the run reports in `data/crawl/informes/`. Identifiers also stay in Spanish
because the scripts depend on them: JSON keys and values (`estado`, `con_eventos`, `fecha_inicio`…), file
names, script names, subcommands and options (`crawl.py guardar`, `--simular`…), and the literal messages the
scripts print (quote them as they appear, for example **NO SE GUARDÓ**).

## Documentation is updated in the same commit as the change

Every change to the code, the website or the data format updates, **in the same commit**, every document that
becomes outdated. A change without its documentation is not finished.

| If you change… | Review and update… |
|---|---|
| A script in `scripts/` (what it does, its options, whether it uses the network, which files it reads or writes) | The script's docstring; `README.md` (Scripts section); the skill section where it is used |
| The run process (steps, order, commands, rules, criteria for what gets loaded) | `.claude/skills/actualizar-agenda/SKILL.md` |
| The browser tools (`navegador.js`) | `.claude/skills/actualizar-agenda/navegador.md` |
| A new `data/` file, or one with a different format | Data table in `README.md`; the skill if the agent reads or writes it |
| The website (`index.html`, `assets/`): filters, buttons, tabs | First paragraph of `README.md` |
| How a specific site is handled (where its agenda is, whether it is crawled or not) | That site in `data/crawl/sitios.json` (`comportamiento`, `notas`, `rastrear`), not the skill |

Before committing, search the documents for anything your change made false (`grep` for the script name, the
option or the file) and fix it. The documents describe how things work **today**: do not leave "this used to
be done…" or history in them; that goes in the commit message.

## What is learned in each run gets written down

Every run of the `actualizar-agenda` skill ends by moving what it learned to the right place ("Lecciones de
la corrida" section of the skill):

- **About one site**: in `data/crawl/sitios.json` (`comportamiento`, `nota`), with `crawl.py guardar`.
- **About several sites or the process**: a technique that worked, a platform that behaves a certain way, a
  script bug, a step that was confusing or missing, a criterion that had to be decided. It goes in the skill
  (or in `navegador.md`, or in the script and its docstring if it needs fixing), in the same commit that
  closes the run.

## Other rules

- Do not edit `data/eventos.json` or `data/crawl/capturas/` by hand: the scripts write them.
- Scripts use only the Python 3.10+ standard library.
- Test website changes in a browser (Playwright is available in the cloud) and script changes with
  `python scripts/armar_agenda.py --simular` before publishing.
