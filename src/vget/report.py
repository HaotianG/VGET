"""Self-contained, escaped reports and reproducible export packages.

This module presents computational records; it does not infer biological function,
validate assembly methods, or make laboratory recommendations. No network I/O.
"""
from __future__ import annotations

import base64
import hashlib
import html
import json
import math


_COLORS = ('#167b78', '#aa7833', '#6b65a3', '#a25870', '#3c8097', '#6b8245', '#8c6455', '#53668d')
_LIMITS = (
    'This local prototype reports exact sequence composition and annotation transformations only.',
    'Host compatibility, biological function, expression, and laboratory assembly feasibility are unevaluated.',
    'A computational pass does not establish experimental success or authorize laboratory use.',
    'Source provenance describes supplied records; it does not independently authenticate their scientific claims.',
)


def _e(value) -> str:
    return html.escape(str(value if value is not None else 'Not specified'), quote=True)


def _dump(value) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False) + '\n').encode('utf-8')


def _pre(value) -> str:
    return '<pre>' + _e(_dump(value).decode().rstrip()) + '</pre>'


def _badge(status) -> str:
    styles = {'pass': 'pass', 'passed': 'pass', 'fail': 'fail', 'failed': 'fail',
              'warning': 'warn', 'warn': 'warn', 'unevaluated': 'neutral',
              'unsupported': 'warn', 'unknown': 'neutral'}
    return '<span class="badge ' + styles.get(str(status), 'neutral') + '">' + _e(status) + '</span>'


def _point(angle, radius, cx=220, cy=220):
    return cx + radius * math.cos(angle), cy + radius * math.sin(angle)


def _triangle(x, y, dx, dy, size=5):
    """Arrowhead with its tip at the directional segment boundary."""
    bx, by = x - dx * size * 2, y - dy * size * 2
    return f'{x:.3f},{y:.3f} {bx - dy * size:.3f},{by + dx * size:.3f} {bx + dy * size:.3f},{by - dx * size:.3f}'


def _map(record: dict) -> str:
    features = record.get('features', [])
    length = len(record.get('sequence', ''))
    if not length:
        return '<p class="muted">No sequence coordinates available.</p>'
    circular = record.get('topology') == 'circular'
    height = 440 if circular else max(130, 80 + 27 * len(features))
    width = 440 if circular else 900
    pieces = [f'<svg class="sequence-map" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" role="img" aria-labelledby="map-title map-description">',
              f'<title id="map-title">{_e(record.get("topology", "unknown"))} sequence feature map</title>',
              '<desc id="map-description">Each compound location is drawn as its separate exact segments. Arrowheads show strand direction; undirected spans have no arrowhead. Coordinates in the table are one-based inclusive.</desc>']
    if circular:
        pieces += ['<circle cx="220" cy="220" r="163" fill="none" stroke="#d8e3dc" stroke-width="2"/>',
                   '<path d="M220 47V65" stroke="#6c8177"/>',
                   '<text x="220" y="34" text-anchor="middle" class="map-label">1</text>',
                   f'<text x="220" y="214" text-anchor="middle" class="map-count">{length:,}</text>',
                   '<text x="220" y="239" text-anchor="middle" class="map-label">bp · circular</text>']
    else:
        pieces += ['<path d="M70 32H860" stroke="#d8e3dc" stroke-width="3"/>',
                   '<text x="70" y="20" class="map-label">1</text>',
                   f'<text x="860" y="20" text-anchor="end" class="map-label">{length:,} bp</text>']
    for i, feature in enumerate(features):
        color = _COLORS[i % len(_COLORS)]
        pieces.append(f'<a href="#feature-{i}"><g fill="{color}" stroke="{color}">')
        for seg in feature.get('segments', []):
            start, end, strand = int(seg['start']), int(seg['end']), int(seg.get('strand') or 0)
            title = f'{feature.get("label", feature.get("type", "Feature"))}: {start + 1}–{end}; strand {strand}'
            pieces.append(f'<g data-start="{start}" data-end="{end}" data-strand="{strand}"><title>{_e(title)}</title>')
            if circular:
                radius = 118 + (i % 7) * 6
                a1, a2 = start / length * math.tau - math.pi / 2, end / length * math.tau - math.pi / 2
                am = (a1 + a2) / 2
                x1, y1 = _point(a1, radius); xm, ym = _point(am, radius); x2, y2 = _point(a2, radius)
                pieces.append(f'<path d="M{x1:.3f} {y1:.3f} A{radius} {radius} 0 0 1 {xm:.3f} {ym:.3f} A{radius} {radius} 0 0 1 {x2:.3f} {y2:.3f}" fill="none" stroke-width="5"/>')
                if strand:
                    angle = a1 if strand < 0 else a2
                    x, y = _point(angle, radius)
                    direction = -1 if strand < 0 else 1
                    dx, dy = -math.sin(angle) * direction, math.cos(angle) * direction
                    # Keep the arrowhead within short spans instead of overstating extent.
                    size = min(4, max(0.1, (end - start) / length * math.tau * radius / 3))
                    pieces.append(f'<polygon points="{_triangle(x, y, dx, dy, size)}" stroke="none"/>')
            else:
                x1, x2, y = 70 + start / length * 790, 70 + end / length * 790, 60 + i * 27
                pieces.append(f'<path d="M{x1:.3f} {y}H{x2:.3f}" fill="none" stroke-width="7"/>')
                if strand:
                    pieces.append(f'<polygon points="{_triangle(x1 if strand < 0 else x2, y, -1 if strand < 0 else 1, 0, min(5, max(0.1, (x2 - x1) / 3)))}" stroke="none"/>')
            pieces.append('</g>')
        if not circular:
            pieces.append(f'<text x="53" y="{64 + i * 27}" text-anchor="end" stroke="none" class="map-label">{i + 1}</text>')
        pieces.append('</g></a>')
    pieces.append('</svg>')
    return ''.join(pieces)


def _features(record: dict) -> str:
    features = record.get('features', [])
    if not features:
        return '<p class="muted">No annotated features.</p>'
    rows = []
    for i, f in enumerate(features):
        spans = []
        for seg in f.get('segments', []):
            strand = seg.get('strand')
            direction = 'reverse (−)' if strand == -1 else 'forward (+)' if strand == 1 else 'unknown strand'
            spans.append(f'{int(seg["start"]) + 1}–{int(seg["end"])} · {direction}')
        # Preserve source-provided provenance fields without guessing its schema.
        provenance = {k: v for k, v in f.items() if k not in {'type', 'label', 'location', 'segments', 'qualifiers'}}
        rows.append(f'<tr id="feature-{i}"><td><span class="swatch" style="background:{_COLORS[i % len(_COLORS)]}"></span>{i + 1}</td>'
                    f'<td><strong>{_e(f.get("label", f.get("type", "Feature")))}</strong><br><span class="muted">{_e(f.get("type"))}</span></td>'
                    f'<td>{"<br>".join(spans)}<code class="location">{_e(f.get("location", "Not supplied"))}</code></td>'
                    f'<td><details><summary>Full qualifiers &amp; provenance</summary><h4>Qualifiers</h4>{_pre(f.get("qualifiers", {}))}'
                    f'<h4>Identity, layer &amp; provenance</h4>{_pre(provenance)}</details></td></tr>')
    return '<div class="table-wrap"><table><thead><tr><th>#</th><th>Feature</th><th>Exact location · 1-based inclusive</th><th>Annotations</th></tr></thead><tbody>' + ''.join(rows) + '</tbody></table></div>'


def _list(values: list, empty: str) -> str:
    if not values:
        return '<p class="muted">' + _e(empty) + '</p>'
    return '<ul>' + ''.join('<li>' + (_pre(v) if isinstance(v, (dict, list)) else _e(v)) + '</li>' for v in values) + '</ul>'


def _changes(changes: list) -> str:
    if not changes:
        return '<p class="muted">No changes were recorded.</p>'
    rows = []
    for change in changes:
        if not isinstance(change, dict):
            rows.append('<li>' + _e(change) + '</li>')
            continue
        message = change.get('message') or str(change.get('kind', 'Change')).replace('_', ' ').capitalize()
        facts = []
        if 'start' in change and 'end' in change:
            location_context = 'Parent span' if change.get('kind') == 'replace' else 'Output span'
            facts.append(f'{location_context}: {int(change["start"]) + 1}–{int(change["end"])} (1-based inclusive)')
        if 'length_delta' in change:
            delta = int(change['length_delta'])
            sign = '−' if delta < 0 else '+' if delta > 0 else ''
            facts.append(f'Length change: {sign}{abs(delta):,} bp')
        if 'replacement_length' in change:
            facts.append(f'Replacement length: {int(change["replacement_length"]):,} bp')
        rows.append('<li>' + _e(message) + ('<br><span class="muted small">' + _e(' · '.join(facts)) + '</span>' if facts else '') + '</li>')
    return '<ul>' + ''.join(rows) + '</ul><details><summary>Full change record</summary>' + _pre(changes) + '</details>'


def _display_value(value) -> str:
    """Format a recorded decision without assigning meaning to its value."""
    if isinstance(value, dict):
        return '; '.join(str(key).replace('_', ' ') + ': ' + _display_value(item)
                         for key, item in value.items())
    if isinstance(value, list):
        return ', '.join(_display_value(item) for item in value)
    return str(value if value is not None else 'Not recorded')


def _evidence_refs(refs) -> str:
    # References are displayed as inert identifiers, never as trusted links.
    if not refs:
        return '<span class="muted">No evidence references supplied.</span>'
    if not isinstance(refs, list):
        refs = [refs]
    return 'Referenced identifiers: ' + ', '.join('<code>' + _e(ref) + '</code>' for ref in refs)


def _agent_notes(entries: list, empty: str) -> str:
    """Human-readable optional questions, assumptions, or stated limitations."""
    if not entries:
        return '<p class="muted">' + _e(empty) + '</p>'
    rows = []
    for entry in entries:
        if not isinstance(entry, dict):
            rows.append('<li>' + _e(entry) + '</li>')
            continue
        text = next((entry[key] for key in ('text', 'question', 'assumption', 'message')
                     if entry.get(key) is not None), 'No description supplied.')
        facts = []
        for key in ('origin', 'status', 'reason'):
            if entry.get(key) is not None:
                label = 'Recorded origin' if key == 'origin' else key.capitalize()
                facts.append(_e(label) + ': ' + _e(_display_value(entry[key])))
        if entry.get('evidence_refs'):
            facts.append(_evidence_refs(entry['evidence_refs']))
        rows.append('<li>' + _e(text) + ('<br><span class="muted small">' + '<br>'.join(facts) + '</span>' if facts else '') + '</li>')
    return '<ul>' + ''.join(rows) + '</ul>'


def _agent_rationale(context: dict | None) -> str:
    """Present caller-supplied reasoning separately from measured results.

    This renderer does not decide whether an assessment is correct or turn a
    reference identifier into an authenticated scientific claim.
    """
    if context is None:
        return ''
    identity = [('Job ID', context.get('job_id')), ('Job revision', context.get('revision')),
                ('Plan hash', context.get('plan_hash'))]
    identity_html = ''.join('<dt>' + _e(k) + '</dt><dd>' + _e(v) + '</dd>' for k, v in identity)
    criteria = []
    for item in context.get('criteria', []):
        criteria.append('<tr><td><strong>' + _e(item.get('id')) + '</strong><br>' + _e(item.get('text')) +
                        '</td><td>' + _badge(item.get('status', 'not assessed')) + '</td><td>' +
                        _e(item.get('evaluation', 'No evaluation supplied.')) + '<br><span class="muted small">' +
                        _evidence_refs(item.get('evidence_refs', [])) + '</span></td></tr>')
    criteria_html = ('<div class="table-wrap"><table><thead><tr><th>Requirement</th><th>Agent-assigned status</th>'
                     '<th>Agent assessment &amp; references</th></tr></thead><tbody>' + ''.join(criteria) +
                     '</tbody></table></div>') if criteria else '<p class="muted">No requirement assessments were supplied.</p>'
    decisions = []
    for item in context.get('decisions', []):
        decisions.append('<tr><td>' + _e(item.get('field')) + '</td><td>' + _e(_display_value(item.get('value'))) +
                         '</td><td>' + _e(item.get('origin', 'Not recorded')) + '</td><td>' +
                         _e(item.get('reason', 'No reason supplied.')) + '</td></tr>')
    decisions_html = ('<div class="table-wrap"><table><thead><tr><th>Decision</th><th>Value</th><th>Recorded origin</th>'
                      '<th>Reason</th></tr></thead><tbody>' + ''.join(decisions) + '</tbody></table></div>') if decisions else '<p class="muted">No decisions were recorded.</p>'
    selections = []
    for item in context.get('selections', []):
        selections.append('<li><strong>' + _e(item.get('record_id')) + '</strong><br>' +
                          _e(item.get('reason', 'No selection reason supplied.')) + '<br><span class="muted small">' +
                          _evidence_refs(item.get('evidence_refs', [])) + '</span></li>')
    selections_html = '<ul>' + ''.join(selections) + '</ul>' if selections else '<p class="muted">No selection rationale was supplied.</p>'
    alternatives = []
    for item in context.get('alternatives', []):
        alternatives.append('<li><strong>' + _e(item.get('record_id')) + '</strong><br>' +
                            _e(item.get('reason', 'No comparison reason supplied.')) + '</li>')
    alternatives_html = '<ul>' + ''.join(alternatives) + '</ul>' if alternatives else '<p class="muted">No alternatives were recorded.</p>'
    extra_limits = ('<h3>Agent-stated limitations</h3>' + _agent_notes(context['limitations'], '')) if context.get('limitations') else ''
    return ('<section><h2>Objective interpretation</h2><p>' +
            _e(context.get('summary', 'No objective interpretation was supplied.')) + '</p>' +
            '<p class="notice">Agent assessments are separate from computational checks and experimental evidence. '
            'The following reasoning is supplied by the calling agent and has not been independently verified. '
            'Evidence references are identifiers, not proof of a claim or a biological validation result.</p>' +
            '<dl class="identity">' + identity_html + '</dl></section>' +
            '<section><h2>Requirement assessments</h2>' + criteria_html + '</section>' +
            '<section><h2>Decisions and origins</h2><p class="muted">Origins are recorded as supplied; '
            'an agent choice or assumption does not establish user confirmation.</p>' + decisions_html + '</section>' +
            '<div class="grid"><section><h2>Selected records</h2>' + selections_html + '</section>' +
            '<section><h2>Alternatives considered</h2>' + alternatives_html + '</section></div>' +
            '<div class="grid"><section><h2>Agent assumptions and recorded origins</h2>' +
            _agent_notes(context.get('assumptions', []), 'No agent assumptions were recorded.') + '</section>' +
            '<section><h2>Unresolved questions</h2>' +
            _agent_notes(context.get('questions', []), 'No unresolved questions were recorded. This does not establish completeness.') + '</section></div>' +
            '<section><h2>Reasoning record</h2>' + extra_limits +
            '<details><summary>Full agent context</summary>' + _pre(context) + '</details></section>')


_CSS = '''
:root{color-scheme:light;--ink:#193d38;--muted:#667a70;--line:#dce4db;--paper:#fffef9;--teal:#167b78}
*{box-sizing:border-box}body{margin:0;background:#f1f3eb;color:var(--ink);font:15px/1.65 system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}
main{max-width:1180px;margin:36px auto;padding:0 28px}header{padding:34px 38px;background:var(--ink);color:var(--paper);border-radius:14px 14px 0 0}
.brand{font-size:12px;letter-spacing:.19em;text-transform:uppercase;color:#bedbd0}h1{font-size:36px;line-height:1.18;margin:14px 0 12px;overflow-wrap:anywhere}h2{font-size:20px;margin:0 0 15px}h3{font-size:15px;margin:0 0 9px}h4{font-size:12px;margin:14px 0 3px;text-transform:uppercase;letter-spacing:.06em}
.subtitle{max-width:820px;color:#d5e4db;margin:0;white-space:pre-wrap;overflow-wrap:anywhere}.toolbar{display:flex;gap:12px;align-items:center;flex-wrap:wrap;margin-top:23px}.download{display:inline-block;padding:9px 15px;color:var(--ink);background:#e3eee3;text-decoration:none;border-radius:7px;font-weight:650}.small{font-size:12px}.muted{color:var(--muted)}
section{background:var(--paper);border:1px solid var(--line);padding:28px 32px;margin:0 0 17px;border-radius:10px}section:first-of-type{border-radius:0 0 10px 10px}.grid{display:grid;grid-template-columns:1fr 1fr;gap:20px}.identity{display:grid;grid-template-columns:135px 1fr;gap:5px 14px;margin:0}.identity dt{color:var(--muted)}.identity dd{margin:0;overflow-wrap:anywhere}.map-grid{display:grid;grid-template-columns:minmax(280px,440px) 1fr;gap:32px;align-items:center}.map-scroll{overflow:auto}.sequence-map{display:block;width:100%;min-width:300px}.map-label{font:12px system-ui;fill:#667a70}.map-count{font:600 33px system-ui;fill:#193d38}.sequence-map a:hover{opacity:.65}
code,pre{font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;font-size:12px}code{overflow-wrap:anywhere}pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#f3f5ef;padding:13px;border-radius:5px;max-height:360px;overflow:auto}.location{display:block;margin-top:7px}.table-wrap{overflow:auto}table{width:100%;border-collapse:collapse;text-align:left;font-size:13px}th{font-size:11px;letter-spacing:.05em;text-transform:uppercase;color:var(--muted)}td,th{padding:13px 10px;border-bottom:1px solid var(--line);vertical-align:top}td{overflow-wrap:anywhere}tr:target{background:#e6f1e8}.swatch{display:inline-block;width:10px;height:10px;border-radius:50%;margin-right:6px}summary{cursor:pointer;color:var(--teal)}.badge{display:inline-block;border-radius:5px;padding:2px 9px;font-size:12px;font-weight:600;overflow-wrap:anywhere}.pass{background:#e1efe5;color:#265c42}.fail{background:#fbe5e1;color:#943d35}.warn{background:#f7ecd3;color:#846021}.neutral{background:#edf0e8;color:#52665b}.checks{list-style:none;padding:0;margin:0}.checks li{display:grid;grid-template-columns:minmax(100px,150px) 1fr;gap:15px;padding:12px 0;border-bottom:1px solid var(--line)}.checks p{margin:3px 0;overflow-wrap:anywhere}ul{padding-left:20px}li{margin:7px 0}footer{padding:6px 0 36px;color:var(--muted);font-size:12px}.notice{border-left:3px solid #aa7833;padding:4px 15px;background:#f6f2e6}a{color:var(--teal)}
@media(max-width:700px){main{padding:0 12px;margin:12px auto}header,section{padding:23px 20px}h1{font-size:27px}.grid,.map-grid{grid-template-columns:1fr}.identity{grid-template-columns:95px 1fr}.checks li{grid-template-columns:1fr;gap:2px}}
@media print{body{background:white}main{max-width:none;margin:0;padding:0}header{background:white;color:var(--ink);border:1px solid var(--line)}.brand,.subtitle{color:var(--ink)}.toolbar{display:none}section{break-inside:avoid}.map-grid{grid-template-columns:330px 1fr}details{display:block}pre{max-height:none}.table-wrap{overflow:visible}}
'''


def render_report(design: dict, genbank_text: str | bytes) -> str:
    """Render a standalone report without evaluating or changing input records."""
    r = design['record']
    seq = r.get('sequence', '')
    actual_hash = hashlib.sha256(seq.encode('utf-8')).hexdigest()
    gbk_bytes = genbank_text.encode('utf-8') if isinstance(genbank_text,str) else genbank_text
    gbk_hash = hashlib.sha256(gbk_bytes).hexdigest()
    href = 'data:application/octet-stream;base64,' + base64.b64encode(gbk_bytes).decode('ascii')
    identity = [
        ('Design ID', design.get('id')), ('Record ID', r.get('id')),
        ('Created', design.get('created_at')), ('Mode', design.get('mode')),
        ('Host profile', design.get('host_name', design.get('host_id'))),
        ('Host profile ID', design.get('host_id')), ('Topology', r.get('topology')),
        ('Convention ID', design.get('convention_id')), ('Parent ID', design.get('parent_id')),
    ]
    identity_html = ''.join(f'<dt>{_e(k)}</dt><dd>{_e(v)}</dd>' for k, v in identity)
    checks = ''.join(f'<li><div>{_badge(c.get("status", "unknown"))}</div><div><strong>{_e(c.get("id", "Check"))}</strong><p>{_e(c.get("message", "No result supplied"))}</p></div></li>' for c in design.get('checks', []))
    if not checks:
        checks = '<li>No computational checks supplied.</li>'
    metadata = {'source': r.get('source', {}), 'metadata': r.get('metadata', {}),
                'part_ids': design.get('part_ids', []), 'parent_id': design.get('parent_id'),
                'evidence': design.get('evidence', [])}
    source = r.get('source', {})
    source_summary = [
        ('Source kind', source.get('kind')),
        ('Source record IDs', ', '.join(str(value) for value in design.get('part_ids', [])) or 'None recorded'),
        ('Parent ID', design.get('parent_id')),
    ]
    if source.get('replacement_id'):
        source_summary.append(('Replacement ID', source['replacement_id']))
    provenance_html = '<dl class="identity">' + ''.join(f'<dt>{_e(k)}</dt><dd>{_e(v)}</dd>' for k, v in source_summary) + '</dl>'
    features = _features(r)
    map_html = _map(r)
    summary = f'<h3>Exact sequence representation</h3><p>{len(seq):,} bp · {_e(r.get("topology"))} · {len(r.get("features", []))} annotated features</p><p class="muted">Map spans follow the supplied exact coordinates. Compound locations retain every segment. Arrowheads denote strand direction. Select a feature to reach its annotation row.</p><p class="notice">The map describes sequence composition; laboratory assembly and host compatibility remain unevaluated.</p>'
    if r.get('metadata',{}).get('inspection_only'):
        summary = summary.replace('Map spans follow the supplied exact coordinates.', 'Map spans show interpreted locations; original expressions remain source evidence.')
        summary = '<p class="notice"><strong>Parser interpretation.</strong> This map displays the parser’s interpretation of the original annotations. Source warnings and original location expressions are retained in the provenance. The downloaded GenBank is unchanged; no repair is claimed.</p>' + summary
    if r.get('topology') == 'circular':
        map_block = '<div class="map-grid"><div class="map-scroll">' + map_html + '</div><div>' + summary + '</div></div>'
    else:
        map_block = summary + '<div class="map-scroll">' + map_html + '</div>'
    assembly_html = ''
    fragment_html = ''
    planning = r.get('metadata',{}).get('fragment_planning')
    if planning:
        blocks=[]
        for fragment in planning:
            rows=''.join('<tr><td>'+_e(f['label'])+'</td><td><code>'+_e(f['source_location'])+'</code></td><td>'+_e(f['status'])+'</td><td><code>'+_e(f['fragment_location'])+'</code></td></tr>' for f in fragment['features'])
            blocks.append('<h3>'+_e(fragment['source_name'])+'</h3><p>Ranges (0-based half-open): <code>'+_e(fragment['ranges'])+'</code>; orientation: '+_e(fragment['orientation'])+'; prepared length: '+str(fragment['fragment_length'])+' bp.</p><div class="table-wrap"><table><thead><tr><th>Source feature</th><th>Original location</th><th>Outcome</th><th>Prepared location</th></tr></thead><tbody>'+rows+'</tbody></table></div><details><summary>Bibliography projection and exact preparation evidence</summary>'+_pre(fragment)+'</details>')
        fragment_html='<section><h2>Fragment preparation and annotation comparison</h2><p class="notice">Source records remain unchanged. Complete selected features are retained; annotations wholly outside the ranges are explicitly excluded. A single whole-record source annotation can be projected with an audit; cuts through other features are rejected. Bibliography text is retained with audited range projection. This coordinate operation does not validate physical cutting, PCR or reaction conditions.</p>'+''.join(blocks)+'</section>'
    assembly = r.get('metadata',{}).get('assembly')
    if assembly:
        rows = ''.join('<tr><td>'+str(i+1)+'</td><td>'+_e(j['left_source_id'])+' → '+_e(j['right_source_id'])+'</td><td>'+str(j['length'])+' bp</td><td>'+str(j['output_range'][0]+1)+'–'+str(j['output_range'][1])+'</td><td><code>'+_e(j['overlap'])+'</code></td></tr>' for i,j in enumerate(assembly['junctions']))
        assembly_html = '<section><h2>Homology assembly prediction</h2><p>Two prepared linear inputs, supplied orientations, one unique circular product. Backend: '+_e(assembly['backend'])+' '+_e(assembly['backend_version'])+'. Origin: backbone base 0.</p><div class="table-scroll"><table><thead><tr><th>Junction</th><th>Sources</th><th>Overlap</th><th>Output span (1-based inclusive)</th><th>Exact homology</th></tr></thead><tbody>'+rows+'</tbody></table></div><p class="notice">Exact terminal homology and sequence prediction passed. Primers, cutting, thermal conditions, host suitability and experimental assembly remain unevaluated. Shared-overlap annotations from both inputs are retained independently.</p></section>'
    return f'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; img-src data:; base-uri 'none'; form-action 'none'">
<title>{_e(design.get('name', 'VGET design'))} · VGET report</title><style>{_CSS}</style></head>
<body><main><header><div class="brand">VGET / Local design record</div><h1>{_e(design.get('name', r.get('name', 'Untitled')))}</h1>
<p class="subtitle">{_e(design.get('objective'))}</p><div class="toolbar"><a class="download" href="{href}" download="construct.gbk">Download GenBank</a>{_badge(design.get('status', 'unknown'))}<span class="small">Computational result · experimental function unverified</span></div></header>
<section><h2>Design identity</h2><dl class="identity">{identity_html}</dl></section>
{_agent_rationale(design.get('agent_context'))}
{fragment_html}
{assembly_html}
<section><h2>Sequence &amp; annotation map</h2>{map_block}</section>
<section><h2>Features</h2>{features}</section>
<section><h2>Validation record</h2><ul class="checks">{checks}</ul></section>
<div class="grid"><section><h2>Assumptions</h2>{_list(design.get('assumptions', []), 'No assumptions were recorded.')}</section>
<section><h2>Changes</h2>{_changes(design.get('changes', []))}</section></div>
<section><h2>Provenance &amp; evidence</h2>{provenance_html}<p class="muted">Complete source records and original imported bytes, when available, are included in the export bundle.</p><details><summary>Full provenance &amp; evidence</summary>{_pre(metadata)}</details></section>
<section><h2>Content fingerprints</h2><dl class="identity"><dt>Sequence SHA-256</dt><dd><code>{actual_hash}</code></dd><dt>Recorded sequence hash</dt><dd><code>{_e(r.get('sequence_sha256'))}</code></dd><dt>GenBank SHA-256</dt><dd><code>{gbk_hash}</code></dd></dl><p class="muted small">Sequence hash covers the exact sequence string encoded as UTF-8. GenBank hash covers the exact downloadable UTF-8 file bytes.</p></section>
<section><h2>Interpretation limits</h2>{_list(list(_LIMITS) + list(design.get('limitations', [])), '')}</section>
<footer>VGET local prototype · Standalone HTML · No scripts, external fonts, or remote resources</footer></main></body></html>'''


def package_files(design: dict, genbank_text: str | bytes, source_records: list[dict], originals: dict[str, bytes]) -> dict[str, bytes]:
    """Return deterministic bundle members; input names never become paths.

    The manifest hashes every payload file and intentionally excludes itself.
    Original byte blobs have generated flat paths and their display names are
    recorded as JSON data. No input object is modified.
    """
    files = {
        'construct.gbk': genbank_text.encode('utf-8') if isinstance(genbank_text,str) else genbank_text,
        'report.html': render_report(design, genbank_text).encode('utf-8'),
        'design.json': _dump(design),
        'features.json': _dump(design['record'].get('features', [])),
        'changes.json': _dump(design.get('changes', [])),
        'validation.json': _dump({'status': design.get('status'), 'checks': design.get('checks', []), 'limitations': list(_LIMITS) + list(design.get('limitations', []))}),
        'source-records.json': _dump(source_records),
    }
    if design.get('agent_context') is not None:
        files['agent-context.json'] = _dump(design['agent_context'])
    if design['record'].get('metadata',{}).get('fragment_planning') is not None:
        files['fragment-planning.json']=_dump(design['record']['metadata']['fragment_planning'])
    originals_index = []
    for i, (name, data) in enumerate(sorted(originals.items()), 1):
        if not isinstance(data, bytes):
            raise TypeError('Original source contents must be bytes')
        path = f'sources/source-{i:04d}.bin'
        files[path] = data
        originals_index.append({'original_name': name, 'path': path, 'sha256': hashlib.sha256(data).hexdigest(), 'bytes': len(data)})
    evidence = {
        'design_id': design.get('id'), 'part_ids': design.get('part_ids', []), 'parent_id': design.get('parent_id'),
        'assumptions': design.get('assumptions', []), 'evidence': design.get('evidence', []),
        'source_records': [{'id': r.get('id'), 'name': r.get('name'), 'sequence_sha256': r.get('sequence_sha256'),
                            'source': r.get('source', {}), 'metadata': r.get('metadata', {})} for r in source_records],
        'originals': originals_index,
        'limitations': list(_LIMITS),
    }
    files['evidence.json'] = _dump(evidence)
    files['manifest.json'] = _dump({
        'format': 'vget-export-v1', 'design_id': design.get('id'), 'hash_algorithm': 'sha256',
        'files': [{'path': path, 'sha256': hashlib.sha256(data).hexdigest(), 'bytes': len(data)} for path, data in sorted(files.items())],
        'manifest_note': 'Manifest lists every other bundle member; it has no self hash.',
    })
    return files
