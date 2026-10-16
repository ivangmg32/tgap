# Examples — learn TGAP in six small steps

Each file is a short script. Open it, look at the **PARAMETERS** block at the
top, change a value, run it, and look at the results. Go in order; each one
adds one idea.

```sh
python examples/01_quickstart.py         # run one example
python run.py examples                   # or run them all
python run.py examples/01_quickstart.py     # one file, no install needed
tgap run script examples/01_quickstart.py   # one file, via the tgap command
tgap run examples                        # (same, if you installed the workbench)
```

| step | file | you learn to… | you change |
|---|---|---|---|
| 1 | [`01_quickstart.py`](01_quickstart.py) | run TGAP and read its answer | graph size, model, concepts |
| 2 | [`02_your_own_dataset.py`](02_your_own_dataset.py) | use **your own data** (a CSV) | file path, column names |
| 3 | [`03_your_own_model.py`](03_your_own_model.py) | explain **your own model** | the `predict()` method |
| 4 | [`04_your_own_transformation.py`](04_your_own_transformation.py) | write **your own concept** | a small class |
| 5 | [`05_real_dataset.py`](05_real_dataset.py) | use one of the 8 real datasets | the dataset name |
| 6 | [`06_my_project.py`](06_my_project.py) | put it all together — **copy this for your study** | everything |

## The wrapper - the shortest way

[`wrapper/`](wrapper/README.md) is TGAP in the style of TSAP: your model and
your concept are **plain functions**, and a study is a few lines
(`Wrapper.fromCsv(...)`, `@w.model`, `@w.concept`, `w.explain()`). Six
examples, from five lines to Ivan's stock market.

## Complete example projects

[`projects/`](projects/README.md) has eleven self-contained studies - team
silos, open-source bus factor, DAO voting blocs, classroom friendships,
supply chains, epidemics, and five studies of Ivan's financial code. Each
folder has its own data, model, concept and outputs, and every run writes a
`TUTORIAL.md` that walks through the results.

## Financial markets

[`financial/`](financial/README.md) has seven more examples, from "which
stocks move together?" to Ivan's full statistical study and a complete
30-stock TGAP study.

## What you see

Every example prints its steps, then a small table:

```text
  [1/4] Building a made-up temporal graph: 6 snapshots, two groups of 10 people
  [2/4] Model: trend_bridge_width (bridge width, extrapolated from its trend ...)
  [3/4] Concepts to test: bridge_width, centralization, density, ...
  [4/4] Explaining

      The model predicts 8.0000 on your data.
      Nudging each concept by 10%:

        concept                  direction        impact
        ------------------------------------------------
        Bridge Width             increase        +8.0000
        Bridge Width             decrease        -8.0000
        ...
```

**impact > 0**: more of that concept raises the prediction. **< 0**: lowers it.
**0**: the model ignores it. These describe the *model*, not causes in the
real world.

And it saves, in `output/examples/<example name>/`:

| file | what it shows |
|---|---|
| `explanation.csv` / `.png` | the table above, as data and as a bar chart |
| `sensitivity.csv` / `.png` | the prediction as each concept goes from −50 % to +50 % |
| `graph_over_time.csv` / `.png` | your data: ties and bridge width per snapshot |
| `what_changed.png` | the graph **before / after / difference** for every concept (red = ties added, blue dashed = ties removed) |
| `when_it_mattered.png` | **which snapshot** the concept mattered in |
| `edge_impact.png` | **which single ties** the model leans on |
| `edge_over_time.png` | which tie, in which snapshot |
| `node_impact.png` | **which people / stocks** the model leans on |
| `impact_heatmap.png` | every concept at every size of nudge, in one picture |
| `bridge_matrix.png` | ties between every pair of groups (only with 3+ groups) |
| `beeswarm.png`, `boxplot.png` | the **global** explanation: every impact over many sliding windows, as a beeswarm and a boxplot (paper figs. 9, 10) |
| `dependence.png` | does the impact depend on how much of the concept the window had? (paper fig. 8) |
| `global_impacts.csv`, `global_summary.csv` | every observation behind those, and n / median / quartiles per concept |
| `how_tgap_works.png` | the method as one diagram (paper fig. 0) |
| `side_effects.png` | does a concept change ONLY its own property? (concept independence) |
| `concept_trajectories.png` | how the graph's properties move over time (what models read) |
| `validity_map.png` | which experiments can be trusted, and why not the others |
| `impacts_by_direction.png` | more vs less of each concept, side by side (paper fig. 1) |
| `impact_distribution.png` | the spread of impacts per concept (paper fig. 6) |
| `sparsity.png` | how many concepts / ties / nodes actually carry the answer |
| `tsap_summary.png` | the original TSAP summary chart (signed-log bars) |
| `TUTORIAL.md` | all of the above, explained step by step |

The last seven are the same kinds of pictures as the paper
(`output/publication/figures`), drawn from your own data by
[`figures.py`](figures.py). They re-ask your model a limited number of times
(40 per picture); a very slow model can skip them with
`toolkit.explainAndSave(..., figures=False)`.

## The three things you can swap

**1. Data** — a CSV with one row per interaction:

```text
source,target,time
alice,bruno,2024-01-01
carla,ines,2024-01-02
```

`time` is a date (`2024-03-20` is safest) or a number. Commas or semicolons
and files saved by Excel all work. Known groups go in a second CSV with
`person,group` rows; without one, TGAP finds groups itself. The sample files
in [`data/`](data/) show the format: two teams whose contact fades.

**2. Model** — pick a built-in one by name:

| name | predicts |
|---|---|
| `persistence_bridge_width` | tomorrow's bridge width = today's |
| `trend_bridge_width` | bridge width, extrapolated from its trend |
| `slope_bridge_width` | how fast the bridge grows or shrinks |
| `persistence_density`, `trend_density` | density, now / trend |
| `persistence_centralization` | how much activity sits on one person |
| `trend_clustering` | clustering, extrapolated from its trend |

…or write your own: any class with `predict(snapshots) -> number`
([example 3](03_your_own_model.py)).

**3. Concepts** — built-in: `bridge_width`, `centralization`, `density`,
`bridge_trend`, `churn`. Or your own class with `name`, `propertyValue()` and
`transformGraph()` ([example 4](04_your_own_transformation.py)).

## More

| file | what it is |
|---|---|
| [`more/synthetic_demos.py`](more/synthetic_demos.py) | the guided tour, with interactive plotly charts |
| [`more/MyCustomTransformation.py`](more/MyCustomTransformation.py) | a fuller custom concept, with notes on feasibility |
| [`toolkit.py`](toolkit.py) | the helpers the examples use (loading CSVs, saving results) |
