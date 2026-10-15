# Examples

Start here. Every numbered file is a complete, runnable script with a
**PARAMETERS** block at the top: change values there, run the file, and look
at the outputs.

```bash
python examples/01_quickstart.py        # one example
python run.py examples                  # all of them (sets up Python for you)
```

Outputs go to `output/examples/<name>/`: `explanation.csv/.png`,
`sensitivity.csv/.png` and `graph_over_time.csv/.png`.

| file | for when you want to… |
|---|---|
| `01_quickstart.py` | see TGAP work on a made-up graph |
| `02_your_own_dataset.py` | use **your own CSV** of interactions |
| `03_your_own_model.py` | explain **your own model** |
| `04_your_own_transformation.py` | write **your own concept** (transformation) |
| `05_real_dataset.py` | use one of the 8 real datasets |
| `06_my_project.py` | start your own study - copy this template |
| `synthetic_demos.py` | the guided tour, with interactive plotly charts |
| `MyCustomTransformation.py` | a fuller custom-concept example, with notes on feasibility |
| `toolkit.py` | the helpers the numbered examples use (loading CSVs, saving outputs) |
| `data/` | the sample data: two teams whose contact fades over 12 weeks |

## The three things you can swap

**Data** - a CSV with one row per interaction: `source,target,time`.
`time` is a date (`2024-03-20` is safest) or a number. TGAP cuts the time span
into `SNAPSHOTS` equal windows. Groups (optional) are a second CSV with
`person,group` rows; without it, TGAP detects `HOW_MANY_GROUPS` groups.

**Model** - a built-in one by name:

| name | predicts |
|---|---|
| `persistence_bridge_width` | tomorrow's bridge width = today's |
| `trend_bridge_width` | bridge width, extrapolated from its trend |
| `slope_bridge_width` | how fast the bridge grows or shrinks |
| `persistence_density` / `trend_density` | density, now / trend |
| `persistence_centralization` | how much activity sits on one person |
| `trend_clustering` | clustering, extrapolated from its trend |

or your own class with a `predict(snapshots) -> number` method
(see `03_your_own_model.py`).

**Concepts** - built-in ones by name: `bridge_width`, `centralization`,
`density`, `bridge_trend`, `churn`, or your own class with `name`,
`propertyValue` and `transformGraph` (see `04_your_own_transformation.py`).

## Reading the result

`impact` = how much the prediction moves per unit of the concept's achieved
change. Positive: more of the concept pushes the prediction **up**. Negative:
**down**. Zero: the model does not react to it. A row marked
`nothing_changed` means the graph could not be changed that way (for example,
there was nobody quiet to bring back). These are sensitivities of the
**model**, not causal claims about the world.
