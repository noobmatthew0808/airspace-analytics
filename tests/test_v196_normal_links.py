"""Regression: launcher outbound URLs must remain standard HTTP(S)."""
import shutil
import subprocess
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
class TestNormalLinks(unittest.TestCase):
    def test_invalid_ios_scheme_not_used(self):
        js=(ROOT/"frontend"/"app.js").read_text()
        self.assertNotIn("safariAppLink",js)
        self.assertNotIn("x-safari-http",js)
        self.assertIn("const destination=primary?'/analytics#explore':hrefFor(it);",js)

    @unittest.skipUnless(shutil.which("node"),"Node.js unavailable")
    def test_actual_links(self):
        code=r"""
const fs=require('node:fs'),s=fs.readFileSync(process.argv[1],'utf8');
const start=s.indexOf('function launcherEntry('),end=s.indexOf('\nfunction launcherGroup(',start);
if(start<0||end<0)throw Error('Launcher function missing');
const render=new Function('hrefFor','esc','branding','icon',s.slice(start,end)+';return launcherEntry')(
 it=>it.url||'http://192.168.1.187:'+(it.port||8088)+(it.path||'/'),String,()=>'',()=>'');
const a=render({name:'ADSB.im',port:'1099',path:'/'});
if(!a.includes('href="http://192.168.1.187:1099/"')||!a.includes('target="_blank"'))throw Error('Local link changed');
const b=render({name:'ADS-B Exchange',url:'https://www.adsbexchange.com/myip/',extraLabel:'Feeder map',extraUrl:'https://globe.adsbexchange.com/?feed=CGyw2ZDXE-Y2'});
if(!b.includes('href="https://www.adsbexchange.com/myip/"')||!b.includes('href="https://globe.adsbexchange.com/?feed=CGyw2ZDXE-Y2"'))throw Error('Feeder link changed');
if(!render({name:'Airspace Analytics'},true).includes('href="/analytics#explore"'))throw Error('Analytics link changed');
"""
        result=subprocess.run(["node","-e",code,str(ROOT/"frontend"/"app.js")],capture_output=True,text=True,timeout=10)
        self.assertEqual(result.returncode,0,result.stderr)

if __name__=="__main__":unittest.main()
