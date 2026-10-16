'''
TgapExplainer - the temporal-graph explainer, TGAP's counterpart of
TsapExplainer.

It answers, for a model that reads a sequence of graph snapshots:

    "If the ecosystem's recent history had had 10% wider bridges
     (or 10% more centralization, ...), how would the model's
     prediction change?"

All the machinery (explanation loop, summary bars, sensitivity sweeps,
global boxplots) is inherited from ExplainerBase - see GraphExplainer.py.
The only temporal-specific part is how a transformation is applied:
to EVERY snapshot in the window, so the property changes consistently
across the whole observed history (the counterfactual reading; see
TemporalGraphTransformation.transform for the rationale).

Typical usage (mirrors TsapExplainer exactly):

    model     = TrendTemporalModel(CohesionMetric())
    explainer = TgapExplainer(model)
    print(explainer.explain(temporalGraph))       # the raw numbers
    explainer.plotSummary(temporalGraph)          # local: bar chart
    explainer.plotTrans(temporalGraph)            # local: sensitivity curve
    explainer.boxplotTrans(listOfTemporalGraphs)  # global: boxplots
'''

from .GraphExplainer import ExplainerBase


class TgapExplainer(ExplainerBase):
    ''' This explainer will transform the temporal graph and measure
    the impact on the output. '''

    def _applyTransformation(self, temporalGraph, trans, delta):
        # Delegate to the transformation's temporal mode: apply the
        # single-graph transformation to every snapshot in the list.
        return trans.transform(temporalGraph, delta)
