"""Traceable mapping: paper chart -> computation -> data -> results-page component.

INVENTORY is the single source for the chart inventory. Every figure of the
paper (Temporal_GNN_Explainer, Figs 1-12, files in workbench/publication) and
every chart produced by the paper's experiment pipelines (output/synthetic,
output/real_data/*/figures, referenced by RQ1-RQ8 and Tables 5-7) has exactly
one entry. Each entry is either regenerated from the user's run (`dynamic`),
shown as a labelled reference (`static`), or `blocked` with the precise
missing dependency. build_charts() turns one guided run into chart payloads;
every payload carries an explanation produced by sandbox.interpret.
"""
import math
import statistics

from sandbox.interpret import explain

GROUPS = [
    ('intervention', 'Intervention behaviour', 'What was requested, what was achieved, and how the prediction moved.'),
    ('global', 'Concept impacts across models', 'The paper\'s global views (Figs 2, 3, 4, 11), regenerated for your dataset.'),
    ('temporal', 'Temporal sensitivity', 'Whether and when history matters to the model.'),
    ('local', 'Local structure and elements', 'The concrete graph change and element-level measurements.'),
    ('side_effects', 'Unintended effects', 'How non-target properties moved.'),
    ('robustness', 'Stability, size and computational cost', 'Repeatability, graph-size behaviour and model-call budget.'),
    ('reference', 'Static figures and published references', 'Conceptual illustrations and results that cannot be recomputed here.'),
]

# kind: dynamic | conditional (needs an opt-in or dataset type) | static | blocked
INVENTORY = [
    dict(id='workflow', paper='Fig. 1', paper_figure='fig0_tgap_architecture', group='reference', renderer='workflow', kind='static',
         caption='TGAP architecture. A temporal graph is measured using a human-defined concept, transformed into a controlled counterfactual, evaluated with the same model, and converted into a directional sensitivity measure.',
         source='Paper §4.4; workbench/publication/fig0_tgap_architecture.png', question='Method overview (no research question).',
         axes='Diagram; no axes.', requires='Nothing; the live diagram fills in this run\'s dataset, model, concept and call counts.',
         multi_run='No.', display='Original diagram in the reference area plus a live workflow diagram with this run\'s values.',
         implementation='chart_registry._workflow'),
    dict(id='model_separated_impacts', paper='Fig. 2', paper_figure='fig1_final_model_separated_impacts', group='global', renderer='strips', kind='dynamic',
         caption='Global TGAP impacts, separated by model; comparisons only within compatible perturbation semantics; empty cells are missing valid observations, not zeros.',
         source='Paper §7.6; realdata.make_publication.figure1FinalModelSeparated; output/real_data/temporal_evaluation/*/tgap_results.csv',
         question='How does each model respond to each transformation on a dataset?',
         axes='x: normalized impact (own axis per model panel); rows: semantic groups (relative-delta concepts share a row; Centralization and Bridge Trend own rows); columns: models; points: one valid (delta, direction) row; colour: sign.',
         requires='All selected models x selected concepts x request sizes x both directions on the selected dataset, with validity gating.',
         multi_run='Yes: models x concepts x deltas x 2 (paper: 6 x 5 x 3 x 2 = 180 per dataset).', display='Strip-plot small multiples, one panel per model and semantic row.',
         implementation='guided.execute_guided.run_matrix + chart_registry._strips'),
    dict(id='beeswarm', paper='Fig. 3', paper_figure='fig9_true_beeswarm', group='global', renderer='beeswarm', kind='dynamic',
         caption='Deterministic beeswarm of valid real-data TGAP impacts; each point is a valid observed result.',
         source='Paper §7.7; realdata.make_publication.figure9TrueBeeswarm', question='How are valid impacts distributed for each concept?',
         axes='x: impact; rows: concepts inside semantic-group panels; colour: sign; deterministic packing, no jitter.',
         requires='The model x concept x delta matrix (valid rows only).', multi_run='Yes (same matrix as Fig. 2).',
         display='Packed dot plot per semantic group.', implementation='chart_registry._beeswarm'),
    dict(id='boxplot', paper='Fig. 4', paper_figure='fig10_publication_boxplot', group='global', renderer='boxplot', kind='dynamic',
         caption='Distributional boxplots of valid real-data impacts, with model identity preserved; descriptive, no cross-model ranking.',
         source='Paper §7.7; realdata.make_publication.figure10PublicationBoxplot', question='What is the spread of comparable concept responses within each model?',
         axes='x: impact; one panel per model; boxes: relative-delta concepts only (Centralization and Bridge Trend excluded); n printed; points overlaid.',
         requires='The model x concept x delta matrix (valid rows only).', multi_run='Yes (same matrix as Fig. 2).',
         display='One box panel per model.', implementation='chart_registry._boxplot'),
    dict(id='tgn_seed_stability', paper='Fig. 5 (and Tables 6-7)', paper_figure='fig7_tgn_seed_stability', group='reference', renderer='reference', kind='blocked',
         caption='Held-out performance across five TGN training seeds; a seed-stability summary rather than a benchmark ranking.',
         source='Paper §8; realdata.run_tgn_stability; output/tgn_stability/email_eu_core', question='Learned-model applicability and seed stability.',
         axes='x: metric (AUC, AP, accuracy, baseline score); y: value across 5 training seeds.',
         requires='Training a Temporal Graph Network (PyTorch, torch_geometric) five times on Email-Eu-core with held-out evaluation.',
         multi_run='Yes: 5 training seeds.', display='Published reference image, clearly labelled; the RQ3 seed-stability chart below measures a different quantity on your model.',
         implementation='none (blocked)',
         blocked='The web workbench runs only the six transparent analytical models in a bounded worker (one process, minutes at most). Training and replaying a TGN for five seeds needs PyTorch/torch_geometric and far more time than the worker budget, so this chart is not regenerated. Run `tgap run tgn` locally to reproduce it.'),
    dict(id='local_graph', paper='Fig. 6', paper_figure='fig4_local_graph', group='local', renderer='network', kind='dynamic',
         caption='Controlled local graph demonstration: the highlighted elements are those involved in the concrete graph change used to instantiate a concept-level counterfactual.',
         source='Paper §9.1; realdata.make_publication.figure4LocalGraph', question='Which concrete edges realize the concept change?',
         axes='Node-link diagram with fixed positions; added edges and removed edges highlighted; snapshot selectable.',
         requires='The original and transformed snapshots for the selected concept and direction.', multi_run='No.',
         display='Original vs transformed network, side by side, with a snapshot selector.', implementation='guided.run_structure (view)'),
    dict(id='local_bar', paper='Fig. 7', paper_figure='fig11_local_bar', group='local', renderer='bars', kind='dynamic',
         caption='Element-level attribution: positive and negative effects around zero; ordering is local to one explanation, not a concept ranking.',
         source='Paper §9.2; core.edgeAttribution via sandbox.analyses', question='Which individual edges move this prediction when removed?',
         axes='y: edge; x: prediction difference after removing the edge from every snapshot (model output units).',
         requires='Edge occlusion on the user\'s graph and model (bounded subset).', multi_run='No (bounded extra calls).',
         display='Diverging bar chart.', implementation='sandbox.analyses.detailed_analyses (edges)'),
    dict(id='temporal_local', paper='Fig. 8', paper_figure='fig5_temporal_local', group='temporal', renderer='temporal', kind='dynamic',
         caption='Controlled temporal local demonstration: snapshot-level perturbations show when a temporal counterfactual changes the model response.',
         source='Paper §9.3; core.temporalAttribution', question='When does the concept matter to each model?',
         axes='x: snapshot; y: prediction difference when only that snapshot is transformed; one panel per model.',
         requires='The selected concept/direction applied to one snapshot at a time, scored by each selected model.',
         multi_run='Yes: models x snapshots predictions (transformation computed once).', display='Bar panels per model.',
         implementation='guided.run_temporal (core.temporalAttribution)'),
    dict(id='edge_time', paper='Fig. 9', paper_figure='fig12_temporal_edge_time', group='temporal', renderer='edge_time', kind='dynamic',
         caption='Edge-time attribution: each cell corresponds to one edge at one snapshot; not a TSHAP/TimeSHAP implementation.',
         source='Paper §9.4; sandbox.analyses (edge-time occlusion)', question='Which edges matter at which time?',
         axes='rows: selected edges; columns: snapshots; colour: prediction difference after removing that edge at that time only.',
         requires='Edge occlusion per snapshot for the most responsive measured edges.', multi_run='No (bounded extra calls).',
         display='Heatmap.', implementation='sandbox.analyses.detailed_analyses (edge_time)'),
    dict(id='dependence', paper='Fig. 10', paper_figure='fig8_dependence', group='local', renderer='dependence', kind='dynamic',
         caption='Dependence-style visualization: a structural element property against its observed attribution; the structural variable is discrete.',
         source='Paper §10.1; realdata.make_publication.figure8Dependence', question='Do structurally prominent elements have larger measured responses?',
         axes='x: node total degree / edge snapshots present; y: prediction difference after removal.',
         requires='Node and edge occlusion measurements.', multi_run='No.', display='Two scatter plots.',
         implementation='sandbox.analyses.detailed_analyses (nodes, edges)'),
    dict(id='impact_distribution', paper='Fig. 11', paper_figure='fig6_impact_distribution', group='global', renderer='signedlog', kind='dynamic',
         caption='Distributional summary of valid TGAP impacts; descriptive; exploratory mixed-model view on a signed-log axis.',
         source='Paper §10.2; realdata.make_publication.figure6ImpactDistribution', question='Exploratory spread of all valid impacts per concept.',
         axes='x: sign(impact) * log10(1+|impact|); rows: concepts; colour: sign.',
         requires='The model x concept x delta matrix (valid rows).', multi_run='Yes (same matrix as Fig. 2).',
         display='Packed dot plot on a signed-log axis.', implementation='chart_registry._signedlog'),
    dict(id='bridge_matrix', paper='Fig. 12', paper_figure='fig3_bridge_matrix', group='local', renderer='bridge_matrix', kind='dynamic',
         caption='Multi-community Bridge Width matrix: community-pair structure instead of a single cross-community count.',
         source='Paper §10.3; core.bridgeMatrix', question='How do ties between each pair of communities change?',
         axes='Community x community matrix; cells: edges in the target snapshot, original -> transformed; diagonal: internal edges.',
         requires='Original and transformed target snapshot.', multi_run='No.', display='Two matrices (increase, decrease).',
         implementation='guided.run_structure (core.bridgeMatrix)'),
    dict(id='requested_vs_achieved', paper='§4.6 (Eqs. 8-10)', paper_figure=None, group='intervention', renderer='req_ach', kind='dynamic',
         caption='Requested versus achieved concept change; impacts are normalized by the achieved change.',
         source='Paper §4.6-4.7; core.GraphExplainer.explainDetailed', question='Did the transformation achieve what was requested?',
         axes='x: requested change (signed); y: achieved change in the concept\'s own units; status per point.',
         requires='Requested/achieved deltas for the selected concept at every request size, and for all concepts at the selected size.',
         multi_run='Uses the matrix runs.', display='Paired comparison chart and table.', implementation='chart_registry._req_ach'),
    dict(id='validity_map', paper='Table 5; real-data validity_map.png', paper_figure=None, group='intervention', renderer='validity', kind='dynamic',
         caption='Validity of each concept/direction/request size; invalid settings are excluded, not repaired.',
         source='Paper §7.5; realdata pipeline validity_map.png; sandbox.engine.validity_gate', question='Which settings are valid for analysis, and why are others excluded?',
         axes='rows: concepts; columns: request size x direction; colour: status. Counts by cause as in Table 5.',
         requires='Validity gate for every concept x delta x direction (model-independent).', multi_run='Uses the matrix runs.',
         display='Status grid and Table-5-style counts.', implementation='chart_registry._validity'),
    dict(id='delta_sensitivity', paper='RQ5 (§6.7); output/synthetic/delta_sensitivity.png', paper_figure=None, group='intervention', renderer='delta', kind='dynamic',
         caption='Perturbation size: active requests recover a stable sensitivity after achieved normalization; small requests can be no-ops.',
         source='experiments.synthetic_evaluation.rq5DeltaSensitivity', question='What happens as the requested perturbation size changes?',
         axes='x: requested change; y: normalized impact; markers: no-op / invalid.', requires='The selected model and concept at each requested size.',
         multi_run='Yes: one explanation per request size.', display='Line-and-point chart per direction.', implementation='chart_registry._delta'),
    dict(id='normalization', paper='RQ8 (§6.10); output/synthetic/normalization_ablation.png', paper_figure=None, group='intervention', renderer='normalization', kind='dynamic',
         caption='Achieved- versus requested-delta normalization.',
         source='experiments.synthetic_evaluation.rq8NormalizationAblation', question='What is the effect of normalizing by achieved rather than requested change?',
         axes='x: requested change; y: impact under each normalization.', requires='Prediction change, requested and achieved deltas from the same runs.',
         multi_run='Uses the matrix runs.', display='Grouped bars per request size.', implementation='chart_registry._normalization'),
    dict(id='temporal_sensitivity', paper='RQ2 (§6.4); output/synthetic/temporal_sensitivity.png', paper_figure=None, group='temporal', renderer='model_bars', kind='conditional',
         caption='Bridge Trend changes history while keeping the latest snapshot fixed: present-only models stay at zero, trajectory models respond.',
         source='experiments.synthetic_evaluation.rq2TemporalSensitivity', question='Can TGAP distinguish a present-only model from a history-dependent model?',
         axes='x: model; y: Bridge Trend impact for increase and decrease.', requires='Bridge Trend in the concept set and at least one model.',
         multi_run='Uses the matrix runs.', display='Grouped bars per model.', implementation='chart_registry._temporal_sensitivity'),
    dict(id='trajectory', paper='Real-data metric_trajectories.png', paper_figure=None, group='temporal', renderer='trajectory', kind='dynamic',
         caption='Original and transformed concept trajectories through time.',
         source='realdata pipeline metric_trajectories.png; sandbox.engine.execute (comparisons)', question='How did the transformation reshape the history?',
         axes='x: snapshot; y: Bridge Width, Density, Centralization; original vs transformed.', requires='Original and transformed snapshots.',
         multi_run='No.', display='Line chart with metric selector.', implementation='sandbox.engine.execute (comparisons.trajectory)'),
    dict(id='leakage', paper='RQ6 (§6.8); output/synthetic/leakage.png', paper_figure=None, group='side_effects', renderer='leakage', kind='dynamic',
         caption='Non-target graph properties can change when one concept is transformed.',
         source='experiments.synthetic_evaluation.rq6Leakage; core.GraphExplainer.explainDetailed(leakageMetrics)', question='How much do non-target properties change?',
         axes='rows: measured property; x: change (mean over snapshots), increase and decrease.', requires='Leakage panel measured on the same counterfactual.',
         multi_run='Uses the matrix runs.', display='Diverging bars per property.', implementation='guided.run_matrix (leakage)'),
    dict(id='seed_stability', paper='RQ3 (§6.5); output/synthetic/stability.png', paper_figure=None, group='robustness', renderer='stability', kind='conditional',
         caption='Same-seed runs are exactly reproducible; different graph or transformation seeds produce measurable variation.',
         source='experiments.synthetic_evaluation.rq3Stability', question='Are repeated explanations reproducible, and how much do they vary across seeds?',
         axes='x: direction; y: impact per seed; mean, SD and range.', requires='Repeated runs with different transformation (or, for synthetic data, graph) seeds.',
         multi_run='Yes: one explanation per seed (user-chosen count).', display='Dot plot with mean and range.', implementation='guided.run_stability'),
    dict(id='efficiency', paper='RQ4 (§6.6, Eq. 6); output/synthetic/efficiency.csv', paper_figure=None, group='robustness', renderer='efficiency', kind='dynamic',
         caption='Model calls follow 1 + 2K for K transformations.',
         source='experiments.synthetic_evaluation.rq4Efficiency; core.CallCountingModel', question='Does the implementation use the expected model-call budget?',
         axes='x: run; y: model calls, measured vs expected 1 + 2K; stage durations.', requires='Call counters on every explanation run.',
         multi_run='Uses all runs.', display='Paired bars and timing table.', implementation='chart_registry._efficiency'),
    dict(id='graph_size', paper='RQ7 (§6.9); output/synthetic/graph_size_robustness.csv, global_bridge_sensitivity.png', paper_figure=None, group='robustness', renderer='sizes', kind='conditional',
         caption='Known-truth behaviour persists at 6, 15 and 30 nodes per community.',
         source='experiments.synthetic_evaluation.rq7GraphSizeRobustness', question='Does behaviour persist across graph sizes?',
         axes='x: nodes per community; y: impact (and achieved change, no-op, edge-count preservation).',
         requires='Regenerating a synthetic dataset at several sizes; impossible for real fixtures whose node set is fixed.',
         multi_run='Yes: one explanation per size.', display='Point chart per direction.', implementation='guided.run_sizes'),
    dict(id='matched_comparison', paper='RQ1b (§6.3); output/synthetic/matched_comparison.png', paper_figure=None, group='global', renderer='matched', kind='conditional',
         caption='Concepts are compared only when units are compatible and achieved changes match within 10%.',
         source='experiments.synthetic_evaluation.sweepConcept/bestMatch; realdata.comparability.comparabilityOf',
         question='When can two concepts\' responses be compared?', axes='Concept pairs x direction: comparable or not, reason, matched impacts.',
         requires='A fine sweep of request sizes per concept (MATCH_DELTAS) on the selected model.', multi_run='Yes: concepts x 12 request sizes x 2.',
         display='Pair table with matched impacts.', implementation='guided.run_matched'),
    dict(id='faithfulness', paper='RQ1 (§6.2); output/synthetic/faithfulness.csv', paper_figure=None, group='reference', renderer='reference', kind='blocked',
         caption='Known analytical relationships are recovered in pure Bridge Width, persistence, Centralization, weighted and slope models.',
         source='experiments.synthetic_evaluation.rq1Faithfulness', question='Can TGAP recover relationships known from the model definition?',
         axes='Table of measured vs analytical impact and relative error.',
         requires='The synthetic known-truth model suite (pure Bridge Width, pure Centralization, weighted 2*BW + 3*C) with analytical expectations.',
         multi_run='Yes.', display='Documented limitation.', implementation='none (blocked)',
         blocked='The workbench models are the six real-data analytical variants (Table 4), not the known-truth suite, and no analytical expectation is defined for an arbitrary dataset. Run `tgap run paper` locally for RQ1. Your persistence-model runs on synthetic data can still be checked by hand: a present-only Bridge Width model\'s impact equals its baseline bridge count when bridges are constant over time.'),
]

INVENTORY_BY_ID = {item['id']: item for item in INVENTORY}


def inventory():
    return dict(groups=[dict(id=g, title=t, description=d) for g, t, d in GROUPS], charts=INVENTORY)


def chart(item_id, status, data=None, scope='', deviation='', ctx=None):
    item = INVENTORY_BY_ID[item_id]
    payload = dict(id=item_id, title=TITLES[item_id], caption=item['caption'],
                   paper=item['paper'], paper_figure=item['paper_figure'], group=item['group'], renderer=item['renderer'],
                   kind=item['kind'], status=status, scope=scope, deviation=deviation, data=data, axes=item['axes'],
                   blocked=item.get('blocked'))
    payload['explanation'] = explain(item_id, payload, ctx or {})
    return payload


TITLES = dict(workflow='How this explanation was produced', model_separated_impacts='Concept impacts, separated by model',
              beeswarm='Individual concept responses (beeswarm)', boxplot='Response distributions by model',
              tgn_seed_stability='Learned-model (TGN) seed stability', local_graph='Original versus transformed graph',
              local_bar='Local edge explanation', temporal_local='When the concept matters (one snapshot at a time)',
              edge_time='Edges and time', dependence='Structure versus measured response', impact_distribution='Exploratory spread of all valid impacts',
              bridge_matrix='Connections between communities', requested_vs_achieved='Requested versus achieved change',
              validity_map='Validity of every tested setting', delta_sensitivity='Response to request size',
              normalization='Achieved versus requested normalization', temporal_sensitivity='Present-only versus history-reading models (Bridge Trend)',
              trajectory='Concept history: original versus transformed', leakage='Side effects on other graph properties',
              seed_stability='Stability across seeds', efficiency='Model-call budget and run time', graph_size='Behaviour across graph sizes',
              matched_comparison='Matched cross-concept comparison', faithfulness='Known-truth faithfulness')


def quartiles(values):
    """Matplotlib boxplot convention (linear percentiles, 1.5 IQR whiskers)."""
    v = sorted(values)
    if len(v) == 1:
        q1 = med = q3 = v[0]
    else:
        # 'inclusive' equals numpy's default linear percentile; median is exact.
        q1, _, q3 = statistics.quantiles(v, n=4, method='inclusive')
        med = statistics.median(v)
    iqr = q3-q1
    low = min(x for x in v if x >= q1-1.5*iqr)
    high = max(x for x in v if x <= q3+1.5*iqr)
    return dict(q1=q1, median=med, q3=q3, whisker_low=low, whisker_high=high, n=len(v))


def build_charts(ctx):
    builders = [_workflow, _req_ach, _validity, _delta, _normalization, _strips, _beeswarm, _boxplot, _signedlog,
                _matched, _temporal_sensitivity, _temporal_local, _trajectory, _edge_time, _local_graph, _bridge_matrix,
                _local_bar, _dependence, _leakage, _stability, _graph_size, _efficiency, _tgn, _faithfulness]
    charts = []
    for builder in builders:
        try:
            charts.append(builder(ctx))
        except Exception as error:   # never drop a chart silently
            item_id = builder.__name__.lstrip('_')
            item_id = ALIASES.get(item_id, item_id)
            charts.append(chart(item_id, 'unavailable', scope=f'Chart computation failed: {type(error).__name__}: {str(error)[:200]}', ctx=ctx))
    missing = set(INVENTORY_BY_ID) - {c['id'] for c in charts}
    assert not missing, f'Inventory entries without a chart: {missing}'
    return charts


ALIASES = dict(strips='model_separated_impacts', signedlog='impact_distribution', matched='matched_comparison', stability='seed_stability',
               tgn='tgn_seed_stability', req_ach='requested_vs_achieved', validity='validity_map', delta='delta_sensitivity')


def _matrix_rows(ctx, valid_only=False):
    matrix = ctx.get('matrix')
    if not matrix:
        return None
    rows = matrix['rows']
    return [r for r in rows if r['valid_for_analysis'] and r['impact'] is not None] if valid_only else rows


def _missing_matrix(item_id, ctx):
    error = next((e['error'] for e in ctx.get('errors', []) if e['stage'] == 'matrix'), 'The model x concept runs did not complete.')
    return chart(item_id, 'unavailable', scope=f'Needs the model x concept runs, which failed: {error}', ctx=ctx)


def _workflow(ctx):
    main, matrix = ctx['main'], ctx.get('matrix')
    data = dict(dataset=ctx['spec']['dataset'], model=ctx['spec']['model'], concept=ctx['selected'], direction=ctx['spec']['direction'],
                snapshots=main['summary']['snapshots'], nodes=main['summary']['nodes'], core_calls=main['summary']['model_calls'],
                figure_calls=main['summary'].get('figure_model_calls', 0), matrix_calls=sum(c['measured'] for c in matrix['calls']) if matrix else 0,
                valid_rows=main['summary']['valid_rows'], total_rows=main['summary']['total_rows'])
    return chart('workflow', 'ok', data, scope='The original Fig. 1 is a static diagram; this live version shows the same pipeline with your run\'s values.', ctx=ctx)


def _req_ach(ctx):
    rows = _matrix_rows(ctx)
    if rows is None:
        return _missing_matrix('requested_vs_achieved', ctx)
    model, concept = ctx['spec']['model'], ctx['selected']
    selected = [r for r in rows if r['model'] == model and r['concept'] == concept]
    at_delta = [r for r in rows if r['model'] == model and abs(r['sweep_delta']-ctx['spec']['delta']) < 1e-9]
    keep = ('concept', 'direction', 'requested_delta', 'measured_achieved_delta', 'delta_mode', 'status', 'reason', 'noop', 'valid_for_analysis', 'property_baseline')
    data = dict(selected=[{k: r[k] for k in keep} for r in selected], all_concepts=[{k: r[k] for k in keep} for r in at_delta],
                primary={k: ctx['primary'][k] for k in ('direction', 'requested_delta', 'achieved_delta', 'delta_mode', 'status', 'reason', 'noop', 'valid_for_analysis')})
    return chart('requested_vs_achieved', 'ok', data, scope='Achieved values of excluded rows are shown as measured but flagged; they never enter impacts.', ctx=ctx)


def _validity(ctx):
    rows = _matrix_rows(ctx)
    if rows is None:
        return _missing_matrix('validity_map', ctx)
    model = ctx['spec']['model']
    grid = [dict(concept=r['concept'], delta=r['sweep_delta'], direction=r['direction'], status=r['status'], noop=r['noop'], reason=r['reason'])
            for r in rows if r['model'] == model]
    counts = dict(total=len(rows), valid=sum(r['valid_for_analysis'] for r in rows),
                  edge_count_infeasible=sum(r['status'] == 'edge_count_infeasible' for r in rows),
                  saturated=sum(r['status'] == 'saturated' for r in rows), wrong_direction=sum(r['status'] == 'wrong_direction' for r in rows),
                  no_property_change=sum(r['status'] == 'no_property_change' for r in rows),
                  noop_valid=sum(r['noop'] and r['valid_for_analysis'] for r in rows))
    counts['invalid'] = counts['total']-counts['valid']
    data = dict(grid=grid, counts=counts, models=len(ctx['matrix']['models']), concepts=ctx['matrix']['concepts'], deltas=ctx['matrix']['deltas'])
    return chart('validity_map', 'ok', data, scope='Validity depends only on the graph and the transformation, so the grid is the same for every model; counts cover all model rows like Table 5.', ctx=ctx)


def _delta(ctx):
    rows = _matrix_rows(ctx)
    if rows is None:
        return _missing_matrix('delta_sensitivity', ctx)
    sel = [r for r in rows if r['model'] == ctx['spec']['model'] and r['concept'] == ctx['selected']]
    keep = ('direction', 'sweep_delta', 'requested_delta', 'achieved_delta', 'impact', 'prediction_change', 'noop', 'status', 'valid_for_analysis')
    status = 'ok' if len({r['sweep_delta'] for r in sel}) > 1 else 'partial'
    return chart('delta_sensitivity', status, dict(rows=[{k: r[k] for k in keep} for r in sel], deltas=ctx['matrix']['deltas']),
                 scope='' if status == 'ok' else 'Only one request size was run; choose several sizes to see a trend.', ctx=ctx)


def _normalization(ctx):
    rows = _matrix_rows(ctx)
    if rows is None:
        return _missing_matrix('normalization', ctx)
    sel = [r for r in rows if r['model'] == ctx['spec']['model'] and r['concept'] == ctx['selected']]
    keep = ('direction', 'sweep_delta', 'achieved_delta', 'impact', 'impact_requested_normalization', 'prediction_change', 'noop', 'valid_for_analysis', 'delta_mode')
    return chart('normalization', 'ok', dict(rows=[{k: r[k] for k in keep} for r in sel]),
                 deviation='The paper measures each normalization\'s error against a known analytical impact (synthetic Bridge Width model). Your configuration has no analytical truth, so the chart compares the two normalizations directly instead of reporting an error.', ctx=ctx)


def _strips(ctx):
    rows = _matrix_rows(ctx)
    if rows is None:
        return _missing_matrix('model_separated_impacts', ctx)
    matrix = ctx['matrix']
    panels = []
    for model in matrix['models']:
        for group in matrix['semantic_rows']:
            for concept in group['concepts']:
                cell = [r for r in rows if r['model'] == model and r['concept'] == concept]
                points = [dict(impact=r['impact'], delta=r['sweep_delta'], direction=r['direction']) for r in cell if r['valid_for_analysis'] and r['impact'] is not None]
                panels.append(dict(model=model, group=group['label'], concept=concept, points=points, n=len(points), excluded=len(cell)-len(points)))
    return chart('model_separated_impacts', 'ok', dict(panels=panels, models=matrix['models'], semantic_rows=matrix['semantic_rows'], deltas=matrix['deltas']),
                 scope=f"Your dataset only (the paper shows Decentraland and Email-Eu-core); {len(matrix['models'])} model(s), {len(matrix['concepts'])} concept(s), request sizes {', '.join(f'{d:g}' for d in matrix['deltas'])}.", ctx=ctx)


def _beeswarm(ctx):
    rows = _matrix_rows(ctx, valid_only=True)
    if rows is None:
        return _missing_matrix('beeswarm', ctx)
    groups = []
    for group in ctx['matrix']['semantic_rows']:
        groups.append(dict(label=group['label'], concepts=[dict(concept=c, points=[dict(impact=r['impact'], model=r['model'], delta=r['sweep_delta'], direction=r['direction'])
                                                                                  for r in rows if r['concept'] == c]) for c in group['concepts']]))
    return chart('beeswarm', 'ok', dict(groups=groups), scope='One dataset panel (yours). As in the paper, each panel pools the valid rows of all selected models for a concept; model is shown on hover.', ctx=ctx)


def _boxplot(ctx):
    rows = _matrix_rows(ctx, valid_only=True)
    if rows is None:
        return _missing_matrix('boxplot', ctx)
    shared = next((g['concepts'] for g in ctx['matrix']['semantic_rows'] if g['label'] == 'relative delta'), [])
    excluded = [c for c in ctx['matrix']['concepts'] if c not in shared]
    panels = []
    for model in ctx['matrix']['models']:
        boxes = []
        for concept in shared:
            values = [r['impact'] for r in rows if r['model'] == model and r['concept'] == concept]
            boxes.append(dict(concept=concept, values=values, **(quartiles(values) if values else dict(n=0))))
        panels.append(dict(model=model, boxes=boxes))
    status = 'ok' if shared else 'unavailable'
    return chart('boxplot', status, dict(panels=panels, concepts=shared, excluded=excluded),
                 scope='Only the relative-delta concepts are boxed, as in the paper.' + (' None of your selected concepts belongs to that group.' if not shared else ''), ctx=ctx)


def _signedlog(ctx):
    rows = _matrix_rows(ctx, valid_only=True)
    if rows is None:
        return _missing_matrix('impact_distribution', ctx)
    concepts = sorted({r['concept'] for r in rows})
    data = dict(concepts=[dict(concept=c, points=[dict(impact=r['impact'], shown=math.copysign(math.log10(1+abs(r['impact'])), r['impact']), model=r['model'])
                                                  for r in rows if r['concept'] == c]) for c in concepts])
    return chart('impact_distribution', 'ok', data, scope='The paper pools 8 datasets; this view pools the selected models on your one dataset. Exploratory only.', ctx=ctx)


def _matched(ctx):
    matched = ctx.get('matched')
    if not ctx['spec']['sweep'].get('matched'):
        return chart('matched_comparison', 'not_requested', scope='Optional: enable "Matched cross-concept comparison" before running (adds a 12-size sweep per concept).', ctx=ctx)
    if not matched:
        return chart('matched_comparison', 'unavailable', scope='The matched sweep failed: ' + next((e['error'] for e in ctx['errors'] if e['stage'] == 'matched'), 'unknown error'), ctx=ctx)
    return chart('matched_comparison', 'ok', matched, deviation='Rows failing the validity gate are removed before matching (the synthetic RQ1b world had no infeasible rows).', ctx=ctx)


def _temporal_sensitivity(ctx):
    rows = _matrix_rows(ctx)
    if rows is None:
        return _missing_matrix('temporal_sensitivity', ctx)
    if 'Bridge Trend' not in ctx['matrix']['concepts']:
        return chart('temporal_sensitivity', 'not_requested', scope='Add Bridge Trend to the comparison concepts to run this test.', ctx=ctx)
    data = [dict(model=r['model'], direction=r['direction'], delta=r['sweep_delta'], impact=r['impact'], prediction_change=r['prediction_change'],
                 status=r['status'], valid_for_analysis=r['valid_for_analysis']) for r in rows if r['concept'] == 'Bridge Trend']
    # Show the user's size when Bridge Trend is valid there, otherwise the size
    # with the most valid rows (an invalid size says nothing about RQ2).
    def n_valid(d):
        return sum(r['valid_for_analysis'] for r in data if abs(r['delta']-d) < 1e-9)
    own = round(ctx['spec']['delta'], 6)
    shown = own if n_valid(own) else max(ctx['matrix']['deltas'], key=lambda d: (n_valid(d), -d))
    scope = '' if shown == own or not n_valid(shown) else f"Bridge Trend is invalid at your {round(own*100)}% request on this dataset, so the {round(shown*100)}% request is shown."
    if not n_valid(shown):
        shown = own
    return chart('temporal_sensitivity', 'ok', dict(rows=data, models=ctx['matrix']['models'], deltas=ctx['matrix']['deltas'], shown_delta=shown),
                 scope=scope, ctx=ctx)


def _temporal_local(ctx):
    temporal = ctx.get('temporal')
    if not temporal:
        return chart('temporal_local', 'unavailable', scope='The per-snapshot runs failed: ' + next((e['error'] for e in ctx['errors'] if e['stage'] == 'temporal'), 'unknown'), ctx=ctx)
    status = 'ok' if any(p['valid_for_analysis'] for p in temporal['panels']) else 'unavailable'
    return chart('temporal_local', status, temporal, scope='' if status == 'ok' else 'The selected direction is invalid for analysis, so per-snapshot effects are not computed.', ctx=ctx)


def _trajectory(ctx):
    comparisons = [c for c in ctx['main'].get('comparisons', []) if c['concept'] == ctx['selected']]
    data = dict(original=ctx['main']['trajectory'], transformed={c['direction']: c['trajectory'] for c in comparisons},
                status={c['direction']: c['status'] for c in comparisons})
    return chart('trajectory', 'ok' if comparisons else 'unavailable', data, ctx=ctx)


def _edge_time(ctx):
    a = ctx['main'].get('analyses') or {}
    if not a.get('edge_time'):
        return chart('edge_time', 'unavailable', scope='No edge-time measurements completed within the bounded budget (128 calls / 10 s).', ctx=ctx)
    data = dict(cells=a['edge_time'], edges=a['edge_time_selection']['edges'], snapshots=a['snapshot_indices'], selection=a['edge_time_selection'], labels=ctx['labels'])
    partial = a['edge_time_selection']['evaluated_pairs'] < a['edge_time_selection']['possible_pairs']
    return chart('edge_time', 'partial' if partial else 'ok', data,
                 scope=f"{a['edge_time_selection']['evaluated_pairs']}/{a['edge_time_selection']['possible_pairs']} edge/time cells measured for up to 4 edges and 8 snapshots (the paper's synthetic demo used 22 edges).", ctx=ctx)


def _local_graph(ctx):
    structure = ctx.get('structure')
    if not structure:
        return chart('local_graph', 'unavailable', scope='The graph comparison failed.', ctx=ctx)
    return chart('local_graph', 'ok', dict(view=structure['view'], per_snapshot=structure['directions'][ctx['spec']['direction']]['per_snapshot']),
                 scope='Your dataset instead of the paper\'s controlled synthetic example.', ctx=ctx)


def _bridge_matrix(ctx):
    structure = ctx.get('structure')
    if not structure:
        return chart('bridge_matrix', 'unavailable', scope='The graph comparison failed.', ctx=ctx)
    data = dict(labels=structure['view']['community_labels'], directions=structure['directions'])
    return chart('bridge_matrix', 'ok', data, scope=f"{len(data['labels'])} communities in your dataset (the paper's demo uses four).", ctx=ctx)


def _local_bar(ctx):
    a = ctx['main'].get('analyses') or {}
    if not a.get('edges') or not a['edges'].get('rows'):
        return chart('local_bar', 'unavailable', scope='Edge occlusion did not complete within the bounded budget.', ctx=ctx)
    e = a['edges']
    return chart('local_bar', 'partial' if e['edges_evaluated'] < e['edges_total'] else 'ok', e,
                 scope=f"{e['edges_evaluated']}/{e['edges_total']} candidate edges measured; ordering is among measured edges only.", ctx=ctx)


def _dependence(ctx):
    a = ctx['main'].get('analyses') or {}
    if not a.get('nodes') and not a.get('edges'):
        return chart('dependence', 'unavailable', scope='No element measurements completed.', ctx=ctx)
    return chart('dependence', 'ok', dict(nodes=a.get('nodes'), edges=a.get('edges')), ctx=ctx)


def _leakage(ctx):
    matrix = ctx.get('matrix')
    if not matrix:
        return _missing_matrix('leakage', ctx)
    rows = [r for r in matrix['leakage'] if r['concept'] == ctx['selected']]
    return chart('leakage', 'ok' if rows else 'unavailable', dict(rows=rows, delta=ctx['spec']['delta']),
                 deviation='Cohesion is computed by exact dense eigen-decomposition instead of core.CohesionMetric\'s iterative solver, which can fail to terminate on graphs with repeated Laplacian eigenvalues; the definition (Fiedler value, 0 if disconnected) is unchanged.', ctx=ctx)


def _stability(ctx):
    if not ctx['spec']['sweep'].get('repeats'):
        return chart('seed_stability', 'not_requested', scope='Optional: choose a number of extra seeds before running.', ctx=ctx)
    stability = ctx.get('stability')
    if not stability:
        return chart('seed_stability', 'unavailable', scope='Seed repeats failed: ' + next((e['error'] for e in ctx['errors'] if e['stage'] == 'stability'), 'unknown'), ctx=ctx)
    scope = ''
    if ctx['family'] == 'real' and stability['variation'] == 'graph':
        scope = 'Real fixtures do not depend on the seed, so graph-seed variation is not meaningful here.'
    if ctx['spec']['concept'] == 'custom':
        scope += ' Custom transformations have no seed; repeats test determinism only.'
    return chart('seed_stability', 'ok', stability, scope=scope.strip(), ctx=ctx)


def _graph_size(ctx):
    if ctx['family'] != 'synthetic':
        return chart('graph_size', 'not_applicable', scope='Real fixtures have a fixed node set, so they cannot be regenerated at other sizes.', ctx=ctx)
    if not ctx['spec']['sweep'].get('sizes'):
        return chart('graph_size', 'not_requested', scope='Optional: choose graph sizes before running.', ctx=ctx)
    sizes = ctx.get('sizes')
    if not sizes:
        return chart('graph_size', 'unavailable', scope='Size runs failed: ' + next((e['error'] for e in ctx['errors'] if e['stage'] == 'sizes'), 'unknown'), ctx=ctx)
    return chart('graph_size', 'ok', sizes, deviation='The paper reports relative error against a known analytical impact; without an analytical truth for this model, measured impacts, no-ops and edge-count preservation are shown instead.', ctx=ctx)


def _efficiency(ctx):
    main, matrix = ctx['main'], ctx.get('matrix')
    k = main['summary']['total_rows']//2
    runs = [dict(run='Selected explanation', transformations=k, expected=1+2*k, measured=main['summary']['model_calls'])]
    if matrix:
        runs += [dict(run=f"{c['model']} at {c['delta']:g}", transformations=c['transformations'], expected=c['expected'], measured=c['measured']) for c in matrix['calls']]
    data = dict(runs=runs, figure_calls=main['summary'].get('figure_model_calls', 0), engine_seconds=main.get('seconds'))
    return chart('efficiency', 'ok', data, ctx=ctx)


def _tgn(ctx):
    return chart('tgn_seed_stability', 'blocked', scope='Published reference only.', ctx=ctx)


def _faithfulness(ctx):
    return chart('faithfulness', 'blocked', ctx=ctx)
