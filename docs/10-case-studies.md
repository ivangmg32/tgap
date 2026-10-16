# TGAP Case Studies: Decentraland and Email-Eu-core

> Every number here was measured by running the code. Reproduce with:
> ```bash
> python -m realdata.run_real_data
> python -m realdata.run_ncommunity
> python -m realdata.run_tgn
> python -m realdata.make_publication
> ```
>
> **Scope.** Real data has no ground truth, so nothing here validates
> TGAP's correctness — that comes from the synthetic known-truth
> experiments. These case studies show the method applied to messy real
> structure, and every result is a **model sensitivity to a controlled
> counterfactual**, never a causal claim about voters or employees.

---

## Why these two

They are chosen to be maximally different, so a result that appears in both
is unlikely to be an artefact of either.

| | Decentraland | Email-Eu-core |
|---|---|---|
| Domain | blockchain DAO governance | a European research institute |
| Edges are | **derived** (one-mode projection) | **observed** (A emailed B) |
| Communities from | an algorithm, early period only | **real department labels** |
| Node meaning | voter wallet address | a person |
| Period | 2021-05 → 2023-04 | 804 days |

Decentraland is the harder, more realistic case: its edges do not exist in
the data and must be constructed. Email-Eu-core is the **control**: its
communities are real organisational units, so bridge width literally counts
emails between two real departments.

---

## Case study 1 — Decentraland DAO

### Construction

```
   voter ──votes on──> proposal          raw data (bipartite)
                 ↓
   voter ────────────  voter             one-mode projection
        "both voted on the same proposal in this month"
```

> ⚠️ **A projected edge is not a social relationship.** It means two people
> voted on the same proposal in the same month. They may never have
> communicated. Every statement below is about co-voting structure, not
> about acquaintance, influence or trust.

The projection is necessary, not cosmetic: in the raw bipartite graph every
edge crosses between voters and proposals, so "bridge width" would equal the
edge count and become a duplicate of density — the concept would carry no
information at all.

### What was used

| | raw | retained | % |
|---|---|---|---|
| voters | 4,133 | 100 | 2.42% |
| votes | 53,533 | 4,996 | 9.33% |

19 monthly snapshots. Communities **50 / 50**, detected by greedy modularity
on the **selection period only** (2021-05-24 → 2021-10-12) and then frozen;
TGAP explains 2021-10-12 → 2023-04-30. The two periods are disjoint, so no
future voting behaviour could influence who was selected or how the blocs
were drawn.

### What the data does

Bridge width between the two voting blocs falls from **234 to 36**, with a
range of 36–493 across the period. The DAO's co-voting structure fragments:
by the end, far fewer pairs of voters from opposite blocs are turning up on
the same proposal.

That is a description of the measured co-voting graph. It is **not** a claim
that the DAO polarised, became less effective, or that anything caused
anything.

### What TGAP says about the model

For the trend-of-bridge-width model, at +10%:

| concept | impact |
|---|---|
| **Bridge Width** | **+14.44** |
| Centralization | 0.0000 |
| Density | 0.0000 |
| Churn | 0.0000 |
| Bridge Trend | *excluded — saturated* |

The zeros are exact, not small. This model reads bridge width, and the other
three concepts are constructed to leave bridge width untouched — so a zero
here is the confounder control working, verified rather than assumed.

Largest response across all models: `persistence_bridge_width` + Bridge
Width increase, **+40.15**.

### Honesty

**144 of 180 perturbations are valid.** Excluded: 18 `edge_count_infeasible`
(the intra-community pool could not pay for the new bridge edges) and 18
`saturated` (the trend recursion hit the width-1 floor). Bridge Trend is
therefore **not quotable** on this dataset — and that is why the table above
marks it excluded rather than printing a number.

---

## Case study 2 — Email-Eu-core

### Why it is the control

SNAP publishes the real department of all 1,005 people — **42 departments**.
So the communities are not an algorithm's opinion. At N = 2 we take the two
largest (department 4 with 109 people, department 14 with 92), and bridge
width counts **actual emails between two actual departments**.

This also makes the dataset immune to the leakage question in a way no other
is: which department you belong to is a fact about you, not a statistic
computed from the email stream.

### What was used

| | raw | retained | % |
|---|---|---|---|
| people | 986 | 201 | 20.39% |
| emails | 332,334 | 12,599 | 3.79% |

12 snapshots of 40 days. Selection period 0–160.8 d, evaluation
160.8–803.9 d.

### What TGAP says

Trend-of-bridge-width model, +10%:

| concept | impact |
|---|---|
| **Bridge Width** | **+45.93** |
| Bridge Trend | +1.13 |
| Centralization | 0.0000 |
| Density | 0.0000 |
| Churn | 0.0000 |

**138 of 180 valid**; excluded: 30 `edge_count_infeasible`, 12 `saturated`.

Cross-department email falls from **82 to 11** over the evaluated period.

### The finding that only this dataset could produce

Real departments are **not** dense email clusters.

```
   edges within departments : 294
   edges between departments: 319      ->  52.0% of email crosses a boundary
   modularity of the real partition: -0.021   (NEGATIVE)
```

A negative modularity means the real organisational partition is *worse than
a random one* at explaining the email graph. People at this institute email
across departments slightly more than within them.

This is not a defect of the method — it is a property of the organisation,
and it has a concrete methodological consequence. TGAP's bridge-width
transformation pays for each new cross-department edge by deleting an
intra-department one. When the cross pool already exceeds the intra pool,
that payment becomes impossible, which is exactly the
`edge_count_infeasible` exclusion above. **The organisation's structure, not
a bug, is what makes 30 of its perturbations invalid.**

### N communities: a question two communities cannot ask

With real departments we can go beyond a single bridge. Measured bridge
matrix at N = 4 (last snapshot, real departments):

```
                dept4  dept14  dept1  dept21
    dept4          -      11     11      9
    dept14        11       -     10      9
    dept1         11      10      -      7
    dept21         9       9      7      -
```

And the explanation stays selective as N grows. A model reading one
department pair responds to that pair and is **exactly zero** on every
other:

| N | pairs | own-pair rows (non-zero) | other-pair rows (**exactly zero**) |
|---|---|---|---|
| 2 | 1 | 2 / 2 | 0 |
| 3 | 3 | 6 / 6 | **12 / 12** |
| 4 | 6 | 12 / 12 | **60 / 60** |

This is the N-community form of concept selectivity, on real organisational
data. The two-community formulation cannot even express the question
*"which department pair does this model care about?"*

**But note the cost of merging.** The data supports ~42–51 natural
communities; forcing it into 4 discards **0.39** of the available modularity.
Reporting 4 departments is a deliberate simplification, and the number
discarded is recorded in every run rather than hidden.

---

## Explaining a learned model

A TGN (PyTorch Geometric) was trained on Email-Eu-core by self-supervised
link prediction and explained through TGAP's ordinary interface — TGAP sees
only `predict(temporalGraph)`, never gradients, memory or attention.

```
  training : 5 epochs, loss 1.3819 → 1.2864
  baseline : 0.4515   (mean predicted probability of the present edges)
  budget   : 11 model calls per delta = 1 + 2×5, exactly as documented
```

| concept | achieved Δ | impact |
|---|---|---|
| **Density** | 0.1012 | **+0.0217** |
| Churn | 0.0067 | +0.0140 |
| Centralization | 1.5002 | +0.0028 |
| **Bridge Width** | 0.1006 | **−0.0029** |
| Bridge Trend | 5.8322 | +0.0008 |

This is the result that most justifies including a learned model. Every
metric-based model in this project responds to the concept it is *defined*
in terms of, so a sceptic can object that TGAP only ever recovered
definitions. Here nobody knew the answer in advance — and the TGN turns out
to depend most on **density**, while responding **negatively and weakly** to
bridge width.

> **Scope.** The TGN is trained briefly and is not tuned for benchmark
> performance. The claim is that TGAP explains a genuinely learned temporal
> graph model, not that this model is competitive.

---

## What both case studies share

1. **Bridge width dominates** for bridge-reading models, and the other
   concepts return **exact** zeros — the confounder control, verified on
   real data twice.
2. **Both lose roughly 20–25% of their perturbations** to validity gates
   (144/180 and 138/180). Those are reported, not hidden, and the excluded
   rows carry their numeric fields empty so they cannot be used by accident.
3. **Bridge Trend is unusable on both** — saturated. No trend magnitude from
   either dataset should appear in a paper.
4. **Leakage-safe selection costs a lot**: 2.4% and 20.4% of actors
   retained. Results describe an early-selected cohort, not the whole
   ecosystem.

## What they cannot show

- Nothing about causation in either organisation.
- Nothing about correctness of TGAP — only applicability.
- Decentraland's edges are **constructed**; a different projection or window
  would give a different graph.
- Both run on a single seed (42) and a single preprocessing configuration.
