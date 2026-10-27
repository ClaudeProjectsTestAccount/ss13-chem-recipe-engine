"""
effects.py - reads what each reagent DOES to a mob out of the game source (on_mob_life, overdose_process, on_mob_metabolize, expose_* hooks) and
writes data/chem_stats.json.  Run from a source checkout (MONKE_SRC or src/.cache/source):   python3 src/effects.py

Units: one Life tick = 2 s (seconds_per_tick = 2), REM = 0.5, so `adjustBruteLoss(-3 * REM * seconds_per_tick)` is -3 brute per tick.
The extractor is deliberately literal: every number comes from an expression in the source that evaluates with those constants; anything it
cannot evaluate (depends on current health, on another reagent, ...) is kept as text in `dyn`.  Curated meaning (severity, nicknames, tooltips)
lives in data/chem_curated.json and is merged on top by chemstats.py.
"""
import os, re, json, sys
import dmparse

REM = 0.5
SPT = 2.0
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(os.path.dirname(HERE), 'data', 'chem_stats.json')

DMG = {'adjustBruteLoss': 'brute', 'adjustFireLoss': 'burn', 'adjustToxLoss': 'tox', 'adjustOxyLoss': 'oxy', 'adjustCloneLoss': 'clone', 'adjustStaminaLoss': 'stamina'}
STATUS = {   # call -> tag
    'AdjustSleeping': 'sleep', 'Sleeping': 'sleep', 'SetSleeping': 'sleep', 'Paralyze': 'paralyze', 'AdjustParalyzed': 'paralyze', 'Knockdown': 'knockdown', 'AdjustKnockdown': 'knockdown',
    'Stun': 'stun', 'AdjustStun': 'stun', 'AdjustAllImmobility': 'stun-recovery', 'adjust_drowsiness': 'drowsy', 'set_drowsiness': 'drowsy', 'adjust_confusion': 'confusion', 'set_confusion': 'confusion',
    'set_confusion_if_lower': 'confusion', 'adjust_jitter': 'jitter', 'set_jitter_if_lower': 'jitter', 'adjust_dizzy': 'dizzy', 'set_dizzy_if_lower': 'dizzy', 'adjust_eye_blur': 'blur', 'set_eye_blur_if_lower': 'blur',
    'adjust_temp_blindness': 'blind', 'set_temp_blindness': 'blind', 'adjust_blindness': 'blind', 'set_drugginess': 'drugged', 'adjust_drugginess': 'drugged', 'adjust_hallucinations': 'hallucinate',
    'adjust_disgust': 'disgust', 'vomit': 'vomit', 'adjust_bodytemperature': 'temperature', 'adjust_fire_stacks': 'fire-stacks', 'adjust_nutrition': 'nutrition', 'adjust_stutter': 'stutter',
    'adjust_slurring': 'slur', 'set_slurring_if_lower': 'slur', 'adjust_slurring': 'slur', 'set_stutter_if_lower': 'stutter', 'adjust_silence': 'mute', 'set_silence': 'mute', 'adjust_dizzy': 'dizzy',
    'set_blindness': 'blind', 'adjust_blurriness': 'blur', 'emote': 'emote', 'add_mood_event': 'mood', 'ignite_mob': 'ignite', 'set_heartattack': 'heart-attack', 'gain_trauma': 'brain-trauma',
    'cure_trauma_type': 'cures-trauma', 'cure_all_traumas': 'cures-trauma', 'add_movespeed_modifier': 'speed', 'remove_movespeed_modifier': 'speed', 'apply_status_effect': 'status-effect',
    'remove_status_effect': 'removes-status', 'adjust_stamina_loss': 'stamina', 'AdjustUnconscious': 'unconscious', 'Unconscious': 'unconscious', 'adjust_radiation': 'radiation', 'adjust_organ_loss': 'organ',
    'become_blind': 'blind', 'cure_blind': 'cures-blindness', 'cure_nearsighted': 'cures-nearsight', 'cure_husk': 'cures-husk', 'adjust_hair_loss': 'hair', 'spawn_gibs': 'gibs', 'gib': 'gib', 'dust': 'dust',
}
KEEP_NAMED = ('losebreath', 'heal_bodypart_damage', 'heal_overall_damage', 'adjustOrganLoss', 'stamina.adjust', 'remove_reagent', 'add_reagent', 'ADD_TRAIT', 'REMOVE_TRAIT', 'adjust_wound', 'heal_wound', 'cure_')

def split_args(s):
    out, depth, cur = [], 0, ''
    for c in s:
        if c in '([{': depth += 1
        elif c in ')]}': depth -= 1
        if c == ',' and depth == 0: out.append(cur.strip()); cur = ''
        else: cur += c
    if cur.strip(): out.append(cur.strip())
    return out

def call_args(text, name):
    """argument list of the first `name(` call in text (balanced), or None"""
    i = text.find(name + '(')
    if i < 0: return None
    j = i + len(name) + 1; depth = 1; k = j
    while k < len(text) and depth:
        if text[k] == '(': depth += 1
        elif text[k] == ')': depth -= 1
        k += 1
    return split_args(text[j:k - 1])

ALLOWED_FN = {'max': max, 'min': min, 'round': lambda x, q=1: round(x / q) * q, 'abs': abs, 'rand': lambda a, b: (a + b) / 2.0}   # rand() = its mean
DYNVARS = ('current_cycle', 'overdose_progress', 'volume')
CTX = {'defs': None, 'path': None}

def num(expr, env=None):
    """evaluate a DM numeric expression with REM / seconds_per_tick / purity = 1; None if it depends on anything else"""
    if expr is None: return None
    e = expr.strip()
    e = re.sub(r'normalise_creation_purity\(\)', '1', e)
    e = re.sub(r'\bREM\b', repr(REM), e)
    e = re.sub(r'\bseconds_per_tick\b', repr(SPT), e)
    e = re.sub(r'\bSPT\b', repr(SPT), e)
    e = re.sub(r'\bTRUE\b', '1', e); e = re.sub(r'\bFALSE\b', '0', e)
    e = re.sub(r'\bSECONDS\b', '*10', e); e = re.sub(r'\bMINUTES\b', '*600', e)
    e = re.sub(r'\bREAGENTS_METABOLISM\b', '0.2', e)
    for k in set(re.findall(r'[A-Za-z_]\w*', e)):
        if CTX['defs'] is not None and k not in dmparse.MACROS and k.islower() and k not in DYNVARS:
            v, _ = dmparse.resolve_chain(CTX['defs'], CTX['path'], k)       # reagent variable such as toxpwr
            if v is not None:
                vv = num(v)
                if vv is not None: e = re.sub(r'\b%s\b' % k, '(%r)' % vv, e)
        if k in dmparse.MACROS: e = re.sub(r'\b%s\b' % k, '(%r)' % dmparse.MACROS[k], e)
    if any(w not in ALLOWED_FN for w in re.findall(r'[A-Za-z_]\w*', e)) or not re.fullmatch(r'[0-9A-Za-z_.,+\-*/() ]+', e): return None
    try: return float(eval(e, {'__builtins__': {}}, ALLOWED_FN))
    except Exception: return None

def cexpr(expr):
    """like num() but leaves current_cycle / overdose_progress / volume as names: a python expression string to evaluate per tick, or None"""
    if expr is None or not any(re.search(r'\b%s\b' % v, expr) for v in DYNVARS): return None
    e = expr.strip()
    e = re.sub(r'normalise_creation_purity\(\)', '1', e); e = re.sub(r'\bREM\b', repr(REM), e); e = re.sub(r'\bseconds_per_tick\b', repr(SPT), e)
    for k in set(re.findall(r'[A-Za-z_]\w*', e)):
        if k in DYNVARS or k in ALLOWED_FN: continue
        if k in dmparse.MACROS: e = re.sub(r'\b%s\b' % k, '(%r)' % dmparse.MACROS[k], e); continue
        if CTX['defs'] is not None and k.islower():
            v, _ = dmparse.resolve_chain(CTX['defs'], CTX['path'], k)
            vv = num(v) if v is not None else None
            if vv is not None: e = re.sub(r'\b%s\b' % k, '(%r)' % vv, e); continue
        return None
    if not re.fullmatch(r'[0-9A-Za-z_.,+\-*/() ]+', e): return None
    try: eval(e, {'__builtins__': {}}, dict(ALLOWED_FN, current_cycle=10, overdose_progress=10, volume=10))
    except Exception: return None
    return e

def prob_of(cond):
    """probability per tick from SPT_PROB(p, t) / prob(p); None when not a pure random gate"""
    m = re.fullmatch(r'(?:SPT_PROB|SPT_PROB_RATE)\((.+?),\s*(.+)\)', cond)
    if m:
        p = num(m.group(1)); t = num(m.group(2))
        if p is not None and t is not None: return round(1 - (1 - p / 100.0) ** t, 4)
    m = re.fullmatch(r'prob\((.+)\)', cond)
    if m:
        p = num(m.group(1))
        if p is not None: return round(p / 100.0, 4)
    return None

INF = 10 ** 6
def parse_range(txt):
    m = re.fullmatch(r'\s*([\d.]+)\s+to\s+([\d.]+|INFINITY)\s*', txt)
    if not m: return None
    return (float(m.group(1)), INF if m.group(2) == 'INFINITY' else float(m.group(2)))

def split_conds(conds):
    """conds (outer->inner) -> (text conditions that remain, cycle range, overdose-progress range, prob)"""
    text, cyc, odp = [], None, None
    prev = None
    for c in conds:
        c0 = c.strip()
        if prev in ('switch(current_cycle)', 'switch(overdose_progress)'):
            r = parse_range(c0)
            if r:
                if prev == 'switch(current_cycle)': cyc = r if cyc is None else (max(cyc[0], r[0]), min(cyc[1], r[1]))
                else: odp = r if odp is None else (max(odp[0], r[0]), min(odp[1], r[1]))
                prev = None; continue
        if c0 in ('switch(current_cycle)', 'switch(overdose_progress)'):
            prev = c0; continue
        prev = None
        m = re.fullmatch(r'current_cycle\s*(<=|>=|<|>|==)\s*([\d.]+)', c0)
        if m:
            op, n = m.group(1), float(m.group(2)); lo, hi = (cyc or (0, INF))
            if op == '<=': hi = min(hi, n)
            elif op == '<': hi = min(hi, n - 1)
            elif op == '>=': lo = max(lo, n)
            elif op == '>': lo = max(lo, n + 1)
            else: lo, hi = max(lo, n), min(hi, n)
            cyc = (lo, hi); continue
        c1 = c0
        for pat in (r'toxpwr\s*&&\s*', r'affected_mob\.health\s*>\s*health_required', r'affected_mob\.get(?:Brute|Tox|Fire|Oxy)Loss\(\)\s*&&\s*', r'^\s*&&\s*'):
            c1 = re.sub(pat, '', c1)
        c1 = c1.strip().strip('&').strip()
        if c1: text.append(c1)
    return text, cyc, odp

def cond_text(c):
    c = c.strip()
    reps = [(r'affected_mob\.health\s*<=?\s*affected_mob\.crit_threshold', 'in crit'), (r'affected_mob\.health\s*<=?\s*(\S+)', r'health <= \1'),
            (r'HAS_TRAIT\(affected_mob,\s*(\w+)\)', r'has \1'), (r'!HAS_TRAIT\(affected_mob,\s*(\w+)\)', r'lacks \1'),
            (r'holder\.has_reagent\((/datum/reagent/[\w/]+)(?:,\s*([\d.]+))?\)', r'has \1')]
    for a, b in reps: c = re.sub(a, b, c)
    return c

def body_events(lines):
    """walk a proc body keeping the if/else nesting; yields dict(kind, args, line, conds)"""
    stack = []         # (indent, cond text, is_else)
    last_if_at = {}
    ev = []
    for ind, text in lines:
        while stack and stack[-1][0] >= ind: stack.pop()
        m = re.match(r'(else if|if)\s*\(', text)
        inline = None
        if m:
            i0 = text.find('(', m.start()); depth = 0
            for k in range(i0, len(text)):
                if text[k] == '(': depth += 1
                elif text[k] == ')':
                    depth -= 1
                    if depth == 0: break
            cnd = text[i0 + 1:k]; rest = text[k + 1:].strip()
            if m.group(1) == 'else if': cnd = 'else, ' + cnd
            stack.append((ind, cnd, False))
            if rest: inline = rest
            else: continue
        elif text.startswith('else'):
            stack.append((ind, 'else', True))
            rest = text[4:].strip()
            if rest: inline = rest
            else: continue
        elif re.match(r'(switch|for|while)\s*\(', text):
            stack.append((ind, text, False)); continue
        stmt = inline if inline is not None else text
        conds = [c for _, c, _ in stack]
        if inline is not None and stack: stack = stack[:-1] + [stack[-1]]
        ev.append((stmt, conds))
    return ev

def eval_events(events):
    """turn statements into effect records"""
    dmg, organ, tags, dyn = [], [], [], []
    for stmt, conds in events:
        pr = None; rest = []
        for c in conds:
            p = prob_of(c)
            if p is not None: pr = p if pr is None else pr * p
            else: rest.append(c)
        text, cyc, odp = split_conds(rest)
        ctxt = [cond_text(c) for c in text]
        base = dict(cond='; '.join(ctxt) or None, prob=pr)
        if cyc: base['cyc'] = [cyc[0], cyc[1]]
        if odp: base['odp'] = [odp[0], odp[1]]
        for fn, kind in DMG.items():
            if fn + '(' in stmt:
                a = call_args(stmt, fn); v = num(a[0]) if a else None
                ce = cexpr(a[0]) if a and v is None else None
                if ce: dmg.append(dict(kind=kind, amt=None, cexpr=ce, **base))
                elif v is None: dyn.append(dict(kind=kind, expr=a[0] if a else '', **base))
                else: dmg.append(dict(kind=kind, amt=round(v, 3), **base))
        if 'stamina.adjust(' in stmt:
            a = call_args(stmt, 'stamina.adjust'); v = num(a[0]) if a else None
            if v is not None: dmg.append(dict(kind='stamina', amt=round(-v, 3), **base))      # stamina.adjust(-x) = x stamina damage
        for fn in ('heal_bodypart_damage', 'heal_overall_damage'):
            if fn + '(' in stmt:
                a = call_args(stmt, fn) or []
                kv = {}; pos = ['brute', 'burn', 'stamina']
                for i, x in enumerate(a):
                    if '=' in x and not x.startswith('='):
                        k, _, val = x.partition('='); kv[k.strip()] = val.strip()
                    elif i < len(pos): kv[pos[i]] = x
                for k, kind in (('brute', 'brute'), ('burn', 'burn'), ('stamina', 'stamina')):
                    if k in kv:
                        v = num(kv[k])
                        if v is not None: dmg.append(dict(kind=kind, amt=round(-v, 3), **base))
        if 'adjustOrganLoss(' in stmt:
            a = call_args(stmt, 'adjustOrganLoss') or []
            if len(a) >= 2:
                v = num(a[1]); slot = a[0].replace('ORGAN_SLOT_', '').lower()
                if v is not None: organ.append(dict(slot=slot, amt=round(v, 3), **base))
                else: dyn.append(dict(kind='organ:' + slot, expr=a[1], **base))
        for fn, tag in STATUS.items():
            if re.search(r'(?<![\w.])' + fn + r'\(|\.' + fn + r'\(', stmt):
                a = call_args(stmt, fn) or []
                t = dict(tag=tag, detail=(a[0] if a else ''), **base)
                if fn == 'apply_status_effect' or fn == 'remove_status_effect': t['detail'] = (a[0] if a else '').split('/')[-1]
                elif a:
                    v = num(a[0])
                    if v is not None: t['detail'] = ('%g' % v)
                tags.append(t)
        m = re.search(r'ADD_TRAIT\([^,]+,\s*(TRAIT_\w+)', stmt)
        if m: tags.append(dict(tag='trait', detail=m.group(1), **base))
        m = re.search(r'remove_reagent\((/datum/reagent/[\w/]+|[\w.]+(?:\.type)?),\s*([^)]*)\)', stmt)
        if m and 'metabol' not in stmt: tags.append(dict(tag='purges', detail=m.group(1).split('/')[-1], **base))
        m = re.search(r'add_reagent\((/datum/reagent/[\w/]+)', stmt)
        if m: tags.append(dict(tag='makes', detail=m.group(1).split('/')[-1], **base))
        if re.search(r'losebreath\s*(\+\+|\+=)', stmt): tags.append(dict(tag='losebreath', detail='+', **base))
        if re.search(r'losebreath\s*(--|-=)', stmt): tags.append(dict(tag='restores-breath', detail='', **base))
    return dmg, organ, tags, dyn

def chain(defs, path, proc):
    """the proc's lines: own, then the parent's when the own body calls ..()"""
    out = []; p = path
    while True:
        d = defs.get(p)
        if d is not None and proc in d.pind:
            out.append((p, d.pind[proc]))
            if not any(re.search(r'\.\.\(\)', t) for _, t in d.pind[proc]): break
        if p.count('/') <= 2: break
        p = p.rsplit('/', 1)[0]
    return out

def summarize(dmg, organ, tags, dyn):
    flat = {}
    cond = []
    for e in dmg:
        if e['cond'] is None and e['prob'] is None and 'cyc' not in e and 'odp' not in e and e.get('amt') is not None: flat[e['kind']] = round(flat.get(e['kind'], 0) + e['amt'], 3)
        else: cond.append(e)
    return dict(flat=flat, cond=cond, organ=organ, tags=tags, dyn=dyn)

def extract(db):
    defs = db.rdefs; out = {}
    for path, r in db.reagents.items():
        d = defs.get(path)
        if d is None: continue
        CTX['defs'] = defs; CTX['path'] = path
        life = [x for _, lines in chain(defs, path, 'on_mob_life') for x in lines]
        # a chain entry per proc owner; run each owner's lines separately so nesting indent stays relative
        ev = []
        for _, lines in chain(defs, path, 'on_mob_life'): ev += body_events(lines)
        life_s = summarize(*eval_events(ev))
        ev = []
        for proc in ('overdose_process',):
            for _, lines in chain(defs, path, proc): ev += body_events(lines)
        od_s = summarize(*eval_events(ev))
        ev = []
        for proc in ('overdose_start',):
            for _, lines in chain(defs, path, proc): ev += body_events(lines)
        od_start = summarize(*eval_events(ev))
        ev = []
        for proc in ('on_mob_metabolize', 'on_mob_add'):
            for _, lines in chain(defs, path, proc): ev += body_events(lines)
        meta_s = summarize(*eval_events(ev))
        hooks = sorted(h for h in ('expose_mob', 'expose_turf', 'expose_obj', 'expose_atom', 'on_mob_dead', 'on_burn_wound_processing') if any(h in (defs.get(q).procs if defs.get(q) else {}) for q in [path]))
        vars_ = {}
        for vn in ('toxpwr', 'acidpwr', 'boozepwr', 'penetrates_skin', 'lube_kind', 'addiction_types', 'ph', 'purity', 'metabolization_rate'):
            v, _ = dmparse.resolve_chain(defs, path, vn)
            if v is not None:
                nv = num(v)
                vars_[vn] = nv if nv is not None else v.strip()
        out[path] = dict(name=r.name, vars=vars_, od=r.overdose or None, metab=r.metab, desc=r.description, life=life_s, od_process=od_s, od_start=od_start, on_metabolize=meta_s, hooks=hooks,
                         flags=(dmparse.resolve_chain(defs, path, 'chemical_flags')[0] or '').strip())
    return out

def main():
    import chemlib
    db = chemlib.DB()
    if db.meta.get('loaded_from'): raise SystemExit('need a source checkout (MONKE_SRC), found only the JSON snapshot')
    data = extract(db)
    with open(OUT, 'w') as fh: json.dump({'meta': dict(commit=db.meta.get('commit'), REM=REM, seconds_per_tick=SPT), 'reagents': data}, fh, indent=0, sort_keys=True)
    n = sum(1 for v in data.values() if v['life']['flat'] or v['life']['cond'] or v['life']['organ'])
    print('wrote %s: %d reagents, %d with life-tick damage/healing' % (OUT, len(data), n))

if __name__ == '__main__': main()
