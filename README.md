# TGAP

**Explain how changes to a temporal graph affect a model’s prediction.**

TGAP is a Python toolkit for model-agnostic explanations of temporal graph
models. It changes one graph concept at a time—such as bridge width, density,
centralization, churn, or bridge trend—and measures how the model’s prediction
moves.

> TGAP measures a model’s response to controlled graph changes. An explanation
> describes model behavior; it does not establish that changing the real world
> would cause the same outcome.

## Get started

TGAP includes a local browser workbench and a command line for research. The
first install starts from a TGAP checkout. It creates an isolated Python
environment, installs the workbench, and creates your first account.

### Windows

Open PowerShell in the checkout and run:

```powershell
.\tgap.cmd install
```

### Linux or macOS

Install Python 3.10 or later first. From the checkout, run:

```sh
sh ./tgap install
```

If the installer says `~/.local/bin` is missing from your PATH, add it to the
current terminal and retry `tgap start`:

```sh
export PATH="$HOME/.local/bin:$PATH"
```

The installer asks whether to add optional TGN and finance packages. It prints
an initial account and password; save the password somewhere private.
After installation, open a new terminal and use the `tgap` command:

```sh
tgap start
tgap status
tgap stop
```

`tgap start` starts the workbench and opens it in your browser. The default
address is `http://127.0.0.1:8080`. Sign in with the account printed during
installation. `tgap stop` stops the service and keeps your account, experiments,
and installed environment.

See the [installation guide](docs/12-installation-and-self-hosting.md) for
options, platform notes, and troubleshooting.

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
tgap run examples            Run the getting-started examples
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
tgap run evaluation
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
```


TGN commands need the optional TGN packages. Finance commands need the optional
finance packages. Install them when prompted, or add a group later:

```text
tgap install --tgn --yes
tgap install --finance --yes
```

Downloads and some workflows create files under the repository’s output or
real-data folders. Read the relevant workflow documentation before running
large evaluations.

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

See the [custom transformation example](examples/MyCustomTransformation.py)
and the [worked example](docs/05-TGAP-worked-example-trace.md) for the full
contract, feasibility checks, and limitations.

## Documentation

- [Documentation index](docs/README.md)
- [Installation and self-hosting](docs/12-installation-and-self-hosting.md)
- [Research dashboard guide](docs/15-research-dashboard.md)
- [Worked example](docs/05-TGAP-worked-example-trace.md)
- [Real data and preprocessing](realdata/README.md)
- [Scientific reliability audit](docs/14-scientific-reliability-audit-2026-10-08.md)

## Project layout

```text
core/       Explainer, models, metrics, transformations, and graph utilities
examples/   Small examples and the custom transformation walkthrough
realdata/   Dataset preparation and research workflows
tests/      Automated checks
workbench/  Local browser interface and its service
```

## Citation and license

TGAP is part of the CATALYST project. See [LICENSE](LICENSE) for licensing
terms and the research documentation for project attribution and study details.
