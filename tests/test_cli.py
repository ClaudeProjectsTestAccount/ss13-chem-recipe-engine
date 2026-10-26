import unittest
from helpers import load_db, capture
import chemcli

class Cli(unittest.TestCase):
    def test_parse_ops(self):
        ops = chemcli.parse_ops('dispense sulfuric acid 5; draw; heat 400; swap; inject')
        self.assertEqual(ops, [('dispense', 'sulfuric acid', 5), ('draw', None), ('heat', 400.0), ('swap',), ('inject',)])

    def test_sim_prints_the_foam_and_gear(self):
        _, out = capture(chemcli.main, ['sim', 'dispense fluorine 10; dispense carbon 10; dispense sulfuric acid 5; draw; spill; '
                                        'dispense hydrogen 30; dispense nitrogen 10; dispense water 45; inject', '--syringe', 'standard'])
        self.assertIn('FOAM: 30 tiles', out); self.assertIn('192u Space Cleaner', out)

    def test_nade_cleaner_foam_end_to_end(self):
        _, out = capture(chemcli.main, ['nade', '--trigger', 'foam', '--payload', 'space cleaner', '--top', '1'])
        self.assertIn('[gear: payload beaker large (100u) + standard syringe (15u)]', out)
        self.assertIn('36 of 36 dispense orders give this same result', out)

    def test_smoke_recipes_flag_order_dependence(self):
        _, out = capture(chemcli.main, ['nade', '--trigger', 'smoke', '--payload', 'space lube', '--top', '1'])
        self.assertIn('ORDER MATTERS', out)

    def test_unknown_reagent_is_a_clean_error(self):
        with self.assertRaises((SystemExit, KeyError)):
            capture(chemcli.main, ['nade', '--trigger', 'foam', '--payload', 'definitely not a reagent'])

if __name__ == '__main__': unittest.main()
