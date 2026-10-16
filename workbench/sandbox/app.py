"""Authenticated TGAP API, bounded experiment workers and study records."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import datetime, timezone
import csv
import asyncio
import hashlib
import hmac
import io
import json
import os
from pathlib import Path
import secrets
import sqlite3
import shutil
import subprocess
import sys
import threading
import time
import uuid

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, ConfigDict
import psutil

from sandbox.engine import catalogue, generated_program, SYNTHETIC, MODELS, TRANSFORMS

HOME = Path(os.environ.get('TGAP_SANDBOX_HOME',Path(__file__).resolve().parents[1])).resolve()
HOME.mkdir(parents=True,exist_ok=True)
CONFIG = json.loads((HOME/'config.json').read_text(encoding='utf-8'))
DATA = HOME/'data'
DATA.mkdir(exist_ok=True)
JOBS = DATA/'jobs'
JOBS.mkdir(exist_ok=True)
USERS = HOME/'users.txt'
DB = DATA/'laboratory.sqlite3'
SECRET_PATH = DATA/'session.key'
if not SECRET_PATH.exists():
    SECRET_PATH.write_text(secrets.token_hex(32),encoding='utf-8')
SECRET = SECRET_PATH.read_text(encoding='utf-8').strip()
POOL = ThreadPoolExecutor(max_workers=2,thread_name_prefix='tgap')
QUEUE_LOCK = threading.Lock()


@contextmanager
def db():
    conn = sqlite3.connect(DB,timeout=20)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA foreign_keys=ON')
    try:
        with conn:
            yield conn
    finally:
        conn.close()


with db() as conn:
    conn.executescript('''
    PRAGMA journal_mode=WAL;
    CREATE TABLE IF NOT EXISTS sessions(token TEXT PRIMARY KEY, username TEXT NOT NULL, csrf TEXT NOT NULL,
        account_signature TEXT NOT NULL, expires REAL NOT NULL);
    CREATE TABLE IF NOT EXISTS jobs(id TEXT PRIMARY KEY, owner TEXT NOT NULL, status TEXT NOT NULL,
        created REAL NOT NULL, spec TEXT NOT NULL, result TEXT, error TEXT, study_id TEXT);
    CREATE TABLE IF NOT EXISTS studies(id TEXT PRIMARY KEY, owner TEXT NOT NULL, participant TEXT NOT NULL,
        started REAL NOT NULL, finished REAL, consent_version TEXT NOT NULL, condition TEXT NOT NULL,
        stage TEXT NOT NULL DEFAULT 'bridge', stage_started REAL NOT NULL, questionnaire TEXT);
    CREATE TABLE IF NOT EXISTS responses(id INTEGER PRIMARY KEY, study_id TEXT NOT NULL REFERENCES studies(id),
        task TEXT NOT NULL, answer TEXT NOT NULL, correct INTEGER NOT NULL, confidence INTEGER NOT NULL,
        elapsed REAL NOT NULL, submitted REAL NOT NULL, UNIQUE(study_id,task));
    ''')
    conn.execute('CREATE INDEX IF NOT EXISTS jobs_study_idx ON jobs(study_id,created)')
    conn.execute('CREATE INDEX IF NOT EXISTS studies_started_idx ON studies(started)')
    conn.execute("UPDATE jobs SET status='failed', error='The service restarted. Please run this experiment again.' WHERE status IN ('queued','running')")

app = FastAPI(title='TGAP Laboratory',docs_url=None,redoc_url=None,openapi_url=None)
from sandbox.security import Security
SECURITY = Security(db,SECRET)


def accounts():
    found = {}
    for line in USERS.read_text(encoding='utf-8-sig').splitlines():
        if not line.strip() or line.lstrip().startswith('#'):
            continue
        parts = line.strip().split(':')
        if len(parts) != 3 or parts[2] not in ('admin','participant'):
            continue
        username,password,role = parts
        if username and password:
            found[username] = dict(password=password,role=role,
                signature=hmac.new(SECRET.encode(),line.strip().encode(),hashlib.sha256).hexdigest())
    return found


def account_for(username):
    username=username.strip()
    for name,account in accounts().items():
        if name.casefold()==username.casefold():
            return dict(account,username=name)
    return SECURITY.registered(username.lower())


def session(request):
    token = request.cookies.get('tgap_session','')
    digest = hashlib.sha256(token.encode()).hexdigest()
    with db() as conn:
        row = conn.execute('SELECT * FROM sessions WHERE token=? AND expires>?',(digest,time.time())).fetchone()
    account = account_for(row['username']) if row else None
    if not row or not account or not hmac.compare_digest(account['signature'],row['account_signature']):
        raise HTTPException(401,'Please sign in to the laboratory.')
    identity = dict(username=row['username'],role=account['role'],csrf=row['csrf'])
    if request.method not in ('GET','HEAD','OPTIONS') and not hmac.compare_digest(request.headers.get('x-csrf-token',''),identity['csrf']):
        raise HTTPException(403,'Refresh the page before trying again.')
    return identity


def owner_key(username):
    return hmac.new(SECRET.encode(),('participant:'+username).encode(),hashlib.sha256).hexdigest()


@app.middleware('http')
async def guard(request: Request,call_next):
    peer=request.client.host if request.client else 'unknown'
    try:SECURITY.admit(peer)
    except HTTPException as error:
        return JSONResponse({'detail':error.detail},status_code=error.status_code,headers=error.headers)
    try:
        return await guarded_request(request,call_next)
    finally:SECURITY.release()


async def guarded_request(request,call_next):
    if request.method not in ('GET','HEAD'):
        # Check streamed bodies as well as Content-Length; do not buffer unlimited input.
        async def read_body():
            body=bytearray()
            async for chunk in request.stream():
                if len(body)+len(chunk)>65536:
                    raise HTTPException(413,'Request is too large.')
                body.extend(chunk)
            return bytes(body)
        try:request._body=await asyncio.wait_for(read_body(),timeout=10)
        except asyncio.TimeoutError:
            return JSONResponse({'detail':'Request body timed out.'},status_code=408)
        except HTTPException as error:
            return JSONResponse({'detail':error.detail},status_code=error.status_code)
        origin = request.headers.get('origin')
        if origin:
            from urllib.parse import urlsplit
            if urlsplit(origin).netloc != request.headers.get('host'):
                return JSONResponse({'detail':'Cross-origin requests are unavailable.'},status_code=403)
    response = await call_next(request)
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'DENY'
    response.headers['Referrer-Policy'] = 'same-origin'
    response.headers['Content-Security-Policy'] = "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
    if request.url.path.startswith('/api/'):
        response.headers['Cache-Control'] = 'no-store'
    return response


class Login(BaseModel):
    model_config = ConfigDict(extra='forbid')
    username: str = Field(min_length=1,max_length=80)
    password: str = Field(min_length=1,max_length=150)
    captcha_id: str = Field(min_length=1,max_length=80)
    captcha_answer: str = Field(min_length=1,max_length=12)


class Registration(Login):
    username: str = Field(min_length=3,max_length=32,pattern=r'^[A-Za-z][A-Za-z0-9_-]*$')
    password: str = Field(min_length=15,max_length=128)


class Experiment(BaseModel):
    model_config = ConfigDict(extra='forbid')
    dataset: str = Field(default='stable',pattern=r'^[a-z][a-z0-9_-]{0,50}$')
    model: str = 'persistence_bridge'
    transformations: list[str] = Field(default=['bridge_width','centralization','density'],max_length=5)
    delta: float = Field(default=0.1,ge=0.02,le=0.5)
    seed: int = Field(default=42,ge=0,le=100000)
    custom_code: str = Field(default='',max_length=12000)


def validate_spec(spec):
    available = {d['id'] for d in catalogue(DATA)['datasets']}
    if spec.dataset not in available or spec.model not in MODELS or any(t not in TRANSFORMS for t in spec.transformations):
        raise HTTPException(422,'Choose a listed dataset, model, and transformations.')
    if len(set(spec.transformations)) != len(spec.transformations):
        raise HTTPException(422,'Choose each transformation once.')
    if not spec.transformations and not spec.custom_code.strip():
        raise HTTPException(422,'Choose a transformation or write a custom one.')
    if spec.custom_code.strip():
        from sandbox.restricted import Interpreter,CodeError
        try:
            from sandbox.engine import load_core
            Interpreter(spec.custom_code,load_core(CONFIG['tgap_source']).TemporalGraphTransformation)
        except (CodeError,SyntaxError,ValueError) as error:
            raise HTTPException(422,str(error)) from None
    return spec.model_dump()


@app.get('/api/health')
def health():
    return {'status':'ok','service':'tgap-laboratory','version':'1.0.0'}


@app.post('/api/login')
def login(form: Login,request: Request,response: Response):
    host = request.client.host if request.client else 'unknown'
    now = time.time()
    SECURITY.rate('login-ip:'+host,20,900)
    SECURITY.rate('login-account:'+form.username.strip().casefold(),20,900)
    SECURITY.rate('login-global',120,60)
    SECURITY.check(request,form.captcha_id,form.captcha_answer,'login')
    account = account_for(form.username)
    if not SECURITY.verify(form.password,account):
        raise HTTPException(401,'Username or password is incorrect.')
    return create_session(account,response,now)


def create_session(account,response,now=None):
    now=now or time.time()
    token,csrf = secrets.token_urlsafe(32),secrets.token_urlsafe(24)
    with db() as conn:
        conn.execute('DELETE FROM sessions WHERE expires<?',(now,))
        conn.execute('INSERT INTO sessions VALUES (?,?,?,?,?)',
                     (hashlib.sha256(token.encode()).hexdigest(),account['username'],csrf,account['signature'],now+43200))
    response.set_cookie('tgap_session',token,max_age=43200,httponly=True,samesite='strict',secure=CONFIG.get('secure_cookies',False))
    return {'username':account['username'],'role':account['role'],'csrf':csrf}


@app.get('/api/captcha')
def captcha(request: Request,response: Response,purpose: str='login'):
    if purpose not in ('login','register'):
        raise HTTPException(422,'Choose sign-in or registration verification.')
    return SECURITY.issue(request,response,purpose,CONFIG.get('secure_cookies',False))


@app.post('/api/register',status_code=201)
def register(form: Registration,request: Request,response: Response):
    if not CONFIG.get('registration_enabled',True):
        raise HTTPException(403,'New account registration is currently closed.')
    peer=request.client.host if request.client else 'unknown'
    SECURITY.rate('register-ip:'+peer,max(1,min(100,int(CONFIG.get('registration_attempts_per_ip_hour',20)))),3600)
    SECURITY.rate('register-global',100,86400)
    SECURITY.check(request,form.captcha_id,form.captcha_answer,'register')
    username=form.username.lower()
    if form.password.casefold() in ('passwordpassword','123456789012345','qwertyuiopasdfgh','password123456789'):
        raise HTTPException(422,'Choose a less predictable password or passphrase.')
    if account_for(username):
        raise HTTPException(409,'That username is unavailable. Choose another.')
    try:SECURITY.register(username,form.password)
    except sqlite3.IntegrityError:
        raise HTTPException(409,'That username is unavailable. Choose another.') from None
    return create_session(account_for(username),response)


@app.get('/api/me')
def me(request: Request):
    return session(request)


@app.post('/api/logout')
def logout(request: Request,response: Response):
    session(request)
    with db() as conn:
        conn.execute('DELETE FROM sessions WHERE token=?',(hashlib.sha256(request.cookies.get('tgap_session','').encode()).hexdigest(),))
    response.delete_cookie('tgap_session')
    return {'ok':True}


@app.get('/api/catalogue')
def get_catalogue(request: Request):
    session(request)
    return catalogue(DATA)


@app.post('/api/program')
def program(spec: Experiment,request: Request):
    session(request)
    return {'program':generated_program(validate_spec(spec))}


def run_job(job_id, spec):
    incoming, outgoing = JOBS/f'{job_id}.input.json',JOBS/f'{job_id}.output.json'
    incoming.write_text(json.dumps(dict(spec=spec,tgap_source=CONFIG['tgap_source'],data_root=str(DATA))),encoding='utf-8')
    with db() as conn:
        conn.execute("UPDATE jobs SET status='running' WHERE id=?",(job_id,))
    process = None
    try:
        # Credentials and session data are never passed to the worker.
        env = {k:v for k,v in os.environ.items() if k in ('SystemRoot','WINDIR','TEMP','TMP','PATH','HOME')}
        process = subprocess.Popen([sys.executable,'-I',str(Path(__file__).with_name('worker.py')),str(incoming),str(outgoing)],
                    cwd=JOBS,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,env=env,
                    creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
        started = time.monotonic()
        monitor = psutil.Process(process.pid)
        while process.poll() is None:
            if time.monotonic()-started>40:
                raise TimeoutError('Experiment exceeded the 40-second limit. Try fewer transformations.')
            try:
                memory = monitor.memory_info().rss + sum(p.memory_info().rss for p in monitor.children(recursive=True))
                if memory > 768*1024*1024:
                    raise MemoryError('Experiment exceeded the 768 MiB memory limit.')
            except psutil.NoSuchProcess:
                break
            time.sleep(0.15)
        if not outgoing.exists() or outgoing.stat().st_size>4*1024*1024:
            raise RuntimeError('The worker could not produce a bounded result. Try a smaller experiment.')
        payload = json.loads(outgoing.read_text(encoding='utf-8'))
        if not payload['ok']:
            raise ValueError(payload['error'])
        with db() as conn:
            conn.execute("UPDATE jobs SET status='complete',result=? WHERE id=?",(json.dumps(payload['result']),job_id))
    except Exception as error:
        with db() as conn:
            conn.execute("UPDATE jobs SET status='failed',error=? WHERE id=?",(str(error)[:1500],job_id))
    finally:
        if process and process.poll() is None:
            try:
                parent = psutil.Process(process.pid)
                for child in parent.children(recursive=True):
                    child.kill()
                parent.kill()
            except psutil.NoSuchProcess:
                pass
            process.wait(timeout=5)
        incoming.unlink(missing_ok=True)
        outgoing.unlink(missing_ok=True)


@app.post('/api/experiments',status_code=202)
def experiment(spec: Experiment,request: Request):
    identity = session(request)
    SECURITY.rate('experiment:'+identity['username'],30,3600)
    values = validate_spec(spec)
    owner = owner_key(identity['username'])
    with QUEUE_LOCK,db() as conn:
        stored_bytes=sum(p.stat().st_size for p in (DB,Path(str(DB)+'-wal')) if p.exists())
        if stored_bytes>512*1024*1024 or shutil.disk_usage(DATA).free<256*1024*1024 or conn.execute('SELECT count(*) FROM jobs').fetchone()[0]>=5000:
            raise HTTPException(503,'Experiment storage is full. Please contact the laboratory operator.',headers={'Retry-After':'3600'})
        if conn.execute("SELECT count(*) FROM jobs WHERE status IN ('queued','running')").fetchone()[0]>=10:
            raise HTTPException(429,'The laboratory is busy. Please try again shortly.')
        if conn.execute("SELECT count(*) FROM jobs WHERE owner=? AND status IN ('queued','running')",(owner,)).fetchone()[0]:
            raise HTTPException(429,'Your current experiment is still running.')
        study = conn.execute('SELECT id FROM studies WHERE owner=? AND finished IS NULL ORDER BY started DESC LIMIT 1',(owner,)).fetchone()
        job_id = str(uuid.uuid4())
        conn.execute('INSERT INTO jobs(id,owner,status,created,spec,study_id) VALUES (?,?,?,?,?,?)',
                     (job_id,owner,'queued',time.time(),json.dumps(values),study['id'] if study else None))
    POOL.submit(run_job,job_id,values)
    return {'id':job_id,'status':'queued'}


def own_job(job_id,identity):
    with db() as conn:
        row = conn.execute('SELECT * FROM jobs WHERE id=? AND owner=?',(job_id,owner_key(identity['username']))).fetchone()
    if not row:
        raise HTTPException(404,'Experiment not found.')
    return row


@app.get('/api/experiments')
def history(request: Request):
    identity = session(request)
    with db() as conn:
        rows = conn.execute('SELECT id,status,created,spec,error FROM jobs WHERE owner=? ORDER BY created DESC LIMIT 30',
                            (owner_key(identity['username']),)).fetchall()
    return [dict(id=r['id'],status=r['status'],created=r['created'],spec=json.loads(r['spec']),error=r['error']) for r in rows]


@app.get('/api/experiments/{job_id}')
def job(job_id: str,request: Request):
    row = own_job(job_id,session(request))
    return dict(id=row['id'],status=row['status'],error=row['error'],result=json.loads(row['result']) if row['result'] else None)


@app.get('/api/experiments/{job_id}/download/{kind}')
def download(job_id: str,kind: str,request: Request):
    row = own_job(job_id,session(request))
    if not row['result']:
        raise HTTPException(409,'Wait for the experiment to finish.')
    result = json.loads(row['result'])
    if kind=='json':
        body,media,ext = json.dumps(result,indent=2),'application/json','json'
    elif kind=='python':
        body,media,ext = result['program'],'text/x-python','py'
    elif kind=='csv':
        buf = io.StringIO(newline='')
        writer = csv.DictWriter(buf,fieldnames=list(result['rows'][0]))
        writer.writeheader()
        writer.writerows(result['rows'])
        body,media,ext = buf.getvalue(),'text/csv','csv'
    else:
        raise HTTPException(404,'Unknown format.')
    return Response(body,media_type=media,headers={'Content-Disposition':f'attachment; filename="tgap-{job_id[:8]}.{ext}"'})


TASKS = {
    'bridge':dict(title='Read a concept explanation',question='A present-only bridge model sees one additional crossing edge in the last snapshot. Its prediction will…',options=['increase','decrease','stay the same'],answer='increase',example='first',next='history'),
    'history':dict(title='Separate present from history',question='Bridge Trend changes earlier snapshots and keeps the last one fixed. What should a present-only model do?',options=['increase','decrease','stay the same'],answer='stay the same',example='history',next='validity'),
    'validity':dict(title='Judge an invalid perturbation',question='A result is marked edge_count_infeasible. Can it support a conclusion about that concept’s sensitivity?',options=['include it','exclude it from conclusions','treat it as zero'],answer='exclude it from conclusions',example='limits',next='reflection'),
}


def study_state(row):
    if row is None:
        return None
    result = dict(id=row['id'],participant=row['participant'],stage=row['stage'],started=row['started'],finished=row['finished'],condition=row['condition'])
    if row['stage'] in TASKS:
        result['task'] = {k:v for k,v in TASKS[row['stage']].items() if k not in ('answer','next')}
    with db() as conn:
        result['responses'] = [dict(r) for r in conn.execute('SELECT task,answer,confidence,elapsed FROM responses WHERE study_id=? ORDER BY submitted',(row['id'],))]
    return result


@app.get('/api/study')
def get_study(request: Request):
    identity = session(request)
    with db() as conn:
        row = conn.execute('SELECT * FROM studies WHERE owner=? ORDER BY started DESC LIMIT 1',(owner_key(identity['username']),)).fetchone()
    return study_state(row)


class Consent(BaseModel):
    consent: bool


@app.post('/api/study/start')
def start_study(form: Consent,request: Request):
    identity = session(request)
    if not form.consent:
        raise HTTPException(422,'Consent is required to record a study session. You can still explore without joining.')
    owner = owner_key(identity['username'])
    now = time.time()
    with db() as conn:
        row = conn.execute('SELECT * FROM studies WHERE owner=? AND finished IS NULL',(owner,)).fetchone()
        if not row:
            ident = str(uuid.uuid4())
            conn.execute('INSERT INTO studies(id,owner,participant,started,consent_version,condition,stage_started) VALUES (?,?,?,?,?,?,?)',
                          (ident,owner,'P-'+secrets.token_hex(4).upper(),now,'pilot-1.1','concept-guided-pilot',now))
            row = conn.execute('SELECT * FROM studies WHERE id=?',(ident,)).fetchone()
    return study_state(row)


class Answer(BaseModel):
    task: str
    answer: str = Field(max_length=100)
    confidence: int = Field(ge=1,le=7)


@app.post('/api/study/answer')
def answer(form: Answer,request: Request):
    identity = session(request)
    with db() as conn:
        row = conn.execute('SELECT * FROM studies WHERE owner=? AND finished IS NULL',(owner_key(identity['username']),)).fetchone()
        if not row or row['stage']!=form.task or form.task not in TASKS:
            raise HTTPException(409,'This task is not currently active. Refresh the study.')
        task = TASKS[form.task]
        if form.answer not in task['options']:
            raise HTTPException(422,'Choose one of the offered answers.')
        if not conn.execute("SELECT id FROM jobs WHERE study_id=? AND status='complete' AND created>=?",(row['id'],row['stage_started'])).fetchone():
            raise HTTPException(409,'Run an experiment for this task before answering.')
        now = time.time()
        conn.execute('INSERT INTO responses(study_id,task,answer,correct,confidence,elapsed,submitted) VALUES (?,?,?,?,?,?,?)',
                     (row['id'],form.task,form.answer,int(form.answer==task['answer']),form.confidence,now-row['stage_started'],now))
        conn.execute('UPDATE studies SET stage=?,stage_started=? WHERE id=?',(task['next'],now,row['id']))
        row = conn.execute('SELECT * FROM studies WHERE id=?',(row['id'],)).fetchone()
    return study_state(row)


class Reflection(BaseModel):
    ease: int = Field(ge=1,le=7)
    understanding: int = Field(ge=1,le=7)
    trust: int = Field(ge=1,le=7)
    feedback: str = Field(default='',max_length=2000)


@app.post('/api/study/finish')
def finish(form: Reflection,request: Request):
    identity = session(request)
    with db() as conn:
        row = conn.execute("SELECT * FROM studies WHERE owner=? AND finished IS NULL AND stage='reflection'",(owner_key(identity['username']),)).fetchone()
        if not row:
            raise HTTPException(409,'Complete the three study tasks first.')
        custom_jobs=conn.execute("SELECT spec FROM jobs WHERE study_id=? AND status='complete' AND created>=?",(row['id'],row['stage_started'])).fetchall()
        if not any(json.loads(job['spec']).get('custom_code','').strip() for job in custom_jobs):
            raise HTTPException(409,'Run the custom-transformer example before finishing the reflection.')
        conn.execute("UPDATE studies SET stage='complete',finished=?,questionnaire=? WHERE id=?",(time.time(),json.dumps(form.model_dump()),row['id']))
        row = conn.execute('SELECT * FROM studies WHERE id=?',(row['id'],)).fetchone()
    return study_state(row)


@app.delete('/api/study')
def withdraw(request: Request):
    identity = session(request)
    owner = owner_key(identity['username'])
    with db() as conn:
        for row in conn.execute('SELECT id FROM studies WHERE owner=?',(owner,)).fetchall():
            conn.execute('DELETE FROM responses WHERE study_id=?',(row['id'],))
        conn.execute('DELETE FROM jobs WHERE owner=?',(owner,))
        conn.execute('DELETE FROM studies WHERE owner=?',(owner,))
    return {'ok':True}


def researcher(request):
    user = session(request)
    if user['role']!='admin':
        raise HTTPException(403,'Researcher access is required.')


def research_report(start='',end='',status='all'):
    from sandbox.reporting import report
    try:
        with db() as conn:
            conn.execute('BEGIN')
            return report(conn,SECRET,TASKS,start,end,status)
    except (ValueError,OverflowError) as error:
        raise HTTPException(422,str(error)) from None


@app.get('/api/admin/report')
def admin_report(request: Request,start: str='',end: str='',status: str='all'):
    researcher(request)
    return research_report(start,end,status)


@app.get('/api/admin/experiments/{job_id}')
def admin_experiment(job_id: str,request: Request):
    researcher(request)
    with db() as conn:
        row=conn.execute('SELECT j.id,j.status,j.spec,j.result,j.error,s.participant FROM jobs j JOIN studies s ON j.study_id=s.id WHERE j.id=?',(job_id,)).fetchone()
    if not row:raise HTTPException(404,'Consented study experiment not found.')
    return dict(experiment_id=row['id'],participant=row['participant'],status=row['status'],spec=json.loads(row['spec']),result=json.loads(row['result']) if row['result'] else None,error=row['error'])


@app.get('/api/admin/report/download/{kind}')
def admin_report_download(kind: str,request: Request,start: str='',end: str='',status: str='all'):
    researcher(request)
    if kind not in ('json','zip'):raise HTTPException(404,'Choose JSON or the research ZIP.')
    data=research_report(start,end,status)
    if kind=='json':
        return Response(json.dumps(data,allow_nan=False,indent=2),media_type='application/json',headers={'Content-Disposition':'attachment; filename="tgap-research-report.json"'})
    import zipfile
    archive=io.BytesIO()
    with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as zipped:
        zipped.writestr('report.json',json.dumps(data,allow_nan=False,indent=2))
        for table in ('sessions','responses','experiments','impacts'):
            rows=[]
            for item in data[table]:
                rows.append({k:json.dumps(v,ensure_ascii=True) if isinstance(v,(list,dict)) else v for k,v in item.items()})
            # Older result schemas may omit new provenance fields.
            keys=list(dict.fromkeys(key for row in rows for key in row))
            normalized=[{key:row.get(key) for key in keys} for row in rows]
            zipped.writestr(table+'.csv',csv_response(normalized,table+'.csv').body)
        metadata={key:data[key] for key in ('schema_version','generated_at','filters','coverage','summary','notes')}
        import platform
        metadata['python']=platform.python_version()
        metadata['source_sha256']={path.name:hashlib.sha256(path.read_bytes()).hexdigest() for path in sorted(Path(__file__).parent.glob('*.py'))}
        import importlib.metadata
        metadata['packages']={name:importlib.metadata.version(name) for name in ('networkx','numpy','fastapi')}
        metadata['dataset_fixture_sha256']={path.name:hashlib.sha256(path.read_bytes()).hexdigest() for path in sorted((DATA/'datasets').glob('*.json')) if path.stem in {r['dataset'] for r in data['experiments']}}
        metadata['task_definitions']=TASKS
        metadata['data_dictionary']={'sessions':'One row per consented visit. Times are Unix seconds UTC; duration only for completed visits; ease/understanding/trust are ordinal 1-7. participant_key links repeated visits without account names.', 'responses':'One row per submitted task answer. correct is 0/1; confidence is ordinal 1-7; elapsed is seconds including reading and waiting.', 'experiments':'One row per study-linked job attempt; delta is the requested transformation control; baseline is in model output units; seconds is worker execution time, not total waiting time; request_hash fingerprints the configuration.', 'impacts':'One row per tested concept/direction for saved results. impact is prediction_change divided by an absolute normalization magnitude. delta_mode describes achieved-change units; requested_delta_mode may differ at zero baseline. Invalid numerical values are blank/null; no-op is not evidence of irrelevance.'}
        metadata['core_sha256']={str(path.relative_to(CONFIG['tgap_source'])):hashlib.sha256(path.read_bytes()).hexdigest() for path in sorted((Path(CONFIG['tgap_source'])/'core').rglob('*.py'))}
        zipped.writestr('metadata.json',json.dumps(metadata,indent=2))
        zipped.writestr('README.txt','TGAP descriptive research export. Times are UTC Unix seconds; filters select study starts. See metadata.json for scope, coverage and source hashes. Sessions are visits; participant_key links repeated visitors. Invalid numbers are blank/null. CSV free text beginning with spreadsheet formula characters is prefixed with an apostrophe. Review free text/custom code for identifying information before publication. No significance or causal claims are implied. A withdrawn record disappears from new exports; downloaded copies require separate handling. Graph-level result JSON is available through the protected per-experiment detail API. Empty CSV files mean no records.\n')
    return Response(archive.getvalue(),media_type='application/zip',headers={'Content-Disposition':'attachment; filename="tgap-research-data.zip"'})


@app.get('/api/admin/summary')
def admin_summary(request: Request):
    researcher(request)
    with db() as conn:
        studies = [dict(r) for r in conn.execute('SELECT participant,condition,stage,started,finished FROM studies ORDER BY started DESC')]
        count = conn.execute("SELECT count(*) FROM jobs j JOIN studies s ON j.study_id=s.id WHERE j.status='complete'").fetchone()[0]
    return dict(studies=studies,experiments=count)


def csv_response(rows,filename):
    buf = io.StringIO(newline='')
    if rows:
        writer = csv.DictWriter(buf,fieldnames=list(rows[0]))
        writer.writeheader()
        for row in rows:
            # Prevent formula execution when exported free text is opened in Excel.
            writer.writerow({k:("'"+v if isinstance(v,str) and v.startswith(('=','+','-','@','\t','\r')) else v) for k,v in row.items()})
    return Response(buf.getvalue(),media_type='text/csv',headers={'Content-Disposition':f'attachment; filename="{filename}"'})


@app.get('/api/admin/export/{kind}')
def export(kind: str,request: Request):
    researcher(request)
    with db() as conn:
        if kind=='responses':
            rows = [dict(r) for r in conn.execute('SELECT s.participant,s.condition,s.consent_version,r.task,r.answer,r.correct,r.confidence,r.elapsed,r.submitted FROM responses r JOIN studies s ON r.study_id=s.id ORDER BY r.submitted')]
        elif kind=='sessions':
            rows=[]
            for r in conn.execute('SELECT * FROM studies ORDER BY started'):
                rows.append(dict(participant=r['participant'],condition=r['condition'],consent_version=r['consent_version'],started=r['started'],finished=r['finished'],stage=r['stage'],duration_seconds=r['finished']-r['started'] if r['finished'] else None,**(json.loads(r['questionnaire']) if r['questionnaire'] else dict(ease=None,understanding=None,trust=None,feedback=''))))
        elif kind=='experiments':
            rows=[]
            for r in conn.execute('SELECT j.*,s.participant FROM jobs j JOIN studies s ON j.study_id=s.id ORDER BY j.created'):
                spec=json.loads(r['spec'])
                rows.append(dict(participant=r['participant'],experiment_id=r['id'],created=r['created'],status=r['status'],dataset=spec['dataset'],model=spec['model'],transformations=';'.join(spec['transformations']),delta=spec['delta'],seed=spec['seed'],custom=bool(spec['custom_code']),error=r['error']))
        else:
            raise HTTPException(404,'Unknown export.')
    return csv_response(rows,f'tgap-study-{kind}.csv')


PUBLICATION = Path(__file__).resolve().parents[1]/'publication'


@app.get('/api/publication')
def publication_catalogue(request: Request):
    session(request)
    manifest=PUBLICATION/'manifest.json'
    if not manifest.exists():
        return dict(figures=[])
    return json.loads(manifest.read_text(encoding='utf-8'))


@app.get('/api/publication/{figure_id}/{kind}')
def publication_file(figure_id: str,kind: str,request: Request):
    session(request)
    manifest=PUBLICATION/'manifest.json'
    records=json.loads(manifest.read_text(encoding='utf-8'))['figures'] if manifest.exists() else []
    figure=next((f for f in records if f['id']==figure_id),None)
    if not figure or kind not in figure['formats'] or kind not in ('png','pdf'):
        raise HTTPException(404,'Unknown publication figure.')
    path=PUBLICATION/(figure_id+'.'+kind)
    if not path.is_file():
        raise HTTPException(404,'Publication file is unavailable.')
    return FileResponse(path,media_type='image/png' if kind=='png' else 'application/pdf')


STATIC = Path(__file__).resolve().parents[1]/'static'
app.mount('/static',StaticFiles(directory=STATIC),name='static')


@app.get('/')
def index():
    return FileResponse(STATIC/'index.html')
