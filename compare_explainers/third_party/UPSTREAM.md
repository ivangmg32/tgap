# Vendored: CoDy (official implementation)

| | |
|---|---|
| Repository | https://github.com/daniel-gomm/CoDy |
| Commit | `0a004c2ad171b7ded59751c2179b64bf7738693a` (2025-10-02, "Merge pull request #3 … remove-unused-code") |
| Paper | Qu et al., *CoDy: Counterfactual Explainers for Dynamic Graphs*, ICML 2025 (PMLR 267), https://proceedings.mlr.press/v267/qu25b.html |
| License | MIT, Copyright (c) 2025 Daniel Gomm — see `cody/LICENSE.md` |
| What is copied | the `cody/` Python package only (explainers, selection policies, data classes, the `TGNNWrapper` connector). Not copied: `scripts/`, `submodules/` (the two Twitter-TGN forks), `resources/`. |
| Modified | **No.** Every file is byte-identical to the commit above; `cody_manifest.sha256` lists their SHA-256 hashes and `tests/test_compare_explainers.py` checks them. |

TGAP connects its model to CoDy the way CoDy's README (§4.1 "Adding a new
target model") prescribes: a subclass of
`cody.implementations.connector.TGNNWrapper`, implemented in
`compare_explainers/cody_adapter.py`. CoDy's search (`cody.explainer.cody.CoDy`)
is called unchanged.

Python dependencies needed by the copied package: `numpy`, `pandas`, `torch`,
`tqdm`, `ipython` (CoDy's `utils.py` imports IPython for notebook detection).
`cody/implementations/tgn.py`, `ttgn.py` and `tgat.py` import the excluded
submodules and are never imported here.

To re-vendor a different commit: clone with `--recurse-submodules`, check out
the commit, copy `cody/` and `LICENSE.md` here, regenerate the manifest
(`cd third_party && find cody -type f | sort | xargs sha256sum > cody_manifest.sha256`),
and update the commit in `compare_explainers/cody_adapter.py` (`CODY_UPSTREAM`).
