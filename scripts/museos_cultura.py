"""Reads the activities and exhibitions of a Ministry of Culture museum (museo<x>.cultura.gob.ar) over plain HTTP.

Usage:
    python scripts/museos_cultura.py actividades  https://museorojas.cultura.gob.ar [salida.json] [--desde AAAA-MM-DD] [--hasta AAAA-MM-DD]
    python scripts/museos_cultura.py exhibiciones https://museorojas.cultura.gob.ar [salida.json]

`actividades` opens /actividades/?page=1..3, then every /actividad/<slug>/ ficha, and prints one line per ficha
(`OK` when its "Cuándo" date falls inside the window, which defaults to the next 14 days) with the title, hour,
price and slug. The OK ones are written to the JSON file (title, start, end, horario, dónde, entrada, picture,
description, url) so they can be turned into events by hand.

`exhibiciones` opens /exhibiciones/ and every /exhibicion/<slug>/ ficha and prints the line that carries the closing
date ("Del X al Y de 2026", "Hasta el ..."); an exhibition without a closing date is not an event to load.

It uses the network (HTTP only, 1 s between pages), reads nothing else and writes only the JSON file you name.
Python 3.10+ standard library plus `sondear.py`.
"""
import html as H
import json
import re
import sys
import time
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import sondear  # noqa: E402

sondear.TIMEOUT = 45
MES = {'Ene': 1, 'Feb': 2, 'Mar': 3, 'Abr': 4, 'May': 5, 'Jun': 6, 'Jul': 7, 'Ago': 8, 'Sep': 9, 'Set': 9,
       'Oct': 10, 'Nov': 11, 'Dic': 12}


def fecha(s):
    m = re.match(r'(\d+) (\w{3})\.? (\d{4})', s.strip())
    return f"{m[3]}-{MES[m[2]]:02d}-{int(m[1]):02d}" if (m and m[2] in MES) else None


def lineas(html, base):
    return [x.strip() for x in sondear.texto_legible(html, base).split('\n') if x.strip()]


def despues(L, clave):
    for i, x in enumerate(L):
        if x == clave and i + 1 < len(L):
            return L[i + 1]
    return ''


def titulo(html):
    t = re.search(r'<h1[^>]*>(.*?)</h1>', html, re.S)
    return H.unescape(re.sub(r'<[^>]+>', '', t[1])).strip() if t else ''


def actividades(base, salida, desde, hasta):
    links = []
    for p in (1, 2, 3):
        est, _, h, _ = sondear.pedir(f"{base}/actividades/?page={p}")
        nuevos = [x for x in dict.fromkeys(re.findall(r'href="(/actividad/[^"]+)"', h)) if x not in links] if est == 200 else []
        if not nuevos:
            break
        links += nuevos
        time.sleep(1)
    print(len(links), 'actividades')
    out = []
    for l in links:
        est, _, h, _ = sondear.pedir(base + l)
        time.sleep(1)
        if est != 200:
            continue
        L = lineas(h, base)
        cu, ho, do, en = (despues(L, k) for k in ('Cuándo', 'Horario', 'Dónde', 'Entrada'))
        ds = re.findall(r'\d+ \w{3}\.? \d{4}', cu)
        ini = fecha(ds[0]) if ds else None
        fin = fecha(ds[-1]) if len(ds) > 1 else ''
        ok = bool(ini and ini <= hasta and (fin or ini) >= desde)
        print('OK ' if ok else '-- ', ini, fin, ho[:30], '|', titulo(h)[:50], '|', en[:20], '|', l.split('/')[-2][:30])
        if ok:
            img = re.search(r'og:image" content="([^"]+)', h)
            d = re.search(r'og:description" content="([^"]*)', h)
            out.append(dict(titulo=titulo(h), inicio=ini, fin=fin, horario=ho, donde=do, entrada=en,
                            imagen=img[1] if img else '', descripcion=H.unescape(d[1])[:300] if d else '', url=base + l))
    if salida:
        Path(salida).write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding='utf-8')


def exhibiciones(base, salida):
    est, _, h, _ = sondear.pedir(base + "/exhibiciones/")
    links = list(dict.fromkeys(re.findall(r'href="(/exhibicion/[^"]+)"', h))) if est == 200 else []
    out = []
    for l in links:
        est, _, h, _ = sondear.pedir(base + l)
        time.sleep(1)
        if est != 200:
            continue
        L = lineas(h, base)
        cierre = [x for x in L if re.search(r'\b(Del|del|Hasta|hasta)\b.*(2026|2027)', x)]
        print(l.split('/')[-2][:45], '|', cierre[:1], '|', despues(L, 'Horario')[:40])
        if cierre:
            img = re.search(r'og:image" content="([^"]+)', h)
            out.append(dict(titulo=titulo(h), cierre=cierre[0], horario=despues(L, 'Horario'),
                            imagen=img[1] if img else '', url=base + l))
    if salida:
        Path(salida).write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding='utf-8')


def main(argv):
    args = [a for a in argv if not a.startswith('--')]
    desde = date.today().isoformat()
    hasta = (date.today() + timedelta(days=14)).isoformat()
    for i, a in enumerate(argv):
        if a == '--desde':
            desde = argv[i + 1]
            args.remove(desde)
        if a == '--hasta':
            hasta = argv[i + 1]
            args.remove(hasta)
    if len(args) < 2 or args[0] not in ('actividades', 'exhibiciones'):
        print(__doc__)
        return 1
    base = args[1].rstrip('/')
    salida = args[2] if len(args) > 2 else ''
    if args[0] == 'actividades':
        actividades(base, salida, desde, hasta)
    else:
        exhibiciones(base, salida)
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
