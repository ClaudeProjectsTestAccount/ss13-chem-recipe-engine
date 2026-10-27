"""
stoich.py - exact ingredient amounts for a chemical, with nothing left over.

A recipe wastes beaker space when a reaction chain is fed in the wrong proportions: the surplus of an intermediate (oil, phenol, ammonia...) or of a raw
reagent stays in the beaker and rides into the foam / smoke doing nothing.  This module works the chain out exactly, in whole fractions:

  plan(db, avail, path, amount)   -> dict(raw={reagent: units}, steps=[(reagent, units) in dispense order], heat=K)
  quantum(db, avail, path)        -> smallest amount of the product whose every raw ingredient is a multiple of 5u (the dispenser's smallest click), i.e. no leftovers
  quanta(db, avail, path, cap)    -> every such amount up to cap
  ops(db, avail, path, amount)    -> planner ops for it ([('dispense', 'name', units), ...]); None when the amount is not exact

Cheapest recipe per ingredient is chosen like chemcli.decompose does (fewest raw reagents; heated reactions cost a little more).
"""
from fractions import Fraction
from collections import OrderedDict

STEP = 5

ALLOW_EFFECTS = {'/datum/reagent/phlogiston'}      # reactions with a side effect we know how to handle (phlogiston: needs stabilizing agent in the beaker; the engine checks that)

def _reaction_for(db, avail, path, seen=()):
    """-> (reaction, cost) cheapest way to make `path` from `avail`, or (None, None).  Reactions with containers, side effects, timing or cold requirements are skipped."""
    if path in avail: return None, 1
    if path in seen: return None, None
    best = (None, None)
    for rx in db.reactions:
        if path not in rx.results: continue
        if rx.container or rx.other or rx.non_instant or rx.is_cold or (rx.effects and path not in ALLOW_EFFECTS): continue
        if rx.required_temp > 1000: continue
        if any(r in rx.cat for r in rx.results): continue
        cost = 3 if rx.required_temp > 300 else 0; ok = True
        for q in rx.req:
            if q in avail: cost += 1; continue
            sub, c = _reaction_for(db, avail, q, seen + (path,))
            if sub is None: ok = False; break
            cost += c
        if ok and (best[1] is None or cost < best[1]): best = (rx, cost)
    return best

def plan(db, avail, path, amount):
    """exact plan for `amount` units of `path`.  amounts are Fractions.  -> dict(raw, steps, heat, reactions) or None"""
    amount = Fraction(amount).limit_denominator(1000)
    raw = OrderedDict(); steps = []; heat = [0]; rxs = []
    def go(p, a):
        if p in avail:
            return [(p, a)]
        rx, _ = _reaction_for(db, avail, p)
        if rx is None: raise KeyError(p)
        m = a / Fraction(rx.results[p]).limit_denominator(1000)
        if rx.required_temp > 300: heat[0] = max(heat[0], rx.required_temp)
        rxs.append(rx.short)
        out = []
        direct = []
        for q, r in rx.req.items():
            qa = m * Fraction(r).limit_denominator(1000)
            if q in avail: direct.append((q, qa))
            else: out += go(q, qa)
        return out + direct
    try:
        steps = go(path, amount)
    except KeyError:
        return None
    for q, a in steps: raw[q] = raw.get(q, Fraction(0)) + a
    return dict(raw=raw, steps=steps, heat=heat[0], reactions=rxs)

def _exact(pl, step=STEP):
    return all((a / step).denominator == 1 for a in pl['raw'].values())

def quantum(db, avail, path, cap=600):
    for a in range(1, cap + 1):
        pl = plan(db, avail, path, a)
        if pl is not None and _exact(pl): return a
    return None

def quanta(db, avail, path, cap=600):
    q = quantum(db, avail, path, cap)
    return [] if q is None else list(range(q, cap + 1, q))

def raw_total(pl):
    return sum(float(a) for a in pl['raw'].values())

def ops(db, avail, path, amount):
    pl = plan(db, avail, path, amount)
    if pl is None or not _exact(pl): return None
    out = []
    for q, a in pl['steps']:
        u = int(a)
        if out and out[-1][1] == db.name(q).lower(): out[-1] = ('dispense', out[-1][1], out[-1][2] + u)
        else: out.append(('dispense', db.name(q).lower(), u))
    return out
