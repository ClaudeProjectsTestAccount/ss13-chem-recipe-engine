"""tidy.py - make a recipe's step list short and easy to follow, without changing what it makes.

Two rules, both applied by the tool (never by hand) and both checked by running the engine on the result:

  1. COMBINE.  Neighbouring dispenser steps that add the same number of units (of different chemicals) become ONE step on the page
     ("Dispenser, 3 chemicals, in this order: 10u Hydrogen, 10u Nitrogen, 10u Sulfuric Acid").  To get more of those, a run of
     neighbouring dispenser steps may be re-ordered (by quantity) when the engine says the result is identical.
  2. FEWER BUTTON CHANGES.  Pressing the same dispenser button again is nearly free; switching to another button is the effort.  Each
     step's units are split into clicks (at most 3 per step, more only if the units need more) so the whole recipe has as few button
     changes as possible, e.g. 20u then 10u -> two 10u clicks, then one 10u click.  Dispenser steps that clamp to the free space are
     left alone, because their exact clicks are part of the recipe.

`tidy()` returns ops whose dispense entries carry their clicks: ('dispense', name, units, (click, click, ...)).  `display_steps()` turns the
simulated rig into the steps the page shows, merging the combinable ones.
"""
import itertools
import planner, chemcli

MAX_CLICKS = 3          # clicks of one step: as few as it takes, but up to this many when that saves a button change
CLICK_COST = 0.1        # one more click costs this, one button change costs 1
BUTTONS = sorted(planner.DISP_AMOUNTS, reverse=True)


# ------------------------------------------------------------------ click choice
def click_options(units):
    """every way to press `units` as a run of clicks, grouped by button: tuples, fewest clicks first"""
    best = len(planner.click_plan(units))
    limit = max(best, MAX_CLICKS)
    seen = set(); out = []
    def rec(rest, start, cur):
        if rest == 0:
            multiset = tuple(cur)
            if multiset not in seen:
                seen.add(multiset)
                vals = sorted(set(cur), reverse=True)
                for perm in itertools.permutations(vals):
                    out.append(tuple(v for v in perm for _ in range(cur.count(v))))
            return
        if len(cur) >= limit: return
        for i in range(start, len(BUTTONS)):
            b = BUTTONS[i]
            if b <= rest: rec(rest - b, i, cur + [b])
    rec(units, 0, [])
    out.sort(key=lambda t: (len(t), [-x for x in t]))
    return out

def pick_clicks(unit_list, pinned=()):
    """one click tuple per dispense step so that the whole recipe presses as few different buttons in a row as possible"""
    opts = []
    for i, u in enumerate(unit_list):
        if i in pinned: opts.append([tuple(sorted(planner.click_plan(u), reverse=True))])
        else: opts.append(click_options(u))
    # Viterbi over (step, last button pressed)
    layer = {None: (0.0, [])}
    for step in opts:
        nxt = {}
        for last, (cost, path) in layer.items():
            for arr in step:
                c = cost + CLICK_COST * len(arr); prev = last
                for a in arr:
                    if prev is not None and a != prev: c += 1
                    prev = a
                if prev not in nxt or c < nxt[prev][0] - 1e-9: nxt[prev] = (c, path + [arr])
        layer = nxt
    return min(layer.values(), key=lambda v: v[0])[1] if opts else []

def button_changes(click_lists):
    seq = [a for cl in click_lists for a in cl]
    return sum(1 for x, y in zip(seq, seq[1:]) if x != y)


# ------------------------------------------------------------------ equivalence
def _fingerprint(db, ops, gear, tier):
    """what the recipe makes, run twice: clicks as listed and clicks of every step in the opposite order (so a recipe that does not care
    about click order keeps not caring)"""
    out = []
    for biggest in (True, False):
        planner.CLICKS_BIGGEST_FIRST = biggest
        try: rig = chemcli._run(db, ops, tier, False, gear)
        except Exception: return None
        finally: planner.CLICKS_BIGGEST_FIRST = True
        out.append((chemcli.signature(rig), tuple(sorted(rig.sim.warnings)), round(rig.peak, 1), round(rig.beaker.temp), round(rig.syringe.total, 1)))
    return tuple(out)

def _segments(ops):
    segs = []; cur = []
    for i, o in enumerate(ops):
        if o[0] == 'dispense': cur.append(i)
        else:
            if cur: segs.append(cur); cur = []
    if cur: segs.append(cur)
    return segs

def groups(ops, two=False):
    """number of page steps the dispenser steps of `ops` turn into (neighbours with equal units merge)"""
    n = 0; prev = None
    for o in ops:
        if o[0] == 'dispense' and prev is not None and o[2] == prev and not two: continue
        prev = o[2] if o[0] == 'dispense' else None
        n += 1
    return n

def _orders(items):
    """candidate orders for a run of dispense ops: as written, grouped by quantity (three ways)"""
    first = []
    for o in items:
        if o[2] not in first: first.append(o[2])
    cands = [list(items),
             sorted(items, key=lambda o: -o[2]),
             sorted(items, key=lambda o: o[2]),
             sorted(items, key=lambda o: first.index(o[2]))]
    out = []
    for c in cands:
        if c not in out: out.append(c)
    return out


# ------------------------------------------------------------------ the rule set
def tidy(db, ops, gear=None, tier=1, reorder=True):
    """-> ops with explicit clicks.  The result is guaranteed to make exactly what `ops` makes (same beaker, effects, warnings, temperature)."""
    ops = [tuple(o[:3]) if o[0] == 'dispense' else tuple(o) for o in ops]           # drop clicks from an earlier tidy: start from the plain recipe
    base = _fingerprint(db, ops, gear, tier)
    if base is None: return ops
    two = bool(gear and gear.two)
    cur = list(ops)
    if reorder and not two:
        for seg in _segments(cur):
            items = [cur[i] for i in seg]
            if len(items) < 2: continue
            best = None
            for cand in _orders(items):
                trial = list(cur)
                for i, o in zip(seg, cand): trial[i] = o
                if cand != items and _fingerprint(db, trial, gear, tier) != base: continue
                score = (groups(trial, two), button_changes(pick_clicks([o[2] for o in trial if o[0] == 'dispense'], _pinned(db, ops, gear, tier, trial))))
                if best is None or score < best[0]: best = (score, trial)
            if best: cur = best[1]
    pin = _pinned(db, ops, gear, tier, cur)
    units = [o[2] for o in cur if o[0] == 'dispense']
    chosen = pick_clicks(units, pin)
    default = [tuple(sorted(planner.click_plan(u), reverse=True)) for u in units]
    def build(cl):
        it = iter(cl); return [(o[0], o[1], o[2], next(it)) if o[0] == 'dispense' else o for o in cur]
    out = build(chosen)
    if _fingerprint(db, out, gear, tier) == base: return out
    # the engine disagrees (a click-order effect): put the default clicks back one step at a time, last step first, until it agrees
    cl = list(chosen)
    for i in reversed(range(len(cl))):
        if cl[i] != default[i]:
            cl[i] = default[i]
            out = build(cl)
            if _fingerprint(db, out, gear, tier) == base: return out
    return build(default)

def _pinned(db, ops, gear, tier, cur):
    """indexes (among the dispense steps of `cur`) whose click amounts are clamped by the free space: those clicks stay as they are"""
    try: rig = chemcli._run(db, cur, tier, False, gear)
    except Exception: return ()
    pins = []; prev = 0; k = -1
    for st in rig.steps:
        if st['op'] and st['op'][0] == 'dispense':
            k += 1
            if st['nwarn'] > prev and any('clamp' in w for w in rig.sim.warnings[prev:st['nwarn']]): pins.append(k)
        prev = st['nwarn']
    return tuple(pins)


# ------------------------------------------------------------------ display
def display_steps(rig, gear=None):
    """the simulated steps as the page shows them: [{'t': plain text, 'parts': [[kind, text]], 'items': [...]?, 'b': beaker state, 's': syringe state}]"""
    two = bool(gear and gear.two); out = []; i = 0; sts = rig.steps
    while i < len(sts):
        st = sts[i]; op = st['op']
        if op and op[0] == 'dispense' and not two:
            j = i
            while j + 1 < len(sts) and sts[j + 1]['op'] and sts[j + 1]['op'][0] == 'dispense' and sts[j + 1]['op'][2] == op[2]: j += 1
            if j > i:
                grp = sts[i:j + 1]
                items = [[['u', '%du' % g['op'][2]], ['c', g['op'][1]], ['n', '(%s)' % g['op'][4]]] for g in grp]
                head = [['t', 'Dispenser, %d chemicals, %du each, in this order:' % (len(grp), op[2])]]
                flat = 'Dispenser, %d chemicals, in this order: %s' % (len(grp), '; '.join('%du %s (%s)' % (g['op'][2], g['op'][1], g['op'][4]) for g in grp))
                out.append({'t': flat, 'parts': head, 'items': items, 'b': grp[-1]['beaker'], 's': grp[-1]['syringe']})
                i = j + 1; continue
        out.append({'t': st['text'], 'parts': [list(p) for p in st['parts'] if p[1] or p[0] == 'trig'], 'b': st['beaker'], 's': st['syringe']})
        i += 1
    return out
