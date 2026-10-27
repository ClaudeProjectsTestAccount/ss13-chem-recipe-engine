"""exact ingredient amounts, hellfoam designer, payload builder, order-sensitive slick check, supporting chemicals, floor safety"""
import os, sys, unittest
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'src'))
import chemlib, stoich, tileapply as ta, hellfoam as hf, payload, book, chemcli, statspanel as sp

DB = chemlib.DB(json_path=os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'src', 'chemdata.json'))
AV = set(DB.dispensers[1])
def P(n): return DB.find_reagent(n)

class TestStoich(unittest.TestCase):
    def test_quanta(self):
        for name, q in (('lube', 20), ('drying agent', 15), ('napalm', 45), ('phlogiston', 15), ('chloral hydrate', 5), ('libital', 135), ('aiuri', 60)):
            self.assertEqual(stoich.quantum(DB, AV, P(name)), q, name)

    def test_exact_amounts_leave_nothing(self):
        for name, amt in (('napalm', 90), ('libital', 135), ('aiuri', 60), ('lube', 40), ('fluorosulfuric acid', 60)):
            ops = stoich.ops(DB, AV, P(name), amt)
            if stoich.plan(DB, AV, P(name), amt)['heat']: ops = ops + [('heat', 400)]
            rig = chemcli._run(DB, ops, 1, False, __import__('planner').Gear('bluespace'))
            left = {DB.name(k): round(v[0], 1) for k, v in rig.beaker.r.items() if k != P(name)}
            self.assertEqual(left, {}, '%s %d leaves %s' % (name, amt, left))
            self.assertAlmostEqual(rig.beaker.amount(P(name)), amt, places=1)

    def test_inexact_amount_is_refused(self):
        self.assertIsNone(stoich.ops(DB, AV, P('libital'), 30))

class TestSlip(unittest.TestCase):
    def test_window(self):
        for tiles in (10, 20, 80, 120):
            lube, dry = hf.slip_package(DB, tiles)
            s = ta.slick_sim('foam', tiles, {'/datum/reagent/lube': lube * 3.2, '/datum/reagent/drying_agent': dry * 3.2})['total_s']
            self.assertTrue(hf.SLICK_MIN <= s <= hf.SLICK_GOAL, (tiles, s))
        self.assertIsNone(hf.slip_package(DB, 30))             # the 15u drying step skips over the window at 30 tiles

    def test_drying_before_lube_is_not_the_same(self):
        L, D = '/datum/reagent/lube', '/datum/reagent/drying_agent'
        good = ta.slick_sim('foam', 20, {L: 64, D: 48})['total_s']; bad = ta.slick_sim('foam', 20, {D: 48, L: 64})['total_s']
        self.assertLess(good, 15); self.assertGreater(bad, 15)

    def test_signature_sees_wet_order(self):
        a = chemcli.signature(chemcli._run(DB, [('dispense', 'fluorine', 10), ('dispense', 'carbon', 10), ('dispense', 'sulfuric acid', 5), ('draw', 10), ('spill',),
              ('dispense', 'water', 5), ('dispense', 'silicon', 5), ('dispense', 'oxygen', 5), ('dispense', 'stable plasma', 10), ('dispense', 'ethanol', 5), ('dispense', 'sodium', 5), ('dispense', 'water', 10), ('inject',)], 1, False, __import__('planner').Gear('large', 'standard')))
        b = chemcli.signature(chemcli._run(DB, [('dispense', 'fluorine', 10), ('dispense', 'carbon', 10), ('dispense', 'sulfuric acid', 5), ('draw', 10), ('spill',),
              ('dispense', 'stable plasma', 10), ('dispense', 'ethanol', 5), ('dispense', 'sodium', 5), ('dispense', 'water', 5), ('dispense', 'silicon', 5), ('dispense', 'oxygen', 5), ('dispense', 'water', 10), ('inject',)], 1, False, __import__('planner').Gear('large', 'standard')))
        self.assertNotEqual(a, b)

class TestSupport(unittest.TestCase):
    def test_stabilizer_is_not_wasted_when_phlogiston_is_there(self):
        tile = {P('stabilizing agent'): 48.0, P('phlogiston'): 48.0}
        self.assertIn(P('stabilizing agent'), ta.supported(tile))
        self.assertNotIn(P('stabilizing agent'), ta.supported({P('stabilizing agent'): 48.0}))

    def test_floor_safety(self):
        self.assertTrue(ta.floor_safety('foam', 20, {P('fluorosulfuric acid'): 100.0, P('napalm'): 96.0})['safe'])
        self.assertFalse(ta.floor_safety('foam', 20, {P('thermite'): 800.0})['safe'])

class TestDesigner(unittest.TestCase):
    def test_design_passes_the_engine(self):
        d = hf.design(DB, 100, 15, 'fire-sleep', 10)[0]
        spec, comp, bad = hf.spec_for(DB, d, 100, 15)
        self.assertEqual(bad, [])
        st = comp['stats']; self.assertFalse(st['broken']); self.assertTrue(st['exp']['floor_safety']['safe'])
        self.assertTrue(hf.SLICK_MIN <= st['exp']['slick']['total'] <= 15)

    def test_every_design_is_exact(self):
        for beaker in (100, 300):
            for d in hf.design(DB, beaker, 15, 'all', 10, slip=False)[:2]:
                for b, a in d['blocks'].items(): self.assertEqual(a % hf.quantum(DB, b), 0, (b, a))

    def test_payload_builder(self):
        spec, comp, bad = payload.build(DB, 100, 15, 'smoke', 10, [('aiuri', 60)], 'aiuri', base=dict(type='med', title='t', what='w', harm='caution'))
        self.assertEqual(bad, []); self.assertEqual(comp['summary']['tiles'], 30); self.assertEqual(comp['summary']['per_tile'], 60.0)

if __name__ == '__main__':
    unittest.main()
