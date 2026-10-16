# TGAP

**Explain how changes to a temporal graph affect a model’s prediction.**

TGAP is a Python toolkit for model-agnostic explanations of temporal graph
models. It changes one graph concept at a time—such as bridge width, density,
centralization, churn, or bridge trend—and measures how the model’s prediction
moves.

> TGAP measures a model’s response to controlled graph changes. An explanation
> describes model behavior; it does not establish that changing the real world
> would cause the same outcome.

**Quick links:** [Start here](#get-started) · [One file, no install](#no-install-one-file-python-runpy) ·
[Easy examples](#easy-examples-your-data-your-model-your-concept) ·
[Commands](#everyday-commands) · [Python API](#use-tgap-from-python) ·
[Documentation index](docs/README.md)

## Get started

### The fastest way - one command, nothing to set up

Open a terminal **in the TGAP folder** and run:

```sh
py run.py start          # Windows   (if "py" is not found:  python run.py start)
python3 run.py start     # macOS / Linux
```

That's all. The first time, it installs everything it needs (2-3 minutes),
prints your account and password, and opens the workbench in your browser.
Stop it with `py run.py stop` (Windows) or `python3 run.py stop`.

This never depends on PATH settings, so it works even where the short `tgap`
command is not available.

> **Windows tip - opening a terminal in the right folder:** open the TGAP
> folder in File Explorer, click the address bar, type `cmd` and press Enter.

| command | does |
|---|---|
| `py run.py start` | start the workbench (installs it the first time) |
| `py run.py stop` | stop it - accounts and results are kept |
| `py run.py status` | is it running? where is the accounts file? |
| `py run.py path` | make the short `tgap` command work in your terminal |
| `py run.py` | run the demos and examples instead (no workbench) |

The rest of this section describes the same things in more detail.

### Two ways to use TGAP

There are two ways to use TGAP. Pick one:

| | **A. Workbench** (`tgap start` / `tgap stop`) | **B. One file** (`python run.py`) |
|---|---|---|
| what you get | a browser interface + the research command line | the research pipeline and the easy examples, in the terminal |
| install | once, into `~/.tgap` (adds `tgap` to your PATH) | nothing - the first run sets itself up inside the project folder |
| Python | 3.10 or newer | 3.9 or newer |
| start here | [steps 1-4 below](#1-get-the-tgap-checkout) | [one command](#no-install-one-file-python-runpy) |

Both use the same TGAP code and write the same outputs.

### Workbench: follow these steps in order. You only need to install once.

### 1. Get the TGAP checkout

If you already have this repository on your computer, open a terminal in its
folder and continue to step 2. Otherwise, clone the `real-data` branch, which
contains the current launcher and guides:

```sh
git clone --branch real-data https://github.com/ivangmg32/tgap.git
cd tgap
```

### 2. Install TGAP

The first install creates an isolated Python environment, installs the
workbench, and creates your first account. Windows can offer to install Python
if it is missing. Linux and macOS need Python 3.10 or newer with `venv` support.

**Windows (PowerShell):**

```powershell
.\tgap.cmd install
```

**Linux or macOS:** Install Python 3.10 or later first, then run from the
repository folder:

```sh
sh ./tgap install
```

If the installer says `~/.local/bin` is missing from your PATH, that is the
Linux/macOS instruction. In that shell, add it to the current terminal:

```sh
export PATH="$HOME/.local/bin:$PATH"
```

On Windows, do not use `export`. Usually, close and reopen PowerShell after
installation. To update the current PowerShell window for the default install,
run:

```powershell
$env:Path = "$env:USERPROFILE\.tgap\bin;$env:Path"
```

For a custom install folder, replace `$env:USERPROFILE\.tgap\bin` with that
folder's `bin` path.

If `tgap` is not recognized, use `py run.py start` from the TGAP folder
(always works), or run `py run.py path` to make `tgap` work. In PowerShell
you can also run the launcher in the repository folder directly:

```powershell
.\tgap.cmd start
```

Use `.\tgap.cmd status` and `.\tgap.cmd stop` the same way. The file named
`tgap` without `.cmd` is the Linux/macOS launcher.

The installer asks whether to add optional TGN and finance packages. It prints
the initial `researcher` username and a generated password; save the password
somewhere private.

### 3. Start the workbench

After installation, open a new terminal on Windows. On Linux/macOS, continue
in the current terminal if you added `~/.local/bin` to PATH; otherwise open a
new terminal. Run:

```text
tgap start
```

TGAP opens the workbench in your browser. If it does not, visit
`http://127.0.0.1:8080` and sign in with the account from step 2. The service
runs on your own computer by default.

### 4. Run an example and stop

Open another terminal in the repository folder and try:

```text
tgap run examples
```

When you are done, stop the local service:

```text
tgap stop
```

Stopping TGAP keeps your account, experiments, and installed environment.

See the [installation guide](docs/12-installation-and-self-hosting.md) for
custom setup, more commands, platform notes, and troubleshooting.

## No install: one file, `python run.py`

If you do not want the workbench, one Python file runs everything. You only
need **Python 3.9 or newer** ([python.org](https://www.python.org/downloads/);
on Windows tick *"Add python.exe to PATH"*).

```sh
cd tgap
python run.py            # Windows: if "python" is not found, use  py run.py
```

On the first run `run.py` checks your Python, creates a private environment in
the project's `.venv/` folder and installs the libraries there (1-3 minutes,
first run only; your system Python is not touched). It keeps temporary files
and caches inside the project (`.tgap_cache/`), so a full, locked or non-ASCII
system `TEMP` folder cannot break a run. Then it runs a quick tour: an
environment check, the demos and the easy examples.

If anything goes wrong you get a short message in plain English saying what
happened and how to fix it; technical details go to `output/logs/`.

| command | what it runs | time |
|---|---|---|
| `python run.py` | check + demos + easy examples | ~2 min |
| `python run.py examples` | only the easy examples | ~30 s |
| `python run.py all` | the full research pipeline (downloads 8 datasets, ~100 MB) | ~11 min |
| `python run.py realdata publication` | any steps, in the order given | |
| `python run.py tests` | the automatic test suite | ~9 min |
| `python run.py tgn --with-torch` | also install PyTorch for the learned model | |
| `python run.py finance` | stock markets: TGAP + Ivan's RQ1-RQ4 (offline) | ~2 min |
| `python run.py --with-finance` | also install `yfinance` to download new stock prices | |
| `python run.py --help` | every step and option | |
| `python run.py reset` | delete `.venv/` and caches, start fresh | |

## Easy examples: your data, your model, your concept

Six short scripts in [`examples/`](examples/). Each starts with a
**PARAMETERS** block: change the values, run the file, and look at the CSV and
PNG files it writes to `output/examples/<name>/`.

```sh
python examples/01_quickstart.py      # or: python run.py examples   /   tgap run examples
```

| file | what you change | what it shows |
|---|---|---|
| [`01_quickstart.py`](examples/01_quickstart.py) | size of a made-up graph, model, concepts, delta | TGAP in 30 seconds |
| [`02_your_own_dataset.py`](examples/02_your_own_dataset.py) | path to **your CSV** and its column names | explaining a model on your own data |
| [`03_your_own_model.py`](examples/03_your_own_model.py) | the body of `predict()` | plugging in **your own model** |
| [`04_your_own_transformation.py`](examples/04_your_own_transformation.py) | a 20-line class | writing **your own concept** |
| [`05_real_dataset.py`](examples/05_real_dataset.py) | the dataset name | one of the 8 real datasets (downloads once) |
| [`06_my_project.py`](examples/06_my_project.py) | all of the above | **template**: copy it and make it yours |

**The shortest way - the wrapper:** your model and your concept are plain
functions, a study is a few lines. See [`examples/wrapper/`](examples/wrapper/README.md)
(`from tgap_wrapper import Wrapper`).

**Complete studies:** [`examples/projects/`](examples/projects/README.md)
has eleven self-contained projects - each folder with its own dataset,
model, concept and outputs - including five studies of Ivan's financial
code. Every example and project writes a **`TUTORIAL.md`** next to its
results that walks through each step, table and figure.

Every run writes `explanation.csv/.png` (impact of each concept),
`sensitivity.csv/.png` (the prediction as each concept goes from -50 % to
+50 %) and `graph_over_time.csv/.png` (your temporal graph per snapshot).

**Your own dataset** is a CSV with one row per interaction - who, with whom,
when:

```text
source,target,time
alice,bruno,2024-01-01
carla,ines,2024-01-02
```

`time` may be a date or a number; commas or semicolons, UTF-8 or Excel's
Windows encoding all work. Known groups (teams, departments) can be given as a
second CSV of `person,group` rows; otherwise TGAP finds them. More in
[`examples/README.md`](examples/README.md).

## Financial markets

Ivan's stock-market work is part of TGAP ([`finance/`](finance/__init__.py)):
daily prices become correlation networks over time, strong co-movements
become ties, sectors become communities, and TGAP explains models of the
market - with the same validity checks as every other dataset.

```sh
python examples/financial/01_stock_correlations.py   # start here (offline)
python -m finance.run_finance                        # full TGAP study, Ivan's 8 stocks
python -m finance.run_finance --wide                 # 30 stocks, 6 sectors
python -m finance.experimentationDatamining          # Ivan's RQ1-RQ4
```

Seven step-by-step examples: [`examples/financial/`](examples/financial/README.md).
A full study (`python -m finance.run_finance`) writes, next to the report and
the six overview figures, **`insight.md`**: the paper-style pictures drawn on
the stock network itself - which stocks and ties each concept changes, which
pair or single stock a model leans on, and in which window.
Downloading new stock prices needs `python run.py --with-finance` (or
`tgap install --finance`); the cached prices of Ivan's eight stocks need
nothing extra.

## What you can do

- **Explore explanations in your browser.** Choose a sample temporal graph,
  model, transformation, perturbation, and seed; inspect results and export
  them for later use.
- **Run research workflows.** Use the managed environment for examples,
  evaluations, real datasets, publication figures, and optional learned-model
  experiments.
- **Extend the method.** Implement a transformation class and pass it to the
  explainer. The explainer does not need to know about your specific concept.

The workbench runs locally on your computer. It is private by default and binds
to `127.0.0.1`; other computers cannot connect unless you deliberately change
the host setting.

## Everyday commands

```text
tgap install                 Install or update the managed environment
tgap start                   Start the local workbench
tgap status                  Check whether it is running
tgap stop                    Stop it; keep your data
tgap start --port 8090       Use another port
tgap start --no-browser      Start without opening a browser
tgap run examples            Run the easy examples (CSV + PNG outputs)
tgap --help                  Show command help
```

On a first install, use the checkout launcher shown above (`.\tgap.cmd` on
Windows or `sh ./tgap` on Linux/macOS). After installation, use `tgap` from a
new terminal. To choose a custom installation directory, pass `--home` before
the command, for example `tgap --home D:\TGAP start` on Windows.

## Run research workflows

Run these from a terminal after installing TGAP. Research workflows use the
managed Python environment and the source checkout.

```text
tgap run examples
tgap run demos
tgap run paper
tgap run download
tgap run real-data email_eu_core
tgap run compare
tgap run ncommunity email_eu_core
tgap run tgn email_eu_core
tgap run tgn-stability email_eu_core
tgap run publication
tgap run tests
tgap run finance --graphs 20
tgap run finance-tgap --wide
```


TGN commands need the optional TGN packages. Finance commands need the optional
finance packages. Install them when prompted, or add a group later:

```text
tgap install --tgn --yes
tgap install --finance --yes
```

Every workflow writes to exactly one folder, defined once in
[`paths.py`](paths.py):

| workflow | writes to |
|---|---|
| `examples` | `output/examples/<name>/` |
| `paper` | `output/synthetic/` (the synthetic known-truth evaluation, RQ1-RQ8) |
| `download` | `data/` (raw files, not in git) |
| `real-data` | `output/real_data/<mode>/<dataset>/` |
| `compare` | `output/comparison/<mode>/` |
| `ncommunity` | `output/ncommunity/<dataset>/` |
| `tgn`, `tgn-stability` | `output/tgn/`, `output/tgn_stability/` |
| `finance` | `output/finance/datamining/` (Ivan's RQ1-RQ4) |
| `finance-tgap` | `output/finance/<market>/` (TGAP on stock markets) |
| `publication` | `output/publication/{figures,tables,attribution}/` |

## Use TGAP from Python

For a small synthetic example, run `tgap run examples`. To use the API in your
own project, clone this repository and install its dependencies from the
repository root:

```sh
pip install -r requirements.txt
pip install --no-deps -e .
```

Then import the explainer and concepts you need:

```python
from core import (
    BridgeWidthMetric,
    BridgeWidthTransformation,
    CentralizationTransformation,
    TgapExplainer,
    TrendTemporalModel,
    makeTemporalGraph,
)

snapshots, communities = makeTemporalGraph(
    nSnapshots=6,
    nPerCommunity=8,
    bridgeWidth=10,
    seed=1,
)

model = TrendTemporalModel(BridgeWidthMetric(communities))
explainer = TgapExplainer(model, [
    BridgeWidthTransformation(communities, seed=42),
    CentralizationTransformation(communities, seed=42),
])

impacts = explainer.explain(snapshots)
print(impacts)
```

The result contains an impact for each tested concept and direction. TGAP
normalizes impact by the change the transformation actually achieved; a
transformation may be unable to reach its requested change on a particular
graph.

## Add a transformation

A transformation measures one concept and applies a controlled change to a
graph. Implement the transformation contract, then pass an instance to
`TgapExplainer`:

```python
from core import TemporalGraphTransformation

class MyTransformation(TemporalGraphTransformation):
    name = "My concept"
    preservesEdgeCount = False

    def propertyValue(self, graph_or_history):
        # Return a numeric measurement of your concept.
        ...

    def transformGraph(self, graph, delta):
        changed = graph.copy()
        # Apply the requested change without mutating the input.
        ...
        return changed
```

See the [custom transformation example](examples/more/MyCustomTransformation.py)
and the [worked example](docs/05-TGAP-worked-example-trace.md) for the full
contract, feasibility checks, and limitations.

## Documentation

- [Documentation index](docs/README.md)
- [Installation and self-hosting](docs/12-installation-and-self-hosting.md)
- [Study dashboard and exports](docs/15-research-dashboard.md) (researcher role)
- [Worked example](docs/05-TGAP-worked-example-trace.md)
- [Real data and preprocessing](realdata/README.md)
- [Scientific reliability audit](docs/14-scientific-reliability-audit-2026-10-08.md)

## Project layout

```text
run.py        One-file runner: setup + any workflow, no install
tgap, tgap.cmd, bootstrap.py, tgap_cli/
              The `tgap` command (install / start / stop / run)
paths.py      Every input and output folder, defined once
core/         Explainer, models, metrics, transformations, graph utilities
examples/     Easy examples (your data / model / concept) + sample data
experiments/  Synthetic known-truth evaluation (RQ1-RQ8)
realdata/     Dataset preparation, research workflows, publication figures
workbench/    Local browser interface and its service
tests/        Automated checks
docs/         Guides (see docs/README.md); old versions in docs/archive/
finance/      Stock markets: Ivan's correlation networks + the TGAP bridge
contrib/      Early drafts, kept for the record
data/         Raw downloads (not in git)
output/       Every generated result (see the table above)
```

## Citation and license

TGAP is part of the CATALYST project. See [LICENSE](LICENSE) for licensing
terms and the research documentation for project attribution and study details.
