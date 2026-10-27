"""
payload.py - build a foam / smoke recipe whose payload is made from EXACT amounts (stoich.py), so no ingredient or intermediate is left over to ride into the cloud.

  ops_for(db, kind, draw, products, batch)   -> the whole procedure: trigger, payload blocks, the trigger's second ingredient(s), inject
  build(db, beaker, syringe, kind, draw, products, payload, ...)  -> (spec, comp, problems)   tries batch plans until the engine accepts one

products = [(reagent name, units made), ...] in the order they are built.  Units must be exact amounts (stoich.quantum multiples).
A product built from far more raw ingredient than it makes (chloral hydrate: 5 to 1) or made in a large amount can overflow the beaker while it is being
built; the batch plan then builds it in several rounds.
"""
import stoich, book, hellfoam

def trigger(kind, draw):
    if kind == 'smoke':
        return [('dispense', 'phosphorus', draw), ('draw', draw), ('spill',)]
    return hellfoam.trigger_ops(draw)

def closer(kind, draw):
    """what goes in after the payload: smoke powder's potassium then sugar (potassium and water explode, so never before the payload is done); foam's water"""
    if kind == 'smoke':
        return [('dispense', 'potassium', draw), ('dispense', 'sugar', draw), ('inject',)]
    return [('dispense', 'water', draw), ('inject',)]

def ops_for(db, kind, draw, products, batch=None):
    av = set(db.dispensers[1]); ops = list(trigger(kind, draw)); hot = False
    for name, amt in products:
        p = db.find_reagent(name)
        bs = (batch or {}).get(name) or amt; left = amt
        while left > 0:
            part = min(bs, left)
            o = stoich.ops(db, av, p, part)
            if o is None: raise ValueError('%s %du is not an exact amount' % (name, part))
            ops += o; left -= part
        pl = stoich.plan(db, av, p, amt)
        if pl and pl['heat']: ops.append(('heat', int(pl['heat']) + 20))
    return ops + closer(kind, draw)

def batch_plans(db, products):
    """everything at once first, then each product on its own in rounds of decreasing size"""
    out = [None]
    for name, amt in products:
        q = stoich.quantum(db, set(db.dispensers[1]), db.find_reagent(name))
        for bs in sorted(range(q, amt, q), reverse=True): out.append({name: bs})
    return out

def problems(comp, slip=False):
    bad = []
    if comp['warnings']: bad.append('warnings: %s' % comp['warnings'][:2])
    o = comp['order']
    if not (o.get('clicks_ok', True) and o.get('reverse_ok', True) and o.get('temp_ok', True)): bad.append('order or temperature sensitive')
    st = comp.get('stats') or {}
    if st.get('broken'): bad.append('wasted: %s' % [(i['n'], i['u']) for i in st['exp']['inert']])
    sl = (st.get('exp') or {}).get('slick')
    if sl and sl['over'] and not slip: bad.append('slick %s s' % sl['total'])
    return bad

def build(db, beaker, syringe, kind, draw, products, payload, base=None, **spec_kw):
    """-> (spec, comp, problems).  base = a recipe dict to copy the text fields from."""
    last = None
    for batch in batch_plans(db, products):
        ops = ops_for(db, kind, draw, products, batch)
        spec = dict(base or {}); spec.update(spec_kw)
        spec.update(beaker=beaker, syringe=syringe, ops=[list(o) for o in ops], payload=payload)
        spec.pop('allow_waste', None); spec.pop('scaled_from', None)
        try: comp = book.simulate(db, spec)
        except ValueError as e: last = (spec, None, [str(e)]); continue
        bad = problems(comp)
        last = (spec, comp, bad)
        if not bad: return last
    return last
