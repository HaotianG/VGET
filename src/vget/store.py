"""Atomic local workspace storage with shared CLI/GUI process locking. No remote access."""
from __future__ import annotations
import copy
import hashlib
import io
import json
import os
from pathlib import Path
import random
from .locking import workspace_lock
import uuid
from datetime import datetime, timezone

HOSTS = [dict(id=i,name=n,status='unevaluated') for i,n in [
    ('HP-EC','E. coli'),('HP-BS','B. subtilis'),('HP-SC','S. cerevisiae'),
    ('HP-PP','Pichia pastoris'),('HP-SF9','Sf9'),('HP-SF21','Sf21'),
    ('HP-H5','High-5'),('HP-CHO','CHO'),('HP-HEK','HEK293')]]

def now():
    return datetime.now(timezone.utc).isoformat()

def uid(prefix):
    return f'{prefix}-{uuid.uuid4().hex[:16]}'

def digest(data):
    return hashlib.sha256(data).hexdigest()

def json_bytes(value):
    return (json.dumps(value,ensure_ascii=False,sort_keys=True,indent=2,allow_nan=False)+'\n').encode()

class SourceIntegrityError(ValueError):
    pass

class Store:
    def __init__(self, root, seed_demo=True):
        self.root=Path(root).resolve()
        self.root.mkdir(parents=True,exist_ok=True,mode=0o700)
        self.raw=self.root/'sources';self.raw.mkdir(exist_ok=True,mode=0o700)
        self.packages=self.root/'packages';self.packages.mkdir(exist_ok=True,mode=0o700)
        self.path=self.root/'state.json'
        self.lock=workspace_lock(self.root/'.lock')
        with self.lock:
            if not self.path.exists():
                self.save(self.seed() if seed_demo else {'schema_version':'0.2.0','records':{},'designs':{},'conventions':{},'jobs':{},'evidence':{},'created_at':now()})

    def load(self):
        with self.lock:
            return json.loads(self.path.read_text())

    def save(self,state):
        with self.lock:
            temporary=self.path.with_name('state-'+uuid.uuid4().hex+'.tmp')
            with temporary.open('xb') as f:
                f.write(json_bytes(state));f.flush();os.fsync(f.fileno())
            os.replace(temporary,self.path)

    def keep_raw(self,data):
        h=digest(data);path=self.raw/h
        if path.exists() or path.is_symlink():
            if path.is_symlink() or not path.is_file() or digest(path.read_bytes())!=h:
                raise SourceIntegrityError('An existing original evidence blob is missing, changed or indirect; it was not overwritten.')
        else:
            with path.open('xb') as f: f.write(data)
        return h

    def seed(self):
        from Bio import SeqIO
        from Bio.Seq import Seq
        from Bio.SeqRecord import SeqRecord
        from Bio.SeqFeature import SeqFeature, SimpleLocation
        from .sequence import parse_records
        rng=random.Random(11973)
        def bases(n):return ''.join(rng.choice('ACGT') for _ in range(n))
        backbone=bases(480);insert=bases(160);replacement=bases(220)
        specs=[('Demo_backbone',backbone,[('Demo_backbone',0,480,1)],'linear'),
               ('Demo_insert',insert,[('Demo_insert',0,160,1)],'linear'),
               ('Demo_replacement',replacement,[('Demo_replacement',0,220,1)],'linear'),
               ('Demo_parent',backbone[:240]+insert+backbone[240:],
                [('Left_context',0,240,1),('Demo_insert',240,400,1),('Right_context',400,640,-1)],'circular')]
        records={}
        for name,sequence,features,topology in specs:
            rec=SeqRecord(Seq(sequence),id=name,name=name,description='Synthetic software fixture; no biological function asserted.')
            rec.annotations={'molecule_type':'DNA','topology':topology,'date':'21-SEP-2026','comment':'DEMONSTRATION ONLY. Arbitrary bases for software testing, not a laboratory construct.'}
            rec.features=[SeqFeature(SimpleLocation(start,end,strand=strand),type='misc_feature',qualifiers={'label':[label],'note':['Synthetic software fixture; uncharacterized.']}) for label,start,end,strand in features]
            f=io.StringIO();SeqIO.write(rec,f,'genbank');raw=f.getvalue().encode()
            r=parse_records(raw.decode(),name+'.gbk')[0]
            r['id']=uid('rec');r['source']={'kind':'demo','filename':name+'.gbk','raw_sha256':self.keep_raw(raw),'evidence':'synthetic software fixture','imported_at':now()}
            r['_import_key']=digest(raw)+':0:demo';records[r['id']]=r
        convention={'id':'demo-convention','name':'Demo sequence composition','notes':'Assembly family: sequence_composition\nMax length: 100000','rules':[{'kind':'assembly_family','value':'sequence_composition','source_text':'Assembly family: sequence_composition'},{'kind':'max_length','value':100000,'source_text':'Max length: 100000'}],'unsupported':[],'state':'active','version':1,'created_at':now(),'reviewed_at':now(),'review_basis':'Bundled software demonstration, not a lab cloning convention.'}
        return {'schema_version':'0.1.0','records':records,'designs':{},'conventions':{convention['id']:convention},'created_at':now()}
