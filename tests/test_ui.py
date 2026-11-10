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

    def test_drilldown_is_year_month_week_day_hour(self):
        js=(ROOT/'frontend/app.js').read_text()
        for token in ("level:'year'", "next='month'", "next='week'", "next='day'", "next='hour'", "drillCrumbs()", 'id="zoomBack"', "queryArgs()", "hourAxis:true", 'id="patternRange"', 'id="allVizSwitch"'):
            self.assertIn(token,js,token)
        self.assertIn("const labels=hourAxis?n",js)

    def test_single_mobile_navigation_and_no_compare(self):
        js=(ROOT/'frontend/app.js').read_text()
        css=(ROOT/'frontend/styles.css').read_text()
        self.assertNotIn('function renderCompare',js)
        self.assertNotIn('function renderPatterns',js)
        self.assertNotIn('function renderSavedViews',js)
        self.assertNotIn('id="savedViews"',js)
        self.assertNotIn('id="zoomReset"',js)
        self.assertIn('class="mobile-tabbar"',js)
        self.assertIn('.sidebar,.overlay,.mobile-menu{display:none!important}',css)

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
