"""Guided TGAP user study: one configured experiment plus the additional
measured runs needed to regenerate the paper's charts for that configuration.

Nothing here re-implements TGAP mathematics. Every number comes from the
research library (TgapExplainer.explainDetailed, temporalAttribution,
bridgeMatrix, sweepConcept/bestMatch, comparabilityOf) or from the existing
workbench engine (execute, validity_gate). The only addition is caching: a
transformation is model-independent, so each (concept, delta) counterfactual
is built once and then scored by every selected model. All models therefore
see the identical counterfactual graph.
"""
import hashlib
import json
import math
import statistics
import time
from pathlib import Path

from sandbox.engine import (MODELS, SYNTHETIC, TRANSFORMS, build, execute,
                            load_core, validity_gate, world)

GUIDED_VERSION = '1.0.0'
PAPER_DELTAS = (0.1, 0.25, 0.5)          # realdata.run_real_data.DELTAS
PAPER_SIZES = (6, 15, 30)                # RQ7 nodes per community
SIZE_CHOICES = (6, 10, 15, 30)
MAX_REPEATS = 10
TIME_LIMIT_SECONDS = 240

# Paper §4.3: structure within a snapshot vs. evolution across snapshots.
CONCEPTS = {
    'bridge_width': dict(kind='structural',
        represents='The number of edges that connect different communities (cross-community ties).',
        changes='Adds or removes cross-community edges; the same number of internal edges is removed or added so the total edge count stays fixed.',
        fixed='Node set and, when feasible, each snapshot\'s edge count.',
        constraints='A decrease cannot go below zero bridges and an increase needs free node pairs across communities; if the edge budget cannot be kept the run is marked edge_count_infeasible.',
        controls='Requested relative change (e.g. 10% more bridges) and direction.'),
    'centralization': dict(kind='structural',
        represents='How strongly ties concentrate on the best-connected actors (Freeman degree centralization, 0..1).',
        changes='Rewires a fraction of edges toward (increase) or away from (decrease) hub nodes.',
        fixed='Node set, edge count and community-pair tie counts.',
        constraints='The requested delta is a rewiring fraction (a mechanism knob), not a relative change of centralization, so its numbers cannot be compared with the relative-delta concepts.',
        controls='Rewiring fraction and direction.'),
    'density': dict(kind='structural',
        represents='The fraction of possible ties that are present, changed through ties inside communities.',
        changes='Adds or removes internal (within-community) edges.',
        fixed='Node set and cross-community ties.',
        constraints='Edge count changes by design. Very sparse or nearly complete communities limit how far it can move.',
        controls='Requested relative change and direction.'),
    'bridge_trend': dict(kind='temporal',
        represents='The slope of Bridge Width through time (bridges per snapshot).',
        changes='Reshapes earlier snapshots\' bridges so the trajectory becomes steeper or flatter, keeping the latest snapshot fixed.',
        fixed='The present (last) snapshot and, when feasible, earlier edge budgets.',
        constraints='Earlier snapshots cannot go below one bridge (saturation), and the achieved slope can move against the request (wrong_direction). Achieved change is measured in absolute slope units.',
        controls='Requested change and direction.'),
    'churn': dict(kind='temporal',
        represents='Relationship turnover: how much earlier snapshots differ from the present.',
        changes='Swaps ties in earlier snapshots to make the history more (or less) different from the latest snapshot.',
        fixed='The present snapshot, node sets and edge counts.',
        constraints='Short or very sparse histories leave little to swap, which can produce no-ops.',
        controls='Requested relative change and direction.'),
}

# What each model's output number means (core.TemporalGraphModel docstrings).
MODEL_INFO = {
    'persistence_bridge': dict(output='Bridge Width (number of cross-community edges) in the target snapshot.',
        unit='edges', reads='target snapshot only', operator='persistence', metric='Bridge Width'),
    'trend_bridge': dict(output='A straight-line forecast of Bridge Width one step after the target snapshot, fitted to all snapshots.',
        unit='edges', reads='full history', operator='trend extrapolation', metric='Bridge Width'),
    'slope_bridge': dict(output='The least-squares slope of Bridge Width across snapshots (bridges gained per snapshot).',
        unit='edges per snapshot', reads='full history', operator='trajectory slope', metric='Bridge Width'),
    'persistence_density': dict(output='Graph density (fraction of possible ties) of the target snapshot.',
        unit='fraction 0..1', reads='target snapshot only', operator='persistence', metric='Density'),
    'persistence_centralization': dict(output='Freeman degree centralization (0..1) of the target snapshot.',
        unit='fraction 0..1', reads='target snapshot only', operator='persistence', metric='Centralization'),
    'trend_clustering': dict(output='A straight-line forecast of average clustering one step after the target snapshot.',
        unit='coefficient 0..1', reads='full history', operator='trend extrapolation', metric='Clustering'),
}


def stable_hash(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def finite(value):
    return value is not None and isinstance(value, (int, float)) and math.isfinite(value)


def clean(value):
    """JSON-safe float (NaN/inf become None)."""
    if isinstance(value, bool) or value is None:
        return value
    if isinstance(value, (int, float)):
        return float(value) if math.isfinite(value) else None
    return value


##  Catalogue, dataset profiles, previews  ##


def concept_catalogue(core):
    classes = {'bridge_width': core.BridgeWidthTransformation, 'centralization': core.CentralizationTransformation,
               'density': core.DensityTransformation, 'bridge_trend': core.BridgeTrendTransformation,
               'churn': core.ChurnTransformation}
    out = []
    for key, (name, description) in TRANSFORMS.items():
        cls = classes[key]
        out.append(dict(id=key, name=name, description=description, delta_mode=getattr(cls, 'deltaMode', 'relative'),
                        preserves_edge_count=bool(getattr(cls, 'preservesEdgeCount', False)),
                        achieved_units='rewiring fraction (mechanism)' if key == 'centralization'
                        else 'absolute slope units' if getattr(cls, 'deltaMode', 'relative') == 'absolute'
                        else 'relative change of the measured property', **CONCEPTS[key]))
    return out


def model_catalogue():
    return [dict(id=k, name=n, description=d, **MODEL_INFO[k]) for k, (n, d) in MODELS.items()]


def dataset_profile(dataset, core, data_root, seed=42):
    """Genuine metadata computed from the bundled fixture or generator."""
    graphs, comm, labels, meta = world(dict(dataset=dataset, seed=seed), core, data_root)
    edges = [g.number_of_edges() for g in graphs]
    sizes = [len(c) for c in comm]
    community_labels = list(getattr(comm, 'labels', None) or [f'Community {i+1}' for i in range(len(comm))])
    family = 'synthetic' if dataset in SYNTHETIC or dataset == 'three_communities' else 'real'
    keep = ('dataset', 'description', 'source', 'graph_nodes_are', 'graph_edges_are', 'graph_family', 'snapshot_interval',
            'raw_nodes', 'retained_nodes', 'raw_events', 'retained_events', 'raw_span_days', 'evaluated_span_days',
            'directed', 'weighted', 'edge_attributes_note', 'name', 'groundTruth')
    pre = meta.get('preprocessing', {}) if isinstance(meta.get('preprocessing'), dict) else {}
    return dict(id=dataset, family=family, snapshots=len(graphs), snapshot_labels=list(labels),
                nodes=graphs[-1].number_of_nodes(), edges_per_snapshot=edges, edges_min=min(edges), edges_max=max(edges),
                edges_mean=round(sum(edges)/len(edges), 2), communities=len(comm), community_sizes=sizes,
                community_labels=community_labels,
                meta={k: meta[k] for k in keep if k in meta},
                preprocessing={k: pre[k] for k in ('projection', 'node_selection', 'selection_period', 'evaluation_period',
                                                   'time_unit', 'future_information_used_for_node_selection') if k in pre},
                # Every built-in model and concept runs on every dataset; whether a
                # particular request is feasible is decided by the validity gate.
                models=list(MODELS), concepts=list(TRANSFORMS),
                min_target_snapshot=1, constraints=dataset_constraints(dataset, family, edges, sizes))


def dataset_constraints(dataset, family, edges, sizes):
    notes = []
    if family == 'real':
        notes.append('Actor set and communities are frozen from the first 20% of the time span; the remaining period is evaluated (leakage-safe preprocessing).')
        notes.append('Edge weights, signs and directions are not used by the TGAP metrics; edges are undirected and collapsed within a snapshot.')
        notes.append('Real data demonstrates applicability; it has no explanation ground truth.')
    else:
        notes.append('Generated from the seed, so the graph itself changes with the seed. Known structure makes expected responses checkable.')
    if min(edges) < 10:
        notes.append(f'Some snapshots are very sparse (minimum {min(edges)} edges); small requests can become no-ops and edge budgets can be infeasible.')
    if len(sizes) > 2:
        notes.append(f'{len(sizes)} communities: Bridge Width counts all cross-community edges (sum over community pairs).')
    return notes


def preview(spec, core, data_root):
    """Original model outputs for every model at the chosen target, plus the
    original concept values. Cheap, deterministic, no transformation."""
    graphs, comm, labels, meta = world(spec, core, data_root)
    outputs = []
    for key in MODELS:
        model, _ = build(dict(spec, model=key, transformations=[], custom_code=''), core, comm)
        outputs.append(dict(model=key, prediction=clean(float(model.predict(graphs)))))
    _, transforms = build(dict(spec, model='persistence_bridge', transformations=list(TRANSFORMS), custom_code=''), core, comm)
    concepts = [dict(concept=t.name, id=key, value=clean(float(t.propertyValue(graphs))), delta_mode=t.deltaMode)
                for key, t in zip(TRANSFORMS, transforms)]
    return dict(spec=spec, target_snapshot=len(graphs)-1, target_label=labels[-1], snapshots_used=len(graphs),
                outputs=outputs, concepts=concepts)


def feasibility(spec, core, data_root):
    """Validity gate for both directions of one concept at one delta, before running."""
    graphs, comm, labels, meta = world(spec, core, data_root)
    _, transforms = build(dict(spec, model='persistence_bridge', transformations=[spec['concept']], custom_code=''), core, comm)
    trans = transforms[0]
    out = []
    for delta in (spec['delta'], -spec['delta']):
        status, reason = validity_gate(core, graphs, trans, delta, comm)
        out.append(dict(direction='increase' if delta > 0 else 'decrease', status=status, reason=reason,
                        valid_for_analysis=status == 'ok'))
    return dict(concept=trans.name, delta=spec['delta'], property_value=clean(float(trans.propertyValue(graphs))), directions=out)


##  Execution  ##


class CachedTransformation:
    """Model-independent counterfactual cache around a real transformation.
    Forwards every attribute; transform() is computed once per delta."""

    def __init__(self, inner, cache):
        self._inner, self._cache = inner, cache

    def __getattr__(self, name):
        return getattr(self._inner, name)

    def transform(self, snapshots, delta):
        key = (id(snapshots), self._inner.name, round(delta, 12))
        if key not in self._cache:
            self._cache[key] = self._inner.transform(snapshots, delta)
        return self._cache[key]


class ExactCohesion:
    """Cohesion (algebraic connectivity, the Fiedler value) by exact dense
    eigen-decomposition. core.CohesionMetric uses networkx's iterative
    solver, which does not terminate on some graphs with repeated Laplacian
    eigenvalues (e.g. a snapshot that became complete). The definition is
    unchanged: 0 for disconnected graphs, else the second-smallest Laplacian
    eigenvalue. Graphs here have at most a few hundred nodes."""

    def measure(self, graph):
        import networkx as nx
        import numpy as np
        if graph.number_of_nodes() < 2 or not nx.is_connected(graph):
            return 0.0
        laplacian = nx.laplacian_matrix(graph, nodelist=sorted(graph.nodes())).toarray().astype(float)
        return float(np.linalg.eigvalsh(laplacian)[1])


def leakage_panel(core, comm):
    return {'Bridge Width': core.BridgeWidthMetric(comm), 'Density': core.DensityMetric(),
            'Centralization': core.DegreeCentralizationMetric(), 'Clustering': core.ClusteringMetric(),
            'Cohesion': ExactCohesion()}


def semantic_rows(transformations):
    """Panel grouping used by the paper's Figs 2-4 (realdata.make_publication
    .semanticRows): one shared row for concepts that comparabilityOf admits as
    commensurable with a relative-delta reference, one row per other concept.
    Applied to the user's own concept set so a custom concept is grouped by
    the same rule. If the rule cannot be imported, every concept gets its own
    row, which never implies a comparison."""
    try:
        from realdata.comparability import comparabilityOf
    except Exception as error:
        return [dict(label=t.name, concepts=[t.name], note='own perturbation units',
                     fallback=f'Comparability rule unavailable ({type(error).__name__}); no concepts share a panel.')
                for t in transformations]
    reference = next((t for t in transformations if getattr(t, 'deltaMode', 'relative') == 'relative'
                      and comparabilityOf(t, t)[0]), None)
    shared = [t.name for t in transformations if reference is not None and comparabilityOf(reference, t)[0]]
    rows = [dict(label='relative delta', concepts=shared, note='comparable under the matched-delta protocol')] if shared else []
    for t in transformations:
        if t.name not in shared:
            rows.append(dict(label=t.name, concepts=[t.name], note='own perturbation units',
                             reason=comparabilityOf(reference or t, t)[1] if reference is not None else None))
    return rows


def row_from_record(record, trans, p0, status, reason, model_key):
    valid = status == 'ok'
    delta = record['requestedDelta']
    change = record['transformed'] - record['baseline']
    mode = 'absolute' if record['deltaMode'] == 'relative' and p0 == 0 else record['deltaMode']
    return dict(model=model_key, concept=trans.name, direction='increase' if delta > 0 else 'decrease',
                requested_delta=delta, sweep_delta=abs(delta), delta_mode=mode, requested_delta_mode=record['deltaMode'],
                measured_achieved_delta=clean(record['achievedDelta']),
                achieved_delta=clean(record['achievedDelta']) if valid else None,
                baseline=clean(record['baseline']), prediction=clean(record['transformed']) if valid else None,
                prediction_change=clean(change) if valid else None, impact=clean(record['impact']) if valid else None,
                impact_requested_normalization=clean(change/abs(delta)) if valid else None,
                normalizer=record['normalizer'], noop=bool(record['noop']), status=status, reason=reason,
                valid_for_analysis=valid, property_baseline=clean(p0))


def execute_guided(spec, root, data_root, progress=None):
    progress = progress or (lambda stage, message: None)
    started = time.monotonic()
    timings, errors = {}, []
    core = load_core(root)

    def stage(name, message, operation, required=False):
        progress(name, message)
        t0 = time.monotonic()
        try:
            return operation()
        except Exception as error:
            if required:
                raise
            errors.append(dict(stage=name, error=f'{type(error).__name__}: {str(error)[:300]}'))
            return None
        finally:
            timings[name] = round(time.monotonic()-t0, 3)

    sweep = spec['sweep']
    custom = bool(spec.get('custom_code', '').strip())
    concept_ids = [] if spec['concept'] == 'custom' else [spec['concept']]
    main_spec = dict(dataset=spec['dataset'], model=spec['model'], transformations=concept_ids, delta=spec['delta'],
                     seed=spec['seed'], custom_code=spec.get('custom_code', '') if custom else '',
                     target_snapshot=spec.get('target_snapshot'))

    progress('validate', 'Loading the dataset and checking the configuration')
    graphs, comm, labels, meta = world(main_spec, core, data_root)
    if len(graphs) < 2:
        raise ValueError('At least two snapshots are needed.')

    main = stage('main', 'Running the selected explanation (both directions) and local measurements',
                 lambda: execute(main_spec, root, data_root), required=True)
    selected_name = main['rows'][0]['concept'] if spec['concept'] != 'custom' else [r['concept'] for r in main['rows']][-1]
    primary = next(r for r in main['rows'] if r['concept'] == selected_name and r['direction'] == spec['direction'])

    # Concept set for the paper's model x concept charts.
    matrix_ids = list(dict.fromkeys(list(sweep['concepts']) + concept_ids))
    _, inner = build(dict(main_spec, transformations=matrix_ids), core, comm)
    cache = {}
    transforms = [CachedTransformation(t, cache) for t in inner]
    deltas = sorted(set(round(d, 6) for d in sweep['deltas']) | {round(spec['delta'], 6)})
    model_keys = list(dict.fromkeys([spec['model']] + list(sweep['models'])))
    models = {k: build(dict(main_spec, model=k, transformations=[], custom_code=''), core, comm)[0] for k in model_keys}
    gates, p0 = {}, {t.name: float(t.propertyValue(graphs)) for t in inner}

    # The validity gate looks at the mean over snapshots. A present-only model
    # reads only the target snapshot, so also check that the target snapshot
    # itself moved the requested way (Bridge Width keeps >= 1 bridge per
    # snapshot, so a 0-bridge target goes UP even under "decrease").
    target_check = None
    if spec['concept'] in ('bridge_width', 'density', 'centralization'):
        try:
            sel_t = next(t for t in inner if t.name == selected_name)
            signed = spec['delta'] if spec['direction'] == 'increase' else -spec['delta']
            before = float(sel_t.propertyValue(graphs[-1]))
            after = float(sel_t.propertyValue(sel_t.transform(graphs, signed)[-1]))
            target_check = dict(label=labels[-1], before=before, after=after,
                                against=(after - before) * signed < 0, unchanged=after == before)
        except Exception as error:
            errors.append(dict(stage='target_check', error=f'{type(error).__name__}: {str(error)[:300]}'))

    def gate(trans, delta):
        key = (trans.name, delta)
        if key not in gates:
            gates[key] = validity_gate(core, graphs, trans._inner if isinstance(trans, CachedTransformation) else trans, delta, comm)
        return gates[key]

    def run_matrix():
        rows, leakage, calls = [], [], []
        panel = leakage_panel(core, comm)
        for d in deltas:
            for index, key in enumerate(model_keys):
                counter = core.CallCountingModel(models[key])
                records = core.TgapExplainer(counter, transforms, defaultDelta=d).explainDetailed(
                    graphs, leakageMetrics=panel if index == 0 else None)
                calls.append(dict(model=key, delta=d, transformations=len(transforms), measured=counter.calls,
                                  expected=1+2*len(transforms)))
                for record in records:
                    trans = next(t for t in transforms if t.name == record['transformation'])
                    status, reason = gate(trans, record['requestedDelta'])
                    rows.append(row_from_record(record, trans, p0[trans.name], status, reason, key))
                    if index == 0:
                        leakage.append(dict(concept=trans.name, requested_delta=record['requestedDelta'],
                                            direction='increase' if record['requestedDelta'] > 0 else 'decrease',
                                            status=status, valid_for_analysis=status == 'ok',
                                            metrics={n: {k: clean(v) for k, v in m.items()} for n, m in record['leakage'].items()}))
        return dict(rows=rows, leakage=leakage, calls=calls, deltas=deltas, models=model_keys,
                    concepts=[t.name for t in transforms], semantic_rows=semantic_rows([t._inner for t in transforms]))

    matrix = stage('matrix', f'Scoring {len(model_keys)} model(s) on {len(transforms)} concept(s) at {len(deltas)} request size(s)', run_matrix)

    sel = next(t for t in transforms if t.name == selected_name)
    signed = spec['delta'] if spec['direction'] == 'increase' else -spec['delta']

    def run_temporal():
        status, reason = gate(sel, signed)
        panels = []
        for key in model_keys:
            if status != 'ok':
                panels.append(dict(model=key, valid_for_analysis=False, status=status, reason=reason, rows=[]))
                continue
            out = core.temporalAttribution(graphs, models[key], sel, signed)
            rows = []
            for r in out['rows']:
                broken = bool(sel.preservesEdgeCount and r['edges_added'] != r['edges_removed'])
                rows.append(dict(snapshot=r['snapshot_index'], label=labels[r['snapshot_index']],
                                 impact=None if broken else clean(r['impact']), valid=not broken,
                                 edges_added=r['edges_added'], edges_removed=r['edges_removed'],
                                 baseline=clean(r['baseline_prediction']), prediction=None if broken else clean(r['after_prediction'])))
            panels.append(dict(model=key, valid_for_analysis=True, status='ok', rows=rows, model_calls=out['model_calls']))
        return dict(concept=selected_name, requested_delta=signed, panels=panels, method_note=
                    'One snapshot is perturbed per row; all others are original. Per-snapshot impacts are not a decomposition of the all-snapshot impact.')

    temporal = stage('temporal', 'Measuring when the concept matters (one snapshot at a time)', run_temporal)

    def run_stability():
        # Paper RQ3 varies graph seeds and transformation seeds separately.
        variation = sweep.get('variation', 'transformation')
        seeds = [spec['seed']] + [spec['seed'] + i for i in range(1, int(sweep.get('repeats', 0)) + 1)]

        def one(s):
            g, c, _, _ = world(dict(main_spec, seed=s if variation == 'graph' else spec['seed']), core, data_root)
            model, trs = build(dict(main_spec, seed=s if variation == 'transformation' else spec['seed'],
                                    transformations=concept_ids), core, c)
            trans = next(t for t in trs if t.name == selected_name)
            records = core.TgapExplainer(model, [trans], defaultDelta=spec['delta']).explainDetailed(g)
            return g, c, trans, records

        rows, base_records = [], None
        for s in seeds:
            g, c, trans, records = one(s)
            if s == spec['seed']:
                base_records = records
            for record in records:
                status, reason = validity_gate(core, g, trans, record['requestedDelta'], c)
                rows.append(dict(row_from_record(record, trans, float(trans.propertyValue(g)), status, reason, spec['model']), seed=s))
        # Determinism: rebuild everything for the base seed and compare exactly.
        repeat = one(spec['seed'])[3]
        identical = all(a['transformed'] == b['transformed'] and a['achievedDelta'] == b['achievedDelta']
                        for a, b in zip(base_records, repeat))
        summary = []
        for direction in ('increase', 'decrease'):
            values = [r['impact'] for r in rows if r['direction'] == direction and r['valid_for_analysis'] and finite(r['impact'])]
            summary.append(dict(direction=direction, n=len(values), seeds=len(seeds),
                                mean=clean(statistics.fmean(values)) if values else None,
                                sd=clean(statistics.stdev(values)) if len(values) > 1 else None,
                                min=clean(min(values)) if values else None, max=clean(max(values)) if values else None))
        return dict(variation=variation, seeds=seeds, rows=rows, summary=summary, deterministic_repeat=identical)

    stability = stage('stability', 'Repeating the selected run across seeds', run_stability) if sweep.get('repeats', 0) else None

    def run_matched():
        from experiments.synthetic_evaluation import MATCH_DELTAS, MATCH_TOLERANCE, bestMatch, sweepConcept
        from realdata.comparability import comparabilityOf
        model = models[spec['model']]
        sweeps = {}
        for t in transforms:
            rows = sweepConcept(model, graphs, t, MATCH_DELTAS)
            sweeps[t.name] = [r for r in rows if gate(t, r['requested_delta'])[0] == 'ok']
        pairs = []
        for i, a in enumerate(transforms):
            for b in transforms[i+1:]:
                comparable, reason = comparabilityOf(a._inner, b._inner)
                for direction in ('increase', 'decrease'):
                    item = dict(first=a.name, second=b.name, direction=direction)
                    if not comparable:
                        pairs.append(dict(item, comparable=False, reason=reason))
                        continue
                    match = bestMatch(sweeps[a.name], sweeps[b.name], direction)
                    if match is None:
                        pairs.append(dict(item, comparable=False, reason='No valid non-no-op rows to match in this direction.'))
                        continue
                    ra, rb, gapv = match
                    ok = gapv <= MATCH_TOLERANCE
                    pairs.append(dict(item, comparable=ok, gap=clean(gapv),
                                      reason=None if ok else f'Closest achieved magnitudes differ by {gapv:.1%} (> {MATCH_TOLERANCE:.0%}).',
                                      first_achieved=clean(ra['achieved_delta']), second_achieved=clean(rb['achieved_delta']),
                                      first_impact=clean(ra['impact']), second_impact=clean(rb['impact']),
                                      larger=(a.name if abs(ra['impact']) > abs(rb['impact']) else b.name if abs(rb['impact']) > abs(ra['impact']) else 'tie') if ok else None))
        return dict(model=spec['model'], tolerance=MATCH_TOLERANCE, deltas=list(MATCH_DELTAS), pairs=pairs)

    matched = stage('matched', 'Searching matched achieved changes across concepts (RQ1b)', run_matched) if sweep.get('matched') else None

    def run_sizes():
        rows = []
        for size in sweep['sizes']:
            s_spec = dict(main_spec, n_per_community=size)
            g, c, _, _ = world(s_spec, core, data_root)
            model, trs = build(dict(s_spec, transformations=concept_ids), core, c)
            trans = next(t for t in trs if t.name == selected_name)
            counter = core.CallCountingModel(model)
            for record in core.TgapExplainer(counter, [trans], defaultDelta=spec['delta']).explainDetailed(g):
                status, reason = validity_gate(core, g, trans, record['requestedDelta'], c)
                edges_kept = all(a.number_of_edges() == b.number_of_edges()
                                 for a, b in zip(g, trans.transform(g, record['requestedDelta'])))
                rows.append(dict(row_from_record(record, trans, float(trans.propertyValue(g)), status, reason, spec['model']),
                                 n_per_community=size, nodes=g[-1].number_of_nodes(), edge_count_preserved=edges_kept))
        return dict(sizes=list(sweep['sizes']), rows=rows)

    family = 'synthetic' if spec['dataset'] in SYNTHETIC or spec['dataset'] == 'three_communities' else 'real'
    sizes = stage('sizes', 'Repeating across graph sizes (RQ7)', run_sizes) if sweep.get('sizes') and family == 'synthetic' else None

    def run_structure():
        import networkx as nx
        out = {}
        for direction, delta in (('increase', spec['delta']), ('decrease', -spec['delta'])):
            changed = sel.transform(graphs, delta)
            before = core.bridgeMatrix(graphs[-1], comm)
            after = core.bridgeMatrix(changed[-1], comm)
            internal = lambda g: [len(core.intraCommunityEdges(g, comm, i)) for i in range(len(comm))]
            per_snapshot = []
            for i, (a, b) in enumerate(zip(graphs, changed)):
                diff = core.graphDifference(a, b)
                per_snapshot.append(dict(snapshot=i, label=labels[i], added=len(diff['added']), removed=len(diff['removed']),
                                         edges_before=a.number_of_edges(), edges_after=b.number_of_edges()))
            out[direction] = dict(bridge_matrix=[dict(pair=list(k), before=v, after=after[k]) for k, v in before.items()],
                                  internal_before=internal(graphs[-1]), internal_after=internal(changed[-1]),
                                  per_snapshot=per_snapshot)
        # Snapshot-by-snapshot network view of the primary direction.
        union = nx.Graph()
        for g in graphs:
            union.add_nodes_from(g.nodes())
            union.add_edges_from(g.edges())
        positions = nx.spring_layout(union, seed=spec['seed'], iterations=40)
        changed = sel.transform(graphs, signed)
        snaps = []
        for i, (a, b) in enumerate(zip(graphs, changed)):
            diff = core.graphDifference(a, b)
            snaps.append(dict(label=labels[i], edges=[list(e) for e in a.edges()],
                              added=[list(e) for e in diff['added']], removed=[list(e) for e in diff['removed']]))
        view = dict(direction=spec['direction'], nodes=[dict(id=n, community=comm.communityOf(n), x=float(positions[n][0]),
                    y=float(positions[n][1])) for n in union.nodes()], snapshots=snaps,
                    community_labels=list(getattr(comm, 'labels', None) or [f'Community {i+1}' for i in range(len(comm))]))
        return dict(directions=out, view=view)

    structure = stage('structure', 'Comparing original and transformed graphs', run_structure)

    progress('charts', 'Building charts and data-grounded explanations')
    from sandbox.chart_registry import build_charts
    from sandbox.interpret import overall_conclusion, experiment_status
    context = dict(spec=spec, main=main, primary=primary, selected=selected_name, matrix=matrix, temporal=temporal,
                   stability=stability, matched=matched, sizes=sizes, structure=structure, family=family,
                   labels=list(labels), errors=errors, target_check=target_check)
    charts = build_charts(context)
    status = experiment_status(context)
    guided = dict(version=GUIDED_VERSION, spec=spec, family=family, selected_concept=selected_name, primary=primary,
                  model_info=MODEL_INFO[spec['model']], snapshot_labels=list(labels), matrix=matrix, temporal=temporal,
                  stability=stability, matched=matched, sizes=sizes, structure=structure, charts=charts,
                  experiment_status=status, stage_errors=errors, timings=timings,
                  target_check=target_check)
    guided['conclusion'] = overall_conclusion(dict(context, charts=charts, status=status))
    guided['provenance'] = provenance(spec, root, data_root, main)
    guided['seconds'] = round(time.monotonic()-started, 3)
    guided['config_hash'] = stable_hash(spec)
    return dict(main, guided=guided)


def provenance(spec, root, data_root, main):
    root = Path(root)
    fixture = Path(data_root)/'datasets'/f"{spec['dataset']}.json"
    sources = {}
    for name in ('engine.py', 'analyses.py', 'guided.py', 'chart_registry.py', 'interpret.py'):
        path = Path(__file__).with_name(name)
        if path.exists():
            sources[name] = hashlib.sha256(path.read_bytes()).hexdigest()
    core_hash = hashlib.sha256()
    for path in sorted((root/'core').rglob('*.py')):
        core_hash.update(path.read_bytes())
    import platform
    import importlib.metadata as md
    versions = {}
    for name in ('networkx', 'numpy'):
        try:
            versions[name] = md.version(name)
        except Exception:
            versions[name] = None
    return dict(generated_at=time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()), guided_version=GUIDED_VERSION,
                engine_schema=main.get('schema_version'), request_hash=main.get('request_hash'), config_hash=stable_hash(spec),
                dataset_fixture_sha256=hashlib.sha256(fixture.read_bytes()).hexdigest() if fixture.exists() else None,
                dataset_source='bundled fixture' if fixture.exists() else 'seeded generator',
                core_sha256=core_hash.hexdigest(), workbench_sha256=sources, python=platform.python_version(),
                packages=versions, seed=spec['seed'], program=main.get('program'))
