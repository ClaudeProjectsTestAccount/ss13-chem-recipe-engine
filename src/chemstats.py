"""
chemstats.py - what a chemical (or a mix of chemicals) does to a person, from data/chem_stats.json (game code, src/effects.py) plus
data/chem_curated.json (hand-written meaning: severity of overdoses, names + tooltips for special effects, contact effects).

Units: one Life tick = 2 s.  Damage/healing numbers are per tick, NEGATIVE = healing, positive = damage.  A chemical's per-tick effect does not depend on how
much of it is in the blood (only on it being there), so a mix does the SUM of what each member does; amounts decide how long each lasts
(1u lasts 1 / (2 * metabolization_rate) ticks) and when its overdose starts.
"""
import os, json, math

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(os.path.dirname(HERE), 'data')
KINDS = ('brute', 'burn', 'tox', 'oxy', 'clone', 'stamina')
TICK_S = 2.0

_stats = None; _cur = None
def stats():
    global _stats
    if _stats is None:
        with open(os.path.join(DATA, 'chem_stats.json')) as fh: _stats = json.load(fh)['reagents']
    return _stats
def curated():
    global _cur
    if _cur is None:
        try:
            with open(os.path.join(DATA, 'chem_curated.json')) as fh: _cur = {k: v for k, v in json.load(fh).items() if not k.startswith('_')}
        except Exception: _cur = {}
    return _cur

# tag -> (label, class, tooltip).  class: buff | debuff | flavor (flavor is kept in the data but not shown as a chip)
TAG_INFO = {
    'sleep': ('Sedation', 'debuff', 'Puts the target to sleep: each trigger adds sleeping time. A sleeper cannot act until the timer ends or they are woken.'),
    'unconscious': ('Knockout', 'debuff', 'Knocks the target unconscious for a while.'),
    'paralyze': ('Paralysis', 'debuff', 'Paralyzes the target: no moving or acting while it lasts.'),
    'knockdown': ('Knockdown', 'debuff', 'Knocks the target to the floor for a while.'),
    'stun': ('Stun', 'debuff', 'Stuns the target: no moving or acting while it lasts.'),
    'stun-recovery': ('Stun recovery', 'buff', 'Shortens stuns, knockdowns and paralysis already on the target (gets them back on their feet sooner).'),
    'drowsy': ('Drowsy', 'debuff', 'Builds drowsiness: the screen dims and sleep comes quickly.'),
    'confusion': ('Confusion', 'debuff', 'Confuses the target: movement direction is randomised at times.'),
    'jitter': ('Jitters', 'debuff', 'Shaky hands and screen; harder to aim and to do fine work.'),
    'dizzy': ('Dizzy', 'debuff', 'Dizziness: the screen sways and walking drifts.'),
    'blur': ('Blurred vision', 'debuff', 'Blurs the target\'s eyesight.'),
    'blind': ('Blindness', 'debuff', 'Blinds the target for a while.'),
    'drugged': ('High', 'debuff', 'Drug visuals (colours shift) for a while.'),
    'hallucinate': ('Hallucinations', 'debuff', 'The target sees things that are not there.'),
    'disgust': ('Nausea', 'debuff', 'Builds disgust; past thresholds the target vomits.'),
    'vomit': ('Vomiting', 'debuff', 'Makes the target vomit.'),
    'temperature': ('Body temperature', 'debuff', 'Changes body temperature (sign in the detail).'),
    'fire-stacks': ('Fire stacks', 'debuff', 'Adds fire stacks: fuel on the target that burns for longer when lit.'),
    'ignite': ('Ignite', 'debuff', 'Sets the target on fire.'),
    'stutter': ('Stutter', 'debuff', 'Speech stutters.'), 'slur': ('Slurred speech', 'debuff', 'Speech slurs.'), 'mute': ('Mute', 'debuff', 'Cannot speak for a while.'),
    'heart-attack': ('Heart attack', 'debuff', 'Can stop the heart.'),
    'brain-trauma': ('Brain trauma', 'debuff', 'Can give the target a lasting brain trauma.'),
    'cures-trauma': ('Cures brain trauma', 'buff', 'Removes brain traumas.'),
    'cures-blindness': ('Cures blindness', 'buff', 'Fixes blindness.'), 'cures-nearsight': ('Cures nearsightedness', 'buff', 'Fixes nearsightedness.'), 'cures-husk': ('Cures husking', 'buff', 'Undoes husking.'),
    'speed': ('Speed change', 'debuff', 'Changes how fast the target moves.'),
    'unconscious_': ('', 'flavor', ''),
    'losebreath': ('Suffocation', 'debuff', 'Makes the target lose their breath: oxygen damage builds until they recover.'),
    'restores-breath': ('Breath restore', 'buff', 'Clears the lost-breath state (stops the choking).'),
    'radiation': ('Radiation', 'debuff', 'Irradiates the target.'),
    'gib': ('Gibs', 'debuff', 'Gibs the target.'), 'gibs': ('Gore', 'flavor', ''), 'dust': ('Dusting', 'debuff', 'Turns the target to dust.'),
    'removes-status': ('Removes status', 'buff', 'Removes a status effect from the target.'),
    'purges': ('Purge', 'buff', 'Removes other chemicals from the blood while it is active.'),
    'makes': ('Converts', 'flavor', ''), 'organ': ('Organ effect', 'flavor', ''),
    'status-effect': ('Status effect', 'debuff', 'Applies a game status effect (see the detail).'),
    'trait': ('Trait', 'buff', 'Grants a trait while in the blood (see the detail).'),
    'nutrition': ('Nutrition', 'flavor', ''), 'emote': ('Emotes', 'flavor', ''), 'mood': ('Mood', 'flavor', ''), 'hair': ('Hair', 'flavor', ''), 'stamina': ('Stamina', 'flavor', ''),
}
# organs: how much one point of organ damage matters (optional organs low), used for overdose severity only
ORGAN_WEIGHT = {'brain': 0.6, 'heart': 0.6, 'liver': 0.3, 'lungs': 0.3, 'kidneys': 0.2, 'stomach': 0.15, 'eyes': 0.1, 'ears': 0.05, 'tongue': 0.02, 'appendix': 0.0}
KIND_WEIGHT = {'brute': 1.0, 'burn': 1.0, 'tox': 1.0, 'oxy': 1.0, 'clone': 2.0, 'stamina': 0.25}
TAG_WEIGHT = {'sleep': 1.5, 'unconscious': 2.0, 'paralyze': 3.0, 'knockdown': 1.5, 'stun': 3.0, 'drowsy': 0.3, 'confusion': 0.3, 'jitter': 0.1, 'dizzy': 0.1, 'blur': 0.2, 'blind': 0.5,
              'drugged': 0.1, 'hallucinate': 0.2, 'disgust': 0.2, 'vomit': 0.4, 'losebreath': 1.0, 'heart-attack': 5.0, 'brain-trauma': 2.0, 'radiation': 0.5, 'gib': 20.0, 'dust': 20.0, 'ignite': 1.0,
              'fire-stacks': 0.5, 'temperature': 0.2, 'speed': 0.3, 'mute': 0.1}

def short(path): return path.replace('/datum/reagent/', '')

def _expect(e):
    """expected value of one conditional record per tick (probability applied)"""
    return e['amt'] * (e['prob'] if e.get('prob') is not None else 1.0)

def tick_effects(block):
    """block = stats()[p]['life' | 'od_process'] -> {'always': {kind: v}, 'crit': {kind: v}, 'sometimes': [(kind, v, cond)]}"""
    always = dict(block['flat']); crit = {}; some = []; timed = []
    for e in block['cond']:
        if 'cyc' in e or 'odp' in e or e.get('amt') is None:
            if e.get('cond') is None: timed.append(e); continue
        v = _expect(e) if e.get('amt') is not None else 0.0
        if e.get('cond') is None: always[e['kind']] = round(always.get(e['kind'], 0) + v, 4)
        elif 'crit' in e['cond']: crit[e['kind']] = round(crit.get(e['kind'], 0) + v, 4)
        else: some.append((e['kind'], round(v, 4), e['cond']))
    return {'always': always, 'crit': crit, 'sometimes': some, 'timed': timed}

def organ_effects(block):
    """{slot: expected per tick} (positive = damage, negative = heals), unconditional only; conditional ones listed apart"""
    out = {}; cond = []
    for e in block['organ']:
        v = _expect(e)
        if e.get('cond') is None: out[e['slot']] = round(out.get(e['slot'], 0) + v, 4)
        else: cond.append((e['slot'], round(v, 4), e['cond']))
    return out, cond

def tag_list(block):
    out = []
    for t in block['tags']:
        info = TAG_INFO.get(t['tag'])
        if not info or info[1] == 'flavor': continue
        out.append(dict(tag=t['tag'], label=info[0], cls=info[1], tip=info[2], detail=t.get('detail', ''), prob=t.get('prob'), cond=t.get('cond'), cyc=t.get('cyc'), odp=t.get('odp')))
    return out

def od_severity(p):
    """rough scale: ~ expected damage per tick while overdosed (2 brute per tick ~ 2.0); weights for organs and statuses are in the tables above"""
    c = curated().get(p, {})
    if 'od_severity' in c: return c['od_severity']
    st = stats().get(p)
    if not st or not st['od']: return None
    sev = 0.0
    for blk in (st['od_process'],):
        te = tick_effects(blk)
        for k, v in list(te['always'].items()) + [(k, v) for k, v, _ in te['sometimes']] + list(te['crit'].items()):
            if v > 0: sev += KIND_WEIGHT.get(k, 1.0) * v
        org, ocond = organ_effects(blk)
        for slot, v in list(org.items()) + [(s, v) for s, v, _ in ocond]:
            if v > 0: sev += ORGAN_WEIGHT.get(slot, 0.2) * v
        for t in blk['tags']:
            w = TAG_WEIGHT.get(t['tag'])
            if w: sev += w * (t['prob'] if t.get('prob') is not None else 1.0) * 0.25     # status hits are brief; a quarter weight per trigger
        for e in blk['dyn']:
            sev += 0.5
    for t in st['od_start']['tags']:
        w = TAG_WEIGHT.get(t['tag'])
        if w: sev += 0.1 * w
    return round(sev, 2)

COND_FIX = [('affected_mob.getBruteLoss()', 'brute damage'), ('affected_mob.getFireLoss()', 'burn damage'), ('affected_mob.getToxLoss()', 'toxin damage'), ('affected_mob.getOxyLoss()', 'oxygen damage'),
            ('affected_mob.health', 'health'), ('affected_mob.stat', 'state'), ('SOFT_CRIT', 'in soft crit'), ('CONSCIOUS', 'awake'), ('switch(state); ', ''), ('&&', 'and'), ('||', 'or'), ('else', 'otherwise')]
def cond_words(c):
    for a, b in COND_FIX: c = c.replace(a, b)
    return c.replace('  ', ' ').strip()

def profile(p):
    """everything about one chemical, ready to display"""
    st = stats().get(p)
    if st is None: return None
    c = curated().get(p, {})
    life = tick_effects(st['life']); org, ocond = organ_effects(st['life'])
    metab = st['metab'] or 0.2
    od = st['od']
    if od is not None and od > 1e9: od = None
    return dict(path=p, name=st['name'], od=od, metab=metab, tick_units=metab * TICK_S, ticks_per_unit=1.0 / (metab * TICK_S),
                tick=life, organ=org, organ_cond=ocond, tags=tag_list(st['life']) + tag_list(st['on_metabolize']),
                od_tick=tick_effects(st['od_process']), od_organ=organ_effects(st['od_process'])[0], od_tags=tag_list(st['od_process']) + tag_list(st['od_start']),
                od_sev=od_severity(p), od_note=c.get('od_note', ''), status=c.get('status', []), buffs=c.get('buffs', []), contact=c.get('contact'), dyn=[(e['kind'], e['expr']) for e in st['life']['dyn']],
                hooks=st['hooks'], cond=[(k, v, cond_words(c)) for k, v, c in life['sometimes']])

def analyze_mix(mix, names=None):
    """mix = {reagent path: units}.  Returns the per-chemical table and the totals of a dose of the whole mix.
    Overdose: a chemical at fraction f of the mix reaches its overdose threshold after  od / f  units of the mix are in the blood at once."""
    total = float(sum(mix.values()))
    rows = []
    net = {k: 0.0 for k in KINDS}; crit = {k: 0.0 for k in KINDS}; organ = {}; stat = {}; buffs = {}; totals = {k: 0.0 for k in KINDS}
    for p, u in sorted(mix.items(), key=lambda kv: -kv[1]):
        pr = profile(p)
        if pr is None: continue
        f = u / total
        row = dict(path=p, name=pr['name'], units=round(u, 2), frac=f, od=pr['od'], od_at=(pr['od'] / f) if pr['od'] else None, od_sev=pr['od_sev'], pr=pr)
        rows.append(row)
        dur = u * pr['ticks_per_unit']                  # ticks this much of the chemical lasts
        row['ticks'] = dur
        for k, v in pr['tick']['always'].items():
            net[k] = net.get(k, 0.0) + v; totals[k] = totals.get(k, 0.0) + v * dur
        for k, v in pr['tick']['crit'].items(): crit[k] = crit.get(k, 0.0) + v
        for s, v in pr['organ'].items(): organ.setdefault(s, []).append((pr['name'], v))
        for t in pr['tags']:
            stat.setdefault((t['label'], t['cls']), []).append((pr['name'], t))
        for b in pr['buffs'] + pr['status']:
            buffs.setdefault(b['name'], []).append((pr['name'], b))
    return dict(total=total, rows=rows, net=net, crit=crit, organ=organ, statuses=stat, curated=buffs, per_unit={k: totals[k] / total for k in totals}, totals=totals)

def fmt_num(v, plus=False):
    s = '%.2f' % v
    s = s.rstrip('0').rstrip('.') if '.' in s else s
    if s in ('-0', ''): s = '0'
    return ('+' + s if plus and v > 0 else s)


def timed_value(e, cycle, odp):
    """value of a time-gated record (cycle = ticks the chemical has been in the blood, odp = ticks overdosed) or 0 when it is outside its window"""
    lo, hi = e.get('cyc') or (0, 10 ** 9)
    if not (lo <= cycle <= hi): return 0.0
    lo, hi = e.get('odp') or (0, 10 ** 9)
    if not (lo <= odp <= hi): return 0.0
    if e.get('amt') is not None: v = e['amt']
    else:
        try: v = float(eval(e['cexpr'], {'__builtins__': {}}, dict(max=max, min=min, abs=abs, round=round, rand=lambda a, b: (a + b) / 2.0, current_cycle=cycle, overdose_progress=odp, volume=10)))
        except Exception: v = 0.0
    return v * (e['prob'] if e.get('prob') is not None else 1.0)

def tag_active(t, cycle, odp):
    lo, hi = t.get('cyc') or (0, 10 ** 9)
    if not (lo <= cycle <= hi): return False
    lo, hi = t.get('odp') or (0, 10 ** 9)
    return lo <= odp <= hi
