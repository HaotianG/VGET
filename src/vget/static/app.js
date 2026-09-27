'use strict';
(() => {
  const $ = (s, root = document) => root.querySelector(s);
  const $$ = (s, root = document) => [...root.querySelectorAll(s)];
  const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const colors = ['#8faf77','#537f70','#d0b776','#7da6a3','#c39175','#9f9aaf','#a7b865','#649080'];
  const state = {records:[], designs:[], hosts:[], conventions:[], parts:[], mode:'create', selectedRecord:null, lastDesign:null, initialized:false};
  let briefVersion = 0;
  const record = id => state.records.find(r => r.id === id);
  const number = n => Number(n || 0).toLocaleString();
  const length = r => Number(r?.length ?? r?.sequence?.length ?? 0);
  const nice = value => String(value ?? '').replace(/_/g, ' ');
  const textValue = value => typeof value === 'string' ? value : JSON.stringify(value, null, 2);
  const color = index => colors[index % colors.length];

  async function api(path, options = {}) {
    const headers = {...(options.headers || {})};
    if ((options.method || 'GET').toUpperCase() === 'POST') headers['X-VGET-Local'] = '1';
    if (options.body && !(options.body instanceof FormData)) {headers['Content-Type'] = 'application/json'; options.body = JSON.stringify(options.body);}
    const response = await fetch(path, {...options, headers, credentials:'same-origin'});
    let data;
    try {data = await response.json();} catch {throw new Error(`The server returned an unreadable response (${response.status}).`);}
    if (!response.ok) {
      const error = new Error(data.error?.message || `Request failed (${response.status}).`);
      error.details = data.error?.details;
      error.code = data.error?.code;
      throw error;
    }
    return data;
  }
  function notice(message, kind = '', details) {
    $('#global-status').innerHTML = `<div class="notice ${esc(kind)}"><div>${esc(message)}${details ? `<pre>${esc(textValue(details))}</pre>` : ''}</div><button class="dismiss" aria-label="Dismiss notification">×</button></div>`;
    $('.dismiss').onclick = () => {$('#global-status').innerHTML = '';};
  }
  async function busy(button, action) {
    if (button.disabled) return;
    const previous = button.innerHTML;
    button.disabled = true; button.textContent = 'Working…';
    try {await action();} catch (error) {notice(error.message, 'error', error.details);}
    finally {button.disabled = false; button.innerHTML = previous;}
  }
  function options(records, empty) {
    return `${empty ? `<option value="">${esc(empty)}</option>` : ''}${records.map(r => `<option value="${esc(r.id)}">${esc(r.name)} · ${number(length(r))} bp</option>`).join('')}`;
  }
  function preserveOptions(selector, html) {
    const input = $(selector), old = input.value;
    input.innerHTML = html;
    if ([...input.options].some(o => o.value === old)) input.value = old;
  }
  function navigate(page) {
    if (!$(`#page-${page}`)) page = 'workspace';
    $$('.page').forEach(el => el.classList.toggle('active', el.id === `page-${page}`));
    $$('.nav').forEach(el => {const active = el.dataset.page === page; el.classList.toggle('active', active); if (active) el.setAttribute('aria-current', 'page'); else el.removeAttribute('aria-current');});
    $('#breadcrumb-current').textContent = $(`.nav[data-page="${page}"]`).textContent.replace(/^[^A-Za-z]+/, '').replace(/\s*\d+\s*$/, '').trim();
    if (location.hash !== `#${page}`) history.replaceState(null, '', `#${page}`);
  }
  async function refresh() {
    const data = await api('/api/state');
    state.records = data.records || []; state.designs = data.designs || []; state.hosts = data.hosts || []; state.conventions = data.conventions || [];
    state.parts = state.parts.filter(id => record(id));
    preserveOptions('#host', state.hosts.map(h => `<option value="${esc(h.id)}">${esc(h.name)}</option>`).join(''));
    for (const id of ['#part-picker','#parent','#replacement','#compare-left','#compare-right']) preserveOptions(id, options(state.records, 'Select a record…'));
    preserveOptions('#convention', '<option value="">No convention selected</option>' + state.conventions.filter(c => c.state === 'active').map(c => `<option value="${esc(c.id)}">${esc(c.name)} · v${esc(c.version)}</option>`).join(''));
    if (!state.initialized) {
      const demo = state.records.filter(r => /demo|synthetic/i.test(`${r.name} ${r.description} ${JSON.stringify(r.source || {})}`));
      const choices = demo.length ? demo : state.records;
      const parts = choices.filter(r => !/parent|complete|construct|replacement/i.test(r.name));
      const orderedDemoParts = ['Demo_backbone', 'Demo_insert'].map(name => demo.find(r => r.name === name)).filter(Boolean);
      state.parts = (orderedDemoParts.length === 2 ? orderedDemoParts : (parts.length ? parts : choices).slice(0,3)).map(r => r.id);
      const demoConvention = state.conventions.find(c => c.id === 'demo-convention' && c.state === 'active');
      if (demoConvention) $('#convention').value = demoConvention.id;
      $('#parent').value = (choices.find(r => /^demo[_ ]parent$/i.test(r.name)) || choices.find(r => (r.features || []).some(f => f.segments?.length === 1)) || choices[0])?.id || '';
      $('#replacement').value = (choices.find(r => /^demo[_ ]replacement$/i.test(r.name)) || choices.find(r => r.id !== $('#parent').value) || choices[0])?.id || '';
      state.initializeDemoTarget = true;
      $('#compare-left').value = choices[0]?.id || '';
      $('#compare-right').value = choices[1]?.id || choices[0]?.id || '';
      state.selectedRecord = choices[0]?.id || null;
      state.initialized = true;
    }
    $('#library-count').textContent = state.records.length; $('#history-count').textContent = state.designs.length;
    $('#record-count').textContent = state.records.length;
    renderSelectedParts(); renderParent();
    if (state.initializeDemoTarget) {
      const parent = record($('#parent').value);
      if (parent?.source?.kind === 'demo' && /^demo[_ ]parent$/i.test(parent.name)) {
        $('#target').value = (parent.features || []).find(f => /^demo[_ ]insert$/i.test(f.label))?.id || '';
        $$('#protected-features input').forEach(input => {const feature = parent.features.find(f => f.id === input.value); input.checked = /^(left|right)_context$/i.test(feature?.label || '');});
      }
      state.initializeDemoTarget = false;
    }
    renderLibrary(); renderHosts(); renderConventions(); renderHistory();
  }
  function invalidateBrief() {
    briefVersion++;
    $('#result-card').hidden = true;
    $('#brief-state').textContent = 'Not reviewed'; $('#brief-state').className = 'badge muted';
    $('#brief-content').innerHTML = '<p class="empty-copy">The brief has changed. Review it again to check the current inputs.</p><div class="small-note">Deterministic input checks. No language model or functional prediction.</div>';
  }
  function setMode(mode) {
    state.mode = mode;
    const defaultCreate = 'Explore an ordered composition of the synthetic demonstration parts.';
    const defaultModify = 'Replace the selected synthetic demonstration feature while preserving the chosen context features.';
    if ([$('#objective').value].some(value => value === defaultCreate || value === defaultModify)) $('#objective').value = mode === 'create' ? defaultCreate : defaultModify;
    $$('[data-mode]').forEach(b => {const selected = b.dataset.mode === mode; b.classList.toggle('selected', selected); b.setAttribute('aria-pressed', String(selected));});
    $('#create-fields').hidden = mode !== 'create'; $('#modify-fields').hidden = mode !== 'modify';
    $('#preview-heading').textContent = mode === 'create' ? 'Composition preview' : 'Parent record preview';
    $('#build-design').innerHTML = mode === 'create' ? 'Compose design <span>→</span>' : 'Apply replacement <span>→</span>';
    $('#topology').disabled = mode === 'modify';
    if (mode === 'modify') $('#topology').value = record($('#parent').value)?.topology || 'circular';
    invalidateBrief(); renderPreview();
  }
  function renderSelectedParts() {
    $('#part-total').textContent = `${state.parts.length} PART${state.parts.length === 1 ? '' : 'S'}`;
    $('#selected-parts').innerHTML = state.parts.length ? state.parts.map((id,i) => {
      const r = record(id);
      return `<li class="part-item"><span class="part-number">${String(i+1).padStart(2,'0')}</span><span class="part-color" style="background:${color(i)}"></span><span class="part-meta"><strong>${esc(r.name)}</strong><small>${number(length(r))} bp · ${esc(r.source?.kind || 'local record')}</small></span><span class="part-controls"><button type="button" data-part-action="up" data-index="${i}" aria-label="Move ${esc(r.name)} up" ${i === 0 ? 'disabled' : ''}>↑</button><button type="button" data-part-action="down" data-index="${i}" aria-label="Move ${esc(r.name)} down" ${i === state.parts.length-1 ? 'disabled' : ''}>↓</button><button type="button" data-part-action="remove" data-index="${i}" aria-label="Remove ${esc(r.name)}">×</button></span></li>`;
    }).join('') : '<li class="empty-copy">Add input records to start a composition.</li>';
    renderPreview();
  }
  function renderParent() {
    const parent = record($('#parent').value), oldTarget = $('#target').value;
    const protectedIds = new Set($$('#protected-features input:checked').map(el => el.value));
    $('#target').innerHTML = '<option value="">Select an exact feature…</option>' + (parent?.features || []).map(f => `<option value="${esc(f.id)}">${esc(f.label || f.type)} · ${esc(f.location || featureSpan(f))}</option>`).join('');
    if ((parent?.features || []).some(f => f.id === oldTarget)) $('#target').value = oldTarget;
    $('#protected-features').innerHTML = (parent?.features || []).length ? parent.features.map(f => `<label class="checkbox-label"><input type="checkbox" value="${esc(f.id)}" ${protectedIds.has(f.id) ? 'checked' : ''}><span>${esc(f.label || f.type)} <small>(${esc(f.location || featureSpan(f))})</small></span></label>`).join('') : '<p class="help">This record has no annotated features.</p>';
    if (state.mode === 'modify') $('#topology').value = parent?.topology || 'circular';
    renderPreview();
  }
  function featureSpan(f) {return (f.segments || []).map(s => `${number(s.start+1)}–${number(s.end)}${s.strand === -1 ? ' (−)' : ''}`).join(', ');}
  function renderPreview() {
    const input = state.mode === 'create' ? state.parts.map(record).filter(Boolean) : [record($('#parent').value)].filter(Boolean);
    const total = input.reduce((sum,r) => sum+length(r),0), topology = $('#topology').value;
    $('#preview-length').textContent = `${number(total)} bp`;
    let graphic = '';
    if (topology === 'circular') {
      const radius = 77, circumference = 2*Math.PI*radius;
      let offset = 0;
      graphic = `<circle cx="180" cy="124" r="${radius}" fill="none" stroke="#edf1e7" stroke-width="16"/>`;
      input.forEach((r,i) => {const arc = total ? length(r)/total*circumference : 0; graphic += `<circle cx="180" cy="124" r="${radius}" fill="none" stroke="${color(i)}" stroke-width="16" stroke-dasharray="${Math.max(0,arc-4)} ${circumference-Math.max(0,arc-4)}" stroke-dashoffset="${-offset}" transform="rotate(-90 180 124)"/>`; offset += arc;});
      graphic += `<circle cx="180" cy="124" r="56" fill="none" stroke="#e8ede2" stroke-dasharray="2 5"/><text x="180" y="114" text-anchor="middle" style="font-size:10px;fill:#95a186;letter-spacing:1px">${state.mode === 'create' ? 'COMPOSITION' : 'PARENT RECORD'}</text><text x="180" y="140" text-anchor="middle" style="font-size:23px;font-family:Georgia,serif">${number(total)} <tspan style="font-size:12px">bp</tspan></text><text x="180" y="161" text-anchor="middle" style="font-size:9px;fill:#9ca68e">circular · ${input.length} input${input.length === 1 ? '' : 's'}</text>`;
    } else {
      let x = 25; graphic = '<line x1="25" y1="105" x2="335" y2="105" stroke="#e3e9db" stroke-width="15"/>';
      input.forEach((r,i) => {const width = total ? length(r)/total*310 : 0; graphic += `<rect x="${x}" y="95" width="${Math.max(0,width-3)}" height="20" fill="${color(i)}" rx="3"/>`; x += width;});
      graphic += `<text x="180" y="157" text-anchor="middle" style="font-size:24px;font-family:Georgia,serif">${number(total)} bp</text><text x="180" y="179" text-anchor="middle" style="font-size:10px;fill:#95a186">linear · ${input.length} input${input.length === 1 ? '' : 's'}</text>`;
    }
    $('#construct-preview').innerHTML = `<svg class="construct-svg" viewBox="0 0 360 250" role="img" aria-label="${esc(topology)} sequence preview, ${number(total)} base pairs">${graphic}</svg>`;
    $('#preview-legend').innerHTML = input.map((r,i) => `<span class="legend-item"><span class="legend-swatch" style="background:${color(i)}"></span>${esc(r.name)}</span>`).join('');
  }
  function payload() {
    return {name:$('#design-name').value.trim(),objective:$('#objective').value.trim(),mode:state.mode,host_id:$('#host').value,topology:$('#topology').value,part_ids:state.mode === 'create' ? [...state.parts] : [],parent_id:state.mode === 'modify' ? $('#parent').value || null : null,target_feature_id:state.mode === 'modify' ? $('#target').value || null : null,replacement_id:state.mode === 'modify' ? $('#replacement').value || null : null,convention_id:$('#convention').value || null,protected_feature_ids:state.mode === 'modify' ? $$('#protected-features input:checked').map(el => el.value) : []};
  }
  function renderBrief(brief) {
    $('#brief-state').textContent = brief.ready ? 'Ready to compute' : 'Inputs needed'; $('#brief-state').className = `badge ${brief.ready ? 'teal' : 'amber'}`;
    $('#brief-content').innerHTML = `<p class="result-description">${esc(textValue(brief.summary || 'Brief evaluated.'))}</p>${(brief.questions || []).length ? `<ul class="question-list">${brief.questions.map(q => `<li><span class="check-marker warn">?</span><span><strong>${esc(nice(q.field))}</strong><br>${esc(q.message)}</span></li>`).join('')}</ul>` : '<ul class="check-list"><li><span class="check-marker">✓</span><span>Required inputs are present for a computational result.</span></li></ul>'}${(brief.assumptions || []).length ? `<h3>Explicit assumptions</h3>${list(brief.assumptions)}` : ''}<div class="small-note">${esc(brief.supported_scope ? textValue(brief.supported_scope) : 'Deterministic brief resolver; no language model connected.')}</div>`;
  }
  function list(items) {return `<ul class="assumption-list">${items.map(item => `<li><span class="check-marker warn">·</span><span>${esc(typeof item === 'string' ? item : item.message || item.description || textValue(item))}</span></li>`).join('')}</ul>`;}
  function safeDownload(url) {return typeof url === 'string' && /^\/api\/designs\/[^/]+\/(construct\.gbk|report\.html|bundle\.zip)$/.test(url) ? url : '#';}
  function downloads(design) {
    const files = design.files || {}, base = `/api/designs/${encodeURIComponent(design.id)}`;
    return `<div class="download-actions"><a class="button primary" href="${esc(safeDownload(files.bundle || `${base}/bundle.zip`))}" download>Download bundle ↓</a><a class="button secondary" href="${esc(safeDownload(files.genbank || `${base}/construct.gbk`))}" download>GenBank</a><a class="button secondary" href="${esc(safeDownload(files.report || `${base}/report.html`))}" target="_blank" rel="noopener">HTML report ↗</a></div>`;
  }
  function resultMarkup(design) {
    return `<div class="result-title">${esc(design.name)}</div><div class="result-statline"><span class="badge muted">${number(length(design.record))} bp</span><span class="badge muted">${esc(design.record?.topology)}</span><span class="badge muted">${esc(design.host_name || design.host_id)}</span></div><p class="result-description">${esc(nice(design.status || 'Computational result; biological function unevaluated'))}</p><h3>Computational checks</h3><ul class="check-list">${(design.checks || []).map(c => {const status = String(c.status).toLowerCase(), failed = /fail|error|block/.test(status), warning = /warn|unevaluated|unknown|skip|not_evaluated/.test(status);return `<li><span class="check-marker ${failed ? 'fail' : warning ? 'warn' : ''}">${failed ? '×' : warning ? '!' : '✓'}</span><span>${esc(c.message || nice(c.id))}<small class="help">${esc(nice(c.status))}</small></span></li>`;}).join('')}</ul>${(design.changes || []).length ? `<h3>Change record</h3>${list(design.changes)}` : ''}${(design.assumptions || []).length ? `<h3>Assumptions</h3>${list(design.assumptions)}` : ''}${downloads(design)}`;
  }
  function showResult(design) {
    state.lastDesign = design; $('#result-card').hidden = false; $('#result-content').innerHTML = resultMarkup(design);
    $('#result-card').scrollIntoView({behavior:'smooth',block:'nearest'});
  }
  function renderLibrary() {
    const query = $('#library-search').value.toLowerCase();
    const records = state.records.filter(r => `${r.name} ${r.description} ${r.source?.kind || ''} ${r.source?.filename || ''}`.toLowerCase().includes(query));
    $('#record-list').innerHTML = records.length ? records.map(r => `<button class="record-button ${r.id === state.selectedRecord ? 'selected' : ''}" data-record="${esc(r.id)}"><strong>${esc(r.name)}</strong><small>${number(length(r))} bp · ${esc(r.topology)} · ${esc(r.source?.kind || 'local')}</small><p>${esc((r.description || '').slice(0,130))}</p></button>`).join('') : '<div class="card-body"><p class="empty-copy">No matching records.</p></div>';
    if (state.selectedRecord && record(state.selectedRecord)) inspectRecord(record(state.selectedRecord));
  }
  function canMapFeature(f, total) {
    const location = String(f.location || '');
    if (/[<>^?:]|\border\s*\(|\bone-of\s*\(|\(\d+\.\d+\)/i.test(location)) return false;
    return Array.isArray(f.segments) && f.segments.length > 0 && f.segments.every(segment => !segment.ref && Number.isInteger(segment.start) && Number.isInteger(segment.end) && segment.start >= 0 && segment.end > segment.start && segment.end <= total);
  }
  function inspectRecord(r) {
    const features = r.features || [], total = length(r);
    const unsupportedGeometry = features.filter(f => !canMapFeature(f, total)).length;
    let svg = '<line x1="12" y1="39" x2="488" y2="39" stroke="#e8eddf" stroke-width="5"/>';
    features.forEach((f,i) => (canMapFeature(f, total) ? f.segments : []).forEach(s => {const x = 12+(total ? s.start/total*476 : 0), width = total ? (s.end-s.start)/total*476 : 0; svg += `<rect x="${x}" y="${i%2 ? 42 : 22}" width="${Math.max(1,width)}" height="13" rx="2" fill="${color(i)}"><title>${esc(f.label || f.type)} · ${esc(featureSpan(f))}</title></rect>`;}));
    svg += `<text x="12" y="81" font-size="9" fill="#91a17f">1</text><text x="488" y="81" font-size="9" text-anchor="end" fill="#91a17f">${number(total)} bp</text>`;
    const seq = r.sequence || '', lines = [];
    for (let i = 0; i < seq.length; i += 60) lines.push(`${String(i+1).padStart(7,' ')}  ${(seq.slice(i,i+60).match(/.{1,10}/g) || []).join(' ')}`);
    $('#record-inspector').innerHTML = `<div class="card-body"><div class="inspect-head"><div><span class="eyebrow">RECORD INSPECTOR</span><h2 style="margin-top:8px">${esc(r.name)}</h2></div><span class="badge muted">${esc(r.topology)}</span></div><p class="result-description">${esc(r.description)}</p><dl class="metadata-grid"><dt>Length</dt><dd>${number(total)} bp</dd><dt>Source</dt><dd>${esc(r.source?.kind || 'local')} ${r.source?.filename ? `· ${esc(r.source.filename)}` : ''}</dd><dt>Record ID</dt><dd>${esc(r.id)}</dd><dt>SHA-256</dt><dd>${esc(r.sequence_sha256 || 'Not supplied')}</dd></dl><h3>Annotation map</h3><div class="inspection-map"><svg viewBox="0 0 500 95" role="img" aria-label="Exact local feature spans on record sequence">${svg}</svg></div>${unsupportedGeometry ? `<div class="notice warning">Unsupported geometry retained in feature table: ${unsupportedGeometry} feature${unsupportedGeometry === 1 ? '' : 's'} omitted from this map.</div>` : ''}<h3>Features <span class="count">${features.length}</span></h3><p class="help">Displayed coordinates are 1-based, inclusive. Exact local spans, including joins, appear on the map. Fuzzy, remote, between-base, and order locations are retained in the feature table without inferred geometry.</p><div class="feature-table-wrap"><table><thead><tr><th>Label</th><th>Type</th><th>Location</th></tr></thead><tbody>${features.map((f,i) => `<tr><td><span class="legend-swatch" style="display:inline-block;background:${color(i)};margin-right:5px"></span>${esc(f.label || 'Unlabelled')}</td><td>${esc(f.type)}</td><td><code>${esc(f.location || featureSpan(f))}</code>${f.qualifiers && Object.keys(f.qualifiers).length ? `<details><summary>Qualifiers</summary><pre class="sequence-block">${esc(JSON.stringify(f.qualifiers,null,2))}</pre></details>` : ''}</td></tr>`).join('') || '<tr><td colspan="3">No annotated features.</td></tr>'}</tbody></table></div><h3>Sequence</h3><pre class="sequence-block">${esc(lines.join('\n'))}</pre><details class="supported-notes"><summary>Record metadata and provenance</summary><pre class="sequence-block">${esc(JSON.stringify({metadata:r.metadata,source:r.source},null,2))}</pre></details><button type="button" class="button secondary" data-use-record="${esc(r.id)}">Add to current composition +</button></div>`;
  }
  function renderConventions() {
    $('#convention-list').innerHTML = state.conventions.length ? [...state.conventions].reverse().map(c => `<section class="card convention-card"><div class="card-heading"><h2>${esc(c.name)}</h2><span class="badge ${c.state === 'active' ? 'teal' : 'amber'}">${esc(c.state)} · v${esc(c.version)}</span></div><div class="card-body"><h3 style="margin-top:0">Extracted rules</h3>${(c.rules || []).length ? `<table><tbody>${c.rules.map(r => `<tr><td>${esc(nice(r.kind))}</td><td>${esc(textValue(r.value))}</td></tr>`).join('')}</tbody></table>` : '<p class="empty-copy">No supported rules extracted.</p>'}${(c.unsupported || []).length ? `<div class="notice warning"><strong>Activation blocked: unsupported notes</strong>${c.unsupported.map(n => esc(textValue(n))).join('<br>')}</div>` : ''}<details class="supported-notes"><summary>Original notes</summary><pre>${esc(c.notes)}</pre></details>${c.state !== 'active' ? `<label class="checkbox-label"><input type="checkbox" data-review-convention="${esc(c.id)}" ${(c.unsupported || []).length ? 'disabled' : ''}>I have reviewed the extracted rules and their scope.</label><button type="button" class="button primary" data-activate="${esc(c.id)}" disabled>Activate reviewed convention</button>` : '<p class="help">Available in the design workspace. Original notes retained for review.</p>'}</div></section>`).join('') : '<section class="card"><div class="card-body"><p class="empty-copy">No conventions yet. Draft your first set of supported rules to the left.</p></div></section>';
  }
  function renderHosts() {
    $('#host-grid').innerHTML = state.hosts.map((h,i) => `<article class="host-card"><div class="host-icon">${['◎','◌','◈'][i%3]}</div><h2>${esc(h.name)}</h2><span class="badge amber">Compatibility unevaluated</span><p>${esc(h.description || 'Host context is recorded in the design and exported review packet.')}</p><p>${esc(nice(h.status || 'prototype context only'))}</p></article>`).join('');
  }
  function renderHistory() {
    $('#history-list').innerHTML = state.designs.length ? [...state.designs].sort((a,b) => String(b.created_at || '').localeCompare(String(a.created_at || ''))).map(d => `<section class="card"><div class="history-row"><div><h2>${esc(d.name)}</h2><div class="history-meta">${esc(nice(d.mode))} · ${esc(d.host_name || d.host_id)} · ${number(length(d.record))} bp<br>${esc(d.created_at ? new Date(d.created_at).toLocaleString() : '')}</div></div><div class="history-actions"><button type="button" class="button secondary" data-open-design="${esc(d.id)}">Review result</button><a class="button primary" href="${esc(safeDownload(d.files?.bundle || `/api/designs/${encodeURIComponent(d.id)}/bundle.zip`))}" download>Download bundle ↓</a></div></div></section>`).join('') : '<section class="card"><div class="card-body"><p class="empty-copy">Your first computed design will appear here with its source records, checks, and exports.</p></div></section>';
  }
  function renderComparison(c) {
    const extra = Object.entries(c).filter(([k]) => !['same_sequence','same_circular_molecule','length_delta','summary'].includes(k));
    $('#comparison-result').hidden = false;
    $('#comparison-result').innerHTML = `<div class="card-heading"><h2>Comparison result</h2><span class="badge muted">Computational comparison</span></div><div class="card-body"><div class="compare-stats"><div class="compare-stat"><strong>${c.same_sequence === true ? 'Identical' : c.same_sequence === false ? 'Different' : 'Unknown'}</strong><span>Sequence identity</span></div><div class="compare-stat"><strong>${c.same_circular_molecule === true ? 'Equivalent' : c.same_circular_molecule === false ? 'Not equivalent' : 'Not applicable'}</strong><span>Circular molecule</span></div><div class="compare-stat"><strong>${Number(c.length_delta) > 0 ? '+' : ''}${number(c.length_delta)} bp</strong><span>Length difference</span></div></div><p class="result-description">${esc(textValue(c.summary || 'Comparison complete.'))}</p>${extra.length ? `<details class="supported-notes" open><summary>Comparison details</summary><pre class="sequence-block">${esc(JSON.stringify(Object.fromEntries(extra),null,2))}</pre></details>` : ''}</div>`;
  }

  $$('.nav').forEach(el => el.addEventListener('click', () => navigate(el.dataset.page)));
  window.addEventListener('hashchange', () => navigate(location.hash.slice(1)));
  $('#refresh').onclick = () => busy($('#refresh'), async () => {await refresh(); notice('Workspace refreshed.');});
  $$('[data-mode]').forEach(el => el.onclick = () => setMode(el.dataset.mode));
  $('#design-form').addEventListener('input', invalidateBrief);
  $('#design-form').addEventListener('change', e => {invalidateBrief(); if (e.target.id === 'parent') renderParent(); if (e.target.id === 'topology') renderPreview();});
  $('#add-part').onclick = () => {const id = $('#part-picker').value; if (!record(id)) {notice('Select a record to add.', 'warning'); return;} state.parts.push(id); renderSelectedParts(); invalidateBrief();};
  $('#selected-parts').onclick = e => {const b = e.target.closest('[data-part-action]'); if (!b) return; const i = Number(b.dataset.index); if (b.dataset.partAction === 'remove') state.parts.splice(i,1); else {const j = i+(b.dataset.partAction === 'up' ? -1 : 1); if (j >= 0 && j < state.parts.length) [state.parts[i],state.parts[j]] = [state.parts[j],state.parts[i]];} renderSelectedParts(); invalidateBrief();};
  $('#review-brief').onclick = () => busy($('#review-brief'), async () => {const version = briefVersion, data = await api('/api/brief',{method:'POST',body:payload()}); if (version === briefVersion) renderBrief(data);});
  $('#design-form').onsubmit = e => {e.preventDefault(); busy($('#build-design'), async () => {const version = briefVersion; const data = await api('/api/design',{method:'POST',body:payload()}); await refresh(); if (version !== briefVersion) {notice('The submitted design was saved in history. Your inputs changed while it was computing; review the current brief before computing again.', 'warning'); return;} if (data.design.brief) renderBrief(data.design.brief); showResult(data.design); notice('Design computed and saved locally. Review the checks and assumptions before using its exports.');});};
  $('#library-search').oninput = renderLibrary;
  $('#record-list').onclick = e => {const b = e.target.closest('[data-record]'); if (b) {state.selectedRecord = b.dataset.record; renderLibrary();}};
  $('#record-inspector').onclick = e => {const b = e.target.closest('[data-use-record]'); if (b) {state.parts.push(b.dataset.useRecord); setMode('create'); renderSelectedParts(); navigate('workspace'); notice('Record added to the end of the composition.');}};
  $('#import-form').onsubmit = e => {e.preventDefault(); busy($('#import-form button[type=submit]'), async () => {const data = new FormData(); for (const file of $('#import-files').files) data.append('files',file); data.append('source',$('#import-source').value); const result = await api('/api/import',{method:'POST',body:data}); $('#import-result').innerHTML = `<div class="notice"><strong>${(result.records || []).length} record(s) imported</strong>${(result.diagnostics || []).length ? `<pre>${esc(textValue(result.diagnostics))}</pre>` : 'Original source files and provenance are retained locally.'}</div>`; await refresh(); if (result.records?.length) {state.selectedRecord = result.records[0].id; renderLibrary();} $('#import-files').value = '';});};
  $('#convention-form').onsubmit = e => {e.preventDefault(); busy($('#convention-form button[type=submit]'), async () => {await api('/api/conventions',{method:'POST',body:{name:$('#convention-name').value.trim(),notes:$('#convention-notes').value}}); await refresh(); notice('Convention drafted. Review the extracted rules before activation.');});};
  $('#convention-list').onchange = e => {if (e.target.matches('[data-review-convention]')) {const id = e.target.dataset.reviewConvention; const button = $$('[data-activate]').find(b => b.dataset.activate === id); if (button) button.disabled = !e.target.checked;}};
  $('#convention-list').onclick = e => {const b = e.target.closest('[data-activate]'); if (b) busy(b, async () => {await api(`/api/conventions/${encodeURIComponent(b.dataset.activate)}/activate`,{method:'POST',body:{reviewed:true}}); await refresh(); invalidateBrief(); notice('Reviewed convention activated. Select it in the design workspace to apply its rules.');});};
  $('#history-list').onclick = e => {const b = e.target.closest('[data-open-design]'); if (b) busy(b, async () => {const data = await api(`/api/designs/${encodeURIComponent(b.dataset.openDesign)}`); navigate('workspace'); showResult(data.design);});};
  $('#compare-form').onsubmit = e => {e.preventDefault(); busy($('#compare-form button[type=submit]'), async () => {const data = await api('/api/compare',{method:'POST',body:{left_id:$('#compare-left').value,right_id:$('#compare-right').value}}); renderComparison(data.comparison);});};
  navigate(location.hash.slice(1) || 'workspace');
  refresh().catch(error => notice(`Could not load the local workspace: ${error.message}`, 'error', error.details));
})();
