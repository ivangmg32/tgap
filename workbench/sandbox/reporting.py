"""Consent-scoped, descriptive research reporting. No user names or credentials."""
from collections import Counter
from datetime import datetime,timezone,timedelta
import hashlib,hmac,json,statistics,time

def date_boundary(value,end=False):
    if not value:return None
    parsed=datetime.strptime(value,'%Y-%m-%d').replace(tzinfo=timezone.utc)
    return (parsed+timedelta(days=1) if end else parsed).timestamp()

def describe(values):
    values=[v for v in values if isinstance(v,(int,float))]
    return dict(n=len(values),median=statistics.median(values) if values else None,minimum=min(values) if values else None,maximum=max(values) if values else None)

def counts(values):return [dict(label=k,count=v) for k,v in sorted(Counter(values).items(),key=lambda item:(-item[1],str(item[0])))]

def report(conn,secret,tasks,start='',end='',status='all'):
    low,high=date_boundary(start),date_boundary(end,True)
    if low is not None and high is not None and low>=high:raise ValueError('Start date must be on or before end date.')
    where=['1=1'];params=[]
    if low is not None:where.append('started>=?');params.append(low)
    if high is not None:where.append('started<?');params.append(high)
    if status=='complete':where.append('finished IS NOT NULL')
    elif status=='incomplete':where.append('finished IS NULL')
    elif status!='all':raise ValueError('Choose all, complete, or incomplete sessions.')
    clause=' AND '.join(where)
    total=conn.execute('SELECT count(*) FROM studies WHERE '+clause,params).fetchone()[0]
    raw=conn.execute('SELECT * FROM studies WHERE '+clause+' ORDER BY started DESC,id LIMIT 2000',params).fetchall()
    sessions=[];responses=[];experiments=[];impacts=[]
    for s in raw:
        participant_key='R-'+hmac.new(secret.encode(),('research:'+s['owner']).encode(),hashlib.sha256).hexdigest()[:16].upper()
        q=json.loads(s['questionnaire']) if s['questionnaire'] else {}
        sessions.append(dict(session_id=s['id'],participant=s['participant'],participant_key=participant_key,condition=s['condition'],consent_version=s['consent_version'],stage=s['stage'],started=s['started'],finished=s['finished'],duration_seconds=s['finished']-s['started'] if s['finished'] is not None else None,ease=q.get('ease'),understanding=q.get('understanding'),trust=q.get('trust'),feedback=q.get('feedback','')))
        for r in conn.execute('SELECT task,answer,correct,confidence,elapsed,submitted FROM responses WHERE study_id=? ORDER BY submitted',(s['id'],)):
            responses.append(dict(session_id=s['id'],participant=s['participant'],participant_key=participant_key,**dict(r)))
        for j in conn.execute("""SELECT id,status,created,spec,error,
          CASE WHEN json_valid(result) THEN json_extract(result,'$.baseline') END AS baseline,
          CASE WHEN json_valid(result) THEN json_extract(result,'$.seconds') END AS seconds,
          CASE WHEN json_valid(result) THEN json_extract(result,'$.rows') END AS rows,
          CASE WHEN json_valid(result) THEN json_extract(result,'$.request_hash') END AS request_hash
          FROM jobs WHERE study_id=? ORDER BY created,id""",(s['id'],)):
            spec=json.loads(j['spec'])
            experiments.append(dict(session_id=s['id'],participant=s['participant'],participant_key=participant_key,experiment_id=j['id'],created=j['created'],status=j['status'],dataset=spec['dataset'],model=spec['model'],delta=spec['delta'],seed=spec['seed'],transformations=spec['transformations'],custom=bool(spec.get('custom_code','').strip()),custom_code=spec.get('custom_code',''),baseline=j['baseline'],seconds=j['seconds'],request_hash=j['request_hash'],error=j['error']))
            for row in json.loads(j['rows'] or '[]'):
                valid=bool(row.get('valid_for_analysis',False))
                impacts.append({**dict(session_id=s['id'],participant=s['participant'],participant_key=participant_key,experiment_id=j['id'],dataset=spec['dataset'],model=spec['model'],seed=spec['seed']),**row,**({} if valid else dict(impact=None,prediction=None,prediction_change=None,achieved_delta=None))})
    task_stats=[]
    for name,task in tasks.items():
        rows=[r for r in responses if r['task']==name];correct=sum(r['correct'] for r in rows)
        task_stats.append(dict(task=name,question=task.get('question',name),answered=len(rows),expected=len(sessions),correct=correct,accuracy=correct/len(rows) if rows else None,confidence=describe([r['confidence'] for r in rows]),time=describe([r['elapsed'] for r in rows])))
    completed=[s for s in sessions if s['finished'] is not None]
    by_session=Counter(r['session_id'] for r in responses)
    ratings={key:[dict(rating=n,count=sum(s[key]==n for s in completed)) for n in range(1,8)] for key in ('ease','understanding','trust')}
    validity=[]
    for name in sorted({r['concept'] for r in impacts}):
        rows=[r for r in impacts if r['concept']==name]
        validity.append(dict(concept=name,total=len(rows),valid=sum(bool(r['valid_for_analysis']) for r in rows),invalid=sum(not r['valid_for_analysis'] for r in rows),noops=sum(bool(r['valid_for_analysis'] and r.get('noop')) for r in rows)))
    return dict(schema_version=1,generated_at=time.time(),filters=dict(start=start,end=end,status=status),coverage=dict(matching_sessions=total,included_sessions=len(sessions),limit=2000,truncated=total>len(sessions)),summary=dict(sessions=len(sessions),unique_participants=len({s['participant_key'] for s in sessions}),completed=len(completed),all_tasks=sum(by_session[s['session_id']]>=len(tasks) for s in sessions),responses=len(responses),experiments=len(experiments),completed_experiments=sum(j['status']=='complete' for j in experiments),duration=describe([s['duration_seconds'] for s in completed])),charts=dict(tasks=task_stats,ratings=ratings,datasets=counts(j['dataset'] for j in experiments),models=counts(j['model'] for j in experiments),transformations=counts(t for j in experiments for t in j['transformations']),job_statuses=counts(j['status'] for j in experiments),validity=validity,timeline=sorted(counts(datetime.fromtimestamp(s['started'],timezone.utc).strftime('%Y-%m-%d') for s in sessions),key=lambda r:r['label'])),sessions=sessions,responses=responses,experiments=experiments,impacts=impacts,notes=['Only experiments linked to explicitly consented study sessions are included.','Date filters select study starts in UTC, including all experiments linked to those sessions.','Session IDs identify visits; participant_key links repeated sessions pseudonymously. Repeated sessions/experiments are not independent participants.','Task accuracy uses submitted answers only; unanswered tasks are not scored as wrong.','Ratings are ordinal distributions, not a validated usability scale. Durations include reading, waiting and experimentation.','Concept impacts use different units. Invalid numerical values are null, never zero. No cross-concept impact ranking is computed.','These are descriptive pilot results, not causal effects, significance tests or population estimates.','Free text/custom code can contain identifying information. Review and redact before publication.'])
