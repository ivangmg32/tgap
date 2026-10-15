# Examples — learn TGAP in six small steps

Each file is a short script. Open it, look at the **PARAMETERS** block at the
top, change a value, run it, and look at the results. Go in order; each one
adds one idea.

```sh
python examples/01_quickstart.py         # run one example
python run.py examples                   # or run them all
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
