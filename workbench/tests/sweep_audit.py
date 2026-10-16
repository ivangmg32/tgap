"""Independent verification of every completed live sweep sample."""
import itertools,json,sys,time
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from scientific_audit import SOURCE,DATA,ROOT,predict,prop,close
from sandbox.engine import execute,catalogue,MODELS,TRANSFORMS
from sandbox.analyses import detailed_analyses
report=dict(cases=0,samples=0,failures=[]);started=time.time()
for d,m in itertools.product([d['id'] for d in catalogue(DATA)['datasets']],MODELS):
    try:
        store={}
        def measure(core,gs,c,model,ts,rows,changed,spec):
            store.update(gs=gs,c=c,ts=ts)
            return detailed_analyses(core,gs,c,model,ts,rows,changed,spec)
        spec=dict(dataset=d,model=m,transformations=list(TRANSFORMS),delta=.1,seed=42,custom_code='')
        with patch('sandbox.analyses.detailed_analyses',side_effect=measure):r=execute(spec,SOURCE,DATA)
        gs,c=store['gs'],store['c'];base=predict(gs,c,m)
        for row in r['analyses']['sweep']:
            if not row['valid_for_analysis']:continue
            trans=next(t for t in store['ts'] if t.name==row['concept'])
            after=trans.transform(gs,row['requested_delta']);value=predict(after,c,m)
            close(row['prediction'],value,'sweep independent model')
            p0=prop(gs,c,row['concept']);pt=prop(after,c,row['concept'])
            achieved=(pt-p0)/abs(p0) if row['delta_mode']=='relative' else pt-p0
            close(row['achieved_delta'],achieved,'sweep independent property')
            denominator=abs(achieved) if row.get('normalizer','achieved' if achieved else 'requested')=='achieved' else abs(row['requested_delta'])
            close(row['impact'],(value-base)/denominator if denominator else 0,'sweep independent impact')
            report['samples']+=1
    except Exception as error:report['failures'].append(dict(dataset=d,model=m,error=repr(error)))
    report['cases']+=1;report['seconds']=round(time.time()-started,3)
    (ROOT/'verification'/'sweep-audit.json').write_text(json.dumps(report,indent=2))
    if report['cases']%12==0:print(json.dumps(report),flush=True)
print(json.dumps(report),flush=True)
sys.exit(bool(report['failures']))
