"""Plain-language reading aids for the guided-study charts (sandbox/easy.py):
every chart has an axis/colour key and two easy sentences, names carry their
"model" / "concept" suffixes, and rounding noise is never reported as a
reaction. Uses a real guided run on the bundled stable world."""
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
SOURCE = ROOT.parent if (ROOT.parent/'core').is_dir() else ROOT.parent/'tgap'

from sandbox import easy as E  # noqa: E402
from sandbox.chart_registry import INVENTORY_BY_ID  # noqa: E402
from sandbox.guided import execute_guided  # noqa: E402


class NamingTests(unittest.TestCase):
    def test_suffixes(self):
        self.assertEqual(E.model_label('persistence_bridge'), 'Bridge Width — Current Snapshot model')
        self.assertEqual(E.label_terms('Bridge Width and Density moved'), 'Bridge Width concept and Density concept moved')
        self.assertEqual(E.label_terms('the Bridge Width concept'), 'the Bridge Width concept')   # never doubled
        self.assertEqual(E.label_terms('the Bridge Width — Current Snapshot model model'), 'the Bridge Width — Current Snapshot model')

    def test_every_chart_has_a_guide(self):
        for chart_id in INVENTORY_BY_ID:
            g = E.guide(chart_id)
            self.assertTrue(g['shows'], chart_id)
            self.assertTrue(g['x'] and g['y'], chart_id)


class RunTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        spec = dict(dataset='stable', model='persistence_bridge', concept='bridge_width', direction='increase', delta=0.1, seed=42,
                    target_snapshot=None, custom_code='', sweep=dict(deltas=[0.1, 0.25], models=['persistence_bridge', 'trend_bridge', 'slope_bridge'],
                    concepts=['bridge_width', 'bridge_trend', 'density'], repeats=1, variation='transformation', matched=True, sizes=[6, 15]))
        cls.g = execute_guided(spec, SOURCE, ROOT/'fixtures', progress=lambda s, m: None)['guided']
        cls.charts = {c['id']: c for c in cls.g['charts']}

    def test_every_chart_carries_two_easy_sentences_and_a_key(self):
        for c in self.g['charts']:
            self.assertTrue(c['explanation']['easy_shows'], c['id'])
            self.assertTrue(c['explanation']['easy_result'], c['id'])
            self.assertIn('guide', c)

    def test_sentences_follow_the_data(self):
        req = self.charts['requested_vs_achieved']['explanation']['easy_result']
        self.assertIn('Bridge Width concept by 10%', req)
        self.assertIn('+12.5%', req)                     # the measured achieved change
        ts = self.charts['temporal_sensitivity']['explanation']['easy_result']
        self.assertIn('Bridge Width — Current Snapshot model did not react when only the past changed', ts)

    def test_rounding_noise_is_not_a_reaction(self):
        # The slope model's Bridge Width impacts are ~1e-16 (noise): it must be reported as not reacting.
        text = self.charts['model_separated_impacts']['explanation']['easy_result']
        self.assertIn('Bridge Width — Historical Slope model did not react', text)
        box = self.charts['boxplot']['explanation']['easy_result']
        self.assertIn('Bridge Width — Historical Slope model did not react', box)
        self.assertIn('between −8 and +8', box)         # +8/-8 is a reaction even though the middle value is 0

    def test_names_have_suffixes_in_explanations(self):
        text = ' '.join(v for c in self.g['charts'] for v in c['explanation'].values())
        self.assertNotIn('Bridge Width,', text.replace('Bridge Width concept', ''))
        self.assertNotIn('model model', text)


class ChartAuditTests(RunTests):
    """Automated chart-quality audit over a real run (chart redesign, section 14)."""
    GENERIC = {'fig. 2', 'rq1 results', 'impact distribution', 'global metrics', 'graph statistics', 'model comparison'}

    def test_every_chart_is_accounted_for_with_title_axes_and_status(self):
        from sandbox.chart_registry import CHART_META, STATUS_LABEL
        from sandbox.registry import METRICS
        self.assertEqual(set(self.charts), set(INVENTORY_BY_ID))
        for c in self.g['charts']:
            self.assertTrue(c['title'] and c['title'].lower() not in self.GENERIC, c['id'])
            self.assertEqual(c['title'], E.label_terms(CHART_META[c['id']]['title']))
            if c['id'] not in ('workflow', 'matched_comparison', 'faithfulness'):
                self.assertTrue(c['guide']['x'] and c['guide']['y'], c['id'])
            self.assertTrue(c['metric'] is None or c['metric'] in METRICS, c['id'])
            self.assertIn(c['provenance'], ('current run', 'requested sweep', 'published'))
            if c['status'] not in ('ok',):
                self.assertTrue(c['status_label'], c['id'])
            self.assertEqual(c['status_label'], STATUS_LABEL[c['status']])

    def test_published_references_are_never_current_results(self):
        for c in self.g['charts']:
            if INVENTORY_BY_ID[c['id']]['kind'] == 'blocked':
                self.assertEqual(c['provenance'], 'published')
                self.assertIn('not made for your run', c['explanation']['easy_result'])

    def test_model_names_follow_the_registry(self):
        from sandbox.registry import MODELS
        text = ' '.join(v for c in self.g['charts'] for v in c['explanation'].values()) + self.g['conclusion']
        for key, m in MODELS.items():
            self.assertNotIn(m['technical'] + ' model', text)        # old names never appear as model labels
        self.assertIn(MODELS['persistence_bridge']['name'] + ' model', text)

    def test_metric_glossary_is_complete(self):
        from sandbox.registry import METRICS
        for key, m in METRICS.items():
            for field in ('name', 'short', 'definition', 'unit', 'better', 'reading', 'formula'):
                self.assertTrue(m[field], (key, field))
            self.assertIn(m['better'], ('higher', 'lower', 'depends'))

    def test_key_finding_numbers_match_the_data(self):
        delta = self.charts['delta_sensitivity']
        vals = [r['impact'] for r in delta['data']['rows'] if r['direction'] == 'increase' and r['valid_for_analysis'] and not r['noop']]
        if len(set(vals)) == 1:
            self.assertIn('the same way', delta['explanation']['easy_result'])


if __name__ == '__main__':
    unittest.main()
