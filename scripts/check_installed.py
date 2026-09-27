"""Run using a clean wheel environment from outside the source checkout."""
from importlib.metadata import metadata
from pathlib import Path
import tempfile
from vget.app import create_app
from vget.toolkit import Toolkit

with tempfile.TemporaryDirectory() as directory:
    kit = Toolkit(Path(directory) / 'workspace')
    kit.call('workspace.init', {})
    records = kit.call('library.search', {'query': 'BBa_'})['records']
    assert len(records) == 6, f'Expected six bundled references, found {len(records)}'
    app = create_app(Path(directory) / 'gui', testing=True)
    client = app.test_client()
    for route in ('/', '/static/app.js', '/static/styles.css'):
        response = client.get(route)
        assert response.status_code == 200 and response.data, route
    assert metadata('vget-agent-toolkit')['License-Expression'] == 'MIT AND CC-BY-4.0'
print('Installed wheel: six bundled references, GUI assets and license metadata verified.')
