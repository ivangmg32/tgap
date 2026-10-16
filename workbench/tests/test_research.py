"""Research cohort, aggregation, export and privacy regression tests."""
import csv,io,json,time,unittest,uuid,zipfile
from fastapi.testclient import TestClient
from test_workbench import app,captcha_fields,spec
from sandbox.app import db,owner_key
class ResearchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.admin=TestClient(app,client=('research-admin',1234));cls.user=TestClient(app,client=('research-participant',1234))
        for client,name in ((cls.admin,'admin'),(cls.user,'alice')):
            r=client.post('/api/login',json=dict(username=name,password=f'test-{name}-pass',**captcha_fields(client)));assert r.status_code==200,r.text
            client.headers['x-csrf-token']=r.json()['csrf']
    def setUp(self):
        self.ids=[str(uuid.uuid4()) for _ in range(2)];self.jobs=[str(uuid.uuid4()) for _ in range(3)];self.tag='P-AUDIT-'+uuid.uuid4().hex[:6]
        self.start=1780272000 # 2026-06-01 UTC
        with db() as c:
            for i,id in enumerate(self.ids):
                c.execute('INSERT INTO studies VALUES (?,?,?,?,?,?,?,?,?,?)',(id,owner_key('alice'),self.tag+str(i),self.start+i*86400,self.start+600 if i==0 else None,'pilot-1.0','concept-guided-pilot','complete' if i==0 else 'bridge',self.start,json.dumps(dict(ease=7,understanding=5,trust=3,feedback='=1+2 <script>audit</script>')) if i==0 else None))
            for task,correct,confidence,elapsed in [('bridge',1,7,90),('history',0,3,120),('validity',1,5,180)]:
                c.execute('INSERT INTO responses(study_id,task,answer,correct,confidence,elapsed,submitted) VALUES (?,?,?,?,?,?,?)',(self.ids[0],task,'audit-answer',correct,confidence,elapsed,self.start+elapsed))
            result=dict(baseline=8,seconds=1.25,request_hash='abc123',rows=[dict(concept='Bridge Width',direction='increase',valid_for_analysis=True,noop=False,status='ok',delta_mode='relative',normalizer='achieved',achieved_delta=.125,prediction_change=1,prediction=9,impact=8),dict(concept='Bridge Width',direction='decrease',valid_for_analysis=False,noop=False,status='edge_count_infeasible',delta_mode='relative',impact=999,prediction=999,prediction_change=999,achieved_delta=999)])
            for i,id in enumerate(self.jobs):
                c.execute('INSERT INTO jobs(id,owner,status,created,spec,result,study_id) VALUES (?,?,?,?,?,?,?)',(id,owner_key('alice'),'complete' if i!=1 else 'failed',self.start+100,json.dumps(spec()),json.dumps(result) if i!=1 else None,self.ids[i] if i<2 else None))
    def tearDown(self):
        with db() as c:
            for id in self.jobs:c.execute('DELETE FROM jobs WHERE id=?',(id,))
            for id in self.ids:c.execute('DELETE FROM responses WHERE study_id=?',(id,));c.execute('DELETE FROM studies WHERE id=?',(id,))
    def report(self,**params):
        r=self.admin.get('/api/admin/report',params=dict(start='2026-06-01',end='2026-06-02',**params));self.assertEqual(r.status_code,200,r.text);return r.json()
    def test_denominators_repeated_visits_missing_and_units(self):
        r=self.report();self.assertEqual(r['summary']['sessions'],2);self.assertEqual(r['summary']['unique_participants'],1)
        self.assertEqual(r['summary']['completed'],1);self.assertEqual(r['summary']['experiments'],2);self.assertEqual(r['summary']['duration']['median'],600)
        self.assertEqual(r['charts']['tasks'][0]['accuracy'],1);self.assertEqual(r['charts']['tasks'][0]['answered'],1);self.assertEqual(r['charts']['tasks'][0]['expected'],2)
        self.assertEqual(r['charts']['tasks'][1]['accuracy'],0)
        self.assertEqual(r['charts']['ratings']['ease'][-1]['count'],1)
        self.assertIsNone(r['sessions'][0]['duration_seconds']);self.assertIsNone(r['sessions'][0]['ease'])
        invalid=next(row for row in r['impacts'] if not row['valid_for_analysis']);self.assertIsNone(invalid['impact']);self.assertIsNone(invalid['prediction'])
        self.assertEqual(r['charts']['validity'][0]['invalid'],1)
    def test_consent_privacy_and_admin_permissions(self):
        anonymous=TestClient(app)
        for path in ('/api/admin/report','/api/admin/report/download/zip','/api/admin/experiments/'+self.jobs[0]):
            self.assertEqual(anonymous.get(path).status_code,401);self.assertEqual(self.user.get(path).status_code,403)
        r=self.report();self.assertNotIn(self.jobs[2],json.dumps(r));self.assertNotIn('test-alice-pass',json.dumps(r));self.assertNotIn('"owner"',json.dumps(r))
        self.assertEqual(self.admin.get('/api/admin/experiments/'+self.jobs[2]).status_code,404)
        self.assertEqual(self.admin.get('/api/admin/experiments/'+self.jobs[0]).status_code,200)
    def test_date_and_completion_filters(self):
        self.assertEqual(self.report(status='complete')['summary']['sessions'],1)
        self.assertEqual(self.report(status='incomplete')['summary']['completed'],0)
        r=self.admin.get('/api/admin/report?start=2026-06-02&end=2026-06-02').json();self.assertEqual(r['summary']['sessions'],1)
        for query in ('start=bad','start=2026-06-02&end=2026-06-01','status=bad','end=9999-12-31'):
            self.assertEqual(self.admin.get('/api/admin/report?'+query).status_code,422)
    def test_empty_report_has_no_invented_statistics(self):
        r=self.admin.get('/api/admin/report?start=1900-01-01&end=1900-01-02').json()
        self.assertEqual(r['summary']['sessions'],0);self.assertIsNone(r['summary']['duration']['median'])
        self.assertTrue(all(t['accuracy'] is None for t in r['charts']['tasks']))
    def test_export_reproducibility_and_spreadsheet_safety(self):
        params=dict(start='2026-06-01',end='2026-06-02')
        response=self.admin.get('/api/admin/report/download/zip',params=params);self.assertEqual(response.status_code,200)
        with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
            self.assertEqual(set(archive.namelist()),{'sessions.csv','responses.csv','experiments.csv','impacts.csv','report.json','metadata.json','README.txt'})
            self.assertIn("'=1+2",archive.read('sessions.csv').decode())
            meta=json.loads(archive.read('metadata.json'));self.assertEqual(meta['filters']['start'],'2026-06-01');self.assertTrue(meta['core_sha256'])
            rows=list(csv.DictReader(io.StringIO(archive.read('impacts.csv').decode())));self.assertEqual(rows[1]['impact'],'')
        self.assertEqual(self.admin.get('/api/admin/report/download/json',params=params).json()['summary']['sessions'],2)
    def test_coverage_cap_is_explicit(self):
        prefix='coverage-'+uuid.uuid4().hex
        try:
            with db() as c:
                c.executemany('INSERT INTO studies(id,owner,participant,started,consent_version,condition,stage,stage_started) VALUES (?,?,?,?,?,?,?,?)',[(prefix+str(i),owner_key('alice'),'P-COVERAGE',3786912000,'pilot-1.0','concept-guided-pilot','bridge',3786912000) for i in range(2001)])
            r=self.admin.get('/api/admin/report?start=2090-01-01').json()
            self.assertTrue(r['coverage']['truncated']);self.assertEqual(r['coverage']['matching_sessions'],2001);self.assertEqual(r['summary']['sessions'],2000)
        finally:
            with db() as c:c.execute('DELETE FROM studies WHERE id LIKE ?',(prefix+'%',))

    def test_withdrawal_removes_future_reports_and_detail(self):
        r=self.user.delete('/api/study');self.assertEqual(r.status_code,200)
        self.assertEqual(self.report()['summary']['sessions'],0)
        self.assertEqual(self.admin.get('/api/admin/experiments/'+self.jobs[0]).status_code,404)
if __name__=='__main__':unittest.main()
