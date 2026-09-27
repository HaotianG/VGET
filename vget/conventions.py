"""Inspectable convention-note extraction. Unknown rules never activate."""
import re
from .store import HOSTS, now, uid

class ConventionError(ValueError):
    pass

ALIASES={'name prefix':'name_prefix','name_prefix':'name_prefix','protect feature':'protect','protect':'protect','protected feature':'protect','allowed hosts':'allowed_hosts','allowed_hosts':'allowed_hosts','topology':'topology','max length':'max_length','max_length':'max_length','assembly family':'assembly_family','assembly_family':'assembly_family'}

def parse_convention(name,notes):
    if not isinstance(name,str) or not name.strip() or len(name)>120:
        raise ConventionError('Give the convention a name of 1–120 characters.')
    if not isinstance(notes,str) or not notes.strip() or len(notes)>20000:
        raise ConventionError('Provide convention notes of 1–20,000 characters.')
    rules=[];unsupported=[]
    for raw in notes.splitlines():
        line=raw.strip().lstrip('- ').strip()
        if not line or line.startswith('#'):continue
        if ':' not in line:
            unsupported.append(raw);continue
        key,value=line.split(':',1);kind=ALIASES.get(key.strip().lower());value=value.strip()
        valid=bool(kind and value)
        if kind=='max_length':
            valid=value.isdigit() and 0<int(value)<=100000
            if valid:value=int(value)
        elif kind=='topology':
            value=value.lower();valid=value in ('circular','linear')
        elif kind=='assembly_family':
            value=value.lower();valid=value=='sequence_composition'
        elif kind=='allowed_hosts':
            value=[v.strip() for v in value.split(',') if v.strip()]
            valid=bool(value) and all(v in {h['name'] for h in HOSTS}|{h['id'] for h in HOSTS} for v in value)
        if not valid:unsupported.append(raw)
        else:rules.append({'kind':kind,'value':value,'source_text':raw})
    for kind in ('name_prefix','topology','assembly_family'):
        values=[r['value'] for r in rules if r['kind']==kind]
        if len(set(values))>1:unsupported.append(f'Conflicting {kind} rules: {values}')
    return {'id':uid('conv'),'name':name.strip(),'notes':notes,'rules':rules,'unsupported':unsupported,'state':'draft','version':1,'created_at':now()}

def check_convention(convention,name,host,topology,length,parent=None):
    failures=[];protected=[]
    for rule in convention['rules']:
        kind,value=rule['kind'],rule['value']
        if kind=='name_prefix' and not name.startswith(value):failures.append(f'Name must start with {value}.')
        elif kind=='allowed_hosts' and host['id'] not in value and host['name'] not in value:failures.append(f'{host["name"]} is outside this convention’s allowed host list.')
        elif kind=='topology' and topology!=value:failures.append(f'Convention requires {value} topology.')
        elif kind=='max_length' and length>value:failures.append(f'Length {length} exceeds the convention limit of {value}.')
        elif kind=='protect' and parent:
            matches=[f['id'] for f in parent['features'] if f['label']==value or f['id']==value]
            if not matches:failures.append(f'Protected feature {value} is not found in the parent.')
            elif len(matches)>1:failures.append(f'Protected feature label {value} is ambiguous; use an exact feature ID.')
            else:protected.extend(matches)
    return failures,protected
