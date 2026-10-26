import unittest
from helpers import load_db, planner, chemlib

class GearTables(unittest.TestCase):
    def test_named_and_numeric_lookup(self):
        self.assertEqual(planner.Gear().beaker, 100)
        self.assertEqual(planner.Gear('bluespace').beaker, 300)
        self.assertEqual(planner.Gear(300).bname, 'bluespace')
        self.assertEqual(planner.Gear(77).beaker, 77)                 # custom volume
        self.assertEqual(planner.Gear('large', 60).sname, 'bluespace')
        with self.assertRaises(ValueError): planner.Gear('nonsense')

    def test_default_trigger_units(self):
        self.assertEqual(planner.Gear().default_trigger_units(), 15)
        self.assertEqual(planner.Gear('large', 'bluespace').default_trigger_units(), 60)
        self.assertEqual(planner.Gear('large', trigger_beaker='tube').default_trigger_units(), 15)

class RigBehaviour(unittest.TestCase):
    def setUp(self): self.db = load_db()

    def test_big_beaker_holds_more_and_small_one_warns(self):
        ops = [('dispense', 'water', 100), ('dispense', 'water', 20)]
        r = planner.run(self.db, ops, 1, False, planner.Gear('xl'))
        self.assertAlmostEqual(r.beaker.total, 120); self.assertFalse(r.sim.warnings)
        r = planner.run(self.db, ops, 1, False, planner.Gear('large'))
        self.assertAlmostEqual(r.beaker.total, 100); self.assertTrue(r.sim.warnings)

    def test_syringe_amount_must_be_selectable(self):
        with self.assertRaises(ValueError):
            planner.run(self.db, [('dispense', 'phosphorus', 15), ('draw', 15)], 1, False, planner.Gear('large', 'bluespace'))
        with self.assertRaises(ValueError):                           # piercing syringe only does 5 / 10
            planner.run(self.db, [('dispense', 'phosphorus', 15), ('draw', 15)], 1, False, planner.Gear('large', 'piercing'))

    def test_two_beaker_swap_and_pour(self):
        ops = [('swap',), ('dispense', 'fluorine', 10), ('dispense', 'carbon', 10), ('dispense', 'sulfuric acid', 5), ('swap',),
               ('dispense', 'hydrogen', 15), ('dispense', 'nitrogen', 5), ('dispense', 'water', 40), ('inject',)]
        r = planner.run(self.db, ops, 1, False, planner.Gear('large', trigger_beaker='large'))
        foam = [e for e in r.sim.effects if e['kind'] == 'foam']
        self.assertEqual(len(foam), 1); self.assertEqual(foam[0]['tiles'], 50)
        self.assertEqual(r.trigger.total, 0)

    def test_swap_is_rejected_in_syringe_mode(self):
        with self.assertRaises(ValueError): planner.run(self.db, [('swap',)], 1, False, planner.Gear())

    def test_pour_that_needs_several_clicks_is_rejected(self):
        # a 50u beaker's biggest pour is 30u: it cannot pour 40u of trigger at once
        g = planner.Gear('large', trigger_beaker='beaker')
        ops = [('swap',), ('dispense', 'water', 30), ('dispense', 'sugar', 10), ('swap',), ('inject',)]
        with self.assertRaises(ValueError): planner.run(self.db, ops, 1, False, g)

class Search(unittest.TestCase):
    def test_default_gear_finds_the_known_cleaner_foam(self):
        import chemcli
        db = load_db()
        out = chemcli.plan(db, 'foam', 'space cleaner', top=1, quiet=True)
        score = out[0][0][0]
        self.assertEqual((score[0], score[1]), (True, 30.0))       # clean, 30 tiles

    def test_bluespace_beaker_gives_a_stronger_payload(self):
        import chemcli
        db = load_db()
        base = chemcli.plan(db, 'foam', 'space cleaner', top=1, quiet=True)[0][0][0]
        big = chemcli.plan(db, 'foam', 'space cleaner', top=1, quiet=True, gear=planner.Gear('bluespace'))[0][0][0]
        self.assertGreater(big[3], base[3])                         # payload per tile

if __name__ == '__main__': unittest.main()
