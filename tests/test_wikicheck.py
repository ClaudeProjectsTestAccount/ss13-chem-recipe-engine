import unittest
from helpers import load_db, tmp
import wikicheck

TABLE = ("{| class=\"wikitable\"\n! Name\n! Formula\n! Reaction Conditions\n|-\n| '''Ammonia'''\n|\n* 2 Parts Hydrogen\n* 1 Part Nitrogen\n"
         "'''Alternatively:'''<br>\n* 1 Part Ammonia (T2 Chem Dispenser)\n| '''Minimum''': 100K<br>\n'''Overheat''': 900K\n"
         "|-\n| Space Cleaner\n| 1u Ammonia, 1u Water\n| any\n|-\n| ⬤ '''Acetone'''\n|\n* 1 Part Oil\n* 1 Part Welding Fuel\n* 1 Part Oxygen\n| '''Minimum''': 450K\n|}")

class Parser(unittest.TestCase):
    def setUp(self): self.e = {x['name']: x for x in wikicheck.parse_tables(TABLE)}

    def test_bullets_commas_and_alternatives(self):
        self.assertEqual(self.e['Ammonia']['parts'], {'hydrogen': 2.0, 'nitrogen': 1.0})
        self.assertEqual(self.e['Ammonia']['alts'], [('ammonia', 1.0)])
        self.assertEqual(self.e['Space Cleaner']['parts'], {'ammonia': 1.0, 'water': 1.0})

    def test_temperature_and_decorated_names(self):
        self.assertEqual(self.e['Ammonia']['tmin'], 100.0)
        self.assertEqual(self.e['Acetone']['tmin'], 450.0)                 # leading bullet glyph stripped from the name
        self.assertIsNone(self.e['Space Cleaner']['tmin'])

    def test_headers_and_na_rows_are_skipped(self):
        self.assertNotIn('Name', self.e)

class Safety(unittest.TestCase):
    def test_only_wiki_host_and_clean_titles(self):
        self.assertTrue(wikicheck.raw_url('Chemistry/Components').startswith('https://wiki.monkestation.com/'))
        for bad in ('x;rm -rf', 'a<b>', 'x?y=1&z=2'):
            with self.assertRaises(ValueError): wikicheck.raw_url(bad)

    def test_redirect_off_host_is_refused(self):
        import urllib.request, urllib.error
        h = wikicheck.SameHostOnly()
        req = urllib.request.Request('https://wiki.monkestation.com/x')
        with self.assertRaises(urllib.error.URLError):
            h.redirect_request(req, None, 302, 'Found', {}, 'https://evil.example.com/x')

    def test_discover_transclusions(self):
        txt = "{{:Chemistry/Components}} text {{:Chemistry/Area of Effect}} {{NavMedical}}"
        self.assertEqual(wikicheck.discover(txt), ['Chemistry/Area_of_Effect', 'Chemistry/Components'])

class Compare(unittest.TestCase):
    def test_wiki_vs_code(self):
        db = load_db(); ents = wikicheck.parse_tables(TABLE)
        rows, unmatched, ok = wikicheck.compare_to_code(db, ents, {'ammonia'})
        self.assertEqual([r['product'] for r in rows], ['Ammonia'])
        self.assertTrue(rows[0]['critical']); self.assertGreaterEqual(ok, 1)

    def test_snapshot_diff(self):
        a = wikicheck.parse_tables(TABLE)
        b = [dict(x) for x in a]; b[0] = dict(b[0], parts={'hydrogen': 3.0, 'nitrogen': 1.0})
        added, removed, changed = wikicheck.diff_cache(a, b + [dict(name='New', parts={'x': 1.0}, alts=[], tmin=None)])
        self.assertEqual(added, ['new']); self.assertEqual(removed, []); self.assertEqual(changed[0][0], 'ammonia')

if __name__ == '__main__': unittest.main()
