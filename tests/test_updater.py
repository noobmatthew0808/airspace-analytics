"""Verify update/rollback logic using an isolated local Git remote."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]

class TestUpdater(unittest.TestCase):
 def test_fast_forward_and_rollback(self):
  with tempfile.TemporaryDirectory() as tmp:
   tmp=Path(tmp)
   publisher=tmp/'publisher'
   shutil.copytree(ROOT,publisher,ignore=shutil.ignore_patterns('__pycache__','.airspace-state','.git'))
   def git(cwd,*args):
    p=subprocess.run(['git','-C',str(cwd),*args],capture_output=True,text=True,check=True,timeout=15)
    return p.stdout.strip()
   git(publisher,'init','-b','main')
   git(publisher,'config','user.email','local-test@example.invalid')
   git(publisher,'config','user.name','Local Test')
   git(publisher,'add','.')
   git(publisher,'commit','-qm','initial')
   origin=tmp/'origin.git'
   subprocess.run(['git','init','--bare',str(origin)],capture_output=True,check=True)
   git(publisher,'remote','add','origin',str(origin))
   git(publisher,'push','-u','origin','main')
   # Bare Git repos may default to master even after main push.
   git(origin,'symbolic-ref','HEAD','refs/heads/main')
   clone=tmp/'working'
   subprocess.run(['git','clone',str(origin),str(clone)],capture_output=True,check=True)
   before=git(clone,'rev-parse','HEAD')
   state=clone/'.airspace-state'
   state.mkdir()
   (state/'update-action.json').write_text(json.dumps({'action':'update'}))
   (publisher/'VERSION').write_text('1.0.1\n')
   git(publisher,'add','VERSION')
   git(publisher,'commit','-qm','update site')
   git(publisher,'push','origin','main')
   p=subprocess.run(['python3',str(clone/'scripts/update_worker.py')],cwd=clone,capture_output=True,text=True,timeout=60)
   self.assertEqual(p.returncode,0,p.stderr)
   self.assertEqual((clone/'VERSION').read_text().strip(),'1.0.1')
   self.assertEqual((state/'previous-commit').read_text().strip(),before)
   self.assertEqual(json.loads((state/'update-status.json').read_text())['state'],'success')
   (state/'update-action.json').write_text(json.dumps({'action':'rollback'}))
   p=subprocess.run(['python3',str(clone/'scripts/update_worker.py')],cwd=clone,capture_output=True,text=True,timeout=60)
   self.assertEqual(p.returncode,0,p.stderr)
   self.assertEqual((clone/'VERSION').read_text().strip(),(ROOT/'VERSION').read_text().strip())

if __name__=='__main__':unittest.main()
