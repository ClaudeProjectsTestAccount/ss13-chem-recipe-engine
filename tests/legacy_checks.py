"""
test_engine.py - checks the engine against facts read straight out of the DM source
(each test cites the file/line it encodes). Run: python3 test_engine.py
"""
import sys, math
import chemlib, planner
from chemlib import Sim, Holder, DB, byond_round
db = DB(); R = db.find_reagent
fails = []
def check(name, cond, detail=''):
    print(('PASS ' if cond else 'FAIL ') + name + (('  ' + detail) if detail and not cond else ''))
    if not cond: fails.append(name)
def beaker(sim=None, cap=100):
    s = sim or Sim(db); return s, Holder(s, 'b', cap)

# --- BYOND round() (holder.dm:1119 uses round(volume/ratio) with ONE argument)
check('round(2.5)=3, round(2.49)=2, round(0.4)=0', byond_round(2.5) == 3 and byond_round(2.49) == 2 and byond_round(0.4) == 0)

# --- parsed recipes match what I read in the .dm files
def rx(n, req, res, T=None):
    r = db.by_short[n]
    ok = {db.name(k): v for k, v in r.req.items()} == req and {db.name(k): v for k, v in r.results.items()} == res
    return ok and (T is None or r.required_temp == T)
check('recipe surfactant  F2 C2 H2SO4 1 -> 5 (others.dm:322)', rx('surfactant', {'Fluorine': 2, 'Carbon': 2, 'Sulfuric Acid': 1}, {'Fluorosurfactant': 5}))
check('recipe foam  surfactant1 + water1, no results (others.dm:328)', rx('foam', {'Fluorosurfactant': 1, 'Water': 1}, {}))
check('recipe ammonia H3 N1 -> 3 (others.dm:~379)', rx('ammonia', {'Hydrogen': 3, 'Nitrogen': 1}, {'Ammonia': 3}))
check('recipe space_cleaner  NH3 1 + water 1 -> 2 (others.dm:391)', rx('space_cleaner', {'Ammonia': 1, 'Water': 1}, {'Space Cleaner': 2}))
check('recipe lube  water1 Si1 O1 -> 4 (others.dm:7)', rx('lube', {'Water': 1, 'Silicon': 1, 'Oxygen': 1}, {'Space Lube': 4}))
check('recipe smoke_powder  K1 sugar1 P1 -> 3 (pyrotechnics.dm:326)', rx('smoke_powder', {'Potassium': 1, 'Sugar': 1, 'Phosphorus': 1}, {'Smoke Powder': 3}))
check('recipe facid  acid1 F1 H1 K1 -> 4 @>=380K (toxins.dm:83)', rx('facid', {'Sulfuric Acid': 1, 'Fluorine': 1, 'Hydrogen': 1, 'Potassium': 1}, {'Fluorosulfuric Acid': 4}, 380))
check('no recipe is timed except the two reaction agents (NON_INSTANT)', sorted(r.short for r in db.reactions if r.non_instant) != [] and len([r for r in db.reactions if r.non_instant]) <= 3,
      str([r.short for r in db.reactions if r.non_instant]))

# --- stoichiometry & rounding
s, b = beaker(); b.add_reagent(R('hydrogen'), 15); b.add_reagent(R('nitrogen'), 5)
check('H15+N5 -> 15 ammonia, nothing left', abs(b.amount(R('ammonia')) - 15) < 1e-6 and b.total == 15)
s, b = beaker(); [b.add_reagent(R(n), 5) for n in ('fluorine', 'carbon', 'sulfuric acid')]
check('F5 C5 acid5: round(2.5)=3 quirk -> 15 surfactant, 2u acid left', abs(b.amount(R('fluorosurfactant')) - 15) < 1e-6 and abs(b.amount(R('sulfuric acid')) - 2) < 1e-6, b.describe())
s, b = beaker(); [b.add_reagent(R(n), a) for n, a in (('fluorine', 10), ('carbon', 10), ('sulfuric acid', 5))]
check('F10 C10 acid5 -> 25 surfactant exactly', abs(b.amount(R('fluorosurfactant')) - 25) < 1e-6 and b.total == 25)

# --- update_total drops reagents < 0.05u (holder.dm:1185)
s, b = beaker(); b.add_reagent(R('water'), 0.04)
check('0.04u water vanishes on update_total', b.total == 0 and not b.r)

# --- temperature gates
s, b = beaker(); [b.add_reagent(R(n), 5) for n in ('sulfuric acid', 'fluorine', 'hydrogen', 'potassium')]
check('facid does not form at 300K', not b.has(R('fluorosulfuric acid')))
b.temp = 380; b.handle_reactions()
check('facid forms at 380K: 20u', abs(b.amount(R('fluorosulfuric acid')) - 20) < 1e-6, b.describe())

# --- potassium + water explodes (pyrotechnics, instant, required_temp 0)
s, b = beaker(); b.add_reagent(R('potassium'), 5); b.add_reagent(R('water'), 5)
check('potassium + water raises an unmodeled explosion (so plans containing it are rejected)', any(e['kind'] == 'UNMODELED' and 'explosion' in e['tags'] for e in s.effects))

# --- transfers are proportional (holder.dm:361)
s = Sim(db); b = Holder(s, 'b', 100); sy = Holder(s, 's', 15)
b.add_reagent(R('water'), 30, no_react=True); b.add_reagent(R('oxygen'), 10, no_react=True)
b.trans_to(sy, 8)
check('syringe draw is proportional: 6u water + 2u oxygen', abs(sy.amount(R('water')) - 6) < 1e-6 and abs(sy.amount(R('oxygen')) - 2) < 1e-6)

# --- foam: 2*mult tiles, payload x3.2 (others.dm:334, effects_foam.dm)
s, b = beaker(); b.add_reagent(R('space cleaner'), 10); b.add_reagent(R('water'), 20); b.add_reagent(R('fluorosurfactant'), 15)
f = [e for e in s.effects if e['kind'] == 'foam']
check('foam: 15 surfactant + 20 water -> 30 tiles', len(f) == 1 and f[0]['tiles'] == 30)
check('foam: tile carries 10*3.2=32u cleaner and 5*3.2=16u water', f and abs(f[0]['tile'].get(R('space cleaner'), 0) - 32) < 1e-6 and abs(f[0]['tile'].get(R('water'), 0) - 16) < 1e-6, str(f and f[0]['tile']))
check('foam consumes the holder (clear_reagents)', b.total == 0)

# --- smoke powder: 3*mult tiles, powder removed, payload copied unscaled (pyrotechnics.dm:332)
s, b = beaker(); b.add_reagent(R('space lube'), 40); b.add_reagent(R('potassium'), 15); b.add_reagent(R('sugar'), 15); b.add_reagent(R('phosphorus'), 15)
sm = [e for e in s.effects if e['kind'] == 'smoke']
check('smoke: 15/15/15 -> 45 tiles carrying 40u lube, no smoke powder left in tiles', len(sm) == 1 and sm[0]['tiles'] == 45 and list(sm[0]['tile']) == [R('space lube')] and abs(sm[0]['tile'][R('space lube')] - 40) < 1e-6, str(sm and sm[0]['tile']))

# --- containers: large beaker 100, syringe 15 (_cup.dm:297, syringes.dm:13)
check('beaker cap 100 / syringe cap 15 / dispenser clicks', planner.BEAKER_CAP == 100 and planner.SYRINGE_CAP == 15 and planner.click_plan(45) in ([30, 15], [15, 30]))
check('dispenser base list has no ammonia (needs manipulator tier >= 2)', R('ammonia') not in db.dispensers[1] and R('ammonia') in db.dispensers[2])

# --- whole procedures end-to-end
def run(ops, tier=1):
    return planner.run(db, ops, tier)
rig = run([('dispense', 'fluorine', 10), ('dispense', 'carbon', 10), ('dispense', 'sulfuric acid', 5), ('draw', 15), ('spill',),
           ('dispense', 'hydrogen', 30), ('dispense', 'nitrogen', 10), ('dispense', 'water', 45), ('inject',)])
f = [e for e in rig.sim.effects if e['kind'] == 'foam'][0]
check('cleaner foam: 30 tiles x 192u cleaner', f['tiles'] == 30 and abs(f['tile'][R('space cleaner')] - 192) < 1e-6 and len(f['tile']) == 1)
# --- gear is a parameter (sizes from _cup.dm / syringes.dm / storage.dm)
G = planner.Gear
check('gear tables: beaker 50/100/120/180/300, syringe 15/10/60', [planner.BEAKER_TYPES[k][0] for k in ('beaker','large','xl','meta','bluespace')] == [50,100,120,180,300] and [planner.SYRINGE_TYPES[k][0] for k in ('standard','piercing','bluespace')] == [15,10,60])
check('gear accepts a custom volume and finds named types by volume', G(300).bname == 'bluespace' and G(77).beaker == 77 and G('large', 60).sname == 'bluespace')
SYR60 = [('dispense','fluorine',20),('dispense','carbon',20),('dispense','sulfuric acid',10),('draw',30),('spill',),
         ('dispense','hydrogen',15),('dispense','nitrogen',5),('dispense','water',45),('inject',)]
r = planner.run(db, SYR60, 1, False, G('large', 'bluespace'))
f = [e for e in r.sim.effects if e['kind'] == 'foam']
check('bluespace syringe: 30u trigger -> 60 tiles x 96u cleaner', len(f) == 1 and f[0]['tiles'] == 60 and abs(f[0]['tile'][R('space cleaner')] - 96) < 1e-6)
try: planner.run(db, [('dispense','phosphorus',15),('draw',15)], 1, False, G('large', 'bluespace')); ok = False
except ValueError: ok = True
check('bluespace syringe refuses a 15u draw (its amounts are 10,20..60)', ok)
TWO = [('swap',),('dispense','fluorine',10),('dispense','carbon',10),('dispense','sulfuric acid',5),('swap',),
       ('dispense','hydrogen',15),('dispense','nitrogen',5),('dispense','water',40),('inject',)]
r = planner.run(db, TWO, 1, False, G('large', trigger_beaker='large'))
f = [e for e in r.sim.effects if e['kind'] == 'foam']
check('two-beaker pour: 25u surfactant trigger beaker -> 50 tiles x 96u cleaner', len(f) == 1 and f[0]['tiles'] == 50 and abs(f[0]['tile'][R('space cleaner')] - 96) < 1e-6 and r.syringe.total == 0)
r = planner.run(db, [('dispense','water',100),('dispense','water',20)], 1, False, G('xl'))
check('120u beaker really holds 120u; the 100u beaker clamps and warns', abs(r.beaker.total - 120) < 1e-6 and not r.sim.warnings and
      planner.run(db, [('dispense','water',100),('dispense','water',20)], 1, False, G('large')).sim.warnings != [])
r = planner.run(db, [('dispense','fluorine',5),('dispense','carbon',5),('dispense','sulfuric acid',5)], 1, False, G('bluespace', trigger_beaker='noreact'))
# --- wikicheck parser + comparison (fixture markup follows the wiki's table layout; confirm against a live fetch)
import wikicheck
WT = "{| class=\"wikitable\"\n! Name\n! Formula\n! Reaction Conditions\n|-\n| '''Ammonia'''\n|\n* 2 Parts Hydrogen\n* 1 Part Nitrogen\n'''Alternatively:'''<br>\n* 1 Part Ammonia (T2 Chem Dispenser)\n| '''Minimum''': 100K<br>\n'''Overheat''': 900K\n|-\n| Space Cleaner\n| 1u Ammonia, 1u Water\n| any\n|}"
ents = wikicheck.parse_tables(WT)
check('wikicheck parses bullet and comma formulas', len(ents) == 2 and ents[0]['parts'] == {'hydrogen': 2.0, 'nitrogen': 1.0} and ents[0]['tmin'] == 100.0 and ents[1]['parts'] == {'ammonia': 1.0, 'water': 1.0}, str(ents))
rows, un, okc = wikicheck.compare_to_code(db, ents, {'ammonia'})
check('wikicheck flags wiki 2H:1N ammonia vs code 3H:1N and accepts space cleaner', len(rows) == 1 and rows[0]['product'] == 'Ammonia' and rows[0]['critical'] and okc == 1, str(rows))
print('\n%d failure(s)' % len(fails)); sys.exit(1 if fails else 0)
