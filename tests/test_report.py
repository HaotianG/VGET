"""Report/export checks use only short, arbitrary software fixtures."""
import base64
import copy
import hashlib
import json
import re
import unittest
from html.parser import HTMLParser

from vget.report import package_files, render_report


class Tags(HTMLParser):
    def __init__(self):
        super().__init__()
        self.tags = []
    def handle_starttag(self, tag, attrs):
        self.tags.append((tag, dict(attrs)))


def fixture(topology='circular'):
    sequence = 'ACGT' * 5
    return {
        'id': 'design-1', 'name': 'Fixture', 'created_at': '2026-09-21',
        'mode': 'create', 'host_id': 'demo', 'host_name': 'Unvalidated profile',
        'objective': 'Software demonstration only.', 'parent_id': None,
        'part_ids': ['input-1'], 'convention_id': None, 'assumptions': ['Fixture assumption'],
        'checks': [{'id': s, 'status': s, 'message': s + ' result'} for s in
                   ['pass', 'fail', 'warning', 'unevaluated', 'unsupported', 'unknown']],
        'changes': [{'kind': 'compose', 'source_id': 'input-1'}],
        'status': 'computationally_checked',
        'record': {'id': 'record-1', 'name': 'Fixture', 'sequence': sequence,
            'length': len(sequence), 'sequence_sha256': hashlib.sha256(sequence.encode()).hexdigest(),
            'topology': topology, 'description': 'Arbitrary software fixture',
            'metadata': {}, 'source': {'kind': 'demo'},
            'features': [{'id': 'x', 'type': 'misc_feature', 'label': 'Compound fixture',
                'location': 'complement(join(2..5,15..18))', 'layer': 'source',
                'segments': [{'start': 1, 'end': 5, 'strand': -1}, {'start': 14, 'end': 18, 'strand': -1}],
                'qualifiers': {'note': ['first', 'second']}, 'provenance': {'record_id': 'input-1'}}]},
    }


GBK = 'LOCUS       Fixture 20 bp DNA circular\nCOMMENT     Software fixture: µ\n//\n'


class VisibleText(HTMLParser):
    """Only text outside collapsed details, scripts, and styles."""
    def __init__(self):
        super().__init__(); self.depth = 0; self.text = []
    def handle_starttag(self, tag, attrs):
        if tag in ('details', 'style', 'script'): self.depth += 1
    def handle_endtag(self, tag):
        if tag in ('details', 'style', 'script'): self.depth -= 1
    def handle_data(self, data):
        if self.depth == 0: self.text.append(data)


def agent_context():
    return {
        'summary': 'Interpret the objective as a synthetic software demonstration.',
        'criteria': [{'id': 'C1', 'text': 'Preserve the supplied label.',
                      'evaluation': 'The chosen record carries that label.',
                      'status': 'agent_assessed', 'evidence_refs': ['record:input-1']}],
        'decisions': [{'field': 'topology', 'value': 'circular', 'origin': 'user',
                       'reason': 'The user supplied the topology.'},
                      {'field': 'display name', 'value': 'Fixture', 'origin': 'agent',
                       'reason': 'A temporary name for review.'}],
        'selections': [{'record_id': 'input-1', 'reason': 'It matches the requested fixture label.',
                        'evidence_refs': ['record:input-1']}],
        'alternatives': [{'record_id': 'input-2', 'reason': 'It has a different label.'}],
        'assumptions': [{'text': 'The labels express the intended demonstration.',
                         'origin': 'agent', 'reason': 'No additional user preference was supplied.'}],
        'questions': [{'text': 'Is the display name acceptable?', 'status': 'open',
                       'reason': 'It has not been confirmed by the user.'}],
        'job_id': 'job-1', 'revision': 3, 'plan_hash': 'abc123',
        'debug_only': 'raw-context-sentinel',
    }


class ReportTests(unittest.TestCase):
    def test_agent_rationale_is_human_readable_and_assessments_are_distinct(self):
        d = fixture(); d['agent_context'] = agent_context()
        text = render_report(d, GBK)
        visible = VisibleText(); visible.feed(text)
        readable = ' '.join(visible.text)
        for expected in ['Objective interpretation', 'Requirement assessments', 'Decisions and origins',
                         'Selected records', 'Alternatives considered', 'Agent assumptions',
                         'Unresolved questions', 'job-1', 'abc123',
                         'Preserve the supplied label.', 'The chosen record carries that label.',
                         'agent_assessed', 'record:input-1', 'The user supplied the topology.',
                         'A temporary name for review.', 'It has a different label.',
                         'The labels express the intended demonstration.',
                         'Is the display name acceptable?', 'not been confirmed',
                         'Agent assessments are separate from computational checks',
                         'Evidence references are identifiers', 'experimental evidence']:
            self.assertIn(expected, readable)
        self.assertNotIn('raw-context-sentinel', readable)
        self.assertIn('<details><summary>Full agent context</summary>', text)
        self.assertIn('raw-context-sentinel', text)

    def test_agent_context_is_escaped_and_cannot_add_remote_assets(self):
        d = fixture(); context = agent_context()
        malicious = '\"><script>alert(1)</script><img src=https://evil.invalid onerror=alert(2)>'
        context['summary'] = context['job_id'] = context['plan_hash'] = malicious
        for group in ('criteria', 'decisions', 'selections', 'alternatives', 'assumptions', 'questions'):
            for item in context[group]:
                for key in item:
                    item[key] = [malicious] if key == 'evidence_refs' else malicious
        d['agent_context'] = context
        text = render_report(d, GBK)
        p = Tags(); p.feed(text)
        self.assertFalse(any(tag in ('script', 'img', 'iframe') for tag, _ in p.tags))
        self.assertTrue(all(not k.startswith('on') for _, attrs in p.tags for k in attrs))
        self.assertTrue(all(attrs['href'].startswith(('#', 'data:'))
                            for _, attrs in p.tags if 'href' in attrs))
        self.assertIn('&lt;script&gt;', text)

    def test_agent_context_is_preserved_and_hashed_as_an_independent_payload(self):
        d = fixture(); d['agent_context'] = agent_context()
        before = copy.deepcopy(d)
        files = package_files(d, GBK, [], {})
        self.assertEqual(json.loads(files['agent-context.json']), d['agent_context'])
        manifest = json.loads(files['manifest.json'])
        self.assertEqual({item['path'] for item in manifest['files']}, set(files) - {'manifest.json'})
        for item in manifest['files']:
            self.assertEqual(item['sha256'], hashlib.sha256(files[item['path']]).hexdigest())
            self.assertEqual(item['bytes'], len(files[item['path']]))
        self.assertEqual(d, before)
        self.assertEqual(files, package_files(d, GBK, [], {}))
        legacy = package_files(fixture(), GBK, [], {})
        self.assertNotIn('agent-context.json', legacy)
        self.assertNotIn('Objective interpretation', legacy['report.html'].decode())

    def test_empty_context_and_plain_assumptions_do_not_invent_assessments(self):
        d = fixture(); d['agent_context'] = {'assumptions': ['A plain assumption'],
                                           'questions': ['A plain question?']}
        text = render_report(d, GBK)
        visible = VisibleText(); visible.feed(text)
        readable = ' '.join(visible.text)
        self.assertIn('A plain assumption', readable)
        self.assertIn('A plain question?', readable)
        self.assertIn('No requirement assessments were supplied.', readable)
        self.assertIn('No alternatives were recorded.', readable)

    def test_user_text_never_becomes_markup(self):
        d = fixture()
        malicious = '\"><script>alert(1)</script><img src=https://evil.invalid onerror=alert(2)>'
        d['name'] = d['objective'] = d['host_name'] = malicious
        d['record']['features'][0].update(id=malicious, label=malicious)
        d['record']['features'][0]['qualifiers'] = {'note': [malicious]}
        text = render_report(d, GBK)
        p = Tags(); p.feed(text)
        self.assertFalse(any(tag in ('script', 'img', 'iframe') for tag, _ in p.tags))
        self.assertIn('&lt;script&gt;', text)
        self.assertTrue(all(not k.startswith('on') for _, attrs in p.tags for k in attrs))
        for _, attrs in p.tags:
            if 'href' in attrs:
                self.assertTrue(attrs['href'].startswith(('#', 'data:')))
        self.assertIn('id="feature-0"', text)

    def test_download_is_exact_utf8_genbank(self):
        text = render_report(fixture(), GBK)
        p = Tags(); p.feed(text)
        link = next(attrs for tag, attrs in p.tags if tag == 'a' and attrs.get('download') == 'construct.gbk')
        self.assertEqual(base64.b64decode(link['href'].split(',', 1)[1]), GBK.encode('utf-8'))

    def test_compound_segments_and_direction_remain_explicit(self):
        for topology in ['linear', 'circular']:
            with self.subTest(topology=topology):
                text = render_report(fixture(topology), GBK)
                p = Tags(); p.feed(text)
                segments = [a for _, a in p.tags if 'data-start' in a]
                self.assertEqual([(a['data-start'], a['data-end'], a['data-strand']) for a in segments],
                                 [('1', '5', '-1'), ('14', '18', '-1')])
                self.assertIn('2–5', text)
                self.assertIn('15–18', text)
                self.assertIn('complement(join(2..5,15..18))', text)
                self.assertIn('second', text)
                self.assertIn('input-1', text)

    def test_statuses_and_limits_are_explicit(self):
        text = render_report(fixture(), GBK)
        for status in ['pass', 'fail', 'warning', 'unevaluated', 'unsupported', 'unknown']:
            self.assertIn(status + ' result', text)
        self.assertIn('laboratory assembly', text)
        self.assertIn('unevaluated', text)
        self.assertIn('sequence composition', text)
        self.assertIn('default-src', text)
        self.assertNotIn('https://', text)

    def test_bundle_manifest_and_immutable_inputs(self):
        d = fixture(); sources = [copy.deepcopy(d['record'])]
        originals = {'../../private.txt': b'original bytes\x00\xff', 'a/b.fa': b'other original'}
        before = copy.deepcopy((d, sources, originals))
        files = package_files(d, GBK, sources, originals)
        self.assertEqual((d, sources, originals), before)
        required = {'construct.gbk', 'report.html', 'design.json', 'features.json', 'changes.json',
                    'validation.json', 'evidence.json', 'source-records.json', 'manifest.json'}
        self.assertTrue(required <= set(files))
        manifest = json.loads(files['manifest.json'])
        self.assertEqual({item['path'] for item in manifest['files']}, set(files) - {'manifest.json'})
        for item in manifest['files']:
            self.assertEqual(item['sha256'], hashlib.sha256(files[item['path']]).hexdigest())
            self.assertEqual(item['bytes'], len(files[item['path']]))
        self.assertEqual(files['construct.gbk'], GBK.encode())
        self.assertEqual(json.loads(files['source-records.json']), sources)
        self.assertEqual(sorted(v for k, v in files.items() if k.startswith('sources/')), sorted(originals.values()))
        self.assertTrue(all('..' not in path and not path.startswith('/') for path in files))
        self.assertEqual(files, package_files(d, GBK, sources, originals))

    def test_changes_and_provenance_are_readable_with_collapsed_raw_evidence(self):
        class VisibleText(HTMLParser):
            def __init__(self):
                super().__init__(); self.depth = 0; self.text = []
            def handle_starttag(self, tag, attrs):
                if tag == 'details': self.depth += 1
            def handle_endtag(self, tag):
                if tag == 'details': self.depth -= 1
            def handle_data(self, data):
                if self.depth == 0: self.text.append(data)
        d = fixture()
        d['parent_id'] = 'parent-fixture'
        d['changes'] = [{'kind': 'replace', 'start': 2, 'end': 8, 'length_delta': -2,
                         'message': 'Replaced the selected span.', 'raw_only': 'change-sentinel'}]
        d['record']['metadata'] = {'raw_only': 'metadata-sentinel'}
        text = render_report(d, GBK)
        visible = VisibleText(); visible.feed(text)
        readable = ' '.join(visible.text)
        for expected in ['Replaced the selected span.', '3–8', '−2 bp', 'input-1',
                         'parent-fixture', 'Fixture assumption', 'unevaluated result']:
            self.assertIn(expected, readable)
        self.assertNotIn('change-sentinel', readable)
        self.assertNotIn('metadata-sentinel', readable)
        self.assertIn('change-sentinel', text)
        self.assertIn('metadata-sentinel', text)
        self.assertIn('<details><summary>Full change record</summary>', text)
        self.assertIn('<details><summary>Full provenance &amp; evidence</summary>', text)

    def test_empty_features_and_sequence_and_unknown_status(self):
        d = fixture(); d['record'].update(sequence='', length=0, features=[])
        d['status'] = '<unexpected>'
        text = render_report(d, GBK)
        self.assertIn('No annotated features', text)
        self.assertIn('&lt;unexpected&gt;', text)
        self.assertNotIn('NaN', text)


if __name__ == '__main__':
    unittest.main()
