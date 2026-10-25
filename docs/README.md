# TGAP documentation

Use this page as a reading path. Start with the setup steps, then choose the
guide that matches your next task. The research reports and technical audits
are reference material; you do not need them to install or use TGAP.

## First time using TGAP

1. **Run it.** Either [install the workbench](12-installation-and-self-hosting.md)
   (`tgap start` / `tgap stop`), or run the single file `python run.py` with no
   installation (see the [project README](../README.md#no-install-one-file-python-runpy)).
2. **Try the easy examples** in [`examples/`](../examples/README.md): your own
   data, your own model, your own concept, with CSV + PNG outputs.
3. [Follow an experiment from input to explanation](05-TGAP-worked-example-trace.md)
   — a complete worked example.
4. [Read the complete guide](06-TGAP-complete-guide-A-to-Z.md) for the concepts
   behind the workflow.

## Choose what to do next

| If you want to… | Read this |
| --- | --- |
| Run examples or research workflows from a terminal | [Install and run TGAP](12-installation-and-self-hosting.md), or `python run.py --help` |
| Use your own data, model or concept | [Examples](../examples/README.md) |
| Study stock markets (Ivan's finance work) | [Financial examples](../examples/financial/README.md) |
| Inspect consented study results and export research data (researcher role) | [Study dashboard and exports](15-research-dashboard.md) |
| Run the guided TGAP user study and read the paper-chart inventory | [Guided user study](16-guided-user-study.md) |
| Compare TGAP with CoDy on one TGN prediction (UCI-Messages): run, results, compatibility audit | [TGAP vs CoDy comparison](17-tgap-vs-cody-comparison.md) |
| Use TGAP from Python or understand its concepts | [Complete guide](06-TGAP-complete-guide-A-to-Z.md) |
| Start a new study in a few lines (functions, no classes) | [The wrapper](../examples/wrapper/README.md) |
| Add your own transformation | [Example 4](../examples/04_your_own_transformation.py) and the [worked example](05-TGAP-worked-example-trace.md) |
| Run or interpret real-data studies | [Real data explained simply](07-real-data-explained-simply.md) and [dataset workflow](../realdata/README.md) |
| Know what each output file means | [Real-data outputs and pipeline](08-real-data-outputs-and-pipeline.md) and [`paths.py`](../paths.py) |

## Research and project records

- [Case studies](10-case-studies.md) — examples using real temporal graphs
- [User study design](09-user-study-design.md) — study protocol and tasks
- [Scientific reliability audit](14-scientific-reliability-audit-2026-10-08.md)
- [Self-hosting and deployment notes](13-sandbox-and-self-hosting-knowledge.md)
- [TSAP explained simply](01-TSAP-explained-simply.md) — the time-series
  method TGAP is ported from

## archive/

Point-in-time documents kept for the record. They describe **earlier
versions** of the code (file names, test counts and some results have since
changed) and must not be quoted as current.

| # | document | superseded by |
|---|---|---|
| 02 | [Code walkthrough (v0.1)](archive/02-TGAP-code-walkthrough.md) | 06 |
| 03 | [Technical audit (v0.2)](archive/03-TGAP-technical-audit.md) | 06, 14, and the docstrings in `core/` |
| 04 | [v0.2 walkthrough](archive/04-TGAP-v02-walkthrough.md) | 06 |
| 11 | [Status report](archive/11-status-report.md) | `output/publication/tables/` (its own banner lists the corrections) |

For a short overview and quick commands, return to the [project README](../README.md).
