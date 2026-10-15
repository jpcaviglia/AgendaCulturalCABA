# Rutina: actualizar la Agenda Cultural CABA

Repositorio: esta carpeta. Idioma de los datos: español. Ejecutar de principio a fin sin pedir confirmaciones, salvo lo indicado en "Límites".

## 1. Recolección automática
```bash
python scripts/rutina_agenda.py --simular
```
Revisar la salida. Esto no escribe nada; sirve para confirmar que las fuentes responden. Luego mirar `data/fuente/revision_pendiente.json` (generado en la corrida anterior, o corriendo el paso 4 sin push):
- `solo_instagram`: lugares cuyo único canal es Instagram.
- `sitios_sin_datos`: sitios con agenda en HTML libre.

## 2. Recolección con el navegador (fuente principal)
Los scripts solo cubren ~8 fuentes con datos estructurados; el resto (HTML libre, Instagram, ticketeras, galerías) se recorre con el navegador. Usar Chrome del usuario (herramientas `mcp__claude-in-chrome__*`; cargarlas con ToolSearch). La cuenta de Instagram de esa sesión es descartable y ya está iniciada. Si Instagram pide login o captcha, no intentar resolverlo: anotar "requiere login", cortar el lote de Instagram y seguir con webs.

Trabajar por lotes, hasta vaciar la cola (solo se corta por bloqueo de Instagram o por error del navegador; no se publica antes de terminar):
1. Leer `data/fuente/revision_estado.json` (`{ "<lugar>": "AAAA-MM-DD último chequeo" }`; si no existe, está vacío).
2. Recorrer **toda la cola**, sin tope de lugares por corrida y sin cortar por cansancio ni por cantidad: primero los nunca revisados, luego los de chequeo más viejo; prioridad a los que ya tuvieron eventos. Saltear los `caido` y `sin_agenda` del mapa (ver 2c).
3. Por cada lugar, recorrer de forma orgánica, como lo haría una persona. El punto de partida es siempre la web o el Instagram enlazado en `lugares.json` / `galerias.json` / el mapa (campo `web`, `agenda_url`, `instagram`):
   - **Web**: abrir la página de agenda/cartelera/programación (no la portada), esperar ~3 s, y **rastrear recursivamente**: entrar a la ficha de cada evento, función o muestra listada, y desde ahí seguir enlaces a entradas/ticketera, "más info", ediciones o ciclos relacionados. Profundidad máxima 3 niveles desde la agenda, solo enlaces del mismo dominio o de la ticketera (Alternativa Teatral, Passline, Eventbrite, Tuentrada, Universe, etc.). Mantener una lista de URLs ya visitadas para no repetir, y paginar ("ver más", "próximos", calendario por mes) hasta cubrir los próximos 14 días.
   - **Instagram** (`https://www.instagram.com/<usuario>/`): leer los últimos ~9 posts y las historias destacadas "Agenda/Cartelera/Programación". Abrir cada post con un evento; seguir el link de la bio (Linktree, entradas) con la misma regla recursiva.
   - **Por cada evento hallado, extraer todo lo que figure en su ficha**: título, fecha de inicio y fin, hora, todos los horarios/funciones, sala o espacio, dirección y barrio, categoría/género, precio y tipo de entrada, descripción (sinopsis, artistas, director, duración, edad), y la URL de la ficha o de las entradas. Un ciclo con varias funciones o una muestra con fechas de apertura y cierre es un solo evento con `fecha_inicio`/`fecha_fin` y `horarios`; las inauguraciones con día y hora propios van aparte.
   - **Ritmo en Instagram**: esperar 4-10 s al azar entre acciones y entre perfiles, scroll natural, sin abrir endpoints directos ni recorrer perfiles en ráfaga. Al primer aviso de "intentá de nuevo más tarde", límite de acciones o captcha, cortar Instagram, anotar los lugares pendientes y seguir con webs. Hashtags y búsqueda de Instagram requieren login: para descubrir posts usar Google con `site:instagram.com/p/ <lugar>`.
4. **Insertar los eventos a medida que se encuentran**, sin esperar a terminar el lote. Después de leer cada ficha (o cada lugar, si es una cartelera corta), escribir los eventos en un JSON temporal (lista de objetos con los campos `titulo,fecha_inicio,fecha_fin,hora,lugar,barrio,direccion,categoria,horarios,precio,url,descripcion`) y correr:
   ```bash
   python scripts/agregar_evento.py <archivo.json>
   ```
   El script valida, descarta lo que está fuera de la ventana de 14 días, lo anexa a `data/fuente/eventos_manuales.csv` (para que sobreviva a la próxima corrida completa), lo clasifica, lo deduplica contra lo que ya hay y lo inserta en `data/eventos.json`. Reglas para armar cada evento:
   - `fecha_inicio` y `fecha_fin` en `AAAA-MM-DD`. Si el post no dice año, asumir el actual solo si la fecha no queda en el pasado; si hay duda, no cargar el evento.
   - `lugar` igual al nombre del lugar en `data/lugares.json` (así se deduplica contra otras fuentes).
   - `categoria`: dejar vacío si no es obvio; el clasificador decide.
   - `url`: la ficha del evento o de las entradas; el post de Instagram solo si no hay otra.
   - **No inventar datos.** Si falta fecha, título o lugar, no se carga. Si un dato (precio, hora) no figura, dejarlo vacío.
5. Actualizar `data/fuente/revision_estado.json` con la fecha de hoy para cada lugar revisado, apenas se termina con él (incluidos los que no tenían nada o requirieron login; los pendientes por bloqueo de Instagram NO se marcan, para que entren primero en la próxima corrida).
6. Podar de `eventos_manuales.csv` las filas cuya `fecha_fin` (o `fecha_inicio` si no hay fin) sea anterior a hoy.

## 2a. Descubrimiento de lugares faltantes
Una vez por corrida, buscar lugares de CABA que no estén en `data/lugares.json` ni `data/galerias.json`: cines (INCAA y Espacios INCAA, cines independientes), museos, centros culturales, teatros y salas. Fuentes: listados del INCAA y del Gobierno de la Ciudad, Google Maps/búsquedas ("cines en <barrio>", "museos de Buenos Aires"), y los lugares que aparecen mencionados o etiquetados en los posts revisados. Confirmar que está en CABA y tiene web o Instagram vigente. Agregar a `lugares.json` (mismos campos que el resto) o, si es galería/museo de arte, a `galerias.json`. Informar cuántos se sumaron.

## 2b. Galerías de arte y museos de CABA
Las galerías casi nunca publican datos estructurados, así que se leen con el navegador. La lista está en `data/galerias.json` (`galerias`); el script ya las intenta leer y deja en `revision_pendiente.json` → `galerias_sin_datos` las que hay que abrir. Revisarlas **todas** en cada corrida (son pocas y las muestras duran semanas):
1. **No alcanza con la portada**: suele mostrar una sola muestra. Abrir la página de listado ("Muestras", "Exposiciones", "Exhibiciones"), mirar las pestañas actuales/próximas y entrar a **cada** muestra para leer sus fechas. Buscar la sección "Exposiciones", "Exhibitions", "Muestras", "Agenda" o "Actual/Próximas". Leer las muestras **en curso y próximas** (que empiecen dentro de los próximos 14 días o que ya hayan empezado y no hayan terminado).
2. Cargar cada muestra en `eventos_manuales.csv` con `fecha_inicio` y `fecha_fin` (las muestras sí tienen fin, así que se mantienen vigentes hasta esa fecha), `categoria` = `Artes visuales`, `lugar` = nombre de la galería, `url` = página de la muestra. Inauguraciones con día y hora propios: cargarlas como fila aparte con `hora`.
3. Galerías con `"verificada": false`: la URL no respondió desde el script. Buscar la web oficial de la galería (confirmar que está en CABA), corregir `web` en `galerias.json` y poner `"verificada": true`; si no existe o cerró, borrarla.
4. **Descubrimiento**: una vez por corrida abrir las fuentes de `descubrimiento` (circuito Gallery de Arte al Día, agenda de Arte al Día, nota mensual de Indiehoy) para encontrar galerías o muestras que no estén en la lista. Agregar a `galerias.json` las galerías nuevas ubicadas en CABA (campos `nombre`, `web`, `tipo`, `verificada`) y cargar sus muestras vigentes. No agregar galerías de otras ciudades.

## 2c. Mapa de agendas (`data/fuente/mapa_agendas.json`)
Antes de abrir un sitio, consultar su entrada en el mapa (generado con `python scripts/mapear_agendas.py` y revisado con el navegador el 2026-10-14). Campo `revision.estado`:
- `automatico`: el script ya lo lee (datos estructurados). No abrir.
- `html` / `navegador` / `ticketera`: abrir directo `revision.agenda_url` (no la portada), esperar ~3 s a que cargue y leer fechas. En `ticketera`, la ficha de entradas es la fuente.
- `instagram`: usar el handle del campo `instagram` (paso 2).
- `sin_agenda`, `no_es_agenda`, `desactualizado`: no gastar tiempo; solo Instagram si hay handle.
- `caido`: no abrir. Si hay handle en `data/fuente/sitios_corregidos.json`, usar Instagram; una vez por mes volver a probar el dominio.
Si durante la rutina se encuentra que un sitio cambió (nueva URL de agenda, sitio caído), actualizar su entrada en el mapa.

## 3. Revisión de calidad antes de publicar
- Abrir `data/fuente/eventos_manuales.csv` y verificar que las filas nuevas tengan fechas plausibles y sin duplicados obvios.
- No editar `data/eventos.json` a mano: lo modifican `agregar_evento.py` (durante el recorrido) y `rutina_agenda.py` (que lo regenera completo, incluyendo `eventos_manuales.csv`).

## 4. Agregar, clasificar, deduplicar, actualizar y publicar
```bash
python scripts/rutina_agenda.py
```
Esto aplica el filtro de ventana (14 días), clasifica, quita duplicados entre fuentes, reescribe `data/eventos.json` y hace commit + push. Para probar sin publicar: `--sin-push`.

## 5. Informe final (3-5 líneas)
Eventos totales, duplicados quitados, cuántos lugares se revisaron en el navegador, cuántos lugares nuevos se descubrieron, cuántos eventos nuevos se cargaron a mano, y qué fuentes fallaron o pidieron login.

## Límites
- Solo se modifican: `data/fuente/mapa_agendas.json`, `data/galerias.json`, `data/lugares.json`, `data/eventos.json`, `data/fuente/revision_pendiente.json`, `data/fuente/eventos_manuales.csv`, `data/fuente/revision_estado.json`. El script hace commit y push de los cuatro.
- No iniciar sesión, no crear cuentas, no seguir cuentas ni dar likes, no mandar mensajes, no comprar entradas.
- Si el push falla (conflicto), hacer `git pull --rebase` y reintentar una vez; si vuelve a fallar, dejar el commit local e informarlo.
- Instagram limita el ritmo: ver "Ritmo en Instagram" en el paso 2.
