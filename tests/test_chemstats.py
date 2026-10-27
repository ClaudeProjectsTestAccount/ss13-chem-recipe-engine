"""chem stats: overdose math, per-tick totals, the foam / smoke exposure model.  Uses the checked-in data/chem_stats.json and data/gear_protection.json."""
import os, sys, unittest
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'src'))
import chemlib, chemstats as cs, exposure as ex, statspanel as sp

DB = chemlib.DB(json_path=os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'src', 'chemdata.json'))
def P(n): return DB.find_reagent(n)

class TestMix(unittest.TestCase):
    def test_od_scales_with_share(self):
        a = cs.analyze_mix({P('mannitol'): 10.0, P('libital'): 20.0})
        row = [r for r in a['rows'] if r['name'] == 'Mannitol'][0]
        self.assertAlmostEqual(row['frac'], 1 / 3.0)
        self.assertAlmostEqual(row['od_at'], 15.0 * 3, places=6)          # od 15u alone, a third of the mix -> 45u of mix

    def test_per_tick_sums(self):
        a = cs.analyze_mix({P('libital'): 20.0, P('lenturi'): 10.0})
        self.assertAlmostEqual(a['net']['brute'], -3.0); self.assertAlmostEqual(a['net']['burn'], -3.0)

    def test_organ_flag_and_crit(self):
        m = sp.mix_block(DB, {P('mannitol'): 5.0, P('epinephrine'): 5.0}, 't')
        self.assertTrue(any(o['slot'] == 'brain' and o['heal'] for o in m['organ']))
        self.assertAlmostEqual(m['crit']['brute'], -0.5)

    def test_parse_mix(self):
        mix = sp.parse_mix(DB, 'libital 30, mannitol=15u; epinephrine 5')
        self.assertEqual(sorted(mix.values()), [5.0, 15.0, 30.0])

class TestExposure(unittest.TestCase):
    def tile(self): return {P('lube'): 64.0, P('phlogiston'): 48.0, P('chloralhydrate'): 16.0}
    def sc(self, rep, name): return [s for s in rep['scenarios'] if s['sc']['name'].startswith(name)][0]

    def test_foam_fraction(self):
        self.assertAlmostEqual(ex.foam_fraction(20), 0.025); self.assertAlmostEqual(ex.foam_fraction(50), 0.0125)

    def test_foam_floor_and_armour(self):
        rep = ex.analyse('foam', self.tile(), 20)
        bare = self.sc(rep, 'Bare skin'); suit = self.sc(rep, 'EVA suit + helmet, internals OFF')
        self.assertGreater(bare['absorbed'][P('phlogiston')], 40)
        self.assertEqual(bare['absorbed'][P('chloralhydrate')], 0)        # 0.4u per exposure is under the 0.5u floor
        self.assertEqual(suit['absorbed_total'], 0)
        self.assertGreater(suit['contact']['fire_stacks'], 0)             # contact effects ignore armour

    def test_smoke_blockers(self):
        rep = ex.analyse('smoke', {P('lube'): 40.0}, 20)
        self.assertGreater(self.sc(rep, 'Bare skin')['absorbed_total'], 30)
        self.assertEqual(self.sc(rep, 'EVA suit + helmet, internals ON')['absorbed_total'], 0)
        self.assertGreater(self.sc(rep, 'EVA suit + helmet, internals OFF')['absorbed_total'], 30)   # a space helmet alone does not stop smoke
        self.assertEqual(self.sc(rep, 'Cyborg')['absorbed_total'], 0)

if __name__ == '__main__': unittest.main()
