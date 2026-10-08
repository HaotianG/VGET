"""Run actual installed CLI calls; independent byte/sequence/annotation oracles."""
import argparse, base64, hashlib, io, json, re, subprocess, sys, warnings
import vget
from pathlib import Path
from Bio import SeqIO
from Bio.Seq import Seq
from Bio.SeqFeature import SeqFeature, SimpleLocation
from Bio.SeqRecord import SeqRecord

root=Path(__file__).resolve().parents[1]
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--output', type=Path, required=True, help='Fresh local directory; existing directories are refused')
parser.add_argument('--cli', type=Path, default=Path(sys.executable).with_name('vget'))
args=parser.parse_args()
run=args.output.resolve()
if run.exists(): raise SystemExit('Choose a new output directory; acceptance never overwrites an earlier run.')
run.mkdir(parents=True)
cli=args.cli.resolve()
workspace=run/'workspace'
outputs=run/'reports'
outputs.mkdir()
receipts=[]

def call(tool,args,expected_code=0):
    p=subprocess.run([str(cli),'--workspace',str(workspace),'call',tool,'--input','-'],input=json.dumps(args),capture_output=True,text=True,timeout=20)
    r=json.loads(p.stdout)
    receipts.append({'tool':tool,'exit_code':p.returncode,'response':r})
    assert p.returncode==expected_code,(tool,p.returncode,p.stderr,r)
    return r.get('data',r)


def execute(record_ids,mode,name,operation,expected,criteria=None,expected_warned=False):
    j=call('job.start',{'objective': 'Inspect the supplied public reference unchanged.' if mode=='inspect' else 'Compute a synthetic software fixture with an exact, checked sequence and retained annotations.'})['job']
    topology=call('record.inspect',{'record_id':record_ids[0]})['record']['topology'] if mode=='inspect' else 'circular'
    values={'mode':mode,'host_id':None if mode=='inspect' else 'HP-EC','name':name,'topology':topology,'convention_id':None}
    criteria=criteria or [{'id':'exact_sequence','text':'Exact expected sequence content','blocks_export':True,'check':{'kind':'sequence_sha256','value':hashlib.sha256(expected.encode()).hexdigest()}}]
    j=call('job.update',{'job_id':j['id'],'expected_revision':j['revision'],'decisions':[{'field':k,'value':v,'origin':'agent','reason':'Bounded acceptance fixture; no biological performance assessment.'} for k,v in values.items()],'criteria':criteria})['job']
    plan={'operation':operation,'summary':'Unchanged public inspection or exact synthetic operation; no functional design claim.',
        'selections':[{'record_id':rid,'reason':'Exact acceptance source','evidence_refs':[rid]} for rid in record_ids], 'alternatives':[],
        'criteria':[{'id':c['id'],'status':'satisfied_by_plan','evaluation':'Verified expected source sequence; independent post-export check required.','evidence_refs':record_ids} for c in criteria]}
    j=call('job.plan',{'job_id':j['id'],'expected_revision':j['revision'],'plan':plan})['job']
    result=call('job.run',{'job_id':j['id'],'plan_hash':j['plan']['sha256']})
    repeated=call('job.run',{'job_id':j['id'],'plan_hash':j['plan']['sha256']})
    assert repeated['design']['id']==result['design']['id']
    exported=call('artifact.export',{'job_id':j['id'],'destination':str(outputs/name)})
    files=exported['artifacts'];raw=Path(files['genbank']).read_bytes();html=Path(files['html']).read_text()
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter('always')
        bio=SeqIO.read(io.StringIO(raw.decode('utf-8-sig')),'genbank')
    assert bool(caught)==expected_warned, [str(w.message) for w in caught]
    assert str(bio.seq)==expected
    encoded=re.search(r'data:application/octet-stream;base64,([A-Za-z0-9+/=]+)',html).group(1)
    assert base64.b64decode(encoded)==raw
    assert '<svg' in html and '<script' not in html and 'https://' not in re.sub(r'<details>.*?</details>','',html,flags=re.S)
    manifest=json.loads(Path(files['manifest']).read_text())
    for f in manifest['files']:
        data=(outputs/name/f['path']).read_bytes();assert hashlib.sha256(data).hexdigest()==f['sha256'] and len(data)==f['bytes']
    return j,exported,bio


call('workspace.init',{})
records=call('library.search',{})['records']
for rec in records:
    inspected=call('record.inspect',{'record_id':rec['id'],'include_sequence':True})['record']
    name='reference-'+rec['name']
    _,exported,bio=execute([rec['id']],'inspect',name,{'record_id':rec['id']},inspected['sequence'])
    original=workspace/'originals'/rec['source']['raw_sha256']
    # Store uses a content-addressed raw directory; find exact hash under it.
    original=next(p for p in workspace.rglob(rec['source']['raw_sha256']) if p.is_file())
    assert Path(exported['artifacts']['genbank']).read_bytes()==original.read_bytes()

example=root/'examples'
call('library.import',{'paths':[str(example/(n+'.gbk')) for n in ['Demo_backbone','Demo_insert','Demo_parent','Demo_replacement']]})
records=call('library.search',{})['records'];by={r['name']:r for r in records}
a=SeqIO.read(example/'Demo_backbone.gbk','genbank');b=SeqIO.read(example/'Demo_insert.gbk','genbank')
ids=[by['Demo_backbone']['id'],by['Demo_insert']['id']]
_,_,composed=execute(ids,'create','synthetic-create',{'part_ids':ids},str(a.seq)+str(b.seq))
# Independent original feature offset oracle.
assert [(int(f.location.start),int(f.location.end)) for f in composed.features]==[(int(f.location.start),int(f.location.end)) for f in a.features]+[(len(a)+int(f.location.start),len(a)+int(f.location.end)) for f in b.features]
parent=SeqIO.read(example/'Demo_parent.gbk','genbank');replacement=SeqIO.read(example/'Demo_replacement.gbk','genbank')
p=by['Demo_parent'];target=next(f for f in p['features'] if f['label']=='Demo_insert')
start,end=map(int,re.findall(r'\d+',target['location']))
# Original target range is 1-based inclusive. Literal splicing is an independent oracle.
expected=str(parent.seq[:start-1])+str(replacement.seq)+str(parent.seq[end:])
execute([p['id'],by['Demo_replacement']['id']],'modify','synthetic-modify',{'parent_id':p['id'],'target_feature_id':target['id'],'replacement_id':by['Demo_replacement']['id'],'protected_feature_ids':[]},expected)
# Verify failed typed requirements produce no design, using actual CLI error contract.
j=call('job.start',{'objective':'Synthetic negative control: demand 1000 bases for a shorter source.'})['job']
vals={'mode':'create','host_id':'HP-EC','name':'negative-control','topology':'circular','convention_id':None}
j=call('job.update',{'job_id':j['id'],'expected_revision':j['revision'],'decisions':[{'field':k,'value':v,'origin':'agent','reason':'Negative control'} for k,v in vals.items()],'criteria':[{'id':'size','text':'Exactly 1000 bases','blocks_export':True,'check':{'kind':'length','value':1000}}]})['job']
plan={'operation':{'part_ids':ids},'summary':'Deliberately inconsistent caller assessment.','selections':[{'record_id':rid,'reason':'Synthetic input','evidence_refs':[rid]} for rid in ids],'alternatives':[],'criteria':[{'id':'size','status':'satisfied_by_plan','evaluation':'Deliberate false assessment to test engine gate','evidence_refs':ids}]}
j=call('job.plan',{'job_id':j['id'],'expected_revision':j['revision'],'plan':plan})['job']
error=call('job.run',{'job_id':j['id'],'plan_hash':j['plan']['sha256']},2)
assert error['error']['code']=='CRITERION_FAILED'
assert call('job.get',{'job_id':j['id']})['job']['status']=='failed'
# Ambiguous synthetic original: strict import fails; explicit inspection preserves bytes.
warned=SeqRecord(Seq('ACGT'*200),id='Ambiguous_fixture',name='Ambiguous_fixture',description='Deliberately ambiguous synthetic software fixture; no biological use')
warned.annotations={'molecule_type':'DNA','topology':'circular'}
warned.features=[SeqFeature(SimpleLocation(10,20),type='misc_feature',qualifiers={'label':['ambiguous_fixture']})]
stream=io.StringIO();SeqIO.write(warned,stream,'genbank')
raw=b'\xef\xbb\xbf'+stream.getvalue().encode().replace(b'11..20',b'784..90').replace(b'\n',b'\r\n')+b' \t\r\n'
source=run/'ambiguous-synthetic.gbk';source.write_bytes(raw)
strict=call('library.import',{'paths':[str(source)]},2)
rec=call('library.import',{'paths':[str(source)],'inspection_only':True})['records'][0]
assert rec['metadata']['parser_warnings'] and rec['metadata']['original_feature_locations']==['784..90'] and rec['metadata']['inspection_only'] is True
_,exported,_=execute([rec['id']],'inspect','warned-inspection',{'record_id':rec['id']},str(warned.seq),expected_warned=True)
assert Path(exported['artifacts']['genbank']).read_bytes()==raw
html=Path(exported['artifacts']['html']).read_text()
assert 'parser interpretation' in html.lower() and '784..90' in html
(run/'acceptance.json').write_text(json.dumps({'interpreter':sys.executable,'installed_package':vget.__file__,'package_version':vget.__version__,
    'calls':len(receipts),'public_unchanged_pairs':6,'synthetic_transformed_pairs':2,'warned_inspection_pairs':1,
    'negative_control':'CRITERION_FAILED; no completed design','warned_strict_import_error':strict['error']['code'],
    'receipts':receipts},indent=2)+'\n')
print(f'PASS: 9 GenBank/HTML pairs, independent byte/sequence/annotation checks, safe retries, manifest hashes and typed failure gate. Receipts: {run / "acceptance.json"}',flush=True)
