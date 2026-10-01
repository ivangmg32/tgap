# Real Data: The Datasets, The Pipeline, and Every Output File

> **What this is:** the reference manual for the real-data part of TGAP.
> Four questions answered: what each dataset actually contains, how each one
> is turned into TGAP input, what every output file and every column means,
> and how to run it.
>
> **Style:** simple words, but complete. This is the document to keep open
> while looking at the result files.
>
> **Date of the run described here:** 24 September 2026.
> All numbers come from that run. Nothing is invented.
>
> **Companion documents:** [07](07-real-data-explained-simply.md) explains
> *why* we made each decision and what we learned.
> [06](06-TGAP-complete-guide-A-to-Z.md) explains the TGAP code itself.
> `tgap/realdata/README.md` is the short technical version.

---

## Table of contents

1. [The 60-second version](#1-the-60-second-version)
2. [Where everything lives](#2-where-everything-lives)
3. [The process, start to finish](#3-the-process-start-to-finish)
4. [The 8 datasets: what each file really contains](#4-the-8-datasets-what-each-file-really-contains)
5. [How each dataset becomes TGAP input](#5-how-each-dataset-becomes-tgap-input)
6. [The output folder structure](#6-the-output-folder-structure)
7. [Every output file, column by column](#7-every-output-file-column-by-column)
8. [Reading one real row, end to end](#8-reading-one-real-row-end-to-end)
9. [How to run it](#9-how-to-run-it)
10. [How to tell a run went well](#10-how-to-tell-a-run-went-well)
11. [Known problems and dates](#11-known-problems-and-dates)

---

## 1. The 60-second version

```
  8 real datasets          →  preprocessing  →  a temporal graph each
  (raw files on disk)                           (list of snapshots +
                                                 two communities)
                                      ↓
                           6 models × 5 concepts × 3 sizes × 2 directions
                                      ↓
                              180 experiments per dataset
                                      ↓
                           2 validity checks throw out the broken ones
                                      ↓
              1,440 experiments total, 1,140 usable, in CSV files
```

| | |
|---|---|
| Raw data in | `C:\catalyst\tgap\realdata\data\` (11 files, ~100 MB) |
| Results out | `C:\catalyst\tgap\output\real_data_v2\temporal_evaluation\` |
| Command | `python -m realdata.run_real_data` (3 minutes) |
| Branch | `real-data` (the files do not exist on `WorkingBranch`) |
| Random seed | 42, everywhere |

---

## 2. Where everything lives

```
C:\catalyst\tgap\
│
├── realdata\                  ← the code that reads real data
│   ├── data\                       ← THE RAW INPUT (11 files, not in git)
│   ├── download.py                 fetches them; records rejected datasets
│   ├── adapters\
│   │   ├── base.py                 shared preprocessing for all 8
│   │   ├── edgelist.py             the 6 "person → person" datasets
│   │   ├── tgbl_wiki.py            Wikipedia
│   │   └── decentraland.py         the DAO
│   ├── run_real_data.py            runs TGAP, writes results
│   └── compare_datasets.py         compares the 8 against each other
│
├── core\                      ← TGAP itself (used by the above, never the reverse)
│
├── tests\test_realdata.py     ← 158 automatic checks
│
└── output\
    └── real_data_v2\
        └── temporal_evaluation\   ← THE RESULTS  ← look here
```

**The two folders people confuse.** `realdata\data\` is what we *downloaded*.
`output\real_data_v2\` is what TGAP *produced*. Only the second one is worth
showing anyone.

---

## 3. The process, start to finish

Every dataset goes through the same eight steps. The only thing that differs
is step 2.

```
 STEP 1   Download the raw file
          → realdata\data\  (cached; done once, then works offline)

 STEP 2   Read it
          → a plain list of events: (who, whom, when)
            or (who, which-item, when) for the two bipartite ones

 STEP 3   Cut the time span in two
          |◄─ first 20% ─►|◄────── remaining 80% ──────►|
            SELECTION          EVALUATION
          Nothing from the right side may influence the left side's job.

 STEP 4   Choose the actors  — using the SELECTION period only
          → the most active 100–120, frozen for the whole run

 STEP 5   Find the two communities — using the SELECTION period only
          → one fixed split, frozen for the whole run
            (except email_eu_core: real department labels, no algorithm)

 STEP 6   Build the snapshots — from the EVALUATION period only
          → a list of networkx graphs, same node set in every one

 STEP 7   Run TGAP
          6 models × 5 concepts × 3 deltas × 2 directions = 180 experiments

 STEP 8   Check validity, then write the files
          → broken experiments labelled and their numbers withheld
```

> ### 🔬 Why steps 3–5 are in that order
> This is the part a reviewer checks first. If you choose your actors using
> the whole time span, you have used the future to decide what the past
> looked like — which is impossible in real life and makes results look
> better than they are. Splitting by time first, and only then choosing, is
> the standard cure. Every output file records that it was done
> (`future_information_used_for_node_selection: false`).

---

## 4. The 8 datasets: what each file really contains

Every format below was read from the actual file, not assumed.

### Family A — "person → person" (6 datasets, no projection needed)

These are the easy ones: the file already says *A interacted with B*, so the
links are **observed**, not invented.

#### `email_eu_core` — a European research institute

```
  file    email-Eu-core-temporal.txt.gz   (1.6 MB)
  format  SENDER RECEIVER TIME     (space separated, no header)
  line    582 364 0
          168 472 2797
  time    seconds counted from the start of the study (not a real date)
```
Plus a **second file**, which is what makes this dataset special:
```
  file    email-Eu-core-department-labels.txt.gz   (2.6 KB)
  format  PERSON DEPARTMENT
  line    0 1
          1 1
          2 21
```
332,334 emails, 986 people in the log, 42 real departments, 804 days.

#### `tgbl_enron` — the Enron company email archive

```
  file    tgbl-enron.zip
  format  CSV *with* a header: u,i,ts,label,idx
  line    115,170,0.0,0,1
  note    the header is NOT the same as tgbl-wiki's — each adapter checks
          its own, so a changed format fails loudly
```
125,235 emails, 184 employees, 1,316 days.

#### `tgbl_uci` — students messaging in an online community

```
  file    tgbl-uci.zip
  format  CSV with header: u,i,ts,label,idx
  line    1,2,0,0,1
```
59,835 messages, 1,899 students, 194 days.
**This is the same data as SNAP's `CollegeMsg`** — verified identical event
count, node count and timestamps. Only one of the two is used.

#### `sx_mathoverflow` — the MathOverflow Q&A site

```
  file    sx-mathoverflow.txt.gz   (3.5 MB)
  format  USER1 USER2 TIME   (no header)
  line    1 4 1254192988
  time    real unix timestamp (seconds since 1970)
```
506,550 interactions, 24,818 users, 2,350 days — the longest span we have.

#### `bitcoin_otc` and `bitcoin_alpha` — two crypto trust networks

```
  file    soc-sign-bitcoinotc.csv.gz / soc-sign-bitcoinalpha.csv.gz
  format  RATER,RATED,RATING,TIME   (no header)
  line    6,2,4,1289241911.72836
          │ │ │        └── the time      ← column 3, NOT column 2!
          │ │ └── trust rating, −10 to +10
          │ └── who was rated
          └── who rated
```
otc: 35,592 ratings, 5,881 traders, 1,903 days.
alpha: 24,186 ratings, 3,783 traders, 1,901 days.

⚠️ **The trap in this file.** Every other file above puts the time in
column 2. These put it in column **3**. Reading column 2 gives a time span
of *0.0 days* instead of 1,903 — a silent, catastrophic error. A test now
locks the column number in place.

### Family B — "person → thing" (2 datasets, projection needed)

#### `tgbl_wiki` — people editing Wikipedia pages

```
  file    tgbl-wiki-v2.zip      39 MB zipped, 560 MB unzipped
  header  user_id,item_id,timestamp,state_label,comma_separated_list_of_features
  line    0,0,0.0,0,-0.17506251,-0.17667764,-0.93709077, ... (176 fields!)
```
That last "column" is really **172 numeric edit-features**. We read only the
first three fields and ignore the rest — which is why a 560 MB file loads in
a few seconds and never gets unzipped.
157,474 edits, 8,227 users, 1,000 pages, 31 days.

#### `decentraland` — voting in a blockchain organisation (DAO)

```
  file    dcl_votes.csv      13.3 MB, plain CSV
  columns Member, Snapshot ID, Created, Proposal Title, Choice #, Choice,
          Vote Weight, Total VP, MANA VP, Names VP, LAND VP, Delegated VP,
          L1 Wearables VP, Rental VP
  row     Member      = 0x30b1f4Bd5476906f38385B891f2c09973196b742
          Snapshot ID = QmbYNKMYJMrud9VzhsCDHZXbSD2t7HkbPzwtFCPL2dBvxv
          Created     = 2021-05-24T15:29:29.000Z
```
53,533 votes, 4,133 voters, 1,816 proposals, 705 days. This is a **frozen**
snapshot taken 30 April 2023 — the live export keeps growing, so only the
frozen copy reproduces these numbers.

---

## 5. How each dataset becomes TGAP input

TGAP needs exactly two things:

1. a **list of networkx graphs** (the snapshots), all with the *same* nodes
2. a **two-community split** of those nodes

Here is how each dataset gets there. Everything in this table was measured
in the 24 September 2026 run.

| Dataset | A node is | A link means | Window | Actors kept | Snapshots |
|---|---|---|---|---|---|
| `email_eu_core` | a person | they emailed each other | 40 days | 201 of 986 | 12 |
| `tgbl_enron` | an employee | they emailed each other | 60 days | 25 of 184 | 18 |
| `tgbl_uci` | a student | they messaged each other | 10 days | 120 of 1,899 | 16 |
| `sx_mathoverflow` | a user | one answered/commented the other | 120 days | 120 of 24,818 | 16 |
| `bitcoin_otc` | a trader | one rated the other's trust | 90 days | 120 of 5,881 | 14 |
| `bitcoin_alpha` | a trader | same | 90 days | 120 of 3,783 | 13 |
| `tgbl_wiki` | a **page** | the same user edited both | 2 days | 100 of 1,000 | 13 |
| `decentraland` | a **voter** | they voted on the same proposal | 1 month | 100 of 4,133 | 19 |

### The five things done to every dataset

**1. Direction is thrown away.** TGAP's measurements are undirected, so
"A emailed B" and "B emailed A" become the same link.

**2. Self-loops are thrown away.** Someone emailing themselves inflates
their connection count without expressing a tie to anyone.

**3. Repeats collapse.** 50 emails between two people inside one window
become **one** link. No weight is stored, because no TGAP measurement reads
link weights.

**4. Every actor appears in every snapshot**, sitting alone if inactive.
TGAP's anchor rule needs the node list to never change.
*Honest consequence:* snapshots are therefore never fully connected, so the
"cohesion" measurement is always exactly 0 and we do not use it.

**5. Extra columns are recorded as unused, not silently dropped.** The
bitcoin trust rating, Decentraland's voting power, Wikipedia's 172 features —
all named in `edge_attributes_available`, with `edge_weight_used: false`.

### The one extra thing done to the two bipartite datasets

A person→page file cannot be used directly. If we called "all people" one
community and "all pages" the other, then *every* link would cross between
them, so bridge width would just equal the total link count — a useless
duplicate of density.

So we **project onto one side**:

```
   BEFORE                          AFTER
   user1 → page A                  page A ──── page B
   user1 → page B                    (same user edited both)
```

For Wikipedia we project onto **pages**; for Decentraland onto **voters**.
This costs something and we say so: the links are now *deduced* rather than
observed, and the pair-building is expensive, which is why only the top 100
actors are kept.

### The one dataset that is different

`email_eu_core` does not need an algorithm to find its two communities. SNAP
publishes the **real department** of every person, so we take the two largest
departments — **109 people and 92 people** — and use *those* as the
communities. Bridge width then literally counts emails between two real
departments of a real organisation. It is the project's control case.

---

## 6. The output folder structure

```
output\real_data_v2\
│
├── temporal_evaluation\            ← USE THIS ONE (leakage-safe)
│   │
│   ├── summary.json                headline numbers for all 8 datasets
│   ├── comparison.csv              ★ all 8 datasets in one table
│   ├── comparison_observations.json  computed cross-dataset facts
│   ├── figures\                    3 pictures comparing datasets
│   │   ├── saturation_vs_trend_status.png
│   │   ├── noop_vs_bridge_width.png
│   │   └── concept_response_heatmap.png
│   │
│   ├── bitcoin_alpha\              ← one folder per dataset, 11 files + 6 pictures
│   ├── bitcoin_otc\
│   ├── decentraland\
│   ├── email_eu_core\
│   ├── sx_mathoverflow\
│   ├── tgbl_enron\
│   ├── tgbl_uci\
│   └── tgbl_wiki\
│
(A `descriptive\` folder appears beside it only if you run
`--mode descriptive`. Those results are deliberately NOT committed, so a
leakage-unsafe number cannot be quoted by accident.)
```

**142 files in total** = 8 datasets × (11 files + 6 pictures) + 6 comparison
files.

Inside each dataset folder:

```
  metadata.json                    1.7 KB   the facts about the dataset
  preprocessing_summary.json       2.3 KB   every decision + what it dropped
  graph_summary.csv                1.5 KB   one row per snapshot
  metrics.csv                      1.3 KB   the measurements over time
  tgap_results.csv                38.7 KB   ★ THE EXPLANATIONS (180 rows)
  transformation_feasibility.csv   3.8 KB   validity check 1 (30 rows)
  bridge_trend_status.csv          1.3 KB   validity check 2 (6 rows)
  transformation_diagnostics.csv   3.1 KB   did each change reach the graph?
  leakage.csv                      2.5 KB   did we change other things too?
  summary.json                     2.5 KB   headline numbers
  figures\                                  4 pictures
```

---

## 7. Every output file, column by column

### ★ `tgap_results.csv` — the results (180 rows)

180 = 6 models × 5 concepts × 3 sizes × 2 directions. **This is the file to
open.**

The columns come in four groups.

**Group 1 — what experiment is this?**

| Column | Meaning |
|---|---|
| `dataset` | which dataset |
| `analysis_mode` | `temporal_evaluation` (safe) or `descriptive` (not) — **check this first** |
| `snapshot_count` | how many snapshots the model saw |
| `model` | which of the 6 models was asked |
| `transformation` | which of the 5 concepts was changed |
| `direction` | `increase` or `decrease` |
| `requested_delta` | the size we asked for: 0.1, 0.25 or 0.5 |
| `delta_mode` | `relative` (a %) or `absolute` (own units — only Bridge Trend) |
| `seed` | 42, always |

**Group 2 — is this experiment trustworthy?** *(new; these are the gates)*

| Column | Meaning |
|---|---|
| **`valid_for_analysis`** | **`True` = usable. Filter on this before using anything.** |
| `transformation_status` | why not: `ok`, `edge_count_infeasible`, `saturated`, `wrong_direction` |
| `feasible` | did the change keep its promise to hold the link count fixed |
| `infeasible_reason` | if not, the measured reason in words |
| `edge_count_before` / `edge_count_after` | the total links, summed over snapshots |
| `edge_count_preserved` | `True` if those two match |
| `snapshots_violating_edge_count` | how many snapshots broke the promise |

**Group 3 — the actual result**

| Column | Meaning |
|---|---|
| `achieved_delta` | how much the concept **really** moved (graphs are chunky, so ≠ requested) |
| `baseline_prediction` | the model's answer **before** the change |
| `after_prediction` | the model's answer **after** |
| `prediction_change` | after − before |
| **`impact`** | **the explanation**: `prediction_change ÷ achieved_delta` |
| `normalizer` | `achieved` (good) or `requested` (fallback) — which divisor was used |
| `noop` | `True` = the change was too small to move even one link, so this row proves nothing |

> ⚠️ **If `valid_for_analysis` is `False`, the number columns are EMPTY on
> purpose** for the infeasible rows. You cannot accidentally use a number
> that was never written down.

### `graph_summary.csv` — one row per snapshot (12–19 rows)

| Column | Meaning |
|---|---|
| `snapshot_index` | 0, 1, 2, … oldest first |
| `label` | a readable date or day range, e.g. `2013-05-12` or `d160-d200` |
| `retained_nodes` | how many actors are in the graph (**not** the dataset's population) |
| `active_retained_nodes` | how many of them actually have a link in this snapshot |
| `edges` | number of links |
| `density` | how full the graph is, 0 to 1 |
| `average_degree` / `max_degree` | average / largest number of links per actor |
| `bridge_width` | **links between the two communities** — the CATALYST concept |
| `connected_components` | how many separate pieces the graph is in |
| `is_connected` | `True` if it is one piece (always `False` here — see §5 point 4) |

### `metrics.csv` — the four measurements over time

`snapshot_index`, `label`, then `bridge_width`, `density`, `centralization`,
`clustering`. This is the raw material the models read. Good for a line chart.

### `transformation_feasibility.csv` — validity check 1 (30 rows)

30 = 5 concepts × 3 sizes × 2 directions. Same for every model, so it is
computed once.

| Column | Meaning |
|---|---|
| `declares_edge_count_preservation` | does this concept even promise to hold the link count? (`Density` does not — changing it *is* its job) |
| `feasible` / `infeasible_reason` | the verdict and the measured cause |
| `snapshots_checked` / `snapshots_violating` | how many snapshots, how many broke |
| `strict_mode_raises` | did the second, independent check also fail? |
| `strict_mode_reason` | its message, naming the exact point of failure |
| **`strict_agrees_with_measurement`** | **must be `True` in all 30 rows** — the two checks agreeing is what makes the gate trustworthy |

### `bridge_trend_status.csv` — validity check 2 (6 rows)

Only the Bridge Trend concept has this, because only it reshapes history.

| Column | Meaning |
|---|---|
| `requested_direction` | +1 = we asked the trend to rise, −1 = to fall |
| `achieved_direction` | what actually happened |
| `slope_before` / `slope_after` / `slope_change` | the trend line, in links per step |
| `compounding_factor` | `(1+delta)^(T−1)` — how badly the oldest snapshot gets squeezed |
| `snapshots_saturated` / `fraction_saturated` | how many snapshots got stuck at the floor of 1 link |
| `min_bridge_width_before` / `max_bridge_width_before` | the bridge before |
| `min_bridge_width` / `max_bridge_width` | the bridge after |
| `status` | `ok` / `saturated` / `wrong_direction` / `no_property_change` |
| `valid_for_analysis` | `True` only when `status` is `ok` |

### `transformation_diagnostics.csv` — did the change reach the graph? (30 rows)

| Column | Meaning |
|---|---|
| `family` | `structural` (changes each snapshot) or `temporal` (reshapes history) |
| `snapshots_modified` / `modified_fraction` | in how many snapshots did anything change |
| `last_snapshot_modified` | did the **most recent** snapshot change? |
| `structurally_blocked` | `True` = the graph had no room to make this change |

> The `last_snapshot_modified` column explains a confusing case. Temporal
> concepts leave the last snapshot alone **on purpose**. For a structural
> concept the same observation means the graph **blocked** it — so the same
> fact means opposite things depending on `family`.

### `leakage.csv` — did we accidentally change other things? (20 rows)

5 concepts × 4 properties. `before`, `after`, `change` for each property.
TGAP's promise is *change one thing only*; this file is where you check that
promise instead of trusting it.

### `metadata.json` — the facts (30 keys)

Groups: identity (`dataset`, `source`, `description`), the exact file
(`raw_file`, `raw_bytes`, `raw_sha256_first_1mb` — a fingerprint so you can
prove you have the same file), **raw vs retained** (`raw_nodes`,
`retained_nodes`, `nodes_retained_pct`, and the same four for events), time
(`raw_span_days`, `evaluated_span_days`), shape (`graph_family`,
`graph_nodes_are`, `graph_edges_are`, `snapshot_interval`, `snapshot_count`),
and the weights declaration (`edge_weight_used`, `edge_sign_used`,
`edge_attributes_available`).

### `preprocessing_summary.json` — the honesty file (47 keys)

The one to show if someone asks "what did you throw away?". Key fields:

| Field | Meaning |
|---|---|
| `node_selection` | in words, how the actors were chosen |
| `node_selection_mode` | `temporal_train` / `full_period_descriptive` / `ground_truth_labels` |
| `selection_period` / `evaluation_period` | the two time windows |
| `pct_of_events_outside_selection_period` | how much data the evaluation half holds |
| **`future_information_used_for_node_selection`** | **must be `false` in the safe mode** |
| `community_mode` | where the two communities came from |
| `partition_sizes` | e.g. `[109, 92]` |
| `nodes_isolated_in_partition_graph` | actors with no link at all in the detection period |
| `events_dropped_selection_period` / `_node_filter` / `_self_loops` | what was dropped, and why |
| `unique_window_edges` | links after repeats collapsed |
| `cohesion_usable` | `false`, with the reason attached |

### `summary.json` — the headline (42 keys)

The numbers you would put on a slide: retention, partition, bridge-width
range, `explanation_rows` / `valid_rows` / `invalid_rows_by_status`,
`largest_absolute_impact_valid_rows`, and
`expected_invariance_history_only_transformations` (which carries a written
statement explaining that this is a *verified expectation*, not a discovery).

### The 4 pictures per dataset

| File | Shows |
|---|---|
| `activity_over_time.png` | links and bridge width across snapshots |
| `metric_trajectories.png` | all four measurements, rescaled to share one axis |
| `impact_by_transformation.png` | ★ the explanation as a bar chart — **valid rows only** |
| `delta_sensitivity.png` | does the answer change when the nudge gets bigger? |

---

## 8. Reading one real row, end to end

A genuine row from `sx_mathoverflow\tgap_results.csv`, 24 September 2026:

```
  model                  trend_bridge_width
  transformation         Bridge Width
  direction              increase
  requested_delta        0.1
  ─────────────────────────────────────────── the validity gates
  feasible               True
  edge_count_before      5020
  edge_count_after       5020          ← promise kept, exactly
  transformation_status  ok
  valid_for_analysis     True          ← usable
  ─────────────────────────────────────────── the result
  achieved_delta         0.1016...     ← we asked for 10%, got 10.16%
  baseline_prediction    -11.0999...
  after_prediction       -12.0499...
  prediction_change      -0.9500...
  impact                 -9.3464...
  normalizer             achieved
  noop                   False
```

**In words:** we asked to widen the bridge between MathOverflow's two user
groups by 10%. Because graphs move in whole links, we actually got 10.16%.
The total number of links stayed at exactly 5,020 — so this really was "the
same activity, routed differently", not "more activity".

The model, which predicts the trend of bridge width, moved from −11.10 to
−12.05. Dividing the drop by the change we made gives **−9.35**.

**Read it as:** *this model is strongly sensitive to bridge width, and in the
negative direction* — widening the bridge now makes it predict a more
steeply falling trend. That is a statement about **the model's behaviour**,
not about mathematicians. Nothing here says one thing *caused* another.

---

## 9. How to run it

From `C:\catalyst\tgap`, on the `real-data` branch.

```bash
# 0. the files only exist on this branch
git switch real-data

# 1. get the raw data — ONCE. Already done on your machine.
python -m realdata.download

# 2. run TGAP on all 8 datasets          ⏱ 3 minutes
python -m realdata.run_real_data

# 3. compare the 8 against each other     ⏱ 10 seconds
python -m realdata.compare_datasets

# 4. check the code is healthy             ⏱ 40 seconds
python -m unittest tests.test_realdata
```

**Variations**

```bash
# one dataset only                          ⏱ 17 seconds
python -m realdata.run_real_data bitcoin_otc

# two of them
python -m realdata.run_real_data email_eu_core tgbl_enron

# the full-period version (NOT leakage-safe; for describing data only)
python -m realdata.run_real_data --mode descriptive
python -m realdata.run_real_data --mode both

# the whole test suite                      ⏱ 1 min 40
python -m unittest discover -s tests
```

Valid dataset names: `tgbl_wiki`, `decentraland`, `email_eu_core`,
`tgbl_enron`, `tgbl_uci`, `sx_mathoverflow`, `bitcoin_otc`, `bitcoin_alpha`.

**Notes**

- **Do not unzip anything.** The `.zip` and `.gz` files are read as they
  are. `tgbl-wiki-v2.zip` is 39 MB zipped and 560 MB unzipped; we only need
  3 of its 176 columns.
- **No internet needed** after step 1.
- **Same seed (42)** everywhere, so results repeat — with one known
  exception, in §11.
- ⚠️ After running the **full** test suite (`discover -s tests`), run
  `git restore -- output/paper/`. Those tests overwrite that folder with
  test-sized fixtures. This is a known bug.

---

## 10. How to tell a run went well

Four things to look at. Nothing else is needed.

**1. In the printed output**, every dataset must show:

```
  future info used for selection: False        ← no cheating with time
  strict-mode / measurement agreement: 30/30   ← the two gates agree
```

**2. Valid rows** should be 130–162 of 180 per dataset. Measured on
24 September 2026:

| Dataset | valid / 180 |
|---|---|
| `sx_mathoverflow` | 162 |
| `tgbl_wiki` | 144 |
| `decentraland` | 144 |
| `tgbl_enron` | 144 |
| `email_eu_core` | 138 |
| `tgbl_uci` | 138 |
| `bitcoin_alpha` | 138 |
| `bitcoin_otc` | 132 |
| **total** | **1,140 of 1,440** |

**3. The tests** must say `OK`. 158 tests, 2 skipped on purpose (an abstract
base class, and one check that does not apply to the department-labels
dataset).

**4. `comparison_observations.json`** should report
`datasets_where_expected_invariance_verified: 8` and
`strict_mode_disagreements_total: 0`.

---

## 11. Known problems and dates

### Dates

| Date | What |
|---|---|
| 11–17 Sep 2026 | TGAP core built, synthetic evaluation (RQ1–RQ8) |
| 21 Sep 2026 | Iván's separate stock-correlation graph work (`finance/`) |
| 24 Sep 2026 | real-data layer; methodological clean-up; **the run described here** |
| 30 Apr 2023 | the date the Decentraland export was frozen |

### Problems, in order of importance

1. **⚠️ "Change one thing only" sometimes breaks.** On real data the
   link-count promise fails in **31 of 240** settings, on all 8 datasets. It
   is now *reported and excluded*, not repaired — the three possible repairs
   each change what the method measures, so the choice was left to the team.

2. **⚠️ Bridge Trend has too few usable rows** — only **36 of 288**. Do not
   quote Bridge Trend magnitudes. The cause: reshaping history squeezes old
   snapshots below the floor of 1 link, and the results get marked
   `saturated`.

3. **⚠️ One result is not perfectly repeatable.** Re-running changes about
   **40 of 1,440 rows**, all of them `Density` + `increase`. Cause: networkx
   lists "pairs not yet connected" in an order that depends on how Python
   scrambles text labels, which differs in every program run. The synthetic
   experiments are unaffected because they use whole-number labels. **The fix
   is one line** and has not yet been applied.

4. **The full test suite overwrites `output/paper/`.** Run
   `git restore -- output/paper/` afterwards. Also a one-line fix, not yet
   applied.

5. **We keep very little** — a median of 4.75% of actors and 3.29% of
   events. `bitcoin_otc` and `bitcoin_alpha` keep only ~415 events each;
   treat their numbers as indicative.

6. **`tgbl_enron` keeps only 25 actors**, split 8/17. Small for a
   two-community analysis.

7. **Two datasets reach bridge width 0** (`tgbl_wiki`, `tgbl_enron`), where
   a percentage change of the bridge has no meaning.

8. **Window sizes and actor counts were chosen by measurement, not
   optimised.** Nothing shows the conclusions survive different choices.

9. **Cohesion is unusable** here, for the reason in §5 point 4.

10. **One random seed (42)** on real data.

11. **No trained AI model.** All six models are simple measurement-based
    baselines. A graph neural network would plug into the same socket but is
    not built.

12. **Real data shows applicability, not correctness.** There is no ground
    truth on real data. Proof of correctness comes from the synthetic
    experiments in `paper_evaluation.py`.

---

*To reproduce everything in this document:*

```bash
cd C:\catalyst\tgap
git switch real-data
python -m realdata.run_real_data
python -m realdata.compare_datasets
python -m unittest tests.test_realdata
```
