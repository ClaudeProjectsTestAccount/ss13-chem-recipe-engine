"""the 'Overdoses reached' logic: only what is actually reached is listed"""
import unittest, json, os
from helpers import ROOT
import statspanel as sp

def row(n, u, od, odfx=None): return dict(n=n, u=u, od=od, sev=3, odnote='', odfx=odfx or dict(tick={'tox': 2}, organ={}, tags=[]))

class OD(unittest.TestCase):
    def test_plain_mix_lists_only_reached(self):
        m = dict(rows=[row('A', 30, 30), row('B', 29, 30), row('C', 100, None)])
        self.assertEqual([o['n'] for o in sp.od_block(m)], ['A'])

    def test_exposure_needs_a_scenario_that_reaches_it(self):
        m = dict(rows=[row('A', 60, 30)])
        none = [dict(name='x', blood=dict(peak={'A': 20}, od={}, organ={}))]
        hit = [dict(name='bare', blood=dict(peak={'A': 58.2}, od={'A': 40}, organ={})), dict(name='suit', blood=None)]
        self.assertEqual(sp.od_block(m, none), [])
        r = sp.od_block(m, hit); self.assertEqual(r[0]['dose'], 58.2); self.assertEqual(r[0]['who'], [dict(name='bare', secs=40)])

    def test_organ_limit(self):
        m = dict(organ=[dict(slot='eyes', by=['Aiuri'], heal=False)])
        sc = [dict(name='bare', blood=dict(peak={}, od={}, organ={'eyes': 75.0, 'liver': 30.0}))]
        w = sp.organ_warn(m, sc); self.assertEqual([(o['slot'], o['dmg'], o['limit']) for o in w], [('eyes', 75.0, 50)])

    def test_burn_mender_fog_is_flagged_in_the_book(self):
        with open(os.path.join(ROOT, 'docs', 'index.html')) as fh: html = fh.read()
        self.assertIn('"organ_warn":[{"slot":"eyes"', html)

if __name__ == '__main__': unittest.main()
