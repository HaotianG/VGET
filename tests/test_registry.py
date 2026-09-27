"""Real bundled reference records, offline integrity and explicit live-check boundary."""
import copy
import json
from pathlib import Path
import shutil
import pytest
from vget.toolkit import Toolkit, ToolError


def test_default_init_installs_real_bounded_pack_and_is_idempotent(tmp_path):
    kit=Toolkit(tmp_path/'workspace')
    before=kit.call('registry.status',{})
    assert before['bundled_records']==6 and before['installed_records']==0
    result=kit.call('workspace.init',{})
    assert result['records']==6 and result['registry']['installed']==6
    original=kit.store.load()['records']
    assert kit.call('workspace.init',{})['registry']['installed']==0
    assert kit.store.load()['records']==original
    records=kit.call('library.search',{'source':'igem'})['records']
    assert len(records)==6 and all(r['source']['access']=='bundled official public API snapshot' for r in records)
    assert not any(r['source']['kind']=='demo' for r in records)
    assert kit.call('registry.verify',{})['status']=='pass'


def test_registry_search_exposes_source_attribution_and_caveats_without_bases(tmp_path):
    kit=Toolkit(tmp_path/'workspace')
    found=kit.call('registry.search',{'query':'mut3b'})['parts']
    assert len(found)==1 and found[0]['name']=='BBa_E0040'
    assert found[0]['authors']==['Jennifer Braff']
    assert found[0]['license']['spdx_id']=='CC-BY-4.0'
    assert 'sequence' not in found[0] and found[0]['biological_validation']=='unevaluated'
    ambiguous=kit.call('registry.search',{'query':'BBa_E1010'})['parts'][0]
    assert any('CDS' in w for w in ambiguous['warnings'])
    assert not kit.store.load()['records']


def test_empty_and_demo_stay_explicit(tmp_path):
    kit=Toolkit(tmp_path/'empty')
    assert kit.call('workspace.init',{'empty':True})['records']==0
    assert kit.call('workspace.init',{'demo':True})['records']==4
    with pytest.raises(ToolError):kit.call('workspace.init',{'demo':True,'empty':True})


def test_install_subset_unknown_id_and_corrupt_pack_are_atomic(tmp_path,monkeypatch):
    from vget import registry
    kit=Toolkit(tmp_path/'workspace')
    with pytest.raises(ToolError) as e:kit.call('registry.install',{'part_ids':['BBa_E0040','invented']})
    assert e.value.code=='REGISTRY_PART_UNKNOWN' and not kit.store.load()['records']
    result=kit.call('registry.install',{'part_ids':['BBa_E0040']})
    assert result['installed']==1 and result['records'][0]['name']=='BBa_E0040'
    copied=tmp_path/'pack';shutil.copytree(registry.PACK_DIR,copied)
    (copied/'bba-e1010.gb').write_text('damaged')
    monkeypatch.setattr(registry,'PACK_DIR',copied)
    with pytest.raises(ToolError) as e:kit.call('registry.install',{})
    assert e.value.code=='REGISTRY_INTEGRITY' and len(kit.store.load()['records'])==1


def test_installed_record_and_evidence_tampering_detected(tmp_path):
    kit=Toolkit(tmp_path/'workspace');kit.call('workspace.init',{})
    state=kit.store.load();record=next(iter(state['records'].values()))
    record['features'][0]['label']='tampered';kit.store.save(state)
    result=kit.call('registry.verify',{})
    assert result['status']=='fail' and any(c['code']=='RECORD_CHANGED' for c in result['issues'])
    with pytest.raises(ToolError) as e:kit.call('registry.install',{})
    assert e.value.code=='REGISTRY_INSTALLED_CHANGED'


def test_missing_attribution_blob_blocks_export_and_registry_verification(tmp_path):
    from test_inspect import prepare,planned
    kit=Toolkit(tmp_path/'workspace');kit.call('workspace.init',{})
    record=next(iter(kit.store.load()['records'].values()))
    blob=record['source']['evidence_blobs'][0]
    (kit.store.raw/blob['raw_sha256']).write_bytes(b'corrupt')
    assert kit.call('registry.verify',{})['status']=='fail'
    job,plan=prepare(kit,record);job=planned(kit,job,plan)
    with pytest.raises(ToolError) as e:kit.call('job.run',{'job_id':job['id'],'plan_hash':job['plan']['sha256']})
    assert e.value.code=='SOURCE_INTEGRITY'


def test_live_check_is_bounded_read_only_and_structures_network_failures(tmp_path,monkeypatch):
    from vget import registry
    kit=Toolkit(tmp_path/'workspace');kit.call('workspace.init',{})
    original=copy.deepcopy(kit.store.load()['records'])
    def unavailable(url):raise ToolError('REGISTRY_NETWORK','offline')
    monkeypatch.setattr(registry,'fetch_public',unavailable)
    result=kit.call('registry.check_live',{'part_ids':['BBa_E0040']})
    assert result['results'][0]['status']=='error'
    assert result['results'][0]['error']['code']=='REGISTRY_NETWORK'
    assert kit.store.load()['records']==original
    with pytest.raises(ToolError):kit.call('registry.check_live',{'part_ids':['https://arbitrary.example/private']})


def test_live_check_detects_changed_sequence_without_installing_it(tmp_path,monkeypatch):
    from vget import registry
    kit=Toolkit(tmp_path/'workspace');kit.call('workspace.init',{})
    pack=registry.load_pack();part=next(p for p in pack['parts'] if p['name']=='BBa_E0040')
    def fetch(url):
        if url.endswith('.gb'):return (registry.PACK_DIR/part['files']['genbank']['path']).read_bytes()
        data=json.loads((registry.PACK_DIR/part['files']['metadata']['path']).read_bytes())
        data['sequence']='A'+data['sequence'][1:]
        if data['sequence']==json.loads((registry.PACK_DIR/part['files']['metadata']['path']).read_bytes())['sequence']:data['sequence']='C'+data['sequence'][1:]
        return json.dumps(data).encode()
    monkeypatch.setattr(registry,'fetch_public',fetch)
    before=kit.store.load()['records']
    result=kit.call('registry.check_live',{'part_ids':['BBa_E0040']})
    assert result['results'][0]['status']=='inconsistent_upstream'
    assert kit.store.load()['records']==before
