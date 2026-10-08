"""Independent numerical audit of actual engine results; writes reproducible evidence."""
import itertools,json,math,sys,time
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from sandbox.engine import execute,catalogue,load_core,MODELS,TRANSFORMS
from sandbox.analyses import detailed_analyses
SOURCE=ROOT.parent if (ROOT.parent/'core').is_dir() else ROOT.parent/'tgap';DATA=ROOT/'data';OUT=ROOT/'verification'/'scientific-audit.json'
checks=0

def close(a,b,label):
    global checks
    checks+=1
    assert a is not None and math.isfinite(a) and math.isclose(a,b,rel_tol=2e-9,abs_tol=2e-10),(label,a,b)

def slope(y):
    n=len(y);mean=(n-1)/2;ym=sum(y)/n
    return sum((i-mean)*(v-ym) for i,v in enumerate(y))/sum((i-mean)**2 for i in range(n)) if n>1 else 0.

def metric(g,comm,kind):
    n=len(g);edges=list(g.edges())
    if kind=='bridge':return sum(comm.communityOf(u)!=comm.communityOf(v) for u,v in edges)
    if kind=='density':return 2*len(edges)/(n*(n-1)) if n>1 else 0.
    if kind=='centralization':
        ds=[len(list(g.neighbors(v))) for v in g];m=max(ds,default=0)
        return sum(m-d for d in ds)/((n-1)*(n-2)) if n>2 else 0.
    values=[]
    for v in g:
        neighbors=list(g.neighbors(v));d=len(neighbors)
        pairs=sum(g.has_edge(u,w) for u,w in itertools.combinations(neighbors,2))
        values.append(2*pairs/(d*(d-1)) if d>1 else 0.)
    return sum(values)/n if n else 0.

def predict(gs,comm,model):
    kind={'persistence_bridge':'bridge','trend_bridge':'bridge','slope_bridge':'bridge','persistence_density':'density','persistence_centralization':'centralization','trend_clustering':'clustering'}[model]
    y=[metric(g,comm,kind) for g in gs]
    if model.startswith('persistence'):return y[-1]
    if model.startswith('slope'):return slope(y)
    return sum(y)/len(y)+slope(y)*(len(y)-(len(y)-1)/2)

def prop(gs,c,name):
    if name=='Bridge Trend':return slope([metric(g,c,'bridge') for g in gs])
    if name=='Churn':
        def intra(g):return {frozenset((u,v)) for u,v in g.edges() if c.communityOf(u)==c.communityOf(v)}
        last=intra(gs[-1]);dist=[]
        for g in gs[:-1]:
            e=intra(g);dist.append(len(e^last)/len(e|last) if e|last else 0.)
        return sum(dist)/len(dist)
    if name=='Density':return sum(g.number_of_edges() for g in gs)/len(gs)
    kind={'Bridge Width':'bridge','Centralization':'centralization'}[name]
    return sum(metric(g,c,kind) for g in gs)/len(gs)

def audit(spec):
    captured={}
    def measure(core,gs,c,m,ts,rows,changed,configuration):
        captured.update(gs=gs,c=c,changed=changed)
        return detailed_analyses(core,gs,c,m,ts,rows,changed,configuration)
    with patch('sandbox.analyses.detailed_analyses',side_effect=measure):r=execute(spec,SOURCE,DATA)
    gs,c,changed=captured['gs'],captured['c'],captured['changed'];model=spec['model'];base=predict(gs,c,model)
    close(r['baseline'],base,'baseline');assert r['summary']['model_calls']==11
    invalid=noop=0
    for row,comparison in zip(r['rows'],r['comparisons']):
        after=changed[(row['concept'],row['requested_delta'])]
        for g,h,t in zip(gs,after,comparison['trajectory']):
            assert set(g)==set(h) and not any(u==v for u,v in h.edges())
            for kind in ('bridge','density','centralization'):close(t[kind],metric(h,c,kind),'trajectory '+kind)
        if row['concept'] in ('Bridge Trend','Churn'):assert set(gs[-1].edges())==set(after[-1].edges())
        if not row['valid_for_analysis']:
            invalid+=1
            assert all(row[k] is None for k in ('prediction','prediction_change','impact','achieved_delta'))
            assert row['status']!='ok';continue
        value=predict(after,c,model);close(row['prediction'],value,'prediction');close(row['prediction_change'],value-base,'raw difference')
        p0=prop(gs,c,row['concept']);pt=prop(after,c,row['concept'])
        mode='absolute' if row['concept']=='Bridge Trend' or p0==0 else 'relative'
        achieved=pt-p0 if mode=='absolute' else (pt-p0)/abs(p0)
        close(row['achieved_delta'],achieved,'achieved');assert row['delta_mode']==mode
        denom=abs(achieved) if row['normalizer']=='achieved' else abs(row['requested_delta'])
        close(row['impact'],(value-base)/denom if denom else 0,'normalized impact')
        if row['noop']:noop+=1;close(value,base,'noop output')
        if row['concept']!='Density':assert all(g.number_of_edges()==h.number_of_edges() for g,h in zip(gs,after))
        if row['concept'] in ('Centralization','Density','Churn'):
            for g,h in zip(gs,after):close(metric(g,c,'bridge'),metric(h,c,'bridge'),'bridge anchor')
    analyses=r['analyses']
    for row in (analyses['nodes'] or {}).get('rows',[]):
        after=[g.copy() for g in gs]
        for g in after:g.remove_edges_from(list(g.edges(row['node'])))
        close(row['impact'],predict(after,c,model)-base,'node occlusion')
    for row in (analyses['edges'] or {}).get('rows',[]):
        after=[g.copy() for g in gs]
        for g in after:
            if g.has_edge(row['u'],row['v']):g.remove_edge(row['u'],row['v'])
        close(row['impact'],predict(after,c,model)-base,'edge occlusion')
    for panel in analyses['temporal']:
        if not panel['valid_for_analysis']:continue
        alt=changed[(panel['concept'],spec['delta'])]
        for row in panel['rows']:
            if row['valid']:
                hybrid=[alt[i] if i==row['snapshot'] else g for i,g in enumerate(gs)]
                close(row['impact'],predict(hybrid,c,model)-base,'one snapshot response')
    for row in analyses['edge_time']:
        after=[g.copy() for g in gs];g=after[row['snapshot']]
        if g.has_edge(row['u'],row['v']):g.remove_edge(row['u'],row['v'])
        close(row['impact'],predict(after,c,model)-base,'edge time response')
    for row in analyses['sweep']:
        if not row['valid_for_analysis']:assert row['impact'] is None
        else:close(row['prediction_change'],row['prediction']-row['baseline'],'sweep difference')
    json.dumps(r,allow_nan=False)
    return dict(spec=spec,seconds=r['seconds'],invalid=invalid,noops=noop,figure_calls=analyses['model_calls'],unavailable=analyses['unavailable'])

if __name__=='__main__':
    started=time.time();report=dict(started=started,runs=[],failures=[])
    datasets=[d['id'] for d in catalogue(DATA)['datasets']]
    cases=[dict(dataset=d,model=m,transformations=list(TRANSFORMS),delta=a,seed=42,custom_code='') for d,m,a in itertools.product(datasets,MODELS,(.02,.1,.5))]
    cases += [dict(dataset=d,model=m,transformations=list(TRANSFORMS),delta=.25,seed=s,custom_code='') for d,m,s in itertools.product(('stable','decaying-bridge','three_communities'),MODELS,(0,17))]
    for i,spec in enumerate(cases):
        try:report['runs'].append(audit(spec))
        except Exception as error:report['failures'].append(dict(spec=spec,error=repr(error)))
        report.update(checks=checks,completed=i+1,total=len(cases),seconds=round(time.time()-started,3))
        OUT.parent.mkdir(exist_ok=True);OUT.write_text(json.dumps(report,indent=2))
        if (i+1)%12==0:print(f'{i+1}/{len(cases)} cases; {checks} numerical checks; {len(report["failures"])} failures',flush=True)
    print(json.dumps({k:v for k,v in report.items() if k not in ('runs','failures')}),flush=True)
    sys.exit(bool(report['failures']))
