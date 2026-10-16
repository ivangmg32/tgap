"""Bounded local reliability exercise using the actual production supervisor."""
import concurrent.futures,hashlib,hmac,json,os,shutil,sqlite3,statistics,subprocess,sys,tempfile,time,uuid
from pathlib import Path
import httpx,psutil
ROOT=Path(__file__).resolve().parents[1];HOME=Path(tempfile.mkdtemp(prefix='tgap-reliability-'));PORT=8094;URL=f'http://127.0.0.1:{PORT}'
for folder in ('sandbox','static','publication'):shutil.copytree(ROOT/folder,HOME/folder,ignore=shutil.ignore_patterns('__pycache__'))
shutil.copytree(ROOT/'fixtures',HOME/'data'/'datasets')
(HOME/'config.json').write_text(json.dumps(dict(host='127.0.0.1',port=PORT,tgap_source=str(ROOT.parent if (ROOT.parent/'core').is_dir() else ROOT.parent/'tgap'))))
line='audit:reliability-test-passphrase:participant';(HOME/'users.txt').write_text(line+'\n')
report=dict(home=str(HOME),checks=[],load={});supervisor=None

def wait_health(timeout=25):
    end=time.monotonic()+timeout
    while time.monotonic()<end:
        try:
            if httpx.get(URL+'/api/health',timeout=1).status_code==200:return
        except httpx.HTTPError:pass
        time.sleep(.2)
    raise AssertionError('Server did not become healthy')
def connection():return sqlite3.connect(HOME/'data'/'laboratory.sqlite3',timeout=20)
def check(label,condition):
    assert condition,label
    report['checks'].append(label);print(label,flush=True)
def finished(client,job):
    for _ in range(200):
        r=client.get('/api/experiments/'+job);r.raise_for_status();item=r.json()
        if item['status'] in ('complete','failed'):return item
        time.sleep(.15)
    raise AssertionError('Job did not finish')
def start_job(client):
    r=client.post('/api/experiments',json=SPEC);assert r.status_code==202,r.text
    return r.json()['id']
SPEC=dict(dataset='stable',model='persistence_bridge',transformations=['bridge_width','centralization','density'],delta=.1,seed=42,custom_code='')
try:
    log=(HOME/'supervisor.log').open('wb')
    supervisor=subprocess.Popen([sys.executable,str(HOME/'sandbox'/'serve.py'),'--home',str(HOME)],cwd=HOME,stdout=log,stderr=log,creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
    wait_health();check('Production supervisor starts isolated instance',True)
    secret=(HOME/'data'/'session.key').read_text().strip();token=uuid.uuid4().hex;csrf=uuid.uuid4().hex
    signature=hmac.new(secret.encode(),line.encode(),hashlib.sha256).hexdigest()
    with connection() as c:c.execute('INSERT INTO sessions VALUES (?,?,?,?,?)',(hashlib.sha256(token.encode()).hexdigest(),'audit',csrf,signature,time.time()+3600))
    client=httpx.Client(base_url=URL,cookies={'tgap_session':token},headers={'x-csrf-token':csrf},timeout=20)
    # Session seeding isolates worker reliability from authentication, tested separately in browser/API tests.
    job=start_job(client)
    check('One active experiment per account returns 429',client.post('/api/experiments',json=SPEC).status_code==429)
    check('Known-truth worker returns baseline 8',finished(client,job)['result']['baseline']==8)
    for i in range(5):
        job=start_job(client);check(f'Repeated experiment {i+1} completes',finished(client,job)['status']=='complete')
    job=start_job(client);killed=False
    for _ in range(200):
        runtime=json.loads((HOME/'data'/'runtime.json').read_text())
        for child in psutil.Process(runtime['server_pid']).children(recursive=True):
            if 'worker.py' in ' '.join(child.cmdline()):child.kill();killed=True;break
        if killed:break
        time.sleep(.02)
    check('Worker crash injected',killed)
    check('Worker crash produces explicit failed job',finished(client,job)['status']=='failed')
    check('Queue recovers after worker crash',finished(client,start_job(client))['status']=='complete')
    owner=hmac.new(secret.encode(),b'participant:audit',hashlib.sha256).hexdigest()
    placeholders=[str(uuid.uuid4()) for _ in range(10)]
    with connection() as c:
        for id in placeholders:c.execute('INSERT INTO jobs(id,owner,status,created,spec) VALUES (?,?,?,?,?)',(id,'fixture-other-owner','queued',time.time(),json.dumps(SPEC)))
    check('Global queue bound returns 429',client.post('/api/experiments',json=SPEC).status_code==429)
    with connection() as c:
        for id in placeholders:c.execute('DELETE FROM jobs WHERE id=?',(id,))
    pending=str(uuid.uuid4())
    with connection() as c:c.execute('INSERT INTO jobs(id,owner,status,created,spec) VALUES (?,?,?,?,?)',(pending,owner,'queued',time.time(),json.dumps(SPEC)))
    old=json.loads((HOME/'data'/'runtime.json').read_text())['server_pid'];psutil.Process(old).kill()
    begin=time.monotonic()
    for _ in range(150):
        time.sleep(.1)
        try:
            if json.loads((HOME/'data'/'runtime.json').read_text())['server_pid']!=old:break
        except (OSError,ValueError):pass
    wait_health();report['restart_seconds']=round(time.monotonic()-begin,3)
    check('Supervisor restarts killed API process',json.loads((HOME/'data'/'runtime.json').read_text())['server_pid']!=old)
    check('Session persists across API restart',client.get('/api/me').status_code==200)
    item=client.get('/api/experiments/'+pending).json()
    check('Interrupted queue explicitly marked failed on restart',item['status']=='failed' and 'restarted' in item['error'])
    check('Completed result survives restart',client.get('/api/experiments/'+job).status_code==200)
    check('New experiment succeeds after API restart',finished(client,start_job(client))['status']=='complete')
    def request(i):
        begin=time.monotonic()
        try:r=client.get('/api/health');return r.status_code,(time.monotonic()-begin)*1000
        except httpx.HTTPError:return 0,(time.monotonic()-begin)*1000
    # 200 requests, only ten concurrent connections, exclusively on loopback.
    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as pool:responses=list(pool.map(request,range(200)))
    times=sorted(t for _,t in responses);counts={str(code):sum(c==code for c,_ in responses) for code in set(c for c,_ in responses)}
    report['load']=dict(requests=200,concurrency=10,statuses=counts,p50_ms=round(statistics.median(times),2),p95_ms=round(times[189],2),p99_ms=round(times[197],2))
    check('Load has no unexpected HTTP errors or connection failures',all(code in (200,429,503) for code,_ in responses))
    check('Burst limiter rejects excess requests',any(code==429 for code,_ in responses))
    time.sleep(1.2);check('Health recovers after bounded burst',client.get('/api/health').status_code==200)
    check('Oversized streamed request rejected',client.post('/api/login',content=b'x'*65537).status_code==413)
    check('Malformed JSON rejected without crashing',client.post('/api/login',content=b'{bad',headers={'content-type':'application/json'}).status_code==422)
    runtime=json.loads((HOME/'data'/'runtime.json').read_text());process=psutil.Process(runtime['server_pid'])
    report['api_tree_rss_mib']=round((process.memory_info().rss+sum(p.memory_info().rss for p in process.children(recursive=True)))/1024**2,2)
    check('Worker scratch inputs and outputs cleaned',not list((HOME/'data'/'jobs').glob('*.json')))
    with connection() as c:check('SQLite integrity check passes',c.execute('PRAGMA integrity_check').fetchone()[0]=='ok')
    report['passed']=True
finally:
    (ROOT/'verification'/'reliability-audit.json').write_text(json.dumps(report,indent=2))
    (HOME/'data'/'service.stopped').write_text('Test finished')
    if supervisor:
        try:supervisor.wait(timeout=12)
        except subprocess.TimeoutExpired:
            for child in psutil.Process(supervisor.pid).children(recursive=True):child.kill()
            supervisor.kill()
    print(json.dumps(report,indent=2),flush=True)
