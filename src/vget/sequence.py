"""Local sequence bookkeeping, not assembly or biological compatibility validation."""
from __future__ import annotations

import copy
import hashlib
import io
import json
import re
import warnings

from Bio import SeqIO
from Bio.Seq import Seq
from Bio.SeqFeature import ExactPosition, Location, Reference, SeqFeature, SimpleLocation
from Bio.SeqRecord import SeqRecord
from Bio.SeqIO.InsdcIO import _insdc_location_string

DNA = frozenset('ACGTRYSWKMBDHVN')


class SequenceError(ValueError):
    def __init__(self, code, message, details=None):
        super().__init__(message)
        self.code = code
        self.details = details


def _hash(value):
    if not isinstance(value, str):
        value = json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':'))
    return hashlib.sha256(value.encode()).hexdigest()


def _location_text(location, length):
    if location is None:
        raise SequenceError('invalid_location', 'Feature location could not be parsed; no annotations were discarded.')
    return _insdc_location_string(location, length)


def _location(text, length, topology):
    try:
        loc = Location.fromstring(text, length=length, circular=topology == 'circular')
    except Exception as exc:
        raise SequenceError('invalid_location', f'Cannot parse feature location: {text}', str(exc)) from exc
    if loc is None:
        raise SequenceError('invalid_location', f'Cannot parse feature location: {text}')
    return loc


def _segments(loc):
    return [dict(start=int(part.start), end=int(part.end), strand=part.strand,
                 **({'ref': part.ref} if part.ref else {})) for part in loc.parts]


def _encode_annotation(value, length):
    if isinstance(value, Reference):
        return {'__reference__': True, **{key: copy.deepcopy(getattr(value, key)) for key in
                ('authors', 'consrtm', 'title', 'journal', 'medline_id', 'pubmed_id', 'comment')},
                'location': [_location_text(loc, length) for loc in value.location]}
    if isinstance(value, (list, tuple)):
        return [_encode_annotation(item, length) for item in value]
    if isinstance(value, dict):
        return {key: _encode_annotation(item, length) for key, item in value.items()}
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    raise SequenceError('unsupported_metadata', f'Unsupported metadata type: {type(value).__name__}')


def _decode_annotation(value, length, topology):
    if isinstance(value, dict) and value.get('__reference__'):
        ref = Reference()
        for key, item in value.items():
            if key == 'location':
                ref.location = [_location(text, length, topology) for text in item]
            elif key != '__reference__':
                setattr(ref, key, copy.deepcopy(item))
        return ref
    if isinstance(value, dict):
        return {key: _decode_annotation(item, length, topology) for key, item in value.items()}
    if isinstance(value, list):
        return [_decode_annotation(item, length, topology) for item in value]
    return copy.deepcopy(value)


def _feature_from_bio(feature, length, index):
    loc = feature.location
    result = {'type': feature.type, 'label': next((str(feature.qualifiers[k][0]) for k in
              ('label', 'gene', 'locus_tag', 'product', 'note') if feature.qualifiers.get(k)), feature.type),
              'location': _location_text(loc, length), 'segments': _segments(loc),
              'qualifiers': copy.deepcopy(feature.qualifiers), 'layer': 'imported'}
    result['id'] = 'feat-' + _hash([index, result])[:20]
    return result


def _finalize(record):
    record['sequence'] = record['sequence'].upper()
    record['length'] = len(record['sequence'])
    record['sequence_sha256'] = _hash(record['sequence'])
    record['id'] = 'rec-' + _hash({k: v for k, v in record.items() if k != 'id'})[:24]
    return record


def _check_sequence(sequence):
    if not sequence:
        raise SequenceError('empty_sequence', 'A sequence record cannot be empty.')
    bad = sorted(set(sequence.upper()) - DNA)
    if bad:
        raise SequenceError('invalid_sequence', 'Sequence must contain IUPAC DNA symbols only.', {'invalid_symbols': bad})


def parse_records(text, filename, *, allow_parser_warnings=False):
    if not isinstance(text, str) or not text.strip():
        raise SequenceError('empty_input', 'Input file is empty.')
    if text.lstrip().startswith('>'):
        fmt = 'fasta'
    elif text.lstrip().startswith('LOCUS'):
        fmt = 'genbank'
    else:
        raise SequenceError('unsupported_format', 'Expected GenBank (LOCUS) or FASTA (>) records.')
    if fmt == 'genbank':
        inside = False
        for line in text.splitlines():
            if not inside:
                if not line.strip():
                    continue
                if not line.startswith('LOCUS '):
                    raise SequenceError('malformed_input', 'Unexpected text outside a GenBank record.')
                inside = True
            elif line.strip() == '//':
                inside = False
            elif line.startswith('LOCUS '):
                raise SequenceError('malformed_input', 'A GenBank record is missing its // terminator.')
        if inside:
            raise SequenceError('malformed_input', 'A GenBank record is missing its // terminator.')
    try:
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter('always')
            bio_records = list(SeqIO.parse(io.StringIO(text.lstrip()), fmt))
        if caught and not allow_parser_warnings:
            raise SequenceError('malformed_input', 'Parser reported ambiguous or malformed input; review the original file.',
                                [str(w.message) for w in caught])
        if not bio_records:
            raise SequenceError('empty_input', 'No sequence records were found.')
        original_blocks = [b for b in re.split(r'(?m)(?=^LOCUS )', text.lstrip()) if b.startswith('LOCUS ')] if allow_parser_warnings else []
        result = []
        for bio in bio_records:
            sequence = str(bio.seq).upper()
            _check_sequence(sequence)
            molecule = bio.annotations.get('molecule_type', 'DNA')
            if 'DNA' not in molecule.upper():
                raise SequenceError('unsupported_molecule', 'This prototype accepts DNA records only.')
            record = {'name': bio.name if fmt == 'genbank' else bio.id,
                      'description': bio.description, 'sequence': sequence,
                      'topology': bio.annotations.get('topology', 'unknown'),
                      'features': [_feature_from_bio(f, len(sequence), i) for i, f in enumerate(bio.features)],
                      'metadata': {'record_id': bio.id, 'record_name': bio.name,
                                   'annotations': _encode_annotation(bio.annotations, len(sequence)),
                                   'dbxrefs': list(bio.dbxrefs)},
                      'source': {'kind': 'import', 'filename': str(filename), 'format': fmt}}
            if allow_parser_warnings:
                if fmt != 'genbank':
                    raise SequenceError('inspection_format', 'Inspection-only import requires GenBank originals.')
                record['metadata'].update(inspection_only=True, parser_warnings=[str(w.message) for w in caught])
                block = original_blocks[len(result)]
                expressions = []
                active = False
                qualifier = False
                for line in block.splitlines():
                    if line.startswith('FEATURES'): active = True; continue
                    if active and line and not line.startswith(' '): break
                    if not active: continue
                    if line[5:21].strip():
                        expressions.append(line[21:].strip()); qualifier = False
                    elif line[21:].lstrip().startswith('/'): qualifier = True
                    elif expressions and not qualifier: expressions[-1] += line[21:].strip()
                record['metadata']['original_feature_locations'] = expressions
            record = _finalize(record)
            failures = [c for c in validate_record(record) if c['status'] == 'fail']
            if failures:
                raise SequenceError('invalid_record', 'Imported record failed structural validation.', failures)
            result.append(record)
        return result
    except SequenceError:
        raise
    except Exception as exc:
        raise SequenceError('parse_error', f'Cannot parse {filename}: {exc}') from exc


def to_genbank(record, *, audited_reference_ranges=False):
    failures = [c for c in validate_record(record) if c['status'] == 'fail']
    if failures:
        raise SequenceError('invalid_record', 'Cannot export an invalid record.', failures)
    metadata = record.get('metadata', {})
    bio = SeqRecord(Seq(record['sequence']), id=metadata.get('record_id', record['name']),
                    name=metadata.get('record_name', record['name']), description=record.get('description', ''))
    bio.annotations = _decode_annotation(metadata.get('annotations', {}), record['length'], record['topology'])
    if audited_reference_ranges:
        for reference in bio.annotations.get('references', []):
            # Biopython 1.86 writes only a single reference start/end; a join
            # otherwise becomes its bounding interval, including excluded DNA.
            # Keep exact disjoint citation scopes as remarks plus JSON evidence.
            if len(reference.location)>1 or any(len(loc.parts)>1 for loc in reference.location):
                exact='; '.join(_location_text(loc,record['length']) for loc in reference.location)
                note='VGET exact projected citation ranges (1-based inclusive): '+exact+'. Structured reference range omitted to avoid a misleading bounding interval; see fragment-planning.json and record metadata.'
                reference.comment=(reference.comment+'\n' if reference.comment else '')+note
                reference.location=[]
    bio.annotations['molecule_type'] = 'DNA'
    if record['topology'] == 'unknown':
        bio.annotations.pop('topology', None)
    else:
        bio.annotations['topology'] = record['topology']
    bio.dbxrefs = list(metadata.get('dbxrefs', []))
    bio.features = [SeqFeature(_location(f['location'], record['length'], record['topology']),
                              type=f['type'], qualifiers=copy.deepcopy(f['qualifiers'])) for f in record['features']]
    output = io.StringIO()
    try:
        SeqIO.write(bio, output, 'genbank')
    except Exception as exc:
        raise SequenceError('export_error', f'GenBank export failed: {exc}') from exc
    return output.getvalue()


def validate_record(record):
    checks = []
    def check(identifier, okay, message):
        checks.append({'id': identifier, 'status': 'pass' if okay else 'fail', 'message': message})
    sequence = record.get('sequence', '')
    check('dna_alphabet', isinstance(sequence, str) and bool(sequence) and not (set(sequence.upper()) - DNA), 'Nonempty IUPAC DNA sequence')
    check('length', record.get('length') == len(sequence), 'Recorded length matches sequence')
    check('checksum', record.get('sequence_sha256') == _hash(sequence), 'Sequence checksum matches content')
    if record.get('topology') == 'unknown':
        checks.append({'id': 'topology', 'status': 'unevaluated',
                       'message': 'Source topology is unknown; modification requires an explicit parent topology.'})
    else:
        check('topology', record.get('topology') in ('linear', 'circular'), 'Topology is linear or circular')
    ids = [f.get('id') for f in record.get('features', [])]
    check('feature_ids', all(ids) and len(ids) == len(set(ids)) if ids else True, 'Feature identifiers are present and unique')
    for index, feature in enumerate(record.get('features', [])):
        try:
            loc = _location(feature['location'], len(sequence), record.get('topology'))
            segments = feature['segments']
            okay = segments == _segments(loc)
            check(f'feature_{index}_location', okay, 'Location string and normalized segments agree')
            # Remote positions refer to the remote record, not the imported molecule.
            okay = all(p.ref or 0 <= int(p.start) <= int(p.end) <= len(sequence) for p in loc.parts)
            check(f'feature_{index}_bounds', okay, 'Local feature coordinates are within sequence bounds')
        except (SequenceError, KeyError, TypeError, ValueError):
            check(f'feature_{index}_location', False, 'Feature location is invalid')
    checks.append({'id': 'biological_validation', 'status': 'unevaluated',
                   'message': 'Sequence bookkeeping only; biological function and assembly feasibility are unevaluated.'})
    return checks


def _require_transformable(record):
    if record.get('metadata', {}).get('inspection_only'):
        raise SequenceError('inspection_only_record', 'This record is reserved for exact original inspection; parser interpretations cannot be used for transformations.')
    failures = [c for c in validate_record(record) if c['status'] == 'fail']
    if failures:
        raise SequenceError('invalid_record', 'Input record failed structural validation.', failures)
    for feature in record['features']:
        _require_exact(_location(feature['location'], record['length'], record['topology']))
        unsupported = sorted(k for k in feature.get('qualifiers', {})
                             if k.casefold() in {'transl_except', 'anticodon', 'rpt_unit_range', 'tag_peptide'})
        if unsupported:
            raise SequenceError('unsupported_qualifier_transform', 'Coordinate-bearing qualifiers require a mapping this engine does not implement. Use unchanged inspection or a separately reviewed derivative.',
                                {'feature_id': feature['id'], 'qualifiers': unsupported})


def _require_exact(loc):
    if getattr(loc, 'operator', 'join') != 'join' or any(
            p.ref or p.ref_db or not isinstance(p.start, ExactPosition) or not isinstance(p.end, ExactPosition)
            for p in loc.parts):
        raise SequenceError('unsupported_location', 'Transformations require exact local feature locations using join, not fuzzy, remote, or order locations.')


def _shift_feature(feature, offset, old_length, new_length, topology, salt):
    changed = copy.deepcopy(feature)
    location = _location(feature['location'], old_length, topology)
    _require_exact(location)
    location += offset
    changed['location'] = _location_text(location, new_length)
    changed['segments'] = _segments(location)
    changed['id'] = 'feat-' + _hash([salt, feature['id'], changed['location']])[:20]
    return changed


def _name(name):
    if not isinstance(name, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,47}', name):
        raise SequenceError('invalid_name', 'Name must be 1–48 letters, numbers, dots, underscores or hyphens, starting with a letter or number.')
    return name


def _reference_offsets(metadata, old_length, topology, offset, new_length):
    refs = copy.deepcopy(metadata.get('annotations', {}).get('references', []))
    for ref in refs:
        mapped = []
        for text in ref.get('location', []):
            loc = _location(text, old_length, topology)
            _require_exact(loc)
            mapped.append(_location_text(loc + offset, new_length))
        ref['location'] = mapped
    return refs


def compose(records, name, topology='circular'):
    _name(name)
    if not records:
        raise SequenceError('missing_parts', 'Select at least one source record.')
    if topology not in ('circular', 'linear'):
        raise SequenceError('invalid_topology', 'Topology must be circular or linear.')
    for record in records:
        _require_transformable(record)
    sequence = ''.join(record['sequence'] for record in records)
    features, changes, references, dbxrefs = [], [], [], []
    offset = 0
    for index, record in enumerate(records):
        features.extend(_shift_feature(f, offset, record['length'], len(sequence), record['topology'], ['compose', index]) for f in record['features'])
        references.extend(_reference_offsets(record.get('metadata', {}), record['length'], record['topology'], offset, len(sequence)))
        dbxrefs.extend(record.get('metadata', {}).get('dbxrefs', []))
        changes.append({'kind': 'append', 'source_id': record['id'], 'start': offset, 'end': offset + record['length'],
                        'message': f'Appended {record["name"]} as supplied; assembly feasibility unevaluated.'})
        offset += record['length']
    return _finalize({'name': name, 'description': 'VGET local sequence composition; not experimentally validated.',
                      'sequence': sequence, 'topology': topology, 'features': features,
                      'metadata': {'record_id': name, 'record_name': name,
                                   'annotations': {'molecule_type': 'DNA', 'topology': topology, 'references': references},
                                   'dbxrefs': list(dict.fromkeys(dbxrefs)),
                                   'source_records': [{'id': r['id'], 'metadata': copy.deepcopy(r.get('metadata', {}))} for r in records]},
                      'source': {'kind': 'composition', 'part_ids': [r['id'] for r in records]}}), changes


def replace_feature(parent, feature_id, replacement, name, protected_feature_ids=None):
    _name(name)
    if parent.get('topology') not in ('linear', 'circular'):
        raise SequenceError('unknown_topology', 'Modification requires an explicit parent topology (linear or circular).')
    _require_transformable(parent)
    _require_transformable(replacement)
    protected = set(protected_feature_ids or [])
    ids = {f['id'] for f in parent['features']}
    if not protected <= ids:
        raise SequenceError('unknown_protection', 'A protected feature identifier does not exist.', sorted(protected - ids))
    candidates = [f for f in parent['features'] if f['id'] == feature_id]
    if len(candidates) != 1:
        raise SequenceError('unknown_target', 'Select a unique existing target feature.')
    target = candidates[0]
    if len(target['segments']) != 1:
        raise SequenceError('compound_target', 'Replacement requires a single contiguous exact target span; origin-spanning and compound targets are unsupported.')
    start, end = target['segments'][0]['start'], target['segments'][0]['end']
    if start == end:
        raise SequenceError('empty_target', 'Replacement requires a nonempty target feature.')
    if feature_id in protected:
        raise SequenceError('protected_feature', 'The selected target feature is protected.')
    for f in parent['features']:
        if f['id'] == feature_id:
            continue
        if any(p['start'] < end and p['end'] > start or p['start'] == p['end'] and start < p['start'] < end for p in f['segments']):
            raise SequenceError('protected_feature' if f['id'] in protected else 'annotation_intersection',
                                'Replacement would intersect ' + ('a protected feature.' if f['id'] in protected else 'another parent annotation.'), {'feature_id': f['id'], 'label': f['label']})
    delta = replacement['length'] - (end - start)
    sequence = parent['sequence'][:start] + replacement['sequence'] + parent['sequence'][end:]
    result = copy.deepcopy(parent)
    result.update(name=name, description=f'VGET exact-span edit of {parent["name"]}; not experimentally validated.', sequence=sequence)
    features = []
    for f in parent['features']:
        if f['id'] == feature_id:
            features.extend(_shift_feature(g, start, replacement['length'], len(sequence), replacement['topology'], ['replacement', parent['id']]) for g in replacement['features'])
            continue
        changed = copy.deepcopy(f)
        loc = _location(f['location'], parent['length'], parent['topology'])
        # Shift each compound segment independently; a split feature may straddle the edit without intersecting it.
        parts = [p + (delta if int(p.start) >= end else 0) for p in loc.parts]
        newloc = parts[0] if len(parts) == 1 else type(loc)(parts, operator=loc.operator)
        changed['location'] = _location_text(newloc, len(sequence))
        changed['segments'] = _segments(newloc)
        features.append(changed)
    result['features'] = features
    metadata = result.setdefault('metadata', {})
    metadata['record_id'] = metadata['record_name'] = name
    metadata['source_records'] = [{'id': r['id'], 'metadata': copy.deepcopy(r.get('metadata', {}))} for r in (parent, replacement)]
    # The edited molecule gets a local identity; original accession/version remain in source_records.
    metadata.setdefault('annotations', {})['accessions'] = [name]
    metadata['annotations'].pop('sequence_version', None)
    metadata['annotations'].pop('gi', None)
    # Bibliographic ranges spanning the edit retain their citation and have mapped boundaries.
    for ref in metadata.get('annotations', {}).get('references', []):
        mapped = []
        for text in ref.get('location', []):
            loc = _location(text, parent['length'], parent['topology'])
            _require_exact(loc)
            parts = []
            for part in loc.parts:
                a, b = int(part.start), int(part.end)
                new_a = a if a <= start else a + delta if a >= end else start
                new_b = b if b <= start else b + delta if b >= end else start + replacement['length']
                parts.append(SimpleLocation(new_a, new_b, strand=part.strand))
            mapped.append(_location_text(parts[0] if len(parts) == 1 else type(loc)(parts, operator=loc.operator), len(sequence)))
        ref['location'] = mapped
    metadata.setdefault('annotations', {}).setdefault('references', []).extend(
        _reference_offsets(replacement.get('metadata', {}), replacement['length'], replacement['topology'], start, len(sequence)))
    result['source'] = {'kind': 'replacement', 'parent_id': parent['id'], 'replacement_id': replacement['id'], 'target_feature_id': feature_id}
    changes = [{'kind': 'replace', 'feature_id': feature_id, 'start': start, 'end': end,
                'replacement_length': replacement['length'], 'length_delta': delta,
                'same_sequence': sequence == parent['sequence'],
                'message': 'Replaced the target span with the source sequence as supplied; source strand is not automatically reversed.'}]
    result = _finalize(result)
    failures = [c for c in validate_record(result) if c['status'] == 'fail']
    if failures:
        raise SequenceError('invalid_result', 'Edit failed structural validation.', failures)
    return result, changes


def compare_records(left, right):
    a, b = left['sequence'].upper(), right['sequence'].upper()
    same = a == b
    circular = left.get('topology') == right.get('topology') == 'circular'
    equivalent = bool(a) and circular and len(a) == len(b) and (b in a + a or str(Seq(b).reverse_complement()) in a + a)
    def annotations(record):
        return [{key: f.get(key) for key in ('type', 'location', 'qualifiers')} for f in record.get('features', [])]
    return {'same_sequence': same, 'same_circular_molecule': bool(equivalent),
            'length_delta': len(b) - len(a),
            'same_annotations': annotations(left) == annotations(right),
            'summary': 'Sequences are identical.' if same else 'Circular molecules are equivalent after origin/strand normalization.' if equivalent else 'Sequences differ.',
            'limitations': ['Circular equivalence compares literal IUPAC symbols; annotations and biological function are evaluated separately.']}
