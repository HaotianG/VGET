"""Frozen, independent sequence/location expectations for explicit fragment planning."""
import copy, hashlib, io, json
from pathlib import Path
import pytest
from Bio import SeqIO
from Bio.Seq import Seq
from Bio.SeqFeature import CompoundLocation, Reference, SeqFeature, SimpleLocation
from Bio.SeqRecord import SeqRecord
from vget.fragments import prepare_fragment, prepare_fragments
from vget.assembly import assemble_homology
from vget.sequence import SequenceError, parse_records
from vget.service import APIError
from vget.toolkit import Toolkit
from vget.contracts import ToolError

FROZEN=json.loads((Path(__file__).resolve().parents[1]/'examples/fragment-fixtures.json').read_text())


def raw_inputs(case):
    result=[]
    for spec in case['sources']:
        name='F'+hashlib.sha256(spec['name'].encode()).hexdigest()[:11]
        bio=SeqRecord(Seq(spec['sequence']),id=name,name=name,description=spec['name']+'; synthetic software source')
        bio.annotations={'molecule_type':'DNA','topology':spec['topology']}
        for f in spec['features']:
            parts=[SimpleLocation(a,b,strand=s) for a,b,s in f['parts']]
            bio.features.append(SeqFeature(parts[0] if len(parts)==1 else CompoundLocation(parts,'join'),type=f['type'],qualifiers=f['qualifiers']))
        ref=Reference()
        for key in ('title','authors','journal'):setattr(ref,key,spec['reference'][key])
        ref.location=[SimpleLocation(a,b,strand=s) for a,b,s in spec['reference']['parts']]
        bio.annotations['references']=[ref]
        text=io.StringIO();SeqIO.write(bio,text,'genbank');result.append((spec['name']+'.gbk',text.getvalue().encode()))
    return result


def records_specs(case):
    records=[parse_records(raw.decode(),name)[0] for name,raw in raw_inputs(case)]
    specs=[{'record_id':records[s['source_index']]['id'],'ranges':copy.deepcopy(s['ranges']),'orientation':s['orientation']} for s in case['fragments']]
    return records,specs


@pytest.mark.parametrize('case',FROZEN['cases'],ids=lambda c:c['id'])
def test_fragments_and_assembled_annotations_match_frozen_oracles(case):
    records,specs=records_specs(case);before=copy.deepcopy(records)
    prepared,comparisons=prepare_fragments(records,specs)
    for index,(fragment,comparison) in enumerate(zip(prepared,comparisons)):
        raw=''.join(records[index]['sequence'][r['start']:r['end']] for r in specs[index]['ranges'])
        assert fragment['sequence']==(str(Seq(raw).reverse_complement()) if specs[index]['orientation']=='reverse' else raw)
        assert fragment['topology']=='linear' and comparison['source_id']==records[index]['id']
        assert len([f for f in comparison['features'] if f['status']=='retained'])==2
        assert len([f for f in comparison['features'] if f['status']=='excluded'])==1
        assert comparison['references'][0]['status']=='projected'
        assert len(fragment['metadata']['annotations']['references'])==1
    result,_=assemble_homology(prepared,'fragment_fixture',{'method':'homology','overlaps':case['overlaps']})
    assert result['sequence']==case['expected_sequence'] and records==before
    expected={f['label']:f for f in case['expected_features']}
    assert set(f['label'] for f in result['features'])==set(expected)
    for f in result['features']:
        assert [[s['start'],s['end'],s['strand']] for s in f['segments']]==expected[f['label']]['parts']
        assert f['qualifiers']==expected[f['label']]['qualifiers']
        origin=f['provenance']['preparation']
        source=next(r for r in records if r['id']==origin['source_id'])
        original=next(g for g in source['features'] if g['id']==origin['source_feature_id'])
        from Bio.SeqFeature import Location
        assert Location.fromstring(original['location'],length=source['length'],circular=source['topology']=='circular').extract(Seq(source['sequence']))==Location.fromstring(f['location'],length=result['length'],circular=True).extract(Seq(result['sequence']))


def test_cut_through_feature_returns_complete_annotation_comparison():
    records,specs=records_specs(FROZEN['cases'][0]);spec=copy.deepcopy(specs[0]);spec['ranges'][0]['start']=40
    before=copy.deepcopy(records)
    with pytest.raises(SequenceError) as e:prepare_fragment(records[0],spec)
    assert e.value.code=='FRAGMENT_PARTIAL_FEATURE' and records==before
    assert len(e.value.details['features'])==3
    assert {f['status'] for f in e.value.details['features']}=={'partial','retained','excluded'}


@pytest.mark.parametrize('ranges',[
    [],[{'start':7,'end':7}],[{'start':-1,'end':20}],[{'start':0,'end':1000}],
    [{'start':84,'end':124},{'start':0,'end':90}],
    [{'start':84,'end':123},{'start':0,'end':68}],
    [{'start':0,'end':68},{'start':84,'end':124}]
])
def test_invalid_and_overlapping_wrap_ranges_fail(ranges):
    records,specs=records_specs(FROZEN['cases'][1]);spec=copy.deepcopy(specs[0]);spec['ranges']=ranges
    with pytest.raises(SequenceError) as e:prepare_fragment(records[0],spec)
    assert e.value.code in ('FRAGMENT_SPEC','FRAGMENT_RANGES')


def test_wrapping_linear_record_and_invalid_unknown_strand_are_rejected():
    records,specs=records_specs(FROZEN['cases'][1]);records[0]['topology']='linear'
    with pytest.raises(SequenceError) as e:prepare_fragment(records[0],specs[0])
    assert e.value.code=='FRAGMENT_RANGES'
    records,specs=records_specs(FROZEN['cases'][2]);records[1]['features'][0]['location']=records[1]['features'][0]['location'].replace('complement(','').rstrip(')')
    # Parse an explicitly unstranded feature without altering its exact range.
    from vget.sequence import _location_text, _segments
    part=records[1]['features'][0]['segments'][0];loc=SimpleLocation(part['start'],part['end'],strand=None)
    records[1]['features'][0].update(location=_location_text(loc,records[1]['length']),segments=_segments(loc))
    with pytest.raises(SequenceError) as e:prepare_fragment(records[1],specs[1])
    assert e.value.code=='invalid_record'  # GenBank syntax cannot round-trip an unknown strand here.


@pytest.mark.parametrize('damage,code',[('inspection','inspection_only_record'),('qualifier','unsupported_qualifier_transform'),('fuzzy','unsupported_location')])
def test_existing_transform_restrictions_are_preserved(damage,code):
    records,specs=records_specs(FROZEN['cases'][0])
    if damage=='inspection':records[0]['metadata']['inspection_only']=True
    if damage=='qualifier':records[0]['features'][2]['qualifiers']['transl_except']=['(pos:1..3,aa:Sec)']
    if damage=='fuzzy':records[0]['features'][0]['location']='<'+records[0]['features'][0]['location']
    with pytest.raises(SequenceError) as e:prepare_fragment(records[0],specs[0])
    assert e.value.code==code


def plan(kit,case=FROZEN['cases'][1]):
    records=kit.service.import_files(raw_inputs(case))['records']
    specs=[{'record_id':records[s['source_index']]['id'],'ranges':copy.deepcopy(s['ranges']),'orientation':s['orientation']} for s in case['fragments']]
    ids=[r['id'] for r in records]
    j=kit.call('job.start',{'objective':case['objective']})['job']
    vals={'mode':'create','host_id':'HP-EC','name':'fragment_job','topology':'circular','convention_id':None}
    j=kit.call('job.update',{'job_id':j['id'],'expected_revision':j['revision'],'decisions':[{'field':k,'value':v,'origin':'agent','reason':'Synthetic software acceptance intent; host compatibility unassessed'} for k,v in vals.items()],
        'criteria':[{'id':'length','text':'Independent fixture length','blocks_export':True,'check':{'kind':'length','value':len(case['expected_sequence'])}}]})['job']
    p={'operation':{'fragments':specs,'assembly':{'method':'homology','overlaps':case['overlaps']}},'summary':'Select explicit source ranges and supplied orientations, retain complete features, predict one circle.',
       'selections':[{'record_id':rid,'reason':'Inspected synthetic source','evidence_refs':[rid]} for rid in ids],'alternatives':[],
       'criteria':[{'id':'length','status':'satisfied_by_plan','evaluation':'Frozen independent fixture length','evidence_refs':ids}]}
    return j,p,records


def test_preview_is_read_only_and_plan_pins_originals(tmp_path):
    kit=Toolkit(tmp_path/'workspace');j,p,records=plan(kit);before=kit.store.path.read_bytes()
    preview=kit.call('fragment.preview',{'fragment':p['operation']['fragments'][0]})
    assert 'sequence' not in preview['fragment'] and kit.store.path.read_bytes()==before
    assert preview['fragment']['source']['kind']=='fragment_preparation'
    explicit=kit.call('fragment.preview',{'fragment':p['operation']['fragments'][0],'include_sequence':True})
    assert len(explicit['fragment']['sequence'])==108
    j=kit.call('job.plan',{'job_id':j['id'],'expected_revision':j['revision'],'plan':p})['job']
    assert j['plan']['context']['fragment_previews'][0]['source_id']==records[0]['id']
    assert {r['id'] for r in j['plan']['source_refs'] if r['kind']=='records'}=={r['id'] for r in records}
    result=kit.call('job.run',{'job_id':j['id'],'plan_hash':j['plan']['sha256']})
    assert len(kit.store.load()['records'])==3  # original two plus committed output, no stored intermediate
    directory=Path(result['artifacts']['directory']);report=(directory/'report.html').read_text()
    comparison=json.loads((directory/'fragment-planning.json').read_text())
    assert comparison==j['plan']['context']['fragment_previews'] and 'Fragment preparation and annotation comparison' in report
    assert 'excluded_0' in report and 'excluded_1' in report
    source_records=json.loads((directory/'source-records.json').read_text());assert source_records==records
    assert kit.call('job.run',{'job_id':j['id'],'plan_hash':j['plan']['sha256']})['design']['id']==result['design']['id']


def test_changed_source_and_changed_range_invalidate_plan(tmp_path):
    kit=Toolkit(tmp_path/'workspace');j,p,records=plan(kit)
    j=kit.call('job.plan',{'job_id':j['id'],'expected_revision':j['revision'],'plan':p})['job'];old=j['plan']['sha256']
    p['operation']['fragments'][1]['ranges'][0]['end']-=1
    with pytest.raises(ToolError):kit.call('job.plan',{'job_id':j['id'],'expected_revision':j['revision'],'plan':p})
    assert kit.call('job.get',{'job_id':j['id']})['job']['plan']['sha256']==old
    state=kit.store.load();state['records'][records[0]['id']]['description']='Changed evidence';kit.store.save(state)
    with pytest.raises(ToolError) as e:kit.call('job.run',{'job_id':j['id'],'plan_hash':old})
    assert e.value.code=='STALE_SOURCE' and not kit.store.load()['designs']


def test_invalid_fragment_plan_is_atomic_and_shared_service_checks_scope(tmp_path):
    kit=Toolkit(tmp_path/'workspace');j,p,records=plan(kit);p['operation']['fragments'][0]['ranges'][1]['end']=50
    before=kit.store.path.read_bytes()
    with pytest.raises(ToolError) as e:kit.call('job.plan',{'job_id':j['id'],'expected_revision':j['revision'],'plan':p})
    assert e.value.code=='FRAGMENT_PARTIAL_FEATURE' and kit.store.path.read_bytes()==before
    for payload in [
        {'mode':'inspect','fragments':p['operation']['fragments']},
        {'mode':'create','fragments':p['operation']['fragments']},
        {'mode':'create','fragments':p['operation']['fragments'],'assembly':p['operation']['assembly'],'part_ids':[records[0]['id']]}
    ]:
        with pytest.raises(APIError) as e:kit.service.design(payload)
        assert e.value.code in ('FRAGMENT_MODE','FRAGMENT_OPERATION')


def test_reverse_compound_origin_feature_keeps_biological_extraction_order():
    records,specs=records_specs(FROZEN['cases'][1]);source=records[0]
    from vget.sequence import _location_text, _segments
    n=source['length'];loc=CompoundLocation([SimpleLocation(0,44,-1),SimpleLocation(n-16,n,-1)],'join')
    source['features'][0].update(location=_location_text(loc,n),segments=_segments(loc))
    spec=copy.deepcopy(specs[0]);spec['orientation']='reverse'
    prepared,comparison=prepare_fragment(source,spec)
    projected=next(f for f in prepared['features'] if f['label']=='backbone_core')
    from Bio.SeqFeature import Location
    mapped=Location.fromstring(projected['location'],length=prepared['length'])
    assert loc.extract(Seq(source['sequence']))==mapped.extract(Seq(prepared['sequence']))
    assert projected['segments']==[{'start':24,'end':84,'strand':1}]
    assert comparison['features'][0]['status']=='retained'


def test_outside_and_unlocalized_bibliography_remain_explicit():
    records,specs=records_specs(FROZEN['cases'][0]);source=records[0]
    reference=source['metadata']['annotations']['references'][0]
    reference['location']=['1..3']
    source['metadata']['annotations']['references'].append({**copy.deepcopy(reference),'title':'Unlocalized fixture','location':[]})
    prepared,comparison=prepare_fragment(source,specs[0])
    assert [r['status'] for r in comparison['references']]==['outside','unlocalized']
    assert len(prepared['metadata']['annotations']['references'])==2
    assert all(r['location']==[] for r in prepared['metadata']['annotations']['references'])


def test_fragment_limits_and_source_identity_are_explicit():
    source=parse_records('>large\n'+'A'*10001+'\n','large.fasta')[0]
    source['topology']='linear'
    spec={'record_id':source['id'],'ranges':[{'start':0,'end':10001}],'orientation':'forward'}
    with pytest.raises(SequenceError) as e:prepare_fragment(source,spec)
    assert e.value.code=='FRAGMENT_LIMIT'
    spec['ranges'][0]['end']=10000
    assert prepare_fragment(source,spec)[0]['length']==10000
    spec['record_id']='another'
    with pytest.raises(SequenceError) as e:prepare_fragment(source,spec)
    assert e.value.code=='FRAGMENT_SPEC'


def test_point_annotations_are_rejected_instead_of_silently_excluded():
    records,specs=records_specs(FROZEN['cases'][0]);source=records[0]
    from vget.sequence import _location_text, _segments
    point=SimpleLocation(40,40,1)
    source['features'][0].update(location=_location_text(point,source['length']),segments=_segments(point))
    with pytest.raises(SequenceError) as e:prepare_fragment(source,specs[0])
    assert e.value.code=='FRAGMENT_POINT_LOCATION'


def test_direct_service_and_brief_share_fragment_operation(tmp_path):
    kit=Toolkit(tmp_path/'workspace');j,p,records=plan(kit)
    payload={k:v['value'] for k,v in j['decisions'].items()}|p['operation']|{'objective':j['objective']}
    assert kit.service.brief(payload)['ready']
    before=copy.deepcopy(kit.store.load()['records'])
    design=kit.service.design(payload)
    assert design['record']['sequence']==FROZEN['cases'][1]['expected_sequence']
    assert all(kit.store.load()['records'][rid]==record for rid,record in before.items())
    assert any(c['id']=='fragment_preparation' and c['status']=='pass' for c in design['checks'])


def test_whole_record_source_annotation_is_projected_with_explicit_audit():
    records,specs=records_specs(FROZEN['cases'][1]);source=records[0]
    from vget.sequence import _feature_from_bio
    f=_feature_from_bio(SeqFeature(SimpleLocation(0,source['length'],1),type='source',qualifiers={'organism':['synthetic construct'],'note':['Original record scope']}),source['length'],3)
    source['features'].append(f)
    fragment,comparison=prepare_fragment(source,specs[0])
    projected=next(g for g in fragment['features'] if g['type']=='source')
    assert projected['qualifiers']==f['qualifiers']
    assert projected['segments']==[{'start':0,'end':108,'strand':1}]
    assert projected['provenance']['outcome']=='projected_source'
    audit=comparison['features'][-1]
    assert audit['status']=='projected_source' and audit['source_bases']==124 and audit['selected_bases']==108
    # A narrower source annotation is not automatically treated as record scope.
    source['features'][-1]=_feature_from_bio(SeqFeature(SimpleLocation(0,90,1),type='source',qualifiers=f['qualifiers']),source['length'],3)
    with pytest.raises(SequenceError) as e:prepare_fragment(source,specs[0])
    assert e.value.code=='FRAGMENT_PARTIAL_FEATURE'


def test_projected_source_annotations_survive_genbank_roundtrip(tmp_path):
    case=FROZEN['cases'][1];kit=Toolkit(tmp_path/'workspace');items=[]
    for name,raw in raw_inputs(case):
        bio=SeqIO.read(io.StringIO(raw.decode()),'genbank')
        bio.features.append(SeqFeature(SimpleLocation(0,len(bio),1),type='source',qualifiers={'organism':['synthetic construct'],'note':['Original record-wide source annotation']}))
        text=io.StringIO();SeqIO.write(bio,text,'genbank');items.append((name,text.getvalue().encode()))
    records=kit.service.import_files(items)['records']
    specs=[{'record_id':records[s['source_index']]['id'],'ranges':copy.deepcopy(s['ranges']),'orientation':s['orientation']} for s in case['fragments']]
    d=kit.service.design({'mode':'create','host_id':'HP-EC','name':'scoped_source','topology':'circular','convention_id':None,'objective':case['objective'],
        'fragments':specs,'assembly':{'method':'homology','overlaps':case['overlaps']}},agent_context={})
    bio=SeqIO.read(kit.store.packages/d['id']/'construct.gbk','genbank')
    scopes=[f for f in bio.features if f.type=='source'];assert len(scopes)==2
    assert [[(int(p.start),int(p.end),p.strand) for p in f.location.parts] for f in scopes]==[[(0,108,1)],[(0,24,-1),(84,151,-1)]]
    assert all(f.qualifiers['organism']==['synthetic construct'] for f in scopes)
    assert all(r['features'][-1]['status']=='projected_source' for r in d['record']['metadata']['fragment_planning'])
    # A disjoint citation must not be serialized as its 1..151 bounding range.
    references=bio.annotations['references']
    assert references[1].location==[]
    assert 'complement(join(85..151,1..24))' in references[1].comment
    assert 'Structured reference range omitted' in references[1].comment
