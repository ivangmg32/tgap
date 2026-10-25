'''
TGAP vs CoDy: a reproducible comparison of two explainers on ONE prediction.

    python -m compare_explainers run        # full pilot (trains the TGN once)
    python -m compare_explainers status     # what exists, what is comparable
    python -m compare_explainers export     # JSON + CSV of the latest record

What is compared
    Dataset  UCI-Messages (TGB tgbl-uci; verified identical to Opsahl's
             OCnodeslinks.txt without its 1,899 self-loop rows)
    Model    ONE trained TGN checkpoint (event-level; TGAP's TGN modules)
    Target   one real future message A -> B at time t from the test split
    TGAP     the existing ChurnTransformation + TgapExplainer, mapped to the
             TGN's event history by a documented, round-trip-checked adapter
    CoDy     the official CoDy search (vendored, unmodified, pinned commit),
             driven through CoDy's own extension point (a TGNNWrapper)

Both explainers query the same model instance with the same original history.
The baseline-consistency check proves it before anything is compared.

Package layout (one responsibility per file)
    config.py        the shared experiment contract + hashing
    dataset.py       the canonical UCI-Messages event stream and its split
    tgn_backend.py   the canonical event-level TGN: train, save, load, score
    target.py        deterministic target selection
    tgap_adapter.py  snapshots, Churn, the event lift, the TGAP run
    cody_adapter.py  the CoDy TGNNWrapper and the CoDy run
    pipeline.py      runs everything, writes the reproducibility record
    export.py        JSON / CSV export of a record
    third_party/     the vendored CoDy package (MIT) + file-hash manifest
'''
