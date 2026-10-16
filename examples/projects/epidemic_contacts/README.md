# Super-spreaders in a contact network

Contacts between pupils of two schools during one term.
An "outbreak reach" model estimates how large a share of pupils an infection could reach.
TGAP asks how much that depends on a few highly connected pupils - super-spreaders.

| file | what it is |
|---|---|
| `data.py` | makes `data/contacts.csv` and `data/groups.csv` |
| `model.py` | `OutbreakReach` - the model being explained |
| `concept.py` | `SuperSpreaders` - how much of the contact runs through the most connected 10% |
| `main.py` | the step-by-step flow; change the PARAMETERS block |

```sh
python examples/projects/epidemic_contacts/main.py
```

Then open `output/TUTORIAL.md`.
