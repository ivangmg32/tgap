"""Numerical and API contracts for the isolated application view."""
import json
import time
import uuid
import unittest
from unittest.mock import patch

from test_workbench import SOURCE, TEMP, app, captcha_fields, spec
from fastapi.testclient import TestClient
from sandbox.applications import execute_applications
from sandbox.engine import build, load_core, world


class ApplicationMeasurementsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.spec=spec()
        cls.result=execute_applications(cls.spec,SOURCE,TEMP/'data')

    def test_prefix_backtests_have_known_truth(self):
        f=self.result['applications']['forecast']
        self.assertEqual(f['mae'],0)
        self.assertEqual(f['next_prediction'],8)
        self.assertEqual(len(f['rows']),4)
        for row in f['rows']:
            self.assertEqual(row['prediction'],8)
            self.assertEqual(row['observed'],8)
        core=load_core(SOURCE)
        graphs,_,_,_=world(self.spec,core,TEMP/'data')
        original=core.PersistenceTemporalModel.predict
        calls=[]
        def track(model,history):
            calls.append(len(history))
            return original(model,history)
        with patch.object(core.PersistenceTemporalModel,'predict',track):
            from sandbox.applications import application_measurements
            application_measurements(self.spec,SOURCE,TEMP/'data',self.result)
        self.assertEqual(calls[:5],[2,3,4,5,6])

    def test_visual_scenarios_match_exact_evaluated_transformations(self):
        r=self.result
        base={frozenset(e) for e in r['graph']['edges']}
        for s in r['applications']['scenarios']:
            comparison=next(c for c in r['comparisons'] if (c['concept'],c['direction'])==(s['concept'],s['direction']))
            last=s['windows'][-1]
            after={frozenset(e) for e in last['edges']}
            self.assertEqual(after,{frozenset(e) for e in comparison['edges']})
            self.assertEqual(after-base,{frozenset(e) for e in last['added']['edges']})
            self.assertEqual(base-after,{frozenset(e) for e in last['removed']['edges']})
            if s['valid']:
                row=next(v for v in r['rows'] if (v['concept'],v['direction'])==(s['concept'],s['direction']))
                self.assertEqual(s['after']['bridge'],row['prediction'])

    def test_stress_test_uses_fixed_cohort_and_zero_reference(self):
        a=self.result['applications']
        self.assertEqual(a['robustness'][0]['prediction'],self.result['baseline'])
        self.assertEqual(a['robustness'][0]['disabled_nodes'],0)
        previous=1
        for row in a['robustness']:
            self.assertLessEqual(row['largest_component'],previous)
            previous=row['largest_component']
        self.assertEqual(len(a['network']['nodes']),self.result['summary']['nodes'])
        json.dumps(self.result,allow_nan=False)

    def test_temporal_changes_and_slope_are_not_mislabeled_forecasts(self):
        values=spec();values.update(model='slope_bridge',transformations=['bridge_trend','churn'])
        r=execute_applications(values,SOURCE,TEMP/'data')
        self.assertFalse(r['applications']['forecast']['available'])
        self.assertIsNone(r['applications']['forecast']['next_prediction'])
        for s in r['applications']['scenarios']:
            self.assertEqual(s['before'],s['after'])
            self.assertEqual(s['windows'][-1]['added']['total'],0)
            self.assertEqual(s['windows'][-1]['removed']['total'],0)

    def test_real_data_invalidity_sampling_and_provenance(self):
        values=spec();values.update(dataset='decentraland',model='trend_bridge',transformations=['bridge_width','bridge_trend'],delta=.5)
        r=execute_applications(values,SOURCE,TEMP/'data')
        a=r['applications']
        self.assertTrue(any(not s['valid'] for s in a['scenarios']))
        self.assertEqual(len(a['provenance']['fixture_sha256']),64)
        self.assertLessEqual(len(a['network']['nodes']),100)
        for window in a['network']['windows']:
            self.assertLessEqual(window['shown'],2000)
            self.assertLessEqual(window['shown'],window['total'])
        json.dumps(r,allow_nan=False)


class ApplicationApiTests(unittest.TestCase):
    def login(self,client,username='alice',password='test-alice-pass'):
        response=client.post('/api/login',json=dict(username=username,password=password,**captcha_fields(client)))
        self.assertEqual(response.status_code,200,response.text)
        return {'X-CSRF-Token':response.json()['csrf']}

    def test_auth_validation_dispatch_and_no_study_link(self):
        from sandbox.app import db, owner_key
        with TestClient(app) as client:
            self.assertEqual(client.post('/api/applications/experiments',json=spec()).status_code,401)
            headers=self.login(client)
            self.assertEqual(client.post('/api/applications/experiments',json=spec()).status_code,403)
            invalid=spec();invalid['transformations']=[]
            self.assertEqual(client.post('/api/applications/experiments',json=invalid,headers=headers).status_code,422)
            invalid=spec();invalid['custom_code']='x=1'
            self.assertEqual(client.post('/api/applications/experiments',json=invalid,headers=headers).status_code,422)
            study_id=str(uuid.uuid4())
            with db() as conn:
                conn.execute('INSERT INTO studies(id,owner,participant,started,consent_version,condition,stage_started) VALUES (?,?,?,?,?,?,?)',
                             (study_id,owner_key('alice'),'app-test',time.time(),'test','test',time.time()))
            with patch('sandbox.app.POOL.submit') as submit:
                response=client.post('/api/applications/experiments',json=spec(),headers=headers)
            self.assertEqual(response.status_code,202,response.text)
            job=response.json()['id']
            self.assertEqual(submit.call_args.args[-1],'applications')
            with db() as conn:
                row=conn.execute('SELECT * FROM jobs WHERE id=?',(job,)).fetchone()
                self.assertEqual(row['kind'],'applications')
                self.assertIsNone(row['study_id'])
                conn.execute("UPDATE jobs SET status='failed' WHERE id=?",(job,))
            self.assertNotIn(job,[v['id'] for v in client.get('/api/experiments').json()])
            self.assertIn(job,[v['id'] for v in client.get('/api/applications/experiments').json()])
            with db() as conn:
                conn.execute('DELETE FROM studies WHERE id=?',(study_id,))
            client.post('/api/logout',headers=headers)
            self.login(client,'bob','test-bob-pass')
            self.assertEqual(client.get('/api/experiments/'+job).status_code,404)


if __name__=='__main__':unittest.main()
