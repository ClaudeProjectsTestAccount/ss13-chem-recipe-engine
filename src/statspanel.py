"""
statspanel.py - the "Effects" block of a recipe card: the chemical mix (overdose amounts, net damage / healing per tick, status effects) and, for foam and
smoke, what a person standing in it actually absorbs under each kind of protection.  Pure data (JSON-safe); the page only draws it.
"""
import chemstats as cs
import exposure as ex

KIND_LABEL = {'brute': 'Brute', 'burn': 'Burn', 'tox': 'Toxin', 'oxy': 'Oxygen', 'clone': 'Clone', 'stamina': 'Stamina'}

def r2(x, n=2): return round(x, n)

def mix_block(db, mix, title):
    a = cs.analyze_mix(mix)
    rows = []
    for r in a['rows']:
        pr = r['pr']
        te = {k: v for k, v in pr['tick']['always'].items() if abs(v) > 1e-9}
        rows.append(dict(n=r['name'], u=r['units'], f=r2(100 * r['frac'], 1), od=r['od'], od_at=(r2(r['od_at'], 1) if r['od_at'] else None), sev=r['od_sev'],
                         dur=r2(r['ticks'] * cs.TICK_S, 0), tick=te, crit={k: v for k, v in pr['tick']['crit'].items() if abs(v) > 1e-9},
                         cond=[dict(k=k, v=r2(v), c=c) for k, v, c in pr['cond']][:6],
                         timed=[dict(k=e['kind'], v=r2(e['amt'] if e.get('amt') is not None else 0), lo=(e.get('cyc') or [0, 0])[0], hi=(e.get('cyc') or [0, 10 ** 6])[1]) for e in pr['tick']['timed'] if e.get('amt')][:3],
                         odnote=pr['od_note'],
                         odfx=dict(tick={k: v for k, v in pr['od_tick']['always'].items() if abs(v) > 1e-9}, organ=pr['od_organ'], tags=[t['label'] for t in pr['od_tags']][:5])))
    chips = []
    seen = set()
    for (label, cls), lst in a['statuses'].items():
        by = sorted({n for n, _ in lst}); t0 = lst[0][1]
        key = (label, tuple(by))
        if key in seen: continue
        seen.add(key)
        chips.append(dict(l=label, c=cls, tip=t0['tip'] + ('  Value in the code: %s.' % t0['detail'] if t0['detail'] not in ('', None) else ''), by=by))
    for name, lst in a['curated'].items():
        b0 = lst[0][1]
        chips.append(dict(l=name, c=b0.get('cls', 'buff'), tip=b0.get('tip', ''), by=sorted({n for n, _ in lst})))
    organ = []
    for slot, lst in a['organ'].items():
        tot = sum(v for _, v in lst)
        if tot < 0: organ.append(dict(slot=slot, rate=r2(tot, 2), by=sorted({n for n, _ in lst}), heal=True))
        elif tot > 0: organ.append(dict(slot=slot, rate=r2(tot, 2), by=sorted({n for n, _ in lst}), heal=False))
    return dict(title=title, total=r2(a['total'], 1), rows=rows, net={k: r2(v) for k, v in a['net'].items() if abs(v) > 1e-9}, crit={k: r2(v) for k, v in a['crit'].items() if abs(v) > 1e-9},
                per_unit={k: r2(v) for k, v in a['per_unit'].items() if abs(v) > 1e-9}, organ=organ, chips=chips)

RULES = {
 'foam': [
   'Foam spreads over up to the stated number of tiles and lasts about 8 s per tile. Heat above 475 K dissolves it early; every extra person standing in the same tile cuts that tile\'s life further.',
   'Each foam tick (every 0.2 s) EVERY chemical in the tile is exposed to everyone in the tile by VAPOR: 40 exposures over the 8 s.',
   'Each exposure is (tile units) x 0.2 x 25 / (8 x the larger of 25 and the foam area). Up to 25 tiles that is 2.5% of the tile contents per exposure (about 100% over 8 s); a bigger foam dilutes it in proportion.',
   'Blood gain per chemical per exposure = that amount x (1 - bio protection), rounded to 0.1u, and ONLY IF it comes to 0.5u or more. A chemical present in small amounts never gets in at all.',
   'Bio protection is the average over head, chest, both arms and both legs of the bio armour on that part (garments multiply). Gloves, boots and groin coverage count for nothing. Injection-proof / thick material does not matter here: only the bio armour number does.',
   'A full hardsuit / EVA suit (with helmet) or bio suit with hood stops 100% of the absorption; a suit without the helmet leaves 1/6 of the exposure.',
   'Contact effects (fire stacks, acid, mutation, washing, wetting) happen on every exposure whatever you wear. Fire stacks cap at 20. Fire armour only scales the burning damage afterwards.',
   'Foam does not need a working lung: it works through the skin. Borgs and AIs have no bloodstream, so nothing is absorbed, but contact effects still land.',
 ],
 'smoke': [
   'Chemical smoke covers up to the stated number of tiles through any open path (closed doors stop it) and lasts 20 s per tile.',
   'Every 2 s each person who is breathing in the smoke gets 10% of every chemical in the tile copied straight into the blood: 10 breaths (9 ticks plus one when it first reaches you) = about 100% of the tile contents. No armour roll and no minimum.',
   'You are NOT affected if: an internals tank is open (mask or helmet), you do not breathe (TRAIT_NOBREATH), or your mask, glasses or hat has the gas-smoke-blocking flag (gas masks, sec hailers, bio hoods, firefighter helmets...). Space helmets and hardsuits do not block it unless internals are on. Armour makes no difference.',
   'Each tick the smoke also TOUCHes everything in the tile with 10% of the contents: contact effects (fire stacks, acid, washing) work even on protected people, but nothing enters the blood that way.',
   'Smoke is not carried over to borgs or AIs (they are not carbon) but contact effects reach them.',
 ]}

def scenario_row(s, chem_names):
    num = s['num']; fx = s['contact']; b = s['blood']
    row = dict(id=s['sc']['id'], name=s['sc']['name'], note=s['sc']['note'], block=r2(100 * num['block'], 0), breathes=not num['smoke_block'], absorbed=r2(s['absorbed_total'], 1),
               per={chem_names.get(p, p): v for p, v in s['absorbed'].items() if v > 0}, fire_cover=r2(100 * num['fire_cover'], 0))
    row['fx'] = {k: r2(v) for k, v in dict(fire=fx['fire_stacks'], burn=fx['burn_flat'], brute=fx['brute_flat'], slip=fx['slip_s'], acid_brute=fx['acid'][0], acid_burn=fx['acid'][1], acid_borg=fx['acid_borg'], mutate=fx['mutate']).items() if abs(v) > 1e-9}
    if fx['ignite']: row['fx']['ignite'] = 1
    if fx['clean']: row['fx']['clean'] = 1
    if fx['extinguish']: row['fx']['extinguish'] = 1
    if b:
        row['blood'] = dict(totals={k: r2(v, 1) for k, v in b['totals'].items() if abs(v) > 1e-9}, organ={k: r2(v, 1) for k, v in b['organ'].items() if abs(v) > 1e-9},
                            peak={chem_names.get(p, p): r2(v, 1) for p, v in b['peak'].items()}, od={chem_names.get(p, p): t * 2 for p, t in b['od_first'].items()},
                            tags=[dict(l=k[0], c=k[1], by=sorted(v)) for k, v in b['tags'].items()], secs=b['duration_ticks'] * 2)
    return row

def exposure_block(db, x):
    """x = one foam / smoke entry from rig.sim.effects"""
    rep = ex.analyse(x['kind'], x['tile'], x['tiles'])
    names = {c['path']: c['name'] for c in rep['chems']}
    chems = [dict(n=c['name'], tile=r2(c['tile'], 1), per=r2(c['per_call'], 2), contact=c['contact'], pen=bool(c['pen'] & ex.VAPOR), od=cs.stats().get(c['path'], {}).get('od')) for c in rep['chems']]
    return dict(kind=rep['kind'], tiles=rep['tiles'], frac=r2(100 * rep['fraction'], 2), calls=rep['calls'], dt=rep['dt'], life=rep['life'], tile_total=r2(rep['tile_total'], 1),
                chems=chems, rules=RULES[rep['kind']], scenarios=[scenario_row(s, names) for s in rep['scenarios']])

def build(db, e, rig):
    """-> dict for the page, or None when there is nothing to show.  Foam / smoke: the tile mix plus the exposure table.
    Plain chemical recipes: only when the recipe lists a `mix` (name -> units) it is meant to be used as."""
    out = {}
    fx = [x for x in rig.sim.effects if x['kind'] in ('foam', 'smoke') and sum(x['tile'].values()) > 0.05]
    if fx:
        x = fx[0]
        out['mix'] = mix_block(db, x['tile'], 'What each tile of the %s carries (per tile, all at once)' % x['kind'])
        out['exp'] = exposure_block(db, x)
    elif e.get('mix'):
        mix = {}
        for n, u in e['mix'].items():
            p = db.find_reagent(n)
            if p is None: raise ValueError('mix: unknown chemical %r' % n)
            mix[p] = float(u)
        out['mix'] = mix_block(db, mix, 'What this mix does (%gu total)' % sum(mix.values()))
    return out or None

# ---------------------------------------------------------------- plain text (CLI, for the AI)
def _sg(v): return ('%+g' % round(v, 2)) if abs(v) > 1e-9 else '0'
def _net(o): return ', '.join('%s %s' % (KIND_LABEL[k], _sg(o[k])) for k in KIND_LABEL if abs(o.get(k, 0)) > 1e-9) or 'no damage or healing'

def mix_text(m):
    L = ['%s  (%gu)' % (m['title'], m['total'])]
    L.append('  %-26s %7s %6s  %-24s %5s  %s' % ('chemical', 'units', 'share', 'overdoses at (whole mix)', 'sev', 'per tick (neg = heals)'))
    for r in m['rows']:
        od = ('%gu (alone %gu)' % (r['od_at'], r['od'])) if r['od_at'] else 'no overdose'
        L.append('  %-26s %7g %5.1f%%  %-24s %5s  %s' % (r['n'], r['u'], r['f'], od, r['sev'] if r['sev'] is not None else '-', _net(r['tick'])))
        for c in r['cond']: L.append('      when %s: %s %s' % (c['c'], KIND_LABEL.get(c['k'], c['k']), _sg(c['v'])))
        for c in r['timed']: L.append('      ticks %g-%g in blood: %s %s' % (c['lo'], c['hi'], KIND_LABEL.get(c['k'], c['k']), _sg(c['v'])))
        if r['odnote']: L.append('      overdose: %s' % r['odnote'])
    L.append('  NET per 2 s tick: %s' % _net(m['net']))
    if m['crit']: L.append('  while in crit: %s' % _net(m['crit']))
    if m['organ']: L.append('  organs: ' + '; '.join('%s %s %s/tick (%s)' % ('heals' if o['heal'] else 'damages', o['slot'], _sg(o['rate']), ', '.join(o['by'])) for o in m['organ']))
    if m['chips']: L.append('  status: ' + '; '.join('%s [%s] (%s)' % (c['l'], c['c'], ', '.join(c['by'])) for c in m['chips']))
    return '\n'.join(L)

def exp_text(x):
    foam = x['kind'] == 'foam'
    L = ['%s: %d tiles, ~%g s, %g%% of the tile per %g s tick x %d = about %d%% of the tile over its life (tile holds %gu)' % (x['kind'].upper(), x['tiles'], x['life'], x['frac'], x['dt'], x['calls'], round(x['frac'] * x['calls']), x['tile_total'])]
    for c in x['chems']: L.append('  %-24s tile %6gu  per tick %5gu  whole life %6.1fu  blood:%s  %s' % (c['n'], c['tile'], c['per'], c['per'] * x['calls'], 'yes' if c['pen'] else 'no', c['contact'] or ''))
    L.append('  Rules:'); L += ['   - ' + r for r in x['rules']]
    for s in x['scenarios']:
        fx = s['fx']; bits = []
        if fx.get('fire'): bits.append('%g fire stacks' % fx['fire'])
        if fx.get('ignite'): bits.append('ignites')
        for k in ('burn', 'brute', 'slip'):
            if fx.get(k): bits.append('%s %g%s' % (k, fx[k], ' s' if k == 'slip' else ''))
        if fx.get('acid_brute') or fx.get('acid_burn'): bits.append('acid %g brute/%g burn' % (fx.get('acid_brute', 0), fx.get('acid_burn', 0)))
        b = s.get('blood')
        L.append('  [%s] %s | %s | absorbed %gu%s | contact: %s | blood: %s' % (s['name'], ('bio %g%% blocked' % s['block']) if foam else ('breathes' if s['breathes'] else 'BLOCKED'), s['note'], s['absorbed'],
                 (' (' + ', '.join('%gu %s' % (v, k) for k, v in s['per'].items()) + ')') if s['per'] else '', ', '.join(bits) or 'none',
                 (_net(b['totals']) + ('; ' + ', '.join(t['l'] for t in b['tags']) if b['tags'] else '')) if b else '-'))
    return '\n'.join(L)

def parse_mix(db, text):
    """'libital 30, mannitol 15' or 'libital=30;mannitol=15' -> {path: units}"""
    import re
    mix = {}
    for part in re.split(r'[;,]', text):
        part = part.strip()
        if not part: continue
        m = re.match(r'^(.*?)[\s=:x]*([0-9]+(?:\.[0-9]+)?)\s*u?$', part) or re.match(r'^([0-9]+(?:\.[0-9]+)?)\s*u?\s+(.*)$', part)
        if not m: raise ValueError('cannot read %r (use "name units, name units")' % part)
        a, b = m.group(1).strip(), m.group(2).strip()
        name, units = (a, b) if re.match(r'^[0-9.]+$', b) else (b, a)
        p = db.find_reagent(name)
        if p is None: raise ValueError('unknown chemical %r' % name)
        mix[p] = mix.get(p, 0) + float(units)
    return mix
