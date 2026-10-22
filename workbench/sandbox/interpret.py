"""Deterministic, data-grounded explanations for guided-study charts.

Every sentence is generated from values already present in the chart payload
or the run context; nothing is sampled from a language model. Each chart gets
six parts answering: what is measured, under which conditions, the key
numbers, the visible pattern, what can be concluded, and what cannot.
Wording deliberately avoids causal claims, significance claims and
cross-concept rankings where units are incompatible.
"""
import math
import statistics

from sandbox.engine import MODELS

NOT_CAUSAL = 'This is the model\'s response to a controlled graph change, not evidence of a causal effect in the real network.'


def fmt(value, sign=False, digits=4):
    if value is None:
        return 'n/a'
    if isinstance(value, bool):
        return str(value)
    if value == 0:
        return '0'
    if not math.isfinite(value):
        return 'n/a'
    magnitude = abs(value)
    text = f'{magnitude:.{digits}g}' if 1e-4 <= magnitude < 1e6 else f'{magnitude:.3e}'
    if 'e' not in text and '.' in text:
        text = text.rstrip('0').rstrip('.')
    return ('-' if value < 0 else '+' if sign else '') + text


def pct(delta):
    return f'{abs(delta)*100:g}%'


def model_name(key):
    return MODELS.get(key, (key,))[0]


def achieved_text(value, mode):
    if value is None:
        return 'unmeasured'
    return f'{fmt(value*100, True)}% (relative)' if mode == 'relative' else f'{fmt(value, True)} (absolute units)'


def conditions(ctx, extra=''):
    spec = ctx.get('spec', {})
    if not spec:
        return extra
    labels = ctx.get('labels') or []
    target = f", predicting at {labels[-1]}" if labels else ''
    text = (f"Dataset {spec['dataset']}{target}; model {model_name(spec['model'])}; "
            f"{ctx.get('selected', spec.get('concept'))} {spec['direction']} of {pct(spec['delta'])}; seed {spec['seed']}.")
    return (text + ' ' + extra).strip()


def part(what, cond, observations, pattern, conclusion, caution):
    return dict(what=what, conditions=cond, observations=observations, pattern=pattern, conclusion=conclusion, caution=caution)


STATUS_TEXT = {
    'not_requested': 'This chart was not requested for this run.',
    'not_applicable': 'This chart does not apply to the selected dataset.',
    'blocked': 'This chart cannot be regenerated in the web workbench.',
    'unavailable': 'The computation needed for this chart did not produce usable data.',
}


def explain(chart_id, payload, ctx):
    status = payload['status']
    if status in STATUS_TEXT:
        reason = payload.get('blocked') or payload.get('scope') or ''
        return part(WHAT.get(chart_id, payload['title']), conditions(ctx), STATUS_TEXT[status] + (' ' + reason if reason else ''),
                    'No pattern is shown because no values were computed for this configuration.',
                    'Nothing can be concluded from this chart for this run.',
                    'An absent chart is not a zero result. No numbers were substituted.')
    try:
        return EXPLAINERS[chart_id](payload['data'], ctx, payload)
    except Exception as error:   # interpretation must never invent text around a failure
        return part(WHAT.get(chart_id, payload['title']), conditions(ctx),
                    f'The automatic interpretation could not be generated ({type(error).__name__}).',
                    'Read the chart values directly.', 'No automatic conclusion is offered.', NOT_CAUSAL)


WHAT = dict(
    workflow='The sequence of measurements that produced this explanation.',
    requested_vs_achieved='How far the concept actually moved compared with the requested change.',
    validity_map='Which concept/direction/request-size settings passed the validity gate and why the others were excluded.',
    delta_sensitivity='How the normalized impact of the selected concept changes with the requested size.',
    normalization='The impact computed with the achieved change (TGAP default) versus the requested change as denominator.',
    model_separated_impacts='Every valid normalized impact, separated by model and by perturbation semantics.',
    beeswarm='The distribution of every valid impact per concept, without averaging.',
    boxplot='The spread of valid impacts for the comparable (relative-delta) concepts within each model.',
    impact_distribution='An exploratory signed-log view of all valid impacts per concept.',
    matched_comparison='Which concept pairs can be compared, using achieved changes matched within 10%.',
    temporal_sensitivity='The response of each model to Bridge Trend, which edits history but keeps the latest snapshot fixed.',
    temporal_local='The prediction difference when the concept change is applied to one snapshot at a time.',
    trajectory='The concept measurements through time before and after the transformation.',
    edge_time='The prediction difference after removing one selected edge at one snapshot only.',
    local_graph='The concrete edges added and removed by the transformation.',
    bridge_matrix='Edges between and within communities in the target snapshot, before and after the transformation.',
    local_bar='The prediction difference after removing individual edges from every snapshot.',
    dependence='Whether structurally prominent nodes or edges have larger measured removal responses.',
    leakage='How non-target graph properties moved under the selected transformation.',
    seed_stability='How the selected impact varies when the run is repeated with different seeds.',
    efficiency='The number of model calls each explanation used compared with the expected 1 + 2K.',
    graph_size='Whether the selected response persists when the synthetic graph is regenerated at other sizes.',
    tgn_seed_stability='Held-out performance of a trained TGN across five seeds (published result).',
    faithfulness='Recovery of known analytical impacts by the synthetic known-truth models (published result).',
)


def _workflow(d, ctx, p):
    return part(WHAT['workflow'], conditions(ctx),
                f"The selected explanation used {d['core_calls']} prediction calls; element-level figures used {d['figure_calls']} bounded extra calls and the model x concept charts used {d['matrix_calls']}. {d['valid_rows']} of {d['total_rows']} direction results of the selected explanation are valid for analysis.",
                f"The graph has {d['nodes']} nodes over {d['snapshots']} snapshots; every counterfactual was scored by the same model as the original.",
                'The run followed the TGAP procedure: measure, transform, predict again, normalize by the achieved change, and record validity.',
                'The diagram describes the procedure; it is not itself a finding.')


def _req_ach(d, ctx, p):
    prim = d['primary']
    sel = d['selected']
    obs = f"Primary request: {prim['direction']} of {pct(prim['requested_delta'])}; "
    if prim['valid_for_analysis']:
        obs += f"achieved {achieved_text(prim['achieved_delta'], prim['delta_mode'])}."
    else:
        obs += f"excluded as {prim['status'].replace('_', ' ')}" + (f" ({prim['reason']})." if prim['reason'] else '.')
    measured = [r for r in sel if r['measured_achieved_delta'] is not None]
    relative = [r for r in measured if r['delta_mode'] == 'relative' and r['valid_for_analysis'] and not r['noop']]
    gaps = [abs(abs(r['measured_achieved_delta'])-abs(r['requested_delta']))/abs(r['requested_delta']) for r in relative]
    noops = sum(r['noop'] for r in sel)
    invalid = sum(not r['valid_for_analysis'] for r in sel)
    pattern = f"Across {len(sel)} tested settings of {ctx.get('selected')}: {invalid} excluded, {noops} no-op."
    if gaps:
        pattern += f" For valid relative-mode settings the achieved magnitude differs from the request by {fmt(min(gaps)*100)}% to {fmt(max(gaps)*100)}%, because graphs change in whole edges."
    elif sel and sel[0]['delta_mode'] == 'absolute':
        pattern += ' This concept measures achieved change in absolute units, so the request (a control setting) and the achieved value are not on the same scale.'
    if ctx.get('selected') == 'Centralization':
        pattern += ' Centralization\'s request is a rewiring fraction, not a target change of centralization.'
    if prim['valid_for_analysis'] and not prim['noop']:
        concl = 'The transformation moved the concept, so the impact is a valid finite-difference sensitivity normalized by the achieved change.'
    elif prim['noop']:
        concl = 'The primary request realized no concept change and no prediction change (a no-op); it yields no sensitivity information.'
    else:
        concl = 'The primary request is invalid for analysis, so its prediction change must not be interpreted as a concept sensitivity.'
    return part(WHAT['requested_vs_achieved'], conditions(ctx), obs, pattern, concl,
                'Requested values are inputs, achieved values are measurements; they should not be used interchangeably.')


def _validity(d, ctx, p):
    c = d['counts']
    share = c['valid']/c['total'] if c['total'] else 0
    failing = sorted({g['concept'] for g in d['grid'] if g['status'] != 'ok'})
    causes = ', '.join(f"{k.replace('_', ' ')} {c[k]}" for k in ('edge_count_infeasible', 'saturated', 'wrong_direction', 'no_property_change') if c[k])
    obs = f"{c['valid']} of {c['total']} model x concept x size x direction rows are valid ({fmt(share*100)}%); {c['invalid']} are excluded" + (f" ({causes})." if causes else '.')
    if c['noop_valid']:
        obs += f" {c['noop_valid']} valid rows are no-ops."
    pattern = (f"Exclusions concentrate on {', '.join(failing)}." if failing else 'Every tested concept passed the gate at every size and direction.')
    return part(WHAT['validity_map'], conditions(ctx, f"{d['models']} model(s), {len(d['concepts'])} concept(s), sizes {', '.join(f'{x:g}' for x in d['deltas'])}."),
                obs, pattern,
                f"Conclusions in the other charts rest only on the {c['valid']} valid rows." if c['valid'] else 'No valid rows exist, so no concept sensitivity can be reported for this configuration.',
                'Excluded rows are not zeros and are not repaired; a concept with only excluded rows has unknown sensitivity here.')


def _delta(d, ctx, p):
    rows = d['rows']
    obs, spreads = [], []
    for direction in ('increase', 'decrease'):
        sub = sorted([r for r in rows if r['direction'] == direction], key=lambda r: r['sweep_delta'])
        parts = []
        values = []
        for r in sub:
            if not r['valid_for_analysis']:
                parts.append(f"{pct(r['sweep_delta'])}: excluded ({r['status'].replace('_', ' ')})")
            elif r['noop']:
                parts.append(f"{pct(r['sweep_delta'])}: no-op")
            else:
                parts.append(f"{pct(r['sweep_delta'])}: {fmt(r['impact'], True)}")
                values.append(r['impact'])
        obs.append(f"{direction.title()} - " + '; '.join(parts) + '.')
        if len(values) > 1:
            spreads.append((direction, min(values), max(values)))
    if spreads:
        bits = []
        for direction, lo, hi in spreads:
            mean = (lo+hi)/2
            rel = (hi-lo)/abs(mean) if mean else None
            bits.append(f"{direction}: range {fmt(lo, True)} to {fmt(hi, True)}" + (f" ({fmt(rel*100)}% of the midpoint)" if rel is not None else ''))
        pattern = 'Across active request sizes the impact spans ' + '; '.join(bits) + '.'
        concl = ('The normalized response is essentially constant across sizes, consistent with a locally linear response.' if all(lo == hi for _, lo, hi in spreads)
                 else 'The normalized response changes with request size, so the sensitivity depends on how large a change is considered.')
    else:
        pattern = 'Fewer than two active request sizes per direction, so no size trend can be read.'
        concl = 'No conclusion about size dependence is possible from this run.'
    return part(WHAT['delta_sensitivity'], conditions(ctx), ' '.join(obs), pattern, concl,
                'Points are different requests on one graph, not independent repetitions; lines do not predict untested sizes. ' + NOT_CAUSAL)


def _normalization(d, ctx, p):
    rows = [r for r in d['rows'] if r['valid_for_analysis'] and not r['noop'] and r['impact'] is not None]
    if not rows:
        return part(WHAT['normalization'], conditions(ctx), 'No valid, active rows for the selected model and concept.',
                    'No comparison is possible.', 'Nothing can be concluded about normalization here.', 'Excluded rows are not zeros.')
    ratios = [(r, r['impact_requested_normalization']/r['impact']) for r in rows if r['impact']]
    obs = ' '.join(f"{r['direction']} {pct(r['sweep_delta'])}: achieved-normalized {fmt(r['impact'], True)}, requested-normalized {fmt(r['impact_requested_normalization'], True)}." for r in rows[:6])
    if ratios:
        lo, hi = min(x for _, x in ratios), max(x for _, x in ratios)
        pattern = f"Requested normalization rescales the impact by a factor between {fmt(lo)} and {fmt(hi)}, because the realized change differs from the request."
    else:
        pattern = 'The prediction did not move in the active rows, so both normalizations give zero.'
    mode = rows[0]['delta_mode']
    concl = ('When the two normalizations disagree, only the achieved version measures response per unit of actual concept change.' if mode == 'relative'
             else 'For this concept the request and the achieved change have different units, so requested normalization is not a meaningful sensitivity.')
    return part(WHAT['normalization'], conditions(ctx), obs, pattern, concl,
                'Without an analytical truth for this model and dataset, neither value can be scored for error here (the paper does that on synthetic data).')


def _strips(d, ctx, p):
    obs, zero_models = [], []
    for model in d['models']:
        cells = [x for x in d['panels'] if x['model'] == model]
        n = sum(x['n'] for x in cells)
        excluded = sum(x['excluded'] for x in cells)
        empty = [x['concept'] for x in cells if not x['n']]
        zeros = [x['concept'] for x in cells if x['n'] and all(pt['impact'] == 0 for pt in x['points'])]
        signs = []
        for x in cells:
            vals = [pt['impact'] for pt in x['points'] if pt['impact'] != 0]
            if vals and all(v > 0 for v in vals):
                signs.append(f"{x['concept']} positive")
            elif vals and all(v < 0 for v in vals):
                signs.append(f"{x['concept']} negative")
            elif vals:
                signs.append(f"{x['concept']} mixed sign")
        text = f"{model_name(model)}: {n} valid points, {excluded} excluded"
        if empty:
            text += f"; no valid observations for {', '.join(empty)}"
        if zeros:
            text += f"; exactly zero for {', '.join(zeros)}"
            zero_models.append(model)
        if signs:
            text += f"; {', '.join(signs)}"
        obs.append(text + '.')
    pattern = ('Some models are exactly blind to some concepts (all impacts zero), which is what their definitions predict when the concept does not touch what the model reads.'
               if zero_models else 'Every model responds to at least part of every concept it has valid observations for.')
    return part(WHAT['model_separated_impacts'], conditions(ctx, p.get('scope', '')), ' '.join(obs), pattern,
                'Read each panel on its own: the chart shows how each model responds to each concept on this dataset.',
                'Every model has its own output scale and concepts in different rows have different units, so no global or cross-model ranking follows. Empty cells are missing valid observations, not zeros.')


def _beeswarm(d, ctx, p):
    obs = []
    for g in d['groups']:
        for c in g['concepts']:
            vals = [pt['impact'] for pt in c['points']]
            if not vals:
                obs.append(f"{c['concept']}: no valid observations.")
                continue
            pos, neg, zero = sum(v > 0 for v in vals), sum(v < 0 for v in vals), sum(v == 0 for v in vals)
            obs.append(f"{c['concept']}: n={len(vals)}, from {fmt(min(vals), True)} to {fmt(max(vals), True)} ({pos} positive, {neg} negative, {zero} zero).")
    many_zero = [c['concept'] for g in d['groups'] for c in g['concepts'] if c['points'] and sum(pt['impact'] == 0 for pt in c['points']) > len(c['points'])/2]
    pattern = (f"Most valid responses are exactly zero for {', '.join(many_zero)}: several selected models do not read those concepts." if many_zero
               else 'The valid responses are spread on both sides of zero or concentrated on one side as listed.')
    return part(WHAT['beeswarm'], conditions(ctx, p.get('scope', '')), ' '.join(obs), pattern,
                'The chart shows the full spread of responses rather than a single average per concept.',
                'Points pool different models with different output scales; read spread and sign, not a ranking across rows.')


def _boxplot(d, ctx, p):
    obs = []
    for panel in d['panels']:
        parts = [f"{b['concept']} median {fmt(b['median'], True)} (IQR {fmt(b['q1'], True)} to {fmt(b['q3'], True)}, n={b['n']})" for b in panel['boxes'] if b['n']]
        obs.append(f"{model_name(panel['model'])}: " + ('; '.join(parts) if parts else 'no valid observations') + '.')
    small = max((b['n'] for panel in d['panels'] for b in panel['boxes']), default=0)
    return part(WHAT['boxplot'], conditions(ctx, f"Boxed concepts: {', '.join(d['concepts'])}; excluded by design: {', '.join(d['excluded']) or 'none'}."),
                ' '.join(obs), f"Each box summarizes at most {small} values (request sizes x directions), so boxes describe the tested settings rather than a population.",
                'Within one model panel the comparable concepts can be read side by side.',
                'Boxes are descriptive; they are not confidence intervals, and no box spans two models.')


def _signedlog(d, ctx, p):
    obs = []
    for c in d['concepts']:
        vals = [pt['impact'] for pt in c['points']]
        obs.append(f"{c['concept']}: n={len(vals)}, |impact| up to {fmt(max(abs(v) for v in vals))}.")
    return part(WHAT['impact_distribution'], conditions(ctx, p.get('scope', '')), ' '.join(obs),
                'The signed-log axis keeps very small and very large impacts readable on one axis.',
                'Use it to spot where responses cluster or are extreme.',
                'Model scales and concept units differ; this view must not be used for cross-model or cross-concept numerical ranking.')


def _matched(d, ctx, p):
    pairs = d['pairs']
    comparable = [x for x in pairs if x['comparable']]
    units = sum(1 for x in pairs if not x['comparable'] and x.get('gap') is None)
    tol = sum(1 for x in pairs if not x['comparable'] and x.get('gap') is not None)
    obs = f"{len(comparable)} of {len(pairs)} pair-directions are comparable; {units} fail on units or missing valid rows, {tol} on the {fmt(d['tolerance']*100)}% tolerance."
    detail = '; '.join(f"{x['direction']} {x['first']} vs {x['second']}: larger |impact| {x['larger']} ({fmt(x['first_impact'], True)} vs {fmt(x['second_impact'], True)}, gap {fmt(x['gap']*100)}%)" for x in comparable[:6])
    return part(WHAT['matched_comparison'], conditions(ctx, f"Model {model_name(d['model'])}; {len(d['deltas'])} request sizes per concept."), obs,
                detail + '.' if detail else 'No pair could be matched.',
                'Only matched pairs support a statement about which concept moved this model more at a similar actual change.',
                'Results hold for this model and dataset only; they are not a universal ordering of concepts.')


def _temporal_sensitivity(d, ctx, p):
    delta = d.get('shown_delta', ctx['spec']['delta'])
    obs, blind, responsive, unknown = [], [], [], []
    for model in d['models']:
        rows = [r for r in d['rows'] if r['model'] == model and abs(r['delta']-delta) < 1e-9]
        valid = [r for r in rows if r['valid_for_analysis']]
        if not valid:
            unknown.append(model_name(model))
            obs.append(f"{model_name(model)}: no valid Bridge Trend rows at {pct(delta)}.")
            continue
        obs.append(f"{model_name(model)}: " + ', '.join(f"{r['direction']} {fmt(r['impact'], True)}" for r in valid) + '.')
        (blind if all(r['impact'] == 0 for r in valid) else responsive).append(model_name(model))
    pattern = ''
    if blind:
        pattern += f"Unchanged by a history-only edit: {', '.join(blind)}. "
    if responsive:
        pattern += f"Responding to the history edit: {', '.join(responsive)}. "
    if unknown:
        pattern += f"Not assessable (Bridge Trend invalid): {', '.join(unknown)}."
    concl = ('The test separates models that read only the present from models that read the history, as in the paper\'s RQ2.' if blind and responsive
             else 'This run does not contain both kinds of behaviour, so it does not by itself separate present-only from history-reading models.')
    note = '' if abs(delta-ctx['spec']['delta']) < 1e-9 else f" Bridge Trend had no valid rows at your {pct(ctx['spec']['delta'])}, so the {pct(delta)} request is shown."
    return part(WHAT['temporal_sensitivity'], conditions(ctx, note.strip()), ' '.join(obs), pattern.strip() or 'No valid rows.', concl,
                'If Bridge Trend is invalid (saturated or wrong direction) on this dataset, no temporal claim can be made, as the paper notes for Decentraland.')


def _temporal_local(d, ctx, p):
    obs, last_only, earlier = [], [], []
    for panel in d['panels']:
        if not panel['valid_for_analysis']:
            obs.append(f"{model_name(panel['model'])}: not computed ({panel['status'].replace('_', ' ')}).")
            continue
        nonzero = [r for r in panel['rows'] if r['valid'] and r['impact']]
        if not nonzero:
            obs.append(f"{model_name(panel['model'])}: no single-snapshot edit changed the prediction.")
            continue
        top = max(nonzero, key=lambda r: abs(r['impact']))
        obs.append(f"{model_name(panel['model'])}: {len(nonzero)} snapshot(s) matter; largest {fmt(top['impact'], True)} at {top['label']}.")
        last = len(panel['rows'])-1
        (last_only if all(r['snapshot'] == last for r in nonzero) else earlier).append(model_name(panel['model']))
    pattern = ''
    if last_only:
        pattern += f"Only the target snapshot matters for {', '.join(last_only)} (a present-only signature). "
    if earlier:
        pattern += f"Earlier snapshots also matter for {', '.join(earlier)}."
    return part(WHAT['temporal_local'], conditions(ctx), ' '.join(obs), pattern.strip() or 'No snapshot-specific response was measured.',
                'The chart locates in time where this concept change can influence each model.',
                'Per-snapshot impacts are not additive and do not sum to the all-snapshot impact. ' + NOT_CAUSAL)


def _trajectory(d, ctx, p):
    direction = ctx['spec']['direction']
    changed = d['transformed'].get(direction)
    if not changed:
        return part(WHAT['trajectory'], conditions(ctx), 'No transformed trajectory is available.', 'n/a', 'Nothing can be concluded.', NOT_CAUSAL)
    obs = []
    for metric, name in (('bridge', 'Bridge Width'), ('density', 'Density'), ('centralization', 'Centralization')):
        diffs = [b[metric]-a[metric] for a, b in zip(d['original'], changed)]
        moved = [i for i, x in enumerate(diffs) if abs(x) > 1e-12]
        if moved:
            obs.append(f"{name} changed in {len(moved)} of {len(diffs)} snapshots (largest change {fmt(max(diffs, key=abs), True)}).")
        else:
            obs.append(f"{name} unchanged in every snapshot.")
    last_same = all(abs(changed[-1][m]-d['original'][-1][m]) < 1e-12 for m in ('bridge', 'density', 'centralization'))
    pattern = 'The target (last) snapshot is unchanged, so only history was edited.' if last_same else 'The target snapshot itself was changed.'
    return part(WHAT['trajectory'], conditions(ctx, f"Direction shown: {direction}; validity {d['status'].get(direction, 'n/a')}."), ' '.join(obs), pattern,
                'This shows where in time the counterfactual differs from the original.', 'Movement in non-target measures here is side effect, not intent (see the leakage chart).')


def _edge_time(d, ctx, p):
    cells = d['cells']
    measured = [c for c in cells if c['present']]
    nonzero = [c for c in measured if c['impact']]
    obs = f"{len(cells)} cells: {len(measured)} measured removals, {len(cells)-len(measured)} absent edges (no-ops)."
    if nonzero:
        top = max(nonzero, key=lambda c: abs(c['impact']))
        obs += f" {len(nonzero)} removals changed the prediction; largest {fmt(top['impact'], True)} for edge {top['u']}-{top['v']} at snapshot {top['snapshot']+1}."
        snaps = sorted({c['snapshot'] for c in nonzero})
        pattern = f"Responses occur at snapshot(s) {', '.join(str(s+1) for s in snaps)}."
    else:
        pattern = 'No single edge-time removal changed the prediction.'
    return part(WHAT['edge_time'], conditions(ctx, p.get('scope', '')), obs, pattern,
                'The heatmap shows which of the selected edges matter at which time for this model.',
                'It is an occlusion analysis, not TSHAP/TimeSHAP, and cells are not summed across time. Unmeasured cells are not zeros.')


def _local_graph(d, ctx, p):
    per = d['per_snapshot']
    added, removed = sum(s['added'] for s in per), sum(s['removed'] for s in per)
    touched = [s for s in per if s['added'] or s['removed']]
    kept = all(s['edges_before'] == s['edges_after'] for s in per)
    obs = f"The {ctx['spec']['direction']} transformation added {added} and removed {removed} edges in total, touching {len(touched)} of {len(per)} snapshots."
    pattern = ('Edge counts are preserved in every snapshot.' if kept else 'Edge counts change in at least one snapshot.') + (
        f" Changes are concentrated in {', '.join(s['label'] for s in touched[:5])}{'...' if len(touched) > 5 else ''}." if touched else ' No edge changed.')
    return part(WHAT['local_graph'], conditions(ctx), obs, pattern,
                'These are the exact edits behind the concept-level result.',
                'Edited edges are the realization of one counterfactual, not individual importance scores.')


def _bridge_matrix(d, ctx, p):
    labels = d['labels']
    obs = []
    for direction, info in d['directions'].items():
        moved = [f"{labels[x['pair'][0]]}-{labels[x['pair'][1]]} {x['before']}->{x['after']}" for x in info['bridge_matrix'] if x['before'] != x['after']]
        internal = [f"{labels[i]} {a}->{b}" for i, (a, b) in enumerate(zip(info['internal_before'], info['internal_after'])) if a != b]
        obs.append(f"{direction.title()}: bridges " + (', '.join(moved) if moved else 'unchanged') + '; internal ' + (', '.join(internal) if internal else 'unchanged') + '.')
    return part(WHAT['bridge_matrix'], conditions(ctx, f'{len(labels)} communities; target snapshot.'), ' '.join(obs),
                'The matrix shows which community pairs carry the change instead of a single cross-community total.',
                'Use it to check that the transformation acted on the intended community boundaries.',
                'Connection counts are structure, not model importance.')


def _local_bar(d, ctx, p):
    rows = d['rows']
    pos, neg, zero = sum(r['impact'] > 0 for r in rows), sum(r['impact'] < 0 for r in rows), sum(r['impact'] == 0 for r in rows)
    top = sorted(rows, key=lambda r: -abs(r['impact']))[:3]
    obs = f"{len(rows)} edges measured: {pos} raise, {neg} lower, {zero} leave the prediction unchanged when removed. Largest: " + ', '.join(f"{r['u']}-{r['v']} {fmt(r['impact'], True)}" for r in top) + '.'
    return part(WHAT['local_bar'], conditions(ctx, p.get('scope', '')), obs,
                'Signs show the direction in which each removal moved the prediction.',
                'The ordering identifies the most responsive edges among those measured, for this model only.',
                'An element-level occlusion is not a decomposition of the concept impact and is not exhaustive.')


def _rank_corr(xs, ys):
    if len(xs) < 5 or len(set(xs)) < 2 or len(set(ys)) < 2:
        return None

    def ranks(v):
        order = sorted(range(len(v)), key=lambda i: v[i])
        out = [0.0]*len(v)
        i = 0
        while i < len(v):
            j = i
            while j+1 < len(v) and v[order[j+1]] == v[order[i]]:
                j += 1
            for k in range(i, j+1):
                out[order[k]] = (i+j)/2
            i = j+1
        return out
    return statistics.correlation(ranks(xs), ranks(ys))


def _dependence(d, ctx, p):
    obs, pats = [], []
    if d.get('nodes'):
        rows = d['nodes']['rows']
        rho = _rank_corr([r['total_degree'] for r in rows], [abs(r['impact']) for r in rows])
        obs.append(f"{len(rows)} nodes measured" + (f"; rank correlation between total degree and |response| = {fmt(rho)}" if rho is not None else '') + '.')
        if rho is not None:
            pats.append('Higher-degree nodes tend to have larger responses.' if rho > .5 else 'Little monotone association between node degree and response.' if abs(rho) < .3 else 'A moderate association between node degree and response.')
    if d.get('edges'):
        rows = d['edges']['rows']
        rho = _rank_corr([r['snapshots_present'] for r in rows], [abs(r['impact']) for r in rows])
        obs.append(f"{len(rows)} edges measured" + (f"; rank correlation between snapshots present and |response| = {fmt(rho)}" if rho is not None else '') + '.')
    return part(WHAT['dependence'], conditions(ctx), ' '.join(obs), ' '.join(pats) or 'Too few distinct values for a rank correlation (needs at least 5).',
                'The plot describes how measured responses relate to simple structure for the measured subset.',
                'Descriptive association only (no significance test); it does not show that degree causes the response, and node and edge scores are different quantities.')


INTENDED = {'Bridge Width': 'Bridge Width', 'Density': 'Density', 'Centralization': 'Centralization', 'Bridge Trend': 'Bridge Width'}


def _leakage(d, ctx, p):
    rows = [r for r in d['rows'] if abs(abs(r['requested_delta'])-d['delta']) < 1e-9]
    intended = INTENDED.get(ctx['selected'])
    obs, ratios = [], []
    for r in rows:
        changes = {k: v['change'] for k, v in r['metrics'].items()}
        obs.append(f"{r['direction'].title()}: " + ', '.join(f"{k} {fmt(v, True)}" for k, v in changes.items()) + ('' if r['valid_for_analysis'] else ' (row excluded)') + '.')
        if intended and changes.get(intended):
            others = {k: v for k, v in changes.items() if k != intended and v is not None}
            if others:
                k, v = max(others.items(), key=lambda kv: abs(kv[1]))
                ratios.append((r['direction'], k, abs(v)/abs(changes[intended])))
    if ratios:
        pattern = ' '.join(f"{direction}: largest side effect {k} is {fmt(x)}x the size of the intended {intended} change (in each metric's own units)." for direction, k, x in ratios)
    else:
        pattern = 'Changes are listed in each metric\'s own units; no single intended metric exists for this concept.' if not intended else 'The intended metric did not move.'
    return part(WHAT['leakage'], conditions(ctx, 'Values are means over snapshots.'), ' '.join(obs), pattern,
                'Non-zero side effects mean the prediction change may partly reflect properties other than the selected concept.',
                'Metrics have different units, so the size comparison is indicative only; no transformation is assumed perfectly isolated.')


def _stability(d, ctx, p):
    obs = []
    for s in d['summary']:
        if s['n']:
            obs.append(f"{s['direction'].title()}: {s['n']}/{s['seeds']} valid, mean {fmt(s['mean'], True)}, SD {fmt(s['sd']) if s['sd'] is not None else 'n/a'}, range {fmt(s['min'], True)} to {fmt(s['max'], True)}.")
        else:
            obs.append(f"{s['direction'].title()}: no valid seeds.")
    pattern = ('Repeating the base seed gives exactly identical results (deterministic). ' if d['deterministic_repeat'] else 'Repeating the base seed did NOT reproduce the result exactly. ')
    sds = [s['sd'] for s in d['summary'] if s['sd'] is not None]
    pattern += ('Different seeds give identical impacts.' if sds and max(sds) == 0 else 'Different seeds give measurably different impacts.' if sds else '')
    return part(WHAT['seed_stability'], conditions(ctx, f"Varying the {d['variation']} seed over {len(d['seeds'])} seeds."), ' '.join(obs), pattern,
                'Determinism and seed-to-seed variation are separate properties; the SD shows how much the selected impact depends on random choices in the transformation or graph.',
                'Few seeds give a rough spread only, not a confidence interval.')


def _graph_size(d, ctx, p):
    obs = []
    for size in d['sizes']:
        rows = [r for r in d['rows'] if r['n_per_community'] == size]
        obs.append(f"{size}/community ({rows[0]['nodes'] if rows else '?'} nodes): " + ', '.join(
            f"{r['direction']} " + (fmt(r['impact'], True) if r['valid_for_analysis'] and not r['noop'] else 'no-op' if r['noop'] else 'excluded') for r in rows) + '.')
    kept = all(r['edge_count_preserved'] for r in d['rows'])
    return part(WHAT['graph_size'], conditions(ctx), ' '.join(obs),
                'Edge counts were preserved at every size.' if kept else 'Edge counts were not preserved at every size.',
                'The chart shows whether the selected response keeps its sign and scale as the synthetic graph grows.',
                'Each size is a different generated graph; differences mix size and structure.')


def _efficiency(d, ctx, p):
    mismatched = [r for r in d['runs'] if r['measured'] != r['expected']]
    obs = f"{len(d['runs'])} explanation runs; {len(d['runs'])-len(mismatched)} used exactly 1 + 2K calls."
    if mismatched:
        obs += ' Mismatches: ' + ', '.join(f"{r['run']} {r['measured']} vs {r['expected']}" for r in mismatched) + '.'
    return part(WHAT['efficiency'], conditions(ctx), obs + f" Element-level figures used {d['figure_calls']} extra calls.",
                'The call count grows linearly with the number of transformations.' if not mismatched else 'Some runs deviated from the expected budget.',
                'The explainer loop has the expected computational structure for these runs.' if not mismatched else 'Investigate the deviating runs before relying on the cost model.',
                'Call counts are not timings for learned models; these are cheap analytical models.')


def _blocked(chart_id):
    def explain_blocked(d, ctx, p):
        return part(WHAT[chart_id], conditions(ctx), p.get('blocked') or '', 'n/a', 'Nothing from this chart refers to your run.', 'The published reference values are not your results.')
    return explain_blocked


EXPLAINERS = dict(workflow=_workflow, requested_vs_achieved=_req_ach, validity_map=_validity, delta_sensitivity=_delta, normalization=_normalization,
                  model_separated_impacts=_strips, beeswarm=_beeswarm, boxplot=_boxplot, impact_distribution=_signedlog, matched_comparison=_matched,
                  temporal_sensitivity=_temporal_sensitivity, temporal_local=_temporal_local, trajectory=_trajectory, edge_time=_edge_time,
                  local_graph=_local_graph, bridge_matrix=_bridge_matrix, local_bar=_local_bar, dependence=_dependence, leakage=_leakage,
                  seed_stability=_stability, graph_size=_graph_size, efficiency=_efficiency,
                  tgn_seed_stability=_blocked('tgn_seed_stability'), faithfulness=_blocked('faithfulness'))


##  Experiment status and overall conclusion  ##


def experiment_status(ctx):
    prim = ctx['primary']
    rows = (ctx.get('matrix') or {}).get('rows') or []
    counts = dict(total=len(rows), valid=sum(r['valid_for_analysis'] for r in rows), noop=sum(r['noop'] for r in rows),
                  edge_count_infeasible=sum(r['status'] == 'edge_count_infeasible' for r in rows),
                  saturated=sum(r['status'] == 'saturated' for r in rows), wrong_direction=sum(r['status'] == 'wrong_direction' for r in rows),
                  no_property_change=sum(r['status'] == 'no_property_change' for r in rows))
    counts['invalid'] = counts['total']-counts['valid']
    if not prim['valid_for_analysis']:
        code, label = 'invalid', f"Requested transformation invalid ({prim['status'].replace('_', ' ')})"
    elif prim['noop']:
        code, label = 'no_op', 'No-op: the request did not change the concept'
    elif prim['prediction_change'] == 0:
        code, label = 'no_response', 'Transformation achieved; prediction unchanged'
    else:
        code, label = 'responded', 'Transformation achieved; prediction changed'
    tc = ctx.get('target_check') or {}
    if code in ('responded', 'no_response') and tc.get('against'):
        code, label = 'target_against', 'Prediction changed, but the target snapshot moved against the request' if code == 'responded' \
            else 'Target snapshot moved against the request; prediction unchanged'
    partial = bool(ctx.get('errors'))
    return dict(code=code, label=label, partial=partial, failed_stages=[e['stage'] for e in ctx.get('errors', [])], matrix_counts=counts)


def overall_conclusion(ctx):
    spec, prim, main = ctx['spec'], ctx['primary'], ctx['main']
    status = ctx['status']
    labels = ctx.get('labels') or []
    concept = ctx['selected']
    s = [f"On {spec['dataset']} ({main['summary']['nodes']} nodes, {main['summary']['snapshots']} snapshots, predicting at {labels[-1] if labels else 'the last snapshot'}), "
         f"the {model_name(spec['model'])} model originally output {fmt(prim['baseline'])}. "
         f"You requested a {pct(spec['delta'])} {spec['direction']} of {concept}."]
    if status['code'] == 'invalid':
        s.append(f" That request was excluded as {prim['status'].replace('_', ' ')}" + (f" ({prim['reason']})" if prim['reason'] else '') +
                 ', so the experiment provides no valid sensitivity for it and its prediction change is not reported.')
    elif status['code'] == 'no_op':
        s.append(' The transformation realized no change in the concept and none in the prediction (a no-op); this is not evidence that the concept is irrelevant, only that the request was too small or not realizable on this graph.')
    else:
        s.append(f" The transformation achieved {achieved_text(prim['achieved_delta'], prim['delta_mode'])} and the prediction moved to {fmt(prim['prediction'])} "
                 f"(change {fmt(prim['prediction_change'], True)}), a normalized impact of {fmt(prim['impact'], True)}.")
        tc = ctx.get('target_check') or {}
        if status['code'] == 'target_against':
            s.append(f" Caution: averaged over all snapshots {concept} moved as requested, but in the target snapshot {tc['label']} it went from "
                     f"{fmt(tc['before'])} to {fmt(tc['after'])}, against the request"
                     + (" (the Bridge Width transformation keeps at least one bridge in every snapshot, so an empty boundary is raised to one even under a decrease)" if concept.startswith('Bridge Width') else '')
                     + ". A model that reads the target snapshot responds to that opposite change, so the sign and size of this impact do not describe the requested direction.")
        if status['code'] == 'no_response':
            s.append(' The concept moved but the prediction did not, so within this test the model is insensitive to this change.')
    other = next((r for r in main['rows'] if r['concept'] == concept and r['direction'] != spec['direction']), None)
    if other:
        s.append(f" The opposite direction was {'valid with impact ' + fmt(other['impact'], True) if other['valid_for_analysis'] else 'excluded (' + other['status'].replace('_', ' ') + ')'}.")
    charts = {c['id']: c for c in ctx.get('charts', [])}
    evidence = []

    def sentence(text):
        text = text.strip().rstrip('.').replace('. ', '; ')
        return text[:1].lower() + text[1:]
    delta = charts.get('delta_sensitivity')
    if delta and delta['status'] == 'ok' and delta['explanation']['conclusion'].startswith('The normalized response'):
        evidence.append(sentence(delta['explanation']['conclusion']))
    tl = charts.get('temporal_local')
    if tl and tl['status'] == 'ok' and tl['explanation']['pattern'] and 'matter' in tl['explanation']['pattern']:
        evidence.append(sentence(tl['explanation']['pattern']))
    st = charts.get('seed_stability')
    if st and st['status'] == 'ok':
        mine = next((x for x in st['data']['summary'] if x['direction'] == spec['direction']), None)
        if mine and mine['n']:
            evidence.append(f"across {mine['seeds']} seeds the {spec['direction']} impact ranged from {fmt(mine['min'], True)} to {fmt(mine['max'], True)}")
    lk = charts.get('leakage')
    if lk and lk['status'] == 'ok' and 'largest side effect' in lk['explanation']['pattern']:
        evidence.append('the transformation also moved non-target properties (see the leakage chart)')
    if evidence:
        s.append(' Supporting evidence: ' + '; '.join(evidence) + '.')
    c = status['matrix_counts']
    if c['total']:
        s.append(f" Across the {c['total']} model x concept x size x direction rows, {c['valid']} were valid and {c['invalid']} excluded"
                 + (f" ({c['edge_count_infeasible']} edge-count infeasible, {c['saturated']} saturated, {c['wrong_direction']} wrong direction)" if c['invalid'] else '') + '.')
    if status['partial']:
        s.append(f" Some computations failed ({', '.join(status['failed_stages'])}); the affected charts are marked unavailable and are not part of this conclusion.")
    unavailable = [c['title'] for c in ctx.get('charts', []) if c['status'] in ('unavailable',)]
    if unavailable:
        s.append(f" {len(unavailable)} chart(s) could not be produced for this configuration.")
    if status['code'] == 'responded':
        s.append(f" Overall, the experiment supports the statement that this model's output is sensitive to {concept} on this dataset under the tested controlled transformation; it does not show that {concept} causes any real-world outcome.")
    elif status['code'] == 'target_against':
        s.append(f" Overall, this run cannot show how the model responds to a {spec['direction']} of {concept}: the snapshot the prediction depends on was changed the other way. Try a later target snapshot with more activity, the opposite direction, or a model that reads the whole history.")
    elif status['code'] == 'no_response':
        s.append(f" Overall, the experiment indicates that this model's output did not respond to a realized change in {concept} on this dataset; this is a statement about the model, not the network.")
    else:
        s.append(' Overall, the main request cannot support a conclusion about this concept; consider a different request size or direction, or read the valid rows in the charts above.')
    return ''.join(s)
