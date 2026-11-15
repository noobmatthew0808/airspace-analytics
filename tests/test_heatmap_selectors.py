"""Current year/month activity calendar listener regression checks."""
from pathlib import Path
import re
import unittest
APP=Path(__file__).resolve().parents[1]/'frontend'/'app.js'

class TestHeatmapSelectors(unittest.TestCase):
 def test_month_cards_have_collection_listener_and_back_button(self):
  js=APP.read_text(encoding='utf-8')
  self.assertIn("$$('[data-heat-month]',$('#heatmap')).forEach",js)
  self.assertIn("if(back)back.onclick=",js)
 def test_single_element_selector_never_uses_foreach(self):
  js=APP.read_text(encoding='utf-8')
  self.assertIsNone(re.search(r'(?<!\$)\$\([^\n)]*\)\.forEach\(',js))

if __name__=='__main__':unittest.main()
