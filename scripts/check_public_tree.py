"""Small publication guard for tracked files; not a comprehensive secret scanner."""
from pathlib import Path
import re
import subprocess
import sys

root = Path(__file__).resolve().parents[1]
tracked = subprocess.check_output(['git', 'ls-files', '-z'], cwd=root).decode().split('\0')
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
