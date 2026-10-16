# Workbench source in Git

This directory preserves the complete web source, tests, bundled prepared
fixtures and reviewed publication artifacts. The live VPS deployment remains
outside this checkout at `C:\catalyst\tgap-sandbox`; its accounts, configuration,
database, logs and virtual environment are excluded from Git.

From this directory, using an environment with `requirements.txt`, HTTP test
client and Playwright dependencies installed:

```powershell
python -m unittest discover -s tests -p test_*.py -v
```

The browser fixture scripts bind only loopback and use deterministic test-only
CAPTCHA answers. Never publish those fixture servers. See the repository's
`docs/15-research-dashboard.md` for the research-dashboard workflow and other
knowledge/audit documents for reproducibility and deployment limits. Standalone
scientific audits require prepared fixtures under `data/datasets`; the installed
self-host workbench supplies them. Running source tests stages them temporarily.

Rebuild the portable installer snapshot from the repository root:

```powershell
python scripts/bundle-sandbox.py
```

To rebuild from the deployed sibling instead, pass `--source` explicitly.
Production deployment/configuration is separate; committing or rebuilding the
bundle does not restart the live service.
