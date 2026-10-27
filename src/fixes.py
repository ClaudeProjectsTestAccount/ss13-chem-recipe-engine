"""
fixes.py - repair the recipes the engine flags BROKEN (chemicals that take up beaker space and do nothing).

Almost every case is the same cause: the ingredients were not fed in exact proportions, so an intermediate (oil, phenol, ammonia) or a raw reagent was left over.
payload.py rebuilds the recipe from exact amounts (stoich.py).  Where the smallest exact batch does not fit the beaker (libital needs 135u at the very least) there is
no honest fix and the recipe is removed.

  chemcli.py fixbroken            show what would change
  chemcli.py fixbroken --apply    rebuild / remove and rewrite the page
"""
import book, payload

# recipes with no exact version that fits the gear (the smallest exact batch is too big for the beaker or the area)
REMOVE = {
    'libital-fog-100-15':   'libital needs a 135u batch to leave nothing over (oil and phenol are left otherwise); a 100u beaker cannot hold that plus the smoke powder',
    'libital-foam-100-60':  'same: libital needs a 135u batch, which does not fit a 100u beaker',
    'aiuri-fog-100-60':     'aiuri needs a 60u batch; with the 60u syringe the smallest cloud (20u of trigger = 60 tiles) also needs 40u of smoke powder and the 20u trigger, which leaves no room: use the 30 tile aiuri fog (works with both syringes)',
    'medfog-strong-300-60': 'the all-round fog needs 195u (libital 135u + aiuri 60u) of payload, but a 120 tile cloud leaves only 180u; replaced by the 90 tile all-round fog (medfog-wide-300-60), and the 180 tile cloud by the wide burn fog',
}

# recipes rebuilt from exact amounts.  (id, text copied from base, kind, beaker, syringe, draw, products, payload, title)
REBUILD = [
    dict(id='aiuri-fog-100-15', base='aiuri-fog-100-15', kind='smoke', beaker=100, syringe=15, draw=10, products=[('aiuri', 60)], payload='aiuri',
         title='Burn-mender fog (aiuri smoke, 30 tiles)', tagline='Smoke that heals burn damage on everyone breathing it'),
    dict(id='aiuri-fog-300-15', base='aiuri-fog-100-15', kind='smoke', beaker=300, syringe=15, draw=15, products=[('aiuri', 60)], payload='aiuri',
         title='Burn-mender fog (aiuri smoke, 45 tiles) - 300u beaker', tagline='The same aiuri dose over a bigger cloud'),
    dict(id='aiuri-fog-300-60', base='aiuri-fog-100-15', kind='smoke', beaker=300, syringe=60, draw=60, products=[('aiuri', 60)], payload='aiuri',
         title='Burn-mender fog, wide (180 tiles) - 300u beaker', tagline='The same aiuri dose over 180 tiles'),
    dict(id='libital-fog-300-15', base='libital-fog-100-15', kind='smoke', beaker=300, syringe=15, draw=15, products=[('libital', 135)], payload='libital',
         title='Brute-mender fog (libital smoke, 45 tiles) - 300u beaker', tagline='Libital smoke: 135u is the smallest batch with nothing left over'),
    dict(id='libital-foam-300-60', base='libital-foam-100-60', kind='foam', beaker=300, syringe=60, draw=60, products=[('libital', 135)], payload='libital',
         title='Brute-mender foam, wide (120 tiles) - 300u beaker', tagline='Libital foam spread thin over 120 tiles'),
    dict(id='medfog-300-15', base='medfog-300-15', kind='smoke', beaker=300, syringe=15, draw=15, products=[('libital', 135), ('aiuri', 60)], payload='libital',
         title='All-round medfog (45 tiles)', tagline='Brute + burn healing, 45 tile cloud'),
    dict(id='medfog-wide-300-60', base='medfog-300-15', kind='smoke', beaker=300, syringe=60, draw=30, products=[('libital', 135), ('aiuri', 60)], payload='libital',
         title='All-round medfog, wide (90 tiles)', tagline='Brute + burn healing, 90 tile cloud'),
    dict(id='drying-foam-300-15', base='drying-foam-100-15', kind='foam', beaker=300, syringe=15, draw=15, products=[('drying agent', 'max')], payload='drying agent',
         title='Drying foam - removes lube and wet floors (30 tiles) - 300u beaker', tagline='The most drying agent that fits, nothing left over'),
]

EXACT_NOTE = 'Built from exact multiples of its ingredients (%s), so nothing is left over to ride into the cloud and nothing in the beaker is wasted.'

def _what(spec, comp, kind):
    s = comp['summary']
    if spec['type'] == 'med':
        base = ('Healing %s over up to %d tiles; each tile holds %gu %s.' % (s['kind'], s['tiles'], s['per_tile'], spec['payload']))
        if s['kind'] == 'smoke':
            return base + ' Chem smoke copies a share of every reagent straight into each breathing mob in the cloud (no internals or smoke protection): %gu per 2 s tick, up to the whole tile over the 20 s life. A person who leaves early takes less.' % s['per_tick']
        return base + ' Foam reaches the blood by vapour (about %gu per 0.2 s tick), but it is slippery and knocks people down.' % s['per_tick']
    return base_text(spec, comp)

def base_text(spec, comp):
    s = comp['summary']
    return '%s over up to %d tiles; each tile holds %gu of %s (%gu per tick).' % (s['kind'].capitalize(), s['tiles'], s['per_tile'], spec['payload'], s.get('per_tick', 0))

def build_all(db, log=print):
    book_by_id = {r['id']: r for r in book.load_book()}
    out = []
    for f in REBUILD:
        base = dict(book_by_id.get(f['base']) or book_by_id.get(f['id']) or {})
        prods = f['products']
        if prods[0][1] == 'max':                      # the largest exact amount that builds
            import stoich
            name = prods[0][0]; q = stoich.quantum(db, set(db.dispensers[1]), db.find_reagent(name)); got = None
            cap = f['beaker'] - (2 * f['draw'] if f['kind'] == 'foam' else 3 * f['draw'])
            for amt in range(cap // q * q, 0, -q):
                r = payload.build(db, f['beaker'], f['syringe'], f['kind'], f['draw'], [(name, amt)], f['payload'], base=base)
                if not r[2]: got = (amt, r); break
            if not got: log('  FAILED %s' % f['id']); continue
            prods = [(name, got[0])]
        spec, comp, bad = payload.build(db, f['beaker'], f['syringe'], f['kind'], f['draw'], prods, f['payload'], base=base)
        if bad: log('  FAILED %s: %s' % (f['id'], bad)); continue
        spec.update(id=f['id'], title=f['title'], tagline=f['tagline'], type=base.get('type', 'med'))
        spec['what'] = _what(spec, comp, f['kind'])
        spec['notes'] = EXACT_NOTE % ', '.join('%du %s' % (a, n) for n, a in prods)
        spec.setdefault('src', ''); spec.setdefault('caution', '')
        out.append((spec, comp)); log('  ok   %-26s %s' % (spec['id'], comp['summary']))
    return out

def apply(db, built):
    recipes = [r for r in book.load_book() if r['id'] not in REMOVE and r['id'] not in {s['id'] for s, _ in built}]
    recipes += [s for s, _ in built]
    book.save_book(recipes); book.write_page(recipes=recipes, db=db)
