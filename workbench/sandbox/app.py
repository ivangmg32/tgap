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
    # Guided-study additions: job kind, live progress, and consented interaction events.
    columns = {row[1] for row in conn.execute('PRAGMA table_info(jobs)')}
    if 'kind' not in columns:
        conn.execute("ALTER TABLE jobs ADD COLUMN kind TEXT NOT NULL DEFAULT 'lab'")
    if 'progress' not in columns:
        conn.execute('ALTER TABLE jobs ADD COLUMN progress TEXT')
    conn.execute('''CREATE TABLE IF NOT EXISTS guided_events(id INTEGER PRIMARY KEY, study_id TEXT NOT NULL REFERENCES studies(id),
        event TEXT NOT NULL, step TEXT NOT NULL, job_id TEXT, scenario TEXT, created REAL NOT NULL)''')
    # Compare Explainers study: own consent, pseudonymous code, responses paired by participant and case.
    conn.execute('''CREATE TABLE IF NOT EXISTS cmp_sessions(id TEXT PRIMARY KEY, owner TEXT NOT NULL, participant TEXT NOT NULL,
        bank TEXT NOT NULL, method_order TEXT NOT NULL, case_order TEXT NOT NULL, consent_version TEXT NOT NULL,
        started REAL NOT NULL, finished REAL, UNIQUE(owner,bank))''')
    conn.execute('''CREATE TABLE IF NOT EXISTS cmp_responses(id INTEGER PRIMARY KEY, session_id TEXT NOT NULL REFERENCES cmp_sessions(id),
        case_id TEXT NOT NULL, stage TEXT NOT NULL, answers TEXT NOT NULL, correct TEXT NOT NULL, elapsed REAL NOT NULL,
        submitted REAL NOT NULL, UNIQUE(session_id,case_id,stage))''')
    conn.execute('''CREATE TABLE IF NOT EXISTS cmp_pre(session_id TEXT PRIMARY KEY REFERENCES cmp_sessions(id),
        version TEXT NOT NULL, answers TEXT NOT NULL, submitted REAL NOT NULL, updated REAL NOT NULL)''')
    conn.execute('''CREATE TABLE IF NOT EXISTS cmp_events(id INTEGER PRIMARY KEY, session_id TEXT NOT NULL REFERENCES cmp_sessions(id),
        case_id TEXT NOT NULL, stage TEXT NOT NULL, created REAL NOT NULL)''')
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
    # Accounts are identified by e-mail address (stored in lowercase). Study
    # records never contain it: they are keyed by a random participant code.
    username: str = Field(min_length=6,max_length=254,pattern=r'^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$')
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
        raise HTTPException(409,'An account with that e-mail address already exists. Please sign in.')
    try:SECURITY.register(username,form.password)
    except sqlite3.IntegrityError:
        raise HTTPException(409,'An account with that e-mail address already exists. Please sign in.') from None
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


JOB_LIMITS = {'lab':dict(seconds=40,cpu=35,output=4*1024*1024),
              'guided':dict(seconds=240,cpu=230,output=16*1024*1024)}


def run_job(job_id, spec, kind='lab'):
    limits = JOB_LIMITS[kind]
    incoming, outgoing = JOBS/f'{job_id}.input.json',JOBS/f'{job_id}.output.json'
    progress_file = JOBS/f'{job_id}.progress.json'
    incoming.write_text(json.dumps(dict(spec=spec,kind=kind,cpu_seconds=limits['cpu'],tgap_source=CONFIG['tgap_source'],data_root=str(DATA))),encoding='utf-8')
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
        seen = None
        while process.poll() is None:
            if time.monotonic()-started>limits['seconds']:
                raise TimeoutError(f"Experiment exceeded the {limits['seconds']}-second limit. " +
                                   ('Choose fewer comparison models, concepts, request sizes or seeds.' if kind=='guided' else 'Try fewer transformations.'))
            try:
                stage = progress_file.read_text(encoding='utf-8') if progress_file.exists() else None
            except OSError:
                stage = None
            if stage and stage != seen:
                seen = stage
                with db() as conn:
                    conn.execute('UPDATE jobs SET progress=? WHERE id=?',(stage,job_id))
            try:
                memory = monitor.memory_info().rss + sum(p.memory_info().rss for p in monitor.children(recursive=True))
                if memory > 768*1024*1024:
                    raise MemoryError('Experiment exceeded the 768 MiB memory limit.')
            except psutil.NoSuchProcess:
                break
            time.sleep(0.15)
        if not outgoing.exists() or outgoing.stat().st_size>limits['output']:
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
        progress_file.unlink(missing_ok=True)
        progress_file.with_suffix('.tmp').unlink(missing_ok=True)


@app.post('/api/experiments',status_code=202)
def experiment(spec: Experiment,request: Request):
    identity = session(request)
    SECURITY.rate('experiment:'+identity['username'],30,3600)
    values = validate_spec(spec)
    return admit_job(identity,values,'lab')


def admit_job(identity,values,kind):
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
        conn.execute('INSERT INTO jobs(id,owner,status,created,spec,study_id,kind) VALUES (?,?,?,?,?,?,?)',
                     (job_id,owner,'queued',time.time(),json.dumps(values),study['id'] if study else None,kind))
    POOL.submit(run_job,job_id,values,kind)
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
        rows = conn.execute('SELECT id,status,created,spec,error,kind FROM jobs WHERE owner=? ORDER BY created DESC LIMIT 30',
                            (owner_key(identity['username']),)).fetchall()
    return [dict(id=r['id'],status=r['status'],created=r['created'],spec=json.loads(r['spec']),error=r['error'],kind=r['kind']) for r in rows]


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
            conn.execute('DELETE FROM guided_events WHERE study_id=?',(row['id'],))
        conn.execute('DELETE FROM jobs WHERE owner=?',(owner,))
        conn.execute('DELETE FROM studies WHERE owner=?',(owner,))
        delete_compare_records(conn,owner)
    return {'ok':True}


def delete_compare_records(conn,owner):
    for row in conn.execute('SELECT id FROM cmp_sessions WHERE owner=?',(owner,)).fetchall():
        conn.execute('DELETE FROM cmp_responses WHERE session_id=?',(row['id'],))
        conn.execute('DELETE FROM cmp_events WHERE session_id=?',(row['id'],))
        conn.execute('DELETE FROM cmp_pre WHERE session_id=?',(row['id'],))
    conn.execute('DELETE FROM cmp_sessions WHERE owner=?',(owner,))



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
        elif kind=='guided_events':
            rows = [dict(r) for r in conn.execute('SELECT s.participant,s.consent_version,e.event,e.step,e.job_id,e.scenario,e.created FROM guided_events e JOIN studies s ON e.study_id=s.id ORDER BY e.created')]
        elif kind=='compare_responses':
            # One row per participant x case x stage: 0-7 ratings (review and side stages) or the free-text feedback.
            rows=[]
            rating_ids=list(dict.fromkeys(k for items in COMPARE.RATINGS.values() for k,_ in items))
            for r in conn.execute('SELECT s.participant,s.bank,s.method_order,s.case_order,r.case_id,r.stage,r.answers,r.correct,r.elapsed,r.submitted,s.finished FROM cmp_responses r JOIN cmp_sessions s ON r.session_id=s.id ORDER BY s.participant,r.submitted'):
                a=json.loads(r['answers'])
                ratings=a.get('ratings') or {}
                rows.append(dict(participant=r['participant'],bank=r['bank'],method_order=r['method_order'],case_id=r['case_id'],stage=r['stage'],
                                 method=r['stage'].replace('review_','') if r['stage'].startswith('review_') else '',
                                 **{f'rating_{k}':ratings.get(k) for k in rating_ids},
                                 feedback=a.get('text'),elapsed_seconds=r['elapsed'],submitted=r['submitted'],
                                 session_complete=r['finished'] is not None))
        elif kind=='compare_pre':
            rows=[]
            for r in conn.execute('SELECT s.participant,s.consent_version,p.* FROM cmp_pre p JOIN cmp_sessions s ON p.session_id=s.id ORDER BY p.submitted'):
                a=json.loads(r['answers'])
                rows.append(dict(participant=r['participant'],consent_version=r['consent_version'],version=r['version'],age=a.get('age'),education=a.get('education'),
                                 **{k:(a.get('familiarity') or {}).get(k) for k,_ in COMPARE.PRE_FAMILIARITY},submitted=r['submitted'],updated=r['updated']))
        elif kind=='compare_sessions':
            rows=[dict(participant=r['participant'],bank=r['bank'],method_order=r['method_order'],case_order=r['case_order'],
                       consent_version=r['consent_version'],started=r['started'],finished=r['finished']) for r in conn.execute('SELECT * FROM cmp_sessions ORDER BY started')]
        else:
            raise HTTPException(404,'Unknown export.')
    return csv_response(rows,f'tgap-study-{kind}.csv')


##  Guided TGAP user study  ##

from typing import Literal, Optional
from sandbox import guided as GUIDED

GUIDED_LOCK = threading.Lock()
GUIDED_CACHE = {}
SCENARIOS = Path(__file__).with_name('guided_scenarios.json')


def guided_core():
    from sandbox.engine import load_core
    return load_core(CONFIG['tgap_source'])


def cached(key,compute):
    # Small bounded cache for deterministic, trusted previews (no custom code).
    with GUIDED_LOCK:
        if key in GUIDED_CACHE:
            return GUIDED_CACHE[key]
        value = compute()
        if len(GUIDED_CACHE) > 256:
            GUIDED_CACHE.clear()
        GUIDED_CACHE[key] = value
        return value


def guided_profile(dataset,seed=42):
    if dataset not in {d['id'] for d in catalogue(DATA)['datasets']}:
        raise HTTPException(422,'Choose a listed dataset.')
    synthetic = dataset in SYNTHETIC or dataset=='three_communities'
    return cached(('profile',dataset,seed if synthetic else 0),lambda:GUIDED.dataset_profile(dataset,guided_core(),DATA,seed))


def scenarios():
    try:
        return json.loads(SCENARIOS.read_text(encoding='utf-8')).get('scenarios',[]) if SCENARIOS.exists() else []
    except (OSError,ValueError):
        return []


class GuidedSweep(BaseModel):
    model_config = ConfigDict(extra='forbid')
    deltas: list[float] = Field(default=list(GUIDED.PAPER_DELTAS),min_length=1,max_length=5)
    models: list[str] = Field(default=list(MODELS),min_length=1,max_length=6)
    concepts: list[str] = Field(default=list(TRANSFORMS),max_length=5)
    repeats: int = Field(default=2,ge=0,le=GUIDED.MAX_REPEATS)
    variation: Literal['transformation','graph'] = 'transformation'
    matched: bool = False
    sizes: list[int] = Field(default=[],max_length=4)


class GuidedExperiment(BaseModel):
    model_config = ConfigDict(extra='forbid')
    dataset: str = Field(pattern=r'^[a-z][a-z0-9_-]{0,50}$')
    model: str
    concept: str
    direction: Literal['increase','decrease']
    delta: float = Field(ge=0.02,le=0.5)
    seed: int = Field(default=42,ge=0,le=100000)
    target_snapshot: Optional[int] = Field(default=None,ge=1,le=10000)
    custom_code: str = Field(default='',max_length=12000)
    sweep: GuidedSweep = Field(default_factory=GuidedSweep)
    scenario: Optional[str] = Field(default=None,max_length=60,pattern=r'^[a-z0-9_-]+$')


def validate_guided(form):
    spec = form.model_dump()
    profile = guided_profile(spec['dataset'],spec['seed'])
    problems = []
    if spec['model'] not in MODELS:
        problems.append('Choose one of the listed models.')
    custom = bool(spec['custom_code'].strip())
    if spec['concept']=='custom':
        if not custom:
            problems.append('The custom concept needs transformer code (Advanced mode), or choose a built-in concept.')
    elif spec['concept'] not in TRANSFORMS:
        problems.append('Choose one of the listed concepts.')
    elif custom:
        problems.append('Custom code is only used when the selected concept is "custom". Clear the editor or select the custom concept.')
    sweep = spec['sweep']
    if any(m not in MODELS for m in sweep['models']) or any(c not in TRANSFORMS for c in sweep['concepts']):
        problems.append('Comparison models and concepts must come from the lists.')
    if len(set(sweep['models']))!=len(sweep['models']) or len(set(sweep['concepts']))!=len(sweep['concepts']):
        problems.append('Choose each comparison model and concept once.')
    if any(not 0.02<=d<=0.9 for d in sweep['deltas']) or len({round(d,6) for d in sweep['deltas']})!=len(sweep['deltas']):
        problems.append('Request sizes must be distinct values between 2% and 90%.')
    if spec['target_snapshot'] is not None and spec['target_snapshot']>=profile['snapshots']:
        problems.append(f"The target snapshot must be between 2 and {profile['snapshots']}.")
    if profile['family']!='synthetic':
        if sweep['variation']=='graph':
            problems.append('Graph-seed variation needs a synthetic dataset; real fixtures do not change with the seed. Use transformation seeds.')
        if sweep['sizes']:
            problems.append('Graph-size repeats need a synthetic dataset; real fixtures have a fixed node set.')
    if any(size not in GUIDED.SIZE_CHOICES for size in sweep['sizes']):
        problems.append(f'Graph sizes must be chosen from {list(GUIDED.SIZE_CHOICES)} nodes per community.')
    if custom:
        from sandbox.restricted import Interpreter,CodeError
        try:
            Interpreter(spec['custom_code'],guided_core().TemporalGraphTransformation)
        except (CodeError,SyntaxError,ValueError) as error:
            problems.append(f'Custom transformer: {error}')
    if spec['scenario'] and spec['scenario'] not in {s['id'] for s in scenarios()}:
        problems.append('Unknown predefined scenario.')
    if problems:
        raise HTTPException(422,' '.join(problems))
    spec['sweep']['sizes'] = sorted(set(sweep['sizes']))
    # Keep the lab's field names so history, exports and the researcher report keep working.
    spec['transformations'] = [] if spec['concept']=='custom' else [spec['concept']]
    return spec


@app.get('/api/guided/catalogue')
def guided_catalogue(request: Request):
    session(request)
    base = catalogue(DATA)
    datasets = []
    for item in base['datasets']:
        try:
            datasets.append({**item,**guided_profile(item['id'])})
        except Exception as error:
            datasets.append({**item,'available':False,'unavailable_reason':str(error)[:200]})
    with db() as conn:
        rows = conn.execute("SELECT spec,result FROM jobs WHERE kind='guided' AND status='complete' ORDER BY created DESC LIMIT 200").fetchall()
    durations = {}
    for row in rows:
        try:
            durations.setdefault(json.loads(row['spec'])['dataset'],[]).append(json.loads(row['result'])['guided']['seconds'])
        except (ValueError,KeyError,TypeError):
            continue
    import statistics
    timing = {k:dict(runs=len(v),median_seconds=round(statistics.median(v),1),max_seconds=round(max(v),1)) for k,v in durations.items()}
    from sandbox.chart_registry import inventory
    from sandbox import custom_samples as CS
    from sandbox.registry import glossary
    return dict(glossary=glossary(),custom=dict(skeleton=CS.SKELETON,samples=CS.SAMPLES,api=CS.API_REFERENCE,rules=CS.RULES),
                datasets=datasets,models=GUIDED.model_catalogue(),concepts=GUIDED.concept_catalogue(guided_core()),
                inventory=inventory(),scenarios=scenarios(),timing=timing,custom_template=base['custom_template'],
                defaults=dict(delta=0.1,direction='increase',seed=42,sweep=GuidedSweep().model_dump(),paper_deltas=list(GUIDED.PAPER_DELTAS),
                              paper_sizes=list(GUIDED.PAPER_SIZES),size_choices=list(GUIDED.SIZE_CHOICES)),
                limits=dict(seconds=JOB_LIMITS['guided']['seconds'],max_repeats=GUIDED.MAX_REPEATS),version=GUIDED.GUIDED_VERSION)


class GuidedPreview(BaseModel):
    model_config = ConfigDict(extra='forbid')
    dataset: str = Field(pattern=r'^[a-z][a-z0-9_-]{0,50}$')
    seed: int = Field(default=42,ge=0,le=100000)
    target_snapshot: Optional[int] = Field(default=None,ge=1,le=10000)


@app.post('/api/guided/preview')
def guided_preview(form: GuidedPreview,request: Request):
    session(request)
    profile = guided_profile(form.dataset,form.seed)
    if form.target_snapshot is not None and form.target_snapshot>=profile['snapshots']:
        raise HTTPException(422,f"The target snapshot must be between 2 and {profile['snapshots']}.")
    spec = dict(dataset=form.dataset,seed=form.seed,target_snapshot=form.target_snapshot)
    try:
        return cached(('preview',json.dumps(spec,sort_keys=True)),lambda:GUIDED.preview(spec,guided_core(),DATA))
    except ValueError as error:
        raise HTTPException(422,str(error)) from None


class GuidedFeasibility(GuidedPreview):
    concept: str
    delta: float = Field(ge=0.02,le=0.5)


@app.post('/api/guided/feasibility')
def guided_feasibility(form: GuidedFeasibility,request: Request):
    session(request)
    profile = guided_profile(form.dataset,form.seed)
    if form.concept not in TRANSFORMS:
        raise HTTPException(422,'Feasibility pre-checks are available for built-in concepts; custom concepts are checked when the experiment runs.')
    if form.target_snapshot is not None and form.target_snapshot>=profile['snapshots']:
        raise HTTPException(422,f"The target snapshot must be between 2 and {profile['snapshots']}.")
    spec = form.model_dump()
    return cached(('feasibility',json.dumps(spec,sort_keys=True)),lambda:GUIDED.feasibility(spec,guided_core(),DATA))


class GuidedCode(BaseModel):
    model_config = ConfigDict(extra='forbid')
    custom_code: str = Field(max_length=12000)


@app.post('/api/guided/validate-code')
def guided_validate_code(form: GuidedCode,request: Request):
    # Parses with the restricted interpreter only; nothing is executed here.
    session(request)
    from sandbox.restricted import Interpreter,CodeError
    import ast
    try:
        interp = Interpreter(form.custom_code,guided_core().TemporalGraphTransformation)
    except SyntaxError as error:
        return dict(ok=False,message=f'Python syntax error on line {error.lineno}: {error.msg}.',line=error.lineno)
    except (CodeError,ValueError) as error:
        return dict(ok=False,message=str(error),line=getattr(error,'lineno',None))
    tree = ast.parse(form.custom_code)
    cls = next((n.name for n in tree.body if isinstance(n,ast.ClassDef)),None)
    instance = interp.instance
    if instance.name in [n for n,_ in TRANSFORMS.values()]:
        return dict(ok=False,message=f'The name "{instance.name}" is already a built-in concept. Choose a different name.')
    mode = 'transform (all snapshots)' if 'transform' in interp.methods else 'transformGraph (each snapshot)'
    return dict(ok=True,message='Looks good! The code passed every safety and structure check.',
                details=dict(class_name=cls,name=instance.name,delta_mode=instance.deltaMode,
                             preserves_edge_count=bool(instance.preservesEdgeCount),entry=mode))


@app.post('/api/guided/experiments',status_code=202)
def guided_experiment(form: GuidedExperiment,request: Request):
    identity = session(request)
    SECURITY.rate('experiment:'+identity['username'],30,3600)
    return admit_job(identity,validate_guided(form),'guided')


@app.get('/api/guided/experiments/{job_id}')
def guided_job(job_id: str,request: Request):
    row = own_job(job_id,session(request))
    progress = None
    if row['progress']:
        try:progress = json.loads(row['progress'])
        except ValueError:progress = None
    return dict(id=row['id'],kind=row['kind'],status=row['status'],error=row['error'],progress=progress,spec=json.loads(row['spec']),
                created=row['created'],result=json.loads(row['result']) if row['result'] and row['status']=='complete' else None)


def flatten(prefix,value,out):
    if isinstance(value,dict):
        for key,item in value.items():
            flatten(f'{prefix}.{key}' if prefix else key,item,out)
    elif isinstance(value,list):
        out[prefix] = json.dumps(value,ensure_ascii=True)
    else:
        out[prefix] = value
    return out


@app.get('/api/guided/experiments/{job_id}/download/{kind}')
def guided_download(job_id: str,kind: str,request: Request):
    row = own_job(job_id,session(request))
    if row['status']!='complete' or not row['result']:
        raise HTTPException(409,'Wait for the experiment to finish.')
    result = json.loads(row['result'])
    if 'guided' not in result:
        raise HTTPException(409,'This is not a guided-study experiment.')
    g = result['guided']
    if kind=='json':
        return Response(json.dumps(result,indent=2,allow_nan=False),media_type='application/json',
                        headers={'Content-Disposition':f'attachment; filename="tgap-guided-{job_id[:8]}.json"'})
    if kind=='csv':
        # Long format: every measured row of every stage, plus one row per chart explanation.
        rows = []
        for stage,items in (('selected',result['rows']),('matrix',(g.get('matrix') or {}).get('rows',[])),
                            ('stability',(g.get('stability') or {}).get('rows',[])),('sizes',(g.get('sizes') or {}).get('rows',[]))):
            for item in items:
                rows.append(flatten('',dict(record='measurement',stage=stage,**({'model':g['spec']['model']} if stage=='selected' and 'model' not in item else {}),**item),{}))
        for panel in (g.get('temporal') or {}).get('panels',[]):
            for item in panel['rows']:
                rows.append(flatten('',dict(record='measurement',stage='temporal_local',model=panel['model'],**item),{}))
        for chart in g['charts']:
            rows.append(dict(record='chart',stage=chart['id'],status=chart['status'],paper=chart['paper'],**{f'explanation.{k}':v for k,v in chart['explanation'].items()}))
        rows.append(dict(record='conclusion',stage='overall',conclusion=g['conclusion']))
        keys = list(dict.fromkeys(k for r in rows for k in r))
        response = csv_response([{k:r.get(k) for k in keys} for r in rows],f'tgap-guided-{job_id[:8]}.csv')
        return response
    raise HTTPException(404,'Choose JSON or CSV.')


GUIDED_EVENTS = ('step_enter','step_complete','validation_error','run_submitted','run_complete','run_failed','results_viewed','export','scenario_selected')
GUIDED_STEPS = ('intro','dataset','model','transformation','review','results','pre_survey')


class GuidedEvent(BaseModel):
    model_config = ConfigDict(extra='forbid')
    event: Literal[GUIDED_EVENTS]
    step: Literal[GUIDED_STEPS]
    job_id: Optional[str] = Field(default=None,max_length=40,pattern=r'^[0-9a-f-]{36}$')
    scenario: Optional[str] = Field(default=None,max_length=60,pattern=r'^[a-z0-9_-]+$')


@app.post('/api/guided/events')
def guided_event(form: GuidedEvent,request: Request):
    identity = session(request)
    # Interaction events are research data: recorded only inside an active, consented study session.
    with db() as conn:
        study = conn.execute('SELECT id FROM studies WHERE owner=? AND finished IS NULL ORDER BY started DESC LIMIT 1',
                             (owner_key(identity['username']),)).fetchone()
        if not study:
            return dict(recorded=False,reason='No active consented study session; nothing was recorded.')
        if conn.execute('SELECT count(*) FROM guided_events WHERE study_id=?',(study['id'],)).fetchone()[0]>=2000:
            return dict(recorded=False,reason='Event limit reached for this session.')
        conn.execute('INSERT INTO guided_events(study_id,event,step,job_id,scenario,created) VALUES (?,?,?,?,?,?)',
                     (study['id'],form.event,form.step,form.job_id,form.scenario,time.time()))
    return dict(recorded=True)


##  Compare Explainers: TGAP vs CoDy (phase 2 of the guided study)  ##
# Results are precomputed offline (python -m compare_explainers batch / casebank).
# Within-participant, counterbalanced study; the observed outcome is withheld
# until every required answer of the participant is stored.

from sandbox import compare as COMPARE

COMPARE_CONSENT = 'compare-pilot-4'   # native pre-study questionnaire + ratings + final feedback


def compare_cases():
    cases,meta,problem = COMPARE.load_cases(CONFIG)
    if cases is None:
        raise HTTPException(404,problem)
    return COMPARE.study_cases(cases),meta


def compare_bank_id(meta,cases):
    # The single-case study is a new bank id, so sessions of the earlier two-case pilot are kept apart.
    return f"{meta.get('batch_id') or cases[0]['case_id']}:{'+'.join(c['case_id'] for c in cases)}:{COMPARE_CONSENT}"


def compare_session(conn,identity,bank):
    return conn.execute('SELECT * FROM cmp_sessions WHERE owner=? AND bank=?',(owner_key(identity['username']),bank)).fetchone()


def compare_state(conn,row):
    done = {(r['case_id'],r['stage']) for r in conn.execute('SELECT case_id,stage FROM cmp_responses WHERE session_id=?',(row['id'],))}
    cases = json.loads(row['case_order'])
    nxt = COMPARE.next_stage(row['method_order'],cases,done)
    pre = conn.execute('SELECT 1 FROM cmp_pre WHERE session_id=?',(row['id'],)).fetchone()
    return dict(participant=row['participant'],order=row['method_order'],cases=cases,done=sorted([list(d) for d in done]),
                next=list(nxt) if nxt else None,finished=row['finished'],recording=True,pre_done=bool(pre))


@app.get('/api/compare/scenario')
def compare_scenario(request: Request):
    identity = session(request)
    cases,meta,problem = COMPARE.load_cases(CONFIG)
    cases = COMPARE.study_cases(cases) if cases else cases
    if cases is None:
        return dict(available=False,reason=problem)
    bank = compare_bank_id(meta,cases)
    with db() as conn:
        row = compare_session(conn,identity,bank)
        state = compare_state(conn,row) if row else None
    reveal = bool(state and state['finished'])
    if not state:
        # Exploring without consent: nothing is recorded and the outcome is never shown here.
        state = dict(participant=None,order=COMPARE.assign_order(owner_key(identity['username'])),
                     cases=[c['case_id'] for c in cases],done=[],next=None,finished=None,recording=False,pre_done=False)
    return dict(available=True,session=state,page=COMPARE.bank_view(cases,meta,reveal),consent_version=COMPARE_CONSENT)


class CompareConsent(BaseModel):
    model_config = ConfigDict(extra='forbid')
    consent: bool
    pre: Optional[dict] = None


class ComparePre(BaseModel):
    model_config = ConfigDict(extra='forbid')
    pre: dict


def save_pre(conn,session_id,answers):
    # One row per session: a second submission updates it instead of adding a duplicate.
    now = time.time()
    conn.execute('INSERT INTO cmp_pre(session_id,version,answers,submitted,updated) VALUES (?,?,?,?,?) '
                 'ON CONFLICT(session_id) DO UPDATE SET version=excluded.version,answers=excluded.answers,updated=excluded.updated',
                 (session_id,COMPARE.PRE_VERSION,json.dumps(answers),now,now))


STUDY_DATA = HOME/'study-data'


def write_study_files(conn):
    """Rewrite the study files from the database after every change, so they
    always match it (withdrawn participants disappear from them too). Keyed by
    the random participant code only; no account name or e-mail."""
    STUDY_DATA.mkdir(parents=True,exist_ok=True)
    sessions = [dict(r) for r in conn.execute('SELECT participant,bank,method_order,consent_version,started,finished,id FROM cmp_sessions ORDER BY started')]
    code = {r['id']:r['participant'] for r in sessions}
    pre = []
    for r in conn.execute('SELECT * FROM cmp_pre ORDER BY submitted'):
        a = json.loads(r['answers'])
        pre.append(dict(participant=code.get(r['session_id']),version=r['version'],age=a.get('age') or '',education=a.get('education') or '',
                        **{k:(a.get('familiarity') or {}).get(k) for k,_ in COMPARE.PRE_FAMILIARITY},submitted=r['submitted'],updated=r['updated']))
    ids = list(dict.fromkeys(k for items in COMPARE.RATINGS.values() for k,_ in items))
    ratings,feedback = [],[]
    for r in conn.execute('SELECT * FROM cmp_responses ORDER BY submitted'):
        a = json.loads(r['answers'])
        base = dict(participant=code.get(r['session_id']),case_id=r['case_id'],stage=r['stage'],elapsed_seconds=r['elapsed'],submitted=r['submitted'])
        if r['stage']=='feedback':
            feedback.append(dict(base,text=a.get('text') or ''))
        else:
            for k in ids:
                if k in (a.get('ratings') or {}):
                    ratings.append(dict(base,method={'review_tgap':'tgap','review_cody':'cody'}.get(r['stage'],'side'),question_id=k,value=a['ratings'][k]))
    for r in sessions: r.pop('id')
    tables = dict(sessions=sessions,pre_survey=pre,ratings=ratings,feedback=feedback)
    for name,rows in tables.items():
        tmp = STUDY_DATA/f'.{name}.csv.tmp'
        with tmp.open('w',newline='',encoding='utf-8') as fh:
            if rows:
                w = csv.DictWriter(fh,fieldnames=list(rows[0]))
                w.writeheader(); w.writerows(rows)
        tmp.replace(STUDY_DATA/f'{name}.csv')
    questions = dict(pre=COMPARE.pre_definition(),ratings={k:[dict(id=i,text=t) for i,t in v] for k,v in COMPARE.RATINGS.items()},
                     scale=dict(range=list(COMPARE.RATING),agreement=list(COMPARE.SCALE_LABELS),familiarity=list(COMPARE.FAMILIARITY_LABELS)))
    tmp = STUDY_DATA/'.study.json.tmp'
    tmp.write_text(json.dumps(dict(written=time.time(),consent_version=COMPARE_CONSENT,questions=questions,**tables),indent=1,ensure_ascii=False),encoding='utf-8')
    tmp.replace(STUDY_DATA/'study.json')


@app.post('/api/compare/start')
def compare_start(form: CompareConsent,request: Request):
    identity = session(request)
    if not form.consent:
        raise HTTPException(422,'Consent is required to record your answers. You can still explore without joining.')
    problems = COMPARE.validate_pre(form.pre or {})
    if problems:
        raise HTTPException(422,' '.join(problems))
    cases,meta = compare_cases()
    usable = [c for c in cases if c['comparability']['comparable']]
    if not usable:
        raise HTTPException(409,'No case in the bank is verified as comparable, so the study cannot start. The cases remain viewable as a technical demonstration.')
    bank = compare_bank_id(meta,cases)
    with db() as conn:
        if not compare_session(conn,identity,bank):
            participant = 'P-'+secrets.token_hex(4).upper()
            conn.execute('INSERT INTO cmp_sessions(id,owner,participant,bank,method_order,case_order,consent_version,started) VALUES (?,?,?,?,?,?,?,?)',
                         (str(uuid.uuid4()),owner_key(identity['username']),participant,bank,COMPARE.assign_order(participant),
                          json.dumps(COMPARE.case_order(participant,[c['case_id'] for c in usable])),COMPARE_CONSENT,time.time()))
        row = compare_session(conn,identity,bank)
        if not conn.execute('SELECT 1 FROM cmp_pre WHERE session_id=?',(row['id'],)).fetchone():
            save_pre(conn,row['id'],form.pre)   # a repeated start never overwrites; edits go through /api/compare/pre
        write_study_files(conn)
    return compare_scenario(request)


@app.post('/api/compare/pre')
def compare_pre(form: ComparePre,request: Request):
    """Submit or edit the pre-study questionnaire; editable only until the first rating is saved."""
    identity = session(request)
    problems = COMPARE.validate_pre(form.pre)
    if problems:
        raise HTTPException(422,' '.join(problems))
    cases,meta = compare_cases()
    with db() as conn:
        row = compare_session(conn,identity,compare_bank_id(meta,cases))
        if not row:
            raise HTTPException(409,'Join the study first.')
        if conn.execute('SELECT 1 FROM cmp_responses WHERE session_id=?',(row['id'],)).fetchone():
            raise HTTPException(409,'The study has started, so the pre-study answers can no longer be changed.')
        save_pre(conn,row['id'],form.pre)
        write_study_files(conn)
    return compare_scenario(request)


class CompareEvent(BaseModel):
    model_config = ConfigDict(extra='forbid')
    case_id: str = Field(max_length=60,pattern=r'^[a-z0-9-]+$')
    stage: Literal['case','review_tgap','review_cody','side','feedback','finish']


@app.post('/api/compare/events')
def compare_event(form: CompareEvent,request: Request):
    identity = session(request)
    cases,meta,_ = COMPARE.load_cases(CONFIG)
    if cases is None:
        return dict(recorded=False)
    cases = COMPARE.study_cases(cases)
    with db() as conn:
        row = compare_session(conn,identity,compare_bank_id(meta,cases))
        if not row or row['finished']:
            return dict(recorded=False,reason='No active consented comparison session; nothing was recorded.')
        if conn.execute('SELECT count(*) FROM cmp_events WHERE session_id=?',(row['id'],)).fetchone()[0]>=1000:
            return dict(recorded=False,reason='Event limit reached.')
        conn.execute('INSERT INTO cmp_events(session_id,case_id,stage,created) VALUES (?,?,?,?)',(row['id'],form.case_id,form.stage,time.time()))
    return dict(recorded=True)


class CompareResponse(BaseModel):
    model_config = ConfigDict(extra='forbid')
    case_id: str = Field(max_length=60,pattern=r'^[a-z0-9-]+$')
    stage: Literal['review_tgap','review_cody','side','feedback']
    answers: dict


@app.post('/api/compare/responses')
def compare_response(form: CompareResponse,request: Request):
    identity = session(request)
    cases,meta = compare_cases()
    record = next((c for c in cases if c['case_id']==form.case_id),None)
    if record is None:
        raise HTTPException(422,'Unknown case.')
    problems = COMPARE.validate(form.stage,form.answers,record)
    if problems:
        raise HTTPException(422,' '.join(problems))
    with db() as conn:
        row = compare_session(conn,identity,compare_bank_id(meta,cases))
        if not row:
            raise HTTPException(409,'Join the comparison study first; nothing is recorded while exploring.')
        if row['finished']:
            raise HTTPException(409,'This comparison session is already complete.')
        state = compare_state(conn,row)
        if not state['pre_done']:
            raise HTTPException(409,'Please complete the "Before We Begin" questionnaire first.')
        if state['next']!=[form.case_id,form.stage]:
            raise HTTPException(409,f"Please complete the steps in order. The current step is {state['next']}.")
        now = time.time()
        entered = conn.execute('SELECT max(created) FROM cmp_events WHERE session_id=? AND case_id=? AND stage=?',
                               (row['id'],form.case_id,form.stage)).fetchone()[0]
        last = conn.execute('SELECT max(submitted) FROM cmp_responses WHERE session_id=?',(row['id'],)).fetchone()[0]
        elapsed = now-(entered or last or row['started'])
        correct = {}   # rating-only questionnaire: nothing is graded
        conn.execute('INSERT INTO cmp_responses(session_id,case_id,stage,answers,correct,elapsed,submitted) VALUES (?,?,?,?,?,?,?)',
                     (row['id'],form.case_id,form.stage,json.dumps(form.answers),json.dumps(correct),elapsed,now))
        if compare_state(conn,row)['next'] is None:
            conn.execute('UPDATE cmp_sessions SET finished=? WHERE id=?',(now,row['id']))
        write_study_files(conn)
    return compare_scenario(request)


@app.delete('/api/compare')
def compare_withdraw(request: Request):
    identity = session(request)
    with db() as conn:
        delete_compare_records(conn,owner_key(identity['username']))
        write_study_files(conn)
    return {'ok':True}


@app.get('/api/compare/download/{kind}')
def compare_download(kind: str,request: Request):
    session(request)
    cases,meta = compare_cases()
    # Downloads contain the full records (including outcomes): technical material, not participant pages.
    if kind=='json':
        return Response(json.dumps(dict(bank=meta,cases=cases),indent=2,allow_nan=False),media_type='application/json',
                        headers={'Content-Disposition':'attachment; filename="tgap-vs-cody-cases.json"'})
    if kind=='csv':
        import importlib.util
        spec = importlib.util.spec_from_file_location('compare_export',Path(CONFIG['tgap_source'])/'compare_explainers'/'export.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        rows = [dict(case_id=c['case_id'],**row) for c in cases for row in module.summaryRows(c)]
        return csv_response(rows,'tgap-vs-cody-cases.csv')
    raise HTTPException(404,'Choose JSON or CSV.')


@app.get('/api/admin/compare/summary')
def compare_summary(request: Request):
    researcher(request)
    with db() as conn:
        # Only sessions of the current questionnaire version (earlier pilots used different items).
        sessions = [dict(r) for r in conn.execute('SELECT * FROM cmp_sessions WHERE consent_version=?',(COMPARE_CONSENT,))]
        rows = [dict(participant=r['participant'],case_id=r['case_id'],stage=r['stage'],answers=json.loads(r['answers']),elapsed=r['elapsed'])
                for r in conn.execute('SELECT s.participant,r.* FROM cmp_responses r JOIN cmp_sessions s ON r.session_id=s.id WHERE s.consent_version=?',(COMPARE_CONSENT,))]
    technical = None
    root = Path(CONFIG.get('tgap_source','.'))/'output'/'compare_explainers'/'records'/'batch'
    try:
        bid = json.loads((root/'latest.json').read_text(encoding='utf-8'))['batch_id']
        technical = json.loads((root/bid/'technical_summary.json').read_text(encoding='utf-8'))
    except (OSError,ValueError,KeyError):
        technical = None
    return COMPARE.research_summary(rows,sessions,technical)


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
