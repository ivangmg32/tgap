"""Compare Explainers study flow, through the real endpoint functions of
sandbox/app.py with a temporary database (no HTTP client needed): consent,
counterbalanced order, stage order, the second method only after the first
review, the outcome withheld until every answer is stored, pairing by
participant and case, exports, the research summary and withdrawal.

The case bank is three copies of the REAL demonstration record (one with a
CoDy timeout, one marked non-comparable), so positive values are genuine."""
import copy
import csv
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT.parent if (ROOT.parent/'core').is_dir() else ROOT.parent/'tgap'
if 'TGAP_SANDBOX_HOME' not in os.environ:
    HOME = Path(tempfile.mkdtemp(prefix='cx-study-'))
    (HOME/'config.json').write_text(json.dumps(dict(tgap_source=str(SOURCE))), encoding='utf-8')
    (HOME/'users.txt').write_text('admin:test-admin-pass:admin\n', encoding='utf-8')
    os.environ['TGAP_SANDBOX_HOME'] = str(HOME)
sys.path.insert(0, str(ROOT))
from fastapi import HTTPException  # noqa: E402
import sandbox.app as A  # noqa: E402
from sandbox import compare as C  # noqa: E402

POINTER = SOURCE/'output'/'compare_explainers'/'latest.json'


def make_bank(folder, records):
    rec_dir = folder/'output'/'compare_explainers'/'records'
    rec_dir.mkdir(parents=True, exist_ok=True)
    entries = []
    for r in records:
        path = rec_dir/f"{r['case_id']}.json"
        path.write_text(json.dumps(r), encoding='utf-8')
        entries.append(dict(case_id=r['case_id'], record=f'output/compare_explainers/records/{path.name}',
                            record_sha256=hashlib.sha256(path.read_bytes()).hexdigest(), inclusion_reason='test copy'))
    bank = folder/'output'/'compare_explainers'/'casebank.json'
    bank.write_text(json.dumps(dict(batch_id='b-test', rule='test', absent_categories=[], warning='', cases=entries)), encoding='utf-8')
    return bank


PRE = dict(age='25–34', education='Master’s degree', familiarity={k: 3 for k, _ in C.PRE_FAMILIARITY})


def as_user(name):
    return patch.object(A, 'session', lambda request: dict(username=name, role='participant', csrf='x'))


@unittest.skipUnless(POINTER.is_file(), 'no saved pilot record')
class StudyFlowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        demo = C.load_cases({'compare_latest': str(POINTER), 'compare_casebank': '/nonexistent'})[0][0]
        a = dict(copy.deepcopy(demo), case_id='uci-1')
        b = dict(copy.deepcopy(demo), case_id='uci-2')
        b['cody'].update(status='timeout', events=[], event_count=0, counterfactual_probability_exact=None)
        bad = dict(copy.deepcopy(demo), case_id='uci-3')
        bad['comparability'].update(comparable=False)
        cls.tmp = Path(tempfile.mkdtemp(prefix='cx-bank-'))
        cls.bank = make_bank(cls.tmp, [a, b, bad])
        cls.records = {'uci-1': a, 'uci-2': b}

    def setUp(self):
        self.cfg = patch.dict(A.CONFIG, {'compare_casebank': str(self.bank)})
        self.cfg.start()

    def tearDown(self):
        self.cfg.stop()

    def answer(self, case, stage):
        if stage == 'feedback':
            return dict(text='The cards were clear.')
        return dict(ratings={k: 5 for k, _ in C.RATINGS['side' if stage == 'side' else stage.split('_')[1]]})

    def test_full_flow(self):
        with as_user('flow-user'):
            data = A.compare_scenario(None)
            self.assertFalse(data['session']['recording'])
            self.assertTrue(all('outcome' not in c for c in data['page']['cases']))
            with self.assertRaises(HTTPException):
                A.compare_response(A.CompareResponse(case_id='uci-1', stage='review_tgap', answers=self.answer('uci-1', 'review_tgap')), None)
            with self.assertRaises(HTTPException):                               # the pre-study questionnaire is required
                A.compare_start(A.CompareConsent(consent=True), None)
            data = A.compare_start(A.CompareConsent(consent=True, pre=PRE), None)
            s = data['session']
            self.assertTrue(s['pre_done'])
            edited = dict(PRE, age='35–44')
            A.compare_pre(A.ComparePre(pre=edited), None)                          # editing updates, no duplicate
            A.compare_start(A.CompareConsent(consent=True, pre=PRE), None)         # a repeated start adds nothing
            self.assertEqual(s['cases'], ['uci-1'])                             # the study uses one case only
            self.assertEqual(len(data['page']['cases']), 1)
            self.assertEqual(s['order'], C.assign_order(s['participant']))
            seq = C.stage_sequence(s['order'], s['cases'])
            self.assertEqual(len(seq), 4)       # review, review, side, feedback (the Finish stage)
            first_case, first_stage = seq[0]
            with self.assertRaises(HTTPException) as out_of_order:
                A.compare_response(A.CompareResponse(case_id=seq[1][0], stage=seq[1][1], answers=self.answer(*seq[1])), None)
            self.assertEqual(out_of_order.exception.status_code, 409)
            with self.assertRaises(HTTPException) as invalid:
                A.compare_response(A.CompareResponse(case_id=first_case, stage=first_stage, answers=dict(ratings={'easy': 9})), None)
            self.assertEqual(invalid.exception.status_code, 422)
            for case, stage in seq:
                A.compare_event(A.CompareEvent(case_id=case, stage=stage), None)
                data = A.compare_response(A.CompareResponse(case_id=case, stage=stage, answers=self.answer(case, stage)), None)
                if (case, stage) != seq[-1]:
                    self.assertTrue(all('outcome' not in c for c in data['page']['cases']), 'outcome leaked before the end')
            self.assertIsNotNone(data['session']['finished'])
            self.assertTrue(all('outcome' in c for c in data['page']['cases']))
        with patch.object(A, 'researcher', lambda request: None):
            pre_rows = list(csv.DictReader(A.export('compare_pre', None).body.decode().splitlines()))
            mine_pre = [r for r in pre_rows if r['participant'] == s['participant']]
            self.assertEqual(len(mine_pre), 1)
            self.assertEqual(mine_pre[0]['age'], '35–44')
            self.assertEqual(mine_pre[0]['fam_tgnn'], '3')
            files = {p.name for p in A.STUDY_DATA.iterdir()}
            self.assertLessEqual({'sessions.csv', 'pre_survey.csv', 'ratings.csv', 'feedback.csv', 'study.json'}, files)
            saved = json.loads((A.STUDY_DATA/'study.json').read_text())
            self.assertEqual(len([r for r in saved['ratings'] if r['participant'] == s['participant']]), 10)   # 4 + 4 + 2
            self.assertEqual([r['text'] for r in saved['feedback'] if r['participant'] == s['participant']], ['The cards were clear.'])
            self.assertNotIn('flow-user', (A.STUDY_DATA/'study.json').read_text())                          # no account name in the files
            rows = list(csv.DictReader(A.export('compare_responses', None).body.decode().splitlines()))
            mine = [r for r in rows if r['participant'] == s['participant']]
            self.assertEqual(len(mine), 4)                                     # TGAP, CoDy, side, feedback
            self.assertEqual({r['method'] for r in mine if r['method']}, {'tgap', 'cody'})
            tg = next(r for r in mine if r['case_id'] == 'uci-1' and r['method'] == 'tgap')
            self.assertNotIn('correct_a', tg)
            self.assertEqual(next(r for r in mine if r['stage'] == 'feedback')['feedback'], 'The cards were clear.')
            self.assertEqual(C.keys(self.records['uci-2'], 'cody')['b'], 5)    # timeout: "no resulting score" is the key
            self.assertEqual(tg['rating_easy'], '5')
            summary = A.compare_summary(None)
            self.assertGreaterEqual(summary['sessions']['complete'], 1)
            self.assertGreaterEqual(summary['feedback']['with_text'], 1)
        with as_user('flow-user'):
            A.compare_withdraw(None)
            self.assertFalse(A.compare_scenario(None)['session']['recording'])
            self.assertNotIn(s['participant'], (A.STUDY_DATA/'study.json').read_text())                       # withdrawal removes it from the files

    def test_consent_required_and_unverified_bank_refused(self):
        with as_user('consent-user'):
            with self.assertRaises(HTTPException) as e:
                A.compare_start(A.CompareConsent(consent=False), None)
            self.assertEqual(e.exception.status_code, 422)
        only_bad = make_bank(Path(tempfile.mkdtemp()), [dict(copy.deepcopy(self.records['uci-1']), case_id='uci-9',
                                                             comparability=dict(self.records['uci-1']['comparability'], comparable=False))])
        with patch.dict(A.CONFIG, {'compare_casebank': str(only_bad)}), as_user('consent-user'):
            with self.assertRaises(HTTPException) as e:
                A.compare_start(A.CompareConsent(consent=True, pre=PRE), None)
            self.assertEqual(e.exception.status_code, 409)

    def test_tampered_record_is_refused(self):
        folder = Path(tempfile.mkdtemp())
        bank = make_bank(folder, [self.records['uci-1']])
        path = folder/'output'/'compare_explainers'/'records'/'uci-1.json'
        path.write_text(path.read_text().replace('"status"', '"status" ', 1))
        cases, meta, problem = C.load_cases({'compare_casebank': str(bank)})
        self.assertIsNone(cases)
        self.assertIn('changed', problem)


if __name__ == '__main__':
    unittest.main()
