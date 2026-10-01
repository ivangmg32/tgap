# TGAP v0.2 — Complete Code Walkthrough: Architecture, Every File, Line by Line

> **Who this is for:** you, after [doc 01](01-TSAP-explained-simply.md)
> (TSAP concepts), [doc 02](02-TGAP-code-walkthrough.md) (the v0.1 code),
> and [doc 03](03-TGAP-technical-audit.md) (the audit that produced v0.2).
> **What this is:** the walkthrough of the codebase **as it exists now** —
> v0.2. Files unchanged since doc 02 get a compressed recap with a pointer;
> everything new or rewritten gets the full line-by-line treatment.
> **The one-sentence summary of v0.2:** the explainer stopped trusting the
> delta you *asked for* and started measuring the change it *actually made*
> — and everything else (protocol, diagnostics, known-truth models, tests,
> evaluation) exists to support and prove that.

---

## Table of contents

1. [What changed from v0.1 to v0.2](#1-what-changed-from-v01-to-v02)
2. [Architecture of v0.2](#2-architecture-of-v02)
3. [The contracts, including the new optional one](#3-the-contracts)
4. [The math corner (read this before the code)](#4-the-math-corner)
5. [`TemporalGraphTransformation.py` — the extended base](#5-temporalgraphtransformationpy)
6. [`Transformations.py` — propertyValue and the two big fixes](#6-transformationspy)
7. [`GraphExplainer.py` — explainDetailed, the new heart](#7-graphexplainerpy)
8. [`TemporalGraphModel.py` — the known-truth models](#8-temporalgraphmodelpy)
9. [`Diagnostics.py` — counting and leakage](#9-diagnosticspy)
10. [`GraphMetric.py` — one new probe](#10-graphmetricpy)
11. [`SyntheticData.py` — the scenario registry](#11-syntheticdatapy)
12. [Unchanged files, quick recaps](#12-unchanged-files-quick-recaps)
13. [`tests/` — what 55 tests actually prove](#13-tests)
14. [`evaluation.py` — the five experiments](#14-evaluationpy)
15. [`examples.py` — what moved and why](#15-examplespy)
16. [Reading a detailed explanation record](#16-reading-a-detailed-record)
17. [The design rules, v0.2 edition](#17-the-design-rules-v02)
18. [The two bug stories of this round](#18-the-two-bug-stories)
19. [Exercises](#19-exercises)

---

## 1. What changed from v0.1 to v0.2

| Area | v0.1 | v0.2 |
|---|---|---|
| Normalization | divide by **requested** delta (TSAP's literal formula) | divide by **achieved** property change (default); `"requested"` kept as a mode |
| Transformation base | `name`, `transformGraph`, `transform` | + `propertyValue(x)`, `deltaMode` |
| Centralization decrease | drains one fixed hub — silently no-ops under degree ties | drains the *current* top node each step |
| Density | adds/removes edges anywhere (leaks +6.17 bridges at δ=+0.1!) | optional `communities` confines to intra pairs (leak = 0.00) |
| Explainer defaults | `communities=None` (the leaky configuration) | one partition detected at explain time, shared by both defaults |
| `boxplotTrans` | recomputes baseline per (delta × input) | baselines computed once |
| Provenance | dict of floats only | + `explainDetailed()`: achieved delta, normalizer, no-op flags, leakage |
| Models | Persistence, Trend | + `WeightedMetricModel`, `SlopeModel` (analytic ground truth) |
| Metrics | Density, Centralization, BridgeWidth, Cohesion | + `ClusteringMetric` (leakage probe) |
| Data | equal-size communities, ad-hoc worlds | + `nPerCommunityB`, `makeScenario` (10 named ground-truth scenarios) |
| Verification | asserts inside `examples.py` | + `tests/` (55 tests) + `evaluation.py` (5 experiments, CSV outputs) |
| New module | — | `Diagnostics.py` (call counting, leakage reports) |

Headline numbers after the changes: faithfulness magnitude error vs
analytic ground truth **0.00–0.85%** (was up to 49%), concept recovery
4/4, Spearman ρ = 1.0, model calls exactly `1 + 2K`.

---

## 2. Architecture of v0.2

### Data flow of one explanation (what actually happens now)

```
                     x = temporal graph [g0 … g5]
                                 │
                 TgapExplainer.explain(x)  ──►  explainDetailed(x)
                                 │
              ┌──────────────────┼──────────────────────────────┐
              │ 1 baseline call  │ per transformation T:        │
              │ f = model.predict(x)                            │
              │                  │  p0 = T.propertyValue(x)  ◄── NEW: measure
              │                  │       (0 model calls!)        the property
              │                  │  for δ in {+0.1, −0.1}:       before…
              │                  │    xT = T.transform(x, δ)
              │                  │    fT = model.predict(xT)     (2K calls)
              │                  │    pT = T.propertyValue(xT) ◄─ …and after
              │                  │    achieved = (pT−p0)/|p0|    (relative)
              │                  │            or pT−p0           (absolute)
              │                  │    impact = (fT − f) / |achieved|  ◄── THE FIX
              └──────────────────┴──────────────────────────────┘
                                 │
        {label: impact}  +  detailed records (deltas, normalizer,
                             noop flags, optional leakage panel)
```

Model-call budget is **unchanged**: `1 + 2K`. `propertyValue` is a graph
computation (counting edges, a polyfit), never a model call — verified by
`CallCountingModel` in the tests.

### Dependency graph (new modules marked ●)

```
examples.py  evaluation.py●  tests/●
      └──────────┴──────────────┘
                 ▼
         core/__init__.py
                 ▼
 TemporalGraphExplainer ─► GraphExplainer (engine; now: normalization)
 Diagnostics● ──────────► (models, metrics — measurement only)
 GraphExplainer ────────► Transformations, Communities (lazy defaults)
 Transformations ───────► TemporalGraphTransformation, Communities,
                          GraphMetric ◄── NEW dependency (propertyValue
                                          reuses DegreeCentralizationMetric)
 SyntheticData ─────────► Transformations ◄── NEW dependency (the
                                          centralizing scenario reuses the
                                          transformation as a generator)
 TemporalGraphModel ────► numpy only        GraphModel ─► nothing
```

Two new arrows deserve a comment. `Transformations → GraphMetric` exists
so a transformation can *measure the property it claims to change* — the
transformation and the measurement now share one definition, which is what
makes achieved-delta normalization honest. `SyntheticData → Transformations`
is a deliberate reuse: the "centralizing" scenario *generates* data by
applying the centralization transformation with growing delta — the same
code that perturbs is trusted to construct, so ground truth and
counterfactual share semantics.

---

## 3. The contracts

The three original contracts are untouched — this is what §15 of the audit
verified ("prepare for a real TGN"):

```python
GraphModel.predict(graph) -> float
TemporalGraphModel.predict(temporalGraph) -> float
Metric.measure(graph) -> float
```

Any future TGN/GAT/GraphSAGE/Transformer wraps behind `predict` and the
explainer never knows. The **new, fourth contract is optional**:

```python
TemporalGraphTransformation.propertyValue(x) -> float | None
TemporalGraphTransformation.deltaMode: "relative" | "absolute"
```

Optional means: a user-written transformation that doesn't implement it
still works — the explainer falls back to requested-delta normalization
and *says so* in the detailed record (`normalizer: "requested"`). Nothing
breaks; precision degrades visibly instead of silently.

---

## 4. The math corner

Three small derivations power everything in v0.2. Worth 10 minutes each.

### 4.1 Why "achieved" normalization is the faithful TSAP port

TSAP computes `impact = (f(x_δ) − f(x)) / |δ|`. For a *continuous* series,
multiplying deviations by (1+δ) changes volatility by **exactly** δ — the
requested and actual change coincide, so TSAP is *already* dividing by the
actual change. Graphs are discrete: `round(6·1.1) = 7` is a change of
1/6 ≈ 16.7%, not 10%. Dividing by the requested 0.1 multiplies every
impact by the rounding ratio (here 1.67), which varies with the width —
so v0.1 magnitudes were biased and not comparable across inputs.

With achieved normalization and relative `deltaMode`:

```
impact = (f(xT) − f(x)) / |Δp / p₀|
```

which is a finite-difference estimate of **∂f/∂ln p** — a
*semi-elasticity*: "how much does the prediction move per relative unit of
property change". Two consequences you can verify by running
`evaluation.py`:

- For `f = p` (persistence of bridge width), impact = `Δp·p₀/|Δp|` =
  **±p₀ exactly** (±8 on the standard world). The explainer returns the
  model's true derivative, at any delta big enough to move one edge.
- The impact is **delta-invariant** (8.0 at δ = 0.1, 0.2, 0.3, 0.5), while
  requested-mode fluctuates between 6.67 and 10.0 with the rounding.

### 4.2 The Freeman collapse (the tied-hub bug)

Freeman degree centralization is `C = Σᵢ(d_max − dᵢ) / ((n−1)(n−2))`.
Expand the sum: `Σᵢ(d_max − dᵢ) = n·d_max − Σᵢdᵢ = n·d_max − 2m`. So

```
C = (n·d_max − 2m) / ((n−1)(n−2))
```

Under a rewiring that preserves the edge count, `n` and `m` are constants
— **C is a function of the maximum degree alone.** Concentrating works
(the hub's degree rises, d_max rises). But *redistributing from one fixed
hub* only lowers d_max if that hub was the *unique* maximum. If another
node ties at d_max, you can drain the first hub to zero and C does not
move. In the standard world, 4 of 6 snapshots had such ties → the decrease
direction silently achieved ΔC = 0 → the faithfulness experiment showed
impact 0.000 where theory demanded ≈ c₀. Fix in §6.4.

### 4.3 The linear known-truth predictions

For `f = Σⱼ wⱼ·pⱼ` (a `WeightedMetricModel`), perturbing concept j by
relative amount r changes f by `wⱼ·pⱼ·r` (+ leakage through the other
terms). Normalizing by |r| leaves **wⱼ·pⱼ** — so the expected impact of
each concept is *weight × current property value*, computable by hand.
That's the entire faithfulness protocol: measured vs `wⱼ·pⱼ`. And for
`SlopeModel` under BridgeTrend (absolute mode), `f` *is* the slope, so
impact = `Δslope/|Δslope|` = **±1.0 exactly**. Both show up verbatim in
the evaluation output.

---

## 5. `TemporalGraphTransformation.py`

File: [core/TemporalGraphTransformation.py](../tgap/core/TemporalGraphTransformation.py).
The v0.1 parts (the `name` attribute, `transformGraph` contract,
`transform` = map-over-snapshots, the structural/temporal taxonomy) are as
in doc 02 §9. New lines:

```python
    # How the ACHIEVED property change should be computed by the explainer:
    #   "relative": (pAfter - pBefore) / |pBefore|   (a ratio, like delta)
    #   "absolute": pAfter - pBefore                 (property's own units;
    #               used when pBefore can legitimately be 0, e.g. a slope)
    deltaMode = "relative"
```

A class attribute, like `name`. Why two modes? Division by `|p₀|` breaks
when `p₀ = 0` — and a *slope* is legitimately 0 on a stable world. So
trajectory properties declare `"absolute"` and their achieved change stays
in the property's own units (edges/step). The explainer also falls back to
absolute arithmetic automatically if a relative-mode property happens to
be 0 (§7).

```python
    def propertyValue(self, x):
        ...
        return None
```

The base returns `None` — "not measurable". This is the graceful-degradation
hook: the explainer treats `None` as "use requested normalization and flag
it". Every shipped transformation overrides it; a user's quick experiment
doesn't have to.

---

## 6. `Transformations.py`

File: [core/Transformations.py](../tgap/core/Transformations.py). The
mechanics of `_edgeKey`, `_safeToRemove`, `setBridgeWidth`, and each
transformation's edge surgery are unchanged from doc 02 §10 — reread that
if fuzzy. Here: the new helper, the five `propertyValue`s, and the two
fixes.

### 6.1 `_snapshots` — one code path for both explainers

```python
def _snapshots(x):
    return x if isinstance(x, list) else [x]
```

`propertyValue` gets called with a single graph (static explainer) or a
list (temporal). Wrapping the single graph in a one-element list lets every
implementation just loop. A one-liner that halves the code below it.

### 6.2 The five propertyValues — each concept, made measurable

**BridgeWidth** (relative):

```python
    def propertyValue(self, x):
        widths = []
        for g in _snapshots(x):
            communities = self.communities
            if communities is None:
                communities = detectTwoCommunities(g)
            widths.append(len(interCommunityEdges(g, communities)))
        return float(np.mean(widths))
```

Mean width across snapshots — *mean*, not last, because the structural
transformation scales **every** snapshot; the property definition must
match what the transformation actually touches. Note it mirrors
`transformGraph`'s community handling exactly (given partition, else
per-snapshot detection): measurement and mechanism must agree or the
achieved delta lies.

**Centralization** (relative):

```python
    def propertyValue(self, x):
        metric = DegreeCentralizationMetric()
        return float(np.mean([metric.measure(g) for g in _snapshots(x)]))
```

Reuses the *metric class* rather than re-deriving the formula — one
definition of Freeman centralization in the whole codebase. The docstring
makes the honest admission: this transformation's `delta` is a *mechanism
knob* (fraction of edges rewired), not a property ratio — measuring
before/after is precisely what makes its impacts comparable with the
others despite that.

**BridgeTrend** (absolute — see §4 for why):

```python
    deltaMode = "absolute"

    def propertyValue(self, x):
        snapshots = _snapshots(x)
        if len(snapshots) < 2:
            return None
        widths = [len(interCommunityEdges(g, self.communities))
                  for g in snapshots]
        slope, _ = np.polyfit(np.arange(len(widths)), widths, 1)
        return float(slope)
```

The property is the OLS slope of the width series — the same quantity
`SlopeModel` predicts and `TrendTemporalModel` extrapolates; three uses,
one definition (`np.polyfit(..., 1)`). `None` for a single snapshot: a
trajectory property needs a trajectory.

**Churn** (relative) — the concept finally gets a formal definition:

```python
        lastEdges = {_edgeKey(u, v) for u, v in snapshots[-1].edges()
                     if self._isIntra(u, v)}
        distances = []
        for g in snapshots[:-1]:
            gEdges = {_edgeKey(u, v) for u, v in g.edges()
                      if self._isIntra(u, v)}
            union = gEdges | lastEdges
            if not union:
                distances.append(0.0)
            else:
                distances.append(len(gEdges ^ lastEdges) / len(union))
        return float(np.mean(distances))
```

Line by line: normalize both edge sets with `_edgeKey`; `^` is symmetric
difference (edges in exactly one of the two graphs — the *disagreement*);
`|` is union; their ratio is the **Jaccard distance** (0 = identical,
1 = disjoint); mean over history = "how much does the past disagree with
the present". Two subtleties: the `if self._isIntra(u, v)` filters restrict
measurement to the same universe the transformation churns (given a
partition, intra edges only — measuring bridges it never touches would
dilute the achieved delta); and the empty-union guard returns 0.0 rather
than dividing by zero.

**Density** (relative): mean edge count — with the comment explaining why
count, not density: they differ by the constant n(n−1)/2, so their
*relative* changes are identical, and the count is the simpler number.

### 6.3 Fix: `DensityTransformation(communities=...)`

v0.1's density transformation added edges anywhere. The audit quantified
what "anywhere" means on a two-community graph: the non-edge pool is
dominated by cross pairs (two sparse 15-blobs have ≈15×15 cross non-edges),
so "+10% edges" mostly **widened the bridge** — measured +6.17 bridges of
leakage. The fix is the same `_isIntra` pattern centralization and churn
already use:

```python
        if k > 0:
            candidates = sorted(e for e in nx.non_edges(g)
                                if self._isIntra(*e))
```

With a partition: adds/removes intra only → bridge width untouched
(measured leak 0.00, tested). Without: old behavior, now loudly documented
in the `Leakage:` docstring section. The unconstrained mode is *kept* —
sometimes you genuinely want "more edges anywhere" — but choosing it is now
an informed act.

### 6.4 Fix: the redistribute branch (the tied-hub bug)

The concentrate branch is unchanged. The decrease branch was rewritten:

```python
            rewired = 0
            attempts = 0
            while rewired < k and attempts < 4 * k + 20:  # bounded loop
                attempts += 1
                top = max(sorted(g.nodes()), key=lambda n: g.degree(n))
                neighbors = sorted(g.neighbors(top))
                if not neighbors:
                    break
                v = neighbors[rng.randrange(len(neighbors))]
```

- `top` is recomputed **inside** the loop — that is the entire fix. §4.2:
  C depends only on d_max; to lower d_max you must drain whichever node
  currently holds it, and after a few moves that's a *different* node
  (ties get pulled down one by one).
- `while ... attempts < 4*k + 20` — a bounded loop instead of `for` over a
  precomputed edge list, because the edge list changes as we go. The bound
  guarantees termination even on pathological graphs where receivers keep
  failing; 4k+20 gives generous headroom for skipped attempts.
- `v = neighbors[rng.randrange(len(neighbors))]` — seeded choice of which
  tie to move, over a sorted list: same determinism idiom as everywhere.

```python
                receivers = sorted(g.nodes(), key=lambda n: (g.degree(n), n))
                receiver = next(
                    (r for r in receivers
                     if r not in (top, v)
                     and self._sameSide(r, top)
                     and not g.has_edge(r, v)),
                    None,
                )
                if receiver is None:
                    continue  # this v had no valid receiver; try another
                g.remove_edge(top, v)
                g.add_edge(receiver, v)
                rewired += 1
```

The receiver logic is the v0.1 one with `hub` → `top`: poorest node
(degree, then id — deterministic tie-break), on *top's* side (status
preservation: the swapped endpoints are same-side, so the tie's
intra/inter character — hence bridge width — is invariant), not already
tied to `v`. One line of comment-worthy physics: **v's degree is unchanged
by the move** (loses top, gains receiver), so only `top` (−1) and
`receiver` (+1) move — and since the receiver starts minimal it can't
accidentally become the new maximum.

Regression test: `testRedistributeLowersMetricUnderTiedMaxDegree` runs the
decrease on **every** snapshot of the standard world — including the four
that silently no-oped in v0.1 — and requires C to strictly drop.

---

## 7. `GraphExplainer.py`

File: [core/GraphExplainer.py](../tgap/core/GraphExplainer.py). The plot
methods and `summaryData` are as in doc 02 §11 (one `boxplotTrans` change
below). The constructor, defaults, and explanation core are new.

### 7.1 `_panelValue` (module level)

```python
def _panelValue(metric, x):
    if isinstance(x, list):
        return float(np.mean([metric.measure(g) for g in x]))
    return float(metric.measure(x))
```

Same both-input-kinds trick as `_snapshots`, for the leakage panel: a
metric on a temporal graph = mean over snapshots.

### 7.2 `__init__` — one new parameter, one big docstring

```python
    def __init__(self, model, transformations=None, defaultDelta=0.1,
                 normalization="achieved"):
```

Backward compatible: all old call sites work unchanged (the new argument
is keyword-with-default, in last position). The docstring carries the §4.1
argument in full — deliberately, because whoever reads
`help(TgapExplainer)` must understand *why* their numbers differ from
v0.1. Note what `__init__` no longer does: build default transformations.
It just stores `None`.

### 7.3 `_resolveTransformations` — leak-free lazy defaults

```python
    def _resolveTransformations(self, x):
        if self.transformations is not None:
            return self.transformations
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
```

The v0.1 defaults were `BridgeWidthTransformation()` +
`CentralizationTransformation()` — both partition-less, i.e. *the exact
configuration measured to leak +60 on a ±10 signal*. A dangerous default
is worse than no default. But defaults can't know the partition at
construction time (there's no data yet) — so resolution moves to explain
time: detect **one** partition from the input (last snapshot for temporal
— the most current structure) and *share it* between both defaults, making
default-centralization bridge-preserving. Deterministic (greedy modularity
is), re-derived per call, and still second-best to passing explicit
transformations — the docstring says so. The lazy `import` inside the
method is the same circular-import avoidance as v0.1, relocated.
`plotTrans`/`boxplotTrans` default `trans=None` now resolve through this
too.

### 7.4 `explain` — now a two-liner

```python
    def explain(self, x):
        return {r["label"]: r["impact"] for r in self.explainDetailed(x)}
```

The public shape is untouched — same dict, same labels, same use in
`summaryData`/plots — but it is now a *view* of the detailed records.
One implementation, two presentations.

### 7.5 `explainDetailed` — the new heart, line by line

Setup:

```python
        transformations = self._resolveTransformations(x)
        baseline = self.model.predict(x)  # baseline: 1 model call
        leakageMetrics = leakageMetrics or {}
        leakBefore = {name: _panelValue(metric, x)
                      for name, metric in leakageMetrics.items()}
```

Baseline once (call #1). Leakage "before" values once per metric — they
depend only on `x`, so computing them inside the loop would be waste.

Per transformation:

```python
        for trans in transformations:
            p0 = trans.propertyValue(x) if self.normalization == "achieved" \
                else None
```

The property *before*, measured once per transformation (not once per
direction — it's the same `x`). In `"requested"` mode we skip measurement
entirely: `p0 = None` routes every record down the legacy path.

Per direction:

```python
            for delta in [self.delta, -self.delta]:
                direction = "Increase" if delta > 0 else "Decrease"
                label = direction + " " + trans.name + \
                    " (" + str(100 * abs(delta)) + "%)"
                xT = self._applyTransformation(x, trans, delta)
                transformed = self.model.predict(xT)
                numerator = transformed - baseline
```

Unchanged v0.1 logic up to here (labels identical → old asserts and plots
keep working). Calls #2…#(1+2K).

The normalization decision tree — the most important 20 lines in v0.2:

```python
                achievedDelta = None
                normalizer = "requested"
                if p0 is not None:
                    pT = trans.propertyValue(xT)
                    if trans.deltaMode == "relative" and p0 != 0:
                        achievedDelta = (pT - p0) / abs(p0)
                    else:
                        achievedDelta = pT - p0
                    if achievedDelta != 0:
                        normalizer = "achieved"
```

Read it as a fallback cascade:
1. property unmeasurable (`p0 is None`, including `"requested"` mode and
   custom transformations without `propertyValue`) → requested;
2. measurable, relative mode, nonzero base → relative achieved change
   (`abs(p0)` in the denominator keeps the *sign* of the change intact —
   only the scale is normalized);
3. absolute mode **or** `p0 == 0` → absolute difference (the `p0 == 0`
   case is the relative-mode-with-zero-base rescue: rather than divide by
   zero, degrade to the property's own units);
4. and if the achieved change is exactly 0, the "achieved" normalizer is
   unusable — fall through with `normalizer` still `"requested"`.

Then the impact:

```python
                noop = False
                if normalizer == "achieved":
                    impact = numerator / abs(achievedDelta)
                elif achievedDelta == 0 and numerator == 0:
                    impact = 0.0
                    noop = True
                else:
                    impact = numerator / abs(delta)
```

Three exits: the honest sensitivity (achieved); the honest **no-op**
(property unchanged *and* prediction unchanged — e.g. δ=0.05 on width 8
rounds to width 8; reporting 0 with `noop=True` says "no counterfactual
was actually tested here", which is different from "tested and the model
didn't care"); and the flagged fallback (property unchanged but the
prediction *did* move — the perturbation did something the property
doesn't capture; requested-normalization keeps the information, and
`normalizer: "requested"` in the record warns you).

Leakage and the record itself close the loop:

```python
                leakage = {}
                for name, metric in leakageMetrics.items():
                    after = _panelValue(metric, xT)
                    leakage[name] = {"before": leakBefore[name],
                                     "after": after,
                                     "change": after - leakBefore[name]}
                records.append({ "label": label, ... "leakage": leakage })
```

Every number that went into an impact is preserved: `requestedDelta`,
`achievedDelta`, `deltaMode`, `baseline`, `transformed`, `impact`,
`normalizer`, `noop`, `leakage`. Nothing to reverse-engineer when a value
surprises you. See §16 for a worked read.

### 7.6 The `boxplotTrans` fix

```python
        baselines = [self.model.predict(x) for x in xs]
        df = pd.DataFrame({})
        for delta in X:
            distrib = []
            for x, baseline in zip(xs, baselines):
                xT = self._applyTransformation(x, trans, delta)
                distrib.append(self.model.predict(xT) - baseline)
```

v0.1 (inherited from TSAP) called `predict(x)` inside the delta loop —
`nValues×` redundant baseline calls. Now: `|xs|` baselines up front, then
one perturbed call per (delta, input). The test asserts the exact count:
`len(xs) + nValues*len(xs)`.

---

## 8. `TemporalGraphModel.py`

File: [core/TemporalGraphModel.py](../tgap/core/TemporalGraphModel.py).
The interface and the Persistence/Trend baselines are doc 02 §6. New: the
two models whose explanations are *derivable before running anything* —
the comment block above them states the philosophy: *"If the explainer's
output disagrees with the derivation, the explainer is wrong — there is no
ambiguity to hide in."*

### `WeightedMetricModel`

```python
    def __init__(self, weightedMetrics, mode="last"):
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
```

- `weightedMetrics` is a list of `(weight, metric)` pairs — so
  `WeightedMetricModel([(2.0, BridgeWidthMetric(comm)), (3.0,
  DegreeCentralizationMetric())])` *is* the model `pred = 2·bw + 3·c`
  requested in the review brief, literally.
- The loop is four lines of arithmetic: measure each metric (on the last
  snapshot, or the mean), multiply by its weight, sum.
- The known truth (§4.3): expected impact of concept j = `wⱼ·pⱼ`. The
  evaluation measures 16.000 vs expected 16.000 (bridge term) and 0.373 vs
  0.369 (centralization term — the 1% gap *is the measured leakage*, and
  the leakage panel shows you exactly where it came from).
- The explicit `ValueError` on a bad mode: a typo like `mode="latest"`
  fails at construction, not as silently-wrong numbers three calls later.

### `SlopeModel`

```python
    def predict(self, temporalGraph):
        y = [self.metric.measure(g) for g in temporalGraph]
        if len(y) < 2:
            return 0.0  # a single snapshot has no slope
        slope, _ = np.polyfit(np.arange(len(y)), y, 1)
        return float(slope)
```

Prediction = the slope itself (not an extrapolated level — that's
`TrendTemporalModel`'s job). A pure trajectory-reader: the mirror image of
`PersistenceTemporalModel` (pure level-reader). Between them they bracket
the temporal dimension, which is why demo 4 and the tests use the pair to
prove blindness/sensitivity from both sides. Its known truth: BridgeTrend
impact = ±1.0 *exactly* (measured: 1.000), churn impact = 0 exactly.

---

## 9. `Diagnostics.py`

File: [core/Diagnostics.py](../tgap/core/Diagnostics.py). New module, three
tools, all measurement, zero magic.

### `CallCountingModel`

```python
class CallCountingModel:
    def __init__(self, model):
        self.model = model
        self.calls = 0

    def predict(self, x):
        self.calls += 1
        return self.model.predict(x)
```

The decorator pattern at its smallest: satisfies the model contract,
forwards everything, counts. Because the explainer only knows `predict`,
this wraps *any* model — which is how the `1 + 2K` complexity claim became
an executable assertion (`testExplainCostsOnePlusTwoK`) instead of a
sentence in a docstring.

### `leakageReport` / `formatLeakageReport`

```python
def leakageReport(x, transformation, delta, metrics):
    if isinstance(x, list):
        xT = transformation.transform(x, delta)
    else:
        xT = transformation.transformGraph(x, delta)
    report = {}
    for name, metric in metrics.items():
        before = panelValue(metric, x)
        after = panelValue(metric, xT)
        report[name] = {"before": before, "after": after,
                        "change": after - before}
    return report
```

Apply the transformation once, measure a whole *panel* of metrics
before/after. The transformation's own property row is the **intended**
change; every other nonzero row is **leakage** — the docstring includes the
reading guide (leakage orders of magnitude below the intended change =
acceptable noise; comparable size = these two concepts cannot be explained
independently with this transformation pair). `formatLeakageReport` renders
it as an aligned console table with `*` marking the intended row. This is
the §7-of-the-review requirement ("do not merely document leakage —
quantify it") as a first-class API.

---

## 10. `GraphMetric.py`

Doc 02 §8 still covers Density/Centralization/BridgeWidth/Cohesion
(including the seeded-eigensolver story). One addition:

```python
class ClusteringMetric(Metric):
    def measure(self, graph):
        if graph.number_of_nodes() == 0:
            return 0.0
        return float(nx.average_clustering(graph))
```

Average clustering coefficient — "do my friends know each other". Its role
in TGAP is deliberate: **no transformation targets clustering**, so any
movement in this metric under a transformation is *pure, measured
side-effect* — the canary in the leakage panel. (Current readings: −0.007
under BridgeWidth, +0.112 under Centralization — hub concentration
naturally creates triangles.)

---

## 11. `SyntheticData.py`

Doc 02 §13 covers the generator mechanics (backbone trick, G(n,p) coin
flips, exact bridge sampling, churn/drift evolution). Two v0.2 changes:

### Asymmetric communities

```python
    nA = nPerCommunity
    nB = nPerCommunityB if nPerCommunityB is not None else nPerCommunity
    setA = set(range(nA))
    setB = set(range(nA, nA + nB))
```

`nPerCommunityB=None` defaults to equal sizes — every existing call site
unchanged. The two backbone loops split accordingly (they can't share a
loop anymore since the communities differ in length). Why it matters: real
ecosystems are asymmetric, and several algorithms (candidate pools,
detection) behave differently when |A| ≠ |B| — now testable.

### The scenario registry

```python
SCENARIOS = {
    "stable":          "constant bridge width, mild churn",
    "growing-bridge":  "bridge gains one tie per snapshot (positive trend)",
    ...
}

def makeScenario(name, nSnapshots=6, nPerCommunity=15, seed=42):
```

Ten named worlds, each returning `(temporalGraph, communities, info)` where
`info["groundTruth"]` records the fact the world was built to embody
(`{"bridgeTrendSign": -1}` for `decaying-bridge`, etc.). The registry turns
"does TGAP identify the concept that actually drives the model?" into a
loop over names. Two implementation notes:

- The trend scenarios just parameterize the existing generator
  (`bridgeDrift=±1`). The **centralizing/decentralizing** scenarios do
  something more interesting:

```python
        trans = CentralizationTransformation(communities, seed=seed)
        tg = [trans.transformGraph(g, sign * 0.06 * t) if t > 0 else g
              for t, g in enumerate(tg)]
```

  Build a stable world, then push snapshot *t* by delta `±0.06·t` — a
  progressively concentrating (or flattening) history, generated **by the
  transformation itself**. Reusing the perturbation as the generator means
  scenario ground truth and counterfactual semantics can't drift apart.
- Ground truths are *tested, not assumed*: `testScenarioTrendGroundTruth`
  measures the slope of the built world and checks its sign matches the
  registry claim.

---

## 12. Unchanged files, quick recaps

- **`GraphModel.py`** (doc 02 §5): the `predict(graph) → float` interface +
  `MetricGraphModel`. Untouched — which is itself the finding: the entire
  v0.2 normalization overhaul happened without changing the model contract,
  confirming a TGN can be wrapped later with zero explainer changes.
- **`TemporalGraphExplainer.py`** (doc 02 §12): still four lines. All new
  behavior arrived via the base class; `TgapExplainer` inherited
  `explainDetailed` and the normalization modes without an edit.
- **`Communities.py`** (doc 02 §7): unchanged; now also the partition
  supplier for the lazy defaults.
- **`Cache`-style plumbing**: none needed here; synthetic data is
  regenerated deterministically from seeds.

---

## 13. `tests/`

Files: [tests/](../tgap/tests/). 55 tests, stdlib `unittest` (no new
dependency), run with `python -m unittest discover -s tests`. The shim in
`tests/__init__.py` prepends the tgap root to `sys.path` so `core` imports
regardless of runner quirks.

The suite's philosophy (from the module docstring): *every test asserts a
hand-derivable value or a docstring-promised invariant — "it runs" is not
a test.* Two helpers make graph equality exact:

```python
def edgeSet(g):
    return {frozenset(e) for e in g.edges()}

def snapshotFingerprint(tg):
    return [(set(g.nodes()), edgeSet(g)) for g in tg]
```

`frozenset` because `(3,7)` and `(7,3)` are the same undirected edge, and
sets of frozensets compare exactly. What each class proves:

| Test class | Proves |
|---|---|
| `TestBridgeWidthExact` | width targets to the edge (`round(8·1.1)=9`); zero/tiny delta = identity; huge delta capped; edge-count anchor at ±30%/±60%/100%; never severs the last bridge; 2-node communities and disconnected inputs don't crash |
| `TestCentralization` | metric rises on concentrate, falls on redistribute; **falls on every snapshot even under tied max degrees** (the v0.2 regression test); bridge width exact-preserved for six deltas; anchors |
| `TestDensity` | exact `round(m(1+δ))` counts; confined mode preserves bridges; **unconstrained mode's leak is asserted as a fact, not hidden**; complete graph = no candidates handled |
| `TestBridgeTrend` | last snapshot byte-identical; rising/decaying direction; the hand-derived `[5,5,6,7,7,8]` compounding trajectory; per-snapshot anchors; static mode raises |
| `TestChurn` | last snapshot identical; Jaccard property moves with delta's sign; bridge and edge counts preserved per snapshot; single-snapshot property is `None`; static mode raises |
| `TestDeterminismAndMutation` | same seed → identical edge sets for all 5 transformations × both directions; inputs never mutated (fingerprint before == after); different seeds → different edges but same achieved width (guards against a dead rng) |
| `TestMetrics` | star = 1.0, ring = 0.0 (Freeman); K₅ density = 1; exact widths; cohesion 0 when disconnected, deterministic (bug-2 regression), and ranks thin < wide bridges; triangle clustering = 1 |
| `TestNormalization` | achieved = ±8.0 (the true derivative), requested = ±10.0 (TSAP parity), tiny delta → `noop=True` + impact 0, provenance fields exact (`achievedDelta == 1/8`) |
| `TestEfficiency` | `explain` = exactly `1+2K` calls; `boxplotTrans` = exactly `len(xs) + nValues·len(xs)` |
| `TestStability` | byte-identical repeated explanations across all 4 transformations |
| `TestFaithfulnessKnownTruth` | single-concept recovery exact (8.0/0.0); two-concept model ≈16 ± leakage with dominance and signs; SlopeModel reads only trajectory; persistence blind to history |
| `TestScenariosAndDefaults` | all 10 scenarios build with consistent node sets; trend ground truths *measured*; **lazy defaults are leak-free** (default centralization impact = 0.0 on a width model) |

---

## 14. `evaluation.py`

File: [evaluation.py](../tgap/evaluation.py). The research-facing script —
TSAP's `GummadiEvaluation.py` + `PerturbationFaithfulness.py` in spirit,
*not* copied: TSAP evaluates on real stock data where no ground truth
exists, so it can only correlate explanations with model behavior. TGAP's
synthetic setting permits the stricter test — **error against analytic
ground truth**. Five experiments, console tables + CSVs in `output/`:

1. **Faithfulness** — four known-truth models × four concepts. Measures
   dominant-concept recovery, sign agreement, magnitude error vs `wⱼ·pⱼ`,
   Spearman ρ between measured |impacts| and expected sensitivities.
   Current results: **4/4, 4/4, 0.00–0.85%, ρ=1.0**.
2. **Stability** — two *distinct* properties the review demanded we not
   conflate: deterministic repeatability (same everything → byte-equal;
   asserted) and robustness to transformation randomness (10 different
   transformation seeds → std of impacts; currently 0.000 on the linear
   models: seed changes *which* edges move, not the measured sensitivity).
3. **Efficiency** — `CallCountingModel` + wall clock: 9 calls for K=4
   (asserted equal to `1+2K`), ~38 ms with metric models.
4. **Delta sensitivity** — the §4.1 table: achieved-norm flat at the true
   8.0; requested-norm wobbling 6.67–10.0. The empirical argument for the
   default, in five rows.
5. **Leakage panel** — all transformations × five metrics, including the
   density pair (confined vs unconstrained: bridge-width leak 0.00 vs
   **+6.17**) — §7 of the review, delivered as data.

---

## 15. `examples.py`

Doc 02 §14 still describes demos 2–4 structurally. What moved in v0.2:

- **Demo 1's numbers changed — deliberately.** Achieved normalization gives
  `±6.0` (= the current width = the true semi-elasticity of a
  persistence-of-width model), and a second explainer with
  `normalization="requested"` asserts the old `±10.0`. Both derivations are
  in the docstring; keeping both testable *documents the why* of the
  default.
- **Demo 2 gained a leakage panel** — `leakageReport` +
  `formatLeakageReport` on the bridge transformation, showing intended
  `+0.5` mean width against `+0.000` density, `+0.0000` centralization,
  `−0.0031` clustering.
- Demo 4's sign/blindness/orthogonality asserts survived normalization
  unchanged — zeros are zeros under any normalizer, and signs are
  normalization-invariant (the normalizer is an absolute value).

---

## 16. Reading a detailed record

```python
>>> explainer = TgapExplainer(model, transformations)
>>> r = explainer.explainDetailed(tg)[0]
{'label': 'Increase Bridge Width (10.0%)',
 'transformation': 'Bridge Width',
 'requestedDelta': 0.1,          # what we asked for
 'achievedDelta': 0.125,         # what actually happened: 8 -> 9 = +1/8
 'deltaMode': 'relative',
 'baseline': 8.0,                # model on the original
 'transformed': 9.0,             # model on the perturbed
 'impact': 8.0,                  # (9-8)/0.125 - the semi-elasticity
 'normalizer': 'achieved',       # which denominator was used
 'noop': False,
 'leakage': {}}                  # fill via leakageMetrics=...
```

Diagnostic recipes:
- `noop: True` → your delta was below the discreteness threshold; raise it
  or accept that no counterfactual was tested.
- `normalizer: 'requested'` on a shipped transformation → the property
  didn't move but the prediction did — the perturbation had an effect the
  property doesn't capture; check the leakage panel.
- `achievedDelta` far from `requestedDelta` → small property values +
  rounding; the impact is still correct (that's the point), but sweeps
  will be steppy.
- comparing impacts across concepts → same-units comparison is exact for
  relative-mode concepts; BridgeTrend (absolute, edges/step) is in its own
  units — flagged as open research decision #2 in doc 03.

---

## 17. The design rules, v0.2

The five v0.1 rules (model-agnostic; anchors; determinism; never mutate;
document delta + leakage) stand. Three earned promotions:

6. **Normalize by what happened, not what was requested.** Discrete
   domains break the requested≡achieved identity; measuring restores it.
7. **Every concept must be measurable.** A transformation without a
   `propertyValue` still runs, but its impacts carry a visible warning
   label. Mechanism and measurement share one definition (the metric
   classes), or the achieved delta lies.
8. **Quantify leakage; never merely acknowledge it.** The leakage panel is
   part of the explanation's provenance, not an appendix.

And one meta-rule this round demonstrated twice: **known-truth harnesses
outrank code review.** Both v0.2 bugs (below) passed human reading and
direction-tests; both fell to a hand-derivable expected value.

---

## 18. The two bug stories

**The rounding bias (found by derivation, confirmed by experiment).**
v0.1's `±10.0` sanity value was *asserted and passing* — and subtly wrong
as a sensitivity: the true derivative of `pred = width` is the width
itself (8, or 6 in the demo world), and the 10 was `6 × (1/6)/(1/10)` —
truth × rounding artifact. Lesson: a passing exact-value test proves
*reproducibility*, not *meaning*; the meaning came from asking "what
quantity should this number be an estimate of?"

**The tied hub (found by the faithfulness harness).** The redistribute
branch rewired 10 edges and changed nothing — because Freeman
centralization is `(n·d_max − 2m)/((n−1)(n−2))` and d_max belonged to a
tie. No direction-test caught it (tests happened to use graphs with unique
hubs post-concentration); the analytic expectation `impact ≈ c₀` caught it
instantly as a measured `0.000`. Error: 49% → 0.85% after the fix. Lesson:
test against *values* derived from theory, not just *directions* derived
from intuition.

---

## 19. Exercises

1. **Feel the invariance.** Run `python evaluation.py`, look at table 4.
   Then set `normalization="requested"` as the default in your head and
   re-read the same table: which impact would you have reported at
   δ=0.3, and how wrong is it?
2. **Trip the fallback.** Write a `NoOpTransformation` whose
   `transformGraph` returns `graph.copy()` and that has no
   `propertyValue`. Run `explainDetailed` — find the `normalizer` and
   `noop` fields doing their jobs.
3. **Recreate the tied-hub bug.** In the redistribute branch, move the
   `top = max(...)` line back above the `while` loop. Run the tests: which
   one fails, and on which snapshot indices?
4. **Extend the panel.** Add `CohesionMetric` to demo 2's leakage panel
   and explain (in one sentence per row) why each cohesion change is or
   isn't "leakage" in the problematic sense.
5. **A sixth concept, full protocol.** Implement
   `AssortativityTransformation` (rewire toward/away from
   degree-assortative mixing) with `propertyValue` =
   `nx.degree_assortativity_coefficient` (careful: it can be 0 — pick your
   `deltaMode` and justify it). Then write its known-truth test *first*.
6. **The real next step.** Fit `sklearn.linear_model.LinearRegression` on
   `[bridgeWidth, centralization]` features across scenario worlds, wrap it
   in a 5-line `TemporalGraphModel`, and check TGAP recovers its learned
   coefficients — the bridge from transparent to opaque models, using only
   the contract from §3.

---

*State of the prototype: 55/55 tests green; faithfulness error ≤0.85%
against analytic ground truth; every claim in this document is enforced by
a test or reproduced by `evaluation.py`. The open research decisions —
churn's reference point, trend units, multi-community bridges — are logged
in [doc 03 §7](03-TGAP-technical-audit.md), waiting on science, not code.*
