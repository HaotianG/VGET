import copy
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import pytest
from vget.toolkit import Toolkit, ToolError

@pytest.fixture
def kit(tmp_path):
    k = Toolkit(tmp_path/'workspace')
    k.call('workspace.init', {'demo':True})
    return k

def setup_job(k):
    records=k.call('library.search', {})['records']
    by_name={r['name']:r for r in records}
    j=k.call('job.start', {'objective':'Make a circular software demonstration from our two demo components for E. coli; explain choices, no biological performance claim.'})['job']
    decisions=[{'field':field,'value':value,'origin':origin,'reason':reason} for field,value,origin,reason in [
        ('mode','create','agent','New record requested'),('host_id','HP-EC','user','E. coli specified in objective'),
        ('topology','circular','user','Circular specified'),('name','Agent_demo','agent','Unambiguous output label'),
        ('convention_id','demo-convention','agent','Software demonstration convention, not a lab protocol')]]
    j=k.call('job.update', {'job_id':j['id'],'expected_revision':j['revision'],'decisions':decisions,
        'criteria':[{'id':'C1','text':'Use exact synthetic components and retain annotations','blocks_export':True}],
        'assumptions':['This is a software demonstration; function is not assessed.']})['job']
    ids=[by_name[n]['id'] for n in ['Demo_backbone','Demo_insert']]
    plan={'operation':{'part_ids':ids},'summary':'Compose the two supplied synthetic records in the stated order.',
        'selections':[{'record_id':r,'reason':'Matches intended synthetic component','evidence_refs':[r]} for r in ids],
        'alternatives':[{'record_id':by_name['Demo_replacement']['id'],'reason':'Replacement fixture is for the modify example.'}],
        'criteria':[{'id':'C1','status':'satisfied_by_plan','evaluation':'Selected exact source records; core preserves their annotations.','evidence_refs':ids}]}
    return j,plan

def propose(k,j,p):
    return k.call('job.plan', {'job_id':j['id'],'expected_revision':j['revision'],'plan':p})['job']

def test_objective_starts_empty_and_discovery_omits_raw_bases(tmp_path):
    k=Toolkit(tmp_path/'empty')
    assert k.call('library.search', {})['records']==[]
    j=k.call('job.start',{'objective':'Help me make a construct'})['job']
    assert j['status']=='needs_input'
    assert not j['decisions'] and j['objective']=='Help me make a construct'
    assert 'mode' in {q['field'] for q in j['questions']}
    k.call('workspace.init',{'demo':True})
    records=k.call('library.search',{})['records']
    assert len(records)==4 and all('sequence' not in r for r in records)
    inspected=k.call('record.inspect',{'record_id':records[0]['id']})['record']
    assert inspected['features'] and 'sequence' not in inspected
    assert k.call('record.inspect',{'record_id':records[0]['id'],'include_sequence':True})['record']['sequence']

def test_agent_plan_exports_explanation_exact_sources_and_resume(kit):
    j,p=setup_job(kit);planned=propose(kit,j,p)
    assert planned['status']=='planned'
    result=kit.call('job.run',{'job_id':j['id'],'plan_hash':planned['plan']['sha256']})
    assert result['job']['status']=='exported'
    assert result['design']['length']==640
    paths=result['artifacts']; assert Path(paths['genbank']).is_file()
    html=Path(paths['html']).read_text()
    assert 'Matches intended synthetic component' in html
    assert 'Replacement fixture is for the modify example.' in html
    package=Path(paths['directory'])
    manifest=json.loads((package/'manifest.json').read_text())
    for entry in manifest['files']:
        assert hashlib.sha256((package/entry['path']).read_bytes()).hexdigest()==entry['sha256']
    second=Toolkit(kit.store.root)
    assert second.call('job.get',{'job_id':j['id']})['job']['status']=='exported'
    assert second.call('job.run',{'job_id':j['id'],'plan_hash':planned['plan']['sha256']})['design']['id']==result['design']['id']
    assert len(kit.store.load()['designs'])==1

def test_questions_block_only_computation_and_answers_preserve_history(kit):
    j,p=setup_job(kit)
    j=kit.call('job.update',{'job_id':j['id'],'expected_revision':j['revision'],
        'questions':[{'id':'Q1','question':'Which exact context is intended?','blocks_export':True}]})['job']
    with pytest.raises(ToolError,match='unresolved'):propose(kit,j,p)
    assert kit.call('library.search',{'query':'replacement'})['records']
    j=kit.call('job.update',{'job_id':j['id'],'expected_revision':j['revision'],
        'answers':[{'question_id':'Q1','answer':'Only a synthetic software context','origin':'user'}]})['job']
    assert next(q for q in j['questions'] if q.get('id')=='Q1')['state']=='answered'
    assert propose(kit,j,p)['status']=='planned'
    assert len(kit.call('job.history',{'job_id':j['id']})['revisions'])>=4

def test_revision_and_plan_hash_protect_against_changed_input(kit):
    j,p=setup_job(kit);planned=propose(kit,j,p)
    with pytest.raises(ToolError) as e:
        kit.call('job.update',{'job_id':j['id'],'expected_revision':j['revision'],'assumptions':['stale']})
    assert e.value.code=='STALE_REVISION'
    changed=kit.call('job.update',{'job_id':j['id'],'expected_revision':planned['revision'],'assumptions':['New scope']})['job']
    assert changed['plan'] is None
    with pytest.raises(ToolError):kit.call('job.run',{'job_id':j['id'],'plan_hash':planned['plan']['sha256']})
    assert not kit.store.load()['designs']

def test_stale_annotations_are_detected_even_if_bases_unchanged(kit):
    j,p=setup_job(kit);planned=propose(kit,j,p)
    with kit.store.lock:
        state=kit.store.load();state['records'][p['operation']['part_ids'][0]]['features'][0]['label']='changed';kit.store.save(state)
    with pytest.raises(ToolError) as e:kit.call('job.run',{'job_id':j['id'],'plan_hash':planned['plan']['sha256']})
    assert e.value.code=='STALE_SOURCE'
    assert not kit.store.load()['designs']

def test_cannot_omit_criteria_or_selection_evidence(kit):
    j,p=setup_job(kit)
    for key in ['criteria','selections']:
        bad=copy.deepcopy(p);bad[key]=[]
        with pytest.raises(ToolError):propose(kit,j,bad)
    bad=copy.deepcopy(p);bad['selections'][0]['evidence_refs']=['invented-reference']
    with pytest.raises(ToolError):propose(kit,j,bad)
    bad=copy.deepcopy(p);bad['operation']['mode']='modify'
    with pytest.raises(ToolError):propose(kit,j,bad)

def test_unevaluated_hard_requirement_blocks_materialization(kit):
    j,p=setup_job(kit);p['criteria'][0]['status']='unevaluated'
    with pytest.raises(ToolError):propose(kit,j,p)
    assert not kit.store.load()['designs']

def test_job_failure_retains_plan_and_has_no_success_artifacts(kit):
    j,p=setup_job(kit);planned=propose(kit,j,p)
    source=kit.store.load()['records'][p['operation']['part_ids'][0]]['source']['raw_sha256']
    (kit.store.raw/source).rename(kit.store.raw/(source+'.unavailable'))
    with pytest.raises(ToolError) as e:kit.call('job.run',{'job_id':j['id'],'plan_hash':planned['plan']['sha256']})
    assert e.value.code=='SOURCE_INTEGRITY'
    actual=kit.call('job.get',{'job_id':j['id']})['job']
    assert actual['status']=='failed' and actual['plan'] and not actual.get('artifacts')

def test_completed_package_corruption_is_not_reused(kit):
    j,p=setup_job(kit);planned=propose(kit,j,p)
    r=kit.call('job.run',{'job_id':j['id'],'plan_hash':planned['plan']['sha256']})
    Path(r['artifacts']['html']).write_text('damaged')
    with pytest.raises(ToolError) as e:kit.call('job.run',{'job_id':j['id'],'plan_hash':planned['plan']['sha256']})
    assert e.value.code=='ARTIFACT_INTEGRITY'

def test_unknown_fields_never_silently_dropped(kit):
    with pytest.raises(ToolError):kit.call('job.start',{'objective':'demo','unkown':True})
    with pytest.raises(ToolError):kit.call('library.search',{'limit':'ten'})
    with pytest.raises(ToolError):kit.call('record.inspect',{'record_id':['bad']})
    with pytest.raises(ToolError):kit.call('job.start',{'objective':' '})

def test_cli_machine_contract_without_server(tmp_path):
    env={k:v for k,v in os.environ.items() if k!='PYTHONPATH'}
    args=[sys.executable,'-m','vget','--workspace',str(tmp_path/'cli')]
    r=subprocess.run(args+['tools'],capture_output=True,text=True,env=env)
    assert r.returncode==0,r.stderr
    response=json.loads(r.stdout);assert response['status']=='ok'
    assert 'job.start' in {t['name'] for t in response['data']['tools']}
    r=subprocess.run(args+['call','job.start','--input','-'],input=json.dumps({'objective':'Explore a demonstration'}),capture_output=True,text=True,env=env)
    assert r.returncode==0 and json.loads(r.stdout)['status']=='needs_input'
    invalid=subprocess.run(args+['call','job.start','--input','-'],input='{',capture_output=True,text=True,env=env)
    assert invalid.returncode!=0 and json.loads(invalid.stdout)['error']['code']=='INPUT_JSON'

def test_gui_reads_same_agent_result_and_export_never_overwrites(kit,tmp_path):
    from vget.app import create_app
    j,p=setup_job(kit);planned=propose(kit,j,p)
    result=kit.call('job.run',{'job_id':j['id'],'plan_hash':planned['plan']['sha256']})
    gui=create_app(kit.store.root,testing=True).test_client()
    state=gui.get('/api/state').get_json()
    assert state['designs'][0]['agent_context']['plan_hash']==planned['plan']['sha256']
    assert gui.get(state['designs'][0]['files']['genbank']).data==Path(result['artifacts']['genbank']).read_bytes()
    dest=tmp_path/'portable'
    exported=kit.call('artifact.export',{'job_id':j['id'],'destination':str(dest)})
    assert Path(exported['artifacts']['html']).read_bytes()==Path(result['artifacts']['html']).read_bytes()
    with pytest.raises(ToolError) as e:kit.call('artifact.export',{'job_id':j['id'],'destination':str(dest)})
    assert e.value.code=='DESTINATION_EXISTS'

def test_cli_processes_do_not_lose_each_others_updates(tmp_path):
    env={k:v for k,v in os.environ.items() if k!='PYTHONPATH'}
    args=[sys.executable,'-m','vget','--workspace',str(tmp_path/'shared'),'call','job.start','--input','-']
    processes=[subprocess.Popen(args,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,env=env) for _ in range(6)]
    results=[p.communicate(json.dumps({'objective':f'Synthetic example {i}'}),timeout=20) for i,p in enumerate(processes)]
    assert all(p.returncode==0 for p in processes),results
    ids={json.loads(out)['data']['job']['id'] for out,err in results}
    assert len(ids)==6
    assert set(Toolkit(tmp_path/'shared').store.load()['jobs'])==ids

def test_plan_rejects_ignored_create_protection_and_supports_modify(kit):
    j,p=setup_job(kit)
    bad=copy.deepcopy(p);bad['operation']['protected_feature_ids']=['anything']
    with pytest.raises(ToolError):propose(kit,j,bad)
    rs={r['name']:r for r in kit.call('library.search',{})['records']}
    parent=kit.call('record.inspect',{'record_id':rs['Demo_parent']['id']})['record']
    features={f['label']:f['id'] for f in parent['features']}
    j=kit.call('job.update',{'job_id':j['id'],'expected_revision':j['revision'],'decisions':[{'field':'mode','value':'modify','origin':'user','reason':'Replace the selected component for a software example'}]})['job']
    p['operation']={'parent_id':parent['id'],'target_feature_id':features['Demo_insert'],'replacement_id':rs['Demo_replacement']['id'],'protected_feature_ids':[features['Left_context'],features['Right_context']]}
    ids=[parent['id'],rs['Demo_replacement']['id']]
    p['selections']=[{'record_id':rid,'reason':'The selected parent or replacement software fixture','evidence_refs':[rid]} for rid in ids]
    p['alternatives']=[];p['criteria'][0]['evidence_refs']=ids
    planned=propose(kit,j,p)
    result=kit.call('job.run',{'job_id':j['id'],'plan_hash':planned['plan']['sha256']})
    assert result['design']['length']==700
    after=kit.call('record.inspect',{'record_id':result['design']['record_id']})['record']
    assert {f['label'] for f in after['features']}=={'Left_context','Right_context','Demo_replacement'}

def test_recover_committed_design_after_job_update_interruption(kit):
    j,p=setup_job(kit);planned=propose(kit,j,p)
    plan=planned['plan']
    # Reproduce a crash after Service commits the package but before job status is saved.
    existing=kit.service.design(plan['payload'],agent_context={**plan['context'],'plan_hash':plan['sha256']})
    result=kit.call('job.run',{'job_id':j['id'],'plan_hash':plan['sha256']})
    assert result['design']['id']==existing['id'] and len(kit.store.load()['designs'])==1

def test_valid_package_cannot_be_substituted_for_another_job(kit):
    j,p=setup_job(kit);a=propose(kit,j,p)
    ra=kit.call('job.run',{'job_id':j['id'],'plan_hash':a['plan']['sha256']})
    j2,p2=setup_job(kit)
    p2['operation']['part_ids']=p2['operation']['part_ids'][:1]
    p2['selections']=p2['selections'][:1]
    b=propose(kit,j2,p2)
    rb=kit.call('job.run',{'job_id':j2['id'],'plan_hash':b['plan']['sha256']})
    pa,pb=Path(ra['artifacts']['directory']),Path(rb['artifacts']['directory'])
    swap=pa.with_name('swap-temp');pa.rename(swap);pb.rename(pa);swap.rename(pb)
    with pytest.raises(ToolError) as e:kit.call('job.run',{'job_id':j['id'],'plan_hash':a['plan']['sha256']})
    assert e.value.code=='ARTIFACT_INTEGRITY'

def test_unmanifested_payload_cannot_enter_export(kit,tmp_path):
    j,p=setup_job(kit);planned=propose(kit,j,p)
    r=kit.call('job.run',{'job_id':j['id'],'plan_hash':planned['plan']['sha256']})
    (Path(r['artifacts']['directory'])/'unrelated.txt').write_text('Unexpected content')
    with pytest.raises(ToolError) as e:kit.call('artifact.export',{'job_id':j['id'],'destination':str(tmp_path/'export')})
    assert e.value.code=='ARTIFACT_INTEGRITY'
    assert not (tmp_path/'export').exists()

def test_catalogue_bases_are_opt_in_in_agent_summaries(kit,tmp_path):
    file=tmp_path/'catalog.csv';file.write_text('name,sequence,role\nprivate_part,ACGTTGCA,software\n')
    imported=kit.call('library.import',{'paths':[str(file)]})['records'][0]
    assert 'sequence' not in imported['metadata']['catalogue']
    rid=imported['id']
    assert 'sequence' not in kit.call('record.inspect',{'record_id':rid})['record']['metadata']['catalogue']
    assert 'sequence' not in kit.call('library.search',{'query':'private_part'})['records'][0]['metadata']['catalogue']
    assert kit.call('record.inspect',{'record_id':rid,'include_sequence':True})['record']['sequence']=='ACGTTGCA'

def test_input_limit_error_is_not_relabelled(tmp_path):
    from vget.cli import read_input
    path=tmp_path/'large.json';path.write_text(' '* (1024*1024+1))
    with pytest.raises(ToolError) as e:read_input(str(path))
    assert e.value.code=='INPUT_LIMIT'

def test_unsupported_objective_can_end_with_assessment_without_fake_export(kit):
    j=kit.call('job.start',{'objective':'A capability not present in this toolkit'})['job']
    r=kit.call('job.assess',{'job_id':j['id'],'expected_revision':j['revision'],'outcome':'unsupported','explanation':'The required operation is not supported by the declared toolkit capabilities.','evidence_refs':['HP-EC']})
    assert r['job']['status']=='unsupported' and r['job']['assessment']['explanation']
    assert not r['job'].get('artifacts') and not kit.store.load()['designs']
    with pytest.raises(ToolError):kit.call('artifact.export',{'job_id':j['id'],'destination':str(kit.store.root/'fake')})
    resumed=kit.call('job.update',{'job_id':j['id'],'expected_revision':r['job']['revision'],'assumptions':['User will supply revised scope.']})
    assert resumed['job']['status']=='needs_input' and 'assessment' not in resumed['job']

def test_derived_record_summaries_also_omit_nested_catalogue_bases(kit,tmp_path):
    file=tmp_path/'nested.csv';file.write_text('name,sequence,role\nnested_part,ACGTTGCA,software\n')
    rid=kit.call('library.import',{'paths':[str(file)]})['records'][0]['id']
    j,p=setup_job(kit);p['operation']['part_ids']=[rid]
    p['selections']=[{'record_id':rid,'reason':'Inline supplied fixture','evidence_refs':[rid]}]
    p['criteria'][0]['evidence_refs']=[rid]
    planned=propose(kit,j,p)
    result=kit.call('job.run',{'job_id':j['id'],'plan_hash':planned['plan']['sha256']})
    r=kit.call('record.inspect',{'record_id':result['design']['record_id']})['record']
    assert 'sequence' not in r['metadata']['source_records'][0]['metadata']['catalogue']
    assert 'ACGTTGCA' not in json.dumps(kit.call('library.search',{'query':'Agent_demo'}))

def test_export_preserves_source_comment_with_attribution_and_current_creation_date(kit):
    from datetime import datetime
    from Bio import SeqIO
    j,p=setup_job(kit);planned=propose(kit,j,p)
    result=kit.call('job.run',{'job_id':j['id'],'plan_hash':planned['plan']['sha256']})
    record=SeqIO.read(result['artifacts']['genbank'],'genbank')
    assert 'DEMONSTRATION ONLY' in record.annotations.get('comment','')
    assert 'Source comment' in record.annotations['comment']
    design=kit.store.load()['designs'][result['design']['id']]
    assert record.annotations['date']==datetime.fromisoformat(design['created_at']).strftime('%d-%b-%Y').upper()
