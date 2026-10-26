import json, os, unittest
from helpers import load_db, planner, chemlib, ROOT
import chemcli, chemplan, book

def run(db, ops, gear):
    return chemcli._run(db, [tuple(o) for o in ops], 1, False, gear)

class Planner(unittest.TestCase):
    def setUp(self): self.db = load_db()

    def plan(self, name, beaker):
        return chemplan.plan(self.db, self.db.find_reagent(name), beaker)

    def test_known_plans(self):
        for name, beaker, made in (('libital', 100, 90), ('libital', 50, 30), ('convermol', 100, 90), ('calomel', 100, 100), ('lube', 100, 100)):
            res = self.plan(name, beaker)
            self.assertAlmostEqual(res['made'], made, msg='%s %s' % (name, beaker))
            self.assertEqual(res['rig'].sim.warnings, [], name)

    def test_dispensable_and_unbuildable_have_no_plan(self):
        self.assertIsNone(self.plan('water', 100))
        self.assertIsNone(self.plan('leporazine', 100))      # needs real plasma as a catalyst, the dispenser only has stable plasma
        self.assertIsNone(self.plan('clonexadone', 100))

    def test_heated_plan_actually_reaches_temperature(self):
        res = self.plan('convermol', 100)
        heats = [o[1] for o in res['ops'] if o[0] == 'heat']
        self.assertTrue(heats and min(heats) >= 370 + 10)

    def test_heater_asymptote_warns_when_setpoint_equals_requirement(self):
        ops = [['dispense', 'hydrogen', 40], ['dispense', 'fluorine', 30], ['dispense', 'welding fuel', 10], ['dispense', 'carbon', 10], ['heat', 370]]
        rig = run(self.db, ops, planner.Gear('large'))
        self.assertTrue(any('heater' in w for w in rig.sim.warnings), rig.sim.warnings)

    def test_plans_are_click_order_robust(self):
        for name in ('libital', 'mutadone', 'oculine', 'epinephrine'):
            res = self.plan(name, 100)
            v = chemcli.verify_orders(self.db, [tuple(o) for o in res['ops']], 1, res['gear'])
            self.assertTrue(v['clicks_order_same'] and v['reverse_index_order_same'], name)

    def test_heat_steps_are_pruned_when_not_needed(self):
        for name in ('calomel', 'convermol', 'oculine'):
            heats = [o for o in self.plan(name, 100)['ops'] if o[0] == 'heat']
            self.assertLessEqual(len(heats), 1, name)

class MetaAndBook(unittest.TestCase):
    def setUp(self): self.db = load_db(); self.meta = chemplan.load_meta()

    def test_every_meta_entry_resolves_and_has_valid_fields(self):
        for k, m in self.meta.items():
            p = self.db.find_reagent(k)
            self.assertIn(m['type'], book.CHEM_TYPE_KEYS, k); self.assertIn(m.get('harm', 'caution'), book.HARM, k)
            self.assertTrue(chemplan.build_tree(self.db, p, set(planner.Rig(self.db, 1).avail)), k)

    def test_every_chem_recipe_in_the_book_is_clean(self):
        n = 0
        for r in book.load_book():
            if r.get('group') != 'chem': continue
            n += 1
            rig = run(self.db, r['ops'], book.gear_of(r))
            self.assertEqual(rig.sim.warnings, [], r['id']); self.assertEqual(rig.sim.effects, [], r['id'])
            self.assertGreaterEqual(rig.beaker.amount(self.db.find_reagent(r['payload'])), 10, r['id'])
            comp = book.computed(self.db, r)
            self.assertTrue(comp['order']['clicks_ok'] and comp['order']['reverse_ok'], r['id'])
        self.assertGreater(n, 20)

    def test_page_has_both_sections(self):
        html = open(os.path.join(ROOT, 'docs', 'index.html')).read()
        self.assertIn('id="g-chem"', html); self.assertIn('id="g-medborg"', html); self.assertNotIn('Planned: chemistry recipes', html)

    def test_chem_recipe_rejects_foam(self):
        spec = {'id': 'x', 'group': 'chem', 'type': 'util', 'title': 'x', 'beaker': 100, 'payload': 'space cleaner', 'harm': 'safe', 'what': 'x',
                'ops': [['dispense', 'fluorine', 10], ['dispense', 'carbon', 10], ['dispense', 'sulfuric acid', 10], ['dispense', 'water', 50]]}
        with self.assertRaises(ValueError): book.add_recipe(spec, db=self.db, write=False)

if __name__ == '__main__': unittest.main()
