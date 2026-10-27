"""
hellfoam.py - the hellfoam designer.

A hellfoam is a combat foam whose point is a short burst: the foam slips people over, and in the same 8-15 seconds fire, acid and a sedative land on them.
This module plans one for a given beaker + syringe, from the numbers the engine already has, so nothing is worked out by hand:

  - the TRIGGER sets the area (draw N from the syringe = 2N tiles).  A foam of up to 25 tiles puts 3.2x the beaker contents in every tile; a bigger foam dilutes it.
  - the PAYLOAD is built from BLOCKS (stoich.py gives exact amounts, so nothing is left over to waste space):
        slip   lube just over its 1u-per-exposure threshold + the least drying agent (placed after it in the tile) that ends the slick floor within the policy limit
        fire   phlogiston (the igniter; it needs 15u of stabilizing agent in the beaker) + napalm to reach 20 fire stacks sooner
        acid   fluorosulfuric acid (chem heater) or plain sulfuric acid (no heater)
        sleep  chloral hydrate
        tox    cyanide (chem heater)
  - every block amount is a whole multiple of the block's smallest exact amount; a search picks the amounts that score best for the roles of the design
  - the winner is built into ops, run through the full engine (book.simulate) and refused if it warns, wastes a chemical, depends on click order, or leaves the floor slick too long.

Used through  chemcli.py hellfoam  (list / publish).
"""
import itertools
import chemlib, stoich, tileapply as ta, exposure as ex, chemstats as cs, planner, book

FOAM_SCALE = chemlib.FOAM_SCALE if hasattr(chemlib, 'FOAM_SCALE') else 3.2
SLICK_MIN = 9.0            # seconds: the lube must actually leave the floor slick for about the foam's life; less means the drying agent cancelled it
SLICK_GOAL = 14.0          # seconds: design target, a little under the 15 s policy so rounding in the game cannot push it over
LUBE_MARGIN = 1.15         # per-exposure lube must clear the 1u threshold by this factor

# reagent each block makes
BLOCK_REAGENT = {'lube': 'lube', 'dry': 'drying agent', 'stab': 'stabilizing agent', 'phlo': 'phlogiston', 'napalm': 'napalm',
                 'facid': 'fluorosulfuric acid', 'sulf': 'sulfuric acid', 'chloral': 'chloral hydrate', 'cyan': 'cyanide'}
HOT = ('facid', 'cyan')                       # blocks that need the chem heater
BUILD_ORDER = ['chloral', 'facid', 'cyan', 'stab', 'phlo', 'napalm', 'sulf', 'lube', 'dry']     # chloral first (it needs 5u of ingredients per 1u made, so it peaks the beaker); heat step after the hot blocks; lube then drying LAST so drying acts after lube in each exposure
BATCH_BLOCKS = ('chloral',)       # blocks that can be built in several smaller batches to keep the beaker from overflowing

# archetype id -> (label, roles, payload blocks, slip package?)
ARCHETYPES = [
    dict(id='fire-sleep',  label='slip + fire + sleep',          roles=['fire', 'sleep'],                  blocks=['phlo', 'napalm', 'chloral']),
    dict(id='acid-sleep',  label='slip + acid + sleep',          roles=['acid', 'sleep'],                  blocks=['facid', 'chloral']),
    dict(id='acid-fire',   label='slip + acid + fire',           roles=['acid', 'fire'],                   blocks=['facid', 'phlo', 'napalm']),
    dict(id='all',         label='slip + acid + fire + sleep',   roles=['acid', 'fire', 'sleep'],          blocks=['facid', 'phlo', 'napalm', 'chloral']),
    dict(id='fire',        label='slip + fire',                  roles=['fire'],                           blocks=['phlo', 'napalm']),
    dict(id='lite',        label='no heater: slip + sulfuric acid + fire + sleep', roles=['acid', 'fire', 'sleep'], blocks=['sulf', 'phlo', 'napalm', 'chloral']),
    dict(id='toxic',       label='slip + cyanide + acid + sleep', roles=['tox', 'acid', 'sleep'],          blocks=['cyan', 'facid', 'chloral']),
]
ARCH = {a['id']: a for a in ARCHETYPES}

# what "enough" of each role is (primary, scored to 1.0) and what counts as headroom (secondary)
REF = dict(acid=(60.0, 240.0), sleep=(30.0, 90.0), tox=(15.0, 45.0), fire_t=(6.0, 1.0), phlo_abs=(40.0, 120.0))

_q = {}
def _db(db=None):
    return db or chemlib.DB()

def avail_of(db): return set(db.dispensers[1])

def quantum(db, block):
    key = (id(db), block)
    if key not in _q:
        p = db.find_reagent(BLOCK_REAGENT[block])
        _q[key] = stoich.quantum(db, avail_of(db), p)
    return _q[key]

def amounts(db, block, cap):
    q = quantum(db, block)
    return list(range(q, cap + 1, q)) if q else []

# ---------------------------------------------------------------- the trigger
def trigger_ops(draw):
    """dispenser ops that make the foam trigger and draw `draw` units of it into the syringe; the rest of the beaker is spilled"""
    p = 25 * int(-(-draw // 25))
    k = p // 5
    return [('dispense', 'fluorine', 2 * k), ('dispense', 'carbon', 2 * k), ('dispense', 'sulfuric acid', k), ('draw', draw), ('spill',)]

def draws_for(syringe):
    return [d for d in (planner.SYRINGE_TYPES['standard'][1] if syringe == 15 else planner.SYRINGE_TYPES['bluespace'][1])]

# ---------------------------------------------------------------- a quick evaluator (the same exposure model the page uses, without the blood simulation)
def lean(tiles, tile):
    """what one person takes standing in the foam for its whole life.  tile = {reagent path: units in a tile}.  -> dict for 'bare' and 'suit'"""
    pl = ta.plan('foam', tiles); frac = pl['fraction']; dt = pl['dt']; n = pl['exposures']
    out = {}
    for sid in ('bare', 'suit'):
        sc = next(s for s in ex.SCENARIOS if s['id'] == sid); num = ex.scenario_numbers(sc)
        absorbed = {}; fire_add = 0.0; ignite = False; burn_flat = 0.0; acid = [0.0, 0.0]; flat = []
        for p, u in tile.items():
            vol = u * frac
            if vol <= 1e-9: continue
            pen = cs.stats().get(p, {}).get('vars', {}).get('penetrates_skin', 4.0)
            pen = int(pen) if isinstance(pen, (int, float)) else 4
            if pen & ex.VAPOR:
                amt = ex.bround(vol * max(0.0, 1 - num['block']), 0.1)
                if amt >= 0.5: absorbed[p] = amt * n
            e = ex.contact(p, ex.VAPOR, vol, sc)
            flat.append(e)
        zones = {'head': 'head', 'chest': 'chest', 'l_arm': 'arms', 'r_arm': 'arms', 'l_leg': 'legs', 'r_leg': 'legs'}
        k_ = len({zones[q] for q in num['acid_open']})
        stacks = 0.0; t20 = None
        for i in range(n):
            for e in flat:
                if 'fire_stacks' in e: stacks = min(stacks + e['fire_stacks'], 20.0)
                if 'burn_per_stack' in e: burn_flat += e['burn_per_stack'] * max(stacks, 1.0)
                if e.get('ignite'): ignite = True
                if 'burn_flat' in e: burn_flat += e['burn_flat']
                if 'acid_part' in e: acid[0] += e['acid_part'][0] * k_; acid[1] += e['acid_part'][1] * k_
            if ignite and stacks >= 20.0 and t20 is None: t20 = (i + 1) * dt
        out[sid] = dict(absorbed=absorbed, ignite=ignite, t20=t20, stacks=stacks, burn_flat=burn_flat, acid=acid[0] + acid[1])
    return out

def role_scores(tiles, tile, roles):
    """-> (primary mean, headroom mean, detail) over the roles of a design.  1.0 primary = the role does what it is meant to."""
    L = lean(tiles, tile); su, ba = L['suit'], L['bare']
    P = lambda n: '/datum/reagent/' + n
    pr = {}; hr = {}
    cl = lambda x: max(0.0, min(1.0, x))
    for r in roles:
        if r == 'fire':
            if not ba['ignite']: pr[r] = 0.0; hr[r] = 0.0
            else:
                t = ba['t20'] if ba['t20'] is not None else 99.0
                pr[r] = 0.6 + 0.4 * cl((REF['fire_t'][0] - t) / (REF['fire_t'][0] - 1.0))
                hr[r] = 0.5 * cl((REF['fire_t'][0] - t) / (REF['fire_t'][0] - 0.5)) + 0.5 * cl(ba['absorbed'].get(P('phlogiston'), 0) / REF['phlo_abs'][1])
        elif r == 'acid':
            pr[r] = cl(su['acid'] / REF['acid'][0]); hr[r] = cl(su['acid'] / REF['acid'][1])
        elif r == 'sleep':
            a = su['absorbed'].get(P('toxin/chloralhydrate'), 0.0)
            pr[r] = cl(a / REF['sleep'][0]); hr[r] = cl(a / REF['sleep'][1])
        elif r == 'tox':
            a = su['absorbed'].get(P('toxin/cyanide'), 0.0)
            pr[r] = cl(a / REF['tox'][0]); hr[r] = cl(a / REF['tox'][1])
    n = max(1, len(roles))
    return sum(pr.values()) / n, sum(hr.values()) / n, dict(primary=pr, headroom=hr, lean=L)

# ---------------------------------------------------------------- the slip package
def slip_package(db, tiles):
    """-> (lube units, drying agent units) in the beaker: the least lube + drying agent that leave the floor slick for SLICK_MIN..SLICK_GOAL seconds.
    Too little drying agent and the floor stays slick for minutes; too much and it cancels the lube in the same tick it lands (the lube then does nothing).
    The drying agent comes in 15u steps, so for some foam sizes no amount lands in the window: None (use the foam's own slipperiness there)."""
    frac = ta.foam_fraction(tiles)
    L = '/datum/reagent/lube'; D = '/datum/reagent/drying_agent'
    ql, qd = quantum(db, 'lube'), quantum(db, 'dry')
    need = ql * max(1, int(-(-((LUBE_MARGIN / frac) / FOAM_SCALE) // ql)))
    best = None
    for lube in range(need, need + 4 * ql, ql):
        for dry in range(qd, 12 * qd, qd):
            s = ta.slick_sim('foam', tiles, {L: lube * FOAM_SCALE, D: dry * FOAM_SCALE})['total_s']
            if SLICK_MIN <= s <= SLICK_GOAL and (best is None or lube + dry < sum(best)): best = (lube, dry)
    return best

# ---------------------------------------------------------------- search
def stab_needed(blocks): return 'phlo' in blocks

def candidates(db, arch, cap, tiles):
    """every combination of block amounts that fits in `cap` units: dict block -> beaker units"""
    names = list(arch['blocks'])
    opts = []
    for b in names:
        a = amounts(db, b, cap)
        if b == 'phlo': a = [x for x in a if x <= 30]
        if b == 'napalm': a = [0] + a
        opts.append(a)
    def rec(i, left, cur):
        if i == len(names):
            yield dict(cur); return
        for a in opts[i]:
            if a > left: break
            cur[names[i]] = a
            yield from rec(i + 1, left - a, cur)
        cur.pop(names[i], None)
    yield from rec(0, cap, {})

def tile_of(db, blocks):
    """tile contents (reagent path -> units) the foam will hold for these beaker amounts (x3.2), in the order the blocks are built"""
    t = {}
    for b in BUILD_ORDER:
        a = blocks.get(b, 0)
        if a: t[db.find_reagent(BLOCK_REAGENT[b])] = a * FOAM_SCALE
    return t

def design(db, beaker, syringe, arch_id, draw, slip=True, top=12):
    """best designs (a list, best first) of one archetype at one trigger size.  -> list of dict(blocks, score, ...)"""
    arch = ARCH[arch_id]; tiles = 2 * draw
    cap = beaker - 2 * draw                         # at the moment of the inject the beaker holds the payload + `draw` of water and gets `draw` of trigger
    pk = None
    if slip:
        pk = slip_package(db, tiles)
        if pk is None: return []
    fixed = {}
    if slip: fixed.update(lube=pk[0], dry=pk[1])
    if stab_needed(arch['blocks']): fixed['stab'] = quantum(db, 'stab')
    cap_free = cap - sum(fixed.values())
    if cap_free <= 0: return []
    roles = list(arch['roles'])
    res = []
    for combo in candidates(db, arch, cap_free, tiles):
        if any(r == 'fire' and combo.get('phlo', 0) == 0 for r in roles): continue
        if any(r == 'acid' and not (combo.get('facid', 0) or combo.get('sulf', 0)) for r in roles): continue
        if 'sleep' in roles and not combo.get('chloral', 0): continue
        if 'tox' in roles and not combo.get('cyan', 0): continue
        blocks = dict(fixed); blocks.update({k: v for k, v in combo.items() if v})
        p, h, det = role_scores(tiles, tile_of(db, blocks), roles)
        if min(det['primary'].values()) < 0.5: continue
        used = sum(blocks.values())
        res.append(dict(blocks=blocks, primary=p, headroom=h, detail=det, used=used, tiles=tiles, draw=draw, arch=arch_id, slip=slip, cap=cap))
    res.sort(key=lambda r: (-(r['primary'] + 0.25 * r['headroom']), r['used']))
    return res[:top]

# ---------------------------------------------------------------- ops
def blocks_ops(db, blocks, batch=None):
    """payload ops in the order the blocks must be built (chloral, hot blocks, heat, stabilizer, phlogiston, napalm, sulfuric acid, lube, drying agent).
    batch = {block: units per batch} builds that block in several rounds (needed when its ingredients, 5u per 1u made for chloral, would overflow the beaker)"""
    av = avail_of(db); ops = []
    hot = [b for b in HOT if blocks.get(b)]
    for b in BUILD_ORDER:
        a = blocks.get(b, 0)
        if not a: continue
        bs = (batch or {}).get(b) or a
        left = a
        while left > 0:
            part = min(bs, left)
            o = stoich.ops(db, av, db.find_reagent(BLOCK_REAGENT[b]), part)
            if o is None: raise ValueError('%s %du is not an exact amount' % (b, part))
            ops += o; left -= part
        if b in hot: ops.append(('heat', 400))           # heat after EACH hot block: two sets of hot ingredients in the beaker together would react with each other
    return ops

def batch_options(db, blocks):
    """batch plans to try, fewest steps first: everything at once, then chloral in rounds of decreasing size"""
    out = [None]
    a = blocks.get('chloral', 0)
    if a:
        q = quantum(db, 'chloral')
        for bs in sorted({x for x in range(q, a, q)}, reverse=True):
            out.append({'chloral': bs})
    return out

def full_ops(db, blocks, draw, batch=None):
    return trigger_ops(draw) + blocks_ops(db, blocks, batch) + [('dispense', 'water', draw), ('inject',)]

# ---------------------------------------------------------------- verified build
def spec_for(db, d, beaker, syringe, rank=40):
    """turn a design into a recipe spec and prove it with the full engine; tries the batch plans in turn.  -> (spec, comp, problems) of the first plan with no problems,
    or of the last one tried with its problems listed"""
    blocks = d['blocks']; draw = d['draw']
    payload = next((BLOCK_REAGENT[b] for b in ('facid', 'sulf', 'phlo', 'chloral', 'cyan', 'napalm') if blocks.get(b)), 'lube')
    last = None
    for batch in batch_options(db, blocks):
        ops = full_ops(db, blocks, draw, batch)
        spec = dict(type='hell', beaker=beaker, syringe=syringe, ops=[list(o) for o in ops], payload=payload, harm='danger', rank=rank,
                    title='', tagline='', what='', notes='', caution='', src='')
        try:
            comp = book.simulate(db, spec)
        except ValueError as e:
            last = (spec, None, [str(e)]); continue
        bad = check(comp, d['slip'])
        last = (spec, comp, bad)
        if not bad: return last
    return last

def check(comp, slip):
    """reasons a built design is not acceptable (empty list = fine)"""
    bad = []
    if comp['warnings']: bad.append('warnings: %s' % comp['warnings'][:2])
    o = comp['order']
    if not (o.get('clicks_ok', True) and o.get('reverse_ok', True) and o.get('temp_ok', True)): bad.append('order or temperature sensitive')
    st = comp.get('stats') or {}
    if st.get('broken'): bad.append('wasted: %s' % [(i['n'], i['u']) for i in st['exp']['inert']])
    sl = (st.get('exp') or {}).get('slick')
    if slip and not sl: bad.append('no slick floor')
    if slip and sl and sl['total'] is not None and sl['total'] < SLICK_MIN: bad.append('lube cancelled by the drying agent (%s s)' % sl['total'])
    if sl and sl['over']: bad.append('slick %s s' % sl['total'])
    fs = (st.get('exp') or {}).get('floor_safety')
    if fs and not fs['safe']: bad.append('floor destroyed: %s' % fs['reasons'])
    return bad

# ---------------------------------------------------------------- text for the card (every number comes from the engine result)
def _sc(comp, sid):
    return next(s for s in comp['stats']['exp']['scenarios'] if s['id'] == sid)

def _chem(comp, name):
    return next((c for c in comp['stats']['exp']['chems'] if c['n'] == name), None)

def describe(db, d, spec, comp):
    """fill title / tagline / what / notes / caution / src of the spec"""
    arch = ARCH[d['arch']]; b = d['blocks']; tiles = d['tiles']; x = comp['stats']['exp']; slip = d['slip']
    bare, suit = _sc(comp, 'bare'), _sc(comp, 'suit')
    L = d['detail']['lean']['bare']
    near = 'tight' if tiles <= 20 else ('mid-size' if tiles <= 30 else 'wide')
    spec['title'] = 'Hellfoam: %s%s (%d tiles)' % (arch['label'], '' if slip else ', no lube', tiles)
    bits = []
    lines = ['Combat foam over up to %d tiles (%du of trigger, %s foam). Floor-safe: nothing in it melts or burns away the floor tile.' % (tiles, d['draw'], near)]
    if slip:
        lube = _chem(comp, 'Space Lube'); sl = x['slick']
        lines.append('Slip: the foam itself is slippery for its 8 s life, and %du of space lube puts %gu of lube into every 0.2 s tick (the floor needs 1u). %du of drying agent, which sits after the lube in the tile, strips the wet time again each tick, so the floor stops being slippery about %g s after the foam starts.' % (b['lube'], lube['per'], b['dry'], sl['total']))
        bits.append('slip')
    else:
        lines.append('Slip: no lube. The foam itself is slippery for its 8 s life and nothing is left on the floor afterwards.')
    if b.get('phlo'):
        ph = _chem(comp, 'Phlogiston')
        t = ('20 fire stacks at %g s' % L['t20']) if L['t20'] else 'fire stacks build up'
        lines.append('Fire: phlogiston sets the target alight on the first 0.2 s tick and adds a stack on every tick%s. A bare person has %s (%gu of phlogiston in the blood over the foam life).' % (
            (', napalm (%du, %gu per tick) adds a quarter of its dose as stacks each tick' % (b['napalm'], _chem(comp, 'Napalm')['per'])) if b.get('napalm') else '', t, bare['per'].get('Phlogiston', 0)))
    if b.get('facid') or b.get('sulf'):
        nm = 'Fluorosulfuric Acid' if b.get('facid') else 'Sulfuric Acid'
        ac = _chem(comp, nm)
        lines.append('Acid: %du of %s, %gu per tile, %gu per tick. A person in a plain jumpsuit takes about %g brute and %g burn from it over the foam life (bare skin %g / %g). It leaves an acid layer that eats items lying on the floor, but acid power %s is far under the 200 that melts a tile.' % (
            b.get('facid') or b.get('sulf'), nm.lower(), ac['tile'], ac['per'], suit['fx'].get('acid_brute', 0), suit['fx'].get('acid_burn', 0), bare['fx'].get('acid_brute', 0), bare['fx'].get('acid_burn', 0), '42' if b.get('facid') else '10'))
    if b.get('chloral'):
        lines.append('Sleep: %du of chloral hydrate; a person in a jumpsuit absorbs %gu of it over the foam life (about 30u is enough for roughly 100 s of sleep after about 20 s of confusion and drowsiness).' % (b['chloral'], suit['per'].get('Chloral Hydrate', 0)))
    if b.get('cyan'):
        lines.append('Poison: %du of cyanide; a person in a jumpsuit absorbs %gu of it (suffocation and stun while it lasts).' % (b['cyan'], suit['per'].get('Cyanide', 0)))
    spec['what'] = ' '.join(lines)
    notes = []
    if b.get('phlo'): notes.append('The %du of stabilizing agent is only there so the phlogiston can form (without it phlogiston makes a 1000 K fireball on the borg and wipes the beaker); it does nothing in the foam.' % b['stab'])
    if slip: notes.append('The lube is held at the least that works (just over 1u per tick) and the drying agent is placed after it, so the slippery floor ends with the foam instead of lasting minutes. If the game orders the tile differently the floor could stay slick longer: the check is in the page\'s slick-floor panel.')
    if any(o[0] == 'heat' for o in spec['ops']): notes.append('Needs a chem heater (400 K). The beaker stays hot for the later steps.')
    if b.get('chloral') and sum(1 for o in spec['ops'] if o[0] == 'dispense' and o[1] == 'chloral') > 1: pass
    notes.append('Every chemical here is made from exact multiples of its ingredients, so nothing is left over in the foam. Fill: %d%% of the beaker.' % comp['summary']['fill'])
    spec['notes'] = ' '.join(notes)
    spec['caution'] = 'Lethal-force chemistry: it burns, poisons and puts people to sleep. Law 1 and Law 2 apply: use it only on a clear threat (an antagonist already attacking the crew), never on someone you merely suspect. Fire and acid foam also reach YOU if you stand in it: trigger it at range and stay out.'
    spec['src'] = 'effects_foam.dm, reagents/pyrotechnic_reagents.dm (phlogiston, napalm), toxin_reagents.dm (fluacid, chloral hydrate, cyanide), lube / wet_floor component, recipes (foam, phlogiston)'
    spec['tagline'] = {'fire-sleep': 'Burn them and put them down; no acid anywhere', 'acid-sleep': 'Acid to wear them down, chloral to put them down; no fire',
                       'acid-fire': 'Acid and fire together; no sedative', 'all': 'Acid, fire, sleep and slip in one foam',
                       'fire': 'Fire only: the lightest recipe', 'lite': 'No chem heater: plain sulfuric acid instead of fluorosulfuric',
                       'toxic': 'Cyanide, acid and sleep: the poisoning mix'}[d['arch']] + ('' if slip else '; the foam itself does the slipping')
    spec['id'] = 'hf-%d-%d-%s-%s-%d' % (spec['beaker'], spec['syringe'], d['arch'], 'lube' if slip else 'nolube', tiles)
    return spec

# ---------------------------------------------------------------- what to publish for a beaker + syringe
MIN_PRIMARY = 0.75                                   # a design must do its roles at least this well to be offered
LIMITS = {(100, 15): 14, (100, 60): 8, (300, 60): 14, (300, 15): 24}      # most recipes per beaker + syringe
MULTI_DRAW = ('all', 'fire-sleep', 'acid-sleep')      # archetypes offered at every trigger size where the beaker + syringe has room (the 'range' experiments)
OLD_IDS = ['hellfoam-fire-100-15', 'hellfoam-acid-100-15', 'hellfoam-acid-100-60', 'hellfoam-300-15', 'hellfoam-300-60', 'hellfoam-fire-300-15', 'hellfoam-acid-300-15', 'hellfoam-acid-300-60']

def combo_draws(syringe):
    """trigger sizes native to this syringe: the 15u syringe offers 5/10/15; the 60u syringe's other sizes are 20 and up (10 works on both and is listed with the 15u syringe)"""
    return [5, 10, 15] if syringe == 15 else [20, 30, 40, 50, 60]

def generate(db, beaker, syringe, log=print, tries=6):
    groups = {}
    for draw in combo_draws(syringe):
        for a in ARCHETYPES:
            for slip in (True, False):
                ds = design(db, beaker, syringe, a['id'], draw, slip)
                if ds and ds[0]['primary'] >= MIN_PRIMARY:
                    groups.setdefault((a['id'], slip), []).append((ds[0]['primary'] + 0.25 * ds[0]['headroom'], draw, ds))
    picks = []
    for (aid, slip), lst in groups.items():
        lst.sort(key=lambda t: -t[0])
        take = lst if aid in MULTI_DRAW else lst[:1]
        picks += [(t[0], aid, slip, t[1], t[2]) for t in take]
    picks.sort(key=lambda t: -t[0])
    out = []
    for total, aid, slip, draw, ds in picks:
        if len(out) >= LIMITS[(beaker, syringe)]: break
        for d in ds[:tries]:
            spec, comp, bad = spec_for(db, d, beaker, syringe)
            if bad:
                log('  skip %s %s draw %d %s: %s' % (aid, 'lube' if slip else 'nolube', draw, d['blocks'], '; '.join(bad)[:160])); continue
            describe(db, d, spec, comp)
            out.append((total, spec, comp, d)); log('  ok   %-44s score %.2f  %s' % (spec['id'], total, d['blocks'])); break
        else:
            log('  none passed: %s %s draw %d' % (aid, slip, draw))
    for i, (total, spec, comp, d) in enumerate(out): spec['rank'] = 10 + i
    return out

def publish(db, entries, remove=()):
    """file the built specs into the book (replacing same ids), drop `remove`, rebuild the page once"""
    recipes = [r for r in book.load_book() if r['id'] not in set(remove) and r['id'] not in {e[1]['id'] for e in entries}]
    for _, spec, comp, d in entries: recipes.append(spec)
    book.save_book(recipes); book.write_page(recipes=recipes, db=db)
    return len(entries)
