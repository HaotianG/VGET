"""Check tracked documentation targets and the published tool contract."""
import json
from pathlib import Path
import re
import subprocess
from urllib.parse import unquote, urlsplit
import xml.etree.ElementTree as ET
from vget.contracts import TOOL_LIST

root = Path(__file__).resolve().parents[1]
files = subprocess.check_output(['git', 'ls-files', '-z'], cwd=root).decode().split('\0')
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
print('Local documentation targets, runtime tool schema and SVG parse checked.')
