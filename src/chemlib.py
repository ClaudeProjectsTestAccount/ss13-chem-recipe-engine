"""
chemlib.py - an executable model of Monkestation 2.0 chemistry (instant-reaction subset).

What it models, taken line-by-line from the DM source:
  holder.dm   add_reagent / remove_reagent / update_total / trans_to / copy_to /
              handle_reactions (possible-reaction scan, stale list, nested re-entry) /
              instant_react (BYOND round() multiplier, purity, product add)
  recipes     all `/datum/chemical_reaction` definitions parsed from the real files,
              with DM path inheritance and tgstation.dme compile order
  effects     foam (create_foam -> fluid_spread/foam) and chem smoke (smoke_powder)
              payload bookkeeping: tile count, x3.2 foam amplification, dilution
  machines    chem dispenser (5/10/15/20/25/30/50/100 clicks, 100u large beaker),
              syringe (15u) draw/inject, spill, optional heater

What it does NOT model: timed (equilibrium) reactions - Monkestation flags only two
reaction-agent recipes REACTION_NON_INSTANT, so everything a nade needs is instant;
pH/purity mechanics (Monkestation commented them out); mobs; atmos.
"""
import os, re, math, itertools, copy
from collections import OrderedDict
import dmparse

SRC = os.environ.get('MONKE_SRC', os.path.join(os.path.dirname(os.path.abspath(__file__)), '.cache', 'source'))

QUANT = 0.0001          # CHEMICAL_QUANTISATION_LEVEL
VOL_MIN = 0.001         # CHEMICAL_VOLUME_MINIMUM
FOAM_SCALE = 3.2        # FOAM_REAGENT_SCALE
FOAM_MIN_DILUTION = 25  # DIAMOND_AREA(3)
DEFAULT_TEMP = 300      # DEFAULT_REAGENT_TEMPERATURE
SH_DEFAULT = 200        # SPECIFIC_HEAT_DEFAULT

def byond_round(x):
    """BYOND round(x) with one argument: nearest integer, .5 rounds up (away from zero)."""
    return math.floor(x + 0.5 + 1e-9) if x >= 0 else -math.floor(-x + 0.5 + 1e-9)

def round_q(x, q=QUANT):
    return math.floor(x / q + 0.5 + 1e-9) * q

# --------------------------------------------------------------------------------------
#  database
# --------------------------------------------------------------------------------------
class Reagent:
    def __init__(self, path):
        self.path = path; self.name = None; self.creation_purity = 1.0
        self.specific_heat = SH_DEFAULT; self.flags = ''
class Reaction:
    def __init__(self, path):
        self.path = path; self.results = {}; self.req = OrderedDict(); self.cat = {}
        self.required_temp = 100.0; self.is_cold = False; self.mob_react = True
        self.non_instant = False; self.container = None; self.other = False
        self.order = 0; self.on_reaction = None; self.source = ''
        self.effects = []  # classified side effects

    @property
    def short(self): return self.path.replace('/datum/chemical_reaction/', '')

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_JSON = os.path.join(HERE, 'chemdata.json')

class DB:
    """Loads from a Monkestation source checkout when available, else from the bundled chemdata.json snapshot."""
    def __init__(self, src=SRC, json_path=None):
        self.src = src
        self.reagents = {}; self.reactions = []; self.index = {}
        self.rdefs = {}; self.cdefs = {}; self.unparsed = []
        self.dispensers = {}; self.meta = {}
        jp = json_path or (DEFAULT_JSON if not os.path.exists(os.path.join(src, 'tgstation.dme')) else None)
        if jp:
            self._from_json(jp)
        else:
            self._load()
            self.dispensers = self._dispenser_lists()
            try:
                import subprocess
                self.meta['commit'] = subprocess.check_output(['git', '-C', src, 'rev-parse', 'HEAD'], stderr=subprocess.DEVNULL).decode().strip()
            except Exception:
                pass
        self._index()

    def _dispenser_lists(self):
        f = os.path.join(self.src, 'code/modules/reagents/chemistry/machinery/chem_dispenser.dm')
        if not os.path.exists(f): return {1: [], 2: [], 3: [], 4: []}      # other forks move/rename the dispenser file
        txt = open(f, errors='replace').read()
        def grab(name):
            m = re.search(r'var/list/%s\s*=\s*list\((.*?)\n\t\)' % name, txt, re.S)
            return re.findall(r'/datum/reagent[\w/]*', m.group(1)) if m else []
        return {1: grab('dispensable_reagents'), 2: grab('upgrade_reagents'),
                3: grab('upgrade_reagents2'), 4: grab('upgrade_reagents3')}

    def to_json(self, path):
        import json
        out = {'meta': self.meta, 'dispensers': {str(k): v for k, v in self.dispensers.items()},
               'reagents': {p: dict(name=r.name, creation_purity=r.creation_purity, specific_heat=r.specific_heat)
                            for p, r in self.reagents.items()},
               'reactions': [dict(path=r.path, order=r.order, source=r.source, req=list(r.req.items()),
                                  results=list(r.results.items()), cat=list(r.cat.items()),
                                  required_temp=r.required_temp, is_cold=r.is_cold, mob_react=r.mob_react,
                                  non_instant=r.non_instant, container=r.container, other=r.other,
                                  on_reaction=r.on_reaction, effects=r.effects) for r in self.reactions]}
        with open(path, 'w') as fh: json.dump(out, fh, indent=0)

    def _from_json(self, path):
        import json
        with open(path) as fh: d = json.load(fh)
        self.meta = d.get('meta', {}); self.meta['loaded_from'] = os.path.basename(path)
        self.dispensers = {int(k): v for k, v in d['dispensers'].items()}
        for p, r in d['reagents'].items():
            x = Reagent(p); x.name = r['name']; x.creation_purity = r['creation_purity']; x.specific_heat = r['specific_heat']
            self.reagents[p] = x
        for r in d['reactions']:
            x = Reaction(r['path']); x.order = r['order']; x.source = r['source']
            x.req = OrderedDict(r['req']); x.results = OrderedDict(r['results']); x.cat = OrderedDict(r['cat'])
            x.required_temp = r['required_temp']; x.is_cold = r['is_cold']; x.mob_react = r['mob_react']
            x.non_instant = r['non_instant']; x.container = r['container']; x.other = r['other']
            x.on_reaction = r['on_reaction']; x.effects = r['effects']
            self.reactions.append(x)

    # file order = tgstation.dme order, restricted to chemistry files we have on disk
    def _files(self):
        dme = os.path.join(self.src, 'tgstation.dme')
        order = dmparse.dme_order(dme, self.src)
        keep = [f for f in order if ('modules/reagents' in f.lower()) and f.endswith('.dm')]
        return [f for f in keep if os.path.exists(os.path.join(self.src, f))]

    def _load(self):
        dmparse.load_macros(self.src)
        cnt = itertools.count()
        rcnt = itertools.count()
        self.files = self._files()
        for f in self.files:
            p = os.path.join(self.src, f)
            dmparse.parse_file(p, 'reagent', self.rdefs, rcnt)
            dmparse.parse_file(p, 'chemical_reaction', self.cdefs, cnt)
        # reagents
        for path, d in self.rdefs.items():
            r = Reagent(path)
            nm, _ = dmparse.resolve_chain(self.rdefs, path, 'name')
            r.name = nm.strip('"') if nm else None
            cp, _ = dmparse.resolve_chain(self.rdefs, path, 'creation_purity')
            if cp is not None:
                v = cp.replace('REAGENT_STANDARD_PURITY', '0.75')
                r.creation_purity = dmparse.parse_num(v) or 1.0
            sh, _ = dmparse.resolve_chain(self.rdefs, path, 'specific_heat')
            if sh:
                v = dmparse.parse_num(sh.replace('SPECIFIC_HEAT_DEFAULT', '200'))
                if v: r.specific_heat = v
            self.reagents[path] = r
        # reactions
        for path, d in sorted(self.cdefs.items(), key=lambda kv: kv[1].order):
            def g(k):
                v, _ = dmparse.resolve_chain(self.cdefs, path, k)
                return v
            rq = g('required_reagents')
            if not rq: continue
            rx = Reaction(path)
            rx.order = d.order
            rx.source = os.path.relpath(os.path.abspath(d.file), os.path.abspath(self.src)).replace(os.sep, '/')
            rx.req = OrderedDict(dmparse.parse_pairs(rq))
            if not rx.req: continue
            rx.results = OrderedDict(dmparse.parse_pairs(g('results') or ''))
            rx.cat = OrderedDict(dmparse.parse_pairs(g('required_catalysts') or ''))
            t = g('required_temp')
            if t is not None:
                v = dmparse.parse_num(t)
                if v is not None: rx.required_temp = v
                else: self.unparsed.append((path, 'required_temp', t))
            rx.is_cold = (g('is_cold_recipe') or 'FALSE').strip() == 'TRUE'
            rx.mob_react = (g('mob_react') or 'TRUE').strip() != 'FALSE'
            fl = g('reaction_flags') or ''
            rx.non_instant = 'REACTION_NON_INSTANT' in fl
            rx.container = (g('required_container') or None)
            rx.other = (g('required_other') or 'FALSE').strip() == 'TRUE'
            # on_reaction text from the nearest ancestor that defines it
            p = path
            body = None
            while True:
                dd = self.cdefs.get(p)
                if p == '/datum/chemical_reaction': break      # base proc is a no-op
                if dd is not None and 'on_reaction' in dd.procs and ''.join(dd.procs['on_reaction']).strip():
                    body = dd.procs['on_reaction']; break
                if p.count('/') <= 2: break
                p = p.rsplit('/', 1)[0]
            if body:
                rx.on_reaction = '\n'.join(body)
                rx.effects = classify_effects(rx.on_reaction, path)
            self.reactions.append(rx)
    def _index(self):
        # reactant index: keyed by the FIRST required reagent (see _globalvars/lists/reagents.dm)
        for rx in self.reactions:
            first = next(iter(rx.req))
            self.index.setdefault(first, []).append(rx)
        self.by_path = {r.path: r for r in self.reactions}
        self.by_short = {r.short: r for r in self.reactions}

    def name(self, path):
        r = self.reagents.get(path)
        if r and r.name: return r.name
        return path.rsplit('/', 1)[-1].replace('_', ' ')

    def find_reagent(self, text):
        """accept a path, a short path tail (e.g. 'fluorosurfactant'), or a display name"""
        if text in self.reagents: return text
        t = text.lower().strip()
        c = [p for p in self.reagents if p.lower() == '/datum/reagent/' + t]
        if c: return c[0]
        c = [p for p, r in self.reagents.items() if (r.name or '').lower() == t]
        if c: return sorted(c, key=len)[0]
        c = [p for p in self.reagents if p.lower().endswith('/' + t)]
        if len(c) >= 1: return sorted(c, key=len)[0]
        raise KeyError(text)

EFFECT_KEYS = [
    ('explosion', r'default_explode|explosion|explode\(|goonchem_vortex'),
    ('fire', r'explode_fire|fire_act|hotspot|IgniteTurf|ignite'),
    ('smoke', r'fluid_spread/smoke|do_smoke|explode_smoke|explode_invert_smoke'),
    ('foam', r'create_foam'),
    ('flash', r'flash|explode_flash'),
    ('mob-spawn', r'chemical_mob_spawn|new /mob'),
    ('gas', r'atmos|assert_gas|adjust_gas|air\.'),
    ('shock/emp', r'emp_|tesla|lightning'),
]
def classify_effects(body, path):
    tags = [t for t, rx in EFFECT_KEYS if re.search(rx, body)]
    return tags

# --------------------------------------------------------------------------------------
#  simulation
# --------------------------------------------------------------------------------------
class Sim:
    """one simulation world: shared database, event log and effect list"""
    def __init__(self, db, reverse_same_primary=False):
        self.db = db; self.log = []; self.effects = []; self.warnings = []
        self.reverse_same_primary = reverse_same_primary
        self.depth = 0
    def note(self, msg): self.log.append('  ' * self.depth + msg)

class Holder:
    NO_REACT = 1; INSTANT = 2
    def __init__(self, sim, name, cap, flags=0):
        self.sim = sim; self.name = name; self.max = cap; self.flags = flags
        self.r = OrderedDict()      # path -> [volume, purity]
        self.temp = 150.0
        self.total = 0.0
        self.is_reacting = False

    # ---- bookkeeping
    def update_total(self):
        tot = 0.0
        for p in list(self.r):
            v = self.r[p][0]
            if v < 0.05 and not self.is_reacting:
                del self.r[p]
            elif v <= VOL_MIN:
                del self.r[p]
            else:
                tot += v
        self.total = tot
        return tot
    def amount(self, p): return self.r[p][0] if p in self.r else 0.0
    def has(self, p, amt=-1):
        if p not in self.r: return False
        if amt == -1: return True
        return round_q(self.r[p][0]) >= amt
    def heat_capacity(self):
        db = self.sim.db
        return sum(db.reagents[p].specific_heat * v[0] for p, v in self.r.items() if p in db.reagents)
    def contents(self): return OrderedDict((p, round(v[0], 3)) for p, v in self.r.items())
    def describe(self):
        if not self.r: return 'empty'
        return ', '.join('%gu %s' % (round(v[0], 2), self.sim.db.name(p)) for p, v in self.r.items())

    # ---- add_reagent (holder.dm:75)
    def add_reagent(self, p, amount, temp=DEFAULT_TEMP, purity=None, no_react=False):
        if amount <= QUANT: return False
        gr = self.sim.db.reagents.get(p)
        if gr is None:
            self.sim.warnings.append('unknown reagent %s' % p); return False
        if purity is None: purity = gr.creation_purity
        self.update_total()
        if self.total + amount > self.max:
            amount = self.max - self.total
            if amount <= 0: return False
        cached_temp = self.temp
        old_hc = 0.0
        if temp != cached_temp:
            old_hc = self.heat_capacity()
        if p in self.r:
            ent = self.r[p]
            ent[1] = ((ent[1] * ent[0]) + (purity * amount)) / (ent[0] + amount)
            ent[0] += round_q(amount)
            self.update_total()
            if temp != cached_temp:
                nhc = self.heat_capacity()
                self.temp = (((old_hc * cached_temp) + (gr.specific_heat * amount * temp)) / nhc) if nhc else temp
            if not no_react and not self.is_reacting:
                self.handle_reactions()
            return True
        self.r[p] = [amount, purity]
        self.update_total()
        if temp != cached_temp:
            nhc = self.heat_capacity()
            self.temp = (((old_hc * cached_temp) + (gr.specific_heat * amount * temp)) / nhc) if nhc else temp
        if not no_react:
            self.handle_reactions()
        return True

    def remove_reagent(self, p, amount):
        if p not in self.r: return False
        amount = max(0.0, min(amount, self.r[p][0]))
        self.r[p][0] -= amount
        self.update_total()
        return True

    def clear(self):
        for p in list(self.r): del self.r[p]
        self.total = 0.0

    # ---- transfers
    def trans_to(self, target, amount, multiplier=1.0, no_react=False):
        if not self.total or amount < 0: return 0
        if not no_react: pass  # transfer_reactions only concerns timed reactions
        amount = min(amount, self.total, target.max - target.total)
        part = amount / self.total
        moved = []
        for p, (v, pur) in list(self.r.items()):
            ta = v * part
            if target.add_reagent(p, ta * multiplier, self.temp, pur, no_react=True):
                moved.append((p, ta))
        for p, ta in moved:
            self.remove_reagent(p, ta)
        self.update_total(); target.update_total()
        if not no_react:
            target.handle_reactions()
            self.handle_reactions()
        return amount

    def copy_to(self, target, amount, multiplier=1.0, no_react=False):
        if not self.total: return 0
        amount = min(min(amount, self.total), target.max - target.total)
        part = amount / self.total
        for p, (v, pur) in list(self.r.items()):
            target.add_reagent(p, v * part * multiplier, self.temp, pur, no_react=True)
        if not no_react:
            self.update_total(); target.update_total()
            target.handle_reactions()
            self.handle_reactions()
        return amount

    # ---- reactions (holder.dm:795)
    def handle_reactions(self):
        sim = self.sim; db = sim.db
        if not self.r: return False
        if self.flags & Holder.NO_REACT: return False
        possible = []
        for p in list(self.r):
            lst = db.index.get(p, [])
            if sim.reverse_same_primary: lst = list(reversed(lst))
            for rx in lst:
                if rx.container or rx.other: continue
                if not all(self.has(q, a * VOL_MIN) for q, a in rx.req.items()): continue
                if not all(self.has(q, a * VOL_MIN) for q, a in rx.cat.items()): continue
                tempok = (rx.required_temp == 0 or
                          (rx.is_cold and self.temp <= rx.required_temp) or
                          (not rx.is_cold and self.temp >= rx.required_temp))
                if tempok:
                    possible.append(rx)
        n = 0
        for rx in possible:
            if rx.non_instant and not (self.flags & Holder.INSTANT):
                sim.warnings.append('timed (equilibrium) reaction %s skipped - not modelled' % rx.short)
                continue
            self.instant_react(rx)
            n += 1
            self.update_total()
        return n

    def instant_react(self, rx):
        sim = self.sim
        mult = math.inf
        for q, a in rx.req.items():
            mult = min(mult, byond_round(self.amount(q) / a))
        if mult == 0: return False
        sum_purity = 0.0
        for q in rx.req:
            if q in self.r: sum_purity += self.r[q][1]
        sum_purity /= len(rx.req)
        removed = OrderedDict((q, a * mult) for q, a in rx.req.items())
        before = OrderedDict((q, self.amount(q)) for q in rx.req)
        for q, a in rx.req.items():
            self.remove_reagent(q, mult * a)
        mult = max(mult, 1)
        sim.note('%s: x%d  consumes %s' % (rx.short, mult,
                 ', '.join('%gu %s' % (min(before[q], removed[q]), sim.db.name(q)) for q in rx.req)
                 + ('' if all(before[q] >= removed[q] - 1e-9 for q in rx.req) else '  [ROUNDING QUIRK: asked for more than present]')))
        sim.depth += 1
        for prod, y in rx.results.items():
            yld = y * mult * sum_purity
            sim.note('-> +%gu %s' % (round(yld, 3), sim.db.name(prod)))
            self.add_reagent(prod, yld, self.temp, sum_purity)
        sim.depth -= 1
        self.fire_effect(rx, mult)
        return True

    def fire_effect(self, rx, mult):
        sim = self.sim
        if not rx.on_reaction: return
        h = HANDLERS.get(rx.path) or HANDLERS.get(rx.path.rsplit('/', 1)[0] if False else None)
        if h:
            sim.depth += 1; h(sim, self, rx, mult); sim.depth -= 1
        else:
            tags = rx.effects or ['unclassified']
            sim.effects.append({'kind': 'UNMODELED', 'reaction': rx.short, 'tags': tags, 'mult': mult})
            sim.note('!! on_reaction of %s has side effects the engine does not model: %s' % (rx.short, ','.join(tags)))

# ---- effect handlers --------------------------------------------------------------
def _foam(sim, holder, rx, mult):
    m = re.search(r'create_foam\(\s*([\w/]+)\s*,\s*(?:(\d+(?:\.\d+)?)\s*\*\s*created_volume|(\d+(?:\.\d+)?))', rx.on_reaction)
    if not m:
        sim.effects.append({'kind': 'UNMODELED', 'reaction': rx.short, 'tags': ['foam(unparsed)'], 'mult': mult}); return
    ftype = m.group(1).split('/')[-1]
    size = float(m.group(2)) * mult if m.group(2) else float(m.group(3))
    scale = FOAM_SCALE * (30 / 8) if ftype == 'long' else FOAM_SCALE
    # foam.set_up(carry = src): carry.copy_to(chemholder, total)   (chemholder is NO_REACT)
    chem = Holder(sim, 'foam chemholder', 1000, Holder.NO_REACT)
    holder.copy_to(chem, holder.total, no_react=False)   # includes src.handle_reactions() afterwards
    # foam.start(): chemholder.copy_to(foam, total, reagent_scale)  into an INSTANT_REACT holder
    fh = Holder(sim, 'foam tile', 1000 * scale, Holder.INSTANT)
    fh.temp = holder.temp
    sim.note('foam spreads: %d tiles, payload copied x%g into each tile' % (size, scale))
    chem.copy_to(fh, chem.total, multiplier=scale)
    holder.clear()
    sim.effects.append({'kind': 'foam', 'type': ftype, 'tiles': size, 'reaction': rx.short,
                        'scale': scale, 'tile': fh.contents(), 'pre_scale': chem.contents(),
                        'holder': fh})

def _smoke_powder(sim, holder, rx, mult):
    if holder.has('/datum/reagent/stabilizing_agent'):
        sim.note('stabilizing agent present: smoke suppressed'); return
    holder.remove_reagent('/datum/reagent/smoke_powder', mult * 3)
    chem = Holder(sim, 'smoke chemholder', 1000, Holder.NO_REACT)
    holder.copy_to(chem, holder.total)
    sh = Holder(sim, 'smoke tile', 1000, Holder.INSTANT)
    sh.temp = holder.temp
    chem.copy_to(sh, chem.total)
    tiles = mult * 3
    sim.note('smoke cloud: %d tiles, full payload in every tile' % tiles)
    holder.clear()
    sim.effects.append({'kind': 'smoke', 'tiles': tiles, 'reaction': rx.short, 'tile': sh.contents(),
                        'pre_scale': chem.contents(), 'holder': sh})

HANDLERS = {
    '/datum/chemical_reaction/foam': _foam,
    '/datum/chemical_reaction/smoke_powder': _smoke_powder,
}
