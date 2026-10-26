"""
planner.py - procedures (dispenser / syringe / beaker / heater) executed on top of chemlib,
plus a grid search for "15u syringe + 85u beaker" nade designs.
"""
import re, os, itertools, copy
from collections import OrderedDict
import chemlib
from chemlib import Sim, Holder, DB

DISP_AMOUNTS = [100, 50, 30, 25, 20, 15, 10, 5]   # chem dispenser click sizes (independent of the borg's beaker)

# ---- gear tables, read from the Monkestation source (reagent_containers/cups/_cup.dm, bottle.dm, syringes.dm)
# name -> (volume, possible_transfer_amounts, reagent_flags NO_REACT?)   the borg apparatus accepts any
# beaker / bottle / tube (storage.dm whitelist_storables), and ships with a large beaker (100u).
BEAKER_TYPES = {
    'beaker':    (50,  [5, 10, 15, 20, 25, 30], False),
    'large':     (100, [5, 10, 15, 20, 25, 30, 50, 100], False),     # borg default
    'xl':        (120, [5, 10, 15, 20, 25, 30, 60, 120], False),     # "x-large beaker" (plastic)
    'meta':      (180, [5, 10, 15, 20, 25, 30, 60, 120, 180], False),
    'bluespace': (300, [5, 10, 15, 20, 25, 30, 50, 100, 300], False),
    'noreact':   (50,  [5, 10, 15, 20, 25, 30], True),               # cryostasis beaker: holds chems with no reactions
    'bottle':    (50,  [5, 10, 15, 25, 50], False),
    'tube':      (30,  [5, 10, 15, 30], False),
}
# borg syringe + the medical-borg upgrades (robot_upgrades.dm /borg/upgrade/syringe/*; medical models only)
SYRINGE_TYPES = {
    'standard':  (15, [5, 10, 15]),
    'piercing':  (10, [5, 10]),                       # upgrade: SMALLER volume, pierces thick clothing
    'bluespace': (60, [10, 20, 30, 40, 50, 60]),      # upgrade: 60u
}
BEAKER_CAP = BEAKER_TYPES['large'][0]      # defaults kept for old callers
SYRINGE_CAP = SYRINGE_TYPES['standard'][0]

def _pick(table, key, what):
    if isinstance(key, str) and key in table: return key, table[key]
    if isinstance(key, (int, float)) or (isinstance(key, str) and key.replace('.', '', 1).isdigit()):
        v = float(key); v = int(v) if v == int(v) else v
        for k, t in table.items():
            if t[0] == v: return k, t
        # custom volume: allow any transfer list, mirror the large-container pattern
        amts = [a for a in (5, 10, 15, 20, 25, 30, 50, 60, 100, 120, 180, 300) if a <= v] or [5]
        if v not in amts: amts.append(v)
        return 'custom%g' % v, ((v, amts, False) if what == 'beaker' else (v, amts))
    raise ValueError('unknown %s %r; known: %s (or give a volume number)' % (what, key, ', '.join(table)))

class Gear:
    """The borg's reagent hardware. Everything is a parameter so sub-formulas / future items just work.
       beaker        : payload beaker (the one the foam/smoke reaction fires in)   name or volume
       syringe       : onboard syringe (trigger carrier) name or volume            (ignored when trigger_beaker is set)
       trigger_beaker: None -> syringe mode.  A beaker name/volume -> TWO-BEAKER mode: the trigger is built in this
                       second beaker (secondary beaker apparatus upgrade) and poured into `beaker`.
       Medical-only upgrades in game: bluespace/piercing syringe, secondary beaker apparatus."""
    def __init__(self, beaker='large', syringe='standard', trigger_beaker=None):
        self.bname, (self.beaker, self.bamts, self.b_noreact) = _pick(BEAKER_TYPES, beaker, 'beaker')
        self.sname, (self.syringe, self.samts) = _pick(SYRINGE_TYPES, syringe, 'syringe')
        self.two = trigger_beaker is not None
        if self.two:
            self.tname, (self.tbeaker, self.tamts, self.t_noreact) = _pick(BEAKER_TYPES, trigger_beaker, 'beaker')
        else:
            self.tname, self.tbeaker, self.tamts, self.t_noreact = None, 0, [], False
    @property
    def trigger_vol(self):
        """most the trigger carrier can hold"""
        return self.tbeaker if self.two else self.syringe
    @property
    def trigger_amts(self):
        return self.tamts if self.two else self.samts
    def default_trigger_units(self):
        """syringe: it is drawn full. two-beaker: 15u (same as a stock syringe) unless told otherwise"""
        return self.syringe if not self.two else min(15, self.tbeaker)
    def describe(self):
        if self.two:
            return 'payload beaker %s (%gu) + trigger beaker %s (%gu), pour trigger into payload' % (self.bname, self.beaker, self.tname, self.tbeaker)
        return 'payload beaker %s (%gu) + %s syringe (%gu)' % (self.bname, self.beaker, self.sname, self.syringe)

def dispenser_lists(db):
    return db.dispensers

def click_plan(units):
    """fewest dispenser clicks to deliver `units` (multiple of 5)"""
    best = {0: []}
    for u in range(5, units + 1, 5):
        cand = None
        for a in DISP_AMOUNTS:
            if a <= u and (u - a) in best:
                p = best[u - a] + [a]
                if cand is None or len(p) < len(cand): cand = p
        best[u] = cand
    return best.get(units)

class Rig:
    """a borg's working set: internal beaker, onboard syringe, a dispenser, optional heater"""
    def __init__(self, db, tier=1, reverse=False, gear=None):
        self.db = db; self.sim = Sim(db, reverse_same_primary=reverse)
        self.gear = gear or Gear()
        g = self.gear
        self.beaker = Holder(self.sim, 'payload beaker' if g.two else 'beaker', g.beaker, Holder.NO_REACT if g.b_noreact else 0)
        # trigger carrier: the syringe, or (two-beaker mode) the second beaker.  `.syringe` stays as the alias.
        self.syringe = Holder(self.sim, 'trigger beaker' if g.two else 'syringe', g.trigger_vol,
                              Holder.NO_REACT if g.t_noreact else 0)
        self.trigger = self.syringe
        self.active = self.beaker          # which beaker is currently in the dispenser (two-beaker mode: see swap())
        lists = dispenser_lists(db)
        self.avail = set(sum([lists[t] for t in range(1, tier + 1)], []))
        self.steps = []   # (text, state-after, notes)

    def _snap(self, text, notes=None):
        nlog = self.sim.log[:]; self.sim.log.clear()
        self.steps.append({'text': text, 'beaker': self.beaker.describe(), 'syringe': self.syringe.describe(),
                           'beaker_temp': round(self.beaker.temp), 'log': nlog, 'notes': notes or []})

    def dispense(self, reagent, units):
        p = self.db.find_reagent(reagent)
        if p not in self.avail:
            raise ValueError('%s is not dispensable at this dispenser tier' % self.db.name(p))
        if units % 5: raise ValueError('dispenser can only deliver multiples of 5u')
        tgt = self.active
        clicks = click_plan(units)
        for a in clicks:
            to_disp = max(0, min(a, tgt.max - tgt.total))
            if to_disp < a: self.sim.warnings.append('%s full: dispenser click of %du was clamped to %du' % (tgt.name, a, to_disp))
            tgt.add_reagent(p, to_disp, chemlib.DEFAULT_TEMP)
        ct = {}
        for a in clicks: ct[a] = ct.get(a, 0) + 1
        how = ' + '.join('%d click%s at %du' % (n, 's' if n > 1 else '', a) for a, n in sorted(ct.items(), reverse=True))
        self._snap('Dispenser: %du %s%s  (%s)' % (units, self.db.name(p), (' into the ' + tgt.name) if self.gear.two else '', how))

    def add(self, reagent, units, source=None):
        """an ingredient that is NOT from the chem dispenser (a donor bottle, a syringe of someone's blood...).  Any amount."""
        p = self.db.find_reagent(reagent)
        tgt = self.active
        to_add = max(0, min(units, tgt.max - tgt.total))
        if to_add < units: self.sim.warnings.append('%s full: outside supply of %gu was clamped to %gu' % (tgt.name, units, to_add))
        tgt.add_reagent(p, to_add, chemlib.DEFAULT_TEMP)
        self._snap('Outside supply: put %gu %s into the %s%s' % (units, self.db.name(p), tgt.name, (' (' + source + ')') if source else ''))

    def draw(self, units=None):
        if self.gear.two: raise ValueError('two-beaker mode has no syringe; use swap/inject (pour)')
        units = units or self.gear.syringe
        if units not in self.gear.samts:
            raise ValueError('syringe transfer amounts are %s, not %s' % (self.gear.samts, units))
        got = self.beaker.trans_to(self.syringe, units)
        self._snap('Syringe: draw %du from the beaker (got %.2fu)' % (units, got or 0))

    def spill(self):
        left = self.beaker.describe()
        self.beaker.clear(); self.beaker.temp = 150.0
        self._snap('Beaker: spill/empty the rest', notes=['discarded: ' + left])

    def heat(self, kelvin, coeff=0.05):
        """chem_heater.dm process(): each tick adjust_thermal_energy((target-T)*coeff*dt*SH*volume) then handle_reactions().
        That is dT = (target-T)*coeff*dt.  Step dt=1s; report when the first reaction fires and when target is reached."""
        b = self.beaker; t = 0; fired = None
        while abs(kelvin - b.temp) > 1 and t < 600:
            b.temp += (kelvin - b.temp) * coeff * 1.0
            t += 1
            n = len(self.sim.log)
            b.handle_reactions()
            if fired is None and len(self.sim.log) > n:
                fired = (t, round(b.temp))
        if abs(kelvin - b.temp) <= 1: b.temp = float(kelvin)
        msg = 'Heater: set target %dK, put the beaker in' % kelvin
        if fired: msg += ' - the reaction fires after ~%ds (beaker ~%dK); you can take it out then' % fired
        msg += ' [heater speed %.2f]' % coeff
        self._snap(msg)

    def swap(self):
        """two-beaker mode: switch which beaker sits in the dispenser (right-click the machine with the apparatus to eject/stash)"""
        if not self.gear.two: raise ValueError('swap only exists in two-beaker mode')
        self.active = self.beaker if self.active is self.syringe else self.syringe
        self._snap('Switch beakers: put the %s in the dispenser (apparatus right-click on the machine ejects/stashes the other)' % self.active.name)

    def inject(self):
        g = self.gear
        total = self.syringe.total
        if g.two:
            # one pour click moves `amount_per_transfer_from_this`; set it >= the trigger beaker's contents (cup/interact_with_atom)
            if not any(a >= total - 1e-9 for a in g.tamts):
                raise ValueError('trigger beaker holds %.0fu but its largest pour is %du: it would need several pours (the first one would already react)'
                                 % (total, max(g.tamts)))
            amt = min(a for a in g.tamts if a >= total - 1e-9)
            n = self.syringe.trans_to(self.beaker, amt)
            if self.syringe.total > 0.05:
                self.sim.warnings.append('payload beaker overflowed: %.1fu of the trigger stayed behind' % self.syringe.total)
            self._snap('Beaker: set pour amount %du and pour the whole trigger beaker into the payload beaker  <-- TRIGGER' % amt)
        else:
            if not any(a >= total - 1e-9 for a in g.samts):
                raise ValueError('syringe transfer amounts %s cannot inject %.0fu in one go' % (g.samts, total))
            amt = min(a for a in g.samts if a >= total - 1e-9)
            n = self.syringe.trans_to(self.beaker, amt)
            if self.syringe.total > 0.05:
                self.sim.warnings.append('payload beaker overflowed: %.1fu stayed in the syringe' % self.syringe.total)
            self._snap('Syringe: set transfer %du, inject all %.0fu into the beaker  <-- TRIGGER' % (amt, n or 0))

def run(db, proc, tier=1, reverse=False, gear=None):
    """proc: list of ('dispense', reagent, units) | ('draw',[units]) | ('spill',) | ('swap',) | ('heat', K) | ('inject',)"""
    rig = Rig(db, tier, reverse, gear)
    for st in proc:
        op = st[0]
        if op == 'dispense': rig.dispense(st[1], st[2])
        elif op == 'draw': rig.draw(st[1] if len(st) > 1 else None)
        elif op == 'swap': rig.swap()
        elif op == 'spill': rig.spill()
        elif op == 'add': rig.add(st[1], st[2], st[3] if len(st) > 3 else None)
        elif op == 'heat': rig.heat(st[1])
        elif op == 'inject': rig.inject()
        else: raise ValueError(op)
    return rig

def effects_summary(rig):
    out = []
    for e in rig.sim.effects:
        if e['kind'] in ('foam', 'smoke'):
            out.append(e)
    return out
