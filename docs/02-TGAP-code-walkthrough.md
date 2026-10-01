# TGAP Code Walkthrough — Every File, Every Part, Line by Line

> **Who this is for:** you, after reading
> [01-TSAP-explained-simply.md](01-TSAP-explained-simply.md).
> **What this is:** a guided tour of every file in `tgap/`, in the order that
> makes them easiest to understand. Code blocks are quoted from the real
> files; under each block, every line (or small group of lines) is explained.
> **How to use it:** open the file being discussed in one window, this doc in
> another. Type the mini-experiments as you go — they take seconds and teach
> more than reading.

---

## Table of contents

1. [Python survival kit](#1-python-survival-kit)
2. [networkx survival kit](#2-networkx-survival-kit)
3. [The big picture: how the files call each other](#3-the-big-picture)
4. [`core/__init__.py` — the package front door](#4-core__init__py)
5. [`core/GraphModel.py` — the one-button interface](#5-coregraphmodelpy)
6. [`core/TemporalGraphModel.py` — models that read history](#6-coretemporalgraphmodelpy)
7. [`core/Communities.py` — who is on which side](#7-corecommunitiespy)
8. [`core/GraphMetric.py` — one number per graph](#8-coregraphmetricpy)
9. [`core/TemporalGraphTransformation.py` — the rules of the game](#9-coretemporalgraphtransformationpy)
10. [`core/Transformations.py` — the heart of TGAP](#10-coretransformationspy)
11. [`core/GraphExplainer.py` — the engine](#11-coregraphexplainerpy)
12. [`core/TemporalGraphExplainer.py` — four lines that matter](#12-coretemporalgraphexplainerpy)
13. [`core/SyntheticData.py` — worlds with known truth](#13-coresyntheticdatapy)
14. [`examples.py` — the proofs](#14-examplespy)
15. [The design rules, collected](#15-the-design-rules-collected)
16. [The two bugs testing caught (and why they matter)](#16-the-two-bugs-testing-caught)
17. [Exercises](#17-exercises)

---

## 1. Python survival kit

Only the constructs that actually appear in the code. Skip what you know.

### Classes, `self`, `__init__`

```python
class Dog:
    def __init__(self, name):     # runs when you write Dog("Rex")
        self.name = name          # store name ON THIS particular dog
    def bark(self):
        return self.name + " says woof"

d = Dog("Rex")
d.bark()                          # 'Rex says woof'
```

- `class` = a blueprint. `Dog("Rex")` = build one object from it.
- `__init__` = the constructor, runs once at creation. Its job is almost always
  "store the settings on `self`".
- `self` = "this particular object". Every method's first parameter. When you
  call `d.bark()`, Python secretly passes `d` as `self`.

### Inheritance and overriding

```python
class Animal:
    def speak(self):
        raise NotImplementedError("subclass must implement")

class Dog(Animal):                # Dog IS an Animal
    def speak(self):              # this REPLACES (overrides) Animal.speak
        return "woof"
```

The whole TGAP architecture is this pattern: a parent class declares *what*
must exist (`predict`, `measure`, `transformGraph`), children provide *how*.
`raise NotImplementedError(...)` makes forgetting to override a loud error
instead of silent nonsense.

### Comprehensions (compact loops)

```python
[x * 2 for x in [1, 2, 3]]                  # list:  [2, 4, 6]
[x for x in [1, 2, 3, 4] if x % 2 == 0]     # filtered list: [2, 4]
{(min(u,v), max(u,v)) for u, v in edges}    # SET comprehension (curly braces)
```

Read them right to left: "for each x in the list, (if condition), keep the
expression". Sets (`{...}`) hold unique items and support fast membership
tests (`e in mySet`) and algebra: `A - B` (in A not B), `A & B` (in both).

### Tuples and unpacking

```python
pair = (3, 7)          # a tuple: fixed-size bundle
a, b = pair            # unpacking: a=3, b=7
setA, setB = communities   # used constantly in TGAP
for u, v in g.edges():     # each edge arrives as a (u, v) tuple
```

### `sorted`, `key=`, `lambda`

```python
sorted(nodes, key=lambda n: g.degree(n))    # nodes ordered by their degree
max(nodes, key=lambda n: g.degree(n))       # the highest-degree node
```

`lambda n: ...` is a one-line unnamed function. `key=` tells sorted/max
"judge each item by this value, not by the item itself".

### Seeded randomness — the single most important idiom in this codebase

```python
import random
rng = random.Random(42)      # a PRIVATE random generator with a fixed seed
rng.sample([1,2,3,4,5], 2)   # ALWAYS the same 2 items, run after run
```

`random.Random(seed)` creates a personal dice-roller whose entire sequence of
"random" choices is fully determined by the seed. Same seed → same choices →
same transformed graph → **same explanation every time** (the *stability*
property). Every transformation re-creates its `rng` inside the method call,
so even calling it twice in a row gives identical results.

### Slicing on lists

```python
tg[-1]      # last element (the newest snapshot)
tg[:-1]     # everything EXCEPT the last
series[::5] # every 5th element (you saw this in TSAP)
```

### Odds and ends

- `f"  {key:38s} -> {value:+.3f}"` — an f-string: `{key:38s}` pads the text
  to 38 characters (aligned columns), `{value:+.3f}` prints 3 decimals with a
  forced +/− sign.
- `assert condition, "message"` — crash with the message if condition is
  false. Our executable truth-checks.
- `enumerate(items)` — loop yielding `(index, item)` pairs.
- `if __name__ == "__main__":` — "run this only when the file is executed
  directly, not when imported".
- `from .GraphMetric import Metric` — the leading dot means "from the same
  package (folder)". This is why files in `core/` can find each other.

---

## 2. networkx survival kit

`networkx` is Python's standard graph library. `import networkx as nx`.

```python
import networkx as nx
g = nx.Graph()                 # an empty UNDIRECTED graph
g.add_nodes_from([0, 1, 2, 3])
g.add_edge(0, 1)               # connect node 0 and node 1
g.add_edges_from([(1, 2), (2, 3)])
```

Everything TGAP uses, in one table:

| Call | Returns / does |
|---|---|
| `g.nodes()`, `g.edges()` | iterable of nodes / of `(u, v)` edge tuples |
| `g.number_of_nodes()`, `g.number_of_edges()` | counts |
| `g.has_edge(u, v)` | `True`/`False` (order doesn't matter — undirected) |
| `g.add_edge(u, v)`, `g.remove_edge(u, v)` | modify in place |
| `g.add_edges_from(list)`, `g.remove_edges_from(list)` | bulk versions |
| `g.copy()` | independent duplicate — modify the copy, original untouched |
| `g.degree(n)` | how many edges touch node n |
| `g.neighbors(n)` | the nodes directly connected to n |
| `nx.density(g)` | existing edges ÷ possible edges (0..1) |
| `nx.non_edges(g)` | all pairs that are NOT connected |
| `nx.is_connected(g)` | is there a path between every pair of nodes? |
| `nx.bridges(g)` | the **cut-edges**: edges whose removal disconnects the graph |
| `nx.algebraic_connectivity(g, seed=...)` | the cohesion number (see §8) |

⚠️ **Naming collision to burn into memory:** in graph theory a "bridge"
(`nx.bridges`) is a *cut-edge* — an edge whose removal splits the graph. In
CATALYST a "bridge" is the *social bridge* — the bundle of ties between two
communities. Same word, different things. The code comments flag this
everywhere the clash appears.

One crucial habit the code enforces: **`g.add_edge` mutates the graph in
place.** That's why every transformation starts with `g = graph.copy()` —
the explainer still needs the untouched original to compute the baseline.

---

## 3. The big picture

Data flow of one explanation (demo 2, say):

```
SyntheticData.makeTemporalGraph ──► temporalGraph = [g0, g1, ..., g7]
                                    communities   = ({0..14}, {15..29})
                                            │
     TrendTemporalModel(CohesionMetric())   │       ◄── "the model"
                    │                       │
                    ▼                       ▼
            TgapExplainer(model, [BridgeWidthTransformation(communities),
                                  CentralizationTransformation(communities)])
                    │
                    │  explain(temporalGraph):
                    │    baseline = model.predict(tg)              ─┐
                    │    for each transformation, for delta ±0.1:   │ 5 model
                    │       tgT = trans.transform(tg, delta)        │ calls
                    │       impact = (predict(tgT) − baseline)/|δ| ─┘
                    ▼
        {'Increase Bridge Width (10.0%)': −0.24, ...}
                    │
                    ▼
        plotSummary / plotTrans / boxplotTrans
```

Who imports whom (arrows = "uses"):

```
examples.py ──► core/__init__.py ──► everything below

TemporalGraphExplainer ──► GraphExplainer (the shared engine)
GraphExplainer         ──► Transformations (for defaults)
Transformations        ──► TemporalGraphTransformation (base class)
                       ──► Communities (partitions, bridge listing)
GraphMetric            ──► Communities
TemporalGraphModel     ──► (numpy only)
GraphModel             ──► (nothing)
SyntheticData          ──► (networkx + random only)
```

Note what's at the bottom: the interfaces (`GraphModel`, `Metric`) depend on
nothing. Everything depends on them. That's the sign of a clean architecture —
the contracts are the foundation.

---

## 4. `core/__init__.py`

File: [core/\_\_init\_\_.py](../tgap/core/__init__.py)

A folder becomes a Python **package** when it contains an `__init__.py`. That
file runs when someone writes `import core`, and whatever it imports becomes
the package's public face.

```python
from .GraphMetric import (
    Metric,
    DensityMetric,
    ...
)
```

- Each `from .X import Y` pulls class `Y` from file `core/X.py` (the dot =
  same package) up to the package level.
- Result: users write `from core import TgapExplainer, CohesionMetric` and
  never need to know which file each class lives in. If we later reorganize
  files, user code doesn't break — only `__init__.py` changes.
- The big docstring at the top is deliberate: `import core` then
  `help(core)` prints it. It carries the TSAP↔TGAP correspondence table and
  the data conventions (what a `temporalGraph` is, what `delta` means), so
  the package documents itself.

---

## 5. `core/GraphModel.py`

File: [core/GraphModel.py](../tgap/core/GraphModel.py)

### The interface

```python
class GraphModel:
    def predict(self, graph):
        raise NotImplementedError("'predict' method should be implemented")
```

- Line 1: the class. No `__init__` — an interface holds no data.
- Line 2–3: the contract: *give me a graph, I give you one float.* If a
  subclass forgets to override it, calling `predict` crashes with a clear
  message instead of returning garbage.
- This is TSAP's `TsModel` with `series` swapped for `graph` — the
  model-agnostic trick, verbatim. (One deliberate improvement: TSAP wrote
  `raise "text"`, which is not even legal as an exception in Python 3;
  we raise a real `NotImplementedError`.)

### The wrapper

```python
class MetricGraphModel(GraphModel):
    def __init__(self, metric):
        self.metric = metric

    def predict(self, graph):
        return self.metric.measure(graph)
```

- `(GraphModel)` — inherits, so a `MetricGraphModel` *is a* `GraphModel` and
  fits anywhere the explainer expects one.
- `__init__` stores the metric object; `predict` just forwards to it.
- Two lines of logic, two big payoffs (from the docstring): (1) you can now
  *explain a metric* — "which structural change moves cohesion most?" — with
  no learned model anywhere; (2) it's a **known-truth model**: we know
  exactly how `BridgeWidthMetric` responds to a bridge transformation, so we
  can catch the explainer lying. Demo 1 is built on this.

---

## 6. `core/TemporalGraphModel.py`

File: [core/TemporalGraphModel.py](../tgap/core/TemporalGraphModel.py)

### The interface

```python
class TemporalGraphModel:
    def predict(self, temporalGraph):
        raise NotImplementedError("'predict' method should be implemented")
```

Identical shape to `GraphModel`, but the input is a **list of snapshots**
(oldest → newest). This is the class a future Temporal Graph Network wrapper
will subclass — exactly as `LstmKeras` subclasses `TsModel` in TSAP.

### Baseline 1: persistence

```python
class PersistenceTemporalModel(TemporalGraphModel):
    def __init__(self, metric):
        self.metric = metric

    def predict(self, temporalGraph):
        return self.metric.measure(temporalGraph[-1])
```

- `temporalGraph[-1]` — the last snapshot. That's the *entire* model:
  "tomorrow = today". It reads **only the present**.
- Why ship something so dumb? Because its blindness is a *feature* for
  testing: any transformation that anchors the last snapshot must produce an
  impact of exactly 0 on this model. Demo 4 asserts precisely that.

### Baseline 2: trend

```python
class TrendTemporalModel(TemporalGraphModel):
    def __init__(self, metric):
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
```

Line by line:

1. `y = [self.metric.measure(g) for g in temporalGraph]` — measure the metric
   on every snapshot. A list of graphs becomes an ordinary list of numbers.
   **This line is the conceptual bridge between TGAP and TSAP**: a temporal
   graph, seen through one metric, IS a time series.
2. Guard: you can't fit a line through one point.
3. `np.arange(n)` = `[0, 1, ..., n-1]` (the time axis).
   `np.polyfit(t, y, 1)` = least-squares fit of a degree-**1** polynomial
   (a straight line), returning `(slope, intercept)`.
4. The line's value at `t = len(y)` — i.e. one step into the future.
   `float(...)` converts numpy's number type to a plain Python float.

**Worked example.** Widths `y = [14, 12, 11, 10, 9, 8]` (decaying bridge):
polyfit gives slope ≈ −1.17, so the prediction is ≈ 8 − 1.17 ≈ 6.9. The
model says "the decay will continue". This is the simplest model that
genuinely *uses time* — and demo 4 shows the explainer can tell it apart
from the persistence model.

---

## 7. `core/Communities.py`

File: [core/Communities.py](../tgap/core/Communities.py)

Three small functions used by metrics and transformations alike.

### `detectTwoCommunities`

```python
def detectTwoCommunities(graph):
    communities = community.greedy_modularity_communities(graph)
    setA = set(communities[0])
    setB = set(graph.nodes()) - setA
    return setA, setB
```

- `greedy_modularity_communities` — a standard algorithm that groups nodes so
  that edges are dense *inside* groups and sparse *between* them. It is
  deterministic: same graph in, same groups out.
- It may find 3+ communities; we force exactly two: the largest found group
  becomes side A (`communities[0]` — results come sorted largest-first), and
  `set(graph.nodes()) - setA` (set subtraction) makes "everyone else" side B.
- The docstring's warning matters: auto-detection is for exploration. In an
  experiment, **pass the partition explicitly** — a perturbed graph might be
  re-partitioned differently, and then you'd be measuring "the detector
  changed its mind", not "the model reacted".

### `interCommunityEdges` / `intraCommunityEdges`

```python
def interCommunityEdges(graph, communities):
    setA, setB = communities
    bridges = [
        (u, v) for (u, v) in graph.edges()
        if (u in setA and v in setB) or (u in setB and v in setA)
    ]
    return sorted(bridges)
```

- Walk all edges; keep those with one endpoint on each side. The `or` covers
  both storage orders — networkx may hand you `(u, v)` either way round.
- These crossing edges **are** the CATALYST bridge; `len(...)` of this list is
  the bridge's width.
- `sorted(...)` before returning — this is not cosmetic. Random *sampling*
  from a list is only reproducible if the list itself is always in the same
  order. Sorting guarantees that. You'll see `sorted(...)` before every
  `rng.sample(...)` in the codebase, for exactly this reason.
- `intraCommunityEdges` is the mirror image (`and` both-inside instead), used
  when a transformation must "pay" for a bridge change with an internal edge.

---

## 8. `core/GraphMetric.py`

File: [core/GraphMetric.py](../tgap/core/GraphMetric.py)

### The interface

```python
class Metric:
    def measure(self, graph):
        raise NotImplementedError("'measure' method should be implemented")
```

Same interface pattern, third appearance. Give a graph, get one float.

### `DensityMetric`

```python
class DensityMetric(Metric):
    def measure(self, graph):
        return nx.density(graph)
```

One line: existing edges ÷ possible edges. Baseline "how connected is it".

### `DegreeCentralizationMetric`

```python
def measure(self, graph):
    n = graph.number_of_nodes()
    if n < 3:
        return 0.0  # centralization is undefined/trivial below 3 nodes
    degrees = [d for _, d in graph.degree()]
    maxDegree = max(degrees)
    return sum(maxDegree - d for d in degrees) / ((n - 1) * (n - 2))
```

- `graph.degree()` yields `(node, degree)` pairs; `for _, d in` keeps only
  the degree (the underscore is the convention for "value I don't need").
- The formula (Freeman centralization): sum every node's *shortfall* from the
  most-connected node, then divide by the largest that sum could possibly be
  — which is `(n−1)(n−2)`, achieved by a perfect star.
- Result lands in 0..1: `0` = everyone equal, `1` = one hub owns every tie.

**Worked example.** A star with 1 hub + 4 leaves: degrees `[4,1,1,1,1]`.
Sum of shortfalls = `0+3+3+3+3 = 12`. Denominator = `4×3 = 12`. Result **1.0** —
maximal centralization. A ring of 5 (everyone degree 2): shortfalls all 0 →
**0.0**. This is CATALYST's "coordinator burnout" risk quantified.

### `BridgeWidthMetric`

```python
def __init__(self, communities=None):
    self.communities = communities

def measure(self, graph):
    communities = self.communities
    if communities is None:
        communities = detectTwoCommunities(graph)
    return float(len(interCommunityEdges(graph, communities)))
```

- Stores an optional partition at construction; detects one per call
  otherwise (with the caveats from §7).
- Then it's literally "count the crossing edges". The simplest possible
  operationalization of *wide bridges*: the count is how many ties must fail
  before the two groups separate (along this partition).

### `CohesionMetric` — and the stability lesson

```python
def __init__(self, seed=42):
    self.seed = seed

def measure(self, graph):
    # A disconnected graph has, by definition, zero cohesion.
    # (networkx would raise an error, so we check first.)
    if graph.number_of_nodes() < 2 or not nx.is_connected(graph):
        return 0.0
    return float(nx.algebraic_connectivity(graph, seed=self.seed))
```

- **Algebraic connectivity** (the "Fiedler value"), in plain words: *how hard
  is it to cut this graph in two?* 0 = already in pieces; near 0 = there's a
  thin bottleneck somewhere; larger = well-knit. It's the perfect cohesion
  number for CATALYST because a graph held together by ONE narrow bridge
  scores near zero *even if both sides are internally dense* — it sees
  exactly the fragility wide bridges are about.
- The guard clause: disconnected graphs would make networkx raise an error;
  we return the honest answer (0) instead.
- **`seed=self.seed` is a bug fix with a story.** networkx computes this
  value with a *randomized* eigenvalue solver. Unseeded, the same graph
  returned *slightly different numbers on different calls* — which made the
  same explanation differ between runs, failing our stability test. One
  parameter fixes it. Full story in §16.

---

## 9. `core/TemporalGraphTransformation.py`

File: [core/TemporalGraphTransformation.py](../tgap/core/TemporalGraphTransformation.py)

The base class is tiny; its docstrings carry the design law of the project.

```python
class TemporalGraphTransformation:
    name = "Property"

    def transformGraph(self, graph, delta):
        raise NotImplementedError("'transformGraph' should be implemented")

    def transform(self, temporalGraph, delta):
        return [self.transformGraph(g, delta) for g in temporalGraph]
```

- `name = "Property"` — a **class attribute** (shared default, overridden by
  each subclass: `"Bridge Width"`, `"Churn"`, ...). It feeds the explanation
  labels (`"Increase Bridge Width (10.0%)"`) and plot axis titles. TSAP used
  the function's `__name__` for this; since our transformations are objects,
  they carry an explicit label instead.
- `transformGraph(graph, delta)` — change ONE property of ONE snapshot by
  ratio `delta`; return a NEW graph.
- `transform(temporalGraph, delta)` — the temporal default: apply
  `transformGraph` to *every* snapshot. Why every one? Because the question
  is counterfactual — "if the whole recent history had had 10% wider
  bridges, what would you predict?" — same as TSAP's volatility change
  applying to the whole series, not one point.

The docstring also records the **anchor rule** translation:

| | TSAP | TGAP |
|---|---|---|
| anchor | last value kept fixed | node set (and edge count) kept fixed |
| so that | prediction changes because of *shape*, not starting point | prediction changes because of *structure*, not size |

...and the taxonomy that the previous conversation round added:

- **Structural** transformations (BridgeWidth, Centralization, Density)
  implement `transformGraph` and inherit the uniform-over-time `transform`.
- **Temporal** transformations (BridgeTrend, Churn) override `transform`
  itself — they reshape the *trajectory* — and their `transformGraph` raises,
  because "change the trend of one snapshot" is meaningless.

---

## 10. `core/Transformations.py`

File: [core/Transformations.py](../tgap/core/Transformations.py)

The longest and most important file. Its module docstring makes two honest
points before any code:

- **Discreteness:** a series can change by exactly 10%; a graph changes by
  whole edges. We `round()`, so sensitivity curves come out **steppy** — not
  a bug, the honest geometry of discrete structures.
- **Leakage:** perfectly orthogonal structural properties don't exist (TSAP's
  volatility also nudges trend). We document leakage instead of hiding it.

### 10.1 `_edgeKey` — comparing edges across graphs

```python
def _edgeKey(u, v):
    return (u, v) if u <= v else (v, u)
```

An undirected edge might be stored as `(3, 7)` in one graph and `(7, 3)` in
another. Normalizing to (smaller, larger) makes set comparisons between
graphs' edge sets meaningful. Used by `ChurnTransformation`, which lives on
such comparisons. (The leading `_` means "module-private helper".)

### 10.2 `_safeToRemove` — don't shatter the graph by accident

```python
def _safeToRemove(graph, edges):
    cutEdges = set()
    for u, v in nx.bridges(graph):
        cutEdges.add((u, v))
        cutEdges.add((v, u))
    safe = [e for e in edges if e not in cutEdges]
    return safe if safe else list(edges)
```

- `nx.bridges(graph)` yields the **cut-edges** (graph-theory bridges — the
  naming clash from §2; the comment in the file flags it).
- Both orientations go into the set, since candidate tuples might be stored
  either way.
- Filter the candidates down to non-cut-edges; if *everything* was a
  cut-edge, fall back to the original list rather than returning nothing.
- Why bother: removing a cut-edge disconnects the graph, cohesion crashes to
  exactly 0, and the explanation gets polluted by an artifact of our own
  edit. Removing a "safe" edge keeps the counterfactual meaningful.

### 10.3 `setBridgeWidth` — the shared engine

This function exists because *two* transformations need "make the bridge
exactly this wide": `BridgeWidthTransformation` (one target from one delta)
and `BridgeTrendTransformation` (a different target per snapshot). Factoring
it out was the refactor in the temporal round.

```python
def setBridgeWidth(graph, communities, targetWidth, rng):
    g = graph.copy()
    setA, setB = communities

    bridges = interCommunityEdges(g, communities)
    width = len(bridges)
    targetWidth = max(1, targetWidth)  # never sever the last tie
    k = targetWidth - width  # >0: widen, <0: narrow
```

- `g = graph.copy()` — first line of every transformation. Never mutate the
  input; the explainer still needs the original for the baseline.
- `max(1, targetWidth)` — clamp: we never remove the last bridge. Total
  disconnection is a *different* counterfactual ("what if these communities
  had no contact at all?") and a much more brutal one than "a thinner
  bridge"; conflating them would distort the explanation.
- `k` — the signed number of edges to move.

The widen branch:

```python
    if k > 0:
        candidates = sorted(
            (a, b) for a in setA for b in setB if not g.has_edge(a, b)
        )
        toAdd = rng.sample(candidates, min(k, len(candidates)))
        g.add_edges_from(toAdd)
        intra = _safeToRemove(g, intraCommunityEdges(g, communities))
        toRemove = rng.sample(intra, min(len(toAdd), len(intra)))
        g.remove_edges_from(toRemove)
```

- `candidates` — every cross pair not yet connected (`sorted` → reproducible
  sampling, the §7 idiom).
- `rng.sample(candidates, min(k, len(candidates)))` — pick k of them;
  `min(...)` guards the edge case where fewer candidates exist than wanted.
  Note the `rng` comes *from the caller* — each transformation owns its
  determinism.
- Then the **payment**: remove the same number of intra-community edges
  (safe ones preferred). This is the anchor rule in action — total edge
  count unchanged, so the model sees the same amount of activity, just
  *routed* differently. A model reacting to this transformation is reacting
  to *routing*, which is exactly the wide-bridge question.

The narrow branch mirrors it: remove `|k|` bridges, pay back by adding intra
non-edges (the `a < b` in the candidate comprehension avoids listing each
same-side pair twice). And if `k == 0`, the graph passes through unchanged —
which is what creates the flat steps in sensitivity plots.

### 10.4 `BridgeWidthTransformation`

With the engine extracted, the class is small:

```python
class BridgeWidthTransformation(TemporalGraphTransformation):
    name = "Bridge Width"

    def __init__(self, communities=None, seed=42):
        self.communities = communities
        self.seed = seed

    def transformGraph(self, graph, delta):
        rng = random.Random(self.seed)
        communities = self.communities
        if communities is None:
            communities = detectTwoCommunities(graph)
        width = len(interCommunityEdges(graph, communities))
        target = round(width * (1 + delta))
        return setBridgeWidth(graph, communities, target, rng)
```

- `rng = random.Random(self.seed)` — **re-created on every call**, so calling
  twice gives identical output (stability). If the rng were created once in
  `__init__`, the second call would continue the random sequence and differ.
- `target = round(width * (1 + delta))` — TSAP-style relative delta: +10% of
  *the current width*. Width 6, delta +0.1 → `round(6.6)` = 7 → one bridge
  added. This ×(1+δ) is precisely `series *= factor` from TSAP's
  `transformVolatility`, in graph clothing.
- The docstring's `Leakage` note is honest: swapping intra↔inter edges under
  a fixed edge budget necessarily nudges internal density a little.

### 10.5 `CentralizationTransformation` — and the leakage lesson

Read this class knowing its history: **the first version leaked
catastrophically** (see §16), and the `communities`/`_sameSide` machinery is
the fix.

```python
    def __init__(self, communities=None, seed=42):
        self.communities = communities
        self.seed = seed

    def _sameSide(self, a, b):
        if self.communities is None:
            return True
        setA, _ = self.communities
        return (a in setA) == (b in setA)
```

- `_sameSide`: are two nodes in the same community? The trick in the last
  line: `(a in setA) == (b in setA)` is `True` when both are in A **or**
  both are not (i.e. both in B). Two membership tests, one comparison.
- If no partition was given, everything counts as "same side" — the
  constraint simply switches off (and the docstring warns you loudly about
  the consequences).

The concentrate branch (`delta > 0`):

```python
        m = g.number_of_edges()
        k = round(abs(delta) * m)  # how many edges to rewire
        if k == 0 or m == 0:
            return g

        hub = max(sorted(g.nodes()), key=lambda n: g.degree(n))
```

- Delta semantics differ from BridgeWidth, and the docstring says so: here
  delta is *the fraction of all edges rewired* (+0.1 = move ~10% of edges
  onto the hub). Each transformation defines what its delta means —
  documented under `Delta:` in every docstring.
- `max(sorted(g.nodes()), key=...)` — the hub. Sorting first makes the
  tie-break deterministic (if two nodes share the top degree, the same one
  wins every run).

```python
            candidates = []
            for u, v in sorted(g.edges()):
                if hub in (u, v):
                    continue  # already a hub tie: nothing to concentrate
                if self._sameSide(u, hub):
                    candidates.append((u, v))
                elif self._sameSide(v, hub):
                    candidates.append((v, u))
```

- Skip edges already touching the hub — repointing those wouldn't
  concentrate anything.
- The subtle part: we will replace `(u, v)` by `(hub, v)` — detaching `u`,
  keeping `v`. For the tie's intra/inter **status** to survive, the detached
  endpoint must be on the hub's side (then "u → hub" swaps one A-node for
  another A-node, and whatever the tie was to `v` — internal or crossing —
  it still is). The if/elif *orients* each candidate pair so the detachable
  endpoint comes first, and silently drops edges where neither endpoint is
  on the hub's side (those cannot be rewired without flipping status).

```python
            rng.shuffle(candidates)
            rewired = 0
            for u, v in candidates:
                if rewired >= k:
                    break
                if not g.has_edge(hub, v):
                    g.remove_edge(u, v)
                    g.add_edge(hub, v)
                    rewired += 1
```

- Shuffle (seeded) then take candidates until k succeeded.
- `if not g.has_edge(hub, v)` — if the hub already knows `v`, adding the
  edge again would silently merge with the existing one and the edge count
  would shrink by one, violating the anchor. Skip instead.

The redistribute branch (`delta < 0`) is the mirror: walk the hub's own
edges, and for each, hand the tie to the "poorest" node —
`sorted(g.nodes(), key=lambda n: (g.degree(n), n))` sorts by degree with
node-id as deterministic tie-break — that is on the hub's side (status
preservation again), isn't `v` or the hub, and isn't already tied to `v`.
`next((r for r in ... ), None)` takes the first qualifying receiver, or
`None` if nobody qualifies (then that edge is skipped).

### 10.6 `BridgeTrendTransformation` — TSAP's trend transform, in time

The first *inherently temporal* transformation. Three things to notice
before the code: `communities` is **required** (you steer one well-defined
bridge through time; auto-detecting per snapshot could pick different
partitions), `transformGraph` **raises** (a single graph has no trajectory),
and the anchor moves to the time dimension (**last snapshot untouched**).

```python
    def transformGraph(self, graph, delta):
        raise NotImplementedError(
            "BridgeTrendTransformation changes a trajectory across "
            "snapshots; it has no meaning for a single graph. Use it "
            "with TgapExplainer (temporal), not GraphExplainer.")
```

A deliberate, explanatory crash — if someone wires this into the static
explainer, they learn *why* it can't work, not just that it didn't.

Step 1 — read the trajectory:

```python
    def transform(self, temporalGraph, delta):
        widths = [len(interCommunityEdges(g, self.communities))
                  for g in temporalGraph]
```

The property's history as a plain list of numbers, e.g. `[8, 8, 8, 8, 8, 8]`.

Step 2 — TSAP's backward recursion, verbatim, on that series:

```python
        target = [float(w) for w in widths]
        i = len(target) - 2
        while i >= 0:
            origChange = widths[i] - widths[i + 1]
            target[i] = (target[i + 1] + origChange) / (1 + delta)
            i = i - 1
```

- Start at the second-to-last snapshot and walk **backwards** (`i -= 1`).
- `origChange` — the original step between snapshot i and i+1 (read from the
  untouched `widths`, not from the evolving `target`).
- Rebuild point i from the already-transformed point i+1 plus the original
  step, then divide by `(1 + delta)`. Because the division happens at
  *every* step, the effect **compounds** the further back you go — early
  history is bent the most, the present not at all.
- Put this side by side with
  [TsapExplainer.transformTrendReverse](../tsap_v2.1/tsap/TsapExplainer.py)
  — it is the same recursion, with `seriesT.iloc[i]` replaced by
  `target[i]`. This line-level correspondence is the whole "TGAP = TSAP for
  graphs" claim, made concrete.

**Worked example** (stable width 8, delta = +0.1, six snapshots):

| t | recursion | target | rounded |
|---|---|---|---|
| 5 (last) | anchor | 8 | 8 (untouched) |
| 4 | (8+0)/1.1 | 7.27 | 7 |
| 3 | (7.27+0)/1.1 | 6.61 | 7 |
| 2 | (6.61+0)/1.1 | 6.01 | 6 |
| 1 | (6.01+0)/1.1 | 5.46 | 5 |
| 0 | (5.46+0)/1.1 | 4.97 | 5 |

History becomes `[5, 5, 6, 7, 7, 8]` — the same present reached from below:
a **rising** trajectory. A trend model now extrapolates upward (demo 4
measured impact +5.33). With delta = −0.1 you divide by 0.9 and history
inflates to `[14, 12, 11, 10, 9, 8]` — **decay** (impact −13.33). The
asymmetry (+5.33 vs −13.33) is inherited from TSAP: dividing by 0.9
compounds faster than dividing by 1.1.

Step 3 — realize the targets in actual graphs:

```python
        result = []
        for t, g in enumerate(temporalGraph[:-1]):
            rng = random.Random(self.seed + t)
            result.append(setBridgeWidth(
                g, self.communities, round(target[t]), rng))
        result.append(temporalGraph[-1].copy())
        return result
```

- `temporalGraph[:-1]` — all snapshots *except the last*.
- `random.Random(self.seed + t)` — a per-snapshot seed stream: fully
  deterministic, but snapshot 0 and snapshot 3 make *independent* edge
  choices (using one shared rng would correlate them in arbitrary ways).
- Each earlier snapshot gets its width set to the rounded target by the
  shared engine from §10.3 — so within each snapshot, node set and edge
  count are still preserved.
- `temporalGraph[-1].copy()` — the anchor: the present passes through
  untouched. This single line is what demo 4's blindness check verifies.

### 10.7 `ChurnTransformation` — volatility, translated to time

The mapping: TSAP's volatility = how much a series wiggles around its
anchor. TGAP's churn = how much past snapshots' **edge sets differ from the
last snapshot's**. Delta < 0 calms history toward the present; delta > 0
agitates it away.

```python
    def transform(self, temporalGraph, delta):
        last = temporalGraph[-1]
        lastEdges = {_edgeKey(u, v) for u, v in last.edges()}
```

The present's edges as a set of normalized keys (§10.1) — the reference
everything is compared against. Computed once, outside the loop.

```python
        for t, g in enumerate(temporalGraph[:-1]):
            rng = random.Random(self.seed + t)  # deterministic per snapshot
            g = g.copy()
            gEdges = {_edgeKey(u, v) for u, v in g.edges()}
```

Per earlier snapshot: own seed stream, own copy, own edge set.

The calm branch (`delta < 0`):

```python
                onlyHere = sorted(e for e in gEdges - lastEdges
                                  if self._isIntra(*e))
                onlyLast = sorted(e for e in lastEdges - gEdges
                                  if self._isIntra(*e))
                n = min(round(-delta * len(onlyHere)),
                        len(onlyHere), len(onlyLast))
                if n > 0:
                    toRemove = rng.sample(onlyHere, n)
                    toAdd = rng.sample(onlyLast, n)
                    g.remove_edges_from(toRemove)
                    g.add_edges_from(toAdd)
```

- `gEdges - lastEdges` — set subtraction: edges this snapshot has that the
  present doesn't (**onlyHere** — the "old news"). `lastEdges - gEdges` —
  edges the present has that this snapshot lacks (**onlyLast**). Together
  they *are* the disagreement, i.e. the churn.
- `self._isIntra(*e)` — the `*` unpacks the tuple into the two arguments.
  With a partition given, only intra-community edges participate — so bridge
  width is untouched in every snapshot (the orthogonality demo 4 asserts).
- `n = min(round(-delta * len(onlyHere)), len(onlyHere), len(onlyLast))` —
  intended count is a fraction of the disagreement; the two `len` caps
  guarantee we can pair every removal with an addition.
- Remove n old-news edges, add n present-edges: the snapshot moves toward
  the present, **one-for-one, so edge count never moves** (anchor).

The agitate branch (`delta > 0`) swaps *agreeing* edges (`gEdges &
lastEdges`, set intersection, filtered by `_safeToRemove`) for **fresh**
pairs connected in *neither* graph — history diverges from the present
without inventing edges the present has. The `fresh` comprehension's
`for i, a in enumerate(nodes) for b in nodes[i + 1:]` idiom enumerates each
unordered pair exactly once.

```python
        result.append(last.copy())
        return result
```

And again, the last line is the anchor.

### 10.8 `DensityTransformation`

```python
    def transformGraph(self, graph, delta):
        g = graph.copy()
        rng = random.Random(self.seed)
        m = g.number_of_edges()
        k = round(m * (1 + delta)) - m
        if k > 0:
            candidates = sorted(nx.non_edges(g))
            g.add_edges_from(rng.sample(candidates, min(k, len(candidates))))
        elif k < 0:
            candidates = _safeToRemove(g, sorted(g.edges()))
            g.remove_edges_from(rng.sample(candidates, min(-k, len(candidates))))
        return g
```

The simplest one, and a good self-test: you should now recognize *every*
idiom — the copy, the fresh seeded rng, the relative-delta rounding, sorted
candidates, capped sampling, safe removal. One honest wrinkle in the
docstring: this transformation's edge count is deliberately NOT preserved,
because the edge count *is* the property being changed (just as TSAP's
volatility transform is allowed to change volatility).

---

## 11. `core/GraphExplainer.py`

File: [core/GraphExplainer.py](../tgap/core/GraphExplainer.py)

The engine. One base class holds everything; the two public explainers only
differ in one hook.

### `__init__` — and a circular-import note

```python
    def __init__(self, model, transformations=None, defaultDelta=0.1):
        if transformations is None:
            from .Transformations import (
                BridgeWidthTransformation,
                CentralizationTransformation,
            )
            transformations = [
                BridgeWidthTransformation(),
                CentralizationTransformation(),
            ]
        self.model = model
        self.transformations = transformations
        self.delta = defaultDelta
```

- Defaults mirror TSAP's hardcoded `[Volatility, Trend]` pair — but here the
  list is a *parameter*, so adding a new explainable property never means
  editing the explainer. (A small structural improvement over TSAP.)
- The import sits *inside* the method, unusually. The comment explains:
  importing Transformations at the top of this module, while
  `core/__init__.py` imports both modules, would risk a circular-import
  tangle. Importing lazily, only when defaults are actually needed,
  sidesteps it.
- `defaultDelta=0.1` — the 10% nudge, same default as TSAP.

### The hook

```python
    def _applyTransformation(self, x, trans, delta):
        raise NotImplementedError
```

The one thing the base class doesn't know: is `x` a single graph or a list
of snapshots? Each subclass answers in one line (§12). This is the
["template method" pattern]: the algorithm lives once in the parent; the
variable step is delegated.

### `explain` — the five model calls

```python
    def explain(self, x):
        dictExplain = dict()
        result = self.model.predict(x)  # baseline: 1 model call
        for trans in self.transformations:
            for delta in [self.delta, -self.delta]:
                direction = "Increase" if delta > 0 else "Decrease"
                key = direction + " " + trans.name + \
                    " (" + str(100 * abs(delta)) + "%)"
                xT = self._applyTransformation(x, trans, delta)
                resultTransf = self.model.predict(xT)
                dictExplain[key] = (resultTransf - result) / abs(delta)
        return dictExplain
```

Line by line:

- `result = self.model.predict(x)` — the baseline, computed **once**.
  (TSAP's `boxplotTrans` recomputes it inside a loop — a wart doc 01 §12.4
  noted; here it's done right.)
- Two nested loops: each property × each direction (+δ, −δ). Both
  directions because models are non-linear — increasing AND decreasing a
  property can both raise the output, and only testing both reveals it.
- `key` — the human-readable label, assembled from the transformation's
  `name`: `"Increase Bridge Width (10.0%)"`.
- `xT = self._applyTransformation(x, trans, delta)` — the hook: perturb.
- `(resultTransf - result) / abs(delta)` — **the entire method in one
  line**: output change per unit of property change; a numerical
  derivative. `abs()` so the sign of the impact reflects the model's
  response, not the direction of the nudge.
- Count the `predict` calls: 1 + 2×(number of transformations). Two
  transformations → 5 calls — the exact cost profile of TSAP.

### `summaryData` — the signed-log scale

Ported from TSAP (doc 01 §9.2 explains the *why*; here's the *how*):

```python
        nonZeroMagnitudes = [abs(v) for v in values if v != 0]
        if not nonZeroMagnitudes:
            return labels, values, [0.0] * len(values), "Signed log₁₀(value)"
        minLog = math.floor(np.min(np.log10(nonZeroMagnitudes)))
        summand = abs(minLog) if minLog < 0 else 0
        signedLog = [
            np.sign(v) * (np.log10(abs(v)) + summand) if v != 0 else 0
            for v in values
        ]
```

- Guard first: a model blind to every property gives all-zero impacts;
  `log10(0)` is −infinity, so we return flat zeros honestly instead of
  crashing. (This guard is *new* relative to TSAP, whose version also let
  zeros pollute `minLog` — a small robustness fix.)
- `log10` of each magnitude compresses "+8.3 next to +0.0004" into
  comparable bar lengths; `np.sign(v) * (...)` puts direction back;
  `summand` shifts everything up so the smallest bar starts at 0 — without
  it, a *small positive* impact would have a negative log and draw a bar
  pointing left, visually lying about its direction.
- The axis title honestly reports the shift:
  `'Signed (log₁₀(value)+2)'` when `summand = 2`.

### The three plot methods

All three follow TSAP's signatures with one addition — `show=True` — so
tests and scripts can run headless (`show=False` builds and *returns* the
figure without opening a browser). Highlights only:

`plotSummary` — horizontal bars, `marker_color=['red' if v > 0 else 'blue'
for v in values]` (red = pushes prediction up, blue = down; SHAP's visual
language), `labels[::-1]` reverses lists so the first property lands at the
*top* of the chart, `add_vline(x=0, ...)` draws the dashed zero line.

`plotTrans` — the sensitivity sweep:

```python
        X = np.linspace(minDelta, maxDelta, nValues)
        Y = []
        result = self.model.predict(x)  # baseline computed ONCE
        for delta in X:
            xT = self._applyTransformation(x, trans, delta)
            Y.append(self.model.predict(xT) - result)
```

`np.linspace(-0.2, 0.2, 40)` = 40 evenly spaced deltas. One perturb+predict
per delta, impact relative to the single precomputed baseline. The docstring
warns you to *expect steps*: many nearby deltas round to the same integer
edge change, hence flat plateaus — discrete structures, honest plots.

`boxplotTrans` — the global view: same sweep, but over a *list* of inputs,
collecting a distribution per delta into a pandas DataFrame column
(`df[str(round(delta * 100, 2))] = distrib`), rendered by `px.box`. Tight
boxes = the effect is systematic across ecosystems; wide boxes = it depends
on the input — itself a finding.

### The static subclass

```python
class GraphExplainer(ExplainerBase):
    def _applyTransformation(self, graph, trans, delta):
        return trans.transformGraph(graph, delta)
```

One line: for static graphs, "apply" means "transform this one snapshot".
Note the consequence: handing it a temporal-only transformation
(BridgeTrend/Churn) hits their raising `transformGraph` — the type system
politely refuses nonsense.

---

## 12. `core/TemporalGraphExplainer.py`

File: [core/TemporalGraphExplainer.py](../tgap/core/TemporalGraphExplainer.py)

```python
from .GraphExplainer import ExplainerBase


class TgapExplainer(ExplainerBase):
    def _applyTransformation(self, temporalGraph, trans, delta):
        return trans.transform(temporalGraph, delta)
```

The headline class of the whole package is four lines — and that is the
*point*, not a shortcut. All machinery lives in `ExplainerBase`; the only
temporal-specific fact is that "apply" means `trans.transform(...)` — the
whole-list method. For structural transformations that maps over every
snapshot; for temporal ones (BridgeTrend, Churn) it runs their overridden
trajectory logic. Either way `TgapExplainer` neither knows nor cares — the
polymorphism does the routing.

If you're ever unsure whether the temporal path is "real", trace one call:
`TgapExplainer.explain(tg)` → `ExplainerBase.explain` → this
`_applyTransformation` → `ChurnTransformation.transform` → per-snapshot
edge-set comparisons against the anchored last snapshot. Every link in that
chain is code you have now read.

---

## 13. `core/SyntheticData.py`

File: [core/SyntheticData.py](../tgap/core/SyntheticData.py)

Why synthetic data first? With real FOSS/DeFi data everything is uncertain
at once. Here **we choose the ground truth** — so when the explainer speaks,
we can check it. (Same philosophy as doc 01 §15's "write a trivial model"
exercise.)

### `makeTwoCommunityGraph` — one snapshot

```python
    rng = random.Random(seed)
    n = nPerCommunity
    setA = set(range(n))
    setB = set(range(n, 2 * n))

    g = nx.Graph()
    g.add_nodes_from(range(2 * n))
```

Nodes `0..n−1` are community A, `n..2n−1` are B — the partition is known *by
construction*, no detection needed.

```python
    # 1. A path backbone inside each community guarantees each blob is
    #    connected regardless of how the random edges fall.
    for i in range(n - 1):
        g.add_edge(i, i + 1)            # backbone of A: 0-1-2-...
        g.add_edge(n + i, n + i + 1)    # backbone of B: n-(n+1)-...
```

The backbone trick: purely random edges can leave a node isolated by bad
luck; a path `0−1−2−...` guarantees connectivity, and the random edges then
add realistic density on top:

```python
    # 2. Random intra-community edges with probability pIntra.
    for part in (sorted(setA), sorted(setB)):
        for i in range(len(part)):
            for j in range(i + 2, len(part)):  # +2: backbone already did i+1
                if rng.random() < pIntra:
                    g.add_edge(part[i], part[j])
```

`rng.random() < pIntra` — a seeded coin flip per candidate pair (this is the
classic G(n, p) random-graph construction). The `i + 2` start skips the
neighbor pairs the backbone already connected.

```python
    # 3. Exactly bridgeWidth inter-community edges, sampled at random.
    crossPairs = [(a, b) for a in sorted(setA) for b in sorted(setB)]
    g.add_edges_from(rng.sample(crossPairs, bridgeWidth))
```

Note: *exactly* `bridgeWidth`, not "on average" — sampled, not coin-flipped.
Known truth must be exact, or the sanity checks in demo 1 couldn't assert
exact numbers.

### `makeTemporalGraph` — the movie

```python
    rng = random.Random(seed + 1)  # separate stream from the base graph
    temporalGraph = [g]
    for _ in range(nSnapshots - 1):
        g = g.copy()
```

Each snapshot is a *copy* of the previous, then evolved — so the list holds
independent graphs, not one graph referenced many times.

Churn (ordinary turnover):

```python
        nRewire = round(churn * len(intra))
        for u, v in rng.sample(intra, nRewire):
            part = sorted(setA if u in setA else setB)
            candidates = [w for w in part
                          if w != u and not g.has_edge(u, w)]
            if candidates:
                g.remove_edge(u, v)
                g.add_edge(u, rng.choice(candidates))
```

A person (`u`) drops one collaborator (`v`) and picks a new one **inside
their own community** — so generator churn never touches the bridge (which
is why demo 1's bridge widths stay put while the insides shuffle).

Drift (the CATALYST scenario):

```python
        if bridgeDrift > 0:
            nRemove = min(bridgeDrift, len(bridges) - 1)
            if nRemove > 0:
                g.remove_edges_from(rng.sample(bridges, nRemove))
```

`bridgeDrift=1` = the bridge loses one tie per snapshot — the slow decay an
early-warning model is supposed to catch. The `len(bridges) - 1` cap keeps
the last tie (same "never sever" policy as `setBridgeWidth`). Negative
drift widens instead. Demo 2's `[8,7,6,5,4,3,2,1]` is this line at work.

---

## 14. `examples.py`

File: [examples.py](../tgap/examples.py)

```python
SHOW = "--no-show" not in sys.argv
```

`sys.argv` is the command line as a list. `python examples.py --no-show`
makes `SHOW` false → every plot call gets `show=SHOW` → figures are built
but not opened. This is how the demos double as automated tests.

### Demo 1 — `sanityCheck`: the explainer on trial

The construction: a world with **exactly 6 bridges** + the persistence model
of `BridgeWidthMetric` → the prediction *is* the bridge count of the last
snapshot. Now every explanation value is computable by hand *before running
anything*:

- Increase 10%: `round(6 × 1.1) = 7` → prediction +1 → impact `+1/0.1 = +10`.
- Decrease 10%: `round(6 × 0.9) = 5` → impact `−10`.
- Centralization (partition given → status-preserving): bridge width cannot
  change → impact exactly `0`.

```python
    assert explanation["Increase Bridge Width (10.0%)"] == +10.0, \
        "widening bridges by 10% must give impact +1/0.1 = +10"
```

Note these assert **exact equality**, not "roughly positive". We can afford
that only because every link in the chain is deterministic — which is why
the codebase is so obsessive about seeds and sorted candidate lists. If any
of the four asserts fires, the *explainer* (not the model) is broken.

### Demo 2 — `localExplanation`: the honest surprise

A decaying world (`bridgeDrift=1`) + a cohesion-*trend* model. The docstring
pre-empts the confusion you'd otherwise have: **"Increase Bridge Width"
comes out negative**, correctly. Mechanism: the transformation is
multiplicative, so wide early snapshots gain bridges while thin late ones
gain none (rounding) → measured cohesion *decays more steeply* → a
slope-reading model forecasts *lower*. The explanation faithfully exposes
that this model reasons about slopes, not levels. Sit with that example
until it clicks — it is the best illustration in the repo of what
"explaining the model, not the world" means.

### Demo 3 — `globalExplanation`

Five ecosystems from seeds 0..4, one `boxplotTrans`. One line worth pausing
on:

```python
    # All generated ecosystems share the same node numbering, so the
    # partition of the first one is valid for all (nodes 0..11 vs 12..23).
    communities = communitiesList[0]
```

This works *only* because the generator always numbers A = first half,
B = second half. With real data, each graph would need its own partition —
a thing to remember when WP2 data arrives.

### Demo 4 — `temporalProperties`: three theorems, executed

A *stable* world (constant width 8) and the two temporal transformations,
against two models that differ only in what they read:

| Claim | Why it must be true | Assert |
|---|---|---|
| **Blindness** | temporal transformations return the last snapshot untouched; the persistence model reads *only* that snapshot | all four impacts `== 0.0` |
| **Sensitivity** | BridgeTrend bends history; the trend model fits history's slope | Increase `> 0`, Decrease `< 0` |
| **Orthogonality** | churn (with partition) touches only intra edges; bridge width is identical in every snapshot | churn impacts `== 0.0` on the width model |

The measured `+5.33 / −13.33` match the §10.6 worked example. Then the coda:
churn against a *cohesion*-trend model gives non-zero impacts — proving
churn is a real transformation that this particular metric simply doesn't
see. **The explainer distinguishing "the transformation does nothing" from
"this model doesn't look at that" is the entire value proposition.**

---

## 15. The design rules, collected

Every file obeys these five. When you write new TGAP code, so should it.

1. **Model-agnostic:** the explainer touches models only through
   `predict(x) → float`. Anything wrappable is explainable.
2. **Anchor:** structural transformations preserve node set and (where
   meaningful) edge count; temporal transformations return the last
   snapshot untouched. Changes measure *structure* and *trajectory*, never
   size or a moved starting point.
3. **Determinism everywhere:** fresh `random.Random(seed)` per call,
   `sorted(...)` before every `sample(...)`, deterministic tie-breaks,
   seeded eigensolver. Same input → same explanation, always.
4. **Never mutate the input:** `g = graph.copy()` first; the baseline needs
   the original.
5. **Document the delta and the leakage:** every transformation's docstring
   says what its delta *means* and what side effects remain. Honesty over
   false purity.

---

## 16. The two bugs testing caught

Both were found by the test suite within minutes of writing the code, and
both teach a principle.

**Bug 1 — centralization leaked into bridge width.** First version of
`CentralizationTransformation`: rewiring any edge onto the hub. Sanity check
showed the supposedly-irrelevant centralization moving a pure bridge-width
model by **+60** (vs. the true signal of ±10): repointing an intra-B edge
onto a hub in A silently *created a bridge*. The fix is the
`_sameSide`/status-preserving machinery of §10.5. *Principle: leakage
between "orthogonal" properties is the default, not the exception — and only
a known-truth test makes it visible.*

**Bug 2 — the cohesion metric was unstable.** `nx.algebraic_connectivity`
uses a randomized solver; unseeded, identical inputs produced slightly
different explanations run to run, failing the stability check. Fix: the
`seed` parameter in §8. *Principle: hidden randomness lurks in library
calls, not just your own code. Test stability explicitly.*

Both fixes are *verified* by asserts that now run in every
`python examples.py` — the tests that caught the bugs became permanent
guards against their return.

---

## 17. Exercises

In rising order of difficulty. Each has a built-in way to know you succeeded.

1. **Feel the discreteness.** Run `python examples.py`, look at the
   BridgeWidth `plotTrans` staircase. Then change `nPerCommunity` from 15 to
   40 in demo 2 and re-run: with a wider bridge, more deltas round to
   distinct integers — do the steps get finer?
2. **Break the anchor, watch a test catch it.** In `setBridgeWidth`,
   comment out the "pay for them" removal block. Re-run. Which demo fails,
   and does the assert message tell you why?
3. **Recreate bug 1.** In demo 1, change
   `CentralizationTransformation(communities)` back to
   `CentralizationTransformation()`. Watch the sanity check explode. Now you
   have *seen* leakage, not just read about it.
4. **Write your own metric.** `class BusFactorMetric(Metric)` — e.g. count
   how many top-degree nodes you must delete before `nx.is_connected` fails.
   Plug it into `TrendTemporalModel`, explain it. Before running, write down
   which transformation should move it, and check yourself.
5. **Write your own transformation.** Structural: `FragmentationTransformation`
   (rewire to weaken one community's backbone). Follow the checklist from
   §15: name, delta meaning, anchor, leakage note, seeded rng, sorted
   candidates. Then write its known-truth sanity check *first*, TSAP-style.
6. **The real next step.** Port the four-property evaluation
   (faithfulness / sparsity / stability / efficiency, doc 01 §10) from
   `GummadiEvaluation.py` + `PerturbationFaithfulness.py` to TGAP. The
   structures line up one-to-one; this is the piece a paper would need.

---

*You now know every line of TGAP. When the real WP2 data or a first GNN
arrives, nothing in this package needs to change — only a new `Metric`, a
new dataset loader, or a new `TemporalGraphModel` wrapper gets added. That
is what the architecture was for.*
