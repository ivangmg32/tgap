# TGAP Technical Audit & Design Decisions (v0.2)

Record of the deep review performed on the TGAP research prototype: what
was found, what was changed, why, and what remains open. Companion to
[01-TSAP-explained-simply.md](01-TSAP-explained-simply.md) and
[02-TGAP-code-walkthrough.md](02-TGAP-code-walkthrough.md) (note: doc 02
describes v0.1; the deltas are listed at the end of this file).

---

## 1. The central fix: achieved-change normalization

**Problem (Critical).** TGAP v0.1 normalized impacts by the *requested*
delta, copying TSAP's formula literally. But TSAP's `/|δ|` works because a
continuous series changes by *exactly* δ; graphs change by whole edges, so
a requested +10% on 6 bridges realizes as +1 edge = +16.7%. Dividing by
0.1 inflates the impact by the rounding ratio (×1.67 here), differently at
every width — biased magnitudes, invalid cross-concept comparison.

**Fix.** Each transformation now reports its own property
(`propertyValue(x)`, with `deltaMode` "relative" or "absolute"), and the
explainer divides by the change **actually achieved**. This is not a
departure from TSAP — in the continuous limit the two coincide; achieved
normalization is the faithful port of TSAP's semantics to a discrete
domain. Interpretation: for relative mode, the impact estimates
**∂(prediction)/∂(log property)** — a semi-elasticity.

**Evidence** (`evaluation.py`, section 4): for `pred = bridgeWidth(last)`
whose true semi-elasticity is exactly 8.0 at every delta:

| requested δ | achieved-norm impact | requested-norm impact |
|---|---|---|
| 0.05 | 0.0 (honest no-op: no edge moves) | 0.0 |
| 0.10 | **8.0** | 10.0 |
| 0.20 | **8.0** | 10.0 |
| 0.30 | **8.0** | 6.67 |
| 0.50 | **8.0** | 8.0 |

Achieved normalization is delta-invariant at the true value; requested
fluctuates ±25% with rounding. `normalization="requested"` remains
available for TSAP-parity, and `explainDetailed()` records both deltas,
the normalizer used, and no-op flags.

## 2. The mathematical bug the harness caught: tied hubs

Under edge-count-preserving rewiring, Freeman centralization collapses to

    C = (n·d_max − 2m) / ((n−1)(n−2))

because Σ(d_max − dᵢ) = n·d_max − 2m and m is held fixed. **C moves only if
the maximum degree moves.** The v0.1 "redistribute" branch drained one
fixed hub — a silent no-op whenever a second node was tied at d_max (true
in 4 of 6 standard-world snapshots; the faithfulness run showed impact
exactly 0.000 for the decrease direction). Fix: each step drains the
*currently* top-degree node, so ties are pulled down one by one.
Regression test: `testRedistributeLowersMetricUnderTiedMaxDegree`.

Effect on faithfulness (magnitude error vs analytic ground truth):
pure-centralization model **49.2% → 0.85%**; two-concept model
**24.6% → 0.42%**.

## 3. Other fixes in this pass

| Issue | Severity | Fix |
|---|---|---|
| `DensityTransformation` leaked heavily into bridge width (cross pairs dominate the non-edge pool; measured: +6.17 bridges at δ=+0.1 vs 0.00 confined) | High | optional `communities` confines changes to intra pairs |
| Default `TgapExplainer(model)` transformations used `communities=None` — the known-leaky configuration | High | defaults now built at explain time from one detected partition shared by both |
| `boxplotTrans` recomputed the baseline per (delta × input) | Medium | baselines hoisted; verified by exact call-count test |
| `setBridgeWidth` can under-pay on tiny/near-complete graphs (edge-count anchor silently partial) | Medium | documented + boundary-tested; achieved-delta reporting exposes it |
| Delta semantics inconsistent across transformations (relative property / fraction rewired / compounding ratio) | High | unified reporting via `propertyValue`; churn got a measurable definition (mean Jaccard distance to the last snapshot) |
| No leakage measurement, no call counting, no test suite | High/Med | `Diagnostics.py`, `ClusteringMetric`, `tests/` (55 tests), `evaluation.py` |

## 4. Verified results (v0.2)

- **Tests:** 55/55 pass (`python -m unittest discover -s tests`).
  Correctness (hand-derived widths, trajectories `[5,5,6,7,7,8]`), anchors
  (node set, edge counts, byte-identical last snapshots), determinism,
  input-mutation safety, orthogonality, boundaries (width 1, tiny graphs,
  complete graphs, zero/large/negative delta, disconnected input).
- **Faithfulness** (analytic ground-truth models): dominant-concept
  recovery 4/4, sign agreement 4/4, Spearman ρ = 1.0, magnitude errors
  0.00–0.85%.
- **Stability:** deterministic repeatability exact (5 runs identical);
  across 10 transformation seeds, impact std = 0.000 on every concept for
  the linear models (seed choice affects *which* edges move, not the
  measured sensitivities, on these worlds).
- **Efficiency:** exactly 1 + 2K model calls per explanation (K=4 → 9
  calls, ~38 ms with metric models); `boxplotTrans` = |xs| + nValues·|xs|.
- **Leakage panel** (δ=+0.1, change per metric; own column = intended):

| transformation | bridge width | centralization | density | clustering | cohesion |
|---|---|---|---|---|---|
| Bridge Width | **+1.00** | +0.006 | 0 | −0.007 | +0.114 |
| Centralization | 0.000 | **+0.363** | 0 | +0.112 | −0.120 |
| Bridge Trend | −1.67 (mean, intended trajectory) | +0.012 | 0 | +0.020 | −0.136 |
| Churn | 0.000 | −0.006 | 0 | +0.018 | +0.002 |
| Density (intra-confined) | 0.000 | +0.006 | **+0.023** | +0.059 | +0.016 |
| Density (unconstrained) | **+6.17 (leak)** | +0.025 | +0.023 | +0.003 | +0.630 |

Cohesion moving under bridge transformations is not leakage in the
problematic sense — cohesion *depends* on bridges by design.

## 5. Scientific framing (required caution)

Everything TGAP outputs is **model sensitivity to a controlled
counterfactual transformation** — concept attribution for the *model's*
behavior. It is **not** causal inference about the real-world system the
graph represents. Use: "the model's prediction responds to bridge
widening", never "widening bridges causes X in the ecosystem".

Positioning vs existing XAI: SHAP/LIME attribute to input features;
GNNExplainer/PGExplainer/GraphMask learn per-instance edge/node masks;
TCAV tests concepts but needs internal activations. TGAP's slot:
**concept-level, model-agnostic (predict-only), temporally aware
(trajectory concepts), O(K) model calls, with explicit confounder control
and measured leakage.** Its inherited limitation: it explains only the
concepts you defined.

## 6. Prototype assumptions (fail on real FOSS/DeFi data)

Exactly two communities; fixed node set across snapshots; undirected,
unweighted, attribute-free graphs; snapshot lists (not event streams);
partition constant over time; O(n²) candidate enumeration. None of these
holds in raw ecosystem data — WP2 ingestion must address node churn,
multi-community structure, weights/direction, before TGAP runs on real
graphs.

## 7. Open research decisions (not coding decisions)

1. **Churn's reference point:** current definition = disagreement with the
   *last* snapshot. Alternative: consecutive-step turnover
   (E_t vs E_{t+1}). Both defensible; they measure different things
   (memory-of-the-present vs volatility-of-change). Needs a domain call.
2. **BridgeTrend units:** slope is normalized absolutely (edges/step), so
   its impacts are not in the same units as relative-mode concepts. A
   shared normalization (e.g. standardized properties) would buy
   comparability at the cost of interpretability.
3. **Multi-community generalization:** pairwise bridges? one-vs-rest?
   weighted bridge portfolios? This changes the metric *and* every
   transformation; a WP3 design question.
4. **Anchor for density:** we chose "edge count is the property, so it may
   change". An alternative school would hold density fixed and treat it
   only as a confounder. Depends on whether density is a concept
   stakeholders want explained.
5. **Achieved-delta granularity for temporal transformations:** mean-based
   properties blur *where* in history the change happened; a per-snapshot
   profile would be richer but no longer a single number.

## 8. Changes vs doc 02 (v0.1 → v0.2)

- `explain()` default normalization is now **achieved**; sanity numbers in
  examples changed from ±10.0 to ±6.0 (see §1). `explainDetailed()` added.
- Centralization redistribute branch rewritten (see §2).
- `DensityTransformation(communities=...)`, `ClusteringMetric`,
  `WeightedMetricModel`, `SlopeModel`, `CallCountingModel`,
  `leakageReport`, `makeScenario` (10 ground-truth scenarios),
  `tests/` (55 tests), `evaluation.py` are new.
- `makeTwoCommunityGraph` accepts `nPerCommunityB` (asymmetric sizes).
