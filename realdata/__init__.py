'''
Real-data integration layer for TGAP.

This package sits BESIDE the main system: it imports from core/ but nothing
in core/ imports from here, so the synthetic experiments and the TGAP
explanation logic are untouched by anything in this folder.

    raw real dataset  ->  selection period / evaluation period split
                      ->  preprocessing  ->  temporal snapshots
                      ->  TGAP-compatible temporal graph (list of nx.Graph)
                      ->  metrics  ->  model  ->  TGAP explanation
                      ->  validity gating
                      ->  output/real_data/<analysis_mode>/<dataset>/

Layout:
    download.py            reproducible downloads of the raw files
    adapters/base.py       shared preprocessing (modes, projection,
                           snapshots, raw-vs-retained accounting, stats)
    adapters/tgbl_wiki.py  TGB tgbl-wiki adapter (bipartite, projected)
    adapters/decentraland.py  Decentraland DAO adapter (bipartite, projected)
    adapters/edgelist.py   six unipartite temporal edge lists
    run_real_data.py       runs TGAP on every supported dataset
    compare_datasets.py    cross-dataset comparison table and figures
    run_ncommunity.py      N = 2, 3, 4 community sweep
    run_tgn.py             explains a trained TGN (needs torch)
    run_tgn_stability.py   the TGN over five seeds, matched comparison
    comparability.py       the concept comparability rule (no torch import)
    make_publication.py    the paper's figures and tables
    plotting.py            the shared publication theme

Every output folder is defined in paths.py at the repository root.

Two analysis modes, always labelled in the output (adapters/base.py
DECISION 4):
    temporal_evaluation  DEFAULT. Actors and communities are chosen from the
                         first 20% of the time span; TGAP explains snapshots
                         from the remaining 80%. Leakage-safe.
    descriptive          Full-period selection and snapshots. NOT
                         leakage-safe; for describing a dataset only.

Only the DEFAULT mode's results are committed, under
output/real_data/temporal_evaluation/. Descriptive-mode results are
reproducible with `--mode descriptive` but are not stored, so a
leakage-unsafe number cannot be quoted by accident. The pre-cleanup v1
results were deleted; git history still holds them.

Scientific caution: running TGAP on real data shows that the pipeline
works on real temporal structure and produces interpretable sensitivities.
It does NOT by itself validate TGAP's correctness - there is no ground
truth on real data. Correctness evidence comes from the synthetic
known-truth experiments in experiments/synthetic_evaluation.py.
'''
