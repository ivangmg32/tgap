import ast
import json
import os
from pathlib import Path
import shutil
import tempfile
import time
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT.parent if (ROOT.parent/'core').is_dir() else ROOT.parent/'tgap'
TEMP=Path(tempfile.mkdtemp(prefix='tgap-workbench-tests-'))
(TEMP/'config.json').write_text(json.dumps(dict(tgap_source=str(SOURCE),host='127.0.0.1',port=8091)),encoding='utf-8')
(TEMP/'users.txt').write_text('admin:test-admin-pass:admin\nalice:test-alice-pass:participant\nbob:test-bob-pass:participant\n',encoding='utf-8')
shutil.copytree(ROOT/'fixtures',TEMP/'data'/'datasets')
os.environ['TGAP_SANDBOX_HOME']=str(TEMP)

from fastapi.testclient import TestClient
from sandbox.app import app, POOL
from sandbox.engine import execute, CUSTOM_TEMPLATE, generated_program, load_core
from sandbox.restricted import Interpreter, CodeError


def captcha_fields(client,purpose='login'):
    with patch('sandbox.security.generate_answer',return_value='ABC234'):
        response=client.get('/api/captcha',params={'purpose':purpose})
    assert response.status_code==200,response.text
    return dict(captcha_id=response.json()['id'],captcha_answer='ABC234')


def spec(**kwargs):
    return dict(dataset='stable',model='persistence_bridge',transformations=['bridge_width','centralization','density'],
                delta=.1,seed=42,custom_code='',**kwargs)


class EngineTests(unittest.TestCase):
    def test_known_truth_and_call_count(self):
        result=execute(spec(),SOURCE,TEMP/'data')
        self.assertEqual(result['summary']['model_calls'],7)
        self.assertEqual(result['baseline'],8)
        bridge=[r for r in result['rows'] if r['concept']=='Bridge Width']
        self.assertEqual([r['impact'] for r in bridge],[8,-8])
        self.assertTrue(all(r['impact']==0 for r in result['rows'] if r['concept']!='Bridge Width'))

    def test_live_paper_figures_are_measured_and_bounded(self):
        result=execute(spec(),SOURCE,TEMP/'data')
        a=result['analyses']
        self.assertLessEqual(a['model_calls'],128)
        self.assertEqual(result['summary']['total_model_calls'],7+a['model_calls'])
        communities={n['id']:n['community'] for n in result['graph']['nodes']}
        edges=result['graph']['edges']
        self.assertIsNotNone(a['nodes'])
        self.assertIsNotNone(a['edges'])
        for row in a['nodes']['rows']:
            lost=sum(1 for u,v in edges if row['node'] in (u,v) and communities[u]!=communities[v])
            self.assertEqual(row['impact'],-lost)
        for row in a['edges']['rows']:
            lost=int((row['u'],row['v']) in edges or (row['v'],row['u']) in edges)
            lost*=int(communities[row['u']]!=communities[row['v']])
            self.assertEqual(row['impact'],-lost)
        temporal=next(p for p in a['temporal'] if p['concept']=='Bridge Width')
        self.assertEqual([r['impact'] for r in temporal['rows']],[0,0,0,0,0,1])
        for row in a['edge_time']:
            expected=-1 if row['snapshot']==5 and row['present'] and communities[row['u']]!=communities[row['v']] else 0
            self.assertEqual(row['impact'],expected)
        self.assertFalse(a['trained_seed_stability']['available'])
        self.assertTrue(a['sweep'])
        for row in a['sweep']:
            if not row['valid_for_analysis']:
                self.assertIsNone(row['impact'])

    def test_history_is_invisible_to_present_model(self):
        values=spec();values['transformations']=['bridge_trend','churn']
        result=execute(values,SOURCE,TEMP/'data')
        self.assertTrue(all(r['impact']==0 for r in result['rows'] if r['valid_for_analysis']))

    def test_figures_match_tested_transformations_without_extra_model_calls(self):
        values=spec();values['transformations']=['bridge_width','bridge_trend']
        result=execute(values,SOURCE,TEMP/'data')
        self.assertEqual(result['summary']['model_calls'],5)
        self.assertEqual(len(result['comparisons']),len(result['rows']))
        for row,comparison in zip(result['rows'],result['comparisons']):
            self.assertEqual((row['concept'],row['direction']),(comparison['concept'],comparison['direction']))
            self.assertEqual(len(comparison['trajectory']),len(result['trajectory']))
            original={tuple(sorted(e)) for e in result['graph']['edges']}
            after={tuple(sorted(e)) for e in comparison['edges']}
            self.assertEqual(after-original,{tuple(sorted(e)) for e in comparison['added']})
            self.assertEqual(original-after,{tuple(sorted(e)) for e in comparison['removed']})
            if row['concept']=='Bridge Trend':
                self.assertEqual(comparison['trajectory'][-1],result['trajectory'][-1])
            elif row['valid_for_analysis']:
                self.assertEqual(comparison['trajectory'][-1]['bridge'],row['prediction'])

    def test_custom_transformer_and_export(self):
        values=spec();values.update(custom_code=CUSTOM_TEMPLATE,model='persistence_density')
        result=execute(values,SOURCE,TEMP/'data')
        self.assertTrue(any(r['concept']=='Remove one edge' and r['impact']<0 for r in result['rows']))
        ast.parse(result['program'])

    def test_all_fixtures_and_invalid_rows(self):
        invalid=0
        for path in (TEMP/'data'/'datasets').glob('*.json'):
            values=spec();values.update(dataset=path.stem,transformations=['bridge_width','bridge_trend'],delta=.25)
            result=execute(values,SOURCE,TEMP/'data')
            for row in result['rows']:
                if not row['valid_for_analysis']:
                    invalid+=1
                    self.assertIsNone(row['impact'])
                    self.assertTrue(row['reason'])
        self.assertGreater(invalid,0)

    def test_custom_language_blocks_host_access(self):
        base=load_core(SOURCE).TemporalGraphTransformation
        for injection in ('import os\n','import subprocess\n','open("users.txt")\n'):
            with self.assertRaises(CodeError):Interpreter(injection+CUSTOM_TEMPLATE,base)
        with self.assertRaises(CodeError):Interpreter(CUSTOM_TEMPLATE.replace('g = graph.copy()','g = graph.__class__'),base)

    def test_numeric_and_collection_limits(self):
        base=load_core(SOURCE).TemporalGraphTransformation
        interpreter=Interpreter(CUSTOM_TEMPLATE,base)
        with self.assertRaises(CodeError):interpreter.binary(ast.Mult(),[1],1000000)
        with self.assertRaises(CodeError):interpreter.binary(ast.Pow(),10,100000)

    def test_generated_program_matches_builtin_configuration(self):
        values=spec();program=generated_program(values)
        self.assertIn('nPerCommunity=10',program)
        self.assertIn('valid_for_analysis',program)
        compile(program,'generated.py','exec')


class APITests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.admin=TestClient(app)
        cls.alice=TestClient(app)
        cls.bob=TestClient(app)
        for client,user in ((cls.admin,'admin'),(cls.alice,'alice'),(cls.bob,'bob')):
            response=client.post('/api/login',json=dict(username=user,password=f'test-{user}-pass',**captcha_fields(client)))
            if response.status_code!=200:raise AssertionError(response.text)
            client.headers['x-csrf-token']=response.json()['csrf']

    def job(self,client,values=None):
        response=client.post('/api/experiments',json=values or spec())
        self.assertEqual(response.status_code,202,response.text)
        job_id=response.json()['id']
        for _ in range(120):
            response=client.get('/api/experiments/'+job_id)
            if response.json()['status'] in ('complete','failed'):break
            time.sleep(.2)
        self.assertEqual(response.json()['status'],'complete',response.text)
        return job_id,response.json()

    def test_access_and_csrf(self):
        client=TestClient(app)
        self.assertEqual(client.get('/api/catalogue').status_code,401)
        self.assertEqual(self.alice.get('/api/admin/summary').status_code,403)
        self.assertEqual(self.alice.post('/api/experiments',json=spec(),headers={'x-csrf-token':'wrong'}).status_code,403)
        self.assertEqual(self.alice.post('/api/experiments',json=spec(),headers={'origin':'http://untrusted.example'}).status_code,403)

    def test_publication_access_and_actual_files(self):
        import hashlib
        client=TestClient(app)
        self.assertEqual(client.get('/api/publication').status_code,401)
        figures=self.alice.get('/api/publication').json()['figures']
        self.assertEqual(len(figures),12)
        self.assertTrue(all('superseded' not in f['id'] for f in figures))
        item=figures[0]
        path=f"/api/publication/{item['id']}/png"
        self.assertEqual(client.get(path).status_code,401)
        response=self.alice.get(path)
        self.assertTrue(response.content.startswith(b'\x89PNG'))
        self.assertEqual(hashlib.sha256(response.content).hexdigest(),item['sha256'])
        self.assertTrue(self.alice.get(f"/api/publication/{item['id']}/pdf").content.startswith(b'%PDF'))
        self.assertEqual(self.alice.get('/api/publication/users/txt').status_code,404)

    def test_private_results_and_downloads(self):
        job_id,result=self.job(self.alice)
        self.assertEqual(self.bob.get('/api/experiments/'+job_id).status_code,404)
        for kind in ('json','csv','python'):
            response=self.alice.get(f'/api/experiments/{job_id}/download/{kind}')
            self.assertEqual(response.status_code,200)
            self.assertIn('attachment',response.headers['content-disposition'])

    def test_validated_input_and_custom_import(self):
        values=spec();values['custom_code']='import os\n'+CUSTOM_TEMPLATE
        self.assertEqual(self.alice.post('/api/experiments',json=values).status_code,422)
        values=spec();values['dataset']='../../users'
        self.assertEqual(self.alice.post('/api/experiments',json=values).status_code,422)
        self.assertEqual(self.alice.post('/api/experiments',json={**spec(),'delta':-1}).status_code,422)

    def test_study_consent_timing_exports_and_withdrawal(self):
        response=self.bob.post('/api/study/start',json={'consent':False})
        self.assertEqual(response.status_code,422)
        response=self.bob.post('/api/study/start',json={'consent':True})
        self.assertEqual(response.status_code,200)
        self.assertNotIn('answer',response.json()['task'])
        for task,answer in [('bridge','increase'),('history','stay the same'),('validity','exclude it from conclusions')]:
            self.job(self.bob)
            response=self.bob.post('/api/study/answer',json=dict(task=task,answer=answer,confidence=5))
            self.assertEqual(response.status_code,200,response.text)
        values=spec();values['custom_code']=CUSTOM_TEMPLATE
        self.job(self.bob,values)
        response=self.bob.post('/api/study/finish',json=dict(ease=5,understanding=6,trust=4,feedback='=1+2'))
        self.assertEqual(response.status_code,200,response.text)
        for kind in ('sessions','responses','experiments'):
            exported=self.admin.get('/api/admin/export/'+kind)
            self.assertEqual(exported.status_code,200)
            self.assertNotIn('test-bob-pass',exported.text)
            self.assertNotIn('bob,',exported.text)
        self.assertIn("'=1+2",self.admin.get('/api/admin/export/sessions').text)
        self.assertEqual(self.bob.delete('/api/study').status_code,200)
        self.assertIsNone(self.bob.get('/api/study').json())
        self.assertEqual(self.bob.get('/api/experiments').json(),[])

    def test_account_file_reload_revokes_session(self):
        client=TestClient(app)
        with (TEMP/'users.txt').open('a',encoding='utf-8') as handle:handle.write('temporary:pw:participant\n')
        response=client.post('/api/login',json=dict(username='temporary',password='pw',**captcha_fields(client)))
        self.assertEqual(response.status_code,200)
        text=(TEMP/'users.txt').read_text(encoding='utf-8')
        (TEMP/'users.txt').write_text(text.replace('temporary:pw:participant','temporary:newpw:participant'),encoding='utf-8')
        self.assertEqual(client.get('/api/me').status_code,401)


if __name__=='__main__':
    try:unittest.main()
    finally:POOL.shutdown(wait=True);shutil.rmtree(TEMP)
