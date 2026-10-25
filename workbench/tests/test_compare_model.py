"""Compare Explainers: page model, wording, answer keys and study design.
Pure functions over the REAL saved demonstration record; negative and
multi-case situations are made by editing copies of it."""
import copy
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
SOURCE = ROOT.parent if (ROOT.parent/'core').is_dir() else ROOT.parent/'tgap'
from sandbox import compare as C  # noqa: E402

POINTER = SOURCE/'output'/'compare_explainers'/'latest.json'


def demo():
    cases, meta, problem = C.load_cases({'compare_latest': str(POINTER), 'compare_casebank': '/nonexistent'})
    assert cases, problem
    return cases[0]


@unittest.skipUnless(POINTER.is_file(), 'no saved pilot record')
class ExplanationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.r = demo()
        cls.view = C.case_view(cls.r)

    def test_score_differences_come_from_raw_values(self):
        t = self.view['tgap']
        d = next(x for x in self.r['tgap']['directions'] if x['direction'] == 'Increase')
        p0, p1 = d['original_probability'], d['modified_probability']
        self.assertEqual(C.score(p0), f'{100 * p0:.2f}%')
        self.assertEqual(C.points(p0, p1), f"+{100 * (p1 - p0):.2f} points")   # 54.04 -> 54.17 is +0.13, not "+0.1"
        self.assertEqual(t['score_change_text'], C.points(t['original_score'], t['resulting_score']))

    def test_requested_and_achieved_are_separate(self):
        t = self.view['tgap']
        d = next(x for x in self.r['tgap']['directions'] if x['direction'] == self.r['tgap']['primary_direction'])
        self.assertEqual(t['requested_change'], d['requested_delta'])
        self.assertEqual(t['achieved_change'], d['achieved_delta'])
        self.assertIn(f"requested a {100 * abs(d['requested_delta']):.0f}% reduction", t['summary'])
        self.assertIn(f"achieved a {100 * abs(d['achieved_delta']):.1f}% reduction", t['summary'])

    def test_unsuccessful_cody_is_never_called_successful(self):
        c = self.view['cody']
        self.assertEqual(c['state'], 'no_class_change')
        self.assertTrue(c['summary'].startswith('No class-flipping counterfactual found within the search budget.'))
        self.assertNotIn('Valid', c['state_label'])
        self.assertEqual(C.keys(self.r, 'cody')['c'], 2)         # "searched ... did not find one"

    def test_both_methods_share_the_same_structure(self):
        common = {'summary', 'investigated', 'original_score', 'resulting_score', 'class_changed', 'conclude', 'cannot', 'details', 'threshold'}
        self.assertLessEqual(common, set(self.view['tgap']))
        self.assertLessEqual(common, set(self.view['cody']))
        self.assertNotIn('questions', self.view)                 # rating-only questionnaire
        self.assertEqual([k for k, _ in C.RATINGS['tgap']], [k for k, _ in C.RATINGS['cody']])
        self.assertEqual(len(C.RATINGS['tgap']), 4)
        self.assertEqual(len(C.RATINGS['side']), 2)

    def test_validation_is_ratings_only(self):
        good = dict(ratings={k: 3 for k, _ in C.RATINGS['tgap']})
        self.assertEqual(C.validate('review_tgap', good), [])
        self.assertTrue(C.validate('review_tgap', dict(good, a=0)))                       # no multiple-choice answers
        self.assertTrue(C.validate('review_cody', dict(ratings={k: 8 for k, _ in C.RATINGS['cody']})))
        self.assertEqual(C.validate('side', dict(ratings={'side_helped': 0, 'side_describe': 7})), [])
        self.assertEqual(C.validate('feedback', dict(text='')), [])
        self.assertTrue(C.validate('feedback', dict(text='x', preference='TGAP')))

    def test_terminology_is_model_score_with_threshold(self):
        text = json.dumps(self.view)
        self.assertNotIn('probability that', text.lower())
        self.assertNotIn('more confident', text)
        self.assertEqual(self.view['original']['threshold'], 0.5)

    def test_outcome_hidden_until_revealed(self):
        self.assertNotIn('outcome', self.view)
        self.assertNotIn('did send a message', json.dumps(self.view))
        self.assertIn('outcome', C.case_view(self.r, reveal=True))

    def test_keys_follow_the_record(self):
        k = C.keys(self.r, 'tgap')
        self.assertEqual(k['b'], 1)          # score down, class unchanged
        self.assertEqual(k['c'], 0)          # moved, no flip
        self.assertEqual(C.grade(self.r, 'tgap', {'a': 0, 'b': 1, 'c': 0}), {'a': True, 'b': True, 'c': True})

    def test_timeout_and_no_result_stay_distinct_and_unfilled(self):
        timeout, none = copy.deepcopy(self.r), copy.deepcopy(self.r)
        for rec, status in ((timeout, 'timeout'), (none, 'no_counterfactual')):
            rec['cody'].update(status=status, events=[], event_count=0, counterfactual_probability_exact=None)
        a, b = C.cody_explanation(timeout), C.cody_explanation(none)
        self.assertNotEqual(a['state_label'], b['state_label'])
        self.assertIsNone(a['resulting_score'])
        self.assertIsNone(a['resulting_score_text'])
        self.assertEqual(C.keys(timeout, 'cody')['c'], 4)
        self.assertEqual(C.keys(none, 'cody')['c'], 2)
        self.assertEqual(C.keys(timeout, 'cody')['b'], 5)

    def test_noop_and_invalid_tgap_are_not_zero_effects(self):
        noop = copy.deepcopy(self.r)
        d = next(x for x in noop['tgap']['directions'] if x['direction'] == 'Decrease')
        d.update(status='noop', modified_probability=d['original_probability'], prediction_change=0.0, class_changed=False)
        e = C.tgap_explanation(noop)
        self.assertIn('no-op', e['summary'])
        self.assertIn('not a zero-effect', e['summary'])
        self.assertEqual(C.keys(noop, 'tgap')['c'], 4)

    def test_valid_cody_flip(self):
        flip = copy.deepcopy(self.r)
        flip['cody'].update(status='valid_counterfactual', counterfactual_probability_exact=0.31, event_count=2)
        e = C.cody_explanation(flip)
        self.assertTrue(e['class_changed'])
        self.assertEqual(C.keys(flip, 'cody'), {'a': 0, 'b': 0, 'c': 1})

    def test_unverified_comparison_is_labelled(self):
        bad = copy.deepcopy(self.r)
        bad['comparability'].update(comparable=False, label='NOT COMPARABLE', reasons=['weights differ'])
        self.assertFalse(C.case_view(bad)['verification']['verified'])


class DesignTests(unittest.TestCase):
    def test_order_is_reproducible_and_balanced(self):
        self.assertEqual(C.assign_order('P-1'), C.assign_order('P-1'))
        share = [C.assign_order('P-%08X' % i) for i in range(4000)].count('tgap_first') / 4000
        self.assertTrue(0.46 < share < 0.54, share)

    def test_case_order_and_stage_sequence(self):
        cases = ['uci-1', 'uci-2', 'uci-3']
        self.assertEqual(sorted(C.case_order('P-A', cases)), cases)
        self.assertEqual(C.case_order('P-A', cases), C.case_order('P-A', cases))
        seq = C.stage_sequence('cody_first', ['x', 'y'])
        self.assertEqual(seq[:4], [('x', 'review_cody'), ('x', 'review_tgap'), ('x', 'side'), ('x', 'feedback')])
        self.assertEqual(C.next_stage('tgap_first', ['x'], {('x', 'review_tgap')}), ('x', 'review_cody'))

    def test_paired_summary(self):
        rows = []
        for p in ('P-1', 'P-2'):
            for m, v in (('tgap', 6), ('cody', 4)):
                rows.append(dict(participant=p, case_id='uci-1', stage=f'review_{m}', elapsed=10.0,
                                 answers=dict(ratings={k: v for k, _ in C.RATING_ITEMS})))
            rows.append(dict(participant=p, case_id='uci-1', stage='side', elapsed=5.0, answers=dict(ratings={'side_helped': 5, 'side_describe': 3})))
            rows.append(dict(participant=p, case_id='uci-1', stage='feedback', elapsed=5.0, answers=dict(text='clear' if p == 'P-1' else '')))
        s = C.research_summary(rows, [dict(finished=1.0), dict(finished=None)])
        self.assertEqual(s['ratings']['paired_difference']['easy'], dict(pairs=2, mean_tgap_minus_cody=2.0))
        self.assertEqual(s['ratings']['side'], dict(side_helped=5.0, side_describe=3.0))
        self.assertEqual(s['feedback'], dict(responses=2, with_text=1))
        self.assertEqual(s['sessions'], dict(total=2, complete=1, incomplete=1))


if __name__ == '__main__':
    unittest.main()
