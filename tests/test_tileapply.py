"""amount applied per floor tile: exposure share, floor-effect thresholds, wet-floor timer, wasted-chemical detection"""
import os, sys, unittest
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'src'))
import chemlib, tileapply as ta, exposure as ex, statspanel as sp

DB = chemlib.DB(json_path=os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'src', 'chemdata.json'))
def P(n): return DB.find_reagent(n)

class TestPlan(unittest.TestCase):
    def test_foam(self):
        pl = ta.plan('foam', 20); self.assertAlmostEqual(pl['fraction'], 0.025); self.assertEqual(pl['exposures'], 40)
        self.assertAlmostEqual(ta.plan('foam', 100)['fraction'], 0.00625)
    def test_smoke(self):
        pl = ta.plan('smoke', 30); self.assertAlmostEqual(pl['fraction'], 0.1); self.assertEqual(pl['exposures'], 9)
    def test_units_needed(self):
        self.assertAlmostEqual(ta.units_needed('foam', 20, 3.0), 120.0)          # radium glow: 3u per exposure

class TestFloor(unittest.TestCase):
    def test_lube_threshold(self):
        tile = {P('lube'): 39.0}                       # 39 x 2.5% = 0.975 u per exposure: under the 1u floor
        fl = ta.tile_report('foam', 20, tile)['rows'][0]; self.assertFalse(fl['floor_active'])
        tile = {P('lube'): 41.0}
        fl = ta.tile_report('foam', 20, tile)['rows'][0]; self.assertTrue(fl['floor_active'])
        self.assertGreater(fl['effects'][0]['wet_left_s'], 50)

    def test_lube_add_is_capped_per_exposure(self):
        ev = ta.evaluate('/datum/reagent/lube', 20.0, 2)[0]
        self.assertAlmostEqual(ev['add_s'], 12.0)                                # 120 deciseconds, not 120 s

    def test_thermite_accumulates(self):
        ev = ta.evaluate('/datum/reagent/thermite', 1.0, 40)[0]
        self.assertTrue(ev['enough']); self.assertFalse(ev['enough_rwall'])
        self.assertFalse(ta.evaluate('/datum/reagent/thermite', 0.5, 40)[0]['fires'])

    def test_inheritance(self):
        self.assertEqual([e['id'] for e in ta.turf_effects('/datum/reagent/uranium/radium')], ['glow'])
        self.assertEqual([e['kind'] for e in ta.turf_effects('/datum/reagent/lube/superlube')], ['superlube'])

    def test_wet_rate(self):
        self.assertAlmostEqual(ta.wet_rate(293.15), 20 / 2.0 / 15.0)
        self.assertEqual(ta.wet_rate(260), 0.0)

class TestInert(unittest.TestCase):
    def test_wasted_payload(self):
        tile = {P('lube'): 64.0, P('oil'): 32.0}
        rep = ex.analyse('foam', tile, 20)
        names = [i['n'] for i in sp.inert_chems(rep)]
        self.assertIn('Oil', names); self.assertNotIn('Space Lube', names)

class TestSlick(unittest.TestCase):
    L = '/datum/reagent/lube'; D = '/datum/reagent/drying_agent'
    def test_below_threshold_not_slick(self):
        self.assertIsNone(ta.slick_report('foam', 20, {self.L: 39.0}))

    def test_threshold_foam_still_long(self):
        r = ta.slick_report('foam', 20, {self.L: 40.1})
        self.assertTrue(r['over']); self.assertGreater(r['sim']['total_s'], 100)            # 40 exposures x 2 s: the floor cannot be short
        self.assertAlmostEqual(r['chems'][0]['extra_tile'], 0.1, places=1)

    def test_more_lube_lasts_longer(self):
        a = ta.slick_sim('foam', 20, {self.L: 64.0})['total_s']; b = ta.slick_sim('foam', 20, {self.L: 41.0})['total_s']
        self.assertGreater(a, b)

    def test_smoke_shorter_than_foam(self):
        self.assertLess(ta.slick_sim('smoke', 30, {self.L: 12.0})['total_s'], ta.slick_sim('foam', 20, {self.L: 41.0})['total_s'])

    def test_drying_agent_after_lube_cuts_it(self):
        t = {self.L: 64.0, self.D: 60.0}
        self.assertLess(ta.slick_sim('foam', 20, t)['total_s'], 15.0)
        t = {self.D: 60.0, self.L: 64.0}             # drying agent first: the lube then resets the timer each exposure
        self.assertGreater(ta.slick_sim('foam', 20, t)['total_s'], 22.5)        # still the 15 s minimum (22.5 s of draining) after the last exposure

    def test_policy(self):
        self.assertEqual(ta.policy()['slick_max_s'], 15)

if __name__ == '__main__': unittest.main()
