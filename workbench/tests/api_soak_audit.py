"""API experiment soak against the disposable loopback CAPTCHA fixture only."""
import concurrent.futures,itertools,json,statistics,time,uuid
from pathlib import Path
import httpx
URL='http://127.0.0.1:8093';ROOT=Path(__file__).resolve().parents[1]
report=dict(runs=[],failures=[]);started=time.time()
clients=[]
for i in range(3):
    client=httpx.Client(base_url=URL,timeout=30)
    challenge=client.get('/api/captcha?purpose=register').json()
    r=client.post('/api/register',json=dict(username='soak_'+uuid.uuid4().hex[:12],password='Disposable soak passphrase 123!',captcha_id=challenge['id'],captcha_answer='ABC234'))
    assert r.status_code==201,r.text
    client.headers['x-csrf-token']=r.json()['csrf'];clients.append(client)
catalogue=clients[0].get('/api/catalogue').json()
cases=[dict(dataset=d['id'],model=m['id'],transformations=['bridge_width','bridge_trend'],delta=.25,seed=17,custom_code='') for d,m in itertools.product(catalogue['datasets'],catalogue['models'])]
def group(pair):
    client,specs=pair;out=[]
    for spec in specs:
        begin=time.monotonic()
        try:
            r=client.post('/api/experiments',json=spec);assert r.status_code==202,r.text
            id=r.json()['id']
            for _ in range(300):
                r=client.get('/api/experiments/'+id);assert r.status_code==200,r.text
                item=r.json()
                if item['status'] in ('complete','failed'):break
                time.sleep(1)
            assert item['status']=='complete',item.get('error')
            result=item['result'];assert result['spec']==spec
            assert result['summary']['model_calls']==5
            json.dumps(result,allow_nan=False)
            # Other accounts cannot retrieve this experiment.
            stranger=clients[(clients.index(client)+1)%3]
            assert stranger.get('/api/experiments/'+id).status_code==404
            out.append(dict(dataset=spec['dataset'],model=spec['model'],seconds=round(time.monotonic()-begin,3),baseline=result['baseline'],invalid=sum(not row['valid_for_analysis'] for row in result['rows'])))
        except Exception as error:report['failures'].append(dict(spec=spec,error=repr(error)))
        report['runs'].append(out[-1]) if out and out[-1]['dataset']==spec['dataset'] and out[-1]['model']==spec['model'] else None
        report['seconds']=round(time.time()-started,3)
        (ROOT/'verification'/'api-soak-audit.json').write_text(json.dumps(report,indent=2))
        print(f'{len(report["runs"])}/{len(cases)} API jobs completed; {len(report["failures"])} failures',flush=True)
    return out
with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
    batches=list(pool.map(group,[(clients[i],cases[i::3]) for i in range(3)]))
report['runs']=[row for batch in batches for row in batch]
times=sorted(row['seconds'] for row in report['runs'])
report['summary']=dict(total=len(cases),completed=len(times),failures=len(report['failures']),p50_seconds=statistics.median(times),p95_seconds=times[int(.95*(len(times)-1))],max_seconds=max(times))
report['seconds']=round(time.time()-started,3)
(ROOT/'verification'/'api-soak-audit.json').write_text(json.dumps(report,indent=2))
print(json.dumps(report['summary']),flush=True)
for c in clients:c.close()
raise SystemExit(bool(report['failures']))
