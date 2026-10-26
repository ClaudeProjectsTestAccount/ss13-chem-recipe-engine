#!/usr/bin/env python3
"""
chemcli.py - Cyborg Chem Nade planner for Monkestation (uses chemlib/planner/search).

  chemcli.py reagent <name>                 recipes that make / use a reagent, dispenser availability
  chemcli.py reaction <name>                one recipe in detail
  chemcli.py sim "<ops>" [--tier N] [gear]  run a hand-written procedure and print the trace
         ops: dispense <reagent> <units>; draw [units]; spill; swap; heat <K>; inject   (separate with ';')
  chemcli.py nade --trigger foam|smoke --payload <reagent> [--mode max|lean] [--tier N] [--top K] [gear]
                                            search trigger-carrier + payload-beaker designs, print guide(s)
  gear (all optional, name or volume):  --beaker large|xl|meta|bluespace|beaker|noreact|bottle|tube|<units>   (payload beaker, default large=100)
                                        --syringe standard|piercing|bluespace|<units>                        (default standard=15)
                                        --trigger-beaker <name|units>   two-beaker mode: no syringe, pour this beaker into --beaker
                                        --trigger-units N               how much trigger to make (default: syringe volume / 15 for two-beaker)
                                        --step N                        dispenser granularity of the search grid (auto for big beakers)

Everything is simulated by chemlib (a port of holder.dm / recipes). See README in the notes tab.
"""
import sys, argparse, itertools, random, time, json
import chemlib, planner, search
from chemlib import DB

def tail(s): return s.replace('/datum/reagent/', '')

# ---------------------------------------------------------------- payload decomposition
def decompose(db, payload, avail, max_temp=1000, seen=()):
    """cheapest way to make `payload` from dispensable reagents.
       returns dict(order=[raw...], heat=K, reactions=[...]) or None"""
    if payload in avail:
        return dict(order=[payload], heat=0, reactions=[], cost=1)
    if payload in seen: return None
    best = None
    for rx in db.reactions:
        if payload not in rx.results: continue
        if rx.container or rx.other or rx.non_instant or rx.is_cold or rx.effects: continue
        if rx.required_temp > max_temp: continue
        if any(r in rx.cat for r in rx.results): continue   # self-catalytic (e.g. blood multiplier): needs a seed, not a source
        order, heat, rxs, cost, ok = [], rx.required_temp if rx.required_temp > 300 else 0, [rx.short], 0, True
        for q in rx.req:
            sub = decompose(db, q, avail, max_temp, seen + (payload,))
            if sub is None: ok = False; break
            for o in sub['order']:
                if o not in order: order.append(o)
            heat = max(heat, sub['heat']); rxs = sub['reactions'] + rxs; cost += sub['cost']
        if not ok: continue
        cand = dict(order=order, heat=heat, reactions=rxs, cost=cost + (3 if heat else 0))
        if best is None or cand['cost'] < best['cost']: best = cand
    return best

# ---------------------------------------------------------------- design search
# syr_pure = (reagent, tolerance): trigger needs >= trigger_units - tolerance of that reagent
# (foam tolerance 0.5 reproduces the old 14.5-of-15; BYOND round() can leave the exact amount a hair short)
TRIGGERS = {
    'foam': dict(syr=['fluorine', 'carbon', 'sulfuric acid'], syr_pure=('fluorosurfactant', 0.5),
                 extras=['water'], metric='foam'),
    'smoke': dict(syr=['phosphorus'], syr_pure=('phosphorus', 0.1),
                  extras=['potassium', 'sugar'], metric='smoke'),
}

def plan(db, trigger, payload, tier=1, mode='max', min_expo=1.0, top=3, max_grid=40000, heat_speed=0.05, quiet=False,
         gear=None, trig_units=None, step=None):
    T = TRIGGERS[trigger]
    gear = gear or planner.Gear()
    trig_units = trig_units or gear.default_trigger_units()
    if trig_units > gear.trigger_vol: raise SystemExit('trigger amount %g exceeds the trigger carrier (%g)' % (trig_units, gear.trigger_vol))
    if not gear.two and trig_units not in gear.samts:
        raise SystemExit('syringe can only be set to %s per draw/inject; use one of those as --trigger-units' % gear.samts)
    bcap = gear.beaker - trig_units
    if bcap <= 0: raise SystemExit('no room for a payload: beaker %g, trigger %g' % (gear.beaker, trig_units))
    step = step or (5 if gear.beaker <= 120 else 10 if gear.beaker <= 200 else 15)
    avail = set(planner.Rig(db, tier, gear=gear).avail)
    pay = db.find_reagent(payload)
    dec = decompose(db, pay, avail)
    if dec is None:
        raise SystemExit('cannot build %s from dispensable reagents at dispenser tier %d' % (db.name(pay), tier))
    raws = [tail(p) for p in dec['order']]
    extras = list(T['extras'])
    names = raws + ['+' + e for e in extras]            # '+x' = trigger-side extra, added last
    n = len(names)
    heat = dec['heat']
    if heat and not quiet:
        print('payload needs %dK -> design includes a heater step (assumes your borg can use a chem heater)' % (heat + 20))

    def bkr_builder(v):
        ops = [('dispense', raws[i], v[i]) for i in range(len(raws)) if v[i]]
        if heat: ops.append(('heat', heat + 20, heat_speed))
        ops += [('dispense', extras[j], v[len(raws) + j]) for j in range(len(extras)) if v[len(raws) + j]]
        return ops
    syr_ings = T['syr']
    syr_builder = lambda v: trigger_ops(gear, syr_ings, v, trig_units)
    pure_p = db.find_reagent(T['syr_pure'][0]); pure_amt = trig_units - T['syr_pure'][1]
    metric = search.foam_metrics if T['metric'] == 'foam' else search.smoke_metrics

    def judge(rig):
        if rig.syringe.total > 0.05 or rig.sim.warnings: return None      # trigger did not all go in / beaker overflowed
        m = metric(rig, pay)
        if not m or m['per_call'] < min_expo: return None
        return (m['junk_tile'] <= 0.5, m['tiles'], -round(m['junk_tile'], 2), m['payload_tile'])   # clean foam/smoke first, then area

    # grid (n <= 5) else hill-climb
    count = 0
    t0 = time.time()
    if n <= 5:
        res, ns, nb = search.evaluate_designs(db, syr_ings, names, syr_builder,
                                              lambda v: bkr_builder(v), judge,
                                              syr_filter=lambda c: c.get(pure_p, 0) >= pure_amt,
                                              bkr_max=bcap, bkr_cap=bcap, keep=400, tier=tier, step=step, syr_step=5,
                                              gear=gear, trig_units=trig_units)
    else:
        res = hillclimb(db, names, bkr_builder, syr_ings, syr_builder, judge, pure_p, pure_amt, tier, gear, bcap, step)
        ns = nb = -1
    if not res: return []
    if mode == 'lean':
        top_score = res[0][0][:3]                 # best purity/tiles/junk class
        pool = [r for r in res if r[0][:3] == top_score]
        pool.sort(key=lambda r: (r[3] + r[4], -r[0][3]))
        res = pool
    return res[:top], names, raws, extras, heat, heat_speed, trig_units

def plan_auto(db, trigger, payload, tier, mode, min_expo, top, gear, step, cands=None):
    """try several trigger amounts and keep the best design; returns (plan output, sweep table)"""
    if cands is None:
        cands = [t for t in gear.samts if t <= gear.syringe] if not gear.two else list(range(5, int(min(gear.tbeaker, gear.beaker - 5, 100)) + 1, 5))
    sweep, best = [], None
    for t in cands:
        try: out = plan(db, trigger, payload, tier, mode, min_expo, top, gear=gear, trig_units=t, step=step, quiet=True)
        except SystemExit: out = None
        if not out: sweep.append((t, None)); continue
        sweep.append((t, out[0][0][0]))
        if best is None or out[0][0][0] > best[0][0][0][0]: best = (out, t)
    return (best[0] if best else None), sweep

def trigger_ops(gear, syr_ings, v, units=None):
    """ops that prepare the trigger carrier"""
    ops = [('dispense', a, b) for a, b in zip(syr_ings, v) if b]
    if gear.two: return [('swap',)] + ops                    # fill the trigger beaker (the other beaker sits in the dispenser)
    return ops + [('draw', int(units or gear.syringe)), ('spill',)]

def hillclimb(db, names, bkr_builder, syr_ings, syr_builder, judge, pure_p, pure_amt, tier, gear=None, bcap=85, step=5):
    gear = gear or planner.Gear()
    # fixed best syringe: smallest raw that gives a pure 15u draw
    best_syr = None
    for v in search.vectors(len(syr_ings), 5, 100):
        if sum(v) == 0: continue
        try: rig = planner.run(db, syr_builder(v), tier, False, gear)
        except Exception: continue
        if rig.sim.warnings: continue
        if rig.syringe.r.get(pure_p, [0])[0] >= pure_amt and (best_syr is None or sum(v) < sum(best_syr)):
            best_syr = v
    if best_syr is None: return []
    sst = None
    rig = planner.run(db, syr_builder(best_syr), tier, False, gear)
    sst = search.state_of(rig.syringe)
    def score(v):
        if sum(v) == 0 or sum(v) > gear.beaker: return None
        try: r = planner.run(db, bkr_builder(v), tier, False, gear)
        except Exception: return None
        if r.beaker.total > bcap + 1e-6 or r.sim.effects or r.sim.warnings: return None
        r2 = planner.Rig(db, tier, gear=gear)
        search.load_state(r2.syringe, sst); search.load_state(r2.beaker, search.state_of(r.beaker))
        r2.inject()
        return judge(r2)
    found = {}
    rnd = random.Random(1)
    for restart in range(60):
        hi = max(30, int(bcap // 3) // step * step + step)
        v = [rnd.choice(range(0, hi, step)) for _ in names]
        s = score(tuple(v))
        for _ in range(300):
            if s is not None: break
            v = [rnd.choice(range(0, hi, step)) for _ in names]; s = score(tuple(v))
        if s is None: continue
        improved = True
        while improved:
            improved = False
            for i in range(len(v)):
                for d in (-step, step):
                    w = list(v); w[i] += d
                    if w[i] < 0: continue
                    s2 = score(tuple(w))
                    if s2 is not None and s2 > s:
                        v, s = w, s2; improved = True
        found[tuple(v)] = s
    out = [(s, best_syr, v, sum(best_syr), sum(v)) for v, s in found.items()]
    out.sort(key=lambda r: r[0], reverse=True)
    return out

# ---------------------------------------------------------------- presentation
def full_ops(raws, extras, heat, heat_speed, syr_ings, sv, bv, gear=None, units=None):
    gear = gear or planner.Gear()
    ops = trigger_ops(gear, syr_ings, sv, units)
    if gear.two: ops.append(('swap',))                       # back to the payload beaker
    for i, r in enumerate(raws):
        if bv[i]: ops.append(('dispense', r, bv[i]))
    if heat: ops.append(('heat', heat + 20, heat_speed))
    for j, e in enumerate(extras):
        if bv[len(raws) + j]: ops.append(('dispense', e, bv[len(raws) + j]))
    ops.append(('inject',))
    return ops

def run_ops(db, ops, tier=1, reverse=False):
    return planner.run(db, [o[:2] + o[2:] if o[0] != 'heat' else ('heat', o[1]) for o in ops], tier, reverse) if False else _run(db, ops, tier, reverse)

def _run(db, ops, tier, reverse, gear=None):
    rig = planner.Rig(db, tier, reverse, gear)
    for st in ops:
        if st[0] == 'dispense': rig.dispense(st[1], st[2])
        elif st[0] == 'swap': rig.swap()
        elif st[0] == 'draw': rig.draw(st[1] if len(st) > 1 else None)
        elif st[0] == 'spill': rig.spill()
        elif st[0] == 'add': rig.add(st[1], st[2], st[3] if len(st) > 3 else None)
        elif st[0] == 'heat': rig.heat(st[1], st[2] if len(st) > 2 else 0.05)
        elif st[0] == 'inject': rig.inject()
    return rig

def signature(rig):
    out = []
    for e in rig.sim.effects:
        out.append((e['kind'], e.get('tiles'), tuple(sorted((k, round(v, 1)) for k, v in e.get('tile', {}).items())), e.get('range'), e.get('max')))
    return tuple(out)

def verify_orders(db, ops, tier, gear=None):
    """order robustness: (1) same-primary reaction-order reversed  (2) every permutation of consecutive dispense runs"""
    base = _run(db, ops, tier, False, gear); sig = signature(base)
    rev = _run(db, ops, tier, True, gear)
    report = {'reverse_index_order_same': signature(rev) == sig, 'perm_total': 0, 'perm_same': 0, 'bad_orders': []}
    # segment dispense runs (split at non-dispense ops)
    segs = []; cur = []
    for i, o in enumerate(ops):
        if o[0] == 'dispense': cur.append(i)
        else:
            if cur: segs.append(cur); cur = []
    if cur: segs.append(cur)
    rnd = random.Random(1)
    def seg_perms(seg):
        if len(seg) <= 6: return list(itertools.permutations(seg))
        out = [tuple(seg)]                                          # long run: as written, each element first / last, plus 150 random orders
        for i in range(len(seg)):
            rest = [x for j, x in enumerate(seg) if j != i]
            out.append(tuple([seg[i]] + rest)); out.append(tuple(rest + [seg[i]]))
        for _ in range(150):
            q = list(seg); rnd.shuffle(q); out.append(tuple(q))
        return out
    perms = [seg_perms(s) for s in segs]
    total = 1
    for pl in perms: total *= len(pl)
    if total <= 2000:
        combos = itertools.product(*perms)                     # every combination of orders across all segments
    else:                                                      # too many: vary one segment at a time, the rest as written
        base_combo = [pl[0] for pl in perms]
        combos = []
        for i, pl in enumerate(perms):
            for perm in pl:
                c = list(base_combo); c[i] = perm; combos.append(c)
    for combo in combos:
        new = list(ops)
        for seg, perm in zip(segs, combo):
            for slot, idx in zip(seg, perm): new[slot] = ops[idx]
        try:
            r = _run(db, new, tier, False, gear)
            ok = signature(r) == sig
        except Exception:
            ok = False
        report['perm_total'] += 1; report['perm_same'] += ok
        if not ok and len(report['bad_orders']) < 4:
            report['bad_orders'].append([o[1] + ' ' + str(o[2]) for o in new if o[0] == 'dispense'])
    return report

def fmt_effect(db, rig, payload):
    lines = []
    for e in rig.sim.effects:
        if e['kind'] in ('foam', 'smoke'):
            tile = e['tile']
            lines.append('%s: %d tiles. Each tile holds: %s' %
                         (e['kind'].upper(), e['tiles'], ', '.join('%gu %s' % (round(v, 1), db.name(p)) for p, v in tile.items())))
            if payload is not None:
                m = (search.foam_metrics if e['kind'] == 'foam' else search.smoke_metrics)(rig, payload)
                if m:
                    note = ('foam amplifies the payload x%g; ' % e['scale']) if e['kind'] == 'foam' else ''
                    lines.append('   (%slives %ds; every %.1fs tick exposes the floor to %.1fu of %s per tile, %d ticks)' %
                                 (note, m['life'], search.FOAM_DT if e['kind'] == 'foam' else search.SMOKE_DT,
                                  m['per_call'], db.name(payload), m['calls']))
        elif e['kind'] == 'vortex':
            lines.append('VORTEX (%s): range %.2f tiles%s' % (e['mode'], e['range'],
                         ' (CAPPED at %g; the raw formula gave %.1f)' % (e['cap'], e['raw_range']) if e['raw_range'] > e['cap'] else ''))
        elif e['kind'] == 'mobspawn':
            lines.append('MOB SPAWN: rand(1,%d) mobs%s' % (e['max'], ' (friendly)' if e['friendly'] else ''))
        else:
            lines.append('!! UNMODELED %s' % e)
    return lines

def print_guide(db, title, ops, tier, payload, show_logs=True, gear=None):
    rig = _run(db, ops, tier, False, gear)
    print('### %s   [gear: %s]' % (title, (gear or planner.Gear()).describe()))
    for i, st in enumerate(rig.steps, 1):
        print('%2d. %s' % (i, st['text']))
        print('      beaker: %s%s | syringe: %s' % (st['beaker'], ('  @%dK' % st['beaker_temp']) if st['beaker_temp'] not in (150, 300) else '', st['syringe']))
        if show_logs:
            for l in st['log']: print('        ' + l)
        for n in st['notes']: print('      note: ' + n)
    for l in fmt_effect(db, rig, payload): print(l)
    for w in rig.sim.warnings: print('WARNING:', w)
    v = verify_orders(db, ops, tier, gear)
    print('order check: reversed same-reagent reaction priority -> %s; %d of %d dispense orders give this same result%s' %
          ('same' if v['reverse_index_order_same'] else 'DIFFERENT', v['perm_same'], v['perm_total'],
           '' if v['perm_same'] == v['perm_total'] else '  => ORDER MATTERS, follow the steps exactly'))
    if v['bad_orders']: print('   e.g. these orders do NOT work:', v['bad_orders'][:2])
    return rig

def parse_ops(text):
    ops = []
    for part in text.split(';'):
        w = part.strip().split()
        if not w: continue
        if w[0] == 'dispense': ops.append(('dispense', ' '.join(w[1:-1]), int(w[-1])))
        elif w[0] == 'add': ops.append(('add', ' '.join(w[1:-1]), float(w[-1])))
        elif w[0] == 'draw': ops.append(('draw', int(w[1]) if len(w) > 1 else None))
        elif w[0] == 'heat': ops.append(('heat', float(w[1])))
        else: ops.append((w[0],))
    return ops

def add_gear(a):
    a.add_argument('--beaker', default='large', help='payload beaker: ' + '/'.join(planner.BEAKER_TYPES) + ' or a volume')
    a.add_argument('--syringe', default='standard', help='syringe: ' + '/'.join(planner.SYRINGE_TYPES) + ' or a volume')
    a.add_argument('--trigger-beaker', default=None, help='two-beaker mode: name or volume of the trigger beaker (replaces the syringe)')
    a.add_argument('--trigger-units', default=None, help='units of trigger to make, or "auto" to sweep amounts and keep the best '
                   '(default: a full syringe; two-beaker mode defaults to auto)')
    a.add_argument('--step', type=int, default=None)

def gear_from(args):
    return planner.Gear(args.beaker, args.syringe, args.trigger_beaker)

def main(argv=None):
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest='cmd')
    a = sub.add_parser('reagent'); a.add_argument('name')
    a = sub.add_parser('reaction'); a.add_argument('name')
    a = sub.add_parser('sim'); a.add_argument('ops'); a.add_argument('--tier', type=int, default=1); add_gear(a)
    a = sub.add_parser('nade'); add_gear(a)
    a.add_argument('--trigger', choices=list(TRIGGERS), required=True)
    a.add_argument('--payload', required=True)
    a.add_argument('--mode', choices=['max', 'lean'], default='max')
    a.add_argument('--tier', type=int, default=1)
    a.add_argument('--top', type=int, default=2)
    a.add_argument('--min-expo', type=float, default=1.0, help='minimum volume exposed per tile per effect tick (turf effects need >=1)')
    args = ap.parse_args(argv)
    db = DB()
    if args.cmd == 'reagent':
        p = db.find_reagent(args.name)
        lists = planner.dispenser_lists(db)
        tier = [t for t, l in lists.items() if p in l]
        print('%s  (%s)  dispensable at dispenser tier: %s' % (db.name(p), p, tier[0] if tier else 'not dispensable'))
        print('made by:'); [print('  ', r.short, {db.name(q): c for q, c in r.req.items()}, '->', {db.name(q): c for q, c in r.results.items()}, 'T>=%g' % r.required_temp) for r in db.reactions if p in r.results]
        print('used in:'); [print('  ', r.short, {db.name(q): c for q, c in r.req.items()}, '->', {db.name(q): c for q, c in r.results.items()}, 'T>=%g' % r.required_temp, r.effects) for r in db.reactions if p in r.req]
    elif args.cmd == 'reaction':
        r = db.by_short.get(args.name) or db.by_path.get(args.name)
        if not r: raise SystemExit('no such reaction; try: ' + ', '.join(x.short for x in db.reactions if args.name in x.short)[:300])
        print(r.path, '\n  from', r.source, '\n  needs', {db.name(q): c for q, c in r.req.items()}, '\n  catalysts', {db.name(q): c for q, c in r.cat.items()},
              '\n  makes', {db.name(q): c for q, c in r.results.items()}, '\n  min temp %g%s' % (r.required_temp, ' (cold recipe)' if r.is_cold else ''),
              '\n  side effects', r.effects, '\n  on_reaction:', (r.on_reaction or '-')[:400])
    elif args.cmd == 'sim':
        rig = _run(db, parse_ops(args.ops), args.tier, False, gear_from(args))
        for i, st in enumerate(rig.steps, 1):
            print('%2d. %s\n      beaker: %s | syringe: %s' % (i, st['text'], st['beaker'], st['syringe']))
            for l in st['log']: print('        ' + l)
        for l in fmt_effect(db, rig, None): print(l)
    elif args.cmd == 'nade':
        gear = gear_from(args)
        tu = args.trigger_units
        if tu is None and gear.two: tu = 'auto'
        if tu == 'auto':
            out, sweep = plan_auto(db, args.trigger, args.payload, args.tier, args.mode, args.min_expo, args.top, gear, args.step)
            print('trigger amount sweep (score = clean?, tiles, -junk, payload/tile): ' + '; '.join(
                '%du: %s' % (t, ('%s/%d tiles' % ('clean' if sc[0] else 'junk', sc[1])) if sc else 'none') for t, sc in sweep))
        else:
            out = plan(db, args.trigger, args.payload, args.tier, args.mode, args.min_expo, args.top, gear=gear,
                       trig_units=int(tu) if tu else None, step=args.step)
        if not out: print('no valid design found'); return
        res, names, raws, extras, heat, hs, tunits = out
        syr_ings = TRIGGERS[args.trigger]['syr']
        pay = db.find_reagent(args.payload)
        for k, (sc, sv, bv, sr, br) in enumerate(res, 1):
            ops = full_ops(raws, extras, heat, hs, syr_ings, sv, bv, gear, tunits)
            print_guide(db, 'design %d  score=%s  (trigger raw %du, payload raw %du)' % (k, tuple(round(x, 2) for x in sc), sr, br), ops, args.tier, pay, gear=gear)
            print()

if __name__ == '__main__':
    main()
