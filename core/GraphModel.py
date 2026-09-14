'''
Interface to be implemented for analyzing a static graph.

This mirrors TSAP's TsModel: the explainer treats the model as a black box
with a single button, `predict`. Anything that can take a networkx.Graph and
return one float can be explained - a GNN, a heuristic, or a plain metric.
That single-method contract is what makes the explainer MODEL-AGNOSTIC.
'''


class GraphModel:
    ''' This class should be implemented for each specific graph
    forecasting/scoring model (e.g. a GNN) to be used with the explainer.
    It can also be used to create a wrapper around any existing
    implementation from any library. '''

    def predict(self, graph):
        ''' Given a networkx.Graph, return the output as a float
        (e.g. a risk score, a health score, a predicted quantity).
        This must be overridden by subclasses. '''
        raise NotImplementedError("'predict' method should be implemented")


class MetricGraphModel(GraphModel):
    ''' The simplest possible GraphModel: it wraps a Metric, so that
    "the model's prediction" is just the value of that metric.

    Why is this useful?
    1. It lets TGAP explain a METRIC, not only a learned model
       ("which structural change moves cohesion the most?").
    2. It is a KNOWN-TRUTH model for testing the explainer: we know
       exactly how a metric reacts to a transformation, so we can check
       that the explanation tells the truth (the sanity-check exercise). '''

    def __init__(self, metric):
        # metric: any object implementing Metric.measure(graph) -> float
        self.metric = metric

    def predict(self, graph):
        return self.metric.measure(graph)
