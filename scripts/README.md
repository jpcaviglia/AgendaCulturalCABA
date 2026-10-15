# Scripts de la agenda

Solo usan la biblioteca estándar de Python 3.10 o superior. No hay que instalar nada.

## Qué hace cada uno

| Script | Qué genera | Cuándo correrlo |
|---|---|---|
| `verificar_lugares.py` | `data/lugares.json` y `data/lugares_verificacion.csv` | Cuando cambie la planilla de lugares |
| `rutina_agenda.py` | `data/eventos.json` + `data/fuente/revision_pendiente.json`, y commit/push | **La rutina principal**, una vez por semana |
| `actualizar_eventos.py` | `data/eventos.json` solo con Turismo BA (versión simple, sin git) | Alternativa más simple |

`comun.py` tiene las funciones compartidas (descarga de páginas, lectura de la agenda de Turismo BA).

## Uso

Desde la raíz del repositorio:

```bash
python scripts/verificar_lugares.py
```

Por defecto lee `data/fuente/lugares_fuente.csv`. Para usar otro export, pasá la ruta:

```bash
python scripts/verificar_lugares.py ruta/al/export.csv
```

Después, la agenda semanal:

```bash
python scripts/actualizar_eventos.py
```

Para ver el sitio en local:

```bash
python -m http.server 8000
```

y abrir `http://localhost:8000`. Hace falta un servidor porque el sitio lee los JSON con `fetch`.

## Límites conocidos

- **Verificación de lugares:** es automática. No entra a Instagram (pide login) ni a sitios que bloquean bots (HTTP 403, 400 o 429). Esos casos aparecen como "No verificable" o "Inaccesible" y hay que revisarlos a mano. Los errores de conexión (DNS, SSL, timeout) pueden ser temporales: correr de nuevo antes de descartar un sitio.
- **Agenda:** Turismo BA publica fecha de inicio, no de fin. Las actividades que ya empezaron aparecen como "En curso" y pueden haber terminado. Confirmar siempre en el sitio del organizador.
- **Agregadores pendientes:** las fuentes de `data/fuentes.json` marcadas con `"integrada": false` todavía no tienen script. Varias (Eventbrite, Time Out) tienen términos de uso que restringen el scraping; revisarlos antes de automatizar.

## Rutina semanal

La rutina es correr `actualizar_eventos.py` y guardar el resultado. Opciones:

- **Windows (Programador de tareas):** crear una tarea semanal que ejecute `python scripts\actualizar_eventos.py` desde la carpeta del repositorio.
- **Cron (Linux o macOS):** `0 7 * * 1 cd /ruta/al/repo && python3 scripts/actualizar_eventos.py`
- Si el repositorio está en GitHub, el paso siguiente sería hacer commit de `data/eventos.json`. Hoy eso no está automatizado.

## Rutina completa (`rutina_agenda.py`)

```bash
python scripts/rutina_agenda.py              # agrega, clasifica, deduplica, actualiza el sitio, commit y push
python scripts/rutina_agenda.py --sin-push   # igual pero sin push
python scripts/rutina_agenda.py --simular    # no escribe ni toca git
```

Pasos: (1) recolecta de Turismo BA, de los sitios propios de `data/lugares.json` (lee datos estructurados schema.org/Event, siguiendo hasta 2 enlaces de agenda por sitio), de agregadores habilitados y de `data/fuente/eventos_manuales.csv`; (2) filtra a la ventana de 14 días; (3) clasifica en categorías canónicas (`clasificar.py`: primero mapea la categoría de la fuente, si es genérica usa palabras clave del título y la descripción); (4) quita duplicados (`deduplicar.py`: mismo día, título parecido y mismo lugar; se conserva la fuente más confiable y se completan campos vacíos, y `fuentes` lista todas las que lo informan); (5) escribe `data/eventos.json`; (6) commit y push solo de `eventos.json` y `revision_pendiente.json`.

Si una fuente falla, se conservan los eventos que aportó en la corrida anterior. Si no cambió nada, no se crea commit.

### Lo que la rutina no puede leer solo
- **Instagram** pide login: no se scrapea. Los lugares que solo tienen Instagram figuran en `revision_pendiente.json` (`solo_instagram`). Los eventos que veas ahí se cargan en `data/fuente/eventos_manuales.csv` (columnas: titulo, fecha_inicio AAAA-MM-DD, fecha_fin, hora, lugar, barrio, direccion, categoria, horarios, precio, url, descripcion) y entran en la próxima corrida.
- **Sitios sin datos estructurados** (`sitios_sin_datos`): tienen agenda pero en HTML libre; hay que revisarlos a mano o escribir un adaptador específico.
- **Agregadores**: para sumar uno que publique JSON-LD, agregá `"adaptador": "jsonld"` a su entrada en `data/fuentes.json`. Probados Time Out, Indiehoy, Alternativa Teatral y SalePlan: sus portadas no traen JSON-LD de eventos, así que quedan sin habilitar. Eventbrite, Ticketek y Passline restringen el scraping en sus términos.
