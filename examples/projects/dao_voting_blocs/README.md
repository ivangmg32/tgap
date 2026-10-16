# Voting blocs in a DAO

A decentralised organisation (DAO) where members vote on proposals. Two blocs form.
A "polarization" model measures how much more members vote with their own bloc than across.
TGAP asks how swing voters - members who vote with both blocs - affect polarization.

| file | what it is |
|---|---|
| `data.py` | makes `data/co_votes.csv` and `data/groups.csv` |
| `model.py` | `Polarization` - the model being explained |
| `concept.py` | `SwingVoters` - the share of members who vote with both blocs |
| `main.py` | the step-by-step flow; change the PARAMETERS block |

```sh
python examples/projects/dao_voting_blocs/main.py
```

Then open `output/TUTORIAL.md`.
