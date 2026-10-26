"""
verify_independent.py - closed-form arithmetic for the final recipes, written WITHOUT chemlib
(only numbers I transcribed by hand from the .dm files). If the engine disagrees, one of them is wrong.
"""
import math, sys
import chemlib, planner

def rnd(x): return math.floor(x + 0.5)            # BYOND round(x)

def react(stock, need, make, times=None):
    """one instant reaction pass, exactly instant_react(): mult = min(round(have/ratio)); clamp removals"""
    m = min(rnd(stock.get(k, 0) / v) for k, v in need.items())
    if m <= 0: return 0
    for k, v in need.items(): stock[k] = max(0.0, stock.get(k, 0) - m * v)
    for k, v in make.items(): stock[k] = stock.get(k, 0) + m * v
    return m

SURF = ({'F': 2, 'C': 2, 'acid': 1}, {'surf': 5})
AMM = ({'H': 3, 'N': 1}, {'nh3': 3})
CLEAN = ({'nh3': 1, 'water': 1}, {'cleaner': 2})
LUBE = ({'water': 1, 'Si': 1, 'O': 1}, {'lube': 4})
FACID = ({'acid': 1, 'F': 1, 'H': 1, 'K': 1}, {'facid': 4})
SMOKE = ({'K': 1, 'sugar': 1, 'P': 1}, {'powder': 3})

def foam_tile(stock, mult_units):
    """foam: consumes surfactant1+water1 per mult; tiles = 2*mult; every tile = leftover * 3.2"""
    m = min(rnd(stock['surf'] / 1), rnd(stock['water'] / 1))
    stock['surf'] -= m; stock['water'] -= m
    return 2 * m, {k: round(v * 3.2, 4) for k, v in stock.items() if v > 0.05}

expected = {}
# --- syringe: F10 C10 acid5 -> 25 surfactant, draw 15 of it
s = {'F': 10, 'C': 10, 'acid': 5}; react(s, *SURF); assert abs(s['surf'] - 25) < 1e-9
syr = 15.0   # pure surfactant, draw is 15 of 25

# --- 1. cleaner foam (tier 1): H30 N10 water45
b = {'H': 30, 'N': 10}; react(b, *AMM); b['water'] = 45; react(b, *CLEAN)
b['surf'] = syr
tiles, tile = foam_tile(b, 15)
expected['cleaner foam'] = (tiles, tile.get('cleaner', 0))
# --- 1b. cleaner foam lean: H15 N5 water30
b = {'H': 15, 'N': 5}; react(b, *AMM); b['water'] = 30; react(b, *CLEAN); b['surf'] = syr
t2, tile2 = foam_tile(b, 15); expected['cleaner foam (lean)'] = (t2, tile2.get('cleaner', 0))
# --- 2. lube foam: water30 Si15 O15
b = {'water': 30, 'Si': 15, 'O': 15}; react(b, *LUBE); b['surf'] = syr
t3, tile3 = foam_tile(b, 15); expected['lube foam'] = (t3, tile3.get('lube', 0))
# --- 3. lube smoke: beaker water10 Si10 O10 -> lube; + K15 sugar15; syringe P15
b = {'water': 10, 'Si': 10, 'O': 10}; react(b, *LUBE); b.update({'K': 15, 'sugar': 15, 'P': 15})
m = react(b, *SMOKE); expected['lube smoke'] = (3 * m, b['lube'])
# --- 4. cleaner smoke: H15 N5 water15 K15 sugar15 + P15
b = {'H': 15, 'N': 5}; react(b, *AMM); b['water'] = 15; react(b, *CLEAN); b.update({'K': 15, 'sugar': 15, 'P': 15})
m = react(b, *SMOKE); expected['cleaner smoke'] = (3 * m, b['cleaner'])
# --- 5. hellfoam: acid15 F15 H15 K15 -> (>=380K) 60 facid, + water15
b = {'acid': 15, 'F': 15, 'H': 15, 'K': 15}; react(b, *FACID); b['water'] = 15; b['surf'] = syr
t5, tile5 = foam_tile(b, 15); expected['hellfoam'] = (t5, tile5.get('facid', 0))

print('closed-form expectations:'); [print('  %-22s tiles=%s payload/tile=%s' % (k, v[0], v[1])) for k, v in expected.items()]

# --- compare with the engine
db = chemlib.DB(); R = db.find_reagent
SYR = [('dispense', 'fluorine', 10), ('dispense', 'carbon', 10), ('dispense', 'sulfuric acid', 5), ('draw', 15), ('spill',)]
PH = [('dispense', 'phosphorus', 15), ('draw', 15), ('spill',)]
cases = {
 'cleaner foam': (SYR + [('dispense', 'hydrogen', 30), ('dispense', 'nitrogen', 10), ('dispense', 'water', 45), ('inject',)], 'space cleaner', 1),
 'cleaner foam (lean)': (SYR + [('dispense', 'hydrogen', 15), ('dispense', 'nitrogen', 5), ('dispense', 'water', 30), ('inject',)], 'space cleaner', 1),
 'lube foam': (SYR + [('dispense', 'water', 30), ('dispense', 'silicon', 15), ('dispense', 'oxygen', 15), ('inject',)], 'space lube', 1),
 'lube smoke': (PH + [('dispense', 'water', 10), ('dispense', 'silicon', 10), ('dispense', 'oxygen', 10), ('dispense', 'potassium', 15), ('dispense', 'sugar', 15), ('inject',)], 'space lube', 1),
 'cleaner smoke': (PH + [('dispense', 'hydrogen', 15), ('dispense', 'nitrogen', 5), ('dispense', 'water', 15), ('dispense', 'potassium', 15), ('dispense', 'sugar', 15), ('inject',)], 'space cleaner', 1),
 'hellfoam': (SYR + [('dispense', 'sulfuric acid', 15), ('dispense', 'fluorine', 15), ('dispense', 'hydrogen', 15), ('dispense', 'potassium', 15), ('heat', 400), ('dispense', 'water', 15), ('inject',)], 'fluorosulfuric acid', 1),
}
bad = 0
for name, (ops, payload, tier) in cases.items():
    rig = planner.run(db, ops, tier)
    effs = [e for e in rig.sim.effects if e['kind'] in ('foam', 'smoke')]
    ok = len(effs) == 1 and not [e for e in rig.sim.effects if e['kind'] == 'UNMODELED']
    got = (effs[0]['tiles'], effs[0]['tile'].get(R(payload), 0)) if ok else None
    exp = expected[name]
    match = ok and got[0] == exp[0] and abs(got[1] - exp[1]) < 1e-6
    print('%-22s engine=%s  closed-form=%s  -> %s' % (name, got, exp, 'MATCH' if match else 'MISMATCH'))
    bad += (not match)
sys.exit(1 if bad else 0)
