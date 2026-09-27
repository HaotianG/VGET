"""Offline public acquisition checks; all sequence data is synthetic."""
import io
import ssl
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlsplit

import pytest
from Bio import SeqIO
from Bio.Seq import Seq
from Bio.SeqRecord import SeqRecord

from vget import public_sources as public
from vget.store import digest
from vget.toolkit import Toolkit, ToolError


def fixture(accession='TEST123.1', comment='Synthetic software fixture'):
    record = SeqRecord(Seq('ACGTACGTACGT'), id=accession, name='TEST123', description='Synthetic test only')
    record.annotations = {'molecule_type': 'DNA', 'topology': 'circular', 'comment': comment}
    output = io.StringIO(); SeqIO.write(record, output, 'genbank')
    return output.getvalue().encode()


@pytest.fixture
def kit(tmp_path, monkeypatch):
    monkeypatch.setattr(public.time, 'sleep', lambda seconds: None)
    return Toolkit(tmp_path / 'workspace')


def respond(monkeypatch, raw):
    monkeypatch.setattr(public, 'fetch_public', lambda url: raw)


def test_exact_acquisition_preserves_bytes_and_is_idempotent(kit, monkeypatch):
    raw = fixture(); respond(monkeypatch, raw)
    first = kit.call('library.fetch_ncbi', {'accession': 'TEST123.1'})
    record = first['record']; source = record['source']
    assert source['kind'] == 'ncbi'
    assert source['acquisition'] == 'public_ncbi_efetch'
    assert source['accession'] == 'TEST123.1' and source['retrieved_at']
    assert source['raw_sha256'] == digest(raw)
    assert (kit.store.raw / digest(raw)).read_bytes() == raw
    assert record['metadata']['annotations']['comment'] == 'Synthetic software fixture'
    assert 'sequence' not in record
    before = kit.store.path.read_bytes()
    repeated = kit.call('library.fetch_ncbi', {'accession': 'TEST123.1'})
    assert repeated['record']['id'] == record['id']
    assert repeated['diagnostics'][0]['code'] == 'DUPLICATE'
    assert kit.store.path.read_bytes() == before
    assert kit.call('library.search', {'source': 'ncbi'})['total'] == 1


def test_user_label_is_not_promoted_and_changed_bytes_are_retained(kit, monkeypatch):
    raw = fixture(); imported = kit.service.import_files([('test.gbk', raw)], 'ncbi')['records'][0]
    respond(monkeypatch, raw)
    fetched = kit.call('library.fetch_ncbi', {'accession': 'TEST123.1'})['record']
    assert fetched['id'] != imported['id']
    assert 'user-supplied' in kit.store.load()['records'][imported['id']]['source']['access']
    changed = fixture(comment='Different public annotation'); respond(monkeypatch, changed)
    result = kit.call('library.fetch_ncbi', {'accession': 'TEST123.1'})
    assert result['record']['id'] != fetched['id']
    assert result['diagnostics'][0]['code'] == 'NCBI_SOURCE_CHANGED'
    assert len(kit.store.load()['records']) == 3
    assert (kit.store.raw / digest(raw)).read_bytes() == raw


@pytest.mark.parametrize('raw,code', [(b'<html>unavailable</html>', 'NCBI_INVALID_RESPONSE'), (fixture('OTHER.1'), 'NCBI_ACCESSION_MISMATCH'), (fixture() * 2, 'NCBI_INVALID_RESPONSE'), (fixture().replace(b'DNA', b'RNA'), 'NCBI_INVALID_RESPONSE'), (b'x' * (2 * 1024 * 1024 + 1), 'NCBI_RESPONSE_LIMIT')])
def test_invalid_response_is_atomic(kit, monkeypatch, raw, code):
    before = kit.store.path.read_bytes(); respond(monkeypatch, raw)
    with pytest.raises(ToolError) as error:kit.call('library.fetch_ncbi', {'accession': 'TEST123.1'})
    assert error.value.code == code
    assert kit.store.path.read_bytes() == before and not list(kit.store.raw.iterdir())


def test_expected_hash_failure_is_atomic(kit, monkeypatch):
    respond(monkeypatch, fixture()); before = kit.store.path.read_bytes()
    with pytest.raises(ToolError) as error:kit.call('library.fetch_ncbi', {'accession': 'TEST123.1', 'expected_raw_sha256': '0' * 64})
    assert error.value.code == 'NCBI_HASH_MISMATCH' and kit.store.path.read_bytes() == before


@pytest.mark.parametrize('accession', ['TEST123', 'TEST123.0', 'TEST123.1,OTHER.1', 'https://example.com', 'TEST123.1&api_key=secret'])
def test_exact_version_required_before_network(kit, monkeypatch, accession):
    monkeypatch.setattr(public, 'fetch_public', lambda url: pytest.fail('No network for invalid identifier'))
    with pytest.raises(ToolError):kit.call('library.fetch_ncbi', {'accession': accession})


def test_one_official_get_tls_timeout_and_bounded_read(monkeypatch):
    calls = []; handlers = []
    class Response(io.BytesIO):
        status = 200
        def read(self, size=-1):
            assert size == public.MAX_BYTES + 1
            return super().read(size)
    class Opener:
        def open(self, request, timeout):
            calls.append(request)
            assert timeout == 10 and request.get_method() == 'GET' and request.data is None
            return Response(fixture())
    def build(*args):handlers.extend(args); return Opener()
    monkeypatch.setattr(public, 'build_opener', build)
    raw = public.fetch_public(public.source_url('TEST123.1'))
    assert raw == fixture() and len(calls) == 1
    url = urlsplit(calls[0].full_url)
    assert url.scheme == 'https' and url.netloc == 'eutils.ncbi.nlm.nih.gov'
    assert parse_qs(url.query) == {'db':['nuccore'], 'rettype':['gb'], 'retmode':['text'], 'id':['TEST123.1'], 'tool':['VGET']}
    context = next(h._context for h in handlers if hasattr(h, '_context'))
    assert context.verify_mode == ssl.CERT_REQUIRED and context.check_hostname
    assert next(h.proxies for h in handlers if hasattr(h, 'proxies')) == {}


@pytest.mark.parametrize('error,code', [(HTTPError('https://eutils.ncbi.nlm.nih.gov/', 429, 'limited', {'Retry-After':'60'}, None), 'NCBI_RATE_LIMIT'), (URLError('offline'), 'NCBI_NETWORK'), (TimeoutError(), 'NCBI_NETWORK')])
def test_network_errors_have_no_retries(monkeypatch, error, code):
    calls=[]
    class Opener:
        def open(self, *args, **kwargs):calls.append(1);raise error
    monkeypatch.setattr(public, 'build_opener', lambda *args: Opener())
    with pytest.raises(ToolError) as caught:public.fetch_public(public.source_url('TEST123.1'))
    assert caught.value.code == code and len(calls) == 1
    if code == 'NCBI_RATE_LIMIT':assert caught.value.details['retry_after'] == '60'


def test_redirect_is_refused():
    with pytest.raises(ToolError) as error:public._NoRedirect().redirect_request(None,None,302,'redirect',{},'https://other.example/')
    assert error.value.code == 'NCBI_NETWORK'


def test_existing_acquisition_cannot_be_overwritten_or_repaired(kit, monkeypatch):
    raw=fixture(); respond(monkeypatch, raw)
    record=kit.call('library.fetch_ncbi', {'accession':'TEST123.1'})['record']
    state=kit.store.load(); state['records'][record['id']]['description']='Changed locally';kit.store.save(state)
    before=kit.store.path.read_bytes()
    with pytest.raises(ToolError) as error:kit.call('library.fetch_ncbi', {'accession':'TEST123.1'})
    assert error.value.code=='SOURCE_INTEGRITY' and kit.store.path.read_bytes()==before


def test_missing_acquired_original_is_not_silently_repaired(kit, monkeypatch):
    raw=fixture();respond(monkeypatch,raw)
    kit.call('library.fetch_ncbi', {'accession':'TEST123.1'})
    (kit.store.raw/digest(raw)).unlink()
    with pytest.raises(ToolError) as error:kit.call('library.fetch_ncbi', {'accession':'TEST123.1'})
    assert error.value.code=='SOURCE_INTEGRITY'
    assert not (kit.store.raw/digest(raw)).exists()


def test_oversized_dna_record_rejected_atomically(kit, monkeypatch):
    record=SeqRecord(Seq('A'*100001), id='TEST123.1', name='TEST123', description='Synthetic software fixture')
    record.annotations={'molecule_type':'DNA'}
    output=io.StringIO();SeqIO.write(record,output,'genbank');respond(monkeypatch,output.getvalue().encode())
    before=kit.store.path.read_bytes()
    with pytest.raises(ToolError) as error:kit.call('library.fetch_ncbi', {'accession':'TEST123.1'})
    assert error.value.code=='NCBI_INVALID_RESPONSE' and kit.store.path.read_bytes()==before
