# TGAP by Example — One Tiny Graph, Traced Through Every Line of Code

> **Purpose:** explain TGAP to someone (your professor) by following ONE
> small example from the first line of code to the final answer.
> **Promise:** every number in this document was produced by actually
> running the code. Nothing is invented. You can re-run it yourself.
> **Style:** very simple language. Small graph you can draw by hand.
> Every step says *which file*, *which function*, and *what happened*.

---

## Table of contents

1. [The idea in one picture](#1-the-idea-in-one-picture)
2. [Our tiny world](#2-our-tiny-world)
3. [The cast: who does what](#3-the-cast-who-does-what)
4. [The model we will explain](#4-the-model-we-will-explain)
5. [The run, step by step](#5-the-run-step-by-step)
6. [The real call trace](#6-the-real-call-trace)
7. [The final answer, and how to read it](#7-the-final-answer)
8. [Why "achieved" and not "requested" — shown with our numbers](#8-why-achieved-not-requested)
9. [The honest "nothing happened" case](#9-the-honest-nothing-happened-case)
10. [Act two: a concept that lives in TIME](#10-act-two-a-concept-that-lives-in-time)
11. [The leakage panel: proving we changed only one thing](#11-the-leakage-panel)
12. [Summary table for your professor](#12-summary-table-for-your-professor)
13. [How to present this in 5 minutes](#13-how-to-present-this-in-5-minutes)
14. [Run it yourself](#14-run-it-yourself)

---

## 1. The idea in one picture

We have a computer model. It looks at a network of people/projects and
outputs a number (a risk score, a health score, a forecast). We want to
know **why** it gave that number.

TGAP's answer is a simple experiment, repeated a few times:

```
   ORIGINAL NETWORK  ──►  model  ──►  5.0     ("the baseline")
           │
           │  change ONE human-meaningful thing
           │  (e.g. "make the bridge between the two groups wider")
           ▼
   CHANGED NETWORK   ──►  model  ──►  6.0
           │
           ▼
   The model moved by +1.0 when we widened the bridge.
   Divide by how much we widened it  →  THE EXPLANATION.
```

That is all. Do it for "wider bridge", "narrower bridge", "more
centralized", "less centralized", and you have a small table that a human
can read.

**Important scientific wording** (your professor will care): this measures
**how sensitive the MODEL is** to a change we made on purpose. It does
**not** prove anything causal about the real world. Say "model
sensitivity" or "counterfactual response", never "this causes that".

---

## 2. Our tiny world

Real experiments use graphs with hundreds of nodes. For teaching we use
**8 nodes**, so you can check every step with a pencil.

Two communities (think: two organizations, two open-source teams):

```
     community A                        community B

     0 ────── 1                         4 ────── 5
     │        │                         │        │
     │        │                         │        │
     3 ────── 2                         7 ────── 6

   the BRIDGE between them = 5 ties:
        0 ── 4
        0 ── 5
        1 ── 5
        2 ── 6
        3 ── 7
```

- **Community A** = nodes {0, 1, 2, 3}, connected in a little square.
- **Community B** = nodes {4, 5, 6, 7}, also a square.
- **The bridge** = the 5 edges that go from one side to the other.
- **Total edges** = 4 (inside A) + 4 (inside B) + 5 (bridge) = **13**.

### Why "bridge width" is the star concept

This comes from the CATALYST project's main hypothesis. If two communities
are joined by only **one** tie, that tie is a single point of failure —
one person quits and the two groups are disconnected. If they are joined
by **many** ties (a "wide bridge"), the connection survives. So
"how wide is the bridge" is the number the whole project cares about.

Here the width is **5**.

### It is a TEMPORAL graph (a little movie)

A temporal graph is just **a list of snapshots**, oldest first:

```
   temporalGraph = [ snapshot0 , snapshot1 , snapshot2 ]
                      (Jan)       (Feb)       (Mar)
```

Our three snapshots all have **13 edges and bridge width 5**. Only small
things inside the communities change (people switch collaborators):

| snapshot | inside A | inside B | bridge | width |
|---|---|---|---|---|
| 0 | (0,1)(0,3)(1,2)(2,3) | (4,5)(4,7)(5,6)(6,7) | (0,4)(0,5)(1,5)(2,6)(3,7) | **5** |
| 1 | (0,1)(1,2)(1,3)(2,3) | (4,5)(4,7)(5,6)(6,7) | same | **5** |
| 2 | (0,1)(0,3)(1,2)(2,3) | (4,5)(4,6)(5,6)(6,7) | same | **5** |

(In snapshot 1 the tie 0–3 became 1–3; in snapshot 2 the tie 4–7 became
4–6. That is normal turnover.)

---

## 3. The cast: who does what

Think of the code as five workers with one job each. All of them live in
[tgap/core/](../tgap/core/).

| Worker | File | Its one job |
|---|---|---|
| **The Model** | `TemporalGraphModel.py` | Look at the snapshots → output ONE number |
| **The Metric** | `GraphMetric.py` | Look at ONE snapshot → output ONE number (e.g. count the bridge) |
| **The Transformation** | `Transformations.py` | Change one concept by a given amount → return a NEW graph |
| **The Explainer** | `GraphExplainer.py` + `TemporalGraphExplainer.py` | Run the experiment: baseline → change → measure → divide |
| **The Helpers** | `Communities.py` | Answer "which edges cross between the two groups?" |

They only talk through very small agreements ("interfaces"):

```
   model.predict(temporalGraph)   -> a float
   metric.measure(graph)          -> a float
   transformation.transform(tg, delta) -> a new temporal graph
   transformation.propertyValue(tg)    -> a float  (how big is the concept now?)
```

**Why this matters for your professor:** because the explainer only ever
calls `predict`, it never needs to know *what kind* of model it is. Today
it is a 3-line rule. Tomorrow it can be a deep Temporal Graph Network.
**Not one line of the explainer changes.** That is what "model-agnostic"
means, and it is the main architectural claim.

---

## 4. The model we will explain

To teach, we pick a model whose behaviour we **already know perfectly** —
so we can check whether TGAP tells the truth.

```python
metric = BridgeWidthMetric(COMM)               # counts the bridge edges
model  = PersistenceTemporalModel(metric)      # "tomorrow = today"
```

`PersistenceTemporalModel.predict` is literally this
([TemporalGraphModel.py](../tgap/core/TemporalGraphModel.py)):

```python
    def predict(self, temporalGraph):
        return self.metric.measure(temporalGraph[-1])
```

`temporalGraph[-1]` means **the last snapshot**. So:

> **prediction = the bridge width of the most recent snapshot.**

Running it gives:

```
prediction on the original temporal graph = 5.0
```

Which is right: the bridge in snapshot 2 has 5 edges.

Because the model *is* the bridge width, we can predict the correct
explanation with mathematics before running TGAP:
**if the bridge grows by 1, the prediction must grow by exactly 1.**
Keep that in mind — in step 5 we check whether TGAP agrees.

---

## 5. The run, step by step

The user writes three lines:

```python
explainer = TgapExplainer(model, [BridgeWidthTransformation(COMM),
                                  CentralizationTransformation(COMM)])
result = explainer.explain(TG)
```

Now follow what the computer actually does.

### STEP 1 — `explain` is only a wrapper

File [GraphExplainer.py](../tgap/core/GraphExplainer.py):

```python
    def explain(self, x):
        return {r["label"]: r["impact"] for r in self.explainDetailed(x)}
```

It calls the real worker, `explainDetailed`, and keeps only two fields
from each result: the name and the number. (The detailed version keeps
everything — we look at it in step 7.)

### STEP 2 — get the list of concepts to test

```python
        transformations = self._resolveTransformations(x)
```

We passed our two transformations, so it just returns them. (If you pass
nothing, this function *detects* the two communities from your graph and
builds safe defaults — see doc 04 §7.3.)

### STEP 3 — the baseline: ask the model once

```python
        baseline = self.model.predict(x)      # ← model call #1
```

→ **baseline = 5.0**

Chain of calls: `GraphExplainer.explainDetailed` → `TemporalGraphModel.predict`
→ `GraphMetric.measure` → `Communities.interCommunityEdges` → counts 5 edges.

### STEP 4 — measure the concept BEFORE changing it

```python
            p0 = trans.propertyValue(x)
```

File [Transformations.py](../tgap/core/Transformations.py), inside
`BridgeWidthTransformation.propertyValue`: it walks the snapshots, counts
the bridge in each, and returns the **average**:

```
widths = [5, 5, 5]   →   p0 = 5.0
```

> **This is new in version 0.2 and it is the key idea of the whole review.**
> We are about to ask for "+10%". We must find out *how much we actually
> got*, because a graph cannot change by 10% — it changes by whole edges.

### STEP 5 — make the change (+10%)

```python
                xT = self._applyTransformation(x, trans, delta)   # delta = +0.1
```

`TgapExplainer._applyTransformation` → `TemporalGraphTransformation.transform`
→ loops over the 3 snapshots → `BridgeWidthTransformation.transformGraph`
for each one:

```python
        width  = len(interCommunityEdges(graph, communities))   # 5
        target = round(width * (1 + delta))                     # round(5.5) = 6
        return setBridgeWidth(graph, communities, target, rng)
```

So the goal is: **make the bridge 6 edges wide.**

`setBridgeWidth` does the surgery, and here is the important rule:

```
  add 1 new bridge edge        ... and PAY for it by
  removing 1 edge inside a community
```

Real result on the last snapshot:

```
   bridge BEFORE: (0,4) (0,5) (1,5) (2,6) (3,7)          = 5 edges
   bridge AFTER : (0,4) (0,5) (1,5) (2,6) (3,6) (3,7)    = 6 edges   ← +1 (3,6) added
   inside A BEFORE: (0,1) (0,3) (1,2) (2,3)              = 4 edges
   inside A AFTER : (0,1) (1,2) (2,3)                    = 3 edges   ← -1 (0,3) removed
   TOTAL EDGES: 13 -> 13    ✓ unchanged
```

**Why pay?** This is the "anchor rule", copied from TSAP. If we simply
added an edge, the network would have *more activity overall*, and the
model might react to that instead of to the bridge. By keeping the edge
count at 13, the network has the same amount of activity — only **routed
differently**. So any reaction is about *routing*, which is exactly the
question "does the bridge matter?".

### STEP 6 — ask the model again

```python
                transformed = self.model.predict(xT)     # ← model call #2
```

→ **transformed = 6.0** (the last snapshot's bridge now has 6 edges).

```
                numerator = transformed - baseline       # 6.0 - 5.0 = +1.0
```

### STEP 7 — measure the concept AFTER, and divide

```python
                    pT = trans.propertyValue(xT)                 # 6.0
                    achievedDelta = (pT - p0) / abs(p0)          # (6-5)/5 = 0.2
                    ...
                    impact = numerator / abs(achievedDelta)      # 1.0 / 0.2
```

→ **impact = +5.0**

**Check it by hand.** We asked for +10%. We actually got
5 → 6 = **+20%**. The prediction moved +1. So the sensitivity is
1 ÷ 0.2 = **5**. And 5 is exactly the current bridge width — which is the
mathematically correct answer, because our model *is* the bridge width.
**TGAP recovered the truth.**

### STEP 8 — do the same in the other direction, and for the other concept

The loop repeats with `delta = −0.1`:
`round(5 × 0.9) = round(4.5) = 4` → remove 1 bridge edge, add 1 edge inside
→ prediction 4.0 → numerator −1.0 → achieved −0.2 → **impact = −5.0**.

Then the whole thing runs again for `CentralizationTransformation`
(2 more model calls). Result: **0.0 and 0.0** — because centralization
rewiring never changes the bridge, and our model only looks at the bridge.
More about this in §9 and §11.

---

## 6. The real call trace

This is not from memory — it was captured by attaching Python's tracer to
one `explain()` call (one transformation, to keep it short). Read it top to
bottom; indentation is flattened, `x3` means "three times in a row":

```
GraphExplainer.py                explain                  ← user calls this
GraphExplainer.py                explainDetailed          ← the real worker
GraphExplainer.py                _resolveTransformations  ← "which concepts?"

TemporalGraphModel.py            predict                  ← MODEL CALL 1 (baseline)
GraphMetric.py                   measure
Communities.py                   interCommunityEdges

Transformations.py               propertyValue            ← concept BEFORE
Transformations.py               _snapshots
Communities.py                   interCommunityEdges   x3   (once per snapshot)

TemporalGraphExplainer.py        _applyTransformation     ← make the +10% change
TemporalGraphTransformation.py   transform
Transformations.py               transformGraph             snapshot 0
Communities.py                   interCommunityEdges
Transformations.py               setBridgeWidth
Communities.py                   interCommunityEdges
Communities.py                   intraCommunityEdges        ← finding the edge to "pay" with
Transformations.py               _safeToRemove              ← don't break the graph
Transformations.py               transformGraph             snapshot 1
        ... (same 5 calls) ...
Transformations.py               transformGraph             snapshot 2
        ... (same 5 calls) ...

TemporalGraphModel.py            predict                  ← MODEL CALL 2 (+10% world)
GraphMetric.py                   measure
Communities.py                   interCommunityEdges

Transformations.py               propertyValue            ← concept AFTER
Communities.py                   interCommunityEdges   x3

TemporalGraphExplainer.py        _applyTransformation     ← now the -10% change
        ... same shape ...
TemporalGraphModel.py            predict                  ← MODEL CALL 3 (-10% world)
Transformations.py               propertyValue
```

Three things your professor will notice immediately:

1. **The model was called exactly 3 times** for 1 concept =
   `1 + 2×1`. With our 2 concepts it is `1 + 2×2 = 5` — and we verified it
   by counting: `model calls for 2 transformations = 5`. This is the
   efficiency claim, *measured*, not asserted. (SHAP would need thousands.)
2. **`propertyValue` never calls the model.** It only counts edges. So
   measuring the achieved change is free in model-call terms.
3. **A small difference between the two directions.** Widening calls
   `intraCommunityEdges` and `_safeToRemove` (it must find an internal
   edge to remove as payment). Narrowing does not — it removes a bridge
   edge and builds its "pay-back" candidate list inline. Same rule, two
   code paths.

---

## 7. The final answer

```
   Increase Bridge Width (10.0%)        -> +5.0000
   Decrease Bridge Width (10.0%)        -> -5.0000
   Increase Centralization (10.0%)      -> +0.0000
   Decrease Centralization (10.0%)      -> +0.0000
```

**In plain words:** *"This model cares only about the width of the bridge.
Widening it pushes the prediction up, narrowing pushes it down, by the
same amount. How centralized the network is makes no difference at all."*

Which is exactly correct — the model is `prediction = bridge width`.

If you want the full story behind any row, call `explainDetailed` instead.
Here is the real record for the first row:

```
   Increase Bridge Width (10.0%)
        requestedDelta   = 0.1        ← what we asked for
        achievedDelta    = 0.2        ← what we actually got (5 → 6 edges)
        deltaMode        = relative
        baseline         = 5.0        ← model before
        transformed      = 6.0        ← model after
        impact           = 5.0        ← (6.0 - 5.0) / 0.2
        normalizer       = achieved   ← which denominator was used
        noop             = False      ← something really did change
```

Nothing is hidden. Every number that produced the impact is kept.

---

## 8. Why "achieved", not "requested"

This is the most important scientific point of the version-0.2 review, and
our tiny example shows it in one line.

TSAP (the time-series original) divides by the **requested** delta:

```
impact = (new prediction − old prediction) / 0.1
```

That is correct for time series, because if you multiply a curve by 1.1,
the volatility really does change by exactly 10%. **Requested = actual.**

But a graph cannot change by 10%. It changes by **whole edges**:

```
   we asked for : 5 × 1.1 = 5.5 bridges     (impossible)
   we got       : round(5.5) = 6 bridges    → a change of 1/5 = 20%
```

So what should we divide by?

| | formula | result | correct? |
|---|---|---|---|
| requested | 1.0 ÷ **0.1** | **10.0** | ✗ inflated by the rounding |
| achieved | 1.0 ÷ **0.2** | **5.0** | ✓ equals the true answer |

The true answer must be **5**, because the model is the width, so "how
much does the prediction move per relative unit of width" = the width = 5.

Both modes still exist in the code, and our example ran both:

```
achieved   mode:  +5.0000 / -5.0000     ← the default now
requested  mode:  +10.0000 / -10.0000   ← TSAP's literal formula
```

**How to say this to your professor in one sentence:**

> *"Because graphs are discrete, we cannot change a property by exactly
> the requested amount, so we measure the change we actually achieved and
> normalise by that. In the continuous limit this is identical to TSAP —
> it is the faithful port of TSAP's formula to a discrete domain, not a
> departure from it."*

(For the mathematically inclined: with relative normalisation the impact
is a finite-difference estimate of ∂f/∂ln p — a semi-elasticity.)

---

## 9. The honest "nothing happened" case

Look again at the last detailed record from our run:

```
   Decrease Centralization (10.0%)
        achievedDelta    = 0.0
        impact           = 0.0
        normalizer       = requested
        noop             = True        ← ★
```

**Why?** Centralization is measured by the Freeman formula, which (when
the number of edges is kept fixed) simplifies to:

```
         n · d_max − 2m                 8 · 4 − 26      6
   C =  ─────────────────      =       ───────────  =  ──  = 0.1429
         (n−1)(n−2)                        7 · 6       42
```

where `d_max` is the **highest degree in the graph**. Our snapshot's
degrees are `[4, 4, 4, 3, 3, 3, 3, 2]` — **three nodes tie at 4**.

The transformation was allowed to move only
`k = round(0.1 × 13) = 1` edge. Taking one edge from one of the three
top nodes still leaves two others at degree 4, so `d_max` stays 4, so **C
does not move at all**.

So TGAP reports `noop = True`: *"we tried, but on this tiny graph a 10%
nudge was too small to change anything — so this row is not evidence about
the model."* That is very different from saying "the model does not care".

> **Teaching point for the professor:** most explainability tools would
> silently print a 0 here, which a reader would interpret as "the model
> ignores centralization". TGAP distinguishes **"we tested and the model
> did not react"** from **"we never managed to test"**. That distinction is
> a correctness feature, and it was added because the review demanded that
> no scientific assumption be made silently.

(The other direction, *Increase* Centralization, did work: it pushed one
node from degree 4 to 5, so `C = (8·5 − 26)/42 = 14/42 = 0.3333`, an
achieved change of (0.3333−0.1429)/0.1429 = **+1.33**, i.e. +133%. Its
impact is still 0.0 — but for the *right* reason: the model genuinely does
not look at centralization.)

---

## 10. Act two: a concept that lives in TIME

Everything above changes the *structure*. But CATALYST's real worry is
**bridge decay** — bridges getting thinner over time, *before* they break.
So TGAP also has concepts that change the **trajectory**.

New world: same 8 nodes, but the bridge is dying.

```
   snapshot:   0     1     2
   width:      5     4     3          ← losing one tie per step
```

The straight-line slope through `[5, 4, 3]` is **−1.0 per step**.

`BridgeTrendTransformation` re-shapes that history. It is a **direct copy
of TSAP's `transformTrendReverse`**, applied to the width series:

```python
        target = [float(w) for w in widths]
        i = len(target) - 2
        while i >= 0:
            origChange = widths[i] - widths[i + 1]
            target[i] = (target[i + 1] + origChange) / (1 + delta)
            i = i - 1
```

Do it by hand for `delta = +0.1`, walking **backwards**:

| step | calculation | target | rounded |
|---|---|---|---|
| snapshot 2 (last) | **untouched — the anchor** | 3 | **3** |
| snapshot 1 | (3 + 1) ÷ 1.1 = 3.636 | 3.636 | **4** |
| snapshot 0 | (3.636 + 1) ÷ 1.1 = 4.215 | 4.215 | **4** |

Predicted new history: `[4, 4, 3]`. And the code produced:

```
  delta=+0.1: widths -> [4, 4, 3], slope -> -0.5000, last snapshot identical: True
  delta=-0.1: widths -> [6, 4, 3], slope -> -1.5000, last snapshot identical: True
```

✓ Exactly our hand calculation. The decay became **less steep**
(−1.0 → −0.5) for `+0.1`, and **more steep** (−1.0 → −1.5) for `−0.1`.

### The anchor rule, now in time

Notice `last snapshot identical: True`. The present is **never touched** —
only the history is re-shaped. This is TSAP's "keep the last value fixed",
translated to time. And it gives us a beautiful test.

Take two models that differ *only* in what they read:

```python
SlopeModel(BridgeWidthMetric)          # reads the TRAJECTORY (the slope)
PersistenceTemporalModel(...)          # reads only the PRESENT (last snapshot)
```

Explain both, with the same transformation:

```
explanation (SlopeModel):
   Increase Bridge Trend (10.0%)        -> +1.0000
   Decrease Bridge Trend (10.0%)        -> -1.0000

explanation (PersistenceModel - reads only the present):
   Increase Bridge Trend (10.0%)        -> +0.0000
   Decrease Bridge Trend (10.0%)        -> +0.0000
```

Two things are proven here at once:

1. **The trajectory model reacts, correctly and exactly.** Its prediction
   *is* the slope, so the impact must be exactly ±1.0 — and it is.
   (Check: slope went −1.0 → −0.5, a change of +0.5; prediction moved
   +0.5; 0.5 ÷ 0.5 = 1.0.)
2. **The present-only model is exactly blind.** It cannot react to a
   change in history, because we never touched the present. `0.0000`,
   not "approximately zero".

> **This is the single best slide for your professor.** Same graph, same
> transformation, same explainer — and TGAP correctly tells apart a model
> that reasons about *trends* from a model that reasons about *levels*.
> That is the whole promise of an explainability method, demonstrated on a
> case where the right answer is known in advance.

---

## 11. The leakage panel

An obvious objection: *"when you add a bridge edge and delete an internal
edge, you changed more than one thing. How do you know the model reacted
to the bridge?"*

Good objection. So we **measure** it. `leakageReport` applies the
transformation and then measures a whole panel of properties before/after
(file [Diagnostics.py](../tgap/core/Diagnostics.py)). Real output for our
tiny world, `Increase Bridge Width (10%)`:

```
metric                       before      after      change
*bridge width                5.0000     6.0000     +1.0000     ← intended
 centralization              0.1429     0.2063     +0.0635     ← side effect
 density                     0.4643     0.4643     +0.0000     ← perfectly held
 clustering                  0.2361     0.4778     +0.2417     ← side effect
```

How to read it:

- The `*` row is **what we meant to change**: +1 bridge edge. ✓
- **density +0.0000** — proof the anchor rule worked. We did not sneak in
  extra edges; the network has exactly the same amount of activity.
- centralization and clustering moved a little. That is **honest,
  unavoidable leakage**: moving any edge changes who is connected to whom.
  We report it instead of hiding it.
- On this 8-node toy the leakage looks big (clustering +0.24) simply
  because one edge is a large fraction of 13 edges. On realistic graphs
  (2×15 nodes, 100 edges) the same measurement gives centralization
  +0.006 and clustering −0.007 — *tiny* next to the intended +1.0.

> **What to say:** *"We do not claim the transformations are perfectly
> independent — that is impossible in a graph. We claim they are
> **measured**, so a reader can judge whether the intended change dominates
> the side effects."*

---

## 12. Summary table for your professor

| Question | Answer from our example |
|---|---|
| What is the input? | A temporal graph = a list of snapshots. Ours: 3 snapshots, 8 nodes, 13 edges, bridge width 5 |
| What is the model? | Anything with `predict(temporalGraph) → float`. Ours: prediction = bridge width of the last snapshot |
| What is a "concept"? | A human-named property + a rule for changing it. Ours: Bridge Width, Centralization, Bridge Trend |
| What does the explainer do? | baseline → perturb → predict again → divide by the achieved change |
| How many model calls? | Exactly `1 + 2×concepts`. Measured: **5** for 2 concepts |
| What is the output? | One number per concept per direction: `+5.0, −5.0, 0.0, 0.0` |
| Is it correct? | Yes — the model *is* the bridge width, so the true sensitivity is 5, and TGAP returned 5 |
| How do you know it is not luck? | 55 automated tests + an evaluation suite where the right answer is derived by mathematics first (error 0.00–0.85%) |
| Does it prove causality? | **No.** It measures *model sensitivity to a controlled counterfactual*. Nothing more |
| What is the link to TSAP? | Same method, same function names. `transformTrendReverse` → `BridgeTrendTransformation`, volatility → churn, "keep last value fixed" → "keep last snapshot fixed" |
| What is still missing? | Real data (FOSS/DeFi), a learned model (TGN), multi-community graphs. See [doc 03 §7](03-TGAP-technical-audit.md) |

---

## 13. How to present this in 5 minutes

A slide order that works:

1. **The problem.** "A model says this ecosystem is at risk. Why? We need
   an answer a community leader can act on."
2. **The idea.** The picture from §1. Change one meaningful thing, see how
   much the model moves.
3. **The example.** The 8-node drawing from §2. "Bridge width is 5."
4. **One experiment.** Widen the bridge 5 → 6, pay for it by deleting one
   internal edge (so total edges stay 13). Prediction 5.0 → 6.0.
5. **The answer table.** `+5, −5, 0, 0` and the plain-English reading.
6. **The subtle bit.** §8: graphs are discrete, so normalise by the change
   you *achieved*, not the one you *requested* — otherwise you report 10
   where the truth is 5.
7. **The proof slide.** §10: the trend model reacts ±1.0, the
   present-only model reacts exactly 0.0. Same graph, same transformation.
8. **Honesty slide.** §11 leakage panel + the "model sensitivity, not
   causality" wording.
9. **Status.** 55 tests passing; faithfulness error under 1% against
   analytically known answers; next step = wrap a learned model.

Likely questions, and short answers:

- *"Why not use SHAP?"* → SHAP explains *individual features* (this node,
  this edge). We explain *human concepts* (bridge width, trend). Also SHAP
  needs thousands of model calls; we need 5.
- *"Why not GNNExplainer?"* → It finds which edges mattered. It cannot
  answer "does the model care about bridge width as a concept?", and it
  needs access to the model's internals. We only need `predict`.
- *"Isn't the perturbed graph unrealistic?"* → We keep the node set and
  the edge count fixed, so the counterfactual graph is the same size and
  the same activity level — only the routing changes. And we measure the
  leakage.
- *"What if the concept you defined is the wrong one?"* → Then TGAP will
  not find it. This is the honest limitation inherited from TSAP: it
  explains only the concepts you define. The answer is to define more
  concepts, with domain experts (which is CATALYST's WP4 co-design).

---

## 14. Run it yourself

Everything in this document is reproducible:

```bash
cd c:\catalyst\tgap
python examples.py --no-show          # the four built-in demos
python -m unittest discover -s tests  # 55 tests
python evaluation.py                  # faithfulness / stability / efficiency / leakage
```

To rebuild *this document's* tiny world in a Python shell:

```python
import networkx as nx
from core import (TgapExplainer, PersistenceTemporalModel,
                  BridgeWidthMetric, BridgeWidthTransformation,
                  CentralizationTransformation)

A, B = {0,1,2,3}, {4,5,6,7}
COMM = (A, B)
INTRA = [(0,1),(1,2),(2,3),(0,3),(4,5),(5,6),(6,7),(4,7)]
BRIDGE = [(0,4),(1,5),(2,6),(3,7),(0,5)]

def snapshot(extra=(), drop=()):
    g = nx.Graph(); g.add_nodes_from(range(8))
    g.add_edges_from(INTRA + BRIDGE)
    g.remove_edges_from(drop); g.add_edges_from(extra)
    return g

TG = [snapshot(),
      snapshot(extra=[(1,3)], drop=[(0,3)]),
      snapshot(extra=[(4,6)], drop=[(4,7)])]

model = PersistenceTemporalModel(BridgeWidthMetric(COMM))
ex = TgapExplainer(model, [BridgeWidthTransformation(COMM),
                           CentralizationTransformation(COMM)])

print(model.predict(TG))        # 5.0
print(ex.explain(TG))           # +5.0, -5.0, 0.0, 0.0
for r in ex.explainDetailed(TG):
    print(r)                    # full provenance
```

---

*Where to go next: [doc 01](01-TSAP-explained-simply.md) for the TSAP
background this is built on, [doc 04](04-TGAP-v02-walkthrough.md) for the
line-by-line tour of the whole codebase, [doc 03](03-TGAP-technical-audit.md)
for the audit and the open research questions.*
