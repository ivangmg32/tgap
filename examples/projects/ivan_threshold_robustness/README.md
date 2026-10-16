# Ivan 5 - Does the explanation survive a different threshold?

The same model explained at every usable correlation threshold, with a verdict
per concept: robust (same direction everywhere) or not.

```sh
python examples/projects/ivan_threshold_robustness/main.py
```

Outputs in `output/`: `TUTORIAL.md`, `threshold_check.csv`,
`impacts_by_threshold.csv`, `verdicts.csv`, `robustness.png`.
