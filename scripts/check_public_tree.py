"""Small publication guard for tracked files; not a comprehensive secret scanner."""
import argparse
import json
from pathlib import Path
import re
import subprocess
import sys

root = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--file-list', type=Path, help='JSON source-file inventory for an unpacked archive without Git metadata')
args = parser.parse_args()
tracked = json.loads(args.file_list.read_text()) if args.file_list else subprocess.check_output(['git', 'ls-files', '-z'], cwd=root).decode().split('\0')
if not isinstance(tracked,list) or any(not isinstance(name,str) for name in tracked):
    raise SystemExit('Source inventory must be a list of relative filenames.')
if any(Path(name).is_absolute() or not (root/name).resolve().is_relative_to(root.resolve()) for name in filter(None,tracked)):
    raise SystemExit('Source inventory contains a path outside the source root.')
patterns = {
    'machine home path': re.compile(r'/(?:Users|home)/[A-Za-z0-9_.-]+/'),
    'private key': re.compile(r'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----'),
    'GitHub credential': re.compile(r'(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{30,})'),
    'provider credential': re.compile(r'sk-(?:proj-)?[A-Za-z0-9_-]{32,}'),
}
forbidden = {'.vget', '.venv', 'workspaces', 'local-data', 'private-data', 'outputs', 'work', '__pycache__'}
failures = []
for name in filter(None, tracked):
    path = root / name
    if forbidden.intersection(Path(name).parts) or path.name == '.env' or path.suffix in {'.pem', '.key', '.p12'}:
        failures.append((name, 'local/private artifact path'))
    if path.is_symlink():
        failures.append((name, 'symlink requires explicit review'))
        continue
    if not path.is_file():
        failures.append((name, 'missing tracked file'))
        continue
    try:
        text = path.read_text(encoding='utf-8')
    except UnicodeDecodeError:
        failures.append((name, 'binary file requires explicit publication review'))
        continue
    for label, pattern in patterns.items():
        if pattern.search(text):
            failures.append((name, label))
if failures:
    for name, reason in failures:
        print(f'{name}: {reason}', file=sys.stderr)
    sys.exit(1)
print(f'Checked {len([p for p in tracked if p])} tracked text files: no configured publication hazards found.')
