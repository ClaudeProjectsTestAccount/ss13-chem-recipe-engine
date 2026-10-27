"""
exposure.py - what standing in a foam or chem-smoke cloud does to one person, from the game's foam / smoke / reagent-expose code
(effects_foam.dm, effects_smoke.dm, reagents.dm expose_mob, living_defense.dm touch_protection, human_defense.dm acid_act, life.dm has_smoke_protection).

FOAM  (every 0.2 s per foam tile, for the 8 s life; a person in the tile is "hit" every tick)
      reagents.expose(mob, VAPOR, f)  with  f = 0.2 * 25 / (8 * max(25, area))   -> each reagent: reac_volume = tile_units * f
      blood gain per reagent = round(reac_volume * (1 - bio_protection), 0.1)   only if that is >= 0.5u (and the reagent penetrates VAPOR)
      bio_protection = mean over head/chest/arm/arm/leg/leg of (1 - prod(1 - bio_armour of each garment on that part)); hands, feet, groin count for nothing
      contact effects (fire stacks, acid, ...) run on every exposure whatever the protection.
SMOKE (every 2 s per smoke tile, 20 s life = 9 process ticks + 1 breath when the cloud first reaches you)
      carbon mobs breathe it unless an internals tank is open, TRAIT_NOBREATH, or a mask / glasses / hat has BLOCK_GAS_SMOKE_EFFECT:
      reagents.copy_to(mob, all, 0.1) = 10% of every tile reagent straight into the blood (no armour roll, no 0.5u minimum) + expose(mob, INGEST, 0.1)
      every process tick the tile also exposes everything in it to TOUCH x0.1 (contact effects; nothing enters the blood that way).
Blood: a chemical leaves at metabolization_rate * 2 u per Life tick (2 s), does its on_mob_life effect every tick it is present, and its overdose effect once volume >= threshold.
"""
import os, json, math
import chemstats as cs
import gear as gearlib

HERE = os.path.dirname(os.path.abspath(__file__))
FOAM_DT, FOAM_LIFE, MIN_DIL = 0.2, 8.0, 25.0
SMOKE_DT, SMOKE_LIFE = 2.0, 20.0
TOUCH, INGEST, VAPOR, PATCH, INJECT = 1, 2, 4, 8, 16

_gear = None
def gear_data():
    global _gear
    if _gear is None:
        with open(os.path.join(os.path.dirname(HERE), 'data', 'gear_protection.json')) as fh: _gear = json.load(fh)
    return _gear

C = '/obj/item/clothing/'
# name, worn items (paths under /obj/item/clothing/), internals open, breathes (False = TRAIT_NOBREATH), carbon (False = borg / AI), note
SCENARIOS = [
    dict(id='bare', name='Bare skin', worn=[], internals=False, note='no clothes at all'),
    dict(id='suit', name='Jumpsuit, nothing on the head', worn=['under/color/grey'], internals=False, note='ordinary crew; uniforms carry 10 bio armour'),
    dict(id='mask', name='Jumpsuit + gas mask (no tank)', worn=['under/color/grey', 'mask/gas'], internals=False, note='a gas mask blocks smoke by itself, the tank is not needed'),
    dict(id='tank', name='Jumpsuit + breath mask + internals ON', worn=['under/color/grey', 'mask/breath'], internals=True, note='an open internals tank blocks smoke breathing'),
    dict(id='eva', name='EVA suit + helmet, internals OFF', worn=['under/color/grey', 'suit/space/eva', 'head/helmet/space/eva'], internals=False, note='space helmets do NOT block smoke without an open tank'),
    dict(id='eva_tank', name='EVA suit + helmet, internals ON', worn=['under/color/grey', 'suit/space/eva', 'head/helmet/space/eva'], internals=True, note='sealed: no foam absorption, no smoke breathing'),
    dict(id='hard', name='Engineering hardsuit, internals OFF', worn=['under/color/grey', 'suit/space/hardsuit/engine', 'head/helmet/space/hardsuit'], internals=False, note='same bio armour as an EVA suit'),
    dict(id='biosuit', name='Bio suit + bio hood', worn=['under/color/grey', 'suit/bio_suit/general', 'head/bio_hood/general'], internals=False, note='the hood blocks smoke, the suit blocks foam'),
    dict(id='suit_only', name='EVA suit, no helmet', worn=['under/color/grey', 'suit/space/eva'], internals=False, note='head stays bare: 1/6 of the body unprotected'),
    dict(id='helmet_only', name='Space helmet only (jumpsuit)', worn=['under/color/grey', 'head/helmet/space/eva'], internals=False, note='only the head is covered'),
    dict(id='nobreath', name='Does not breathe (TRAIT_NOBREATH)', worn=['under/color/grey'], internals=False, breathes=False, note='e.g. species that never breathe: smoke is skipped, foam still soaks in'),
    dict(id='borg', name='Cyborg / AI (not carbon)', worn=[], internals=False, carbon=False, note='no blood to absorb into: only contact effects land'),
]

def scenario_numbers(sc):
    g = gear_data(); worn = [g[C + w] for w in sc['worn'] if C + w in g]
    carbon = sc.get('carbon', True)
    block = gearlib.protection(worn) if carbon else 1.0
    fire_cover = gearlib.protection(worn, 'fire') if carbon else 0.0
    smoke_block = (not carbon) or sc['internals'] or (not sc.get('breathes', True)) or any(x['smoke_block'] for x in worn)
    covered = set()
    for x in worn: covered |= set(x['covers'])
    acid_open = [p for p in ('head', 'chest', 'l_arm', 'r_arm', 'l_leg', 'r_leg') if p not in covered] if carbon else []
    # acid_act looks at 4 zones: head (glasses / mask / neck / hat), chest, arms, legs.  Any clothing there takes the hit instead of the body.
    return dict(block=block, fire_cover=fire_cover, smoke_block=smoke_block, acid_open=acid_open, carbon=carbon)

def bround(x, q):
    return math.floor(x / q + 0.5 + 1e-9) * q          # BYOND round(x, q)

# ---------------------------------------------------------------- contact effects (expose_mob / expose_turf of the reagent, per exposure of `vol` units)
def contact(p, methods, vol, sc):
    """-> dict of effects of ONE exposure; keys: fire_stacks, ignite, burn (per exposed part), brute, wet_turf_s, slip_s, clean, extinguish, mutate_p, notes"""
    out = {}; v = cs.stats().get(p, {}).get('vars', {})
    name = cs.stats().get(p, {}).get('name', '')
    touchlike = methods & (TOUCH | VAPOR)
    if p == '/datum/reagent/phlogiston':
        out['fire_stacks'] = 1; out['ignite'] = True; out['burn_per_stack'] = 0.3
    elif p == '/datum/reagent/napalm':
        if methods & (TOUCH | VAPOR | PATCH): out['fire_stacks'] = min(vol / 4.0, 20)
    elif p == '/datum/reagent/consumable/ethanol':
        if methods & (TOUCH | VAPOR | PATCH): out['fire_stacks'] = vol / 15.0
    elif p == '/datum/reagent/hydrogen_peroxide':
        if methods & TOUCH: out['burn_flat'] = min(vol * 0.5 / 3.0, 25)
        if vol >= 5: out['slip_s'] = min(vol * 1.5, 60); out['slip_kind'] = 'wet floor'
    elif p in ('/datum/reagent/water', '/datum/reagent/water/salt'):
        if methods & TOUCH: out['extinguish'] = True
        if vol >= 5: out['slip_s'] = min(vol * 1.5, 60); out['slip_kind'] = 'wet floor'
    elif p == '/datum/reagent/firefighting_foam':
        if methods & (TOUCH | VAPOR): out['extinguish'] = True
    elif p == '/datum/reagent/lube':
        if vol >= 1: out['slip_s'] = min(vol * 2.0, 120); out['slip_kind'] = 'lubed floor'
    elif p in ('/datum/reagent/space_cleaner', '/datum/reagent/space_cleaner/sterilizine'):
        if methods & (TOUCH | VAPOR): out['clean'] = True
    elif p == '/datum/reagent/toxin/mutagen':
        if methods & VAPOR: out['mutate_p'] = min(33.0, vol) / 100.0
        if methods & (INGEST | PATCH | INJECT): out['mutate_p'] = 1.0
    elif v.get('acidpwr') is not None and (name.endswith('Acid') or 'acid' in p):
        pw = v['acidpwr']; tx = v.get('toxpwr', 1.0)
        if methods & INGEST: out['brute_flat'] = min(6 * tx, vol * tx)
        elif methods & INJECT: out['brute_flat'] = 1.5 * min(6 * tx, vol * tx)
        else:
            acidity = pw * min(vol * 0.005, 0.1)
            out['acid_part'] = (acidity, 2 * acidity)                 # per bare body part (brute, burn); clothes on the zone melt instead
            out['acid_borg'] = pw * min(1.0, vol * 0.1)
    return out

CONTACT_TEXT = {
    '/datum/reagent/phlogiston': 'EVERY exposure: +1 fire stack, 0.3 burn, and sets the target on fire',
    '/datum/reagent/napalm': 'each exposure adds fire stacks = units/4 (max 20)',
    '/datum/reagent/consumable/ethanol': 'each exposure adds fire stacks = units/15',
    '/datum/reagent/hydrogen_peroxide': 'touch: burn = units*0.5/3 (max 25) per exposure; floor wet at 5u+',
    '/datum/reagent/water': 'touch: puts out fire, adds wet stacks; floor wet at 5u+',
    '/datum/reagent/firefighting_foam': 'puts out fire on the target and the turf',
    '/datum/reagent/lube': 'floor: 15 s of lube + 2 s per unit (max 120 s) per exposure of 1u or more',
    '/datum/reagent/space_cleaner': 'washes the target and the floor (floor needs 1u+ per exposure)',
    '/datum/reagent/toxin/mutagen': 'foam: (units)% chance per exposure (max 33%) of a random mutation',
}

# ---------------------------------------------------------------- blood: metabolise absorbed chemicals over time
def run_blood(arrivals, max_ticks=4000):
    """arrivals: {tick index: {path: units}} -> dict(totals by kind, per-chem peak, od events, statuses, ticks)"""
    blood = {}; tot = {k: 0.0 for k in cs.KINDS}; organ = {}; peak = {}; od_first = {}; tags = {}; ticks_present = {}; crit = {k: 0.0 for k in cs.KINDS}
    cycle = {}; odp = {}
    t = 0
    while t < max_ticks:
        for p, u in arrivals.get(t, {}).items(): blood[p] = blood.get(p, 0.0) + u
        for p in list(blood):
            vol = blood[p]
            if vol <= 1e-6: del blood[p]; cycle.pop(p, None); odp.pop(p, None); continue
            pr = cs.profile(p)
            if pr is None: del blood[p]; continue
            peak[p] = max(peak.get(p, 0.0), vol); ticks_present[p] = ticks_present.get(p, 0) + 1
            cycle[p] = cycle.get(p, 0) + 1; cy = cycle[p]
            for k, v in pr['tick']['always'].items(): tot[k] += v
            for k, v in pr['tick']['crit'].items(): crit[k] += v
            for e in pr['tick']['timed']: tot[e['kind']] = tot.get(e['kind'], 0.0) + cs.timed_value(e, cy, 0)
            for s, v in pr['organ'].items(): organ[s] = organ.get(s, 0.0) + v
            for tg in pr['tags']:
                if cs.tag_active(tg, cy, 0): tags.setdefault((tg['label'], tg['cls']), set()).add(pr['name'])
            if pr['od'] and vol >= pr['od']:
                od_first.setdefault(p, t); odp[p] = odp.get(p, 0) + 1; op = odp[p]
                for k, v in pr['od_tick']['always'].items(): tot[k] += v
                for e in pr['od_tick']['timed']: tot[e['kind']] = tot.get(e['kind'], 0.0) + cs.timed_value(e, cy, op)
                for s, v in pr['od_organ'].items(): organ[s] = organ.get(s, 0.0) + v
                for tg in pr['od_tags']:
                    if cs.tag_active(tg, cy, op): tags.setdefault((tg['label'] + ' (overdose)', tg['cls']), set()).add(pr['name'])
            blood[p] = vol - pr['tick_units']
        if not blood and t > max(arrivals or {0: 0}): break
        t += 1
    return dict(totals=tot, organ=organ, peak=peak, od_first=od_first, tags=tags, ticks=ticks_present, crit=crit, duration_ticks=t)

# ---------------------------------------------------------------- the model
def foam_fraction(tiles):
    return FOAM_DT * MIN_DIL / (FOAM_LIFE * max(MIN_DIL, float(tiles)))

def analyse(kind, tile, tiles, payload_paths=None):
    """kind 'foam' | 'smoke'; tile = {reagent path: units in each tile}; tiles = area.  Returns the full report (all scenarios)."""
    kind = 'foam' if kind == 'foam' else 'smoke'
    if kind == 'foam':
        n = int(round(FOAM_LIFE / FOAM_DT)); frac = foam_fraction(tiles); dt = FOAM_DT; life = FOAM_LIFE
    else:
        n = 9; frac = SMOKE_DT / SMOKE_LIFE; dt = SMOKE_DT; life = SMOKE_LIFE
    chems = []
    for p, u in sorted(tile.items(), key=lambda kv: -kv[1]):
        st = cs.stats().get(p, {}); pen = st.get('vars', {}).get('penetrates_skin', 4.0)
        pen = pen if isinstance(pen, (int, float)) else 4.0
        chems.append(dict(path=p, name=st.get('name') or p, tile=u, per_call=u * frac, pen=int(pen), contact=CONTACT_TEXT.get(p)))
    rep = dict(kind=kind, tiles=tiles, fraction=frac, calls=n + (1 if kind == 'smoke' else 0), dt=dt, life=life, chems=chems, scenarios=[], tile_total=sum(tile.values()))
    for sc in SCENARIOS:
        num = scenario_numbers(sc)
        arrivals = {}; absorbed = {c['path']: 0.0 for c in chems}; per_call_abs = {}
        stacks = 0.0
        fx = dict(fire_stacks=0.0, ignite=False, burn_flat=0.0, brute_flat=0.0, slip_s=0.0, clean=False, extinguish=False, mutate=0.0, acid=[0.0, 0.0], acid_borg=0.0, notes=[])
        calls = n + (1 if kind == 'smoke' else 0)
        for i in range(calls):
            t_s = i * dt
            tick = int(t_s // cs.TICK_S)
            for c in chems:
                p = c['path']; vol = c['per_call']
                # blood
                if kind == 'foam':
                    if c['pen'] & VAPOR and num['carbon']:
                        amt = bround(vol * max(0.0, 1 - num['block']), 0.1)
                        if amt >= 0.5:
                            arrivals.setdefault(tick, {}); arrivals[tick][p] = arrivals[tick].get(p, 0) + amt; absorbed[p] += amt
                    methods = VAPOR
                else:
                    if num['carbon'] and not num['smoke_block']:
                        arrivals.setdefault(tick, {}); arrivals[tick][p] = arrivals[tick].get(p, 0) + vol; absorbed[p] += vol
                    methods = TOUCH | (INGEST if (num['carbon'] and not num['smoke_block']) else 0)
                    if i == calls - 1: continue                # the arrival breath has no TOUCH tick; keep the INGEST/blood part only
                e = contact(p, methods if kind == 'smoke' else VAPOR, vol, sc)
                for k, tgt in (('burn_flat', 'burn_flat'), ('brute_flat', 'brute_flat'), ('slip_s', 'slip_s')):
                    if k in e: fx[tgt] += e[k]
                if 'fire_stacks' in e: stacks = min(stacks + e['fire_stacks'], 20.0)       # adjust_fire_stacks is capped at MAX_FIRE_STACKS = 20
                if 'burn_per_stack' in e: fx['burn_flat'] += e['burn_per_stack'] * max(stacks, 1.0)
                if e.get('ignite'): fx['ignite'] = True
                if e.get('clean'): fx['clean'] = True
                if e.get('extinguish'): fx['extinguish'] = True
                if 'mutate_p' in e: fx['mutate'] = 1 - (1 - fx['mutate']) * (1 - e['mutate_p'])
                if 'acid_part' in e:
                    parts = num['acid_open']
                    zones = {'head': 'head', 'chest': 'chest', 'l_arm': 'arms', 'r_arm': 'arms', 'l_leg': 'legs', 'r_leg': 'legs'}
                    bare = {zones[p_] for p_ in parts}          # a zone counts as bare when one of its parts is bare
                    k_ = len(bare)
                    fx['acid'][0] += e['acid_part'][0] * k_; fx['acid'][1] += e['acid_part'][1] * k_
                if 'acid_borg' in e and not num['carbon']: fx['acid_borg'] += e['acid_borg']
        if kind == 'smoke' and fx['fire_stacks']: pass
        # fire stacks are capped at 20 by the game
        fx['fire_stacks'] = stacks
        blood = run_blood(arrivals) if any(absorbed.values()) else None
        rep['scenarios'].append(dict(sc=sc, num=num, absorbed={k: round(v, 2) for k, v in absorbed.items()}, absorbed_total=round(sum(absorbed.values()), 2), contact=fx, blood=blood))
    return rep

def scenario_by_id(rep, sid):
    for s in rep['scenarios']:
        if s['sc']['id'] == sid: return s
