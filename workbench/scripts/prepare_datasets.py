"""Operator-only fixture preparation; participant requests never download data."""
import argparse
import json
from pathlib import Path
import sys

parser=argparse.ArgumentParser()
parser.add_argument('--tgap-source',required=True)
args=parser.parse_args()
sys.path.insert(0,str(Path(args.tgap_source).resolve()))
from realdata.run_real_data import ADAPTERS
from realdata.adapters.base import TEMPORAL_EVALUATION

home=Path(__file__).resolve().parents[1]
fixtures=home/'fixtures'
fixtures.mkdir(exist_ok=True)
datasets=home/'data'/'datasets'
datasets.mkdir(parents=True,exist_ok=True)
for name,adapter in ADAPTERS.items():
    prepared=adapter(TEMPORAL_EVALUATION)
    partition=prepared.communities
    payload=dict(nodes=sorted(prepared.snapshots[0].nodes()),
                 snapshots=[list(g.edges()) for g in prepared.snapshots],
                 communities=[sorted(c) for c in partition],community_labels=list(partition.labels),
                 labels=prepared.labels,meta={**prepared.meta,'preprocessing':prepared.preprocessing},
                 fixture_version='1.0',source_mode=TEMPORAL_EVALUATION)
    content=json.dumps(payload,separators=(',',':'),allow_nan=False)
    for directory in (fixtures,datasets):
        (directory/f'{name}.json').write_text(content,encoding='utf-8')
    print(name, len(payload['nodes']),len(payload['snapshots']),len(content),'bytes',flush=True)
