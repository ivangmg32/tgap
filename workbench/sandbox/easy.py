"""Plain-language reading aids for the guided-study charts.

For every chart:
  GUIDE[chart_id]  what the horizontal and vertical axes are, what each colour
                   means, and one very easy sentence saying what the chart shows
                   (the same for every run);
  easy_result()    one very easy sentence saying what THIS run's data show,
                   built only from values in the chart payload.

Naming rule used on every page: model names end in "model" ("Present ·
bridge width model") and concept / measured-property names end in "concept"
("Bridge Width concept"). `label_terms` applies it to any text.

Words are kept simple on purpose. Sizes are never described as larger than
the numbers show, and nothing is said about real-world causes.
"""
import re

from sandbox.engine import MODELS

CONCEPT_NAMES = ('Bridge Width', 'Bridge Trend', 'Centralization', 'Density', 'Churn', 'Cohesion', 'Clustering')
_CONCEPT_RE = re.compile(r'\b(' + '|'.join(CONCEPT_NAMES) + r")\b(?! concept| \u2014)")

BLUE, ORANGE, GREY, RED = '#345f92', '#b56c38', '#8094a9', '#a25353'
UP = [BLUE, 'Blue: the model’s answer went up']
DOWN = [ORANGE, 'Orange: the model’s answer went down']
SAME = [GREY, 'Grey: the answer did not change']
INC = [BLUE, 'Blue: you asked for MORE of the concept']
DEC = [ORANGE, 'Orange: you asked for LESS of the concept']
OUT = [RED, 'Red ✕: this setting could not be done properly, so it is left out']


def model_label(key):
    """Display name of a model, always ending in "model"."""
    from sandbox.registry import model_name
    name = model_name(key)
    return name if name.endswith(' model') else name + ' model'


def concept_label(name):
    return name if not name or name.endswith(' concept') else name + ' concept'


def label_terms(text):
    """Add "concept" after concept / property names in free text (and never
    say "model model")."""
    if not isinstance(text, str):
        return text
    return _CONCEPT_RE.sub(lambda m: m.group(1) + ' concept', text).replace(' model model', ' model')


EPS = 1e-9   # below this an impact is rounding noise, i.e. no reaction


def _zero(value):
    return value is None or abs(value) < EPS


def _join(items):
    items = list(items)
    return items[0] if len(items) == 1 else ', '.join(items[:-1]) + ' and ' + items[-1]


GUIDE = dict(
    workflow=dict(x='The steps TGAP took, from left to right.', y='No vertical axis: this is a diagram, not a measurement.', colors=[],
                  shows='This picture shows the steps TGAP followed to explain your model.'),
    model_separated_impacts=dict(
        x='How much the model’s answer moved (the impact). The middle line is zero: right of it means up, left means down. Each model column has its own scale.',
        y='One row per concept that was changed.', colors=[UP, DOWN, SAME],
        shows='Each dot shows how much one model reacted when one concept was changed.'),
    beeswarm=dict(x='How much the model’s answer moved (the impact). Zero means no reaction.', y='One row per concept.', colors=[UP, DOWN, SAME],
                  shows='Every dot is one test; the dots show all reactions for each concept at once.'),
    boxplot=dict(x='How much the model’s answer moved (the impact).', y='One row per concept, inside each model’s panel.',
                 colors=[['#d7e5f2', 'Light blue box: the middle half of the results; the line inside is the middle value'], UP, DOWN, SAME],
                 shows='Each box shows the usual range of reactions of one model to one concept.'),
    tgn_seed_stability=dict(x='Quality scores of a trained neural model.', y='The score value.', colors=[],
                            shows='This is a published chart from the paper, not your result.'),
    local_graph=dict(x='No axes: dots are nodes (actors), lines are connections. Left: before the change. Right: after.', y='Use the slider to pick a snapshot (a moment in time).',
                     colors=[[ORANGE, 'Orange dashed line: a connection TGAP removed'], [BLUE, 'Blue line: a connection TGAP added'],
                             ['#547ba8', 'Dot colours: the community (group) each node belongs to']],
                     shows='This picture shows exactly which connections TGAP removed and added.'),
    local_bar=dict(x='How much the model’s answer moved when that one connection was removed.', y='One bar per connection (edge) that was tested.', colors=[UP, DOWN],
                   shows='Each bar shows how much the answer changes when one connection is taken away.'),
    temporal_local=dict(x='The snapshot (moment in time) that was changed; the last one is the present.', y='How much the model’s answer moved.', colors=[UP, DOWN, SAME],
                        shows='Each bar shows what happens when the concept is changed at only one moment in time.'),
    edge_time=dict(x='The snapshot (moment in time).', y='One row per tested connection.',
                   colors=[[BLUE, 'Blue square: removing it made the answer go up'], [ORANGE, 'Orange square: removing it made the answer go down'],
                           [GREY, 'Light square: no change or the connection did not exist then']],
                   shows='Each square shows what happens when one connection is removed at one moment in time.'),
    dependence=dict(x='How busy a node or connection is (how many ties or how many snapshots it appears in).', y='How much the answer moved when it was removed.',
                    colors=[UP, DOWN, SAME], shows='Each dot checks whether busier parts of the network matter more to the model.'),
    impact_distribution=dict(x='The impact on a squeezed (log) scale, so tiny and huge values both fit. Right means up, left means down.', y='One row per concept.',
                             colors=[UP, DOWN, SAME], shows='This shows all reactions for each concept, small and large, on one line.'),
    bridge_matrix=dict(x='Communities (groups of nodes).', y='The same communities. Each square is the number of connections between two groups, before → after.',
                       colors=[['#cfe0f1', 'Light blue square: more connections after the change'], ['#f6dccb', 'Light orange square: fewer connections after the change'],
                               ['#edf3fb', 'Pale square: no change']],
                       shows='This table shows how the connections between groups changed.'),
    requested_vs_achieved=dict(x='The change you asked for (+ means more, − means less).', y='The change that really happened, measured after the change.',
                               colors=[INC, DEC, OUT], shows='Each dot compares the change you asked for with the change that really happened.'),
    validity_map=dict(x='Each column is one requested size and direction (for example +10%).', y='One row per concept.',
                      colors=[['#e3f1ea', 'Green: the setting worked and can be used'], ['#f8dcd9', 'Pink: not enough connections to make the change'],
                              ['#fbe7cd', 'Yellow: the concept was already at its limit'], ['#efd9f0', 'Purple: the concept moved the wrong way'],
                              ['#e6e6e6', 'Grey: the concept did not change at all']],
                      shows='This grid shows which changes TGAP could make properly and which had to be left out.'),
    delta_sensitivity=dict(x='How big a change you asked for.', y='How strongly the model reacted per unit of real change (the normalized impact).',
                           colors=[INC, DEC, OUT], shows='This shows whether the model reacts more strongly to bigger or smaller changes.'),
    normalization=dict(x='How big a change you asked for.', y='The impact, worked out in two ways.',
                       colors=[[BLUE, 'Dark blue: divided by the change that really happened (TGAP’s way)'], ['#9db6cf', 'Light blue: divided by the change you asked for']],
                       shows='This compares two ways of measuring the reaction: by the real change or by the asked-for change.'),
    temporal_sensitivity=dict(x='One group of bars per model.', y='How much the model reacted when only the PAST was changed (Bridge Trend concept).',
                              colors=[INC, DEC, OUT], shows='This shows which models look only at the present and which also look at the past.'),
    trajectory=dict(x='The snapshot (moment in time), from oldest to newest.', y='The value of the chosen concept (pick it in the menu).',
                    colors=[['#29445f', 'Dark line: the original network'], [BLUE, 'Blue dashed line: after asking for more'], [ORANGE, 'Orange dashed line: after asking for less']],
                    shows='These lines show how the concept looked over time before and after the change.'),
    leakage=dict(x='How much each property changed (average over time). Left half: when you asked for LESS of your concept. Right half: when you asked for MORE.',
                 y='One row per measured property.', colors=[[BLUE, 'Blue: this property went up'], [ORANGE, 'Orange: this property went down']],
                 shows='This shows what else changed by accident when TGAP changed your concept.'),
    seed_stability=dict(x='The impact for each repeat with a different random seed.',
                        y='Increase and decrease, one row each. The bar runs from the lowest to the highest result; the line is the average.',
                        colors=[INC, DEC],
                        shows='This shows whether you get the same answer when the test is repeated.'),
    efficiency=dict(x='Each explanation run.', y='How many times the model was asked.',
                    colors=[['#9db6cf', 'Light blue: the number TGAP should need (1 + 2 per concept)'], [BLUE, 'Dark blue: the number it really used (matches)'],
                            [RED, 'Red: a run used a different number than expected']],
                    shows='This checks that TGAP asked the model only as many times as it should.'),
    graph_size=dict(x='How big the made-up network was (nodes per group).', y='The impact at that size.', colors=[INC, DEC, OUT],
                    shows='This shows whether the reaction stays the same when the network is bigger or smaller.'),
    matched_comparison=dict(x='Pairs of concepts.', y='Whether the two can be compared fairly, and their impacts.', colors=[],
                            shows='This table shows which pairs of concepts can be compared fairly.'),
    faithfulness=dict(x='Test models whose right answer is known.', y='Measured versus known answer.', colors=[],
                      shows='This is a published check from the paper, not your result.'),
)


def _n(value, digits=3):
    if value is None:
        return 'n/a'
    text = f'{abs(value):.{digits}g}'
    return ('−' if value < 0 else '+' if value > 0 else '') + text


def _pct(delta):
    return f'{abs(delta) * 100:g}%'


def _way(value):
    return 'up' if value > 0 else 'down' if value < 0 else 'not at all'


def _workflow(d, ctx):
    return (f"TGAP asked the model {d['core_calls']} times to build your explanation, "
            f"and {d['valid_rows']} of {d['total_rows']} results passed the quality checks.")


def _req_ach(d, ctx):
    p, concept = d['primary'], concept_label(ctx.get('selected') or 'the concept')
    if not p['valid_for_analysis']:
        return f"Your requested change to the {concept} could not be done properly, so it is left out of the results."
    if p['noop']:
        return f"Your requested change was too small to change the {concept}, so nothing happened."
    a = p['achieved_delta']
    real = f"{a * 100:+.1f}%" if p['delta_mode'] == 'relative' else f"{_n(a)} (in its own units)"
    return f"You asked to {p['direction']} the {concept} by {_pct(p['requested_delta'])}; it really changed by {real}."


def _validity(d, ctx):
    c = d['counts']
    return (f"{c['valid']} of {c['total']} tested settings worked and are used; "
            f"{c['invalid']} were left out because the network could not be changed that way.")


def _delta(d, ctx):
    direction = ctx.get('spec', {}).get('direction', 'increase')
    vals = [r['impact'] for r in d['rows'] if r['direction'] == direction and r['valid_for_analysis'] and not r['noop'] and r['impact'] is not None]
    if len(vals) < 2:
        return 'There are not enough working sizes to see a pattern.'
    if max(vals) == min(vals):
        return f"The model reacted the same way ({_n(vals[0])}) whatever the size of the change."
    return f"The reaction changed with the size of the change, from {_n(min(vals))} to {_n(max(vals))}."


def _normalization(d, ctx):
    rows = [r for r in d['rows'] if r['valid_for_analysis'] and not r['noop'] and r['impact'] is not None]
    if not rows:
        return 'There are no working results to compare here.'
    r = rows[0]
    return (f"For {r['direction']} {_pct(r['sweep_delta'])}: TGAP’s way gives {_n(r['impact'])}, "
            f"the asked-for way gives {_n(r['impact_requested_normalization'])}.")


def _strips(d, ctx):
    selected = ctx.get('selected')
    moved, still = [], []
    for model in d['models']:
        vals = [pt['impact'] for p in d['panels'] if p['model'] == model and p['concept'] == selected for pt in p['points']]
        if vals:
            (still if all(_zero(v) for v in vals) else moved).append(model_label(model))
    if not moved and not still:
        return 'There are no working results for your concept here.'
    out = []
    if moved:
        out.append(f"The {_join(moved)} reacted to the {concept_label(selected)}.")
    if still:
        out.append(f"The {_join(still)} did not react to it at all.")
    return ' '.join(out)


def _beeswarm(d, ctx):
    zero, moving = [], []
    for g in d['groups']:
        for c in g['concepts']:
            vals = [pt['impact'] for pt in c['points']]
            if vals:
                (zero if sum(_zero(v) for v in vals) > len(vals) / 2 else moving).append(concept_label(c['concept']))
    out = []
    if moving:
        out.append(f"The models clearly react to the {_join(moving)}.")
    if zero:
        out.append(f"For the {_join(zero)}, most dots sit at zero, so most models ignore {'it' if len(zero) == 1 else 'them'}.")
    return ' '.join(out) if out else 'There are no working results here.'


def _boxplot(d, ctx):
    # Judge a reaction by the whole box (q1..q3), not the middle value: +8 and
    # -8 (increase and decrease) have a middle value of 0 but are a reaction.
    out = []
    for panel in d['panels']:
        boxes = [b for b in panel['boxes'] if b['n'] and b['q1'] is not None and b['q3'] is not None]
        if not boxes:
            continue
        top = max(boxes, key=lambda b: max(abs(b['q1']), abs(b['q3'])))
        if _zero(top['q1']) and _zero(top['q3']):
            out.append(f"the {model_label(panel['model'])} did not react to these concepts")
        else:
            out.append(f"the {model_label(panel['model'])} reacts most to the {concept_label(top['concept'])} "
                       f"(the middle half of its results lies between {_n(top['q1'])} and {_n(top['q3'])})")
    return ('In your run, ' + '; '.join(out) + '.') if out else 'There are no working results here.'


def _signedlog(d, ctx):
    pts = [(c['concept'], pt['impact']) for c in d['concepts'] for pt in c['points']]
    if not pts:
        return 'There are no working results here.'
    concept, value = max(pts, key=lambda x: abs(x[1]))
    if _zero(value):
        return 'No change moved the model’s answer at all.'
    return f"The biggest single reaction came from the {concept_label(concept)} ({_n(value)}, the answer went {_way(value)})."


def _matched(d, ctx):
    pairs = d['pairs']
    ok = [x for x in pairs if x['comparable']]
    text = f"{len(ok)} of {len(pairs)} concept pairs could be compared fairly."
    if ok:
        x = ok[0]
        other = x['second'] if x['larger'] == x['first'] else x['first']
        text += f" At a similar real change, the {concept_label(x['larger'])} moved the model more than the {concept_label(other)}."
    return text


def _temporal_sensitivity(d, ctx):
    delta = d.get('shown_delta', ctx.get('spec', {}).get('delta'))
    blind, react = [], []
    for model in d['models']:
        rows = [r for r in d['rows'] if r['model'] == model and abs(r['delta'] - delta) < 1e-9 and r['valid_for_analysis']]
        if rows:
            (blind if all(_zero(r['impact']) for r in rows) else react).append(model_label(model))
    out = []
    if blind:
        out.append(f"The {_join(blind)} did not react when only the past changed, so {'it looks' if len(blind) == 1 else 'they look'} only at the present.")
    if react:
        out.append(f"The {_join(react)} reacted, so {'it also reads' if len(react) == 1 else 'they also read'} the past.")
    return ' '.join(out) if out else 'The past could not be changed properly here, so nothing can be read.'


def _temporal_local(d, ctx):
    out = []
    for panel in d['panels']:
        if not panel['valid_for_analysis']:
            continue
        moved = [r for r in panel['rows'] if r['valid'] and not _zero(r['impact'])]
        last = len(panel['rows']) - 1
        if not moved:
            out.append(f"no single moment changed the {model_label(panel['model'])}")
        elif all(r['snapshot'] == last for r in moved):
            out.append(f"only the present (last snapshot) matters to the {model_label(panel['model'])}")
        else:
            out.append(f"earlier moments also matter to the {model_label(panel['model'])}")
    return ('In your run, ' + '; '.join(out) + '.') if out else 'There are no working results here.'


def _trajectory(d, ctx):
    direction = ctx.get('spec', {}).get('direction')
    changed = d['transformed'].get(direction)
    if not changed:
        return 'There is no changed history to show.'
    same_last = all(abs(changed[-1][m] - d['original'][-1][m]) < 1e-12 for m in ('bridge', 'density', 'centralization'))
    moved = sum(1 for a, b in zip(d['original'], changed) if any(abs(b[m] - a[m]) > 1e-12 for m in ('bridge', 'density', 'centralization')))
    return (f"{moved} of {len(changed)} snapshots changed; "
            + ('the present (last snapshot) stayed exactly the same.' if same_last else 'the present (last snapshot) also changed.'))


def _edge_time(d, ctx):
    moved = [c for c in d['cells'] if c['present'] and not _zero(c['impact'])]
    if not moved:
        return 'Removing a single connection at a single moment never changed the answer.'
    top = max(moved, key=lambda c: abs(c['impact']))
    return (f"{len(moved)} removal{'s' if len(moved) != 1 else ''} changed the answer; the strongest was connection {top['u']}–{top['v']} "
            f"at snapshot {top['snapshot'] + 1} ({_n(top['impact'])}).")


def _local_graph(d, ctx):
    per = d['per_snapshot']
    added, removed = sum(s['added'] for s in per), sum(s['removed'] for s in per)
    touched = sum(1 for s in per if s['added'] or s['removed'])
    return f"TGAP added {added} and removed {removed} connections, in {touched} of {len(per)} snapshots."


def _bridge_matrix(d, ctx):
    direction = ctx.get('spec', {}).get('direction')
    info = d['directions'].get(direction) or next(iter(d['directions'].values()), None)
    if not info:
        return 'There is nothing to show.'
    moved = sum(1 for x in info['bridge_matrix'] if x['before'] != x['after'])
    total = len(info['bridge_matrix'])
    return f"Connections changed between {moved} of {total} pair{'s' if total != 1 else ''} of groups."


def _local_bar(d, ctx):
    rows = d['rows']
    if not rows:
        return 'No connections were tested.'
    top = max(rows, key=lambda r: abs(r['impact']))
    if _zero(top['impact']):
        return 'Removing any single tested connection did not change the answer.'
    return (f"Removing connection {top['u']}–{top['v']} moved the answer the most ({_n(top['impact'])}); "
            f"{sum(not _zero(r['impact']) for r in rows)} of {len(rows)} tested connections mattered.")


def _dependence(d, ctx):
    from sandbox.interpret import _rank_corr
    if d.get('nodes'):
        rows = d['nodes']['rows']
        rho = _rank_corr([r['total_degree'] for r in rows], [abs(r['impact']) for r in rows])
        if rho is None:
            return 'There are too few measurements to see a pattern.'
        if rho > .5:
            return 'Busier nodes tend to matter more to the model.'
        if abs(rho) < .3:
            return 'How busy a node is says little about how much it matters to the model.'
        return 'Busier nodes matter somewhat more to the model.'
    return 'There are too few measurements to see a pattern.'


def _leakage(d, ctx):
    from sandbox.interpret import INTENDED
    rows = [r for r in d['rows'] if abs(abs(r['requested_delta']) - d['delta']) < 1e-9]
    intended = INTENDED.get(ctx.get('selected'))
    for r in rows:
        if r['direction'] != ctx.get('spec', {}).get('direction'):
            continue
        others = {k: v['change'] for k, v in r['metrics'].items() if k != intended and not _zero(v['change'])}
        if not others:
            return 'Nothing else changed: only your concept moved.'
        k, v = max(others.items(), key=lambda kv: abs(kv[1]))
        return f"Besides your concept, the {concept_label(k)} changed the most ({_n(v)}, in its own units)."
    return 'There is nothing to show for your direction.'


def _stability(d, ctx):
    sds = [s['sd'] for s in d['summary'] if s['sd'] is not None]
    if sds and max(sds) < EPS:
        return 'Every repeat gave exactly the same answer.'
    ranges = [f"{s['direction']} {_n(s['min'])} to {_n(s['max'])}" for s in d['summary'] if s['n']]
    return 'The answer changes a little between repeats: ' + '; '.join(ranges) + '.' if ranges else 'No repeat worked.'


def _efficiency(d, ctx):
    wrong = [r for r in d['runs'] if r['measured'] != r['expected']]
    return ('Every run used exactly the expected number of model calls.' if not wrong
            else f"{len(wrong)} of {len(d['runs'])} runs used a different number of calls than expected.")


def _graph_size(d, ctx):
    direction = ctx.get('spec', {}).get('direction')
    vals = [r['impact'] for r in d['rows'] if r['direction'] == direction and r['valid_for_analysis'] and not r['noop'] and r['impact'] is not None]
    if not vals:
        return 'No size gave a working result.'
    if all(_zero(v) for v in vals):
        return 'The model did not react at any size.'
    same = all(v > EPS for v in vals) or all(v < -EPS for v in vals)
    return ('The reaction keeps the same direction at every size.' if same
            else 'The reaction changes direction at some sizes.')


EASY_RESULTS = dict(workflow=_workflow, requested_vs_achieved=_req_ach, validity_map=_validity, delta_sensitivity=_delta,
                    normalization=_normalization, model_separated_impacts=_strips, beeswarm=_beeswarm, boxplot=_boxplot,
                    impact_distribution=_signedlog, matched_comparison=_matched, temporal_sensitivity=_temporal_sensitivity,
                    temporal_local=_temporal_local, trajectory=_trajectory, edge_time=_edge_time, local_graph=_local_graph,
                    bridge_matrix=_bridge_matrix, local_bar=_local_bar, dependence=_dependence, leakage=_leakage,
                    seed_stability=_stability, efficiency=_efficiency, graph_size=_graph_size)


def easy_result(chart_id, payload, ctx):
    """One very easy sentence about what this run's data show in this chart."""
    if payload['status'] not in ('ok', 'partial'):
        return 'This chart was not made for your run, so there is nothing to read here.'
    fn = EASY_RESULTS.get(chart_id)
    if fn is None:
        return 'This is a published reference, not your result.'
    try:
        return label_terms(fn(payload['data'], ctx))
    except Exception:          # never invent a sentence around a failure
        return 'A simple summary could not be made for this chart; read the values in the chart.'


def guide(chart_id):
    g = GUIDE.get(chart_id) or dict(x='', y='', colors=[], shows='')
    return dict(x=label_terms(g['x']), y=label_terms(g['y']), shows=label_terms(g['shows']),
                colors=[dict(color=c, meaning=label_terms(m)) for c, m in g['colors']])
