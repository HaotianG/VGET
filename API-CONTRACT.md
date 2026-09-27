# VGET optional manual HTTP interface

This document describes the retained GUI compatibility API. The primary prototype 2 agent interface is the JSON CLI/Python toolkit in `tool-specs.json` and `skills/vget/references/workflow.md`. Both paths use the same `Service` and sequence/report core. The HTTP form brief remains a manual-input helper, not the agent reasoning layer.

This is a local software prototype, not experimentally validated design software. Data uses the bundled official iGEM reference snapshot, explicit synthetic demonstration records or user-supplied files. Registry tools are exposed through the primary CLI/Python interface; this compatibility HTTP API does not add network endpoints. Nine host profiles selectable; compatibility is unevaluated. No cloud model or credentialed live source access by default.

## HTTP API (all responses JSON except downloads)
- GET /api/state -> {records: Record[], designs: Design[], hosts: [{id,name,status}], conventions: Convention[], sources: [...], limitations: string[]}
- POST /api/import multipart files (multiple), optional source ('lab','igem','addgene','ncbi') -> {records, diagnostics}. Supports GenBank/FASTA and CSV/XLSX catalogue; plain convention notes use conventions API. Duplicates and conflicting labels are surfaced, not overwritten.
- POST /api/brief JSON {objective, mode:'create'|'modify', host_id, part_ids:[], parent_id?, target_feature_id?, replacement_id?, convention_id?} -> {summary, questions:[{field,message}], assumptions:[], ready:boolean, mode, host_id, supported_scope}
- POST /api/design JSON same fields plus {name,topology:'circular'|'linear',protected_feature_ids:[]} -> {design: Design}. Creation composes provided ordered parts (sequence composition, assembly feasibility unevaluated); modify replaces a unique exact feature, preserving protected features. Hard unresolved questions return 422 {error:{code,message,details}}.
- POST /api/conventions JSON {name,notes} -> {convention}; extracted naming/protection rules proposed for review. POST /api/conventions/<id>/activate JSON {reviewed:true} -> {convention}. Current prototype enforces extracted rules it supports and discloses unsupported notes. Unknown meaningful rules block activation.
- POST /api/compare JSON {left_id,right_id} -> {comparison:{same_sequence,same_circular_molecule,length_delta,summary, ...}}
- GET /api/designs/<id> -> {design}
- GET /api/designs/<id>/construct.gbk (download)
- GET /api/designs/<id>/report.html (standalone report view/download)
- GET /api/designs/<id>/bundle.zip (download)
- Errors {error:{code,message,details?}}; fetch UI must display readable errors and never fake success.

## Record
{id,name,description,sequence,topology,length,sequence_sha256,features:[{id,type,label,location,segments:[{start,end,strand}],qualifiers:{key:[values]},layer}],metadata:{},source:{kind,filename,...}}
Internal exact spans zero-based end-exclusive. Compound locations retain location string. Raw import bytes kept separately on server. UI display coordinates 1-based inclusive.

## Design
{id,name,created_at,mode,host_id,host_name,objective,record:Record,parent_id,part_ids,convention_id,assumptions:[],checks:[{id,status,message}],changes:[],status,files:{genbank,report,bundle}}
Status explicitly describes computational result, no functional validation. Records created by design also available in state.records. No browser display of sequence interpreted as executable markup.

## Convention
{id,name,notes,rules:[{kind,value,source_text}],unsupported:[],state:'draft'|'active',version}

## Python core (sequence.py)
class SequenceError(ValueError): .code, .details; init(code,message,details=None)
parse_records(text:str, filename:str) -> list[Record]
to_genbank(record:dict) -> str
compose(records:list[dict],name:str,topology='circular') -> tuple[Record,list[dict]]
replace_feature(parent:dict,feature_id:str,replacement:dict,name:str,protected_feature_ids:list[str]=[]) -> tuple[Record,list[dict]]
validate_record(record:dict) -> list[{id,status,message}]
compare_records(left:dict,right:dict) -> dict

Record IDs and feature IDs stable and unique within record. Inputs immutable. Remote/fuzzy/order location transformations fail explicitly. Parent annotation intersections unresolved => reject unless exactly the selected target feature. Outside features map with qualifiers intact. Unsupported parsing cannot silently discard features. GenBank sidecar round-trip semantic check. Core receives already approved exact sources; no network calls.
