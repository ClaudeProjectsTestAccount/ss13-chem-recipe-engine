import unittest
from helpers import load_db, planner, chemlib
import chemcli, book

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
        rig = run(self.db, FACID20 + [('dispense', 'aluminium', 100)])
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

FACID20 = [('dispense', 'sulfuric acid', 5), ('dispense', 'fluorine', 5), ('dispense', 'hydrogen', 25), ('dispense', 'potassium', 5), ('heat', 400), ('dispense', 'lithium', 20)]

class RecipeTable(unittest.TestCase):
    """every recipe in the book still simulates and gives the headline numbers the page promises"""
    def setUp(self): self.db = load_db(); self.book = {r['id']: r for r in book.load_book()}

    def build(self, rid):
        r = self.book[rid]
        return r, run(self.db, [tuple(o) for o in r['ops']], book.gear_of(r))

    def test_all_recipes_run_without_unmodeled_effects_or_warnings(self):
        for rid, r in self.book.items():
            if r.get('group') == 'chem': continue          # plain chemicals have their own tests (test_chemplan.py)
            rig = run(self.db, [tuple(o) for o in r['ops']], book.gear_of(r))
            self.assertEqual(effects(rig, 'UNMODELED'), [], rid)
            self.assertEqual(effects(rig, 'HAZARD'), [], rid)
            self.assertTrue(rig.sim.effects, rid)
            self.assertEqual([w for w in rig.sim.warnings if 'clamped' not in w], [], rid)   # a clamped click is how some recipes hit an exact amount

    def test_headline_numbers(self):
        want = {'metal-foam-100': ('foam', 100), 'iron-foam-100': ('foam', 100), 'metal-foam-xl-300': ('foam', 200),
                'drying-foam-100-15': ('foam', 30), 'carpet-foam-100-15': ('foam', 30), 'black-carpet-foam-100-15': ('foam', 30),
                'carpet-foam-xl-300-60': ('foam', 120), 'libital-fog-100-15': ('smoke', 45), 'aiuri-fog-100-15': ('smoke', 45),
                'cleaner-smoke-300-60': ('smoke', 180), 'lube-foam-300-60': ('foam', 120), 'hellfoam-300-60': ('foam', 80)}
        for rid, (kind, tiles) in want.items():
            r, rig = self.build(rid)
            tot = sum(e['tiles'] for e in effects(rig, kind)); self.assertEqual(tot, tiles, rid)

    def test_structure_foams_leave_no_acid(self):
        facid = self.db.find_reagent('fluorosulfuric acid')
        for rid in ('metal-foam-100', 'metal-foam-xl-300', 'iron-foam-100', 'iron-foam-xl-300'):
            r, rig = self.build(rid)
            for f in effects(rig, 'foam'): self.assertNotIn(facid, f['tile'], rid)

    def test_carpet_types(self):
        r, rig = self.build('carpet-foam-100-15')
        self.assertIn(self.db.find_reagent('carpet'), effects(rig, 'foam')[0]['tile'])
        r, rig = self.build('black-carpet-foam-100-15')
        t = effects(rig, 'foam')[0]['tile']
        self.assertIn(self.db.find_reagent('black carpet'), t); self.assertNotIn(self.db.find_reagent('carpet'), t)

    def test_fog_doses(self):
        r, rig = self.build('libital-fog-100-15'); t = effects(rig, 'smoke')[0]['tile']
        self.assertAlmostEqual(t[self.db.find_reagent('libital')], 30)
        r, rig = self.build('aiuri-fog-100-15'); t = effects(rig, 'smoke')[0]['tile']
        self.assertAlmostEqual(t[self.db.find_reagent('aiuri')], 20)

    def test_smart_foam_needs_smart_agent_before_aluminium(self):
        r = self.book['smart-foam-300']
        ops = [tuple(o) for o in r['ops'] if tuple(o) != ('dispense', 'aluminium', 100)]
        ops.insert(5, ('dispense', 'aluminium', 100))              # aluminium too early: plain metal foam fires instead
        rig = run(self.db, ops, planner.Gear('bluespace'))
        self.assertEqual(effects(rig, 'foam')[0]['reaction'], 'metalfoam')

    def test_metal_in_before_lithium_beats_metal_last(self):
        """one dispenser click is at most 100u, so metal last caps the reaction; metal first and lithium last does not"""
        g = planner.Gear('bluespace'); base = FACID20[:4] + [('dispense', 'hydrogen', 0)][:0]
        acid = [('dispense', 'sulfuric acid', 15), ('dispense', 'fluorine', 15), ('dispense', 'hydrogen', 65), ('dispense', 'potassium', 15), ('heat', 400)]
        first = run(self.db, acid + [('dispense', 'aluminium', 140), ('dispense', 'lithium', 50)], g)
        last = run(self.db, acid + [('dispense', 'lithium', 50), ('dispense', 'aluminium', 140)], g)
        tiles = lambda rig: sum(e['tiles'] for e in effects(rig, 'foam'))
        self.assertGreater(tiles(first), tiles(last))

if __name__ == '__main__':
    unittest.main()
