"""Failure-path regressions for bounded workers and zero-baseline units."""
import json,time,unittest,uuid
from types import SimpleNamespace
from unittest.mock import Mock,patch
from test_workbench import TEMP,SOURCE,spec
from sandbox.app import db,run_job,JOBS
from sandbox.engine import execute

class WorkerReliabilityTests(unittest.TestCase):
    def run_failure(self,kind):
        id=str(uuid.uuid4());values=spec()
        with db() as c:c.execute('INSERT INTO jobs(id,owner,status,created,spec) VALUES (?,?,?,?,?)',(id,'test-owner','queued',time.time(),json.dumps(values)))
        process=Mock();process.pid=99999999;process.poll.return_value=None if kind in ('timeout','memory') else 0
        monitor=Mock();monitor.children.return_value=[];monitor.memory_info.return_value=SimpleNamespace(rss=1024**3 if kind=='memory' else 1)
        def spawn(args,**kwargs):
            if kind=='invalid-json':__import__('pathlib').Path(args[-1]).write_text('{invalid')
            if kind=='oversized':__import__('pathlib').Path(args[-1]).write_bytes(b'x'*(4*1024*1024+1))
            return process
        with patch('sandbox.app.subprocess.Popen',side_effect=spawn),patch('sandbox.app.psutil.Process',return_value=monitor),patch('sandbox.app.time.monotonic',side_effect=[0,41] if kind=='timeout' else lambda:0):
            run_job(id,values)
        with db() as c:row=c.execute('SELECT * FROM jobs WHERE id=?',(id,)).fetchone()
        self.assertEqual(row['status'],'failed');self.assertTrue(row['error'])
        self.assertFalse((JOBS/(id+'.input.json')).exists());self.assertFalse((JOBS/(id+'.output.json')).exists())
        if kind in ('timeout','memory'):monitor.kill.assert_called_once()
        return row['error']
    def test_timeout_kills_worker(self):self.assertIn('40-second',self.run_failure('timeout'))
    def test_memory_limit_kills_worker(self):self.assertIn('768 MiB',self.run_failure('memory'))
    def test_missing_output_fails_explicitly(self):self.assertIn('bounded result',self.run_failure('missing'))
    def test_oversized_output_fails_explicitly(self):self.assertIn('bounded result',self.run_failure('oversized'))
    def test_malformed_output_fails_explicitly(self):self.run_failure('invalid-json')
    def test_zero_baseline_uses_absolute_units_and_reproducibility(self):
        fixture=TEMP/'data'/'datasets'/'audit-cycle.json'
        fixture.write_text(json.dumps(dict(nodes=[0,1,2,3],snapshots=[[[0,1],[1,2],[2,3],[3,0]]]*6,communities=[[0,1],[2,3]],community_labels=['A','B'],labels=[str(i) for i in range(6)],meta={'dataset':'audit-cycle'})))
        values=spec();values.update(dataset='audit-cycle',delta=.5,model='persistence_centralization')
        first=execute(values,SOURCE,TEMP/'data');second=execute(values,SOURCE,TEMP/'data')
        self.assertEqual(first['rows'],second['rows']);self.assertEqual(first['comparisons'],second['comparisons'])
        rows=[r for r in first['rows'] if r['concept']=='Centralization']
        self.assertTrue(rows);self.assertTrue(all(r['property_baseline']==0 and r['delta_mode']=='absolute' and r['requested_delta_mode']=='relative' for r in rows))
        fixture.unlink()

if __name__=='__main__':unittest.main()
