"""Agent-neutral, persistent objective → plan → artifact tools.

Language understanding belongs to the calling agent. This module records its
explicit choices, checks the tool contract, and executes exact local operations.
"""
from __future__ import annotations
import copy
import json
import os
from pathlib import Path
import re
import shutil
import tempfile
import zipfile
from . import registry, public_sources
from .contracts import TOOL_LIST, TOOLS, ToolError, validate
from .store import SourceIntegrityError, Store, HOSTS, digest, json_bytes, uid, now
from .service import Service, APIError, SOURCES, LIMITATIONS
from .criteria import validate_criteria
from .assembly import backend_status, validate_request
from .fragments import prepare_fragment, prepare_fragments
from .sequence import SequenceError

REQUIRED=('mode','host_id','name','topology','convention_id')

def fingerprint(value):return digest(json_bytes(value))

def without_bases(record):
    record=copy.deepcopy(record)
    record.pop('sequence',None)
    def clean(value):
        if isinstance(value,dict):
            if isinstance(value.get('catalogue'),dict):value['catalogue'].pop('sequence',None)
            for child in value.values():clean(child)
        elif isinstance(value,list):
            for child in value:clean(child)
    clean(record.get('metadata',{}))
    return record

def summary(record):
    value={k:copy.deepcopy(record.get(k)) for k in ('id','name','description','length','topology','sequence_sha256','source','metadata')} | {
        'features':[{'id':f['id'],'label':f['label'],'type':f['type'],'location':f['location']} for f in record['features']],
        'record_sha256':fingerprint(record)}
    return without_bases(value)

class Toolkit:
    def __init__(self,workspace):
        self.store=Store(workspace,seed_demo=False)
        self.service=Service(self.store)

    def call(self,name,arguments):
        if name not in TOOLS:raise ToolError('TOOL_NOT_FOUND',f'Unknown tool: {name}. Read `vget tools`.')
        validate(arguments,TOOLS[name]['input_schema'])
        try:
            # Entire calls serialize across CLI processes and the optional GUI.
            with self.store.lock:
                return self._dispatch(name,copy.deepcopy(arguments))
        except APIError as e:raise ToolError(e.code,str(e),e.details) from e
        except SourceIntegrityError as e:raise ToolError('SOURCE_INTEGRITY',str(e)) from e
        except (FileNotFoundError,PermissionError,IsADirectoryError,NotADirectoryError) as e:raise ToolError('FILE_ACCESS',str(e)) from e

    def _dispatch(self,name,p):
        store=self.store
        state=store.load()
        if name=='workspace.init':
            if p.get('demo') and p.get('empty'):raise ToolError('INIT_OPTIONS','Choose demo or empty, not both.')
            if p.get('demo'):
                if state['records']:raise ToolError('WORKSPACE_NOT_EMPTY','Demo fixtures require an empty library; choose a fresh workspace.')
                seed=store.seed();state['records']=seed['records'];state['conventions'].update(seed['conventions']);store.save(state)
            installation=registry.install(store) if not p.get('demo') and not p.get('empty') else None
            return {'workspace':str(store.root),'records':len(store.load()['records']),'demo':bool(p.get('demo')),'registry':installation}
        if name=='registry.status':return registry.status(store)
        if name=='registry.search':return registry.search(store,p.get('query',''))
        if name=='registry.search_public':return registry.search_public(store,p.get('query'),p.get('page',1),p.get('page_size',10),p.get('name'))
        if name=='registry.import_public':
            result=registry.import_public_part(store,p['slug'],p.get('expected_genbank_sha256'))
            return {**result,'record':summary(result['record'])}
        if name=='registry.install':return registry.install(store,p.get('part_ids'))
        if name=='registry.verify':return registry.verify(store)
        if name=='registry.check_live':return registry.check_live(store,p.get('part_ids'))
        if name=='context.get':
            return {'workspace':str(store.root),'registry':registry.status(store),'hosts':HOSTS,'sources':SOURCES,'conventions':list(state['conventions'].values()),
                'evidence':[{k:v[k] for k in ('id','title','kind','source_uri','sha256')} for v in state.get('evidence',{}).values()],
                'capabilities':{'interpretation':'calling agent','create':'exact ordered composition; optional explicit two-fragment circular homology prediction','assembly':backend_status(),'fragment_planning':'explicit ranges and forward/reverse orientation; annotation preview; partial-feature rejection; homology workflow only','modify':'one contiguous feature replacement with supplied orientation','inspect':'exact original GenBank record and explanatory report; no sequence or annotation edits','outputs':['annotated GenBank','standalone explanatory HTML','evidence bundle'],
                    'access':'local files, bundled iGEM reference snapshot, explicit bounded iGEM published-part search/import, read-only iGEM freshness checks, and public NCBI search plus exact accession.version retrieval','biological_validation':'unevaluated'},
                'limitations':[x for x in LIMITATIONS if not x.startswith(('Local deterministic','One local process'))]+['Caller supplies attributed reasoning; evidence labels are not independently authenticated.','Local CLI and GUI transactions share an OS file lock. Not a multiuser service.']}
        if name=='library.import':
            if not p['paths']:raise ToolError('FILES_REQUIRED','Supply at least one local file.')
            items=[];total=0
            for rawpath in p['paths']:
                path=Path(rawpath).expanduser().resolve()
                if path.stat().st_size>10*1024*1024:raise ToolError('IMPORT_LIMIT','Each file must be at most 10 MB.')
                data=path.read_bytes();total+=len(data)
                if total>12*1024*1024:raise ToolError('IMPORT_LIMIT','One transaction must be at most 12 MB.')
                items.append((path.name,data))
            result=self.service.import_files(items,p.get('source','lab'),inspection_only=p.get('inspection_only',False))
            return {**result,'records':[summary(r) for r in result['records']]}
        if name=='library.fetch_ncbi':
            result=public_sources.fetch_ncbi(store,p['accession'],p.get('expected_raw_sha256'))
            return {**result,'record':summary(result['record'])}
        if name=='library.search_ncbi':return public_sources.search_ncbi(store,p['query'],p.get('limit',10))
        if name=='library.search':
            tokens=p.get('query','').casefold().split();matches=[]
            for r in state['records'].values():
                if p.get('source') and r['source']['kind']!=p['source']:continue
                text=json.dumps(summary(r),ensure_ascii=False).casefold()
                if all(token in text for token in tokens):matches.append(summary(r))
            matches.sort(key=lambda r:(r['name'].casefold(),r['id']))
            offset=p.get('offset',0);limit=p.get('limit',50)
            return {'records':matches[offset:offset+limit],'total':len(matches),'offset':offset,'next_offset':offset+limit if offset+limit<len(matches) else None,'ranking':'lexical matching only; the calling agent assesses suitability'}
        if name=='record.inspect':
            r=copy.deepcopy(self._record(state,p['record_id']));r['record_sha256']=fingerprint(r)
            if not p.get('include_sequence'):r=without_bases(r)
            return {'record':r}
        if name=='record.compare':return {'comparison':self.service.compare(p['left_id'],p['right_id'])}
        if name=='fragment.preview':
            try: fragment,comparison=prepare_fragment(self._record(state,p['fragment']['record_id']),p['fragment'])
            except SequenceError as error:raise ToolError(error.code,str(error),error.details) from error
            return {'fragment':fragment if p.get('include_sequence') else summary(fragment),'annotation_comparison':comparison}
        if name=='convention.draft':return {'convention':self.service.draft_convention(p['name'],p['notes'])}
        if name=='convention.activate':return {'convention':self.service.activate_convention(p['convention_id'],p['reviewed'])}
        if name=='evidence.record':
            e={'id':uid('ev'),'created_at':now(),**p,'verification':'caller-supplied attribution; not independently authenticated'}
            e['sha256']=fingerprint(e);state.setdefault('evidence',{})[e['id']]=e;store.save(state)
            return {'evidence':e}
        if name=='evidence.get':
            e=state.get('evidence',{}).get(p['evidence_id'])
            if not e:raise ToolError('EVIDENCE_NOT_FOUND','Evidence identifier not found.')
            return {'evidence':e}
        if name=='job.start':
            j={'id':uid('job'),'objective':p['objective'],'created_at':now(),'revision':1,'decisions':{},'criteria':[],'assumptions':[],
                'custom_questions':[],'plan':None,'status':'needs_input','design_id':None}
            self._refresh(j);state.setdefault('jobs',{})[j['id']]={'current':j,'history':[copy.deepcopy(j)]};store.save(state)
            return {'job':j,'next_actions':self._next(j)}
        j=self._job(state,p['job_id'])
        if name=='job.get':return {'job':j,'next_actions':self._next(j)}
        if name=='job.history':return {'revisions':state['jobs'][j['id']]['history']}
        if name in ('job.update','job.plan','job.assess') and p['expected_revision']!=j['revision']:
            raise ToolError('STALE_REVISION',f'Expected revision {p["expected_revision"]}; current is {j["revision"]}. Resume with job.get.')
        if name=='job.assess':
            refs=[self._reference(state,ref) for ref in p['evidence_refs']]
            j['status']=p['outcome'];j['assessment']={'outcome':p['outcome'],'explanation':p['explanation'],'source_refs':refs,'origin':'calling_agent'}
            j['plan']=None;j['design_id']=None;j.pop('artifacts',None);j.pop('last_error',None)
            return self._save(state,j)
        if name=='job.update':return self._update(state,j,p)
        if name=='job.plan':return self._plan(state,j,p['plan'])
        if name=='job.run':return self._run(state,j,p['plan_hash'])
        if name=='artifact.export':
            if j['status']!='exported':raise ToolError('NOT_EXPORTED','Materialize a completed job before exporting its package.')
            result=self._result(state,j)
            dest=Path(p['destination']).expanduser().resolve()
            if dest.exists():raise ToolError('DESTINATION_EXISTS','Choose a new directory; existing files are not overwritten.')
            dest.parent.mkdir(parents=True,exist_ok=True)
            stage=Path(tempfile.mkdtemp(prefix='.vget-export-',dir=dest.parent))
            try:
                shutil.copytree(result['artifacts']['directory'],stage,dirs_exist_ok=True)
                self._verify_package(stage,state['designs'][j['design_id']])
                # Lock protects VGET, not unrelated writers: recheck before rename.
                if dest.exists():raise ToolError('DESTINATION_EXISTS','Destination appeared while copying; no overwrite allowed.')
                os.rename(stage,dest)
            finally:
                if stage.exists():shutil.rmtree(stage)
            return {'job_id':j['id'],'artifacts':self._paths(dest),'design':result['design']}
        raise ToolError('TOOL_NOT_FOUND',name)

    def _record(self,state,rid):
        if rid not in state['records']:raise ToolError('RECORD_NOT_FOUND',f'Record {rid} not found; search the local library.')
        return state['records'][rid]

    def _job(self,state,jid):
        if jid not in state.get('jobs',{}):raise ToolError('JOB_NOT_FOUND','Job not found in this workspace.')
        return copy.deepcopy(state['jobs'][jid]['current'])

    def _refresh(self,j):
        missing=[f for f in REQUIRED if f not in j['decisions']]
        questions=[{'id':'field:'+f,'field':f,'question':f'The calling agent must resolve {f} from the objective/evidence or ask the user if consequential.','audience':'agent','blocks_export':True,'state':'open'} for f in missing]
        if not j['criteria']:questions.append({'id':'field:criteria','field':'criteria','question':'State the objective acceptance criteria and identify which are required for export.','audience':'agent','blocks_export':True,'state':'open'})
        questions+=copy.deepcopy(j['custom_questions'])
        j['questions']=questions
        j['status']='needs_input' if any(q['blocks_export'] and q['state']=='open' for q in questions) else 'ready_to_plan'

    def _next(self,j):
        if j['status'] in ('unsupported','infeasible'):return ['Return the assessment and specific capability/constraint gap. Resume with job.update only after obtaining useful new scope or evidence.']
        if j['status']=='needs_input':return ['Inspect context and sources independently. Resolve agent-addressed fields from evidence; ask the user only about consequential ambiguity.','Record decisions and criteria with job.update.']
        if j['status']=='ready_to_plan':return ['Search and inspect available records. Submit justified exact operations with job.plan.']
        if j['status'] in ('planned','failed'):return ['Resolve any failure, then call job.run with the current plan hash. Updates invalidate the plan.']
        return ['Return the GenBank and HTML paths with key assumptions/limitations. Use artifact.export for a portable copy.']

    def _save(self,state,j):
        j['revision']+=1;j['updated_at']=now()
        state['jobs'][j['id']]['current']=j
        state['jobs'][j['id']]['history'].append(copy.deepcopy(j))
        self.store.save(state)
        return {'job':copy.deepcopy(j),'next_actions':self._next(j)}

    def _unique(self,items,key):
        ids=[x[key] for x in items]
        if len(ids)!=len(set(ids)):raise ToolError('DUPLICATE_ID',f'Duplicate {key} in submitted list.')

    def _update(self,state,j,p):
        self._unique(p.get('decisions',[]),'field')
        # Validate the resulting mode regardless of field submission order.
        mode=next((d['value'] for d in p.get('decisions',[]) if d['field']=='mode'),j['decisions'].get('mode',{}).get('value'))
        for d in p.get('decisions',[]):
            field,value=d['field'],d['value']
            if field=='mode' and value not in ('create','modify','inspect'):raise ToolError('DECISION_INVALID','mode must be create, modify or inspect.')
            if field=='host_id' and value not in {h['id'] for h in HOSTS} and not (mode=='inspect' and value is None):raise ToolError('DECISION_INVALID','Select an exact host profile; inspection alone may explicitly record null as unassessed.')
            if field=='topology' and value not in ('linear','circular') and not (mode=='inspect' and value=='unknown'):raise ToolError('DECISION_INVALID','Declare linear or circular topology; inspection alone may retain unknown source topology.')
            if field=='name' and (not isinstance(value,str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,47}',value)):raise ToolError('DECISION_INVALID','name must use 1–48 letters/numbers/underscore/dot/hyphen.')
            if field=='convention_id' and value is not None:
                c=state['conventions'].get(value)
                if not c or c['state']!='active':raise ToolError('CONVENTION_UNREVIEWED','Use an active convention or explicitly record null with a reason.')
            for ref in d.get('evidence_refs',[]):self._reference(state,ref)
            j['decisions'][field]=d
        if mode in ('create','modify'):
            if 'host_id' in j['decisions'] and j['decisions']['host_id']['value'] not in {h['id'] for h in HOSTS}:raise ToolError('DECISION_INVALID','Creation/modification requires a real host profile; update the host decision with the mode.')
            if 'topology' in j['decisions'] and j['decisions']['topology']['value'] not in ('linear','circular'):raise ToolError('DECISION_INVALID','Creation/modification requires known topology; update topology with the mode.')
        for key in ('criteria','assumptions'):
            if key in p:j[key]=p[key]
        self._unique(j['criteria'],'id')
        validate_criteria(j['criteria'])
        self._unique(p.get('questions',[]),'id');self._unique(p.get('answers',[]),'question_id')
        for q in p.get('questions',[]):
            if q['id'].startswith('field:'):raise ToolError('QUESTION_INVALID','field: is reserved for generated completeness questions.')
            found=next((x for x in j['custom_questions'] if x['id']==q['id']),None)
            if found:raise ToolError('QUESTION_EXISTS','Question IDs are immutable; use a new question ID for a new question.')
            j['custom_questions'].append({**q,'state':'open','audience':'user'})
        for answer in p.get('answers',[]):
            q=next((x for x in j['custom_questions'] if x['id']==answer['question_id']),None)
            if not q:raise ToolError('QUESTION_NOT_FOUND','Answer must refer to an existing explicit question.')
            q.update(state='answered',answer=answer['answer'],answer_origin=answer['origin'])
        j['plan']=None;j['design_id']=None;j.pop('artifacts',None);j.pop('last_error',None);j.pop('assessment',None)
        self._refresh(j)
        return self._save(state,j)

    def _reference(self,state,ref):
        for collection in ('records','conventions','evidence'):
            if ref in state.get(collection,{}):return {'kind':collection,'id':ref,'sha256':fingerprint(state[collection][ref])}
        for host in HOSTS:
            if ref==host['id']:return {'kind':'host','id':ref,'sha256':fingerprint(host)}
        raise ToolError('EVIDENCE_NOT_FOUND',f'Unknown evidence reference {ref}. Inspect a record/context or retain evidence before citing it.')

    def _plan(self,state,j,p):
        self._refresh(j)
        if j['status']=='needs_input':raise ToolError('NEEDS_INPUT','Resolve unresolved blocking decisions/questions before planning.',j['questions'])
        decisions={k:v['value'] for k,v in j['decisions'].items()}
        op=p['operation'];mode=decisions['mode'];fragment_previews=None
        if mode=='inspect':
            if set(op)!={'record_id'}:raise ToolError('OPERATION_INVALID','Inspect needs only record_id and performs no sequence or annotation edits.')
            inspected=self._record(state,op['record_id']);used=[inspected['id']]
            if decisions['topology']!=inspected['topology']:raise ToolError('TOPOLOGY_CONFLICT','Inspection retains exact source topology, including unknown.')
            if decisions['convention_id'] is not None:raise ToolError('INSPECT_CONVENTION','Inspection does not apply cloning conventions. Explicitly record convention_id=null; no rules will be silently ignored.')
        elif mode=='create':
            if 'fragments' in op:
                if set(op)!={'fragments','assembly'}:raise ToolError('OPERATION_INVALID','Explicit fragments require homology assembly, with no simultaneous part_ids or modification fields.')
                used=[f['record_id'] for f in op['fragments']]
                try:
                    prepared,fragment_previews=prepare_fragments([self._record(state,rid) for rid in used],op['fragments'])
                    validate_request(prepared,op['assembly'],decisions['topology'])
                except SequenceError as error:raise ToolError(error.code,str(error),error.details) from error
            else:
                if not op.get('part_ids') or set(op)-{'part_ids','assembly'}:raise ToolError('OPERATION_INVALID','Create needs ordered part_ids and optional explicit assembly. Parent/protection fields apply to modification.')
                used=op['part_ids']
                if 'assembly' in op:
                    try: validate_request([self._record(state,rid) for rid in used],op['assembly'],decisions['topology'])
                    except SequenceError as error: raise ToolError(error.code,str(error),error.details) from error
            c=state['conventions'].get(decisions['convention_id'])
            if c and any(r['kind']=='protect' for r in c['rules']):raise ToolError('UNSUPPORTED_RULE','Protection rules currently require a modify parent; cannot silently ignore them in create.')
        else:
            if set(op)!={'parent_id','target_feature_id','replacement_id','protected_feature_ids'}:raise ToolError('OPERATION_INVALID','Modify needs only parent_id, target_feature_id, replacement_id and explicit protected_feature_ids (possibly empty).')
            used=[op['parent_id'],op['replacement_id']]
            parent=self._record(state,op['parent_id']);features={f['id'] for f in parent['features']}
            if op['target_feature_id'] not in features or not set(op['protected_feature_ids'])<=features:raise ToolError('FEATURE_NOT_FOUND','Targets and protections must be exact parent feature IDs.')
            if op['target_feature_id'] in op['protected_feature_ids']:raise ToolError('PROTECTED_FEATURE','The replacement target is protected.')
            if decisions['topology']!=parent['topology']:raise ToolError('TOPOLOGY_CONFLICT','Modification retains parent topology. Resolve the decision before planning.')
        for rid in used:self._record(state,rid)
        self._unique(p['selections'],'record_id');self._unique(p['alternatives'],'record_id');self._unique(p['criteria'],'id')
        if {s['record_id'] for s in p['selections']}!=set(used):raise ToolError('SELECTIONS_REQUIRED','Explain every selected source record, including the parent for modification.')
        if {a['record_id'] for a in p['alternatives']}&set(used):raise ToolError('ALTERNATIVE_INVALID','Rejected alternatives cannot also be selected inputs.')
        for a in p['alternatives']:self._record(state,a['record_id'])
        expected={c['id']:c for c in j['criteria']}
        if {c['id'] for c in p['criteria']}!=expected.keys():raise ToolError('CRITERIA_REQUIRED','Assess every objective criterion exactly once.')
        criteria=[]
        for assessment in p['criteria']:
            criterion=expected[assessment['id']]
            if criterion['blocks_export'] and assessment['status']!='satisfied_by_plan':raise ToolError('UNMET_CRITERION',f'{criterion["id"]}: required criterion is {assessment["status"]}. Resolve it or obtain an explicit scope change.')
            if assessment['status']=='satisfied_by_plan' and not assessment['evidence_refs']:raise ToolError('EVIDENCE_REQUIRED','A satisfied-by-plan assessment needs source references.')
            criteria.append({**criterion,**assessment})
        for s in p['selections']:
            if not s['evidence_refs']:raise ToolError('EVIDENCE_REQUIRED','Each selection needs cited inspected evidence.')
        refs=set(used)|{a['record_id'] for a in p['alternatives']}
        if decisions['host_id'] is not None:refs.add(decisions['host_id'])
        if decisions['convention_id']:refs.add(decisions['convention_id'])
        for item in p['selections']+criteria+list(j['decisions'].values()):refs.update(item.get('evidence_refs',[]))
        pinned=[self._reference(state,ref) for ref in sorted(refs)]
        payload={**decisions,**op,'objective':j['objective']}
        context={**p,'criteria':criteria,'job_id':j['id'],'revision':j['revision']+1,'objective':j['objective'],
                 'decisions':list(j['decisions'].values()),'assumptions':j['assumptions'],'questions':[q for q in j['questions'] if q['state']=='open'],
                 'resolved_questions':[q for q in j['custom_questions'] if q['state']=='answered'],'source_refs':pinned,
                 'evidence':[state['evidence'][r['id']] for r in pinned if r['kind']=='evidence'],
                 'assessment_origin':'calling_agent; reasoning is recorded, not experimentally validated'}
        if fragment_previews is not None:context['fragment_previews']=fragment_previews
        plan={'payload':payload,'context':context,'source_refs':pinned,'based_on_revision':j['revision']}
        plan['sha256']=fingerprint(plan)
        j['plan']=plan;j['status']='planned';j['design_id']=None;j.pop('artifacts',None);j.pop('last_error',None)
        return self._save(state,j)

    def _run(self,state,j,plan_hash):
        plan=j.get('plan')
        if not plan or plan['sha256']!=plan_hash:raise ToolError('STALE_PLAN','No matching active plan. Resume with job.get and review the current plan.')
        if fingerprint({k:v for k,v in plan.items() if k!='sha256'})!=plan_hash:raise ToolError('PLAN_INTEGRITY','Stored plan content does not match its fingerprint.')
        if j['status']=='exported':return self._result(state,j)
        for ref in plan['source_refs']:
            try:current=self._reference(state,ref['id'])
            except ToolError as e:raise ToolError('STALE_SOURCE','A planned source is missing.') from e
            if current!=ref:raise ToolError('STALE_SOURCE',f'{ref["id"]} changed since planning. Inspect it and submit a new plan.')
        # Recover a committed design after interruption before job status save.
        recovered=next((d for d in state['designs'].values() if d.get('agent_context',{}).get('job_id')==j['id'] and d.get('agent_context',{}).get('plan_hash')==plan_hash),None)
        try:
            context={**plan['context'],'plan_hash':plan_hash}
            design=recovered or self.service.design(plan['payload'],agent_context=context)
        except APIError as e:
            j['status']='failed';j['last_error']={'code':e.code,'message':str(e),'details':e.details}
            self._save(self.store.load(),j)
            raise ToolError(e.code,str(e),e.details) from e
        # Service has changed state; never save the stale state loaded above.
        state=self.store.load();j['design_id']=design['id'];j['status']='exported';j.pop('last_error',None)
        j['artifacts']=self._paths(self.store.packages/design['id'])
        self._verify_package(Path(j['artifacts']['directory']),design)
        self._save(state,j)
        return self._result(self.store.load(),j)

    def _paths(self,directory):
        return {'directory':str(directory),'genbank':str(directory/'construct.gbk'),'html':str(directory/'report.html'),
                'bundle':str(directory/'bundle.zip'),'manifest':str(directory/'manifest.json'),'agent_context':str(directory/'agent-context.json')}

    def _verify_package(self,directory,expected_design):
        try:
            manifest=json.loads((directory/'manifest.json').read_text())
            names=[e['path'] for e in manifest['files']]
            if len(names)!=len(set(names)) or not {'construct.gbk','report.html','agent-context.json'}<=set(names):raise ValueError('Missing or duplicate payloads')
            actual={str(f.relative_to(directory)) for f in directory.rglob('*') if f.is_file()}
            if actual!=set(names)|{'manifest.json','bundle.zip'}:raise ValueError('Unmanifested or missing directory payloads')
            if manifest['design_id']!=expected_design['id']:raise ValueError('Package belongs to another design')
            if json.loads((directory/'design.json').read_text())!=expected_design:raise ValueError('Design snapshot differs from committed design')
            if json.loads((directory/'agent-context.json').read_text())!=expected_design['agent_context']:raise ValueError('Agent context differs from committed plan')
            for e in manifest['files']:
                file=(directory/e['path']).resolve()
                if not file.is_relative_to(directory.resolve()):raise ValueError('Unexpected artifact path')
                content=file.read_bytes()
                if digest(content)!=e['sha256'] or len(content)!=e['bytes']:raise ValueError('Payload hash mismatch')
            with zipfile.ZipFile(directory/'bundle.zip') as archive:
                if set(archive.namelist())!=set(names)|{'manifest.json'} or len(archive.namelist())!=len(names)+1:raise ValueError('Bundle membership mismatch')
                for name in archive.namelist():
                    if archive.read(name)!=(directory/name).read_bytes():raise ValueError('Bundle bytes differ')
        except (OSError,ValueError,KeyError,TypeError,zipfile.BadZipFile) as e:raise ToolError('ARTIFACT_INTEGRITY','Stored export is missing or has changed; it cannot be reported as a verified success.',str(e)) from e

    def _result(self,state,j):
        d=state['designs'].get(j['design_id'])
        if not d:raise ToolError('ARTIFACT_INTEGRITY','Job references an unavailable design.')
        if d.get('agent_context',{}).get('job_id')!=j['id'] or d.get('agent_context',{}).get('plan_hash')!=j['plan']['sha256']:
            raise ToolError('ARTIFACT_INTEGRITY','Design does not belong to the requested job and plan.')
        directory=self.store.packages/d['id'];self._verify_package(directory,d)
        return {'job':j,'design':{'id':d['id'],'name':d['name'],'length':d['record']['length'],'record_id':d['record']['id'],
            'sequence_sha256':d['record']['sequence_sha256'],'checks':d['checks'],'status':d['status']},'artifacts':self._paths(directory)}
