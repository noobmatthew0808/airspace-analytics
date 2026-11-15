"""Regression guard: compare every existing test against unchanged main.

Legacy UI tests may already fail in main because they assert removed v1.6
features. Do not make the application regress just to satisfy obsolete tests:
the staging branch may not introduce a new failing test.
"""
import re
import subprocess
import sys
import tempfile
from pathlib import Path

def run(path):
    result = subprocess.run(
        [sys.executable, '-m', 'unittest', 'discover', '-s', 'tests', '-t', '.', '-q'],
        cwd=path, text=True, capture_output=True, timeout=180)
    failed = set(re.findall(r'^(?:FAIL|ERROR):\s+(\S+)\s+\(', result.stderr, re.M))
    count = re.findall(r'Ran (\d+) tests?', result.stderr)
    print(Path(path).name, ':', count[-1] if count else 'unknown',
          'tests; failures:', ', '.join(sorted(failed)) or 'none', flush=True)
    if not count or (result.returncode and not failed):
        print(result.stderr[-3000:])
        raise RuntimeError('Test suite crashed before reporting its outcome')
    return failed

with tempfile.TemporaryDirectory(prefix='airspace-baseline-') as tmp:
    subprocess.run(['git', 'fetch', '-q', 'origin', 'main'], check=True)
    subprocess.run(['git', 'worktree', 'add', '--detach', tmp, 'origin/main'],
                   check=True, stdout=subprocess.DEVNULL)
    try:
        baseline = run(tmp)
    finally:
        subprocess.run(['git', 'worktree', 'remove', '--force', tmp],
                       check=True, stdout=subprocess.DEVNULL)
head = run('.')
new_failures = head - baseline
if new_failures:
    print('NEW FAILURES:', sorted(new_failures), file=sys.stderr)
    raise SystemExit(1)
print('PASS: no newly failing tests. Pre-existing baseline failures:',
      len(baseline), 'Current:', len(head))
