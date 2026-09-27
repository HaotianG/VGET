import io
import json
import zipfile
import hashlib
from pathlib import Path
import pytest
from vget.app import create_app

HEADERS = {'X-VGET-Local': '1'}

@pytest.fixture
def app(tmp_path):
    return create_app(tmp_path, testing=True)

@pytest.fixture
def client(app):
    return app.test_client()

def post(client, path, **kw):
    return client.post(path, headers=HEADERS, **kw)

def state(client):
    return client.get('/api/state').get_json()

def create_payload(client):
    s=state(client)
    return dict(objective='Create a demonstration sequence from these exact parts.', mode='create',host_id=s['hosts'][0]['id'],part_ids=[r['id'] for r in s['records'][:2]],name='Demo_construct',topology='circular',convention_id=s['conventions'][0]['id'])

def test_fresh_workspace_has_nine_hosts_and_explicit_demo_sources(client):
    s=state(client)
    assert len(s['hosts'])==9
    assert {'E. coli','B. subtilis','S. cerevisiae','Pichia pastoris','Sf9','Sf21','High-5','CHO','HEK293'} == {h['name'] for h in s['hosts']}
    assert all(r['source']['kind']=='demo' for r in s['records'])
    assert s['designs']==[]
    assert all(h['status']=='unevaluated' for h in s['hosts'])

def test_vague_brief_asks_and_does_not_create_design(client):
    r=post(client,'/api/brief',json={'objective':'Make a construct'})
    assert r.status_code==200
    body=r.get_json()
    assert not body['ready']
    assert {'host_id','part_ids'} <= {q['field'] for q in body['questions']}
    bad=post(client,'/api/design',json={'objective':'Make a construct'})
    assert bad.status_code==422
    assert not state(client)['designs']

def test_create_downloads_and_persistence(client,app):
    payload=create_payload(client)
    initial={r['id']:r for r in state(client)['records']}
    r=post(client,'/api/design',json=payload)
    assert r.status_code==201,r.get_json()
    d=r.get_json()['design']
    assert d['record']['sequence']==''.join(initial[i]['sequence'] for i in payload['part_ids'])
    assert d['host_name']=='E. coli'
    assert any(c['id']=='biological_function' and c['status']=='unevaluated' for c in d['checks'])
    z=client.get(d['files']['bundle'])
    assert z.status_code==200
    with zipfile.ZipFile(io.BytesIO(z.data)) as archive:
        manifest=json.loads(archive.read('manifest.json'))
        assert archive.read('construct.gbk')==client.get(d['files']['genbank']).data
        for item in manifest['files']:
            assert hashlib.sha256(archive.read(item['path'])).hexdigest()==item['sha256']
    other=create_app(app.config['DATA_DIR'],testing=True).test_client()
    assert state(other)['designs'][0]['id']==d['id']

def test_modify_preserves_parent_and_rejects_protection(client):
    records=state(client)['records']
    parent=next(r for r in records if r['name']=='Demo_parent')
    target=next(f for f in parent['features'] if f['label']=='Demo_insert')
    replacement=next(r for r in records if r['name']=='Demo_replacement')
    payload=dict(objective='Replace the selected demonstration feature.',mode='modify',host_id='HP-EC',parent_id=parent['id'],target_feature_id=target['id'],replacement_id=replacement['id'],name='Demo_edited')
    blocked=post(client,'/api/design',json={**payload,'protected_feature_ids':[target['id']]})
    assert blocked.status_code==422
    assert not state(client)['designs']
    result=post(client,'/api/design',json=payload)
    assert result.status_code==201,result.get_json()
    d=result.get_json()['design'];seg=target['segments'][0]
    assert d['record']['sequence']==parent['sequence'][:seg['start']]+replacement['sequence']+parent['sequence'][seg['end']:]
    assert next(r for r in state(client)['records'] if r['id']==parent['id'])==parent
    assert d['parent_id']==parent['id']

def test_import_multiple_records_duplicate_and_conflict(client):
    content=b'>partA\nACGTACGT\n>partB\nTTTTGGGG\n'
    r=post(client,'/api/import',data={'files':(io.BytesIO(content),'parts.fasta'),'source':'lab'})
    assert r.status_code==201,r.get_json()
    assert len(r.get_json()['records'])==2
    before=len(state(client)['records'])
    duplicate=post(client,'/api/import',data={'files':(io.BytesIO(content),'parts.fasta')})
    assert duplicate.status_code==201
    assert len(state(client)['records'])==before
    assert any(x['code']=='DUPLICATE' for x in duplicate.get_json()['diagnostics'])
    conflict=post(client,'/api/import',data={'files':(io.BytesIO(b'>partA\nCCCCAAAA\n'),'different.fasta')})
    assert conflict.status_code==201
    assert any(x['code']=='NAME_CONFLICT' for x in conflict.get_json()['diagnostics'])
    assert len([r for r in state(client)['records'] if r['name']=='partA'])==2

def test_catalogue_inline_sequence_and_formula_rejection(client):
    r=post(client,'/api/import',data={'files':(io.BytesIO(b'name,sequence,role,host\ncatalog_part,ACGTTT,demonstration,CHO\n'),'catalogue.csv')})
    assert r.status_code==201,r.get_json()
    assert r.get_json()['records'][0]['metadata']['catalogue']['host']=='CHO'
    bad=post(client,'/api/import',data={'files':(io.BytesIO(b'name,sequence\n=CMD(),ACGT\n'),'bad.csv')})
    assert bad.status_code==422

def test_convention_review_and_enforcement(client):
    r=post(client,'/api/conventions',json={'name':'My rules','notes':'Name prefix: LAB_\nMax length: 10\nTopology: circular'})
    assert r.status_code==201
    c=r.get_json()['convention']
    p={**create_payload(client),'name':'LAB_test','convention_id':c['id']}
    assert post(client,'/api/design',json=p).status_code==422
    assert post(client,f"/api/conventions/{c['id']}/activate",json={'reviewed':False}).status_code==422
    assert post(client,f"/api/conventions/{c['id']}/activate",json={'reviewed':True}).status_code==200
    bad=post(client,'/api/design',json=p)
    assert bad.status_code==422
    unknown=post(client,'/api/conventions',json={'name':'Unparsed','notes':'Use our usual assembly method.'}).get_json()['convention']
    assert unknown['unsupported']
    assert post(client,f"/api/conventions/{unknown['id']}/activate",json={'reviewed':True}).status_code==422

def test_no_cross_origin_writes_or_rebinding(client):
    assert client.post('/api/conventions',json={'name':'x','notes':'Max length: 10'}).status_code==403
    assert client.get('/api/state',headers={'Host':'evil.example'}).status_code==403
    assert client.post('/api/brief',headers={**HEADERS,'Origin':'https://evil.example'},json={}).status_code==403
    assert client.get('/api/designs/../../data/state.json').status_code in (404,403)

def test_unknown_ids_and_bad_json_fail_cleanly(client):
    assert post(client,'/api/compare',json={'left_id':'missing','right_id':'missing'}).status_code==404
    assert post(client,'/api/brief',json=[]).status_code==400
    assert post(client,'/api/design',json={**create_payload(client),'topology':'garbage'}).status_code==422

def test_host_names_match_words_not_substrings(client):
    p=create_payload(client)
    p['objective']='Compose the chosen synthetic parts.'
    response=post(client,'/api/brief',json=p).get_json()
    assert response['ready'],response['questions']
    p['objective']='Compose these selected parts for CHO.'
    response=post(client,'/api/brief',json=p).get_json()
    assert not response['ready']
    assert any(q['field']=='host_id' for q in response['questions'])

def test_catalogue_rejects_embedded_records_and_ambiguous_names(client):
    hidden=b'name,sequence\npart,"ACGT\n>hidden\nTTTT"\n'
    before=len(state(client)['records'])
    r=post(client,'/api/import',data={'files':(io.BytesIO(hidden),'hidden.csv')})
    assert r.status_code==422
    assert len(state(client)['records'])==before
    spaces=post(client,'/api/import',data={'files':(io.BytesIO(b'name,sequence\npart with spaces,ACGT\n'),'spaces.csv')})
    assert spaces.status_code==422

def test_malformed_ids_and_workbook_return_structured_errors(client):
    for field,value in [('replacement_id',[]),('convention_id',['bad']),('convention_id',[])]:
        r=post(client,'/api/design',json={**create_payload(client),field:value})
        assert r.status_code in (400,422)
        assert 'error' in r.get_json()
    archive=io.BytesIO()
    with zipfile.ZipFile(archive,'w') as z:z.writestr('test.txt','not a workbook')
    r=post(client,'/api/import',data={'files':(io.BytesIO(archive.getvalue()),'broken.xlsx')})
    assert r.status_code==422
    assert 'error' in r.get_json()

def test_missing_original_source_blocks_provenance_pass(client,app):
    p=create_payload(client)
    r=next(r for r in state(client)['records'] if r['id']==p['part_ids'][0])
    source=Path(app.config['DATA_DIR'])/'sources'/r['source']['raw_sha256']
    source.rename(source.with_suffix('.missing-for-test'))
    response=post(client,'/api/design',json=p)
    assert response.status_code==409
    assert response.get_json()['error']['code']=='SOURCE_INTEGRITY'
    assert not state(client)['designs']
