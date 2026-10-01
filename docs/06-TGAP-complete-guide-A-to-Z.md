# TGAP From A to Z — Every File, Every Function, In Simple Words

> **What this is:** the complete tour of the project. Where the program
> starts, what happens next, and what every single file and function does.
> **Style:** very simple language. Science explained in boxes marked 🔬
> whenever a new idea appears (machine learning, graphs, statistics).
> **Goal:** after reading this you can open any file and know why it exists
> and what each function inside it does — and explain it to your professor.
>
> Sister documents: [01](01-TSAP-explained-simply.md) (the TSAP idea),
> [03](03-TGAP-technical-audit.md) (design decisions),
> [05](05-TGAP-worked-example-trace.md) (one tiny example traced).
> This document replaces [04](04-TGAP-v02-walkthrough.md) as the current
> full reference — the code has grown since then.

---

## Table of contents

**Part I — The big picture**
1. [What the program does, in one page](#1-what-the-program-does-in-one-page)
2. [The science you need first](#2-the-science-you-need-first)
3. [Map of every file](#3-map-of-every-file)
4. [Where the program starts](#4-where-the-program-starts)
5. [The flow, A to Z](#5-the-flow-a-to-z)

**Part II — The engine room (`core/`)**
6. [`GraphModel.py` — the contract](#6-coregraphmodelpy)
7. [`TemporalGraphModel.py` — the models](#7-coretemporalgraphmodelpy)
8. [`GraphMetric.py` — the measurements](#8-coregraphmetricpy)
9. [`Communities.py` — who is on which side](#9-corecommunitiespy)
10. [`TemporalGraphTransformation.py` — the rulebook](#10-coretemporalgraphtransformationpy)
11. [`Transformations.py` — the five concepts](#11-coretransformationspy)
12. [`GraphExplainer.py` — the brain](#12-coregraphexplainerpy)
13. [`TemporalGraphExplainer.py` — four lines](#13-coretemporalgraphexplainerpy)
14. [`SyntheticData.py` — the world builder](#14-coresyntheticdatapy)
15. [`Diagnostics.py` — the measuring tools](#15-corediagnosticspy)
16. [`__init__.py` — the front door](#16-coreinitpy)

**Part III — The programs you run**
17. [`examples.py` — the demos](#17-examplespy)
18. [`evaluation.py` — the quick check](#18-evaluationpy)
19. [`paper_evaluation.py` — the experiments](#19-paper_evaluationpy)
20. [`tests/` — the safety net](#20-tests)

**Part IV — For your presentation**
21. [Explaining it in 5 minutes](#21-explaining-it-in-5-minutes)
22. [Questions your professor may ask](#22-questions-your-professor-may-ask)
23. [Glossary](#23-glossary)

---

# PART I — THE BIG PICTURE

## 1. What the program does, in one page

Imagine a computer program (a "model") that looks at a network of people
or organizations and says: **"this community is at risk."**

The obvious question is **why?** The model gives a number, not a reason.

TGAP answers that question with a simple experiment, repeated a few times:

```
   STEP 1:  Show the network to the model.     → it says 5.0   ("baseline")

   STEP 2:  Change ONE thing a human understands.
            For example: "make the bridge between the two groups wider."

   STEP 3:  Show the changed network to the model.  → it says 6.0

   STEP 4:  The model moved by +1.0.
            Divide by how much we actually changed the bridge.
            → THAT NUMBER IS THE EXPLANATION.
```

Do this for several ideas — wider bridge, narrower bridge, more
centralized, less centralized — and you get a small table a human can read:

```
   Increase Bridge Width   →  +8.0     (this matters a lot)
   Decrease Bridge Width   →  -8.0
   Increase Centralization →   0.0     (this does not matter at all)
   Decrease Centralization →   0.0
```

**TGAP = Temporal Graph Additive exPlanations.** "Temporal graph" = a
network that changes over time. The name copies **TSAP**, the earlier
project that did the same trick for simple number sequences.

> ⚠️ **Say this carefully.** TGAP measures how sensitive **the model** is
> to a change we made on purpose. It does **not** prove anything about the
> real world. Correct words: *"model sensitivity"*, *"counterfactual
> response"*. Wrong words: *"this causes that"*, *"TGAP proves causality"*.

---

## 2. The science you need first

Nine short boxes. Each one appears again later, where it is used.

> ### 🔬 Science box 1 — What is a "model" in machine learning?
> A **model** is a program that takes an input and produces an output.
> In **machine learning (ML)**, the program is not written by hand: it is
> **trained**. You show it thousands of examples ("here is a network, here
> is what happened next"), and it adjusts millions of internal numbers
> ("weights") until its guesses get good.
>
> The problem: after training, nobody — not even the person who built it —
> can read those millions of numbers and say *why* it answered what it
> answered. This is called the **black box problem**.

> ### 🔬 Science box 2 — What is XAI?
> **XAI = eXplainable Artificial Intelligence.** The research field that
> asks: *the model answered — why?* It matters for four reasons:
> **trust** (nobody acts on "the computer said so"), **debugging** (maybe
> the model is right by accident), **law** (the EU AI Act and GDPR push
> toward explanations for automated decisions), and **science** (an
> explanation is a hypothesis about how the world works).

> ### 🔬 Science box 3 — What is a graph?
> A **graph** is dots and lines. The dots are called **nodes** (people,
> projects, companies). The lines are called **edges** (relationships:
> "works with", "depends on", "funds").
> A **temporal graph** is a graph that changes over time. We store it as a
> **list of snapshots**: the graph in January, in February, in March…

> ### 🔬 Science box 4 — What is a "bridge", and why does this project care?
> If two groups of people are connected by **one single link**, that link
> is fragile — one person quits and the groups are cut off. If they are
> connected by **many links**, the connection survives.
>
> The CATALYST research project calls this a **wide bridge**. Its central
> claim comes from sociology: simple information (like a job ad) spreads
> fine through one weak link, but **costly or risky behaviour** — adopting
> a technology, forming an alliance — needs **several independent contacts
> doing it too**. That is called **complex contagion**. So the *width* of
> a bridge is the number we care about most.

> ### 🔬 Science box 5 — Perturbation-based explanation
> There are two big families in XAI. **Gradient methods** open the model
> and look at its internal maths — they only work if you have the model's
> source and it is differentiable. **Perturbation methods** stay outside:
> poke the input, watch the output. TGAP is a perturbation method. That is
> why it works on *any* model.

> ### 🔬 Science box 6 — Derivative, in plain words
> A **derivative** measures "how fast does the output change when I change
> the input". If pressing the accelerator 1 cm makes the car go 5 km/h
> faster, the derivative is 5 km/h per cm.
>
> We cannot compute a true derivative here (the model is a black box), so
> we compute an approximation, called a **finite difference**:
> ```
>              output(after) − output(before)
>  slope  ≈   ─────────────────────────────────
>                   size of the change
> ```
> That formula **is** TGAP. Everything else is careful bookkeeping.

> ### 🔬 Science box 7 — Why the same "10%" is not always 10%
> A number can change by exactly 10%: 100 → 110. A **graph cannot**. A
> bridge has a whole number of edges. Asking for +10% on 5 edges means
> 5.5 edges — impossible. We round to 6, which is really **+20%**.
>
> So we must always ask two questions: *what did we request?* and *what did
> we actually achieve?* Dividing by the achieved change is what makes the
> answer correct. This one idea drives a lot of the code.

> ### 🔬 Science box 8 — Random seeds and reproducibility
> Computers make "random" choices using a formula that starts from a
> number called a **seed**. Same seed → same "random" choices → same
> result, forever. In science this is essential: your professor must be
> able to run your code next month and get the exact same numbers. Every
> random choice in this project is seeded.

> ### 🔬 Science box 9 — How do you know an explanation is *good*?
> You cannot compare it against "the truth", because nobody knows the true
> explanation of a black box. So the field uses proxy properties:
> **faithfulness** (does the explanation match what the model really
> does?), **stability** (same input → same explanation?), **sparsity**
> (short enough for a human to read?), **efficiency** (fast?).
> Our trick to go further: we build models whose true behaviour **we
> choose**, so we can check TGAP against an answer known in advance.

---

## 3. Map of every file

```
tgap/
│
├── core/                        ← THE LIBRARY (the reusable parts)
│   ├── __init__.py                  front door: what users can import
│   │
│   │   ── the contracts (what every model/metric must provide) ──
│   ├── GraphModel.py                a model that reads ONE graph
│   ├── TemporalGraphModel.py        a model that reads MANY snapshots
│   ├── GraphMetric.py               measurements: 6 ways to score a graph
│   │
│   │   ── the perturbations ──
│   ├── TemporalGraphTransformation.py   the rulebook all changes obey
│   ├── Transformations.py               the 5 concepts we can change
│   ├── Communities.py                   who belongs to which group
│   │
│   │   ── the engine ──
│   ├── GraphExplainer.py            the experiment loop + plots
│   ├── TemporalGraphExplainer.py    the temporal version (4 lines!)
│   │
│   │   ── the helpers ──
│   ├── SyntheticData.py             builds test worlds from a seed
│   └── Diagnostics.py               counts model calls, measures leakage
│
├── examples.py                  ← RUN THIS FIRST: 4 demos
├── evaluation.py                ← quick check: 5 experiments
├── paper_evaluation.py          ← the big one: 9 experiments (RQ1–RQ8)
│
├── tests/                       ← 91 automatic checks
│   ├── test_transformations.py      do the perturbations behave?
│   ├── test_metrics.py              do the measurements behave?
│   ├── test_explainer.py            does the engine behave?
│   └── test_paper_evaluation.py     does the evaluation behave?
│
├── output/                      ← results (created by running the code)
│   └── paper/                       results of paper_evaluation.py
├── requirements.txt             ← libraries needed
└── README.md
```

**Sizes** (so you know what is big and what is small):

| File | Lines | Weight |
|---|---|---|
| `paper_evaluation.py` | 1507 | the experiments — biggest |
| `Transformations.py` | 596 | the heart of the method |
| `GraphExplainer.py` | 387 | the engine |
| `examples.py` | 313 | demos |
| `evaluation.py` | 297 | quick check |
| `SyntheticData.py` | 222 | world builder |
| `TemporalGraphModel.py` | 144 | 5 models |
| `GraphMetric.py` | 129 | 6 measurements |
| `TemporalGraphTransformation.py` | 92 | rulebook |
| `Diagnostics.py` | 86 | tools |
| `__init__.py` | 77 | exports |
| `Communities.py` | 65 | helpers |
| `GraphModel.py` | 40 | contract |
| `TemporalGraphExplainer.py` | 38 | 4 real lines |

Notice: the **contracts are the smallest files**. That is a sign of good
design — simple agreements, complex behaviour built on top.

---

## 4. Where the program starts

There is no single "main". There are **three doors**, and you choose one:

```
  DOOR 1:  python examples.py           ← start here to LEARN
  DOOR 2:  python evaluation.py         ← quick numbers
  DOOR 3:  python paper_evaluation.py   ← full experiments for the paper
  (plus)   python -m unittest discover -s tests   ← run the 91 checks
```

All three doors behave the same way at the bottom:

```
      you run a .py file
              │
              ▼
      Python reads the file top to bottom
              │
              ├── executes the import lines  →  loads core/__init__.py
              │                                  which loads all of core/
              │
              └── reaches the last block:
                      if __name__ == "__main__":
                          ...call the functions...
```

> ### 🔬 Science box 10 — What does `if __name__ == "__main__":` mean?
> Every Python file can be used two ways: **run directly** (`python
> examples.py`) or **imported** by another file. This line means: *"only do
> this when I am run directly, not when someone imports me."* It stops
> demos from firing every time another file borrows a function.

---

## 5. The flow, A to Z

Let us follow `python examples.py` from the very first instruction to the
final printed number. **This is the section to show your professor first.**

### A. Python loads the imports

`examples.py` line 21 says `from core import (...)`. Python opens
`core/__init__.py`, which imports every other file in `core/`. Order
matters — a file cannot use something that is not loaded yet:

```
   1. GraphMetric.py       (needs: Communities)
   2. GraphModel.py        (needs: nothing)
   3. TemporalGraphModel.py(needs: numpy)
   4. TemporalGraphTransformation.py  (needs: nothing)
   5. Transformations.py   (needs: the rulebook, Communities, GraphMetric)
   6. GraphExplainer.py    (needs: numpy/pandas/plotly)
   7. TemporalGraphExplainer.py (needs: GraphExplainer)
   8. Communities.py       (needs: networkx)
   9. SyntheticData.py     (needs: networkx, Transformations)
  10. Diagnostics.py       (needs: numpy)
```

Nothing has *run* yet. Python has only learned the definitions.

### B. The demo function starts

```python
if __name__ == "__main__":
    sanityCheck()          ← we follow this one
```

### C. Build a world

```python
temporalGraph, communities = makeTemporalGraph(
    nSnapshots=6, nPerCommunity=15, bridgeWidth=6, churn=0.05, seed=42)
```

Goes to `core/SyntheticData.py` → `makeTemporalGraph` → which calls
`makeTwoCommunityGraph` to build snapshot 0, then copies and modifies it
5 times. You get a **list of 6 graphs**, and the partition
`({0..14}, {15..29})`.

### D. Build a model

```python
model = PersistenceTemporalModel(BridgeWidthMetric(communities))
```

Two objects from `core/`: a **metric** (counts bridge edges) wrapped
inside a **model** (reads only the last snapshot). Its whole behaviour is
*"predict = how many bridge edges exist right now"* — so we already know
the correct explanation before running anything.

### E. Build the explainer

```python
explainer = TgapExplainer(model, transformations=[
    BridgeWidthTransformation(communities),
    CentralizationTransformation(communities)])
```

### F. Run the experiment — the important step

```python
explanation = explainer.explain(temporalGraph)
```

Here is exactly what happens inside, in order:

```
 1. explain()                    GraphExplainer.py   → calls explainDetailed()
 2. _resolveTransformations()    GraphExplainer.py   → "which concepts?"
 3. model.predict(original)      TemporalGraphModel  → BASELINE = 6.0   [call 1]
       └─ metric.measure()       GraphMetric.py
            └─ interCommunityEdges()  Communities.py → counts 6 edges

 4. trans.propertyValue(original) Transformations.py → bridge is 6.0 wide
       (no model call — just counting edges)

 5. trans.transform(tg, +0.1)     rulebook → for each of the 6 snapshots:
       └─ transformGraph()        Transformations.py
            └─ setBridgeWidth()   adds 1 bridge edge, removes 1 inside edge
 6. model.predict(changed)        → 7.0                             [call 2]
 7. trans.propertyValue(changed)  → 7.0, so achieved = (7−6)/6 = 0.1667
 8. impact = (7.0 − 6.0) / 0.1667 = +6.0        ← THE ANSWER

 9-12. repeat steps 5–8 with −0.1                                   [call 3]
13-20. repeat everything for Centralization                    [calls 4, 5]
```

**Total: 5 model calls.** That is the formula `1 + 2×K` where K = number
of concepts (here 2). Cheap.

### G. Print and check

```python
assert explanation["Increase Bridge Width (10.0%)"] == +6.0
```

The demo does not just print — it **checks**. We knew the answer had to be
6.0 (see §5F step 8), and the program confirms it. If TGAP were lying, the
program would crash here.

### The same flow as a picture

```
   examples.py
        │  (1) build world
        ▼
   SyntheticData.py ──► a list of 6 graphs
        │  (2) build model
        ▼
   TemporalGraphModel.py ──► predict(snapshots) → one number
        │  (3) build explainer
        ▼
   TemporalGraphExplainer.py ──► inherits everything from
   GraphExplainer.py
        │  (4) run
        ▼
   ┌──────────────── explainDetailed() ────────────────┐
   │  baseline = model.predict(original)               │
   │  for each concept:                                │
   │     before = concept.propertyValue(original)      │
   │     for delta in (+0.1, −0.1):                    │
   │        changed = concept.transform(original, δ)   │──► Transformations.py
   │        after   = model.predict(changed)           │──► the model
   │        achieved= concept.propertyValue(changed)   │
   │        impact  = (after − baseline) / |achieved|  │
   └───────────────────────────────────────────────────┘
        │  (5) results
        ▼
   a dictionary: {"Increase Bridge Width (10.0%)": +6.0, ...}
```

---

# PART II — THE ENGINE ROOM (`core/`)

Now every file, in the order that makes them easiest to understand: the
simplest first, each one building on the last.

---

## 6. `core/GraphModel.py`

**40 lines. The smallest and most important idea in the project.**

### `class GraphModel`

```python
class GraphModel:
    def predict(self, graph):
        raise NotImplementedError("'predict' method should be implemented")
```

That is the whole class. It is a **contract**, also called an
**interface**: a promise about what a model must provide. It says:

> *"If your thing can take a graph and return one number, TGAP can
> explain it."*

Nothing else is required. Not the source code. Not the weights. Not the
training data. Just one button called `predict`.

> ### 🔬 Science box 11 — Model-agnostic
> An explanation method is **model-agnostic** if it works on *any* model
> without knowing what is inside. This is TGAP's biggest selling point.
> Today the model is a 3-line rule. Tomorrow it can be a deep neural
> network. **The explainer does not change by a single line.**
>
> Compare with **GNNExplainer**, a popular method for graph neural
> networks: it needs access to the model's internal gradients. It cannot
> explain a model you only have as a web service. TGAP can.

`raise NotImplementedError(...)` means: if someone forgets to write their
own `predict`, the program stops with a clear message instead of silently
returning nonsense.

### `class MetricGraphModel(GraphModel)`

```python
def __init__(self, metric):
    self.metric = metric

def predict(self, graph):
    return self.metric.measure(graph)
```

A "fake model" that just reports a measurement. Two uses:
1. You can explain a **measurement** instead of a model ("which structural
   change moves cohesion the most?").
2. It is a **known-truth model** — we know exactly how it behaves, so we
   can catch TGAP lying.

> ### 🔬 Science box 12 — Inheritance, in one sentence
> `class MetricGraphModel(GraphModel)` means *"a MetricGraphModel **is a**
> GraphModel"* — it inherits the parent's promises and can replace
> (**override**) any of them. This is how one explainer works with five
> completely different models.

---

## 7. `core/TemporalGraphModel.py`

**144 lines. Five models, from very dumb to slightly clever.**

All five obey one contract: `predict(list_of_snapshots) → one number`.

### `class TemporalGraphModel` — the contract

Same shape as `GraphModel`, but the input is a **list of graphs** (oldest
first). This is the class a real Temporal Graph Network would subclass.

### `class PersistenceTemporalModel` — "tomorrow = today"

```python
def predict(self, temporalGraph):
    return self.metric.measure(temporalGraph[-1])
```

`temporalGraph[-1]` is Python for **"the last item"** — the newest
snapshot. So this model ignores all history and reports the present.

Why ship something so simple? Because its **blindness is useful**: any
change we make to *history only* must produce an impact of exactly 0 on
this model. That is a test TGAP must pass.

### `class TrendTemporalModel` — "continue the trend"

```python
y = [self.metric.measure(g) for g in temporalGraph]   # e.g. [8,7,6,5,4,3]
if len(y) < 2:
    return float(y[-1])
t = np.arange(len(y))                                  # [0,1,2,3,4,5]
slope, intercept = np.polyfit(t, y, 1)                 # fit a line
return float(intercept + slope * len(y))               # value at t = 6
```

Step by step:
1. Measure the metric on every snapshot → a plain list of numbers.
   **This line is the bridge between graphs and classic statistics.**
2. Safety: you cannot draw a line through one point.
3. `np.polyfit(t, y, 1)` fits a straight line through the points.
4. Evaluate that line one step into the future.

> ### 🔬 Science box 13 — Linear regression (least squares)
> Given points, **linear regression** finds the straight line
> `y = slope·t + intercept` that passes as close as possible to all of
> them. "As close as possible" means: the sum of squared vertical
> distances is the smallest possible. It is the oldest and most used tool
> in statistics (Gauss, ~1800), and `np.polyfit(..., 1)` is one call.
>
> The **slope** tells you the direction: negative slope = declining. For
> us, a declining bridge-width slope is exactly the "bridge decay" signal
> the CATALYST project wants to detect early.

### `class WeightedMetricModel` — known coefficients

```python
WeightedMetricModel([(2.0, BridgeWidthMetric(comm)),
                     (3.0, DegreeCentralizationMetric())], mode="mean")
```

This **is** the formula `prediction = 2·bridgeWidth + 3·centralization`,
written as code. `mode="last"` reads only the newest snapshot;
`mode="mean"` averages over all snapshots.

Why it matters: because we chose the numbers 2 and 3, we can **calculate
on paper** what TGAP should report, then check. (The answer is
`weight × current value` — see §19.)

### `class SlopeModel` — reads only the trajectory

```python
y = [self.metric.measure(g) for g in temporalGraph]
if len(y) < 2:
    return 0.0
slope, _ = np.polyfit(np.arange(len(y)), y, 1)
return float(slope)
```

The prediction **is** the slope. This is the mirror image of the
persistence model: one reads only the present, the other only the trend.
Together they let us prove TGAP can tell those two kinds of model apart.

---

## 8. `core/GraphMetric.py`

**129 lines. Six ways to turn a graph into one number.**

### `class Metric` — the contract
`measure(graph) → float`. Third contract, same pattern.

### `class DensityMetric`
```python
return nx.density(graph)
```
**Density** = (edges that exist) ÷ (edges that could exist). Between 0
(nothing connected) and 1 (everyone connected to everyone).

### `class DegreeCentralizationMetric`
```python
n = graph.number_of_nodes()
if n < 3: return 0.0
degrees = [d for _, d in graph.degree()]
maxDegree = max(degrees)
return sum(maxDegree - d for d in degrees) / ((n - 1) * (n - 2))
```

> ### 🔬 Science box 14 — Degree and Freeman centralization
> A node's **degree** is how many edges touch it — how many friends you
> have. **Centralization** asks: *is the network a star (one hub holds
> everything) or a circle (everyone equal)?*
>
> **Freeman's formula** (1979): add up how far every node falls short of
> the best-connected node, then divide by the biggest that total could be
> (which is `(n−1)(n−2)`, reached by a perfect star).
> - a **star** scores **1.0** — maximum concentration
> - a **ring** scores **0.0** — perfect equality
>
> For CATALYST this measures risk: high centralization means one person
> holds everything together — the "coordinator burnout" danger.
>
> **A useful piece of algebra** (used later in the code): because
> `Σ(degrees) = 2·edges` always, the formula simplifies to
> `C = (n·d_max − 2m) / ((n−1)(n−2))`. So if you keep the number of edges
> fixed, **centralization changes only when the maximum degree changes.**
> This fact revealed a real bug — see §22.

### `class BridgeWidthMetric`
```python
return float(len(interCommunityEdges(graph, communities)))
```
Counts the edges crossing between the two groups. **The project's most
important number.** It takes the partition in `__init__` (or detects one
if you do not give it).

### `class ClusteringMetric`
```python
return float(nx.average_clustering(graph))
```
**Clustering** = "do my friends know each other?" — the chance that two of
your contacts are also connected to each other. In TGAP this is a **probe**:
no transformation tries to change it, so any movement is pure side effect.

### `class CohesionMetric`
```python
if graph.number_of_nodes() < 2 or not nx.is_connected(graph):
    return 0.0
return float(nx.algebraic_connectivity(graph, seed=self.seed))
```

> ### 🔬 Science box 15 — Algebraic connectivity (the Fiedler value)
> This comes from **spectral graph theory**, which studies graphs using
> matrices. Write the graph as a matrix, compute its **eigenvalues**
> (special numbers describing the matrix), and take the second-smallest.
> That number, named after Miroslav Fiedler (1973), answers:
> **"how hard is it to cut this graph in two?"**
> - 0 = already in pieces
> - small = there is a thin bottleneck somewhere (fragile!)
> - large = tightly knit
>
> It is perfect for CATALYST because a graph held together by **one narrow
> bridge** scores near zero *even if both sides are internally dense* — it
> sees exactly the fragility we care about.

The two guard clauses matter. `not nx.is_connected(graph)` → return 0,
because networkx would otherwise throw an error. And `seed=self.seed`
because networkx computes this with a **random** algorithm — without a
seed, the same graph gave slightly different answers on different runs,
which broke reproducibility. One parameter fixed it.

---

## 9. `core/Communities.py`

**65 lines, 3 functions.** Everything about "which group is a node in?"

### `detectTwoCommunities(graph)`
```python
communities = community.greedy_modularity_communities(graph)
setA = set(communities[0])
setB = set(graph.nodes()) - setA
return setA, setB
```
Finds groups automatically, then forces exactly two: the biggest group vs
everyone else. `set(...) - setA` is **set subtraction**: "everything not
in A".

> ### 🔬 Science box 16 — Community detection and modularity
> A **community** is a group of nodes with many links inside and few links
> outside. **Modularity** is a score (Newman & Girvan, 2004) that measures
> how much better a grouping is than random chance. The *greedy* algorithm
> starts with everyone alone and repeatedly merges whichever pair improves
> modularity most. It is deterministic: same graph → same groups.
>
> ⚠️ But: if you change the graph slightly, the algorithm may choose
> **different** groups — and then you would measure "the detector changed
> its mind", not "the model reacted". That is why real experiments always
> pass the partition explicitly.

### `interCommunityEdges(graph, communities)`
```python
bridges = [(u, v) for (u, v) in graph.edges()
           if (u in setA and v in setB) or (u in setB and v in setA)]
return sorted(bridges)
```
Goes through all edges, keeps the ones with one end in each group. **These
edges ARE the bridge**, and `len(...)` of this list is its width.

The `sorted(...)` is not cosmetic — it is required for reproducibility.
Random sampling from a list only repeats if the list is always in the same
order. You will see `sorted()` before every random pick in this project.

### `intraCommunityEdges(graph, communities)`
The mirror image: edges with **both** ends inside the same group. Needed
when a transformation must "pay" for a new bridge by removing an internal
edge.

---

## 10. `core/TemporalGraphTransformation.py`

**92 lines. The rulebook that every perturbation must obey.**

### `class TemporalGraphTransformation`

```python
name = "Property"          # human label, e.g. "Bridge Width"
deltaMode = "relative"     # units of the achieved change
```

Two class attributes shared by all transformations:
- `name` → appears in the explanation labels and on plots.
- `deltaMode` → `"relative"` (a ratio, like +20%) or `"absolute"` (the
  property's own units). Needed because a **slope can legitimately be
  zero**, and you cannot compute "a percentage of zero".

### `propertyValue(self, x)` — returns `None` by default
Measures the concept this transformation changes. Returns `None` when it
is not measurable. **This is the function that fixes the "10% is not 10%"
problem** from Science box 7: measure before, measure after, and you know
what you really achieved.

### `transformGraph(self, graph, delta)`
Change one snapshot. Must return a **new** graph, never modify the input.

### `transform(self, temporalGraph, delta)`
```python
return [self.transformGraph(g, delta) for g in temporalGraph]
```
Apply the change to **every** snapshot. Why all of them? Because the
question is a *counterfactual*: *"if the whole recent history had had 10%
wider bridges, what would you predict?"*

### 🔑 The Anchor Rule — the most important design idea

> When you change something, **hold everything else still**, so the
> model's reaction can only come from the thing you changed.

| | TSAP (numbers) | TGAP (graphs) |
|---|---|---|
| **Anchor** | keep the last value fixed | keep the node set **and edge count** fixed |
| **Why** | so the prediction changes because of the *shape*, not a different starting point | so it changes because of the *structure*, not because the graph got bigger |
| **In time** | — | temporal changes leave the **last snapshot untouched** |

Concretely: to add one bridge edge, we **delete one internal edge**. The
network has the same amount of activity — only **routed differently**.

> ### 🔬 Science box 17 — Why the anchor rule is real science
> This is the same logic as a **controlled experiment**. To test a
> medicine you give one group the drug and another a placebo, keeping
> everything else identical. If you also changed their diet, you would not
> know which caused the result — that is a **confound**.
>
> Edge count is our confound. Holding it fixed is our control.

### Two families of transformation

| | **Structural** | **Temporal** |
|---|---|---|
| Change | the shape of each snapshot | how the graph *evolves* |
| Members | BridgeWidth, Centralization, Density | BridgeTrend, Churn |
| Implement | `transformGraph` | override `transform` |
| Anchor | node set + edge count | **last snapshot untouched** |

Temporal ones make `transformGraph` **raise an error** on purpose:
"change the trend of a single snapshot" is meaningless.

---

## 11. `core/Transformations.py`

**596 lines. The heart of the method: the five concepts.**

### Four helper functions first

**`_edgeKey(u, v)`** — an edge `(3,7)` and `(7,3)` are the same thing in an
undirected graph. This always returns the smaller number first, so edges
from different graphs can be compared.

**`_snapshots(x)`** — accepts one graph *or* a list, always returns a list.
Saves writing everything twice.

**`_safeToRemove(graph, edges)`** — before deleting an edge, check it will
not split the graph in two.

> ### 🔬 Science box 18 — A confusing name collision
> In **graph theory**, a "bridge" (`nx.bridges`) means a **cut-edge**: an
> edge whose removal disconnects the graph.
> In **CATALYST**, a "bridge" means the bundle of social ties between two
> communities.
> **Same word, different meanings.** The code comments flag this wherever
> both appear. Worth mentioning to your professor — it shows you noticed.

**`setBridgeWidth(graph, communities, targetWidth, rng)`** — the workhorse.
"Make the bridge exactly this wide, keeping the edge count fixed."

```python
g = graph.copy()                       # never touch the original
targetWidth = max(1, targetWidth)      # never remove the LAST bridge
k = targetWidth - width                # how many edges to move

if k > 0:                              # WIDEN
    candidates = sorted(cross pairs not yet connected)
    toAdd = rng.sample(candidates, k)  # pick k of them (seeded)
    g.add_edges_from(toAdd)
    intra = _safeToRemove(g, intraCommunityEdges(...))
    g.remove_edges_from(rng.sample(intra, len(toAdd)))   # PAY for them
elif k < 0:                            # NARROW: the mirror image
```

Three details worth explaining:
- `max(1, targetWidth)` — never cut the last tie. Total disconnection is a
  *different, much more brutal* question than "a thinner bridge".
- `rng.sample(...)` — a seeded random pick, so it repeats exactly.
- the "pay for them" block — the anchor rule in action.

---

### The five concepts

#### 1. `BridgeWidthTransformation` — how wide is the bridge?

```python
width  = len(interCommunityEdges(graph, communities))   # e.g. 8
target = round(width * (1 + delta))                     # round(8.8) = 9
return setBridgeWidth(graph, communities, target, rng)
```

- **Changes:** the number of edges between the two groups.
- **Delta means:** a relative change. +0.1 → 10% more bridges (rounded).
- **Keeps fixed:** node set, total edge count, the partition.
- `propertyValue` = the **average** bridge width over all snapshots.

#### 2. `CentralizationTransformation` — how star-shaped is it?

- **Changes:** how much the connections pile onto the biggest hub.
- **Delta means:** ⚠️ **NOT a relative change of centralization.** It is the
  **fraction of edges to rewire**. This difference matters a lot later.
- **Keeps fixed:** node set, edge count, **and bridge width exactly** (when
  you pass the partition).

The bridge-preservation trick is in `_sameSide`:
```python
return (a in setA) == (b in setA)
```
Clever line: `True` when both are in A **or** both are outside A. When
rewiring, the moved endpoint must stay on the same side, so an internal
tie stays internal and a crossing tie stays crossing → bridge width
cannot change.

The "make less central" branch contains a lesson (§22, bug 3): it must
re-find the **currently** most-connected node at every step, because of the
algebra in Science box 14 — centralization only moves when the *maximum
degree* moves.

#### 3. `DensityTransformation` — how many edges in total?

- **Changes:** the total number of edges.
- **Keeps fixed:** node set only. (Edge count **is** the property here, so
  it is allowed to change.)
- With `communities`: only internal edges are touched → bridge preserved.
- **Without** `communities`: ⚠️ leaks badly. Measured: **+6.17 bridge edges**
  at delta 0.1, because most unconnected pairs happen to be cross pairs.
  We kept this visible rather than hiding it.

#### 4. `BridgeTrendTransformation` — is the bridge growing or dying?

**The most important temporal concept, and a direct copy of TSAP's maths.**

```python
target = [float(w) for w in widths]
i = len(target) - 2
while i >= 0:
    origChange = widths[i] - widths[i + 1]
    target[i] = (target[i + 1] + origChange) / (1 + delta)
    i = i - 1
```

Read it as: *start at the last snapshot (untouched), walk **backwards**,
and each step divide by (1 + delta).* Because you divide at every step,
the effect **compounds** — early history bends most, the present not at all.

**Worked example** — widths `[5, 4, 3]`, delta = +0.1:

| snapshot | calculation | result | rounded |
|---|---|---|---|
| 2 (last) | untouched — the anchor | 3 | **3** |
| 1 | (3 + 1) ÷ 1.1 = 3.636 | 3.636 | **4** |
| 0 | (3.636 + 1) ÷ 1.1 = 4.215 | 4.215 | **4** |

New history `[4, 4, 3]` — the decline became gentler. With delta = −0.1
you divide by 0.9 and get `[6, 4, 3]` — a steeper decline. Both keep the
present identical.

`deltaMode = "absolute"` here, because the property is a **slope** which is
legitimately 0 on a stable bridge, and you cannot take a percentage of 0.

#### 5. `ChurnTransformation` — how much does the past differ from now?

The temporal twin of "volatility". Measures how much earlier snapshots
**disagree** with the present.

```python
union = gEdges | lastEdges
distances.append(len(gEdges ^ lastEdges) / len(union))
```

> ### 🔬 Science box 19 — Jaccard distance
> A way to measure how different two sets are.
> `^` is the **symmetric difference** (things in exactly one of the two
> sets); `|` is the **union** (everything in either). Their ratio:
> - **0** = the two sets are identical
> - **1** = they share nothing
>
> Invented by botanist Paul Jaccard (1901) to compare plant species
> between regions. Here it compares "who worked with whom in March" to
> "who works with whom now".

- delta < 0 → **calm** the history (make the past more like the present).
- delta > 0 → **agitate** it (make the past less like the present).
- Every change is a swap (remove one, add one), so edge counts never move.
- Only internal edges are touched, so bridge width is preserved exactly.
- The last snapshot is returned untouched.

---

## 12. `core/GraphExplainer.py`

**387 lines. The engine that runs the experiment.**

### `_panelValue(metric, x)`
Small helper: evaluate a metric on one graph, or on a list (returns the
average).

### `class ExplainerBase` — all the machinery

#### `__init__(self, model, transformations=None, defaultDelta=0.1, normalization="achieved")`
Stores four things. The interesting one is `normalization`:
- `"achieved"` (default) → divide by the change we **really made**
- `"requested"` → divide by the delta we **asked for** (TSAP's original)

See §19 RQ8 for the measured difference between them.

#### `_applyTransformation(self, x, trans, delta)`
Raises `NotImplementedError` — the one thing the base class cannot know:
is `x` one graph or a list? Each child answers in a single line.

> ### 🔬 Science box 20 — The Template Method pattern
> A classic software design pattern: the parent class writes the whole
> recipe once and leaves **one blank** for children to fill in. Here the
> recipe is "baseline → perturb → predict → divide", and the blank is
> "how do I apply a perturbation to this kind of input".
> Result: `TgapExplainer` is **4 lines long** and inherits everything.

#### `_resolveTransformations(self, x)`
If you did not pass any concepts, it builds safe defaults *at the moment
you call explain* — detecting **one** partition from your data and sharing
it between both default transformations. This matters: an earlier version
built partition-less defaults, which leaked badly (§22, bug 2).

#### `explain(self, x)`
```python
return {r["label"]: r["impact"] for r in self.explainDetailed(x)}
```
Just a friendly view of the detailed version: keeps the name and the
number, drops the rest.

#### `explainDetailed(self, x, leakageMetrics=None)` — **the core of TGAP**

```python
baseline = self.model.predict(x)                    # 1 model call
for trans in transformations:
    p0 = trans.propertyValue(x)                     # measure BEFORE
    for delta in [self.delta, -self.delta]:
        xT = self._applyTransformation(x, trans, delta)   # perturb
        transformed = self.model.predict(xT)              # 1 model call
        numerator = transformed - baseline
        pT = trans.propertyValue(xT)                # measure AFTER
        achievedDelta = (pT - p0) / abs(p0)         # what we really did
        impact = numerator / abs(achievedDelta)     # ← THE ANSWER
```

The normalization has a **fallback ladder** for awkward cases:
1. Property not measurable → use the requested delta, and say so.
2. Relative mode with a non-zero base → relative achieved change.
3. Absolute mode, or base = 0 → absolute difference.
4. Achieved change is exactly 0 **and** the prediction did not move →
   report impact 0 and set **`noop = True`**.

> ### 🔬 Science box 21 — Why `noop` is scientific honesty
> Two very different situations both produce the number 0:
> - **(a)** we perturbed the graph and the model did not care.
> - **(b)** the delta was too small to move a single edge — we never
>   actually ran the experiment.
>
> Most tools print 0 for both, and a reader assumes (a). TGAP marks (b)
> with `noop = True`. This distinction is a correctness feature: *"no
> evidence"* is not the same as *"evidence of no effect"*.

Each row it returns carries **everything**: requested delta, achieved
delta, which normalizer was used, the baseline, the transformed
prediction, the noop flag, and optional leakage. Nothing to guess.

#### `summaryData(self, x)` — the log scale
Impacts can be +8.3 next to +0.0004; the small bar would be invisible. So
take `log10` of the size, put the sign back, and shift everything up so the
smallest bar starts at zero.

> ### 🔬 Science box 22 — Logarithmic scale
> A **log scale** compresses huge ranges: 1, 10, 100, 1000 become 0, 1, 2,
> 3. Used everywhere in science (earthquakes, sound, acidity). We use a
> *signed* log so direction survives: `sign(v) × log10(|v|)`.

#### `plotSummary`, `plotTrans`, `boxplotTrans`
Three pictures: a bar chart (one input), a sensitivity curve (sweep the
delta), a boxplot (many inputs). All accept `show=False` so tests can run
without opening a browser.

> ### 🔬 Science box 23 — Local vs global explanation
> **Local** = "why *this* answer for *this* input?" → `plotSummary`.
> **Global** = "what does the model care about *in general*?" →
> `boxplotTrans` over many inputs. A **boxplot** shows the middle 50% as a
> box and the range as whiskers, so you see not just the average effect
> but how *consistent* it is.

### `class GraphExplainer(ExplainerBase)`
```python
def _applyTransformation(self, graph, trans, delta):
    return trans.transformGraph(graph, delta)
```
One line: for a single graph, "apply" means "transform this snapshot".

---

## 13. `core/TemporalGraphExplainer.py`

**38 lines, of which 4 do work.** The headline class of the project.

```python
class TgapExplainer(ExplainerBase):
    def _applyTransformation(self, temporalGraph, trans, delta):
        return trans.transform(temporalGraph, delta)
```

That is all. Every feature — the experiment loop, the normalization, the
plots — is inherited. The only temporal-specific fact is that "apply"
means the whole-list method.

**This is the best evidence that the architecture is sound.** The entire
v0.2 overhaul of the normalization happened without editing this file.

---

## 14. `core/SyntheticData.py`

**222 lines, 3 functions.** Builds test worlds from a seed.

> ### 🔬 Science box 24 — Why fake data is the *right* choice here
> With real data you face two unknowns at once: *is the model right?* and
> *is the explainer right?* You cannot separate them.
>
> With generated data **we choose the truth**: this world has a bridge of
> exactly 8 edges. Then we ask TGAP, and check whether it says 8.
>
> It is like testing a weighing scale: you do not start with a mystery
> object, you put a known 1 kg weight on it.

### `makeTwoCommunityGraph(nPerCommunity, pIntra, bridgeWidth, seed, nPerCommunityB)`
Builds one snapshot in three steps:
1. **A backbone**: connect each community in a line (0–1–2–3…). This
   *guarantees* each side is connected, whatever the random step does.
2. **Random internal edges**, each added with probability `pIntra`.
3. **Exactly `bridgeWidth` crossing edges**, sampled at random.

> ### 🔬 Science box 25 — The Erdős–Rényi random graph
> Step 2 is the classic **G(n, p) model** (Erdős & Rényi, 1959): take n
> nodes and connect each possible pair with probability p. It is the
> "fair coin" of network science — the baseline against which real
> networks are compared.

Note step 3 says **exactly**, not "on average". Known truth must be exact,
or the tests could not check precise numbers.

### `makeTemporalGraph(...)`
Chains snapshots. Between each pair:
- **churn**: a fraction of internal edges are rewired (people change
  collaborators) — always *inside* a community, so the bridge is untouched.
- **bridgeDrift**: the bridge loses (or gains) edges each step.
  `bridgeDrift=1` is the "bridge decay" scenario.

### `makeScenario(name, ...)`
Ten ready-made worlds with recorded ground truth: `stable`,
`growing-bridge`, `decaying-bridge`, `high-churn`, `low-churn`,
`centralizing`, `decentralizing`, `asymmetric`, `sparse`, `dense`.

Returns `(temporalGraph, communities, info)` where `info["groundTruth"]`
records the fact the world was built to embody, e.g.
`{"bridgeTrendSign": -1}`.

Nice detail: the *centralizing* scenario is generated **by the
centralization transformation itself**, with a delta that grows each
snapshot. Re-using the perturbation as the generator means the ground
truth and the counterfactual cannot drift apart.

---

## 15. `core/Diagnostics.py`

**86 lines.** Measurement tools — no cleverness, just honesty.

### `class CallCountingModel`
```python
def predict(self, x):
    self.calls += 1
    return self.model.predict(x)
```
Wraps any model, forwards everything, counts. Because the explainer only
knows `predict`, this works on **any** model. It turns the efficiency
claim (`1 + 2K` calls) from a sentence in a docstring into a **measured,
tested fact**.

> ### 🔬 Science box 26 — The Decorator pattern
> An object that wraps another object, adds one behaviour, and keeps the
> same interface. Here the added behaviour is counting. Nothing else in
> the program notices the difference.

### `panelValue(metric, x)`
Evaluate a metric on a graph or a list of snapshots (average).

### `leakageReport(x, transformation, delta, metrics)`
Apply the transformation once, then measure a **whole panel** of
properties before and after. Returns `{name: {before, after, change}}`.

> ### 🔬 Science box 27 — Leakage (a confound, measured)
> When we add a bridge edge and delete an internal edge, we changed more
> than one thing. Other properties move too. That is **leakage**.
>
> Perfect isolation is impossible in a graph — everything touches
> everything. The scientific answer is not to pretend otherwise but to
> **measure it and publish it**. The transformation's own row is the
> intended change; every other non-zero row is leakage. If the intended
> change is much bigger, the explanation is trustworthy; if leakage is
> comparable, the two concepts cannot be separated with these tools.

### `formatLeakageReport(report, intendedName)`
Prints the table with a `*` marking the intended property.

---

## 16. `core/__init__.py`

**77 lines, no functions.** The front door.

A folder becomes an importable **package** when it contains this file.
Every `from .X import Y` line pulls a class up to package level, so users
write:

```python
from core import TgapExplainer, BridgeWidthMetric
```

instead of knowing which file each class lives in. If you reorganize the
files later, only this one file changes.

---

# PART III — THE PROGRAMS YOU RUN

## 17. `examples.py`

**313 lines, 4 demos.** The teaching file. Run this first.

`SHOW = "--no-show" not in sys.argv` — so `python examples.py --no-show`
computes everything but opens no windows. That is how the demos double as
automatic tests.

### `sanityCheck()` — putting TGAP on trial
Builds a world with **exactly 6 bridges** and the persistence model, so
prediction = 6. Every answer is computable by hand *before* running:

- Increase 10% → `round(6×1.1) = 7`, achieved = 1/6, impact = 1 ÷ (1/6) = **+6.0**
- Decrease 10% → `round(6×0.9) = 5`, impact = **−6.0**
- Centralization → bridge cannot change → **exactly 0**

Then it `assert`s all four. If TGAP were wrong, the program crashes.

It also runs the same thing in `"requested"` mode to show the old formula
gives ±10.0 — the rounding-inflated answer.

### `localExplanation()` — a genuine surprise
A decaying world plus a cohesion-trend model. Result: **"Increase Bridge
Width" comes out negative** — and that is correct. Widening every snapshot
multiplicatively makes the *decline steeper*, and a model that reads the
slope therefore predicts lower. The explanation is faithfully showing that
**this model reasons about trends, not levels.**

### `globalExplanation()`
Five different worlds, one boxplot — does the model react consistently?

### `temporalProperties()` — three theorems, executed
A stable world, the two temporal concepts, and two models:

| Claim | Why it must be true | Measured |
|---|---|---|
| **Blindness** | temporal changes leave the present untouched; persistence reads only the present | all impacts exactly `0.000` |
| **Sensitivity** | the trend model fits history's slope | `+0.848` / `−1.167` |
| **Orthogonality** | churn touches only internal edges | churn impact exactly `0.000` |

**This is the best demo for your presentation:** same graph, same
perturbation, two models — and TGAP correctly separates the one that
reasons about *trends* from the one that reasons about *levels*.

---

## 18. `evaluation.py`

**297 lines, 5 experiments, writes to `output/`.** The quick check.

| Function | What it measures |
|---|---|
| `makeWorld`, `makeTransformations` | shared setup |
| `evaluateFaithfulness()` | known-truth models vs measured impacts |
| `evaluateStability()` | same input → same answer; spread across seeds |
| `evaluateEfficiency()` | model calls + runtime |
| `evaluateDeltaSensitivity()` | impacts across several deltas |
| `evaluateLeakage()` | the property panel |

This is the fast developer-facing script. The paper version is next.

---

## 19. `paper_evaluation.py`

**1507 lines, 9 experiments, writes to `output/paper/`.** The research
artifact that answers eight research questions.

### The helpers at the top

| Function | Purpose |
|---|---|
| `makeWorld(...)` | the standard controlled world |
| `makeTransformations(...)` | all five concepts, with the partition |
| `meanMetric(metric, tg)` | a metric averaged over snapshots |
| `savePlot`, `saveCsv` | write a figure / a table |
| `errorFields(expectation, measured)` | compute errors **only** where a ground truth exists |
| `buildKnownTruthModels(tg, comm)` | the five models + their derived expectations |

### 🔑 The three kinds of expectation

This is the most important methodological idea in the file. For each
(model, concept) pair we record **how much we can legitimately claim in
advance**:

| Kind | Meaning | Example |
|---|---|---|
| `EXACT` | a number that follows mathematically | `f = w·p` → impact must be `w·p₀` |
| `ZERO` | provably exactly zero | a bridge-preserving change fed to a bridge-only model |
| `MEASURED` | **no prediction possible** — report the number, compute no error | bridge changes on a centralization model (they are not isolated) |

> ### 🔬 Science box 28 — Why `MEASURED` is the honest option
> It is tempting to write "expected: 0" everywhere and celebrate small
> errors. But the code does **not guarantee** that a bridge change leaves
> centralization alone. Claiming 0 would be inventing an expectation the
> implementation cannot honour. So we mark it `MEASURED`, report the value,
> and compute **no error at all**. A test enforces this rule.

### The nine experiments

| Function | Research question | What it answers |
|---|---|---|
| `rq1Faithfulness()` | RQ1 | Does TGAP recover a dependency we already know? |
| `rq1bMatchedComparison()` | RQ1b | Cross-concept comparison — but only where fair |
| `rq2TemporalSensitivity()` | RQ2 | Can it tell a history-reader from a present-reader? |
| `rq3Stability()` | RQ3 | Are explanations reproducible? |
| `rq4Efficiency()` | RQ4 | How many model calls and how long? |
| `rq5DeltaSensitivity()` | RQ5 | How do answers change with perturbation size? |
| `rq6Leakage()` | RQ6 | How much unintended change happens? |
| `rq7GraphSizeRobustness()` | RQ7 | Does it work on more than one tiny graph? |
| `rq8NormalizationAblation()` | RQ8 | Achieved vs requested normalization |

Then `printSummary(results)`, `toJson(results)`, `runAll()`.

### RQ1b deserves its own explanation — the fairness problem

**The problem we found.** Asking for "delta = 0.1" does **not** mean the
same thing for every concept:
- Bridge Width: delta = a relative change of the property → lands close to 10%.
- Centralization: delta = *fraction of edges to rewire* → a mechanism knob.
  Measured, it moved the property by **×17.75** the requested amount.

So comparing their impact sizes was comparing **unequal experiments**.

**The fix.** Three new functions:

- **`sweepConcept(model, tg, trans, deltas)`** — run one concept at many
  requested deltas, record what each actually achieved.
- **`bestMatch(sweepA, sweepB, direction, tolerance)`** — find the pair of
  runs whose achieved changes are closest. Returns `None` if the two
  concepts are not even in the same **units** (a ratio vs a slope).
- **`matchedComparisonForSeed(seed)`** / **`rq1bMatchedComparison(seeds)`** —
  do this for every concept pair, in **five different worlds**.

**No match is ever forced.** If the closest achievable pair is still too
far apart, the row says *"not comparable under the current transformation
semantics"* — and no comparison is made.

> ### 🔬 Science box 29 — Matching, and why science insists on it
> This is **experimental control** again. Comparing two treatments only
> makes sense at the same dose. If drug A was given at 10 mg and drug B at
> 200 mg, "B worked better" tells you nothing. Matching finds the doses
> that are comparable, and refuses to compare when none exist.

**And the multi-seed test changed the conclusion.** In one world the
result looked perfect (20 out of 20). Across five worlds: **119 out of 120**,
with one counterexample in seed 4. The summary therefore prints
*"NOT consistent across seeds"* rather than claiming a clean sweep.

### `printSummary` and `toJson`
Print every result next to the expectation fixed **before** running, and
save a machine-readable `summary.json`. Deliberately **no verdicts** like
"TGAP is superior" — only measurements and whether they match the
predefined expectation.

---

## 20. `tests/`

**91 automatic checks, 4 files.** Run: `python -m unittest discover -s tests`

| File | Checks |
|---|---|
| `test_transformations.py` | exact widths; anchors; determinism; never-mutate-input; tiny/complete/disconnected graphs; zero and huge deltas |
| `test_metrics.py` | star = 1.0, ring = 0.0; density of a complete graph = 1; cohesion 0 when disconnected and reproducible |
| `test_explainer.py` | normalization maths; exact model-call counts; stability; known-truth recovery; persistence blindness |
| `test_paper_evaluation.py` | leakage report structure; the discreteness floor; three graph sizes; the matching rules; multi-seed behaviour |

> ### 🔬 Science box 30 — Why tests are part of the science
> A test is a **written-down expectation that the computer checks every
> time**. If someone changes the code and breaks a property, the test fails
> immediately. Without tests, "it worked when I ran it" is the only
> evidence — and that is not reproducible science.
>
> Note carefully: our tests check **implementation behaviour** (is the
> maths right? is it deterministic?), never **research outcomes**. We do
> not test "the reference concept must always win", because that would
> force a conclusion instead of measuring it.

---

# PART IV — FOR YOUR PRESENTATION

## 21. Explaining it in 5 minutes

A slide order that works:

1. **The problem.** "A model says this community is at risk. Why? We need
   an answer a human can act on."
2. **The idea.** Change one meaningful thing, see how much the model moves.
3. **The example.** Two groups of 4 nodes, joined by 5 ties.
4. **One experiment.** Widen the bridge 5 → 6, *pay for it* by deleting one
   internal edge (total edges unchanged). Prediction 5.0 → 6.0.
5. **The answer table.** `+5, −5, 0, 0` and its plain-English reading.
6. **The subtle bit.** Graphs are discrete, so normalise by the change you
   *achieved*, not the one you *requested* — otherwise you report 10 where
   the truth is 5.
7. **The proof slide.** Persistence model reacts exactly `0.000` to a
   history-only change; the trend model reacts `±1.0`. Same graph, same
   perturbation, different models.
8. **The honesty slide.** The leakage panel + "model sensitivity, not
   causality" + the one counterexample in seed 4.
9. **Status.** 91 tests passing; errors under 1% against analytically
   known answers; next step = wrap a trained model.

## 22. Questions your professor may ask

**"Why not just use SHAP?"**
SHAP explains *individual features* ("time step 3 contributed +0.11"). We
explain *human concepts* ("bridge width"). SHAP also needs thousands of
model calls; we need 5. And SHAP's way of removing features creates
*impossible* graphs — the model's answer there is meaningless.

**"Why not GNNExplainer?"**
It finds *which edges* mattered and needs the model's internals. It cannot
answer "does the model care about bridge width as a concept?", and cannot
explain a model you only have as a black box.

**"Isn't your changed graph unrealistic?"**
We keep the node set and edge count fixed, so it is the same size with the
same activity — only routed differently. And we *measure* the leakage.

**"What if you defined the wrong concept?"**
Then TGAP will not find it. This is the honest limitation inherited from
TSAP: it explains only the concepts you define. The answer is to define
more concepts, with domain experts.

**"Did you find any bugs?"** — Yes, three, and each taught something:

1. **Rounding bias.** The original formula divided by the *requested*
   delta. With discrete graphs the achieved change differs, so every
   impact was inflated. Fixed by measuring before and after.
2. **Leakage in the defaults.** Centralization without a partition
   silently changed bridge width (+60 on a ±10 signal). Fixed by making
   rewiring preserve each tie's inside/crossing status.
3. **Tied hubs.** "Make less central" did nothing when two nodes shared the
   highest degree — because of the algebra in Science box 14, only the
   *maximum* degree matters. Fixed by re-finding the top node each step.
   Error dropped from 49% to 0.85%.

**"What is still broken?"**
`BridgeTrendTransformation` divides by `(1 + delta)`, so **delta = −1
crashes**. It is a genuine mathematical singularity, and the fix is a
design decision (raise a clear error, or clamp) — so it is documented, not
silently patched.

**"How do I know the numbers are real?"**
Delete the whole `output/` folder, re-run, and compare with git: 20 of 22
files come back **byte-identical**. The only two that differ contain
wall-clock timings, which naturally vary.

## 23. Glossary

| Term | Plain meaning |
|---|---|
| **Achieved delta** | how much a property *actually* changed |
| **Algebraic connectivity** | "how hard is it to cut this graph in two?" |
| **Anchor rule** | hold everything else fixed while changing one thing |
| **Black box** | a model that gives answers without reasons |
| **Bridge (CATALYST)** | the ties between two communities |
| **Bridge (graph theory)** | a cut-edge — removing it splits the graph |
| **Centralization** | how star-shaped a network is (0 = equal, 1 = one hub) |
| **Churn** | how much the past differs from the present |
| **Clustering** | "do my friends know each other?" |
| **Community** | a group with many links inside, few outside |
| **Complex contagion** | costly behaviour that needs several contacts to spread |
| **Confound** | a second thing that changed and spoils your conclusion |
| **Counterfactual** | "what if things had been different?" |
| **Degree** | how many edges touch a node |
| **Delta (δ)** | the size of the change we request |
| **Density** | fraction of possible edges that exist |
| **Determinism** | same input → same output, always |
| **Discreteness** | graphs change by whole edges, not fractions |
| **Edge / node** | a line / a dot in a graph |
| **Faithfulness** | does the explanation match what the model really does? |
| **Finite difference** | approximate derivative: change ÷ size of change |
| **GNN** | Graph Neural Network |
| **Impact** | the explanation number: prediction change ÷ achieved change |
| **Interface / contract** | the minimum a class must provide |
| **Jaccard distance** | how different two sets are (0 = same, 1 = disjoint) |
| **Leakage** | unintended change in other properties |
| **Linear regression** | the best straight line through points |
| **Model-agnostic** | works on any model, needing only `predict` |
| **Noop** | nothing actually changed — no experiment happened |
| **Perturbation** | deliberately changing the input to see what happens |
| **Seed** | the starting number that makes randomness repeatable |
| **Slope** | how fast something rises or falls over time |
| **Snapshot** | the graph at one moment in time |
| **Stability** | same input → same explanation |
| **Temporal graph** | a graph that changes over time |
| **TGN** | Temporal Graph Network — a GNN with memory |
| **Wide bridge** | many redundant ties between two communities |
| **XAI** | Explainable Artificial Intelligence |

---

*Everything in this document describes the code as it currently exists.
To check any claim yourself:*

```bash
cd c:\catalyst\tgap
python examples.py --no-show           # the 4 demos
python -m unittest discover -s tests   # the 91 checks
python paper_evaluation.py             # the 9 experiments
```
