"""The page's shared UI modules: tooltips must all go through tip(), never the title attribute."""
import os, re, unittest
from helpers import ROOT

class Tooltips(unittest.TestCase):
    def setUp(self):
        with open(os.path.join(ROOT, 'src', 'page_template.html')) as fh: self.t = fh.read()

    def test_module_exists_once(self):
        self.assertEqual(len(re.findall(r'var tip=\(function', self.t)), 1)
        self.assertEqual(len(re.findall(r"id='tip'", self.t)), 1)
        for need in ('#tip .tip-e', 'clip-path', '--tip-bd', 'italic 650'): self.assertIn(need, self.t)

    def test_no_title_attribute_tooltips(self):
        body = re.sub(r'<title>.*?</title>', '', self.t, flags=re.S)
        self.assertEqual(re.findall(r'\.title\s*=[^=]', re.sub(r'[mr]\.title|ty\[\d\]', '', body)), [])
        self.assertEqual(re.findall(r'<[a-z]+[^>]*\stitle="', body), [])
        self.assertNotIn("setAttribute('title'", body)

    def test_built_page_has_no_native_titles(self):
        with open(os.path.join(ROOT, 'docs', 'index.html')) as fh: html = fh.read()
        self.assertEqual(re.findall(r'<[a-z]+[^>]*\stitle="', re.sub(r'<title>.*?</title>', '', html, flags=re.S)), [])

if __name__ == '__main__': unittest.main()

class Menus(unittest.TestCase):
    def setUp(self):
        with open(os.path.join(ROOT, 'src', 'page_template.html')) as fh: self.t = fh.read()

    def test_exclusive_menu_module_exists_once_and_lists_every_menu_kind(self):
        self.assertEqual(len(re.findall(r'var menus=\(function', self.t)), 1)
        kinds = re.search(r"var MENU_KINDS=\[(.*?)\]", self.t).group(1)
        for k in ('group', 'tier', 'type', 'recipe', 'guide'): self.assertIn('details.' + k, kinds)
        self.assertNotIn('details.fx', kinds)                      # inner panels keep their own state

    def test_no_second_open_close_implementation(self):
        # the only code that closes one menu because another opened is inside the menus module
        self.assertEqual(len(re.findall(r'\.open\s*=\s*false', self.t)), 2)   # closeAll (x2); setAll uses a variable

    def test_page_behaviour(self):
        try: from playwright.sync_api import sync_playwright
        except ImportError: self.skipTest('no playwright')
        with sync_playwright() as p:
            b = p.chromium.launch(); pg = b.new_page()
            pg.goto('file://' + os.path.join(ROOT, 'docs', 'index.html')); pg.wait_for_timeout(300)
            n = lambda sel: pg.evaluate("document.querySelectorAll('%s[open]').length" % sel)
            pg.click('#g-medborg > summary'); pg.click('#g-chem > summary'); self.assertEqual(n('details.group'), 1)
            pg.click('#g-chem details.tier >> nth=0 >> summary'); pg.click('#g-chem details.tier >> nth=1 >> summary'); self.assertEqual(n('#g-chem details.tier'), 1)
            pg.click('#g-chem details.tier[open] details.type >> nth=0 >> summary'); pg.click('#g-chem details.tier[open] details.type >> nth=1 >> summary'); self.assertEqual(n('#g-chem details.type'), 1)
            pg.click('#g-chem details.type[open] details.recipe >> nth=0 >> summary'); pg.click('#g-chem details.type[open] details.recipe >> nth=1 >> summary'); self.assertEqual(n('#g-chem details.recipe'), 1)
            pg.click('#g-medborg > summary'); pg.click('#g-medborg details.tier >> nth=0 >> summary'); pg.click('#g-medborg details.tier[open] details.type >> nth=0 >> summary')
            pg.click('#g-medborg details.type[open] details.recipe >> nth=0 >> summary'); pg.click('#g-medborg details.type[open] details.recipe >> nth=1 >> summary')
            self.assertEqual(n('#g-medborg details.recipe'), 1); self.assertGreaterEqual(n('#g-medborg details.recipe[open] details.fx'), 2)   # inner panels were not collapsed by the rule
            pg.click('#expand'); self.assertGreater(n('details'), 50)             # Expand all still opens everything
            b.close()
