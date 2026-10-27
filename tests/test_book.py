import os, unittest
from helpers import load_db, planner
import book, chemcli

TYPES_NEEDED = ('cleaning', 'slip', 'hell', 'med', 'walls')
TIERS = [(100, 15), (100, 60), (300, 15), (300, 60)]

def spec(**kw):
    e = dict(id='t-1', type='cleaning', title='T', beaker=100, syringe=15, payload='space cleaner', harm='safe', what='w',
             ops=[['dispense', 'fluorine', 10], ['dispense', 'carbon', 10], ['dispense', 'sulfuric acid', 5], ['draw', 15], ['spill'],
                  ['dispense', 'hydrogen', 30], ['dispense', 'nitrogen', 10], ['dispense', 'water', 45], ['inject']])
    e.update(kw); return e

class Book(unittest.TestCase):
    def setUp(self): self.db = load_db(); self.recipes = book.load_book()

    def test_matrix_is_complete(self):
        """every gear tier has a recipe of every main type (a recipe that works on both syringes counts for both)"""
        have = set()
        for e in self.recipes:
            if not e['beaker']: continue
            for sy in book.computed(self.db, e)['syringes']: have.add((e['beaker'], sy, e['type']))
        for b, s in TIERS:
            for t in TYPES_NEEDED: self.assertIn((b, s, t), have, 'missing %s for %du/%du' % (t, b, s))

    def test_ids_are_unique_and_fields_valid(self):
        ids = [e['id'] for e in self.recipes]; self.assertEqual(len(ids), len(set(ids)))
        for e in self.recipes: book.validate_spec(e)

    def test_page_is_up_to_date(self):
        with open(book.PAGE_PATH) as fh: self.assertEqual(fh.read(), book.build_page(use_cache=False))

    def test_phlogiston_recipes_stabilize_first(self):
        n = 0
        for e in self.recipes:
            names = [o[1] for o in e['ops'] if o[0] == 'dispense']
            if e['type'] == 'hell' and 'stable plasma' in names and 'phosphorus' in names:   # phlogiston (phosphorus + sulfuric acid + plasma); the lube package also uses stable plasma
                n += 1; self.assertLess(names.index('iron'), names.index('stable plasma'), e['id'])
        self.assertGreater(n, 0)

    def test_every_hell_recipe_is_marked_danger(self):
        for e in self.recipes:
            if e['type'] == 'hell': self.assertEqual(e['harm'], 'danger', e['id'])

class Publish(unittest.TestCase):
    def setUp(self): self.db = load_db()

    def test_add_files_and_replaces_without_writing(self):
        e, comp, replaced = book.add_recipe(spec(), self.db, write=False)
        self.assertEqual(comp['summary']['kind'], 'foam'); self.assertEqual(comp['summary']['tiles'], 30)
        self.assertEqual(comp['syringes'], [15]); self.assertFalse(replaced)
        e, comp, replaced = book.add_recipe(spec(id='cleaner-foam-100-15'), self.db, write=False)
        self.assertTrue(replaced)

    def test_hazard_and_no_effect_are_rejected(self):
        bad = spec(ops=[['dispense', 'phosphorus', 5], ['dispense', 'sulfuric acid', 5], ['dispense', 'stable plasma', 5]])
        with self.assertRaises(ValueError): book.add_recipe(bad, self.db, write=False)        # phlogiston without stabilizer
        with self.assertRaises(ValueError): book.add_recipe(spec(ops=[['dispense', 'water', 10]]), self.db, write=False)

    def test_bad_specs_are_rejected(self):
        with self.assertRaises(ValueError): book.add_recipe(spec(type='nonsense'), self.db, write=False)
        with self.assertRaises(ValueError): book.add_recipe(spec(beaker=77), self.db, write=False)
        with self.assertRaises(ValueError): book.add_recipe(spec(syringe=None), self.db, write=False)

    def test_syringe_detection(self):
        e = spec(); self.assertEqual(book.computed(self.db, e)['syringes'], [15])             # a 15u draw is not a legal 60u setting
        ten = spec(ops=[['dispense', 'phosphorus', 10], ['draw', 10], ['spill'], ['dispense', 'hydrogen', 15], ['dispense', 'nitrogen', 5], ['dispense', 'water', 15],
                        ['dispense', 'potassium', 10], ['dispense', 'sugar', 10], ['inject']])
        self.assertEqual(book.computed(self.db, ten)['syringes'], [15, 60])

    def test_sort_order(self):
        a = dict(beaker=300, type='hell', title='b', rank=50); b = dict(beaker=100, type='slip', title='a', rank=50)
        c = dict(beaker=0, type='cleaning', title='a', rank=50); d = dict(beaker=100, type='cleaning', title='z', rank=50)
        self.assertEqual(sorted([a, b, c, d], key=book.sort_key), [d, b, a, c])

class Phlogiston(unittest.TestCase):
    def test_with_and_without_stabilizer(self):
        db = load_db(); g = planner.Gear('large')
        ph = [('dispense', 'phosphorus', 5), ('dispense', 'sulfuric acid', 5), ('dispense', 'stable plasma', 5)]
        rig = chemcli._run(db, ph, 1, False, g)
        self.assertTrue([x for x in rig.sim.effects if x['kind'] == 'HAZARD'])
        stab = [('dispense', 'iron', 5), ('dispense', 'oxygen', 5), ('dispense', 'hydrogen', 5)]
        rig = chemcli._run(db, stab + ph, 1, False, g)
        self.assertFalse([x for x in rig.sim.effects if x['kind'] == 'HAZARD'])
        self.assertAlmostEqual(rig.beaker.amount(db.find_reagent('phlogiston')), 15)

if __name__ == '__main__':
    unittest.main()
