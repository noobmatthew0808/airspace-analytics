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

class TestV15CompactCharts(unittest.TestCase):
    def test_v13_zoom_algorithm_retained(self):
        js=(ROOT/'frontend/app.js').read_text()
        base=(ROOT.parent/'airspace_v13/frontend/app.js').read_text() if (ROOT.parent/'airspace_v13/frontend/app.js').exists() else None
        start=js.index('function drillInto(');end=js.index('function donut(',start)
        self.assertIn('zoomHistory.push(',js[start:end])
        self.assertIn("$('#zoomBack').onclick",js)
        if base:
            lo=base.index('function drillInto(');hi=base.index('function donut(',lo)
            self.assertEqual(js[start:end],base[lo:hi])

    def test_every_hour_fits_screen_and_date_on_top(self):
        js=(ROOT/'frontend/app.js').read_text()
        css=(ROOT/'frontend/styles.css').read_text()
        self.assertIn('id="chartPeriod"',js)
        self.assertIn('everyHour:true',js)
        self.assertIn('everyTick=everyHour&&n<=25',js)
        self.assertIn('min-width:0!important',css)
        self.assertIn('touch-action:pan-y',css)

    def test_single_top_navigation_and_database_in_settings(self):
        js=(ROOT/'frontend/app.js').read_text()
        self.assertIn('class="top-nav-link"',js)
        self.assertIn('class="top-icon-link top-settings"',js)
        self.assertIn('Database explorer',js)
        self.assertNotIn('mobile-tabbar" id="mobileTabs"',js)
        self.assertNotIn("['aircraft','Aircraft'",js[js.index('const pages='):js.index('const names=')])
