"""Regression checks from independent registry provenance/network review."""
import json
from pathlib import Path

import pytest

from vget import registry
from vget.store import digest
from vget.toolkit import Toolkit, ToolError
from test_inspect import prepare, planned


def _inspect(kit, record):
    job, plan = prepare(kit, record)
    job = planned(kit, job, plan)
    return kit.call('job.run', {'job_id': job['id'], 'plan_hash': job['plan']['sha256']})


def test_reinspecting_registry_output_retains_every_original_evidence_blob(tmp_path):
    kit = Toolkit(tmp_path / 'workspace')
    kit.call('registry.install', {'part_ids': ['BBa_E0040']})
    original = next(iter(kit.store.load()['records'].values()))
    expected = {original['source']['raw_sha256']}
    expected.update(blob['raw_sha256'] for blob in original['source']['evidence_blobs'])
    first = _inspect(kit, original)
    state = kit.store.load()
    generated = state['records'][state['designs'][first['design']['id']]['record']['id']]
    second = _inspect(kit, generated)
    blobs = Path(second['artifacts']['directory']) / 'sources'
    retained = {digest(path.read_bytes()) for path in blobs.iterdir()}
    assert expected <= retained
    assert Path(second['artifacts']['genbank']).read_bytes() == Path(first['artifacts']['genbank']).read_bytes()


def test_registry_install_refuses_preexisting_corrupt_content_addressed_blob(tmp_path):
    kit = Toolkit(tmp_path / 'workspace')
    part = registry.load_pack()['parts'][0]
    (kit.store.raw / part['files']['metadata']['sha256']).write_bytes(b'corrupted existing evidence')
    with pytest.raises(ToolError):
        kit.call('registry.install', {'part_ids': [part['name']]})
    assert not kit.store.load()['records']


def test_rate_limit_stops_remaining_public_requests_without_mutating_records(tmp_path, monkeypatch):
    kit = Toolkit(tmp_path / 'workspace')
    kit.call('workspace.init', {})
    before = kit.store.load()['records']
    calls = []

    def limited(url):
        calls.append(url)
        raise ToolError('REGISTRY_RATE_LIMIT', 'Public registry returned HTTP 429.', {'retry_after': '60'})

    monkeypatch.setattr(registry, 'fetch_public', limited)
    receipt = kit.call('registry.check_live', {})
    assert len(calls) == 1
    assert receipt['results'][0]['error']['details']['retry_after'] == '60'
    assert all(item['status'] == 'not_checked' for item in receipt['results'][1:])
    assert kit.store.load()['records'] == before
    assert json.loads(Path(receipt['receipt']['path']).read_text())['results'] == receipt['results']


def test_public_fetch_refuses_cross_origin_redirect_before_following_it():
    with pytest.raises(ToolError) as error:
        registry._NoRedirect().redirect_request(None, None, 302, 'Redirect', {}, 'https://other.example/data')
    assert error.value.code == 'REGISTRY_NETWORK'
