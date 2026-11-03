"""Builds the website (one index.html) from build/policies.json and tools/template.html.

Usage:  python tools/build_site.py <build folder> <site folder>
"""
import json, re, sys, collections, datetime
from pathlib import Path
from bs4 import BeautifulSoup

BUILD, SITE = Path(sys.argv[1]), Path(sys.argv[2]); SITE.mkdir(parents=True, exist_ok=True)
HERE = Path(__file__).parent
D = json.load(open(BUILD / 'policies.json'))
recs = [r for r in D['records'] if r['parse_ok'] and r.get('type') != 'Template']
SECNAME = {}
for r in recs: SECNAME.setdefault(r['section'], r['section_name'])
SECNAME = dict(sorted(SECNAME.items(), key=lambda kv: int(kv[0])))
allnums = {r['number'].lower() for r in recs}

def slug(n): return 'p-' + re.sub(r'[^a-z0-9]+', '-', n.lower()).strip('-')
def sortkey(r):
    m = re.match(r'(\d+)', r['number'])
    return (int(r['section']), int(m.group(1)) if m and len(m.group(1)) == 4 else 99999, r['number'], r['file'])

seen, out = collections.Counter(), []
for r in sorted(recs, key=sortkey):
    sid = slug(r['number']); seen[sid] += 1
    if seen[sid] > 1: sid += '-' + str(seen[sid])
    soup = BeautifulSoup(r.get('body_html') or '', 'html.parser')
    for t in list(soup.find_all(True)):
        if t.attrs is None or t.decomposed: continue
        for a in ('id', 'style', 'class', 'width', 'align'):
            if a in t.attrs and not (t.name == 'section' and a == 'class'): del t.attrs[a]
        if t.name in ('img', 'col', 'colgroup', 'script', 'style', 'iframe'): t.decompose(); continue
        if t.name == 'a':
            if t.get('href', '').startswith('http'): t['target'] = '_blank'; t['rel'] = 'noopener'
            else: t.unwrap()
    html = str(soup)
    def link(m, n0=r['number']):
        n = m.group(2)
        return f'{m.group(1)}<a href="#{slug(n)}" class="xref">{n}</a>' if n.lower() in allnums and n.lower() != n0.lower() else m.group(0)
    html = re.sub(r'((?:Policy|Policies|Regulation|Bylaw)\s+(?:No\.\s*)?)(\d{4}[A-Za-z]?(?:\([a-z]\))?)(?![\w-])', link, html)
    out.append(dict(id=sid, n=r['number'], t=r['title'], s=r['section'], sub=r.get('subsection') or '', ty=r['type'],
                    a=r.get('adopted') or '', r=r.get('revised') or [], rv=r.get('reviewed') or '', lr=r.get('legal_refs') or [],
                    oc=r.get('old_code') or '', f=r['file'], h=html, pdf=r.get('fmt') == 'PDF'))

data = json.dumps(dict(sections=SECNAME, docs=out, built=datetime.date.today().isoformat()), separators=(',', ':')).replace('</', '<\\/')
page = (HERE / 'template.html').read_text().replace('__DATA__', data)
head, rest = page.split('</style>', 1)
(SITE / 'index.html').write_text('<!doctype html>\n<html lang="en">\n<head>\n<meta charset="utf-8">\n'
    '<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">\n'
    + head + '</style>\n</head>\n<body>\n' + rest + '\n</body>\n</html>\n')
print(f'Built site with {len(out)} documents -> {SITE / "index.html"}')
