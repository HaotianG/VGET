"""Independent failure cases from the published review and September handoff.

Synthetic fixtures only. Network responses are controlled, with no live calls.
"""
import copy
import io
import json
from pathlib import Path

from Bio import SeqIO
from Bio.Seq import Seq
from Bio.SeqFeature import SeqFeature, SimpleLocation
from Bio.SeqRecord import SeqRecord
import pytest

from vget import registry, public_sources
from vget.sequence import SequenceError, compose, parse_records, replace_feature
from vget.service import APIError
from vget.store import digest
from vget.toolkit import Toolkit, ToolError
from test_inspect import prepare, planned, original_genbank
from test_toolkit import setup_job, propose


def genbank(sequence, features=(), name='fixture', topology='circular'):
    bio = SeqRecord(Seq(sequence), id=name, name=name, description='Synthetic test only')
    bio.annotations = {'molecule_type': 'DNA', 'topology': topology}
    bio.features = list(features)
    out = io.StringIO()
    SeqIO.write(bio, out, 'genbank')
    return out.getvalue().encode()


@pytest.mark.parametrize('qualifier,value', [
    ('transl_except', '(pos:4..6,aa:Sec)'),
    ('anticodon', '(pos:4..6,aa:Phe,seq:aaa)'),
    ('rpt_unit_range', '4..6'),
    ('tag_peptide', '4..9'),
])
@pytest.mark.parametrize('route', ['compose', 'replace'])
def test_coordinate_qualifiers_are_not_silently_exported_after_transform(qualifier, value, route):
    f = SeqFeature(SimpleLocation(0, 9), type='misc_feature', qualifiers={qualifier: [value]})
    source = parse_records(genbank('ACG' * 3, [f]).decode(), 'qualifier.gb')[0]
    before = copy.deepcopy(source)
    prefix = parse_records('>prefix\nACGTAC\n', 'prefix.fa')[0]
    with pytest.raises(SequenceError) as error:
        if route == 'compose':
            compose([prefix, source], 'shifted')
        else:
            target = SeqFeature(SimpleLocation(0, 3), type='misc_feature')
            parent = parse_records(genbank('AACCGG', [target]).decode(), 'parent.gb')[0]
            replace_feature(parent, parent['features'][0]['id'], source, 'edited')
    assert error.value.code == 'unsupported_qualifier_transform'
    assert source == before


@pytest.fixture
def demo(tmp_path):
    kit = Toolkit(tmp_path / 'workspace')
    kit.call('workspace.init', {'demo': True})
    return kit


def typed_job(kit, check, blocking=True):
    job, plan = setup_job(kit)
    job = kit.call('job.update', {'job_id': job['id'], 'expected_revision': job['revision'],
        'criteria': [{'id': 'C1', 'text': 'Machine-check this output requirement.',
                      'blocks_export': blocking, 'check': check}]})['job']
    return propose(kit, job, plan)


@pytest.mark.parametrize('check', [
    {'kind': 'length', 'value': 1000},
    {'kind': 'sequence_sha256', 'value': '0' * 64},
    {'kind': 'topology', 'value': 'linear'},
    {'kind': 'feature_count', 'value': 999},
])
def test_typed_criteria_block_incorrect_materialized_output(demo, check):
    before = set(demo.store.load()['records'])
    job = typed_job(demo, check)
    with pytest.raises(ToolError) as error:
        demo.call('job.run', {'job_id': job['id'], 'plan_hash': job['plan']['sha256']})
    assert error.value.code == 'CRITERION_FAILED'
    assert not demo.store.load()['designs']
    assert set(demo.store.load()['records']) == before
    assert demo.call('job.get', {'job_id': job['id']})['job']['status'] == 'failed'


def test_typed_length_pass_is_bound_to_output_and_nonblocking_failure_visible(demo):
    job = typed_job(demo, {'kind': 'length', 'value': 640})
    result = demo.call('job.run', {'job_id': job['id'], 'plan_hash': job['plan']['sha256']})
    checks = result['design']['checks']
    assert any(c['id'] == 'criterion:C1' and c['status'] == 'pass' and c['observed'] == 640 for c in checks)
    job = typed_job(demo, {'kind': 'length', 'value': 1000}, blocking=False)
    result = demo.call('job.run', {'job_id': job['id'], 'plan_hash': job['plan']['sha256']})
    assert any(c['id'] == 'criterion:C1' and c['status'] == 'warning' and c['observed'] == 640 for c in result['design']['checks'])
    assert 'criterion:C1' in Path(result['artifacts']['html']).read_text()


def test_shared_service_enforces_typed_criteria_and_protection_without_toolkit(demo):
    job, _ = setup_job(demo)
    state = demo.store.load()
    parts = [r['id'] for r in state['records'].values() if r['name'] in ('Demo_backbone', 'Demo_insert')]
    payload = {'mode': 'create', 'host_id': 'HP-EC', 'name': 'Demo_direct', 'topology': 'circular',
               'objective': 'Synthetic software test', 'part_ids': parts}
    with pytest.raises(APIError) as error:
        demo.service.design(payload, agent_context={'criteria': [{'id': 'size', 'text': 'size',
            'blocks_export': True, 'check': {'kind': 'length', 'value': 1000}}]})
    assert error.value.code == 'CRITERION_FAILED'
    conv = demo.service.draft_convention('protect', 'Protect feature: Anything')
    demo.service.activate_convention(conv['id'], True)
    with pytest.raises(APIError) as error:
        demo.service.design({**payload, 'convention_id': conv['id']})
    assert error.value.code == 'CONSTRAINT_CONFLICT'
    assert not demo.store.load()['designs']


@pytest.fixture
def public_igem(tmp_path, monkeypatch):
    kit = Toolkit(tmp_path / 'workspace')
    part_uuid = '11111111-1111-4111-8111-111111111111'
    metadata = {'uuid': part_uuid, 'slug': 'bba-test', 'name': 'BBa_TEST', 'status': 'published',
                'sequence': 'ACGTACGT', 'sequenceLength': 8, 'title': 'First title'}
    raw = genbank('ACGTACGT', name='BBa_TEST')
    replies = {'meta': metadata, 'authors': {'data': [], 'total': 0}, 'raw': raw}
    def fetch(url):
        if url.endswith('.gb'): return replies['raw']
        if '/authors?' in url: return json.dumps(replies['authors']).encode()
        return json.dumps(replies['meta']).encode()
    monkeypatch.setattr(registry, 'fetch_public', fetch)
    monkeypatch.setattr(registry.time, 'sleep', lambda _: None)
    return kit, replies


@pytest.mark.parametrize('damage', ['record', 'source', 'blob', 'evidence_list'])
def test_public_igem_duplicate_refuses_corrupted_record_or_evidence(public_igem, damage):
    kit, replies = public_igem
    first = kit.call('registry.import_public', {'slug': 'bba-test'})['record']
    state = kit.store.load()
    record = state['records'][first['id']]
    if damage == 'record': record['description'] = 'Tampered'
    elif damage == 'source': record['source']['source_url'] = 'https://untrusted.example/'
    elif damage == 'evidence_list': record['source']['evidence_blobs'] = []
    else: (kit.store.raw / record['source']['evidence_blobs'][0]['raw_sha256']).write_bytes(b'corrupt')
    kit.store.save(state)
    before = kit.store.path.read_bytes()
    with pytest.raises(ToolError) as error:
        kit.call('registry.import_public', {'slug': 'bba-test'})
    assert error.value.code == 'SOURCE_INTEGRITY'
    assert kit.store.path.read_bytes() == before


@pytest.mark.parametrize('change', ['metadata', 'authors'])
def test_public_igem_changed_evidence_retains_both_acquisitions(public_igem, change):
    kit, replies = public_igem
    first = kit.call('registry.import_public', {'slug': 'bba-test'})['record']
    before = copy.deepcopy(kit.store.load()['records'][first['id']])
    if change == 'metadata': replies['meta']['title'] = 'Changed title'
    else: replies['authors']['data'] = [{'name': 'Synthetic attributed author'}]
    second = kit.call('registry.import_public', {'slug': 'bba-test'})
    assert second['record']['id'] != first['id']
    assert second['record']['sequence_sha256'] == first['sequence_sha256']
    assert any(d['code'] == 'IGEM_EVIDENCE_CHANGED' for d in second['diagnostics'])
    assert kit.store.load()['records'][first['id']] == before
    repeated = kit.call('registry.import_public', {'slug': 'bba-test'})
    assert repeated['record']['id'] == second['record']['id']
    assert repeated['diagnostics'][0]['code'] == 'DUPLICATE'


def test_legacy_public_igem_import_is_revalidated_without_rewriting_it(public_igem):
    kit, replies = public_igem
    first = kit.call('registry.import_public', {'slug': 'bba-test'})['record']
    state = kit.store.load(); legacy = state['records'][first['id']]
    legacy['source'].pop('acquisition_sha256')
    legacy['_import_key'] = 'public_igem:bba-test:' + legacy['source']['raw_sha256']
    kit.store.save(state); before = kit.store.path.read_bytes()
    assert kit.call('registry.import_public', {'slug': 'bba-test'})['record']['id'] == first['id']
    assert kit.store.path.read_bytes() == before


def test_ncbi_missing_and_failed_summaries_are_visible(tmp_path, monkeypatch):
    kit = Toolkit(tmp_path / 'workspace')
    monkeypatch.setattr(public_sources.time, 'sleep', lambda _: None)
    responses = [ {'esearchresult': {'idlist': ['1', '2', '3'], 'count': '3'}},
        {'result': {'uids': ['1', '2', '3'], '1': {'error': 'Summary unavailable'},
                    '3': {'accessionversion': 'TEST123.1', 'title': 'Synthetic'}}}]
    monkeypatch.setattr(public_sources, '_fetch_eutils_json', lambda *args: ('https://example.test/', json.dumps(responses.pop(0)).encode()))
    found = kit.call('library.search_ncbi', {'query': 'public fixture'})
    assert found['returned'] == 1
    assert {d['uid'] for d in found['diagnostics']} == {'1', '2'}
    assert found['summary_status'] == 'partial'


def warned_genbank():
    f = SeqFeature(SimpleLocation(10, 20), type='misc_feature', qualifiers={'label': ['ambiguous']})
    return genbank('ACGT' * 200, [f]).replace(b'11..20', b'784..90')


@pytest.mark.parametrize('prefix', [b'', b'\xef\xbb\xbf'])
def test_explicit_warned_inspection_keeps_original_and_blocks_transforms(tmp_path, prefix):
    kit = Toolkit(tmp_path / 'workspace')
    raw = prefix + warned_genbank().replace(b'\n', b'\r\n') + b' \t\r\n'
    source = tmp_path / 'ambiguous.gbk'; source.write_bytes(raw)
    with pytest.raises(ToolError): kit.call('library.import', {'paths': [str(source)]})
    record = kit.call('library.import', {'paths': [str(source)], 'inspection_only': True})['records'][0]
    assert record['metadata']['parser_warnings']
    assert record['metadata']['original_feature_locations'] == ['784..90']
    assert record['metadata']['inspection_only'] is True
    full = kit.store.load()['records'][record['id']]
    before = copy.deepcopy(full)
    with pytest.raises(SequenceError) as error: compose([full], 'forbidden')
    assert error.value.code == 'inspection_only_record'
    job, plan = prepare(kit, full); job = planned(kit, job, plan)
    result = kit.call('job.run', {'job_id': job['id'], 'plan_hash': job['plan']['sha256']})
    assert Path(result['artifacts']['genbank']).read_bytes() == raw
    assert any(c['id'].startswith('parser_warning:') and c['status'] == 'warning' for c in result['design']['checks'])
    html = Path(result['artifacts']['html']).read_text()
    assert 'parser interpretation' in html.lower()
    assert kit.store.load()['records'][record['id']] == before


def test_reimport_warned_inspection_diagnostics_use_existing_ids(tmp_path):
    kit = Toolkit(tmp_path / 'workspace')
    source = tmp_path / 'warned.gbk'; source.write_bytes(warned_genbank())
    first = kit.call('library.import', {'paths': [str(source)], 'inspection_only': True})
    repeated = kit.call('library.import', {'paths': [str(source)], 'inspection_only': True})
    assert repeated['records'] == []
    assert all(d.get('record_id', first['records'][0]['id']) in kit.store.load()['records'] for d in repeated['diagnostics'])
    assert kit.store.load()['records'][first['records'][0]['id']]['metadata']['parser_warnings']


@pytest.mark.parametrize('check', [
    {'kind': 'length', 'value': True}, {'kind': 'length', 'value': 0},
    {'kind': 'feature_count', 'value': -1}, {'kind': 'topology', 'value': 'mammalian'},
    {'kind': 'sequence_sha256', 'value': 'not-a-hash'}, {'kind': 'function', 'value': 'works'},
])
def test_invalid_computable_criterion_does_not_change_job(demo, check):
    job, _ = setup_job(demo)
    before = demo.store.path.read_bytes()
    with pytest.raises(ToolError):
        demo.call('job.update', {'job_id': job['id'], 'expected_revision': job['revision'],
            'criteria': [{'id': 'bad', 'text': 'Invalid criterion', 'blocks_export': True, 'check': check}]})
    assert demo.store.path.read_bytes() == before


def test_inspection_preserves_utf8_bom_in_exact_download(tmp_path):
    kit = Toolkit(tmp_path / 'workspace')
    raw = b'\xef\xbb\xbf' + original_genbank()
    record = kit.service.import_files([('bom.gbk', raw)])['records'][0]
    job, plan = prepare(kit, record); job = planned(kit, job, plan)
    result = kit.call('job.run', {'job_id': job['id'], 'plan_hash': job['plan']['sha256']})
    assert Path(result['artifacts']['genbank']).read_bytes() == raw
    html = Path(result['artifacts']['html']).read_text()
    import base64, re
    encoded = re.search(r'data:application/octet-stream;base64,([A-Za-z0-9+/=]+)', html).group(1)
    assert base64.b64decode(encoded) == raw
