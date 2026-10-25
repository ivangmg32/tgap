"""Compare Explainers - TGAP vs CoDy: case bank, page model, study design.

The comparison is computed offline (`python -m compare_explainers batch` and
`casebank`, which need PyTorch); the web server never runs a model. This
module only

  * loads the case bank and verifies every record's SHA-256,
  * builds the page model: both methods in the SAME structure (summary, what
    was investigated, original and resulting model score, class decision,
    what can / cannot be concluded, technical details). Every sentence is
    built from measured values; scores are shown with two decimals and every
    difference is computed from the raw values;
  * withholds the observed outcome until a participant's answers are stored;
  * assigns method order (counterbalanced) and case order (seeded), defines
    the questions, and grades them against keys derived from the record.

Terminology: the TGN outputs sigmoid(logit). It is not calibrated, so it is
called the "model score"; the predicted class is "message" above the
decision threshold.
"""
import hashlib
import json
from pathlib import Path
import random

OPSAHL_START_UNIX = 1082015761  # 2004-04-15 07:56:01 UTC = timestamp 0
NO_CHANGE = 1e-6                # score change treated as "no change"
ORDERS = ('tgap_first', 'cody_first')
RATING = (0, 7)
# Rating-only questionnaire (0 = strongly disagree, 7 = strongly agree). The
# TGAP and CoDy items are worded in parallel and share ids, so they pair.
RATINGS = {
    'tgap': [('changed', 'I understood what TGAP changed in the network’s history.'),
             ('response', 'I understood how the model’s score responded to the change made by TGAP.'),
             ('easy', 'The TGAP explanation was easy to follow.'),
             ('scope', 'I understood what this TGAP result does and does not tell us.')],
    'cody': [('changed', 'I understood what CoDy investigated in the network history.'),
             ('response', 'I understood how the model’s score responded to the changes examined by CoDy.'),
             ('easy', 'The CoDy explanation was easy to follow.'),
             ('scope', 'I understood what this CoDy result does and does not tell us.')],
    'side': [('side_helped', 'The side-by-side view helped me understand the difference between TGAP and CoDy.'),
             ('side_describe', 'After viewing both explanations, I can describe what each method tells us about the model’s prediction.')],
}
RATING_ITEMS = RATINGS['tgap']   # ids shared by both methods

# Pre-study questionnaire ("Before We Begin"): two optional single-choice
# questions and seven 0-7 familiarity ratings. Not part of the six stages.
PRE_VERSION = 'pre-1'
PRE_AGE = ('18–24', '25–34', '35–44', '45–54', '55 or older', 'Prefer not to say')
PRE_EDUCATION = ('Secondary education or high school', 'Vocational or technical qualification', 'Bachelor’s degree',
                 'Master’s degree', 'Doctoral degree', 'Other', 'Prefer not to say')
PRE_FAMILIARITY = [
    ('fam_graphs', 'How familiar are you with graphs or networks, where objects are connected to one another?'),
    ('fam_concepts', 'How familiar are you with concepts such as nodes, edges, communities, and bridges in a network?'),
    ('fam_temporal', 'How familiar are you with networks that change over time?'),
    ('fam_ml', 'How familiar are you with machine learning models and their predictions?'),
    ('fam_xai', 'How familiar are you with methods that help people understand or explain AI model predictions?'),
    ('fam_tgnn', 'How familiar are you with temporal graph neural networks, such as TGN?'),
    ('fam_charts', 'How familiar are you with interpreting network visualizations, charts, and numerical model results?'),
]
FAMILIARITY_LABELS = ('Not at all familiar', 'Extremely familiar')


def validate_pre(answers):
    problems = []
    if answers.get('age') not in (None, '', *PRE_AGE):
        problems.append('Please choose an age group from the list, or leave it empty.')
    if answers.get('education') not in (None, '', *PRE_EDUCATION):
        problems.append('Please choose an education level from the list, or leave it empty.')
    fam = answers.get('familiarity') or {}
    for key, text in PRE_FAMILIARITY:
        v = fam.get(key)
        if not isinstance(v, int) or isinstance(v, bool) or not RATING[0] <= v <= RATING[1]:
            problems.append(f'Please rate: "{text}" (0–7).')
    if set(fam) - {k for k, _ in PRE_FAMILIARITY}:
        problems.append('Unexpected familiarity items.')
    if set(answers) - {'age', 'education', 'familiarity'}:
        problems.append('Unexpected fields: ' + ', '.join(sorted(set(answers) - {'age', 'education', 'familiarity'})))
    return problems


def pre_definition():
    return dict(version=PRE_VERSION, age=list(PRE_AGE), education=list(PRE_EDUCATION),
                familiarity=[dict(id=k, text=t) for k, t in PRE_FAMILIARITY], labels=list(FAMILIARITY_LABELS))
SCALE_LABELS = ('Strongly disagree', 'Strongly agree')
FEEDBACK_MAX = 5000
PREFERENCE = ('TGAP', 'CoDy', 'Both were equally useful', 'Neither was useful', 'I cannot decide')
SHARED_TASK = ('Use the explanation to understand what was changed or investigated, how the model’s output '
               'responded, and what can reasonably be concluded from the result.')
DESCRIPTIONS = {
    'tgap': ('TGAP changes one measurable property of the network’s history, such as how much the network '
             'changes over time, and measures how the same model’s prediction responds to the change actually achieved.'),
    'cody': ('CoDy searches for a small set of past messages whose removal would change the model’s prediction. '
             'If it cannot find such a set within its search budget, it reports that no successful counterfactual was found.'),
}
CHURN_PLAIN = ('Churn measures how much the network’s past differs from its most recent period. Here it is the '
               'average, over the earlier 10-day periods, of how different that period’s connections are from '
               'the latest 10 days (0 = identical, 100% = completely different). More churn means the network’s '
               'structure changes more over time.')

# Question B and C use the same options for both methods (parallel structure).
Q_B = ['The score went down and the predicted class changed', 'The score went down but the predicted class stayed the same',
       'The score went up and the predicted class changed', 'The score went up but the predicted class stayed the same',
       'The score did not change', 'There is no resulting score (no result was produced)']
Q_C = ['Changing this property of the network’s history moved the model’s score, but the predicted class did not change.',
       'A change that flips the model’s predicted class was found.',
       'The method searched for a change that flips the prediction but did not find one within its limits.',
       'The change was carried out, but the model’s score did not respond.',
       'No usable result was produced, so nothing can be concluded about the model.',
       'The result shows what really caused the student to send the message.']


##  Loading  ##

def _root(config):
    return Path(config.get('tgap_source', '.'))


def _verified(path, sha):
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != sha:
        raise ValueError(f'{path.name} changed after it was written; it is not shown.')
    return json.loads(raw)


def load_cases(config):
    """Return (cases, bank_meta, None) or (None, None, reason). Uses the case
    bank when present, otherwise the single demonstration record."""
    root = _root(config)
    bank_path = Path(config.get('compare_casebank', root/'output'/'compare_explainers'/'casebank.json'))
    try:
        if bank_path.is_file():
            bank = json.loads(bank_path.read_text(encoding='utf-8'))
            base = bank_path.resolve().parents[2]
            cases = []
            for entry in bank['cases']:
                record = _verified((base/entry['record']).resolve(), entry['record_sha256'])
                cases.append(dict(record, case_id=entry['case_id'], inclusion_reason=entry['inclusion_reason']))
            return cases, {k: bank[k] for k in ('batch_id', 'rule', 'absent_categories', 'warning')}, None
        pointer = Path(config.get('compare_latest', root/'output'/'compare_explainers'/'latest.json'))
        if not pointer.is_file():
            return None, None, 'No comparison has been computed yet. Run "python -m compare_explainers batch" and "casebank".'
        meta = json.loads(pointer.read_text(encoding='utf-8'))
        record = _verified((pointer.resolve().parents[2]/meta['record']).resolve(), meta['record_sha256'])
        record = dict(record, case_id=f"uci-{record['target']['event_id']}", inclusion_reason='demonstration case')
        return [record], dict(batch_id=None, rule='single demonstration record', absent_categories=[], warning=''), None
    except (OSError, ValueError, KeyError) as error:
        return None, None, f'The comparison could not be loaded: {error}'


##  Numbers and wording  ##

def score(p):
    return None if p is None else f'{100 * p:.2f}%'


def points(p0, p1):
    """Signed score difference in percentage points, from raw values."""
    if p0 is None or p1 is None:
        return None
    d = 100 * (p1 - p0)
    return ('±' if abs(d) < 0.005 else '+' if d > 0 else '−') + f'{abs(d):.2f} points'


def threshold(record):
    return record['configuration']['inference']['decision_threshold_probability']


def _cls(p, thr):
    return None if p is None else ('message' if p > thr else 'no message')


def _tgap_primary(record):
    tgap = record.get('tgap') or {}
    return next((d for d in tgap.get('directions', []) if d['direction'] == tgap.get('primary_direction')), None)


def tgap_state(record):
    tgap = record.get('tgap') or {}
    d = _tgap_primary(record)
    if not d:
        return tgap.get('status') or 'execution_failure'
    return d['status']        # valid | noop | invalid


def tgap_explanation(record):
    tgap, d, thr = record.get('tgap') or {}, _tgap_primary(record), threshold(record)
    p0 = record['baseline_consistency']['original_probability']
    state = tgap_state(record)
    base = dict(method='tgap', title='TGAP', description=DESCRIPTIONS['tgap'], state=state, original_score=p0,
                original_score_text=score(p0), threshold=thr, original_class=_cls(p0, thr))
    if not d:
        return dict(base, summary='TGAP produced no valid result for this case' + (f" ({tgap.get('error')})." if tgap.get('error') else '.'),
                    investigated='No transformation could be applied and mapped to the model’s input.',
                    resulting_score=None, resulting_score_text=None, score_change_text=None, class_changed=None,
                    conclude='Nothing can be concluded about the model from this run.',
                    cannot='An absent result is not a zero effect.', details={}, plain=tgap_plain(record, None, state))
    p1 = d['modified_probability']
    less = d['direction'] == 'Decrease'
    req, ach = abs(d['requested_delta']), d['achieved_delta']
    word = 'reduction' if less else 'increase'
    plan = tgap['plan']
    feas = d.get('feasibility') or {}
    if state == 'noop':
        summary = (f"TGAP requested a {100 * req:.0f}% {word} in historical churn, but the request was too small to change any "
                   f"connection, so nothing was changed (a no-op). This is not a zero-effect result.")
        conclude = 'This run gives no information about how the model responds to churn.'
    elif state != 'valid':
        summary = (f"TGAP requested a {100 * req:.0f}% {word} in historical churn, but the transformation was not valid, "
                   f"so its result is not evidence about the model’s sensitivity.")
        conclude = 'Nothing can be concluded about the model from this run.'
    else:
        moved = abs(p1 - p0) > NO_CHANGE
        summary = (f"TGAP requested a {100 * req:.0f}% {word} in historical churn and achieved a {100 * abs(ach):.1f}% {word}. "
                   + (f"The TGN model score {'decreased' if p1 < p0 else 'increased'} from {score(p0)} to {score(p1)}, so the predicted class "
                      f"{'changed' if d['class_changed'] else 'remained unchanged'}." if moved else
                      f"The TGN model score did not change ({score(p0)})."))
        if moved:
            conclude = (f"For this prediction, {'lowering' if less else 'raising'} historical churn by {100 * abs(ach):.1f}% moved the model score by "
                        f"{points(p0, p1)}; the predicted class {'changed' if d['class_changed'] else 'did not change'}.")
            other = next((x for x in tgap['directions'] if x is not d), None)
            if other and other['status'] == 'valid' and abs(other['prediction_change']) > NO_CHANGE:
                agree = (other['prediction_change'] > 0) == (p1 - p0 < 0)
                conclude += (f" The opposite change (churn {'raised' if less else 'lowered'}) moved it the other way ({points(p0, other['modified_probability'])}), "
                             "so the response is consistent in direction." if agree else
                             f" The opposite change moved it the same way ({points(p0, other['modified_probability'])}), so there is no simple trend.")
        else:
            conclude = 'For this prediction, the model score did not respond to the achieved change in churn.'
    return dict(base, summary=summary, plain=tgap_plain(record, d, state),
                investigated=(f"Churn of the earlier history ({plan['temporal_scope']}); the latest {plan['window_days']} days were kept exactly as they were."),
                requested_change=-req if less else req, achieved_change=ach, resulting_score=p1, resulting_score_text=score(p1),
                score_change_text=points(p0, p1), class_changed=d['class_changed'], resulting_class=_cls(p1, thr),
                conclude=conclude,
                cannot=('This describes how the model responded to a controlled change in its input. It does not establish why the '
                        'students sent a message in the real world, and it does not point to individual messages the prediction depends on.'),
                churn_plain=CHURN_PLAIN,
                shortfall=(None if state != 'valid' or abs(abs(ach) - req) < 0.005 or not feas.get('cause') else
                           dict(cause=feas.get('cause'), measure_note=feas.get('measure_note'),
                                limited_periods=feas.get('limited_periods', []),
                                requested_swaps=feas.get('requested_swaps_total'), applied_swaps=feas.get('applied_swaps_total'))),
                timeline=dict(windows=plan.get('windows', []), swaps=d.get('edge_swaps_per_snapshot', []),
                              limited=feas.get('limited_periods', []), window_days=plan['window_days']),
                details=dict(concept='Churn', definition=plan['definition'], churn_before=d['churn_before'], churn_after=d['churn_after'],
                             normalized_impact=d['normalized_impact'], normalizer=d['normalizer'], edges_swapped=d['edges_swapped_total'],
                             events_readdressed=d['events_readdressed'], events_total=d['events_total'],
                             events_touching_target=d['events_readdressed_touching_a_or_b'],
                             latest_preserved=d['latest_snapshot_preserved'], edge_count_preserved=d['edge_count_preserved_every_snapshot'],
                             mapping_verified=d['lift_round_trip'], density_change=(d.get('leakage') or {}).get('Density', {}).get('change'),
                             centralization_change=(d.get('leakage') or {}).get('Centralization', {}).get('change')))


def cody_state(record):
    return (record.get('cody') or {}).get('status') or 'execution_failure'


CODY_LABEL = {
    'valid_counterfactual': 'Valid class-flipping counterfactual found',
    'no_class_change': 'No class-flipping counterfactual found within the search budget',
    'no_counterfactual': 'No usable counterfactual found within the search budget',
    'timeout': 'The search timed out',
    'execution_failure': 'The search failed',
    'reported_counterfactual_not_reproduced': 'Reported counterfactual could not be reproduced',
}


def cody_explanation(record):
    c, thr = record.get('cody') or {}, threshold(record)
    p0 = record['baseline_consistency']['original_probability']
    state = cody_state(record)
    n = c.get('event_count') or 0
    p1 = c.get('counterfactual_probability_exact') if n else None
    msgs = f"{n} historical message{'s' if n != 1 else ''}"
    base = dict(method='cody', title='CoDy', description=DESCRIPTIONS['cody'], state=state, state_label=CODY_LABEL.get(state, state),
                original_score=p0, original_score_text=score(p0), threshold=thr, original_class=_cls(p0, thr),
                resulting_score=p1, resulting_score_text=score(p1), score_change_text=points(p0, p1),
                class_changed=(None if p1 is None else _cls(p1, thr) != _cls(p0, thr)), resulting_class=_cls(p1, thr),
                investigated=(f"A search over the {c.get('candidate_size', 'n/a')} most recent past messages around the two students "
                              f"for a small set whose removal flips the prediction (budget: {(c.get('configuration') or {}).get('max_steps', 'n/a')} search steps)."))
    cannot = ('It does not show that these messages caused the original prediction, or that they are the only messages that matter.')
    if state == 'valid_counterfactual':
        summary = (f"CoDy found {msgs} whose removal flips the prediction: the model score falls from {score(p0)} to {score(p1)}, "
                   f"below the {score(thr)} decision threshold.")
        conclude = f"Removing these {msgs} would change this model’s predicted class for this case."
    elif state == 'no_class_change':
        summary = (f"No class-flipping counterfactual found within the search budget. CoDy’s best candidate removes {msgs} and "
                   f"{'lowers' if p1 < p0 else 'raises'} the model score from {score(p0)} to {score(p1)}. However, the score remains "
                   f"{'above' if p1 > thr else 'below'} the study’s decision threshold ({score(thr)}), so the predicted class does not change.")
        conclude = (f"This is an unsuccessful counterfactual attempt: removing these {msgs} moves the score by {points(p0, p1)} but does not flip the prediction.")
        cannot += ' It also does not show that no flipping set exists: the search was limited.'
    elif state == 'no_counterfactual':
        summary = 'No usable counterfactual found within the search budget: CoDy finished without returning any messages.'
        conclude = 'Within its limits, CoDy found no set of past messages whose removal flips this prediction.'
        cannot = 'It does not show that no such set exists: the search was limited.'
    elif state == 'timeout':
        summary = 'The CoDy search reached its time limit before finishing, so there is no result for this case.'
        conclude, cannot = 'Nothing can be concluded about the model from this run.', 'A timeout is not evidence that no counterfactual exists.'
    else:
        summary = f"The CoDy run did not produce a usable result ({CODY_LABEL.get(state, state)})."
        conclude, cannot = 'Nothing can be concluded about the model from this run.', 'An absent result is not a zero effect.'
    events = [dict(event_id=e['event_id'], source=e['source'], destination=e['destination'], timestamp=e['timestamp'],
                   time_utc_unix=OPSAHL_START_UNIX + e['timestamp'], hours_before=round(24 * e['days_before_target'], 2),
                   involves_target=e['involves_a_or_b']) for e in c.get('events', [])]
    return dict(base, summary=summary, conclude=conclude, cannot=cannot, events=events, plain=cody_plain(record),
                details=dict(selection_policy=(c.get('configuration') or {}).get('selection_policy'),
                             max_steps=(c.get('configuration') or {}).get('max_steps'), steps=c.get('search_steps_logged'),
                             oracle_calls=c.get('oracle_calls'), runtime_seconds=c.get('runtime_seconds'), termination=c.get('termination'),
                             candidate_size=c.get('candidate_size'), sparsity=c.get('sparsity'),
                             reported_score=c.get('counterfactual_probability_reported'), exact_score=c.get('counterfactual_probability_exact'),
                             commit=(c.get('upstream') or {}).get('commit'), error=c.get('error'),
                             provenance=record.get('provenance', 'precomputed offline')))


##  Questions and answer keys  ##

def question_a(record, method):
    """Method-appropriate options built from the actual case; returns (options, key)."""
    if method == 'tgap':
        d = _tgap_primary(record)
        if d:
            word = 'lowered' if d['direction'] == 'Decrease' else 'raised'
            like = 'more' if d['direction'] == 'Decrease' else 'less'
            right = (f"It made the older network history {like} like the latest {record['tgap']['plan']['window_days']} days "
                     f"(asked for {100 * abs(d['requested_delta']):.0f}%, achieved {100 * abs(d['achieved_delta'] or 0):.1f}%), then asked the model again.")
        else:
            right = 'It tried to change how much the network’s history changes over time, but no valid change was made.'
        options = [right,
                   'It removed a few specific past messages to try to change the model’s answer.',
                   'It changed the messages of the most recent days only.',
                   'It retrained the model on different data.']
        return options, 0
    c, state = record.get('cody') or {}, cody_state(record)
    n = c.get('event_count') or 0
    found = f"It searched for past messages to remove and found {n} whose removal flips the prediction."
    best = f"It searched for past messages to remove; its best candidate ({n} message{'s' if n != 1 else ''}) did not flip the prediction."
    none = 'It searched for past messages to remove but returned none, or did not finish.'
    options = [found if state == 'valid_counterfactual' else 'It searched for past messages to remove and found a set whose removal flips the prediction.',
               best if state == 'no_class_change' else 'It searched for past messages to remove; its best candidate did not flip the prediction.',
               none,
               'It changed a measurable property of the whole network’s history.']
    key = {'valid_counterfactual': 0, 'no_class_change': 1}.get(state, 2)
    return options, key


def keys(record, method):
    """Answer keys for questions A, B, C (indices; None = not gradable)."""
    expl = tgap_explanation(record) if method == 'tgap' else cody_explanation(record)
    p0, p1 = expl['original_score'], expl['resulting_score']
    if p1 is None:
        b = 5
    elif abs(p1 - p0) <= NO_CHANGE:
        b = 4
    else:
        b = (0 if expl['class_changed'] else 1) if p1 < p0 else (2 if expl['class_changed'] else 3)
    state = expl['state']
    if method == 'tgap':
        if state != 'valid':
            c = 4
        elif expl['class_changed']:
            c = 1
        elif abs(p1 - p0) <= NO_CHANGE:
            c = 3
        else:
            c = 0
    else:
        c = {'valid_counterfactual': 1, 'no_class_change': 2, 'no_counterfactual': 2}.get(state, 4)
    return {'a': question_a(record, method)[1], 'b': b, 'c': c}


def questions(record, method):
    """What the browser receives: options only, never the keys."""
    return [dict(id='a', text='What did this explanation change or investigate?', options=question_a(record, method)[0]),
            dict(id='b', text='How did the model’s score and predicted class change?', options=Q_B),
            dict(id='c', text='Which statement best describes what we can conclude from this result?', options=Q_C)]


def grade(record, method, answers):
    k = keys(record, method)
    return {q: (None if k[q] is None or not isinstance(answers.get(q), int) else answers[q] == k[q]) for q in 'abc'}


##  Study design  ##

def assign_order(participant, salt=''):
    """Counterbalancing: parity of SHA-256(participant code + salt). Reproducible
    per participant and ~50/50 across codes (Group A tgap_first, B cody_first)."""
    return ORDERS[hashlib.sha256(f'{participant}|{salt}'.encode()).digest()[0] % 2]


def case_order(participant, case_ids):
    """Seeded permutation of the cases, from the participant code."""
    ids = sorted(case_ids)
    random.Random(hashlib.sha256(f'cases|{participant}'.encode()).hexdigest()).shuffle(ids)
    return ids


def stage_sequence(order, cases):
    methods = ('review_tgap', 'review_cody') if order == 'tgap_first' else ('review_cody', 'review_tgap')
    return [(case, stage) for case in cases for stage in (*methods, 'side', 'feedback')]


def next_stage(order, cases, done):
    return next(((c, s) for c, s in stage_sequence(order, cases) if (c, s) not in done), None)


def validate(stage, answers, record=None):
    """Ratings only (0-7 integers) after each method and after the side-by-side
    view; the final stage takes one optional free-text field."""
    problems = []
    if stage == 'feedback':
        text = answers.get('text', '')
        if not isinstance(text, str) or len(text) > FEEDBACK_MAX:
            problems.append(f'Your feedback must be text of at most {FEEDBACK_MAX} characters.')
        extra = set(answers) - {'text'}
    else:
        items = RATINGS['side' if stage == 'side' else stage.split('_')[1]]
        ratings = answers.get('ratings') or {}
        for key, text in items:
            v = ratings.get(key)
            if not isinstance(v, int) or isinstance(v, bool) or not RATING[0] <= v <= RATING[1]:
                problems.append(f'Please rate: "{text}" (0–7).')
        unknown = set(ratings) - {k for k, _ in items}
        if unknown:
            problems.append('Unexpected ratings: ' + ', '.join(sorted(unknown)))
        extra = set(answers) - {'ratings'}
    if extra:
        problems.append('Unexpected fields: ' + ', '.join(sorted(extra)))
    return problems


##  Page model  ##

def case_view(record, reveal=False):
    t, b = record['target'], record['baseline_consistency']
    comp, model = record['comparability'], record['model']
    view = dict(
        case_id=record['case_id'], inclusion_reason=record.get('inclusion_reason'),
        query=dict(source=t['source'], destination=t['destination'], timestamp=t['timestamp'],
                   timestamp_unix=OPSAHL_START_UNIX + t['timestamp'], history_events=t['history_events'],
                   history_fingerprint=t['history_fingerprint']),
        dataset=dict(name='UCI-Messages', events=record['dataset']['events'], nodes=record['dataset']['nodes'],
                     stream_sha256=record['dataset']['stream_sha256'], source=record['dataset']['archive']),
        model=dict(name='TGN (Temporal Graph Network)', checkpoint_sha256=model['checkpoint_sha256'],
                   parameter_fingerprint=model['parameter_fingerprint'],
                   test_auc=((model.get('evaluation') or {}).get('test') or {}).get('auc')),
        original=dict(score=b['original_probability'], score_text=score(b['original_probability']), threshold=threshold(record),
                      threshold_text=f'{100 * threshold(record):g}%', predicted_class=_cls(b['original_probability'], threshold(record)),
                      score_meaning=('The model score is the TGN’s output (a sigmoid of its logit). It is not a calibrated '
                                     'probability; the model predicts “a message” when the score is above the threshold.')),
        verification=dict(verified=bool(comp['comparable']), label=comp['label'], reasons=comp['reasons'],
                          max_abs_difference=b['max_abs_logit_difference'], tolerance=b['tolerance'],
                          paths=sorted(b['paths']), shared_model=comp['shared_model_verified'], same_input=comp['same_input_verified'],
                          provenance=record.get('provenance', 'precomputed offline (pilot run)')),
        tgap=tgap_explanation(record), cody=cody_explanation(record),
    )
    view['query']['time_text'] = _when(OPSAHL_START_UNIX + t['timestamp'])
    if reveal:
        view['outcome'] = dict(happened=bool(t['ground_truth_label']),
                               text=('Student {s} did send a message to student {d} at that time.' if t['ground_truth_label'] else
                                     'Student {s} did not send a message to student {d} at that time.').format(s=t['source'], d=t['destination']),
                               model_was_right=(_cls(b['original_probability'], threshold(record)) == 'message') == bool(t['ground_truth_label']))
    return view


def _when(unix):
    import datetime
    d = datetime.datetime.fromtimestamp(unix, datetime.timezone.utc)
    return f'{d.day} {d:%B %Y}, {d:%H:%M} UTC'


def bank_view(cases, meta, reveal=False):
    return dict(cases=[case_view(c, reveal) for c in cases], bank=meta, shared_task=SHARED_TASK,
                ratings={k: [dict(id=i, text=t) for i, t in v] for k, v in RATINGS.items()}, rating_scale=list(RATING),
                scale_labels=list(SCALE_LABELS), pre=pre_definition(),
                descriptions=DESCRIPTIONS,
                side_note=('Both methods examine the same prediction but investigate different kinds of change. Their score '
                           'differences should not be treated as a direct ranking of explanation quality.'))


##  Research summary (descriptive)  ##

def research_summary(rows, sessions, technical=None):
    """rows: one dict per stored response (participant, case_id, stage, answers, elapsed). Ratings only."""
    def mean(v):
        v = [x for x in v if x is not None]
        return round(sum(v) / len(v), 3) if v else None
    per = {}
    for method in ('tgap', 'cody'):
        mine = [r for r in rows if r['stage'] == f'review_{method}']
        per[method] = dict(responses=len(mine), median_seconds=(sorted(r['elapsed'] for r in mine)[len(mine) // 2] if mine else None),
                           **{k: mean([(r['answers'].get('ratings') or {}).get(k) for r in mine]) for k, _ in RATING_ITEMS})
    paired = {}
    for k, _ in RATING_ITEMS:
        diffs = []
        for (p, case) in {(r['participant'], r['case_id']) for r in rows}:
            t = next((r for r in rows if (r['participant'], r['case_id'], r['stage']) == (p, case, 'review_tgap')), None)
            c = next((r for r in rows if (r['participant'], r['case_id'], r['stage']) == (p, case, 'review_cody')), None)
            if t and c:
                diffs.append(t['answers']['ratings'][k] - c['answers']['ratings'][k])
        paired[k] = dict(pairs=len(diffs), mean_tgap_minus_cody=mean(diffs))
    side = [r for r in rows if r['stage'] == 'side']
    feedback = [r for r in rows if r['stage'] == 'feedback']
    return dict(note=('Descriptive pilot summary of 0–7 agreement ratings (0 = strongly disagree, 7 = strongly agree). '
                      'Ratings are self-reports, not measures of explanation fidelity; no significance is implied.'),
                sessions=dict(total=len(sessions), complete=sum(1 for s in sessions if s['finished']),
                              incomplete=sum(1 for s in sessions if not s['finished'])),
                ratings=dict(per_method=per, paired_difference=paired,
                             side={k: mean([(r['answers'].get('ratings') or {}).get(k) for r in side]) for k, _ in RATINGS['side']}),
                feedback=dict(responses=len(feedback), with_text=sum(1 for r in feedback if (r['answers'].get('text') or '').strip())),
                technical=technical)


##  Plain-English TGAP explanation (participant-facing)  ##
# Every sentence is generated from the record. Technical names appear only
# in the "technical" parts. Churn is a ratio, so three different numbers are
# kept apart and labelled: the Churn values themselves, their absolute
# difference in percentage points, and the relative change (difference
# divided by the original value; this is TGAP's achieved_delta).

STUDY_CASES = 1   # cases shown to participants; the bank keeps the rest


def study_cases(cases):
    """The cases participants see: the first STUDY_CASES by selection rank."""
    return sorted(cases, key=lambda c: c['target'].get('selection_rank', 0))[:STUDY_CASES]


def _pp(x):
    """Signed percentage points from a raw difference of fractions."""
    v = 100 * x
    return ('±' if abs(v) < 0.005 else '+' if v > 0 else '−') + f'{abs(v):.2f}'


def churn_numbers(d):
    before, after = d['churn_before'], d['churn_after']
    relative = (after - before) / abs(before) if before else None
    return dict(before=before, after=after, before_text=f'{100 * before:.2f}%', after_text=f'{100 * after:.2f}%',
                points=after - before, points_text=f'{_pp(after - before)} percentage points',
                relative=relative, relative_text=None if relative is None else f'{_pp(relative)}%',
                relative_matches_record=relative is not None and abs(relative - d['achieved_delta']) < 1e-9)


def tgap_plain(record, d, state):
    """Three summary cards plus short sections, adapted to the actual outcome."""
    thr = threshold(record)
    p0 = record['baseline_consistency']['original_probability']
    thr_text = f'{100 * thr:.0f}%'
    if not d or state not in ('valid', 'noop'):
        why = 'the change could not be carried out correctly' if d else 'TGAP did not produce a result'
        return dict(state=state, cards=[
            dict(id='changed', title='What did we change?', text=f'Nothing usable: {why}.'),
            dict(id='happened', title='What happened to the model’s answer?', text=f'There is no new score to compare with the original {score(p0)}.'),
            dict(id='takeaway', title='What should I take away?', text='This test gives no information about the model. An empty result is not the same as “no effect”.')])
    plan, tgap = record['tgap']['plan'], record['tgap']
    days = plan['window_days']
    less = d['direction'] == 'Decrease'
    like = 'more like' if less else 'less like'
    req = abs(d['requested_delta'])
    ch = churn_numbers(d)
    if state == 'noop':
        return dict(state=state, churn=ch, cards=[
            dict(id='changed', title='What did we change?', text=f'TGAP tried to make the older history {like} the latest {days} days, but the request was too small to change any connection. Nothing was changed.'),
            dict(id='happened', title='What happened to the model’s answer?', text=f'The data stayed the same, so the score stayed at {score(p0)}.'),
            dict(id='takeaway', title='What should I take away?', text='Because nothing was changed, this test tells us nothing about the model. It is not the same as “the change had no effect”.')])
    p1 = d['modified_probability']
    flipped, moved = d['class_changed'], abs(p1 - p0) > NO_CHANGE
    diff = 100 * (p1 - p0)
    size = 'slightly ' if abs(diff) < 2 else ''
    way = 'down' if diff < 0 else 'up'
    cls0, cls1 = _cls(p0, thr), _cls(p1, thr)
    swaps = d.get('edge_swaps_per_snapshot') or []
    periods, earlier = sum(1 for n in swaps if n), len(swaps)
    feas = d.get('feasibility') or {}
    limited = feas.get('limited_periods') or []
    short = abs(abs(d['achieved_delta']) - req) >= 0.005
    side = 'above' if p0 > thr else 'below'
    lower = 'lowered' if diff < 0 else 'raised'
    if not moved:
        happened = 'The score did not change, so the model gave the same answer.'
        takeaway = 'Changing the older network history did not change the model’s score.'
        response = f'The model’s score stayed at {score(p0)}, so the model’s answer did not change.'
    elif flipped:
        happened = f'The score crossed the {thr_text} cutoff, so the model’s answer changed from “{cls0}” to “{cls1}”.'
        takeaway = f'Changing the older network history {lower} the model’s score enough to change its final answer.'
        response = (f'The model’s score {"decreased" if diff < 0 else "increased"} from {score(p0)} to {score(p1)} '
                    f'({_pp(p1 - p0)} percentage points). It crossed {thr_text}, so the model’s answer changed.')
    else:
        happened = f'The score went {way}{" slightly" if size else ""}, but both scores stayed {side} the {thr_text} cutoff, so the model gave the same answer.'
        takeaway = f'Changing the older network history {size}{lower} the model’s score, but it did not change its final answer.'
        response = (f'The model’s score {"decreased" if diff < 0 else "increased"} from {score(p0)} to {score(p1)} '
                    f'({_pp(p1 - p0)} percentage points). Both scores remain {side} {thr_text}, so the model’s answer did not change.')
    noun = 'reduction' if less else 'increase'
    cards = [
        dict(id='changed', title='What Did We Change?',
             text=f'TGAP changed the older network history to make it {like} the latest {days} days. Those latest {days} days stayed unchanged.',
             facts=[(f'Requested {noun} in Churn', f'{100 * req:.0f}%'), (f'Achieved {noun} in Churn', f'{100 * abs(d["achieved_delta"]):.1f}%')]),
        dict(id='happened', title='What Happened to the Model?', text=happened,
             facts=[('Before', score(p0)), ('After', score(p1)), ('Decision cutoff', thr_text), ('Answer changed?', 'Yes' if flipped else 'No')]),
        dict(id='takeaway', title='What Should I Take Away?', text=takeaway)]
    reason = ''
    if short and limited:
        reason = f' Some earlier periods ({len(limited)} of {earlier}) did not have enough suitable connections to make the full requested change.'
    elif short:
        reason = ' The network can only change whole connections, so the exact amount could not be reached.'
    changed = [f'TGAP made a modified copy of the older network data and changed which students were connected in earlier periods. '
               f'The latest {days} days were left unchanged.',
               f'In this run, TGAP changed {d["edges_swapped_total"]:,} historical connections across {periods} earlier periods. '
               'The number and timing of messages in each period stayed the same.',
               f'You asked TGAP to {"reduce" if less else "increase"} Churn by {100 * req:.0f}%, and it achieved a {noun} of {100 * abs(d["achieved_delta"]):.1f}%.' + reason,
               'No real messages were changed or deleted. Only the data used by the experiment was modified.']
    churn_story = [f'Imagine that every {days} days, we draw a map showing which students exchanged messages.',
                   f'Churn measures how different an older map is from the latest {days}-day map.',
                   'Low Churn means the connections look similar. High Churn means they look more different.',
                   f'Here, Churn was {ch["before_text"]} before the change and {ch["after_text"]} after it.']
    other = next((x for x in tgap['directions'] if x is not d), None)
    reverse = None
    if other and other['status'] == 'valid':
        od = 100 * (other['modified_probability'] - p0)
        reverse = (f'A separate test did the opposite: it made the older history {"less" if less else "more"} like the latest {days} days '
                   f'(Churn {"up" if less else "down"} {100 * abs(other["achieved_delta"]):.1f}%). The score went {"up" if od > 0 else "down"} '
                   f'{abs(od):.2f} percentage points. '
                   + ('The two tests moved the score in opposite directions, but by different amounts, so this does not show a simple straight-line rule.'
                      if (od > 0) != (diff > 0) else 'Both tests moved the score in the same direction, so there is no simple trend.'))
    technical = [('Churn (definition)', 'The average Jaccard distance between each earlier period’s set of connections and the latest period’s set (0% = identical, 100% = no connection in common).'),
                 ('Churn before the change', ch['before_text']), ('Churn after the change', ch['after_text']),
                 ('Absolute difference', ch['points_text'] + ' (after − before)'),
                 ('Relative change', f'{ch["relative_text"]} ((after − before) ÷ before; this is the “achieved change”)'),
                 ('Requested relative change', f'{"−" if less else "+"}{100 * req:.0f}%'),
                 ('Score difference', f'{_pp(p1 - p0)} percentage points ({score(p0)} → {score(p1)})'),
                 ('Normalized impact', f'{d["normalized_impact"]:.4f} (score change ÷ |relative Churn change|)'),
                 ('About the score', 'The model score is the network’s output (a sigmoid of its logit). It is not a calibrated real-world probability.')]
    final = (f'In this test, changing the older network history {size}{lower} the model’s score, but the model still gave the same answer.'
             if moved and not flipped else takeaway)
    return dict(state=state, churn=ch, cards=cards, changed=changed, churn_story=churn_story, response=response,
                final=final, limitation='This shows how the model responded to this particular data change. It does not explain why students exchanged messages in real life.',
                reverse=reverse, technical=technical,
                compact=dict(did=f'Made the older network history {like} the latest {days} days, leaving those {days} days unchanged.',
                             rows=cards[0]['facts'], meaning=takeaway))


def cody_plain(record):
    """CoDy in the same three-part structure, from the record."""
    c, thr = record.get('cody') or {}, threshold(record)
    p0 = record['baseline_consistency']['original_probability']
    state, n = cody_state(record), (record.get('cody') or {}).get('event_count') or 0
    p1 = c.get('counterfactual_probability_exact') if n else None
    thr_text = f'{100 * thr:.0f}%'
    status = {'valid_counterfactual': 'Successful: a set of messages that changes the model’s answer was found.',
              'no_class_change': 'No successful class-changing counterfactual found within the search budget.',
              'no_counterfactual': 'No successful class-changing counterfactual found within the search budget.',
              'timeout': 'The search ran out of time before finishing.'}.get(state, 'The search did not produce a usable result.')
    msgs = f'{n} past message{"s" if n != 1 else ""}'
    if state == 'valid_counterfactual':
        found = f'CoDy found {msgs} that, if removed, would change the model’s answer.'
        takeaway = f'Removing these {msgs} would change this model’s answer for this prediction.'
    elif state == 'no_class_change':
        cls = _cls(p1, thr)
        found = (f'CoDy did not find a set of messages that changed the model’s answer within the search budget. Its best candidate removed '
                 f'{"two" if n == 2 else n} past message{"s" if n != 1 else ""} and {"lowered" if p1 < p0 else "raised"} the model’s score, but the model still predicted “{cls}”.')
        takeaway = 'CoDy could not find messages whose removal changes the model’s answer. This does not prove that no such messages exist: the search was limited.'
    elif state == 'no_counterfactual':
        found = 'CoDy finished without returning any messages.'
        takeaway = 'Within its limits, CoDy found no messages whose removal changes the answer. The search was limited, so such messages may still exist.'
    else:
        found = 'The search did not produce a result.'
        takeaway = 'Nothing can be concluded about the model from this run.'
    facts = [('Before', score(p0)), ('After (best candidate)' if state != 'valid_counterfactual' else 'After', score(p1) or 'no score'),
             ('Difference', f'{_pp(p1 - p0)} percentage points' if p1 is not None else '—'), ('Decision cutoff', thr_text),
             ('Answer changed?', '—' if p1 is None else 'Yes' if _cls(p1, thr) != _cls(p0, thr) else 'No')]
    return dict(state=state, status=status, ok=state == 'valid_counterfactual',
                investigated='CoDy searched recent past messages for a small set that, if removed, would change the model’s answer.',
                found=found, facts=facts, takeaway=takeaway,
                limitation='The messages CoDy picked are candidates it examined. Being picked does not prove that they caused the original prediction.',
                compact=dict(did='Searched recent past messages for a small set whose removal would change the answer.',
                             rows=[('Result', 'Successful' if state == 'valid_counterfactual' else 'Not successful'), ('Messages in best candidate', str(n))],
                             meaning=takeaway))
