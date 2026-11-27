"""Application-only measurements; existing experiments and core stay unchanged."""
import hashlib
import json
import platform
import time
from datetime import datetime, timezone
from pathlib import Path

import networkx as nx

from sandbox.engine import build, execute, load_core, world


def application_measurements(spec, root, data_root, result):
    core = load_core(root)
    graphs, comm, labels, _ = world(spec, core, data_root)
    model, transforms = build(spec, core, comm)
    metrics = dict(bridge=core.BridgeWidthMetric(comm), density=core.DensityMetric(),
                   centralization=core.DegreeCentralizationMetric(), clustering=core.ClusteringMetric())

    def measures(g):
        return {**{k: float(m.measure(g)) for k, m in metrics.items()},
                'edges': g.number_of_edges(), 'active_nodes': sum(d > 0 for _, d in g.degree()),
                'largest_component': max(map(len, nx.connected_components(g)), default=0) / max(1, len(g))}

    history = [dict(index=i, label=labels[i], **measures(g)) for i, g in enumerate(graphs)]
    target = {'persistence_bridge':'bridge', 'trend_bridge':'bridge',
              'persistence_density':'density', 'persistence_centralization':'centralization',
              'trend_clustering':'clustering'}.get(spec['model'])
    # Prefix-only evaluation: no future graph is passed into predict().
    backtest = []
    if target:
        for i in range(2, len(graphs)):
            backtest.append(dict(index=i, label=labels[i], observed=history[i][target],
                                 prediction=float(model.predict(graphs[:i])),
                                 persistence=history[i-1][target]))
    forecast = dict(available=target is not None, target=target, rows=backtest,
                    next_prediction=float(model.predict(graphs)) if target else None,
                    mae=sum(abs(r['prediction']-r['observed']) for r in backtest)/len(backtest) if backtest else None,
                    persistence_mae=sum(abs(r['persistence']-r['observed']) for r in backtest)/len(backtest) if backtest else None,
                    uncertainty_available=False,
                    reason=None if target else 'The slope model reports a historical rate, not a next-period level.')
    # A stable, bounded visual sample; all metrics above use the full graph.
    visible = sorted(graphs[-1].nodes(), key=str)[:100]
    visible_set = set(visible)
    union = nx.Graph()
    union.add_nodes_from(visible)
    for g in graphs:
        union.add_edges_from((u,v) for u,v in g.edges() if u in visible_set and v in visible_set)
    positions = nx.spring_layout(union, seed=spec['seed'], iterations=35)

    def edge_set(g):
        return {tuple(sorted((u,v), key=str)) for u,v in g.edges()}

    def visual_edges(edges):
        eligible = sorted((e for e in edges if set(e) <= visible_set), key=lambda e: tuple(map(str,e)))
        return dict(edges=eligible[:2000], total=len(edges), shown=min(2000,len(eligible)))

    windows = []
    previous = set()
    for i,g in enumerate(graphs):
        edges = edge_set(g)
        windows.append(dict(index=i, label=labels[i], **visual_edges(edges),
                            added=visual_edges(edges-previous), removed=visual_edges(previous-edges)))
        previous = edges
    scenarios = []
    for key, trans in zip(spec['transformations'], transforms):
        for direction, sign in [('increase',1), ('decrease',-1)]:
            row = next(r for r in result['rows'] if r['concept']==trans.name and r['direction']==direction)
            # Use a new transformation instance, with exactly the original seed.
            _, fresh = build({**spec, 'transformations':[key]},core,comm)
            changed = fresh[0].transform([g.copy() for g in graphs], sign*spec['delta'])
            before, after = measures(graphs[-1]), measures(changed[-1])
            diffs=[]
            for i,(old,new) in enumerate(zip(graphs,changed)):
                a,b=edge_set(old),edge_set(new)
                diffs.append(dict(index=i,added=visual_edges(b-a),removed=visual_edges(a-b), **visual_edges(b)))
            scenarios.append(dict(concept=trans.name,direction=direction,valid=row['valid_for_analysis'],
                                  status=row['status'],noop=row['noop'],before=before,after=after,windows=diffs))
    # Structural stress test: disable ties of top-degree nodes without changing
    # the cohort. Ranking uses only the observed history's final snapshot.
    ranked=sorted(graphs[-1].nodes(),key=lambda n:(-graphs[-1].degree(n),str(n)))
    robustness=[]
    for fraction in (0,.05,.10,.20):
        count=0 if fraction==0 else max(1,round(len(ranked)*fraction))
        removed=set(ranked[:count])
        changed=[g.copy() for g in graphs]
        for g in changed:
            g.remove_edges_from([(u,v) for u,v in g.edges() if u in removed or v in removed])
        robustness.append(dict(requested_fraction=fraction,disabled_nodes=count,
                               actual_fraction=count/max(1,len(ranked)),prediction=float(model.predict(changed)),
                               **measures(changed[-1])))
    fixtures=Path(data_root)/'datasets'/f"{spec['dataset']}.json"
    return dict(version=1,model_calls=len(backtest)+(1 if target else 0)+len(robustness),history=history,forecast=forecast,scenarios=scenarios,robustness=robustness,
                network=dict(nodes=[dict(id=n,community=comm.communityOf(n),x=float(positions[n][0]),y=float(positions[n][1])) for n in visible],
                             windows=windows,total_nodes=len(graphs[-1]),node_limit=100,edge_limit=2000),
                provenance=dict(created_utc=datetime.now(timezone.utc).isoformat(),python=platform.python_version(),networkx=nx.__version__,
                                fixture_sha256=hashlib.sha256(fixtures.read_bytes()).hexdigest() if fixtures.exists() else None,
                                module_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()),
                notes=['Graph changes measure model sensitivity, not causal effects.',
                       'Backtests use only preceding snapshots; the fixed cohort comes from the existing dataset adapter.',
                       'Active nodes mean nodes with at least one edge, not all voters or retention.',
                       'Stress tests disable ties in every snapshot; they are not validated governance interventions.',
                       'Visual sampling never changes the metrics computed on the complete graph.'])


def execute_applications(spec, root, data_root):
    started=time.monotonic()
    result=execute(spec,root,data_root)
    result['applications']=application_measurements(spec,root,data_root,result)
    result['summary']['application_model_calls']=result['applications']['model_calls']
    result['summary']['total_model_calls']+=result['applications']['model_calls']
    result['seconds']=round(time.monotonic()-started,3)
    # Catch any nonfinite measurement before it reaches a saved job.
    json.dumps(result,allow_nan=False)
    return result
