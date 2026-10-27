import unittest
from helpers import load_db, planner
import chemcli, book, tidy

class Clicks(unittest.TestCase):
    def test_same_button_is_preferred_over_switching(self):
        picked = tidy.pick_clicks([20, 10, 10, 30, 15])
        self.assertEqual(tidy.button_changes(picked), 1)                    # 10 10 | 10 | 10 | 15 15 | 15
        self.assertEqual([sum(c) for c in picked], [20, 10, 10, 30, 15])

    def test_at_most_three_clicks_unless_the_units_need_more(self):
        for u in range(5, 305, 5):
            lim = max(len(planner.click_plan(u)), tidy.MAX_CLICKS)
            self.assertTrue(all(len(o) <= lim and sum(o) == u for o in tidy.click_options(u)), u)

    def test_explicit_clicks_are_validated_and_used(self):
        db = load_db()
        rig = chemcli._run(db, [('dispense', 'water', 20, (10, 10))], 1, False, planner.Gear('large'))
        self.assertEqual(rig.steps[0]['op'][3], (10, 10)); self.assertIn('2 clicks at 10u', rig.steps[0]['text'])
        with self.assertRaises(ValueError): chemcli._run(db, [('dispense', 'water', 20, (10, 5))], 1, False, planner.Gear('large'))

class Tidy(unittest.TestCase):
    def setUp(self): self.db = load_db(); self.book = {r['id']: r for r in book.load_book()}

    def test_result_is_identical_for_a_sample_of_recipes(self):
        ids = sorted(self.book)[::6]
        for rid in ids:
            r = self.book[rid]; gear = book.gear_of(r); ops = [tuple(o) for o in r['ops']]
            t = tidy.tidy(self.db, ops, gear)
            a = chemcli._run(self.db, ops, 1, False, gear); b = chemcli._run(self.db, t, 1, False, gear)
            self.assertEqual(chemcli.signature(a), chemcli.signature(b), rid)
            self.assertEqual(sorted(a.sim.warnings), sorted(b.sim.warnings), rid)

    def test_fewer_button_changes_and_fewer_steps(self):
        ops = [('dispense', 'radium', 10), ('dispense', 'phosphorus', 10), ('dispense', 'chlorine', 10), ('dispense', 'welding fuel', 5), ('dispense', 'carbon', 5),
               ('dispense', 'hydrogen', 5), ('dispense', 'welding fuel', 10), ('dispense', 'oxygen', 10), ('dispense', 'bromine', 30)]
        gear = planner.Gear('large'); t = tidy.tidy(self.db, ops, gear)
        before = tidy.button_changes([tuple(sorted(planner.click_plan(o[2]), reverse=True)) for o in ops])
        after = tidy.button_changes([o[3] for o in t])
        self.assertLess(after, before)
        self.assertLessEqual(tidy.groups(t), 3)

    def test_clamped_final_click_is_left_alone(self):
        r = self.book['metal-foam-xl-300']; gear = book.gear_of(r)
        t = tidy.tidy(self.db, [tuple(o) for o in r['ops']], gear)
        rig = chemcli._run(self.db, t, 1, False, gear)
        self.assertEqual(sum(e['tiles'] for e in rig.sim.effects if e['kind'] == 'foam'), 200)

class Display(unittest.TestCase):
    def setUp(self): self.db = load_db(); self.book = {r['id']: r for r in book.load_book()}

    def test_equal_quantity_neighbours_become_one_numbered_step(self):
        c = book.simulate(self.db, self.book['chem-cure-100-mutadone'])
        grouped = [s for s in c['steps'] if s.get('items')]
        self.assertTrue(grouped)
        for s in grouped:
            self.assertGreaterEqual(len(s['items']), 2)
            self.assertEqual(len({it[0][1] for it in s['items']}), 1)       # one quantity per combined step
            for it in s['items']: self.assertEqual([p[0] for p in it], ['u', 'c', 'n'])
        self.assertLess(len(c['steps']), len(self.book['chem-cure-100-mutadone']['ops']))

    def test_spill_units_and_chemicals_are_tagged(self):
        c = book.simulate(self.db, self.book['hf-300-60-acid-sleep-nolube-40'])
        kinds = {p[0] for s in c['steps'] for p in s['parts'] + [q for it in s.get('items', []) for q in it]}
        self.assertTrue({'u', 'c', 'x'} <= kinds, kinds)
        self.assertTrue(any(p[0] == 'x' and 'SPILL' in p[1] for s in c['steps'] for p in s['parts']))

    def test_page_ships_the_new_markup(self):
        import os
        from helpers import ROOT
        with open(os.path.join(ROOT, 'docs', 'index.html')) as fh: html = fh.read()
        self.assertIn('tk-u', html); self.assertIn('ol.items', html)

if __name__ == '__main__': unittest.main()
