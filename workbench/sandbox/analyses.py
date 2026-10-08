"""Measured, bounded inputs for publication-style figures for a live run."""
import time


class AnalysisLimit(Exception):
    pass


def detailed_analyses(core,graphs,communities,model,transforms,rows,captured,spec):
    started=time.monotonic()
    class BoundedModel:
        calls=0
        def predict(self,x):
            if self.calls>=128 or time.monotonic()-started>10:
                raise AnalysisLimit('Detailed-figure budget reached; completed measurements remain available.')
            self.calls+=1
            return float(model.predict(x))
    measured=BoundedModel()
    output=dict(method='Measured perturbations and occlusions; no interpolated attribution.',
                nodes=None,edges=None,temporal=[],edge_time=[],sweep=[],unavailable=[],
                budgets=dict(max_model_calls=128,max_seconds=10,node_limit=12,edge_limit=16,
                             edge_time_edge_limit=4,snapshot_limit=8),
                trained_seed_stability=dict(available=False,reason='The selected web model is not a trained multi-seed TGN experiment.'))
    def attempt(name,operation):
        try:return operation()
        except Exception as error:
            output['unavailable'].append(dict(analysis=name,reason=str(error)[:200]))
            return None
    output['nodes']=attempt('node occlusion',lambda:core.nodeAttribution(graphs,measured,topK=12,seed=spec['seed']))
    output['edges']=attempt('edge occlusion',lambda:core.edgeAttribution(graphs,measured,communities,topK=16,seed=spec['seed']))
    count=len(graphs)
    indices=sorted({round(i*(count-1)/max(1,min(count,8)-1)) for i in range(min(count,8))})
    baseline=rows[0]['baseline']
    output['snapshot_indices']=indices
    output['snapshots_total']=count
    # Use the exact graphs already tested, changing one snapshot at a time.
    for trans in transforms[:3]:
        row=next(r for r in rows if r['concept']==trans.name and r['direction']=='increase')
        panel=dict(concept=trans.name,requested_delta=spec['delta'],rows=[],
                   valid_for_analysis=row['valid_for_analysis'],status=row['status'])
        output['temporal'].append(panel)
        if not row['valid_for_analysis']:continue
        changed=captured[(trans.name,spec['delta'])]
        for index in indices:
            if trans.preservesEdgeCount and graphs[index].number_of_edges()!=changed[index].number_of_edges():
                panel['rows'].append(dict(snapshot=index,valid=False,impact=None,reason='Edge count changed.'))
                continue
            hybrid=[changed[i] if i==index else graph for i,graph in enumerate(graphs)]
            value=attempt('temporal '+trans.name,lambda:measured.predict(hybrid))
            if value is None:break
            panel['rows'].append(dict(snapshot=index,valid=True,baseline=baseline,prediction=value,impact=value-baseline))
    # Keep the same four selected edges across time; absent edges are explicit no-ops.
    selected_edges=[(r['u'],r['v']) for r in (output['edges'] or {}).get('rows',[])[:4]]
    output['edge_time_selection']=dict(edges=selected_edges,selection='Largest absolute measured whole-sequence edge occlusion among the evaluated subset.',
                                       evaluated_pairs=0,possible_pairs=len(selected_edges)*count)
    for edge in selected_edges:
        for index in indices:
            graph=graphs[index].copy()
            present=graph.has_edge(*edge)
            if present:graph.remove_edge(*edge)
            hybrid=[graph if i==index else g for i,g in enumerate(graphs)]
            value=attempt('edge-time occlusion',lambda:measured.predict(hybrid)) if present else baseline
            if value is None:break
            output['edge_time'].append(dict(u=edge[0],v=edge[1],snapshot=index,present=present,
                                           baseline=baseline,prediction=value,impact=value-baseline))
    output['edge_time_selection']['evaluated_pairs']=len(output['edge_time'])
    # Distributions describe tested delta amounts, not repeated trials or users.
    amounts=sorted({max(.02,spec['delta']/2),spec['delta'],min(.5,spec['delta']*2)})
    output['sweep_amounts']=amounts
    for trans in transforms:
        for amount in amounts:
            if amount==spec['delta']:
                output['sweep'].extend({**row,'sweep_delta':amount} for row in rows if row['concept']==trans.name)
                continue
            def sweep():
                detail=core.TgapExplainer(measured,[trans],defaultDelta=amount).explainDetailed(graphs)
                samples=[]
                for record in detail:
                    delta=record['requestedDelta']
                    gate=core.edgeCountFeasibility(graphs,trans,delta,communities)
                    status='ok' if gate['feasible'] else 'edge_count_infeasible'
                    if status=='ok' and isinstance(trans,core.BridgeTrendTransformation):
                        status=core.bridgeTrendDirection(graphs,trans,delta)['status']
                    valid=status=='ok'
                    samples.append(dict(concept=trans.name,direction='increase' if delta>0 else 'decrease',
                                        requested_delta=delta,sweep_delta=amount,status=status,valid_for_analysis=valid,
                                        baseline=record['baseline'],prediction=record['transformed'] if valid else None,
                                        impact=record['impact'] if valid else None,
                                        prediction_change=record['transformed']-record['baseline'] if valid else None,
                                        achieved_delta=record['achievedDelta'] if valid else None,delta_mode=('absolute' if record['deltaMode']=='relative' and trans.propertyValue(graphs)==0 else record['deltaMode']),
                                        requested_delta_mode=record['deltaMode']))
                return samples
            samples=attempt('delta sweep '+trans.name,sweep)
            if samples:output['sweep'].extend(samples)
    output['model_calls']=measured.calls
    output['seconds']=round(time.monotonic()-started,3)
    output['unavailable']=list({(r['analysis'],r['reason']):r for r in output['unavailable']}.values())
    return output
