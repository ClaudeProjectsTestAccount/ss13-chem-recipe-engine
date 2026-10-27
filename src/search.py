"""
search.py - grid search for trigger-carrier (syringe or 2nd beaker) + payload-beaker nade designs.
(sizes come from planner.Gear; the default is a stock 15u syringe + 100u large beaker => 85u payload)

A design = (syringe recipe, beaker recipe).  Everything is simulated through chemlib, so
reaction order, BYOND round() quirks, partial-draw proportions and leftover reagents are all
accounted for.  Dispenser quantities are multiples of 5u (the only click sizes the large
beaker offers are 5/10/15/20/25/30/50/100).
"""
import itertools, copy, math
from collections import OrderedDict
import chemlib, planner
from chemlib import Holder

def vectors(n, step, total_max, per_max=None, min_total=0):
    """all n-tuples of non-negative multiples of `step` summing to <= total_max"""
    def rec(i, left):
        if i == n:
            yield (); return
        top = left if per_max is None else min(left, per_max[i])
        for v in range(0, top + 1, step):
            for rest in rec(i + 1, left - v):
                yield (v,) + rest
    for v in rec(0, total_max):
        if sum(v) >= min_total:
            yield v

def state_of(h):
    return (OrderedDict((p, list(v)) for p, v in h.r.items()), h.temp)

def load_state(h, st):
    h.r = OrderedDict((p, list(v)) for p, v in st[0].items()); h.temp = st[1]; h.update_total()

def run_phase(db, ops, tier, reverse=False, gear=None):
    return planner.run(db, ops, tier, reverse, gear)

def evaluate_designs(db, syr_ings, bkr_ings, syr_builder, bkr_builder, judge,
                     syr_filter=lambda c: True, bkr_filter=lambda c: True,
                     syr_max=100, bkr_max=100, bkr_cap=None, step=5, tier=1, keep=15,
                     per_max_syr=None, per_max_bkr=None, gear=None, trig_units=None, trig_max=None, syr_step=5):
    """
    syr_builder(vec)  -> trigger prep: ops ending ('draw',S),('spill',)  (syringe mode) or starting ('swap',) (two-beaker mode)
    bkr_builder(vec)  -> ops that build the payload in the main beaker
    judge(rig)        -> score tuple (higher is better) or None if invalid; rig = after inject
    gear              -> planner.Gear (beaker / syringe / trigger beaker sizes); trig_units = trigger amount aimed for
    """
    gear = gear or planner.Gear()
    if trig_units is None: trig_units = gear.default_trigger_units()
    if trig_max is None: trig_max = trig_units if not gear.two else trig_units + 5
    if bkr_cap is None: bkr_cap = gear.beaker - trig_units
    syr_states = {}
    for v in vectors(len(syr_ings), syr_step, syr_max, per_max_syr):
        if sum(v) == 0: continue
        ops = syr_builder(v)
        try:
            rig = run_phase(db, ops, tier, False, gear)
        except Exception:
            continue
        if rig.syringe.total < trig_units - 1e-6 or rig.syringe.total > trig_max + 1e-6: continue
        if rig.sim.effects or rig.sim.warnings: continue   # prep must be inert and not clamped by a full beaker
        c = {p: round(x[0], 3) for p, x in rig.syringe.r.items()}
        if not syr_filter(c): continue
        key = tuple(sorted(c.items()))
        cur = syr_states.get(key)
        if cur is None or sum(v) < cur[0]:
            syr_states[key] = (sum(v), v, state_of(rig.syringe), state_of(rig.beaker), rig.steps)
    bkr_states = {}
    for v in vectors(len(bkr_ings), step, bkr_max, per_max_bkr):
        if sum(v) == 0: continue
        ops = bkr_builder(v)
        try:
            rig = run_phase(db, ops, tier, False, gear)
        except Exception:
            continue
        if rig.beaker.total > bkr_cap + 1e-6: continue
        if rig.sim.effects or rig.sim.warnings: continue
        c = {p: round(x[0], 3) for p, x in rig.beaker.r.items()}
        if not bkr_filter(c): continue
        key = (tuple(sorted(c.items())), round(rig.beaker.temp))
        cur = bkr_states.get(key)
        if cur is None or sum(v) < cur[0]:
            bkr_states[key] = (sum(v), v, state_of(rig.beaker), rig.steps)
    results = []
    for sk, (sraw, sv, sst, _, _) in syr_states.items():
        for bk, (braw, bv, bst, _) in bkr_states.items():
            rig = planner.Rig(db, tier, gear=gear)
            load_state(rig.syringe, sst); load_state(rig.beaker, bst)
            rig.sim.log.clear()
            rig.inject()
            sc = judge(rig)
            if sc is None: continue
            results.append((sc, sv, bv, sraw, braw))
    results.sort(key=lambda r: r[0], reverse=True)
    return results[:keep], len(syr_states), len(bkr_states)

FOAM_DT = 0.2      # SSfoam effect_wait (fluids.dm: FLUID_SUBSYSTEM_DEF(foam)); foam lifetime 8s
SMOKE_DT = 2.0     # SSsmoke effect_wait; chem smoke lifetime 20s

def _metrics(kind, rig, payload_path):
    """per-tile payload and the amount exposed to a tile's floor / mobs on each tick (numbers from tileapply)"""
    import tileapply
    fx = [e for e in rig.sim.effects if e['kind'] == kind]
    if len(fx) != 1 or any(e['kind'] == 'UNMODELED' for e in rig.sim.effects):
        return None
    f = fx[0]; tile = f['tile']
    pay = tile.get(payload_path, 0.0)
    junk = sum(v for p, v in tile.items() if p != payload_path)
    pl = tileapply.plan(kind, f['tiles'])
    per = pay * pl['fraction']
    return dict(tiles=f['tiles'], payload_tile=pay, junk_tile=junk, per_call=per, calls=pl['exposures'] if kind == 'foam' else pl['life'] / pl['dt'], expo_per_s=per / pl['dt'], life=int(pl['life']))

def foam_metrics(rig, payload_path): return _metrics('foam', rig, payload_path)
def smoke_metrics(rig, payload_path): return _metrics('smoke', rig, payload_path)
