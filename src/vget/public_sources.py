"""Bounded public NCBI search and exact record retrieval; no private uploads or retries."""
import json
import re
import ssl
import time
from http.client import HTTPException
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import HTTPRedirectHandler, HTTPSHandler, ProxyHandler, Request, build_opener

from .contracts import ToolError
from .sequence import SequenceError, parse_records
from .store import digest, now, uid

MAX_BYTES = 2 * 1024 * 1024
MAX_BASES = 100000
ACCESSION_PATTERN = r'[A-Z][A-Z0-9_]{0,31}\.[1-9][0-9]{0,8}'


def source_url(accession):
    if not isinstance(accession, str) or not re.fullmatch(ACCESSION_PATTERN, accession):
        raise ToolError('NCBI_ACCESSION_INVALID', 'Supply one exact uppercase accession.version, for example M77789.2.')
    return 'https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi?' + urlencode({
        'db': 'nuccore', 'rettype': 'gb', 'retmode': 'text', 'id': accession, 'tool': 'VGET'})


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ToolError('NCBI_NETWORK', 'NCBI redirected the public request; redirects are not followed.')


def fetch_public(url):
    """GET a fixed official endpoint with verified TLS and a bounded body.

    No environment proxies, cookies, credentials, API keys or local data are sent.
    No redirects or automatic retries. Caller owns workspace serialization/pacing.
    """
    request = Request(url, headers={'User-Agent': 'VGET', 'Accept': 'text/plain'}, method='GET')
    opener = build_opener(ProxyHandler({}), HTTPSHandler(context=ssl.create_default_context()), _NoRedirect())
    try:
        with opener.open(request, timeout=10) as response:
            if response.status != 200:
                raise ToolError('NCBI_INVALID_RESPONSE', 'NCBI did not return HTTP 200.')
            raw = response.read(MAX_BYTES + 1)
    except HTTPError as error:
        details = {'http_status': error.code}
        if error.code == 429:
            details['retry_after'] = error.headers.get('Retry-After') if error.headers else None
            raise ToolError('NCBI_RATE_LIMIT', 'NCBI returned HTTP 429; no retry was attempted.', details) from error
        raise ToolError('NCBI_NETWORK', 'NCBI public retrieval failed; no retry was attempted.', details) from error
    except (URLError, OSError, HTTPException) as error:
        raise ToolError('NCBI_NETWORK', 'NCBI public retrieval failed; no retry was attempted.', {'reason': str(error)}) from error
    if len(raw) > MAX_BYTES:
        raise ToolError('NCBI_RESPONSE_LIMIT', 'NCBI response exceeds the 2 MB limit.')
    return raw


def _fetch_eutils_json(path,params):
    if path not in ('esearch.fcgi','esummary.fcgi'):
        raise ToolError('NCBI_URL','Only the official NCBI nucleotide search and summary endpoints are allowed.')
    url='https://eutils.ncbi.nlm.nih.gov/entrez/eutils/'+path+'?'+urlencode(params)
    request=Request(url,headers={'User-Agent':'VGET-public-reference/0.2.4','Accept':'application/json'},method='GET')
    opener=build_opener(ProxyHandler({}),HTTPSHandler(context=ssl.create_default_context()),_NoRedirect())
    try:
        with opener.open(request,timeout=10) as response:
            if response.status!=200:raise ToolError('NCBI_INVALID_RESPONSE','NCBI did not return HTTP 200.')
            raw=response.read(MAX_BYTES+1)
    except HTTPError as error:
        details={'http_status':error.code}
        if error.code==429:
            details['retry_after']=error.headers.get('Retry-After') if error.headers else None
            raise ToolError('NCBI_RATE_LIMIT','NCBI returned HTTP 429; no retry was attempted.',details) from error
        raise ToolError('NCBI_NETWORK','NCBI public search failed; no retry was attempted.',details) from error
    except (URLError,OSError,HTTPException) as error:
        raise ToolError('NCBI_NETWORK','NCBI public search failed; no retry was attempted.',{'reason':str(error)}) from error
    if len(raw)>MAX_BYTES:raise ToolError('NCBI_RESPONSE_LIMIT','NCBI search response exceeds the 2 MB limit.')
    return url,raw


def search_ncbi(store,query,limit=10):
    """Return bounded NCBI nucleotide summaries; do not acquire sequence bytes."""
    if not isinstance(query,str) or not 1<=len(query.strip())<=120:
        raise ToolError('NCBI_QUERY_INVALID','Supply a public search phrase from 1 to 120 characters.')
    if type(limit) is not int or not 1<=limit<=20:
        raise ToolError('NCBI_RESULT_LIMIT','NCBI search is limited to 20 summaries per request.')
    term=query.strip()
    with store.lock:
        time.sleep(1.1)
        search_url,search_raw=_fetch_eutils_json('esearch.fcgi',{'db':'nuccore','term':term,'retmode':'json','retmax':limit,'tool':'VGET','sort':'relevance'})
        try:
            result=json.loads(search_raw)['esearchresult']
            ids=result['idlist'];count=int(result['count'])
            if not isinstance(ids,list) or len(ids)>limit or any(not isinstance(i,str) or not i.isdigit() for i in ids):raise ValueError('Invalid NCBI ID list')
        except (ValueError,KeyError,TypeError) as error:
            raise ToolError('NCBI_INVALID_RESPONSE','NCBI returned an unexpected nucleotide search response.',type(error).__name__) from error
        summaries_url=None;summaries={}
        if ids:
            time.sleep(1.1)
            summaries_url,summary_raw=_fetch_eutils_json('esummary.fcgi',{'db':'nuccore','id':','.join(ids),'retmode':'json','tool':'VGET'})
            try:
                data=json.loads(summary_raw)['result'];summaries=data
                if not isinstance(data,dict):raise ValueError('Invalid summary map')
            except (ValueError,KeyError,TypeError) as error:
                raise ToolError('NCBI_INVALID_RESPONSE','NCBI returned an unexpected nucleotide summary response.',type(error).__name__) from error
    records=[];diagnostics=[]
    for uid_ in ids:
        item=summaries.get(uid_)
        if not isinstance(item,dict):
            diagnostics.append({'uid':uid_,'code':'NCBI_SUMMARY_MISSING','message':'Search returned this ID but no usable summary.'});continue
        if item.get('error'):
            diagnostics.append({'uid':uid_,'code':'NCBI_SUMMARY_ERROR','message':str(item['error'])});continue
        accession=item.get('accessionversion')
        if not isinstance(accession,str) or not re.fullmatch(ACCESSION_PATTERN,accession):
            diagnostics.append({'uid':uid_,'code':'NCBI_SUMMARY_INVALID','message':'Summary lacks a valid accession.version.'});continue
        records.append({'accession_version':accession,'title':item.get('title'),'length':item.get('slen',item.get('length')),
            'molecule_type':item.get('moltype'),'topology':item.get('topology'),'organism':item.get('organism'),
            'source_url':'https://www.ncbi.nlm.nih.gov/nuccore/'+accession})
    return {'source':'NCBI Nucleotide','search_term':term,'retrieved_at':now(),'result_count':count,'returned':len(records),
        'limit':limit,'has_more':count>len(ids),'search_url':search_url,'summary_url':summaries_url,'records':records,
        'diagnostics':diagnostics,'summary_status':'partial' if records and diagnostics else 'unusable' if diagnostics else 'complete',
        'notice':'Candidates only; no sequence was fetched or imported. Confirm the record is the intended complete plasmid or part before calling library.fetch_ncbi. NCBI search is not host or biological validation.'}


def fetch_ncbi(store, accession, expected_raw_sha256=None):
    url = source_url(accession)
    if expected_raw_sha256 is not None and not re.fullmatch(r'[0-9a-f]{64}', expected_raw_sha256):
        raise ToolError('NCBI_HASH_INVALID', 'Expected raw SHA-256 must be 64 lowercase hexadecimal characters.')
    with store.lock:
        # One-second delay under the shared process lock bounds successive calls
        # in this workspace to <=1 request/sec, including failed requests.
        # Callers using multiple workspaces must coordinate NCBI's shared IP limit.
        time.sleep(1)
        raw = fetch_public(url)
        if len(raw) > MAX_BYTES:raise ToolError('NCBI_RESPONSE_LIMIT', 'NCBI response exceeds the 2 MB limit.')
        raw_hash = digest(raw)
        if expected_raw_sha256 is not None and expected_raw_sha256 != raw_hash:
            raise ToolError('NCBI_HASH_MISMATCH', 'Retrieved bytes differ from the expected SHA-256; nothing was imported.', {'actual_raw_sha256': raw_hash})
        try:
            text = raw.decode('utf-8')
            if not text.startswith('LOCUS '):raise ValueError('Expected original GenBank text.')
            records = parse_records(text, accession + '.gbk')
            if len(records) != 1:raise ValueError('Expected exactly one record.')
            record = records[0]
            if record['length'] > MAX_BASES:raise ValueError('Record exceeds 100,000 bases.')
        except (UnicodeError, SequenceError, ValueError) as error:
            raise ToolError('NCBI_INVALID_RESPONSE', 'NCBI response is not one valid DNA GenBank record of at most 100,000 bases.', {'reason': str(error)}) from error
        if record['metadata']['record_id'] != accession:
            raise ToolError('NCBI_ACCESSION_MISMATCH', 'NCBI returned a different accession.version; nothing was imported.', {'requested': accession, 'returned': record['metadata']['record_id']})
        state = store.load()
        acquisition_key = f'public_ncbi_efetch:{accession}:{raw_hash}'
        acquired = [r for r in state['records'].values() if r.get('source', {}).get('acquisition') == 'public_ncbi_efetch' and r['source'].get('accession') == accession]
        existing = next((r for r in acquired if r.get('_import_key') == acquisition_key), None)
        if existing:
            # Never overwrite or silently repair altered originals or metadata.
            comparable = ('name', 'description', 'sequence', 'length', 'topology', 'features', 'metadata', 'sequence_sha256')
            if any(existing.get(k) != record.get(k) for k in comparable) or existing['source'].get('raw_sha256') != raw_hash or existing['source'].get('source_url') != url or existing['source'].get('kind') != 'ncbi':
                raise ToolError('SOURCE_INTEGRITY', 'Previously acquired NCBI record has changed; it was not overwritten.')
            if not (store.raw / raw_hash).is_file():
                raise ToolError('SOURCE_INTEGRITY', 'Previously acquired original is missing; it was not silently repaired.')
            store.keep_raw(raw)
            return {'record': existing, 'diagnostics': [{'code': 'DUPLICATE', 'message': 'This exact public acquisition is already retained.', 'record_id': existing['id']}], 'biological_function': 'unevaluated'}
        timestamp = now()
        record['id'] = uid('rec')
        record['_import_key'] = acquisition_key
        record['source'].update(kind='ncbi', accession=accession, source_url=url, retrieved_at=timestamp,
            imported_at=timestamp, raw_sha256=raw_hash, acquisition='public_ncbi_efetch',
            access='retrieved from official public NCBI EFetch over verified TLS; biological function unevaluated')
        diagnostics = []
        if acquired:
            diagnostics.append({'code': 'NCBI_SOURCE_CHANGED', 'message': 'The same accession.version returned different original bytes. Both acquisitions are retained; review source changes before selecting a record.', 'record_ids': [r['id'] for r in acquired] + [record['id']]})
        store.keep_raw(raw)
        state['records'][record['id']] = record
        store.save(state)
        return {'record': record, 'diagnostics': diagnostics, 'biological_function': 'unevaluated'}
