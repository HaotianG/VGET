"""Local deterministic brief resolver. No model or remote data transfer."""
import re
from .store import HOSTS

def resolve_brief(payload,state):
    objective=payload.get('objective','')
    if not isinstance(objective,str):objective=''
    mode=payload.get('mode') or ('modify' if re.search(r'\b(replace|modify|edit|change)\b',objective,re.I) else 'create')
    questions=[];assumptions=[]
    def ask(field,message):questions.append({'field':field,'message':message})
    if not objective.strip():ask('objective','Describe the intended change or outcome.')
    if len(objective)>10000:ask('objective','Keep the objective under 10,000 characters.')
    if mode not in ('create','modify'):ask('mode','Choose create or modify.')
    mentioned=[h for h in HOSTS if re.search(r'(?<!\w)'+re.escape(h['name'])+r'(?!\w)',objective,re.I)]
    host_id=payload.get('host_id')
    if not host_id and len(mentioned)==1:
        host_id=mentioned[0]['id'];assumptions.append('Host inferred from the objective; no strain or cell-line variant has been characterized.')
    host=next((h for h in HOSTS if h['id']==host_id),None)
    if not host:ask('host_id','Which expression host or cell line should this proposal be associated with?')
    if host and mentioned and all(h['id']!=host_id for h in mentioned):ask('host_id','The selected host differs from the objective. Reconcile the host before creating a proposal.')
    records=state['records'];part_ids=payload.get('part_ids',[])
    if not isinstance(part_ids,list):part_ids=[];ask('part_ids','Choose an ordered list of part records.')
    if mode=='create':
        if not part_ids:ask('part_ids','Select the exact parts in the desired order. This prototype does not invent or retrieve sequence content.')
        for rid in part_ids:
            if not isinstance(rid,str) or rid not in records:ask('part_ids','One selected part is no longer available. Reselect an exact local record.')
        if len(part_ids)>50:ask('part_ids','The prototype supports at most 50 part instances per design.')
    elif mode=='modify':
        parent=records.get(payload.get('parent_id')) if isinstance(payload.get('parent_id'),str) else None
        if not parent:ask('parent_id','Select the exact parent record.')
        if parent:
            target=payload.get('target_feature_id')
            if not any(f['id']==target for f in parent['features']):ask('target_feature_id','Select a unique target feature in the parent.')
            if parent.get('topology') not in ('linear','circular'):ask('parent_id','Parent topology is unknown. Import a record with explicit topology before modification.')
        if payload.get('replacement_id') not in records:ask('replacement_id','Select an exact replacement record.')
    convention_id=payload.get('convention_id')
    if convention_id:
        convention=state['conventions'].get(convention_id)
        if not convention or convention['state']!='active':ask('convention_id','Review and activate the convention, or select an already active one.')
    else:assumptions.append('No lab convention is selected; only structural sequence checks will run.')
    topology=payload.get('topology','circular')
    if mode=='create' and topology not in ('circular','linear'):ask('topology','Choose circular or linear topology explicitly.')
    if mode=='create' and 'topology' not in payload:assumptions.append('Circular topology is the interface default; confirm it matches your intended construct.')
    if re.search(r'\b(optimi[sz]e|codon|primer|overhang|restriction|golden gate|gibson)\b',objective,re.I):
        ask('objective','This prototype cannot infer method-specific sequence edits, primers or optimization. Supply finalized input records and describe an exact composition/replacement task instead.')
    assumptions.extend(['Host selection records intent; compatibility and biological function remain unevaluated.', 'The local resolver checks required fields and explicit record selections; it does not interpret arbitrary scientific instructions.', 'Sequence composition/replacement does not establish laboratory assembly feasibility.'])
    return {'summary':f'{"Modify an existing record" if mode=="modify" else "Compose selected parts"}'+(f' for {host["name"]}.' if host else '; host unresolved.'), 'questions':questions,'assumptions':assumptions,'ready':not questions,'mode':mode,'host_id':host_id,'supported_scope':'Exact user-specified sequence composition or feature replacement; no autonomous biological design.'}
