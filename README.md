# tgap
Temporal Graph Additive Explanations

TGAP is the graph counterpart of [TSAP](../tsap_v2.1) (Time-Series Additive
exPlanations), built for the CATALYST project. It explains any model that
reads a (temporal) graph and outputs a number, by asking human-meaningful
counterfactual questions:

> *"If the bridges between these two communities were 10% wider, how would
> the model's prediction change?"*

The impact of each structural nudge, divided by the nudge size, **is** the
explanation — a numerical sensitivity per interpretable property, at the
cost of only `1 + 2 × properties` model calls.

## Quickstart

```bash
pip install -r requirements.txt
python examples.py            # interactive charts
python examples.py --no-show  # console only
python -m unittest discover -s tests   # test suite (75 tests)
python evaluation.py          # quick check: faithfulness / stability / efficiency / leakage
python paper_evaluation.py    # full RQ1-RQ8 suite -> output/paper/ (CSVs, figures, summary.json)
```

`evaluation.py` is the fast developer-facing check and writes to `output/`.
`paper_evaluation.py` is the paper artifact: eight research questions
(known-truth faithfulness, temporal sensitivity, stability, efficiency,
delta sensitivity, leakage, graph-size robustness, normalization
ablation), writing CSVs, publication figures and `summary.json` to
`output/paper/`. Neither overwrites the other's outputs.

**Normalization note (v0.2):** impacts are normalized by the property
change the transformation *actually achieved* (graphs are discrete: a
requested +10% on 6 bridges realizes as +16.7%). This makes the impact a
true finite-difference sensitivity — for relative-mode concepts, an
estimate of d(prediction)/d(log property). `normalization="requested"`
reproduces TSAP's literal formula. Full rationale and audit:
[docs/03-TGAP-technical-audit.md](../docs/03-TGAP-technical-audit.md).

**Scientific reading:** TGAP measures *model sensitivity to controlled
counterfactual transformations* — concept attribution for the model's
behavior, not causal claims about the real-world ecosystem.

## Structure

```
core/
├── GraphModel.py                 interface: predict(graph) -> float
│                                 + MetricGraphModel (wrap a metric as a model)
├── TemporalGraphModel.py         interface: predict([graphs]) -> float
│                                 + Persistence / Trend baseline models
├── GraphMetric.py                interface: measure(graph) -> float
│                                 + Density, DegreeCentralization,
│                                   BridgeWidth, Cohesion metrics
├── TemporalGraphTransformation.py  transformation base class + design rules
├── Transformations.py            BridgeWidth / Centralization / Density
├── GraphExplainer.py             shared engine + static-graph explainer
├── TemporalGraphExplainer.py     TgapExplainer (the temporal explainer)
├── Communities.py                two-community partition helpers
└── SyntheticData.py              known-truth synthetic ecosystems
examples.py                       end-to-end demos incl. sanity check
```

## Correspondence with TSAP

| TSAP | TGAP |
|---|---|
| `TsModel.predict(series) → float` | `TemporalGraphModel.predict([graphs]) → float` |
| a `pandas.Series` of values | a `list` of `networkx.Graph` snapshots |
| `transformVolatility` (how jumpy) | `ChurnTransformation` (how much history differs from the present) |
| `transformTrendReverse` (trajectory reshaped, last value fixed) | `BridgeTrendTransformation` (bridge trajectory reshaped, last **snapshot** fixed — the "bridge decay" counterfactual) |
| *(no static analogue)* | structural: `BridgeWidthTransformation`, `CentralizationTransformation`, `DensityTransformation` |
| anchor: last value kept fixed | anchor: last snapshot untouched (temporal) + node set & edge count kept fixed (structural) |
| `TsapExplainer.explain / plotSummary / plotTrans / boxplotTrans` | `TgapExplainer` — same methods, same signatures |

## Minimal usage

```python
from core import (TgapExplainer, TrendTemporalModel, CohesionMetric,
                  BridgeWidthTransformation, makeTemporalGraph)

temporalGraph, communities = makeTemporalGraph(bridgeDrift=1)  # decaying bridge
model = TrendTemporalModel(CohesionMetric())        # forecasts next cohesion
explainer = TgapExplainer(model)

print(explainer.explain(temporalGraph))   # {'Increase Bridge Width (10.0%)': ..., ...}
explainer.plotSummary(temporalGraph)      # local bar chart
explainer.boxplotTrans([temporalGraph])   # global boxplot
```

Any real model (e.g. a Temporal Graph Network) plugs in by wrapping it in a
class with a single `predict(temporalGraph) -> float` method — exactly how
TSAP wraps Keras LSTMs behind `TsModel`.
