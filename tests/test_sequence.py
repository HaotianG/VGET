"""Synthetic, nonfunctional DNA fixtures; expected coordinates are hand-calculated."""
import copy
import io

import pytest
from Bio import SeqIO
from Bio.Seq import Seq
from Bio.SeqFeature import SeqFeature, SimpleLocation, CompoundLocation, BeforePosition, Reference
from Bio.SeqRecord import SeqRecord

from vget.sequence import (SequenceError, parse_records, to_genbank, compose,
                           replace_feature, validate_record, compare_records)


def gb(sequence='AACCGGTTAACC', features=(), circular=False):
    record = SeqRecord(Seq(sequence), id='SYNTH001.1', name='fixture', description='Synthetic nonfunctional fixture')
    record.annotations = {'molecule_type': 'DNA', 'topology': 'circular' if circular else 'linear',
                          'accessions': ['SYNTH001'], 'sequence_version': 1,
                          'keywords': ['synthetic test'], 'source': 'synthetic construct',
                          'organism': 'synthetic construct', 'taxonomy': ['other sequences'],
                          'comment': 'Preserve this provenance.'}
    ref = Reference()
    ref.authors = 'Example,A.'
    ref.title = 'Synthetic fixture citation'
    ref.journal = 'Unpublished'
    ref.location = [SimpleLocation(0, len(sequence))]
    record.annotations['references'] = [ref]
    record.dbxrefs = ['BioProject:TESTONLY']
    record.features = list(features)
    output = io.StringIO()
    SeqIO.write(record, output, 'genbank')
    return output.getvalue()


def feature(start, end, label, strand=1):
    return SeqFeature(SimpleLocation(start, end, strand=strand), type='misc_feature',
                      qualifiers={'label': [label], 'note': ['line one', 'another note'], 'custom': ['retain me']})


def parsed(features=(), circular=False):
    return parse_records(gb(features=features, circular=circular), 'fixture.gbk')[0]


def test_import_multi_record_and_roundtrip_preserves_semantics():
    complex_feature = SeqFeature(CompoundLocation([SimpleLocation(8, 12, -1), SimpleLocation(0, 2, -1)]),
                                 type='misc_feature', qualifiers={'label': ['split reverse'], 'note': ['kept']})
    text = gb(features=[feature(2, 5, 'simple'), complex_feature], circular=True)
    records = parse_records(text + gb('CCAA'), 'many.gb')
    assert len(records) == 2
    first = records[0]
    assert first['length'] == 12 and first['topology'] == 'circular'
    assert first['features'][1]['segments'] == [{'start': 8, 'end': 12, 'strand': -1}, {'start': 0, 'end': 2, 'strand': -1}]
    assert first['id'] == parse_records(text, 'many.gb')[0]['id']
    rewritten = SeqIO.read(io.StringIO(to_genbank(first)), 'genbank')
    original = SeqIO.read(io.StringIO(text), 'genbank')
    assert rewritten.annotations == original.annotations
    assert rewritten.dbxrefs == original.dbxrefs
    assert rewritten.id == original.id
    assert [str(f.location) for f in rewritten.features] == [str(f.location) for f in original.features]
    assert [f.qualifiers for f in rewritten.features] == [f.qualifiers for f in original.features]


def test_compose_offsets_negative_compound_features_and_is_immutable():
    first = parsed([feature(2, 4, 'first')])
    second = parse_records(gb('CCAA', [SeqFeature(CompoundLocation([SimpleLocation(0, 1, -1), SimpleLocation(2, 4, -1)]), type='misc_feature')]), 'second.gb')[0]
    before = copy.deepcopy([first, second])
    result, changes = compose([first, second], 'assembled', 'circular')
    assert result['sequence'] == 'AACCGGTTAACCCCAA'
    assert result['features'][1]['segments'] == [{'start': 12, 'end': 13, 'strand': -1}, {'start': 14, 'end': 16, 'strand': -1}]
    assert len({f['id'] for f in result['features']}) == len(result['features'])
    assert result['topology'] == 'circular' and changes
    assert [first, second] == before
    assert all(check['status'] != 'fail' for check in validate_record(result))
    assert str(SeqIO.read(io.StringIO(to_genbank(result)), 'genbank').seq) == result['sequence']


def test_replace_exact_region_maps_other_features_and_replacement_annotations():
    parent = parsed([feature(0, 2, 'left'), feature(4, 8, 'target', -1), feature(10, 12, 'right')])
    repl = parse_records(gb('TT', [feature(0, 2, 'insert', -1)]), 'replacement.gb')[0]
    before = copy.deepcopy([parent, repl])
    result, changes = replace_feature(parent, parent['features'][1]['id'], repl, 'edited', [parent['features'][0]['id']])
    assert result['sequence'] == 'AACCTTAACC'
    assert [(f['label'], f['segments']) for f in result['features']] == [
        ('left', [{'start': 0, 'end': 2, 'strand': 1}]),
        ('insert', [{'start': 4, 'end': 6, 'strand': -1}]),
        ('right', [{'start': 8, 'end': 10, 'strand': 1}])]
    assert result['features'][2]['qualifiers'] == parent['features'][2]['qualifiers']
    assert result['metadata']['annotations']['comment'] == parent['metadata']['annotations']['comment']
    assert [parent, repl] == before
    assert changes and all(c['status'] != 'fail' for c in validate_record(result))


def test_replacement_noop_and_rejections():
    parent = parsed([feature(4, 8, 'target')])
    replacement = parse_records('>same\nGGTT\n', 'same.fasta')[0]
    result, changes = replace_feature(parent, parent['features'][0]['id'], replacement, 'noop')
    assert result['sequence'] == parent['sequence']
    assert compare_records(parent, result)['same_sequence'] is True
    with pytest.raises(SequenceError, match='protected'):
        replace_feature(parent, parent['features'][0]['id'], replacement, 'x', [parent['features'][0]['id']])
    intersecting = parsed([feature(4, 8, 'target'), feature(6, 9, 'overlap')])
    with pytest.raises(SequenceError, match='intersect'):
        replace_feature(intersecting, intersecting['features'][0]['id'], replacement, 'x')
    with pytest.raises(SequenceError):
        replace_feature(parent, 'missing', replacement, 'x')
    with pytest.raises(SequenceError):
        replace_feature(parent, parent['features'][0]['id'], replacement, 'x', ['missing'])


@pytest.mark.parametrize('location', [SimpleLocation(BeforePosition(2), 4),
    SimpleLocation(2, 4, ref='REMOTE.1'),
    CompoundLocation([SimpleLocation(0, 2), SimpleLocation(4, 6)], operator='order')])
def test_unsupported_location_roundtrip_but_transform_fails(location):
    source = parsed([SeqFeature(location, type='misc_feature')])
    original = SeqIO.read(io.StringIO(gb(features=[SeqFeature(location, type='misc_feature')])), 'genbank')
    assert str(SeqIO.read(io.StringIO(to_genbank(source)), 'genbank').features[0].location) == str(original.features[0].location)
    with pytest.raises(SequenceError, match='location'):
        compose([source], 'unsupported')


def test_compound_target_rejected_without_loss():
    parent = parsed([SeqFeature(CompoundLocation([SimpleLocation(8, 12, 1), SimpleLocation(0, 2, 1)]), type='misc_feature')], True)
    replacement = parse_records('>r\nTT\n', 'r.fa')[0]
    with pytest.raises(SequenceError, match='single'):
        replace_feature(parent, parent['features'][0]['id'], replacement, 'x')


def test_compare_origin_rotation_reverse_complement_and_linear():
    a = parse_records('>a\nAACCGT\n', 'a.fa')[0]
    b = parse_records('>b\nCGTAAC\n', 'b.fa')[0]
    a['topology'] = b['topology'] = 'circular'
    assert compare_records(a, b)['same_circular_molecule'] is True
    b['sequence'] = 'ACGGTT'
    assert compare_records(a, b)['same_circular_molecule'] is True
    b['topology'] = 'linear'
    assert compare_records(a, b)['same_circular_molecule'] is False


@pytest.mark.parametrize('text,filename', [('', 'empty.fa'), ('garbage', 'bad.gb'),
    ('>bad\nACGT*\n', 'bad.fa'), ('>empty\n', 'empty.fa'), ('LOCUS       broken\n//\n', 'bad.gb')])
def test_malformed_input_rejected(text, filename):
    with pytest.raises(SequenceError):
        parse_records(text, filename)


def test_validation_detects_stale_length_checksum_and_bounds():
    record = parsed([feature(0, 2, 'one')])
    record['sequence'] = 'TT'
    record['features'][0]['segments'][0]['end'] = 999
    assert sum(c['status'] == 'fail' for c in validate_record(record)) >= 3


def test_repeat_parts_get_distinct_feature_ids():
    source = parsed([feature(1, 3, 'one')])
    composed, _ = compose([source, source], 'repeat')
    assert len(set(f['id'] for f in composed['features'])) == 2


def test_genbank_trailing_junk_and_missing_terminator_rejected():
    for text in (gb() + 'UNPARSED DATA\n', gb().replace('//\n', '')):
        with pytest.raises(SequenceError):
            parse_records(text, 'bad.gb')


def test_compound_feature_straddling_edit_maps_segments_independently():
    split = SeqFeature(CompoundLocation([SimpleLocation(0, 2, -1), SimpleLocation(10, 12, -1)]), type='misc_feature')
    parent = parsed([feature(4, 8, 'target'), split])
    replacement = parse_records('>r\nTT\n', 'r.fa')[0]
    result, _ = replace_feature(parent, parent['features'][0]['id'], replacement, 'split_edit')
    assert result['features'][0]['segments'] == [{'start': 0, 'end': 2, 'strand': -1}, {'start': 8, 'end': 10, 'strand': -1}]
    exported = parse_records(to_genbank(result), 'edited.gb')[0]
    assert exported['metadata']['record_id'] == 'split_edit'
    assert result['metadata']['annotations'].get('accessions') == ['split_edit']
    assert 'sequence_version' not in result['metadata']['annotations']
    assert result['metadata']['source_records'][0]['metadata']['annotations']['accessions'] == ['SYNTH001']


def test_compare_annotations_ignores_local_identity_but_detects_qualifier_change():
    left = parsed([feature(0, 2, 'one')])
    right = copy.deepcopy(left)
    right['features'][0]['id'] = 'some-local-id'
    assert compare_records(left, right)['same_annotations'] is True
    right['features'][0]['qualifiers']['note'] = ['changed']
    assert compare_records(left, right)['same_annotations'] is False


def test_missing_topology_is_explicitly_unknown_and_export_does_not_invent_it():
    fasta = parse_records('>unknown\nAACCGG\n', 'unknown.fa')[0]
    assert fasta['topology'] == 'unknown'
    topology_check = next(c for c in validate_record(fasta) if c['id'] == 'topology')
    assert topology_check['status'] == 'unevaluated'
    exported = SeqIO.read(io.StringIO(to_genbank(fasta)), 'genbank')
    assert 'topology' not in exported.annotations
    assert parse_records(to_genbank(fasta), 'unknown.gb')[0]['topology'] == 'unknown'
    composed, _ = compose([fasta], 'known_result', 'circular')
    assert composed['topology'] == 'circular'


def test_replacement_requires_explicit_parent_topology():
    parent = parsed([feature(2, 4, 'target')])
    parent['topology'] = 'unknown'
    parent['metadata']['annotations'].pop('topology', None)
    replacement = parse_records('>r\nTT\n', 'r.fa')[0]
    with pytest.raises(SequenceError, match='topology'):
        replace_feature(parent, parent['features'][0]['id'], replacement, 'edited')
