"""Quick contracts for the requested launcher and desktop-only layout."""
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]

class LauncherContract(unittest.TestCase):
    def test_requested_links_and_grouping(self):
        js=(ROOT/'frontend/app.js').read_text()
        for url in ["port:'1099'", "port:'5173'", "path:'/map/'", "port:'1094'",
                    "port:'8754'", "EXTRPI737643", "tryflightdeck.com/map/account/feeder",
                    "port:'30053'", "path:'/stats.html'", "extraPath:'/map.html'",
                    "adsbexchange.com/myip/", "globe.adsbexchange.com/?feed=CGyw2ZDXE-Y2",
                    "port:'1093'"]:
            self.assertIn(url,js)
        for label in ['View Stats','Feeder Website Status','Airspace Analytics']:
            self.assertIn(label,js)
        self.assertIn('extraLabel',js)
        self.assertIn('group:\'feeders\'',js)

    def test_desktop_only_chart_scale_and_responsive_months(self):
        js=(ROOT/'frontend/app.js').read_text()
        css=(ROOT/'frontend/styles.css').read_text()
        self.assertIn('window.innerWidth>=1050',js)
        self.assertIn('W=desktopMain?1120:720',js)
        self.assertIn('@media(min-width:1650px)',css)
        self.assertIn('grid-template-columns:repeat(6,minmax(0,1fr))',css)
        self.assertIn('@media(max-width:700px)',css)
        self.assertIn('shortcut-extras',js)

if __name__=='__main__':unittest.main()
