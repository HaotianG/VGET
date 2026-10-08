"""Computable output requirements, distinct from caller-authored assessments."""
import hashlib
import re
from .contracts import ToolError, CHECK, validate


def validate_criteria(criteria):
    if not isinstance(criteria, list):
        raise ToolError('CRITERION_INVALID', 'Criteria must be a list.')
    for criterion in criteria:
        if not isinstance(criterion, dict):
            raise ToolError('CRITERION_INVALID', 'Each criterion must be an object.')
        if 'check' not in criterion:
            continue
        validate(criterion['check'], CHECK, 'criterion.check')
        if not isinstance(criterion.get('id'), str) or not criterion['id'].strip() or type(criterion.get('blocks_export')) is not bool:
            raise ToolError('CRITERION_INVALID', 'Typed criteria require an ID and explicit blocks_export boolean.')
        kind, value = criterion['check']['kind'], criterion['check']['value']
        okay = (kind == 'length' and type(value) is int and 1 <= value <= 100000 or
                kind == 'feature_count' and type(value) is int and 0 <= value <= 10000 or
                kind == 'sequence_sha256' and isinstance(value, str) and re.fullmatch(r'[0-9a-f]{64}', value) or
                kind == 'topology' and value in ('linear', 'circular', 'unknown'))
        if not okay:
            raise ToolError('CRITERION_INVALID', f'Invalid expected value for {kind}.')


def evaluate_criteria(criteria, record):
    validate_criteria(criteria)
    values = {'length': len(record['sequence']),
              'sequence_sha256': hashlib.sha256(record['sequence'].encode()).hexdigest(),
              'topology': record['topology'], 'feature_count': len(record['features'])}
    checks = []
    for criterion in criteria:
        spec = criterion.get('check')
        if spec is None: continue
        observed = values[spec['kind']]
        passed = observed == spec['value']
        checks.append({'id': 'criterion:' + criterion['id'],
            'status': 'pass' if passed else 'fail' if criterion['blocks_export'] else 'warning',
            'message': f'{spec["kind"]}: expected {spec["value"]}; observed {observed}. Checked on the materialized record.',
            'expected': spec['value'], 'observed': observed, 'blocks_export': criterion['blocks_export'],
            'sequence_sha256': values['sequence_sha256'], 'scope': 'computable output property'})
    return checks
