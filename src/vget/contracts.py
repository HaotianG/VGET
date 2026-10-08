"""Discoverable JSON tool contracts; same schemas drive input validation."""
S={'type':'string','minLength':1,'maxLength':10000}
ID={'type':'string','minLength':1,'maxLength':200}
BOOL={'type':'boolean'}
REFS={'type':'array','items':ID,'maxItems':100}

def obj(properties,required=()):
    return {'type':'object','properties':properties,'required':list(required),'additionalProperties':False}

def arr(items, maximum=100):return {'type':'array','items':items,'maxItems':maximum}
def enum(*values):return {'enum':list(values)}

DECISION=obj({'field':enum('mode','host_id','name','topology','convention_id'),'value':{'type':['string','null']},'origin':enum('user','agent','source','default'),'reason':S,'evidence_refs':REFS},['field','value','origin','reason'])
CHECK=obj({'kind':enum('length','sequence_sha256','topology','feature_count'),'value':{'type':['integer','string']}},['kind','value'])
CRITERION=obj({'id':ID,'text':S,'blocks_export':BOOL,'check':CHECK},['id','text','blocks_export'])
QUESTION=obj({'id':ID,'question':S,'blocks_export':BOOL},['id','question','blocks_export'])
ANSWER=obj({'question_id':ID,'answer':S,'origin':enum('user','agent','source')},['question_id','answer','origin'])
SELECTION=obj({'record_id':ID,'reason':S,'evidence_refs':REFS},['record_id','reason','evidence_refs'])
ASSESSMENT=obj({'id':ID,'status':enum('satisfied_by_plan','unevaluated','unmet'),'evaluation':S,'evidence_refs':REFS},['id','status','evaluation','evidence_refs'])
ASSEMBLY=obj({'method':enum('homology'),'overlaps':{'type':'array','items':{'type':'string','pattern':'[ACGT]{20,80}'},'maxItems':2}},['method','overlaps'])
RANGE=obj({'start':{'type':'integer','minimum':0,'maximum':100000},'end':{'type':'integer','minimum':0,'maximum':100000}},['start','end'])
FRAGMENT=obj({'record_id':ID,'ranges':arr(RANGE,2),'orientation':enum('forward','reverse')},['record_id','ranges','orientation'])
FRAGMENTS=arr(FRAGMENT,2)
OPERATION=obj({'record_id':ID,'part_ids':arr(ID,50),'fragments':FRAGMENTS,'assembly':ASSEMBLY,'parent_id':ID,'target_feature_id':ID,'replacement_id':ID,'protected_feature_ids':REFS})
PLAN=obj({'operation':OPERATION,'summary':S,'selections':arr(SELECTION),'alternatives':arr(obj({'record_id':ID,'reason':S},['record_id','reason'])),'criteria':arr(ASSESSMENT)},['operation','summary','selections','alternatives','criteria'])
REV={'type':'integer','minimum':1}

TOOL_LIST=[]
def tool(name,description,schema):TOOL_LIST.append({'name':name,'description':description,'input_schema':schema})

tool('workspace.init','Initialize a workspace and install the bundled real iGEM reference pack by default. empty=true skips it; demo=true explicitly adds synthetic fixtures instead. Never overwrites records.',obj({'demo':BOOL,'empty':BOOL}))
tool('registry.status','Report bundled and installed starter records, source scope and last explicit live-check receipt. No network access.',obj({}))
tool('registry.search','Search the six bundled public reference parts offline, with attribution, license, hashes and source-quality caveats; does not install them.',obj({'query':{'type':'string','maxLength':1000}}))
tool('registry.search_public','Explicit public network action: search one bounded page of anonymous published iGEM parts by a public phrase or exact BBa_ name. Sends only that public term; never send private objectives/notes. Returns metadata without sequences or imports.',obj({'query':{'type':'string','minLength':1,'maxLength':120},'name':{'type':'string','pattern':'BBa_[A-Za-z0-9]{1,24}'},'page':{'type':'integer','minimum':1,'maximum':1000},'page_size':{'type':'integer','minimum':1,'maximum':20}}))
tool('registry.import_public','Explicit public network action: fetch one exact published iGEM slug plus original GenBank, authors and source license metadata. No login or private data. Preserves source files and caveats; a public record is not evidence of suitability.',obj({'slug':{'type':'string','pattern':'bba-[a-z0-9]{1,24}'},'expected_genbank_sha256':{'type':'string','pattern':'[0-9a-f]{64}'}},['slug']))
tool('registry.install','Install all or named bundled reference records with exact original bytes and evidence. Idempotent; refuses changed existing pins.',obj({'part_ids':arr(ID,6)}))
tool('registry.verify','Verify bundled files and installed record/evidence fingerprints offline. This does not establish biological function or live freshness.',obj({}))
tool('registry.check_live','Explicit network action: GET official public metadata and GenBank only for bundled identifiers. Return freshness receipt; never update records or send local sequences/objectives. May report rate limits.',obj({'part_ids':arr(ID,6)}))
tool('context.get','Get capabilities, nine host contexts, source access status, conventions and evidence summaries. Host compatibility is unevaluated.',obj({}))
tool('library.import','Import exact local GenBank/FASTA/CSV/XLSX files with source provenance; no network retrieval. inspection_only=true explicitly permits GenBank parser warnings, retains them and original location expressions, and forbids transformations of these records. Default import remains strict.',obj({'paths':arr(S,100),'source':enum('lab','igem','addgene','ncbi'),'inspection_only':BOOL},['paths']))
tool('library.search_ncbi','Explicit public network action: search NCBI nucleotide by a short public phrase, return at most 20 accession.version summaries, and do not fetch sequence or import records. Sends the phrase to NCBI; never send private objectives/notes. Two verified-TLS GETs are paced at about one per second per workspace; coordinate shared-IP limits across workspaces. No credentials, redirects or retries.',obj({'query':{'type':'string','minLength':1,'maxLength':120},'limit':{'type':'integer','minimum':1,'maximum':20}},['query']))
tool('library.fetch_ncbi','Explicit network action: retrieve one public DNA GenBank record by exact NCBI accession.version. One verified-TLS GET; no credentials, uploads, redirects or retries. 2 MB/100,000-base limits; original bytes and annotations retained. Paced at <=1 request/sec per workspace; callers must coordinate shared-IP limits across workspaces. Biological function unevaluated.',obj({'accession':{'type':'string','pattern':r'[A-Z][A-Z0-9_]{0,31}\.[1-9][0-9]{0,8}'},'expected_raw_sha256':{'type':'string','pattern':'[0-9a-f]{64}'}},['accession']))
tool('library.search','Search all query tokens across names, annotations and catalogue metadata. Returns summaries without bases; relevance is lexical, not biological.',obj({'query':{'type':'string','maxLength':1000},'source':enum('lab','igem','addgene','ncbi','demo','design'),'limit':{'type':'integer','minimum':1,'maximum':100},'offset':{'type':'integer','minimum':0}}))
tool('record.inspect','Inspect exact annotations, catalogue and provenance. Raw bases are opt-in.',obj({'record_id':ID,'include_sequence':BOOL},['record_id']))
tool('record.compare','Compare exact sequences and circular equivalence without editing.',obj({'left_id':ID,'right_id':ID},['left_id','right_id']))
tool('fragment.preview','Read-only preparation preview from an exact record and 0-based half-open ranges. One contiguous range, or two ranges across a circular origin; explicit forward/reverse orientation. Reports retained/excluded annotations, audits projection of whole-record source annotations and rejects other partial features. No primers, reaction planning or stored intermediate. Bases are opt-in.',obj({'fragment':FRAGMENT,'include_sequence':BOOL},['fragment']))
tool('convention.draft','Extract supported rules from supplied notes into a reviewable draft.',obj({'name':S,'notes':S},['name','notes']))
tool('convention.activate','Activate supported rules after review. Imported text alone is not approval.',obj({'convention_id':ID,'reviewed':BOOL},['convention_id','reviewed']))
tool('evidence.record','Retain a cited text excerpt or user statement as evidence. Attribution is caller supplied, not independently authenticated.',obj({'title':S,'text':S,'source_uri':S,'kind':enum('user_statement','retrieved_source','agent_assessment')},['title','text','source_uri','kind']))
tool('evidence.get','Read a retained evidence item by exact identifier.',obj({'evidence_id':ID},['evidence_id']))
tool('job.start','Persist the original ordinary-language objective. Calling agent supplies interpretation via job.update and job.plan.',obj({'objective':S},['objective']))
tool('job.get','Resume a job with current decisions, open questions, plan and artifact references.',obj({'job_id':ID},['job_id']))
tool('job.history','Read immutable revision snapshots; no sequence bases are duplicated in job history.',obj({'job_id':ID},['job_id']))
tool('job.assess','Record an unsupported or infeasible objective with reasons and evidence, without a fabricated design. A later update can resume it.',obj({'job_id':ID,'expected_revision':REV,'outcome':enum('unsupported','infeasible'),'explanation':S,'evidence_refs':REFS},['job_id','expected_revision','outcome','explanation','evidence_refs']))
tool('job.update','Record attributed decisions, criteria, assumptions and questions/answers. Any edit invalidates the active plan; expected_revision prevents lost updates.',obj({'job_id':ID,'expected_revision':REV,'decisions':arr(DECISION),'criteria':arr(CRITERION),'assumptions':arr(S),'questions':arr(QUESTION),'answers':arr(ANSWER)},['job_id','expected_revision']))
tool('job.plan','Submit an explicit source-pinned plan. Create uses ordered part_ids for composition or homology assembly; alternatively use fragments=[{record_id,ranges,orientation}, {...}] with homology assembly to prepare ranges from original sources. Homology needs the assembly extra and one unique circular prediction. Modify uses an exact target span. Inspect uses only record_id and unchanged source topology; no cloning convention. Requires resolved blocking decisions/questions/criteria.',obj({'job_id':ID,'expected_revision':REV,'plan':PLAN},['job_id','expected_revision','plan']))
tool('job.run','Materialize an exact plan hash; validate and export GenBank+HTML. Safe retries reuse verified output. This does not infer biological intent.',obj({'job_id':ID,'plan_hash':{'type':'string','pattern':'^[0-9a-f]{64}$'}},['job_id','plan_hash']))
tool('artifact.export','Verify then copy a completed job package to a new directory. Existing destinations are not overwritten.',obj({'job_id':ID,'destination':S},['job_id','destination']))
TOOLS={t['name']:t for t in TOOL_LIST}

class ToolError(ValueError):
    def __init__(self,code,message,details=None):
        super().__init__(message);self.code=code;self.details=details

def validate(value,schema,path='input'):
    import re
    if 'enum' in schema and value not in schema['enum']:raise ToolError('INPUT_SCHEMA',f'{path}: expected one of {schema["enum"]}.')
    kind=schema.get('type')
    matches={'string':lambda:isinstance(value,str),'null':lambda:value is None,'boolean':lambda:type(value) is bool,'integer':lambda:type(value) is int,'array':lambda:isinstance(value,list),'object':lambda:isinstance(value,dict)}
    if kind and not any(matches[k]() for k in (kind if isinstance(kind,list) else [kind])):raise ToolError('INPUT_SCHEMA',f'{path}: expected {kind}.')
    if isinstance(value,str):
        if len(value)>schema.get('maxLength',100000) or len(value.strip())<schema.get('minLength',0):raise ToolError('INPUT_SCHEMA',f'{path}: invalid text length.')
        if 'pattern' in schema and not re.fullmatch(schema['pattern'],value):raise ToolError('INPUT_SCHEMA',f'{path}: invalid format.')
    if type(value) is int and (value<schema.get('minimum',value) or value>schema.get('maximum',value)):raise ToolError('INPUT_SCHEMA',f'{path}: outside allowed range.')
    if isinstance(value,list):
        if len(value)>schema.get('maxItems',1000):raise ToolError('INPUT_SCHEMA',f'{path}: too many items.')
        for i,item in enumerate(value):validate(item,schema.get('items',{}),f'{path}[{i}]')
    if isinstance(value,dict):
        missing=set(schema.get('required',[]))-value.keys()
        extra=value.keys()-schema.get('properties',{}).keys()
        if missing or (extra and schema.get('additionalProperties') is False):raise ToolError('INPUT_SCHEMA',f'{path}: missing={sorted(missing)}; unknown={sorted(extra)}.')
        for key,item in value.items():validate(item,schema.get('properties',{}).get(key,{}),f'{path}.{key}')
