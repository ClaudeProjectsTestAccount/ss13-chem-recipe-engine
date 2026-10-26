import unittest
from helpers import load_db, planner, chemlib
import chemcli, recipes, export_recipes

def run(db, ops, gear=None):
    return chemcli._run(db, ops, 1, False, gear)

def effects(rig, kind): return [e for e in rig.sim.effects if e['kind'] == kind]

class DecomposeBlood(unittest.TestCase):
    def test_self_catalytic_blood_loop_is_not_a_source(self):
        db = load_db(); avail = set(planner.Rig(db, 4).avail)
        self.assertIsNone(chemcli.decompose(db, db.find_reagent('blood'), avail))
        self.assertIsNone(chemcli.decompose(db, db.find_reagent('carpet'), avail))     # needs blood
        self.assertIsNotNone(chemcli.decompose(db, db.find_reagent('drying agent'), avail))

class Handlers(unittest.TestCase):
    def setUp(self): self.db = load_db()

    def test_metal_foam_is_five_tiles_per_mult_and_clears_the_beaker(self):
        rig = run(self.db, recipes.FACID20 + [('dispense', 'aluminium', 100)])
        f = effects(rig, 'foam'); self.assertEqual(len(f), 1)
        self.assertEqual(f[0]['tiles'], 100)                          # mult 20 * 5
        self.assertAlmostEqual(rig.beaker.total, 0)
        self.assertNotIn(self.db.find_reagent('fluorosulfuric acid'), f[0]['tile'])   # no acid left in the foam
        self.assertEqual(effects(rig, 'UNMODELED'), [])

    def test_sorium_range_is_capped_at_six(self):
        rig = run(self.db, [('dispense', 'mercury', 10), ('dispense', 'oxygen', 10), ('dispense', 'nitrogen', 10), ('dispense', 'carbon', 10)])
        v = effects(rig, 'vortex')[0]
        self.assertEqual(v['mode'], 'push'); self.assertEqual(v['range'], 6); self.assertGreater(v['raw_range'], 6)
        small = run(self.db, [('dispense', 'mercury', 5), ('dispense', 'oxygen', 5), ('dispense', 'nitrogen', 5), ('dispense', 'carbon', 5)])
        self.assertAlmostEqual(effects(small, 'vortex')[0]['range'], 20 ** 0.5)       # sqrt(4*5)

    def test_ldm_pulls(self):
        rig = run(self.db, [('dispense', 'stable plasma', 15), ('dispense', 'radium', 15), ('dispense', 'carbon', 15)])
        self.assertEqual(effects(rig, 'vortex')[0]['mode'], 'pull')

    def test_stabilizing_agent_stops_the_vortex(self):
        rig = run(self.db, [('add', 'stabilizing agent', 5), ('dispense', 'mercury', 10), ('dispense', 'oxygen', 10), ('dispense', 'nitrogen', 10), ('dispense', 'carbon', 10)])
        self.assertEqual(effects(rig, 'vortex'), [])

    def test_life_spawn_upper_bound_scales_with_beaker(self):
        ops = [('add', 'strange reagent', 90), ('add', 'synthflesh', 90), ('dispense', 'sugar', 90), ('heat', 380)]
        m = effects(run(self.db, ops, planner.Gear('bluespace')), 'mobspawn')[0]
        self.assertEqual(m['max'], 3); self.assertTrue(m['friendly'])
        small = [('add', 'strange reagent', 30), ('add', 'synthflesh', 30), ('dispense', 'sugar', 30), ('heat', 380)]
        self.assertEqual(effects(run(self.db, small), 'mobspawn')[0]['max'], 1)

    def test_life_needs_heat(self):
        rig = run(self.db, [('add', 'strange reagent', 30), ('add', 'synthflesh', 30), ('dispense', 'sugar', 30)])
        self.assertEqual(effects(rig, 'mobspawn'), [])

class BloodLoop(unittest.TestCase):
    def test_one_unit_of_seed_blood_multiplies(self):
        db = load_db()
        rig = run(db, [('add', 'blood', 1), ('dispense', 'radium', 5), ('dispense', 'phosphorus', 5), ('dispense', 'chlorine', 5)])
        self.assertAlmostEqual(rig.beaker.amount(db.find_reagent('blood')), 16)       # 1 seed + 15 from the 15u of mutagen
        self.assertAlmostEqual(rig.beaker.amount(db.find_reagent('unstable mutagen')), 0)

    def test_without_the_seed_you_just_get_mutagen(self):
        db = load_db()
        rig = run(db, [('dispense', 'radium', 5), ('dispense', 'phosphorus', 5), ('dispense', 'chlorine', 5)])
        self.assertAlmostEqual(rig.beaker.amount(db.find_reagent('blood')), 0)
        self.assertAlmostEqual(rig.beaker.amount(db.find_reagent('unstable mutagen')), 15)

class AddOp(unittest.TestCase):
    def test_add_ignores_the_dispenser_but_respects_capacity(self):
        db = load_db()
        rig = planner.run(db, [('add', 'holy water', 30, 'donor')], 1, False, planner.Gear('beaker'))
        self.assertAlmostEqual(rig.beaker.total, 30)
        rig = planner.run(db, [('add', 'holy water', 80, 'donor')], 1, False, planner.Gear('beaker'))
        self.assertAlmostEqual(rig.beaker.total, 50); self.assertTrue(rig.sim.warnings)

    def test_parse_ops_add(self):
        self.assertEqual(chemcli.parse_ops('add strange reagent 90'), [('add', 'strange reagent', 90.0)])

class RecipeTable(unittest.TestCase):
    """every shipped recipe still simulates and gives the headline numbers the docs promise"""
    def setUp(self): self.db = load_db()

    def build(self, key):
        r = [x for x in recipes.EXTRA if x['key'] == key][0]
        g = export_recipes.gear_of(r['gear'])
        return r, run(self.db, r['ops'], g)

    def test_all_new_recipes_run_without_unmodeled_effects(self):
        for r in recipes.EXTRA:
            rig = run(self.db, r['ops'], export_recipes.gear_of(r['gear']))
            self.assertEqual(effects(rig, 'UNMODELED'), [], r['key'])
            self.assertTrue(rig.sim.effects, r['key'])

    def test_headline_numbers(self):
        want = {'metal-foam': ('foam', 100), 'metal-foam-xl': ('foam', 200), 'iron-foam': ('foam', 100), 'smart-foam': ('foam', 100),
                'drying-foam': ('foam', 30), 'carpet-foam': ('foam', 30), 'black-carpet-foam': ('foam', 30), 'carpet-foam-xl': ('foam', 120),
                'libital-fog': ('smoke', 45), 'aiuri-fog': ('smoke', 45)}
        for key, (kind, tiles) in want.items():
            r, rig = self.build(key)
            e = effects(rig, kind); self.assertEqual(len(e), 1, key); self.assertEqual(e[0]['tiles'], tiles, key)

    def test_structure_foams_leave_no_acid(self):
        facid = self.db.find_reagent('fluorosulfuric acid')
        for key in ('metal-foam', 'metal-foam-xl', 'iron-foam', 'smart-foam'):
            r, rig = self.build(key)
            self.assertNotIn(facid, effects(rig, 'foam')[0]['tile'], key)

    def test_carpet_types(self):
        r, rig = self.build('carpet-foam')
        self.assertIn(self.db.find_reagent('carpet'), effects(rig, 'foam')[0]['tile'])
        r, rig = self.build('black-carpet-foam')
        t = effects(rig, 'foam')[0]['tile']
        self.assertIn(self.db.find_reagent('black carpet'), t); self.assertNotIn(self.db.find_reagent('carpet'), t)

    def test_fog_doses(self):
        r, rig = self.build('libital-fog'); t = effects(rig, 'smoke')[0]['tile']
        self.assertAlmostEqual(t[self.db.find_reagent('libital')], 30)
        r, rig = self.build('aiuri-fog'); t = effects(rig, 'smoke')[0]['tile']
        self.assertAlmostEqual(t[self.db.find_reagent('aiuri')], 20)

    def test_smart_foam_needs_smart_agent_before_aluminium(self):
        r = [x for x in recipes.EXTRA if x['key'] == 'smart-foam'][0]
        ops = [o for o in r['ops'] if o != ('dispense', 'aluminium', 100)]
        ops.insert(5, ('dispense', 'aluminium', 100))              # aluminium too early: plain metal foam fires instead
        rig = run(self.db, ops, planner.Gear('bluespace'))
        self.assertEqual(effects(rig, 'foam')[0]['reaction'], 'metalfoam')

    def test_docs_are_up_to_date(self):
        import os
        with open(os.path.join(os.path.dirname(export_recipes.HERE), 'docs', 'RECIPES.md')) as fh:
            self.assertEqual(fh.read(), export_recipes.build())

if __name__ == '__main__':
    unittest.main()
