# Team silos after a reorganisation

Two teams, one year of messages. Contact across the teams fades and runs
more and more through one liaison. A *coordination fragility* model warns
when the teams drift apart; TGAP explains what drives the warning.

| file | what it is |
|---|---|
| `data.py` | makes `data/messages.csv` and `data/teams.csv` |
| `model.py` | `CoordinationFragility` - the model being explained |
| `concept.py` | `LiaisonDependence` - a new concept: how much cross-team contact runs through one person |
| `main.py` | the step-by-step flow; change the PARAMETERS block |

```sh
python examples/projects/team_silos/main.py
```

Then open `output/TUTORIAL.md`.
