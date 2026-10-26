import os, unittest
import helpers
from helpers import load_db, planner, chemlib, tmp, mutated_snapshot, make_mini_source, capture
import codecheck

CUP = """/obj/item/reagent_containers/cup/beaker
\tname = "beaker"
\tdesc = "A beaker. It can hold up to 50 units."

/obj/item/reagent_containers/cup/beaker/large
\tname = "large beaker"
\tvolume = 100

/obj/item/reagent_containers/cup/beaker/meta
\tname = "metamaterial beaker"
\tdesc = "A large beaker. Can hold up to 180 units."
\tvolume = 180
"""

class Parsing(unittest.TestCase):
    def test_find_line(self):
        txt = "a\n\n/datum/chemical_reaction/ammonia\n\tresults = x\n/datum/chemical_reaction/ammonia_extra\n"
        self.assertEqual(codecheck.find_line(txt, '/datum/chemical_reaction/ammonia'), 3)
        self.assertIsNone(codecheck.find_line(txt, '/datum/chemical_reaction/missing'))

    def test_volume_explicit_desc_and_inherited(self):
        self.assertEqual(codecheck.parse_volumes(CUP, '/obj/item/reagent_containers/cup/beaker/large'), 100)
        self.assertEqual(codecheck.parse_volumes(CUP, '/obj/item/reagent_containers/cup/beaker'), 50)   # from desc
        self.assertEqual(codecheck.parse_volume_chain(CUP, '/obj/item/reagent_containers/cup/beaker/plastic'), 50)   # undefined child -> parent
        self.assertIsNone(codecheck.parse_volumes(CUP, '/obj/item/nothing'))

    def test_check_gear_flags_a_changed_volume(self):
        with tmp() as d:
            f = os.path.join(d, codecheck.GEAR_SOURCES['large'][0]); os.makedirs(os.path.dirname(f))
            with open(f, 'w') as fh: fh.write(CUP.replace('volume = 100', 'volume = 120'))
            bad = codecheck.check_gear(d, {'large': (100, [])}, {})
            self.assertEqual(bad, [('large', 100, 120.0)] + [b for b in bad[1:]])  # large flagged first
            self.assertEqual(bad[0], ('large', 100, 120.0))

class Diff(unittest.TestCase):
    def setUp(self): self.old = load_db()

    def test_identical_dbs_have_no_diff(self):
        d = codecheck.diff_dbs(self.old, load_db())
        self.assertEqual((d['added'], d['removed'], d['changed'], d['dispensers']), ([], [], [], []))

    def test_changed_formula_and_dispenser_are_reported(self):
        def mut(d):
            for r in d['reactions']:
                if r['path'].endswith('/ammonia'): r['req'] = [[k, 2 if 'hydrogen' in k else v] for k, v in r['req']]
            d['dispensers']['1'] = [x for x in d['dispensers']['1'] if not x.endswith('/sugar')]
        with tmp() as t:
            new = chemlib.DB(json_path=mutated_snapshot(t, mut))
        d = codecheck.diff_dbs(self.old, new)
        self.assertEqual([c[0] for c in d['changed']], ['ammonia'])
        self.assertEqual(d['changed'][0][3], ['req'])
        self.assertEqual(len(d['dispensers']), 1); self.assertEqual(d['dispensers'][0][0], 1)

    def test_removed_and_added_reactions(self):
        def mut(d): d['reactions'] = [r for r in d['reactions'] if not r['path'].endswith('/foam')]
        with tmp() as t: new = chemlib.DB(json_path=mutated_snapshot(t, mut))
        self.assertEqual(codecheck.diff_dbs(self.old, new)['removed'], ['foam'])
        self.assertEqual(codecheck.diff_dbs(new, self.old)['added'], ['foam'])

    def test_critical_set_contains_the_recipe_reactions(self):
        names, shorts = codecheck.critical_set(self.old)
        self.assertTrue({'ammonia', 'space_cleaner', 'foam', 'surfactant'} <= shorts)
        self.assertIn('space cleaner', names)

    def test_recheck_recipes_reports_a_recipe_that_no_longer_runs(self):
        def mut(d): d['dispensers']['1'] = [x for x in d['dispensers']['1'] if not x.endswith('/fluorine')]
        with tmp() as t: new = chemlib.DB(json_path=mutated_snapshot(t, mut))
        bad = codecheck.recheck_recipes(self.old, new)
        self.assertTrue(any('FAILS' in why for _, _, why in bad))
        self.assertEqual(codecheck.recheck_recipes(self.old, load_db()), [])

    def test_recheck_recipes_reports_a_changed_result(self):
        def mut(d):
            for r in d['reactions']:
                if r['path'].endswith('/ammonia'): r['req'] = [[k, 2 if 'hydrogen' in k else v] for k, v in r['req']]
        with tmp() as t: new = chemlib.DB(json_path=mutated_snapshot(t, mut))
        self.assertTrue(any('RESULT CHANGED' in why for _, _, why in codecheck.recheck_recipes(self.old, new)))

class EndToEnd(unittest.TestCase):
    """codecheck.main against a tiny fake game tree (no network)"""
    def test_main_reports_a_changed_reaction_with_file_and_line(self):
        with tmp() as src, tmp() as t:
            make_mini_source(src, ammonia=(2, 1))                      # 'server' changed ammonia to 2:1
            snap = mutated_snapshot(t, lambda d: None)                  # snapshot still says 3:1
            rv, out = capture(codecheck.main, ['--src', src, '--snapshot', snap])
        self.assertIn('CHANGED ammonia', out); self.assertIn('mini.dm:', out)
        self.assertIn('3 Hydrogen + 1 Nitrogen  ->  2 Hydrogen + 1 Nitrogen', out)
        self.assertIn('USED BY YOUR RECIPES', out); self.assertEqual(rv, 2)

    def test_update_snapshot_writes_the_new_rules(self):
        with tmp() as src, tmp() as t:
            make_mini_source(src, ammonia=(2, 1))
            snap = mutated_snapshot(t, lambda d: None)
            codecheck.main(['--src', src, '--snapshot', snap, '--update-snapshot'])
            new = chemlib.DB(json_path=snap)
        self.assertEqual(len(new.reactions), 1)                         # snapshot now mirrors the mini tree

    def test_unreachable_repo_is_exit_3(self):
        with tmp() as t:
            rv, out = capture(codecheck.main, ['--repo', 'file:///definitely/not/here', '--cache-dir', t])
        self.assertEqual(rv, 3); self.assertIn('ERROR', out)

if __name__ == '__main__': unittest.main()
