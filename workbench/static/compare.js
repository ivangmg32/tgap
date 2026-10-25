'use strict';
/* Phase 2 of the study: Compare Explainers — TGAP vs CoDy.
   One case, six stages: Introduction, The case, TGAP explains, CoDy explains
   (order counterbalanced), Side by side, Finish. After each explanation the
   participant gives four 0–7 agreement ratings; after the side-by-side view,
   two; the finish stage has one optional free-text field. The observed
   outcome is shown only after the feedback is saved. Every number and
   sentence comes from the server (sandbox/compare.py). */

const CX = {data: null, step: 0, error: '', entered: null, explore: false};

function resetCompare() { CX.data = null; CX.step = 0; CX.error = ''; CX.entered = null; CX.explore = false; }

function cxDate(unix) { return new Date(unix * 1000).toISOString().replace('T', ' ').slice(0, 16) + ' UTC'; }
function cxNum(v, d = 3) { return v === null || v === undefined || !isFinite(v) ? '—' : (v < 0 ? '−' : '') + Math.abs(v).toFixed(d); }
function cxRecording() { return !!CX.data?.session?.recording; }
function cxCase(id) { return CX.data.page.cases.find(c => c.case_id === id); }
function cxParas(list) { return (list || []).map(t => `<p>${esc(t)}</p>`).join(''); }
function cxDone(caseId, stage) { return CX.data.session.done.some(([id, st]) => id === caseId && st === stage); }

/* Six stages; the 'feedback' answer belongs to the Finish stage. */
function cxSteps() {
  const s = CX.data.session, order = s.order === 'tgap_first' ? ['review_tgap', 'review_cody'] : ['review_cody', 'review_tgap'];
  const id = s.cases[0];
  return [['intro', null], ['case', id], [order[0], id], [order[1], id], ['side', id], ['finish', id]];
}
function cxStepIndexOfNext() {
  const n = CX.data.session.next;
  if (!n) return cxSteps().length - 1;
  const stage = n[1] === 'feedback' ? 'finish' : n[1];
  return cxSteps().findIndex(([k]) => k === stage);
}

async function renderCompare() {
  const root = $('compare-content');
  if (!root) return;
  if (!CX.data) {
    root.innerHTML = '<div class="panel cx-pad"><span class="busy-spinner"></span> Loading the comparison…</div>';
    try { CX.data = await api('/compare/scenario'); }
    catch (e) { root.innerHTML = `<div class="panel cx-pad"><p class="error-text">${esc(e.message)}</p></div>`; return; }
    if (cxRecording()) CX.step = cxStepIndexOfNext();
  }
  if (!CX.data.available) {
    root.innerHTML = `<div class="panel cx-pad"><span class="eyebrow">NOT READY YET</span><h2>The comparison has not been computed.</h2><p>${esc(CX.data.reason)}</p></div>`;
    return;
  }
  if (!CX.explore && !(cxRecording() && CX.data.session.pre_done)) {
    // "Before We Begin": consent + pre-study questionnaire, before (and not counted in) the six stages.
    root.innerHTML = `<div class="cx-body">${cxPre()}</div><p class="error-text" role="alert">${esc(CX.error)}</p>`;
    return cxWirePre();
  }
  const steps = cxSteps(), [kind, caseId] = steps[CX.step];
  const reachable = i => !cxRecording() || CX.data.session.finished || i <= cxStepIndexOfNext();
  const label = {intro: 'Introduction', case: 'The case', review_tgap: 'TGAP explains', review_cody: 'CoDy explains', side: 'Side by side', finish: 'Finish'};
  const nav = `<nav class="cx-stepper" aria-label="Comparison steps">${steps.map(([k], i) => `<button class="cx-step ${i === CX.step ? 'active' : i < CX.step ? 'done' : ''}" data-cx-step="${i}" ${reachable(i) ? '' : 'disabled'} ${i === CX.step ? 'aria-current="step"' : ''}><span>${i + 1}</span>${esc(label[k])}</button>`).join('')}</nav>`;
  const c = caseId ? cxCase(caseId) : null;
  const body = kind === 'intro' ? cxIntro() : kind === 'finish' ? cxFinish(c) : kind === 'case' ? cxCaseStep(c)
    : kind === 'side' ? cxSide(c) : cxReview(c, kind.split('_')[1]);
  root.innerHTML = nav + `<div class="cx-body">${body}</div><p class="error-text" role="alert">${esc(CX.error)}</p>` +
    (cxRecording() ? '<div class="cx-withdraw"><button class="text-button" id="cx-withdraw">Withdraw from the comparison study and delete my records</button></div>' : '');
  cxWire();
  const key = `${kind}|${caseId}`;
  if (cxRecording() && caseId && CX.entered !== key && !CX.data.session.finished) {
    CX.entered = key;
    api('/compare/events', {method: 'POST', body: JSON.stringify({case_id: caseId, stage: kind === 'finish' ? 'feedback' : kind})}).catch(() => {});
  }
}

function cxGo(i) { CX.error = ''; CX.step = Math.max(0, Math.min(cxSteps().length - 1, i)); renderCompare(); window.scrollTo(0, 0); }
function cxNav(next, back = true) {
  return `<div class="cx-actions">${back ? '<button class="secondary" data-cx-prev>← Back</button>' : ''}${next ? `<button class="primary" data-cx-next>${esc(next)} →</button>` : ''}</div>`;
}

/* ---------- shared pieces ---------- */
function cxScoreChart(e) {
  // Same 0–100% scale and cutoff line for both methods.
  const pct = p => (100 * p).toFixed(2);
  const row = (label, p, text, cls) => p === null || p === undefined ? `<div class="cx-sc-row"><span>${esc(label)}</span><em class="cx-missing">no score</em></div>`
    : `<div class="cx-sc-row ${cls}"><span>${esc(label)}</span><div class="cx-sc-track"><i style="width:${pct(p)}%"></i><b class="cx-sc-thr" style="left:${pct(e.threshold)}%" title="decision cutoff"></b></div><strong>${esc(text)}</strong></div>`;
  return `<div class="cx-sc" role="img" aria-label="Model score before ${esc(e.original_score_text)} and after ${esc(e.resulting_score_text || 'none')}, cutoff ${Math.round(100 * e.threshold)}%">
    ${row('Before', e.original_score, e.original_score_text, 'orig')}${row('After', e.resulting_score, e.resulting_score_text, e.method)}
    <div class="cx-sc-axis"><span>0%</span><span style="left:${pct(e.threshold)}%">${Math.round(100 * e.threshold)}% cutoff</span><span>100%</span></div>
    <p class="cx-sc-note">Model score from 0% to 100%. Above the dark ${Math.round(100 * e.threshold)}% line the model answers “message”; below it, “no message”.</p></div>`;
}

function cxFacts(rows) { return `<dl class="cx-facts">${rows.map(([k, v]) => `<div><dt>${esc(k)}</dt><dd>${esc(v)}</dd></div>`).join('')}</dl>`; }

function cxTimeline(t) {
  if (!t || !t.swaps?.length) return '';
  const max = Math.max(1, ...t.swaps);
  return `<div class="cx-sub"><b>Connections changed in each earlier period</b>
    <div class="cx-strip">${t.swaps.map((n, i) => `<div title="period ${i + 1}: ${n} connections changed${t.limited.includes(i + 1) ? ' (fewer than requested were possible)' : ''}" class="${t.limited.includes(i + 1) ? 'limited' : ''}"><i style="height:${Math.max(4, Math.round(100 * n / max))}%"></i></div>`).join('')}<div class="lock" title="latest ${t.window_days} days: kept exactly"><span>🔒</span></div></div>
    <div class="cx-strip-axis"><span>oldest period</span><span>bar height: connections changed${t.limited.length ? ' · striped: fewer changes were possible than requested' : ''}</span><span>latest ${t.window_days} days · unchanged</span></div></div>`;
}

function cxChurnMaps() {
  const pts = [[20, 20], [70, 15], [95, 55], [55, 80], [15, 65]];
  const map = (edges, label) => `<figure class="cx-map"><svg viewBox="0 0 110 95" role="img" aria-label="${esc(label)}">${edges.map(([a, b]) => `<line x1="${pts[a][0]}" y1="${pts[a][1]}" x2="${pts[b][0]}" y2="${pts[b][1]}"/>`).join('')}${pts.map(([x, y]) => `<circle cx="${x}" cy="${y}" r="6"/>`).join('')}</svg><figcaption>${esc(label)}</figcaption></figure>`;
  const latest = [[0, 1], [1, 2], [2, 3], [3, 4]];
  return `<div class="cx-maps"><div><b>Low Churn: similar maps</b><div class="cx-map-pair">${map([[0, 1], [1, 2], [2, 3], [0, 4]], 'older period')}${map(latest, 'latest 10 days')}</div></div>
    <div><b>High Churn: different maps</b><div class="cx-map-pair">${map([[0, 2], [1, 3], [1, 4], [0, 3]], 'older period')}${map(latest, 'latest 10 days')}</div></div>
    <p class="cx-small">Illustration only — not data from this experiment. Dots are students; lines mean “exchanged messages in that period”.</p></div>`;
}

function cxTable(rows) { return `<table class="cx-table"><tbody>${rows.map(([k, v]) => `<tr><th>${esc(k)}</th><td>${esc(String(v ?? '—'))}</td></tr>`).join('')}</tbody></table>`; }

/* ---------- TGAP ---------- */
function cxTgapCards(pl) {
  return `<div class="cx-cards">${pl.cards.map((c, i) => `<article class="cx-card ${c.id}"><header><span class="cx-card-no">${i + 1}</span><h4>${esc(c.title)}</h4></header>
    <p>${esc(c.text)}</p>${(c.facts || []).length ? cxFacts(c.facts) : ''}</article>`).join('')}</div>`;
}

function cxTgapPage(e) {
  const pl = e.plain;
  if (!pl.changed) return `<h3 class="cx-h3">TGAP — The Result in Three Steps</h3>${cxTgapCards(pl)}`;
  const d = e.details;
  return `<h3 class="cx-h3">TGAP — The Result in Three Steps</h3>${cxTgapCards(pl)}
    <div class="cx-expl tgap">
      <section class="cx-sec"><h4>How Did TGAP Change the Network?</h4>${cxParas(pl.changed)}${cxTimeline(e.timeline)}</section>
      <section class="cx-sec"><h4>What Does Churn Mean?</h4>${cxParas(pl.churn_story)}${cxChurnMaps()}
        <details class="cx-details"><summary>How Churn is calculated</summary>${cxTable(pl.technical.slice(0, 6))}</details></section>
      <section class="cx-sec"><h4>How Did the Model Respond?</h4>${cxScoreChart(e)}<p>${esc(pl.response)}</p></section>
      <div class="cx-final"><p class="cx-final-main">${esc(pl.final)}</p><p>${esc(pl.limitation)}</p></div>
      <details class="cx-details"><summary>Explore Additional Experiments</summary>
        ${pl.reverse ? `<p>${esc(pl.reverse)}</p>` : ''}
        ${cxTable([...pl.technical.slice(6),
          ['Connections changed', d.edges_swapped], ['Past messages re-addressed', `${d.events_readdressed} of ${d.events_total} (${d.events_touching_target} involve the two students)`],
          ['Checks', `latest period unchanged: ${d.latest_preserved}; connection count kept: ${d.edge_count_preserved}; mapping to model input verified: ${d.mapping_verified}`],
          ['Side effects (mean change)', `density ${cxNum(d.density_change, 6)}, centralization ${cxNum(d.centralization_change, 6)}`]])}</details>
    </div>`;
}

/* ---------- CoDy ---------- */
function cxCodyPage(e) {
  const pl = e.plain, d = e.details;
  return `<h3 class="cx-h3">CoDy — The Result in Three Steps</h3>
    <div class="cx-cards cody">
      <article class="cx-card"><header><span class="cx-card-no">1</span><h4>What Did CoDy Investigate?</h4></header><p>${esc(pl.investigated)}</p></article>
      <article class="cx-card"><header><span class="cx-card-no">2</span><h4>What Happened to the Model?</h4></header><p class="cx-status ${pl.ok ? 'ok' : 'warn'}">${esc(pl.status)}</p>${cxFacts(pl.facts)}</article>
      <article class="cx-card takeaway"><header><span class="cx-card-no">3</span><h4>What Should I Take Away?</h4></header><p>${esc(pl.takeaway)}</p></article>
    </div>
    <div class="cx-expl cody">
      <section class="cx-sec"><h4>What Did CoDy Find?</h4><p>${esc(pl.found)}</p>${cxScoreChart(e)}</section>
      <div class="cx-final"><p>${esc(pl.limitation)}</p></div>
      <details class="cx-details"><summary>Technical details</summary>
        ${e.events.length ? `<table class="cx-table"><thead><tr><th>Event id</th><th>Message</th><th>Sent (UTC)</th><th>Before the prediction</th></tr></thead><tbody>${e.events.map(ev => `<tr><td>${ev.event_id}</td><td>student ${ev.source} → student ${ev.destination}</td><td>${cxDate(ev.time_utc_unix)}</td><td>${cxNum(ev.hours_before, 2)} hours</td></tr>`).join('')}</tbody></table>
          <p class="cx-small">${pl.ok ? 'Removing these messages changes the answer.' : 'This is CoDy’s best unsuccessful candidate, not a successful counterfactual.'}</p>` : ''}
        ${cxTable([['Search', `${d.selection_policy} policy, ${d.steps} of ${d.max_steps} steps, ${d.oracle_calls} model queries, ${cxNum(d.runtime_seconds, 1)} s`],
          ['Search ended', d.termination], ['Candidates', `${d.candidate_size} recent messages (sparsity ${cxNum(d.sparsity, 3)})`],
          ['Score reported by CoDy / exact re-check', `${cxNum(d.reported_score, 4)} / ${cxNum(d.exact_score, 4)}`],
          ['Implementation', `official CoDy, commit ${String(d.commit || '').slice(0, 10)}, unmodified; ${d.provenance}`]])}</details>
    </div>`;
}

/* ---------- ratings: one 0–7 component for every scale ---------- */
function cxScale(item, [lo, hi], checked) {
  return `<fieldset class="cx-scale"><legend>${esc(item.text)}</legend>
    <div class="cx-scale-row"><span class="cx-scale-end">0 = ${esc(lo)}</span>${Array.from({length: 8}, (_, i) => `<label><input type="radio" name="cx-r-${item.id}" value="${i}" ${i === 0 ? 'required' : ''} ${checked === i ? 'checked' : ''}><span>${i}</span></label>`).join('')}<span class="cx-scale-end">7 = ${esc(hi)}</span></div></fieldset>`;
}
function cxReadScale(form, items) {
  const out = {};
  items.forEach(r => { const v = form.querySelector(`[name="cx-r-${r.id}"]:checked`)?.value; out[r.id] = v === undefined ? null : Number(v); });
  return out;
}
function cxRatingForm(c, stage, items) {
  const labels = CX.data.page.scale_labels;
  return `<form class="cx-form" id="cx-form" data-case="${esc(c.case_id)}" data-stage="${esc(stage)}">
    <h3 class="cx-h3">Your ratings</h3><p class="cx-small">0 = ${esc(labels[0])}, 7 = ${esc(labels[1])}. Values in between mean increasing agreement.</p>
    ${items.map(r => cxScale(r, labels)).join('')}
    <div class="cx-actions"><button class="primary" type="submit">Save and continue →</button></div></form>`;
}

/* ---------- Before We Begin (pre-study questionnaire) ----------
   Shown once at the very start of the user study (phase 1 page), and on
   the comparison page if it was skipped. */
async function cxNeedsPre() {
  if (!CX.data) { try { CX.data = await api('/compare/scenario'); } catch (e) { return false; } }
  return !!CX.data.available && !CX.explore && !(cxRecording() && CX.data.session.pre_done);
}
function cxPre() {
  const q = CX.data.page.pre, joined = cxRecording();
  const opt = (list, id) => `<select id="${id}"><option value="">Choose (optional)</option>${list.map(o => `<option>${esc(o)}</option>`).join('')}</select>`;
  return `<section class="panel cx-pad"><span class="eyebrow">BEFORE THE STUDY</span><h2 class="cx-title">Before We Begin</h2>
    <p>Before starting the study, we would like to learn a little about your background and your previous familiarity with the topics covered in TGAP Lab. This helps us understand the experience of the participants. Please answer based on your own experience.</p>
    <form class="cx-form" id="cx-pre-form">
      <div class="cx-pre-grid"><label>Which age group do you belong to?${opt(q.age, 'cx-age')}</label>
        <label>What is the highest level of education you have completed?${opt(q.education, 'cx-edu')}</label></div>
      <h3 class="cx-h3">How familiar are you with each of the following topics before starting this study?</h3>
      <p class="cx-small">0 = ${esc(q.labels[0])}, 7 = ${esc(q.labels[1])}.</p>
      ${q.familiarity.map(r => cxScale(r, q.labels)).join('')}
      ${joined ? '' : `<div class="cx-join"><p>The study has two parts: first you run one TGAP experiment and explore its results; then you see TGAP and CoDy explain one prediction, rate each explanation, compare them side by side and, if you like, write some feedback. Your answers and time per step are stored under a random participant code, never with your name or e-mail. You can withdraw at any time.</p>
        <label class="cx-consent"><input type="checkbox" id="cx-consent"> I agree to these answers being recorded for research.</label></div>`}
      <div class="cx-actions"><button class="primary" type="submit">Continue to the Study →</button>${joined ? '' : '<button class="secondary" type="button" id="cx-explore">Explore without recording</button>'}</div>
    </form></section>`;
}
function cxWirePre(after = renderCompare) {
  const form = $('cx-pre-form'), ex = $('cx-explore');
  if (ex) ex.onclick = () => { CX.explore = true; CX.step = 0; after(); };
  form.onsubmit = async ev => {
    ev.preventDefault();
    const pre = {age: $('cx-age').value || null, education: $('cx-edu').value || null, familiarity: cxReadScale(form, CX.data.page.pre.familiarity)};
    const joined = cxRecording();
    if (!joined && !$('cx-consent').checked) { CX.error = 'Please tick the consent box to take part, or explore without recording.'; return renderCompare(); }
    try {
      CX.data = joined ? await api('/compare/pre', {method: 'POST', body: JSON.stringify({pre})})
        : await api('/compare/start', {method: 'POST', body: JSON.stringify({consent: true, pre})});
      if (cxRecording()) CX.step = cxStepIndexOfNext(); else CX.step = 0;
      CX.error = ''; after(); window.scrollTo(0, 0);
    } catch (e) { CX.error = e.message; after(); }
  };
}
function cxAfter(c, stage, items) {
  if (!cxRecording()) return `<p class="cx-small">Exploring: study participants rate this explanation here.</p>${cxNav('Continue')}`;
  return cxDone(c.case_id, stage) || CX.data.session.finished ? cxNav('Continue') : cxRatingForm(c, stage, items);
}

/* ---------- steps ---------- */
function cxIntro() {
  const p = CX.data.page, s = CX.data.session;
  const join = s.recording ? `<div class="cx-callout ok"><b>You are taking part as ${esc(s.participant)}</b>. Your ratings, feedback and time per step are recorded under this code.</div>`
    : `<div class="cx-callout warn">You are exploring without recording. <button class="text-button" id="cx-join">Take part in the study instead</button></div>`;
  return `<section class="panel cx-pad"><span class="eyebrow">PHASE 2 · TWO EXPLAINERS, ONE PREDICTION</span>
    <h2 class="cx-title">How do two explainers describe the same model prediction?</h2>
    <p class="cx-lead">A neural network reads past messages between students and gives a <b>model score</b> for whether one student will message another. Two methods explain that score:</p>
    <div class="cx-two"><div class="cx-method"><b>TGAP</b><p>${esc(p.descriptions.tgap)}</p></div><div class="cx-method"><b>CoDy</b><p>${esc(p.descriptions.cody)}</p></div></div>
    <p>Both look at the <b>same</b> prediction of the <b>same</b> model, but they ask different questions.</p>
    ${join}${cxNav('Start', false)}</section>`;
}

function cxEssentials(c) {
  return `<div class="cx-shared">
    <div><span>Prediction</span><b>Will student ${c.query.source} message student ${c.query.destination}?</b></div>
    <div><span>Prediction time</span><b>${esc(c.query.time_text)}</b></div>
    <div><span>Dataset</span><b>${esc(c.dataset.name)}</b></div><div><span>Model</span><b>${esc(c.model.name)}</b></div>
    <div><span>Original model score</span><b>${esc(c.original.score_text)}</b></div><div><span>Decision cutoff</span><b>${esc(c.original.threshold_text)}</b></div></div>`;
}
function cxRepro(c) {
  const v = c.verification;
  return `<details class="cx-details"><summary>Reproducibility Details</summary>${cxTable([
    ['Same model, history and starting score for both methods', v.verified ? `verified through ${v.paths.length} independent paths (largest difference ${cxNum(v.max_abs_difference, 1)})` : `not verified: ${v.reasons.join(' ')}`],
    ['Case id', c.case_id], ['History', `${c.query.history_events.toLocaleString('en')} messages before the prediction`], ['History fingerprint', c.query.history_fingerprint],
    ['Dataset fingerprint', c.dataset.stream_sha256], ['Model checkpoint', c.model.checkpoint_sha256], ['Model parameters', c.model.parameter_fingerprint],
    ['Provenance', v.provenance]])}</details>`;
}

function cxCaseStep(c) {
  return `<section class="panel cx-pad"><span class="eyebrow">THE CASE</span>
    <h2 class="cx-title">Will student <b>${c.query.source}</b> send a message to student <b>${c.query.destination}</b> on ${esc(c.query.time_text)}?</h2>
    <p>The model read the ${c.query.history_events.toLocaleString('en')} messages sent before that moment and gave this score:</p>
    <div class="cx-sc"><div class="cx-sc-row orig"><span>Model score</span><div class="cx-sc-track"><i style="width:${(100 * c.original.score).toFixed(2)}%"></i><b class="cx-sc-thr" style="left:${(100 * c.original.threshold).toFixed(2)}%"></b></div><strong>${esc(c.original.score_text)}</strong></div>
      <p class="cx-sc-note">The decision cutoff is ${esc(c.original.threshold_text)}, so the model answers <b>“${esc(c.original.predicted_class)}”</b>. The score is the model’s own output, not a guaranteed real-world probability.</p></div>
    <p>Next you will see how TGAP and CoDy explain this prediction, one at a time.</p>
    ${cxRepro(c)}${cxNav('Continue')}</section>`;
}

function cxReview(c, method) {
  const e = c[method];
  return `<section class="panel cx-pad cx-wide"><span class="eyebrow">${esc(e.title.toUpperCase())} EXPLAINS</span>
    <p class="cx-q">Student ${c.query.source} → student ${c.query.destination} · original model score <b>${esc(c.original.score_text)}</b> · cutoff ${esc(c.original.threshold_text)}</p>
    ${method === 'tgap' ? cxTgapPage(e) : cxCodyPage(e)}
    ${cxAfter(c, `review_${method}`, CX.data.page.ratings[method])}</section>`;
}

function cxPanel(e, title) {
  const k = e.plain.compact;
  const diff = e.resulting_score === null || e.resulting_score === undefined ? '—' : e.score_change_text.replace('points', 'percentage points');
  return `<article class="cx-col ${e.method}"><h3>${esc(title)}</h3>
    <h5>What it did</h5><p>${esc(k.did)}</p>
    <h5>${e.method === 'tgap' ? 'What was achieved' : 'What it found'}</h5>${cxFacts(k.rows)}
    <h5>How the model responded</h5>${cxScoreChart(e)}${cxFacts([['Score difference', diff], ['Answer changed?', e.class_changed === null ? '—' : e.class_changed ? 'Yes' : 'No']])}
    <h5>What the result means</h5><p class="cx-meaning">${esc(k.meaning)}</p></article>`;
}

function cxSide(c) {
  return `<section class="panel cx-pad cx-wide"><span class="eyebrow">SIDE BY SIDE</span>
    ${cxEssentials(c)}
    <div class="cx-columns">${cxPanel(c.tgap, 'TGAP — Change a Network Property')}${cxPanel(c.cody, 'CoDy — Search for Messages That Could Change the Answer')}</div>
    <p class="cx-callout warn">${esc(CX.data.page.side_note)}</p>${cxRepro(c)}
    ${cxAfter(c, 'side', CX.data.page.ratings.side)}</section>`;
}

function cxFinish(c) {
  const s = CX.data.session;
  if (cxRecording() && !s.finished) {
    if (s.next && s.next[1] !== 'feedback') return `<section class="panel cx-pad"><h2>Almost done</h2><p>Please complete the earlier steps first.</p></section>`;
    return `<section class="panel cx-pad"><span class="eyebrow">FINISH</span><h2 class="cx-title">Your Final Thoughts</h2>
      <p>We would love to hear your thoughts about the comparison. What was clear or confusing? What did you find useful? What would you improve?</p>
      <form class="cx-form" id="cx-form" data-case="${esc(c.case_id)}" data-stage="feedback">
        <label for="cx-feedback" class="cx-fb-label">Please share your thoughts in your own words.</label>
        <textarea id="cx-feedback" rows="8" maxlength="5000" spellcheck="true" autocomplete="off" placeholder="Optional. You can type, or use your device’s voice typing."></textarea>
        <div class="cx-actions"><button class="primary" type="submit">Submit and finish</button><button class="secondary" type="button" id="cx-skip">Finish without writing</button></div></form></section>`;
  }
  const outcome = c?.outcome ? `<h3 class="cx-h3">What really happened</h3><p>Student ${c.query.source} → ${c.query.destination}: <b>${esc(c.outcome.text)}</b> The model answered “${esc(c.original.predicted_class)}” (${esc(c.original.score_text)}), which was ${c.outcome.model_was_right ? 'right' : 'wrong'}.</p>` : '';
  return `<section class="panel cx-pad"><span class="eyebrow">FINISH</span><h2 class="cx-title">Thank you for taking part.</h2>
    ${s.recording ? outcome : '<p>Study participants see what really happened here, after their answers are saved.</p>'}
    <p class="cx-small">One case cannot show that either method is better in general.</p>
    <details class="cx-details"><summary>Reproducibility Details</summary><p>Case bank ${esc(CX.data.page.bank.batch_id || '')}: ${esc(CX.data.page.bank.rule)}. ${esc(CX.data.page.bank.warning)}</p>
      <div class="cx-actions"><a class="secondary cx-dl" href="/api/compare/download/json">Download JSON</a><a class="secondary cx-dl" href="/api/compare/download/csv">Download CSV</a></div></details></section>`;
}

function cxWire() {
  const root = $('compare-content');
  root.querySelectorAll('[data-cx-step]').forEach(b => b.onclick = () => cxGo(Number(b.dataset.cxStep)));
  root.querySelectorAll('[data-cx-next]').forEach(b => b.onclick = () => cxGo(CX.step + 1));
  root.querySelectorAll('[data-cx-prev]').forEach(b => b.onclick = () => cxGo(CX.step - 1));
  const join = $('cx-join');
  if (join) join.onclick = () => { CX.explore = false; CX.step = 0; renderCompare(); window.scrollTo(0, 0); };
  const form = $('cx-form');
  const send = async answers => {
    try { CX.data = await api('/compare/responses', {method: 'POST', body: JSON.stringify({case_id: form.dataset.case, stage: form.dataset.stage, answers})}); cxGo(cxStepIndexOfNext()); }
    catch (e) { CX.error = e.message; renderCompare(); }
  };
  if (form) form.onsubmit = ev => {
    ev.preventDefault();
    const stage = form.dataset.stage;
    if (stage === 'feedback') return send({text: $('cx-feedback').value});
    send({ratings: cxReadScale(form, CX.data.page.ratings[stage === 'side' ? 'side' : stage.split('_')[1]])});
  };
  const skip = $('cx-skip');
  if (skip) skip.onclick = () => send({text: ''});
  const w = $('cx-withdraw');
  if (w) w.onclick = async () => {
    if (!confirm('Delete all your comparison-study records? This cannot be undone.')) return;
    try { await api('/compare', {method: 'DELETE'}); resetCompare(); renderCompare(); } catch (e) { toast(e.message); }
  };
}
