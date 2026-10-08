"""Versioned public reference snapshot; offline installation and explicit read-only freshness checks.

Never submits local records or objectives. Live checks are restricted to the six
bundled public identifiers, use verified TLS and never update the installed pin.
"""
from __future__ import annotations
import copy
import json
from pathlib import Path
import re
import time
import urllib.error
import urllib.request
import ssl
import uuid
from urllib.parse import parse_qs, urlencode, urlsplit
from .contracts import ToolError
from .sequence import parse_records, SequenceError
from .store import digest, json_bytes, now, uid

PACK_DIR=Path(__file__).parent/'data'/'registry'/'igem-reporters-2026-09-21'
BASE='https://api.registry.igem.org/v1/'
MAX_BYTES=2_000_000
MAX_BASES=100_000


def load_pack():
    try:
        pack=json.loads((PACK_DIR/'manifest.json').read_bytes())
        if pack['schema_version']!=1 or len(pack['parts'])!=6:raise ValueError('Unexpected pack schema/count')
        for part in pack['parts']:
            for item in part['files'].values():
                path=(PACK_DIR/item['path']).resolve()
                if path.parent!=PACK_DIR.resolve():raise ValueError('Invalid pack file path')
                if not path.is_file() or digest(path.read_bytes())!=item['sha256']:raise ValueError('Missing or changed file: '+item['path'])
            meta=json.loads(_bytes(part,'metadata'))
            records=parse_records(_bytes(part,'genbank').decode(),part['files']['genbank']['path'])
            if len(records)!=1:raise ValueError('Expected one original GenBank record')
            record=records[0]
            if (meta['uuid']!=part['uuid'] or meta['slug']!=part['slug'] or meta['name']!=part['name']
                or meta['sequence'].upper()!=record['sequence'] or record['sequence_sha256']!=part['sequence_sha256']
                or record['length']!=part['length'] or record['topology']!=part['topology']):
                raise ValueError('API metadata / GenBank identity mismatch')
        return pack
    except (OSError,ValueError,KeyError,TypeError,SequenceError) as e:
        raise ToolError('REGISTRY_INTEGRITY','Bundled reference pack cannot be verified: '+str(e)) from e


def _bytes(part,kind):return (PACK_DIR/part['files'][kind]['path']).read_bytes()
def _hash(record):return digest(json_bytes(record))


def _select(pack,ids):
    if ids is None:return pack['parts']
    if not ids or len(ids)!=len(set(ids)):raise ToolError('REGISTRY_SELECTION','Supply distinct known part identifiers, or omit part_ids for all six.')
    index={p['name']:p for p in pack['parts']}
    missing=set(ids)-index.keys()
    if missing:raise ToolError('REGISTRY_PART_UNKNOWN','Only bundled public reference identifiers are supported.',sorted(missing))
    return [index[name] for name in ids]


def status(store):
    pack=load_pack();pin=store.load().get('registries',{}).get(pack['pack_id'],{})
    live_imports=[r for r in store.load()['records'].values() if r.get('source',{}).get('acquisition')=='igem_public_published_api']
    return {'pack_id':pack['pack_id'],'version':pack['version'],'bundled_records':len(pack['parts']),
        'installed_records':len(pin.get('records',{})),'retrieved_on':pack['retrieved_on'],
        'scope':pack['scope'],'biological_validation':'unevaluated',
        'public_igem_imports':len(live_imports),
        'addgene':{'status':'file imports only','reason':'Approved API access and the applicable data license are not configured.'},
        'last_live_check':pin.get('last_live_check')}


def search(store,query=''):
    pack=load_pack();tokens=query.casefold().split()
    found=[copy.deepcopy(p) for p in pack['parts'] if all(t in json.dumps(p,ensure_ascii=False).casefold() for t in tokens)]
    mappings=store.load().get('registries',{}).get(pack['pack_id'],{}).get('records',{})
    for p in found:p['installed_record_id']=mappings.get(p['name'],{}).get('record_id')
    return {'pack_id':pack['pack_id'],'parts':found,'total':len(found),'ranking':'lexical matching only; source claims are unevaluated'}


def verify(store):
    pack=load_pack();state=store.load();pin=state.get('registries',{}).get(pack['pack_id'],{});issues=[]
    if pin and pin.get('manifest_sha256')!=digest((PACK_DIR/'manifest.json').read_bytes()):
        issues.append({'code':'PACK_VERSION_CHANGED','message':'Installed manifest differs from bundled pin; no automatic overwrite.'})
    for name,item in pin.get('records',{}).items():
        r=state['records'].get(item['record_id'])
        if not r or _hash(r)!=item['record_sha256']:
            issues.append({'code':'RECORD_CHANGED','part_id':name});continue
        for blob in [r['source']]+r['source'].get('evidence_blobs',[]):
            path=store.raw/blob['raw_sha256']
            if not path.is_file() or digest(path.read_bytes())!=blob['raw_sha256']:
                issues.append({'code':'SOURCE_CHANGED','part_id':name,'filename':blob['filename']})
    return {'status':'fail' if issues else 'pass','pack_id':pack['pack_id'],'bundled_records':len(pack['parts']),
        'installed_records':len(pin.get('records',{})),'issues':issues,
        'meaning':'Local bytes and record fingerprints only; neither scientific validation nor current upstream freshness.'}


def install(store,part_ids=None):
    pack=load_pack();selected=_select(pack,part_ids);check=verify(store)
    if check['status']!='pass':raise ToolError('REGISTRY_INSTALLED_CHANGED','Existing registry installation changed; preserve it and use a fresh workspace or investigate.',check['issues'])
    state=store.load();pin=state.setdefault('registries',{}).setdefault(pack['pack_id'],{
        'version':pack['version'],'manifest_sha256':digest((PACK_DIR/'manifest.json').read_bytes()),'installed_at':now(),'records':{}})
    installed=[];already=[]
    # Validate entire pack before any visible state mutation. Originals are immutable content-addressed blobs.
    for part in selected:
        if part['name'] in pin['records']:
            already.append(state['records'][pin['records'][part['name']]['record_id']]);continue
        raw=_bytes(part,'genbank');r=parse_records(raw.decode(),part['files']['genbank']['path'])[0]
        r['id']=uid('rec');r['_import_key']=f'{digest(raw)}:0:igem'
        r['metadata']['registry']={**copy.deepcopy(part),'pack_id':pack['pack_id'],'pack_version':pack['version'],'retrieved_on':pack['retrieved_on']}
        blobs=[]
        for kind in ('metadata','attribution','license'):
            item=part['files'][kind];blobs.append({'filename':item['path'],'raw_sha256':store.keep_raw(_bytes(part,kind)),'source_url':item['source_url']})
        blobs.append({'filename':'registry-manifest.json','raw_sha256':store.keep_raw((PACK_DIR/'manifest.json').read_bytes()),'origin':'VGET curated snapshot manifest'})
        r['source'].update(kind='igem',raw_sha256=store.keep_raw(raw),imported_at=now(),
            access='bundled official public API snapshot',source_url=part['files']['genbank']['source_url'],evidence_blobs=blobs)
        state['records'][r['id']]=r;pin['records'][part['name']]={'record_id':r['id'],'record_sha256':_hash(r)};installed.append(r)
    store.save(state)
    # Match all other discovery tools: summaries contain no sequence bases.
    from .toolkit import summary
    return {'pack_id':pack['pack_id'],'installed':len(installed),'already_installed':len(already),'records':[summary(r) for r in installed+already]}


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,req,fp,code,msg,headers,newurl):
        raise ToolError('REGISTRY_NETWORK','Public registry redirect refused; no credentials or local data were sent.')


def fetch_public(url):
    parsed=urlsplit(url)
    allowed_path=(re.fullmatch(r'/v1/parts/slugs/bba-[a-z0-9]{1,24}',parsed.path)
        or re.fullmatch(r'/v1/parts/[0-9a-f-]{36}\.gb',parsed.path)
        or re.fullmatch(r'/v1/parts/[0-9a-f-]{36}/authors',parsed.path)
        or re.fullmatch(r'/v1/licenses/[0-9a-f-]{36}',parsed.path)
        or parsed.path=='/v1/parts')
    if parsed.scheme!='https' or parsed.netloc!='api.registry.igem.org' or not allowed_path:
        raise ToolError('REGISTRY_URL','Only documented official part metadata and GenBank endpoints are allowed.')
    query=parse_qs(parsed.query,strict_parsing=True) if parsed.query else {}
    if parsed.path=='/v1/parts':
        if set(query)-{'search','name','page','pageSize','status'} or query.get('status')!=['published'] or bool(query.get('search'))==bool(query.get('name')):
            raise ToolError('REGISTRY_URL','Public searches must request only published parts with bounded pagination.')
        if any(len(values)!=1 for values in query.values()):raise ToolError('REGISTRY_URL','Duplicate public search parameters are refused.')
        try:
            if int(query['page'][0])<1 or not 1<=int(query['pageSize'][0])<=20 or len(query.get('search',query.get('name',['']))[0])>120:
                raise ValueError
        except (KeyError,ValueError,IndexError):
            raise ToolError('REGISTRY_URL','Public search page and size are outside the permitted bounds.')
    elif parsed.query and (not parsed.path.endswith('/authors') or set(query)!={'page','pageSize'} or query.get('page')!=['1'] or query.get('pageSize')!=['100']):
        raise ToolError('REGISTRY_URL','Only the first bounded public-author page may be retrieved.')
    request=urllib.request.Request(url,headers={'User-Agent':'VGET-public-reference/0.2.3','Accept':'application/json, text/plain'})
    try:
        opener=urllib.request.build_opener(urllib.request.ProxyHandler({}),urllib.request.HTTPSHandler(context=ssl.create_default_context()),_NoRedirect())
        with opener.open(request,timeout=10) as response:
            raw=response.read(MAX_BYTES+1)
        if len(raw)>MAX_BYTES:raise ToolError('REGISTRY_RESPONSE_LIMIT','Public registry response exceeds 2 MB.')
        return raw
    except urllib.error.HTTPError as e:
        raise ToolError('REGISTRY_RATE_LIMIT' if e.code==429 else 'REGISTRY_HTTP',f'Public registry returned HTTP {e.code}. Retry later; pinned data is unchanged.',{'retry_after':e.headers.get('Retry-After')}) from e
    except (OSError,urllib.error.URLError) as e:
        raise ToolError('REGISTRY_NETWORK','Public registry unavailable; pinned data is unchanged.',type(e).__name__) from e


def search_public(store,query=None,page=1,page_size=10,name=None):
    """Search one small page of anonymous, published iGEM records."""
    if (query is None)==(name is None):raise ToolError('REGISTRY_QUERY','Supply either a public search phrase or one exact BBa_ part name.')
    if query is not None and (not isinstance(query,str) or not 1<=len(query.strip())<=120):
        raise ToolError('REGISTRY_QUERY','Supply a search phrase from 1 to 120 characters.')
    if name is not None and (not isinstance(name,str) or not re.fullmatch(r'BBa_[A-Za-z0-9]{1,24}',name)):
        raise ToolError('REGISTRY_NAME','Exact name must look like BBa_J23119.')
    if type(page) is not int or not 1<=page<=1000:
        raise ToolError('REGISTRY_PAGE','Page must be an integer from 1 to 1000.')
    if type(page_size) is not int or not 1<=page_size<=20:
        raise ToolError('REGISTRY_PAGE_SIZE','Public search is limited to 20 results per request.')
    params=urlencode({'search':query.strip(),'status':'published','page':page,'pageSize':page_size} if query is not None else {'name':name,'status':'published','page':page,'pageSize':page_size})
    url=BASE+'parts?'+params
    with store.lock:
        time.sleep(1.1)
        raw=fetch_public(url)
    try:
        response=json.loads(raw)
        entries=response['data']
        if not isinstance(entries,list) or len(entries)>page_size:raise ValueError('Invalid result page')
        results=[]
        for part in entries:
            if not isinstance(part,dict) or part.get('status')!='published':continue
            results.append({key:part.get(key) for key in ('uuid','name','slug','status','title','description','sequenceLength','role','chassis','audit','usageCount')})
        return {'source':'iGEM public API','source_url':url,'retrieved_at':now(),'page':page,'page_size':page_size,
            'search_term':query if query is not None else name,'exact_name_filter':name is not None,
            'total_matches':response.get('total'),'results':results,
            'ranking':'Upstream text search order; no biological or host suitability ranking. Only published anonymous results requested.'}
    except (ValueError,KeyError,TypeError) as e:
        raise ToolError('REGISTRY_RESPONSE_INVALID','iGEM public search returned an unexpected published-part response.',type(e).__name__) from e


def _public_metadata(meta, authors, license):
    return {'uuid':str(uuid.UUID(meta['uuid'])),'slug':meta['slug'],'status':'published','title':meta.get('title'),
            'description':meta.get('description'),'role':meta.get('role'),'chassis':meta.get('chassis'),
            'source':meta.get('source'),'audit':meta.get('audit'),'license':license,'authors':authors,
            'reuse_status':'Source-declared license metadata retained; review the license and attribution before redistribution or commercial use.'}


def _acquisition_hash(raw_hash, evidence):
    return _hash({'genbank_sha256':raw_hash,'evidence':sorted(evidence,key=lambda b:b['filename'])})


def _verify_public_acquisition(store, record):
    """Reconstruct identity from verified original blobs, including legacy imports."""
    try:
        source=record['source'];slug=source['registry_slug']
        def read(blob):
            h=blob['raw_sha256']
            if not isinstance(h,str) or not re.fullmatch(r'[0-9a-f]{64}',h):raise ValueError('Invalid original hash')
            path=store.raw/h
            raw=path.read_bytes()
            if digest(raw)!=h:raise ValueError('Original blob changed')
            return raw
        raw=read(source)
        blobs=source['evidence_blobs']
        by_name={b['filename']:b for b in blobs}
        if len(by_name)!=len(blobs):raise ValueError('Duplicate evidence filename')
        meta=json.loads(read(by_name[slug+'.metadata.json']))
        authors=json.loads(read(by_name[slug+'.authors.json']))
        license=None
        expected={slug+'.metadata.json':BASE+'parts/slugs/'+slug,
                  slug+'.authors.json':BASE+f'parts/{str(uuid.UUID(meta["uuid"]))}/authors?page=1&pageSize=100'}
        if meta.get('licenseUUID'):
            expected[slug+'.license.json']=BASE+'licenses/'+str(uuid.UUID(meta['licenseUUID']))
            license=json.loads(read(by_name[slug+'.license.json']))
            if license.get('uuid')!=meta['licenseUUID']:raise ValueError('License identity changed')
        if set(by_name)!=set(expected):raise ValueError('Missing or unexpected evidence')
        for name,url in expected.items():
            if by_name[name]['source_url']!=url:raise ValueError('Evidence origin changed')
        if meta['slug']!=slug or meta['status']!='published':raise ValueError('Metadata identity changed')
        parsed=parse_records(raw.decode('utf-8'),slug+'.gb')
        if len(parsed)!=1:raise ValueError('Original contains multiple records')
        expected_record=parsed[0]
        if expected_record['name']!=meta['name'] or expected_record['sequence']!=str(meta.get('sequence','')).upper():
            raise ValueError('Metadata and original sequence disagree')
        expected_record['metadata']['igem_public']=_public_metadata(meta,authors,license)
        comparable=('name','description','sequence','length','topology','features','metadata','sequence_sha256')
        if any(record.get(k)!=expected_record.get(k) for k in comparable):raise ValueError('Parsed record or evidence metadata changed')
        expected_source={'kind':'igem','filename':slug+'.gb','source_url':BASE+f'parts/{str(uuid.UUID(meta["uuid"]))}.gb',
                         'acquisition':'igem_public_published_api','accession':meta['name'],'registry_uuid':str(uuid.UUID(meta['uuid']))}
        if any(source.get(k)!=v for k,v in expected_source.items()):raise ValueError('Source identity changed')
        identity=_acquisition_hash(source['raw_sha256'],blobs)
        if source.get('acquisition_sha256',identity)!=identity:raise ValueError('Acquisition fingerprint changed')
        return identity
    except (OSError,ValueError,KeyError,TypeError,UnicodeError,SequenceError) as error:
        raise ToolError('SOURCE_INTEGRITY','Previously acquired iGEM record or source evidence has changed; nothing was repaired or overwritten.',str(error)) from error


def import_public_part(store,slug,expected_genbank_sha256=None):
    """Retrieve one explicitly selected published part and its provenance."""
    if not isinstance(slug,str) or not re.fullmatch(r'bba-[a-z0-9]{1,24}',slug):
        raise ToolError('REGISTRY_PART_ID','Choose one exact public iGEM slug such as bba-k5198012.')
    if expected_genbank_sha256 is not None and not re.fullmatch(r'[0-9a-f]{64}',expected_genbank_sha256):
        raise ToolError('REGISTRY_HASH_INVALID','Expected GenBank SHA-256 must be 64 lowercase hexadecimal characters.')
    with store.lock:
        base=BASE
        meta_url=base+'parts/slugs/'+slug
        try:
            time.sleep(1.1)
            meta_raw=fetch_public(meta_url);meta=json.loads(meta_raw)
            if not isinstance(meta,dict):raise ValueError('Invalid part metadata response')
            if meta.get('status')!='published' or meta.get('slug')!=slug:
                raise ToolError('REGISTRY_PART_NOT_PUBLISHED','Only the exact published part identified by its slug can be imported.')
            part_uuid=str(uuid.UUID(meta['uuid']))
            if not isinstance(meta.get('name'),str) or meta['name'].casefold()!=slug.replace('-','_',1).casefold():
                raise ToolError('REGISTRY_UPSTREAM_MISMATCH','The published part slug and registry name disagree.')
            gb_url=base+f'parts/{part_uuid}.gb'
            time.sleep(1.1);gb_raw=fetch_public(gb_url)
            authors_url=base+f'parts/{part_uuid}/authors?page=1&pageSize=100'
            time.sleep(1.1);authors_raw=fetch_public(authors_url);authors=json.loads(authors_raw)
            if not isinstance(authors,dict) or not isinstance(authors.get('data'),list):raise ValueError('Invalid authors response')
            if int(authors.get('total',len(authors.get('data',[]))))>100:
                raise ToolError('REGISTRY_ATTRIBUTION_LIMIT','Author list exceeds the bounded first-page limit; nothing was imported.')
            license=None;license_raw=None;license_url=None
            if meta.get('licenseUUID'):
                license_uuid=str(uuid.UUID(meta['licenseUUID']))
                license_url=base+'licenses/'+license_uuid
                time.sleep(1.1);license_raw=fetch_public(license_url);license=json.loads(license_raw)
                if not isinstance(license,dict):raise ValueError('Invalid license response')
                if license.get('uuid')!=license_uuid:raise ToolError('REGISTRY_UPSTREAM_MISMATCH','License response UUID does not match the published part metadata.')
            if len(gb_raw)>MAX_BYTES:raise ToolError('REGISTRY_RESPONSE_LIMIT','Public GenBank response exceeds 2 MB.')
            records=parse_records(gb_raw.decode('utf-8'),slug+'.gb')
            if len(records)!=1:raise ValueError('Expected one GenBank record')
            record=records[0]
            if record['length']>MAX_BASES:raise ToolError('REGISTRY_RECORD_LIMIT','Selected record exceeds the 100,000-base VGET limit.')
            metadata_sequence=str(meta.get('sequence','')).upper()
            if (record['name']!=meta.get('name') or (meta.get('sequenceLength') is not None and record['length']!=meta['sequenceLength'])
                or record['sequence']!=metadata_sequence):
                raise ToolError('REGISTRY_UPSTREAM_MISMATCH','iGEM metadata and GenBank identity/sequence disagree; nothing was imported.',
                    {'metadata_name':meta.get('name'),'genbank_name':record['name'],'metadata_length':meta.get('sequenceLength'),
                     'genbank_length':record['length'],'metadata_sequence_sha256':digest(metadata_sequence.encode()),
                     'genbank_sequence_sha256':record['sequence_sha256']})
        except ToolError:raise
        except (OSError,ValueError,KeyError,TypeError,UnicodeError,SequenceError) as e:
            raise ToolError('REGISTRY_RESPONSE_INVALID','Selected iGEM part metadata, attribution, license or GenBank response could not be verified.',type(e).__name__) from e

        raw_hash=digest(gb_raw)
        if expected_genbank_sha256 is not None and raw_hash!=expected_genbank_sha256:
            raise ToolError('REGISTRY_HASH_MISMATCH','GenBank bytes differ from the requested SHA-256 pin; nothing was imported.',{'actual_sha256':raw_hash})
        state=store.load()
        evidence_inputs=[(slug+'.metadata.json',meta_raw,meta_url),(slug+'.authors.json',authors_raw,authors_url)]
        if license_raw is not None:evidence_inputs.append((slug+'.license.json',license_raw,license_url))
        evidence=[{'filename':filename,'raw_sha256':digest(data),'source_url':url} for filename,data,url in evidence_inputs]
        acquisition_hash=_acquisition_hash(raw_hash,evidence)
        previous=[r for r in state['records'].values() if r.get('source',{}).get('acquisition')=='igem_public_published_api'
                  and r.get('source',{}).get('registry_slug')==slug]
        verified={r['id']:_verify_public_acquisition(store,r) for r in previous}
        existing=next((r for r in previous if verified[r['id']]==acquisition_hash),None)
        if existing:
            return {'record':existing,'diagnostics':[{'code':'DUPLICATE','message':'The complete acquisition is already retained; parsed identity and every evidence blob were verified.','record_id':existing['id']}],
                'biological_function':'unevaluated','reuse_notice':'The prior public import, including its source metadata and license response, is retained in this workspace.'}
        if len(state['records'])>=1000:raise ToolError('LIBRARY_RECORD_LIMIT','Workspace has reached the 1,000-record limit; nothing was imported.')

        record['id']=uid('rec');record['_import_key']=f'public_igem:{slug}:{acquisition_hash}'
        record['metadata']['igem_public']=_public_metadata(meta,authors,license)
        for filename,data,url in evidence_inputs:store.keep_raw(data)
        retrieved=now();store.keep_raw(gb_raw)
        record['source'].update(kind='igem',filename=slug+'.gb',source_url=gb_url,raw_sha256=raw_hash,
            imported_at=retrieved,retrieved_at=retrieved,acquisition='igem_public_published_api',
            access='one explicitly selected anonymous published iGEM record; original GenBank retained; license is source metadata, not independently verified',
            accession=meta.get('name'),registry_uuid=part_uuid,registry_slug=slug,evidence_blobs=evidence,acquisition_sha256=acquisition_hash)
        # Retain older bytes returned when the API metadata and GenBank disagree only by format.
        store.keep_raw(meta_raw);store.keep_raw(authors_raw)
        state['records'][record['id']]=record;store.save(state)
        warning=[]
        if previous:
            same_bytes=any(r['source']['raw_sha256']==raw_hash for r in previous)
            warning.append({'code':'IGEM_EVIDENCE_CHANGED' if same_bytes else 'IGEM_SOURCE_CHANGED',
                'message':'This slug has an earlier acquisition. Complete changed evidence is retained as a separate revision, including when sequence bytes are unchanged.',
                'record_ids':[r['id'] for r in previous]+[record['id']]})
        if meta.get('sequenceLength') is None:
            warning.append({'code':'IGEM_METADATA_LENGTH_MISSING','message':'The part-detail API omitted sequenceLength; GenBank length and exact sequence were checked against the API sequence.'})
        if not license:
            warning.append({'code':'LICENSE_UNSPECIFIED','message':'The registry returned no license identifier; confirm reuse terms before redistribution or commercial use.'})
        return {'record':record,'diagnostics':warning,'biological_function':'unevaluated',
            'reuse_notice':'Source-declared license metadata is preserved; public visibility alone does not establish reuse rights.'}


def check_live(store,part_ids=None):
    pack=load_pack();parts=_select(pack,part_ids);results=[]
    for i,part in enumerate(parts):
        if i:time.sleep(1.1)  # Respect the public API; never retry a rate limit in a loop.
        item={'part_id':part['name'],'checked_at':now(),'endpoints':[part['files'][k]['source_url'] for k in ('metadata','genbank')]}
        try:
            raw_meta=fetch_public(item['endpoints'][0]);time.sleep(1.1);raw_gb=fetch_public(item['endpoints'][1])
            meta=json.loads(raw_meta);records=parse_records(raw_gb.decode(),part['name']+'.gb')
            if len(records)!=1:raise ValueError('Expected one GenBank record')
            record=records[0]
            if meta['uuid']!=part['uuid'] or meta['slug']!=part['slug'] or meta['name']!=part['name']:
                item['status']='identity_changed'
            elif meta['sequence'].upper()!=record['sequence']:item['status']='inconsistent_upstream'
            elif record['sequence_sha256']!=part['sequence_sha256']:item['status']='sequence_changed'
            elif digest(raw_meta)!=part['files']['metadata']['sha256'] or digest(raw_gb)!=part['files']['genbank']['sha256']:item['status']='source_bytes_changed'
            else:item['status']='unchanged'
            item.update(metadata_sha256=digest(raw_meta),genbank_sha256=digest(raw_gb),sequence_sha256=record['sequence_sha256'],
                api_genbank_sequence_agree=meta['sequence'].upper()==record['sequence'],matches_pinned_sequence=record['sequence_sha256']==part['sequence_sha256'])
        except (ToolError,ValueError,KeyError,TypeError,SequenceError) as e:
            item.update(status='error',error={'code':getattr(e,'code','REGISTRY_RESPONSE_INVALID'),'message':str(e),'details':getattr(e,'details',None)})
        results.append(item)
        if item.get('error',{}).get('code')=='REGISTRY_RATE_LIMIT':
            results.extend({'part_id':p['name'],'status':'not_checked','reason':'Stopped after upstream rate limit; retry later.'} for p in parts[i+1:]);break
    receipt={'pack_id':pack['pack_id'],'checked_at':now(),'results':results,
        'scope':'Read-only metadata and GenBank check for bundled identifiers; attribution/license are pinned snapshots, not re-fetched by this operation. No installed records were updated.'}
    directory=store.root/'registry-checks';directory.mkdir(exist_ok=True)
    receipt_path=directory/(uid('check')+'.json');receipt_path.write_bytes(json_bytes(receipt))
    state=store.load();pin=state.setdefault('registries',{}).setdefault(pack['pack_id'],{'version':pack['version'],'manifest_sha256':digest((PACK_DIR/'manifest.json').read_bytes()),'records':{}})
    pin['last_live_check']={'path':str(receipt_path),'sha256':digest(receipt_path.read_bytes()),'checked_at':receipt['checked_at']};store.save(state)
    return {**receipt,'receipt':pin['last_live_check']}
