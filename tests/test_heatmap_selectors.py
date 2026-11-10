"""Regression tests for heatmap selector crash in v1.6.0."""
from pathlib import Path
import re
import unittest
APP = Path(__file__).resolve().parents[1] / "frontend" / "app.js"
class TestHeatmapSelectors(unittest.TestCase):
    def test_heatmap_listeners_bind_multiple_elements(self):
        src = APP.read_text(encoding="utf-8")
        self.assertIn("$$('[data-heat-scale]').forEach", src)
        self.assertIn("$$('.heatmap-choices button').forEach", src)
    def test_single_element_selector_never_uses_foreach(self):
        src = APP.read_text(encoding="utf-8")
        self.assertIsNone(re.search(r"(?<!\$)\$\([^\n)]*\)\.forEach\(", src))
if __name__ == "__main__":
    unittest.main()
