# TGAP — Temporal Graph Additive exPlanations

Model-agnostic, perturbation-based explanations for models that read
**temporal graphs**.

TGAP answers one question: *if the ecosystem's recent history had had 10%
wider bridges between communities (or more centralization, or more churn…),
how would the model's prediction change?* The size of that change, per
concept, **is** the explanation.

TGAP is the graph counterpart of **TSAP** (Time-Series Additive
exPlanations) and inherits its architecture: a generic explainer, a minimal
model interface, and **pluggable transformations**.

```
                    TGAP
                     │
          ┌──────────┴──────────┐
        MODEL             TRANSFORMATIONS
     predict(...)      pluggable custom classes
          └──────────┬──────────┘
                     ↓
              CONTROLLED CHANGE  →  NEW PREDICTION  →  IMPACT
```

---

## Install and run

For a managed Python environment and the private browser workbench, run
`.\tgap.cmd install` on Windows, or `sh ./tgap install` on Linux/macOS.
The installer asks about optional TGN and finance libraries and creates your
first account. Open a new terminal, then use `tgap start`, `tgap status`, and
`tgap stop`. Use `tgap run examples` for the research demos.

See [installation and self-hosting](docs/12-installation-and-self-hosting.md)
and [deployment knowledge](docs/13-sandbox-and-self-hosting-knowledge.md).
The original manual installation remains available below.

```bash
git clone <this repository>
cd tgap
pip install -r requirements.txt

python examples.py                       # synthetic demos
python -m examples.MyCustomTransformation   # the extensibility example
python -m unittest discover -s tests     # the test suite
```

Optional, for the learned-model experiments (§ *TGN* below):

```bash
pip install torch --index-url https://download.pytorch.org/whl/cpu
pip install torch_geometric
```

> **Windows note.** If `import torch` fails with
> `WinError 1114 … c10.dll`, install the
> [Microsoft VC++ 2015–2022 redistributable](https://aka.ms/vs/17/release/vc_redist.x64.exe).
> PyTorch needs `vcruntime140_1.dll`, which older Windows images lack.

---

## The 60-second version

```python
from core import (TgapExplainer, TrendTemporalModel, BridgeWidthMetric,
                  BridgeWidthTransformation, CentralizationTransformation,
                  makeTemporalGraph, detectTwoCommunities)

snapshots, communities = makeTemporalGraph(nSnapshots=6, nPerCommunity=8,
                                           bridgeWidth=10, seed=1)

model = TrendTemporalModel(BridgeWidthMetric(communities))

explainer = TgapExplainer(model, [
    BridgeWidthTransformation(communities, seed=42),
    CentralizationTransformation(communities, seed=42),
])

print(explainer.explain(snapshots))
# {'Increase Bridge Width (10.0%)':   +10.0,
#  'Decrease Bridge Width (10.0%)':   -10.0,
#  'Increase Centralization (10.0%)':   0.0,
#  'Decrease Centralization (10.0%)':   0.0}
```

The output is **a number per concept per direction** — a sensitivity, read
as *"per unit of relative change in this concept, the model's output moves
this much."* It is a property of the **model**, not a causal claim about the
world.

---

## How to add your own transformation

**This is the core extensibility feature: you never edit TGAP's core.**

Implement three things and pass an instance to the explainer.

```python
from core import TemporalGraphTransformation

class MyTransformation(TemporalGraphTransformation):
    name = "My Concept"                  # 1. labels the explanation row

    # Does your concept promise to keep the total edge count fixed?
    # Say so honestly - the feasibility gate reads this.
    preservesEdgeCount = False

    def propertyValue(self, x):          # 2. MEASURE the concept
        snapshots = x if isinstance(x, list) else [x]
        return float(...)

    def transformGraph(self, graph, delta):   # 3. CHANGE it by `delta`
        g = graph.copy()                 # never mutate the input
        ...
        return g
```

Then simply use it:

```python
explainer = TgapExplainer(model, [MyTransformation()])
explainer.explain(snapshots)
```

That is the whole registration mechanism: **an object in a list.** There is
no registry to edit, no decorator, no configuration file, no plugin
manifest. `core/Transformations/__init__.py` re-exports the five shipped
concepts as a convenience — adding yours there is optional and changes
nothing.

| You implement | Purpose |
|---|---|
| `name` | labels the explanation row |
| `propertyValue(x)` | measures the concept; TGAP divides by its **achieved** change |
| `transformGraph(graph, delta)` | structural concept, applied per snapshot |
| `transform(temporalGraph, delta)` | *instead*, for a temporal concept that reshapes the trajectory |
| `deltaMode` | `"relative"` (default) or `"absolute"` for properties that can legitimately be 0 |
| `preservesEdgeCount` | `True` (default) if your concept keeps the edge budget fixed |

**A complete worked example**, including feasibility, achieved delta and
limitations, is in
[`examples/MyCustomTransformation.py`](examples/MyCustomTransformation.py) —
run it with `python -m examples.MyCustomTransformation`. Its guarantees are
enforced by [`tests/test_custom_transformation.py`](tests/test_custom_transformation.py),
which fails if anyone adds per-transformation special-casing to the
explainer.

---

## Architecture

Folder and class names follow the original scaffolding by
**Prof. Iván García-Magariño**, deliberately preserved.

```
core/                                the TGAP framework
├── GraphModel.py                    predict(graph) -> float
├── TemporalGraphModel.py            predict(temporalGraph) -> float
├── TemporalGraphTransformation.py   the transformation contract
├── GraphExplainer.py                ExplainerBase + GraphExplainer
├── TemporalGraphExplainer.py        TgapExplainer
├── GraphMetric.py                   Metric.measure(graph) -> float
├── Communities.py                   Partition, bridges, detection  (N communities)
├── Feasibility.py                   can a transformation keep its promise?
├── Diagnostics.py                   leakage panel, model-call counting
├── SyntheticData.py                 known-truth generators
├── TgnModel.py                      learned model adapter (optional torch)
└── Transformations/                 ONE CONCEPT PER FILE
    ├── Base.py                      shared engine (setBridgeWidth, …)
    ├── BridgeWidth.py               ├── Centralization.py
    ├── Density.py                   ├── BridgeTrend.py
    └── Churn.py

realdata/          8 real datasets, leakage-safe preprocessing, runners
examples/          public API examples
tests/             the test suite
output/            generated results (see realdata/README.md)
```

**The explainer contains no knowledge of any concrete transformation.** It
uses only `name`, `propertyValue`, `deltaMode`, `transform` /
`transformGraph` — a fact asserted by a test that reads the explainer's own
source.

---

## N communities

TGAP supports a partition of **any** size — 1, 2, 3, … N.

```python
from core.Communities import Partition, bridgeMatrix, detectCommunities

partition = Partition([groupA, groupB, groupC], labels=["A", "B", "C"])

partition.communityOf(node)       # node  -> community id
partition[i]                      # community id -> nodes
partition.pairs()                 # [(0,1), (0,2), (1,2)]

bridgeMatrix(graph, partition)    # {(0,1): 12, (0,2): 5, (1,2): 8}
```

Target one bridge, or all of them:

```python
BridgeWidthTransformation(partition, communityPair=(0, 2))   # just A–C
BridgeWidthTransformation(partition)                          # aggregate
BridgeWidthMetric(partition, communityPair=(1, 2))            # just B–C
```

**Bridge width was derived, not redefined.** The requirement *"at N = 2 the
new result must equal the old"* forces the aggregate to be the **sum over
pairs** — the count of edges crossing any community boundary. Any averaged
or weighted alternative would disagree at N = 2 and invalidate every result
previously published from this code base.

**Backward compatibility is asserted, not assumed.** `Partition` subclasses
`tuple`, so `setA, setB = communities` still works at N = 2. Regression
tests in [`tests/test_communities.py`](tests/test_communities.py) require
that `setBridgeWidth` with and without `communityPair=(0,1)` agree **edge
for edge**.

---

## Explaining a learned model (TGN)

`core/TgnModel.py` trains a Temporal Graph Network (PyTorch Geometric) and
exposes it through Iván's contract:

```bash
python -m realdata.run_tgn            # Email-Eu-core
```

```
Email-Eu-core events → TGN → TgnTemporalGraphModel.predict(temporalGraph) → TGAP
```

TGAP sees **only `predict`** — no gradients, no memory internals, no
attention weights — which is what keeps it reusable with future models.
A test enforces this by handing the explainer a wrapper exposing nothing
else.

> **Scope.** The TGN is trained briefly and is **not** tuned for benchmark
> performance. The claim is *"TGAP explains a real learned temporal-graph
> model"*, not that this TGN is competitive. Training loss is written to the
> output so readers can see what was achieved.

---

## Real data

Eight real temporal datasets with leakage-safe preprocessing, validity
gating and per-dataset reports:

```bash
python -m realdata.download           # fetch raw files (once)
python -m realdata.run_real_data      # run TGAP on all 8
python -m realdata.compare_datasets   # cross-dataset comparison
```

Full detail, including the two case studies (Decentraland and
Email-Eu-core), preprocessing decisions and known limitations, is in
[`realdata/README.md`](realdata/README.md).

> Real data shows **applicability, not correctness** — there is no ground
> truth on real data. Correctness evidence comes from the synthetic
> known-truth experiments in `paper_evaluation.py`.

---

## Reproducing the results

```bash
python paper_evaluation.py            # synthetic evaluation (RQ1–RQ8)
python -m realdata.download
python -m realdata.run_real_data
python -m realdata.compare_datasets
python -m realdata.run_tgn
python -m unittest discover -s tests
```

Every random choice is seeded (`seed=42`). One documented exception to exact
reproducibility is recorded in `realdata/README.md`.

---

## Citing and license

Part of the **CATALYST** project (PID2025; PIs Samer Hassan and
Iván García-Magariño). See [LICENSE](LICENSE).
