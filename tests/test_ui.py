"""Static UI contract checks; do not require a browser or real receiver."""
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

class TestRedesignedUI(unittest.TestCase):
    def test_launcher_first_and_separate_route(self):
        js = (ROOT / 'frontend/app.js').read_text()
        self.assertIn('class="launcher-link launcher-primary" href="/analytics#explore"', js)
        self.assertIn('class="launcher-list"', js)
        self.assertIn("location.pathname==='/analytics'", js)
        self.assertNotIn('Every aircraft tells', js)
        self.assertNotIn('YOUR PRIVATE AIRSPACE', js)

    def test_explorer_has_zoom_and_foldouts(self):
        js = (ROOT / 'frontend/app.js').read_text()
        for token in ('zoomHistory', 'id="zoomBack"', 'id="zoomReset"',
                      'id="breakdownDetails"', 'data-range-mode="rolling"',
                      'id="advancedPanel"', 'id="customStart"', 'id="amount"'):
            self.assertIn(token, js)

    def test_no_preset_lists_or_prose_clutter(self):
        js=(ROOT/'frontend/app.js').read_text()
        self.assertNotIn('Last 46 hours',js)
        self.assertNotIn('Understanding these numbers',js)
        self.assertNotIn('About this installation',js)
        self.assertNotIn('class=\"quick-periods\"',js)
        self.assertIn('id=\"operatorScope\"',js)

    def test_shortcut_editor_add_remove_reorder(self):
        js = (ROOT / 'frontend/app.js').read_text()
        for token in ('id="addLink"', 'data-remove=', 'data-reorder=',
                      'collectSettingsLinks()', 'putLinks(xs)'):
            self.assertIn(token, js)

if __name__ == '__main__':
    unittest.main()
