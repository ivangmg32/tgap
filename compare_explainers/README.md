# Compare Explainers — TGAP vs CoDy

A reproducible pilot that explains **one** prediction of **one** trained
temporal graph network with two explainers, in their native forms:

* **TGAP** changes a graph concept (here: *Churn*, decreased by a requested
  20%) in the history, keeps the latest snapshot fixed, and measures how the
  model's output responds (normalized by the change actually achieved).
* **CoDy** (official code, vendored unmodified) searches for past events whose
  removal flips the model's prediction (a counterfactual explanation).

Both use the same UCI-Messages event stream, the same TGN checkpoint (checked
by SHA-256), the same target message A → B at time *t*, and the same history.
A baseline-consistency check proves that the original score is identical on
every path before anything is compared.

The engineering report, compatibility audit and the pilot's actual results
are in [docs/17-tgap-vs-cody-comparison.md](../docs/17-tgap-vs-cody-comparison.md).

## Install (once)

From the TGAP folder, into the same environment you use for TGAP:

```sh
pip install -r requirements.txt
pip install torch --index-url https://download.pytorch.org/whl/cpu
pip install torch_geometric tqdm ipython
```

`tqdm` and `ipython` are imported by CoDy's own package. The UCI data file is
`data/tgbl-uci.zip`; if it is missing, run `python -m realdata.download`.

## Run

```sh
python -m compare_explainers run       # ~20-30 min on a laptop CPU (first run trains the TGN, ~2 min)
python -m compare_explainers status    # comparable? which statuses?
python -m compare_explainers export --out somewhere/
```

Options for `run`: `--max-steps N`, `--time-limit SECONDS`,
`--policy {random,temporal,spatio-temporal,local-gradient}` (CoDy settings),
`--retrain` (train a new checkpoint), `--allow-noncomparable` (run the
explainers even if the baseline check fails; the record is then labelled
*not comparable*).

The exit code is 0 for a comparable record and 2 otherwise.

## Outputs (`output/compare_explainers/`)

| File | What it is |
|---|---|
| `models/tgn_uci_<key>.pt` (+ `.json`) | the one TGN checkpoint, its SHA-256 and parameter fingerprint, training history and held-out metrics |
| `models/tgn_uci_<key>_test_logits.npz` | original scores of every test event (used by target selection) |
| `records/<experiment-id>.json` | the complete reproducibility record |
| `records/<experiment-id>_summary.csv` | long-format CSV: section, field, value |
| `records/<experiment-id>_cody_events.csv` | CoDy's event set |
| `records/<experiment-id>_tgap_changes.csv` | the history messages TGAP's lift re-addressed |
| `latest.json` | pointer + SHA-256 of the latest record (read by the website) |

The experiment id is a hash of the configuration (`config.py`), so the same
settings always produce the same id and reuse the same checkpoint.

## See it in the website

Start the workbench (`python run.py start`). The comparison is phase 2 of
the guided user study: finish the guided TGAP experiment and press
**Let's compare with CoDy →**, or open **Compare explainers** in the sidebar.
The page reads `latest.json`; it never trains or runs a model itself, and it
records nothing. Survey links are set in `workbench/static/study-links.js`.

## Tests

```sh
python -m pytest tests/test_compare_explainers.py -q       # research side
cd workbench && python -m unittest tests.test_compare -v    # website side (workbench environment)
```
