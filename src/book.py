"""book.py - the recipe book.

    data/recipe_book.json   the recipes (source of truth: gear tier, type, step list, text)
    docs/index.html         the web page, generated from it (src/page_template.html + the book + engine results)

Every recipe is re-simulated here, so the page only ever shows numbers the engine produced.  Use it through chemcli:

    python3 src/chemcli.py publish --type hell --beaker 300 --syringe 60 --title "..." --ops "dispense ...; ..." --what "..."
    python3 src/chemcli.py book rebuild | list | rm <id>

`publish` simulates the recipe, refuses it if the engine cannot model an effect or the beaker overflows, files it in the right tier
section and type group, and rewrites the page, so a new recipe is one command and nothing has to be hand-edited.
"""
import os, sys, json, hashlib, re
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import chemlib, planner, search

BOOK_PATH = os.path.join(ROOT, 'data', 'recipe_book.json')
PAGE_PATH = os.path.join(ROOT, 'docs', 'index.html')
TEMPLATE = os.path.join(HERE, 'page_template.html')
CACHE_PATH = os.path.join(ROOT, '.cache', 'book_cache.json')

# display order of the type groups inside each tier section
TYPES = [('cleaning', 'Cleaning (space cleaner)'), ('slip', 'Slipping (space lube)'), ('hell', 'Combat (hellfoam)'),
         ('med', 'Medical (healing foam / smoke)'), ('walls', 'Walls (metal foam)'), ('other', 'Other effects')]
TYPE_KEYS = [k for k, _ in TYPES]
# plain chemicals (group 'chem'): made in one ordinary container from the basic dispenser, no syringe, no borg gear
CHEM_TYPES = [('heal', 'Healing (brute, burn, toxin, oxygen)'), ('crit', 'Emergency and stabilising'), ('cure', 'Cures and purges (organs, genes, toxins, drugs)'),
              ('boost', 'Stimulants, painkillers and sedatives'), ('util', 'Utility (cleaners, foams, fire, chemistry helpers)'), ('tox', 'Poisons'), ('other', 'Other')]
CHEM_TYPE_KEYS = [k for k, _ in CHEM_TYPES]
CHEM_BEAKER_OF = {50: 'beaker', 100: 'large', 300: 'bluespace'}
GROUPS = ('borg', 'chem')
HARM = ('safe', 'caution', 'danger')
# beaker size -> planner gear name; syringe size -> planner gear name.  (0 = any gear)
BEAKER_OF = {100: 'large', 300: 'bluespace', 0: 'large'}
SYRINGE_OF = {15: 'standard', 60: 'bluespace'}
TIER_BEAKERS = (100, 300)
TIER_SYRINGES = (15, 60)

def group_of(e): return e.get('group', 'borg')

def sort_key(e):
    if group_of(e) == 'chem':
        return (1, e['beaker'], CHEM_TYPE_KEYS.index(e['type']), e.get('rank', 50), e['title'].lower())
    return (0, e['beaker'] == 0, e['beaker'], TYPE_KEYS.index(e['type']), e.get('rank', 50), e['title'].lower())

def slug(s):
    return re.sub(r'[^a-z0-9]+', '-', s.lower()).strip('-')

def op_tuple(o):
    return tuple(o)

def uses_syringe(ops):
    return any(o[0] in ('draw', 'inject') for o in ops)

def syringes_of(e, db=None, rig_sig=None):
    """syringe sizes this recipe is listed under: every size it works with. A recipe that never touches the syringe works with all of
    them; otherwise each syringe is tried (a 15u draw is not an allowed setting on the 60u syringe, a 10u draw is on both)."""
    if group_of(e) == 'chem' or not e['beaker']: return []
    if not uses_syringe(e['ops']): return list(TIER_SYRINGES)
    if db is None: return [e['syringe']]
    import chemcli
    ops = [op_tuple(o) for o in e['ops']]; out = []
    for sy in TIER_SYRINGES:
        try:
            g = planner.Gear(BEAKER_OF[e['beaker']], SYRINGE_OF[sy])
            r = chemcli._run(db, ops, 1, False, g)
            if rig_sig is None or chemcli.signature(r) == rig_sig: out.append(sy)
        except Exception:
            pass
    return out or [e['syringe']]

def gear_of(e):
    if group_of(e) == 'chem': return planner.Gear(CHEM_BEAKER_OF[e['beaker']])
    return planner.Gear(BEAKER_OF[e['beaker']], SYRINGE_OF.get(e.get('syringe') or 15, e.get('syringe') or 15))

def load_book(path=BOOK_PATH):
    with open(path) as fh: return json.load(fh)['recipes']

def save_book(recipes, path=BOOK_PATH):
    recipes = sorted(recipes, key=sort_key)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w') as fh:
        fh.write('{\n "recipes": [\n' + ',\n'.join('  ' + json.dumps(r, ensure_ascii=False, sort_keys=False) for r in recipes) + '\n ]\n}\n')

def validate_spec(e):
    for k in ('id', 'type', 'title', 'beaker', 'ops', 'what', 'harm'):
        if k not in e: raise ValueError('recipe is missing %r' % k)
    if group_of(e) not in GROUPS: raise ValueError('group must be one of %s' % (GROUPS,))
    if e['harm'] not in HARM: raise ValueError('harm must be one of %s' % (HARM,))
    if group_of(e) == 'chem':
        if e['type'] not in CHEM_TYPE_KEYS: raise ValueError('chem type must be one of %s' % CHEM_TYPE_KEYS)
        if e['beaker'] not in CHEM_BEAKER_OF: raise ValueError('chem beaker must be one of %s' % sorted(CHEM_BEAKER_OF))
        if not e.get('payload'): raise ValueError('a chem recipe needs payload = the chemical it makes')
        return
    if e['type'] not in TYPE_KEYS: raise ValueError('type must be one of %s' % TYPE_KEYS)
    if e['beaker'] not in BEAKER_OF: raise ValueError('beaker must be one of %s (0 = works with any gear)' % sorted(BEAKER_OF))
    if uses_syringe(e['ops']) and e.get('syringe') not in SYRINGE_OF:
        raise ValueError('this recipe uses the syringe: set syringe to one of %s' % sorted(SYRINGE_OF))

# ----------------------------------------------------------------------------------------------- engine results per recipe
def _engine_hash():
    h = hashlib.sha1()
    for f in ('chemlib.py', 'planner.py', 'search.py', 'chemcli.py', 'book.py', 'chemdata.json'):
        with open(os.path.join(HERE, f), 'rb') as fh: h.update(fh.read())
    return h.hexdigest()

def needs_of(e, gear):
    n = []
    if group_of(e) == 'chem':
        n.append('chem dispenser (basic reagent list)')
        n.append('%du %s' % (e['beaker'], 'beaker' if e['beaker'] == 50 else 'large beaker' if e['beaker'] == 100 else 'bluespace beaker'))
        if any(o[0] == 'heat' for o in e['ops']): n.append('chem heater')
        return n
    if e['beaker']: n.append('%du beaker (%s)' % (e['beaker'], 'borg default' if e['beaker'] == 100 else gear.bname))
    if uses_syringe(e['ops']) and e['syringe'] != 15: n.append('%du syringe (bluespace syringe upgrade)' % e['syringe'])
    if any(o[0] == 'heat' for o in e['ops']): n.append('chem heater')
    for o in e['ops']:
        if o[0] == 'add': n.append('outside supply: %gu %s' % (o[2], o[1]))
    return n

def result_lines(db, rig, payload):
    R = db.find_reagent
    lines = []
    foams = [x for x in rig.sim.effects if x['kind'] == 'foam']
    for x in foams:
        held = ', '.join('%gu %s' % (round(v, 1), db.name(p)) for p, v in x['tile'].items()) or 'nothing (the foam only leaves its structure)'
        l = 'Foam over up to %d tiles, each tile holds %s.' % (x['tiles'], held)
        if payload and len(foams) == 1:
            m = search.foam_metrics(rig, R(payload))
            if m: l += ' Every %.1fs tick exposes the floor to %.1fu of %s per tile (%d ticks over its 8s life).' % (search.FOAM_DT, m['per_call'], db.name(R(payload)), m['calls'])
        lines.append(l)
    for x in rig.sim.effects:
        if x['kind'] == 'smoke':
            l = 'Smoke over up to %d tiles, each tile holds %s.' % (x['tiles'], ', '.join('%gu %s' % (round(v, 1), db.name(p)) for p, v in x['tile'].items()))
            if payload:
                m = search.smoke_metrics(rig, R(payload))
                if m: l += ' Every %.1fs tick a mob in the tile breathes in %.1fu of %s (%d ticks over the 20s life).' % (search.SMOKE_DT, m['per_call'], db.name(R(payload)), m['calls'])
            lines.append(l)
        elif x['kind'] == 'vortex':
            lines.append('Vortex (%s) with range %.1f tiles%s.' % (x['mode'], x['range'], ' (the formula gave %.1f, capped at %g)' % (x['raw_range'], x['cap']) if x['raw_range'] > x['cap'] else ''))
        elif x['kind'] == 'mobspawn':
            lines.append('Spawns rand(1,%d) %smobs.' % (x['max'], 'friendly ' if x['friendly'] else ''))
        elif x['kind'] == 'UNMODELED':
            lines.append('UNMODELED effect: %s' % x)
    return lines

def simulate(db, e):
    """run one recipe through the engine -> dict of everything the page shows besides the hand-written text"""
    import chemcli
    gear = gear_of(e); ops = [op_tuple(o) for o in e['ops']]
    rig = chemcli._run(db, ops, 1, False, gear)
    if group_of(e) == 'chem': return simulate_chem(db, e, gear, ops, rig)
    haz = [x for x in rig.sim.effects if x['kind'] == 'HAZARD']
    if haz: raise ValueError('hazard for the borg: %s' % '; '.join(x['what'] for x in haz))
    bad = [x for x in rig.sim.effects if x['kind'] == 'UNMODELED']
    if not rig.sim.effects: raise ValueError('the engine saw no effect (no foam, smoke or other reaction fired)')
    if bad: raise ValueError('the engine cannot model: %s' % bad)
    v = chemcli.verify_orders(db, ops, 1, gear)
    cap = gear.beaker
    summ = {}
    for x in rig.sim.effects:
        if x['kind'] in ('foam', 'smoke'):
            summ = {'kind': x['kind'], 'tiles': x['tiles']}
            if e.get('payload'):
                m = (search.foam_metrics if x['kind'] == 'foam' else search.smoke_metrics)(rig, db.find_reagent(e['payload']))
                if m: summ.update(per_tile=round(m['payload_tile'], 1), per_tick=round(m['per_call'], 1))
            break
    if not summ:
        x = rig.sim.effects[0]; summ = {'kind': x['kind']}
        if x['kind'] == 'vortex': summ['range'] = round(x['range'], 1)
        if x['kind'] == 'mobspawn': summ['mobs'] = x['max']
    summ['fill'] = round(100.0 * rig.peak / cap) if e['beaker'] else None
    steps = [{'t': st['text'], 'b': st['beaker'], 's': st['syringe'] if uses_syringe(ops) else None} for st in rig.steps]
    return {'steps': steps, 'results': result_lines(db, rig, e.get('payload')),
            'order': {'same': v['perm_same'], 'total': v['perm_total'], 'bad': v['bad_orders'][:2], 'reverse_ok': v['reverse_index_order_same'], 'clicks_ok': v['clicks_order_same']},
            'summary': summ, 'needs': needs_of(e, gear), 'warnings': rig.sim.warnings, 'syringes': syringes_of(e, db, chemcli.signature(rig))}

def dose_line(db, p):
    """what the reagent code says about dosing: overdose threshold and how long 1u lasts in the blood"""
    r = db.reagents.get(p)
    if r is None: return ''
    bits = []
    bits.append('overdose at %gu' % r.overdose if r.overdose else 'no overdose threshold')
    if r.metab: bits.append('burns off at %gu per second (1u lasts about %gs)' % (r.metab, round(1 / r.metab)))
    return ', '.join(bits) + '.'

def simulate_chem(db, e, gear, ops, rig):
    import chemcli
    bad = [x for x in rig.sim.effects if x['kind'] in ('HAZARD', 'UNMODELED')]
    if bad: raise ValueError('hazard or effect the engine cannot model: %s' % bad)
    if rig.sim.effects: raise ValueError('a plain chemical recipe must not fire a foam, smoke or other effect (%s): file it as a borg recipe' % rig.sim.effects[0]['kind'])
    p = db.find_reagent(e['payload']); amt = rig.beaker.amount(p)
    if amt < 1: raise ValueError('the recipe leaves no %s in the beaker' % e['payload'])
    v = chemcli.verify_orders(db, ops, 1, gear)
    left = [(db.name(k), round(x[0], 1)) for k, x in rig.beaker.r.items() if k != p]
    raw = sum(o[2] for o in ops if o[0] == 'dispense')
    summ = {'kind': 'chem', 'product': db.name(p), 'made': round(amt, 1), 'raw': raw, 'fill': round(100.0 * rig.peak / gear.beaker), 'end_fill': round(100.0 * rig.beaker.total / gear.beaker),
            'left': ['%gu %s' % (a, n) for n, a in left]}
    res = ['Makes %gu %s in the beaker (from %du of ingredients, the beaker peaks at %d%% full).' % (round(amt, 1), db.name(p), raw, summ['fill'])]
    if left: res.append('Left in the beaker with it: %s. Pour them out or leave them: they are not the product.' % ', '.join('%gu %s' % (a, n) for n, a in left))
    d = dose_line(db, p)
    if d: res.append('Dosing (reagent code): %s' % d)
    steps = [{'t': st['text'], 'b': st['beaker'], 's': None} for st in rig.steps]
    return {'steps': steps, 'results': res,
            'order': {'same': v['perm_same'], 'total': v['perm_total'], 'bad': v['bad_orders'][:2], 'reverse_ok': v['reverse_index_order_same'], 'clicks_ok': v['clicks_order_same']},
            'summary': summ, 'needs': needs_of(e, gear), 'warnings': rig.sim.warnings, 'syringes': []}

def computed(db, e, cache=None):
    key = hashlib.sha1((json.dumps([e['ops'], e['beaker'], e.get('syringe'), e.get('payload')]) + _engine_hash()).encode()).hexdigest()
    if cache is not None and key in cache: return cache[key]
    out = simulate(db, e)
    if cache is not None: cache[key] = out
    return out

def _load_cache():
    try:
        with open(CACHE_PATH) as fh: return json.load(fh)
    except Exception: return {}

def _save_cache(c):
    try:
        os.makedirs(os.path.dirname(CACHE_PATH), exist_ok=True)
        with open(CACHE_PATH, 'w') as fh: json.dump(c, fh)
    except Exception: pass

# ----------------------------------------------------------------------------------------------- page
def page_data(recipes, db, cache=None):
    out = []
    for e in sorted(recipes, key=sort_key):
        r = dict(e); r.update(computed(db, e, cache)); out.append(r)
    return {'recipes': out, 'types': TYPES, 'chem_types': CHEM_TYPES, 'rules': db.meta.get('commit', '?')[:10]}

def build_page(recipes=None, db=None, use_cache=True):
    db = db or chemlib.DB(json_path=os.path.join(HERE, 'chemdata.json'))
    recipes = recipes if recipes is not None else load_book()
    cache = _load_cache() if use_cache else None
    data = page_data(recipes, db, cache)
    if cache is not None: _save_cache(cache)
    with open(TEMPLATE) as fh: tpl = fh.read()
    blob = json.dumps(data, ensure_ascii=False, separators=(',', ':')).replace('</', '<\\/')
    import base64
    hero = os.path.join(ROOT, 'data', 'birdbrain_medbay.webp')
    img = 'data:image/webp;base64,' + base64.b64encode(open(hero, 'rb').read()).decode() if os.path.exists(hero) else ''
    return tpl.replace('/*__HERO_IMG__*/', img).replace('/*__BOOK_JSON__*/null', blob)

def write_page(**kw):
    html = build_page(**kw)
    os.makedirs(os.path.dirname(PAGE_PATH), exist_ok=True)
    with open(PAGE_PATH, 'w') as fh: fh.write(html)
    return PAGE_PATH

def add_recipe(spec, db=None, write=True):
    """validate + simulate + file a recipe (replaces one with the same id), rewrite the book and the page. Returns (entry, computed)."""
    db = db or chemlib.DB(json_path=os.path.join(HERE, 'chemdata.json'))
    e = dict(spec)
    e.setdefault('id', slug('%s-%s-%s-%s-%s' % (group_of(e), e.get('type', ''), e.get('beaker', ''), e.get('syringe', 'x'), e.get('title', ''))))
    e.setdefault('tagline', '')
    validate_spec(e)
    comp = simulate(db, e)
    o = comp['order']
    if group_of(e) != 'chem' and (not o.get('clicks_ok', True) or not o.get('reverse_ok', True)):
        raise ValueError('the result depends on the click order inside a dispenser step (%s) or on which of two same-ingredient reactions the game tries first (%s): '
                         'rebalance the amounts (e.g. keep every split click a multiple of the reaction ratio)' % ('click order' if not o.get('clicks_ok', True) else 'ok', 'reaction priority' if not o.get('reverse_ok', True) else 'ok'))
    recipes = [r for r in load_book() if r['id'] != e['id']] if os.path.exists(BOOK_PATH) else []
    replaced = len(recipes) != (len(load_book()) if os.path.exists(BOOK_PATH) else 0)
    recipes.append(e)
    if write:
        save_book(recipes); write_page(recipes=recipes, db=db)
    return e, comp, replaced

def remove_recipe(rid):
    recipes = load_book(); keep = [r for r in recipes if r['id'] != rid]
    if len(keep) == len(recipes): raise KeyError(rid)
    save_book(keep); write_page(recipes=keep)

def section_name(beaker, syringe=None, group='borg'):
    if group == 'chem': return '%du beaker' % beaker
    if not beaker: return 'any gear'
    return '%du beaker + %du syringe' % (beaker, syringe) if syringe else '%du beaker' % beaker
