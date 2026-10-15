'''
Every folder the project reads from or writes to, defined ONCE.

No script builds an output path from a string literal; they all import from
here. To see where a result lives, read this file - nothing else decides it.

Paths are anchored to the repository root (this file's directory), so a
script writes to the same place whatever the working directory is.

    data/                          raw downloads (gitignored, see realdata/download.py)
    output/
    ├── synthetic/                 experiments/synthetic_evaluation.py (RQ1-RQ8)
    ├── real_data/<mode>/<dataset>/   realdata.run_real_data
    ├── comparison/<mode>/         realdata.compare_datasets
    ├── ncommunity/<dataset>/      realdata.run_ncommunity
    ├── tgn/<dataset>/             realdata.run_tgn
    ├── tgn_stability/<dataset>/   realdata.run_tgn_stability
    ├── finance/<study>/           finance.run_finance (stock correlation networks)
    ├── finance/datamining/        finance.experimentationDatamining (Ivan's RQ1-RQ4)
    ├── publication/               realdata.make_publication - the paper's inputs
    │   ├── figures/
    │   ├── tables/
    │   ├── attribution/
    │   └── figure_metadata.json
    ├── examples/<example>/        the easy examples in examples/ (gitignored)
    └── logs/                      run.py's technical logs (gitignored)

<mode> is the analysis mode (realdata/adapters/base.py, DECISION 4). Only
temporal_evaluation results are committed.
'''

import os

ROOT = os.path.dirname(os.path.abspath(__file__))

# Inputs
DATA = os.path.join(ROOT, "data")
# Daily stock prices, cached per ticker (Ivan's Cache.py keeps them here).
FINANCE_PRICES = os.path.join(ROOT, "finance", "Cache")

# Outputs - one root, one folder per pipeline stage
OUTPUT = os.path.join(ROOT, "output")
SYNTHETIC = os.path.join(OUTPUT, "synthetic")
REAL_DATA = os.path.join(OUTPUT, "real_data")
COMPARISON = os.path.join(OUTPUT, "comparison")
NCOMMUNITY = os.path.join(OUTPUT, "ncommunity")
TGN = os.path.join(OUTPUT, "tgn")
TGN_STABILITY = os.path.join(OUTPUT, "tgn_stability")
FINANCE = os.path.join(OUTPUT, "finance")
FINANCE_DATAMINING = os.path.join(FINANCE, "datamining")

PUBLICATION = os.path.join(OUTPUT, "publication")
PUBLICATION_FIGURES = os.path.join(PUBLICATION, "figures")
PUBLICATION_TABLES = os.path.join(PUBLICATION, "tables")
PUBLICATION_ATTRIBUTION = os.path.join(PUBLICATION, "attribution")

# Your own runs of the easy examples (gitignored), and run.py's logs.
EXAMPLES = os.path.join(OUTPUT, "examples")
LOGS = os.path.join(OUTPUT, "logs")


def relative(path):
    ''' A path as it should appear INSIDE an output file: relative to the
    repository root, with forward slashes, so committed JSON never carries
    one machine's absolute paths. '''
    return os.path.relpath(path, ROOT).replace(os.sep, "/")
