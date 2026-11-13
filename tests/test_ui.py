"""Static UI contract checks; do not require a browser or real receiver."""
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

class TestRedesignedUI(unittest.TestCase):
    def test_launcher_first_and_separate_route(self):
        js = (ROOT / 'frontend/app.js').read_text()
        self.assertIn("const primaryAnalytics=", js)
        self.assertIn("primary?'/analytics#explore'", js)
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
        self.assertIn('href="/analytics#database"',js)
        self.assertIn('database-hitbox',js)
        self.assertNotIn('mobile-tabbar" id="mobileTabs"',js)
        self.assertNotIn("['aircraft','Aircraft'",js[js.index('const pages='):js.index('const names=')])

class TestV17CalendarAndQuietUI(unittest.TestCase):
    def test_sparse_buckets_use_left_anchored_slots(self):
        js=(ROOT/'frontend/app.js').read_text()
        self.assertIn('Math.max(n,guideSlots[axisGroup]||n)',js)
        self.assertIn('year:8,month:12,week:6,day:7,hour:24',js)
        self.assertIn('function toast(){',js)
        self.assertNotIn('append(x);setTimeout(()=>x.remove()',js)

    def test_calendar_is_year_and_month_only(self):
        js=(ROOT/'frontend/app.js').read_text()
        html=(ROOT/'frontend/index.html').read_text()
        self.assertNotIn('id="heatScope"',js)
        self.assertIn('data-heat-back',js)
        self.assertIn('data-heat-month', (ROOT/'frontend/calendar.js').read_text())
        self.assertIn('window.AirspaceCalendar.render',js)
        self.assertIn('calendar.css',html)
        self.assertNotIn("['week','Week'],['day','Day']],state.heatScope",js)

    def test_update_is_one_click_and_not_token_gated(self):
        js=(ROOT/'frontend/app.js').read_text()
        server=(ROOT/'backend/server.py').read_text()
        self.assertNotIn("$('#saveUpdatePair')",js)
        self.assertNotIn("X-Update-Token",js)
        self.assertIn("'update_token_required':False",server)
        self.assertIn('Cross-origin update request blocked',server)
