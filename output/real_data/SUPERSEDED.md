# SUPERSEDED — do not quote these numbers

This directory holds the **v1** real-data run, produced **before** the
methodological cleanup. It is kept only so the change is auditable. Every
number in the documentation now comes from:

```
output/real_data_v2/temporal_evaluation/    <- the scientific evaluation
output/real_data_v2/descriptive/            <- full-period description only
```

## What was wrong with v1

1. **Temporal look-ahead in node selection.** The retained actors were the
   most active over the **whole** observation period, so information from
   the last year could decide which actors appear in the first year's
   snapshot. v2 ranks actors using only the first 20% of the span and
   evaluates on the remaining 80%.

2. **Temporal look-ahead in community detection.** The two communities were
   detected on the union of **all** snapshots. v2 detects them on the
   selection period only and freezes the partition.

3. **No validity gating.** Rows whose transformation could not keep its
   declared edge-count invariant, and rows where the bridge-trend recursion
   saturated at the width-1 floor, were reported as ordinary results. v2
   marks them `feasible=False` / `transformation_status != "ok"` and
   excludes them from every aggregate.

4. **`nodes` meant retained nodes.** Tables reported a single `nodes`
   column for what was really a filtered subset. v2 always reports
   `raw_nodes` and `retained_nodes` side by side, with retention
   percentages.

5. **An overstated claim.** The zero impact of history-only transformations
   on present-only models was described as a property that "survives real
   data". It follows from the definitions — the transformations anchor the
   last snapshot and the models read only the last snapshot — so v2
   describes it as *verification of an expected invariant*.

The preprocessing changes mean v2 graphs are **not** comparable to v1
graphs: sparser, fewer snapshots, and in some cases a very different
partition. Mixing the two would be a methodological error.
