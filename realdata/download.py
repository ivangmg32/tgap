'''
Reproducible download of the raw real-data files.

Run:  python -m realdata.download

Every URL here was verified by inspecting the upstream source, not guessed:
 - the TGB URLs come from tgb/utils/info.py in the TGB repository
   (DATA_URL_DICT), so they match what the official loader uses.
 - the Decentraland files come from the replication package of the paper
   "Vote Delegation and Conformity in DAO Governance" (Ahmed), which ships
   a FROZEN snapshot of the Decentraland DAO Transparency export taken on
   30 April 2023. That matters for reproducibility: the live Transparency
   endpoint keeps growing, so only the frozen copy reproduces our numbers.

Note on TGB: we download the dataset archive directly instead of
installing the py-tgb package, because py-tgb pulls in a deep-learning
stack we do not need (the project deliberately has no torch dependency).
The archive contains the same edge list the official loader reads.

SSL note: this machine's Python has no system certificate store that
urllib can use, so we pass certifi's bundle explicitly. Without it every
HTTPS request fails with CERTIFICATE_VERIFY_FAILED.
'''

import hashlib
import os
import ssl
import time
import urllib.error
import urllib.request

import paths

try:
    import certifi
    _SSL_CONTEXT = ssl.create_default_context(cafile=certifi.where())
except ImportError:  # fall back to the system store if certifi is absent
    _SSL_CONTEXT = ssl.create_default_context()

DATA_DIR = paths.DATA

# name -> (url, local filename)
SOURCES = {
    "decentraland_votes": (
        "https://raw.githubusercontent.com/Dr-Ali-Ahmed/"
        "dao-delegation-replication/main/data/raw/votes.csv",
        "dcl_votes.csv"),
    "decentraland_proposals": (
        "https://raw.githubusercontent.com/Dr-Ali-Ahmed/"
        "dao-delegation-replication/main/data/raw/proposals.csv",
        "dcl_proposals.csv"),
    "tgbl_wiki": (
        "https://object-arbutus.alliancecan.ca/swift/v1/"
        "14c95234f6cd4a21a47deafe20cce2a7/tgb/tgbl-wiki-v2.zip",
        "tgbl-wiki-v2.zip"),
    # --- unipartite temporal edge lists (no projection needed) ---
    "email_eu_core": (
        "https://snap.stanford.edu/data/email-Eu-core-temporal.txt.gz",
        "email-Eu-core-temporal.txt.gz"),
    "email_eu_core_labels": (
        "https://snap.stanford.edu/data/email-Eu-core-department-labels.txt.gz",
        "email-Eu-core-department-labels.txt.gz"),
    "sx_mathoverflow": (
        "https://snap.stanford.edu/data/sx-mathoverflow.txt.gz",
        "sx-mathoverflow.txt.gz"),
    "bitcoin_otc": (
        "https://snap.stanford.edu/data/soc-sign-bitcoinotc.csv.gz",
        "soc-sign-bitcoinotc.csv.gz"),
    "bitcoin_alpha": (
        "https://snap.stanford.edu/data/soc-sign-bitcoinalpha.csv.gz",
        "soc-sign-bitcoinalpha.csv.gz"),
    "tgbl_enron": (
        "https://object-arbutus.alliancecan.ca/swift/v1/"
        "14c95234f6cd4a21a47deafe20cce2a7/tgb/tgbl-enron.zip",
        "tgbl-enron.zip"),
    "tgbl_uci": (
        "https://object-arbutus.alliancecan.ca/swift/v1/"
        "14c95234f6cd4a21a47deafe20cce2a7/tgb/tgbl-uci.zip",
        "tgbl-uci.zip"),
}

# Datasets we deliberately do NOT download, with the measured reason.
# Sizes were obtained with HTTP HEAD requests against the URLs above.
REJECTED = {
    "tgbl-review": "539.6 MB archive; ~4.8M events. Feasible in principle "
                   "but far larger than needed to demonstrate the pipeline.",
    "tgbl-coin": "1284.5 MB archive; ~22M events. Too large for a "
                 "reproducible prototype run.",
    "tgbl-flight": "1281.9 MB archive; ~67M events. Too large for a "
                   "reproducible prototype run.",
    "tgbl-subreddit": "257.9 MB archive; bipartite user-subreddit, so it "
                      "would add a third projection dataset without adding "
                      "a new graph family.",
    "tgbl-lastfm": "416.4 MB archive; bipartite user-track, same reason as "
                   "tgbl-subreddit.",
    "SNAP CollegeMsg": "VERIFIED to be the same data as TGB's tgbl-uci - "
                       "identical event count (59,835), node count and "
                       "timestamp offsets. Including both would count one "
                       "dataset twice, so only tgbl-uci is used.",
    "SNAP sx-askubuntu": "7.4 MB and perfectly usable, but it duplicates "
                         "the Q&A interaction family already covered by "
                         "sx-mathoverflow.",
    "SNAP wiki-talk-temporal": "48.1 MB, 1.1M events. Usable, but adds "
                               "no new graph family beyond the existing "
                               "communication datasets.",
}


def download(name, force=False, attempts=3):
    ''' Download one source if it is not already cached. Returns the local
    path. Caching makes repeated runs offline and fast; pass force=True to
    refetch.

    The file is written to `<name>.part` and renamed only once it is
    complete, so an interrupted download (network drop, Ctrl+C) can never
    leave a truncated file that a later run would mistake for the real one.
    Transient network failures are retried a few times before giving up. '''
    url, filename = SOURCES[name]
    os.makedirs(DATA_DIR, exist_ok=True)
    path = os.path.join(DATA_DIR, filename)
    if os.path.exists(path) and not force:
        return path
    partial = path + ".part"
    request = urllib.request.Request(url, headers={"User-Agent": "python"})
    for attempt in range(1, attempts + 1):
        start = time.time()
        try:
            with urllib.request.urlopen(request, timeout=300,
                                        context=_SSL_CONTEXT) as response, \
                    open(partial, "wb") as handle:
                while True:
                    chunk = response.read(1 << 20)
                    if not chunk:
                        break
                    handle.write(chunk)
            os.replace(partial, path)
            break
        except (OSError, urllib.error.URLError) as failure:
            if os.path.exists(partial):
                os.remove(partial)
            if attempt == attempts:
                raise
            print(f"  download of {filename} failed ({failure}); "
                  f"retrying ({attempt + 1}/{attempts})...")
            time.sleep(2 * attempt)
    print(f"  downloaded {filename}: {os.path.getsize(path) / 1e6:.1f} MB "
          f"in {time.time() - start:.0f}s")
    return path


def fileDigest(path, limit=1 << 20):
    ''' SHA-256 of the first `limit` bytes - a cheap fingerprint recorded
    in the metadata so a reader can tell whether they have the same file
    without hashing hundreds of megabytes. '''
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        digest.update(handle.read(limit))
    return digest.hexdigest()


def downloadAll():
    print("Downloading real datasets into", DATA_DIR)
    paths = {}
    for name in SOURCES:
        paths[name] = download(name)
        print(f"  ready: {name} -> {paths[name]}")
    print("\nNot downloaded (measured sizes, see REJECTED):")
    for name, reason in REJECTED.items():
        print(f"  {name}: {reason}")
    return paths


if __name__ == "__main__":
    downloadAll()
