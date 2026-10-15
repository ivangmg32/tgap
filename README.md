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

## Run it: one command

You need **Python 3.9 or newer** ([python.org](https://www.python.org/downloads/);
on Windows tick *"Add python.exe to PATH"* during installation). Nothing else.

```bash
git clone <this repository>
cd tgap
python run.py            # Windows: if "python" is not found, use  py run.py
```

That is all. On the first run `run.py`:

1. checks your Python version;
2. creates a **private environment** in `.venv/` and installs the libraries
   into it (1–3 minutes, first run only; your system Python is not touched);
3. keeps temporary files and caches inside the project (`.tgap_cache/`), so a
   full, locked or non-ASCII system `TEMP` folder cannot break anything;
4. runs a quick tour: an environment check, the demos and the easy examples.

Results are written as **CSV + PNG** to `output/examples/`. If anything goes
wrong you get a short message in plain English saying what happened and how
to fix it; the technical details go to `output/logs/`.

| command | what it runs | time |
|---|---|---|
| `python run.py` | check + demos + easy examples | ~2 min |
| `python run.py examples` | only the easy examples | ~30 s |
| `python run.py all` | the full research pipeline (downloads 8 datasets, ~100 MB) | ~20 min |
| `python run.py synthetic` | the synthetic known-truth evaluation (RQ1–RQ8) | |
| `python run.py realdata publication` | any steps, in the order given | |
| `python run.py tests` | the automatic test suite | ~8 min |
| `python run.py tgn --with-torch` | also install PyTorch and explain the learned model | |
| `python run.py --help` | every step and option | |
| `python run.py reset` | delete `.venv/` and caches, start fresh | |

Tested from a clean checkout on Python 3.9, 3.11, 3.12 and 3.13, with both the
newest libraries and the oldest versions `requirements.txt` allows.

<details>
<summary>Prefer to manage Python yourself?</summary>

```bash
pip install -r requirements.txt
python -m examples.synthetic_demos          # synthetic demos
python -m unittest discover -s tests        # the test suite
python run.py --no-venv examples            # or use run.py with your own Python
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
</details>

---

## Easy examples: your data, your model, your concept

Six short scripts in [`examples/`](examples/). Each starts with a
**PARAMETERS** block - change the values, run the file, and look at the CSV
and PNG files it writes to `output/examples/<name>/`.

```bash
python examples/01_quickstart.py
```

| file | what you change | what it shows |
|---|---|---|
| [`01_quickstart.py`](examples/01_quickstart.py) | size of a made-up graph, model, concepts, delta | TGAP in 30 seconds |
| [`02_your_own_dataset.py`](examples/02_your_own_dataset.py) | path to **your CSV** and its column names | explaining a model on your own data |
| [`03_your_own_model.py`](examples/03_your_own_model.py) | the body of `predict()` | plugging in **your own model** |
| [`04_your_own_transformation.py`](examples/04_your_own_transformation.py) | a 20-line class | writing **your own concept** |
| [`05_real_dataset.py`](examples/05_real_dataset.py) | the dataset name | one of the 8 real datasets (downloads once) |
| [`06_my_project.py`](examples/06_my_project.py) | all of the above | **template**: copy it and make it yours |

Every run writes:

| file | contents |
|---|---|
| `explanation.csv` / `.png` | impact of each concept, both directions, every delta |
| `sensitivity.csv` / `.png` | the prediction as each concept goes from −50 % to +50 % |
| `graph_over_time.csv` / `.png` | your temporal graph: ties and bridge width per snapshot |

**Add your own dataset.** Save one row per interaction - *who, with whom,
when* - as a CSV:

```text
source,target,time
alice,bruno,2024-01-01
carla,ines,2024-01-02
```

`time` may be a date or a number. Commas or semicolons, UTF-8 or Excel's
Windows encoding are all fine. Set `CSV_FILE` and the column names in
`02_your_own_dataset.py` (or `06_my_project.py`). If you know the groups
(teams, departments), give a second CSV with `person,group` rows; otherwise
TGAP finds them.

**Add your own model.** Anything with one method:

```python
from core import TemporalGraphModel

class MyModel(TemporalGraphModel):
    def predict(self, snapshots):        # list of networkx graphs, oldest first
        return snapshots[-1].number_of_edges()   # any number you like
```

**Add your own concept.** Measure it, and change it by `delta`:

```python
from core import TemporalGraphTransformation

class MyConcept(TemporalGraphTransformation):
    name = "My Concept"
    preservesEdgeCount = False           # say honestly whether ties are added/removed

    def propertyValue(self, snapshots):  # MEASURE: one number
        ...

    def transformGraph(self, graph, delta):   # CHANGE one snapshot; return a copy
        g = graph.copy()
        ...
        return g
```

Then put the objects in the lists in your script. Nothing in `core/` is edited
- see [`examples/README.md`](examples/README.md) for more.

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

realdata/                            the real-data pipeline
├── download.py                      raw files -> data/
├── adapters/                        8 datasets, leakage-safe preprocessing
├── run_real_data.py                 TGAP on every dataset
├── compare_datasets.py              cross-dataset comparison
├── run_ncommunity.py                N = 2, 3, 4 community sweep
├── run_tgn.py, run_tgn_stability.py the learned model (TGN)
├── make_publication.py              the paper's figures and tables
└── plotting.py                      the shared publication theme

experiments/synthetic_evaluation.py  known-truth evaluation, RQ1-RQ8
examples/                            easy examples: your data / model / concept
tests/                               the test suite
docs/                                guides (see docs/README.md)
contrib/                             Iván's finance work, NOT part of TGAP
run.py                               ONE command: setup + run (start here)
paths.py                             every input/output folder, defined once
data/                                raw downloads (gitignored)
output/                              every generated result (see below)
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
> known-truth experiments in `experiments/synthetic_evaluation.py`.

---

## Reproducing the results

`python run.py all` runs steps 1–8 below in order (step 7 runs only if
PyTorch is installed). To run them by hand, use the commands below from the
repository root. Each step writes to exactly one folder under `output/`, and
every folder is defined once, in [`paths.py`](paths.py).

| step | command | writes to |
|---|---|---|
| 1 | `python -m experiments.synthetic_evaluation` | `output/synthetic/` |
| 2 | `python -m realdata.download` | `data/` |
| 3 | `python -m realdata.run_real_data` | `output/real_data/<mode>/<dataset>/` |
| 4 | `python -m realdata.compare_datasets` | `output/comparison/<mode>/` |
| 5 | `python -m realdata.run_ncommunity` | `output/ncommunity/<dataset>/` |
| 6 | `python -m realdata.run_tgn` *(torch)* | `output/tgn/<dataset>/` |
| 7 | `python -m realdata.run_tgn_stability` *(torch)* | `output/tgn_stability/<dataset>/` |
| 8 | `python -m realdata.make_publication` | `output/publication/` |

`<mode>` is the analysis mode; only `temporal_evaluation` (leakage-safe) is
committed. Step 8 only *reads* steps 3 and 5–7; it computes no new science
except the per-example local explanations.

```
output/
├── synthetic/        RQ1–RQ8 CSVs, figures, summary.json
├── real_data/        per-dataset explanations with validity flags
├── comparison/       cross-dataset table, observations, figures
├── ncommunity/       N-community sweep
├── tgn/              TGN explanation (one seed)
├── tgn_stability/    TGN over five seeds
└── publication/      what the paper uses
    ├── figures/      fig0–fig12, PNG + PDF
    ├── tables/       table1–table9, CSV + Markdown
    ├── attribution/  element-level attribution behind fig8/11/12
    └── figure_metadata.json
```

Run the tests with `python -m unittest discover -s tests`. They never write
into `output/`.

Every random choice is seeded (`seed=42`). One documented exception to exact
reproducibility is recorded in `realdata/README.md`.

---

## Citing and license

Part of the **CATALYST** project (PID2025; PIs Samer Hassan and
Iván García-Magariño). See [LICENSE](LICENSE).
