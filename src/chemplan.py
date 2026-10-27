"""chemplan.py - plan a plain chemical (no foam, no syringe) from the basic chem dispenser.

    python3 src/chemcli.py chems                                  list every chemical the dispenser alone can make
    python3 src/chemcli.py make mutadone oculine --beaker 50,100  plan them, print the steps
    python3 src/chemcli.py make mutadone --beaker 100 --publish   ... and file them in the recipe book / page

How it plans a chemical P:
  1. reaction tree: for every ingredient that the dispenser does not carry, pick the cheapest reaction that makes it (instant reactions
     only, no side-effect reactions, nothing that needs a container or another department), down to dispensable raws;
  2. scale: try every size of the final reaction, turn the tree into dispenser steps (raws rounded UP to the 5u the dispenser delivers,
     the last click that completes a reaction last, a heater step wherever a reaction needs heat), and RUN each one in the engine;
  3. keep the plan that leaves the most P in the beaker without overflowing it, nudge each raw by 5u to squeeze more out, and check the
     result does not depend on click order or on reaction priority.
Everything the page shows is the engine's own simulation of the final step list, never the hand calculation of step 1.
"""
import math, itertools, random
import chemlib, planner, chemcli

HEAT_MARGIN = 20      # the heater only approaches its target, so aim this far above the temperature a reaction needs


def usable(rx):
    return not (rx.container or rx.other or rx.non_instant or rx.is_cold or rx.effects) and not any(r in rx.cat for r in rx.results)


class Node:
    """one reaction in the tree: how P is made, from raws (children[q] is None) or from further nodes"""
    def __init__(self, product, rx, children, cost):
        self.product = product; self.rx = rx; self.children = children; self.cost = cost   # cost = raw units per unit of product
        self.r = rx.results[product]

def build_tree(db, product, avail, memo=None, seen=()):
    """cheapest instant-reaction route from dispensable raws to `product`; None when impossible"""
    memo = {} if memo is None else memo
    if product in memo: return memo[product]
    if product in seen: return None
    best = None
    for rx in db.reactions:
        if product not in rx.results or not usable(rx) or rx.required_temp > 900: continue
        children = {}; cost = 0.0; ok = True
        for q, a in list(rx.req.items()) + list(rx.cat.items()):
            if q in avail:
                children[q] = None; cost += a if q in rx.req else 0
                continue
            sub = build_tree(db, q, avail, memo, seen + (product,))
            if sub is None: ok = False; break
            children[q] = sub; cost += a * sub.cost if q in rx.req else 0
        if not ok: continue
        c = cost / rx.results[product] + (0.4 if rx.required_temp > 300 else 0)
        if best is None or c < best.cost: best = Node(product, rx, children, c)
    memo[product] = best
    return best

def raw_per_unit(node, acc=None, mult=1.0):
    """raws needed per unit of the tree's product (floats)"""
    acc = {} if acc is None else acc
    m = mult / node.r
    for q, a in node.rx.req.items():
        c = node.children[q]
        if c is None: acc[q] = acc.get(q, 0) + a * m
        else: raw_per_unit(c, acc, a * m)
    return acc

def roundup5(x): return int(math.ceil(x / 5.0 - 1e-9) * 5)

def gen_ops(db, node, X, ops=None):
    """steps that make X units of node.product: sub-products first, then this reaction's raws, then its heater step"""
    ops = [] if ops is None else ops
    m = max(1, int(math.ceil(X / node.r - 1e-9)))
    for q, a in node.rx.req.items():
        c = node.children[q]
        if c is not None: gen_ops(db, c, a * m, ops)
    for q, a in node.rx.req.items():
        if node.children[q] is None: ops.append(['dispense', db.name(q), roundup5(a * m)])
    for q, a in node.rx.cat.items():
        c = node.children[q]
        if c is None: ops.append(['dispense', db.name(q), roundup5(a)])
        else: gen_ops(db, c, a, ops)
    if node.rx.required_temp > 300: ops.append(['heat', int(node.rx.required_temp) + HEAT_MARGIN])
    return ops

def merge_ops(ops):
    """neighbouring dispenses of the same reagent become one step (the dispenser clicks add up anyway)"""
    out = []
    for o in ops:
        if out and o[0] == 'dispense' and out[-1][0] == 'dispense' and out[-1][1] == o[1]: out[-1] = ['dispense', o[1], out[-1][2] + o[2]]
        else: out.append(list(o))
    return out

def run(db, ops, gear):
    try: return chemcli._run(db, [tuple(o) for o in ops], 1, False, gear)
    except Exception: return None

def made(db, rig, product):
    return rig.beaker.amount(product)

def score(db, rig, product, cap):
    """higher is better: units of product in the beaker; overflowing / warnings disqualify"""
    if rig is None or [w for w in rig.sim.warnings if 'clamp' in w or 'overflow' in w or 'unknown' in w]: return -1
    if [e for e in rig.sim.effects if e['kind'] in ('HAZARD', 'UNMODELED', 'foam', 'smoke', 'vortex', 'mobspawn')]: return -1
    return made(db, rig, product)

def plan(db, product, beaker, tier=1, quiet=True):
    """best plan for `product` in a beaker (name or volume).  returns dict(ops, made, rig, gear, tree) or None"""
    avail = set(planner.Rig(db, tier).avail)
    gear = planner.Gear(beaker)
    if product in avail: return None
    tree = build_tree(db, product, avail)
    if tree is None: return None
    best = None; seen = set()
    per = raw_per_unit(tree); total_per = sum(per.values()) or 1
    for X in range(1, int(gear.beaker * 2) + 1):
        ops = merge_ops(gen_ops(db, tree, X))
        key = repr(ops)
        if key in seen: continue
        seen.add(key)
        if sum(o[2] for o in ops if o[0] == 'dispense') > gear.beaker * 3: break
        rig = run(db, ops, gear); s = score(db, rig, product, gear.beaker)
        if s > 0 and (best is None or (s, -sum(o[2] for o in ops if o[0] == 'dispense')) > (best[0], -sum(o[2] for o in best[1] if o[0] == 'dispense'))):
            best = (s, ops, rig)
    if best is None: return None
    s, ops, rig = best
    # nudge every dispense by +-5u while the product grows (or the same amount costs less raw)
    improved = True
    while improved:
        improved = False
        for i, o in enumerate(ops):
            if o[0] != 'dispense': continue
            for d in (-5, 5):
                if o[2] + d <= 0: continue
                cand = [list(x) for x in ops]; cand[i][2] += d
                r2 = run(db, cand, gear); s2 = score(db, r2, product, gear.beaker)
                raw1 = sum(x[2] for x in ops if x[0] == 'dispense'); raw2 = sum(x[2] for x in cand if x[0] == 'dispense')
                if s2 > s + 1e-6 or (abs(s2 - s) < 1e-6 and s2 > 0 and raw2 < raw1):
                    ops, rig, s = cand, r2, s2; improved = True; break
            if improved: break
    ops = prune_heat(db, ops, gear, product, s)
    ops, fragile = robustify(db, ops, gear, product, s)
    ops = best_order(db, ops, gear, product, s)
    rig = run(db, ops, gear)
    return dict(ops=ops, made=made(db, rig, product), rig=rig, gear=gear, tree=tree, fragile=fragile)

TEMP_SPREAD = (-planner.HEAT_SLACK, 0, planner.HEAT_TEST_DROP)    # beaker exactly at the heater target / as simulated (HEAT_SLACK under) / HEAT_TEST_DROP K colder than that
COOL_STEPS = (400, 360, 340, 320)              # thresholds tried for an inserted cool-down step, highest (shortest wait) first

def temp_robust(db, ops, gear, product, want):
    """does the recipe still give the same result if the beaker is a bit hotter or colder than simulated after every heater step?
    (the game's heater only approaches its target and cold chems dilute the temperature, so the real value is never exactly the simulated one)"""
    ok = True; base = None
    try:
        for d in TEMP_SPREAD:
            planner.HEAT_DROP = d
            rig = run(db, ops, gear)
            if rig is None or score(db, rig, product, gear.beaker) < want - 1e-6: return False
            sig = chemcli.signature(rig)
            if base is None: base = sig
            elif sig != base: return False
    finally: planner.HEAT_DROP = 0.0
    return ok

def robustify(db, ops, gear, product, want):
    """make the plan survive temperature drift.  tries, in order: as written / heating once at the very end (nothing cold is added to a hot beaker) /
    a cool-down step after each heater step that is followed by more chemicals (a hot beaker mixes into what you add next).  returns (ops, still_fragile)"""
    if not any(o[0] == 'heat' for o in ops): return ops, False
    if temp_robust(db, ops, gear, product, want): return ops, False
    heats = [o for o in ops if o[0] == 'heat']
    top = max(o[1] for o in heats)
    whole = merge_ops([list(o) for o in ops if o[0] != 'heat'] + [['heat', top]])
    if temp_robust(db, whole, gear, product, want): return whole, False
    cur = [list(o) for o in ops]
    for k in reversed(range(len(heats))):                                   # last heater step first
        hidx = [i for i, o in enumerate(cur) if o[0] == 'heat']
        i = hidx[k]; h = cur[i]; rest = cur[:i] + cur[i + 1:]
        found = None
        for p in range(len(rest), i - 1, -1):                               # latest spot first: nothing cold gets added to the hot beaker
            for thr in (None,) + COOL_STEPS:
                if thr is not None and not any(x[0] == 'dispense' for x in rest[p:]): continue
                c = rest[:p] + [list(h)] + ([['cool', thr]] if thr else []) + rest[p:]
                if temp_robust(db, c, gear, product, want): found = c; break
            if found: break
        if found: cur = found
    if temp_robust(db, cur, gear, product, want): return cur, False
    return ops, True

def prune_heat(db, ops, gear, product, want):
    """drop heater steps that the simulation shows are not needed (a later, hotter step often covers an earlier one)"""
    for i in reversed([i for i, o in enumerate(ops) if o[0] == 'heat']):
        cand = ops[:i] + ops[i + 1:]
        if score(db, run(db, cand, gear), product, gear.beaker) >= want - 1e-6: ops = cand
    return ops

def best_order(db, ops, gear, product, want):
    """try reordering neighbouring dispenses (largest first / reaction trigger last) so the result is click-order and priority robust"""
    def robust(o):
        rig = run(db, o, gear)
        if rig is None or score(db, rig, product, gear.beaker) < want - 1e-6: return False
        sig = chemcli.signature(rig)
        planner.CLICKS_BIGGEST_FIRST = False
        try: s2 = chemcli.signature(run(db, o, gear))
        finally: planner.CLICKS_BIGGEST_FIRST = True
        rev = chemcli.signature(chemcli._run(db, [tuple(x) for x in o], 1, True, gear))
        return sig == s2 == rev
    if robust(ops): return ops
    # permute within runs of consecutive dispenses (cheap local search), keep the first robust order that makes as much product
    idx = [i for i, o in enumerate(ops) if o[0] == 'dispense']
    runs = []; cur = []
    for i, o in enumerate(ops):
        if o[0] == 'dispense': cur.append(i)
        else:
            if cur: runs.append(cur); cur = []
    if cur: runs.append(cur)
    rnd = random.Random(7)
    for _ in range(400):
        cand = [list(o) for o in ops]
        for r in runs:
            if len(r) > 1 and rnd.random() < 0.7:
                vals = [ops[i] for i in r]; rnd.shuffle(vals)
                for i, v in zip(r, vals): cand[i] = list(v)
        if robust(cand): return cand
    return ops


# ---------------------------------------------------------------- bulk helpers used by `chemcli chems` / `chemcli make`
import json, os
META_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'data', 'chem_meta.json')

def load_meta(path=META_PATH):
    try:
        with open(path) as fh: return {k: v for k, v in json.load(fh).items() if not k.startswith('_')}
    except Exception: return {}

def buildable(db, tier=1):
    """every non-dispensable chemical the dispenser alone can make: {path: tree}"""
    avail = set(planner.Rig(db, tier).avail); memo = {}; out = {}
    for p in db.reagents:
        if p in avail: continue
        t = build_tree(db, p, avail, memo)
        if t is not None: out[p] = t
    return out

def meta_for(db, p, meta):
    short = chemcli.tail(p).split('/')[-1]
    return meta.get(short) or meta.get(db.name(p).lower().replace(' ', '_')) or {}

def make_spec(db, p, beaker_units, res, meta):
    """book entry (group 'chem') for a finished plan; the page re-simulates it, so only the labels are written here"""
    m = meta_for(db, p, meta); r = db.reagents[p]; name = db.name(p)
    heats = [o[1] for o in res['ops'] if o[0] == 'heat']
    notes = ['The chem heater only approaches its target and never reaches it, so wait until its display shows the temperature in the step before you carry on. Reactions that need heat fire as soon as the beaker is hot enough.'] if heats else []
    if any(o[0] == 'cool' for o in res['ops']): notes.append('The cool-down step matters: a beaker that is still hot would react with what you add next in a way the recipe does not want.')
    return {'id': 'chem-%s-%d-%s' % (m.get('type', 'other'), beaker_units, book_slug(name)), 'group': 'chem', 'type': m.get('type', 'other'),
            'title': name, 'tagline': m.get('tag', ''), 'beaker': beaker_units, 'payload': name, 'harm': m.get('harm', 'caution'),
            'what': m.get('what') or (r.description or name).strip(), 'notes': ' '.join(notes), 'caution': m.get('caution', ''),
            'src': '', 'rank': m.get('rank', 50), 'ops': [list(o) for o in res['ops']]}

def book_slug(s): return ''.join(c if c.isalnum() else '-' for c in s.lower()).strip('-')
