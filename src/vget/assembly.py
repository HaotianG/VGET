"""Bounded two-fragment homology prediction, with explicit source-coordinate mapping.

The pinned backend predicts DNA; this adapter never substitutes concatenation on
failure. Exact end homologies are computational conditions, not assay evidence.
"""
from __future__ import annotations
import copy
import importlib.metadata
import json
import re
import subprocess
import sys
from Bio.Seq import Seq
from Bio.SeqFeature import CompoundLocation, SimpleLocation
from .sequence import (SequenceError, _finalize, _hash, _location, _location_text,
                       _name, _require_exact, _require_transformable, _segments)

BACKEND_VERSION = '5.5.8'
MAX_INPUT_BASES = 10000
MAX_GRAPH_NODES = 16
MAX_GRAPH_EDGES = 32


def backend_status():
    try: version = importlib.metadata.version('pydna')
    except importlib.metadata.PackageNotFoundError: version = None
    return {'backend': 'pydna', 'required_version': BACKEND_VERSION, 'installed_version': version,
            'available': version == BACKEND_VERSION, 'scope': 'two prepared linear fragments; exact explicit end homologies; unique circular product'}


def validate_request(records, spec, topology):
    if not isinstance(spec, dict) or set(spec) != {'method', 'overlaps'} or spec['method'] != 'homology':
        raise SequenceError('ASSEMBLY_SPEC', 'Supply assembly={method: homology, overlaps: [backbone_to_insert, insert_to_backbone]}.')
    overlaps = spec['overlaps']
    if not isinstance(overlaps, list) or len(overlaps) != 2 or any(
        not isinstance(s, str) or not re.fullmatch('[ACGT]{20,80}', s) for s in overlaps):
        raise SequenceError('ASSEMBLY_SPEC', 'Two explicit uppercase A/C/G/T overlap sequences of 20–80 bases are required.')
    if len(records) != 2 or records[0]['id'] == records[1]['id']:
        raise SequenceError('ASSEMBLY_INPUTS', 'Select two distinct records in backbone, insert order.')
    if topology != 'circular' or any(r['topology'] != 'linear' for r in records):
        raise SequenceError('ASSEMBLY_TOPOLOGY', 'This operation requires prepared linear inputs and a circular output. No implicit cutting or linearization occurs.')
    if sum(r['length'] for r in records) > MAX_INPUT_BASES:
        raise SequenceError('ASSEMBLY_LIMIT', 'Combined prepared inputs must contain at most 10,000 bases.')
    for r in records:
        _require_transformable(r)
        if set(r['sequence']) - set('ACGT'):
            raise SequenceError('ASSEMBLY_ALPHABET', 'Exact homology prediction requires unambiguous A/C/G/T inputs.')
        if r['length'] <= sum(map(len, overlaps)):
            raise SequenceError('ASSEMBLY_INPUTS', 'Each fragment needs a nonempty interior between its two overlaps.')
    a, b = (r['sequence'] for r in records)
    for index, (left, right, overlap) in enumerate(((a, b, overlaps[0]), (b, a, overlaps[1]))):
        if not left.endswith(overlap) or not right.startswith(overlap):
            raise SequenceError('ASSEMBLY_OVERLAP_MISMATCH', 'A declared overlap does not match both exact fragment ends.', {'junction': index})
        if any(left[-n:] == right[:n] for n in range(len(overlap) + 1, min(len(left), len(right)) + 1)):
            raise SequenceError('ASSEMBLY_OVERLAP_CONFLICT', 'The declared overlap is shorter than a terminal homology; explicitly resolve the junction.', {'junction': index})
        if any(len(list(re.finditer('(?=' + overlap + ')', s))) != 1 for s in (a, b)):
            raise SequenceError('ASSEMBLY_AMBIGUOUS', 'A declared homology occurs at multiple source positions; this bounded operation cannot choose one silently.', {'junction': index})
    if overlaps[0] == overlaps[1] or overlaps[0] == str(Seq(overlaps[1]).reverse_complement()):
        raise SequenceError('ASSEMBLY_AMBIGUOUS', 'The two junction identities do not distinguish the intended orientation.')
    return len(a) + len(b) - sum(map(len, overlaps))


def _predict(sequences):
    status = backend_status()
    if not status['available']:
        code = 'ASSEMBLY_BACKEND_MISSING' if status['installed_version'] is None else 'ASSEMBLY_BACKEND_VERSION'
        raise SequenceError(code, 'Install VGET with the assembly extra and the tested pydna pin.', status)
    try:
        p = subprocess.run([sys.executable, '-m', 'vget.assembly', '--worker'],
            input=json.dumps({'sequences': sequences}), text=True, capture_output=True, timeout=12)
    except subprocess.TimeoutExpired as error:
        raise SequenceError('ASSEMBLY_TIMEOUT', 'The bounded backend prediction timed out; no product was accepted.') from error
    try:
        result = json.loads(p.stdout)
        if not isinstance(result, dict):
            raise SequenceError('ASSEMBLY_BACKEND_FAILED', 'The backend response is not a prediction object.')
        if p.returncode or 'error' in result:
            raise SequenceError(result.get('code', 'ASSEMBLY_BACKEND_FAILED'), 'The backend did not complete a verified prediction.', result.get('error'))
        if not isinstance(result.get('sequences'), list) or any(not isinstance(s,str) or not re.fullmatch('[ACGT]{1,10000}',s) for s in result['sequences']):
            raise SequenceError('ASSEMBLY_BACKEND_FAILED', 'The backend response lacks valid bounded DNA candidates.')
        return result
    except SequenceError:
        raise
    except (ValueError, TypeError) as error:
        raise SequenceError('ASSEMBLY_BACKEND_FAILED', 'The backend returned an unusable response; no fallback product was generated.') from error


def _equivalent(a, b):
    return len(a) == len(b) and (a in b + b or str(Seq(a).reverse_complement()) in b + b)


def _map_location(location, offset, size):
    _require_exact(location)
    parts = []
    for p in location.parts:
        start = (int(p.start) + offset) % size
        end = start + int(p.end) - int(p.start)
        mapped = [SimpleLocation(start, min(end, size), strand=p.strand)]
        if end > size:
            mapped.append(SimpleLocation(0, end - size, strand=p.strand))
            if p.strand == -1: mapped.reverse()
        parts.extend(mapped)
    return parts[0] if len(parts) == 1 else CompoundLocation(parts, operator='join')


def assemble_homology(records, name, spec, topology='circular'):
    _name(name)
    size = validate_request(records, spec, topology)
    a, b = (r['sequence'] for r in records)
    h1, h2 = spec['overlaps']
    prediction = _predict([a, b])
    molecules = []
    for seq in prediction['sequences']:
        if not any(_equivalent(seq, old) for old in molecules): molecules.append(seq)
    if not molecules:
        raise SequenceError('ASSEMBLY_NO_PRODUCT', 'No circular prediction uses both supplied fragments exactly once.')
    if len(molecules) != 1:
        raise SequenceError('ASSEMBLY_AMBIGUOUS', 'The backend predicts multiple circular molecules; no product was selected.', {'unique_products': len(molecules)})
    # Canonical origin is backbone base zero, with the supplied forward orientation.
    seq = molecules[0]
    for candidate in (seq, str(Seq(seq).reverse_complement())):
        index = (candidate + candidate).find(a)
        if 0 <= index < len(candidate):
            seq = (candidate + candidate)[index:index + len(candidate)]; break
    declared = a + b[len(h1):-len(h2)]
    if seq != declared or len(seq) != size:
        raise SequenceError('ASSEMBLY_PATH_CONFLICT', 'The unique backend prediction disagrees with the declared forward junction path.')
    features, references, dbxrefs, mappings = [], [], [], []
    for index, record in enumerate(records):
        offset = 0 if index == 0 else len(a) - len(h1)
        mappings.append({'source_id': record['id'], 'source_length': record['length'], 'offset': offset,
                         'orientation': 1, 'mapping': '(source_position + offset) modulo output_length'})
        for feature in record['features']:
            f = copy.deepcopy(feature)
            mapped = _map_location(_location(f['location'], record['length'], 'linear'), offset, size)
            f.update(location=_location_text(mapped, size), segments=_segments(mapped),
                     id='feat-' + _hash(['homology', index, feature['id'], str(mapped)])[:20],
                     provenance={'source_id': record['id'], 'source_feature_id': feature['id'], 'source_location': feature['location']})
            if feature.get('provenance'):
                key='preparation' if record.get('source',{}).get('kind')=='fragment_preparation' else 'prior_provenance'
                f['provenance'][key]=copy.deepcopy(feature['provenance'])
            features.append(f)
        for ref in copy.deepcopy(record.get('metadata', {}).get('annotations', {}).get('references', [])):
            ref['location'] = [_location_text(_map_location(_location(text, record['length'], 'linear'), offset, size), size) for text in ref.get('location', [])]
            references.append(ref)
        dbxrefs.extend(record.get('metadata', {}).get('dbxrefs', []))
    junctions = [
        {'left_source_id': records[0]['id'], 'right_source_id': records[1]['id'], 'overlap': h1, 'length': len(h1),
         'left_range': [len(a)-len(h1), len(a)], 'right_range': [0, len(h1)], 'output_range': [len(a)-len(h1), len(a)]},
        {'left_source_id': records[1]['id'], 'right_source_id': records[0]['id'], 'overlap': h2, 'length': len(h2),
         'left_range': [len(b)-len(h2), len(b)], 'right_range': [0, len(h2)], 'output_range': [0, len(h2)]}]
    assembly = {'method': 'homology', 'backend': 'pydna', 'backend_version': BACKEND_VERSION,
                'backend_algorithm': 'pydna.assembly.Assembly.assemble_circular',
                'prediction': {k:v for k,v in prediction.items() if k != 'sequences'}, 'coordinate_system': '0-based half-open', 'origin': 'backbone base 0',
                'input_orientations': 'as supplied', 'junctions': junctions, 'fragment_mappings': mappings,
                'unique_circular_products': 1, 'wet_lab_feasibility': 'unevaluated'}
    result = _finalize({'name': name, 'description': 'VGET two-fragment exact-homology prediction; not experimentally validated.',
        'sequence': seq, 'topology': 'circular', 'features': features,
        'metadata': {'record_id': name, 'record_name': name,
            'annotations': {'molecule_type': 'DNA', 'topology': 'circular', 'references': references},
            'dbxrefs': list(dict.fromkeys(dbxrefs)), 'assembly': assembly,
            'source_records': [{'id': r['id'], 'metadata': copy.deepcopy(r.get('metadata', {}))} for r in records]},
        'source': {'kind': 'homology_assembly', 'part_ids': [r['id'] for r in records]}})
    changes = [{'kind': 'homology_junction', 'start': j['output_range'][0], 'end': j['output_range'][1],
                'message': f'Exact {j["length"]}-base terminal homology collapsed to one copy; predicted by pydna {BACKEND_VERSION}.', **j} for j in junctions]
    return result, changes


def _worker():
    """Run the optional backend in a bounded child process, never a service."""
    try:
        from pydna.assembly import Assembly
        from pydna.dseqrecord import Dseqrecord
        values = json.loads(sys.stdin.read(100000))['sequences']
        asm = Assembly([Dseqrecord(s, name=n) for s,n in zip(values, ('backbone', 'insert'))], limit=20)
        nodes, edges = asm.G.number_of_nodes(), asm.G.number_of_edges()
        if nodes > MAX_GRAPH_NODES or edges > MAX_GRAPH_EDGES:
            print(json.dumps({'code': 'ASSEMBLY_LIMIT', 'error': 'Homology graph exceeds the bounded prediction budget.'})); return 2
        products = asm.assemble_circular(length_bound=2)
        selected = [r for r in products if r.graph.number_of_edges() == 2 and
                    {e['name'].removesuffix('_rc') for _,_,e in r.graph.edges(data=True)} == {'backbone', 'insert'}]
        print(json.dumps({'sequences': [str(r.seq).upper() for r in selected], 'graph_nodes': nodes, 'graph_edges': edges,
                          'raw_candidates_using_both_once': len(selected), 'minimum_overlap': 20})); return 0
    except Exception as error:
        print(json.dumps({'code': 'ASSEMBLY_BACKEND_FAILED', 'error': type(error).__name__})); return 2


if __name__ == '__main__':
    if sys.argv[1:] != ['--worker']: raise SystemExit('Internal bounded assembly worker only.')
    raise SystemExit(_worker())
