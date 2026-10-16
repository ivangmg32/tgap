# The wrapper - a new TGAP study in a few lines

TSAP is easy to use because a model is just *something with `predict(series)`*
and a transformation is just *a function `(series, delta) -> series`*.
`tgap_wrapper.py` gives TGAP the same feel. **No classes, no base classes, no
files in `core/` to edit.** You supply functions; the wrapper loads the data,
checks your functions for the usual mistakes, runs the explainer and writes
the CSV / PNG / `TUTORIAL.md` outputs.

```python
from tgap_wrapper import Wrapper

w = Wrapper.fromCsv("my_study", "messages.csv", groups="teams.csv")   # 1. data

@w.model                                                              # 2. model
def predict(snapshots):                 # list of graphs, oldest first -> ONE number
    last = snapshots[-1]
    return last.number_of_edges() / last.number_of_nodes()

@w.concept(measure=my_measure)                                        # 3. concepts
def my_concept(graph, delta):           # change ONE graph; delta 0.1 = "10% more"
    ...

w.concept(["bridge_width", "density"])  # built-in concepts, by name
w.explain()                                                           # 4. run
```

Run an example with any of these (they do the same):

```sh
tgap run script examples/wrapper/01_five_lines.py   # the tgap command
python run.py examples/wrapper/01_five_lines.py       # ONE file, no install needed
python run.py examples                                # all examples, no install
python examples/wrapper/01_five_lines.py              # plain Python (needs the libraries)
```

`tgap run script FILE` and `python run.py FILE.py` also run **your own** study
file, from any folder (on Windows use `py run.py FILE.py`). `run.py` sets up its
private environment by itself the first time.
 Results go to
`output/examples/wrapper_<name>/`; open `TUTORIAL.md` first.

| example | you learn to |
|---|---|
| [`01_five_lines.py`](01_five_lines.py) | run a whole study in five lines (made-up data, built-ins) |
| [`02_my_data_my_model.py`](02_my_data_my_model.py) | use **your CSV** and **your model as a function** (`@w.model`) |
| [`03_my_concept.py`](03_my_concept.py) | add **your own concept** as a function (`@w.concept`) |
| [`04_any_model_object.py`](04_any_model_object.py) | explain a **trained object** with a `predict` method (scikit-learn style) |
| [`05_concept_over_time.py`](05_concept_over_time.py) | a concept that reshapes the **whole history** (`overTime=`) |
| [`06_stock_market.py`](06_stock_market.py) | the same on **Ivan's stock market** data (offline) |

## What you get

`w.explain()` writes, to `output/examples/<name>/`: the table
(`explanation.csv`, `explanation.png`), the response curves
(`sensitivity.png`), your data over time (`graph_over_time.png`), and the
**paper-style pictures** that show where and when the model reacts:

| picture | answers |
|---|---|
| `what_changed.png` | what does each concept DO to my graph? (before / after / difference) |
| `when_it_mattered.png` | in which snapshot did it matter? |
| `edge_impact.png`, `node_impact.png` | which ties / which people does the model lean on? |
| `edge_over_time.png` | which tie, in which snapshot? |
| `impact_heatmap.png` | the whole explanation in one picture |
| `bridge_matrix.png` | ties between every pair of groups (3+ groups) |
| `beeswarm.png`, `boxplot.png` | how steady is each effect? every impact over many sliding windows of the history, as in the paper |
| `dependence.png` | does the effect grow with how much of the concept there already is? |
| `how_tgap_works.png` | the method as one diagram |
| `side_effects.png`, `validity_map.png` | can I trust each experiment? does a concept change only what it should? |
| `impacts_by_direction.png`, `impact_distribution.png` | more vs less of each concept; the spread of impacts |
| `sparsity.png`, `tsap_summary.png`, `concept_trajectories.png` | how few things carry the answer; the original TSAP chart; the graph's properties over time |

`TUTORIAL.md` shows every picture with a plain-English caption. They re-ask
your model up to 40 times per picture; for a very slow model use
`w.explain(figures=False)` (or `figureBudget=10`).

## Reference

**Data** - `Wrapper.fromCsv(name, edges, groups=None, snapshots=6)`,
`Wrapper.synthetic(name)`, or `Wrapper(name, snapshots, groups)` if you already
have a list of `networkx` graphs (oldest first) and the groups as sets of nodes.
Without `groups`, TGAP finds two groups itself the first time something needs
them (`w.groups`).

**Model** - `w.model(...)`, any of:

| you write | meaning |
|---|---|
| `@w.model` on `def f(snapshots): ...` | a function returning one number |
| `@w.model(on="last")` on `def f(graph): ...` | the same, but it only sees the latest graph |
| `w.model(obj)` | any object with a `predict(snapshots)` method |
| `w.model("trend_bridge_width")` | a built-in model by name |

**Concept** - `w.concept(...)`, any of:

| you write | meaning |
|---|---|
| `w.concept("density")` / `w.concept(["density", "churn"])` | built-in concepts: `bridge_width`, `centralization`, `density`, `bridge_trend`, `churn` |
| `@w.concept` on `def f(graph, delta): ...` | change one snapshot; edit the graph you receive (it is a copy) or return a new one |
| `... def f(graph, delta, rng)` | the same with a seeded `random.Random` for random choices |
| `measure=fn` | `fn(graph) -> number`: the concept's value. Lets TGAP divide by how far it **really** moved |
| `keepsEdgeCount=False` | say so when adding / removing ties is the point (default `True`, and checked) |
| `overTime=fn, measure=fn2` | `fn(snapshots, delta)` reshapes the whole history; `fn2(snapshots)` measures it |
| `absolute=True` | for concepts that can be 0 (a slope): delta is added instead of multiplied |
| `name="..."` | label in the results (default: the function's name) |
| `w.concept(MyTransformation())` | a full `TemporalGraphTransformation` object, if you already have one |

**Rules for a concept** (the wrapper checks them before running):
`delta > 0` must make the measured value go **up**; never rely on global state
for random choices (use `rng`); keep the people (nodes) fixed; the same graph and
delta must always give the same result.

**Run** - `w.check()` (done automatically) reports problems in plain English;
`w.explain(deltas=(0.1, 0.25), sweep=True, folder=None)` runs TGAP and returns
the explanation as a table.

## What the wrapper does NOT change

The rules of the method stay exactly as in `core/`: one concept at a time,
impact = change in prediction / change actually achieved, `1 + 2K` model calls.
The wrapper only removes the ceremony around them. For the full research
protocol (validity gating, leakage checks, six models) use the real-data
pipeline (`python run.py realdata`); the wrapper is for studies and
prototypes.
