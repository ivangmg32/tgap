"""Acceptance tests for the beginner-friendly study (single case, plain TGAP
explanation, collapsed chart explorer). Uses the REAL saved Case 1 record;
variants (no-op, invalid, flipped) are copies with fields changed so the
wording can be checked for every outcome."""
import copy
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT.parent
sys.path.insert(0, str(ROOT))
from sandbox import compare as C  # noqa: E402
from sandbox import chart_registry as R  # noqa: E402
from sandbox.easy import guide  # noqa: E402

BANK = SOURCE/'output'/'compare_explainers'/'casebank.json'
STATIC = ROOT/'static'


@unittest.skipUnless(BANK.is_file(), 'no saved case bank')
class PlainTgapTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cases, _, problem = C.load_cases({'compare_casebank': str(BANK)})
        assert cases, problem
        cls.all = cases
        cls.case = C.study_cases(cases)[0]
        cls.raw = json.loads((SOURCE/json.loads(BANK.read_text())['cases'][0]['record']).read_text())

    def primary(self, rec):
        return next(d for d in rec['tgap']['directions'] if d['direction'] == rec['tgap']['primary_direction'])

    def test_single_case_is_case_1(self):
        self.assertEqual(len(C.study_cases(self.all)), 1)
        t = self.case['target']
        self.assertEqual((t['source'], t['destination']), (492, 463))
        date = __import__('datetime').datetime.fromtimestamp(C.OPSAHL_START_UNIX + t['timestamp'], __import__('datetime').timezone.utc).date().isoformat()
        self.assertEqual(date, '2004-09-27')
        self.assertAlmostEqual(self.case['baseline_consistency']['original_probability'], 0.5404, places=4)
        self.assertEqual(C.threshold(self.case), 0.5)

    def test_values_come_from_the_record(self):
        d, pl = self.primary(self.raw), C.tgap_explanation(self.case)['plain']
        self.assertEqual(pl['churn']['before'], d['churn_before'])
        self.assertEqual(pl['churn']['after'], d['churn_after'])
        self.assertIn(f"{d['edges_swapped_total']:,}", pl['changed'][1])
        self.assertIn(f"{100 * abs(d['achieved_delta']):.1f}%", pl['cards'][0]['facts'][1][1])
        self.assertIn(f"{100 * abs(d['requested_delta']):.0f}%", pl['cards'][0]['facts'][0][1])

    def test_scores_agree(self):
        d, pl = self.primary(self.raw), C.tgap_explanation(self.case)['plain']
        p0, p1 = d['original_probability'], d['modified_probability']
        facts = dict(pl['cards'][1]['facts'])
        self.assertEqual(facts['Before'], f'{100 * p0:.2f}%')
        self.assertEqual(facts['After'], f'{100 * p1:.2f}%')
        self.assertEqual(facts['Decision cutoff'], '50%')
        self.assertIn(f'−{abs(100 * (p1 - p0)):.2f} percentage points', pl['response'])
        self.assertAlmostEqual(round(100 * p0, 2) - round(100 * p1, 2), 0.80)
        self.assertEqual(facts['Answer changed?'], 'No')
        self.assertEqual(p0 > 0.5, p1 > 0.5)

    def test_churn_quantities_are_labelled_apart(self):
        d, ch = self.primary(self.raw), C.tgap_explanation(self.case)['plain']['churn']
        self.assertTrue(ch['relative_matches_record'])
        self.assertAlmostEqual(ch['points'], d['churn_after'] - d['churn_before'])
        self.assertAlmostEqual(ch['relative'], d['achieved_delta'])
        self.assertNotAlmostEqual(abs(ch['points']), abs(ch['relative']), places=3)   # 11.47 pp versus 11.80 %
        self.assertTrue(ch['points_text'].endswith('percentage points'))
        self.assertTrue(ch['relative_text'].endswith('%') and 'points' not in ch['relative_text'])
        tech = dict(C.tgap_explanation(self.case)['plain']['technical'])
        self.assertIn(ch['points_text'], tech['Absolute difference'])
        self.assertIn(ch['relative_text'], tech['Relative change'])

    def test_wording_adapts_to_the_outcome(self):
        pl = C.tgap_explanation(self.case)['plain']
        self.assertEqual(pl['cards'][2]['text'], 'Changing the older network history slightly lowered the model’s score, but it did not change its final answer.')
        flipped = copy.deepcopy(self.case)
        dd = self.primary(flipped)
        dd.update(modified_probability=0.40, class_changed=True)
        self.assertIn('enough to change its final answer', C.tgap_explanation(flipped)['plain']['cards'][2]['text'])
        same = copy.deepcopy(self.case)
        self.primary(same).update(modified_probability=self.primary(same)['original_probability'])
        self.assertIn('did not change', C.tgap_explanation(same)['plain']['cards'][2]['text'])

    def test_invalid_and_noop_are_distinct(self):
        noop, bad = copy.deepcopy(self.case), copy.deepcopy(self.case)
        self.primary(noop)['status'] = 'noop'
        self.primary(bad)['status'] = 'invalid'
        n, b = C.tgap_explanation(noop)['plain'], C.tgap_explanation(bad)['plain']
        self.assertIn('Nothing was changed', n['cards'][0]['text'])
        self.assertIn('not the same as “the change had no effect”', n['cards'][2]['text'])
        self.assertIn('could not be carried out correctly', b['cards'][0]['text'])
        self.assertNotEqual(n['cards'][2]['text'], b['cards'][2]['text'])

    def test_no_jargon_in_main_text(self):
        pl = C.tgap_explanation(self.case)['plain']
        main = ' '.join([c['text'] for c in pl['cards']] + pl['changed'] + pl['churn_story'] + [pl['response'], pl['final'], pl['limitation']])
        for word in ('Jaccard', 'intervention', 'predicted class', 'snapshot', 'rewired', 'perturbation', 'operationaliz'):
            self.assertNotIn(word.lower(), main.lower(), word)
        self.assertIn('Jaccard', dict(pl['technical'])['Churn (definition)'])          # kept, but only in technical details
        self.assertIn('No real messages were changed or deleted', ' '.join(pl['changed']))
        texts = [c['text'] for c in pl['cards']] + pl['changed'] + pl['churn_story'] + [pl['response']]
        self.assertEqual(len(texts), len(set(texts)))                               # no sentence repeated verbatim

    def test_outcome_hidden_until_reveal(self):
        self.assertNotIn('outcome', C.case_view(self.case))
        self.assertIn('outcome', C.case_view(self.case, reveal=True))


class ChartExplorerTests(unittest.TestCase):
    def test_every_chart_has_plain_question_title_group_and_axes(self):
        groups = {g for g, _, _ in R.GROUPS}
        for item in R.INVENTORY:
            meta = R.CHART_META[item['id']]
            self.assertTrue(meta.get('question', '').startswith('Shows'), item['id'])
            self.assertTrue(meta.get('title'), item['id'])
            self.assertIn(item['group'], groups, item['id'])
            if item['kind'] in ('dynamic', 'conditional') and item['renderer'] not in ('network', 'workflow', 'matrix'):
                g = guide(item['id'])
                self.assertTrue(g.get('x') or g.get('y'), f"{item['id']} has no axis description")
                self.assertTrue(g.get('shows'), item['id'])

    def test_cards_and_groups_start_collapsed(self):
        js = (STATIC/'guided.js').read_text()
        card = js[js.index('function gChartCard'):js.index('function gGuideHtml')]
        self.assertIn('<details class="figure-card g-chart"', card)
        self.assertNotRegex(card, r'<details class="figure-card g-chart"[^>]*\bopen\b')
        self.assertNotIn("gi === 0 ? 'open'", js)                                  # no group opens by default
        self.assertRegex(js, r'<details class="g-group" id="g-group-\$\{gr\.id\}">')
        self.assertIn('Explore More TGAP Results', js)
        self.assertIn('How to read this chart', card)
        self.assertIn('What did we find?', card)
        # The contents link opens its group and only the chosen chart.
        wire = js[js.index('function gWireExplore'):js.index('function gWireResultsInner')]
        self.assertIn('c.open = true', wire)
        self.assertNotIn('querySelectorAll(\'details', wire)

    @unittest.skipUnless(shutil.which('node'), 'node not installed')
    def test_participant_flow_has_six_stages(self):
        js = (STATIC/'compare.js').read_text()
        script = js + """
CX.data = {session: {order: 'cody_first', cases: ['uci-58894']}};
const s = cxSteps();
console.log(JSON.stringify(s.map(x => x[0])));"""
        out = subprocess.run(['node', '-e', script], capture_output=True, text=True, check=True).stdout
        self.assertEqual(json.loads(out), ['intro', 'case', 'review_cody', 'review_tgap', 'side', 'finish'])


if __name__ == '__main__':
    unittest.main()


class StudyPageStaticTests(unittest.TestCase):
    """Checks on the participant page source (rendering is checked in headless Chrome separately)."""
    js = (STATIC/'compare.js').read_text()

    def test_no_multiple_choice_or_preference(self):
        self.assertNotIn('cx-q-', self.js)          # old multiple-choice inputs
        self.assertNotIn('cx-pref', self.js)        # old preference radios
        stages = self.js[self.js.index('function cxAfter'):]
        self.assertNotIn('<select', stages)          # dropdowns only on the pre-study page (age, education)
        self.assertNotIn('type="checkbox"', self.js.split('function cxFinish')[1])

    def test_finish_has_one_text_field(self):
        finish = self.js[self.js.index('function cxFinish'):self.js.index('function cxWire()')]
        self.assertEqual(finish.count('<textarea'), 1)
        self.assertEqual(finish.count('<input'), 0)
        self.assertIn('Your Final Thoughts', finish)

    def test_hashes_only_in_reproducibility_details(self):
        for fn in ('function cxCaseStep', 'function cxSide', 'function cxEssentials'):
            body = self.js[self.js.index(fn):]
            body = body[:body.index('\nfunction ', 1)]
            self.assertNotIn('sha256', body)
            self.assertNotIn('fingerprint', body)
        self.assertIn('Reproducibility Details', self.js)


class QuestionnaireTests(unittest.TestCase):
    def test_pre_questionnaire(self):
        self.assertEqual(len(C.PRE_FAMILIARITY), 7)
        self.assertEqual(C.FAMILIARITY_LABELS, ('Not at all familiar', 'Extremely familiar'))
        text = json.dumps(C.pre_definition()).lower()
        self.assertNotIn('gender', text)
        good = dict(age='18–24', education='Other', familiarity={k: 0 for k, _ in C.PRE_FAMILIARITY})
        self.assertEqual(C.validate_pre(good), [])
        self.assertEqual(C.validate_pre(dict(good, age=None, education=None)), [])          # age and education optional
        self.assertTrue(C.validate_pre(dict(good, age='17')))
        self.assertTrue(C.validate_pre(dict(good, familiarity={k: 8 for k, _ in C.PRE_FAMILIARITY})))
        self.assertTrue(C.validate_pre(dict(good, gender='x')))

    def test_exactly_ten_post_ratings_on_agreement_scale(self):
        self.assertEqual([len(C.RATINGS[k]) for k in ('tgap', 'cody', 'side')], [4, 4, 2])
        self.assertEqual(C.SCALE_LABELS, ('Strongly disagree', 'Strongly agree'))
        self.assertEqual(C.RATINGS['tgap'][0][1], 'I understood what TGAP changed in the network’s history.')

    def test_google_form_links(self):
        links = (STATIC/'study-links.js').read_text()
        self.assertEqual(links.count("pre: '"), 1)
        self.assertEqual(links.count("url: '"), 2)                     # two post-study surveys
        js = (STATIC/'compare.js').read_text()
        finish = js[js.index('function cxFinish'):js.index('function cxWire()')]
        self.assertIn('STUDY_LINKS.post', finish)
        self.assertIn('function cxRecording() { return false; }', js)      # no in-app ratings or text boxes are shown
        g = (STATIC/'guided.js').read_text()
        entry = g[g.index('async function renderGuided'):g.index('function gCanVisit')]
        self.assertIn('cxPreLink()', g[g.index('function gRender()'):g.index('function gRender()') + 400])
        self.assertNotIn('cxPostHtml', g)


class StudyEntryTests(unittest.TestCase):
    def test_user_study_menu_opens_phase_one_with_pre_survey_first(self):
        html = (STATIC/'index.html').read_text()
        self.assertIn('<a href="#guided" data-view="guided">', html)
        self.assertNotIn('<a href="#compare" data-view="compare">', html)        # part 2 is reached from the end of part 1
        g = (STATIC/'guided.js').read_text()
        entry = g[g.index('async function renderGuided'):g.index('function gCanVisit')]
        self.assertLess(entry.index('cxNeedsPre'), entry.index('gRender()'))   # pre-study survey link first
        self.assertIn('href="#compare"', g)                                       # "Let's compare with CoDy" button
