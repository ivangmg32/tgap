"""Security regression tests. CAPTCHA answers are mocked only inside this test process."""
from contextlib import contextmanager
import base64
import sqlite3
import tempfile
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch
from fastapi import HTTPException
from fastapi.testclient import TestClient
from test_workbench import app, captcha_fields, spec
from sandbox.app import db, SECURITY, CONFIG
from sandbox.security import Security,hash_password,verify_password

class AuthenticationTests(unittest.TestCase):
    def setUp(self):
        self.client=TestClient(app,client=('test-'+uuid.uuid4().hex,1234))
        self.name='audit_'+uuid.uuid4().hex[:12]
        self.password='A long unique test passphrase 123!'
    def register(self,**changes):
        payload=dict(username=self.name,password=self.password,**captcha_fields(self.client,'register'))
        payload.update(changes)
        return self.client.post('/api/register',json=payload)
    def test_registration_hashed_participant_and_private(self):
        r=self.register();self.assertEqual(r.status_code,201,r.text)
        self.assertEqual(r.json()['role'],'participant')
        with db() as c:row=c.execute('SELECT * FROM registered_accounts WHERE username=?',(self.name,)).fetchone()
        self.assertNotIn(self.password,row['password_hash']);self.assertTrue(verify_password(self.password,row['password_hash']))
        self.assertEqual(self.client.get('/api/me').status_code,200)
        self.assertEqual(self.client.get('/api/admin/summary').status_code,403)
        self.client.headers['x-csrf-token']=r.json()['csrf']
        self.assertEqual(self.client.post('/api/logout').status_code,200)
        self.assertEqual(self.client.get('/api/me').status_code,401)
        r=self.client.post('/api/login',json=dict(username=self.name.upper(),password=self.password,**captcha_fields(self.client)))
        self.assertEqual(r.status_code,200,r.text)
    def test_duplicate_case_and_operator_reserved(self):
        self.assertEqual(self.register().status_code,201)
        self.assertEqual(self.register(username=self.name.upper()).status_code,409)
        self.assertEqual(self.register(username='ADMIN').status_code,409)
    def test_invalid_password_username_extra_role(self):
        for change in ({'password':'short'},{'username':'../oops'},{'role':'admin'}):
            self.assertEqual(self.register(**change).status_code,422)
    def test_captcha_required_wrong_and_single_use(self):
        self.assertEqual(self.client.post('/api/login',json=dict(username='admin',password='wrong')).status_code,422)
        fields=captcha_fields(self.client)
        payload=dict(username='admin',password='wrong',**fields)
        self.assertEqual(self.client.post('/api/login',json={**payload,'captcha_answer':'WRONG'}).status_code,400)
        self.assertEqual(self.client.post('/api/login',json=payload).status_code,400)
    def test_captcha_purpose_binding_and_expiration(self):
        fields=captcha_fields(self.client,'register')
        self.assertEqual(self.client.post('/api/login',json=dict(username='admin',password='wrong',**fields)).status_code,400)
        fields=captcha_fields(self.client)
        stranger=TestClient(app,client=('other-'+self.name,1234))
        self.assertEqual(stranger.post('/api/login',json=dict(username='admin',password='wrong',**fields)).status_code,400)
        fields=captcha_fields(self.client)
        with db() as c:c.execute('UPDATE captcha_challenges SET expires=0 WHERE id=?',(fields['captcha_id'],))
        self.assertEqual(self.client.post('/api/login',json=dict(username='admin',password='wrong',**fields)).status_code,400)
    def test_captcha_is_png_and_no_answer_leak(self):
        with patch('sandbox.security.generate_answer',return_value='ABC234'):
            r=self.client.get('/api/captcha')
        self.assertNotIn('ABC234',r.text)
        self.assertTrue(base64.b64decode(r.json()['image'].split(',')[1]).startswith(b'\x89PNG'))
        self.assertEqual(r.headers['cache-control'],'no-store')
    def test_disabled_registration_account_revokes_sessions(self):
        self.assertEqual(self.register().status_code,201)
        with db() as c:c.execute('UPDATE registered_accounts SET disabled=1 WHERE username=?',(self.name,))
        self.assertEqual(self.client.get('/api/me').status_code,401)
    def test_request_bounds_and_cross_origin(self):
        self.assertEqual(self.client.post('/api/login',content=b'x'*65537).status_code,413)
        self.assertEqual(self.client.post('/api/login',json={},headers={'origin':'http://evil.example'}).status_code,403)
        self.assertEqual(self.client.get('/api/health').status_code,200)
    def test_concurrent_duplicate_registration(self):
        from concurrent.futures import ThreadPoolExecutor
        other=TestClient(app,client=('concurrent-'+self.name,1234))
        forms=[(client,dict(username=self.name,password=self.password,**captcha_fields(client,'register'))) for client in (self.client,other)]
        with ThreadPoolExecutor(max_workers=2) as pool:
            statuses=list(pool.map(lambda pair:pair[0].post('/api/register',json=pair[1]).status_code,forms))
        self.assertEqual(sorted(statuses),[201,409])
    def test_wrong_password_and_unknown_account_use_same_error(self):
        results=[]
        for name in ('admin','missing_'+self.name):
            r=self.client.post('/api/login',json=dict(username=name,password='wrong',**captcha_fields(self.client)))
            results.append((r.status_code,r.json()))
        self.assertEqual(results[0],results[1]);self.assertEqual(results[0][0],401)

    def test_storage_exhaustion_fails_safely(self):
        r=self.register();self.assertEqual(r.status_code,201)
        self.client.headers['x-csrf-token']=r.json()['csrf']
        from types import SimpleNamespace
        with patch('sandbox.app.shutil.disk_usage',return_value=SimpleNamespace(free=1)):
            r=self.client.post('/api/experiments',json=spec())
        self.assertEqual(r.status_code,503,r.text)
        self.assertEqual(self.client.get('/api/health').status_code,200)

    @patch.dict(CONFIG,{'registration_attempts_per_ip_hour':5})
    def test_registration_throttle(self):
        for i in range(6):
            r=self.client.post('/api/register',json=dict(username=self.name,password=self.password,captcha_id='bad',captcha_answer='bad'))
            self.assertEqual(r.status_code,429 if i==5 else 400,r.text)
        self.assertIn('retry-after',r.headers)

class LimitTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.path=Path(self.temp.name)/'test.sqlite3'
        @contextmanager
        def connect():
            conn=sqlite3.connect(self.path);conn.row_factory=sqlite3.Row
            try:
                with conn:yield conn
            finally:conn.close()
        self.connect=connect;self.security=Security(connect,'test-secret')
    def tearDown(self):self.temp.cleanup()
    def test_limits_persist_across_restart(self):
        self.security.rate('probe',1,3600)
        second=Security(self.connect,'test-secret')
        with self.assertRaises(HTTPException) as error:second.rate('probe',1,3600)
        self.assertEqual(error.exception.status_code,429)
    def test_global_active_bound_and_release(self):
        for i in range(64):self.security.admit(str(i))
        with self.assertRaises(HTTPException):self.security.admit('65')
        self.security.release();self.security.admit('65')
        self.assertEqual(self.security.active,64)
    def test_peer_bound(self):
        for i in range(60):self.security.admit('same');self.security.release()
        with self.assertRaises(HTTPException):self.security.admit('same')
    def test_password_slots_are_bounded(self):
        for _ in range(4):self.security.password_slot()
        with self.assertRaises(HTTPException):self.security.verify('test',None)
        for _ in range(4):self.security.hash_slots.release()
    def test_hash_salts_and_wrong_password(self):
        first=hash_password('test passphrase');second=hash_password('test passphrase')
        self.assertNotEqual(first,second);self.assertFalse(verify_password('wrong',first))

if __name__=='__main__':unittest.main()
