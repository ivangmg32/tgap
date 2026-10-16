# Bus factor in an open-source project

A small open-source project: a few maintainers and a larger, shifting community of contributors.
A "bus factor risk" model says how much the project depends on its top two people.
TGAP asks whether onboarding more newcomers would lower that risk - or raise it.

| file | what it is |
|---|---|
| `data.py` | makes `data/reviews.csv` and `data/groups.csv` |
| `model.py` | `BusFactorRisk` - the model being explained |
| `concept.py` | `NewcomerOnboarding` - the share of people taking part; onboarding newcomers through the community |
| `main.py` | the step-by-step flow; change the PARAMETERS block |

```sh
python examples/projects/open_source_bus_factor/main.py
```

Then open `output/TUTORIAL.md`.
