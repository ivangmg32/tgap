"""TGAP experiment engine. Uses the research library without changing its math."""
import hashlib
import json
import math
from pathlib import Path
import sys
import time

CUSTOM_TEMPLATE = '''from core import TemporalGraphTransformation
import networkx as nx

class CustomTransformation(TemporalGraphTransformation):
    name = "Remove one edge"
    deltaMode = "absolute"
    preservesEdgeCount = False

    def propertyValue(self, x):
        graphs = x if isinstance(x, list) else [x]
        return sum(g.number_of_edges() for g in graphs) / len(graphs)

    def transformGraph(self, graph, delta):
        g = graph.copy()
        edges = sorted(g.edges())
        if delta < 0 and len(edges) > 0:
            u, v = edges[0]
            g.remove_edge(u, v)
        return g
'''

TRANSFORMS = {
    'bridge_width': ('Bridge Width', 'Reroute ties between communities while keeping the edge budget.'),
    'centralization': ('Centralization', 'Move ties toward or away from the most connected actors.'),
    'density': ('Density', 'Change the number of ties inside communities.'),
    'bridge_trend': ('Bridge Trend', 'Reshape the history of bridges, keeping the present fixed.'),
    'churn': ('Churn', 'Change how much the past differs from the present.'),
}
MODELS = {
    'persistence_bridge': ('Present · bridge width', 'Reads the last snapshot only.'),
    'trend_bridge': ('Forecast · bridge width', 'Fits a line to the complete bridge history.'),
    'slope_bridge': ('Trajectory · bridge slope', 'Returns the rate of change rather than the present level.'),
    'persistence_density': ('Present · density', 'Reads the fraction of possible ties in the last snapshot.'),
    'persistence_centralization': ('Present · centralization', 'Reads hub concentration in the last snapshot.'),
    'trend_clustering': ('Forecast · clustering', 'Extrapolates how interconnected neighbors are.'),
}
SYNTHETIC = {
    'stable': ('Stable ecosystem', 'Two communities, a steady bridge, mild turnover.'),
    'decaying-bridge': ('Bridge decay', 'An exact, shrinking bridge for comparing present and history.'),
    'growing-bridge': ('Bridge recovery', 'Cross-community ties grow through time.'),
    'high-churn': ('High turnover', 'A noisier history with the same bridge width.'),
    'three_communities': ('Three communities', 'Explore a network with three separate community boundaries.'),
}
EXAMPLES = [
    dict(id='first', title='Your first explanation', subtitle='Why does one extra bridge matter?', minutes=3,
         dataset='stable', model='persistence_bridge', transformations=['bridge_width','centralization','density'], delta=0.1),
    dict(id='history', title='Same present, different history', subtitle='See what a forecast reads that a present-only model cannot.', minutes=4,
         dataset='decaying-bridge', model='trend_bridge', transformations=['bridge_width','bridge_trend','churn'], delta=0.1),
    dict(id='turnover', title='Turnover and clustering', subtitle='Probe an ecosystem with changing internal ties.', minutes=3,
         dataset='high-churn', model='trend_clustering', transformations=['centralization','density','churn'], delta=0.25),
    dict(id='communities', title='Beyond two communities', subtitle='Inspect bridges across a three-community ecosystem.', minutes=3,
         dataset='three_communities', model='persistence_bridge', transformations=['bridge_width','density'], delta=0.25),
    dict(id='custom', title='Write a transformer', subtitle='Start with one edge, then define your own graph concept.', minutes=4,
         dataset='stable', model='persistence_density', transformations=['density'], delta=0.1, custom_code=CUSTOM_TEMPLATE),
    dict(id='limits', title='When a perturbation cannot be trusted', subtitle='Inspect validity gates on a real co-voting network.', minutes=3,
         dataset='decentraland', model='trend_bridge', transformations=['bridge_width','bridge_trend'], delta=0.25),
]


def load_core(root):
    root = Path(root).resolve()
    if not (root / 'core' / 'TemporalGraphExplainer.py').exists():
        raise ValueError('TGAP source path is missing. Check config.json.')
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    import core
    return core


def catalogue(data_root):
    datasets = [dict(id=k, name=n, description=d, family='synthetic', available=True) for k,(n,d) in SYNTHETIC.items()]
    for p in sorted((Path(data_root) / 'datasets').glob('*.json')):
        fixture = json.loads(p.read_text(encoding='utf-8'))
        meta = fixture['meta']
        datasets.append(dict(id=p.stem, name=meta.get('dataset',p.stem).replace('_',' ').replace('-',' ').title(),
                             description=meta.get('graph_edges_are',meta.get('description','Observed temporal interactions.')),
                             family='real', available=True, nodes=len(fixture['nodes']), snapshots=len(fixture['snapshots'])))
    return dict(datasets=datasets, models=[dict(id=k,name=n,description=d) for k,(n,d) in MODELS.items()],
                transformations=[dict(id=k,name=n,description=d) for k,(n,d) in TRANSFORMS.items()],
                examples=EXAMPLES, custom_template=CUSTOM_TEMPLATE)


def world(spec, core, data_root):
    key = spec['dataset']
    if key == 'three_communities':
        graphs, comm = core.makeNCommunityTemporalGraph(nSnapshots=6, nCommunities=3,
            nPerCommunity=8,pIntra=0.45,bridgeWidths={(0,1):8,(0,2):5,(1,2):3},seed=spec['seed'])
        return graphs, comm, [f'Window {i+1}' for i in range(len(graphs))], {'dataset':key,'analysis_mode':'synthetic','ground_truth_available':True}
    if key in SYNTHETIC:
        graphs, comm, info = core.makeScenario(key,nSnapshots=6,nPerCommunity=10,seed=spec['seed'])
        return graphs, core.asPartition(comm), [f'Window {i+1}' for i in range(len(graphs))], {'dataset':key,'analysis_mode':'synthetic',**info}
    path = Path(data_root) / 'datasets' / f'{key}.json'
    if not path.is_file() or path.parent.resolve() != (Path(data_root)/'datasets').resolve():
        raise ValueError('Dataset unavailable. Choose a bundled example.')
    import networkx as nx
    item = json.loads(path.read_text(encoding='utf-8'))
    graphs = []
    for edges in item['snapshots']:
        graph = nx.Graph()
        graph.add_nodes_from(item['nodes'])
        graph.add_edges_from(edges)
        graphs.append(graph)
    return graphs, core.Partition(item['communities'],labels=item['community_labels']), item['labels'], item['meta']


def build(spec, core, comm):
    metric = core.BridgeWidthMetric(comm)
    models = {'persistence_bridge':core.PersistenceTemporalModel(metric),
              'trend_bridge':core.TrendTemporalModel(metric), 'slope_bridge':core.SlopeModel(metric),
              'persistence_density':core.PersistenceTemporalModel(core.DensityMetric()),
              'persistence_centralization':core.PersistenceTemporalModel(core.DegreeCentralizationMetric()),
              'trend_clustering':core.TrendTemporalModel(core.ClusteringMetric())}
    classes = {'bridge_width':core.BridgeWidthTransformation,'centralization':core.CentralizationTransformation,
               'density':core.DensityTransformation,'bridge_trend':core.BridgeTrendTransformation,'churn':core.ChurnTransformation}
    transforms = [classes[k](comm,seed=spec['seed']) for k in spec['transformations']]
    if spec.get('custom_code','').strip():
        from sandbox.restricted import Interpreter, CodeError
        raw = Interpreter(spec['custom_code'],core.TemporalGraphTransformation).instance
        class SafeCustom(core.TemporalGraphTransformation):
            name = raw.name
            deltaMode = raw.deltaMode
            preservesEdgeCount = raw.preservesEdgeCount

            def propertyValue(self, x):
                copies = [g.copy() for g in x] if isinstance(x,list) else x.copy()
                return raw.propertyValue(copies)

            def transform(self, snapshots, delta):
                fingerprints = [fingerprint(g) for g in snapshots]
                originals = [g.copy() for g in snapshots]
                changed = raw.transform(originals, delta)
                if [fingerprint(g) for g in originals] != fingerprints:
                    raise CodeError('Do not mutate the input. Start with graph.copy().')
                if not isinstance(changed,list) or len(changed) != len(snapshots):
                    raise CodeError('Return the same number of graph snapshots as the input.')
                for before, after in zip(snapshots,changed):
                    import networkx as nx
                    if not isinstance(after,nx.Graph) or set(before.nodes()) != set(after.nodes()) or nx.number_of_selfloops(after):
                        raise CodeError('Preserve the node set and return simple graphs without self-loops.')
                return changed
        if raw.name in [t.name for t in transforms]:
            raise CodeError('Give your custom concept a distinct name.')
        transforms.append(SafeCustom())
    return models[spec['model']], transforms


def fingerprint(g):
    return (tuple(sorted(g.nodes())), tuple(sorted(tuple(sorted(e)) for e in g.edges())))


def generated_program(spec):
    names = {'bridge_width':'BridgeWidthTransformation','centralization':'CentralizationTransformation',
             'density':'DensityTransformation','bridge_trend':'BridgeTrendTransformation','churn':'ChurnTransformation'}
    model = {'persistence_bridge':'PersistenceTemporalModel(BridgeWidthMetric(communities))',
             'trend_bridge':'TrendTemporalModel(BridgeWidthMetric(communities))',
             'slope_bridge':'SlopeModel(BridgeWidthMetric(communities))',
             'persistence_density':'PersistenceTemporalModel(DensityMetric())',
             'persistence_centralization':'PersistenceTemporalModel(DegreeCentralizationMetric())',
             'trend_clustering':'TrendTemporalModel(ClusteringMetric())'}[spec['model']]
    imports = ['TgapExplainer','PersistenceTemporalModel','TrendTemporalModel','SlopeModel','BridgeWidthMetric',
               'DensityMetric','DegreeCentralizationMetric','ClusteringMetric','makeScenario','makeNCommunityTemporalGraph',
               'edgeCountFeasibility','bridgeTrendDirection'] + [names[k] for k in spec['transformations']]
    code = '# Generated by TGAP Laboratory. Run from a TGAP checkout.\nfrom pprint import pprint\nfrom core import (\n    '+',\n    '.join(imports)+'\n)\n\n'
    if spec.get('custom_code','').strip():
        code += spec['custom_code']+'\n\n'
    if spec['dataset'] == 'three_communities':
        code += f"snapshots, communities = makeNCommunityTemporalGraph(nSnapshots=6, nCommunities=3, nPerCommunity=8, pIntra=0.45, bridgeWidths={{(0,1):8,(0,2):5,(1,2):3}}, seed={spec['seed']})\n"
    elif spec['dataset'] in SYNTHETIC:
        code += f"snapshots, communities, info = makeScenario({spec['dataset']!r}, nSnapshots=6, nPerCommunity=10, seed={spec['seed']})\n"
    else:
        adapter = spec['dataset'] if spec['dataset'] in ('decentraland','tgbl_wiki') else 'edgelist'
        arg = '' if adapter != 'edgelist' else repr(spec['dataset'])
        code += f'from realdata.adapters import {adapter}\nprepared = {adapter}.prepare({arg})\nsnapshots, communities = prepared.snapshots, prepared.communities\n'
    code += f'model = {model}\ntransformations = [\n'
    for key in spec['transformations']:
        code += f"    {names[key]}(communities, seed={spec['seed']}),\n"
    if spec.get('custom_code','').strip():
        import ast
        cls = next(n.name for n in ast.parse(spec['custom_code']).body if isinstance(n,ast.ClassDef))
        code += f'    {cls}(),\n'
    code += f"]\nexplainer = TgapExplainer(model, transformations, defaultDelta={spec['delta']})\nrecords = explainer.explainDetailed(snapshots)\n"
    code += '''for record in records:
    trans = next(t for t in transformations if t.name == record["transformation"])
    gate = edgeCountFeasibility(snapshots, trans, record["requestedDelta"], communities)
    valid = gate["feasible"]
    if isinstance(trans, BridgeTrendTransformation):
        valid = valid and bridgeTrendDirection(snapshots, trans, record["requestedDelta"])["valid_for_analysis"]
    record["valid_for_analysis"] = valid
    if not valid:
        record["impact"] = None
pprint(records)
'''
    if 'BridgeTrendTransformation' not in imports:
        code = code.replace('    TgapExplainer,','    BridgeTrendTransformation,\n    TgapExplainer,')
    return code


def execute(spec, root, data_root):
    started = time.monotonic()
    core = load_core(root)
    graphs, comm, labels, meta = world(spec,core,data_root)
    model, transforms = build(spec,core,comm)
    counter = core.CallCountingModel(model)
    captured = {}
    class VisualExplainer(core.TgapExplainer):
        def _applyTransformation(self, x, trans, delta):
            changed = super()._applyTransformation(x, trans, delta)
            captured[(trans.name, delta)] = [g.copy() for g in changed]
            return changed
    explainer = VisualExplainer(counter, transforms, defaultDelta=spec['delta'])
    detailed = explainer.explainDetailed(graphs)
    rows = []
    for record in detailed:
        trans = next(t for t in transforms if t.name == record['transformation'])
        delta = record['requestedDelta']
        gate = core.edgeCountFeasibility(graphs,trans,delta,comm)
        status = 'ok' if gate['feasible'] else 'edge_count_infeasible'
        reason = gate.get('reason')
        if status == 'ok' and isinstance(trans,core.BridgeTrendTransformation):
            trend = core.bridgeTrendDirection(graphs,trans,delta)
            status = trend['status']
            if status != 'ok':
                reason = {'saturated':'The width-one floor distorted part of the intended history.',
                          'wrong_direction':'The achieved trend moved against the requested direction.',
                          'no_property_change':'The trend did not change.'}[status]
        valid = status == 'ok'
        rows.append(dict(concept=trans.name,direction='increase' if delta>0 else 'decrease',
                         requested_delta=delta,achieved_delta=record['achievedDelta'] if valid else None,
                         delta_mode=('absolute' if record['deltaMode']=='relative' and trans.propertyValue(graphs)==0 else record['deltaMode']),
                         requested_delta_mode=record['deltaMode'],property_baseline=trans.propertyValue(graphs),baseline=record['baseline'],
                         prediction=record['transformed'] if valid else None,
                         prediction_change=record['transformed']-record['baseline'] if valid else None,
                         impact=record['impact'] if valid else None,noop=record['noop'],status=status,
                         valid_for_analysis=valid,reason=reason,normalizer=record['normalizer']))
    def history(sequence):
        return [dict(index=i,label=labels[i],edges=g.number_of_edges(),
                       bridge=core.BridgeWidthMetric(comm).measure(g),density=core.DensityMetric().measure(g),
                       centralization=core.DegreeCentralizationMetric().measure(g)) for i,g in enumerate(sequence)]
    trajectory = history(graphs)
    comparisons = []
    for row in rows:
        changed = captured[(row['concept'], row['requested_delta'])]
        difference = core.graphDifference(graphs[-1], changed[-1])
        comparisons.append(dict(concept=row['concept'],direction=row['direction'],
                                valid_for_analysis=row['valid_for_analysis'],status=row['status'],
                                trajectory=history(changed),edges=list(changed[-1].edges()),
                                added=difference['added'],removed=difference['removed']))
    selected = transforms[0]
    changed = captured[(selected.name,spec['delta'])]
    difference = core.graphDifference(graphs[-1],changed[-1])
    import networkx as nx
    positions = nx.spring_layout(graphs[-1],seed=spec['seed'],iterations=35)
    nodes = [dict(id=n,community=comm.communityOf(n),x=float(positions[n][0]),y=float(positions[n][1]),
                  degree=graphs[-1].degree(n)) for n in graphs[-1].nodes()]
    from sandbox.analyses import detailed_analyses
    analyses=detailed_analyses(core,graphs,comm,model,transforms,rows,captured,spec)
    result = dict(schema_version=3,spec=spec,baseline=detailed[0]['baseline'],rows=rows,trajectory=trajectory,comparisons=comparisons,analyses=analyses,
                  graph=dict(nodes=nodes,edges=list(graphs[-1].edges()),added=difference['added'],removed=difference['removed'],
                             transformation=selected.name),meta=meta,
                  summary=dict(nodes=graphs[-1].number_of_nodes(),snapshots=len(graphs),communities=len(comm),
                               model_calls=counter.calls,figure_model_calls=analyses['model_calls'],total_model_calls=counter.calls+analyses['model_calls'],valid_rows=sum(r['valid_for_analysis'] for r in rows),
                               total_rows=len(rows),sparsity=core.conceptSparsity([dict(impact=r['impact'],noop=r['noop'],
                               valid_for_analysis=r['valid_for_analysis']) for r in rows])),
                  program=generated_program(spec),seconds=round(time.monotonic()-started,3),
                  notes=['Impacts describe model sensitivity, not real-world causation.',
                         'Compare concepts only when their perturbation units and the model output scale are compatible.',
                         'Network comparisons show the last snapshot with fixed positions; history comparisons show all snapshots.',
                         'Visual comparisons are captured from the exact transformations evaluated by the explainer.'])
    result['request_hash'] = hashlib.sha256(json.dumps(spec,sort_keys=True).encode()).hexdigest()
    return result
