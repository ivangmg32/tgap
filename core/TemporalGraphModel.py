'''
Interface to be implemented for analyzing a TEMPORAL graph
(a list of networkx.Graph snapshots, ordered oldest -> newest).

This is the direct analogue of TSAP's TsModel: where TsModel predicts the
next value of a series of numbers, a TemporalGraphModel looks at a series
of graphs and outputs one float (e.g. the predicted next value of a health
metric, or a risk score for the ecosystem).

Design note: heavy models (e.g. Temporal Graph Networks) should be wrapped
so they satisfy this one-method contract - exactly like LstmKeras wraps a
Keras LSTM behind TsModel.predict in TSAP. The two simple baseline models
below need no training at all; they exist so the explainer can be developed
and validated before any deep-learning model is available.
'''

import numpy as np


class TemporalGraphModel:
    ''' This class should be implemented for each specific temporal-graph
    forecasting model to be used with the explainer. It can also be used
    to create a wrapper around any existing implementation of any library
    (e.g. a TGN from PyTorch Geometric). '''

    def predict(self, temporalGraph):
        ''' Given a temporal graph (list of snapshots, oldest -> newest),
        return one float: the model's output of interest (e.g. the
        predicted next value of an ecosystem-health metric).
        This must be overridden by subclasses. '''
        raise NotImplementedError("'predict' method should be implemented")


class PersistenceTemporalModel(TemporalGraphModel):
    ''' Baseline model: "tomorrow will look like today".
    It predicts the next value of a metric as simply the metric value of
    the LAST snapshot. This is the graph analogue of predicting that the
    next price equals the current price.

    Because its behavior is fully understood, it is ideal for verifying
    that the explainer reports the truth: its explanation must react to a
    transformation exactly as the underlying metric does on the last
    snapshot, and be blind to everything else. '''

    def __init__(self, metric):
        # metric: any object implementing Metric.measure(graph) -> float
        self.metric = metric

    def predict(self, temporalGraph):
        return self.metric.measure(temporalGraph[-1])


class TrendTemporalModel(TemporalGraphModel):
    ''' Baseline model: "continue the recent trend".
    It computes the metric on every snapshot (giving an ordinary
    time-series of metric values), fits a straight line through those
    values, and extrapolates one step into the future.

    This is the simplest model that genuinely USES the temporal dimension,
    so its explanations should be sensitive to how a transformation
    changes the trajectory across snapshots - e.g. it can react to
    "bridge decay" (bridges getting thinner over time). '''

    def __init__(self, metric):
        # metric: any object implementing Metric.measure(graph) -> float
        self.metric = metric

    def predict(self, temporalGraph):
        # 1. Turn the temporal graph into a plain series of numbers.
        y = [self.metric.measure(g) for g in temporalGraph]
        # 2. With a single snapshot there is no trend: fall back to persistence.
        if len(y) < 2:
            return float(y[-1])
        # 3. Fit y = slope*t + intercept over t = 0..len(y)-1 ...
        t = np.arange(len(y))
        slope, intercept = np.polyfit(t, y, 1)
        # 4. ... and evaluate the line one step AFTER the last snapshot.
        return float(intercept + slope * len(y))


##  Known-truth models for validating the explainer  ##
#
# These models exist for FAITHFULNESS evaluation: their internal logic is
# chosen by US, so the correct explanation is derivable with pen and
# paper BEFORE running TGAP. If the explainer's output disagrees with the
# derivation, the explainer is wrong - there is no ambiguity to hide in.


class WeightedMetricModel(TemporalGraphModel):
    ''' prediction = sum of weight_i * metric_i(last snapshot).

    A linear model over concepts with KNOWN coefficients, e.g.:

        WeightedMetricModel([(2.0, BridgeWidthMetric(comm)),
                             (3.0, DegreeCentralizationMetric())])

    predicts 2*bridgeWidth + 3*centralization of the present.

    Known truth it provides: with achieved-relative normalization, the
    impact of transforming concept j should be approximately
    weight_j * p_j (the semi-elasticity of a linear term), where p_j is
    the concept's current value - plus measurable leakage through the
    other terms. mode="mean" averages each metric over all snapshots
    instead of reading only the last one. '''

    def __init__(self, weightedMetrics, mode="last"):
        # weightedMetrics: list of (weight, metric) pairs.
        self.weightedMetrics = weightedMetrics
        if mode not in ("last", "mean"):
            raise ValueError("mode must be 'last' or 'mean'")
        self.mode = mode

    def predict(self, temporalGraph):
        total = 0.0
        for weight, metric in self.weightedMetrics:
            if self.mode == "last":
                value = metric.measure(temporalGraph[-1])
            else:
                value = float(np.mean(
                    [metric.measure(g) for g in temporalGraph]))
            total += weight * value
        return float(total)


class SlopeModel(TemporalGraphModel):
    ''' prediction = OLS slope of the metric across snapshots - a model
    that reads ONLY the trajectory, not the level.

    Known truth it provides: it must react strongly to trajectory
    transformations (BridgeTrend, when the metric is bridge width) and
    be exactly blind to any transformation that shifts all snapshots
    uniformly without changing the slope. The mirror image of
    PersistenceTemporalModel (which reads only the level of the
    present). '''

    def __init__(self, metric):
        self.metric = metric

    def predict(self, temporalGraph):
        y = [self.metric.measure(g) for g in temporalGraph]
        if len(y) < 2:
            return 0.0  # a single snapshot has no slope
        slope, _ = np.polyfit(np.arange(len(y)), y, 1)
        return float(slope)
