"""Current Traffic workspace invariants, replacing obsolete v1.6 UI selectors."""
import unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]

class TestTrafficUI(unittest.TestCase):
 def test_single_traffic_workspace(self):
  js=(ROOT/'frontend/app.js').read_text()
  self.assertNotIn('data-page="patterns">Patterns</a>',js)
  for name in ('id="trafficFilterPanel"','id="filtersToggle"','id="filtersReset"',
               'id="exploreChart"','id="zoomBack"','id="zoomReset"'):
   self.assertIn(name,js)

 def test_drill_and_grouping(self):
  js=(ROOT/'frontend/app.js').read_text()
  for name in ("next='month'","next='week'","next='day'","next='hour'",
               "function resetTimeline()","period:'all',bucket:'year'",
               "function drillInto(point,group)"):
   self.assertIn(name,js)

 def test_all_time_averages_and_heatmap(self):
  js=(ROOT/'frontend/app.js').read_text()
  for name in ("period:'all',exclude_days:excludedAverageDays().join(',')",
               "$$('[data-heat-month]'","window.AirspaceCalendar.render",
               "function periodHeading(data)","const m=(previous[0]+pt[0])/2"):
   self.assertIn(name,js)

if __name__=='__main__':unittest.main()
