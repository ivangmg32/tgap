# Supply-chain resilience across two regions

Suppliers and factories in two regions trade with each other over two years.
A "disruption exposure" model asks: if the busiest company failed, how much of the network would be cut off?
TGAP asks whether diversification - companies keeping a second trading partner - lowers that exposure.

| file | what it is |
|---|---|
| `data.py` | makes `data/orders.csv` and `data/groups.csv` |
| `model.py` | `DisruptionExposure` - the model being explained |
| `concept.py` | `SupplierDiversification` - the share of companies with a backup trading partner |
| `main.py` | the step-by-step flow; change the PARAMETERS block |

```sh
python examples/projects/supply_chain/main.py
```

Then open `output/TUTORIAL.md`.
