"""Export a bundled reference unchanged; no network and no biological design claim."""
from pathlib import Path
from vget.toolkit import Toolkit


def main():
    kit = Toolkit(Path.cwd() / '.vget')
    kit.call('workspace.init', {})
    matches = kit.call('library.search', {'query': 'BBa_E0040'})['records']
    record = next(r for r in matches if r['name'] == 'BBa_E0040')
    rid = record['id']
    job = kit.call('job.start', {
        'objective': 'Inspect bundled BBa_E0040 unchanged and explain its annotations; biological suitability is unassessed.'
    })['job']
    decisions = [
        {'field': field, 'value': value, 'origin': 'agent',
         'reason': 'Explicit unchanged-reference demonstration.', 'evidence_refs': [rid]}
        for field, value in [('mode', 'inspect'), ('host_id', None),
                             ('convention_id', None), ('topology', record['topology']),
                             ('name', 'Reference_inspection')]
    ]
    job = kit.call('job.update', {
        'job_id': job['id'], 'expected_revision': job['revision'], 'decisions': decisions,
        'criteria': [{'id': 'original', 'text': 'Retain the original GenBank record unchanged.', 'blocks_export': True}],
        'assumptions': ['This example establishes artifact inspection only, not biological function.']
    })['job']
    job = kit.call('job.plan', {
        'job_id': job['id'], 'expected_revision': job['revision'],
        'plan': {'operation': {'record_id': rid},
                 'summary': 'Inspect the bundled source; preserve its original sequence and annotations.',
                 'selections': [{'record_id': rid, 'reason': 'The exact bundled reference requested by this example.', 'evidence_refs': [rid]}],
                 'alternatives': [],
                 'criteria': [{'id': 'original', 'status': 'satisfied_by_plan',
                               'evaluation': 'Inspect mode checks the stored record against its original GenBank.', 'evidence_refs': [rid]}]}
    })['job']
    result = kit.call('job.run', {'job_id': job['id'], 'plan_hash': job['plan']['sha256']})
    print('Unchanged reference inspection; biological suitability unevaluated.')
    for label in ('genbank', 'html'):
        print(f'{label}: {result["artifacts"][label]}')


if __name__ == '__main__':
    main()
