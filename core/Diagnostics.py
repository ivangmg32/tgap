'''
Diagnostics for the TGAP research prototype.

Two independent tools live here:

1. CallCountingModel - wrap any model to COUNT its predict() calls.
   Used to verify the efficiency claim (one explanation costs exactly
   1 + 2 x number_of_transformations model calls) instead of asserting
   it on faith.

2. leakageReport - quantify TRANSFORMATION LEAKAGE: when we perturb
   concept A, how much do concepts B, C, D move as a side effect?
   This separates the intended counterfactual change from unintended
   structural side effects, which is essential for trusting that an
   impact attributed to "Bridge Width" is really about bridge width.
'''

import numpy as np


class CallCountingModel:
    ''' Transparent wrapper: forwards predict() to the wrapped model and
    counts the calls. Satisfies the same one-method contract as every
    model, so it drops into any explainer unchanged. '''

    def __init__(self, model):
        self.model = model
        self.calls = 0

    def predict(self, x):
        self.calls += 1
        return self.model.predict(x)


def panelValue(metric, x):
    ''' Evaluate a Metric on a single graph, or on a temporal graph as
    the mean across snapshots. '''
    if isinstance(x, list):
        return float(np.mean([metric.measure(g) for g in x]))
    return float(metric.measure(x))


def leakageReport(x, transformation, delta, metrics):
    ''' Measure how a transformation moves EVERY metric in a panel, not
    just its own property.

    x              : a graph or temporal graph
    transformation : a TemporalGraphTransformation instance
    delta          : the nudge to apply
    metrics        : dict {name: Metric instance} - the measurement panel

    Returns a dict {name: {"before", "after", "change"}}. The row for
    the transformation's own property is the INTENDED change; every
    other nonzero row is leakage. Interpretation guide: leakage that is
    orders of magnitude below the intended change is acceptable noise;
    leakage of comparable size means the two concepts cannot be
    explained independently with this transformation pair (see the
    CentralizationTransformation docstring for a historical example). '''
    if isinstance(x, list):
        xT = transformation.transform(x, delta)
    else:
        xT = transformation.transformGraph(x, delta)
    report = {}
    for name, metric in metrics.items():
        before = panelValue(metric, x)
        after = panelValue(metric, xT)
        report[name] = {
            "before": before,
            "after": after,
            "change": after - before,
        }
    return report


def formatLeakageReport(report, intendedName=None):
    ''' Render a leakage report as aligned console text. Marks the
    intended property row with '*' when its panel name is given. '''
    lines = []
    header = f"{'metric':24s} {'before':>10s} {'after':>10s} {'change':>11s}"
    lines.append(header)
    for name, row in report.items():
        marker = "*" if name == intendedName else " "
        lines.append(
            f"{marker}{name:23s} {row['before']:10.4f} "
            f"{row['after']:10.4f} {row['change']:+11.4f}")
    return "\n".join(lines)
