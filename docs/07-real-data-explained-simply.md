# Real Data for TGAP — Explained in Simple Words

> **What this is:** everything about the real-data part of the project.
> Which datasets we use, how I found them, what I had to decide, how to run
> them yourself, and what we learned.
> **Style:** very simple words. Science explained in 🔬 boxes.
> **Promise:** every number here came from running the code. Nothing invented.
>
> **Version 2 — after the methodological clean-up.** The first version of
> this work had three real problems: it let the future leak into the past, it
> reported a filtered subset as if it were the whole dataset, and it counted
> broken experiments as if they had worked. All three are fixed. Section 15
> lists exactly what changed and which old numbers are now wrong.
>
> Other documents: [01](01-TSAP-explained-simply.md) (the idea),
> [06](06-TGAP-complete-guide-A-to-Z.md) (all the code),
> [03](03-TGAP-technical-audit.md) (design decisions).

---

## Table of contents

1. [Why we needed real data at all](#1-why-we-needed-real-data-at-all)
2. [The 8 datasets, in one table](#2-the-8-datasets-in-one-table)
3. [How I found them](#3-how-i-found-them)
4. [The datasets we did NOT use, and why](#4-the-datasets-we-did-not-use-and-why)
5. [Problem 1: real data is the wrong shape](#5-problem-1-real-data-is-the-wrong-shape)
6. [Problem 2: we were cheating with time](#6-problem-2-we-were-cheating-with-time)
7. [Problem 3: some experiments were broken and we counted them anyway](#7-problem-3-some-experiments-were-broken-and-we-counted-them-anyway)
8. [The six decisions I had to make](#8-the-six-decisions-i-had-to-make)
9. [Each dataset, one by one](#9-each-dataset-one-by-one)
10. [The special one: real departments](#10-the-special-one-real-departments)
11. [How to run it yourself](#11-how-to-run-it-yourself)
12. [What the output files mean](#12-what-the-output-files-mean)
13. [Mistakes that checking things caught](#13-mistakes-that-checking-things-caught)
14. [What we learned](#14-what-we-learned)
15. [What changed in version 2](#15-what-changed-in-version-2)
16. [What is still broken](#16-what-is-still-broken)
17. [Where the code lives](#17-where-the-code-lives)

---

## 1. Why we needed real data at all

Until now the whole project ran on **made-up graphs**. That was the right
choice, and doc 06 explains why: with invented data *we* decide the truth,
so we can check whether TGAP tells it. Like testing a weighing scale with a
known 1 kg weight instead of a mystery object.

But a made-up graph is tidy. Real networks are messy:

- people appear and disappear
- some parts are very crowded, some almost empty
- the numbers are much bigger
- nothing is balanced or neat

So the real question is: **does the method survive contact with real data?**
That is all the real-data part is for.

> ⚠️ **Very important, say this to your professor.**
> Real data does **not** prove TGAP is correct. On real data nobody knows
> the true answer, so there is nothing to compare against. Real data shows
> that TGAP **works on messy input** and produces readable results. Proof of
> correctness still comes from the made-up experiments, where the true answer
> is known.
>
> And nothing here is a claim about *causes*. We never say "wider bridges
> cause X". We say "the model's prediction responds to this change".

---

## 2. The 8 datasets, in one table

All real, all downloaded automatically, all working. **We did not add or
remove any dataset in version 2** — the clean-up was about method, not size.

Two numbers per dataset now, always: what the **file** contains, and what
**we actually use**. Mixing those two up was one of the old mistakes.

| Dataset | What it is | Events in file | Events used | People in file | People used |
|---|---|---|---|---|---|
| `email_eu_core` | emails inside a European research institute | 332,334 | 12,599 | 986 | 201 |
| `tgbl_enron` | emails inside the Enron company | 125,235 | 18,510 | 184 | 25 |
| `tgbl_uci` | private messages between students | 59,835 | 1,663 | 1,899 | 120 |
| `sx_mathoverflow` | questions/answers on MathOverflow | 506,550 | 10,685 | 24,818 | 120 |
| `bitcoin_otc` | trust ratings between Bitcoin traders | 35,592 | 414 | 5,881 | 120 |
| `bitcoin_alpha` | same, on a different Bitcoin platform | 24,186 | 415 | 3,783 | 120 |
| `tgbl_wiki` | people editing Wikipedia pages | 157,474 | 13,267 | 1,000 pages | 100 pages |
| `decentraland` | people voting in a DAO (blockchain organisation) | 53,533 | 4,996 | 4,133 | 100 |

**Six different worlds:** company email, university email, student chat,
a Q&A website, crypto trust, wiki editing, and online governance. If a
result shows up in all of them, it is probably about the method — not about
one dataset.

Together they produce **1,440 experiments**. After the new checks
(section 7), **1,140 of them count** and 300 are thrown out.

> 🔎 Yes, the "events used" numbers are small. Two things cause that: we keep
> only the most active people (section 8, decision 3), and we now only use
> the **later** part of each dataset (section 6). The typical dataset keeps
> about **4.75%** of its people and **3.29%** of its events. That is a real
> cost and it is printed in every single run.

---

## 3. How I found them

Not by guessing. Step by step:

**Step 1 — start from what you asked for.** You named TGB (`tgbl-coin`,
`tgbl-wiki`, `tgbl-review`, `tgbl-flight`) and Decentraland.

**Step 2 — find the real download links.** My first guess at the TGB
addresses returned **404 Not Found**. So instead of guessing again, I opened
TGB's own source code on GitHub (the file `tgb/utils/info.py`) and copied
the links from the list the official program itself uses. Lesson: read the
source, do not guess.

**Step 3 — check the sizes before downloading.** There is a way to ask a
web server "how big is this file?" without downloading it. The answers:

```
  tgbl-wiki       40.9 MB     ← fine
  tgbl-review    539.6 MB     ← big
  tgbl-coin     1284.5 MB     ← too big
  tgbl-flight   1281.9 MB     ← too big
```

That is how the choice was made: by measuring, not by opinion.

**Step 4 — look inside the Decentraland repository.** It had a file called
`DATA.md` that describes every column. Reading documentation first saved a
lot of guessing.

**Step 5 — realise something was missing.** Both of your datasets have the
same shape problem (section 5), which forces us to throw away most of the
data. So I went looking for datasets with a **better** shape, and found a
well-known free collection: **SNAP** (Stanford Network Analysis Project). I
checked several candidates the same way — sizes first, then the real file
contents.

**Step 6 — keep the ones that genuinely fit**, reject the rest with a
written reason (section 4).

> ### 🔬 Science box 1 — Why "I measured it" beats "I think"
> Every choice above is written down with the number that caused it. That
> is what makes a method **reproducible**: another researcher can check your
> reasoning, not just your result. A rejected dataset with a measured reason
> is good science. A rejected dataset with no reason looks like hiding
> something.

---

## 4. The datasets we did NOT use, and why

All reasons are recorded in the code (`realdata/download.py`) and checked by
a test, so they cannot quietly disappear.

| Dataset | Why not |
|---|---|
| `tgbl-coin` | 1,284 MB, ~22 million events — too big for a prototype |
| `tgbl-flight` | 1,282 MB, ~67 million events — too big |
| `tgbl-review` | 540 MB — usable, but far more than needed |
| `tgbl-subreddit` | 258 MB, and same shape as datasets we already have |
| `tgbl-lastfm` | 416 MB, same reason |
| `SNAP sx-askubuntu` | only 7 MB, but it is another Q&A site — MathOverflow already covers that |
| `SNAP wiki-talk` | 48 MB, but adds no new *type* of network |
| **`SNAP CollegeMsg`** | **it is the same data as `tgbl-uci`** (see below) |

The CollegeMsg case is worth telling. I loaded both and compared:

```
  CollegeMsg : 59,835 events, 1,350 senders, 193.7 days
  tgbl-uci   : 59,835 events, 1,350 senders, 193.7 days
  first timestamps: 0, 114878, 373430, 398658, 398795   ← identical in both
```

They are the **same dataset under two names**. Using both would have meant
counting one dataset twice and pretending we had more evidence than we do.
So only one is used, and the duplicate is documented.

---

## 5. Problem 1: real data is the wrong shape

This is the most important idea in this document. Take your time here.

### Two kinds of network

**Kind A — "two different sorts of thing" (bipartite).**
A person edits a *page*. A voter votes on a *proposal*. There are two
separate groups, and links only go **between** them, never inside:

```
   people          pages
     P1 ────────►  page A
     P2 ────────►  page A
     P2 ────────►  page B
```
People never link to people. Pages never link to pages.

**Kind B — "one sort of thing" (unipartite).**
A person emails a *person*. A trader rates a *trader*. Everyone is the same
kind of thing, and links go between them directly:

```
     A ──── B
     │      │
     C ──── D
```

### Why this breaks TGAP

TGAP's most important idea is **bridge width**: split the network into two
communities, and count the links **between** them. A thin bridge is fragile;
a wide bridge is strong.

Now look at Kind A again. If I say "community 1 = all people, community 2 =
all pages", then **every single link crosses between the two communities**.
So bridge width = total number of links. It becomes an exact copy of another
measurement (density) and tells us **nothing new**. The idea collapses.

### The fix: turn Kind A into Kind B

Instead of "person → page", we build "page ↔ page":

> Two pages are connected if the **same person edited both** in that time
> window.

This is called a **one-mode projection**. Now everything is one kind of
thing, communities are real groups, and bridge width means something.

```
   BEFORE (Kind A)              AFTER (projection, Kind B)
   P1 ──► page A                page A ──── page B
   P1 ──► page B                  (because P1 edited both)
```

### But the fix costs something

Two real costs, and I report both:

1. **We throw data away.** Making all those pairs is expensive, so we keep
   only the most active 100–120 actors.
2. **The links are invented, not observed.** Nobody observed "page A relates
   to page B" — we deduced it. That is a weaker kind of evidence.

### Which is why I added six new datasets

The six new ones are **already Kind B**. Email is person→person. Trust
ratings are trader→trader. So:

- **no projection needed** — the links are really there
- bridge width counts **real observed** links

I checked this properly rather than assuming. If sources and destinations are
the same kind of thing, the two lists of names should overlap heavily:

```
  email-Eu-core    81% overlap    → same kind of thing ✓
  tgbl-enron       98% overlap    → same kind of thing ✓
  bitcoin-alpha    86% overlap    → same kind of thing ✓
```

So the project now has **two families side by side**, which is useful in
itself: if a finding appears in both, it is not an artefact of the
projection trick.

---

## 6. Problem 2: we were cheating with time

**This is the most important fix in version 2.** Read it slowly — it is the
kind of mistake a reviewer looks for first.

### What we were doing wrong

We keep only the most active 100–120 people. The question is: *active when?*

Version 1 answered "active over the whole dataset". Picture a dataset
covering four years:

```
 2018 ─────── 2019 ─────── 2020 ─────── 2021
                    ▲
       we picked the people who were busiest
       across ALL FOUR YEARS — including 2021
```

Then we put those people into the **2018** snapshot and asked the model to
explain it. But we chose them using information from 2021. Somebody looking
at 2018 in real life could not possibly know who would be famous in 2021.

That is called **look-ahead** or **leakage**: information from the future
sneaking into a picture of the past. It quietly makes results look better
than they are, because the cast of characters was chosen with hindsight.

The same problem applied to the **communities**. We glued all four years
together into one big graph and found the two groups there — again using
2021 to decide what the groups were in 2018.

### How it is fixed

The dataset is cut in two, by time:

```
 |◄─ first 20% ─►|◄──────────── remaining 80% ────────────►|
   SELECTION          EVALUATION
   period             period

   used ONLY to:      used ONLY to:
    • pick the people   • build the snapshots TGAP explains
    • find the two
      communities

   The two periods never overlap, so nothing from the
   evaluation period can affect who was chosen.
```

The people and the two communities are decided once, in the early period,
and then **frozen** — they do not change again. So no future information can
possibly get in.

### Both ways are kept, and always labelled

We did not delete the old behaviour; we labelled it. Every result file now
carries an `analysis_mode` field with one of two values:

| Mode | What it does | Safe? |
|---|---|---|
| `temporal_evaluation` | the split above — **this is the default** | ✅ yes |
| `descriptive` | the old way: use everything | ❌ no, and it says so |

The old way is still useful for **describing** a dataset ("how big did this
DAO get?"), which does not require any prediction. It must never be used for
the scientific results. Every file says which mode made it, so the two can
never be mixed up by accident.

### Why 20% and not something else

I did not just pick 20% and hope. I measured what happens at 20%, 30%, 40%
and 50% on the four weakest datasets:

| | 20% | 30% | 40% | 50% |
|---|---|---|---|---|
| `tgbl_enron` — people kept | 25 | 43 | 100 | 120 |
| `bitcoin_otc` — links per snapshot | 9 | 7 | 15 | 17 |
| `bitcoin_alpha` — links per snapshot | 12 | 9 | 17 | 21 |
| `tgbl_uci` — widest bridge | 74 | 13 | 17 | 10 |

A bigger selection period barely helps Bitcoin and actively **hurts**
`tgbl_uci`, while eating into the part we are allowed to evaluate. So 20%
stays, as a fixed written-down constant, not a knob I tuned until the
results looked nice.

### The honest cost: doing it properly makes everything harder

The people who are busiest early are often quiet later. Real communities turn
over. So the safe mode gives us **smaller, thinner graphs**:

| Dataset | snapshots (safe / old) | events used (safe / old) | links per snapshot (safe / old) |
|---|---|---|---|
| `decentraland` | 19 / 24 | 4,996 / 23,543 | 299 / 1,230 |
| `tgbl_wiki` | 13 / 16 | 13,267 / 43,764 | 19 / 141 |
| `email_eu_core` | 12 / 16 | 12,599 / 16,643 | 175 / 180 |
| `tgbl_enron` | 18 / 22 | 18,510 / 99,745 | 40 / 158 |
| `tgbl_uci` | 16 / 20 | 1,663 / 13,602 | 13 / 40 |
| `sx_mathoverflow` | 16 / 20 | 10,685 / 35,392 | 236 / 622 |
| `bitcoin_otc` | 14 / 21 | 414 / 2,950 | 9 / 97 |
| `bitcoin_alpha` | 13 / 20 | 415 / 2,883 | 12 / 102 |

Two things stand out:

- **`email_eu_core` hardly changes** (175 vs 180 links). That is because its
  people come from real department labels, not from an activity ranking — so
  it never had the leakage problem in the first place (section 10).
- **`tgbl_enron` loses the most people**: only **25** employees are active in
  the first 20% of its 1,316 days, so there are not even 120 candidates to
  choose from.

> ### 🔬 Science box 2 — Why leakage matters so much
> In machine learning, *leakage* means your setup accidentally shows the
> model something it would not have in real life. It is one of the most
> common reasons published results fail to reproduce: the number is real, but
> it was obtained in an impossible situation. The standard cure is exactly
> what we did — split by **time**, fit everything on the earlier part, and
> evaluate only on the later part. The giveaway that we did it right: the
> numbers got *worse*. A leakage fix that improves your results is usually
> not a leakage fix.

---

## 7. Problem 3: some experiments were broken and we counted them anyway

TGAP's central promise is *change one thing, hold everything else still*. For
bridge width that promise is concrete:

```
   add 1 link between the two communities
 + delete 1 link inside a community
 ──────────────────────────────────────
 = the total number of links did not change
```

That is what makes the answer meaningful: the model sees the **same amount of
activity, routed differently**. If the total changed too, we could not tell
whether the model reacted to the new routing or simply to *more activity*.

### On real data the payment sometimes cannot be made

Sometimes there is no link inside a community left to delete. Sometimes there
is no unconnected pair left to add. Version 1 just… carried on, under-paid,
and reported the result as if nothing had happened.

Version 2 **refuses to hide it**. Every setting is checked before it is
trusted, and the checking is done twice, two different ways:

1. **By measurement** — run the change, then count the links before and
   after. If they differ, the promise was broken.
2. **By asking the code to fail loudly** — the transformation can be put in
   `strict` mode, where it stops with an error at the exact moment the
   payment falls short, and reports the numbers that prove it.

Those two methods agreed **480 times out of 480**. That agreement is what
makes the check trustworthy rather than just reassuring.

Broken settings get a label, a written reason, and — importantly — **their
numbers are left blank in the results file**. You cannot accidentally use a
number that was never written down.

### The second broken case: the history-reshaping change

One change ("Bridge Trend") reshapes the *past*: it walks backwards through
time, dividing each snapshot's bridge width by a factor. Over a long history
that factor multiplies up and the older numbers get tiny. The code has a
floor — it never removes the very last link — so many old snapshots get
**stuck at exactly 1**. Once enough of them are stuck, the reshaping can do
the **opposite** of what was asked.

Version 2 detects this and gives every setting one of four labels:

| Label | Meaning | Counts as a result? |
|---|---|---|
| `ok` | worked as asked, nothing got stuck | ✅ yes |
| `saturated` | right direction, but some snapshots hit the floor | ❌ no |
| `wrong_direction` | it did the opposite of what we asked | ❌ no |
| `no_property_change` | nothing moved at all | ❌ no |

### What the checks cost us

| | safe mode | old mode |
|---|---|---|
| experiments run | 1,440 | 1,440 |
| **experiments that count** | **1,140** (79%) | 1,128 (78%) |
| thrown out: broken link-count promise | 186 | — |
| thrown out: stuck/backwards history | 114 | — |
| **usable "Bridge Trend" rows** | **36 of 288** | **6 of 288** |

That last line is the uncomfortable one and it deserves to be said out loud:
**only 1 in 8 of our Bridge Trend experiments survives the check** in the
safe mode, and 1 in 48 in the old mode. Any statement about Bridge Trend
numbers rests on very little. The other four changes are mostly fine
(240–288 usable rows each).

> ### 🔬 Science box 3 — Why throwing results away is the honest move
> It is tempting to "repair" a broken experiment — cap the request, borrow a
> link from somewhere else, nudge the numbers. But every repair silently
> changes *what you are measuring*, so you end up reporting a number for a
> concept you did not define. Marking the experiment invalid and excluding it
> keeps the definition intact. Fewer results, but each one means what it says.

---

## 8. The six decisions I had to make

Real data always needs decisions. The rule I followed: **never decide
silently**. Every one is written in the code and saved into
`preprocessing_summary.json` on every run.

### Decision 1 — project bipartite data onto one side
Explained in section 5. For Wikipedia I project onto **pages**; for
Decentraland onto **voters**.

*Why pages and not people for Wikipedia?* I measured both. People-to-people
was nearly empty — about 70 active people but only **34 links** per day,
because two Wikipedia editors rarely touch the same page on the same day.
Page-to-page was much richer. So the measurement chose, not me.

### Decision 2 — every snapshot contains every node
In real life, someone active in March may vanish in April. But TGAP needs the
node list to stay the same in every snapshot (that is its "anchor rule" —
hold everything still except the one thing you are changing). So I include
everybody in every snapshot, and people who did nothing simply sit there with
no links.

**Honest consequence:** because inactive nodes are floating alone, the
snapshots are never fully connected. That makes one measurement (cohesion)
always exactly 0, so we **do not use cohesion** on real data. Better to say
that plainly than to publish a column of zeros.

### Decision 3 — keep only the most active actors, and always show both counts
Because the projection cost grows very fast (see section 5), we keep the top
100–120. This throws data away — so every report now carries **four**
numbers instead of two: people in the file, people kept, events in the file,
events kept, plus the percentages. There is no longer a column anywhere
called just "nodes"; it is called `retained_nodes`, and a test fails if
anyone renames it back.

### Decision 4 — which actors, chosen using which period
The whole of section 6. In the default mode, the ranking sees only the first
20% of time.

### Decision 5 — find the communities once, from the same early period
If I looked for communities in every snapshot separately, the groups would
keep changing. Then when bridge width changed, I would not know whether the
*network* changed or the *algorithm changed its mind*. So the two communities
are found **once** and frozen.

Version 2 changes *where* they are found: in the early selection period only,
not in the whole dataset (section 6). Three possible sources, and each run
says which one it used:

| `community_mode` | Meaning |
|---|---|
| `temporal_train` | found in the early period only — the default |
| `full_period_descriptive` | found using everything — not safe, labelled |
| `ground_truth_labels` | not found at all; real departments (section 10) |

**One detail worth knowing:** somebody can be in our list of kept people but
have no links at all in the early period. They still need to belong to one of
the two communities, because "count the links between the groups" needs every
node to be on a side. The rule is simple and automatic: side A is the biggest
group the algorithm found, and side B is *everybody else* — so a person with
no early links lands in side B by default. The code **reports how many such
people there were** (`nodes_isolated_in_partition_graph`), rather than
quietly deciding and saying nothing. It is not a hypothetical case:
`tgbl_wiki` has **24** pages with no co-edit link in the early period, and
`email_eu_core` has **35** people who neither send nor receive anything in
the evaluated period.

### Decision 6 — ignore extra columns, and say so
The Bitcoin files contain a trust **rating** from −10 to +10 — which carries
both a *sign* (do I trust or distrust you) and a *size* (how much). The
Decentraland file contains vote choice and six voting-power columns.

We **do not use any of them**, because no current TGAP measurement reads link
weights. Every dataset's metadata now states this in three fields:

```
   edge_weight_used            : false
   edge_sign_used              : false
   edge_attributes_available   : "RATING, integer -10..+10 in column 2,
                                  carrying BOTH a sign and a magnitude..."
```

A test even checks that the links in every snapshot really carry no hidden
weight. This is about **transparency, not expansion**: we are not claiming
the data is unweighted, we are stating that we ignored the weights.

### How long is one snapshot?
Chosen by measurement. The windows were not changed in version 2, so the safe
mode simply gets fewer of them (80% of the time span):

| Dataset | Window | Snapshots (safe / old) |
|---|---|---|
| tgbl-wiki | 2 days | 13 / 16 |
| decentraland | 1 month | 19 / 24 |
| email-Eu-core | 40 days | 12 / 16 |
| tgbl-enron | 60 days | 18 / 22 |
| tgbl-uci | 10 days | 16 / 20 |
| sx-mathoverflow | 120 days | 16 / 20 |
| bitcoin-otc | 90 days | 14 / 21 |
| bitcoin-alpha | 90 days | 13 / 20 |

---

## 9. Each dataset, one by one

| Dataset | A node is… | A link means… | Family |
|---|---|---|---|
| `email_eu_core` | a person at the institute | they emailed each other | observed |
| `tgbl_enron` | an Enron employee | they emailed each other | observed |
| `tgbl_uci` | a student | they sent a private message | observed |
| `sx_mathoverflow` | a MathOverflow user | one answered/commented on the other | observed |
| `bitcoin_otc` | a Bitcoin trader | one gave the other a trust rating | observed |
| `bitcoin_alpha` | a trader (other platform) | same | observed |
| `tgbl_wiki` | a **Wikipedia page** | the same person edited both | projected |
| `decentraland` | a **voter** | they voted on the same proposal | projected |

The measured results, **safe mode**:

| Dataset | People kept | Events kept | Density | Bridge width | Useless rows |
|---|---|---|---|---|---|
| `decentraland` | 2.4% | 9.3% | 0.060 | 36 – 493 | 0.0% |
| `tgbl_wiki` | 10.0% | 8.4% | 0.004 | 0 – 29 | 12.5% |
| `email_eu_core` | 20.4% | 3.8% | 0.009 | 11 – 139 | 0.0% |
| `tgbl_enron` | 13.6% | 14.8% | 0.135 | 0 – 28 | 8.3% |
| `tgbl_uci` | 6.3% | 2.8% | 0.002 | 1 – 74 | 26.1% |
| `sx_mathoverflow` | 0.5% | 2.1% | 0.033 | 29 – 386 | 0.0% |
| `bitcoin_otc` | 2.0% | 1.2% | 0.001 | 1 – 25 | 27.3% |
| `bitcoin_alpha` | 3.2% | 1.7% | 0.002 | 1 – 25 | 26.1% |

("Useless rows" = the share of *valid* experiments where the requested change
was too small to move even one whole link. Explained in section 14,
finding 2.)

**Two honest observations about this table.** `tgbl_wiki` and `tgbl_enron`
reach snapshots with **bridge width 0** — no links at all between the two
groups — where "increase the bridge by 10%" has no meaning. And the three
sparsest datasets (`tgbl_uci`, `bitcoin_otc`, `bitcoin_alpha`) waste about a
quarter of their experiments on changes too small to happen. Both facts are
counted and printed.

---

## 10. The special one: real departments

`email_eu_core` is the most valuable dataset in the set, and it is worth a
slide of its own.

For all the others, we **guess** the two communities with an algorithm. For
this one, we do not have to. SNAP publishes a second small file giving the
**real department** of all 1,005 people — 42 departments in a real research
institute. (986 of those people actually appear in the email log; that is the
number our reports call `raw_nodes`.)

So I took the two biggest departments:

```
   department 4  → 109 people
   department 14 →  92 people
```

and used **them** as the two communities. Nicely balanced, and completely
real.

This means **bridge width literally counts emails between two real
departments in a real organisation.** No algorithm's opinion involved.

It also makes this dataset the one that is **immune to the time-cheating
problem** of section 6. Which department you belong to is a fact about you,
not a statistic computed from the emails — so using it cannot leak the
future. That is why its `analysis_mode` says the safe thing in *both* modes,
and why its numbers barely change between them.

> ### 🔬 Science box 4 — Why this is called a control case
> In science a **control** is the case where you know the answer, used to
> check your instrument. Every other dataset here relies on a
> community-detection algorithm; if that algorithm were bad, our bridge
> widths would be meaningless everywhere and we would never know. This one
> dataset does not depend on it. If results look similar here and elsewhere,
> the detection algorithm is probably doing a reasonable job.

---

## 11. How to run it yourself

Run from the `tgap` folder.

```bash
# 1. Download all the raw files (once; about 100 MB total)
python -m realdata.download

# 2. Run TGAP the SAFE way on all 8 datasets  ← the scientific results
python -m realdata.run_real_data

# 3. Compare all 8 datasets against each other
python -m realdata.compare_datasets

# 4. Check everything still works (269 automatic tests, about 100 seconds)
python -m unittest discover -s tests
```

To also produce the old full-period description, for comparison:

```bash
python -m realdata.run_real_data --mode descriptive
python -m realdata.run_real_data --mode both
python -m realdata.compare_datasets --mode both
```

Want just one dataset? Name it:

```bash
python -m realdata.run_real_data decentraland
python -m realdata.run_real_data email_eu_core tgbl_enron
```

Valid names: `tgbl_wiki`, `decentraland`, `email_eu_core`, `tgbl_enron`,
`tgbl_uci`, `sx_mathoverflow`, `bitcoin_otc`, `bitcoin_alpha`.

**Things worth knowing:**

- **The default is the safe mode.** You have to ask explicitly for the
  unsafe one, and it labels itself in every file it writes.
- **Downloads are cached.** After step 1 everything works offline.
- **The tests skip politely.** If a dataset is not downloaded, its tests are
  skipped instead of failing — so the test suite never needs the internet.
- **Same numbers every time.** Everything uses a fixed random seed (42), so
  you and your professor get identical results.
- **Raw files are not in git** (they are big). They come back from step 1.
- **Only the safe mode's results are stored.** They are in
  `output/real_data_v2/temporal_evaluation/`. Descriptive-mode results are
  NOT committed - run `--mode descriptive` to regenerate them. That way a
  leakage-unsafe number cannot be quoted by accident. The old version-1
  results were deleted; git history still has them.

> ### 🔬 Science box 5 — Random seeds
> Computers make "random" choices from a formula that starts at a number
> called a **seed**. Same seed → same choices → same answer, forever. This is
> why anyone can reproduce your numbers. Every random choice in this project
> is seeded.

---

## 12. What the output files mean

Everything lands in `output/real_data_v2/<mode>/` — **236 files** across both
modes: 10 files plus 4 pictures for each of the 16 dataset-runs (8 datasets
× 2 modes = 224), plus 6 comparison files per mode.

```
output/real_data_v2/
├── temporal_evaluation/     ← the safe mode: use these numbers
│   ├── summary.json
│   ├── comparison.csv
│   ├── comparison_observations.json
│   ├── figures/             (3 pictures comparing datasets)
│   └── bitcoin_alpha/  ...  (one folder per dataset)
└── descriptive/             ← the old full-period view, clearly labelled
```

For each dataset:

| File | What it holds |
|---|---|
| `metadata.json` | the facts: events in file vs used, nodes in file vs used, dates, and whether weights were used |
| `preprocessing_summary.json` | every decision, what was dropped, and **which period chose the people** |
| `graph_summary.csv` | one row per snapshot: `retained_nodes`, links, density, bridge width |
| `metrics.csv` | how each measurement changed over time |
| **`tgap_results.csv`** | **the explanations — 180 rows per dataset, with validity flags** |
| `transformation_feasibility.csv` | the link-count promise, checked in all 30 settings |
| `bridge_trend_status.csv` | the history-reshaping check, 6 settings |
| `transformation_diagnostics.csv` | did each change actually reach the graph? |
| `leakage.csv` | did we accidentally change other things too? |
| `summary.json` | the headline numbers |
| `figures/` | 4 pictures |

### Reading `tgap_results.csv`

This is the file to show your professor. Each row is one experiment:

| Column | Meaning |
|---|---|
| `analysis_mode` | safe mode or old mode — check this first |
| `model` | which model we asked |
| `transformation` | what we changed (e.g. Bridge Width) |
| `direction` | did we increase it or decrease it |
| `requested_delta` | how much we **asked** to change |
| `achieved_delta` | how much we **really** changed (graphs are chunky!) |
| `baseline_prediction` | model's answer before |
| `after_prediction` | model's answer after |
| `impact` | **the explanation**: change in answer ÷ change we made |
| `noop` | `True` = nothing actually changed, so this row proves nothing |
| **`valid_for_analysis`** | **`True` = this experiment kept its promises. Filter on this column before you use anything.** |
| `transformation_status` | why it was rejected: `ok`, `edge_count_infeasible`, `saturated`, `wrong_direction` |
| `feasible` / `infeasible_reason` | did the link-count promise hold, and if not, why not |
| `edge_count_before` / `_after` / `_preserved` | the proof, in numbers |

> 💡 **The one-sentence rule for reading this file:**
> `tgap_results[tgap_results.valid_for_analysis]` — everything else is
> evidence about the method's limits, not about the data.

---

## 13. Mistakes that checking things caught

I am including these because they are the best argument for checking instead
of trusting.

### Mistake 1 — I read the wrong column
The Bitcoin files look like this:

```
  6,2,4,1289241911.72836
  │ │ │      └── the time
  │ │ └── the trust rating
  │ └── who was rated
  └── who rated
```

The other SNAP files put the time in the **third** column, so I did too. But
here the time is the **fourth**. The result: the dataset appeared to span
**0.0 days** instead of 1,903 days.

**How it was caught:** I printed the time span as a sanity check. "0 days"
for a five-year dataset is obviously impossible. There is now a test that
locks the column number in place.

### Mistake 2 — two datasets were secretly the same
Described in section 4. `tgbl-uci` and `CollegeMsg` are identical. Had I not
compared them, the project would have claimed 9 datasets while really having 8.

### Mistake 3 — I mislabelled my own diagnostic
I wrote a check that counts when a change accidentally alters the number of
links (which it should not). It reported huge numbers — until I realised one
of the changes, **Density**, is *supposed* to change the number of links.
That is its whole job.

Version 2 fixes this properly instead of with a special case: each change now
carries its own written promise (`preservesEdgeCount`), and the checker reads
that promise instead of guessing from the change's name.

### Mistake 4 — my "safe mode" was not labelling itself (caught by a test)
While writing version 2 I added a field saying whether future information was
used. I wrote the label-comparison slightly wrong, so **the unsafe mode
reported itself as safe**. A test I had just written for exactly this
(`testOnlyDescriptiveModeUsesFutureInformation`) failed immediately.

**Lesson:** the honesty flag needs a test as much as the science does. A
mislabelled warning is worse than no warning.

### Mistake 5 — my first feasibility check was not strict enough
My first version of "can this change pay for itself?" counted the links
available inside the communities. It said "yes, plenty" — and then the change
still broke the promise. The reason: the code *prefers* not to delete links
that would split the network apart, so the pool it can really draw from is
smaller than the raw count.

The fix was to check at the exact moment the payment happens, rather than
guessing beforehand. Before the fix the two checking methods disagreed twice
out of thirty; after it, **480 out of 480 agree**.

---

## 14. What we learned

All measured across all 8 datasets, in both modes.

### Finding 1 — an expected rule, confirmed on real data ✅

Some of our changes only touch the **past** and leave the present exactly as
it was. A model that only looks at the present **must** therefore answer "no
difference at all".

**Result: exactly 0.0 on 8 out of 8 datasets**, in both modes, across 219
checked rows in the safe mode.

⚠️ **But describe this carefully** — version 1 oversold it. This is not a
surprising discovery about real networks. It follows directly from the two
definitions: the change leaves the last snapshot alone, and the model reads
only the last snapshot. So zero is the *only* possible answer.

The correct wording is: **"the real-data runs verified an expected
invariant"** — a correctness check on our code and our pipeline. It is still
worth running: if a bug crept in, this is the test that would catch it. But
it is a check that passed, not a finding.

> ### 🔬 Science box 6 — Discovery vs verification
> If a result follows from your definitions, observing it is **verification**
> — you confirmed the machine works. If it does not follow, and you observe it
> anyway, that is a **discovery**. Both are valuable and they are not the
> same thing. Calling verification a discovery is one of the easiest ways to
> lose a reviewer's trust, because the reviewer can see the definitions too.

### Finding 2 — a prediction from the made-up data came true ✅

The synthetic work predicted a rule: you cannot change a whole-number
property of size *p* by less than about `0.5 / p`. A bridge of 4 links
cannot change by 10%, because 10% of 4 is less than half a link.

So datasets with **thin** bridges should sometimes fail to change anything (a
"no-op"). Measured on valid experiments only:

| | safe mode | old mode |
|---|---|---|
| datasets whose bridge gets thin (≤ 5 links) | **20.06%** did nothing | 14.47% |
| datasets with thicker bridges | **0.00%** | 0.00% |

Exactly as predicted, on data the prediction was never tuned on. **This is
the strongest real scientific result in the real-data work:** a rule derived
from theory, tested on independent data, confirmed. And it shows up *more*
strongly in the safe mode, because the safe mode's graphs are thinner.

### Finding 3 — we measured how much stress the history-change survives ⚠️

Section 7 explained how Bridge Trend can get stuck at the floor. The useful
question is not "does it get stuck" but **"how stuck before it breaks?"**

Looking only at the settings where something *did* get stuck — so both groups
below are stuck, which makes the comparison fair:

| | how many settings | how much of the history was stuck |
|---|---|---|
| direction still came out **right** | 17 | **21.0%** on average |
| direction came out **backwards** | 6 | **57.8%** on average |

So it survives about a fifth of the history hitting the floor, and inverts
somewhere around three-fifths. The backwards cases happen in exactly two
datasets — `decentraland` and `tgbl_enron` — and **only in the old mode**,
because the old mode has longer histories (24 and 22 snapshots instead of 19
and 18), which multiplies the shrinking factor more times.

In the safe mode, **19 settings got stuck and none of them came out
backwards**.

⚠️ Version 1 reported this as "65.2% vs 26.4%, a clean threshold between
datasets". That comparison lumped whole datasets together. The per-setting
numbers above replace it.

### Finding 4 — the "hold everything else still" rule really does break ⚠️

On real data the link-count promise fails on **all 8 datasets**: 31 of 240
settings in the safe mode, 30 of 240 in the old mode. Three genuinely
different causes, now named separately:

| Cause | How often (safe mode) |
|---|---|
| no unconnected cross-community pair left to add | 11 |
| not enough **deletable** links inside the communities to pay with | 10 |
| not enough links inside the communities at all | 10 |

The clearest single picture is two real departments that email **each other**
more than they email internally — so there is not enough internal structure
to trade away. The made-up graphs never had this problem, because they were
built generously.

**What changed in version 2 is not the problem but the handling.** These
settings are now labelled, their numbers withheld, and they are excluded from
every summary and every picture. The problem itself is still there and is
still the first thing I would fix.

### Finding 5 — doing it properly is harder, and that is the point ⚠️

Because the safe mode has sparser graphs, the changes get **blocked** more
often — the graph simply has no room to make them:

| Change | blocked settings, safe mode | old mode |
|---|---|---|
| Centralization | 27 of 48 | 12 of 48 |
| Density | 21 of 48 | 5 of 48 |
| Bridge Width | 13 of 48 | 9 of 48 |

This is worth saying to your professor directly: **the methodologically
correct setup produces weaker-looking results.** That is expected. Results
that get better when you remove leakage usually mean the leakage was not
really removed.

---

## 15. What changed in version 2

For anyone comparing this document to the previous one.

| # | Old behaviour | New behaviour |
|---|---|---|
| 1 | one `nodes` column, meaning the filtered subset | `raw_nodes` **and** `retained_nodes` everywhere, plus percentages |
| 2 | people picked using the whole time span | picked using the first 20% only; the rest is evaluation |
| 3 | communities found using all snapshots | found in the early period only, then frozen |
| 4 | broken link-count promise reported as a result | labelled `edge_count_infeasible`, numbers withheld, excluded |
| 5 | stuck / backwards history changes counted as results | labelled `saturated` / `wrong_direction`, excluded |
| 6 | "the blindness property survives real data" | "an expected invariant was verified" |
| 7 | Bitcoin trust ratings silently unused | `edge_weight_used: false`, `edge_sign_used: false`, stated per dataset |
| 8 | one unlabelled analysis | `analysis_mode` in every file, two modes |
| 9 | 192 tests | 269 tests |
| 10 | results in `output/real_data/` | results in `output/real_data_v2/temporal_evaluation/`; the v1 folder was deleted (git history keeps it) |

**Old numbers that are now wrong** (do not reuse them from the earlier
document or any slide):

- every snapshot count, node count, event count, density and bridge-width
  range — the graphs themselves changed
- "no-op rate 11.1% vs 0.0%" → now **20.06% vs 0.00%** (safe mode)
- "clamp 65.2% vs 26.4% between datasets" → replaced by the per-setting
  **21.0% vs 57.8%** in finding 3
- "1,440 explanation rows" → still 1,440 run, but **1,140 usable**
- "`core/` was not touched at all" → **no longer true**, see section 17

**One thing that did not change:** all 8 datasets, all 5 changes, all 6
models, the fixed seed 42, and every synthetic experiment. The synthetic test
suite passes unchanged.

---

## 16. What is still broken

Said plainly, because a reviewer will find these anyway.

1. **⚠️ The "hold everything else still" rule still breaks** (finding 4). It
   is now *reported* rather than repaired. The three possible repairs all
   change what the method measures, so I did not pick one alone.
2. **⚠️ "Bridge Trend" has too few usable rows** — 36 of 288 in the safe
   mode, 6 of 288 in the old one. Do not quote Bridge Trend magnitudes. The
   real fix is redesigning the recursion, which would change both the concept
   and the synthetic results, so it was left as a decision for the team.
3. **A crash that still exists.** Asking for a change of exactly −1 makes the
   trend code divide by zero. Known since the earlier audit; the real-data
   code stays away from that value instead of hiding it.
4. **We keep very little** in the safe mode — a median of 4.75% of people and
   3.29% of events. `bitcoin_otc` and `bitcoin_alpha` keep only ~415 events
   each; treat their numbers as indicative at best.
5. **`tgbl_enron` keeps only 25 people** in the safe mode, split 8 / 17. That
   is a small graph for a two-community analysis.
6. **Two datasets reach bridge width 0** (`tgbl_wiki`, `tgbl_enron`), where a
   percentage change of the bridge has no meaning.
7. **"Centralization" gets stuck on crowded graphs** — the most-connected
   person already knows almost everyone, so there is nobody left to connect
   them to. Blocked in 27 of 48 settings in the safe mode.
8. **Window size and actor count were chosen sensibly, not optimally**, and
   the 20% split was checked on four values on four datasets only.
9. **Cohesion is unusable** here, for the reason in Decision 2.
10. **One random seed** on real data.
11. **No trained AI model yet.** All the models are simple measurement-based
    baselines. A real graph neural network would plug into the same socket,
    but is not built.
12. **Real data proves applicability, not correctness.** Worth repeating.

---

## 17. Where the code lives

```
tgap/
├── core/                        ← THE MAIN SYSTEM
│   ├── Feasibility.py               ★ NEW: is a change even possible?
│   ├── Transformations.py           + optional "strict" mode (default off)
│   ├── TemporalGraphTransformation.py  + each change states its own promise
│   └── (everything else unchanged)
│
├── realdata/                    ← the real-data layer
│   ├── download.py                  gets the files; lists rejected ones
│   ├── adapters/
│   │   ├── base.py                  modes, time split, projection, counting
│   │   ├── tgbl_wiki.py             Wikipedia (bipartite → projected)
│   │   ├── decentraland.py          DAO voting (bipartite → projected)
│   │   └── edgelist.py              ALL SIX observed-link datasets
│   ├── run_real_data.py             runs TGAP, checks validity, writes results
│   ├── compare_datasets.py          compares all 8
│   ├── README.md                    the technical version of this document
│   └── data/                        downloaded files (not in git)
│
├── tests/
│   ├── test_realdata.py         ← 158 tests
│   └── test_feasibility.py      ← 20 tests (NEW)
│
└── output/
    └── real_data_v2/
        └── temporal_evaluation/   ← 142 result files (the safe mode only;
                                     descriptive is regenerated on demand)
```

Three things worth pointing out to your professor:

**The six observed-link datasets share one file.** They all arrive in the
same shape — "who, whom, when" — so `edgelist.py` handles all six, with one
small configuration block per dataset saying which columns to read and how
long a window should be. Six datasets, one tested code path.

**`core/` was touched this time — carefully.** The earlier version of this
document said `core/` was untouched, and that is no longer true. Version 2
adds one new file (`Feasibility.py`) and makes two **additive** changes: an
optional `strict` setting that defaults to off, and one attribute per change
saying whether it promises to keep the link count. Nothing existing behaves
differently, which is why **every synthetic test still passes with the same
results**. The direction of dependency is unchanged: `realdata/` uses
`core/`, never the other way round.

**The tests are the argument.** Two of the five mistakes in section 13 were
caught by tests written *for that exact purpose*, one of them within minutes
of writing it. Test counts:

```
   269 tests total, 267 passed, 0 failed, 2 skipped, 101.8 seconds
   (the 2 skips are deliberate: an abstract base class, and one test that
    does not apply to the dataset with real department labels)
```

---

*To check any claim in this document:*

```bash
cd c:\catalyst\tgap
python -m realdata.download
python -m realdata.run_real_data --mode both
python -m realdata.compare_datasets --mode both
python -m unittest discover -s tests
```
