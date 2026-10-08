"""Offline objective-to-fragment-to-artifact CLI replay with independent oracles.

The script supplies explicit caller reasoning. It does not test an embedded
language interpreter, external agents, biological function or reaction success.
"""
import argparse, base64, copy, hashlib, io, json, re, subprocess, sys
from pathlib import Path
import xml.etree.ElementTree as ET
from Bio import SeqIO
from Bio.Seq import Seq
from Bio.SeqFeature import CompoundLocation, Reference, SeqFeature, SimpleLocation
from Bio.SeqRecord import SeqRecord
import vget

parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--output',type=Path,required=True,help='Fresh directory; no existing artifacts are overwritten')
parser.add_argument('--expect-backend-missing',action='store_true')
args=parser.parse_args();out=args.output.resolve()
if out.exists():raise SystemExit('Choose a fresh output directory.')
out.mkdir(parents=True);(out/'inputs').mkdir()
fixture_path=Path(__file__).resolve().parents[1]/'examples/fragment-fixtures.json'
fixture=json.loads(fixture_path.read_text());workspace=out/'workspace'
cli=Path(sys.executable).with_name('vget');receipts=[];accepted=[];rejected=[]


def call(name,arguments,code=0):
    process=subprocess.run([str(cli),'--workspace',str(workspace),'call',name,'--input','-'],input=json.dumps(arguments),text=True,capture_output=True,timeout=25)
    response=json.loads(process.stdout)
    receipts.append({'tool':name,'arguments':arguments,'exit_code':process.returncode,'response':response})
    (out/'cli-receipts.json').write_text(json.dumps(receipts,indent=2)+'\n')
    assert process.returncode==code,(name,process.returncode,process.stderr,response)
    return response.get('data',response)


def import_case(case):
    paths=[];bios=[]
    for spec in case['sources']:
        name='F'+hashlib.sha256(spec['name'].encode()).hexdigest()[:11]
        bio=SeqRecord(Seq(spec['sequence']),id=name,name=name,description=spec['name']+'; synthetic software source')
        bio.annotations={'molecule_type':'DNA','topology':spec['topology']}
        for f in spec['features']:
            parts=[SimpleLocation(a,b,strand=s) for a,b,s in f['parts']]
            bio.features.append(SeqFeature(parts[0] if len(parts)==1 else CompoundLocation(parts,'join'),type=f['type'],qualifiers=copy.deepcopy(f['qualifiers'])))
        ref=Reference()
        for key in ('title','authors','journal'):setattr(ref,key,spec['reference'][key])
        ref.location=[SimpleLocation(a,b,strand=s) for a,b,s in spec['reference']['parts']]
        bio.annotations['references']=[ref]
        path=out/'inputs'/(name+'.gbk');SeqIO.write(bio,path,'genbank');paths.append(str(path));bios.append(bio)
    records=call('library.import',{'paths':paths})['records'];assert len(records)==2
    specs=[{'record_id':records[s['source_index']]['id'],'ranges':copy.deepcopy(s['ranges']),'orientation':s['orientation']} for s in case['fragments']]
    for record in records:
        inspected=call('record.inspect',{'record_id':record['id'],'include_sequence':True})['record']
        assert inspected['sequence_sha256']==record['sequence_sha256']
    return records,specs,bios,paths


def plan(case,records,specs,question=None,code=0):
    ids=[r['id'] for r in records]
    j=call('job.start',{'objective':case['objective']})['job']
    vals={'mode':'create','host_id':'HP-EC','name':case['id'],'topology':'circular','convention_id':None}
    criteria=[{'id':'length','text':'Frozen literal output length','blocks_export':True,'check':{'kind':'length','value':len(case['expected_sequence'])}},
        {'id':'sequence','text':'Frozen literal sequence hash','blocks_export':True,'check':{'kind':'sequence_sha256','value':hashlib.sha256(case['expected_sequence'].encode()).hexdigest()}},
        {'id':'features','text':'Complete selected annotations only','blocks_export':True,'check':{'kind':'feature_count','value':len(case['expected_features'])}}]
    update={'job_id':j['id'],'expected_revision':j['revision'],'decisions':[{'field':key,'value':value,'origin':'agent','reason':'Explicit synthetic fixture intent; host profile records intent, compatibility unassessed','evidence_refs':ids} for key,value in vals.items()],'criteria':criteria,
        'assumptions':['Ranges and orientations are supplied as exact synthetic fixture facts; no source endpoints or reaction conditions were inferred.']}
    if question:update['questions']=[{'id':'range_choice','question':question,'blocks_export':True}]
    j=call('job.update',update)['job']
    p={'operation':{'fragments':specs,'assembly':{'method':'homology','overlaps':case['overlaps']}},
       'summary':'Apply the explicit source ranges and orientation, review retained/excluded annotations, then accept one unique circular homology prediction.',
       'selections':[{'record_id':r['id'],'reason':'Exact source inspected; ranges and orientation checked by fragment.preview. Outside flank features are explicitly excluded; complete selected features retained.','evidence_refs':[r['id']]} for r in records],
       'alternatives':[], 'criteria':[{'id':c['id'],'status':'satisfied_by_plan','evaluation':'Independent literal fixture oracle; the shared service checks the materialized record.','evidence_refs':ids} for c in criteria]}
    planned=call('job.plan',{'job_id':j['id'],'expected_revision':j['revision'],'plan':p},code)
    return planned,j,p


call('workspace.init',{'empty':True})
context=call('context.get',{});assert 'fragment_planning' in context['capabilities']
status=context['capabilities']['assembly']
assert status['available'] != args.expect_backend_missing
cases=fixture['cases'][:1] if args.expect_backend_missing else fixture['cases']
for case in cases:
    records,specs,bios,paths=import_case(case)
    previews=[]
    for spec in specs:
        preview=call('fragment.preview',{'fragment':spec})
        assert 'sequence' not in preview['fragment']
        comparison=preview['annotation_comparison'];previews.append(comparison)
        assert [f['status'] for f in comparison['features']].count('retained')==2
        assert [f['status'] for f in comparison['features']].count('excluded')==1
    planned,j,p=plan(case,records,specs);j=planned['job']
    assert j['plan']['context']['fragment_previews']==previews
    if args.expect_backend_missing:
        error=call('job.run',{'job_id':j['id'],'plan_hash':j['plan']['sha256']},2)
        assert error['error']['code']=='ASSEMBLY_BACKEND_MISSING'
        failed=call('job.get',{'job_id':j['id']})['job']
        assert failed['status']=='failed' and failed['design_id'] is None
        assert not any((workspace/'packages').iterdir())
        rejected.append({'case':'missing_backend_after_preparation','code':'ASSEMBLY_BACKEND_MISSING'})
        break
    result=call('job.run',{'job_id':j['id'],'plan_hash':j['plan']['sha256']})
    assert call('job.run',{'job_id':j['id'],'plan_hash':j['plan']['sha256']})['design']['id']==result['design']['id']
    artifacts=call('artifact.export',{'job_id':j['id'],'destination':str(out/'reports'/case['id'])})['artifacts']
    directory=Path(artifacts['directory']);raw=Path(artifacts['genbank']).read_bytes();bio=SeqIO.read(io.StringIO(raw.decode()),'genbank');html=Path(artifacts['html']).read_text()
    assert str(bio.seq)==case['expected_sequence'] and bio.annotations['topology']=='circular'
    expected={f['label']:f for f in case['expected_features']};actual={f.qualifiers['label'][0]:f for f in bio.features}
    assert set(actual)==set(expected) and len(bio.features)==len(expected)
    for label,f in actual.items():
        assert [[int(part.start),int(part.end),part.strand] for part in f.location.parts]==expected[label]['parts']
        assert f.qualifiers==expected[label]['qualifiers']
        original=next((source,g) for source in bios for g in source.features if g.qualifiers['label'][0]==label)
        assert original[1].extract(original[0].seq)==f.extract(bio.seq)
    assert len(bio.annotations['references'])==2 and all(r.title=='Synthetic source bibliography' for r in bio.annotations['references'])
    assert 'Explicit computational fragment preparation' in bio.annotations['comment']
    comparison=json.loads((directory/'fragment-planning.json').read_text());assert comparison==previews
    assert 'Fragment preparation and annotation comparison' in html and 'excluded_0' in html and 'excluded_1' in html and '<script' not in html
    assert base64.b64decode(re.search(r'data:application/octet-stream;base64,([A-Za-z0-9+/=]+)',html).group(1))==raw
    for svg in re.findall(r'<svg\b.*?</svg>',html,re.S):ET.fromstring(svg)
    evidence=json.loads((directory/'evidence.json').read_text())
    for path in paths:
        data=Path(path).read_bytes();assert any(hashlib.sha256(data).hexdigest()==f['sha256'] and (directory/f['path']).read_bytes()==data for f in evidence['originals'])
    for entry in json.loads((directory/'manifest.json').read_text())['files']:
        data=(directory/entry['path']).read_bytes();assert len(data)==entry['bytes'] and hashlib.sha256(data).hexdigest()==entry['sha256']
    sources=json.loads((directory/'source-records.json').read_text());assert [r['id'] for r in sources]==[r['id'] for r in records]
    accepted.append({'case':case['id'],'length':len(bio),'features':len(bio.features),'genbank':artifacts['genbank'],'html':artifacts['html']})

if not args.expect_backend_missing:
    partial=copy.deepcopy(specs);partial[0]['ranges'][0]['start']+=30
    error=call('fragment.preview',{'fragment':partial[0]},2)
    assert error['error']['code']=='FRAGMENT_PARTIAL_FEATURE'
    assert len(error['error']['details']['features'])==3
    error,_,_=plan(case,records,partial,code=2);assert error['error']['code']=='FRAGMENT_PARTIAL_FEATURE'
    rejected.append({'case':'cut_through_feature','code':'FRAGMENT_PARTIAL_FEATURE'})
    invalid=copy.deepcopy(specs[0]);invalid['ranges']=[]
    assert call('fragment.preview',{'fragment':invalid},2)['error']['code']=='FRAGMENT_RANGES'
    rejected.append({'case':'invalid_ranges','code':'FRAGMENT_RANGES'})
    ambiguous=copy.deepcopy(case);ambiguous['objective']='Assemble the synthetic library into a circle; choose endpoints for me, with no ranges or intended retained features supplied.'
    error,j,_=plan(ambiguous,records,specs,question='Which exact source ranges and retained annotations define the intended construct?',code=2)
    assert error['error']['code']=='NEEDS_INPUT'
    pending=call('job.get',{'job_id':j['id']})['job'];assert pending['status']=='needs_input' and pending['plan'] is None
    assert any(q['id']=='range_choice' and q['state']=='open' for q in pending['questions'])
    rejected.append({'case':'consequential_missing_range','code':'NEEDS_INPUT'})
    unsupported=call('job.start',{'objective':'Design PCR primers and validate the reaction conditions for these synthetic source records.'})['job']
    assessed=call('job.assess',{'job_id':unsupported['id'],'expected_revision':unsupported['revision'],'outcome':'unsupported',
        'explanation':'VGET supports explicit coordinate preparation and sequence prediction; primer design and reaction-condition validation are unavailable. No fabricated primer or construct is exported.',
        'evidence_refs':[r['id'] for r in records]})['job']
    assert assessed['status']=='unsupported' and assessed['design_id'] is None
    rejected.append({'case':'unsupported_primer_design','code':'unsupported'})

receipt={'package_version':vget.__version__,'installed_package':vget.__file__,'fixture_sha256':hashlib.sha256(fixture_path.read_bytes()).hexdigest(),
         'calls':len(receipts),'accepted_pairs':accepted,'rejected_cases':rejected,
         'scope':'Scripted offline tool workflow with caller-supplied reasoning and frozen synthetic objectives; no language-understanding, cross-agent or biological validation.',
         'receipts':receipts}
(out/'acceptance.json').write_text(json.dumps(receipt,indent=2)+'\n')
if args.expect_backend_missing:
    print(f'PASS: read-only fragment previews and a source-pinned plan work without the extra; missing backend retains a failed job and no output package. Calls: {len(receipts)}',flush=True)
else:
    print(f'PASS: {len(accepted)} fragment-planning artifact pairs; {len(rejected)} controlled outcomes; source bytes, feature extraction, annotation comparison, GenBank/HTML, safe retry and hashes verified. Calls: {len(receipts)}',flush=True)
