"""Direct toolkit contract: no Flask application or HTTP server required."""
import copy
import json
import zipfile
from pathlib import Path

import pytest

from vget.service import APIError, Service
from vget.store import Store, digest, json_bytes


@pytest.fixture
def service(tmp_path):
    return Service(Store(tmp_path))


def create_payload(service):
    records=list(service.store.load()['records'].values())
    return dict(objective='Compose selected synthetic records.', mode='create', host_id='HP-EC',
                part_ids=[next(r['id'] for r in records if r['name']==name) for name in ('Demo_backbone','Demo_insert')], name='Demo_service',
                topology='circular', convention_id='demo-convention')


def context():
    return dict(job_id='job-demo', revision=1, plan_hash='a'*64,
                summary='Caller-selected synthetic fixture plan.',
                criteria=[dict(id='C1',text='Keep the requested annotation.',evaluation='toolkit',status='pending',evidence_refs=[])],
                decisions=[dict(field='host_id',value='HP-EC',origin='user',reason='Explicit intent.')],
                selections=[], alternatives=[], assumptions=['Software fixture only.'], questions=[])


def test_direct_service_import_conventions_compare_and_design(service):
    imported=service.import_files([('new.fasta',b'>Extra\nACGTACGT\n')])
    assert len(imported['records'])==1
    convention=service.draft_convention('Local test rules','Name prefix: Demo_\nMax length: 1000')
    with pytest.raises(APIError,match='review'):
        service.activate_convention(convention['id'],False)
    assert service.activate_convention(convention['id'],True)['state']=='active'
    payload={**create_payload(service),'convention_id':convention['id']}
    assert service.brief(payload)['ready']
    design=service.design(payload)
    record=design['record']
    assert record['length']==640
    assert service.compare(record['id'],record['id'])['same_sequence']
    with zipfile.ZipFile(service.store.packages/design['id']/'bundle.zip') as package:
        manifest=json.loads(package.read('manifest.json'))
        for item in manifest['files']:
            assert digest(package.read(item['path']))==item['sha256']
    assert Store(service.store.root).load()['designs'][design['id']]==design


def test_agent_plan_keeps_objective_and_context_without_legacy_language_guessing(service):
    payload=create_payload(service)
    payload['objective']='Compare a future CHO optimization proposal; preserve the scientific rationale in this report.'
    original=copy.deepcopy(payload)
    supplied=context()
    design=service.design(payload,agent_context=supplied)
    assert payload==original
    assert design['objective']==original['objective']
    assert design['brief']['objective']==original['objective']
    assert design['brief']['interpretation']=='caller_supplied_agent_plan'
    assert design['agent_context']==supplied
    source_records=[service.store.load()['records'][rid] for rid in design['part_ids']]
    snapshot={'record':design['record'],'source_records':source_records,'brief':design['brief'],
              'convention':design['convention'],'changes':design['changes'],'agent_context':supplied}
    assert design['snapshot_sha256']==digest(json_bytes(snapshot))
    snapshot['agent_context']={**supplied,'summary':'Different rationale'}
    assert design['snapshot_sha256']!=digest(json_bytes(snapshot))
    supplied['assumptions'].append('Later mutation')
    assert 'Later mutation' not in design['agent_context']['assumptions']
    package=json.loads((service.store.packages/design['id']/'design.json').read_text())
    assert package['agent_context']==design['agent_context']
    assert design['checks'][-1]['status']=='unevaluated'


def test_agent_plan_requires_explicit_structured_fields(service):
    payload=create_payload(service)
    for field in ('mode','host_id','part_ids','topology'):
        bad=copy.deepcopy(payload);bad.pop(field)
        with pytest.raises(APIError) as caught:
            service.design(bad,agent_context=context())
        assert caught.value.code=='NEEDS_INPUT'
        assert field in {question['field'] for question in caught.value.details}
    assert not service.store.load()['designs']


def test_agent_context_does_not_bypass_protection_or_source_integrity(service):
    records=list(service.store.load()['records'].values())
    parent=next(r for r in records if r['name']=='Demo_parent')
    target=next(f for f in parent['features'] if f['label']=='Demo_insert')
    replacement=next(r for r in records if r['name']=='Demo_replacement')
    payload=dict(objective='Preserve a clear report while modifying this demonstration.',mode='modify',
                 host_id='HP-EC',parent_id=parent['id'],target_feature_id=target['id'],
                 replacement_id=replacement['id'],protected_feature_ids=[target['id']],name='Demo_guard')
    with pytest.raises(APIError) as caught:
        service.design(payload,agent_context=context())
    assert caught.value.code=='protected_feature'
    backbone=next(r for r in records if r['name']=='Demo_backbone')
    raw=service.store.raw/backbone['source']['raw_sha256']
    raw.rename(raw.with_suffix('.missing'))
    with pytest.raises(APIError) as caught:
        service.design(create_payload(service),agent_context=context())
    assert caught.value.code=='SOURCE_INTEGRITY'
    assert caught.value.status==409
    assert not service.store.load()['designs']


def test_service_rejects_invalid_transport_values_consistently(service):
    for payload in ([],{'part_ids':'x'},{'convention_id':[]},{'objective':42}):
        with pytest.raises(APIError) as caught:
            service.brief(payload)
        assert caught.value.status==400
    with pytest.raises(APIError) as caught:
        service.import_files([('x.fasta','not bytes')])
    assert caught.value.code=='FILE_TYPE'
    with pytest.raises(APIError) as caught:
        service.import_files([])
    assert caught.value.code=='FILES_REQUIRED'
    with pytest.raises(APIError) as caught:
        service.compare([],None)
    assert caught.value.code=='RECORD_NOT_FOUND'
