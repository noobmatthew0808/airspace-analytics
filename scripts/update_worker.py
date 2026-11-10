#!/usr/bin/env python3
"""Dedicated, unprivileged systemd updater. Executes no shell commands."""
from pathlib import Path
import json
import os
import subprocess
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
STATE=ROOT/'.airspace-state'

def status(state, detail):
    STATE.mkdir(exist_ok=True)
    p=STATE/'update-status.tmp'
    p.write_text(json.dumps({'state':state,'detail':detail,'at':int(time.time())}))
    p.replace(STATE/'update-status.json')

def git(*args, timeout=90):
    env={**os.environ,'GIT_TERMINAL_PROMPT':'0','GIT_SSH_COMMAND':'ssh -o BatchMode=yes'}
    p=subprocess.run(['git','-C',str(ROOT),*args],env=env,capture_output=True,text=True,timeout=timeout)
    if p.returncode:
        raise RuntimeError((p.stderr or p.stdout).strip()[-700:] or f'Git command failed: {args[0]}')
    return p.stdout.strip()

def main():
    prior=None
    try:
        status('running','Checking repository…')
        branch=git('branch','--show-current')
        if not branch: raise RuntimeError('Cannot update a detached Git branch')
        if git('status','--porcelain','--untracked-files=no'):
            raise RuntimeError('Tracked files have local edits; update safely blocked')
        prior=git('rev-parse','HEAD')
        try:
            action=json.loads((STATE/'update-action.json').read_text()).get('action','update')
        except (FileNotFoundError,ValueError): action='update'
        if action=='rollback':
            target=(STATE/'previous-commit').read_text().strip()
            if len(target)!=40 or not all(c in '0123456789abcdef' for c in target.lower()):
                raise RuntimeError('Invalid saved rollback commit')
            if prior==target:
                status('current','Already at the saved previous version')
                return 2
            git('merge-base','--is-ancestor',target,prior)
            status('running','Restoring previous verified commit…')
            git('reset','--hard',target)
        else:
            status('running','Downloading changes from GitHub…')
            git('fetch','--prune','origin',timeout=120)
            target=git('rev-parse',f'origin/{branch}')
            if prior==target:
                status('current','Already running the latest GitHub version')
                return 2  # no restart needed
            # Refuse overwriting history or accidentally switching to another repo.
            git('merge-base','--is-ancestor',prior,target)
            status('running','Installing and verifying files…')
            git('merge','--ff-only',f'origin/{branch}')
        compile_result=subprocess.run([sys.executable,'-m','compileall','-q',str(ROOT/'backend'),
             str(ROOT/'scripts')],capture_output=True,text=True,timeout=45)
        if compile_result.returncode:
            raise RuntimeError('Python validation failed: '+compile_result.stderr[-300:])
        for required in (ROOT/'frontend/index.html',ROOT/'frontend/app.js',ROOT/'frontend/styles.css'):
            if not required.is_file(): raise RuntimeError('Update missing '+required.name)
        if action=='update':
            p=STATE/'previous-commit'
            p.write_text(prior+'\n')
            p.chmod(0o600)
        status('success','Previous version restored. Restarting the website…' if action=='rollback' else 'Update installed. Restarting the website…')
        return 0
    except Exception as exc:
        # Restore previous commit only when we had successfully read HEAD. No
        # database files are ever touched by the updater.
        if prior:
            try:
                if git('rev-parse','HEAD')!=prior:
                    git('reset','--hard',prior)
            except Exception:
                pass
        status('failed',str(exc)[:500])
        return 1

if __name__=='__main__':
    sys.exit(main())
