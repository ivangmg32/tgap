# Research results dashboard

Implemented and deployed: 2026-10-08. Website source:
`C:\catalyst\tgap-sandbox`. Research checkout: `C:\catalyst\tgap`.

## Open the dashboard

Visit `http://144.172.97.105:8080`, sign in with the existing researcher/admin
account, and select **Researcher**. Direct route: `/#researcher` after sign-in.
Self-registered participant accounts cannot access this page or its APIs.
No new researcher password was created or copied into documentation.

The page displays only explicitly consented study sessions and their linked
experiments. Personal experiments outside the study remain private. Empty cohorts
show no observations or unavailable statistics; no demonstration participants
are inserted into the live database.

## Explore the charts and records

Choose a study-start date range in UTC (both dates inclusive), and all/completed/
in-progress sessions; select **Apply / refresh**. This cohort includes every
experiment linked to the selected sessions, even when a job was created after
the selected end date. The displayed snapshot timestamp identifies the refresh.
The maximum cohort is 2,000 sessions; explicit coverage/truncation warnings tell
you to narrow the dates. JSON/ZIP downloads use the same filters, as a fresh
consistent database snapshot; ongoing participation can change counts between
page refresh and download.

The four summary cards distinguish unique pseudonymous participants, study
sessions, completed visits, and experiment attempts. A repeat visitor is counted
once in the participant total but can contribute several sessions/experiments.

Twelve charts show completion counts, task accuracy, median task confidence,
median time per task, ease/understanding/trust rating distributions, dataset and
model selections, job states, invalid concept-test counts, and UTC study starts.
Each has an interpretation note and SVG/PNG export. The SVG includes cohort
counts, dates and UTC provenance. Export SVG for editable publication figures;
PNG exports use twice the SVG view-box resolution.

Tabs provide searchable, paginated tables (50 rows per page):

- **Sessions & feedback:** visit/participant pseudonyms, UTC start, stage,
  completed duration and final ordinal ratings; inspect the visit to read
  feedback, submitted responses and its experiment list.
- **Task responses:** answers, correctness, confidence and elapsed time.
- **Experiments:** dataset, model, request amount, seed, status, custom-code
  indicator, original prediction and execution time. Inspect for the recorded
  configuration, saved prediction-response chart, raw result/provenance, and
  **Download full experiment JSON**.
- **Concept results:** per-direction validity, status, no-op, achieved units,
  normalization mode, achieved change, prediction difference and normalized
  impact. Invalid numbers remain unavailable, not zero.

## Export for a future paper

**Download research data ZIP** contains:

| File | Contents |
| --- | --- |
| `sessions.csv` | One row per consented visit, ratings, feedback, repeat-visit key |
| `responses.csv` | One row per submitted task response |
| `experiments.csv` | Study-linked attempts, configurations, seeds, custom code and outcomes |
| `impacts.csv` | Long-format concept/direction results, validity and normalization |
| `report.json` | Exact raw cohort records and descriptive chart statistics |
| `metadata.json` | Filters, coverage, scope, source/core/fixture SHA-256 hashes, Python/package versions, task definitions/answer keys and data dictionary |
| `README.txt` | Units, privacy and interpretation notes |

Full report JSON and plain-text analysis-note downloads are also available.
The per-experiment JSON includes the complete saved explanation, comparisons
and measured figure inputs when present, rather than only the study summary.
CSV text starting with spreadsheet formula characters is apostrophe-prefixed;
JSON preserves the original string. Mixed older/new result schemas retain all
columns with missing values blank. Empty CSVs currently contain no rows/header;
use the report/metadata data dictionary to interpret an empty cohort.

Account names, passwords, session cookies and internal owner hashes are not
exported. `participant` is the existing random visit ID; `participant_key` is a
stable, server-HMAC-derived repeat-visitor pseudonym. These are pseudonymous
records, not a guarantee of anonymization. Free-text feedback and custom code
can still identify someone; review/redact them before sharing or publication.
Withdrawals remove records from future reports and detailed-result requests;
previously downloaded files require separate handling under your retention
policy. Changing the service secret changes repeat-visitor pseudonyms.

## Scientific interpretation

Accuracy is correct/submitted answers, with submitted/eligible counts visible;
unanswered tasks are excluded, not counted as wrong. Confidence/time summaries
show medians and observed sample sizes. Task times include reading and waiting,
not just tool interaction. Finished-session duration and final ratings exclude
unfinished visits; missing values are never filled with zero. Ratings are
ordinal 1-7 responses to individual pilot questions, not a validated usability
scale. There are no significance tests, population confidence intervals, causal
claims or global rankings of incompatible concept impacts.

Repeated visits and experiments are not independent participants. The study
currently has one condition. A future paper must explain recruitment, approval,
consent, exclusion/withdrawal policy, repeat-visit handling, study design,
analysis choices, dataset preprocessing and the limits of the sample. This
reporting feature does not supply institutional or publication approval.

The new `pilot-1.1` consent notice explicitly describes researcher access to
study-linked results/custom code and repeat-visit pseudonyms. Existing records
retain their original consent version. Review original consent scope before
including older records in a paper.

## Implementation and verification

Backend: sibling `sandbox/reporting.py`; protected routes in `sandbox/app.py`:

- `GET /api/admin/report?start=YYYY-MM-DD&end=YYYY-MM-DD&status=all|complete|incomplete`
- `GET /api/admin/report/download/json|zip` with the same query filters
- `GET /api/admin/experiments/{id}` for a consented, study-linked saved result

The legacy summary/export endpoints remain supported; summary experiment counts
now also use consented study linkage. Snapshot reads use an explicit SQLite
transaction. Indexes on study starts and linked-job IDs avoid repeated full
job-table scans. The main dashboard extracts saved rows/summary fields in SQL
rather than loading every graph-rich full result into memory. Full results are
requested one experiment at a time.

Frontend: `static/researcher.js`, with independent researcher chart exporters;
it does not depend on a participant's current experiment or result tab.
Feedback/code are escaped before display. Signing out clears cached dashboard
records; stale in-flight responses cannot repopulate them. Browser tests include
a delayed report response arriving after sign-out. Existing authentication, CSRF, rate
limits, HTTPS limitations and boot supervision remain as documented elsewhere.

Validation: **45 web/API/security/worker/reporting tests passed**. Seven new
report tests cover repeat visits, denominators, missing/invalid values, dates,
completion filters, empty cohorts, admin-only access, non-consent exclusion,
exports/provenance/formula safety, withdrawal and explicit 2,000-session coverage.
Actual Chromium researcher E2E passed: 12 charts, details, search, ZIP/JSON,
SVG/PNG, safe feedback rendering, filters, empty and populated mobile layouts;
no JavaScript errors. Broader workbench browser regression is also run before
deployment. No explanation-core mathematical code was changed.

Tests: `tests/test_research.py`, `tests/research_browser_check.py` and
`tests/serve_research_test.py` in the sibling. The last is a deterministic
CAPTCHA/artificial-data **loopback-only** fixture and is never deployed or
bundled. Evidence: sibling `verification/research-dashboard-regressions.log`,
`research-report-tests.log`, `research-browser-result.json`; copied to research
`docs/verification/2026-10-08/research-dashboard/`.

Operator recovery: protected database backup before deployment under sibling
`data/backups/before-research-dashboard-2026-10-08.sqlite3`. Boot task
`TGAP-Laboratory` remains enabled and listening on port 8080. Portable self-host
bundle includes the same dashboard without any credentials, live study records
or test fixtures.

Live verification passed after deployment: existing researcher login, protected
report, seven-file ZIP with provenance, script availability and access denial
after sign-out. Automatic startup remains enabled. Final portable bundle contains
55 files and passes all six launcher/distribution checks.
