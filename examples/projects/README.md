# Example projects — complete, self-contained studies

Each folder is a small study you can read in ten minutes and copy for your
own. Everything a study needs lives **inside its folder**: its own dataset,
its own model, its own concept (transformation), and all of its outputs.

```text
<project>/
  README.md     what the study asks, how to run it
  data.py       makes the study's dataset  ->  data/*.csv
  model.py      the model being explained (a class with predict())
  concept.py    a new concept TGAP can change (a transformation)
  main.py       PARAMETERS + the step-by-step flow
  output/       written when you run it:
                  TUTORIAL.md   <- read this first: every step, table and figure explained
                  *.csv, *.png
```

Run one, then open its `output/TUTORIAL.md`:

```sh
python examples/projects/team_silos/main.py
python run.py examples          # runs every example and project
```

## Studies with their own data, model and concept

| folder | question | model | new concept |
|---|---|---|---|
| [`team_silos`](team_silos/) | Is a coordination warning about *fewer* cross-team ties, or about one person carrying them? | `CoordinationFragility` | `LiaisonDependence` |
| [`open_source_bus_factor`](open_source_bus_factor/) | Would onboarding newcomers make a project less dependent on its top maintainers? | `BusFactorRisk` | `NewcomerOnboarding` |
| [`dao_voting_blocs`](dao_voting_blocs/) | Do swing voters reduce polarization in a DAO? | `Polarization` | `SwingVoters` |
| [`classroom_friendships`](classroom_friendships/) | Would a buddy programme change the loneliness forecast? | `LonelinessForecast` | `IsolatedStudents` |
| [`supply_chain`](supply_chain/) | Does keeping a backup partner protect against the busiest company failing? | `DisruptionExposure` | `SupplierDiversification` |
| [`epidemic_contacts`](epidemic_contacts/) | How much does an outbreak's reach depend on a few very connected pupils? | `OutbreakReach` | `SuperSpreaders` |

## Studies of Ivan's financial-market code

| folder | what it teaches | Ivan's code used |
|---|---|---|
| [`ivan_price_cache`](ivan_price_cache/) | prices, returns and risk; how the cache works | `Cache.py` |
| [`ivan_window_length`](ivan_window_length/) | how the correlation window length changes what you see | `CorrGraphs.temporalGraph` |
| [`ivan_rq_walkthrough`](ivan_rq_walkthrough/) | his four research questions, one at a time | `experimentationDatamining.py` |
| [`ivan_market_contagion`](ivan_market_contagion/) | own model + own concept on his networks, with a self-consistency check | `CorrGraphs` via `finance.networks` |
| [`ivan_threshold_robustness`](ivan_threshold_robustness/) | does the TGAP answer survive a different threshold? | `CorrGraphs` via `finance.networks` |

The Ivan studies use the stock prices stored in the repository and work
offline. For the step-by-step introduction to markets, start with
[`examples/financial/`](../financial/README.md).

## Make your own

Copy a folder, rename it, and change one file at a time: first `data.py`
(your data), then `model.py`, then `concept.py`. Rules a concept must follow
are in the docstring of `core/TemporalGraphTransformation.py`: never change
the input graph, be deterministic (seed your random choices), and say
honestly whether you keep the number of ties (`preservesEdgeCount`).
