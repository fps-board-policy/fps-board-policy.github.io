"""FPS Board Policy converter.

Reads every Word (.docx) and PDF file in the "Section ..." folders, pulls out the
number, title, dates and legal references, and writes build/policies.json plus a
list of problems (build/issues.json and build/checks.md).

Usage:  python tools/convert.py <repo folder> <output folder>
"""
import re, json, zipfile, subprocess, difflib, datetime, collections, sys
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from bs4 import BeautifulSoup
import docx

ROOT = Path(sys.argv[1]); OUT = Path(sys.argv[2]); OUT.mkdir(exist_ok=True)
TODAY = datetime.date.today()
REVIEW_CUTOFF = TODAY.replace(year=TODAY.year - 3) if not (TODAY.month == 2 and TODAY.day == 29) else TODAY.replace(year=TODAY.year - 3, day=28)   # Policy 9200: review every 3 years
SERIES = ['Community Relations', 'Administration', 'Administrative', 'Business Operations', 'Business', 'Personnel',
          'Students', 'Instruction', 'New Construction', 'Internal Board Policies', 'Bylaws of the Board']
SERIES_RE = re.compile(r'^(%s)\b(.*)$' % '|'.join(map(re.escape, sorted(SERIES, key=len, reverse=True))), re.I)
META_RE = re.compile(r'^(Date of Adoption|Date Adopted|Adopted|Revised|Reviewed|Updated|Amended|Legal References?|Legal Authorities|Reference|Cross Reference|Policy Review/Revision)\s*:\s*(.*)$', re.I)
DATE_RE = re.compile(r'(January|February|March|April|May|June|July|August|September|October|November|December)\s*,?\s+(\d{1,2},\s*)?\d{4}')

issues = []
def flag(sec, num, sev, kind, detail): issues.append(dict(section=sec, policy=num, severity=sev, type=kind, detail=detail))

def parse_date(s):
    m = DATE_RE.search(s or '')
    if not m: return None
    t = re.sub(r'^(\w+)\s*,\s*(\d{4})$', r'\1 \2', m.group(0).replace(' ,', ','))
    for f in ('%B %d, %Y', '%B %d,%Y', '%B %Y'):
        try: return datetime.datetime.strptime(t, f).date()
        except ValueError: pass

def parse_filename(name):
    stem = re.sub(r'(\.DOC)?\.docx$|\.pdf$', '', name, flags=re.I).strip()
    template = stem.upper().startswith('TEMPLATE')
    stem = re.sub(r'^TEMPLATE\s+', '', stem, flags=re.I)
    m = re.match(r'^(\d{4})([A-Za-z]?)(\([a-z]\))?(\.\d+)?(?:_([0-9A-Za-z.]+))?\s*(?:-+\s*|\s+)(.*)$', stem)
    if m:
        base, suf, paren, dot, alias, rest = m.groups()
        num = base + (suf or '') + (paren or '') + (dot or '')
        return dict(number=num, base=base, suffix=(suf or '') + (dot or ''), old_code=alias, ftitle=rest, template=template, legacy_number=False)
    m = re.match(r'^(\d{2}[A-Z](?:\.\d+[a-z]?\d*)?)\s*(?:-+\s*|\s+)(.*)$', stem)
    if m: return dict(number=m.group(1), base=None, suffix='', old_code=m.group(1), ftitle=m.group(2), template=template, legacy_number=True)
    return None

def clean_ftitle(t):
    t = re.sub(r'_\s*$', '', t.strip()); t = t.replace('_ ', ': ').replace('_', '/')
    return re.sub(r'\s+', ' ', t).strip(' -')

def headers(path):
    with zipfile.ZipFile(path) as z:
        names = z.namelist()
        hdr = [re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', z.read(n).decode('utf8'))).strip() for n in names if re.match(r'word/header\d*\.xml', n)]
        xml = z.read('word/document.xml').decode('utf8')
        tracked = '<w:ins ' in xml or '<w:del ' in xml
        comments = any('comments' in n for n in names)
    return [h for h in hdr if h], tracked, comments

def doc_type(ftitle, first_lines, template):
    t = (ftitle + ' ' + ' '.join(first_lines[:2])).lower()
    if template: return 'Template'
    if 'resolution' in t: return 'Resolution'
    if re.search(r'\bforms?\b|affidavit|application|complaint form|notice of performance|consent', t): return 'Form'
    if 'regulation' in ftitle.lower(): return 'Regulation'
    if re.search(r'protocol|\bplan\b|notification of rights|notice of nondiscrimination|ledger|sample minutes', t): return 'Exhibit'
    return 'Policy'

def html_of(path):
    return subprocess.run(['pandoc', str(path), '-t', 'html', '--wrap=none'], capture_output=True, text=True).stdout

def process(path):
    sec_folder = path.parent.name
    sec_num = re.match(r'Section (\d+)', sec_folder).group(1)
    fn = parse_filename(path.name)
    rec = dict(section=sec_num, section_name=re.sub(r'^Section \d+ ', '', sec_folder), file=path.name, parse_ok=bool(fn))
    if not fn: return rec
    rec.update(fn); rec['ftitle'] = clean_ftitle(fn['ftitle'])
    if path.suffix.lower() == '.pdf':
        txt = subprocess.run(['pdftotext', str(path), '-'], capture_output=True, text=True).stdout
        rec.update(fmt='PDF', title=rec['ftitle'], body_html='', body_text=re.sub(r'\s+', ' ', txt), words=len(txt.split()),
                   type='Form', headers=[], tracked=False, comments=False, meta=[], legal_refs=[], series_label=None, subsection=None)
        return rec
    soup = BeautifulSoup(html_of(path), 'html.parser')
    for li in soup.find_all('li'):
        for bq in li.find_all('blockquote', recursive=False): bq.unwrap()
    els = [e for e in soup.children if getattr(e, 'name', None)]
    texts = [e.get_text(' ', strip=True) for e in els]
    while els and not texts[0]: els.pop(0); texts.pop(0)
    rec['headers'], rec['tracked'], rec['comments'] = headers(path)
    m = SERIES_RE.match(texts[0]) if texts else None
    if m and len(texts[0]) < 90:
        rest = m.group(2).strip()
        rec['fmt'] = 'Standard'
        if re.match(r'^[-–—:]', rest): rec['series_label'] = m.group(1); rec['subsection'] = rest.lstrip('-–—: ').strip() or None
        else: rec['series_label'] = texts[0]; rec['subsection'] = None
        rec['title'] = texts[1]; start = 2
        rec['_alt'] = texts[2] if len(texts) > 2 and len(texts[2]) < 90 and not texts[2].rstrip().endswith(('.', ':')) else None
        # variant: series / subsection / title on three separate lines
        if rec['subsection'] is None and len(texts) > 2 and len(texts[2]) < 90 and not texts[2].rstrip().endswith(('.', ':')) and not re.match(r'^(\d|[A-Z]\.|\()', texts[2]):
            ft = clean_ftitle(fn['ftitle'])
            if difflib.SequenceMatcher(None, texts[2].lower(), ft.lower()).ratio() > difflib.SequenceMatcher(None, texts[1].lower(), ft.lower()).ratio():
                rec['subsection'] = texts[1]; rec['title'] = texts[2]; start = 3
    elif texts and texts[0].lower().startswith('fremont board policy'):
        rec['fmt'] = 'Legacy'; rec['series_label'] = None; rec['subsection'] = None
        rec['title_caps'] = texts[1]; rec['title'] = None; start = 2
    else:
        rec['fmt'] = 'No header'; rec['series_label'] = None; rec['subsection'] = None; rec['title'] = None; start = 0
    # metadata block: the first label-led block that contains a date (inline legal refs mid-policy stay in the body)
    def scan(k, els, texts):
        tail = []
        for e in els[k:]:
            if e.name == 'blockquote': tail += [c for c in e.children if getattr(c, 'name', None)]
            else: tail.append(e)
        els2 = els[:k] + tail; texts2 = texts[:k] + [e.get_text(' ', strip=True) for e in tail]
        meta, legal, mode, j = [], [], None, k
        while j < len(els2):
            t = texts2[j]; mm = META_RE.match(t)
            if not t: j += 1; continue
            if mm: mode = mm.group(1).lower(); val = mm.group(2)
            elif mode and mode.startswith(('legal', 'reference', 'cross')) and len(t) < 400 and els2[j].name == 'p' and not re.match(r'^(APPENDIX|EXHIBIT|AR-|ATTACHMENT|FORM)', t, re.I): val = t
            elif mode and DATE_RE.fullmatch(t.strip()): val = t
            else: break
            if val:
                if mode.startswith(('legal', 'reference', 'cross')): legal.append(val)
                else: meta.append((mode, val))
            j += 1
        return els2, texts2, meta, legal, j
    meta, legal, end, after = [], [], len(els), len(els)
    for k in [i for i in range(start + 1, len(els)) if META_RE.match(texts[i])]:
        e2, t2, m2, l2, j = scan(k, els, texts)
        if m2 or j >= len(e2):
            els, texts, meta, legal, end, after = e2, t2, m2, l2, k, j; break
    for t in texts[start:end] + texts[after:]:
        mm = META_RE.match(t)
        if mm and parse_date(mm.group(2)) and not mm.group(1).lower().startswith(('legal', 'ref', 'cross')):
            meta.append((mm.group(1).lower(), mm.group(2))); rec['meta_in_body'] = True
    rec['has_appendix'] = after < len(els)
    body = ''.join(str(e) for e in els[start:end])
    if after < len(els): body += '<section class="appendix">' + ''.join(str(e) for e in els[after:]) + '</section>'
    rec['meta'] = meta; rec['legal_refs'] = legal
    rec['body_html'] = body
    rec['body_text'] = BeautifulSoup(body, 'html.parser').get_text(' ', strip=True)
    rec['words'] = len(rec['body_text'].split())
    rec['type'] = doc_type(rec['ftitle'], texts, rec['template'])
    return rec

files = sorted(p for d in ROOT.glob('Section *') if d.is_dir() for p in d.iterdir()
               if p.is_file() and p.suffix.lower() in ('.docx', '.pdf') and 'index' not in p.name.lower() and not p.name.startswith('~$'))
def safe_process(path):
    try: return process(path)
    except Exception as e:
        return dict(section=re.match(r'Section (\d+)', path.parent.name).group(1), section_name='', file=path.name, parse_ok=False, error=str(e)[:200])
with ThreadPoolExecutor(8) as ex: recs = list(ex.map(safe_process, files))

# ---------- section indexes
indexes = {}
for f in sorted(ROOT.glob('Section */Section*Index*.docx')):
    sec = re.match(r'Section (\d+)', f.name).group(1)
    d = docx.Document(f); entries = []
    for t in d.tables:
        for r in t.rows:
            cells = [c.text.strip() for c in r.cells]
            if not cells or not cells[0] or 'Alphabetical' in cells[0]: continue
            num = next((c for c in cells[1:] if c), '')
            ns = num.split() or ['']
            for n_ in ns:
                entries.append(dict(title=re.sub(r'\s+', ' ', cells[0]), number=n_, shared=len(ns) > 1))
    heading = [p.text.strip() for p in d.paragraphs if re.match(r'(Section|Alphabetical Index)', p.text.strip())]
    rev = [p.text.strip() for p in d.paragraphs if re.search(r'\d+/\d+/\d+', p.text)]
    indexes[sec] = dict(file=f.name, entries=entries, heading=heading[-1] if heading else '', revised=rev[-1] if rev else '')

def norm(s): return re.sub(r'[^a-z0-9 ]', ' ', (s or '').lower().replace('&', 'and')).split()
def sim(a, b): return difflib.SequenceMatcher(None, ' '.join(norm(a)), ' '.join(norm(b))).ratio()
def smart_title(caps):
    small = {'a', 'an', 'and', 'or', 'of', 'the', 'to', 'in', 'on', 'for', 'by', 'at', 'with'}
    caps = re.sub(r'\s*/\s*', ' / ', caps)
    w = caps.rstrip('*').lower().split()
    return ' '.join(x if (i and x in small) else (x.upper() if re.match(r'^\d|^[ivx]+$', x) and len(x) < 5 else x[:1].upper() + x[1:]) for i, x in enumerate(w)).replace(' / ', '/')

# ---------- per-record checks
SEC_SERIES = {'10': 'community relations', '20': 'administration', '30': 'business', '40': 'personnel', '50': 'students',
              '60': 'instruction', '70': 'new construction', '80': 'internal board', '90': 'bylaws of the board'}
for r in recs:
    s = r['section']
    if not r['parse_ok']:
        if r.get('error'): flag(s, r['file'], 'Needs decision', 'Unreadable file', 'File could not be opened (' + r['error'] + '). It was left off the site; re-save it from Word and upload again.')
        else: flag(s, r['file'], 'Needs decision', 'Filename', 'Filename does not begin with a policy number, so it was left off the site. Rename it like "5415 Anti-Bullying Policy.docx".')
        continue
    n = r['number']; idx = indexes.get(s, {}).get('entries', [])
    by_num = [e for e in idx if e['number'].lower() == n.lower()]
    if r['legacy_number']:
        g = f' The section index still lists it under {n} too.' if by_num else ' It is not in the section index.'
        flag(s, n, 'Fix before launch', 'Old numbering', f'Still uses old-style number {n} — needs a new 4-digit number.{g}')
    if r.get('old_code') and not r['legacy_number']:
        flag(s, n, 'Auto-fixed', 'Old numbering', f'Filename also carries old code {r["old_code"]}; kept as a searchable alias.')
    # title
    if r['fmt'] == 'Legacy':
        r['title'] = smart_title(r['title_caps'])
        flag(s, n, 'Fix before launch', 'Old template', 'Uses the old "Fremont Board Policy ####" layout (ALL-CAPS title, no series line). Converts fine, but should be moved to the current template for consistency.')
    if r.get('_alt') and r['subsection'] is None and by_num and sim(r['_alt'], by_num[0]['title']) > max(.7, sim(r['title'], by_num[0]['title'])):
        r['subsection'], r['title'] = r['title'], r['_alt']
    if not r['title']:
        r['title'] = by_num[0]['title'] if (by_num and r['type'] == 'Policy') else r['ftitle']
    if r['type'] in ('Policy', 'Regulation') and r['fmt'] == 'No header':
        flag(s, n, 'Fix before launch', 'Missing heading', 'No series line or title at the top of the document; title taken from the filename.')
    # series label vs folder
    if r.get('series_label') and SEC_SERIES[s].split()[0] not in r['series_label'].lower() and not (s == '20' and r['series_label'].lower().startswith('admin')):
        flag(s, n, 'Fix before launch', 'Wrong section label', f'First line says "{r["series_label"]}" but the file is in Section {s} ({r["section_name"]}).')
    # headers
    hnums = set()
    for h in r.get('headers', []):
        hnums |= {x.replace(' ', '') for x in re.findall(r'Policy (?:No\.\s*)?(?:Regulation\s*)?(\d{4}[A-Za-z]?(?:\s*\([a-z]\))?|\d{2}[A-Z][\w.]*)', h)}
    base = r['base'] or n
    if hnums and not any(h.lower() in (n.lower(), base.lower()) for h in hnums):
        flag(s, n, 'Cosmetic (Word only)', 'Page header', f'Page header shows Policy No. {", ".join(sorted(hnums))} — filename says {n}.')
    elif len(hnums) > 1 and r['type'] == 'Policy':
        flag(s, n, 'Cosmetic (Word only)', 'Page header', f'Different page headers in the same file show {", ".join(sorted(hnums))}.')
    hdr_series = set(re.findall(r'Article \d+ ([A-Z][A-Z ]+?) Policy', ' '.join(r.get('headers', []))))
    if len(hdr_series) > 1: flag(s, n, 'Cosmetic (Word only)', 'Page header', f'Page headers mix series names: {", ".join(sorted(hdr_series))} (copy-paste leftover).')
    if r.get('tracked'): flag(s, n, 'Fix before launch', 'Tracked changes', 'File contains unaccepted tracked changes — confirm which text is official.')
    if r.get('comments'): flag(s, n, 'Fix before launch', 'Comments', 'File contains Word comments.')
    # dates
    dates = [(lab, parse_date(v), v) for lab, v in r['meta']]
    adopted = [d for lab, d, v in dates if 'adopt' in lab and d]
    revised = [d for lab, d, v in dates if lab in ('revised', 'updated', 'amended', 'policy review/revision') and d]
    reviewed = [d for lab, d, v in dates if lab == 'reviewed' and d]
    for lab, d, v in dates:
        if not d and lab not in ('date',): flag(s, n, 'Fix before launch', 'Dates', f'Unreadable or placeholder date: "{lab.title()}: {v}"')
    r['adopted'] = min(adopted).isoformat() if adopted else None
    r['revised'] = sorted({d.isoformat() for d in revised})
    r['reviewed'] = max(reviewed).isoformat() if reviewed else None
    alld = adopted + revised + reviewed
    r['last_action'] = max(alld).isoformat() if alld else None
    if r['type'] in ('Policy', 'Regulation') and not adopted:
        flag(s, n, 'Fix before launch', 'Dates', 'No adoption date found.')
    if len(set(adopted)) > 1:
        flag(s, n, 'Info', 'Dates', f'Lists more than one "Adopted" date ({", ".join(d.strftime("%-m/%-d/%Y") for d in sorted(adopted))}); earliest used as adoption, all kept as history.')
    if r.get('has_appendix'): flag(s, n, 'Info', 'Appendix', 'Policy is followed by an appendix/exhibit in the same file; shown below the policy on the web page.')
    if r['type'] == 'Policy' and r['fmt'] != 'PDF' and re.search(r'\[insert|\bXX+\b|\[date\]|TBD', r['body_text'] + ' '.join(v for _, v in r['meta']), re.I):
        flag(s, n, 'Fix before launch', 'Placeholder text', 'Contains placeholder text such as "[Insert …]".')
    if r['type'] == 'Policy' and r['words'] < 15:
        flag(s, n, 'Needs decision', 'Empty', f'Body has only {r["words"]} words.')
    if r['type'] == 'Template': flag(s, n, 'Needs decision', 'Template', 'Blank template file — probably should not be on the public site.')
    if r['fmt'] == 'PDF': flag(s, n, 'Info', 'PDF', 'PDF form; will be posted as a downloadable attachment (text is searchable).')

# duplicates: same number, both treated as primary policy
cnt = collections.defaultdict(list)
for r in recs:
    if r['parse_ok'] and r['type'] == 'Policy': cnt[(r['section'], r['number'])].append(r)
for (s, n), rs in cnt.items():
    if len(rs) > 1: flag(s, n, 'Needs decision', 'Duplicate number', 'Two files share this number: ' + ' | '.join(x['file'] for x in rs))

# resolutions by year
res = [r for r in recs if r['parse_ok'] and r['type'] == 'Resolution' and re.search(r'\d{2}-\d{2}', r['file'])]
if len(res) > 1:
    yrs = sorted(res, key=lambda r: re.search(r'(\d{2})-\d{2}', r['file']).group(1))
    for r in yrs[:-1]:
        flag(r['section'], r['number'], 'Needs decision', 'Superseded?', f'Older capacity resolution ({r["file"]}). Post only the current year ({yrs[-1]["file"].strip()}), or keep prior years as an archive?')

# ---------- index cross-check
for s, ix in indexes.items():
    files_here = [r for r in recs if r['section'] == s and r['parse_ok']]
    nums = {r['number'].lower() for r in files_here} | {r['base'].lower() for r in files_here if r['base']}
    for e in ix['entries']:
        if not e['number']:
            m = max(files_here, key=lambda r: sim(r['title'], e['title']))
            hint = f' (looks like {m["number"]} "{m["title"]}")' if sim(m['title'], e['title']) > .7 else ''
            flag(s, '—', 'Fix before launch', 'Section index', f'Index lists "{e["title"]}" with no policy number{hint}.')
        elif e['number'].lower() not in nums:
            flag(s, e['number'], 'Needs decision', 'Missing file', f'Index lists {e["number"]} "{e["title"]}" but there is no file for it. Rescinded, or missing from the folder?')
        else:
            r = next(r for r in files_here if r['number'].lower() == e['number'].lower() or (r['base'] or '').lower() == e['number'].lower())
            sc = sim(r['title'], e['title'])
            it, dt = set(norm(e['title'])), set(norm(r['title']))
            if e.get('shared'):
                flag(s, e['number'], 'Fix before launch', 'Section index', f'Index puts two numbers ({" & ".join(x["number"] for x in ix["entries"] if x["title"] == e["title"])}) on one line "{e["title"]}"; give each its own line.') if e['number'] == next(x['number'] for x in ix['entries'] if x['title'] == e['title']) else None
            elif sc < .9 and it and len(it & dt) / len(it) >= .75 and r['type'] == 'Policy':
                flag(s, e['number'], 'Info', 'Index title differs slightly', f'Index: "{e["title"]}"  |  Document: "{r["title"]}". Close enough to match; the web app will use the document title. Align them if you like.')
            elif sc < .55 and r['type'] == 'Policy':
                flag(s, e['number'], 'Fix before launch', 'Title mismatch', f'Index says "{e["title"]}", document title is "{r["title"]}". Which is correct?')
    idx_nums = {e['number'].lower() for e in ix['entries'] if e['number']}
    idx_titles = [e['title'] for e in ix['entries']]
    for r in files_here:
        if r['type'] != 'Policy': continue
        if r['number'].lower() in idx_nums or (r['base'] or '').lower() in idx_nums: continue
        if any(sim(t, r['title']) > .8 for t in idx_titles): continue
        flag(s, r['number'], 'Fix before launch', 'Not in index', f'"{r["title"]}" has a file but is not listed in the Section {s} index.')

# ---------- cross references inside body text
allnums = {r['number'].lower() for r in recs if r['parse_ok']} | {(r['base'] or '').lower() for r in recs if r['parse_ok']}
for r in recs:
    if not r['parse_ok'] or not r.get('body_text'): continue
    refs = set(re.findall(r'(?:[Pp]olic(?:y|ies)|[Rr]egulation|[Bb]ylaw)\s+(?:No\.\s*)?(\d{4}[A-Za-z]?|\d{2}[A-Z]\.\d+[a-z0-9]*|\d{2}[A-Z])\b', r['body_text']))
    r['xrefs'] = sorted(x for x in refs if x.lower() != r['number'].lower())
    for x in r['xrefs']:
        if re.match(r'^\d{2}[A-Z]', x): flag(r['section'], r['number'], 'Fix before launch', 'Cross-reference', f'Text refers to old-style policy number "{x}" — update to the new number.')
        elif x.lower() not in allnums: flag(r['section'], r['number'], 'Fix before launch', 'Cross-reference', f'Text refers to Policy {x}, which does not exist in the manual.')

# review status
for r in recs:
    if r.get('type') in ('Policy', 'Regulation') and r.get('last_action'):
        r['review_overdue'] = datetime.date.fromisoformat(r['last_action']) < REVIEW_CUTOFF

for r in recs:
    r.pop('title_caps', None); r.pop('_alt', None)
json.dump(dict(generated=TODAY.isoformat(), indexes=indexes, records=recs), open(OUT / 'policies.json', 'w'), indent=1, default=str)
json.dump(issues, open(OUT / 'issues.json', 'w'), indent=1)
c = collections.Counter(i['severity'] for i in issues); t = collections.Counter(i['type'] for i in issues)
print(len(recs), 'records', collections.Counter(r.get('fmt') for r in recs), collections.Counter(r.get('type') for r in recs))
print(c); print(t)

order = ['Needs decision', 'Fix before launch', 'Cosmetic (Word only)', 'Info', 'Auto-fixed']
lines = [f'# Policy checks — {TODAY.strftime("%B %-d, %Y")}', '',
         f'{sum(1 for r in recs if r["parse_ok"])} documents converted. ' + ', '.join(f'{c[k]} {k.lower()}' for k in order if c.get(k)) + '.', '']
for sev in order[:2]:
    rows = [i for i in issues if i['severity'] == sev]
    if not rows: continue
    lines += [f'## {sev} ({len(rows)})', '', '| Section | Policy | Issue | Detail |', '|---|---|---|---|']
    lines += [f"| {i['section']} | {i['policy']} | {i['type']} | {i['detail'].replace('|', '/')} |" for i in rows] + ['']
open(OUT / 'checks.md', 'w').write('\n'.join(lines))
