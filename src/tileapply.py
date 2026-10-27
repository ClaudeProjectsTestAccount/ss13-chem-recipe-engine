"""
tileapply.py - how much of each chemical a foam or smoke puts on ONE floor tile, and what that does to the floor.

The game exposes the tile every foam / smoke tick:  amount in that exposure = (units of the chemical in the tile) x fraction.
Floor effects (reagent.expose_turf) test THAT per-exposure amount (lube needs 1u or more in one exposure, thermite 1u, radium glow 3u ...), not the tile total.
Everything that needs the foam / smoke size, the exposure fraction, the number of exposures or the per-tile amounts goes through here.

  plan(kind, tiles)                 -> timing: dt, life, exposures, fraction (share of the tile contents per exposure)
  per_tile(kind, tiles, tile)       -> per chemical: per exposure, total over the life
  turf_effects(path)                -> floor effects of a chemical (data/turf_effects.json, parents included)
  evaluate(path, per, n, ...)       -> does the floor effect happen at that amount, and with what numbers
  tile_report(kind, tiles, tile)    -> everything above for a whole tile mix, plus which chemicals do nothing on the floor
"""
import os, json

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(os.path.dirname(HERE), 'data')

FOAM_DT, FOAM_LIFE, FOAM_MIN_DIL = 0.2, 8.0, 25.0      # fluids.dm SSfoam wait 0.2 s; foam lifetime 8 s; MINIMUM_FOAM_DILUTION = DIAMOND_AREA(3) = 25
SMOKE_DT, SMOKE_LIFE = 2.0, 20.0                       # SSsmoke wait 2 s; chem smoke lifetime 20 s
SMOKE_TURF_EXPOSURES = 9                               # process ticks that touch the turf (the arrival breath only breathes the mob)
WET_COEFF, WET_RATIO_DS = 2.0, 15.0                    # wet_floors subsystem: temperature_coeff 2, time_ratio 1.5 s
T0C = 273.15

_fx = None
def _load():
    global _fx
    if _fx is None:
        with open(os.path.join(DATA, 'turf_effects.json')) as fh: _fx = {k: v for k, v in json.load(fh).items() if not k.startswith('_')}
    return _fx

def foam_fraction(tiles):
    """share of a foam tile's contents exposed per foam tick:  (dt * 25) / (lifetime * max(25, area))"""
    return FOAM_DT * FOAM_MIN_DIL / (FOAM_LIFE * max(FOAM_MIN_DIL, float(tiles)))

def plan(kind, tiles):
    kind = 'foam' if kind == 'foam' else 'smoke'
    if kind == 'foam':
        return dict(kind=kind, tiles=tiles, dt=FOAM_DT, life=FOAM_LIFE, exposures=int(round(FOAM_LIFE / FOAM_DT)), fraction=foam_fraction(tiles), mob_exposures=int(round(FOAM_LIFE / FOAM_DT)))
    return dict(kind=kind, tiles=tiles, dt=SMOKE_DT, life=SMOKE_LIFE, exposures=SMOKE_TURF_EXPOSURES, fraction=SMOKE_DT / SMOKE_LIFE, mob_exposures=SMOKE_TURF_EXPOSURES + 1)

def per_tile(kind, tiles, tile):
    """-> list of dict(path, tile, per_exposure, exposures, total) sorted by amount"""
    pl = plan(kind, tiles)
    return [dict(path=p, tile=u, per_exposure=u * pl['fraction'], exposures=pl['exposures'], total=u * pl['fraction'] * pl['exposures']) for p, u in sorted(tile.items(), key=lambda kv: -kv[1])]

def per_exposure(kind, tiles, units):
    return units * plan(kind, tiles)['fraction']

def units_needed(kind, tiles, per_exposure_target):
    """units of a chemical each tile must hold so that ONE exposure carries `per_exposure_target`"""
    return per_exposure_target / plan(kind, tiles)['fraction']

# ---------------------------------------------------------------- floor effects
def turf_effects(path):
    """effects of a reagent path on the floor, parents first (each proc in the game calls its parent first); a 'replace' entry drops the parents' effects"""
    fx = _load(); out = []
    parts = path.strip('/').split('/')
    for i in range(2, len(parts) + 1):
        ent = fx.get('/' + '/'.join(parts[:i]))
        if ent is None: continue
        if isinstance(ent, dict): lst = ent['effects']; out = [] if ent.get('replace') else out
        else: lst = ent
        out = out + lst
    return out

def wet_rate(air_k=293.15):
    """wet-time seconds lost per real second: decrease(ds) = ((T - 273.15) / 2) x (elapsed ds / 15); 0 at or below freezing (ice would form), everything dries above 100 C"""
    if air_k >= T0C + 100: return float('inf')
    return max(0.0, (air_k - T0C) / WET_COEFF / WET_RATIO_DS)

def evaluate(path, per_exp, exposures, dt=0.2, air_k=293.15, effect=None):
    """for each floor effect of the chemical: dict(effect, fires, short=units missing, numbers).  per_exp = units of the chemical in one exposure"""
    res = []
    for ef in turf_effects(path):
        thr = ef.get('thr')
        fires = per_exp > 1e-9 and (thr is None or per_exp >= thr - 1e-9)
        r = dict(id=ef['id'], label=ef['label'], tip=ef['tip'], thr=thr, fires=fires, per_exposure=per_exp, model=ef.get('model'))
        if fires and ef.get('model') == 'wet':
            add = min(per_exp * ef['per_u'], ef['cap_add_s']); t = ef['min_s']; rate = wet_rate(air_k)
            for i in range(1, exposures):
                t = max(ef['min_s'], min(300.0, t - rate * dt + add))     # clamp(time + add, min, max) after the decay of dt
            r.update(add_s=add, wet_left_s=t, slick_for_s=(t / rate if rate and rate != float('inf') else (0.0 if rate else float('inf'))), air_k=air_k)
        elif fires and ef.get('model') == 'accum':
            tot = per_exp * exposures
            r.update(total=tot, enough=tot >= ef['need'], enough_rwall=tot >= ef['need_rwall'], need=ef['need'], need_rwall=ef['need_rwall'])
        elif fires and ef.get('model') == 'dry':
            r.update(dry_s=per_exp * ef['per_u'])
        res.append(r)
    return res

def tile_report(kind, tiles, tile, air_k=293.15):
    """floor view of a whole tile mix"""
    pl = plan(kind, tiles); rows = []
    for row in per_tile(kind, tiles, tile):
        ev = evaluate(row['path'], row['per_exposure'], pl['exposures'], pl['dt'], air_k)
        row['effects'] = ev
        row['floor_active'] = any(x['fires'] for x in ev)
        rows.append(row)
    return dict(plan=pl, rows=rows)


# ---------------------------------------------------------------- slippery floor: how long does the tile stay slick
_pol = None
def policy():
    global _pol
    if _pol is None:
        with open(os.path.join(DATA, 'tile_policy.json')) as fh: _pol = {k: v for k, v in json.load(fh).items() if not k.startswith('_')}
    return _pol

MAX_WET_S = 300.0                                  # MAXIMUM_WET_TIME 5 minutes

def _wet_effects(path):
    return [e for e in turf_effects(path) if e.get('model') in ('wet', 'dry')]

def slick_sim(kind, tiles, tile, air_k=293.15):
    """Play the wet_floor component through every exposure of the foam / smoke, reagents in the order they sit in the tile.
    Per exposure: each wet chemical sets the timer of its wet type to the minimum (first time) or to clamp(timer + added, minimum, 5 min);
    a drying chemical takes 10 s per unit off every wet type (and the type is gone at 0).  Between exposures the timers drain at wet_rate(air).
    -> dict(total_s = seconds slick counted from the first exposure, after_s = slick time left after the last exposure, left = {type: s}, kinds = [...])"""
    pl = plan(kind, tiles); rate = wet_rate(air_k); times = {}; kinds = set(); end = 0.0
    for i in range(pl['exposures']):
        if i and times:
            for k in list(times):
                times[k] = times[k] - (rate * pl['dt'] if rate != float('inf') else 1e9)
                if times[k] <= 0: del times[k]
        for p, u in tile.items():
            per = u * pl['fraction']
            if per <= 1e-9: continue
            for ef in _wet_effects(p):
                thr = ef.get('thr')
                if thr is not None and per < thr - 1e-9: continue
                if ef['model'] == 'wet':
                    k = ef['kind']; kinds.add(k)
                    add = min(per * ef['per_u'], ef['cap_add_s'])
                    times[k] = max(ef['min_s'], min(MAX_WET_S, times[k] + add)) if k in times else min(ef['min_s'], MAX_WET_S)
                else:
                    for k in list(times):
                        times[k] -= per * ef['per_u']
                        if times[k] <= 0: del times[k]
        if times:                                   # slick from this exposure until the timer runs out or the next exposure
            run = max(times.values()) / rate if rate not in (0, float('inf')) else (float('inf') if rate == 0 else 0.0)
            end = i * pl['dt'] + (min(run, pl['dt']) if i < pl['exposures'] - 1 else run)
    left = max(times.values()) if times else 0.0
    after = 0.0 if not times else (float('inf') if rate == 0 else (0.0 if rate == float('inf') else left / rate))
    first = 0.0 if kinds else None
    total = end if kinds else 0.0
    return dict(kinds=sorted(kinds), left=dict(times), wet_left_s=left, after_s=after, total_s=total, exposures=pl['exposures'], dt=pl['dt'], life_s=(pl['exposures'] - 1) * pl['dt'], air_k=air_k)

def _scaled(tile, path, units):
    t = dict(tile); t[path] = units; return t

def slick_report(kind, tiles, tile, air_k=293.15, target_s=None):
    """Slick-floor numbers for a foam / smoke mix, or None when nothing in it makes the floor slippery.
    Per slippery chemical: units per tile now, units per tile at its threshold (the minimum that works at all), the extra over that, and what that amount does alone;
    for the whole mix: total slick time, the shortest it could possibly be, the largest amount that would meet the target, and a drying-agent fix."""
    target = policy()['slick_max_s'] if target_s is None else target_s
    pl = plan(kind, tiles); sim = slick_sim(kind, tiles, tile, air_k)
    if not sim['kinds']: return None
    chems = []
    for p, u in tile.items():
        for ef in _wet_effects(p):
            if ef['model'] != 'wet': continue
            per = u * pl['fraction']; thr = ef.get('thr') or 0.0
            thr_tile = thr / pl['fraction'] if thr else 0.0
            solo = slick_sim(kind, tiles, {p: u}, air_k)
            at_thr = slick_sim(kind, tiles, {p: max(thr_tile, 1e-6) * (1 + 1e-9)}, air_k) if thr else solo
            lo = at_thr['total_s']
            # largest tile amount of this chemical that still meets the target (binary search); None when even the threshold amount is too long
            best = None
            if lo <= target:
                a, b = max(thr_tile, 1e-6), max(u, thr_tile) * 4 + 10
                for _ in range(40):
                    m = (a + b) / 2
                    if slick_sim(kind, tiles, _scaled(tile, p, m), air_k)['total_s'] <= target: a = m
                    else: b = m
                best = a
            chems.append(dict(path=p, label=ef['label'], units=u, per_exposure=per, thr=thr, thr_tile=thr_tile, extra_tile=u - thr_tile, fires=(per >= thr - 1e-9),
                              add_s=min(per * ef['per_u'], ef['cap_add_s']), cap_add_s=ef['cap_add_s'], capped=per * ef['per_u'] > ef['cap_add_s'], min_wet_s=ef['min_s'], solo_total_s=solo['total_s'],
                              threshold_total_s=lo, max_tile_u=best))
    # drying agent fix: smallest tile amount of drying agent (appended after everything, so it acts last in each exposure) that brings the total under the target
    fix = None
    dry_path = '/datum/reagent/drying_agent'
    if sim['total_s'] > target:
        a, b = 0.0, 400.0
        if slick_sim(kind, tiles, _scaled(tile, dry_path, b), air_k)['total_s'] <= target:
            for _ in range(40):
                m = (a + b) / 2
                if slick_sim(kind, tiles, _scaled(tile, dry_path, m), air_k)['total_s'] <= target: b = m
                else: a = m
            fix = b
    return dict(sim=sim, target_s=target, over=sim['total_s'] > target + 1e-9, chems=chems, shortest_s=min([c['threshold_total_s'] for c in chems] or [0]),
                dry_fix_tile_u=fix, rate=wet_rate(air_k), min_possible_note=min_note(kind, tiles, air_k))

def min_note(kind, tiles, air_k):
    """the shortest slick time ANY lube can give in this size of foam / smoke (just over its 1u threshold)"""
    pl = plan(kind, tiles)
    return slick_sim(kind, tiles, {'/datum/reagent/lube': 1.0 / pl['fraction'] * 1.0000001}, air_k)['total_s']
