"""Tests for the Guided TGAP User Study: computation, chart mapping,
interpretation and the API flow. Uses the real research library and the
bundled fixtures; no result is mocked."""
import copy
import json
import os
from pathlib import Path
import shutil
import tempfile
import time
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT.parent if (ROOT.parent/'core').is_dir() else ROOT.parent/'tgap'
# Share the existing suite's isolated test home (config, users, fixtures).
try:
    import test_workbench  # noqa: F401  (discover: tests/ is on sys.path)
except ImportError:
    from tests import test_workbench  # noqa: F401
HOME = Path(os.environ['TGAP_SANDBOX_HOME'])
with open(HOME/'users.txt', 'a', encoding='utf-8') as users:
    users.write('\ngcarol:test-gcarol-pass:participant\ngdave:test-gdave-pass:participant\n')

from fastapi.testclient import TestClient  # noqa: E402
from sandbox.app import app  # noqa: E402
from sandbox.chart_registry import INVENTORY, INVENTORY_BY_ID, quartiles  # noqa: E402
from sandbox.engine import CUSTOM_TEMPLATE, MODELS, TRANSFORMS, generated_program  # noqa: E402
from sandbox.guided import execute_guided, stable_hash  # noqa: E402
from sandbox.interpret import overall_conclusion, experiment_status, fmt  # noqa: E402

DATA = HOME/'data'
PARTS = ('what', 'conditions', 'observations', 'pattern', 'conclusion', 'caution')


def guided_spec(**overrides):
    sweep = dict(deltas=[0.1, 0.25], models=['persistence_bridge', 'trend_bridge', 'slope_bridge'],
                 concepts=['bridge_width', 'bridge_trend', 'density'], repeats=1, variation='transformation', matched=False, sizes=[])
    sweep.update(overrides.pop('sweep', {}))
    spec = dict(dataset='stable', model='persistence_bridge', concept='bridge_width', direction='increase', delta=0.1, seed=42,
                target_snapshot=None, custom_code='', sweep=sweep)
    spec.update(overrides)
    return spec


class GuidedEngineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.stages = []
        cls.result = execute_guided(guided_spec(sweep=dict(sizes=[6, 15])), SOURCE, DATA, progress=lambda s, m: cls.stages.append(s))
        cls.g = cls.result['guided']
        cls.charts = {c['id']: c for c in cls.g['charts']}

    def test_known_truth_is_recovered(self):
        # Present-only bridge model on the stable world: impact equals +-8 (paper RQ1/RQ5).
        self.assertEqual(self.result['baseline'], 8)
        self.assertEqual(self.g['primary']['impact'], 8)
        delta = self.charts['delta_sensitivity']['data']['rows']
        self.assertTrue(all(r['impact'] == (8 if r['direction'] == 'increase' else -8) for r in delta if r['valid_for_analysis']))
        # RQ2: Bridge Trend leaves the present-only model at exactly zero; the slope model reads +-1.
        trend = self.charts['temporal_sensitivity']['data']['rows']
        persistence = [r for r in trend if r['model'] == 'persistence_bridge' and r['valid_for_analysis']]
        slope = [r for r in trend if r['model'] == 'slope_bridge' and r['valid_for_analysis'] and abs(r['delta']-0.1) < 1e-9]
        self.assertTrue(persistence and all(r['impact'] == 0 for r in persistence))
        self.assertEqual(sorted(round(r['impact'], 9) for r in slope), [-1, 1])

    def test_matrix_matches_the_explainer_and_call_budget(self):
        m = self.g['matrix']
        self.assertEqual(len(m['rows']), 3*3*2*2)   # models x concepts x deltas x directions
        self.assertTrue(all(c['measured'] == c['expected'] == 1+2*3 for c in m['calls']))
        for row in m['rows']:
            if row['valid_for_analysis'] and not row['noop']:
                self.assertAlmostEqual(row['impact'], row['prediction_change']/abs(row['achieved_delta']))
                self.assertAlmostEqual(row['impact_requested_normalization'], row['prediction_change']/abs(row['requested_delta']))
            if not row['valid_for_analysis']:
                self.assertIsNone(row['impact'])
                self.assertIsNone(row['prediction'])

    def test_every_inventory_entry_has_a_chart_with_a_full_explanation(self):
        self.assertEqual(set(self.charts), set(INVENTORY_BY_ID))
        for chart in self.g['charts']:
            for part in PARTS:
                self.assertTrue(chart['explanation'][part].strip(), (chart['id'], part))
            if chart['status'] == 'ok':
                self.assertIsNotNone(chart['data'], chart['id'])
        self.assertEqual(self.charts['tgn_seed_stability']['status'], 'blocked')
        self.assertEqual(self.charts['faithfulness']['status'], 'blocked')
        self.assertEqual(self.charts['matched_comparison']['status'], 'not_requested')

    def test_inventory_accounts_for_every_paper_figure(self):
        manifest = json.loads((ROOT/'publication'/'manifest.json').read_text(encoding='utf-8'))
        mapped = {item['paper_figure'] for item in INVENTORY if item['paper_figure']}
        self.assertEqual({f['id'] for f in manifest['figures']}, mapped)
        papers = ' '.join(item['paper'] for item in INVENTORY)
        for number in range(1, 13):
            self.assertIn(f'Fig. {number}', papers)
        for item in INVENTORY:
            if item['kind'] == 'blocked':
                self.assertTrue(item.get('blocked'), item['id'])
            for key in ('caption', 'source', 'question', 'axes', 'requires', 'multi_run', 'display', 'implementation'):
                self.assertTrue(item[key], (item['id'], key))

    def test_stability_sizes_and_progress(self):
        stability = self.g['stability']
        self.assertTrue(stability['deterministic_repeat'])
        self.assertEqual(stability['seeds'], [42, 43])
        sizes = self.charts['graph_size']
        self.assertEqual(sizes['status'], 'ok')
        self.assertEqual({r['n_per_community'] for r in sizes['data']['rows']}, {6, 15})
        self.assertTrue(all(r['edge_count_preserved'] for r in sizes['data']['rows']))
        for stage in ('validate', 'main', 'matrix', 'temporal', 'stability', 'sizes', 'structure', 'charts'):
            self.assertIn(stage, self.stages)

    def test_temporal_local_and_structure_are_measured(self):
        panel = next(p for p in self.g['temporal']['panels'] if p['model'] == 'persistence_bridge')
        # Present-only: only the last snapshot can matter; its change equals one added bridge.
        self.assertEqual([r['impact'] for r in panel['rows']], [0, 0, 0, 0, 0, 1])
        matrix = self.charts['bridge_matrix']['data']['directions']
        self.assertEqual(matrix['increase']['bridge_matrix'][0]['after']-matrix['increase']['bridge_matrix'][0]['before'], 1)
        view = self.g['structure']['view']
        self.assertEqual(len(view['snapshots']), 6)

    def test_conclusion_and_provenance(self):
        self.assertEqual(self.g['experiment_status']['code'], 'responded')
        self.assertIn('sensitive to Bridge Width', self.g['conclusion'])
        self.assertIn('does not show that Bridge Width causes', self.g['conclusion'])
        self.assertEqual(self.g['config_hash'], stable_hash(self.g['spec']))
        self.assertEqual(self.g['provenance']['seed'], 42)
        self.assertTrue(self.g['provenance']['core_sha256'])
        json.dumps(self.result, allow_nan=False)


class GuidedRealDataTests(unittest.TestCase):
    def test_validity_reproduces_paper_table5_rates(self):
        # Validity is model-independent, so one model's 30 rows x 6 models equal Table 5.
        spec = guided_spec(dataset='email_eu_core', sweep=dict(deltas=[0.1, 0.25, 0.5], models=['persistence_bridge'],
                           concepts=list(TRANSFORMS), repeats=0))
        g = execute_guided(spec, SOURCE, DATA)['guided']
        counts = next(c for c in g['charts'] if c['id'] == 'validity_map')['data']['counts']
        self.assertEqual((counts['total']*6, counts['valid']*6, counts['edge_count_infeasible']*6, counts['saturated']*6), (180, 138, 30, 12))

    def test_target_snapshot_against_request_is_flagged(self):
        # tgbl_wiki's last snapshot has 0 bridges; the width-one floor raises it to 1
        # even under "decrease", so the response must not be reported as a plain success.
        spec = guided_spec(dataset='tgbl_wiki', direction='decrease', delta=0.31,
                           sweep=dict(models=['persistence_bridge'], concepts=['bridge_width', 'bridge_trend'], deltas=[0.1], repeats=0))
        g = execute_guided(spec, SOURCE, DATA)['guided']
        self.assertEqual((g['target_check']['before'], g['target_check']['after'], g['target_check']['against']), (0.0, 1.0, True))
        self.assertEqual(g['experiment_status']['code'], 'target_against')
        self.assertIn('against the request', g['conclusion'])
        self.assertNotIn('supports the statement', g['conclusion'])
        ts = next(c for c in g['charts'] if c['id'] == 'temporal_sensitivity')
        self.assertEqual(ts['data']['shown_delta'], 0.1)

    def test_target_snapshot_window(self):
        spec = guided_spec(target_snapshot=3, sweep=dict(models=['persistence_bridge'], concepts=['bridge_width'], deltas=[0.1], repeats=0))
        result = execute_guided(spec, SOURCE, DATA)
        self.assertEqual(result['summary']['snapshots'], 4)
        self.assertIn('snapshots = snapshots[:4]', result['program'])

    def test_custom_concept(self):
        spec = guided_spec(concept='custom', model='persistence_density', custom_code=CUSTOM_TEMPLATE,
                           sweep=dict(models=['persistence_density'], concepts=['density'], deltas=[0.1], repeats=1))
        g = execute_guided(spec, SOURCE, DATA)['guided']
        self.assertEqual(g['selected_concept'], 'Remove one edge')
        self.assertIn('Remove one edge', g['matrix']['concepts'])


class InterpretationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.result = execute_guided(guided_spec(sweep=dict(models=['persistence_bridge'], concepts=['bridge_width'], deltas=[0.1], repeats=0)), SOURCE, DATA)

    def context(self, **primary):
        g = self.result['guided']
        ctx = dict(spec=g['spec'], main=self.result, primary=dict(g['primary'], **primary), selected=g['selected_concept'],
                   matrix=g['matrix'], labels=g['snapshot_labels'], errors=[], charts=g['charts'])
        ctx['status'] = experiment_status(ctx)
        return ctx

    def test_invalid_primary_never_yields_a_positive_conclusion(self):
        ctx = self.context(valid_for_analysis=False, status='edge_count_infeasible', reason='Edge budget broken.', impact=None,
                           prediction=None, prediction_change=None, achieved_delta=None)
        self.assertEqual(ctx['status']['code'], 'invalid')
        text = overall_conclusion(ctx)
        self.assertIn('cannot support a conclusion', text)
        self.assertNotIn('supports the statement', text)
        self.assertNotIn('a normalized impact of', text)

    def test_noop_and_no_response_are_distinct(self):
        noop = self.context(noop=True, prediction_change=0, impact=0)
        self.assertEqual(noop['status']['code'], 'no_op')
        self.assertIn('no-op', overall_conclusion(noop))
        flat = self.context(prediction_change=0, impact=0)
        self.assertEqual(flat['status']['code'], 'no_response')
        self.assertIn('did not respond', overall_conclusion(flat))

    def test_failed_stages_are_disclosed(self):
        ctx = self.context()
        ctx['errors'] = [dict(stage='matrix', error='RuntimeError: x')]
        ctx['status'] = experiment_status(ctx)
        self.assertIn('Some computations failed (matrix)', overall_conclusion(ctx))

    def test_explanations_quote_computed_values(self):
        chart = next(c for c in self.result['guided']['charts'] if c['id'] == 'delta_sensitivity')
        self.assertIn('+8', chart['explanation']['observations'])
        self.assertNotIn('significant', json.dumps([c['explanation'] for c in self.result['guided']['charts']]).lower())

    def test_helpers(self):
        self.assertEqual(fmt(0.123456), '0.1235')
        self.assertEqual(fmt(-3, True), '-3')
        self.assertEqual(fmt(None), 'n/a')
        self.assertEqual(quartiles([-36.0, 36.0])['median'], 0)


class GuidedAPITests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.clients = {}
        for user in ('gcarol', 'gdave'):
            client = TestClient(app)
            with patch('sandbox.security.generate_answer', return_value='ABC234'):
                captcha = client.get('/api/captcha', params={'purpose': 'login'}).json()
            response = client.post('/api/login', json=dict(username=user, password=f'test-{user}-pass', captcha_id=captcha['id'], captcha_answer='ABC234'))
            assert response.status_code == 200, response.text
            client.headers['x-csrf-token'] = response.json()['csrf']
            cls.clients[user] = client
        cls.carol, cls.dave = cls.clients['gcarol'], cls.clients['gdave']

    def run_job(self, client, spec):
        response = client.post('/api/guided/experiments', json=spec)
        self.assertEqual(response.status_code, 202, response.text)
        job_id = response.json()['id']
        for _ in range(600):
            data = client.get('/api/guided/experiments/'+job_id).json()
            if data['status'] in ('complete', 'failed'):
                break
            time.sleep(.2)
        self.assertEqual(data['status'], 'complete', data.get('error'))
        return job_id, data

    def test_catalogue_preview_and_feasibility(self):
        self.assertEqual(TestClient(app).get('/api/guided/catalogue').status_code, 401)
        data = self.carol.get('/api/guided/catalogue').json()
        email = next(d for d in data['datasets'] if d['id'] == 'email_eu_core')
        self.assertEqual((email['snapshots'], email['nodes'], email['community_sizes']), (12, 201, [109, 92]))
        self.assertEqual({m['id'] for m in data['models']}, set(MODELS))
        self.assertEqual({c['id'] for c in data['concepts']}, set(TRANSFORMS))
        self.assertTrue(data['inventory']['charts'])
        preview = self.carol.post('/api/guided/preview', json=dict(dataset='stable', target_snapshot=2)).json()
        self.assertEqual(preview['snapshots_used'], 3)
        self.assertEqual(next(o for o in preview['outputs'] if o['model'] == 'persistence_bridge')['prediction'], 8)
        check = self.carol.post('/api/guided/feasibility', json=dict(dataset='decentraland', concept='bridge_trend', delta=0.1)).json()
        self.assertEqual([d['status'] for d in check['directions']], ['saturated', 'edge_count_infeasible'])
        self.assertEqual(self.carol.post('/api/guided/preview', json=dict(dataset='stable', target_snapshot=6)).status_code, 422)

    def test_validation_rejects_incompatible_configurations(self):
        bad = [guided_spec(dataset='email_eu_core', sweep=dict(variation='graph')),
               guided_spec(dataset='email_eu_core', sweep=dict(sizes=[6])),
               guided_spec(concept='custom'),
               guided_spec(custom_code=CUSTOM_TEMPLATE),
               guided_spec(target_snapshot=6),
               guided_spec(model='unknown'),
               guided_spec(sweep=dict(deltas=[0.1, 0.1])),
               guided_spec(sweep=dict(sizes=[7]))]
        for spec in bad:
            response = self.carol.post('/api/guided/experiments', json=spec)
            self.assertEqual(response.status_code, 422, spec)
            self.assertTrue(response.json()['detail'])

    def test_run_poll_download_and_history(self):
        spec = guided_spec(sweep=dict(models=['persistence_bridge', 'slope_bridge'], concepts=['bridge_width', 'bridge_trend'], deltas=[0.1], repeats=1))
        job_id, data = self.run_job(self.dave, spec)
        g = data['result']['guided']
        self.assertEqual(g['spec']['dataset'], 'stable')
        self.assertEqual(g['config_hash'], stable_hash(g['spec']))
        self.assertEqual(data['spec']['transformations'], ['bridge_width'])
        csv_text = self.dave.get(f'/api/guided/experiments/{job_id}/download/csv').text
        self.assertIn('Overall', csv_text.replace('overall', 'Overall'))
        self.assertIn('explanation.conclusion', csv_text)
        self.assertEqual(json.loads(self.dave.get(f'/api/guided/experiments/{job_id}/download/json').text)['guided']['conclusion'], g['conclusion'])
        self.assertEqual(self.carol.get(f'/api/guided/experiments/{job_id}').status_code, 404)  # private to the owner
        history = self.dave.get('/api/experiments').json()
        self.assertEqual(next(h for h in history if h['id'] == job_id)['kind'], 'guided')

    def test_events_require_consent_and_are_withdrawn(self):
        event = dict(event='step_enter', step='dataset')
        self.assertFalse(self.carol.post('/api/guided/events', json=event).json()['recorded'])
        self.assertEqual(self.carol.post('/api/guided/events', json=dict(event='free text', step='dataset')).status_code, 422)
        self.assertEqual(self.carol.post('/api/study/start', json=dict(consent=True)).status_code, 200)
        self.assertTrue(self.carol.post('/api/guided/events', json=event).json()['recorded'])
        self.assertEqual(self.carol.delete('/api/study').status_code, 200)
        from sandbox.app import db
        with db() as conn:
            self.assertEqual(conn.execute('SELECT count(*) FROM guided_events').fetchone()[0], 0)


if __name__ == '__main__':
    unittest.main()


class CustomSampleTests(unittest.TestCase):
    """Every starter shown to participants must pass the interpreter and run."""

    def test_skeleton_and_samples_run_in_both_directions(self):
        from sandbox.custom_samples import SAMPLES, SKELETON
        from sandbox.engine import execute
        for code in [SKELETON] + [s['code'] for s in SAMPLES]:
            result = execute(dict(dataset='stable', model='persistence_density', transformations=[], delta=0.1, seed=42, custom_code=code), SOURCE, DATA)
            self.assertTrue(all(r['status'] == 'ok' for r in result['rows']))
        for sample in SAMPLES:
            result = execute(dict(dataset='stable', model='trend_bridge', transformations=[], delta=0.1, seed=42, custom_code=sample['code']), SOURCE, DATA)
            self.assertTrue(all(r['measured_achieved_delta'] if 'measured_achieved_delta' in r else r['achieved_delta'] for r in result['rows']), sample['id'])

    def test_validate_code_endpoint(self):
        from sandbox.custom_samples import SAMPLES
        client = GuidedAPITests.clients['gcarol'] if hasattr(GuidedAPITests, 'clients') else None
        if client is None:
            GuidedAPITests.setUpClass(); client = GuidedAPITests.clients['gcarol']
        ok = client.post('/api/guided/validate-code', json=dict(custom_code=SAMPLES[0]['code'])).json()
        self.assertTrue(ok['ok']); self.assertEqual(ok['details']['name'], 'Edge volume')
        bad = client.post('/api/guided/validate-code', json=dict(custom_code='import os\nclass X: pass')).json()
        self.assertFalse(bad['ok']); self.assertTrue(bad['message'])
        clash = client.post('/api/guided/validate-code', json=dict(custom_code=SAMPLES[0]['code'].replace('"Edge volume"', '"Density"'))).json()
        self.assertFalse(clash['ok'])
