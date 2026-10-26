"""Runs the original source-cited engine checks (legacy_checks.py) as one unit test.
New tests should be small unittest cases in their own files; migrate checks out of legacy_checks.py over time."""
import os, runpy, unittest
from helpers import SRC, ROOT

class LegacyChecks(unittest.TestCase):
    def test_all_legacy_checks_pass(self):
        import io, contextlib
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            try: runpy.run_path(os.path.join(ROOT, 'tests', 'legacy_checks.py'), run_name='__main__')
            except SystemExit as e: code = e.code
            else: code = 0
        fails = [l for l in buf.getvalue().split('\n') if l.startswith('FAIL')]
        self.assertEqual(code, 0, '\n'.join(fails))
        self.assertGreater(buf.getvalue().count('PASS'), 25)

if __name__ == '__main__': unittest.main()
