'''
The canonical UCI-Messages event stream - loaded ONCE, used by both explainers.

DATASET IDENTITY (verified, not assumed)
    CoDy's README prepares UCI-Messages from Opsahl's OCnodeslinks.txt
    (http://opsahl.co.uk/tnet/datasets/OCnodeslinks.txt, 61,734 rows,
    SHA-256 475242ac...cff8). TGAP already ships TGB's tgbl-uci
    (59,835 rows). Compared row by row (see docs/17): tgbl-uci is EXACTLY
    the Opsahl file with its 1,899 self-loop rows removed - one "n n" row
    per user, a registration artefact, not a message - and with timestamps
    shifted to start at 0 (Opsahl's first message is 2004-04-15 07:56:01
    UTC = unix 1082015761). Sources, destinations and order are identical.

    CoDy's own script would keep those 1,899 self-loops; TGAP's pipeline
    drops self-loops. We use ONE source for both explainers: the tgbl-uci
    stream, i.e. messages only. So both explainers see the same events, and
    neither sees the registration rows.

NO SNAPSHOTS HERE
    This module returns the raw ordered event stream. The TGN consumes events.
    Snapshots exist only inside the TGAP adapter, as TGAP's representation for
    measuring and changing Churn, and are mapped back to events there.
'''

import hashlib
import io
import os
import zipfile
from dataclasses import dataclass, field

import numpy as np

import paths

from .config import PREPROCESSING_VERSION, fileSha256

EXPECTED_EVENTS = 59835
EXPECTED_NODES = 1899
OPSAHL_FIRST_MESSAGE_UNIX = 1082015761


@dataclass(frozen=True)
class EventStream:
    ''' An immutable ordered event stream. Event id = position. '''
    src: np.ndarray
    dst: np.ndarray
    ts: np.ndarray
    num_nodes: int                     # memory slots (max node id + 1)
    provenance: dict = field(default_factory=dict)

    def __post_init__(self):
        for name in ("src", "dst", "ts"):
            array = getattr(self, name)
            array.setflags(write=False)  # never mutated in place
        if not (len(self.src) == len(self.dst) == len(self.ts)):
            raise ValueError("src, dst and ts must have the same length")

    def __len__(self):
        return len(self.ts)

    @property
    def event_ids(self):
        return np.arange(len(self.ts), dtype=np.int64)

    def fingerprint(self):
        return streamFingerprint(self.src, self.dst, self.ts)


def streamFingerprint(src, dst, ts):
    ''' SHA-256 over the int64 arrays (src, dst, ts), in order. Two
    histories with the same fingerprint are the same input to the TGN. '''
    digest = hashlib.sha256()
    for array in (src, dst, ts):
        digest.update(np.ascontiguousarray(array, dtype=np.int64).tobytes())
    return digest.hexdigest()


def archivePath(config):
    return os.path.join(paths.DATA, config["dataset"]["archive"])


def loadUciMessages(config, path=None):
    ''' Read the canonical stream and verify every fact we rely on. '''
    path = path or archivePath(config)
    if not os.path.exists(path):
        raise FileNotFoundError(
            f"{path} is missing. Download it with "
            "`python -m realdata.download` (source key tgbl_uci).")
    member = config["dataset"]["member"]
    with zipfile.ZipFile(path) as archive:
        raw = archive.read(member)
    rows = np.loadtxt(io.BytesIO(raw), delimiter=",", skiprows=1,
                      dtype=np.int64)
    src, dst, ts = rows[:, 0].copy(), rows[:, 1].copy(), rows[:, 2].copy()

    problems = []
    if len(ts) != EXPECTED_EVENTS:
        problems.append(f"{len(ts)} events, expected {EXPECTED_EVENTS}")
    nodes = np.union1d(src, dst)
    if len(nodes) != EXPECTED_NODES:
        problems.append(f"{len(nodes)} nodes, expected {EXPECTED_NODES}")
    if np.any(np.diff(ts) < 0):
        problems.append("timestamps are not in chronological order")
    if np.any(src == dst):
        problems.append("self-loops present")
    if nodes.min() < 1:
        problems.append("node ids must start at 1")
    if problems:
        raise ValueError("UCI-Messages integrity check failed: "
                         + "; ".join(problems))

    provenance = {
        "dataset": config["dataset"]["id"],
        "archive": os.path.basename(path),
        "archive_sha256": fileSha256(path),
        "member": member,
        "member_sha256": hashlib.sha256(raw).hexdigest(),
        "events": int(len(ts)),
        "nodes": int(len(nodes)),
        "node_id_range": [int(nodes.min()), int(nodes.max())],
        "time_span_seconds": int(ts[-1] - ts[0]),
        "preprocessing_version": PREPROCESSING_VERSION,
        "preprocessing": [
            "read tgbl-uci_edgelist.csv columns u, i, ts (label and idx "
            "unused: label is always 0, idx is the 1-based row number)",
            "event id = 0-based row position; rows are already sorted by ts",
            "no events are filtered: the file has no self-loops",
            "direction kept as stored (u = sender, i = receiver)",
            "node ids used as memory slots directly (no remapping)",
        ],
        "relation_to_cody_source": (
            "identical to Opsahl OCnodeslinks.txt (CoDy README source) minus "
            "its 1,899 self-loop rows; timestamps = unix time - "
            f"{OPSAHL_FIRST_MESSAGE_UNIX}"),
    }
    stream = EventStream(src, dst, ts, int(nodes.max()) + 1, provenance)
    provenance["stream_sha256"] = stream.fingerprint()
    return stream


def chronologicalSplit(stream, config):
    ''' Train / validation / test by timestamp quantile, the convention of
    the TGN reference code CoDy builds on. Returns event-id boundaries:
    train = [0, trainEnd), validation = [trainEnd, validationEnd),
    test = [validationEnd, N). Every test event is later than every
    training event. '''
    split = config["split"]
    validationTime, testTime = np.quantile(
        stream.ts, [split["train"], split["train"] + split["validation"]])
    trainEnd = int(np.searchsorted(stream.ts, validationTime, side="right"))
    validationEnd = int(np.searchsorted(stream.ts, testTime, side="right"))
    return {
        "method": split["method"],
        "fractions": [split["train"], split["validation"], split["test"]],
        "train": [0, trainEnd],
        "validation": [trainEnd, validationEnd],
        "test": [validationEnd, len(stream)],
        "validation_start_time": float(validationTime),
        "test_start_time": float(testTime),
        "identifier": hashlib.sha256(
            f"{trainEnd}:{validationEnd}:{len(stream)}".encode()
        ).hexdigest()[:16],
    }


def historyBefore(stream, targetEventId):
    ''' The model input for a prediction at the target's time: every event
    STRICTLY before the target timestamp. Target selection guarantees no
    other event shares that timestamp, so this equals "event ids <
    target id" - the same prefix CoDy's wrapper rolls out. '''
    t = stream.ts[targetEventId]
    end = int(np.searchsorted(stream.ts, t, side="left"))
    if end != targetEventId:
        raise ValueError("another event shares the target timestamp; "
                         "history would be ambiguous")
    return end
