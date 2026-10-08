"""Framework-independent VGET operations over a local Store.

The caller owns objective interpretation and plan review. ``agent_context`` is
caller-authored reasoning/provenance, not a claim that this toolkit understands
scientific natural language or verifies biological function. Agent callers must
supply explicit operations; legacy GUI callers retain the v1 field resolver.
"""
from __future__ import annotations

import copy
from datetime import datetime
from functools import wraps
import json
import os
from pathlib import Path
import re
import tempfile
import zipfile

from .store import SourceIntegrityError, Store, HOSTS, now, uid, digest, json_bytes
from .sequence import SequenceError, compose, replace_feature, to_genbank, parse_records, validate_record, compare_records
from .brief import resolve_brief
from .conventions import parse_convention, check_convention, ConventionError
from .importer import import_files as parse_import_files
from .report import package_files
from .criteria import validate_criteria, evaluate_criteria
from .contracts import ToolError, ASSEMBLY, FRAGMENTS, validate
from .assembly import assemble_homology
from .fragments import prepare_fragments

LIMITATIONS=[
    'Local deterministic toolkit. Calling agents supply plans and reasoning; no embedded model. Local sequences and objectives are never uploaded by this toolkit.',
    'Default initialization installs six real iGEM reference records; explicit demo initialization uses arbitrary synthetic fixtures.',
    'All nine host profiles record intent; host compatibility and biological function are unevaluated.',
    'Create composes finalized parts by default. Explicit homology assembly predicts one circular molecule from two prepared linear inputs; optional explicit range/orientation planning prepares these computationally with annotation accounting. Primers, physical cutting, thermal conditions and wet-lab feasibility remain unevaluated.',
    'Modify supports a unique contiguous target, with no other intersecting annotations. Replacement is inserted as supplied, not automatically reverse-complemented.',
    'The iGEM starter is six versioned reference records. Anonymous published-part search and exact selected imports are available, with original GenBank, authors and source license metadata retained. This is not a comprehensive parts library; biological and host suitability remain unevaluated.',
    'Cloning notes use a small reviewed rule vocabulary; unsupported methods/notes cannot activate.',
    'Local workspace storage with serialized writes; not a multiuser service. Data remains on disk in this workspace.'
]
SOURCES=[
    {'id':'ncbi','name':'NCBI GenBank','status':'public nucleotide search + exact record retrieval','description':'Agent tools search_ncbi returns bounded accession.version summaries without sequences; fetch_ncbi retrieves one exact record and preserves original GenBank bytes. Search terms are sent to NCBI. Biological function unevaluated.','url':'https://www.ncbi.nlm.nih.gov/nuccore/'},
    {'id':'lab','name':'Lab library','status':'file import ready','description':'GenBank / FASTA / CSV / XLSX; original bytes retained.'},
    {'id':'igem','name':'iGEM Registry','status':'six-record starter + public search and selected import','description':'Search only anonymous published records. Import one exact selected slug with original GenBank, authors and source-declared license metadata. Public visibility is not proof of reuse rights or biological suitability.','url':'https://registry.igem.org/'},
    {'id':'addgene','name':'Addgene','status':'user exports only','description':'Sequence login/bulk access requires your entitlement; no credentials or scraping.','url':'https://www.addgene.org/'}]

class APIError(Exception):
    def __init__(self,code,message,status=422,details=None):
        super().__init__(message);self.code=code;self.status=status;self.details=details

def validate_payload(value):
    """Validate transport-independent field types and detach mutable inputs."""
    if not isinstance(value,dict):
        raise APIError('JSON_REQUIRED','Send a JSON object.',400)
    for field in ('objective','mode','host_id','name','record_id','parent_id','target_feature_id','replacement_id','convention_id','left_id','right_id','topology'):
        if field in value and value[field] is not None and not isinstance(value[field],str):
            raise APIError('FIELD_TYPE',f'{field} must be a string or null.',400)
    for field in ('part_ids','protected_feature_ids'):
        if field in value and (not isinstance(value[field],list) or any(not isinstance(item,str) for item in value[field])):
            raise APIError('FIELD_TYPE',f'{field} must be a list of record/feature identifiers.',400)
    if 'fragments' in value:
        try:validate(value['fragments'],FRAGMENTS,'fragments')
        except ToolError as error:raise APIError(error.code,str(error),400,error.details) from error
        if value.get('mode')!='create':raise APIError('FRAGMENT_MODE','Fragment preparation is an explicit create operation.',400)
        if 'assembly' not in value or any(key in value for key in ('part_ids','record_id','parent_id','target_feature_id','replacement_id','protected_feature_ids')):
            raise APIError('FRAGMENT_OPERATION','Use exactly two fragments with homology assembly; whole-record and modification operations cannot be combined.',400)
    if 'assembly' in value:
        try: validate(value['assembly'], ASSEMBLY, 'assembly')
        except ToolError as error: raise APIError(error.code, str(error), 400, error.details) from error
        if value.get('mode') != 'create':
            raise APIError('ASSEMBLY_MODE', 'Assembly is an explicit create operation; it cannot be ignored on inspect or modify.', 400)
    return copy.deepcopy(value)


def _operation(fn):
    """Expose one typed business-error contract to HTTP, CLI and agent callers."""
    @wraps(fn)
    def wrapped(*args,**kwargs):
        try:
            return fn(*args,**kwargs)
        except SourceIntegrityError as error:
            raise APIError('SOURCE_INTEGRITY',str(error),409) from error
        except SequenceError as error:
            raise APIError(error.code,str(error),422,error.details) from error
        except ConventionError as error:
            raise APIError('CONVENTION_INVALID',str(error)) from error
    return wrapped


def _record(state,rid):
    if not isinstance(rid,str) or rid not in state['records']:raise APIError('RECORD_NOT_FOUND','Select an existing record.',404)
    return state['records'][rid]

def _semantic(record):
    return {'sequence':record['sequence'],'topology':record['topology'],'features':[{'type':f['type'],'location':f['location'],'qualifiers':f['qualifiers']} for f in record['features']]}

def _original_identity(record):
    """GenBank content, excluding local provenance/catalogue fields and IDs."""
    return {**_semantic(record),'name':record['name'],'description':record['description'],
            'metadata':{key:record.get('metadata',{}).get(key) for key in ('record_id','record_name','annotations','dbxrefs')}}

def _inspection_genbank(record,store):
    """Return an exact raw GenBank record; never reserialize annotations.

    A multi-record import retains its whole raw file in the evidence bundle.
    The output here selects the matching original record, without changing its
    LOCUS, historical date, accession, references, qualifiers or comments.
    """
    source=record.get('source',{})
    while source.get('sequence_source'):
        source=source['sequence_source']
    raw=(store.raw/source['raw_sha256']).read_bytes()
    try:
        text=raw.decode('utf-8-sig')
    except UnicodeDecodeError as error:
        raise APIError('INSPECT_FORMAT','Exact inspection requires an imported UTF-8 GenBank record.') from error
    if not text.lstrip().startswith('LOCUS '):
        raise APIError('INSPECT_FORMAT','Exact inspection requires an original GenBank record. FASTA/catalogue inputs need annotation preparation before this operation.')
    candidates=[];lines=[]
    for line in text.splitlines(keepends=True):
        if line.startswith('LOCUS '):lines=[line]
        elif lines:lines.append(line)
        if lines and line.strip()=='//':
            original=''.join(lines);parsed=parse_records(original,source.get('filename','original.gbk'),allow_parser_warnings=record.get('metadata',{}).get('inspection_only',False))[0]
            if _original_identity(parsed)==_original_identity(record):candidates.append(original)
            lines=[]
    if not candidates:
        raise APIError('SOURCE_RECORD_MISMATCH','Stored annotations or identity differ from the verified original GenBank record. Exact inspection cannot fabricate a match.',409)
    # Repeated byte-identical records are equivalent; distinct encodings with
    # identical parsed content are ambiguous and require an exact re-import.
    if len(set(candidates))!=1:
        raise APIError('SOURCE_RECORD_AMBIGUOUS','Multiple original GenBank encodings match this record; import the intended single record.',409)
    # EFetch may append blank lines after the terminator. For a single-record
    # file retain that whitespace too; multi-record sources still select only
    # the matched record and retain the whole input separately as evidence.
    original=candidates[0]
    if text.lstrip().startswith(original) and not text.lstrip()[len(original):].strip():
        return (store.raw/source['raw_sha256']).read_bytes()
    return candidates[0].encode('utf-8')

class Service:
    def __init__(self,store: Store):
        self.store=store

    @_operation
    def import_files(self,items,source='lab',inspection_only=False):
        if type(inspection_only) is not bool:
            raise APIError('FIELD_TYPE','inspection_only must be a boolean.',400)
        if not isinstance(items,(list,tuple)) or not items:
            raise APIError('FILES_REQUIRED','Choose one or more GenBank, FASTA or catalogue files.')
        total=0
        for item in items:
            if not isinstance(item,(list,tuple)) or len(item)!=2 or not isinstance(item[0],str) or not isinstance(item[1],bytes):
                raise APIError('FILE_TYPE','Each import item must contain a filename and raw bytes.',400)
            if len(item[1])>10*1024*1024:
                raise APIError('IMPORT_LIMIT','Each file must be at most 10 MB.')
            total+=len(item[1])
        if total>12*1024*1024:
            raise APIError('IMPORT_LIMIT','One import transaction must be at most 12 MB.')
        with self.store.lock:
            state=self.store.load()
            try:
                records,diagnostics=parse_import_files(items,source,state,self.store,inspection_only=inspection_only)
            except SequenceError:
                raise
            except (UnicodeDecodeError,zipfile.BadZipFile,ValueError) as error:
                raise APIError('IMPORT_INVALID',str(error)) from error
            self.store.save(state)
        return {'records':records,'diagnostics':diagnostics}

    @_operation
    def brief(self,payload):
        p=validate_payload(payload)
        if 'fragments' in p:p['part_ids']=[f['record_id'] for f in p['fragments']]
        return resolve_brief(p,self.store.load())

    @_operation
    def draft_convention(self,name,notes):
        convention=parse_convention(name,notes)
        with self.store.lock:
            state=self.store.load()
            state['conventions'][convention['id']]=convention
            self.store.save(state)
        return convention

    @_operation
    def activate_convention(self,cid,reviewed):
        if reviewed is not True:
            raise APIError('REVIEW_REQUIRED','Explicitly review the extracted rules before activation.')
        with self.store.lock:
            state=self.store.load()
            convention=state['conventions'].get(cid) if isinstance(cid,str) else None
            if not convention:
                raise APIError('CONVENTION_NOT_FOUND','Convention not found.',404)
            if convention['unsupported'] or not convention['rules']:
                raise APIError('UNSUPPORTED_RULES','Resolve unsupported or empty convention rules first.',details=convention['unsupported'])
            if convention['state']!='active':
                convention['state']='active'
                convention['reviewed_at']=now()
                self.store.save(state)
        return convention

    @_operation
    def compare(self,left_id,right_id):
        state=self.store.load()
        return compare_records(_record(state,left_id),_record(state,right_id))

    def _design_brief(self,payload,state,agent_context):
        if payload.get('mode')=='inspect':
            questions=[]
            def ask(field,message):questions.append({'field':field,'message':message})
            record=state['records'].get(payload.get('record_id'))
            if not record:ask('record_id','Select the exact existing record to inspect.')
            if 'host_id' not in payload or (payload['host_id'] is not None and payload['host_id'] not in {h['id'] for h in HOSTS}):ask('host_id','State a known host profile or explicit null for unassessed inspection.')
            if 'topology' not in payload or (record and payload['topology']!=record['topology']):ask('topology','Retain exact source topology, including unknown.')
            if 'convention_id' not in payload or payload['convention_id'] is not None:ask('convention_id','Inspection applies no cloning rules; explicitly record null.')
            if any(key in payload for key in ('part_ids','parent_id','target_feature_id','replacement_id','protected_feature_ids')):ask('operation','Inspect accepts only a record_id; no sequence editing operation is allowed.')
            objective=payload.get('objective')
            if not isinstance(objective,str) or not objective.strip() or len(objective)>10000:ask('objective','Supply the original objective, between 1 and 10,000 characters.')
            return {'ready':not questions,'questions':questions,'mode':'inspect','host_id':payload.get('host_id'),'objective':objective,
                    'summary':agent_context.get('summary','Inspect an exact existing GenBank record.') if agent_context else 'Inspect an exact existing GenBank record.',
                    'interpretation':'caller_supplied_agent_plan' if agent_context else 'explicit_record_inspection',
                    'supported_scope':'Exact original GenBank export and explanatory report; sequence, identity and annotations remain unchanged.',
                    'assumptions':['Inspection makes no sequence or annotation edits.','Host compatibility and biological function are not assessed.','No cloning convention is applied.']}
        if agent_context is None:
            computational=copy.deepcopy(payload)
            if 'fragments' in computational:computational['part_ids']=[f['record_id'] for f in computational['fragments']]
            return resolve_brief(computational,state)
        # The caller has interpreted the objective and must provide every
        # consequential input. Only structured operations are validated here.
        computational=copy.deepcopy(payload)
        if 'fragments' in computational:computational['part_ids']=[f['record_id'] for f in computational['fragments']]
        computational['objective']='Apply the explicitly supplied sequence transformation.'
        brief=resolve_brief(computational,state)
        questions=brief['questions']
        if payload.get('mode') not in ('create','modify') and not any(q['field']=='mode' for q in questions):
            questions.append({'field':'mode','message':'Supply an explicit create or modify operation.'})
        if payload.get('mode')=='create' and 'topology' not in payload:
            questions.append({'field':'topology','message':'Supply explicit circular or linear topology.'})
        objective=payload.get('objective')
        if not isinstance(objective,str) or not objective.strip() or len(objective)>10000:
            questions.append({'field':'objective','message':'Supply the original objective, between 1 and 10,000 characters.'})
        brief.update(ready=not questions,objective=objective,
                     interpretation='caller_supplied_agent_plan',
                     supported_scope='Explicit caller-supplied composition, bounded two-fragment homology prediction or feature replacement. Scientific intent and rationale are supplied by the calling agent.')
        if isinstance(agent_context.get('summary'),str) and agent_context['summary'].strip():
            brief['summary']=agent_context['summary']
        brief['assumptions']=[item for item in brief['assumptions'] if not item.startswith('The local resolver')]
        brief['assumptions'].append('Structured plan supplied by the calling agent; the toolkit validates explicit operations and does not interpret or verify the scientific objective.')
        return brief

    @_operation
    def design(self,payload,agent_context=None):
        p=validate_payload(payload)
        if agent_context is not None:
            if not isinstance(agent_context,dict):
                raise APIError('AGENT_CONTEXT_INVALID','Agent context must be a JSON object.',400)
            try:
                agent_context=json.loads(json_bytes(agent_context))
            except (TypeError,ValueError,RecursionError) as error:
                raise APIError('AGENT_CONTEXT_INVALID','Agent context must contain finite JSON values.',400) from error
            try:validate_criteria(agent_context.get('criteria',[]))
            except ToolError as error:raise APIError(error.code,str(error),422,error.details) from error
        store=self.store
        with store.lock:
            state=store.load();brief=self._design_brief(p,state,agent_context)
            if not brief['ready']:raise APIError('NEEDS_INPUT','Resolve the highlighted questions before computing a design.',details=brief['questions'])
            name=p.get('name','VGET_design')
            if not isinstance(name,str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,47}',name):raise APIError('NAME_INVALID','Use 1–48 ASCII letters/numbers/underscore/dot/hyphen, starting with a letter or number.')
            mode=brief['mode'];host=next((h for h in HOSTS if h['id']==brief['host_id']),None)
            convention=state['conventions'].get(p.get('convention_id'))
            protected=list(p.get('protected_feature_ids',[]))
            if not isinstance(protected,list) or any(not isinstance(v,str) for v in protected):raise APIError('PROTECTION_INVALID','Protected features must be a list of exact feature IDs.')
            parent=None;prepared=None;fragment_comparisons=None
            if mode=='inspect':
                sources=[_record(state,p['record_id'])];topology=sources[0]['topology'];length=sources[0]['length']
            elif mode=='create':
                if 'fragments' in p:
                    sources=[_record(state,f['record_id']) for f in p['fragments']]
                    prepared,fragment_comparisons=prepare_fragments(sources,p['fragments'])
                else:sources=[_record(state,rid) for rid in p['part_ids']]
                topology=p.get('topology','circular');length=sum(r['length'] for r in (prepared or sources))
            else:
                parent=_record(state,p['parent_id']);replacement=_record(state,p['replacement_id']);sources=[parent,replacement]
                topology=parent['topology'];target=next(f for f in parent['features'] if f['id']==p['target_feature_id'])
                length=parent['length']-sum(s['end']-s['start'] for s in target['segments'])+replacement['length']
                # Natural-language protection is honored only if its feature label resolves exactly.
                objective=p.get('objective','') if agent_context is None else ''
                for match in re.finditer(r'\b(?:preserve|protect)\s+[\"\']?([A-Za-z0-9_.-]+)',objective,re.I):
                    label=match.group(1);found=[f['id'] for f in parent['features'] if f['label']==label]
                    if len(found)!=1:raise APIError('PROTECTION_AMBIGUOUS',f'Protection phrase “{label}” needs an exact feature selection.')
                    protected.extend(found)
            if length>100000:raise APIError('DESIGN_LIMIT','Prototype output limit is 100,000 bases.')
            originals={}
            def collect(source):
                h=source.get('raw_sha256')
                if not isinstance(h,str) or not re.fullmatch(r'[0-9a-f]{64}',h):
                    raise APIError('SOURCE_INTEGRITY','A source record lacks its original file fingerprint.',409)
                raw_path=store.raw/h
                if not raw_path.is_file() or digest(raw_path.read_bytes())!=h:
                    raise APIError('SOURCE_INTEGRITY','An original source file is missing or has changed. Restore its exact bytes before computing a new design.',409)
                originals[h+'-'+source.get('filename','source')]=raw_path.read_bytes()
                if source.get('sequence_source'):collect(source['sequence_source'])
                for blob in source.get('evidence_blobs',[]):collect(blob)
            for source_record in sources:collect(source_record.get('source',{}))
            assembled = assemble_homology(prepared or sources,name,p['assembly'],topology) if 'assembly' in p else None
            if assembled: length = assembled[0]['length']
            if convention:
                failures,rule_protected=check_convention(convention,name,host,topology,length,parent)
                if failures:raise APIError('CONSTRAINT_CONFLICT','Convention constraints are not satisfied.',details=failures)
                protected.extend(rule_protected)
            if mode=='inspect':record,changes=copy.deepcopy(sources[0]),[]
            elif mode=='create':record,changes=assembled or compose(sources,name,topology)
            else:record,changes=replace_feature(parent,p['target_feature_id'],replacement,name,list(dict.fromkeys(protected)))
            if fragment_comparisons is not None:
                record['metadata']['fragment_planning']=fragment_comparisons
                changes=[{'kind':'fragment_preparation','source_id':r['source_id'],
                          'message':f'Prepared explicit {r["orientation"]} ranges from {r["source_name"]}; complete features retained, outside features listed and whole-record source projections audited. Physical cutting unevaluated.',
                          'ranges':r['ranges'],'fragment_id':r['fragment_id']} for r in fragment_comparisons]+changes
            checks=validate_record(record)
            if assembled:
                checks.append(dict(id='homology_prediction',status='pass',message='Pinned pydna prediction uses both prepared inputs exactly once, matches the explicit terminal junction path and yields one circular molecule. Source annotations map without clipping; thermal and experimental conditions are unevaluated.'))
            if fragment_comparisons is not None:
                checks.append(dict(id='fragment_preparation',status='pass',message='Explicit source ranges and orientations applied; all source features accounted for as complete retained features, outside exclusions or audited whole-record source projections. Other partial features rejected; bibliography ranges projected with an audit.'))
            criterion_checks=evaluate_criteria(agent_context.get('criteria',[]) if agent_context else [],record)
            if any(c['status']=='fail' for c in criterion_checks):
                raise APIError('CRITERION_FAILED','Materialized output does not satisfy required typed criteria.',details=criterion_checks)
            checks.extend(criterion_checks)
            for source_record in sources:
                for index,warning in enumerate(source_record.get('metadata',{}).get('parser_warnings',[])):
                    checks.append({'id':f'parser_warning:{source_record["id"]}:{index}','status':'warning','message':str(warning)})
                if source_record.get('metadata',{}).get('inspection_only'):
                    checks.append({'id':'annotation_interpretation','status':'unevaluated','message':'Map and feature locations are a parser interpretation of the retained original; source warnings have not been repaired or resolved.'})
                for index,warning in enumerate(source_record.get('metadata',{}).get('registry',{}).get('warnings',[])):
                    checks.append({'id':f'registry_{source_record["id"]}_{index}','status':'warning','message':source_record['name']+': '+warning})
            if any(c['status']=='fail' for c in checks):raise APIError('VALIDATION_FAILED','Structural checks failed.',details=checks)
            committed_at=now()
            if mode=='inspect':
                gbk=_inspection_genbank(record,store)
            else:
                annotations=record.setdefault('metadata',{}).setdefault('annotations',{})
                annotations['date']=datetime.fromisoformat(committed_at).strftime('%d-%b-%Y').upper()
                comments=['VGET derived computational record; biological function and laboratory assembly are unevaluated.']
                if assembled:
                    comments.append('Exact terminal homology prediction: pydna '+record['metadata']['assembly']['backend_version']+'; origin anchored to backbone base 0. Two junction overlaps: '+', '.join(p['assembly']['overlaps'])+'. Prepared inputs used as supplied; source annotations retained independently, including shared-overlap annotations. No primer, cutting, temperature or experimental validation.')
                if fragment_comparisons is not None:
                    comments.append('Explicit computational fragment preparation from original records: '+ '; '.join(r['source_id']+' '+r['orientation']+' '+str(r['ranges']) for r in fragment_comparisons)+'. Coordinates are 0-based half-open. Complete selected features retained; whole-record source annotations projected with an audit; wholly outside annotations excluded and listed in fragment-planning.json. Reference ranges projected onto selected bases; source bibliography retained. No physical cutting or PCR claim.')
                for source_record in sources:
                    comment=source_record.get('metadata',{}).get('annotations',{}).get('comment')
                    if comment:
                        comments.append(f'Source comment from {source_record["name"]} ({source_record["id"]}); not validated for this derived record:\n{comment}')
                annotations['comment']='\n\n'.join(comments)
                gbk=to_genbank(record,audited_reference_ranges=fragment_comparisons is not None).encode('utf-8')
            exported=parse_records(gbk.decode('utf-8-sig'),'construct.gbk',allow_parser_warnings=record.get('metadata',{}).get('inspection_only',False))[0]
            if _semantic(exported)!=_semantic(record):raise APIError('EXPORT_MISMATCH','GenBank readback differs from the computed record.')
            if mode=='inspect' and _original_identity(exported)!=_original_identity(record):raise APIError('EXPORT_MISMATCH','Inspection readback differs from original identity or annotation metadata.')
            checks += [dict(id='genbank_roundtrip',status='pass',message='Export readback matches sequence, topology, feature locations and qualifier values.'),dict(id='source_identity',status='pass',message='Exact source record versions and original bytes are retained locally.'),dict(id='convention',status='pass' if convention else 'unevaluated',message='Supported active convention rules passed.' if convention else 'No lab convention selected.'),dict(id='assembly_feasibility',status='unevaluated',message='Sequence composition is not laboratory assembly simulation.'),dict(id='host_compatibility',status='unevaluated',message='Host intent recorded; strain/cell-line compatibility not assessed.'),dict(id='biological_function',status='unevaluated',message='No functional or experimental evidence supplied.')]
            if assembled:
                next(c for c in checks if c['id']=='assembly_feasibility')['message']='Exact homology prediction does not establish laboratory feasibility; primers, cutting and reaction conditions are unassessed.'
            did=uid('design');record['id']=uid('rec')
            record.pop('_import_key',None)
            record['source']={'kind':'design','design_id':did,'filename':'construct.gbk','raw_sha256':store.keep_raw(gbk),'imported_at':now(),
                'evidence_blobs':[copy.deepcopy(source_record['source']) for source_record in sources]}
            base=f'/api/designs/{did}'
            if mode=='inspect':
                checks.append(dict(id='original_genbank_identity',status='pass',message='Exact original GenBank record bytes retained, including identity, historical date, comments and every annotation.'))
                for check in checks:
                    if check['id']=='host_compatibility':check['message']='No host compatibility is assessed by record inspection.'
            d=dict(id=did,name=name,created_at=committed_at,mode=mode,host_id=host['id'] if host else None,host_name=host['name'] if host else 'Not assessed',objective=p['objective'],record=record,parent_id=parent['id'] if parent else None,part_ids=[r['id'] for r in sources],convention_id=convention['id'] if convention else None,convention=copy.deepcopy(convention),assumptions=brief['assumptions'],checks=checks,changes=changes,status='Inspected original · biology unevaluated' if mode=='inspect' else 'Computed proposal · biology unevaluated',files={'genbank':base+'/construct.gbk','report':base+'/report.html','bundle':base+'/bundle.zip'},brief=brief,limitations=LIMITATIONS,protected_feature_ids=list(dict.fromkeys(protected)))
            snapshot={'record':record,'source_records':sources,'brief':brief,'convention':convention,'changes':changes}
            if agent_context is not None:
                d['agent_context']=copy.deepcopy(agent_context)
                snapshot['agent_context']=d['agent_context']
            d['snapshot_sha256']=digest(json_bytes(snapshot))
            payloads=package_files(d,gbk,sources,originals)
            staging=Path(tempfile.mkdtemp(prefix='.pending-',dir=store.packages))
            for filename,data in payloads.items():
                path=staging/filename
                if not path.resolve().is_relative_to(staging.resolve()):raise APIError('EXPORT_PATH','Invalid export artifact path.',500)
                path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(data)
            with zipfile.ZipFile(staging/'bundle.zip','w',zipfile.ZIP_DEFLATED) as z:
                for filename,data in payloads.items():z.writestr(filename,data)
            os.replace(staging,store.packages/did)
            state['records'][record['id']]=record;state['designs'][did]=d;store.save(state)
        return d
