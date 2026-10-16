# Lonely students in two classrooms

Two classrooms over a school year. Some students become isolated.
A "loneliness forecast" model extrapolates how many students will have no friend next term.
TGAP asks how a buddy programme - pairing isolated students with classmates - would change the forecast.

| file | what it is |
|---|---|
| `data.py` | makes `data/interactions.csv` and `data/groups.csv` |
| `model.py` | `LonelinessForecast` - the model being explained |
| `concept.py` | `IsolatedStudents` - the number of isolated students; down = a buddy programme |
| `main.py` | the step-by-step flow; change the PARAMETERS block |

```sh
python examples/projects/classroom_friendships/main.py
```

Then open `output/TUTORIAL.md`.
