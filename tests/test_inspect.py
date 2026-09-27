"""Exact original GenBank inspection; no sequence engineering is performed."""
import copy
import io
import json
from pathlib import Path

from Bio import SeqIO
from Bio.Seq import Seq
from Bio.SeqFeature import SeqFeature, SimpleLocation, Reference
from Bio.SeqRecord import SeqRecord
import pytest

from vget.toolkit import Toolkit, ToolError
from vget.service import APIError
from vget.sequence import parse_records
from vget.store import digest


def original_genbank(name='Original_fixture', topology='unknown'):
    record=SeqRecord(Seq('ACGT'*30),id='TEST000001.3',name=name,description='Synthetic inspection fixture only.')
    record.annotations={'molecule_type':'DNA','date':'07-JAN-2001','accessions':['TEST000001'],'sequence_version':3,
        'keywords':['software fixture'],'source':'synthetic construct','organism':'synthetic construct',
        'taxonomy':['other sequences'],'comment':'Preserve this historical comment exactly.'}
    if topology!='unknown':record.annotations['topology']=topology
    record.dbxrefs=['BioProject:PRJNA000000']
    ref=Reference();ref.authors='Example, A.';ref.title='Fixture reference';ref.journal='Unpublished';ref.location=[SimpleLocation(0,120)]
    record.annotations['references']=[ref]
    record.features=[SeqFeature(SimpleLocation(0,120),type='source',qualifiers={'organism':['synthetic construct'],'note':['arbitrary bases']}),
        SeqFeature(SimpleLocation(10,30,strand=-1),type='misc_feature',qualifiers={'label':['Inspection marker'],'note':['first','second']})]
    output=io.StringIO();SeqIO.write(record,output,'genbank');return output.getvalue().encode()


@pytest.fixture
def kit_record(tmp_path):
    kit=Toolkit(tmp_path/'workspace');raw=original_genbank()
    record=kit.service.import_files([('original.gbk',raw)])['records'][0]
    return kit,record,raw


def prepare(kit,record,host=None,topology=None,convention=None):
    job=kit.call('job.start',{'objective':'Inspect the supplied existing record and explain its annotations without changing its sequence.'})['job']
    values={'mode':'inspect','host_id':host,'name':'Inspection_package','topology':topology or record['topology'],'convention_id':convention}
    decisions=[{'field':field,'value':value,'origin':'source' if field=='topology' else 'agent','reason':'Preserve source or record explicitly unassessed context.'} for field,value in values.items()]
    job=kit.call('job.update',{'job_id':job['id'],'expected_revision':job['revision'],'decisions':decisions,
        'criteria':[{'id':'unchanged','text':'Retain original sequence and every GenBank annotation.','blocks_export':True}]})['job']
    plan={'operation':{'record_id':record['id']},'summary':'Inspect the exact original; make no edits.',
        'selections':[{'record_id':record['id'],'reason':'The user-supplied record is the object of inspection.','evidence_refs':[record['id']]}],
        'alternatives':[],'criteria':[{'id':'unchanged','status':'satisfied_by_plan','evaluation':'Exact imported GenBank record bytes are exported unchanged.','evidence_refs':[record['id']]}]}
    return job,plan


def planned(kit,job,plan):
    return kit.call('job.plan',{'job_id':job['id'],'expected_revision':job['revision'],'plan':plan})['job']


def test_inspect_keeps_original_bytes_identity_metadata_and_no_host(kit_record):
    kit,record,raw=kit_record;before=copy.deepcopy(record)
    job,plan=prepare(kit,record);job=planned(kit,job,plan)
    assert job['plan']['source_refs']==[{'kind':'records','id':record['id'],'sha256':kit.call('record.inspect',{'record_id':record['id']})['record']['record_sha256']}]
    result=kit.call('job.run',{'job_id':job['id'],'plan_hash':job['plan']['sha256']})
    assert Path(result['artifacts']['genbank']).read_bytes()==raw
    design=kit.store.load()['designs'][result['design']['id']]
    assert design['name']=='Inspection_package' and design['record']['name']==record['name']
    assert design['host_id'] is None and design['host_name']=='Not assessed'
    assert design['record']['metadata']==record['metadata']
    assert design['record']['features']==record['features'] and design['record']['sequence']==record['sequence']
    assert design['changes']==[] and design['mode']=='inspect'
    assert '_import_key' not in design['record']
    assert design['record']['source']['raw_sha256']==digest(raw)
    assert kit.store.load()['records'][record['id']]==before
    assert 'Inspect the exact original; make no edits.' in Path(result['artifacts']['html']).read_text()
    assert json.loads(Path(result['artifacts']['agent_context']).read_text())['operation']=={'record_id':record['id']}
    again=kit.call('job.run',{'job_id':job['id'],'plan_hash':job['plan']['sha256']})
    assert again['design']['id']==result['design']['id']


def test_inspect_selects_correct_original_in_multi_record_input(tmp_path):
    kit=Toolkit(tmp_path/'workspace')
    a=original_genbank('First_fixture','linear');b=original_genbank('Second_fixture','circular')
    records=kit.service.import_files([('multi.gbk',a+b)])['records']
    job,plan=prepare(kit,records[1]);job=planned(kit,job,plan)
    result=kit.call('job.run',{'job_id':job['id'],'plan_hash':job['plan']['sha256']})
    assert Path(result['artifacts']['genbank']).read_bytes()==b
    source_files=list((Path(result['artifacts']['directory'])/'sources').iterdir())
    assert any(path.read_bytes()==a+b for path in source_files)


def test_inspect_detects_missing_raw_original(kit_record):
    kit,record,raw=kit_record;job,plan=prepare(kit,record);job=planned(kit,job,plan)
    (kit.store.raw/record['source']['raw_sha256']).write_bytes(b'changed')
    with pytest.raises(ToolError) as caught:kit.call('job.run',{'job_id':job['id'],'plan_hash':job['plan']['sha256']})
    assert caught.value.code=='SOURCE_INTEGRITY'
    assert not kit.store.load()['designs']


def test_inspect_requires_exact_source_topology_and_one_input(kit_record):
    kit,record,raw=kit_record
    job,plan=prepare(kit,record,topology='circular')
    with pytest.raises(ToolError) as caught:planned(kit,job,plan)
    assert caught.value.code=='TOPOLOGY_CONFLICT'
    job,plan=prepare(kit,record);plan['operation']['part_ids']=[record['id']]
    with pytest.raises(ToolError) as caught:planned(kit,job,plan)
    assert caught.value.code=='OPERATION_INVALID'


def test_inspect_cannot_silently_ignore_convention(kit_record):
    kit,record,raw=kit_record
    convention=kit.service.draft_convention('Rules','Name prefix: Inspection_')
    kit.service.activate_convention(convention['id'],True)
    job,plan=prepare(kit,record,convention=convention['id'])
    with pytest.raises(ToolError) as caught:planned(kit,job,plan)
    assert caught.value.code=='INSPECT_CONVENTION'


def test_noninspect_modes_still_require_real_host_and_known_topology(kit_record):
    kit,record,raw=kit_record;job,plan=prepare(kit,record)
    with pytest.raises(ToolError) as caught:kit.call('job.update',{'job_id':job['id'],'expected_revision':job['revision'],
        'decisions':[{'field':'mode','value':'create','origin':'agent','reason':'Changed intent'}]})
    assert caught.value.code=='DECISION_INVALID'
    assert kit.call('job.get',{'job_id':job['id']})['job']['decisions']['mode']['value']=='inspect'


def test_inspection_metadata_changed_after_plan_is_stale(kit_record):
    kit,record,raw=kit_record;job,plan=prepare(kit,record);job=planned(kit,job,plan)
    state=kit.store.load();state['records'][record['id']]['metadata']['annotations']['date']='01-JAN-2020';kit.store.save(state)
    with pytest.raises(ToolError) as caught:kit.call('job.run',{'job_id':job['id'],'plan_hash':job['plan']['sha256']})
    assert caught.value.code=='STALE_SOURCE'


def test_inspection_service_rejects_nonnull_convention_and_unknown_host(kit_record):
    kit,record,raw=kit_record
    payload={'objective':'Inspect existing record','mode':'inspect','host_id':None,'name':'Inspect','record_id':record['id'],
             'topology':record['topology'],'convention_id':None}
    for bad in ({'host_id':'unrecognized'},{'convention_id':'missing-convention'}):
        with pytest.raises(APIError):kit.service.design({**payload,**bad},agent_context={'summary':'Inspect'})
    assert not kit.store.load()['designs']

@pytest.mark.parametrize('newline', [b'\n', b'\r\n'])
def test_inspect_preserves_single_record_trailing_whitespace(tmp_path, newline):
    kit=Toolkit(tmp_path/'workspace')
    raw=original_genbank().replace(b'\n', newline)+newline+b' \t'+newline
    record=kit.service.import_files([('original.gbk',raw)])['records'][0]
    job,plan=prepare(kit,record);job=planned(kit,job,plan)
    result=kit.call('job.run',{'job_id':job['id'],'plan_hash':job['plan']['sha256']})
    assert Path(result['artifacts']['genbank']).read_bytes()==raw
