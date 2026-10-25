# TGAP vs CoDy — reproducible comparison on one TGN prediction

Implemented 2026-10-24 on branch `user-experiment`. Pilot record
`cmp-2fd0359ddb42` (`output/compare_explainers/records/`). How to run:
[compare_explainers/README.md](../compare_explainers/README.md).

## 1. Result of the pilot (measured, not projected)

| | |
|---|---|
| Dataset | UCI-Messages, 59,835 messages, 1,899 students, 193.7 days; stream SHA-256 `e6e62991…` |
| Split | chronological by timestamp quantile 70 / 15 / 15 (train ends at event 41,884; test starts at 50,859) |
| Model | one event-level TGN, checkpoint `output/compare_explainers/models/tgn_uci_de6a9219a182.pt`, SHA-256 `8311596a…9e95219`, weights fingerprint `d68eb3e7…` |
| Held-out quality (sequential protocol, balanced negatives, chance 0.5) | test AUC 0.882, AP 0.874, accuracy 0.746; validation AUC 0.852, AP 0.827 |
| Target | event 58,894: student **492 → 463** at t = 14,311,088 s (day 165.6, 2004-09-27 23:14 UTC); 58,894 history events; no earlier message between the two |
| Selection | seeded permutation of the test split, first eligible event; the first candidate was eligible (0 exclusions) |
| Original prediction | logit 0.161963, **p = 0.5404 → "message"** (correct) |
| Baseline consistency | 4 independent paths (direct replay, selection pass, TGAP adapter, CoDy wrapper): **identical, difference 0.0**; same history fingerprint, same weights → **PASSED** |
| Comparability | **scientific comparison: same model, same input, same original score** |

**TGAP — Decrease Churn, requested −20%** (status *valid*)

| | |
|---|---|
| Churn (mean Jaccard distance to the latest 10-day snapshot, 17 snapshots) | 0.9721 → 0.8573 |
| Achieved change | **−11.8%** (not −20%: Churn can only flip disagreeing edges that have a partner in the latest snapshot) |
| Model output | p 0.5404 → **0.5324** (−0.80 points); class unchanged ("message") |
| Normalized impact (TGAP definition, ÷ achieved) | **−0.068** |
| Checks | latest snapshot identical, edge count kept in every snapshot, event-mapping round trip passed |
| Side effects | 1,574 edge swaps → 4,841 of 58,894 history messages re-addressed (synthetic; 226 involve A or B); event count, timestamps and order unchanged |
| Opposite direction (measured by the same explainer call) | Increase Churn: achieved +0.33%, p → 0.5417, impact +0.41 |

**CoDy — spatio-temporal policy, 300 steps, 2-hop, 64 candidates** (status *no_class_change*)

| | |
|---|---|
| Counterfactual found | **No.** Search used its full budget (301 steps, 301 model queries, 147 s). |
| Returned best events | 2: messages 492 → 1181 sent 0.28 days before t (event ids 58,872 and 58,873) |
| Model output without them | p 0.5404 → **0.5295**; class unchanged. CoDy's reported score equals the exact full-replay re-check. |
| Sparsity (CoDy repository definition) | 2 / 64 = 0.031 |

Reading: on this one prediction both methods report a small, real model
response and neither changes the predicted class. These are different
quantities (a concept sensitivity vs. an event set) and are not compared
numerically. One pilot instance supports no claim that either explainer is
better in general.

## 2. Compatibility audit

* **TGAP's existing TGN** (`core/TgnModel.py`) reads snapshots (time = snapshot
  index), returns the *mean* probability of the last snapshot's edges, and keeps
  no checkpoint. CoDy explains the score of **one event** in an event stream
  and removes individual past events. The two are not compatible without
  changing prediction semantics, so **no existing checkpoint could be shared.**
* **Resolution (shared canonical backend):** `compare_explainers/tgn_backend.py`
  builds one event-level TGN from TGAP's own modules (`GraphAttentionEmbedding`,
  `LinkPredictor`; PyG `TGNMemory`/`IdentityMessage`/`LastAggregator`/
  `LastNeighborLoader`; the 32/32/32 dimensions and neighbour size of
  `buildTgn`), trains it once and saves it with its hash. Both explainers call
  the **same loaded instance**; each path reports the weights fingerprint it
  queried, and the record verifies both against the checkpoint.
* **Inference is sequential** (one event at a time from a reset memory), so
  CoDy's restore-and-replay and TGAP's full replay perform identical
  operations: equal inputs give bit-identical scores.
* **Dataset identity:** TGB `tgbl-uci` = Opsahl `OCnodeslinks.txt` (CoDy's
  documented source, SHA-256 `475242ac…`) minus 1,899 self-loop rows, with
  timestamps shifted by 1,082,015,761 s; checked row by row. One stream is
  used for both explainers; CoDy's own script would have kept the self-loops.
* **Churn ↔ event history:** Churn is defined on snapshots. It is applied by
  the unchanged `ChurnTransformation` inside the unchanged `TgapExplainer`;
  the transformed snapshots are mapped back to events by re-addressing the
  messages of each swapped-out pair to its paired swapped-in pair (same
  timestamp, position and orientation). A round trip must reproduce the
  transformed snapshots exactly and the latest window must be byte-identical,
  otherwise the run is `mapping_invalid` and no TGAP result is claimed. The
  re-addressed messages are synthetic and listed in the record.
* **CoDy integration:** official package vendored unmodified at commit
  `0a004c2a` (MIT; hash manifest), connected through a `TGNNWrapper`
  subclass — CoDy's documented extension point. One deliberate wrapper
  difference from CoDy's reference TGN wrapper: the non-approximate rollout
  keeps ids `>=` the restore point (the reference uses `>`, which skips the
  oldest candidate). Timeouts are enforced in the wrapper.

## 3. Files

Added: `compare_explainers/` (`config.py`, `dataset.py`, `tgn_backend.py`,
`target.py`, `tgap_adapter.py`, `cody_adapter.py`, `pipeline.py`, `export.py`,
`__main__.py`, `README.md`, `third_party/` with CoDy, `UPSTREAM.md`,
manifest), `tests/test_compare_explainers.py`, `workbench/sandbox/compare.py`,
`workbench/static/compare.js`, `workbench/static/study-links.js`, `workbench/tests/test_compare.py`,
`workbench/tests/test_compare_model.py`, `output/compare_explainers/`
(checkpoint, record, CSVs), this document.
Modified: `workbench/sandbox/app.py` (compare tables and endpoints, withdrawal,
researcher exports), `workbench/static/index.html`, `app.js`, `figures.js`,
`style.css`, `guided.js` (optional Python extra, phase-2 button, survey links), `pyproject.toml`, `README.md`, `docs/README.md`,
`tgap_cli/data/sandbox.zip` (rebuilt bundle). No change to `core/` or to CoDy.

## 4. Website: the two-phase user study

**Phase 1 — the guided TGAP study (`#guided`)**, as before: pre-survey,
dataset, model, a ready-made concept, run, results. Writing your own concept
in Python is now an **optional extra** (a small "Try it" card, "skip it now
and come back later"), not one of two equal choices.

**Phase 2 — Compare explainers (`#compare`)**, opened from the
**"Let's compare with CoDy →"** button at the end of the Phase 1 results
(which replaces the old post-survey card). Five steps, no forms:

1. *The case* — the question, the model's answer (54.0%), what really
   happened, what each explainer asks, and the fairness check.
2. *TGAP explains* — one-sentence answer with an effect-size label, a
   "what if" row (less churn 53.2% / as it happened 54.0% / more churn 54.2%),
   a four-step story (question, what changed, how the model reacted, what it
   means), a timeline of where the history was rewired with the last 10 days
   locked, and check badges. Technical numbers sit in a collapsed panel.
3. *CoDy explains* — a factual one-sentence caption, the selected messages,
   and the before/after confidence bars; search details collapsed.
4. *Side by side* — shared header once, TGAP and CoDy columns, a note that
   their numbers are not on one scale, reproducibility record and downloads.
5. *Finish* — the post-study survey link.

All sentences are generated in `workbench/sandbox/compare.py` from measured
values only; effect words are conservative (below 2 points = "very small").
Survey links live in one file, `workbench/static/study-links.js` (mock links
until the real Google Forms are supplied). Phase 2 records nothing; the
earlier in-page questionnaire, consent and 0–7 ratings were removed.

## 5. Tests (run 2026-10-24)

* `tests/test_compare_explainers.py`: **29 passed** (dataset identity, split,
  leakage, four-path baseline, shared weights, memory reset, no stale state,
  checkpoint mismatch, Churn reuse, requested vs achieved, anchor, invalid and
  no-op, no mutation, provenance, unmappable refusal, CoDy forwarding, outcome
  classes, timeout, real events and scores, saved-record checks, exports,
  vendored-code integrity).
* `workbench/tests/test_compare_model.py`: wording never overstates the effect,
  every number in the stories matches the record, the headline direction
  matches the measured change, CoDy's caption reports its own outcome,
  separate method metrics, no filled-in values, missing/invalid runs.
* `workbench/tests/test_compare.py` (API via FastAPI's test client): read-only
  scenario, non-comparable labelling, tamper refusal, downloads. Needs the
  test client's `httpx2` dependency, which is not installed here; the same
  endpoints were checked against a loopback server instead.

## 6. Limitations

* One target, one model, one seed: a pilot, not evidence of general superiority.
* Phase 2 presents TGAP with a richer plain-language layout than CoDy's native
  output. Differences in user understanding may partly reflect presentation
  rather than the explainers themselves.
* The TGN is new (event-level) rather than TGAP's existing snapshot TGN; the
  existing adapter's results are not affected and not compared here.
* The Churn intervention reaches the TGN through re-addressed synthetic
  messages; its effect is a response to that documented mapping.
* Churn achieved −11.8% of the requested −20%; reported as achieved.
* CoDy ran with its approximate predictions (its default); its final scores
  were re-checked exactly. Other selection policies or budgets may find a
  counterfactual; this run did not.
* Training uses batched PyG updates, inference is sequential (batch-size-1
  limit); held-out metrics are reported under the sequential protocol.
* Remaining nondeterminism: none observed in-process (four-path difference
  0.0); cross-machine bit-equality is not guaranteed by PyTorch.
