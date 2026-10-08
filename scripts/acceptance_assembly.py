"""Independent frozen-oracle acceptance through the installed CLI, offline."""
import argparse, base64, hashlib, io, json, re, subprocess, sys
from pathlib import Path
from Bio import SeqIO
from Bio.Seq import Seq
from Bio.SeqFeature import SeqFeature, SimpleLocation, Reference
from Bio.SeqRecord import SeqRecord
import vget

parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--output',type=Path,required=True,help='New local directory; previous runs are never overwritten')
parser.add_argument('--expect-backend-missing',action='store_true',help='Verify controlled failure in a base wheel environment without the optional extra')
args=parser.parse_args();out=args.output.resolve()
if out.exists():raise SystemExit('Choose a fresh output directory.')
out.mkdir(parents=True);(out/'inputs').mkdir()
root=Path(__file__).resolve().parents[1]
frozen=root/'examples/overlap-fixtures.json';fixture=json.loads(frozen.read_text())
cli=Path(sys.executable).with_name('vget');workspace=out/'workspace';receipts=[]

def call(tool,args,code=0):
    p=subprocess.run([str(cli),'--workspace',str(workspace),'call',tool,'--input','-'],input=json.dumps(args),text=True,capture_output=True,timeout=20)
    r=json.loads(p.stdout);receipts.append({'tool':tool,'exit_code':p.returncode,'response':r})
    (out/'cli-receipts.json').write_text(json.dumps(receipts,indent=2)+'\n')
    assert p.returncode==code,(tool,p.returncode,p.stderr,r)
    return r.get('data',r)

def inputs(case,index):
    paths=[];bios=[]
    for k,name in enumerate(('backbone','insert')):
        r=SeqRecord(Seq(case[name]),id=('BB' if k==0 else 'INS')+str(index),name=('BB' if k==0 else 'INS')+str(index),description='Synthetic prepared fragment for '+case['id'])
        r.annotations={'molecule_type':'DNA','topology':'linear'}
        r.features=[SeqFeature(SimpleLocation(24,len(r)-24,strand=1 if name=='backbone' else -1),type='misc_feature',qualifiers={'label':[name+'_core'],'note':['Original synthetic annotation']}),
            SeqFeature(SimpleLocation(len(r)-24,len(r),strand=1),type='misc_feature',qualifiers={'label':['right_overlap' if k==0 else 'origin_overlap']})]
        if k==1 and 'spanning_insert_feature' in case:
            s=case['spanning_insert_feature'];r.features.append(SeqFeature(SimpleLocation(s['input_start'],s['input_end'],strand=s['strand']),type='misc_feature',qualifiers={'label':['origin_spanning']}))
        ref=Reference();ref.title='Synthetic fixture bibliography';ref.authors='Fixture';ref.journal='Software test';ref.location=[SimpleLocation(0,len(r))];r.annotations['references']=[ref]
        p=out/'inputs'/(r.name+'.gbk');SeqIO.write(r,p,'genbank');paths.append(str(p));bios.append(r)
    recs=call('library.import',{'paths':paths})['records'];assert len(recs)==2
    return recs,bios,paths

def plan(case,index,length=151,code=0):
    recs,bios,paths=inputs(case,index);ids=[r['id'] for r in recs]
    j=call('job.start',{'objective':'Assemble these exact synthetic prepared fragments into a circular sequence using the two explicit terminal homologies; preserve every supported source annotation and report junction evidence. No experimental claim.'})['job']
    vals={'mode':'create','host_id':'HP-EC','name':'overlap_'+str(index),'topology':'circular','convention_id':None}
    criteria=[{'id':'length','text':'Exact independent fixture length','blocks_export':True,'check':{'kind':'length','value':length}},
              {'id':'sequence','text':'Exact independent fixture sequence','blocks_export':True,'check':{'kind':'sequence_sha256','value':hashlib.sha256(fixture['expected_sequence'].encode()).hexdigest()}}]
    j=call('job.update',{'job_id':j['id'],'expected_revision':j['revision'],'decisions':[{'field':k,'value':v,'origin':'agent','reason':'Bounded synthetic fixture; host intent unassessed'} for k,v in vals.items()],'criteria':criteria})['job']
    p={'operation':{'part_ids':ids,'assembly':{'method':'homology','overlaps':fixture['overlaps']}},'summary':'Prepared linear inputs, explicit forward junction path, unique circular prediction.',
       'selections':[{'record_id':rid,'reason':'Frozen synthetic source','evidence_refs':[rid]} for rid in ids],'alternatives':[],
       'criteria':[{'id':c['id'],'status':'satisfied_by_plan','evaluation':'Independent fixture oracle; engine checks the materialized record','evidence_refs':ids} for c in criteria]}
    planned=call('job.plan',{'job_id':j['id'],'expected_revision':j['revision'],'plan':p},code)
    return planned,recs,bios,paths

call('workspace.init',{'empty':True})
status=call('context.get',{})['capabilities']['assembly']
if args.expect_backend_missing:
    assert not status['available'] and status['installed_version'] is None
    planned,_,_,_=plan(fixture['cases'][0],0);j=planned['job']
    error=call('job.run',{'job_id':j['id'],'plan_hash':j['plan']['sha256']},2)
    assert error['error']['code']=='ASSEMBLY_BACKEND_MISSING' and call('job.get',{'job_id':j['id']})['job']['status']=='failed'
    (out/'acceptance.json').write_text(json.dumps({'package_version':vget.__version__,'installed_package':vget.__file__,'calls':len(receipts),'missing_backend':'ASSEMBLY_BACKEND_MISSING','receipts':receipts},indent=2)+'\n')
    print('PASS: base wheel reports missing optional backend, retains failed job and exports no assembly fallback.',flush=True)
    raise SystemExit(0)
assert status['available'] and status['installed_version']=='5.5.8'
accepted=[];rejected=[]
for index,case in enumerate(fixture['cases']):
    if case['kind']!='success':
        error,_,_,_=plan(case,index,code=2)
        expected='ASSEMBLY_OVERLAP_MISMATCH' if case['kind']=='no_valid_circle' else 'ASSEMBLY_AMBIGUOUS'
        assert error['error']['code']==expected;rejected.append({'case':case['id'],'code':expected});continue
    planned,recs,bios,paths=plan(case,index);j=planned['job']
    r=call('job.run',{'job_id':j['id'],'plan_hash':j['plan']['sha256']})
    assert call('job.run',{'job_id':j['id'],'plan_hash':j['plan']['sha256']})['design']['id']==r['design']['id']
    exported=call('artifact.export',{'job_id':j['id'],'destination':str(out/'reports'/case['id'])})['artifacts']
    raw=Path(exported['genbank']).read_bytes();html=Path(exported['html']).read_text();bio=SeqIO.read(io.StringIO(raw.decode()),'genbank')
    assert str(bio.seq)==case['expected_sequence'] and bio.annotations['topology']=='circular'
    features={f.qualifiers['label'][0]:f for f in bio.features}
    for f in fixture['expected_features']:
        loc=features[f['label']].location
        assert [(int(p.start),int(p.end),p.strand) for p in loc.parts]==[(f['start'],f['end'],f['strand'])]
    if 'spanning_insert_feature' in case:
        s=case['spanning_insert_feature'];assert [(int(p.start),int(p.end),p.strand) for p in features['origin_spanning'].location.parts]==[(a,b,s['strand']) for a,b in s['expected_segments']]
    for source in bios:
        for f in source.features:
            projected=features[f.qualifiers['label'][0]]
            assert f.extract(source.seq)==projected.extract(bio.seq) and f.qualifiers==projected.qualifiers
    assert len(bio.features)==sum(len(r.features) for r in bios) and len(bio.annotations['references'])==2
    assert 'pydna 5.5.8' in bio.annotations['comment']
    assert base64.b64decode(re.search(r'data:application/octet-stream;base64,([A-Za-z0-9+/=]+)',html).group(1))==raw
    assert 'Homology assembly prediction' in html and all(h in html for h in fixture['overlaps']) and '<script' not in html
    manifest=json.loads(Path(exported['manifest']).read_text());directory=Path(exported['manifest']).parent
    for f in manifest['files']:
        data=(directory/f['path']).read_bytes();assert hashlib.sha256(data).hexdigest()==f['sha256'] and len(data)==f['bytes']
    originals=json.loads((directory/'evidence.json').read_text())['originals']
    for path in paths:
        data=Path(path).read_bytes();assert any(hashlib.sha256(data).hexdigest()==f['sha256'] and (directory/f['path']).read_bytes()==data for f in originals)
    accepted.append({'case':case['id'],'length':len(bio),'features':len(bio.features),'report':exported['html']})

# Typed criteria must use the deduplicated assembly length, never source sum.
p,_,_,_=plan(fixture['cases'][0],len(fixture['cases']),length=199);j=p['job']
error=call('job.run',{'job_id':j['id'],'plan_hash':j['plan']['sha256']},2)
assert error['error']['code']=='CRITERION_FAILED'
assert call('job.get',{'job_id':j['id']})['job']['status']=='failed'
(out/'acceptance.json').write_text(json.dumps({'package_version':vget.__version__,'installed_package':vget.__file__,
    'fixture_sha256':hashlib.sha256(frozen.read_bytes()).hexdigest(),'calls':len(receipts),'accepted_pairs':accepted,
    'rejected_cases':rejected,'negative_typed_length':'CRITERION_FAILED','receipts':receipts},indent=2)+'\n')
print(f'PASS: {len(accepted)} assembly pairs; incompatible/ambiguous cases rejected; typed length failure, annotations, source bytes, junctions, download and manifest hashes verified. Calls: {len(receipts)}',flush=True)
