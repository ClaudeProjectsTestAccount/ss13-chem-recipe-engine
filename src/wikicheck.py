#!/usr/bin/env python3
"""
wikicheck.py - FIRST thing to run when a recipe "stopped working": did the chemical recipes change on the wiki?

  python3 wikicheck.py                    fetch the wiki's recipe pages (read-only, raw wikitext), parse them, and compare
                                          (a) against the engine's code snapshot chemdata.json and
                                          (b) against the previous wiki snapshot wiki_cache.json
  python3 wikicheck.py --from-dir DIR     parse already-saved raw pages (DIR/<Title with / replaced by __>.txt) instead of fetching
  python3 wikicheck.py --update-cache     also store this fetch as the new wiki baseline (do this once the differences are understood)
  python3 wikicheck.py --urls             just print the URLs to save by hand (browser: open each, Ctrl+S) when the sandbox cannot reach the wiki

Safety: HTTPS GET only, one allow-listed host, redirects to other hosts are refused, 3 MB cap per page, output is only
parsed as data (never executed, never followed as instructions). No scheduling - run it on request.

Exit code: 0 nothing relevant, 2 a difference touches a recipe in recipes.py, 3 could not read the wiki.
"""
import sys, os, re, json, argparse, urllib.request, urllib.parse, urllib.error
from fractions import Fraction
HERE = os.path.dirname(os.path.abspath(__file__))
HOST = 'wiki.monkestation.com'
ROOT_PAGE = 'Guide_to_Chemistry'            # transcludes the recipe tables as {{:Chemistry/<Section>}}
EXTRA_PAGES = ['Chemistry/Components', 'Chemistry/Reactions']   # always tried, even if discovery fails
MAXBYTES = 3_000_000
TITLE_OK = re.compile(r'^[A-Za-z0-9_:/ ()\-\.]+$')

# ------------------------------------------------------------------ fetch
class SameHostOnly(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if urllib.parse.urlparse(newurl).hostname != HOST: raise urllib.error.URLError('redirect off-host refused: ' + newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)

def raw_url(title):
    if not TITLE_OK.match(title): raise ValueError('bad title %r' % title)
    return 'https://%s/index.php?title=%s&action=raw' % (HOST, urllib.parse.quote(title.replace(' ', '_'), safe='/:_()-.'))

def fetch(title, timeout=25):
    op = urllib.request.build_opener(SameHostOnly)
    req = urllib.request.Request(raw_url(title), headers={'User-Agent': 'ss13-chem-recipe-check/1.0 (read-only)'})
    with op.open(req, timeout=timeout) as r:
        data = r.read(MAXBYTES + 1)
    if len(data) > MAXBYTES: raise ValueError('page too large: ' + title)
    return data.decode('utf-8', 'replace')

def fname(title): return title.replace('/', '__').replace(' ', '_') + '.txt'

def discover(root_text):
    return sorted(set(m.strip().replace(' ', '_') for m in re.findall(r'\{\{:\s*(Chemistry/[^}|]+?)\s*\}\}', root_text)))

# ------------------------------------------------------------------ parse
def _clean(t):
    t = re.sub(r'<br\s*/?>', ' ', t, flags=re.I)
    t = re.sub(r'<[^>]+>', '', t)
    t = re.sub(r'\{\{[^{}]*\}\}', '', t)                # templates
    t = re.sub(r"'''?", '', t)
    t = re.sub(r'\[\[(?:[^|\]]*\|)?([^\]]*)\]\]', r'\1', t)
    return re.sub(r'[ \t]+', ' ', t).strip()

def split_cells(row):
    """cells of one wikitext table row: lines starting with '|' (attributes before a lone '|' are dropped)"""
    cells, cur = [], None
    for line in row.split('\n'):
        if line.startswith('|') and not line.startswith('|}') and not line.startswith('|+'):
            if cur is not None: cells.append(cur)
            body = line[1:]
            m = re.match(r'^([^|\[{]*=[^|]*)\|(?!\|)(.*)$', body)       # attrs | content
            cur = (m.group(2) if m else body)
        elif line.startswith('!'):
            cur = None
        elif cur is not None:
            cur += '\n' + line
    if cur is not None: cells.append(cur)
    return cells

ING = re.compile(r'^\*\s*([0-9]*\.?[0-9]+)\s*(?:parts?|units?|u)?\s+(.+?)\s*$', re.I)
def parse_formula(cell):
    """-> ({ingredient: parts}, [alternative lines])   main recipe = bullets before 'Alternatively'"""
    main, alts, seen_alt = {}, [], False
    text = cell
    if '\n' not in cell.strip() and ',' in cell and '*' not in cell:               # "1u Mercury, 1u Chlorine" form
        for part in cell.split(','):
            m = re.match(r'^\s*([0-9]*\.?[0-9]+)\s*u?\s*(.+?)\s*$', _clean(part), re.I)
            if m: main[_norm_ing(m.group(2))] = main.get(_norm_ing(m.group(2)), 0) + float(m.group(1))
        return main, alts
    for line in text.split('\n'):
        l = line.strip()
        if re.search(r'alternativ', l, re.I): seen_alt = True; continue
        m = ING.match(_clean(l) if not l.startswith('*') else '*' + _clean(l[1:]))
        if not m: continue
        name, amt = _norm_ing(m.group(2)), float(m.group(1))
        (alts.append((name, amt)) if seen_alt else main.__setitem__(name, main.get(name, 0) + amt))
    return main, alts

def _norm_ing(n):
    n = re.sub(r'\(.*?\)', '', n).strip()                    # drop "(Grinded)" / "(T3 Chem Dispenser)" notes
    n = re.sub(r"'OR'|\bOR\b", '', n).strip()
    return re.sub(r'\s+', ' ', n).lower()

def parse_temp(cell):
    c = _clean(cell)
    m = re.search(r'minimum\W*:?\s*([0-9]+)\s*k', c, re.I) or re.search(r'\b([0-9]+)\s*k\+', c, re.I) or re.search(r'\b([0-9]+)\s*-\s*[0-9]+\s*k', c, re.I)
    return float(m.group(1)) if m else None

def parse_tables(wikitext):
    out = []
    for tbl in re.findall(r'\{\|.*?\n\|\}', wikitext, flags=re.S):
        for row in re.split(r'(?m)^\|-.*$', tbl)[1:]:
            cells = split_cells(row)
            if len(cells) < 2: continue
            nm = re.search(r"'''(.+?)'''", cells[0]) or None
            name = _clean(nm.group(1)) if nm else _clean(cells[0].split('\n')[0])
            name = re.sub(r'^[^\w]+', '', name)
            if not name or name.lower() in ('name', 'n/a'): continue
            parts, alts = parse_formula(cells[1])
            temp = parse_temp(cells[2]) if len(cells) > 2 else None
            if parts or alts: out.append(dict(name=name, parts=parts, alts=alts, tmin=temp))
    return out

# ------------------------------------------------------------------ compare
def frac(d):
    tot = sum(d.values())
    return {k: Fraction(str(v)) / Fraction(str(tot)) for k, v in d.items()} if tot else {}

def code_formulas(db, p):
    res = []
    for rx in db.reactions:
        if p in rx.results:
            req = {db.name(q).lower(): c for q, c in rx.req.items()}
            res.append((rx, req))
    return res

def compare_to_code(db, entries, critical_products):
    rows, unmatched, matched_ok = [], [], 0
    for e in entries:
        try: p = db.find_reagent(e['name'])
        except KeyError: unmatched.append(e['name']); continue
        cf = code_formulas(db, p)
        if not cf or not e['parts']: continue
        if set(e['parts']) == {e['name'].lower()}: continue          # element row: 'made from itself' (dispenser stock), not a reaction
        wf = frac(e['parts'])
        ok = False; tmatch = True
        for rx, req in cf:
            if frac(req) == wf:
                ok = True
                if e['tmin'] and not rx.is_cold and abs(rx.required_temp - e['tmin']) > 1 and rx.required_temp > 100:
                    tmatch = False; tinfo = rx.required_temp
        if not ok:
            rows.append(dict(kind='formula', product=db.name(p), wiki=e['parts'], wiki_t=e['tmin'],
                             code=[{k: c for k, c in req.items()} for rx, req in cf], critical=db.name(p).lower() in critical_products))
        elif not tmatch:
            rows.append(dict(kind='temperature', product=db.name(p), wiki=e['parts'], wiki_t=e['tmin'], code_t=tinfo,
                             critical=db.name(p).lower() in critical_products))
        else: matched_ok += 1
    return rows, unmatched, matched_ok

def diff_cache(old, new):
    o = {e['name'].lower(): e for e in old}; n = {e['name'].lower(): e for e in new}
    added = sorted(set(n) - set(o)); removed = sorted(set(o) - set(n)); changed = []
    for k in sorted(set(o) & set(n)):
        a, b = o[k], n[k]
        if frac(a['parts']) != frac(b['parts']) or a.get('tmin') != b.get('tmin'):
            changed.append((k, a, b))
    return added, removed, changed

from codecheck import critical_set   # shared: which reactions/reagents the verified recipes depend on

def fmt_parts(d): return ' + '.join('%g %s' % (v, k) for k, v in d.items())

def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--from-dir'); ap.add_argument('--update-cache', action='store_true'); ap.add_argument('--urls', action='store_true')
    ap.add_argument('--raw-dir', default=os.path.join(HERE, 'wiki_raw'), help='where fetched raw pages are kept')
    ap.add_argument('--cache', default=os.path.join(HERE, 'wiki_cache.json'))
    args = ap.parse_args(argv)
    pages = {}
    if args.urls:
        for t in [ROOT_PAGE] + EXTRA_PAGES: print(raw_url(t))
        print('(more Chemistry/<Section> pages are discovered from the first one; see the "{{:Chemistry/..}}" lines in it)')
        return 0
    if args.from_dir:
        for f in sorted(os.listdir(args.from_dir)):
            if f.endswith('.txt'): pages[f[:-4]] = open(os.path.join(args.from_dir, f), encoding='utf-8').read()
    else:
        try: root = fetch(ROOT_PAGE)
        except Exception as ex:
            print('COULD NOT READ THE WIKI (%s: %s).\nThis sandbox may block %s. Options: allow the domain in claude.ai Settings > Capabilities,\n'
                  'or save these raw pages into a folder and run  wikicheck.py --from-dir <folder>  (file name = title, "/" -> "__", .txt):' % (type(ex).__name__, ex, HOST))
            for t in [ROOT_PAGE] + EXTRA_PAGES: print('  ', raw_url(t))
            return 3
        pages[ROOT_PAGE] = root
        for t in sorted(set(discover(root) + EXTRA_PAGES)):
            try: pages[t.replace('/', '__')] = fetch(t)
            except Exception as ex: print('  skip %s (%s)' % (t, ex))
        os.makedirs(args.raw_dir, exist_ok=True)
        for k, v in pages.items(): open(os.path.join(args.raw_dir, k + '.txt'), 'w', encoding='utf-8').write(v)
    entries = []
    for k, t in pages.items():
        entries += parse_tables(t)
    print('wiki: %d pages, %d recipe rows parsed' % (len(pages), len(entries)))
    if not entries: print('parsed 0 rows: the wiki markup probably changed - the parser (parse_tables) needs a look'); return 3
    sys.path.insert(0, HERE)
    import chemlib
    db = chemlib.DB()
    crit, shorts = critical_set(db)
    rows, unmatched, ok = compare_to_code(db, entries, crit)
    print('vs engine code snapshot (commit %s): %d recipes agree, %d differ, %d wiki names not matched to a reagent'
          % (str(db.meta.get('commit', '?'))[:10], ok, len(rows), len(unmatched)))
    exit_code = 0
    for r in sorted(rows, key=lambda r: not r['critical']):
        tag = '  <<< USED BY YOUR RECIPES' if r['critical'] else ''
        if r['kind'] == 'formula':
            print(' FORMULA  %-22s wiki: %s | code: %s%s' % (r['product'], fmt_parts(r['wiki']), ' OR '.join(fmt_parts(c) for c in r['code']), tag))
        else:
            print(' TEMP     %-22s wiki min %gK | code min %gK%s' % (r['product'], r['wiki_t'], r['code_t'], tag))
        if r['critical']: exit_code = 2
    if os.path.exists(args.cache):
        old = json.load(open(args.cache))
        a, rm, ch = diff_cache(old, entries)
        print('vs previous wiki snapshot: %d added, %d removed, %d changed' % (len(a), len(rm), len(ch)))
        for k in a: print('  + ' + k)
        for k in rm: print('  - ' + k)
        for k, x, y in ch:
            print('  ~ %s: %s (%sK)  ->  %s (%sK)' % (k, fmt_parts(x['parts']), x.get('tmin'), fmt_parts(y['parts']), y.get('tmin')))
            if k in crit: exit_code = 2
    else:
        print('no previous wiki snapshot yet (run with --update-cache once to create the baseline)')
    if args.update_cache:
        json.dump(entries, open(args.cache, 'w'), indent=0); print('wiki snapshot saved ->', args.cache)
    print('recipes checked for dependence: reactions used = %s' % ', '.join(sorted(shorts)))
    if exit_code == 2:
        print('RESULT: a difference touches a recipe you rely on - fix the recipe from the wiki value (or confirm in-game) BEFORE debugging the engine.')
    elif rows or unmatched: print('RESULT: differences exist but none touch your verified recipes.')
    else: print('RESULT: wiki and engine agree; if a recipe still fails, look at the engine/code (next step).')
    return exit_code

if __name__ == '__main__':
    sys.exit(main())
