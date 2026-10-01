# TGAP — Status Report

> ## ⚠ SUPERSEDED — point-in-time report, retained for history
>
> This report describes the repository **as of `8ab1d6e`**. Its numbers were
> real when written and the body below is left exactly as it was; do not
> quote it as current. Four of its claims have since been superseded:
>
> | Claim in this report | Current source of truth |
> |---|---|
> | `362 tests, 360 passed` (header, §252) | **446 tests, 444 passed, 0 failed, 2 skipped** |
> | TGN `AUC 0.7709` (§3.1) | **five-seed summary: mean 0.744, sd 0.029, range [0.702, 0.773]** — `table6_tgn_seed_stability` |
> | `Churn … −1.6230` (§3.1 table) | one seed out of five. Across seeds Churn's impact has **mean 0.013, sd 2.79, range [−2.32, 4.54]** — `table9_tgn_concept_stability` |
> | "**Churn dominates by a factor of five**" (§3.1) | **Not supported.** Churn's impact changes sign between seeds. Bridge Width is the only concept with a stable sign across all five seeds. |
>
> The §3.1 concept table is also ordered by `|impact|`. That ordering is not
> a ranking: the achieved deltas are in incompatible units (Churn 0.0067
> against Bridge Trend 5.83), and `table8_tgn_not_comparable` records which
> concept pairs may be compared at all.
>
> Limitation 8, "single seed (42)", still holds for the real-data runs but
> **no longer for TGN**, which is now run over five fixed seeds.

**Repository:** `github.com/ivangmg32/tgap`, branch `real-data` @ `8ab1d6e`
**Project:** CATALYST (PID2025) — PIs Samer Hassan, Iván García-Magariño
**Test status:** 362 tests, 360 passed, 0 failed, 2 skipped (deliberate), 157 s
**Output verification:** 43 automated checks, 0 failures

> Every number in this report was produced by running the code. Nothing is
> estimated or carried over from an earlier run.

---

## 1. What TGAP is

TGAP (Temporal Graph Additive exPlanations) explains models that read
**temporal graphs**, by perturbation. It asks: *if the ecosystem's recent
history had had 10% wider bridges between communities (or more
centralization, or more churn), how would the model's prediction change?*
That change, per concept, **is** the explanation.

It is the graph counterpart of TSAP and inherits its architecture: a generic
explainer, a minimal model interface, and pluggable transformations.

**The output is a number per concept per direction** — a *sensitivity of the
model*, not a causal claim about the world.

---

## 2. Where the project stands

**Working and tested:**

- Core architecture, preserving Iván's original `core/` layout, class names
  and camelCase conventions.
- Five built-in concepts, one class per file, plus a documented public API
  for adding your own **without editing any core file**.
- **N communities** (1, 2, 3 … N), with pairwise and aggregate bridge width.
  Two-community results are provably unchanged.
- Eight real temporal datasets with leakage-safe preprocessing and validity
  gating.
- A **trained TGN** (PyTorch Geometric) explained through the same
  interface.
- Publication figures and tables, generated from the runs.

**Not done:**

- The **user study has no results.** The design is complete and
  pre-registered (`docs/09-user-study-design.md`), but no participants have
  been recruited and no data collected. Its results tables are deliberately
  empty.

---

## 3. Three outputs worth reading closely

### 3.1 The TGN explanation — `output/publication/table3_tgn.md`

This is the most scientifically significant result, because it is an
explanation of a model **whose behaviour nobody knew in advance**. Every
other model in the project is a closed-form graph metric, so a sceptic could
object that TGAP only ever recovered definitions. A trained neural network
removes that objection.

The model is a Temporal Graph Network trained on Email-Eu-core by
self-supervised link prediction, with a **temporal** train/test split —
8 training snapshots, 4 held-out snapshots strictly later.

**It demonstrably generalises** (chance = 0.5, classes balanced):

```
                  before training    after training
  AUC                   0.5118            0.7709
  average precision     0.5611            0.7315
  accuracy                   —            0.7161
```

**The explanation:**

| concept | achieved Δ | impact |
|---|---|---|
| **Churn** | 0.0067 | **−1.6230** |
| Bridge Width | 0.1006 | −0.3340 |
| Density | 0.1012 | −0.0956 |
| Centralization | 1.5002 | −0.0371 |
| Bridge Trend | 5.8322 | −0.0011 |

Every impact is negative: any perturbation lowers the model's confidence.
**Churn dominates by a factor of five** — making the past differ more from
the present hurts most, which is coherent for a model that predicts present
edges from history, but was not predictable from the model's definition.

TGAP saw only `predict(temporalGraph)` — no gradients, no memory internals,
no attention weights. A test enforces this by handing the explainer a
wrapper exposing nothing else. The documented cost held exactly: **11 model
calls per delta = 1 + 2 × 5**.

> **Important caveat for whoever reads this.** An earlier version of these
> numbers was wrong and has been retracted. See §5.

### 3.2 The validity table — `output/publication/table4_validity.md`

TGAP's central promise is *change one concept, hold everything else fixed*.
On real graphs that promise is sometimes impossible to keep, and this table
is where that is admitted rather than hidden.

| dataset | rows | valid | valid % | excluded: infeasible | excluded: saturated |
|---|---|---|---|---|---|
| sx_mathoverflow | 180 | 162 | 90.0 | 12 | 6 |
| decentraland | 180 | 144 | 80.0 | 18 | 18 |
| tgbl_enron | 180 | 144 | 80.0 | 18 | 18 |
| tgbl_wiki | 180 | 144 | 80.0 | 24 | 12 |
| bitcoin_alpha | 180 | 138 | 76.7 | 30 | 12 |
| email_eu_core | 180 | 138 | 76.7 | 30 | 12 |
| tgbl_uci | 180 | 138 | 76.7 | 24 | 18 |
| bitcoin_otc | 180 | 132 | 73.3 | 30 | 18 |

**1,440 experiments run; 1,140 (79%) usable.** Excluded rows have their
numeric fields written **empty**, so a number that failed its own invariant
cannot be used by accident.

Two exclusion causes:

- `edge_count_infeasible` — widening a bridge is paid for by deleting an
  intra-community edge, and sometimes there are not enough to delete.
- `saturated` — the bridge-trend recursion pushes old snapshots below the
  width-1 floor, destroying the intended shape.

**Consequence for the paper: Bridge Trend magnitudes are not quotable.**
Only 36 of 288 of its rows survive gating.

### 3.3 The temporal local explanation — `output/publication/fig5_temporal_local.png`

Answers *when* a concept mattered, which a single impact number cannot. Each
point is one snapshot; colour is the impact of perturbing **that snapshot
alone**.

- **Present-only model:** exactly one snapshot is coloured. Every earlier
  one is white — precisely zero. The model cannot see history, and the
  figure shows it rather than asserting it.
- **Trajectory model:** a smooth gradient across time, negative early,
  positive late.

Same data, same perturbation, two models, visibly different temporal
sensitivity.

---

## 4. Supporting results

**N communities, six datasets × N = 2, 3, 4 — 18 of 18 configurations
selective.** A model reading one community pair responds to that pair and is
**exactly zero** on all others (at N = 4: 60 of 60 cross-pair rows zero).

Raising N also recovers structure that collapsing to two discards:

| dataset | modularity N=2 → N=4 |
|---|---|
| tgbl_enron | 0.220 → **0.368** |
| bitcoin_otc | 0.216 → 0.267 |
| bitcoin_alpha | 0.196 → 0.261 |

**A finding specific to Email-Eu-core.** Its communities are *real
departments* (SNAP ships labels for 1,005 people). The real department
partition has **negative modularity (−0.021)**: 294 edges fall within
departments, 319 between them, so **52% of email crosses a boundary**. Real
departments are not dense email clusters — and that is precisely why 30 of
its perturbations are infeasible: the cross pool already exceeds the intra
pool the transformation must pay from. Organisation, not bug.

**Cross-dataset invariants, all 8 datasets:**

- Expected invariance verified **8/8** (history-only perturbations move a
  present-only model by exactly 0 — a verification of something that follows
  from the definitions, not a discovery).
- Two independent feasibility checks agreed in **240/240** settings.
- The discreteness floor predicted by the synthetic work reproduced on real
  data: **20.06%** no-op on thin-bridge datasets vs **0.00%** on thick.

---

## 5. Corrections — things that were wrong and have been fixed

Listed because a reader of earlier material may be holding retracted
numbers.

**5.1 The TGN was degenerate, and earlier TGN results are retracted.**
Adding a held-out evaluation exposed that held-out AUC was **exactly 0.500**
before and after training. Cause: TGN drives memory from per-event messages;
the adapter passed all-zero messages, and with memory also initialised to
zero every node's memory updated *identically* — a symmetry that never
broke. Memory standard deviation across nodes was measured at `0.0`. Every
embedding was identical, so every candidate link scored the same.

**Training loss fell the whole time**, which is exactly why loss alone is
not evidence of learning. Messages now carry endpoint degrees — real
structural signal. The previously reported TGN explanation (which named
Density as dominant) was an explanation of a model that could not tell two
nodes apart, and is superseded by §3.1. A regression test now fails if
memory ever becomes uniform again.

**5.2 A reproducibility defect.** `DensityTransformation` produced different
results across processes, because networkx derives non-edge pairs from set
arithmetic whose ordering depends on string hashing, which Python randomises
per run. ~30 of 1,440 rows moved between otherwise identical runs. Fixed;
three independent runs now produce byte-identical results.

**5.3 Tests corrupted committed results.** The test suite wrote into the
real `output/paper/` directory, overwriting publication results with
test-scale fixtures. Fixed; a full suite run now leaves it untouched.

**5.4 Methodological cleanup (earlier).** Temporal look-ahead in actor
selection and community detection, raw-vs-retained counts conflated, and
failed perturbations counted as successes — all fixed, with the previous
result set deleted rather than kept alongside.

---

## 6. Limitations to state in any publication

1. **No user-study results.** Design only.
2. **Real data shows applicability, not correctness.** There is no ground
   truth on real data; correctness evidence comes from the synthetic
   known-truth experiments.
3. **Bridge Trend is not quotable** — 36 of 288 rows survive gating.
4. **The edge-count invariant still fails on all 8 datasets** (31 of 240
   settings). It is *reported and excluded*, not repaired: the three
   possible repairs each change what the method measures.
5. **Leakage-safe selection retains little** — median 4.75% of actors and
   3.29% of events. Results describe an early-selected cohort.
6. **The TGN is trained briefly and is not tuned for benchmark
   performance.** The claim is explainability, not competitiveness.
7. **Element-level attribution costs O(elements) model calls.** Bounded by
   `topK`/`sample`/`budget`, with coverage always reported.
8. **Single seed (42)** on real data.
9. **Decentraland edges are constructed**, not observed — a projected edge
   means two people voted on the same proposal, not that they know each
   other.

---

## 7. Reproducing everything

```bash
git clone <repository> && cd tgap
git switch real-data
pip install -r requirements.txt

# optional, for the TGN only
pip install torch --index-url https://download.pytorch.org/whl/cpu
pip install torch_geometric

python -m unittest discover -s tests     # 362 tests, ~160 s
python paper_evaluation.py               # synthetic known-truth evaluation
python -m realdata.download              # fetch raw datasets (once)
python -m realdata.run_real_data         # 8 datasets, ~3 min
python -m realdata.compare_datasets
python -m realdata.run_tgn               # trained TGN + explanation
python -m realdata.run_ncommunity        # N-community experiment
python -m realdata.make_publication      # figures and tables
```

**Windows note:** if `import torch` fails with `WinError 1114 … c10.dll`,
install the Microsoft VC++ 2015–2022 redistributable. PyTorch needs
`vcruntime140_1.dll`, which older Windows images lack. That — not PyTorch
Geometric — was the actual blocker on this machine.

---

## 8. Documentation map

| File | Contents |
|---|---|
| `README.md` | public API, how to add your own transformation |
| `docs/01` | TSAP, the method TGAP is derived from |
| `docs/06` | complete code walkthrough |
| `docs/07` | real data, in plain language |
| `docs/08` | datasets, pipeline, every output file and column |
| `docs/09` | user-study design (no results) |
| `docs/10` | the two case studies |
| `docs/11` | this report |
| `realdata/README.md` | preprocessing, validity gating, limitations |
