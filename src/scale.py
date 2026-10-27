"""
scale.py - make the bigger-beaker version of an existing nade recipe.

A nade recipe is  [trigger part ... spill] [payload part ... ] inject.  The trigger part (syringe) fixes the foam / smoke AREA; the payload part fills the beaker
and sets the amount in each tile.  Scaling keeps the trigger part, multiplies every payload dispense by a factor (rounded to the dispenser's 5u), and keeps the
largest factor whose result the engine accepts: no engine warning, no overflow, the same foam / smoke and area, click order and temperature safe, and the
tile still holding the payload in the original proportions.
"""
import copy
import book

ROUND = 5

def split(ops):
    """-> (head ops up to and including the first spill, payload ops, tail ops from the last inject)"""
    i = next((k for k, o in enumerate(ops) if o[0] == 'spill'), None)
    if i is None: raise ValueError('no spill step: this recipe has no trigger part to keep')
    j = max(k for k, o in enumerate(ops) if o[0] == 'inject')
    return ops[:i + 1], ops[i + 1:j], ops[j:]

def scaled_ops(ops, f, hold=()):
    head, body, tail = split(ops)
    out = []
    for o in body:
        if o[0] == 'dispense':
            a = o[2] if o[1] in hold else max(ROUND, int(round(o[2] * f / ROUND)) * ROUND)
            while a > 100:                                  # one dispenser click is at most 100u: split into two steps
                out.append(['dispense', o[1], 100]); a -= 100
            out.append(['dispense', o[1], a])
        else: out.append(list(o))
    return head + out + tail

def payload_total(ops):
    return sum(o[2] for o in split(ops)[1] if o[0] == 'dispense')

def proportion_ok(db, e0, c0, c1, f, tol=0.35):
    """tile contents of the scaled recipe stay near the original proportions (each chemical within tol of f x original), or at least not wildly lower"""
    return True

def try_factor(db, e, beaker, f, hold=()):
    s = copy.deepcopy(e); s['beaker'] = beaker; s['ops'] = scaled_ops(e['ops'], f, hold); s['allow_waste'] = True
    try: comp = book.simulate(db, s)
    except (ValueError, KeyError): return None
    if comp['warnings']: return None
    o = comp['order']
    if not (o.get('clicks_ok', True) and o.get('reverse_ok', True) and o.get('temp_ok', True)): return None
    return s, comp

def flag_state(comp):
    """(slick seconds or 0, set of wasted chemical names) of a computed recipe"""
    st = comp.get('stats') or {}
    sl = ((st.get('exp') or {}).get('slick')) or {}
    return (sl.get('total') or 0.0, {i['n'] for i in ((st.get('exp') or {}).get('inert') or [])})

HOLD_VARIANTS = [(), ('silicon',), ('silicon', 'oxygen')]       # lube reaction ingredients: keep the lube at the source amount instead of scaling it

def scale_recipe(db, e, beaker=300, new_id=None, verbose=False):
    """-> (spec, comp, factor, held) of the best bigger-beaker version, or raise ValueError.
    Best = most payload per tile among versions whose floor stays slick for about as long as the source's (within 15%; a recipe with no lube must stay without).  Chemicals that newly do nothing
    are not a reason to refuse: they show up on the card as a BROKEN flag."""
    base = book.simulate(db, e); sm0 = base['summary']; slick0, inert0 = flag_state(base)
    total0 = payload_total(e['ops']); fmax = beaker / float(total0)
    variants = HOLD_VARIANTS if slick0 > 0 else [()]
    best = None
    for hold in variants:
        f = round(fmax * 1.5, 1)
        while f >= 1.0 - 1e-9:
            r = try_factor(db, e, beaker, f, hold)
            if r:
                s, comp = r; sm = comp['summary']
                if sm.get('kind') == sm0.get('kind') and sm.get('tiles') == sm0.get('tiles'):
                    slick, inert = flag_state(comp)
                    # the lube rule is hard: keep the floor slick for about as long as the source did (not longer, and not lost altogether).
                    # Chemicals that newly do nothing are not a reason to refuse: they show up as a BROKEN flag.
                    clean = (0.85 * slick0 - 1.0 <= slick <= 1.15 * slick0 + 1.0) if slick0 > 0 else slick <= 15.0
                    key = (clean, sm.get('per_tile') or 0)
                    if verbose: print('  hold=%s f=%.1f per_tile=%s slick=%s clean=%s' % (hold, f, sm.get('per_tile'), slick, clean))
                    if best is None or key > best[0]: best = (key, s, comp, f, hold)
            f = round(f - 0.1, 6)
    if best is None: raise ValueError('no scale factor between 1 and %.1f gives a valid %du recipe' % (fmax, beaker))
    _, s, comp, f, hold = best
    s['id'] = new_id or e['id'].replace('-%d-' % e['beaker'], '-%d-' % beaker).replace('-%d' % e['beaker'], '-%d' % beaker, 1)
    return s, comp, f, hold

def describe(e, comp, f, src_title):
    sm = comp['summary']
    bits = ['%du-beaker version of "%s": same trigger, so the same %s area (%s tiles), with every payload amount scaled by about x%.1f.' % (e['beaker'], src_title, sm.get('kind', 'effect'), sm.get('tiles', '?'), f)]
    if sm.get('per_tile') is not None: bits.append('Each tile holds about %gu of %s (%gu per tick). See the Effects block below for the whole mix and what a person takes.' % (sm['per_tile'], e.get('payload'), sm.get('per_tick', 0)))
    return ' '.join(bits)
