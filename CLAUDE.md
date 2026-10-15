# Agenda Cultural CABA: reglas para trabajar en este repositorio

Este archivo lo lee Claude Code al empezar cada sesión. Se habla y se escribe en español.

## La documentación se actualiza en el mismo commit que el cambio

Cada cambio en el código, en la web o en el formato de los datos actualiza, **en el mismo commit**, todo
documento que quede desactualizado. Un cambio sin su documentación no está terminado.

| Si cambiás… | Revisá y actualizá… |
|---|---|
| Un script de `scripts/` (qué hace, sus opciones, si usa la red, qué archivos lee o escribe) | El docstring del script; `README.md` (sección Scripts); la sección de la skill donde se usa |
| El proceso de una corrida (pasos, orden, comandos, reglas, criterios de qué se carga) | `.claude/skills/actualizar-agenda/SKILL.md` |
| Las herramientas del navegador (`navegador.js`) | `.claude/skills/actualizar-agenda/navegador.md` |
| Un archivo de `data/` nuevo o con otro formato | Tabla Datos de `README.md`; la skill si el agente lo lee o lo escribe |
| La web (`index.html`, `assets/`): filtros, botones, pestañas | Primer párrafo de `README.md` |
| El tratamiento de un sitio puntual (dónde está su agenda, si se rastrea o no) | Ese sitio en `data/crawl/sitios.json` (`comportamiento`, `notas`, `rastrear`), no la skill |

Antes de commitear, buscá en los documentos lo que tu cambio dejó falso (`grep` del nombre del script, de la
opción o del archivo) y corregilo. Los documentos describen cómo funciona **hoy**: no dejes "antes se
hacía…" ni historial; eso va en el mensaje del commit.

## Lo que se aprende en cada corrida queda escrito

Cada corrida de la skill `actualizar-agenda` termina pasando lo aprendido a donde corresponde (sección
"Lecciones de la corrida" de la skill):

- **De un sitio**: en `data/crawl/sitios.json` (`comportamiento`, `nota`), con `crawl.py guardar`.
- **De varios sitios o del proceso**: una técnica que sirvió, una plataforma que se comporta de cierta
  manera, un error de un script, un paso que confundió o faltó, un criterio que hubo que decidir. Va a la
  skill (o a `navegador.md`, o al script y su docstring si hay que arreglarlo), en el mismo commit que cierra
  la corrida.

## Otras reglas

- No editar a mano `data/eventos.json` ni `data/crawl/capturas/`: los escriben los scripts.
- Los scripts usan solo la biblioteca estándar de Python 3.10+.
- Probar los cambios en la web en un navegador (Playwright está disponible en la nube) y los de los scripts
  con `python scripts/armar_agenda.py --simular` antes de publicar.
