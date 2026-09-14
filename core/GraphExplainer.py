'''
The explainer machinery, shared by the static and temporal explainers.

The method is TSAP's, unchanged:

    baseline   = model.predict(x)
    perturbed  = model.predict(transform(x, delta))
    impact     = (perturbed - baseline) / |delta|

`impact` is a numerical derivative: "how much does the output move per
unit of property change". Positive = increasing this property pushes the
prediction UP; negative = pushes it DOWN. Computing it for property in
{Bridge Width, Centralization, ...} and delta in {+10%, -10%} gives the
explanation dictionary - one number per human-meaningful question.

Cost per explanation: 1 + 2 * (number of transformations) model calls.
(TSAP: 5 calls. TGAP with 2 transformations: 5 calls. Same efficiency.)

This file contains:
    ExplainerBase  - all the shared logic (explain, plots, summaries)
    GraphExplainer - the explainer for STATIC graphs + a GraphModel
The temporal version (TgapExplainer) lives in TemporalGraphExplainer.py.

The plotting code (signed-log summary bars, sensitivity sweeps, global
boxplots) is a faithful port of TsapExplainer so the two tools produce
the same visual language. Every plot method returns the plotly figure and
accepts show=False, so experiments and tests can run headless.
'''

import math

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go


def _panelValue(metric, x):
    ''' Evaluate a Metric on either a single graph or a temporal graph
    (mean across snapshots) - used for the leakage panel. '''
    if isinstance(x, list):
        return float(np.mean([metric.measure(g) for g in x]))
    return float(metric.measure(x))


class ExplainerBase:
    ''' Shared engine for perturbation-based explanations.

    Subclasses only define HOW a transformation is applied to their input
    type (a single graph, or a list of snapshots) by overriding
    _applyTransformation. Everything else - the explanation loop, the
    summary scale, the three plot types - is identical for both, so it
    lives here once. '''

    def __init__(self, model, transformations=None, defaultDelta=0.1,
                 normalization="achieved"):
        '''
        model           : object with predict(x) -> float
                          (a GraphModel or TemporalGraphModel)
        transformations : list of TemporalGraphTransformation instances
                          defining WHICH properties to explain. If None,
                          defaults are built AT EXPLAIN TIME: one community
                          partition is detected from the input and SHARED
                          by a BridgeWidth and a Centralization
                          transformation - so the defaults are leakage-free
                          (an unconstrained Centralization default would
                          silently contaminate bridge width; measured to be
                          large, see Transformations.py docstrings).
        defaultDelta    : requested nudge size used by explain(); 0.1 = 10%.
        normalization   : how impacts are normalized (see explainDetailed):
                          "achieved"  - divide by the property change the
                                        transformation ACTUALLY realized
                                        (default; scientifically preferred,
                                        see note below)
                          "requested" - divide by the requested delta
                                        (TSAP's literal formula)

        Why "achieved" is the default: for continuous time-series the two
        are identical (multiplying a series by 1.1 changes volatility by
        exactly 10%), so TSAP's /|delta| IS achieved-change normalization.
        Graphs are discrete: a requested +10% on 6 bridges realizes as
        +1 edge = +16.7%. Dividing by the requested 0.1 would inflate the
        impact by that rounding ratio; dividing by the achieved 1/6 makes
        the impact a true finite-difference sensitivity (for relative
        deltaMode: an estimate of d(prediction)/d(log property)). So
        "achieved" is not a departure from TSAP - it is the faithful port
        of TSAP's semantics to a discrete domain.
        '''
        self.model = model
        self.transformations = transformations
        self.delta = defaultDelta
        self.normalization = normalization

    ##  Hook to be implemented by subclasses  ##

    def _applyTransformation(self, x, trans, delta):
        ''' Apply transformation `trans` with nudge `delta` to input `x`.
        GraphExplainer transforms one graph; TgapExplainer transforms a
        whole list of snapshots. '''
        raise NotImplementedError

    ##  Defaults, resolved lazily  ##

    def _resolveTransformations(self, x):
        ''' Return the transformation list, building leak-free defaults
        from the input if the user did not pass any: detect ONE partition
        (from the last snapshot, for temporal input) and share it between
        BridgeWidth and Centralization, so the centralization rewiring is
        bridge-preserving. Detection is deterministic, so repeated calls
        agree; still, pass explicit transformations for real experiments
        (see Communities.py for why detected partitions are fragile). '''
        if self.transformations is not None:
            return self.transformations
        # Imported here (not at module top) to avoid a circular import:
        # Transformations -> TemporalGraphTransformation only, but this
        # module is imported from core/__init__ alongside them.
        from .Transformations import (
            BridgeWidthTransformation,
            CentralizationTransformation,
        )
        from .Communities import detectTwoCommunities
        lastGraph = x[-1] if isinstance(x, list) else x
        communities = detectTwoCommunities(lastGraph)
        return [
            BridgeWidthTransformation(communities),
            CentralizationTransformation(communities),
        ]

    ##  The explanation itself  ##

    def explain(self, x):
        ''' Returns a dictionary with the most relevant aspects of the
        model's behavior on input x, e.g.:

            {'Increase Bridge Width (10.0%)':    +3.2,
             'Decrease Bridge Width (10.0%)':    -2.9,
             'Increase Centralization (10.0%)':  -0.4,
             'Decrease Centralization (10.0%)':  +0.3}

        Each value is (perturbedPrediction - baseline) normalized by the
        property change (achieved or requested - see __init__). Read it
        as: the model's SENSITIVITY to that property, in that direction.
        Scientific reading: this is a counterfactual sensitivity of the
        MODEL, not a causal claim about the real-world system.

        For provenance (requested vs achieved change, no-op detection,
        leakage into other properties) use explainDetailed. '''
        return {r["label"]: r["impact"] for r in self.explainDetailed(x)}

    def explainDetailed(self, x, leakageMetrics=None):
        ''' The full-provenance version of explain(). Returns a list of
        records (one per transformation x direction), each a dict:

          label          - e.g. "Increase Bridge Width (10.0%)"
          transformation - the transformation's name attribute
          requestedDelta - the delta handed to the transformation
          achievedDelta  - the property change actually realized:
                             relative deltaMode: (pT - p0) / |p0|
                             absolute deltaMode: pT - p0
                           None when the property is not measurable
          deltaMode      - "relative" or "absolute" (units of achievedDelta)
          baseline       - model.predict(original)
          transformed    - model.predict(perturbed)
          impact         - (transformed - baseline) / |normalizer|
          normalizer     - "achieved" or "requested" (what was actually
                           used - falls back to "requested", flagged here,
                           when the property is unmeasurable or unchanged
                           while the prediction moved)
          noop           - True when the perturbation realized NO property
                           change AND no prediction change (e.g. delta too
                           small to move a whole edge); impact is 0.0
          leakage        - {metricName: {"before", "after", "change"}} for
                           each metric in leakageMetrics (values averaged
                           over snapshots for temporal input); {} if none
                           requested. This separates the INTENDED property
                           change from unintended structural side effects.

        Model-call budget: exactly 1 + 2 x len(transformations) predict
        calls. propertyValue and leakage metrics are graph computations,
        not model calls, so the efficiency claim is unaffected. '''
        transformations = self._resolveTransformations(x)
        baseline = self.model.predict(x)  # baseline: 1 model call
        leakageMetrics = leakageMetrics or {}
        # Leakage baselines: computed once per metric on the original.
        leakBefore = {name: _panelValue(metric, x)
                      for name, metric in leakageMetrics.items()}
        records = []
        for trans in transformations:
            # Property on the original: once per transformation.
            p0 = trans.propertyValue(x) if self.normalization == "achieved" \
                else None
            for delta in [self.delta, -self.delta]:
                direction = "Increase" if delta > 0 else "Decrease"
                label = direction + " " + trans.name + \
                    " (" + str(100 * abs(delta)) + "%)"
                xT = self._applyTransformation(x, trans, delta)
                transformed = self.model.predict(xT)
                numerator = transformed - baseline

                # --- normalization ---
                achievedDelta = None
                normalizer = "requested"
                if p0 is not None:
                    pT = trans.propertyValue(xT)
                    if trans.deltaMode == "relative" and p0 != 0:
                        achievedDelta = (pT - p0) / abs(p0)
                    else:
                        # absolute mode, or p0 == 0 (relative undefined):
                        # fall back to the property's own units.
                        achievedDelta = pT - p0
                    if achievedDelta != 0:
                        normalizer = "achieved"
                # Compute the impact with whichever normalizer applies.
                noop = False
                if normalizer == "achieved":
                    impact = numerator / abs(achievedDelta)
                elif achievedDelta == 0 and numerator == 0:
                    # True no-op: nothing changed, honestly report 0
                    # (e.g. delta too small to move one whole edge).
                    impact = 0.0
                    noop = True
                else:
                    impact = numerator / abs(delta)

                # --- leakage panel ---
                leakage = {}
                for name, metric in leakageMetrics.items():
                    after = _panelValue(metric, xT)
                    leakage[name] = {
                        "before": leakBefore[name],
                        "after": after,
                        "change": after - leakBefore[name],
                    }

                records.append({
                    "label": label,
                    "transformation": trans.name,
                    "requestedDelta": delta,
                    "achievedDelta": achievedDelta,
                    "deltaMode": trans.deltaMode,
                    "baseline": baseline,
                    "transformed": transformed,
                    "impact": impact,
                    "normalizer": normalizer,
                    "noop": noop,
                    "leakage": leakage,
                })
        return records

    ##  Summary plot (local explanation)  ##

    def summaryData(self, x):
        ''' Returns the summary of the explanation on a signed logarithmic
        scale (ported from TsapExplainer.summaryData).

        Why a log scale? Impacts can differ by orders of magnitude
        (+8.3 next to +0.0004); on a linear axis the small bar vanishes.
        We plot log10 of the MAGNITUDE, put the SIGN back so direction
        survives, and shift everything up by `summand` so the smallest
        bar starts at zero (otherwise a small positive impact would draw
        a bar pointing left, which misleads).

        Returns: (labels, raw values, signed-log values, x-axis title). '''
        dictExplain = self.explain(x)
        labels = list(dictExplain.keys())
        values = list(dictExplain.values())
        # All-zero explanations (a model blind to every property) would
        # break log10; return flat zeros honestly instead.
        nonZeroMagnitudes = [abs(v) for v in values if v != 0]
        if not nonZeroMagnitudes:
            return labels, values, [0.0] * len(values), "Signed log₁₀(value)"
        minLog = math.floor(np.min(np.log10(nonZeroMagnitudes)))
        summand = abs(minLog) if minLog < 0 else 0
        signedLog = [
            np.sign(v) * (np.log10(abs(v)) + summand) if v != 0 else 0
            for v in values
        ]
        xtitle = 'Signed log₁₀(value)'
        if summand > 0:
            xtitle = 'Signed (log₁₀(value)+' + str(summand) + ")"
        return labels, values, signedLog, xtitle

    def plotSummary(self, x, title="", show=True):
        ''' Local explanation summary as a horizontal bar chart:
        red bars push the prediction up, blue bars push it down.
        (Same visual language as a SHAP/TSAP summary plot.) '''
        labels, values, signedLog, xtitle = self.summaryData(x)
        # Reverse so the first property appears at the TOP of the chart.
        labels = labels[::-1]
        values = values[::-1]
        signedLog = signedLog[::-1]
        fig = go.Figure(go.Bar(
            y=labels, x=signedLog, orientation='h',
            marker_color=['red' if v > 0 else 'blue' for v in values]
        ))
        fig.add_vline(x=0, line_dash='dash', line_color='black')
        fig.update_layout(xaxis_title=xtitle)
        if title != "":
            fig.update_layout(title={
                'text': title, 'x': 0.5, 'xanchor': 'center',
                'font': {'size': 24, 'family': "Arial, bold"}
            })
        if show:
            fig.show()
        return fig

    ##  Sensitivity curve (local explanation)  ##

    def plotTrans(self, x, trans=None,
                  minDelta=-0.2, maxDelta=0.2, nValues=40, yName="",
                  show=True):
        ''' Local explanation for a given input: sweep delta across
        [minDelta, maxDelta] and plot the impact on the output at each
        value. Reveals SHAPE (linearity, saturation, asymmetry) that a
        single number would hide.

        Expect STEPS in these curves: a graph changes by whole edges, so
        many nearby deltas round to the same transformed graph (see the
        discreteness note in Transformations.py).

        minDelta/maxDelta are ratios (0.2 = 20%); the axis shows %. '''
        if trans is None:
            trans = self._resolveTransformations(x)[0]
        X = np.linspace(minDelta, maxDelta, nValues)
        Y = []
        result = self.model.predict(x)  # baseline computed ONCE
        for delta in X:
            xT = self._applyTransformation(x, trans, delta)
            Y.append(self.model.predict(xT) - result)
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=100 * X, y=Y, mode="markers"))
        yaxisTitle = "Impact on the output"
        if yName != "":
            yaxisTitle += " in " + yName
        fig.update_layout(
            xaxis_title="Delta Change in " + trans.name + " (%)",
            yaxis_title=yaxisTitle)
        if show:
            fig.show()
        return fig

    ##  Global explanation  ##

    def boxplotTrans(self, xs, trans=None,
                     minDelta=-0.2, maxDelta=0.2, nValues=6, yName="",
                     show=True):
        ''' Global explanation over a LIST of inputs: for each delta,
        compute the impact on every input and draw the distribution as a
        boxplot. A wide box = the model reacts very differently depending
        on the input - itself an important finding.

        xs      : list of inputs (graphs, or temporal graphs)
        nValues : number of delta values in [minDelta, maxDelta] '''
        if trans is None:
            trans = self._resolveTransformations(xs[0])[0]
        X = np.linspace(minDelta, maxDelta, nValues)
        # Baselines depend only on the inputs, not on delta: compute each
        # ONE time up front. (TSAP recomputes them inside the delta loop -
        # a known inefficiency we deliberately do not replicate.)
        baselines = [self.model.predict(x) for x in xs]
        df = pd.DataFrame({})
        for delta in X:
            distrib = []
            for x, baseline in zip(xs, baselines):
                xT = self._applyTransformation(x, trans, delta)
                distrib.append(self.model.predict(xT) - baseline)
            df[str(round(delta * 100, 2))] = distrib
        fig = px.box(df)
        yaxisTitle = "Impact on the output"
        if yName != "":
            yaxisTitle += " in " + yName
        fig.update_layout(
            xaxis_title="Delta in " + trans.name + " (%)",
            yaxis_title=yaxisTitle)
        if show:
            fig.show()
        return fig


class GraphExplainer(ExplainerBase):
    ''' Explainer for STATIC graphs: pairs a GraphModel (predict(graph)
    -> float) with single-graph transformations. Use this when the model
    scores one snapshot in isolation (e.g. "how healthy is this ecosystem
    right now, and which structural change would move that score?"). '''

    def _applyTransformation(self, graph, trans, delta):
        return trans.transformGraph(graph, delta)
