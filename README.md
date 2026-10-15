# Agenda Cultural CABA

Sitio estático con los eventos culturales de la Ciudad de Buenos Aires de las próximas dos semanas
(`index.html`, `assets/`), un mapa y la lista de espacios culturales. Lee `data/eventos.json` y
`data/lugares.json`.

En la web: filtros por texto, lugar, barrio, categoría, fechas, hora y gratis; **Agendar** (Google Calendar
o archivo .ics); **+ info** (la página del evento dentro de la agenda, si el sitio lo permite); y
**Favoritos**, que se guardan en el navegador (localStorage) con una copia del evento, así no se pierden
cuando una corrida rehace `eventos.json`.

## Cómo se actualiza

Los datos se juntan **con el navegador**, con la skill de Claude
[`actualizar-agenda`](.claude/skills/actualizar-agenda/SKILL.md), salvo lo que se puede leer con HTTP simple
(webs sin JavaScript, Linktree de los Instagram, los listados de SalePlan). Cada corrida vuelve a rastrear todos los
sitios (webs de lugares, galerías y museos, agregadores e Instagram), espera a los sitios lentos, scrollea,
expande los "ver más", entra a cada sección de muestras, agenda o cartelera, y anota cómo se comportó cada
sitio para que la corrida siguiente sea mejor. Al final se revisan los posibles duplicados entre fuentes.

Para correrla: abrir Claude Code en esta carpeta con Claude in Chrome conectado y pedir
`/actualizar-agenda` (o "actualizá la agenda"). La rutina programada debería usar ese mismo pedido.

## Datos

| Archivo | Qué es |
|---|---|
| `data/crawl/sitios.json` | Todos los sitios a rastrear y lo aprendido de cada uno: dónde está su agenda (`entradas`), cómo se comporta (`comportamiento`), notas, enlaces pendientes y resultados de las últimas corridas. |
| `data/crawl/capturas/` | Lo que se encontró en la última visita a cada sitio (`<id>.web.json`, `<id>.instagram.json`). |
| `data/crawl/corrida.json` | Cola y avance de la corrida en curso (permite retomarla si se corta). |
| `data/crawl/informes/` | Un informe por corrida. |
| `data/eventos.json` | Lo que publica el sitio. Lo escribe `scripts/armar_agenda.py`. |
| `data/lugares.json`, `data/galerias.json` | Espacios culturales y galerías. El rastreo suma los que descubre. |
| `data/crawl/duplicados.json` | Pares de eventos que el agente revisó: iguales (se unen) o distintos (no se vuelven a preguntar). |
| `data/geocache.json` | Coordenadas ya buscadas para el mapa. |
| `data/barrios.json` | Límites oficiales de los barrios: detectan ubicaciones que cayeron lejos del barrio del evento. |
| `data/direcciones.json` | Direcciones de lugares que no están en las listas (leídas de Alternativa Teatral). |
| `data/embebibles.json` | Qué sitios se dejan mostrar dentro de un iframe (botón "+ info"). |
| `data/fuente/lugares_fuente.csv` | Planilla original de lugares. |

## Scripts

Usan la biblioteca estándar de Python 3.10+. `crawl.py` no entra a ningún sitio; los demás que leen de la
red lo hacen con pedidos HTTP simples, a ritmo lento.

- `scripts/crawl.py`: cola de la corrida, validación de cada resultado (rechaza "sin eventos" si quedaron
  enlaces de agenda sin abrir o listados sin scrollear, y "no carga" con menos de 3 intentos) y registro de
  lo aprendido, incluidos los enlaces descartados para no reabrirlos. `crawl.py herramientas` imprime la
  línea que carga `.claude/skills/actualizar-agenda/navegador.js` en la pestaña (desde jsDelivr, fijado al
  último commit subido de ese archivo).
- `scripts/sondear.py`: lee sin navegador las webs que lo permiten (`--corrida`) o una página suelta
  (`--leer <url>`, también Linktree).
- `scripts/biolinks.py`: busca el Linktree de cada Instagram sin abrir Instagram.
- `scripts/saleplan.py`: lee los listados de SalePlan y guarda solo lo que ninguna otra fuente trajo.
- `scripts/armar_agenda.py`: arma `data/eventos.json` (ventana de 14 días, clasificación, duplicados,
  direcciones que faltan, mapa, id estable de cada evento). `--sin-geo` arma sin consultar la red.
- `scripts/duplicados.py`: lista posibles duplicados para revisar y guarda las decisiones.
- `clasificar.py`, `deduplicar.py`, `direcciones.py`, `embebibles.py`, `geocodificar.py`, `comun.py`:
  funciones compartidas.

## Documentación

`CLAUDE.md` tiene las reglas para trabajar en el repositorio: cada cambio actualiza en el mismo commit los
documentos que afecta (este README, la skill, `navegador.md`, los docstrings), y lo que se aprende en cada
corrida queda escrito en la skill o en `sitios.json`.

## Ver el sitio en local

```bash
python -m http.server 8000
```

y abrir `http://localhost:8000`.
