#!/usr/bin/env python3
"""
codecheck.py - "did the chemistry rules change?"  Run this FIRST when a recipe stops working.

It pulls the CURRENT server source from GitHub (shallow, sparse: only the reagent / robot-item files are downloaded),
re-parses every chemical reaction from the real .dm files, and diffs them against the engine's snapshot (chemdata.json).
Differences are printed with file:line and a GitHub link, and the ones that touch a recipe in recipes.py are marked.
It also re-reads the beaker/syringe volumes the planner's gear table assumes (planner.BEAKER_TYPES / SYRINGE_TYPES).

    python3 codecheck.py                          # default: Monkestation/Monkestation2.0, default branch
    python3 codecheck.py --ref some-branch        # the branch/tag/commit your server actually runs
    python3 codecheck.py --repo https://github.com/tgstation/tgstation.git   # another tg-derived codebase
    python3 codecheck.py --update-snapshot        # after reviewing: write the new rules into chemdata.json
    python3 codecheck.py --src PATH               # skip the download, use an existing checkout

Exit code: 0 identical, 2 something changed that a recipe depends on (or the gear table is stale), 1 other changes, 3 error.
Network use: git over HTTPS to the repo only (read-only). Nothing is executed from the downloaded code - it is parsed as text.
"""
import os, re, sys, json, argparse, subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_REPO = 'https://github.com/Monkestation/Monkestation2.0.git'
CACHE = os.path.join(HERE, '.cache', 'source')
SPARSE = ['code/modules/reagents', 'code/__DEFINES', 'code/__HELPERS', 'code/game/objects/items/robot',
          'code/modules/mob/living/silicon', 'code/game/objects/effects/effect_system', 'monkestation/code/modules/reagents']
SNAPSHOT = os.path.join(HERE, 'chemdata.json')

# gear name -> (source file, DM path) for the volume check; kept next to planner's tables on purpose
GEAR_SOURCES = {
    'beaker':    ('code/modules/reagents/reagent_containers/cups/_cup.dm', '/obj/item/reagent_containers/cup/beaker'),
    'large':     ('code/modules/reagents/reagent_containers/cups/_cup.dm', '/obj/item/reagent_containers/cup/beaker/large'),
    'xl':        ('code/modules/reagents/reagent_containers/cups/_cup.dm', '/obj/item/reagent_containers/cup/beaker/plastic'),
    'meta':      ('code/modules/reagents/reagent_containers/cups/_cup.dm', '/obj/item/reagent_containers/cup/beaker/meta'),
    'bluespace': ('code/modules/reagents/reagent_containers/cups/_cup.dm', '/obj/item/reagent_containers/cup/beaker/bluespace'),
    'noreact':   ('code/modules/reagents/reagent_containers/cups/_cup.dm', '/obj/item/reagent_containers/cup/beaker/noreact'),
}
SYRINGE_SOURCES = {
    'standard':  ('code/modules/reagents/reagent_containers/syringes.dm', '/obj/item/reagent_containers/syringe'),
    'piercing':  ('code/modules/reagents/reagent_containers/syringes.dm', '/obj/item/reagent_containers/syringe/piercing'),
    'bluespace': ('code/modules/reagents/reagent_containers/syringes.dm', '/obj/item/reagent_containers/syringe/bluespace'),
}

def git(*a, cwd=None, check=True):
    r = subprocess.run(['git'] + list(a), cwd=cwd, capture_output=True, text=True)
    if check and r.returncode: raise RuntimeError('git %s failed: %s' % (' '.join(a), r.stderr.strip()[:300]))
    return r.stdout.strip()

def sync(repo, ref, dest):
    """shallow + sparse checkout of `ref`; returns the commit sha"""
    if not os.path.isdir(os.path.join(dest, '.git')):
        os.makedirs(dest, exist_ok=True)
        git('init', '-q', cwd=dest)
        git('remote', 'add', 'origin', repo, cwd=dest)
        git('config', 'extensions.partialClone', 'origin', cwd=dest)
        git('sparse-checkout', 'init', '--cone', cwd=dest)
    else:
        git('remote', 'set-url', 'origin', repo, cwd=dest)
    git('sparse-checkout', 'set', *SPARSE, cwd=dest)
    git('fetch', '-q', '--depth', '1', '--filter=blob:none', 'origin', ref or 'HEAD', cwd=dest)
    git('checkout', '-q', '--detach', 'FETCH_HEAD', cwd=dest)
    return git('rev-parse', 'HEAD', cwd=dest)

# ------------------------------------------------------------------ parsing helpers (pure functions, unit-tested)
def read_text(path):
    with open(path, errors='replace') as fh: return fh.read()

def find_line(path_text, dm_path):
    """1-based line of `/datum/chemical_reaction/foo` (or any DM type path) definition in a file's text, else None"""
    for i, line in enumerate(path_text.split('\n'), 1):
        if line.strip().rstrip('{').strip() == dm_path: return i
    return None

def parse_volumes(text, dm_path):
    """volume of a DM type block: explicit `volume = N`, else the number in 'hold up to N units' of its desc;
       a child type with neither inherits from its parent path (resolved by the caller via parse_volume_chain)"""
    lines = text.split('\n'); start = None
    for i, l in enumerate(lines):
        if l.rstrip() == dm_path: start = i; break
    if start is None: return None
    for l in lines[start + 1:]:
        if l and not l[0].isspace() and l.startswith('/'): break          # next type definition
        m = re.match(r'\s*volume\s*=\s*([0-9.]+)', l)
        if m: return float(m.group(1))
    block = []
    for l in lines[start + 1:]:
        if l and not l[0].isspace() and l.startswith('/'): break
        block.append(l)
    m = re.search(r'hold(?:s)? up to ([0-9]+) units', ' '.join(block))
    return float(m.group(1)) if m else None

def parse_volume_chain(text, dm_path):
    p = dm_path
    while p.count('/') > 1:
        v = parse_volumes(text, p)
        if v is not None: return v
        p = p.rsplit('/', 1)[0]
    return None

def check_gear(src, beaker_types, syringe_types, root=None):
    """compare planner tables with the source; returns list of (name, planner volume, source volume)"""
    bad = []
    for table, sources in ((beaker_types, GEAR_SOURCES), (syringe_types, SYRINGE_SOURCES)):
        for name, (rel, dm) in sources.items():
            if name not in table: continue
            f = os.path.join(src, rel)
            if not os.path.exists(f): bad.append((name, table[name][0], 'file missing: ' + rel)); continue
            v = parse_volume_chain(read_text(f), dm)
            if v is None: bad.append((name, table[name][0], 'volume not found')); continue
            if abs(v - table[name][0]) > 1e-6: bad.append((name, table[name][0], v))
    return bad

def rx_view(rx):
    return dict(req={k: v for k, v in rx.req.items()}, results={k: v for k, v in rx.results.items()}, cat=dict(rx.cat),
                temp=rx.required_temp, cold=rx.is_cold, non_instant=rx.non_instant, effects=list(rx.effects or []),
                container=rx.container, other=rx.other)

def diff_dbs(old, new):
    """-> dict(added=[short], removed=[short], changed=[(short, old_view, new_view, [fields])], dispensers=[(tier, +set, -set)])"""
    o = {r.path: r for r in old.reactions}; n = {r.path: r for r in new.reactions}
    out = dict(added=sorted(n[p].short for p in set(n) - set(o)), removed=sorted(o[p].short for p in set(o) - set(n)), changed=[], dispensers=[])
    for p in sorted(set(o) & set(n)):
        a, b = rx_view(o[p]), rx_view(n[p])
        fields = [k for k in a if a[k] != b[k]]
        if fields: out['changed'].append((o[p].short, a, b, fields))
    for t in sorted(set(old.dispensers) | set(new.dispensers)):
        a, b = set(old.dispensers.get(t, [])), set(new.dispensers.get(t, []))
        if a != b: out['dispensers'].append((t, sorted(b - a), sorted(a - b)))
    return out

def critical_set(db):
    """reaction shorts and reagent names used by the verified recipes in recipes.py, found by running them through the engine"""
    import chemcli
    import planner
    from recipes import all_recipes
    shorts = set()
    for key, title, ops, gspec in all_recipes():
        try: rig = chemcli._run(db, ops, 1, False, planner.Gear(**gspec))
        except Exception: continue            # a recipe that cannot run on this rule set contributes nothing here
        for st in rig.steps:
            for l in st['log']:
                m = re.match(r'\s*([\w]+):\s+x\d+\s+consumes', l)
                if m: shorts.add(m.group(1))
    names = set()
    for rx in db.reactions:
        if rx.short in shorts:
            for q in list(rx.req) + list(rx.results): names.add(db.name(q).lower())
    return names, shorts

def recheck_recipes(old, new):
    """run every verified recipe on both rule sets -> [(key, title, 'FAILS: why' | 'RESULT CHANGED: a -> b')]"""
    import chemcli
    import planner
    from recipes import all_recipes
    bad = []
    for key, title, ops, gspec in all_recipes():
        g = planner.Gear(**gspec)
        try:
            r0 = chemcli._run(old, ops, 1, False, g); a = chemcli.signature(r0)
            if r0.sim.warnings: a = a + (('warnings', tuple(r0.sim.warnings)),)
        except Exception as ex: continue                     # was already broken on the snapshot
        try:
            r = chemcli._run(new, ops, 1, False, g); b = chemcli.signature(r)
            if r.sim.warnings: b = b + (('warnings', tuple(r.sim.warnings)),)
        except Exception as ex: bad.append((key, title, 'FAILS on the new rules: %s' % ex)); continue
        if a != b: bad.append((key, title, 'RESULT CHANGED: %s  ->  %s' % (a, b)))
    return bad

def fmt(d, db):
    return ' + '.join('%g %s' % (v, db.name(k)) for k, v in d.items())

def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--repo', default=DEFAULT_REPO); ap.add_argument('--ref', default=None)
    ap.add_argument('--cache-dir', default=CACHE); ap.add_argument('--src', default=None, help='existing checkout, no download')
    ap.add_argument('--update-snapshot', action='store_true'); ap.add_argument('--max', type=int, default=40)
    ap.add_argument('--snapshot', default=SNAPSHOT, help='snapshot json to compare against (default chemdata.json)')
    args = ap.parse_args(argv)
    sys.path.insert(0, HERE)
    import chemlib, planner
    old = chemlib.DB(json_path=args.snapshot)
    try:
        if args.src: src = args.src; sha = git('rev-parse', 'HEAD', cwd=src, check=False) or '?'
        else:
            print('fetching %s @ %s (shallow, sparse) ...' % (args.repo, args.ref or 'default branch'))
            src = args.cache_dir; sha = sync(args.repo, args.ref, src)
        new = chemlib.DB(src=src, json_path=None)
    except Exception as ex:
        print('ERROR: %s' % ex); return 3
    new.meta['commit'] = sha
    web = re.sub(r'\.git$', '', args.repo)
    print('snapshot commit %s  vs  source commit %s' % (str(old.meta.get('commit', '?'))[:10], sha[:10]))
    print('parsed %d reactions from source (snapshot has %d); parser left %d values unparsed' % (len(new.reactions), len(old.reactions), len(new.unparsed)))
    d = diff_dbs(old, new)
    names, shorts = critical_set(old)
    status = 0
    def where(short):
        rx = new.by_short.get(short) or old.by_short.get(short)
        f = os.path.join(src, rx.source) if rx else None
        ln = find_line(read_text(f), rx.path) if f and os.path.exists(f) else None
        return rx.source, ln, ('%s/blob/%s/%s#L%s' % (web, sha, rx.source, ln) if ln else '')
    def mark(short):
        return '  <<< USED BY YOUR RECIPES' if short in shorts else ''
    for short, a, b, fields in d['changed'][:args.max]:
        f, ln, url = where(short)
        print('CHANGED %-28s %s:%s%s' % (short, f, ln, mark(short)))
        for k in fields:
            if k in ('req', 'results', 'cat'): print('    %s: %s  ->  %s' % (k, fmt(a[k], old), fmt(b[k], new)))
            else: print('    %s: %s  ->  %s' % (k, a[k], b[k]))
        if url: print('    ' + url)
        status = max(status, 2 if short in shorts else 1)
    if len(d['changed']) > args.max: print('  ... %d more changed reactions' % (len(d['changed']) - args.max))
    for s in d['added'][:args.max]: print('ADDED   %s' % s); status = max(status, 1)
    for s in d['removed'][:args.max]:
        print('REMOVED %s%s' % (s, mark(s))); status = max(status, 2 if s in shorts else 1)
    for t, plus, minus in d['dispensers']:
        print('DISPENSER tier %d: +%s -%s' % (t, [new.name(p) for p in plus], [old.name(p) for p in minus])); status = max(status, 1)
    for key, title, why in recheck_recipes(old, new):
        print('RECIPE  %s: %s' % (title, why)); status = 2
    bad = check_gear(src, planner.BEAKER_TYPES, planner.SYRINGE_TYPES)
    for name, mine, theirs in bad:
        print('GEAR    %s: planner says %s, source says %s  (update planner.BEAKER_TYPES / SYRINGE_TYPES)' % (name, mine, theirs)); status = 2
    if status == 0 and not (d['changed'] or d['added'] or d['removed'] or d['dispensers'] or bad):
        print('RESULT: the chemical rules in the source are IDENTICAL to the snapshot. A recipe that still fails is not a recipe-data change:\n'
              '        suspect a different server version than this ref, an engine modelling gap, or an in-game UI step.')
    elif status == 2:
        print('RESULT: a change touches a recipe you rely on - fix the recipe from the new values (rerun chemcli nade) BEFORE any deeper debugging.')
    else:
        print('RESULT: rules changed, but none of the reactions your verified recipes use.')
    if args.update_snapshot:
        new.to_json(args.snapshot); print('snapshot updated ->', args.snapshot)
    return status

if __name__ == '__main__':
    sys.exit(main())
