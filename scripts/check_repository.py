"""Check tracked documentation targets and the published tool contract."""
import argparse
import json
from pathlib import Path
import re
import subprocess
from urllib.parse import unquote, urlsplit
import xml.etree.ElementTree as ET
from vget.contracts import TOOL_LIST

root = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--file-list', type=Path, help='JSON source-file inventory for an unpacked archive without Git metadata')
args = parser.parse_args()
files = json.loads(args.file_list.read_text()) if args.file_list else subprocess.check_output(['git', 'ls-files', '-z'], cwd=root).decode().split('\0')
if not isinstance(files,list) or any(not isinstance(name,str) for name in files):
    raise SystemExit('Source inventory must be a list of relative filenames.')
if any(Path(name).is_absolute() or not (root/name).resolve().is_relative_to(root.resolve()) for name in filter(None,files)):
    raise SystemExit('Source inventory contains a path outside the source root.')
failures = []
for name in filter(None, files):
    path = root / name
    if path.suffix != '.md' or not path.exists():
        continue
    content = re.sub(r'```.*?```', '', path.read_text(), flags=re.S)
    targets = re.findall(r'\]\(([^\s)]+)(?:\s+"[^"]*")?\)', content)
    targets += re.findall(r'(?:href|src)="([^"]+)"', content)
    for target in targets:
        parsed = urlsplit(target.strip('<>'))
        if parsed.scheme or parsed.netloc or not parsed.path:
            continue
        if not (path.parent / unquote(parsed.path)).exists():
            failures.append(f'{name}: missing local target {target}')
if json.loads((root / 'schemas/tool-specs.json').read_text())['tools'] != TOOL_LIST:
    failures.append('Published tool schemas differ from runtime tools.')
svg = ET.parse(root / 'docs/assets/vget-banner.svg').getroot()
if svg.tag != '{http://www.w3.org/2000/svg}svg':
    failures.append('Banner is not an SVG.')
if failures:
    raise SystemExit('\n'.join(failures))
print(f'{len(list(filter(None,files)))} source files: local documentation targets, runtime tool schema and SVG parse checked.')
