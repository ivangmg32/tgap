# TSAP Explained Simply — Everything You Need to Know Before You Write Code

> **Who this is for:** you, the person doing the technical implementation, who has not
> worked with time-series machine learning or explainable AI before.
> **Promise:** no formula appears here without a plain-English sentence next to it.
> Read it top to bottom once. You don't need to memorise anything.

---

## Table of contents

1. [The 30-second version](#1-the-30-second-version)
2. [Where TSAP sits inside the CATALYST project](#2-where-tsap-sits-inside-the-catalyst-project)
3. [Background concepts, from zero](#3-background-concepts-from-zero)
4. [The problem TSAP solves](#4-the-problem-tsap-solves)
5. [The TSAP idea (the important chapter)](#5-the-tsap-idea-the-important-chapter)
6. [The two transformations, with numbers](#6-the-two-transformations-with-numbers)
7. [How the code is organised](#7-how-the-code-is-organised)
8. [Walking through one full run, step by step](#8-walking-through-one-full-run-step-by-step)
9. [The four outputs TSAP can produce](#9-the-four-outputs-tsap-can-produce)
10. [How do you prove an explanation is *good*?](#10-how-do-you-prove-an-explanation-is-good)
11. [Practical: running the code on your machine](#11-practical-running-the-code-on-your-machine)
12. [Honest notes: things in the code to double-check](#12-honest-notes-things-in-the-code-to-double-check)
13. [Where this is going: TGAP and graphs](#13-where-this-is-going-tgap-and-graphs)
14. [Glossary](#14-glossary)
15. [What I suggest we do next](#15-what-i-suggest-we-do-next)

---

## 1. The 30-second version

**TSAP** = **T**ime-**S**eries **A**dditive **exP**lanations.

You have a machine-learning model that looks at the last N numbers of a
time-series (e.g. 10 weekly stock prices) and predicts the next number. That model is a
**black box** — it gives an answer but not a reason.

TSAP opens the box using one very simple trick:

> **Change the input in a way a human understands, and measure how much the
> prediction moves.**

Instead of asking *"how important was the price on day 4?"* (a question nobody
cares about), TSAP asks:

- *"If this series were 10% **more volatile** (more jumpy), how would the prediction change?"*
- *"If this series had a 10% **stronger upward trend**, how would the prediction change?"*

The answer is a small table like:

```
Increase Volatility (10%)  →  +2.3   (prediction goes UP)
Decrease Volatility (10%)  →  -1.1   (prediction goes DOWN)
Increase Trend (10%)       →  +8.7   (prediction goes UP a lot)
Decrease Trend (10%)       →  -7.9   (prediction goes DOWN a lot)
```

Reading that table, a human immediately says: *"ah, this model is mostly
driven by the trend, and only mildly by volatility."* That is the explanation.
That's the whole idea. Everything else is engineering and evaluation.

---

## 2. Where TSAP sits inside the CATALYST project

You have three things on disk. They are three stages of the same idea.

```
c:\catalyst\
├── Catalyst - PID2025 - MemoriaCT...pdf   ← the grant proposal (the "why")
├── tsap_v2.1\                             ← WORKING code, time-series version (the "how", done)
├── Source code of TSAP ...\               ← a zip copy of the same thing
└── tgap\                                  ← EMPTY SKELETON, graph version (YOUR JOB)
```

### The proposal in three sentences

CATALYST ("Strengthening Collaboration in Socio-economic Networks with
Explainable Graph Intelligence") studies **networks that nobody is in charge of**:
open-source software ecosystems (FOSS), decentralised finance (DeFi), and the
social economy (co-ops, non-profits). Its core hypothesis is that these networks
survive thanks to **"wide bridges"** — *many* redundant connections between
communities, not one fragile link. The project wants to (a) **measure** those
bridges over time, (b) **predict** when they are decaying (early warning), and
(c) **recommend** actions to widen them — and every step must be
**explainable** to the humans affected.

Two leaders: **PI1 Samer Hassan** (networks, FOSS, DeFi, sociology) and
**PI2 Iván García-Magariño** (explainable AI, simulation). Six work packages.
The ones that matter for you:

| WP | What it does | Who leads |
|----|--------------|-----------|
| WP2 | Build the network datasets (temporal multi-layer graphs) | PI1 |
| **WP3** | **Health metrics + structural risk models** | **PI2** |
| **WP4** | **Graph AI + explainable recommendations + dashboards** | **PI2** |
| WP5 | Real pilots with 11 partner organisations | PI1 |

### Your position

TSAP is the **proof that the method works** — published/validated on time-series,
which are easy data. TGAP (`tgap\`, currently 5 nearly-empty files) is the
**same method applied to graphs**, which is what CATALYST actually needs for
WP3/WP4.

```
  TSAP (exists, works)                TGAP (you build it)
  ────────────────────                ───────────────────
  input: a time-series        →       input: a temporal graph
  model: LSTM predicts next value →   model: GNN/TGN predicts next state / risk
  transform: volatility, trend →      transform: add/remove edges, widen bridges,
                                                  remove a hub, merge communities
  measure: change in prediction →     measure: change in prediction / in a graph metric
  output: "trend matters most" →      output: "risk is high because bridge X is thin"
```

The git log of `tgap` says: *"Starting together Ivan and Ramin the main
scaffolding and interfaces"* — so the interfaces are agreed, the bodies are empty.
**Understanding TSAP deeply is the prerequisite for filling them in**, because
TGAP is a structural copy of TSAP. That is why this document spends most of
its length on TSAP.

---

## 3. Background concepts, from zero

Skip any subsection you already know.

### 3.1 Time series

A **time series** is just a list of numbers in time order.

```
Day:     1     2     3     4     5
Price:  100   102   101   105   108
```

In Python this is a `pandas.Series` — a list of values with an index (the dates).
Almost every function in TSAP takes a `pandas.Series` as input. That's why you
see `series.iloc[-1]` everywhere: `iloc[-1]` means "the last value", `iloc[0]`
means "the first value".

Key property: **order matters**. Shuffling a time series destroys it. This is
exactly why normal machine-learning explanation tools struggle with it.

### 3.2 Forecasting with a sliding window

The task: *given the last few values, predict the next one.*

The standard trick is a **sliding window**. With `windowSize = 5`:

```
Full series: 100  102  101  105  108  110  109  112

Training example 1: input [100 102 101 105 108] → target 110
Training example 2: input [102 101 105 108 110] → target 109
Training example 3: input [101 105 108 110 109] → target 112
```

One long series becomes hundreds of little (input, answer) pairs. That is your
training dataset. `windowSize` is the model's "memory span": how far back it is
allowed to look.

### 3.3 Neural networks, LSTM and GRU — the minimum you need

A **neural network** is a big flexible function with millions of tunable knobs
("weights"). You show it examples, it adjusts the knobs to reduce its errors
(this is "training" / `fit`). Afterwards it maps new inputs to outputs
(`predict`). Nobody, including its authors, can read the knobs and say why it
answered what it answered. Hence "black box".

An **LSTM** (Long Short-Term Memory) is a neural network designed for *sequences*.
It reads the values one at a time and keeps an internal "notepad" (its memory
state) that it updates as it goes. This lets it notice things like "values have
been rising for a while". A **GRU** (Gated Recurrent Unit) is a simpler, faster
cousin that does the same job.

In the code:

```python
model = Sequential([
    LSTM(64, return_sequences=True, input_shape=(windowSize, 1)),  # layer 1, 64 memory cells
    LSTM(32, return_sequences=True),                               # layer 2
    LSTM(32),                                                      # layer 3
    Dense(1)                                                       # squeeze down to 1 number
])
model.compile(optimizer="adam", loss="mse")
model.fit(x, y, epochs=50, verbose=0)
```

Translation:
- `Sequential([...])` — stack these layers, data flows top to bottom.
- `LSTM(64)` — 64 memory cells. Bigger = more capacity, slower, more overfitting risk.
- `return_sequences=True` — "pass the whole sequence to the next layer", needed when
  another LSTM follows. The last LSTM has it off, so it outputs a single summary vector.
- `Dense(1)` — a plain layer collapsing that vector into **one** number: the answer.
- `loss="mse"` — Mean Squared Error: average of (prediction − truth)². Training means
  making this as small as possible.
- `optimizer="adam"` — the algorithm that nudges the knobs. Adam is the default choice.
- `epochs=50` — go through the whole training set 50 times.

**You don't need to understand the LSTM internals to do this project.** TSAP treats
the model as a sealed box with one button: `predict`. That's the point.

### 3.4 Why the model predicts *returns* and not *prices*

This is a genuinely important detail in
[`LstmKeras.makeDataset`](../tsap_v2.1/tsap/LstmKeras.py):

```python
y.append(np.log(series.iloc[i + windowSize] / series.iloc[i + windowSize - 1]))
```

The target is not the next price. It is the **logarithmic return**:
`log(next_value / current_value)`.

Why? Because a model trained on raw prices of a €10 stock is useless for a €400
stock. But a *relative change* ("it went up 2%") is comparable across any scale.
Log makes those relative changes add up nicely and symmetric (+2% and −2% become
+0.0198 and −0.0198).

Then at prediction time it is converted back to a price
([`LstmKeras.predict`](../tsap_v2.1/tsap/LstmKeras.py)):

```python
predictedRatios = self.scaler_y.inverse_transform(y)      # undo the scaling
predictedValues = x.iloc[-1] * np.exp(predictedRatios)    # last price × e^(return)
```

`exp` undoes `log`. So: *next price = last price × growth factor*.

### 3.5 Scaling / normalisation

Neural networks learn badly when numbers are huge or tiny. `StandardScaler`
rescales a set of numbers so their average is 0 and their spread is 1.
`fit_transform` learns the rescaling *and* applies it;
`inverse_transform` undoes it, which is how you get a human-readable price back.

### 3.6 The black-box problem and XAI

**XAI = eXplainable Artificial Intelligence.** The field that asks: *the model
answered — why?*

You need it because:
- **Trust.** A community leader will not act on "the AI says your ecosystem is at risk."
- **Debugging.** Maybe the model is right by accident, keying off something silly.
- **Law.** The EU AI Act and GDPR push towards explanations for automated decisions.
  The proposal explicitly commits to this (`WP1`, Valeria Ferrari on the team for
  AI Act / GDPR).
- **Science.** An explanation is a hypothesis about how the world works.

### 3.7 Local vs. global explanations

| | Question | TSAP method |
|---|---|---|
| **Local** | "Why *this* prediction, for *this* series?" | `explain(series)`, `plotSummary` |
| **Global** | "What does this model care about *in general*?" | `boxplotTrans(listOfSeries)` |

Both exist in TSAP and this distinction shows up everywhere in XAI literature.
Global = run the local method on many inputs and look at the distribution of answers.

### 3.8 Feature attribution, and what "additive" means

The dominant XAI family is **feature attribution**: hand out a score to each
input feature saying how much it pushed the answer up or down.

**Additive** means the scores are designed to *sum up* to the deviation of the
prediction from a baseline:

```
prediction  ≈  baseline  +  score₁ + score₂ + score₃ + ...
```

That property is what makes a bar chart honest — the bars represent contributions
that add up to the whole. The "A" in TSAP and TGAP comes from here.

**SHAP** (SHapley Additive exPlanations) is the famous method in this family. It
borrows an idea from game theory (Shapley values, 1953): treat each feature as a
player in a team, try the model with every possible subset of players, and give
each player its average marginal contribution. It is mathematically elegant and
**extremely slow** (exponentially many subsets, approximated by sampling).
**LIME** is the other classic: fit a simple linear model locally around the input
and read off its coefficients.

Notice the naming pattern:

```
SHAP  = SHapley      Additive exPlanations
TSAP  = Time-Series  Additive exPlanations       ← deliberately echoes SHAP
TGAP  = Temporal Graph Additive exPlanations     ← your project
```

That naming is a positioning claim: *same family, different, better-suited
primitive.*

---

## 4. The problem TSAP solves

Take SHAP applied to our window of 10 weekly prices. The "features" are
`price_1, price_2, …, price_10`. SHAP gives you:

```
price_1  : +0.03
price_2  : -0.01
price_3  : +0.11
...
price_10 : +0.42
```

Three things are wrong with this:

**Problem 1 — It's not human-meaningful.** "Week 3's price contributed +0.11" is
not actionable knowledge. No analyst thinks in those terms. They think in
*trend*, *volatility*, *momentum*, *seasonality*.

**Problem 2 — The features are not independent, and SHAP assumes they are.**
SHAP works by removing/replacing subsets of features. In a time series,
`price_3` and `price_4` are glued together — prices don't jump randomly.
When SHAP replaces `price_3` with some baseline value it creates a
**series that could never exist in reality**, and asks the model to predict on
it. The model's answer there is meaningless. (This is the classic
"off-manifold perturbation" criticism of SHAP.) TimeSHAP is one attempt to
patch this for sequences; there's a leftover notebook for it in
`tsap_v2.1/tsap/alternatives/timeshap/`.

**Problem 3 — Cost.** Shapley values need many model calls per explanation.

TSAP's response: **stop attributing to raw time points. Attribute to properties
of the shape of the curve.**

---

## 5. The TSAP idea (the important chapter)

### 5.1 The core move

Pick a small set of **human-meaningful properties** of a time series. TSAP picks two:

- **Volatility** — how jumpy/noisy the curve is. Big swings vs. a smooth line.
- **Trend** — how steeply it is going up or down overall.

For each property, define a **transformation**: a function that takes the series
and a knob value `delta`, and returns a *new, still-realistic series* in which
only that property has changed by `delta`.

```
transformVolatility(series, +0.10)  →  same series, 10% more jumpy
transformTrendReverse(series, +0.10) →  same series, 10% steeper rise
```

Then the explanation is pure arithmetic:

```
impact = ( model.predict(transformed_series) − model.predict(original_series) ) / |delta|
```

In code ([`TsapExplainer.explain`](../tsap_v2.1/tsap/TsapExplainer.py)):

```python
def explain(self, series):
    dictExplain = dict()
    result = self.tsModel.predict(series)                    # baseline prediction
    keys   = ["Increase Volatility", "Decrease Volatility",
              "Increase Trend", "Decrease Trend"]
    deltas = [self.delta, -self.delta, self.delta, -self.delta]   # +0.1, -0.1, +0.1, -0.1
    transf = [self.transformVolatility,      self.transformVolatility,
              self.transformTrendReverse,    self.transformTrendReverse]
    for i in range(len(keys)):
        seriesT     = transf[i](series, deltas[i])           # perturb
        resulTransf = self.tsModel.predict(seriesT)          # re-predict
        difResult   = (resulTransf - result) / abs(deltas[i])  # normalised change
        dictExplain[keysWithValues[i]] = difResult
    return dictExplain
```

**Total cost: 5 model calls.** (1 baseline + 4 perturbations.) Compare with
thousands for SHAP. That is the efficiency claim.

### 5.2 Why divide by `|delta|`?

Because you want a **rate**, not a raw difference. Dividing the change in output
by the size of the input nudge gives "output change per unit of property change" —
i.e. a **slope**. This makes the number comparable across different `delta`
choices, and it is exactly the definition of a numerical derivative:

```
                f(x + h) − f(x)
  slope  ≈  ─────────────────────
                      h
```

So TSAP is, mathematically, **estimating the sensitivity (partial derivative) of
the model's output with respect to interpretable properties of the input.** That
single sentence is the most precise summary of the method, and a good one to use
in a paper or a presentation.

### 5.3 Why do both `+delta` and `−delta`?

Because models are **non-linear**. Making a series 10% more volatile might raise
the prediction, and making it 10% *less* volatile might *also* raise it (a U
shape). If you only tested one direction you'd never know. Testing both sides
reveals asymmetry, which is genuine information about the model.

### 5.4 Why this is better on the three problems

| | SHAP on time series | TSAP |
|---|---|---|
| Meaningful to humans? | "week 3 = +0.11" — no | "trend matters 4× more than volatility" — yes |
| Realistic perturbations? | No, breaks the sequence structure | Yes, a transformed series is still a plausible series |
| Cost per explanation? | Thousands of model calls | 5 model calls |
| Model-agnostic? | Yes | Yes (only needs `predict`) |
| Number of outputs | One per time step (10, 50, 200…) | One per property (4) — much **sparser**, easier to read |

### 5.5 The honest limitation you should know about

TSAP explains **only the properties you thought to define**. If the model's real
driver is, say, weekly seasonality, and you never wrote a
`transformSeasonality`, TSAP will never tell you. SHAP, for all its faults, does
not require you to guess in advance.

This is the fundamental trade-off of the whole approach:
**concept-based explanation buys meaning at the price of completeness.**
Say it out loud in any presentation; it's a strength to acknowledge it, and it
immediately suggests the obvious extension (define more transformations —
seasonality, level shift, autocorrelation, outliers, …). Same for TGAP: which
graph transformations you define *is* the research contribution.

---

## 6. The two transformations, with numbers

This is where the actual cleverness of the implementation lives. Both
transformations share one design rule:

> **Keep the last value fixed.**

Why? Because the model's prediction is anchored to the last value
(`predictedValue = last_value × exp(return)`). If a transformation moved the last
value, the prediction would change for a boring reason (different starting
point), and you'd wrongly credit the property. Holding the last value fixed
means any change in output comes from the *shape*, which is what you're
measuring. **This is the single most important design decision in TSAP, and you
will need the graph equivalent of it in TGAP.**

### 6.1 Volatility transformation

```python
def transformVolatility(self, series, delta, ma=None):
    if ma is None:
        ma = series.iloc[-1]     # anchor = the last value
    series = series - ma         # 1. shift so the anchor sits at zero
    factor = 1 + delta
    series *= factor             # 2. stretch (or shrink) everything
    return series + ma           # 3. shift back
```

Three lines: *shift → scale → shift back*. A classic "zoom around a fixed point".

**Worked example.** `series = [100, 104, 98, 106, 110]`, `delta = +0.10`:

| step | values |
|---|---|
| original | 100, 104, 98, 106, 110 |
| minus anchor (110) | −10, −6, −12, −4, 0 |
| × 1.10 | −11.0, −6.6, −13.2, −4.4, 0 |
| plus anchor | **99.0, 103.4, 96.8, 105.6, 110** |

The last value is untouched (110). Everything else moved 10% further away from
it — the swings got bigger. With `delta = −0.10` they'd shrink towards a flat line.

*Subtlety worth knowing:* because the anchor is the **last value** rather than
the series mean, this stretch also slightly steepens the trend. A purist would
anchor on a moving average — and in fact the signature accepts `ma=None` exactly
so you *can* pass a moving average in. Nobody currently does. That's a small,
concrete improvement you could propose and test.

### 6.2 Trend transformation

```python
def transformTrendReverse(self, series, rootDelta):
    seriesT = series.copy()
    i = len(seriesT) - 2
    while i >= 0:                                       # walk BACKWARDS from the end
        origChange   = series.iloc[i] - series.iloc[i+1]   # the original step, reversed
        seriesT.iloc[i] = seriesT.iloc[i+1] + origChange   # rebuild this point
        seriesT.iloc[i] = seriesT.iloc[i] / (1 + rootDelta)  # then shrink it
        i = i - 1
    return seriesT
```

Read it as: *start at the last value (fixed), walk backwards, and each time you
step back also divide by `(1 + rootDelta)`.* Because you divide at **every** step,
the effect **compounds** the further back you go — hence the name `rootDelta`
(each step applies a "root" of the total change).

**Worked example.** `series = [1, 2, 3, 4, 5]`, `rootDelta = +0.05`:

| i | original step (sᵢ − sᵢ₊₁) | rebuild | ÷ 1.05 |
|---|---|---|---|
| 3 | 4 − 5 = −1 | 5 + (−1) = 4 | **3.810** |
| 2 | 3 − 4 = −1 | 3.810 − 1 = 2.810 | **2.676** |
| 1 | 2 − 3 = −1 | 2.676 − 1 = 1.676 | **1.596** |
| 0 | 1 − 2 = −1 | 1.596 − 1 = 0.596 | **0.567** |

Result: `[0.567, 1.596, 2.676, 3.810, 5]`

```
original:               transformed (rootDelta = +0.05):
5 |        ●            5 |        ●
4 |      ●              4 |      ●
3 |    ●                3 |    ●
2 |  ●                  2 |   ●
1 |●                    1 | ●
0 └──────────           0 |●
                        0 └──────────
  same endpoint, but the climb is now STEEPER  →  "trend increased"
```

Last value still 5. The earlier values got pulled down, so the same endpoint is
now reached from lower down: a **steeper rise**. Negative `rootDelta` flattens it.

The word "Reverse" in the name refers to the backwards walk, not to reversing the trend.

### 6.3 Why these two properties in particular?

Because in finance and in most applied time-series work, **trend** and
**volatility** are *the* two things practitioners talk about. The team has an
economist/econometrician (Alfredo García-Hiernaux) on it precisely for this kind of
domain grounding. A good explanation must speak the vocabulary of the person
reading it.

---

## 7. How the code is organised

### 7.1 File map

```
tsap_v2.1/
├── Data/
│   ├── Electric_Production.csv                 US electricity production, monthly
│   └── sales-of-shampoo-over-a-three-ye.csv    classic tiny teaching dataset
└── tsap/
    ├── TsModel.py                  ★ THE INTERFACE. One method: predict(series) → float
    ├── TsapExplainer.py            ★ THE EXPLAINER. All the logic lives here
    │
    ├── LstmKeras.py                a reusable LSTM wrapper that implements TsModel
    ├── LstmStock.py                LstmKeras + Yahoo Finance stock data
    ├── LstmFromCsv.py              LstmKeras + any CSV file
    ├── GruTsModel.py               a GRU model — proof TSAP is model-agnostic
    ├── Cache.py                    saves downloaded stock data so you don't hit rate limits
    │
    ├── CaseStudyStock.py           demo: explanations for a stock
    ├── CaseStudyElectric.py        demo: explanations for electricity production
    │
    ├── PerturbationFaithfulness.py EVALUATION: is TSAP faithful? vs SHAP
    ├── GummadiEvaluation.py        EVALUATION: sparsity, stability, runtime
    ├── auxTests.py / CreateImg.py  helpers
    │
    ├── alternatives/
    │   ├── shap/PerturbationFaithfulnessShap.py   the SHAP baseline
    │   └── timeshap/AReM_TF.ipynb                 a TimeSHAP experiment
    └── output/PerturbationFaithfulness.{csv,xlsx} the results table
```

### 7.2 The single most important architectural idea: the interface

The whole file [`TsModel.py`](../tsap_v2.1/tsap/TsModel.py) is this:

```python
class TsModel:
    def predict(self, series):
        raise "'predict' method should be implemented"
```

That's it. Nine lines including comments. And it is the reason TSAP is a
*framework* and not a script.

The contract says: **"If your model can take a pandas Series and return one
float, TSAP can explain it."** Nothing else. Not "if you use TensorFlow", not
"if you give me your weights". This property has a name:

> **Model-agnostic** — the explainer treats the model as a black box with one
> button, so it works on *any* model: LSTM, GRU, Transformer, ARIMA,
> random forest, or a hand-written rule.

The repo *proves* it by shipping two unrelated implementations:
[`LstmKeras`](../tsap_v2.1/tsap/LstmKeras.py) (TensorFlow, LSTM, predicts
log-returns) and [`GruTsModel`](../tsap_v2.1/tsap/GruTsModel.py) (GRU, MinMax
scaling, predicts the raw value). Both work with the same explainer, unchanged.
That comment in `GruTsModel` — *"another model different from LSTM to prove that
TSAP is model-agnostic"* — is a deliberate scientific argument, not a note to self.

**This pattern is the thing to carry into TGAP.** `tgap/core/` already mirrors it:
`GraphModel.predict(graph)`, `TemporalGraphModel.predict(temporalGraph)`,
`Metric.measure(graph)`, `TemporalGraphTransformation.transform(temporalGraph, delta)`.
Same architecture, different data type.

### 7.3 Inheritance chain

```
TsModel  (interface: predict)
   │
   ├── LstmKeras  (fit, predict, evaluate, makeDataset, createModelLstm)
   │      ├── LstmStock    → __init__ fetches stock prices via Cache, then fit()
   │      └── LstmFromCsv  → __init__ reads a CSV column, then fit()
   │
   └── GruTsModel (own training code, MinMaxScaler, raw-value target)
```

`LstmStock` is only 30 lines because all the machinery is in the parent. Subclasses
only answer "where does the data come from?". That's good design — worth copying.

### 7.4 The caching layer

[`Cache.py`](../tsap_v2.1/tsap/Cache.py) is small but practically essential.
Yahoo Finance rate-limits you. `Cache.history(ticker)`:

1. in memory already? return it;
2. a CSV on disk at `../Cache/TICKER_6mo.csv`? load it;
3. otherwise download from Yahoo, **save the CSV**, return it.

Two consequences you will feel immediately:
- After the first run everything is fast and works offline.
- Experiments are **reproducible** — the data is frozen on disk. (If you *want*
  fresh data, delete the cache folder.)

The same trick applies to trained models: `LstmKeras.activateSave(filename)` sets
`../Models/<ClassName><filename>.keras`, and `createModelLstm` loads that file if it
exists instead of retraining. Training happens once.

### 7.5 The `frequency` trick

You'll see `frequency=5` and `series[::frequency]` constantly.

`series[::5]` is Python slicing for "take every 5th element". Stock markets have
5 trading days per week, so `[::5]` converts a **daily** series into a
**weekly** one. `frequency=1` keeps it daily.

Why bother? Daily price movements are mostly noise. Weekly data is smoother, so
trend and volatility are more meaningful — and there is less data, so everything
runs faster.

---

## 8. Walking through one full run, step by step

Let's trace [`CaseStudyStock.evaluateLocal("WKL.AS")`](../tsap_v2.1/tsap/CaseStudyStock.py)
from start to finish. This is the whole system in one sequence.

```python
def evaluateLocal(ticker):
    frequency = 5
    model    = LstmStock(windowSize=10, ticker=ticker, yfDuration="1y", frequency=frequency)
    series   = Cache().history(ticker)['Close'][::frequency]
    explainer = TsapExplainer(model)
    explainer.plotSummary(series, title=ticker)
    explainer.plotVolatility(series, minDelta=-0.2, maxDelta=0.2, nValues=40, yName=ticker)
    explainer.plotTrend(series,     minDelta=-0.1, maxDelta=0.1, nValues=40, yName=ticker)
```

**Step 1 — Get data.** `Cache(yfDuration="1y").history("WKL.AS")` returns a
DataFrame of one year of daily prices. `['Close']` takes the closing-price
column. `[::5]` thins it to ~52 weekly values.

**Step 2 — Build the training set.** `LstmStock.__init__` calls `self.fit(prices)`,
which calls `makeDataset(values, windowSize=10)`:
- slides a 10-wide window over the ~52 values → ~42 training examples
- `X[i]` = the 10 values in window *i*
- `y[i]` = `log(value_after_window / last_value_in_window)` — the log-return
- `y` gets standard-scaled; `scaler_y` is kept so predictions can be converted back
- `X` is reshaped to `(42, 10, 1)`: 42 examples × 10 time steps × 1 feature

**Step 3 — Train (or load).** `createModelLstm` checks `../Models/LstmStockWKL.AS1yFreq5.keras`.
If it exists → load. Otherwise → build the 3-LSTM stack, train 50 epochs, save.

**Step 4 — Wrap in the explainer.** `TsapExplainer(model)`, with `defaultDelta = 0.1`
(= 10% nudges).

**Step 5 — Baseline prediction.** `explain(series)` calls `model.predict(series)`.
Inside, `x = x[-self.windowSize:]` quietly keeps **only the last 10 values** — so
you can hand it a long series and it uses the most recent window. Then:
model → scaled log-return → `inverse_transform` → `last_value × exp(return)` → a price.

**Step 6 — Four perturbations.** For each of {volatility ±10%, trend ±10%}:
build the transformed series, predict again, compute
`(new − baseline) / 0.1`. Store in a dict.

**Step 7 — Display.** `plotSummary` turns the dict into a horizontal bar chart;
`plotVolatility` / `plotTrend` sweep `delta` across 40 values from −20% to +20%
and plot a sensitivity curve. Plotly opens them in your browser.

Compressed to a diagram:

```
Yahoo Finance ──► Cache (CSV) ──► weekly series
                                       │
                          ┌────────────┴────────────┐
                          ▼                         ▼
                  makeDataset (windows          the series you
                  + log returns)                want explained
                          │                         │
                          ▼                         │
                  LSTM .fit()  ──► saved .keras     │
                          │                         │
                          └──────────┬──────────────┘
                                     ▼
                            TsapExplainer
                                     │
             ┌───────────────────────┼───────────────────────┐
             ▼                       ▼                       ▼
    predict(original)     predict(volatility±)      predict(trend±)
             └───────────────────────┼───────────────────────┘
                                     ▼
                    impacts = (changed − original) / |delta|
                                     ▼
                     bar chart / sensitivity curve / boxplot
```

---

## 9. The four outputs TSAP can produce

### 9.1 `explain(series)` → a dictionary (the raw numbers)

```python
{'Increase Volatility (10.0%)': 1.84,
 'Decrease Volatility (10.0%)': -0.92,
 'Increase Trend (10.0%)':      7.31,
 'Decrease Trend (10.0%)':     -6.88}
```

Read it as: *trend is ~4× more influential than volatility here, and the model
responds roughly symmetrically in both directions.*

### 9.2 `plotSummary(series)` → a horizontal bar chart (local)

Red bars = pushes the prediction up, blue = down, dashed line at zero.
This is deliberately the same *visual language* as a SHAP summary plot, so anyone
who has seen SHAP output reads a TSAP chart instantly.

One wrinkle worth understanding — the **signed logarithmic scale**
(`summaryData`):

```python
logValues = [np.log10(abs(v)) if v != 0 else 0 for v in values]
minLog = math.floor(np.min(logValues))
summand = abs(minLog) if minLog < 0 else 0
signed_log = [np.sign(v) * (np.log10(abs(v)) + summand) if v != 0 else 0 for v in values]
```

The problem: one impact might be `+8.3` and another `+0.0004`. On a normal bar
chart the small one is invisible. The fix:
1. take `log10` of the **magnitude** — compresses huge ranges into readable ones;
2. put the **sign** back, so direction survives (`np.sign(v) * ...`);
3. add `summand` so the smallest bar starts at 0 instead of going negative
   (otherwise a small *positive* impact would draw a bar pointing left — badly
   misleading).

So the bar *lengths* are on a log scale, but their *directions* are true. The axis
label says `Signed (log₁₀(value)+N)` so the reader knows.

### 9.3 `plotTrans` / `plotVolatility` / `plotTrend` → a sensitivity curve (local)

Sweep `delta` over e.g. 40 values from −20% to +20%, and plot
`prediction(delta) − prediction(0)` against `delta`.

```
impact
  │                    ●●●
  │                ●●●
  │            ●●●            ← a straight line = linear response
  │        ●●●
  │    ●●●
──┼●●●─────────────────────  delta (%)
  │
 -20              0        +20
```

This is strictly more informative than a single bar: you see **shape**. A straight
line means the model responds proportionally. A curve, a plateau, or a kink means
non-linearity — e.g. "beyond +15% volatility the model stops reacting". A single
number at `delta = 10%` would have hidden that.

### 9.4 `boxplotTrans(listOfSeries)` → a boxplot (global)

Now take *many* series (e.g. 20 sliding windows from the same stock, or 20
different stocks). For each `delta`, compute the impact on every series, and draw
a **boxplot** of that distribution.

A boxplot shows median, the middle 50% (the box), the range (whiskers), and
outliers. So you see not just "the average effect" but **how consistent** it is.
A wide box means the model behaves very differently on different inputs — an
important finding in itself.

`boxplotTransLong(longSeries, windowSize=5, begin=-20, end=-1, step=1)` is a
convenience wrapper: it chops one long series into overlapping windows and calls
`boxplotTrans` for you.

---

## 10. How do you prove an explanation is *good*?

This is the part beginners always skip and reviewers always attack. You cannot
validate an explanation against ground truth, because there **is** no ground
truth — nobody knows the "true" explanation of a neural network. So the field
uses **proxy properties**. TSAP measures four, and each has code in the repo.

### 10.1 Faithfulness — does the explanation match the model's real behaviour?

The most important one. Logic:

> If the explanation says "increasing the trend raises the prediction a lot",
> then when I *actually* increase the trend, the prediction should *actually*
> rise a lot. Across many series, the explanation's score and the model's real
> reaction should **rank in the same order**.

Measured with **Spearman rank correlation**: a number in [−1, 1] that asks "do
these two lists put things in the same order?" (It uses ranks rather than raw
values, so it doesn't care about scale — only ordering.) 1 = perfect agreement,
0 = no relationship, −1 = exactly backwards.

[`PerturbationFaithfulness.py`](../tsap_v2.1/tsap/PerturbationFaithfulness.py)
does this for 10 stocks, for TSAP and for a SHAP baseline, and writes
`output/PerturbationFaithfulness.csv`. Current results:

| Ticker | SHAP | TSAP | Improvement |
|---|---|---|---|
| IBE.MC | −0.242 | 0.971 | +121.3 |
| MSFT | 0.735 | 0.683 | −5.3 |
| AMZN | 0.418 | 0.728 | +31.0 |
| NVDA | 0.003 | 0.295 | +29.2 |
| TSLA | 0.251 | 0.546 | +29.5 |
| AAPL | −0.286 | −0.059 | +22.7 |
| GOOGL | −0.012 | −0.734 | −72.2 |
| META | 0.370 | −0.149 | −51.9 |
| HD | 0.788 | −0.081 | −86.9 |
| KO | −0.635 | 0.435 | +106.9 |
| **Average** | **0.139** | **0.263** | **+12.4** |

Read this honestly: **TSAP wins on average, but the variance is enormous** and it
loses badly on 4 of 10 tickers. Both methods are near-zero on average, which
mostly says *stock prices are very hard to forecast, so there isn't much
consistent model behaviour to explain.* If you end up strengthening this
evaluation, the levers are: more tickers, easier (more predictable) datasets,
averaging over random seeds, and reporting confidence intervals. Worth
discussing with Iván — it's the kind of table reviewers press on.

### 10.2 Sparsity — is the explanation short enough for a human?

An explanation with 200 bars explains nothing. **Gummadi's sparsity**
(implemented in [`GummadiEvaluation.testSparsity`](../tsap_v2.1/tsap/GummadiEvaluation.py))
normalises all impact values to [0, 1], then for each threshold from 0.0 to 1.0
counts the fraction of features *below* it. A high curve means most features are
negligible — i.e. only a couple of things really matter, i.e. a human can read it.

TSAP has a structural advantage: only 4 outputs by construction, versus one per
time step for SHAP.

### 10.3 Stability — same input, same explanation?

`testStability()` runs `explain()` 10 times on the same series and prints all the
results. If they differ, the explanation is unreliable and nobody should trust
it. TSAP is essentially deterministic (no random sampling — unlike SHAP, which
approximates by sampling), so this should come out clean. That determinism is
worth stating explicitly as a selling point.

### 10.4 Efficiency — how fast?

`testEfficiency(nSamples)` times a global explanation over N series. The
headline argument: TSAP is **O(number of properties)** = 5 model calls per
explanation, constant regardless of window length — where SHAP grows with the
number of features and its sampling budget.

### 10.5 The four properties as a checklist

| Property | Question | Code |
|---|---|---|
| Faithfulness | Does it reflect the real model? | `PerturbationFaithfulness.py` |
| Sparsity | Is it short enough to read? | `GummadiEvaluation.testSparsity` |
| Stability | Is it repeatable? | `GummadiEvaluation.testStability` |
| Efficiency | Is it fast? | `GummadiEvaluation.testEfficiency` |

(Other names you will meet in the literature: *comprehensibility* — can users
understand it, measured with human studies; *completeness* — does it cover
everything the model uses. TSAP is weak on completeness by design, see §5.5.)

**You will need this exact checklist again for TGAP.** Reusing an established
evaluation protocol is much easier to defend than inventing one.

---

## 11. Practical: running the code on your machine

### 11.1 Dependencies

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install tensorflow pandas numpy scikit-learn matplotlib plotly yfinance scipy shap openpyxl
```

Notes:
- `tensorflow` is the heavy one. The LSTM code uses `tensorflow.keras`.
- `plotly` opens interactive charts in your browser; `matplotlib` opens a window.
- `yfinance` downloads stock data (needs internet the first time only — then the
  cache covers you).
- `shap` is only needed for the baseline comparison.

### 11.2 ⚠️ You must run from inside the `tsap` folder

Every path in the code is **relative**: `"../Cache/"`, `"../Models/"`,
`"../Data/Electric_Production.csv"`, `"output/..."`. And the imports are flat
(`from LstmStock import LstmStock`, not `from tsap.LstmStock import ...`). So:

```powershell
cd c:\catalyst\tsap_v2.1\tsap
python CaseStudyElectric.py
```

Running `python tsap_v2.1/tsap/CaseStudyElectric.py` from elsewhere **will fail**
with import or file-not-found errors. This is the #1 thing that will waste your
first hour.

### 11.3 What to run first, in order

```powershell
cd c:\catalyst\tsap_v2.1\tsap

# 1. No internet needed, small data, fastest path to seeing something work:
python CaseStudyElectric.py

# 2. The GRU version — proves model-agnosticism:
python GruTsModel.py

# 3. Stocks (needs internet the first time):
python CaseStudyStock.py

# 4. The evaluations (slow — SHAP is expensive):
python GummadiEvaluation.py
python PerturbationFaithfulness.py
```

Start with `CaseStudyElectric.py`. It reads a local CSV, so no network, no rate
limits, no ticker-symbol problems.

### 11.4 Reading `CaseStudyElectric.py` as a template

```python
model     = LstmFromCsv(path=path, columnName=columnName, topic="Electric Production")
explainer = TsapExplainer(model)
series    = read_csv(path)[columnName]

explainer.plotSummary(series, title=topic)                        # local: bar chart
explainer.plotVolatility(series, -0.2, 0.2, nValues=40, ...)      # local: sensitivity curve
explainer.plotTrend(series, -0.1, 0.1, nValues=40, ...)           # local: sensitivity curve
explainer.boxplotTransLong(series, trans=..., nValues=6, ...)     # global: boxplot
model.evaluate()                                                   # sanity: predicted vs actual
```

Five lines of explanation code. That last one matters: `model.evaluate()` plots
predicted vs. actual. **Always check this first.** Explaining a model that can't
predict is explaining noise. A good explanation of a bad model is worthless.

---

## 12. Honest notes: things in the code to double-check

I read the code carefully. These look like real issues, but I have not executed
anything, so treat them as *things to verify*, not established facts. Each is a
cheap, useful first contribution.

1. **`PerturbationFaithfulness.py` appends the wrong variable.** Lines ~41–45:
   ```python
   predDelta = predTransf - pred
   print(predDelta, tsapScore)
   tsapScores.append(tsapScore)
   predDeltas.append(predTransf)     # ← appends predTransf, not predDelta
   ```
   The SHAP baseline in `alternatives/shap/PerturbationFaithfulnessShap.py` correctly
   appends `predDelta`. So the two sides of the comparison may not be measuring the
   same thing, which would directly affect the results table in §10.1. **Check this
   with Iván before anything else** — it could change published numbers.

2. **`scaler_x` is computed and thrown away** in `LstmKeras.makeDataset`:
   ```python
   scaler_x.fit_transform(X.reshape(-1, 1)).reshape(X.shape)   # result not assigned
   ```
   So inputs are fed to the LSTM unscaled (raw prices, e.g. ~400). Possibly
   intentional (the target is a scaled log-return, so scale-invariance comes from
   there), possibly an oversight. Worth asking.

3. **Possible input-shape mismatch in `LstmKeras.predict`.** Training reshapes `X`
   to 3-D `(n, windowSize, 1)`, but `predict` builds `X = [x]` from a pandas
   Series, giving 2-D `(1, windowSize)`, while the model declares
   `input_shape=(windowSize, 1)`. Depending on your TF/Keras version this may
   silently work or may raise. If you get a "expected ndim=3" error, that's this.

4. **`boxplotTrans` recomputes the baseline inside the inner loop** — it calls
   `predict(series)` once per (delta, series) pair when once per series would do.
   An easy speed-up for the efficiency experiments.

5. **`TsModel.predict` raises a string**, not an exception:
   `raise "'predict' method should be implemented"`. That's a `TypeError` in
   Python 3. Should be `raise NotImplementedError(...)`.

6. **`tsap_v2.1` has no `requirements.txt`** and no packaging. Since CATALYST
   commits to open science and reproducibility (WP1, D1.2 Data Management Plan),
   adding one is a genuinely valuable small contribution.

---

## 13. Where this is going: TGAP and graphs

This section is a preview so you know what the concepts are for. We'll build it
properly later.

### 13.1 Graphs, in plain words

A **graph** is dots and lines. **Nodes** (dots) are things; **edges** (lines) are
relationships.

In FOSS: nodes = developers, projects, packages, companies. Edges = "contributed
to", "depends on", "co-maintains", "funds".

### 13.2 Temporal, multi-layer graphs

- **Temporal** — the graph changes over time. You have a sequence of snapshots:
  graph in Jan, graph in Feb, … This is *exactly* a time series, except each
  element is a whole graph instead of a number. **That is the bridge from TSAP to TGAP.**
- **Multi-layer** — several kinds of edge at once between the same nodes:
  a *collaboration* layer, a *dependency* layer, a *governance* layer, a
  *funding* layer. The proposal argues that cohesion lives in the **overlap**
  between layers, which single-layer analysis cannot see.

### 13.3 Wide bridges — the central hypothesis

Classic network science (Granovetter's "weak ties"): casual acquaintances bridge
communities and spread information efficiently.

Modern correction (Centola; the 2021 *Nature* paper cited in the proposal):
that holds only for **simple contagion** — cheap information, like a job ad.
For **complex contagion** — behaviours that cost something, carry risk, or need
legitimacy, like adopting a technology or forming an alliance — one weak tie is
not enough. People need **social reinforcement**: several independent contacts
doing it. So diffusion needs **wide bridges**: *many redundant connections*
between two communities, not one.

Consequence: a single link between two communities is a **single point of
failure**. One person burns out and the bridge is gone.

CATALYST's hypothesis: *measure bridge width over time, and you can predict
fragility before it breaks — and recommend where to add ties to fix it.*

Candidate metrics from objective O3 (these become `Metric` subclasses in
`tgap/core/GraphMetric.py`):
- **inter-community path redundancy** — how many independent routes between two communities
- **edge-disjoint routes** — routes sharing no link, so one failure doesn't kill them all
- **k-core connectivity** — how deep the densely-connected core is
- **distributed bus factor** ("truck factor") — how many people must leave before
  the project dies. A bus factor of 1 is a crisis. This is a real, measured
  problem in open source.

### 13.4 The AI models

- **GNN (Graph Neural Network)** — a neural network that operates on graphs.
  Intuition: every node repeatedly summarises its neighbours' information and
  mixes it into its own description. After a few rounds each node "knows" about
  its local neighbourhood, and that description (an **embedding** — a list of
  numbers capturing a node's structural position) can be used to predict things.
  **GraphSAGE** and **GAT** (Graph Attention Network — learns *which* neighbours
  to weight more) are the two named in the proposal.
- **TGN (Temporal Graph Network)** — a GNN with a memory module, so it tracks how
  the graph changes. This is what lets CATALYST learn **"bridge decay"**: a bond
  getting weaker *before* it breaks. That's the early-warning mechanism (RQ2).
- **Link prediction** — given the graph now, which edges are likely/desirable next?
  A recommender for collaborations.
- **MORS (Multi-Objective Recommender System)** — normal recommenders maximise one
  thing (clicks). Here you must balance conflicting goals: maximise structural
  redundancy **and** minimise coordination cost, subject to constraints (licence
  compatibility, governance rules, fairness). There is no single best answer, so
  you compute the **Pareto frontier**: the set of options where you cannot improve
  one objective without worsening another. The user then picks their trade-off.
  The proposal suggests evolutionary/genetic algorithms for the search.
- **Agent-Based Simulation (ABS) as surrogate explainer** — the proposal's
  explainability plan: the TGN is accurate but opaque, so you build an
  interpretable simulation of individual agents, calibrate it to reproduce the
  TGN's predictions, and then read the *story* off the simulation:
  *"risk is high because agent X is a bottleneck."* A **surrogate** is a simple
  model that mimics a complex one so you can inspect the simple one.
- **Neuro-symbolic** — combining neural networks (pattern recognition) with
  symbolic/rule-based reasoning (human-readable logic). The TGN + ABS pairing
  is exactly this.

### 13.5 The TSAP → TGAP mapping

This table *is* your implementation plan.

| TSAP (works) | TGAP (to build) | Current file |
|---|---|---|
| `TsModel.predict(series) → float` | `GraphModel.predict(graph) → float` | `tgap/core/GraphModel.py` ✔ stub |
| — | `TemporalGraphModel.predict(temporalGraph) → graph` | `tgap/core/TemporalGraphModel.py` ✔ stub |
| — | `Metric.measure(graph) → float` | `tgap/core/GraphMetric.py` ✔ stub |
| `transformVolatility`, `transformTrendReverse` | `TemporalGraphTransformation.transform(tg, delta)` | `tgap/core/TemporalGraphTransformation.py` ✔ stub |
| `TsapExplainer.explain / plotSummary / boxplotTrans` | `TgapExplainer` | `tgap/core/TemporalGraphExplainer.py` — **empty class** |
| — | concrete metrics, e.g. `CohesionMetric` | `tgap/examples.py` — **returns 0.0** |
| `LstmStock`, `LstmFromCsv`, `GruTsModel` | concrete graph models (GNN/TGN wrappers) | *not started* |
| Faithfulness / sparsity / stability / efficiency | same four, on graphs | *not started* |

The hard, interesting, publishable design questions:

1. **What are the graph equivalents of "volatility" and "trend"?**
   Candidates: *centralisation* (power concentrating in few nodes), *fragmentation*
   (communities drifting apart), *bridge width* (the project's own concept),
   *density*, *churn* (rate of tie turnover). Each needs a transformation.
2. **How do you change one property by `delta` while keeping the graph realistic?**
   Remember TSAP's rule — keep the last value fixed, so the change comes from
   *shape*, not from the anchor. What's the graph analogue? Probably: keep the
   node set and the edge count fixed while rewiring, so the change comes from
   *structure*, not from size. This is the key design decision.
3. **What plays the role of "the prediction"?** Either a model output (risk score
   from a TGN) *or* a graph metric (`Metric.measure`). Note that `tgap` has
   **both** `GraphModel` and `Metric` interfaces — so TGAP can explain a model
   *or* explain a metric. That's a generalisation beyond TSAP, and it's already
   visible in the scaffolding.

---

## 14. Glossary

| Term | Plain meaning |
|---|---|
| **Additive explanation** | Scores that sum to the prediction's deviation from a baseline |
| **Agent-based simulation (ABS)** | Simulating many individual actors to reproduce system behaviour |
| **Bus factor / truck factor** | How many people must leave before a project collapses |
| **Black box** | A model that gives answers without reasons |
| **Complex contagion** | Spread of costly/risky behaviour; needs repeated social reinforcement |
| **Delta (δ)** | The size of the nudge you apply to the input |
| **Dense layer** | A plain fully-connected neural layer |
| **Embedding** | A list of numbers representing a thing (node, word) in a way a model can use |
| **Epoch** | One complete pass over the training data |
| **Faithfulness** | Does the explanation match what the model actually does |
| **FOSS** | Free/Open-Source Software |
| **DeFi** | Decentralised Finance (blockchain financial protocols) |
| **DAO** | Decentralised Autonomous Organisation |
| **GNN** | Graph Neural Network |
| **GAT** | Graph Attention Network — a GNN that learns which neighbours matter |
| **Global explanation** | What the model cares about in general, across many inputs |
| **GRU** | Gated Recurrent Unit — a simpler LSTM |
| **Local explanation** | Why this one prediction, for this one input |
| **Log return** | `log(new / old)` — scale-free measure of change |
| **LSTM** | Long Short-Term Memory — a neural network for sequences |
| **Model-agnostic** | Works on any model, needing only its `predict` function |
| **MORS** | Multi-Objective Recommender System |
| **MSE** | Mean Squared Error — average of squared mistakes |
| **Multi-layer graph** | Several types of edge between the same nodes |
| **Pareto frontier** | Options where improving one goal necessarily worsens another |
| **Perturbation** | Deliberately changing the input to see what happens |
| **Sensitivity / derivative** | How much the output moves per unit of input change |
| **Sliding window** | Taking consecutive fixed-length chunks of a series |
| **Spearman correlation** | Do two lists rank things in the same order? (−1 to 1) |
| **SHAP** | SHapley Additive exPlanations — the standard attribution method |
| **Sparsity** | How few things an explanation needs to mention |
| **Stability** | Same input → same explanation, every time |
| **StandardScaler** | Rescale numbers to mean 0, spread 1 |
| **Surrogate model** | A simple model that imitates a complex one so you can inspect it |
| **Temporal graph** | A graph that changes over time |
| **TGN** | Temporal Graph Network — a GNN with memory |
| **Trend** | The overall up/down slope of a series |
| **Volatility** | How jumpy/noisy a series is |
| **Wide bridge** | Many redundant ties between two communities (CATALYST's core concept) |
| **XAI** | Explainable AI |
| **Window size** | How many past values the model is allowed to look at |

---

## 15. What I suggest we do next

In this order. Each step is small and produces something you can show.

1. **Get TSAP running.** `cd c:\catalyst\tsap_v2.1\tsap` then
   `python CaseStudyElectric.py`. Look at the four plots. Don't move on until the
   bar chart makes sense to you.
2. **Break it on purpose.** Change `defaultDelta` from 0.1 to 0.3 and re-run. Change
   `windowSize`. Watch the explanation change. This builds intuition faster than reading.
3. **Write your own `TsModel`.** Something trivial — e.g. `predict` returns the
   average of the last 3 values, or `last_value * 1.01`. Run TSAP on it. Now you
   *know* what the explanation should say, so you can check TSAP tells you the
   truth. This is the single best exercise in this document.
4. **Add a third transformation.** `transformLevel` (shift the whole series up)
   or `transformSeasonality`. This is the smallest real contribution to TSAP and
   it teaches you the pattern you'll need for TGAP.
5. **Raise the §12 findings with Iván**, especially #1.
6. **Then start TGAP:** pick a graph library (`networkx` to learn,
   `PyTorch Geometric` for real GNNs), implement `CohesionMetric.measure`
   for real, and write the first `TemporalGraphTransformation`.

Ask me for any of these and I'll write the code with you, step by step.
