# Agenda Cultural CABA

Sitio estático con los eventos culturales de la Ciudad de Buenos Aires de las próximas dos semanas
(`index.html`, `assets/`), un mapa y la lista de espacios culturales. Lee `data/eventos.json` y
`data/lugares.json`.

## Cómo se actualiza

Los datos se juntan **solo con el navegador**, con la skill de Claude
[`actualizar-agenda`](.claude/skills/actualizar-agenda/SKILL.md). Cada corrida vuelve a rastrear todos los
sitios (webs de lugares, galerías y museos, agregadores e Instagram), espera a los sitios lentos, scrollea,
expande los "ver más", entra a cada sección de muestras, agenda o cartelera, y anota cómo se comportó cada
sitio para que la corrida siguiente sea mejor.

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
| `data/geocache.json` | Coordenadas ya buscadas para el mapa. |
| `data/fuente/lugares_fuente.csv` | Planilla original de lugares. |

## Scripts

No entran a ningún sitio web; solo procesan lo que juntó el navegador. Usan la biblioteca estándar de
Python 3.10+.

- `scripts/crawl.py`: cola de la corrida, validación de cada resultado (rechaza "sin eventos" si quedaron
  enlaces de agenda sin abrir o listados sin scrollear, y "no carga" con menos de 3 intentos) y registro de
  lo aprendido, incluidos los enlaces descartados para no reabrirlos. `crawl.py herramientas` imprime la
  línea que carga `.claude/skills/actualizar-agenda/navegador.js` en la pestaña (desde jsDelivr, fijado al
  último commit subido de ese archivo).
- `scripts/armar_agenda.py`: arma `data/eventos.json` (ventana de 14 días, clasificación, duplicados) y
  ubica las direcciones nuevas en el mapa con OpenStreetMap (`--sin-geo` para no consultar).
- `clasificar.py`, `deduplicar.py`, `geocodificar.py`, `comun.py`: funciones compartidas.

## Ver el sitio en local

```bash
python -m http.server 8000
```

y abrir `http://localhost:8000`.
