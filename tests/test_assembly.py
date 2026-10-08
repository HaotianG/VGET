"""Frozen sequence/location oracles and bounded assembly failure contracts."""
import copy
import io
import json
from pathlib import Path
import subprocess
from Bio import SeqIO
from Bio.Seq import Seq
from Bio.SeqRecord import SeqRecord
from Bio.SeqFeature import SeqFeature, SimpleLocation, Reference
import pytest
from vget import assembly
from vget.assembly import assemble_homology
from vget.sequence import SequenceError, parse_records
from vget.toolkit import Toolkit, ToolError
from vget.service import APIError

FROZEN = json.loads((Path(__file__).resolve().parents[1]/'examples/overlap-fixtures.json').read_text())
SPEC = {'method':'homology','overlaps':FROZEN['overlaps']}


def originals(case=None):
    case = case or FROZEN['cases'][0]
    result = []
    for name in ('backbone','insert'):
        r = SeqRecord(Seq(case[name]),id=name,name=name,description='Synthetic prepared linear fragment')
        r.annotations = {'molecule_type':'DNA','topology':'linear'}
        r.features = [SeqFeature(SimpleLocation(24,len(r)-24,strand=1 if name=='backbone' else -1),type='misc_feature',qualifiers={'label':[name+'_core'],'note':['Original source annotation']}),
                      SeqFeature(SimpleLocation(len(r)-24,len(r),strand=1),type='misc_feature',qualifiers={'label':['right_overlap' if name=='backbone' else 'origin_overlap']})]
        if name=='insert' and 'spanning_insert_feature' in case:
            s=case['spanning_insert_feature']
            r.features.append(SeqFeature(SimpleLocation(s['input_start'],s['input_end'],strand=s['strand']),type='misc_feature',qualifiers={'label':['origin_spanning']}))
        ref=Reference();ref.title='Synthetic fixture reference';ref.authors='Fixture';ref.journal='Software test';ref.location=[SimpleLocation(0,len(r))]
        r.annotations['references']=[ref]
        out=io.StringIO();SeqIO.write(r,out,'genbank');result.append(out.getvalue().encode())
    return result


def inputs(case=None):return [parse_records(raw.decode(),name+'.gbk')[0] for raw,name in zip(originals(case),('backbone','insert'))]


@pytest.mark.parametrize('case',[c for c in FROZEN['cases'] if c['kind']=='success'],ids=lambda c:c['id'])
def test_unique_circle_and_all_annotations_match_frozen_oracles(case):
    records=inputs(case);before=copy.deepcopy(records)
    result,changes=assemble_homology(records,'overlap_fixture',SPEC)
    assert result['sequence']==case['expected_sequence']
    assert result['length']==151 and result['topology']=='circular' and len(changes)==2
    assert records==before and len(result['features'])==sum(len(r['features']) for r in records)
    mapped={f['label']:f for f in result['features']}
    for f in FROZEN['expected_features']:
        assert mapped[f['label']]['segments']==[{'start':f['start'],'end':f['end'],'strand':f['strand']}]
    if 'spanning_insert_feature' in case:
        span=case['spanning_insert_feature'];assert mapped['origin_spanning']['segments']==[{'start':a,'end':b,'strand':span['strand']} for a,b in span['expected_segments']]
    # Feature sequence extraction is an independent strand/order oracle.
    for original in records:
        for f in original['features']:
            projected=next(g for g in result['features'] if g['provenance']['source_id']==original['id'] and g['provenance']['source_feature_id']==f['id'])
            source_loc=SeqIO.read(io.StringIO(originals(case)[0 if original is records[0] else 1].decode()),'genbank').features[original['features'].index(f)].location
            from Bio.SeqFeature import Location
            dest_loc=Location.fromstring(projected['location'],length=151,circular=True)
            assert source_loc.extract(Seq(original['sequence']))==dest_loc.extract(Seq(result['sequence']))
            assert projected['qualifiers']==f['qualifiers']
    assert len(result['metadata']['annotations']['references'])==2
    assert result['metadata']['assembly']['backend_version']=='5.5.8'
    assert result['metadata']['assembly']['unique_circular_products']==1
    assert 'sequences' not in result['metadata']['assembly']['prediction']


@pytest.mark.parametrize('case,code',[(FROZEN['cases'][1],'ASSEMBLY_OVERLAP_MISMATCH'),(FROZEN['cases'][2],'ASSEMBLY_AMBIGUOUS')])
def test_incompatible_and_repeated_inputs_fail_without_mutating_sources(case,code):
    records=inputs(case);before=copy.deepcopy(records)
    with pytest.raises(SequenceError) as e:assemble_homology(records,'rejected',SPEC)
    assert e.value.code==code and records==before


@pytest.mark.parametrize('damage,code',[
    ('circular','ASSEMBLY_TOPOLOGY'),('alphabet','ASSEMBLY_ALPHABET'),('qualifier','unsupported_qualifier_transform'),
    ('inspection','inspection_only_record'),('short_overlap','ASSEMBLY_SPEC'),('duplicate','ASSEMBLY_INPUTS'),('three','ASSEMBLY_INPUTS')])
def test_unsupported_inputs_have_explicit_outcomes(damage,code):
    records=inputs();spec=copy.deepcopy(SPEC)
    if damage=='circular':records[0]['topology']='circular'
    if damage=='alphabet':
        from vget.sequence import _finalize
        records[0]['sequence']=records[0]['sequence'][:30]+'N'+records[0]['sequence'][31:];_finalize(records[0])
    if damage=='qualifier':records[0]['features'][0]['qualifiers']['transl_except']=['(pos:25..27,aa:Sec)']
    if damage=='inspection':records[0]['metadata']['inspection_only']=True
    if damage=='short_overlap':spec['overlaps'][0]=spec['overlaps'][0][:19]
    if damage=='duplicate':records[1]=records[0]
    if damage=='three':records.append(copy.deepcopy(records[0]))
    with pytest.raises(SequenceError) as e:assemble_homology(records,'unsupported',spec)
    assert e.value.code==code


def test_backend_failure_ambiguity_or_disagreement_never_falls_back(monkeypatch):
    records=inputs();expected=FROZEN['expected_sequence']
    for sequences,code in [([], 'ASSEMBLY_NO_PRODUCT'),([expected,expected[:-1]+'A'],'ASSEMBLY_AMBIGUOUS'),([expected[:-1]+'A'],'ASSEMBLY_PATH_CONFLICT')]:
        monkeypatch.setattr(assembly,'_predict',lambda _,seqs=sequences:{'sequences':seqs})
        with pytest.raises(SequenceError) as e:assemble_homology(records,'failed',SPEC)
        assert e.value.code==code


def test_backend_timeout_and_version_are_controlled(monkeypatch):
    monkeypatch.setattr(assembly,'backend_status',lambda:{'available':False,'installed_version':None})
    with pytest.raises(SequenceError) as e:assembly._predict(['ACGT','ACGT'])
    assert e.value.code=='ASSEMBLY_BACKEND_MISSING'
    monkeypatch.setattr(assembly,'backend_status',lambda:{'available':False,'installed_version':'0.0'})
    with pytest.raises(SequenceError) as e:assembly._predict(['ACGT','ACGT'])
    assert e.value.code=='ASSEMBLY_BACKEND_VERSION'
    monkeypatch.setattr(assembly,'backend_status',lambda:{'available':True})
    def timeout(*args,**kwargs):raise subprocess.TimeoutExpired('worker',12)
    monkeypatch.setattr(assembly.subprocess,'run',timeout)
    with pytest.raises(SequenceError) as e:assembly._predict(['ACGT','ACGT'])
    assert e.value.code=='ASSEMBLY_TIMEOUT'


@pytest.mark.parametrize('stdout,returncode,code',[
    ('not-json',0,'ASSEMBLY_BACKEND_FAILED'),('[]',0,'ASSEMBLY_BACKEND_FAILED'),
    ('{"sequences":["N"]}',0,'ASSEMBLY_BACKEND_FAILED'),
    ('{"code":"ASSEMBLY_LIMIT","error":"graph budget"}',2,'ASSEMBLY_LIMIT')])
def test_worker_response_errors_remain_business_errors(monkeypatch,stdout,returncode,code):
    monkeypatch.setattr(assembly,'backend_status',lambda:{'available':True})
    monkeypatch.setattr(assembly.subprocess,'run',lambda *args,**kwargs:subprocess.CompletedProcess('worker',returncode,stdout,''))
    with pytest.raises(SequenceError) as e:assembly._predict(['ACGT','ACGT'])
    assert e.value.code==code


def planned(kit,length=151):
    recs=kit.service.import_files(list(zip(('backbone.gbk','insert.gbk'),originals())))['records'];ids=[r['id'] for r in recs]
    j=kit.call('job.start',{'objective':'Assemble the supplied synthetic prepared fragments with the two specified homologies into a circular computational record. Preserve annotations; no laboratory performance claim.'})['job']
    vals={'mode':'create','host_id':'HP-EC','name':'assembly_job','topology':'circular','convention_id':None}
    j=kit.call('job.update',{'job_id':j['id'],'expected_revision':j['revision'],'decisions':[{'field':k,'value':v,'origin':'agent','reason':'Exact synthetic fixture intent; compatibility unassessed'} for k,v in vals.items()],
        'criteria':[{'id':'size','text':'Exact fixture length','blocks_export':True,'check':{'kind':'length','value':length}}]})['job']
    p={'operation':{'part_ids':ids,'assembly':SPEC},'summary':'Two explicit terminal homologies, prepared sources, unique circular product.',
       'selections':[{'record_id':rid,'reason':'Frozen synthetic source','evidence_refs':[rid]} for rid in ids],'alternatives':[],
       'criteria':[{'id':'size','status':'satisfied_by_plan','evaluation':'Independent fixture oracle defines the output length','evidence_refs':ids}]}
    return j,p


def test_shared_service_convention_uses_assembled_length_and_exports_junctions(tmp_path):
    kit=Toolkit(tmp_path/'workspace');j,p=planned(kit)
    conv=kit.service.draft_convention('fixture_limit','Max length: 160');kit.service.activate_convention(conv['id'],True)
    payload={k:v['value'] for k,v in j['decisions'].items()}|p['operation']|{'objective':j['objective'],'convention_id':conv['id']}
    d=kit.service.design(payload,agent_context={'criteria':j['criteria']})
    assert d['record']['length']==151
    assert any(c['id']=='homology_prediction' and c['status']=='pass' for c in d['checks'])
    html=(kit.store.packages/d['id']/'report.html').read_text()
    assert 'Homology assembly prediction' in html and all(h in html for h in SPEC['overlaps'])
    bio=SeqIO.read(kit.store.packages/d['id']/'construct.gbk','genbank')
    assert str(bio.seq)==FROZEN['expected_sequence'] and 'pydna 5.5.8' in bio.annotations['comment']


def test_job_plan_pins_assembly_and_safe_retry_and_negative_gate(tmp_path):
    kit=Toolkit(tmp_path/'workspace');j,p=planned(kit)
    j=kit.call('job.plan',{'job_id':j['id'],'expected_revision':j['revision'],'plan':p})['job']
    r=kit.call('job.run',{'job_id':j['id'],'plan_hash':j['plan']['sha256']})
    assert r['design']['length']==151
    assert kit.call('job.run',{'job_id':j['id'],'plan_hash':j['plan']['sha256']})['design']['id']==r['design']['id']
    # Discovery does not duplicate the entire predicted sequence in metadata.
    assert FROZEN['expected_sequence'] not in json.dumps(kit.call('library.search',{}))
    other=Toolkit(tmp_path/'negative');j,p=planned(other,199)
    j=other.call('job.plan',{'job_id':j['id'],'expected_revision':j['revision'],'plan':p})['job']
    with pytest.raises(ToolError) as e:other.call('job.run',{'job_id':j['id'],'plan_hash':j['plan']['sha256']})
    assert e.value.code=='CRITERION_FAILED' and not other.store.load()['designs']


def test_invalid_plan_and_noncreate_service_never_ignore_assembly(tmp_path):
    kit=Toolkit(tmp_path/'workspace');j,p=planned(kit)
    p['operation']['assembly']={'method':'homology','overlaps':[]};before=kit.store.path.read_bytes()
    with pytest.raises(ToolError) as e:kit.call('job.plan',{'job_id':j['id'],'expected_revision':j['revision'],'plan':p})
    assert e.value.code=='ASSEMBLY_SPEC' and kit.store.path.read_bytes()==before
    with pytest.raises(APIError) as e:kit.service.design({'mode':'inspect','assembly':SPEC})
    assert e.value.code=='ASSEMBLY_MODE'
