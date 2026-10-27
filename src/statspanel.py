"""
statspanel.py - the "Effects" block of a recipe card: the chemical mix (overdose amounts, net damage / healing per tick, status effects) and, for foam and
smoke, what a person standing in it actually absorbs under each kind of protection.  Pure data (JSON-safe); the page only draws it.
"""
import chemstats as cs
import exposure as ex
import tileapply as ta

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
   'FLOOR effects (slippery, thermite, glow, cleaning...) need a minimum amount of the chemical in ONE exposure, listed per chemical in the floor table. The tile contents multiply by the exposure share to get it.',
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
   'FLOOR effects (slippery, thermite, glow, cleaning...) need a minimum amount of the chemical in ONE exposure (10% of the tile per tick): see the floor table.',
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
    row['fx'] = {k: r2(v) for k, v in dict(fire=fx['fire_stacks'], burn=fx['burn_flat'], brute=fx['brute_flat'], acid_brute=fx['acid'][0], acid_burn=fx['acid'][1], acid_borg=fx['acid_borg'], mutate=fx['mutate']).items() if abs(v) > 1e-9}
    if fx['ignite']: row['fx']['ignite'] = 1
    if fx['clean']: row['fx']['clean'] = 1
    if fx['extinguish']: row['fx']['extinguish'] = 1
    if b:
        row['blood'] = dict(totals={k: r2(v, 1) for k, v in b['totals'].items() if abs(v) > 1e-9}, organ={k: r2(v, 1) for k, v in b['organ'].items() if abs(v) > 1e-9},
                            peak={chem_names.get(p, p): r2(v, 1) for p, v in b['peak'].items()}, od={chem_names.get(p, p): t * 2 for p, t in b['od_first'].items()},
                            tags=[dict(l=k[0], c=k[1], by=sorted(v)) for k, v in b['tags'].items()], secs=b['duration_ticks'] * 2)
    return row

def _effect_extra(ev):
    """one short sentence with the numbers of a floor effect that fires"""
    if ev.get('model') == 'wet' and ev['fires']:
        return 'adds %g s of wet time per exposure; see the slick-floor panel for how long the whole mix stays slick' % r2(ev['add_s'], 2)
    if ev.get('model') == 'accum' and ev['fires']:
        return 'coat adds up to %g u over the whole life: %s' % (r2(ev['total'], 1), 'enough to melt a floor or wall%s' % (' and a reinforced wall' if ev['enough_rwall'] else ' (not a reinforced wall: needs %g)' % ev['need_rwall']) if ev['enough'] else 'NOT enough: needs %g u in total' % ev['need'])
    if ev.get('model') == 'dry' and ev['fires']:
        return 'removes %g s of wet time per exposure' % r2(ev['dry_s'], 1)
    return ''

def floor_block(rep):
    """floor effects per chemical for a foam / smoke exposure report (tileapply numbers)"""
    fl = rep['floor']; pl = fl['plan']; rows = []
    for r in fl['rows']:
        effs = []
        for ev in r['effects']:
            e = dict(l=ev['label'], fires=ev['fires'], thr=ev['thr'], tip=ev['tip'], extra=_effect_extra(ev))
            if not ev['fires'] and ev['thr']: e['need_tile'] = r2(ev['thr'] / pl['fraction'], 1)
            effs.append(e)
        rows.append(dict(n=ex_name(r['path']), tile=r2(r['tile'], 1), per=r2(r['per_exposure'], 2), total=r2(r['total'], 1), effs=effs))
    return dict(rows=rows, exposures=pl['exposures'], frac=r2(100 * pl['fraction'], 2), per_s=r2(1.0 / pl['dt'], 1))

def ex_name(path): return cs.stats().get(path, {}).get('name') or path.split('/')[-1]

def _has_blood_effect(pr):
    if pr is None: return False
    t = pr['tick']
    return bool(any(abs(v) > 1e-9 for v in t['always'].values()) or t['crit'] or t['sometimes'] or t['timed'] or pr['organ'] or pr['tags'] or pr['buffs'] or pr['status']
                or any(abs(v) > 1e-9 for v in pr['od_tick']['always'].values()) or pr['od_organ'])

def inert_chems(rep):
    """chemicals in the tile that do nothing to anything: no floor effect, no contact effect on a person, nothing absorbed that has an effect in the blood"""
    out = []; bare = rep['scenarios'][0]; sc = bare['sc']
    floor = {r['path']: r for r in rep['floor']['rows']}
    sup = ta.supported({c['path']: c['tile'] for c in rep['chems']})
    for c in rep['chems']:
        p = c['path']; fr = floor[p]
        if p in sup: continue                       # needed to make something else in the tile (stabilizing agent for phlogiston, blood seed for carpet): not wasted
        if fr['floor_active']: continue
        methods = ex.VAPOR if rep['kind'] == 'foam' else (ex.TOUCH | ex.INGEST)
        cx = ex.contact(p, methods, c['per_call'], sc)
        if any(cx.get(k) for k in ('fire_stacks', 'ignite', 'burn_flat', 'brute_flat', 'clean', 'extinguish', 'mutate_p', 'acid_part', 'acid_borg')): continue
        if bare['absorbed'].get(p, 0) > 0 and _has_blood_effect(cs.profile(p)): continue
        unmet = [e for e in fr['effects'] if not e['fires'] and e['thr']]
        if unmet:
            e = unmet[0]
            why = '%s needs %g u in ONE exposure but each exposure carries only %.2g u (the tile would need %.0f u)' % (e['label'], e['thr'], c['per_call'], e['thr'] / rep['fraction'])
        elif bare['absorbed'].get(p, 0) <= 0 and c['pen'] & ex.VAPOR and rep['kind'] == 'foam':
            why = 'each exposure is %.2g u, under the 0.5 u minimum the skin absorbs, so none gets in; it has no floor effect' % c['per_call']
        elif not (c['pen'] & (ex.VAPOR if rep['kind'] == 'foam' else ex.INGEST)) and rep['kind'] == 'foam':
            why = 'does not pass through skin and has no floor or contact effect'
        else:
            why = 'no floor effect, no contact effect, and nothing it does once absorbed'
        out.append(dict(n=c['name'], u=r2(c['tile'], 1), why=why))
    return out

def _fin(v):
    return None if v is None or v == float('inf') else r2(v, 1)

def slick_block(sr):
    """JSON-safe slick-floor report (tileapply.slick_report)"""
    if sr is None: return None
    sim = sr['sim']
    return dict(total=_fin(sim['total_s']), after=_fin(sim['after_s']), life=_fin(sim['life_s']), left=_fin(sim['wet_left_s']), target=sr['target_s'], over=sr['over'], shortest=_fin(sr['shortest_s']),
                dry_fix=_fin(sr['dry_fix_tile_u']), rate=r2(sr['rate'], 3), air_k=round(sim['air_k']), kinds=sim['kinds'],
                chems=[dict(n=ex_name(c['path']), label=c['label'], u=r2(c['units'], 1), per=r2(c['per_exposure'], 2), thr=c['thr'], thr_tile=_fin(c['thr_tile']), extra=_fin(c['extra_tile']), fires=c['fires'],
                            add=r2(c['add_s'], 2), cap=c['cap_add_s'], capped=c['capped'], minwet=c['min_wet_s'], solo=_fin(c['solo_total_s']), at_thr=_fin(c['threshold_total_s']), max_u=_fin(c['max_tile_u'])) for c in sr['chems']])

def exposure_block(db, x, air_k=293.15):
    """x = one foam / smoke entry from rig.sim.effects"""
    rep = ex.analyse(x['kind'], x['tile'], x['tiles'], air_k=air_k)
    names = {c['path']: c['name'] for c in rep['chems']}
    chems = [dict(n=c['name'], tile=r2(c['tile'], 1), per=r2(c['per_call'], 2), contact=c['contact'], pen=bool(c['pen'] & ex.VAPOR), od=cs.stats().get(c['path'], {}).get('od')) for c in rep['chems']]
    sup = ta.supported(x['tile'])
    needed = [dict(n=ex_name(p), u=r2(x['tile'][p], 1), why=v['why'], for_=[ex_name(q) for q in v['for_']]) for p, v in sup.items()]
    return dict(slick=slick_block(ta.slick_report(rep['kind'], rep['tiles'], x['tile'], air_k)), floor=floor_block(rep), inert=inert_chems(rep), needed=needed, floor_safety=ta.floor_safety(rep['kind'], rep['tiles'], x['tile'], air_k), kind=rep['kind'], tiles=rep['tiles'], frac=r2(100 * rep['fraction'], 2), calls=rep['calls'], dt=rep['dt'], life=rep['life'], tile_total=r2(rep['tile_total'], 1),
                chems=chems, rules=RULES[rep['kind']], scenarios=[scenario_row(s, names) for s in rep['scenarios']])

def build(db, e, rig):
    """-> dict for the page, or None when there is nothing to show.  Foam / smoke: the tile mix plus the exposure table.
    Plain chemical recipes: only when the recipe lists a `mix` (name -> units) it is meant to be used as."""
    out = {}
    fx = [x for x in rig.sim.effects if x['kind'] in ('foam', 'smoke') and sum(x['tile'].values()) > 0.05 and x.get('type', 'foam') in ('foam', 'smoke')]    # metal / iron / smart foam: the foam itself is the effect, the tile chemicals are only its ingredients
    if fx:
        x = fx[0]
        out['mix'] = mix_block(db, x['tile'], 'What each tile of the %s carries (per tile, all at once)' % x['kind'])
        out['exp'] = exposure_block(db, x)
        out['broken'] = bool(out['exp']['inert'])
        sl = out['exp']['slick']
        out['flags'] = []
        if sl and sl['over']:
            out['flags'].append(dict(id='lube-long', ok=bool(e.get('lube_ok')), text='Floor stays slick about %g s (target %g s or less). %s' % (
                sl['total'], sl['target'], 'The code gives lube a minimum of %g s of wet time and adds 2 s per unit on EVERY exposure, so the shortest any lube can be in this %s is %g s.' % (max(c['minwet'] for c in sl['chems'] if 'lube' in c['label'].lower() or 'slick' in c['label'].lower()), x['kind'], sl['shortest'])
                + (' A drying agent mix of about %g u per tile (acting after the lube) would cut it under the target.' % sl['dry_fix'] if sl['dry_fix'] else ''))))
        for r in out['exp']['floor']['rows']:
            for e in r['effs']:
                if e['fires']: out['mix']['chips'].append(dict(l='Floor: ' + e['l'], c='floor', tip=e['tip'] + ((' ' + e['extra'] + '.') if e['extra'] else ''), by=[r['n']]))
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
    fl = x['floor']; L.append('  FLOOR (per exposure = tile x %g%%, %d exposures):' % (fl['frac'], fl['exposures']))
    for r in fl['rows']:
        L.append('   %-22s tile %6gu  per exposure %6gu  life %6gu  ' % (r['n'], r['tile'], r['per'], r['total']) + ('; '.join(('OK ' if e['fires'] else 'NO ') + e['l'] + ('' if e['fires'] else ' (needs %gu per exposure = %gu per tile)' % (e['thr'], e['need_tile'])) + ((' [' + e['extra'] + ']') if e['extra'] else '') for e in r['effs']) or 'nothing on the floor'))
    sl = x.get('slick')
    if sl:
        L.append('  SLICK FLOOR: slick about %s s from the first exposure (%s s of that after the last exposure, %s s of wet time stacked); target %g s -> %s; shortest possible here %s s; air %d K drains %s s of wet time per s' % (
            sl['total'], sl['after'], sl['left'], sl['target'], 'OVER' if sl['over'] else 'ok', sl['shortest'], sl['air_k'], sl['rate']))
        for c in sl['chems']:
            L.append('    %s: %gu per tile now, threshold %gu per tile (%gu per exposure), extra over threshold %s u per tile; adds %g s per exposure%s; alone %s s, at threshold %s s%s' % (
                c['n'], c['u'], c['thr_tile'], c['thr'], c['extra'], c['add'], ' (capped at %g)' % c['cap'] if c['capped'] else '', c['solo'], c['at_thr'], ('; largest amount that meets the target %s u per tile' % c['max_u']) if c['max_u'] else ''))
        if sl['dry_fix']: L.append('    drying agent fix: about %g u of drying agent per tile (placed after the lube in the tile) brings it under the target' % sl['dry_fix'])
    for i in x.get('needed') or []: L.append('  NEEDED but passive (not wasted): %s %gu per tile for %s (%s)' % (i['n'], i['u'], ', '.join(i['for_']), i['why']))
    fs = x.get('floor_safety')
    if fs: L.append('  FLOOR: ' + ('safe (nothing melts the tile)' if fs['safe'] else 'DESTROYED: ' + '; '.join(fs['reasons'])))
    if x['inert']: L.append('  BROKEN - wasted chemicals: ' + '; '.join('%s %gu (%s)' % (i['n'], i['u'], i['why']) for i in x['inert']))
    L.append('  Rules:'); L += ['   - ' + r for r in x['rules']]
    for s in x['scenarios']:
        fx = s['fx']; bits = []
        if fx.get('fire'): bits.append('%g fire stacks' % fx['fire'])
        if fx.get('ignite'): bits.append('ignites')
        for k in ('burn', 'brute'):
            if fx.get(k): bits.append('%s %g' % (k, fx[k]))
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
