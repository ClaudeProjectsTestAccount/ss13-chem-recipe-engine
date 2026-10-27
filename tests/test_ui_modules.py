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
