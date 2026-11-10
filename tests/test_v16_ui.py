"""Traffic workspace UI invariants for v1.6."""
import unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
class TestV16UI(unittest.TestCase):
 def test_single_traffic_workspace(self):
  js=(ROOT/'frontend/app.js').read_text()
  self.assertNotIn('data-page="patterns">Patterns</a>',js)
  self.assertIn('trafficFilterPanel()',js)
  self.assertIn('id="filterEnabled"',js)
  self.assertIn('id="trafficReset"',js)
 def test_drill_and_grouping(self):
  js=(ROOT/'frontend/app.js').read_text()
  for x in ("next='month'", "next='week'", "next='day'", "next='hour'", "state.period='all';state.bucket='year'"):
   self.assertIn(x,js)
 def test_all_time_averages_and_heatmap(self):
  js=(ROOT/'frontend/app.js').read_text()
  self.assertIn("period:'all',metric:state.metric",js)
  self.assertIn('data-heat-scale',js)
  self.assertIn('function periodHeading(a)',js)
  self.assertIn('const mid=(prev[0]+pt[0])/2',js)
if __name__=='__main__':unittest.main()
