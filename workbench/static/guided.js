'use strict';
/* TGAP Guided User Study: wizard, execution and results dashboard.
   All numbers come from the server's guided run (sandbox/guided.py); this file
   only lays them out. Chart explanations are generated server-side
   (sandbox/interpret.py) so the export and the page use the same text. */

const G = {
  codeCheck: null, cat: null, step: 0, config: null, preview: null, feasibility: null, job: null, result: null,
  running: false, progress: null, started: 0, error: '', scenario: null, locked: [], snapshot: null, trajMetric: 'bridge',
};
const G_STEPS = [
  ['intro', 'Introduction'], ['dataset', 'Dataset'], ['model', 'Model & target'],
  ['transformation', 'Transformation'], ['review', 'Review & run'], ['results', 'Results'],
];
const G_STAGES = [
  ['validate', 'Validate configuration'], ['main', 'Selected explanation & local measurements'], ['matrix', 'Model × concept runs'],
  ['temporal', 'One-snapshot-at-a-time runs'], ['stability', 'Seed repeats'], ['matched', 'Matched comparison sweep'],
  ['sizes', 'Graph-size repeats'], ['structure', 'Graph comparison'], ['charts', 'Charts & explanations'],
];
// The pre-study questionnaire is now native ("Before We Begin", in the comparison study); phase 1 needs no external survey.
function gOnboard() { return {pre: true}; }
function gOnboardHtml() { return ''; }
function gWireOnboard() {}
const G_POS = '#345f92', G_NEG = '#b56c38', G_ZERO = '#8094a9', G_MUTED = '#566b82', G_INK = '#29445f', G_GRID = '#e6edf4';
pageHelp.guided = ['How the guided study works', 'Follow the six steps in order. Each step explains its choices; the panel on the right always shows your current configuration. Nothing runs until you press Run experiment on the review step. Results always belong to the run named in the provenance panel; if you change a setting afterwards, run again to update them.'];

function resetGuided() {
  // Called on sign-out so a different account never sees the previous results.
  Object.assign(G, {cat: null, step: 0, config: null, preview: null, feasibility: null, job: null, result: null, running: false,
    progress: null, error: '', scenario: null, locked: [], snapshot: null});
  if ($('guided-content')) $('guided-content').innerHTML = '';
}

/* ---------- helpers ---------- */
/* Display rule (same as the server, sandbox/easy.py): model names end in
   "model", concept and measured-property names end in "concept". */
const G_CONCEPT_RE = /\b(Bridge Width|Bridge Trend|Centralization|Density|Churn|Cohesion|Clustering)\b(?! concept| —)/g;
function gTerms(text) { return String(text ?? '').replace(G_CONCEPT_RE, '$1 concept').replace(/ model model/g, ' model'); }
const gName = {
  dataset: id => G.cat?.datasets.find(d => d.id === id)?.name || id,
  model: id => { const n = G.cat?.models.find(m => m.id === id)?.name || id; return n.endsWith(' model') ? n : n + ' model'; },
  concept: id => id === 'custom' ? 'Custom concept' : gTerms(G.cat?.concepts.find(c => c.id === id)?.name || id),
};
const gPct = d => `${+(Math.abs(d) * 100).toFixed(2)}%`;
const gSigned = d => `${d < 0 ? '−' : '+'}${gPct(d)}`;
function gStatusTag(status) {
  const map = {ok: ['success', 'computed'], partial: ['warning', 'partial'], unavailable: ['invalid', 'unavailable'], not_requested: ['', 'not requested'],
    not_applicable: ['', 'not applicable'], blocked: ['warning', 'not reproducible here'], reference: ['', 'reference']};
  const [cls, label] = map[status] || ['', status];
  return `<span class="tag ${cls}">${esc(label)}</span>`;
}
function gValidityTag(status) {
  return status === 'ok' ? '<span class="tag success">valid</span>' : `<span class="tag invalid">${esc(String(status).replaceAll('_', ' '))}</span>`;
}
function gEvent(event, step, extra = {}) {
  // The server records events only during an active, consented study session.
  if (!state.user) return;
  api('/guided/events', {method: 'POST', body: JSON.stringify({event, step, ...extra})}).catch(() => {});
}
function gNormalized(config) {
  const c = JSON.parse(JSON.stringify(config));
  delete c.scenario;
  c.sweep.deltas = [...c.sweep.deltas].sort((a, b) => a - b);
  c.sweep.models = [...c.sweep.models].sort();
  c.sweep.concepts = [...c.sweep.concepts].sort();
  return JSON.stringify(c);
}
function gResultMatchesConfig() {
  if (!G.result || !G.config) return true;
  const spec = {...G.result.guided.spec};
  delete spec.transformations;
  return gNormalized(spec) === gNormalized(G.config);
}
function gDefaults() {
  const d = G.cat.defaults;
  return {dataset: 'stable', model: 'persistence_bridge', concept: 'bridge_width', direction: d.direction, delta: d.delta, seed: d.seed,
    target_snapshot: null, custom_code: '', sweep: JSON.parse(JSON.stringify(d.sweep)), scenario: null};
}
function gDataset() { return G.cat.datasets.find(d => d.id === G.config.dataset); }

/* ---------- entry ---------- */
async function renderGuided() {
  const root = $('guided-content');
  if (!G.cat) {
    root.innerHTML = '<div class="panel"><p class="muted"><span class="busy-spinner"></span> Loading datasets, models and concepts…</p></div>';
    try {
      G.cat = await api('/guided/catalogue');
      G.config = gDefaults();
    } catch (error) {
      root.innerHTML = `<div class="panel"><p class="error-text">${esc(error.message)}</p><button class="secondary" id="g-retry">Try again</button></div>`;
      $('g-retry').onclick = () => { G.cat = null; renderGuided(); };
      return;
    }
    gLoadPreview();
  }
  // The study starts with "Before We Begin" (consent + pre-study questionnaire, shared with the CoDy comparison).
  G.needPre = typeof cxNeedsPre === 'function' && await cxNeedsPre();
  gRender();
}

function gCanVisit(i) {
  if (G.running) return i === 4;
  if (i === 5) return !!G.result;
  return true;
}

function gGo(i) {
  if (i > G.step) {
    const problem = gValidateStep(G.step);
    if (problem) { G.error = problem; gEvent('validation_error', G_STEPS[G.step][0]); gRender(); return; }
    gEvent('step_complete', G_STEPS[G.step][0]);
  }
  G.error = '';
  G.step = i;
  gRender();
  $('guided-content').scrollIntoView({block: 'start'});
}

function gValidateStep(i) {
  const c = G.config, ds = gDataset(), o = gOnboard();
  if (i === 0 && !o.pre) return 'Please fill in the pre-study survey and tick the box (step 1 above).';
  if (i >= 1 && (!ds || ds.available === false)) return 'Choose an available dataset to continue.';
  if (i >= 2) {
    if (!c.model) return 'Choose a model.';
    if (c.target_snapshot !== null && (c.target_snapshot < 1 || c.target_snapshot >= ds.snapshots)) return `Choose a target snapshot between 2 and ${ds.snapshots}.`;
  }
  if (i >= 3) {
    if (c.concept === 'custom' && !c.custom_code.trim()) return 'Write your transformation first: load the skeleton or an example.';
    if (c.concept === 'custom' && !(G.codeCheck && G.codeCheck.ok)) return 'Press "Check my code" and fix any problem before continuing.';
    if (!(c.delta >= 0.02 && c.delta <= 0.5)) return 'The requested change must be between 2% and 50%.';
    if (!c.sweep.models.length) return 'Select at least one comparison model (the paper\'s global charts need it).';
    if (!c.sweep.deltas.length) return 'Select at least one request size.';
    if (c.sweep.concepts.length === 0 && c.concept !== 'custom') return 'Select at least one comparison concept.';
    if (ds.family !== 'synthetic' && (c.sweep.variation === 'graph' || c.sweep.sizes.length)) return 'Graph-seed variation and graph sizes need a synthetic dataset.';
  }
  return '';
}

/* ---------- visual language: icons, step heroes ---------- */
const G_ICONS = {
  book: '<path d="M4 5a2 2 0 0 1 2-2h13v16H6a2 2 0 0 0-2 2z"/><path d="M4 21V5"/><path d="M9 7h6"/>',
  data: '<ellipse cx="12" cy="5" rx="8" ry="3"/><path d="M4 5v6c0 1.7 3.6 3 8 3s8-1.3 8-3V5"/><path d="M4 11v6c0 1.7 3.6 3 8 3s8-1.3 8-3v-6"/>',
  model: '<rect x="5" y="5" width="14" height="14" rx="3"/><path d="M9 9h6v6H9zM9 2v3M15 2v3M9 19v3M15 19v3M2 9h3M2 15h3M19 9h3M19 15h3"/>',
  wand: '<path d="M4 20 16 8M14 6l4 4"/><path d="M18 2v3M20.5 3.5h-5M6 2v2M7 3H5M21 13v2M22 14h-2"/>',
  code: '<path d="m8 8-5 4 5 4M16 8l5 4-5 4M14 4l-4 16"/>',
  play: '<circle cx="12" cy="12" r="9"/><path d="m10 8 6 4-6 4z"/>',
  chart: '<path d="M4 20V10M10 20V4M16 20v-7M22 20H2"/>',
  check: '<circle cx="12" cy="12" r="9"/><path d="m8 12 3 3 5-6"/>',
  info: '<circle cx="12" cy="12" r="9"/><path d="M12 11v6M12 7.5v.5"/>',
  alert: '<path d="M12 3 2 20h20z"/><path d="M12 10v4M12 17v.5"/>',
  spark: '<path d="M12 3v4M12 17v4M3 12h4M17 12h4M6 6l2.5 2.5M15.5 15.5 18 18M6 18l2.5-2.5M15.5 8.5 18 6"/>',
  clock: '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
  shield: '<path d="M12 3 4 6v6c0 5 3.5 8 8 9 4.5-1 8-4 8-9V6z"/><path d="m9 12 2 2 4-4"/>',
  target: '<circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="5"/><circle cx="12" cy="12" r="1"/>',
  graph: '<circle cx="5" cy="6" r="2"/><circle cx="19" cy="6" r="2"/><circle cx="12" cy="18" r="2"/><circle cx="12" cy="9" r="2"/><path d="M7 6.5 10.2 8.5M17 6.5l-3.2 2M12 11v5"/>',
  layers: '<path d="m12 3 9 5-9 5-9-5z"/><path d="m3 13 9 5 9-5"/>',
  download: '<path d="M12 3v12M7 10l5 5 5-5M4 21h16"/>',
  bulb: '<path d="M9 18h6M10 21h4"/><path d="M12 3a6 6 0 0 0-4 10.5c.7.7 1 1.5 1 2.5h6c0-1 .3-1.8 1-2.5A6 6 0 0 0 12 3z"/>',
  time: '<path d="M3 12h4l3-8 4 16 3-8h4"/>',
};
function gIcon(name, size = 20) {
  return `<svg class="g-icon" width="${size}" height="${size}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${G_ICONS[name] || G_ICONS.info}</svg>`;
}
const G_STEP_META = {
  intro: ['book', 'Welcome', 'Learn what TGAP does in two minutes.'],
  dataset: ['data', 'Pick a network', 'Every dataset is a sequence of snapshots of who is connected to whom.'],
  model: ['model', 'Pick a model', 'The model reads the snapshots and answers with one number.'],
  transformation: ['wand', 'Design the change', 'Choose a ready-made concept, or write your own transformation.'],
  review: ['play', 'Review and run', 'One last look, then the real pipeline runs on the server.'],
  results: ['chart', 'Your results', 'Everything TGAP measured, explained chart by chart.'],
};
function gHero(step) {
  const [icon, title, sub] = G_STEP_META[step], i = G_STEPS.findIndex(([id]) => id === step);
  return `<header class="g-hero"><div class="g-hero-icon">${gIcon(icon, 28)}</div><div><span class="eyebrow">STEP ${i + 1} OF 6</span>
    <h2 id="g-step-title" class="g-title">${esc(title)}</h2><p class="g-hero-sub">${esc(sub)}</p></div></header>`;
}
function gProse(text) {
  // Long data-driven paragraphs read better as a short list of sentences.
  const parts = String(text).split(/(?<=\.)\s+(?=[A-Z])/).filter(Boolean);
  return text.length > 220 && parts.length > 2 ? `<ul class="g-prose">${parts.map(p => `<li>${esc(p)}</li>`).join('')}</ul>` : esc(text);
}
function gTip(text, icon = 'bulb') { return `<div class="g-tip">${gIcon(icon, 18)}<p>${text}</p></div>`; }

function gHelp(title, body) {
  return `<details class="g-help"><summary>${gIcon('info', 18)} ${esc(title)}</summary><div>${body}</div></details>`;
}

function gRender() {
  const root = $('guided-content');
  if (G.needPre) {
    // The pre-study survey link comes first; every redraw keeps it until the participant continues.
    root.innerHTML = `<div class="cx-body">${cxPreLink()}</div>`;
    return cxWirePreLink(() => { G.needPre = false; gRender(); });
  }
  const step = G_STEPS[G.step][0];
  const results = step === 'results';
  const pct = Math.round(G.step / (G_STEPS.length - 1) * 100);
  root.innerHTML = `
    <div class="g-progress-wrap"><div class="g-progress-bar"><span style="width:${pct}%"></span></div>
    <ol class="g-progress" aria-label="Guided experiment progress">${G_STEPS.map(([id, label], i) => `
      <li class="${i < G.step ? 'done' : i === G.step ? 'current' : ''}" ${i === G.step ? 'aria-current="step"' : ''}>
        <button type="button" data-g-step="${i}" ${gCanVisit(i) ? '' : 'disabled'}><span>${i < G.step ? '✓' : gIcon(G_STEP_META[id][0], 15)}</span>${esc(label)}</button></li>`).join('')}
    </ol></div>
    <div class="g-layout ${results ? 'g-wide' : ''}">
      <section class="panel g-main g-animate" aria-labelledby="g-step-title">${gStepHtml(step)}</section>
      ${results ? '' : `<aside class="panel g-summary" aria-label="Experiment configuration">${gSummaryHtml()}</aside>`}
    </div>`;
  root.querySelectorAll('[data-g-step]').forEach(b => b.onclick = () => gGo(Number(b.dataset.gStep)));
  gWire(step);
  gEvent('step_enter', step, G.scenario ? {scenario: G.scenario} : {});
}

function gHeroArt() {
  // Animated two-community network: one new bridge is drawn, then the "model" answers.
  const a = [[60, 70], [95, 40], [120, 95], [80, 130], [140, 55]], b = [[260, 60], [300, 40], [320, 95], [280, 130], [235, 105]];
  const edges = [[0, 1], [0, 2], [1, 4], [2, 3], [2, 4], [0, 3]];
  let s = '<svg viewBox="0 0 380 170" class="g-hero-art" aria-hidden="true">';
  for (const [i, j] of edges) s += `<line x1="${a[i][0]}" y1="${a[i][1]}" x2="${a[j][0]}" y2="${a[j][1]}" class="e"/><line x1="${b[i][0]}" y1="${b[i][1]}" x2="${b[j][0]}" y2="${b[j][1]}" class="e"/>`;
  s += `<line x1="${a[4][0]}" y1="${a[4][1]}" x2="${b[4][0]}" y2="${b[4][1]}" class="e bridge"/><line x1="${a[2][0]}" y1="${a[2][1]}" x2="${b[4][0]}" y2="${b[4][1]}" class="e new"/>`;
  a.forEach(([x, y], i) => { s += `<circle cx="${x}" cy="${y}" r="${i === 2 ? 9 : 7}" class="n c1" style="animation-delay:${i * .15}s"/>`; });
  b.forEach(([x, y], i) => { s += `<circle cx="${x}" cy="${y}" r="${i === 4 ? 9 : 7}" class="n c2" style="animation-delay:${.75 + i * .15}s"/>`; });
  return s + '<text x="190" y="160" text-anchor="middle" class="t">+1 bridge → the model answers again</text></svg>';
}

function gIntroHtml() {
  const stable = G.preview?.spec?.dataset === 'stable' ? G.preview.outputs.find(o => o.model === 'persistence_bridge')?.prediction : null;
  const recording = state.study && !state.study.finished;
  const timing = Object.entries(G.cat.timing || {});
  const how = [['graph', 'Take a network', 'A real or synthetic network, observed as snapshots over time.'],
    ['wand', 'Change one idea', 'For example: "10% more ties between the two groups".'],
    ['model', 'Ask the model again', 'The same model predicts on the changed network.'],
    ['chart', 'Compare', 'How much did the answer move per unit of real change?']];
  return `${gHero('intro')}
    ${gOnboardHtml()}
    <div class="g-welcome">
      <div><h3 class="g-welcome-title">What does a graph model really react to?</h3>
        <p class="g-lead">TGAP answers this by <b>changing one human-readable idea</b> in a network — such as how many ties connect two communities — and watching how the model's prediction responds. In about 10 minutes you will design, run and read your own experiment.</p>
        <div class="g-pills"><span>${gIcon('clock', 16)} ~10 minutes</span><span>${gIcon('shield', 16)} real research pipeline</span><span>${gIcon('chart', 16)} 24 charts explained</span></div></div>
      ${gHeroArt()}
    </div>
    <h3 class="g-sub">${gIcon('spark', 18)} How TGAP works, in four moves</h3>
    <div class="g-how">${how.map(([icon, t, d], i) => `<article style="animation-delay:${i * .08}s"><div class="g-how-icon">${gIcon(icon, 24)}</div><b>${i + 1}. ${t}</b><p>${d}</p></article>`).join('')}</div>
    <h3 class="g-sub">${gIcon('book', 18)} Four words you will meet</h3>
    <div class="g-terms">
      <div><b>Temporal graph</b><p>Snapshots of a network in time order — like monthly photos of who talks to whom. Nodes are split into fixed communities.</p></div>
      <div><b>Prediction</b><p>One number the model returns, e.g. "how many ties cross between the groups right now" or a forecast of the next snapshot.</p></div>
      <div><b>Transformation</b><p>A controlled edit of one concept. Graphs change in whole edges, so the <i>achieved</i> change can differ from the <i>requested</i> one — TGAP measures both.</p></div>
      <div><b>Validity</b><p>Some edits cannot be done faithfully. Those results are clearly marked <span class="tag invalid">invalid</span> and never used for conclusions.</p></div>
    </div>
    <div class="g-example">${gIcon('bulb', 22)}<div><b>A tiny example</b><p>In the <b>Stable ecosystem</b>, the <b>Present · bridge width</b> model counts ties between the two communities in the latest snapshot${stable !== null && stable !== undefined ? ` — right now it answers <b class="g-num">${esc(number(stable))}</b>` : ''}. Ask for <b>+10% Bridge Width</b>: TGAP adds a cross-community tie (and removes an internal one to keep the total), runs the model again and divides the change in the answer by the change it actually achieved.</p></div></div>
    <div class="reading-note"><span class="note-symbol">i</span><div><strong>A model's response — not a law of nature.</strong><p>TGAP shows how the selected <i>model</i> reacts to a controlled change. It does not prove that the change would cause anything in the real network.</p></div></div>
    ${G.cat.scenarios.length ? `<h3 class="g-sub">${gIcon('layers', 18)} Quick start: use a ready-made scenario (optional)</h3><div class="g-scenarios">${G.cat.scenarios.map(s => `
      <article class="g-scenario ${G.scenario === s.id ? 'selected' : ''}"><div class="g-scenario-icon">${gIcon(s.id.startsWith('paper') ? 'book' : 'target', 22)}</div><h4>${esc(s.title)}</h4><p>${esc(s.description)}</p><button type="button" class="secondary" data-g-scenario="${esc(s.id)}">${G.scenario === s.id ? '✓ Selected' : 'Use this scenario'}</button></article>`).join('')}</div>
      ${G.scenario ? '<button type="button" class="text-button" id="g-clear-scenario">Clear scenario and use defaults</button>' : ''}` : ''}
    <p class="field-help g-foot">${gIcon('clock', 14)} ${timing.length ? `Measured on this server: ${timing.map(([id, t]) => `${esc(gName.dataset(id))} ≈ ${t.median_seconds}s`).join(' · ')}. ` : ''}Runs stop after ${G.cat.limits.seconds} s at most.
      ${recording ? `<br>${gIcon('shield', 14)} You are in study session <b>${esc(state.study.participant)}</b>: your steps in this experiment are recorded under that pseudonymous ID.` : `<br>${gIcon('shield', 14)} No study session is active, so nothing about your clicks is recorded.`}</p>
    ${gNav(null, 1, "Let's begin")}`;
}

function gCustomPanel() {
  const cu = G.cat.custom, c = G.config, v = G.codeCheck;
  return `<div class="g-custom g-animate">
    <div class="g-custom-steps"><div><span>1</span><b>Start</b><p>Load the skeleton or an example.</p></div><div><span>2</span><b>Edit</b><p>Fill in how to measure and how to change your concept.</p></div><div><span>3</span><b>Check</b><p>Press <i>Check my code</i> — then continue.</p></div></div>
    <h3 class="g-sub">${gIcon('layers', 18)} Start from…</h3>
    <div class="g-samples">
      <article class="g-sample"><span class="tag">Skeleton</span><h4>Empty skeleton</h4><p>A commented template with five numbered places to fill in. It runs as-is (and changes nothing).</p><button type="button" class="secondary" data-g-sample="__skeleton">Load skeleton</button></article>
      ${cu.samples.map(s => `<article class="g-sample"><span class="tag ${s.level === 'Beginner' ? 'success' : s.level === 'Advanced' ? 'warning' : ''}">${esc(s.level)}</span><h4>${esc(s.title)}</h4><p>${esc(s.idea)}</p><button type="button" class="secondary" data-g-sample="${esc(s.id)}">Load example</button></article>`).join('')}
    </div>
    <div class="g-editor-wrap">
      <div class="g-editor-head">${gIcon('code', 18)} <b>Your transformation</b><span>Python subset · interpreted safely in an isolated worker</span>
        <button type="button" class="primary" id="g-check-code">${gIcon('check', 16)} Check my code</button></div>
      <label for="g-custom-code" class="sr-only">Custom transformation code</label>
      <textarea id="g-custom-code" spellcheck="false" rows="22" placeholder="Load the skeleton or an example to begin.">${esc(c.custom_code)}</textarea>
      <div class="g-check-result" aria-live="polite">${!v ? '<p class="field-help">Tip: press Tab to indent. Your code is checked again on the server before it runs.</p>' : v.loading ? '<p class="field-help"><span class="busy-spinner"></span> Checking…</p>' : v.ok
        ? `<div class="g-ok">${gIcon('check', 18)}<div><b>${esc(v.message)}</b><p>Concept <b>${esc(v.details.name)}</b> · class ${esc(v.details.class_name)} · ${esc(v.details.delta_mode)} change · uses ${esc(v.details.entry)} · edge count ${v.details.preserves_edge_count ? 'preserved' : 'may change'}</p></div></div>`
        : `<div class="g-bad">${gIcon('alert', 18)}<div><b>Not ready yet</b><p>${esc(v.message)}</p></div></div>`}</div>
    </div>
    <div class="g-cards-2">
      <article class="g-explain"><h3>${gIcon('shield', 18)} Five rules</h3><ol class="g-rules">${cu.rules.map(r => `<li>${esc(r)}</li>`).join('')}</ol></article>
      <article class="g-explain"><h3>${gIcon('book', 18)} What goes in, what comes out</h3>
        <p><b>propertyValue(self, x)</b> — receives one graph <i>or</i> the list of snapshots, returns <b>one number</b>: your concept's value.</p>
        <p><b>transformGraph(self, graph, delta)</b> — receives one snapshot, returns a <b>new</b> graph. TGAP applies it to every snapshot.</p>
        <p><b>transform(self, graphs, delta)</b> — <i>optional</i> instead: receives all snapshots, returns the same number of new snapshots (for temporal ideas).</p>
        <p><b>delta</b> — positive means increase, negative means decrease; 0.1 = 10%.</p></article>
    </div>
    <details class="g-help"><summary>${gIcon('code', 18)} Quick reference: everything you can call</summary><div class="g-api">${cu.api.map(([t, items]) => `<div><b>${esc(t)}</b><ul>${items.map(i => `<li><code>${esc(i)}</code></li>`).join('')}</ul></div>`).join('')}</div></details>
  </div>`;
}

function gTransformationHtml() {
  const c = G.config, ds = gDataset(), s = c.sweep, synthetic = ds.family === 'synthetic', custom = c.concept === 'custom';
  const concept = G.cat.concepts.find(t => t.id === c.concept);
  const current = G.preview && !G.preview.loading && concept ? G.preview.concepts.find(x => x.id === c.concept)?.value : null;
  const f = G.feasibility;
  let requested = '';
  if (concept && current !== null && current !== undefined) {
    if (concept.id === 'centralization') requested = `Rewire about ${gPct(c.delta)} of edges ${c.direction === 'increase' ? 'toward' : 'away from'} hubs (current centralization ${number(current)}).`;
    else if (concept.delta_mode === 'absolute') requested = `Request ${gSigned(c.direction === 'increase' ? c.delta : -c.delta)}; the achieved change is measured in slope units (current slope ${number(current)}).`;
    else requested = `${concept.name}: ${number(current)} → about ${number(current * (1 + (c.direction === 'increase' ? c.delta : -c.delta)))} requested. The real achieved value is measured during the run.`;
  }
  const deltaChip = d => `<label class="g-chip"><input type="checkbox" name="g-sweep-delta" value="${d}" ${s.deltas.includes(d) ? 'checked' : ''}>${gPct(d)}</label>`;
  const paper = G.cat.defaults.paper_deltas, extraDeltas = s.deltas.filter(d => !paper.includes(d));
  return `${gHero('transformation')}
    ${custom ? `<div class="g-optional-head"><span class="tag">Optional extra</span><p class="g-lead">You are writing your own concept in Python.</p>
        <button type="button" class="secondary" data-g-mode="builtin">← Back to the ready-made concepts</button></div>${gCustomPanel()}`
      : `<p class="g-lead">Choose the graph concept TGAP should change.</p>
        <h3 class="g-sub">${gIcon('wand', 18)} Choose a concept</h3><div class="g-card-grid g-animate">${G.cat.concepts.map(gConceptCard).join('')}</div>
        <aside class="g-optional"><span class="g-optional-icon">${gIcon('code', 24)}</span><div><span class="tag">Optional · not needed for the study</span>
          <b>Curious? Write your own concept in Python</b><p>You can define a new graph idea in a few lines of Python and test it the same way. This is an extra: skip it now and come back to try it after the study.</p></div>
          <button type="button" class="secondary" data-g-mode="custom">Try it</button></aside>`}
    <h3 class="g-sub">${gIcon('target', 18)} Direction and size</h3>
    <div class="g-dir">
      ${['increase', 'decrease'].map(d => `<label class="g-dir-card ${c.direction === d ? 'selected' : ''}"><input type="radio" name="g-direction" value="${d}" ${c.direction === d ? 'checked' : ''} ${G.locked.includes('direction') ? 'disabled' : ''}><span class="g-dir-arrow">${d === 'increase' ? '▲' : '▼'}</span><b>${d === 'increase' ? 'Increase' : 'Decrease'}</b><small>${d === 'increase' ? 'more of the concept' : 'less of the concept'}</small></label>`).join('')}
      <div class="g-size"><label for="g-delta">Requested size</label><div class="g-size-row"><input type="range" id="g-delta" min="2" max="50" step="1" value="${Math.round(c.delta * 100)}" ${G.locked.includes('delta') ? 'disabled' : ''}><output for="g-delta">${gPct(c.delta)}</output></div><small>Both directions are always measured; your choice is the headline result.</small></div>
    </div>
    ${requested ? `<div class="g-callout">${gIcon('target', 18)} <span><b>Requested:</b> ${esc(requested)}</span></div>` : ''}
    <div class="g-feasibility" aria-live="polite">${custom ? gTip('Custom concepts are checked for validity when the experiment runs. Use <i>Check my code</i> above first.', 'info') : !f ? '' : f.loading ? '<p class="field-help"><span class="busy-spinner"></span> Checking whether this change is possible on your graph…</p>' : f.error ? `<p class="error-text">${esc(f.error)}</p>` : `
      <div class="g-feas-grid">${f.directions.map(d => `<div class="g-feas ${d.status === 'ok' ? 'ok' : 'bad'} ${d.direction === c.direction ? 'mine' : ''}">${gIcon(d.status === 'ok' ? 'check' : 'alert', 20)}<div><b>${d.direction === 'increase' ? 'Increase' : 'Decrease'}: ${d.status === 'ok' ? 'possible' : esc(d.status.replaceAll('_', ' '))}</b><p>${d.reason ? esc(d.reason) : d.status === 'ok' ? 'Can be done while keeping the declared constraints.' : ''}</p></div></div>`).join('')}</div>
      ${f.directions.find(d => d.direction === c.direction)?.status !== 'ok' ? `<div class="g-warn">${gIcon('alert', 16)}<span>Your chosen direction cannot be done faithfully at this size. You can still run it to see why — it just won't support conclusions. Try another size or direction.</span></div>` : ''}`}</div>
    <details class="g-extra"><summary>${gIcon('layers', 18)} <b>Extra runs for the paper's charts</b> <span>${gPlan().rows} result rows planned · defaults follow the paper — open to adjust</span></summary>
    <p class="field-help">Some paper charts compare several models, concepts or sizes. These settings decide which extra runs happen.</p>
    <div class="g-sweep">
      <fieldset><legend>Comparison models <span>Figs 2–4, 8, 11</span></legend>${G.cat.models.map(m => `<label class="g-check"><input type="checkbox" name="g-sweep-model" value="${esc(m.id)}" ${s.models.includes(m.id) || m.id === c.model ? 'checked' : ''} ${m.id === c.model ? 'disabled' : ''}>${esc(m.name)}${m.id === c.model ? ' (yours)' : ''}</label>`).join('')}</fieldset>
      <fieldset><legend>Comparison concepts <span>Figs 2–4, 11 · Table 5</span></legend>${G.cat.concepts.map(t => `<label class="g-check"><input type="checkbox" name="g-sweep-concept" value="${esc(t.id)}" ${s.concepts.includes(t.id) || t.id === c.concept ? 'checked' : ''} ${t.id === c.concept ? 'disabled' : ''}>${esc(t.name)}${t.id === c.concept ? ' (yours)' : ''}</label>`).join('')}</fieldset>
      <fieldset><legend>Request sizes <span>RQ5, RQ8</span></legend><div class="g-chips">${paper.map(deltaChip).join('')}${extraDeltas.map(deltaChip).join('')}</div>
        <div class="g-row g-tight"><label for="g-add-delta">Add size (%)</label><input id="g-add-delta" type="number" min="2" max="90" step="1" placeholder="e.g. 5"><button type="button" class="text-button" id="g-add-delta-btn">Add</button></div>
        <p class="field-help">Your size (${gPct(c.delta)}) is always included. Up to 5.</p></fieldset>
      <fieldset><legend>Seed repeats <span>RQ3 stability</span></legend>
        <div class="g-row g-tight"><label for="g-repeats">Extra seeds</label><input id="g-repeats" type="number" min="0" max="${G.cat.limits.max_repeats}" value="${s.repeats}"></div>
        <div class="g-segment"><label><input type="radio" name="g-variation" value="transformation" ${s.variation === 'transformation' ? 'checked' : ''}>Transformation seed</label>
        <label class="${synthetic ? '' : 'disabled'}"><input type="radio" name="g-variation" value="graph" ${s.variation === 'graph' ? 'checked' : ''} ${synthetic ? '' : 'disabled'}>Graph seed${synthetic ? '' : ' (synthetic only)'}</label></div></fieldset>
      <fieldset><legend>Graph sizes <span>RQ7 · synthetic only</span></legend>${synthetic ? `<div class="g-chips">${G.cat.defaults.size_choices.map(n => `<label class="g-chip"><input type="checkbox" name="g-size" value="${n}" ${s.sizes.includes(n) ? 'checked' : ''}>${n}/group</label>`).join('')}</div>` : '<p class="field-help">Not available: real networks have a fixed set of nodes.</p>'}</fieldset>
      <fieldset><legend>Matched comparison <span>RQ1b · slower</span></legend><label class="g-check"><input type="checkbox" id="g-matched" ${s.matched ? 'checked' : ''}>Compare concepts only at matched actual changes</label></fieldset>
      <fieldset><legend>Random seed</legend><div class="g-row g-tight"><label for="g-seed">Seed</label><input id="g-seed" type="number" min="0" max="100000" value="${c.seed}" ${G.locked.includes('seed') ? 'disabled' : ''}></div><p class="field-help">Same settings + same seed = same result.</p></fieldset>
    </div></details>
    ${gNav(2, 4)}`;
}

function gRunningHtml() {
  const current = G.progress?.stage;
  const index = Math.max(0, G_STAGES.findIndex(([id]) => id === current));
  const elapsed = Math.round((Date.now() - G.started) / 1000);
  const pct = Math.round((index + .5) / G_STAGES.length * 100);
  return `<div class="g-running">
    <div class="g-orbit" aria-hidden="true"><span></span><span></span><span></span>${gIcon('graph', 34)}</div>
    <span class="eyebrow">RUNNING ON THE SERVER</span><h2 id="g-step-title" class="g-title">Your experiment is in progress</h2>
    <p class="g-lead">${esc(G.progress?.message || 'Queued — waiting for a free worker…')}</p>
    <div class="g-progress-bar g-big"><span style="width:${pct}%"></span></div>
    <ol class="g-stages">${G_STAGES.map(([id, label], i) => `<li class="${i < index ? 'done' : i === index ? 'current' : ''}"><span>${i < index ? '✓' : i === index ? '<span class="busy-spinner"></span>' : i + 1}</span>${esc(label)}</li>`).join('')}</ol>
    <p class="field-help" id="g-elapsed">${elapsed}s elapsed · stages you did not request are skipped.</p>
    ${gTip('While you wait: the headline result will be the change in the model\'s answer divided by the change TGAP <i>actually achieved</i> in your concept.')}</div>`;
}

const G_GROUP_ICON = {changed: 'graph', response: 'layers', time: 'time', reliable: 'shield', work: 'spark', reference: 'book'};
const G_PART_ICON = {what: 'info', conditions: 'layers', observations: 'chart', pattern: 'spark', conclusion: 'check', caution: 'alert'};

function gHeadline(g) {
  const p = g.primary, verb = g.spec.direction === 'increase' ? 'Increasing' : 'Decreasing';
  if (!p.valid_for_analysis) return `${verb} <b>${esc(g.selected_concept)}</b> could not be done faithfully on this network (${esc(p.status.replaceAll('_', ' '))}), so this request gives no valid answer.`;
  if (p.noop) return `${verb} <b>${esc(g.selected_concept)}</b> by ${gPct(g.spec.delta)} changed nothing in this network (a no-op).`;
  const ach = p.achieved_delta === null ? '' : p.delta_mode === 'relative' ? ` (actually ${number(p.achieved_delta * 100, true)}%)` : ` (actually ${number(p.achieved_delta, true)})`;
  const tc = g.target_check;
  if (tc && tc.against) return `${verb} <b>${esc(g.selected_concept)}</b>${esc(ach)} worked on average, but in the snapshot the model reads (${esc(tc.label)}) it went the other way, from <b>${esc(number(tc.before))}</b> to <b>${esc(number(tc.after))}</b>. The answer moved from <b>${esc(number(p.baseline))}</b> to <b>${esc(number(p.prediction))}</b> because of that, so this impact (${esc(number(p.impact, true))}) does not describe your request.`;
  if (!p.prediction_change) return `${verb} <b>${esc(g.selected_concept)}</b>${esc(ach)} left the model's answer unchanged at <b>${esc(number(p.baseline))}</b>.`;
  return `${verb} <b>${esc(g.selected_concept)}</b>${esc(ach)} moved the model's answer from <b>${esc(number(p.baseline))}</b> to <b>${esc(number(p.prediction))}</b> — a sensitivity of <b>${esc(number(p.impact, true))}</b> per unit of achieved change.`;
}

function gResultsHtml() {
  const r = G.result, g = r.guided, spec = g.spec, prim = g.primary, st = g.experiment_status;
  const ds = G.cat.datasets.find(d => d.id === spec.dataset), model = G.cat.models.find(m => m.id === spec.model);
  const charts = Object.fromEntries(g.charts.map(c => [c.id, c]));
  const statusClass = {responded: 'success', no_response: 'warning', no_op: 'warning', invalid: 'invalid', target_against: 'warning'}[st.code];
  const statusIcon = {responded: 'check', no_response: 'info', no_op: 'info', invalid: 'alert', target_against: 'alert'}[st.code];
  const other = r.rows.find(x => x.concept === g.selected_concept && x.direction !== spec.direction);
  const card = (icon, label, value, note = '', accent = '') => `<div class="g-stat ${accent}"><span class="stat-label">${gIcon(icon, 15)} ${esc(label)}</span><span class="stat-value">${value}</span>${note ? `<small>${note}</small>` : ''}</div>`;
  const groups = G.cat.inventory.groups.filter(gr => gr.id !== 'reference');
  const counts = st.matrix_counts;
  const computed = g.charts.filter(c => ['ok', 'partial'].includes(c.status)).length;
  const toc = [['g-sec-a', 'chart', 'Summary'], ['g-sec-d', 'layers', 'Explore more results'], ['g-sec-ref', 'book', 'References'], ['g-sec-f', 'check', 'Conclusion'], ['g-sec-g', 'download', 'Export']];
  const intro = (text) => `<p class="g-sec-intro">${gIcon('info', 16)}<span>${text}</span></p>`;
  return `<div class="g-results" id="g-report">
    ${gHero('results')}
    <div class="g-headline g-${statusClass}"><div class="g-headline-icon">${gIcon(statusIcon, 30)}</div><div><span class="eyebrow">THE HEADLINE</span><p>${gHeadline(g)}</p>
      <small>${esc(st.label)}${st.partial ? ' · partial' : ''} · ${esc(ds?.name || spec.dataset)} · ${esc(model?.name || spec.model)} · run ${esc(G.job.slice(0, 8))} · ${g.seconds}s · ${computed} charts computed</small></div></div>
    ${gResultMatchesConfig() ? '' : `<div class="g-stale" role="alert">${gIcon('alert', 18)} <span><b>These results belong to an earlier configuration.</b> You changed settings after this run; every number below refers to the run in the provenance panel. Go to <i>Review & run</i> to compute new results.</span></div>`}
    ${st.partial ? `<div class="g-stale" role="alert">${gIcon('alert', 18)} <span><b>Partial result.</b> These stages failed: ${esc(st.failed_stages.join(', '))}. Dependent charts are marked unavailable and excluded from the conclusion.</span></div>` : ''}
    <nav class="g-toc" aria-label="Results sections">${toc.map(([id, icon, label]) => `<a href="#${id}" data-g-jump="${id}">${gIcon(icon, 15)} ${label}</a>`).join('')}</nav>
    <section class="g-section" id="g-sec-a"><h3><span class="g-sec-letter">A</span> Experiment summary</h3>
      ${intro('The key numbers of your run. <b>Original output</b> is the model\'s answer on the real network; <b>Modified output</b> is its answer after the change; the <b>impact</b> divides the difference by the change actually achieved.')}
      <div class="g-stats">
        ${card('data', 'Dataset', esc(ds?.name || spec.dataset), `${r.summary.nodes} nodes · ${r.summary.snapshots} snapshots used`)}
        ${card('model', 'Model', esc(model?.name || spec.model), esc(model?.output || ''))}
        ${card('wand', 'Concept', esc(g.selected_concept), esc(spec.concept === 'custom' ? 'your custom transformation' : (G.cat.concepts.find(t => t.id === spec.concept)?.kind || '')))}
        ${card('target', 'Requested', `${spec.direction === 'increase' ? '▲' : '▼'} ${gPct(spec.delta)}`, 'what you asked for')}
        ${card('check', 'Achieved', prim.valid_for_analysis ? esc(prim.achieved_delta === null ? 'unmeasured' : prim.delta_mode === 'relative' ? number(prim.achieved_delta * 100, true) + '%' : number(prim.achieved_delta, true)) : '—', prim.valid_for_analysis ? 'what really happened' : `excluded: ${esc(prim.status.replaceAll('_', ' '))}`)}
        ${card('chart', 'Original output', esc(number(prim.baseline)), esc(model?.unit || ''))}
        ${card('chart', 'Modified output', prim.valid_for_analysis ? esc(number(prim.prediction)) : '—', prim.valid_for_analysis ? esc(model?.unit || '') : 'not reported for invalid runs')}
        ${card('spark', 'Impact', prim.valid_for_analysis ? esc(number(prim.impact, true)) : '—', prim.valid_for_analysis ? `answer changed by ${esc(number(prim.prediction_change, true))}${prim.noop ? ' · no-op' : ''}` : '', 'g-accent')}
        ${card('time', 'Opposite direction', other ? (other.valid_for_analysis ? esc(number(other.impact, true)) : 'excluded') : '—', other ? (other.valid_for_analysis ? 'impact' : esc(other.status.replaceAll('_', ' '))) : '')}
        ${card('shield', 'All tested rows', `${counts.valid}/${counts.total}`, `valid · ${counts.invalid} invalid · ${counts.noop} no-op`)}
      </div>
      <p class="field-help">Impact = (modified − original) ÷ |achieved change| (paper Eq. 10). All model outputs here are numbers, so a numerical difference is the right comparison.</p>
    </section>
    <section class="g-section" id="g-sec-d"><h3><span class="g-sec-letter">B</span> Explore More TGAP Results</h3>
      ${intro('The following charts explore the experiment from different angles. You do not need to open every chart. Choose any chart that interests you to see what it measures and what the results mean.')}
      ${groups.map(gr => {
        const items = g.charts.filter(c => c.group === gr.id);
        return items.length ? `<details class="g-group" id="g-group-${gr.id}"><summary><span class="g-group-icon">${gIcon(G_GROUP_ICON[gr.id], 20)}</span><span><b>${esc(gr.title)}</b><small>${esc(gr.description)} · ${items.length} chart${items.length > 1 ? 's' : ''}</small></span></summary>${items.map(gChartCard).join('')}</details>` : '';
      }).join('')}
    </section>
    <section class="g-section" id="g-sec-ref"><h3><span class="g-sec-letter">C</span> Static figures and published references</h3>
      ${intro('Illustrations and published results that cannot be recomputed in the browser. Anything framed in a dashed gold border is <b>from the paper, not from your run</b>.')}
      ${g.charts.filter(c => c.group === 'reference').map(gChartCard).join('')}
    </section>
    <section class="g-section g-conclusion" id="g-sec-f"><h3>${gIcon('check', 22)} Overall Experiment Conclusion</h3>${gConclusionHtml(r, g)}</section>
    <section class="g-section" id="g-sec-g"><h3><span class="g-sec-letter">D</span> Reproducibility and export</h3>
      <div class="g-exports">
        <a class="g-export" href="/api/guided/experiments/${esc(G.job)}/download/json" data-g-export="json">${gIcon('data', 22)}<b>Full data</b><small>JSON · every measurement</small></a>
        <a class="g-export" href="/api/guided/experiments/${esc(G.job)}/download/csv" data-g-export="csv">${gIcon('layers', 22)}<b>Table</b><small>CSV · measurements & explanations</small></a>
        <button type="button" class="g-export" id="g-report-html">${gIcon('book', 22)}<b>Report</b><small>HTML · charts, text, conclusion</small></button>
        <button type="button" class="g-export" id="g-print">${gIcon('download', 22)}<b>PDF</b><small>Print or save this page</small></button>
      </div>
      <details class="g-provenance"><summary>${gIcon('shield', 16)} Configuration and provenance (everything needed to reproduce this run)</summary>
        <table class="g-review"><tbody>${gProvenanceRows(g).map(([k, v]) => `<tr><th>${esc(k)}</th><td>${v}</td></tr>`).join('')}</tbody></table>
        <details><summary>Generated Python program</summary><pre class="g-code">${esc(r.program)}</pre></details>
      </details>
    </section>
    <section class="g-phase2"><div class="g-phase2-art" aria-hidden="true"><span>TGAP</span><i>⇄</i><span>CoDy</span></div>
      <div><span class="eyebrow">PHASE 2 · ABOUT 5 MINUTES</span><h3>Now let’s compare TGAP with another explainer</h3>
        <p>You have seen how TGAP explains a model. Next, see TGAP and <b>CoDy</b>, a recent counterfactual explainer, explain the <b>same prediction</b> of a real trained neural network, first one by one, then side by side. The post-study survey follows at the end.</p>
        <a class="primary g-phase2-btn" href="#compare">Let’s compare with CoDy →</a></div></section>
    <div class="g-nav"><button type="button" class="secondary" data-g-go="3">← Try another change</button><button type="button" class="secondary" data-g-go="1">Start a new experiment</button></div>
  </div>`;
}

function gChartCard(chart) {
  if (!chart) return '';
  const id = 'g-fig-' + chart.id;
  let svg = '';
  if (chart.status === 'ok' || chart.status === 'partial') {
    G.currentChart = chart;   // gFrame draws this chart's axis/colour key inside the SVG
    try { svg = gRender_[chart.renderer] ? gRender_[chart.renderer](chart) : ''; }
    catch (error) { svg = `<p class="error-text">This chart could not be drawn (${esc(error.message)}). Its data remain in the JSON export.</p>`; }
    finally { G.currentChart = null; }
  }
  const published = chart.paper_figure && G.cat.inventory.charts.find(i => i.id === chart.id);
  const reference = chart.paper_figure && (chart.kind === 'blocked' || chart.kind === 'static');
  const hasSvg = svg.includes('<svg');
  const prov = chart.provenance === 'published' ? '<span class="g-prov pub">PUBLISHED REFERENCE — NOT YOUR RESULT</span>'
    : chart.provenance === 'requested sweep' ? '<span class="g-prov sweep">Your run · requested comparisons</span>' : '<span class="g-prov run">Your run</span>';
  const metric = chart.metric && G.cat.glossary?.metrics?.[chart.metric];
  const usable = chart.status === 'ok' || chart.status === 'partial';
  const group = (G.cat.inventory?.groups || []).find(gr => gr.id === chart.group);
  return `<details class="figure-card g-chart" id="chart-${esc(chart.id)}" data-chart="${esc(chart.id)}">
    <summary class="g-chart-head"><span class="g-chart-icon">${gIcon(G_GROUP_ICON[chart.group] || 'chart', 20)}</span>
      <div class="g-chart-titles"><h4>${esc(chart.title)}</h4>${chart.question ? `<p class="g-question">${esc(chart.question)}</p>` : ''}
        <div class="g-chart-tags">${group ? `<span class="tag">${esc(group.title)}</span>` : ''}${prov}${chart.status_label ? `<span class="g-prov status">${esc(chart.status_label)}</span>` : ''}</div></div>
      <span class="g-chev" aria-hidden="true">▾</span></summary>
    <div class="g-chart-body">
    ${chart.subtitle && chart.provenance !== 'published' ? `<p class="g-subtitle">${esc(chart.subtitle)}</p>` : ''}
    <div class="g-chart-tags">${metric ? `<span class="tag" title="${esc(metric.definition)}">Measured: ${esc(metric.name)}</span>` : ''}<span class="tag g-paper-tag">${gIcon('book', 12)} ${esc(chart.paper)}</span>
      ${hasSvg ? `<span class="figure-downloads"><button type="button" class="text-button" data-g-svg="${id}">SVG</button><button type="button" class="text-button" data-g-png="${id}">PNG</button></span>` : ''}</div>
    ${chart.scope ? `<p class="g-scope">${gIcon('info', 14)}<span>${esc(chart.scope)}</span></p>` : ''}
    ${chart.deviation ? `<p class="g-deviation">${gIcon('alert', 14)}<span><b>Different from the paper:</b> ${esc(chart.deviation)}</span></p>` : ''}
    ${!usable ? `<p class="g-status-note">${esc(chart.status_label || chart.status)}: ${esc(chart.explanation.observations)}</p>` : ''}
    ${svg ? `<div class="figure-canvas" id="${id}">${svg}</div>` : ''}
    ${hasSvg && !svg.includes('↔ Across:') ? gGuideHtml(chart.guide) : ''}
    ${chart.explanation.easy_shows ? `<div class="g-easy">
      <p><b>How to read this chart:</b> ${esc(chart.explanation.easy_shows)}</p>
      <p class="g-finding"><b>What did we find?</b> ${esc(chart.explanation.easy_result)}</p>
      ${usable ? `<p class="g-limit"><b>What it cannot tell us:</b> ${esc(chart.explanation.caution)}</p>` : ''}</div>` : ''}
    ${reference ? `<div class="g-published"><span class="g-published-label">${gIcon('book', 14)} PUBLISHED REFERENCE · NOT YOUR RESULT</span><img src="/api/publication/${esc(chart.paper_figure)}/png" alt="Published paper figure: ${esc(published?.caption || chart.title)}" loading="lazy"><p>${esc(published?.caption || '')}</p></div>` : ''}
    <details class="g-explanation"><summary>${gIcon('spark', 16)} Technical details</summary>
      ${metric ? `<p><b>${esc(metric.name)}</b> — ${esc(metric.definition)}. Unit: ${esc(metric.unit)}. ${esc(metric.reading)} Higher is ${metric.better === 'depends' ? 'not simply better or worse: it depends on the question' : esc(metric.better === 'higher' ? 'better' : 'worse')}. Formula: <code>${esc(metric.formula)}</code></p>` : ''}
      <p class="field-help">Technical name: ${esc(chart.technical_title || '')} · ${esc(chart.paper)} · axes: ${esc(chart.axes)}</p>
      <dl>${G_PARTS.filter(([k]) => k !== 'what').map(([k, label]) => `<dt>${gIcon(G_PART_ICON[k], 15)} ${label}</dt><dd>${gProse(chart.explanation[k])}</dd>`).join('')}</dl></details>
    </div></details>`;
}

function gGuideHtml(guide) {
  // HTML version of the key, for charts drawn without gFrame (diagrams, heatmaps reused from the Laboratory).
  if (!guide || (!guide.x && !guide.y && !(guide.colors || []).length)) return '';
  return `<div class="g-key">${guide.x ? `<p><b>↔ Across:</b> ${esc(guide.x)}</p>` : ''}${guide.y ? `<p><b>↕ Up/down:</b> ${esc(guide.y)}</p>` : ''}
    ${(guide.colors || []).map(c => `<p><span class="g-key-swatch" style="background:${esc(c.color)}"></span>${esc(c.meaning)}</p>`).join('')}</div>`;
}

function gExploreNav(g, groups) {
  // Contents menu: every chart by group, plus a title search. Clicking opens the group and scrolls to the chart.
  const main = [];
  return `<nav class="g-explore-nav" aria-label="Research analyses contents"><input type="search" id="g-chart-search" placeholder="Search charts (e.g. time, seed, side effect)" aria-label="Search charts">
    <div class="g-explore-groups">${groups.map(gr => { const items = g.charts.filter(c => c.group === gr.id && !main.includes(c.id)); return items.length ? `<div><b>${esc(gr.title)}</b><ul>${items.map(c => `<li data-g-search="${esc((c.title + ' ' + (c.technical_title || '') + ' ' + c.paper).toLowerCase())}"><a href="#chart-${esc(c.id)}" data-g-open="g-group-${esc(gr.id)}" data-g-chart="chart-${esc(c.id)}">${esc(c.title)}</a>${c.status_label ? ` <small>(${esc(c.status_label)})</small>` : ''}</li>`).join('')}</ul></div>` : ''; }).join('')}</div></nav>`;
}

/* ---------- step content ---------- */
function gNav(back, next, nextLabel = 'Continue') {
  return `${G.error ? `<p class="error-text" role="alert">${esc(G.error)}</p>` : ''}
    <div class="g-nav">${back !== null ? `<button type="button" class="secondary" data-g-go="${back}">← Back</button>` : '<span></span>'}
    ${next !== null ? `<button type="button" class="primary" data-g-go="${next}">${esc(nextLabel)} →</button>` : ''}</div>`;
}
function gStepHtml(step) {
  return {intro: gIntroHtml, dataset: gDatasetHtml, model: gModelHtml, transformation: gTransformationHtml, review: gReviewHtml, results: gResultsHtml}[step]();
}

function gDatasetCard(d) {
  const sel = G.config.dataset === d.id;
  const meta = d.meta || {};
  const labels = d.snapshot_labels || [];
  return `<article class="g-card ${sel ? 'selected' : ''} ${d.available === false ? 'disabled' : ''}">
    <label><input type="radio" name="g-dataset" value="${esc(d.id)}" ${sel ? 'checked' : ''} ${d.available === false || G.locked.includes('dataset') ? 'disabled' : ''}>
    <span class="g-card-title">${esc(d.name)}</span><span class="tag">${d.family === 'synthetic' ? 'synthetic · known structure' : 'real data'}</span></label>
    <p>${esc(meta.description || d.description || '')}</p>
    ${d.available === false ? `<p class="error-text">${esc(d.unavailable_reason || 'Unavailable')}</p>` : `
    <dl class="g-facts">
      ${meta.graph_nodes_are ? `<dt>Nodes are</dt><dd>${esc(meta.graph_nodes_are)}</dd>` : ''}
      ${meta.graph_edges_are ? `<dt>Edges are</dt><dd>${esc(meta.graph_edges_are)}</dd>` : ''}
      <dt>Size</dt><dd>${d.nodes} nodes · ${d.edges_min}–${d.edges_max} edges per snapshot (mean ${d.edges_mean})</dd>
      <dt>Time</dt><dd>${d.snapshots} snapshots${labels.length ? ` · ${esc(labels[0])} → ${esc(labels.at(-1))}` : ''}${meta.snapshot_interval ? ` · ${esc(meta.snapshot_interval)} each` : ''}</dd>
      <dt>Communities</dt><dd>${d.communities}: ${d.community_sizes.map((n, i) => `${esc(d.community_labels[i])} (${n})`).join(', ')}</dd>
      <dt>Supports</dt><dd>${d.models.length} models · ${d.concepts.length} concepts (feasibility checked per request)</dd>
    </dl>
    <details class="g-more"><summary>Constraints & preprocessing</summary><ul>${d.constraints.map(c => `<li>${esc(c)}</li>`).join('')}
      ${Object.entries(d.preprocessing || {}).map(([k, v]) => `<li><b>${esc(k.replaceAll('_', ' '))}:</b> ${esc(String(v))}</li>`).join('')}
      ${meta.source ? `<li><b>Source:</b> ${esc(meta.source)}</li>` : ''}</ul></details>`}
  </article>`;
}

function gDatasetHtml() {
  const groups = [['synthetic', 'Controlled synthetic ecosystems', 'Generated from the seed with known structure, so expected model responses can be checked.'],
    ['real', 'Real temporal datasets', 'Prepared with the paper\'s leakage-safe preprocessing. Decentraland and Email-Eu-core are the paper\'s two case studies.']];
  return `${gHero('dataset')}${gTip('<b>Not sure?</b> Start with <b>Stable ecosystem</b>: it is small, fast and has known structure, so you can check that TGAP reports what you expect. The paper\'s real case studies are <b>Decentraland</b> and <b>Email-Eu-core</b>.')}
    <p class="g-lead">All metadata below is computed from the bundled data or generator. Later steps only offer options the selected dataset supports.</p>
    ${gHelp('What makes datasets different?', '<p>Synthetic datasets have known structure (for example, a bridge that decays over time), which makes it possible to check whether TGAP reports what the model definition predicts. Real datasets show how TGAP behaves on observed interactions but have no explanation ground truth. Sparse snapshots make some requests infeasible.</p>')}
    ${groups.map(([family, title, note]) => `<h3 class="g-sub">${title}</h3><p class="field-help">${note}</p>
      <div class="g-card-grid">${G.cat.datasets.filter(d => d.family === family).map(gDatasetCard).join('')}</div>`).join('')}
    ${gNav(0, 2)}`;
}

function gModelHtml() {
  const ds = gDataset(), c = G.config, p = G.preview;
  const target = c.target_snapshot === null ? ds.snapshots - 1 : c.target_snapshot;
  const out = id => p && !p.loading ? p.outputs.find(o => o.model === id)?.prediction : null;
  const sel = G.cat.models.find(m => m.id === c.model);
  return `${gHero('model')}${gTip('<b>Present</b> models only look at the latest snapshot. <b>Forecast</b> and <b>Trajectory</b> models read the whole history. Picking one of each later makes the temporal charts much more interesting.')}
    <p class="g-lead">These are the six deterministic model variants used in the paper's real-data study (Table 4). Each returns one number per temporal graph.</p>
    ${gHelp('Why analytical models?', '<p>The paper uses transparent analytical models so that each model\'s response can be reasoned about. Persistence models read only the target snapshot; trend models fit a line to the whole history and forecast one step ahead; the slope model returns only the rate of change. A learned TGN is covered by the paper but must be trained locally (see the reference area of the results).</p>')}
    <div class="g-card-grid g-models">${G.cat.models.map(m => `
      <article class="g-card ${c.model === m.id ? 'selected' : ''}"><label><input type="radio" name="g-model" value="${esc(m.id)}" ${c.model === m.id ? 'checked' : ''} ${G.locked.includes('model') ? 'disabled' : ''}>
        <span class="g-card-title">${esc(m.name)}</span></label>
        <p>${esc(m.output)}</p>
        <dl class="g-facts"><dt>Reads</dt><dd>${esc(m.reads)}</dd><dt>Operator</dt><dd>${esc(m.operator)} of ${esc(m.metric)}</dd><dt>Unit</dt><dd>${esc(m.unit)}</dd>
        <dt>Original output</dt><dd>${p?.loading ? '<span class="busy-spinner"></span>' : out(m.id) === null || out(m.id) === undefined ? '—' : `<b>${esc(number(out(m.id)))}</b>`}</dd></dl></article>`).join('')}
    </div>
    <h3 class="g-sub">Target: which prediction?</h3>
    <p class="field-help">The model predicts from the snapshots up to the target. Choosing an earlier target explains the prediction that would have been made at that time, using only the history available then.</p>
    <div class="g-row"><label for="g-target">Target snapshot</label>
      <select id="g-target" ${G.locked.includes('target_snapshot') ? 'disabled' : ''}>${ds.snapshot_labels.map((label, i) => i === 0 ? '' : `<option value="${i}" ${i === target ? 'selected' : ''}>${i + 1}. ${esc(label)}${i === ds.snapshots - 1 ? ' (latest)' : ''}</option>`).join('')}</select></div>
    <div class="g-callout"><b>${esc(sel.name)}</b> at <b>${esc(ds.snapshot_labels[target])}</b> uses snapshots 1–${target + 1}${sel.reads === 'full history' ? ' and forecasts the step after the target' : ''}.
      Original prediction: ${p?.loading ? '<span class="busy-spinner"></span>' : `<b>${esc(number(out(c.model)))}</b> ${esc(sel.unit)}`}.
      This is a graph-level prediction; the models here do not predict for individual nodes or edges.</div>
    ${p?.error ? `<p class="error-text">${esc(p.error)}</p>` : ''}
    ${gNav(1, 3)}`;
}

function gConceptCard(t) {
  const c = G.config, sel = c.concept === t.id;
  const value = G.preview && !G.preview.loading ? G.preview.concepts.find(x => x.id === t.id)?.value : null;
  return `<article class="g-card ${sel ? 'selected' : ''}"><label><input type="radio" name="g-concept" value="${esc(t.id)}" ${sel ? 'checked' : ''} ${G.locked.includes('concept') ? 'disabled' : ''}>
    <span class="g-card-title">${esc(t.name)}</span><span class="tag">${t.kind === 'temporal' ? 'temporal' : 'structural'}</span></label>
    <p>${esc(t.represents)}</p>
    <dl class="g-facts"><dt>Changes</dt><dd>${esc(t.changes)}</dd><dt>Keeps fixed</dt><dd>${esc(t.fixed)}</dd>
      <dt>Achieved change</dt><dd>${esc(t.achieved_units)}</dd><dt>Edge count</dt><dd>${t.preserves_edge_count ? 'declared preserved (checked)' : 'may change by design'}</dd>
      <dt>Current value</dt><dd>${value === null || value === undefined ? '—' : esc(number(value))}</dd></dl>
    <details class="g-more"><summary>Constraints</summary><p>${esc(t.constraints)}</p><p><b>You control:</b> ${esc(t.controls)}</p></details></article>`;
}

function gPlan() {
  const c = G.config, s = c.sweep;
  const models = [...new Set([c.model, ...s.models])], concepts = [...new Set([...s.concepts, ...(c.concept === 'custom' ? ['custom'] : [c.concept])])];
  const deltas = [...new Set([...s.deltas, c.delta].map(d => +d.toFixed(6)))];
  const k = concepts.length;
  return {models, concepts, deltas, explanations: models.length * deltas.length, matrixCalls: models.length * deltas.length * (1 + 2 * k),
    rows: models.length * deltas.length * k * 2, repeats: s.repeats + (s.repeats ? 1 : 0), sizes: s.sizes.length, matched: s.matched,
    transforms: deltas.length * k * 2};
}

function gReviewHtml() {
  const c = G.config, ds = gDataset(), p = G.preview, plan = gPlan();
  const model = G.cat.models.find(m => m.id === c.model);
  const target = c.target_snapshot === null ? ds.snapshots - 1 : c.target_snapshot;
  const original = p && !p.loading ? p.outputs.find(o => o.model === c.model)?.prediction : null;
  const charts = G.cat.inventory.charts;
  const willRun = id => {
    if (id === 'matched_comparison') return c.sweep.matched;
    if (id === 'seed_stability') return c.sweep.repeats > 0;
    if (id === 'graph_size') return ds.family === 'synthetic' && c.sweep.sizes.length > 0;
    if (id === 'temporal_sensitivity') return plan.concepts.includes('bridge_trend');
    return true;
  };
  const edit = step => `<button type="button" class="text-button" data-g-go="${step}">Edit</button>`;
  if (G.running) return gRunningHtml();
  return `${gHero('review')}${gTip('Everything below is computed on the server with the real TGAP library. Use <b>Edit</b> to jump back to any step — nothing is lost.', 'shield')}
    <p class="g-lead">Check every setting. The experiment runs on the server with the research library; nothing is simulated in the browser.</p>
    <table class="g-review"><tbody>
      <tr><th>Dataset</th><td>${esc(ds.name)} · ${ds.nodes} nodes · ${ds.snapshots} snapshots</td><td>${edit(1)}</td></tr>
      <tr><th>Model</th><td>${esc(model.name)} — ${esc(model.output)}</td><td>${edit(2)}</td></tr>
      <tr><th>Target</th><td>Snapshot ${target + 1} (${esc(ds.snapshot_labels[target])}); uses snapshots 1–${target + 1}</td><td>${edit(2)}</td></tr>
      <tr><th>Original prediction</th><td>${original === null || original === undefined ? '—' : `<b>${esc(number(original))}</b> ${esc(model.unit)}`}</td><td></td></tr>
      <tr><th>Transformation</th><td>${esc(gName.concept(c.concept))} · <b>${esc(c.direction)}</b> · requested ${gPct(c.delta)}${c.concept === 'custom' ? ' · custom code' : ''}</td><td>${edit(3)}</td></tr>
      <tr><th>Random seed</th><td>${c.seed}${c.sweep.repeats ? ` · ${c.sweep.repeats} extra ${esc(c.sweep.variation)} seed(s)` : ' · no seed repeats'}</td><td>${edit(3)}</td></tr>
      <tr><th>Metrics</th><td>Baseline and transformed prediction, achieved change, normalized impact = (prediction after − baseline) / |achieved change|, no-op flag, validity status, leakage on Bridge Width, Density, Centralization, Clustering and Cohesion.</td><td></td></tr>
      <tr><th>Additional runs</th><td>${plan.models.length} model(s) × ${plan.concepts.length} concept(s) × ${plan.deltas.length} size(s) × 2 directions = <b>${plan.rows}</b> result rows from ${plan.explanations} explanations (${plan.matrixCalls} model calls; ${plan.transforms} counterfactual graphs, each shared by all models)${plan.repeats ? ` · ${plan.repeats} seed runs` : ''}${plan.sizes ? ` · ${plan.sizes} size runs` : ''}${plan.matched ? ' · matched sweep' : ''} · bounded element-level occlusions.</td><td>${edit(3)}</td></tr>
    </tbody></table>
    <h3 class="g-sub">Charts this run will produce</h3>
    <ul class="g-plan">${charts.map(ch => `<li><span>${esc(ch.paper)}</span> ${esc(G_TITLES[ch.id] || ch.id)} — ${ch.kind === 'blocked' ? '<span class="tag warning">reference only</span>' : willRun(ch.id) ? '<span class="tag success">will be computed</span>' : '<span class="tag">not requested / not applicable</span>'}</li>`).join('')}</ul>
    ${gNav(3, null)}
    <div class="g-run"><button type="button" class="primary wide" id="g-run">Run experiment</button>
    <p class="field-help">Runs are limited to ${G.cat.limits.seconds} s. You can keep this page open; progress is shown stage by stage.</p></div>`;
}

/* ---------- summary panel ---------- */
function gSummaryHtml() {
  const c = G.config, ds = gDataset(), plan = gPlan();
  const model = G.cat.models.find(m => m.id === c.model);
  const target = c.target_snapshot === null ? ds.snapshots - 1 : c.target_snapshot;
  const original = G.preview && !G.preview.loading ? G.preview.outputs.find(o => o.model === c.model)?.prediction : null;
  return `<h3>Your configuration</h3>
    ${G.scenario ? `<p class="tag">Scenario: ${esc(G.cat.scenarios.find(s => s.id === G.scenario)?.title || G.scenario)}</p>` : ''}
    <dl class="g-summary-list">
      <dt>Dataset</dt><dd>${esc(ds?.name || c.dataset)}</dd>
      <dt>Model</dt><dd>${esc(model?.name || c.model)}</dd>
      <dt>Target</dt><dd>${ds ? `${target + 1}/${ds.snapshots} · ${esc(ds.snapshot_labels[target])}` : '—'}</dd>
      <dt>Original output</dt><dd>${original === null || original === undefined ? '—' : esc(number(original))}</dd>
      <dt>Concept</dt><dd>${esc(gName.concept(c.concept))}</dd>
      <dt>Request</dt><dd>${esc(c.direction)} ${gPct(c.delta)}</dd>
      <dt>Seed</dt><dd>${c.seed}${c.sweep.repeats ? ` (+${c.sweep.repeats} ${esc(c.sweep.variation)})` : ''}</dd>
      <dt>Extra runs</dt><dd>${plan.models.length} models · ${plan.concepts.length} concepts · sizes ${plan.deltas.map(gPct).join(', ')}${c.sweep.sizes.length ? ` · graph sizes ${c.sweep.sizes.join(', ')}` : ''}${c.sweep.matched ? ' · matched' : ''}</dd>
    </dl>
    ${G.result && !gResultMatchesConfig() ? '<p class="g-warn">Your last results were produced with different settings. Run again to update them.</p>' : ''}
    ${G.result ? '<button type="button" class="text-button" data-g-go="5">View last results →</button>' : ''}`;
}

/* ---------- wiring ---------- */
function gWire(step) {
  document.querySelectorAll('[data-g-go]').forEach(b => b.onclick = () => gGo(Number(b.dataset.gGo)));
  gWireOnboard();
  const c = G.config;
  if (step === 'intro') {
    document.querySelectorAll('[data-g-scenario]').forEach(b => b.onclick = () => gApplyScenario(b.dataset.gScenario));
    if ($('g-clear-scenario')) $('g-clear-scenario').onclick = () => { G.scenario = null; G.locked = []; G.config = gDefaults(); gLoadPreview(); gRender(); };
  }
  if (step === 'dataset') {
    document.querySelectorAll('[name=g-dataset]').forEach(input => input.onchange = () => {
      c.dataset = input.value; c.target_snapshot = null;
      const ds = gDataset();
      if (ds.family !== 'synthetic') { c.sweep.variation = 'transformation'; c.sweep.sizes = []; }
      G.feasibility = null; gLoadPreview(); gRender();
    });
  }
  if (step === 'model') {
    document.querySelectorAll('[name=g-model]').forEach(input => input.onchange = () => { c.model = input.value; gRender(); });
    $('g-target').onchange = () => {
      const value = Number($('g-target').value);
      c.target_snapshot = value === gDataset().snapshots - 1 ? null : value;
      G.feasibility = null; gLoadPreview(); gRender();
    };
  }
  if (step === 'transformation') {
    document.querySelectorAll('[name=g-concept]').forEach(input => input.onchange = () => { c.concept = input.value; c.custom_code = ''; gCheckFeasibility(); gRender(); });
    document.querySelectorAll('[name=g-direction]').forEach(input => input.onchange = () => { c.direction = input.value; gRender(); });
    $('g-delta').oninput = () => { c.delta = Number($('g-delta').value) / 100; document.querySelector('output[for=g-delta]').textContent = gPct(c.delta); };
    $('g-delta').onchange = () => { gCheckFeasibility(); gRender(); };
    const collect = (name, cast = String) => [...document.querySelectorAll(`[name=${name}]:checked:not(:disabled)`)].map(e => cast(e.value));
    document.querySelectorAll('[name=g-sweep-model]').forEach(e => e.onchange = () => { c.sweep.models = collect('g-sweep-model'); gRender(); });
    document.querySelectorAll('[name=g-sweep-concept]').forEach(e => e.onchange = () => { c.sweep.concepts = collect('g-sweep-concept'); gRender(); });
    document.querySelectorAll('[name=g-sweep-delta]').forEach(e => e.onchange = () => { c.sweep.deltas = collect('g-sweep-delta', Number); gRender(); });
    document.querySelectorAll('[name=g-size]').forEach(e => e.onchange = () => { c.sweep.sizes = collect('g-size', Number); gRender(); });
    document.querySelectorAll('[name=g-variation]').forEach(e => e.onchange = () => { c.sweep.variation = e.value; gRender(); });
    $('g-repeats').onchange = () => { c.sweep.repeats = Math.max(0, Math.min(G.cat.limits.max_repeats, Math.round(Number($('g-repeats').value) || 0))); gRender(); };
    $('g-matched').onchange = () => { c.sweep.matched = $('g-matched').checked; gRender(); };
    $('g-seed').onchange = () => { c.seed = Math.max(0, Math.min(100000, Math.round(Number($('g-seed').value) || 0))); gLoadPreview(); gCheckFeasibility(); gRender(); };
    $('g-add-delta-btn').onclick = () => {
      const value = Number($('g-add-delta').value) / 100;
      if (!(value >= 0.02 && value <= 0.9)) { G.error = 'Additional sizes must be between 2% and 90%.'; gRender(); return; }
      if (c.sweep.deltas.length >= 5) { G.error = 'Use at most 5 request sizes.'; gRender(); return; }
      if (!c.sweep.deltas.includes(value)) c.sweep.deltas.push(value);
      G.error = ''; gRender();
    };
    document.querySelectorAll('[data-g-mode]').forEach(b => b.onclick = () => {
      if (b.dataset.gMode === 'custom') { if (c.concept !== 'custom') { c.concept = 'custom'; if (!c.custom_code.trim()) c.custom_code = G.cat.custom.skeleton; G.codeCheck = null; } }
      else if (c.concept === 'custom') { c.concept = 'bridge_width'; c.custom_code = ''; G.codeCheck = null; gCheckFeasibility(); }
      gEvent('step_complete', 'transformation');
      gRender();
    });
    document.querySelectorAll('[data-g-sample]').forEach(b => b.onclick = () => {
      const id = b.dataset.gSample;
      if (c.custom_code.trim() && c.custom_code !== G.cat.custom.skeleton && !confirm('Replace the code in the editor?')) return;
      c.custom_code = id === '__skeleton' ? G.cat.custom.skeleton : G.cat.custom.samples.find(x => x.id === id).code;
      G.codeCheck = null; gRender();
      $('g-custom-code')?.scrollIntoView({block: 'center'});
      toast('Loaded. Read the comments, edit, then press Check my code.');
    });
    if ($('g-custom-code')) {
      $('g-custom-code').oninput = () => { c.custom_code = $('g-custom-code').value; if (G.codeCheck) { G.codeCheck = null; document.querySelector('.g-check-result').innerHTML = '<p class="field-help">Code changed — press Check my code again.</p>'; } };
      $('g-custom-code').onkeydown = event => { if (event.key === 'Tab') { event.preventDefault(); event.target.setRangeText('    ', event.target.selectionStart, event.target.selectionEnd, 'end'); c.custom_code = event.target.value; } };
      $('g-check-code').onclick = async () => {
        G.codeCheck = {loading: true}; gRender();
        try { G.codeCheck = await api('/guided/validate-code', {method: 'POST', body: JSON.stringify({custom_code: c.custom_code})}); }
        catch (error) { G.codeCheck = {ok: false, message: error.message}; }
        gRender();
        document.querySelector('.g-check-result')?.scrollIntoView({block: 'center'});
      };
    }
    if (!G.feasibility && c.concept !== 'custom') gCheckFeasibility();
  }
  if (step === 'review' && $('g-run')) $('g-run').onclick = gRun;
  if (step === 'results') gWireResults();
}

function gApplyScenario(id) {
  const s = G.cat.scenarios.find(x => x.id === id);
  if (!s) return;
  const base = gDefaults();
  G.config = {...base, ...JSON.parse(JSON.stringify(s.spec)), sweep: {...base.sweep, ...(s.spec.sweep || {})}, scenario: s.id};
  if (G.config.target_snapshot === undefined) G.config.target_snapshot = null;
  if (G.config.custom_code === undefined) G.config.custom_code = '';
  G.scenario = s.id; G.locked = s.locked || []; G.feasibility = null;
  gEvent('scenario_selected', 'intro', {scenario: s.id});
  gLoadPreview(); gRender();
  toast('Scenario loaded. Review each step before running.');
}

async function gLoadPreview() {
  const c = G.config;
  const key = JSON.stringify([c.dataset, c.seed, c.target_snapshot]);
  G.preview = {loading: true, key};
  try {
    const data = await api('/guided/preview', {method: 'POST', body: JSON.stringify({dataset: c.dataset, seed: c.seed, target_snapshot: c.target_snapshot})});
    if (G.preview.key !== key) return;
    G.preview = data; G.preview.key = key;
  } catch (error) {
    if (G.preview.key === key) G.preview = {error: error.message, outputs: [], concepts: [], key};
  }
  if (['intro', 'model', 'transformation', 'review'].includes(G_STEPS[G.step][0]) && !G.running) gRender();
}

async function gCheckFeasibility() {
  const c = G.config;
  if (c.concept === 'custom') { G.feasibility = null; return; }
  const key = JSON.stringify([c.dataset, c.seed, c.target_snapshot, c.concept, c.delta]);
  G.feasibility = {loading: true, key};
  try {
    const data = await api('/guided/feasibility', {method: 'POST', body: JSON.stringify({dataset: c.dataset, seed: c.seed, target_snapshot: c.target_snapshot, concept: c.concept, delta: c.delta})});
    if (G.feasibility.key !== key) return;
    G.feasibility = {...data, key};
  } catch (error) {
    if (G.feasibility.key === key) G.feasibility = {error: error.message, key};
  }
  if (G_STEPS[G.step][0] === 'transformation') gRender();
}

/* ---------- run ---------- */
function gPayload() {
  const c = JSON.parse(JSON.stringify(G.config));
  c.sweep.models = c.sweep.models.filter(m => m !== c.model);
  c.sweep.models.unshift(c.model);
  if (c.concept !== 'custom' && !c.sweep.concepts.includes(c.concept)) c.sweep.concepts.push(c.concept);
  if (!c.sweep.deltas.some(d => Math.abs(d - c.delta) < 1e-9)) c.sweep.deltas.push(c.delta);
  c.sweep.deltas = c.sweep.deltas.slice(0, 5);
  if (!c.scenario) delete c.scenario;
  return c;
}

async function gRun() {
  const problem = [1, 2, 3].map(gValidateStep).find(Boolean);
  if (problem) { G.error = problem; gRender(); return; }
  G.error = ''; G.running = true; G.progress = null; G.started = Date.now();
  const payload = gPayload();
  G.config = JSON.parse(JSON.stringify(payload));
  if (!G.config.scenario) G.config.scenario = null;
  gRender();
  const tick = setInterval(() => { if ($('g-elapsed')) $('g-elapsed').textContent = `${Math.round((Date.now() - G.started) / 1000)}s elapsed · stages that were not requested are skipped.`; }, 1000);
  try {
    const job = await api('/guided/experiments', {method: 'POST', body: JSON.stringify(payload)});
    gEvent('run_submitted', 'review', {job_id: job.id, ...(G.scenario ? {scenario: G.scenario} : {})});
    let data;
    const deadline = Date.now() + (G.cat.limits.seconds + 120) * 1000;
    while (Date.now() < deadline) {
      await new Promise(resolve => setTimeout(resolve, 1200));
      try { data = await api('/guided/experiments/' + job.id); }
      catch (error) { if (error.status === 429 || error.status === 503) { await new Promise(r => setTimeout(r, error.retryAfter * 1000)); continue; } throw error; }
      if (data.status === 'complete' || data.status === 'failed') break;
      if (JSON.stringify(data.progress) !== JSON.stringify(G.progress)) { G.progress = data.progress; gRender(); }
    }
    if (data?.status !== 'complete') {
      gEvent('run_failed', 'review', {job_id: job.id});
      throw Error(data?.error ? `The experiment failed: ${data.error}` : 'The experiment did not finish in time. Check Recent experiments in the Laboratory later.');
    }
    G.job = job.id; G.result = data.result; G.snapshot = null;
    G.running = false; G.step = 5;
    gEvent('run_complete', 'review', {job_id: job.id});
    toast('Experiment complete. Read the requested versus achieved change before the impact.');
    refreshHistory().catch(() => {});
    gRender();
  } catch (error) {
    G.running = false;
    G.error = `${error.message} Recovery: check the feasibility pre-check, reduce comparison models, concepts, sizes or seeds, or try again shortly if the laboratory is busy. Your configuration is unchanged.`;
    gRender();
  } finally { clearInterval(tick); }
}

/* ---------- results ---------- */
const G_TITLES = {workflow: 'How this explanation was produced', model_separated_impacts: 'Concept impacts, separated by model', beeswarm: 'Individual concept responses (beeswarm)',
  boxplot: 'Response distributions by model', tgn_seed_stability: 'Learned-model (TGN) seed stability', local_graph: 'Original versus transformed graph',
  local_bar: 'Local edge explanation', temporal_local: 'When the concept matters', edge_time: 'Edges and time', dependence: 'Structure versus measured response',
  impact_distribution: 'Exploratory spread of all valid impacts', bridge_matrix: 'Connections between communities', requested_vs_achieved: 'Requested versus achieved change',
  validity_map: 'Validity of every tested setting', delta_sensitivity: 'Response to request size', normalization: 'Achieved versus requested normalization',
  temporal_sensitivity: 'Present-only versus history-reading models', trajectory: 'Concept history: original versus transformed', leakage: 'Side effects on other properties',
  seed_stability: 'Stability across seeds', efficiency: 'Model-call budget', graph_size: 'Behaviour across graph sizes', matched_comparison: 'Matched cross-concept comparison',
  faithfulness: 'Known-truth faithfulness'};

function gProvenanceRows(g) {
  const p = g.provenance, s = g.spec;
  return [
    ['Run ID', esc(G.job)], ['Configuration hash', `<code>${esc(p.config_hash)}</code>`], ['Engine request hash', `<code>${esc(p.request_hash || '')}</code>`],
    ['Generated (UTC)', esc(p.generated_at)], ['Guided version', esc(p.guided_version)], ['Dataset', `${esc(s.dataset)} · ${esc(p.dataset_source)}${p.dataset_fixture_sha256 ? ` · sha256 <code>${esc(p.dataset_fixture_sha256.slice(0, 16))}…</code>` : ''}`],
    ['Model', esc(s.model)], ['Concept', `${esc(s.concept)}${s.custom_code ? ' (custom code included in JSON)' : ''}`], ['Direction / size', `${esc(s.direction)} ${gPct(s.delta)}`],
    ['Target snapshot', s.target_snapshot === null ? 'latest' : String(s.target_snapshot + 1)], ['Seed', String(s.seed)],
    ['Comparison models', esc(s.sweep.models.join(', '))], ['Comparison concepts', esc(s.sweep.concepts.join(', ') || '—')], ['Request sizes', esc(s.sweep.deltas.map(gPct).join(', '))],
    ['Seed repeats', `${s.sweep.repeats} (${esc(s.sweep.variation)})`], ['Graph sizes', esc(s.sweep.sizes.join(', ') || '—')], ['Matched sweep', s.sweep.matched ? 'yes' : 'no'],
    ['Core library sha256', `<code>${esc(p.core_sha256.slice(0, 16))}…</code>`], ['Workbench sources', esc(Object.entries(p.workbench_sha256).map(([k, v]) => `${k} ${v.slice(0, 10)}`).join(' · '))],
    ['Python / packages', esc(`${p.python} · ${Object.entries(p.packages).map(([k, v]) => `${k} ${v}`).join(' · ')}`)],
    ['Stage timings (s)', esc(Object.entries(g.timings).map(([k, v]) => `${k} ${v}`).join(' · '))],
  ];
}

const G_PARTS = [['what', 'What it measures'], ['conditions', 'Conditions'], ['observations', 'Key results'], ['pattern', 'Pattern'], ['conclusion', 'What you can conclude'], ['caution', 'What not to conclude']];

function gWireResults() {
  document.querySelectorAll('[data-g-jump]').forEach(a => a.onclick = e => { e.preventDefault(); $(a.dataset.gJump)?.scrollIntoView({behavior: 'smooth', block: 'start'}); });
  gEvent('results_viewed', 'results', {job_id: G.job});
  document.querySelectorAll('[data-g-svg]').forEach(b => b.onclick = () => {
    const svg = $(b.dataset.gSvg).querySelector('svg');
    downloadText(new XMLSerializer().serializeToString(svg), `tgap-guided-${G.job.slice(0, 8)}-${b.dataset.gSvg.slice(6)}.svg`, 'image/svg+xml');
  });
  document.querySelectorAll('[data-g-png]').forEach(b => b.onclick = async () => {
    try {
      const svg = $(b.dataset.gPng).querySelector('svg'), image = new Image(), xml = new XMLSerializer().serializeToString(svg);
      await new Promise((resolve, reject) => { image.onload = resolve; image.onerror = reject; image.src = 'data:image/svg+xml;charset=utf-8,' + encodeURIComponent(xml); });
      const box = svg.viewBox.baseVal, canvas = document.createElement('canvas');
      canvas.width = box.width * 2; canvas.height = box.height * 2;
      canvas.getContext('2d').drawImage(image, 0, 0, canvas.width, canvas.height);
      const a = document.createElement('a'); a.download = `tgap-guided-${G.job.slice(0, 8)}-${b.dataset.gPng.slice(6)}.png`; a.href = canvas.toDataURL('image/png'); a.click();
    } catch { toast('Could not create the PNG. Download the SVG instead.'); }
  });
  document.querySelectorAll('[data-g-export]').forEach(a => a.addEventListener('click', () => gEvent('export', 'results', {job_id: G.job})));
  $('g-report-html').onclick = () => { gEvent('export', 'results', {job_id: G.job}); downloadText(gReportHtml(), `tgap-guided-report-${G.job.slice(0, 8)}.html`, 'text/html'); };
  $('g-print').onclick = () => { gEvent('export', 'results', {job_id: G.job}); document.querySelectorAll('#g-report details').forEach(d => d.open = true); window.print(); };
  gWireResultsInner();
}
function gWireExplore() {
  const box = $('g-chart-search');
  if (box) box.oninput = () => { const q = box.value.trim().toLowerCase(); document.querySelectorAll('[data-g-search]').forEach(li => { li.hidden = q && !li.dataset.gSearch.includes(q); }); };
  document.querySelectorAll('[data-g-open]').forEach(a => a.onclick = () => { const d = $(a.dataset.gOpen), c = $(a.dataset.gChart); if (d) d.open = true; if (c) c.open = true; });
}
function gWireResultsInner() {
  gWireExplore();
  const slider = $('g-snapshot');
  if (slider) slider.oninput = () => { G.snapshot = Number(slider.value); $('g-fig-local_graph').innerHTML = gRender_.network(G.result.guided.charts.find(c => c.id === 'local_graph')); gWireResultsInner(); };
  const metric = $('g-traj-metric');
  if (metric) metric.onchange = () => { G.trajMetric = metric.value; $('g-fig-trajectory').innerHTML = gRender_.trajectory(G.result.guided.charts.find(c => c.id === 'trajectory')); gWireResultsInner(); };
}

function gReportHtml() {
  const g = G.result.guided;
  const cards = [...document.querySelectorAll('#g-report .g-chart')].map(card => {
    const chart = g.charts.find(c => c.id === card.dataset.chart);
    const svg = card.querySelector('.figure-canvas svg');
    const published = card.querySelector('.g-published');
    return `<section><h3>${esc(chart.title)} <small>(${esc(chart.paper)} · ${esc(chart.status)})</small></h3>
      ${chart.scope ? `<p><i>${esc(chart.scope)}</i></p>` : ''}${chart.deviation ? `<p><b>Deviation from the paper:</b> ${esc(chart.deviation)}</p>` : ''}
      ${svg ? new XMLSerializer().serializeToString(svg) : ''}
      ${chart.explanation.easy_shows ? `<p><b>What this chart shows:</b> ${esc(chart.explanation.easy_shows)}<br><b>What your result shows:</b> ${esc(chart.explanation.easy_result)}</p>` : ''}
      ${published ? `<p><i>The paper's original ${esc(chart.paper)} is shown next to this chart in the app as a reference; it is not part of this run.</i></p>` : ''}
      <dl>${G_PARTS.map(([k, label]) => `<dt>${label}</dt><dd>${esc(chart.explanation[k])}</dd>`).join('')}</dl><p class="axes">${esc(chart.axes)}</p></section>`;
  }).join('');
  const summary = document.querySelector('#g-report .g-stats')?.outerHTML || '';
  return `<!doctype html><html lang="en"><head><meta charset="utf-8"><title>TGAP guided experiment ${esc(G.job.slice(0, 8))}</title>
    <style>body{font-family:Arial,sans-serif;max-width:960px;margin:24px auto;color:#18283e;line-height:1.5;padding:0 16px}svg{max-width:100%;height:auto;border:1px solid #e3e8ee}section{page-break-inside:avoid;margin:28px 0}dt{font-weight:bold;margin-top:6px}dd{margin:0 0 4px 0}.g-stats{display:grid;grid-template-columns:repeat(auto-fill,minmax(180px,1fr));gap:10px}.g-stat{border:1px solid #e3e8ee;padding:8px;border-radius:6px}.g-stat span{display:block}.stat-label{font-size:12px;color:#566b82}table{border-collapse:collapse}td,th{border:1px solid #e3e8ee;padding:4px 8px;text-align:left;vertical-align:top}.axes{font-size:13px;color:#566b82}.conclusion{background:#eef6f4;padding:12px;border-left:3px solid #398b7b}</style></head><body>
    <h1>TGAP Guided User Study — experiment report</h1><p>Run ${esc(G.job)} · configuration ${esc(g.config_hash)} · generated ${esc(g.provenance.generated_at)} UTC</p>
    <h2>Status</h2><p>${esc(g.experiment_status.label)}${g.experiment_status.partial ? ' (partial: ' + esc(g.experiment_status.failed_stages.join(', ')) + ')' : ''}</p>
    <h2>Summary</h2>${summary}
    <h2>Configuration and provenance</h2><table>${gProvenanceRows(g).map(([k, v]) => `<tr><th>${esc(k)}</th><td>${v}</td></tr>`).join('')}</table>
    <h2>Charts and explanations</h2>${cards}
    <h2>Overall Experiment Conclusion</h2><p class="conclusion">${esc(g.conclusion)}</p>
    <h2>Limitations</h2><ul><li>Results describe model sensitivity to controlled graph changes, not real-world causal effects.</li><li>Invalid rows are excluded and never treated as zero.</li>${g.charts.filter(c => !['ok', 'partial'].includes(c.status)).map(c => `<li>${esc(c.title)}: ${esc(c.status.replaceAll('_', ' '))}${c.scope ? ' — ' + esc(c.scope) : ''}${c.blocked ? ' — ' + esc(c.blocked) : ''}</li>`).join('')}</ul>
    </body></html>`;
}


/* ---------- visual overall conclusion (built only from measured values) ---------- */
function gEvidence(r, g) {
  const p = g.primary, c = g.experiment_status.matrix_counts, items = [];
  const add = (state, title, text) => items.push({state, title, text});
  add(p.valid_for_analysis ? (p.noop ? 'warn' : 'ok') : 'bad', 'Change made faithfully',
    p.valid_for_analysis ? (p.noop ? 'Valid, but nothing actually changed (no-op).' : 'The graph edit respected every constraint.') : `Excluded: ${p.status.replaceAll('_', ' ')}.`);
  if (p.valid_for_analysis && !p.noop) add(p.prediction_change ? 'ok' : 'info', 'Model reacted', p.prediction_change ? `The answer moved by ${number(p.prediction_change, true)}.` : 'The concept changed but the answer did not.');
  const other = r.rows.find(x => x.concept === g.selected_concept && x.direction !== g.spec.direction);
  if (other && p.valid_for_analysis && other.valid_for_analysis && p.impact && other.impact)
    add(Math.sign(p.prediction_change) === -Math.sign(other.prediction_change) ? 'ok' : 'warn', Math.sign(p.prediction_change) === -Math.sign(other.prediction_change) ? 'Both directions consistent' : 'Directions behave differently', `Increase and decrease give impacts ${number(r.rows.find(x => x.concept === g.selected_concept && x.direction === 'increase').impact, true)} and ${number(r.rows.find(x => x.concept === g.selected_concept && x.direction === 'decrease').impact, true)}.`);
  else if (other && !other.valid_for_analysis) add('warn', 'Opposite direction', `Could not be tested (${other.status.replaceAll('_', ' ')}).`);
  const st = g.stability?.summary?.find(x => x.direction === g.spec.direction);
  if (st && st.n > 1) add(st.sd === 0 ? 'ok' : 'info', 'Repeatable across seeds', st.sd === 0 ? `Identical in all ${st.n} seeds.` : `Varies across ${st.n} seeds (${number(st.min, true)} to ${number(st.max, true)}).`);
  const tl = g.temporal?.panels?.find(x => x.model === g.spec.model);
  if (tl && tl.valid_for_analysis) {
    const hit = tl.rows.filter(x => x.valid && x.impact);
    add('info', 'When it matters', hit.length ? (hit.every(x => x.snapshot === tl.rows.length - 1) ? 'Only the latest snapshot matters to this model.' : `${hit.length} of ${tl.rows.length} snapshots matter, including earlier ones.`) : 'No single snapshot changed the answer on its own.');
  }
  const lk = g.matrix?.leakage?.find(x => x.concept === g.selected_concept && x.direction === g.spec.direction && Math.abs(Math.abs(x.requested_delta) - g.spec.delta) < 1e-9);
  if (lk) {
    const moved = Object.entries(lk.metrics).filter(([k, v]) => v.change && k !== g.selected_concept).map(([k]) => k);
    add(moved.length ? 'warn' : 'ok', 'Side effects', moved.length ? `Also moved: ${moved.join(', ')}.` : 'No other measured property moved.');
  }
  if (c.total) add(c.valid / c.total >= .75 ? 'ok' : 'warn', 'All extra tests', `${c.valid} of ${c.total} settings valid${c.invalid ? `; ${c.invalid} excluded` : ''}.`);
  if (g.experiment_status.partial) add('bad', 'Missing computations', `Failed: ${g.experiment_status.failed_stages.join(', ')}.`);
  return items;
}

function gConclusionHtml(r, g) {
  const p = g.primary, st = g.experiment_status, c = st.matrix_counts, model = G.cat.models.find(m => m.id === g.spec.model);
  const verdict = {
    responded: ['ok', 'check', 'The model is sensitive to this change', `On this network, ${esc(g.selected_concept)} measurably moves the answer of ${esc(model?.name || g.spec.model)}.`],
    no_response: ['info', 'info', 'The model ignored this change', `${esc(g.selected_concept)} really changed, but the answer of ${esc(model?.name || g.spec.model)} stayed the same.`],
    no_op: ['warn', 'info', 'Nothing was changed', 'The request was too small or not realizable on this graph, so there is nothing to conclude yet.'],
    target_against: ['warn', 'alert', 'Careful: the latest snapshot changed the other way', g.target_check ? `On average ${esc(g.selected_concept)} moved as you asked, but in the snapshot the model reads (${esc(g.target_check.label)}) it went from ${esc(number(g.target_check.before))} to ${esc(number(g.target_check.after))}. The answer's change reflects that opposite edit, not your request.` : ''],
    invalid: ['bad', 'alert', 'No valid answer for this request', 'The change could not be made faithfully. Try a different size or direction.'],
  }[st.code];
  const ach = p.achieved_delta === null || !p.valid_for_analysis ? '—' : p.delta_mode === 'relative' ? number(p.achieved_delta * 100, true) + '%' : number(p.achieved_delta, true);
  const step = (label, value, sub, cls = '') => `<div class="g-story-step ${cls}"><span>${label}</span><b>${value}</b><small>${sub}</small></div>`;
  const arrow = '<div class="g-story-arrow" aria-hidden="true">→</div>';
  const pct = c.total ? Math.round(c.valid / c.total * 100) : 0, R = 34, L = 2 * Math.PI * R;
  const ring = `<svg viewBox="0 0 90 90" class="g-ring" aria-label="${pct}% of tests valid"><circle cx="45" cy="45" r="${R}" class="bg"/><circle cx="45" cy="45" r="${R}" class="fg" stroke-dasharray="${L * pct / 100} ${L}"/><text x="45" y="50" text-anchor="middle">${pct}%</text></svg>`;
  const icons = {ok: 'check', warn: 'alert', bad: 'alert', info: 'info'};
  return `<div class="g-verdict g-v-${verdict[0]}"><div class="g-verdict-icon">${gIcon(verdict[1], 34)}</div><div><span class="eyebrow">VERDICT</span><h4>${verdict[2]}</h4><p>${verdict[3]}</p></div></div>
    <div class="g-story">
      ${step('Original answer', esc(number(p.baseline)), esc(model?.unit || ''))}${arrow}
      ${step('You asked', `${g.spec.direction === 'increase' ? '▲' : '▼'} ${gPct(g.spec.delta)}`, esc(g.selected_concept))}${arrow}
      ${step('TGAP achieved', esc(ach), p.valid_for_analysis ? 'real change' : esc(p.status.replaceAll('_', ' ')), p.valid_for_analysis ? '' : 'bad')}${arrow}
      ${step('New answer', p.valid_for_analysis ? esc(number(p.prediction)) : '—', p.valid_for_analysis ? `change ${esc(number(p.prediction_change, true))}` : 'not reported')}${arrow}
      ${step('Impact', p.valid_for_analysis ? esc(number(p.impact, true)) : '—', 'per unit of achieved change', 'accent')}
    </div>
    <div class="g-concl-grid">
      <div class="g-evidence"><h5>${gIcon('spark', 16)} The evidence at a glance</h5><ul>${gEvidence(r, g).map(e => `<li class="g-e-${e.state}">${gIcon(icons[e.state], 18)}<div><b>${esc(e.title)}</b><span>${esc(e.text)}</span></div></li>`).join('')}</ul></div>
      <div class="g-concl-side">
        <div class="g-ringbox">${ring}<div><b>Valid tests</b><span>${c.valid} of ${c.total} settings across all models, concepts and sizes</span></div></div>
        <div class="g-remember">${gIcon('shield', 20)}<div><b>Keep in mind</b><span>This shows how the <i>model</i> reacts to a controlled change — not that ${esc(g.selected_concept)} causes anything in the real network.</span></div></div>
      </div>
    </div>
    <details class="g-fulltext"><summary>${gIcon('book', 16)} Read the full written conclusion</summary><p>${esc(g.conclusion)}</p></details>`;
}

/* ---------- SVG chart renderers ---------- */
function gWrap(text, maxChars) {
  const words = String(text).split(' '), lines = [''];
  words.forEach(w => { if ((lines[lines.length - 1] + ' ' + w).trim().length > maxChars) lines.push(w); else lines[lines.length - 1] = (lines[lines.length - 1] + ' ' + w).trim(); });
  return lines.filter(Boolean);
}
function gKeyBand(guide, width, y0) {
  // "How to read" band inside the SVG, so it travels with PNG/SVG downloads.
  if (!guide || (!guide.x && !guide.y && !(guide.colors || []).length)) return ['', 0];
  const max = Math.floor((width - 40) / 7.2);
  let s = `<line x1="15" x2="${width - 15}" y1="${y0}" y2="${y0}" stroke="#d7e0ea"/>`, y = y0 + 20;
  const row = (label, text) => {
    gWrap(text, max - label.length - 2).forEach((line, i) => {
      s += `<text x="15" y="${y}" font-size="13" fill="${G_INK}">${i ? '' : `<tspan font-weight="bold">${esc(label)}</tspan> `}${esc(line)}</text>`; y += 18; });
  };
  if (guide.x) row('↔ Across:', guide.x);
  if (guide.y) row('↕ Up/down:', guide.y);
  (guide.colors || []).forEach(c => {
    gWrap(c.meaning, max - 4).forEach((line, i) => { s += (i ? '' : `<rect x="15" y="${y - 11}" width="12" height="12" rx="2" fill="${c.color}" stroke="#9aa9b8" stroke-width=".5"/>`) + `<text x="34" y="${y}" font-size="13" fill="${G_INK}">${esc(line)}</text>`; y += 18; });
  });
  return [s, y - y0 + 4];
}
function gFrame(title, content, width, height) {
  const g = G.result.guided;
  if (G.currentChart?.title) title = G.currentChart.title;   // the image carries the same title as its card
  const caption = `TGAP guided study | ${g.spec.dataset} | ${gName.model(g.spec.model)} | ${gTerms(g.selected_concept)} ${g.spec.direction} ${gPct(g.spec.delta)} | seed ${g.spec.seed} | run ${G.job.slice(0, 8)}`;
  const [key, keyH] = gKeyBand(G.currentChart?.guide, width, height + 48);
  const total = height + 70 + keyH;
  return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${width} ${total}"${width > 900 ? ` style="min-width:${Math.round(width * .85)}px"` : ''} role="img" aria-label="${esc(gTerms(title))}" style="font-family:Arial,sans-serif;background:white"><title>${esc(gTerms(title))}</title><rect width="${width}" height="${total}" fill="white"/>
    <text x="15" y="26" font-size="17" font-weight="bold" fill="${G_INK}">${esc(gTerms(title))}</text><g transform="translate(0 40)">${content}</g>
    ${key}<text x="15" y="${total - 10}" font-size="12" fill="#61748c">${esc(caption)}</text></svg>`;
}
function gText(x, y, text, opts = {}) {
  return `<text x="${x}" y="${y}" font-size="${opts.size || 13}" fill="${opts.fill || G_MUTED}" text-anchor="${opts.anchor || 'start'}"${opts.weight ? ` font-weight="${opts.weight}"` : ''}${opts.rotate ? ` transform="rotate(${opts.rotate} ${x} ${y})"` : ''}>${esc(opts.raw ? text : gTerms(text))}</text>`;
}
function gScale(min, max, a, b) { const span = max - min || 1; return v => a + (v - min) / span * (b - a); }
function gExtent(values, includeZero = true) {
  const v = values.filter(x => x !== null && x !== undefined && Number.isFinite(x));
  if (v.length && v.every(x => Math.abs(x) < 1e-9)) return [-1, 1];   // all rounding noise: show as zero
  let lo = Math.min(...v, includeZero ? 0 : Infinity), hi = Math.max(...v, includeZero ? 0 : -Infinity);
  if (!v.length) { lo = -1; hi = 1; }
  if (lo === hi) { lo -= Math.abs(lo) * .1 || 1; hi += Math.abs(hi) * .1 || 1; }
  const pad = (hi - lo) * .06;
  return [lo - (lo < 0 ? pad : 0), hi + (hi > 0 ? pad : 0)];
}
function gColor(v) { return v > 1e-9 ? G_POS : v < -1e-9 ? G_NEG : G_ZERO; }  // below 1e-9 is rounding noise
function gPack(values, x, center, step = 11, maxRows = 6) {
  // Deterministic beeswarm packing: place each point at the nearest free offset.
  const placed = [];
  return values.map(v => {
    const px = x(v);
    let offset = 0;
    for (let k = 0; k <= maxRows * 2; k++) {
      const candidate = (k % 2 ? 1 : -1) * Math.ceil(k / 2) * step;
      if (placed.every(p => Math.hypot(p.x - px, p.y - (center + candidate)) >= step - 1)) { offset = candidate; break; }
    }
    placed.push({x: px, y: center + offset});
    return {x: px, y: center + offset};
  });
}
function gTick(v) { if (Math.abs(v) < 1e-12) return '0'; const t = +v.toPrecision(3); return (t > 0 ? '+' : t < 0 ? '−' : '') + Math.abs(t); }
function gAxisX(x, lo, hi, y, label, fmtv = gTick) {
  let s = `<line x1="${x(lo)}" x2="${x(hi)}" y1="${y}" y2="${y}" stroke="#cad7e4"/>`;
  for (let i = 0; i <= 4; i++) { const v = lo + (hi - lo) * i / 4; s += gText(x(v), y + 17, fmtv(v), {anchor: 'middle', size: 12}); }
  return s + (label ? gText((x(lo) + x(hi)) / 2, y + 36, label, {anchor: 'middle'}) : '');
}
function gAxisY(y, lo, hi, x0, x1, label) {
  let s = '';
  for (let i = 0; i <= 4; i++) { const v = lo + (hi - lo) * i / 4; s += `<line x1="${x0}" x2="${x1}" y1="${y(v)}" y2="${y(v)}" stroke="${G_GRID}"/>` + gText(x0 - 6, y(v) + 4, gTick(v), {anchor: 'end', size: 12}); }
  return s + (label ? gText(16, (y(lo) + y(hi)) / 2, label, {anchor: 'middle', rotate: -90}) : '');
}
function gLegend(items, x, y) {
  return items.map(([color, label], i) => `<circle cx="${x + i * 170}" cy="${y}" r="5" fill="${color}"/>` + gText(x + 10 + i * 170, y + 4, label, {size: 12})).join('');
}
function gWithMain(fn) {
  // Reuse the Laboratory's measured-figure renderers, which read state.result/state.job.
  const saved = [state.result, state.job];
  state.result = G.result; state.job = G.job;
  try { return fn(); } finally { [state.result, state.job] = saved; }
}

const gRender_ = {
  workflow(chart) {
    const d = chart.data;
    const boxes = [['Input graph', `${d.dataset}`, `${d.nodes} nodes · ${d.snapshots} snapshots`], ['Concept change', d.concept, `${d.direction} · both directions run`],
      ['Same model', d.model, `${d.core_calls} calls (1 + 2K)`], ['Normalized impact', `${d.valid_rows}/${d.total_rows} valid`, `+ ${d.matrix_calls} matrix · ${d.figure_calls} element calls`]];
    let s = '';
    boxes.forEach(([t, a, b], i) => {
      const x = 12 + i * 186;
      s += `<rect x="${x}" y="10" width="166" height="104" rx="9" fill="${i === 3 ? '#e5f3ef' : '#edf3fb'}" stroke="#cfdeeb"/>` + gText(x + 83, 38, t, {anchor: 'middle', size: 15, fill: G_INK, weight: 'bold'})
        + gText(x + 83, 64, String(a).slice(0, 24), {anchor: 'middle', size: 13, fill: G_INK}) + gText(x + 83, 88, String(b).slice(0, 26), {anchor: 'middle', size: 11.5});
      if (i < 3) s += gText(x + 176, 68, '→', {anchor: 'middle', size: 20, fill: '#6989a7'});
    });
    return gFrame('Your TGAP explanation workflow', s, 760, 125);
  },
  req_ach(chart) {
    const rows = chart.data.selected.filter(r => r.measured_achieved_delta !== null);
    const W = 760, H = 330, x = gScale(...gExtent(rows.map(r => r.requested_delta)), 90, W - 30), [ylo, yhi] = gExtent(rows.map(r => r.measured_achieved_delta)), y = gScale(ylo, yhi, H - 50, 15);
    const [xlo, xhi] = gExtent(rows.map(r => r.requested_delta));
    let s = gAxisY(y, ylo, yhi, 90, W - 30, rows[0]?.delta_mode === 'relative' ? 'Achieved relative change' : 'Achieved change (absolute units)');
    s += `<line x1="${x(0)}" x2="${x(0)}" y1="${y(yhi)}" y2="${y(ylo)}" stroke="#cad7e4"/>`;
    if (rows[0]?.delta_mode === 'relative' && chart.data.selected[0]?.concept !== 'Centralization') {
      const a = Math.max(xlo, ylo), b = Math.min(xhi, yhi);
      if (b > a) s += `<line x1="${x(a)}" y1="${y(a)}" x2="${x(b)}" y2="${y(b)}" stroke="#9db6cf" stroke-dasharray="5 4"/>` + gText(x(b) - 4, y(b) - 6, 'achieved = requested', {anchor: 'end', size: 11});
    }
    rows.forEach(r => {
      const valid = r.valid_for_analysis && !r.noop;
      s += valid ? `<circle cx="${x(r.requested_delta)}" cy="${y(r.measured_achieved_delta)}" r="6" fill="${gColor(r.requested_delta)}"><title>requested ${gSigned(r.requested_delta)}, achieved ${number(r.measured_achieved_delta, true)}</title></circle>`
        : `<g><title>${esc(r.status)} · requested ${gSigned(r.requested_delta)} · measured ${number(r.measured_achieved_delta, true)} (excluded)</title><path d="M${x(r.requested_delta) - 6} ${y(r.measured_achieved_delta) - 6}l12 12m0 -12l-12 12" stroke="#a25353" stroke-width="2.5"/></g>`;
    });
    s += gAxisX(x, xlo, xhi, H - 50, 'Requested change (signed)', v => `${v < 0 ? '−' : '+'}${+(Math.abs(v) * 100).toFixed(0)}%`);
    s += gLegend([[G_POS, 'valid increase'], [G_NEG, 'valid decrease'], ['#a25353', '✕ excluded (measured, not used)']], 100, H + 2);
    const table = `<table class="g-table"><thead><tr><th>Concept</th><th>Direction</th><th>Requested</th><th>Achieved (measured)</th><th>Status</th></tr></thead><tbody>${chart.data.all_concepts.map(r => `<tr><td>${esc(r.concept)}</td><td>${esc(r.direction)}</td><td>${gSigned(r.requested_delta)}</td><td>${r.measured_achieved_delta === null ? '—' : esc(r.delta_mode === 'relative' ? number(r.measured_achieved_delta * 100, true) + '%' : number(r.measured_achieved_delta, true) + ' abs')}</td><td>${gValidityTag(r.status)}${r.noop ? ' <span class="tag warning">no-op</span>' : ''}</td></tr>`).join('')}</tbody></table>`;
    return gFrame(`Requested versus achieved: ${chart.data.selected[0]?.concept || ''}`, s, W, H + 10) + `<p class="field-help">All concepts at your requested size (same counterfactual graphs for every model):</p>${table}`;
  },
  validity(chart) {
    const d = chart.data, cols = [];
    d.deltas.forEach(delta => ['increase', 'decrease'].forEach(dir => cols.push([delta, dir])));
    const cw = 64, W = Math.max(560, 170 + cols.length * cw), H = 50 + d.concepts.length * 38;
    const color = {ok: '#e3f1ea', edge_count_infeasible: '#f8dcd9', saturated: '#fbe7cd', wrong_direction: '#efd9f0', no_property_change: '#e6e6e6'};
    let s = cols.map(([delta, dir], i) => gText(170 + i * cw + cw / 2, 14, `${dir === 'increase' ? '+' : '−'}${gPct(delta)}`, {anchor: 'middle', size: 12})).join('');
    d.concepts.forEach((concept, j) => {
      s += gText(160, 46 + j * 38, concept, {anchor: 'end', size: 13, fill: G_INK});
      cols.forEach(([delta, dir], i) => {
        const cell = d.grid.find(g => g.concept === concept && Math.abs(g.delta - delta) < 1e-9 && g.direction === dir);
        const st = cell?.status || 'missing';
        s += `<rect x="${170 + i * cw}" y="${26 + j * 38}" width="${cw - 4}" height="32" rx="4" fill="${color[st] || '#f3f6fa'}"><title>${esc(concept)} ${dir} ${gPct(delta)}: ${esc(st)}${cell?.reason ? ' — ' + esc(cell.reason) : ''}</title></rect>`
          + gText(170 + i * cw + cw / 2 - 2, 46 + j * 38, st === 'ok' ? (cell.noop ? 'no-op' : 'valid') : st === 'missing' ? '—' : st.replace('edge_count_infeasible', 'edges').replace('no_property_change', 'no change').replace('wrong_direction', 'wrong dir'), {anchor: 'middle', size: 11, fill: G_INK});
      });
    });
    const c = d.counts;
    const table = `<table class="g-table"><thead><tr><th>Total rows</th><th>Valid</th><th>Invalid</th><th>Edge-count infeasible</th><th>Saturated</th><th>Wrong direction</th><th>No property change</th></tr></thead><tbody><tr><td>${c.total}</td><td>${c.valid}</td><td>${c.invalid}</td><td>${c.edge_count_infeasible}</td><td>${c.saturated}</td><td>${c.wrong_direction}</td><td>${c.no_property_change}</td></tr></tbody></table>`;
    return gFrame('Validity of every tested setting (same for every model)', s, W, H) + `<p class="field-help">Counts across all ${d.models} model(s), in the format of the paper's Table 5:</p>${table}`;
  },
  delta(chart) {
    const rows = chart.data.rows, W = 760, H = 320;
    const valid = rows.filter(r => r.valid_for_analysis && !r.noop && r.impact !== null);
    const [xlo, xhi] = [0, Math.max(...rows.map(r => r.sweep_delta)) * 1.08], x = gScale(xlo, xhi, 90, W - 30);
    const [ylo, yhi] = gExtent(valid.map(r => r.impact)), y = gScale(ylo, yhi, H - 50, 15);
    let s = gAxisY(y, ylo, yhi, 90, W - 30, 'Normalized impact');
    for (const [dir, color] of [['increase', G_POS], ['decrease', G_NEG]]) {
      const pts = valid.filter(r => r.direction === dir).sort((a, b) => a.sweep_delta - b.sweep_delta);
      if (pts.length > 1) s += `<polyline fill="none" stroke="${color}" stroke-width="1.5" opacity=".6" points="${pts.map(r => `${x(r.sweep_delta)},${y(r.impact)}`).join(' ')}"/>`;
      pts.forEach(r => { s += `<circle cx="${x(r.sweep_delta)}" cy="${y(r.impact)}" r="6" fill="${color}"><title>${dir} ${gPct(r.sweep_delta)}: impact ${number(r.impact, true)}, achieved ${number(r.achieved_delta, true)}</title></circle>`; });
    }
    rows.filter(r => !r.valid_for_analysis || r.noop).forEach(r => {
      const yy = r.direction === 'increase' ? H - 62 : H - 74;
      s += `<g><title>${r.direction} ${gPct(r.sweep_delta)}: ${r.noop ? 'no-op' : esc(r.status)}</title><path d="M${x(r.sweep_delta) - 5} ${yy - 5}l10 10m0 -10l-10 10" stroke="${r.noop ? G_ZERO : '#a25353'}" stroke-width="2"/></g>`;
    });
    s += gAxisX(x, xlo, xhi, H - 50, 'Requested change (magnitude)', v => `${+(v * 100).toFixed(0)}%`);
    s += gLegend([[G_POS, 'increase'], [G_NEG, 'decrease'], ['#a25353', '✕ excluded / no-op (no value)']], 100, H + 2);
    return gFrame('Normalized impact by request size', s, W, H + 10);
  },
  normalization(chart) {
    const rows = chart.data.rows.filter(r => r.valid_for_analysis && !r.noop && r.impact !== null);
    if (!rows.length) return '<p class="result-note">No valid, active rows to compare.</p>';
    const W = 760, H = 300, groups = rows.map(r => `${r.direction === 'increase' ? '+' : '−'}${gPct(r.sweep_delta)}`);
    const [lo, hi] = gExtent(rows.flatMap(r => [r.impact, r.impact_requested_normalization])), y = gScale(lo, hi, H - 50, 15);
    const gw = (W - 120) / rows.length;
    let s = gAxisY(y, lo, hi, 90, W - 30, 'Impact');
    rows.forEach((r, i) => {
      const x0 = 100 + i * gw;
      [[r.impact, G_POS, 'achieved'], [r.impact_requested_normalization, '#9db6cf', 'requested']].forEach(([v, color, label], k) => {
        const bx = x0 + 8 + k * (gw / 2 - 8);
        s += `<rect x="${bx}" y="${Math.min(y(0), y(v))}" width="${Math.max(4, gw / 2 - 14)}" height="${Math.abs(y(v) - y(0)) || 1}" fill="${color}"><title>${groups[i]} ${label}-normalized: ${number(v, true)}</title></rect>`;
      });
      s += gText(x0 + gw / 2, H - 32, groups[i], {anchor: 'middle', size: 12});
    });
    s += `<line x1="90" x2="${W - 30}" y1="${y(0)}" y2="${y(0)}" stroke="#8a9db2"/>`;
    s += gLegend([[G_POS, 'achieved-change normalization (TGAP)'], ['#9db6cf', 'requested-change normalization']], 100, H - 8);
    return gFrame('Impact under achieved and requested normalization', s, W, H);
  },
  strips(chart) {
    const d = chart.data, models = d.models, rows = d.semantic_rows.flatMap(gr => gr.concepts.map(c => [gr.label, c]));
    const pw = 210, rh = 34, W = 170 + models.length * pw, H = 52 + rows.length * rh + 30;
    let s = models.map((m, i) => gName.model(m).split(' — ').map((part, k) => gText(170 + i * pw + pw / 2, k ? 20 : 6, part, {anchor: 'middle', size: 12, fill: G_INK, weight: 'bold', raw: true})).join('')).join('');
    let prevGroup = null;
    rows.forEach(([group, concept], j) => {
      const yy = 52 + j * rh;
      if (group !== prevGroup) { s += `<line x1="10" x2="${W - 10}" y1="${yy - 16}" y2="${yy - 16}" stroke="#cad7e4" stroke-dasharray="${prevGroup ? '4 3' : '0'}"/>` + gText(12, yy - 19, group === concept ? '' : `[${group}]`, {size: 10}); prevGroup = group; }
      s += gText(160, yy + 4, concept, {anchor: 'end', size: 12, fill: G_INK});
    });
    models.forEach((m, i) => {
      const x0 = 175 + i * pw, x1 = x0 + pw - 20;
      const cells = d.panels.filter(p => p.model === m);
      const values = cells.flatMap(p => p.points.map(pt => pt.impact));
      const [lo, hi] = gExtent(values), x = gScale(lo, hi, x0, x1);
      if (values.length) s += `<line x1="${x(0)}" x2="${x(0)}" y1="22" y2="${H - 40}" stroke="#8a9db2"/>` + gText(x0, H - 22, number(lo, true), {size: 10}) + gText(x1, H - 22, number(hi, true), {size: 10, anchor: 'end'});
      rows.forEach(([group, concept], j) => {
        const cell = cells.find(p => p.concept === concept && p.group === group), yy = 52 + j * rh;
        if (!cell || !cell.n) { s += gText((x0 + x1) / 2, yy + 4, 'no valid obs. (n=0)', {anchor: 'middle', size: 10}); return; }
        gPack(cell.points.map(p => p.impact), x, yy, 8, 2).forEach((pt, k) => {
          const p = cell.points[k];
          s += `<circle cx="${pt.x}" cy="${pt.y}" r="4" fill="${gColor(p.impact)}" stroke="#223" stroke-width=".3"><title>${esc(gName.model(m))} · ${esc(concept)} · ${p.direction} ${gPct(p.delta)}: ${number(p.impact, true)}</title></circle>`;
        });
        s += gText(x1 + 2, yy - 6, `n=${cell.n}`, {size: 9, anchor: 'end'});
      });
    });
    s += gText(170, H - 6, 'Impact (each model panel has its own axis; rows separate incompatible perturbation units)', {size: 12});
    return gFrame('TGAP impacts, separated by model and perturbation semantics', s, W, H);
  },
  beeswarm(chart) {
    const groups = chart.data.groups, rowsN = groups.reduce((n, g) => n + g.concepts.length, 0), W = 780, H = 30 + rowsN * 70 + groups.length * 20;
    let s = '', yy = 20;
    groups.forEach(group => {
      const values = group.concepts.flatMap(c => c.points.map(p => p.impact));
      const [lo, hi] = gExtent(values), x = gScale(lo, hi, 190, W - 30);
      s += gText(12, yy, `${group.label}`, {size: 12, fill: G_INK, weight: 'bold'});
      group.concepts.forEach(c => {
        yy += 70;
        s += gText(180, yy - 26, c.concept, {anchor: 'end', size: 12, fill: G_INK});
        if (!c.points.length) { s += gText((190 + W - 30) / 2, yy - 26, 'no valid obs. (n=0)', {anchor: 'middle', size: 11}); return; }
        s += `<line x1="${x(0)}" x2="${x(0)}" y1="${yy - 58}" y2="${yy + 4}" stroke="#8a9db2"/>`;
        gPack(c.points.map(p => p.impact), x, yy - 26, 9, 3).forEach((pt, k) => {
          const p = c.points[k];
          s += `<circle cx="${pt.x}" cy="${pt.y}" r="4.5" fill="${gColor(p.impact)}" opacity=".85"><title>${esc(gName.model(p.model))} · ${p.direction} ${gPct(p.delta)}: ${number(p.impact, true)}</title></circle>`;
        });
        s += gText(W - 30, yy - 46, `n=${c.points.length}`, {anchor: 'end', size: 11}) + gText(190, yy + 14, number(lo, true), {size: 10}) + gText(W - 30, yy + 14, number(hi, true), {size: 10, anchor: 'end'});
      });
      yy += 20;
    });
    return gFrame('Beeswarm of valid TGAP impacts (deterministic packing)', s, W, H);
  },
  boxplot(chart) {
    const d = chart.data, pw = 290, W = Math.max(760, 30 + Math.min(3, d.panels.length) * pw), perRow = Math.min(3, d.panels.length), rowsN = Math.ceil(d.panels.length / perRow);
    const ph = 40 + d.concepts.length * 44, H = rowsN * (ph + 30);
    let s = '';
    d.panels.forEach((panel, i) => {
      const x0 = 15 + (i % perRow) * pw, y0 = Math.floor(i / perRow) * (ph + 30), x1 = x0 + pw - 30;
      const values = panel.boxes.flatMap(b => b.values || []);
      const [lo, hi] = gExtent(values), x = gScale(lo, hi, x0 + 140, x1);
      s += gText(x0, y0 + 14, gName.model(panel.model), {size: 12, fill: G_INK, weight: 'bold'});
      if (values.length) s += `<line x1="${x(0)}" x2="${x(0)}" y1="${y0 + 24}" y2="${y0 + ph - 8}" stroke="#8a9db2"/>`;
      panel.boxes.forEach((b, j) => {
        const yy = y0 + 44 + j * 44;
        s += gText(x0 + 134, yy + 4, b.concept, {anchor: 'end', size: 11, fill: G_INK});
        if (!b.n) { s += gText((x0 + 140 + x1) / 2, yy + 4, 'n=0', {anchor: 'middle', size: 10}); return; }
        s += `<line x1="${x(b.whisker_low)}" x2="${x(b.whisker_high)}" y1="${yy}" y2="${yy}" stroke="${G_POS}"/><rect x="${x(b.q1)}" y="${yy - 12}" width="${Math.max(1.5, x(b.q3) - x(b.q1))}" height="24" fill="#d7e5f2" stroke="${G_POS}"/><line x1="${x(b.median)}" x2="${x(b.median)}" y1="${yy - 12}" y2="${yy + 12}" stroke="#18283e" stroke-width="2"><title>median ${number(b.median, true)}, IQR ${number(b.q1, true)} to ${number(b.q3, true)}, n=${b.n}</title></line>`;
        b.values.forEach(v => { s += `<circle cx="${x(v)}" cy="${yy}" r="2.6" fill="${gColor(v)}" opacity=".8"><title>${number(v, true)}</title></circle>`; });
        s += gText(x1, yy - 14, `n=${b.n}`, {anchor: 'end', size: 10});
      });
      s += gText(x0 + 140, y0 + ph + 8, number(lo, true), {size: 10}) + gText(x1, y0 + ph + 8, number(hi, true), {size: 10, anchor: 'end'});
    });
    return gFrame('Distribution of valid impacts per model (relative-delta concepts)', s, W, H);
  },
  signedlog(chart) {
    const cs = chart.data.concepts, W = 780, H = 30 + cs.length * 64;
    const all = cs.flatMap(c => c.points.map(p => p.shown)), m = Math.max(...all.map(Math.abs), .1), x = gScale(-m, m, 190, W - 30);
    let s = `<line x1="${x(0)}" x2="${x(0)}" y1="0" y2="${H - 30}" stroke="#8a9db2"/>`;
    cs.forEach((c, j) => {
      const yy = 30 + j * 64;
      s += gText(180, yy + 4, c.concept, {anchor: 'end', size: 12, fill: G_INK});
      gPack(c.points.map(p => p.shown), x, yy, 8, 3).forEach((pt, k) => {
        const p = c.points[k];
        s += `<circle cx="${pt.x}" cy="${pt.y}" r="3.6" fill="${gColor(p.impact)}" opacity=".6"><title>${esc(gName.model(p.model))}: impact ${number(p.impact, true)}</title></circle>`;
      });
    });
    s += gAxisX(x, -m, m, H - 28, 'sign(impact) · log10(1 + |impact|)', v => number(v, true));
    return gFrame('Impact distribution per concept (signed-log, exploratory)', s, W, H + 20);
  },
  matched(chart) {
    const pairs = chart.data.pairs;
    return `<table class="g-table"><thead><tr><th>Pair</th><th>Direction</th><th>Comparable?</th><th>Matched achieved changes</th><th>Matched impacts</th><th>Larger |impact|</th></tr></thead><tbody>${pairs.map(p => `<tr><td>${esc(p.first)} vs ${esc(p.second)}</td><td>${esc(p.direction)}</td><td>${p.comparable ? '<span class="tag success">yes</span>' : `<span class="tag">no</span> <small>${esc(p.reason || '')}</small>`}</td><td>${p.first_achieved !== undefined && p.first_achieved !== null ? `${number(p.first_achieved, true)} / ${number(p.second_achieved, true)} (gap ${number(p.gap * 100)}%)` : '—'}</td><td>${p.comparable ? `${number(p.first_impact, true)} / ${number(p.second_impact, true)}` : '—'}</td><td>${p.comparable ? esc(p.larger) : '—'}</td></tr>`).join('')}</tbody></table>`;
  },
  model_bars(chart) {
    const d = chart.data, delta = d.shown_delta ?? G.result.guided.spec.delta, W = 780, H = 300;
    const rows = d.rows.filter(r => Math.abs(r.delta - delta) < 1e-9);
    const vals = rows.filter(r => r.valid_for_analysis).map(r => r.impact);
    const [lo, hi] = gExtent(vals), y = gScale(lo, hi, H - 60, 15), gw = (W - 120) / d.models.length;
    let s = gAxisY(y, lo, hi, 90, W - 30, `Bridge Trend impact at ${gPct(delta)}`);
    d.models.forEach((m, i) => {
      const x0 = 100 + i * gw;
      ['increase', 'decrease'].forEach((dir, k) => {
        const r = rows.find(z => z.model === m && z.direction === dir), bx = x0 + 6 + k * (gw / 2 - 4), bw = Math.max(4, gw / 2 - 12);
        if (!r || !r.valid_for_analysis) s += gText(bx + bw / 2, y(0) - 6, '✕', {anchor: 'middle', size: 14, fill: '#a25353'}) + `<title>${dir}: ${esc(r?.status || 'missing')}</title>`;
        else s += `<rect x="${bx}" y="${Math.min(y(0), y(r.impact))}" width="${bw}" height="${Math.max(1.5, Math.abs(y(r.impact) - y(0)))}" fill="${dir === 'increase' ? G_POS : G_NEG}"><title>${esc(gName.model(m))} ${dir}: ${number(r.impact, true)}</title></rect>`;
      });
      s += gText(x0 + gw / 2, H - 42, gName.model(m).replace(' · ', ' '), {anchor: 'middle', size: 10.5});
    });
    s += `<line x1="90" x2="${W - 30}" y1="${y(0)}" y2="${y(0)}" stroke="#8a9db2"/>` + gLegend([[G_POS, 'increase'], [G_NEG, 'decrease'], ['#a25353', '✕ invalid (no value)']], 100, H - 12);
    return gFrame('History-only edit (Bridge Trend): response by model', s, W, H);
  },
  temporal(chart) {
    const panels = chart.data.panels, W = 780, ph = 150, H = panels.length * (ph + 16);
    let s = '';
    panels.forEach((p, i) => {
      const y0 = i * (ph + 16);
      s += gText(12, y0 + 14, gName.model(p.model), {size: 12, fill: G_INK, weight: 'bold'});
      if (!p.valid_for_analysis) { s += gText(W / 2, y0 + 70, `Not computed: ${p.status.replaceAll('_', ' ')}`, {anchor: 'middle'}); return; }
      const vals = p.rows.filter(r => r.valid).map(r => r.impact), [lo, hi] = gExtent(vals), y = gScale(lo, hi, y0 + ph - 24, y0 + 24), bw = (W - 140) / p.rows.length;
      s += `<line x1="110" x2="${W - 30}" y1="${y(0)}" y2="${y(0)}" stroke="#8a9db2"/>` + gText(104, y(hi) + 4, number(hi, true), {anchor: 'end', size: 10}) + gText(104, y(lo) + 4, number(lo, true), {anchor: 'end', size: 10});
      p.rows.forEach((r, k) => {
        const bx = 115 + k * bw;
        if (!r.valid) s += gText(bx + bw / 2, y(0) - 4, '✕', {anchor: 'middle', size: 12, fill: '#a25353'});
        else s += `<rect x="${bx}" y="${Math.min(y(0), y(r.impact))}" width="${Math.max(2, bw - 4)}" height="${Math.max(1, Math.abs(y(r.impact) - y(0)))}" fill="${gColor(r.impact)}"><title>${esc(r.label)}: ${number(r.impact, true)} (+${r.edges_added}/−${r.edges_removed} edges)</title></rect>`;
        if (p.rows.length <= 20) s += gText(bx + bw / 2 - 2, y0 + ph - 6, String(k + 1), {anchor: 'middle', size: 10});
      });
    });
    return gFrame(`When ${chart.data.concept} matters: one snapshot at a time (x: snapshot, y: prediction difference)`, s, W, H);
  },
  trajectory(chart) {
    const d = chart.data, metric = G.trajMetric, names = {bridge: 'Bridge Width', density: 'Density', centralization: 'Centralization'};
    const series = [['Original', d.original, '#29445f', '']].concat(Object.entries(d.transformed).map(([dir, t]) => [`${dir} (${d.status[dir]})`, t, dir === 'increase' ? G_POS : G_NEG, '6 4']));
    const W = 780, H = 300, n = d.original.length, x = gScale(0, Math.max(1, n - 1), 90, W - 30);
    const [lo, hi] = gExtent(series.flatMap(([, t]) => t.map(r => r[metric])), false), y = gScale(lo, hi, H - 60, 15);
    let s = gAxisY(y, lo, hi, 90, W - 30, names[metric]);
    series.forEach(([label, t, color, dash]) => {
      s += `<polyline fill="none" stroke="${color}" stroke-width="2" ${dash ? `stroke-dasharray="${dash}"` : ''} points="${t.map((r, i) => `${x(i)},${y(r[metric])}`).join(' ')}"/>`;
      t.forEach((r, i) => { s += `<circle cx="${x(i)}" cy="${y(r[metric])}" r="3" fill="${color}"><title>${esc(label)} · ${esc(r.label)}: ${number(r[metric])}</title></circle>`; });
    });
    for (let i = 0; i < n; i += Math.max(1, Math.ceil(n / 12))) s += gText(x(i), H - 42, String(i + 1), {anchor: 'middle', size: 11});
    s += gText((90 + W - 30) / 2, H - 24, 'Snapshot', {anchor: 'middle'}) + gLegend(series.map(([label, , color]) => [color, label]), 100, H - 4);
    const select = `<div class="g-row g-tight"><label for="g-traj-metric">Measure</label><select id="g-traj-metric">${Object.entries(names).map(([k, v]) => `<option value="${k}" ${k === metric ? 'selected' : ''}>${v}</option>`).join('')}</select></div>`;
    return select + gFrame(`${names[metric]} through time: original and transformed`, s, W, H + 6);
  },
  edge_time(chart) { return gWithMain(() => liveEdgeTime(G.result.analyses)); },
  bars(chart) { return gWithMain(() => liveBar(chart.data.rows, row => 'Edge ' + row.u + '–' + row.v, 'Measured edge removals (whole history)')); },
  dependence(chart) {
    return gWithMain(() => (chart.data.nodes ? liveScatter(chart.data.nodes.rows, 'total_degree', 'Node structure versus measured response', 'Total degree across snapshots') : '')
      + (chart.data.edges ? liveScatter(chart.data.edges.rows, 'snapshots_present', 'Edge persistence versus measured response', 'Snapshots containing the edge') : ''));
  },
  network(chart) {
    const view = chart.data.view, per = chart.data.per_snapshot, n = view.snapshots.length;
    const index = G.snapshot === null ? n - 1 : Math.min(G.snapshot, n - 1), snap = view.snapshots[index];
    const W = 780, H = 400, pw = (W - 30) / 2, top = 30, bottom = H - 95;
    const key = e => e.map(String).sort().join('|');
    // Nodes with a tie in any snapshot are laid out; inactive ones go to a small row below.
    const activeIds = new Set();
    view.snapshots.forEach(sn => [...sn.edges, ...sn.added].forEach(([u, v]) => { activeIds.add(String(u)); activeIds.add(String(v)); }));
    const active = view.nodes.filter(nd => activeIds.has(String(nd.id))), idle = view.nodes.filter(nd => !activeIds.has(String(nd.id)));
    const xs = active.map(nd => nd.x), ys = active.map(nd => nd.y);
    // Zoom to the central 94% of nodes; a few far-away nodes are pinned to the frame edge.
    const q = (v, f) => { const o = [...v].sort((a, b) => a - b); return o[Math.min(o.length - 1, Math.max(0, Math.round(f * (o.length - 1))))]; };
    const [x0, x1, y0, y1] = [q(xs, .03), q(xs, .97), q(ys, .03), q(ys, .97)];
    const clamp = (v, lo, hi) => Math.max(lo, Math.min(hi, v));
    const pos = new Map(active.map(nd => [String(nd.id), nd]));
    const sx = (v, off) => off + 18 + clamp((v - x0) / ((x1 - x0) || 1), -.02, 1.02) * (pw - 36), sy = v => top + clamp((v - y0) / ((y1 - y0) || 1), -.02, 1.02) * (bottom - top);
    const palette = ['#547ba8', '#60a0a0', '#ba8a55', '#927ba3', '#7d9b5a', '#a86a7d'];
    const removed = snap.removed, added = snap.added, removedSet = new Set(removed.map(key));
    const touched = new Set([...removed, ...added].flat().map(String));
    const panel = (off, title, transformed) => {
      const changes = transformed ? added : removed, color = transformed ? G_POS : G_NEG;
      let s = gText(off + 12, 14, title, {size: 13, fill: G_INK, weight: 'bold'});
      const line = (e, stroke, width, extra = '') => { const a = pos.get(String(e[0])), b = pos.get(String(e[1])); return a && b ? `<line x1="${sx(a.x, off)}" y1="${sy(a.y)}" x2="${sx(b.x, off)}" y2="${sy(b.y)}" stroke="${stroke}" stroke-width="${width}" stroke-linecap="round" ${extra}/>` : ''; };
      snap.edges.slice(0, 4000).forEach(e => { if (!(transformed && removedSet.has(key(e))) && !(!transformed && removedSet.has(key(e)))) s += line(e, '#d3dee9', .6, 'opacity=".7"'); });
      active.forEach(nd => { if (!touched.has(String(nd.id))) s += `<circle cx="${sx(nd.x, off)}" cy="${sy(nd.y)}" r="3" fill="${palette[nd.community % palette.length] || '#a7b3c1'}" opacity=".55"><title>${esc(nd.id)} · ${esc(view.community_labels[nd.community] || '')}</title></circle>`; });
      // Changed edges last: white halo + thick colour so they stay visible in dense graphs.
      changes.forEach(e => { s += line(e, '#fff', 7) + line(e, color, 3.4, transformed ? '' : 'stroke-dasharray="7 4"'); });
      active.forEach(nd => { if (touched.has(String(nd.id))) s += `<circle cx="${sx(nd.x, off)}" cy="${sy(nd.y)}" r="9" fill="${color}" opacity=".18"/><circle cx="${sx(nd.x, off)}" cy="${sy(nd.y)}" r="4.8" fill="${palette[nd.community % palette.length] || '#a7b3c1'}" stroke="${color}" stroke-width="2"><title>${esc(nd.id)} · ${esc(view.community_labels[nd.community] || '')} · touched by the change</title></circle>`; });
      if (!changes.length) s += gText(off + pw / 2, bottom + 14, transformed ? 'no edges added in this snapshot' : 'no edges removed in this snapshot', {anchor: 'middle', size: 11});
      return s;
    };
    let content = panel(0, `Original — removed edges in orange (${removed.length})`, false) + panel(pw + 30, `Transformed (${view.direction}) — added edges in blue (${added.length})`, true);
    content += `<line x1="${pw + 15}" x2="${pw + 15}" y1="20" y2="${bottom + 10}" stroke="#e3e8ee"/>`;
    if (idle.length) content += gText(18, bottom + 34, `${idle.length} inactive node${idle.length > 1 ? 's' : ''} (no ties in any snapshot) are not drawn.`, {size: 11});
    content += `<line x1="20" x2="48" y1="${H - 30}" y2="${H - 30}" stroke="${G_NEG}" stroke-width="3.4" stroke-dasharray="7 4"/>` + gText(54, H - 26, 'removed edge', {size: 12})
      + `<line x1="160" x2="188" y1="${H - 30}" y2="${H - 30}" stroke="${G_POS}" stroke-width="3.4"/>` + gText(194, H - 26, 'added edge', {size: 12})
      + `<circle cx="292" cy="${H - 30}" r="7" fill="${G_NEG}" opacity=".25"/>` + gText(304, H - 26, 'node touched by the change', {size: 12})
      + view.community_labels.slice(0, 4).map((label, i) => `<circle cx="${500 + i * 70}" cy="${H - 30}" r="4.5" fill="${palette[i]}"/>` + gText(508 + i * 70, H - 26, String(label).slice(0, 9), {size: 11})).join('');
    const maxChange = Math.max(1, ...per.map(p => p.added + p.removed));
    const strip = `<div class="g-strip" aria-label="Edges changed per snapshot">${per.map((p, i) => `<span title="${esc(p.label)}: +${p.added} / −${p.removed} edges" class="${i === index ? 'current' : ''}" style="height:${4 + 36 * (p.added + p.removed) / maxChange}px"></span>`).join('')}</div>`;
    return `<div class="g-row g-tight"><label for="g-snapshot">Snapshot</label><input type="range" id="g-snapshot" min="0" max="${n - 1}" value="${index}"><output>${index + 1}/${n} · ${esc(snap.label)} · <b style="color:${G_POS}">+${per[index].added}</b> / <b style="color:${G_NEG}">−${per[index].removed}</b> edges</output></div>${strip}<p class="field-help">Bar height = number of edges changed in that snapshot. Drag the slider or pick a tall bar to see bigger changes.</p>`
      + gFrame(`Snapshot ${index + 1} (${snap.label}): original versus transformed`, content, W, H);
  },
  bridge_matrix(chart) {
    const d = chart.data, labels = d.labels, k = labels.length, cell = Math.min(90, 300 / k), W = 780, H = 70 + k * cell;
    let s = '';
    Object.entries(d.directions).forEach(([dir, info], p) => {
      const x0 = 120 + p * (k * cell + 160);
      s += gText(x0, 14, dir === 'increase' ? 'Increase' : 'Decrease', {size: 13, fill: G_INK, weight: 'bold'});
      for (let i = 0; i < k; i++) {
        s += gText(x0 - 8, 50 + i * cell + cell / 2, String(labels[i]).slice(0, 12), {anchor: 'end', size: 11}) + gText(x0 + i * cell + cell / 2, 34, String(labels[i]).slice(0, 10), {anchor: 'middle', size: 11});
        for (let j = 0; j < k; j++) {
          let before, after;
          if (i === j) { before = info.internal_before[i]; after = info.internal_after[i]; }
          else { const m = info.bridge_matrix.find(b => (b.pair[0] === Math.min(i, j) && b.pair[1] === Math.max(i, j))); before = m?.before; after = m?.after; }
          const changed = before !== after, fill = !changed ? (i === j ? '#f3f6fa' : '#edf3fb') : after > before ? '#cfe0f1' : '#f6dccb';
          s += `<rect x="${x0 + j * cell}" y="${42 + i * cell}" width="${cell - 3}" height="${cell - 3}" rx="4" fill="${fill}"><title>${esc(labels[i])}–${esc(labels[j])}: ${before} → ${after}</title></rect>` + gText(x0 + j * cell + cell / 2 - 1, 42 + i * cell + cell / 2 + 4, `${before}→${after}`, {anchor: 'middle', size: cell < 50 ? 9 : 12, fill: G_INK});
        }
      }
    });
    s += gText(20, H - 6, 'Off-diagonal: edges between two communities · diagonal: internal edges · target snapshot', {size: 12});
    return gFrame('Community-pair edges in the target snapshot (original → transformed)', s, W, H);
  },
  leakage(chart) {
    const rows = chart.data.rows.filter(r => Math.abs(Math.abs(r.requested_delta) - chart.data.delta) < 1e-9);
    if (!rows.length) return '<p class="result-note">No leakage rows at the selected size.</p>';
    const metrics = Object.keys(rows[0].metrics), W = 780, H = 40 + metrics.length * 44, center = 510, half = 220;
    let s = gText(center - half / 2, 12, 'when you asked for LESS', {anchor: 'middle', size: 12, weight: 'bold'}) + gText(center + half / 2, 12, 'when you asked for MORE', {anchor: 'middle', size: 12, weight: 'bold'});
    metrics.forEach((m, j) => {
      const yy = 36 + j * 44, values = rows.map(r => r.metrics[m].change), max = Math.max(...values.map(v => Math.abs(v || 0)), 1e-12);
      s += gText(215, yy + 4, m, {anchor: 'end', size: 12, fill: G_INK}) + `<line x1="${center}" x2="${center}" y1="${yy - 14}" y2="${yy + 14}" stroke="#8a9db2"/>`;
      rows.forEach(r => {
        const v = r.metrics[m].change || 0, side = r.direction === 'increase' ? 1 : -1, len = Math.abs(v) / max * (half - 20);
        const x = side > 0 ? center : center - len;
        s += `<rect x="${x}" y="${yy - 9}" width="${Math.max(len, v ? 1.5 : 0)}" height="18" fill="${gColor(v)}" opacity="${r.valid_for_analysis ? 1 : .35}"><title>${r.direction}: ${m} change ${number(v, true)} (before ${number(r.metrics[m].before)}, after ${number(r.metrics[m].after)})${r.valid_for_analysis ? '' : ' — row excluded'}</title></rect>`
          + gText(side > 0 ? center + len + 6 : center - len - 6, yy + 4, number(v, true), {anchor: side > 0 ? 'start' : 'end', size: 11});
      });
    });
    s += gText(20, H - 6, 'Each row has its own scale (metrics have different units); faded bars belong to excluded rows', {size: 12});
    return gFrame('Change in each measured property (mean over snapshots)', s, W, H);
  },
  stability(chart) {
    const d = chart.data, W = 780, H = 260, valid = d.rows.filter(r => r.valid_for_analysis && r.impact !== null);
    if (!valid.length) return '<p class="result-note">No valid seed runs to plot.</p>';
    const [lo, hi] = gExtent(valid.map(r => r.impact)), x = gScale(lo, hi, 160, W - 40);
    let s = '';
    ['increase', 'decrease'].forEach((dir, j) => {
      const yy = 50 + j * 90, pts = valid.filter(r => r.direction === dir), sum = d.summary.find(z => z.direction === dir);
      s += gText(150, yy + 4, dir, {anchor: 'end', size: 13, fill: G_INK});
      if (sum?.n) s += `<line x1="${x(sum.min)}" x2="${x(sum.max)}" y1="${yy}" y2="${yy}" stroke="#9db6cf" stroke-width="6" stroke-linecap="round"/><line x1="${x(sum.mean)}" x2="${x(sum.mean)}" y1="${yy - 16}" y2="${yy + 16}" stroke="#18283e" stroke-width="2"><title>mean ${number(sum.mean, true)}</title></line>`;
      gPack(pts.map(r => r.impact), x, yy, 10, 2).forEach((pt, k) => { s += `<circle cx="${pt.x}" cy="${pt.y}" r="5" fill="${dir === 'increase' ? G_POS : G_NEG}"><title>seed ${pts[k].seed}: ${number(pts[k].impact, true)}</title></circle>`; });
      if (!pts.length) s += gText(x((lo + hi) / 2), yy + 4, 'no valid seeds', {anchor: 'middle'});
    });
    s += gAxisX(x, lo, hi, H - 50, `Normalized impact across ${d.seeds.length} ${d.variation} seeds (bar: range · line: mean)`);
    return gFrame('Seed-to-seed variation of the selected impact', s, W, H);
  },
  efficiency(chart) {
    const runs = chart.data.runs, W = 780, rh = 22, H = 40 + runs.length * rh, max = Math.max(...runs.map(r => Math.max(r.expected, r.measured)));
    const x = gScale(0, max, 260, W - 60);
    let s = gLegend([['#9db6cf', 'expected 1 + 2K'], [G_POS, 'measured']], 260, 8);
    runs.forEach((r, i) => {
      const yy = 30 + i * rh;
      s += gText(250, yy + 10, r.run.slice(0, 34), {anchor: 'end', size: 11, fill: G_INK})
        + `<rect x="260" y="${yy}" width="${x(r.expected) - 260}" height="8" fill="#9db6cf"/><rect x="260" y="${yy + 9}" width="${x(r.measured) - 260}" height="8" fill="${r.measured === r.expected ? G_POS : '#a25353'}"><title>${esc(r.run)}: measured ${r.measured}, expected ${r.expected}</title></rect>`
        + gText(x(Math.max(r.expected, r.measured)) + 6, yy + 14, `${r.measured}/${r.expected}`, {size: 10});
    });
    return gFrame('Model calls per explanation run', s, W, H);
  },
  sizes(chart) {
    const d = chart.data, W = 780, H = 280, valid = d.rows.filter(r => r.valid_for_analysis && !r.noop && r.impact !== null);
    const x = gScale(0, d.sizes.length - 1 || 1, 140, W - 60), [lo, hi] = gExtent(valid.map(r => r.impact)), y = gScale(lo, hi, H - 60, 15);
    let s = gAxisY(y, lo, hi, 110, W - 40, 'Normalized impact');
    d.sizes.forEach((size, i) => {
      s += gText(x(i), H - 42, `${size}/community`, {anchor: 'middle', size: 12});
      d.rows.filter(r => r.n_per_community === size).forEach(r => {
        const color = r.direction === 'increase' ? G_POS : G_NEG;
        if (r.valid_for_analysis && !r.noop) s += `<circle cx="${x(i) + (r.direction === 'increase' ? -6 : 6)}" cy="${y(r.impact)}" r="6" fill="${color}"><title>${size}/community ${r.direction}: ${number(r.impact, true)}; edge count ${r.edge_count_preserved ? 'preserved' : 'changed'}</title></circle>`;
        else s += gText(x(i) + (r.direction === 'increase' ? -6 : 6), y(0), '✕', {anchor: 'middle', fill: '#a25353'});
      });
    });
    s += gLegend([[G_POS, 'increase'], [G_NEG, 'decrease'], ['#a25353', '✕ no-op / excluded']], 120, H - 12);
    return gFrame('Selected impact across synthetic graph sizes', s, W, H);
  },
  reference() { return ''; },
};
