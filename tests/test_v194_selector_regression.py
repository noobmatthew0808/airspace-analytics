"""Prevent using Array.forEach on the one-element $() selector."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]

class TestSelectorRegression(unittest.TestCase):
    def test_single_element_selector_must_not_have_foreach(self):
        js = (ROOT / 'frontend' / 'app.js').read_text()
        self.assertNotRegex(js, r"(?<!\$)\$\([^\n)]*\)\.forEach\s*\(")
        self.assertIn("const $$ = (q, root=document)=>[...root.querySelectorAll(q)]", js)
        self.assertIn("$$('.launcher-link-icon img').forEach", js)

if __name__ == '__main__':
    unittest.main()
