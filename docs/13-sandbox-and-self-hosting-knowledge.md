# TGAP workbench and self-hosting knowledge

## Latest conversation handoff - 2026-10-08

### Researcher dashboard follow-up (implemented and deployed)

The user's next request was a researcher view of users' experiences and
experiments with charts and detailed data for a future paper. This now lives in
**Researcher** (`/#researcher`), admin-only, showing consented study-linked data;
non-study personal experiments remain private. There are 12 exportable charts,
UTC study-start/completion filters, unique/repeat-visit counts, searchable/paged
sessions-feedback/responses/experiments/concept tables, saved-experiment detail
and full JSON download. ZIP exports four CSVs, full report, source/core/fixture
hashes, package versions, task answer keys and data dictionary. No invented live
participant records, incompatible pooled impacts or significance claims.
New consent notice is pilot-1.1; historical records keep their original version.
Read **docs/15-research-dashboard.md** for usage, scientific interpretation,
API paths, privacy, tests and recovery. Implementation: sibling
`sandbox/reporting.py`, protected routes in `sandbox/app.py`,
`static/researcher.js`. 45 web tests pass, including seven new research tests;
researcher browser E2E verifies charts/details/exports/mobile without JS errors.
Test fixtures remain loopback-only and excluded from the portable bundle.

The live website now supports self-service **Create account** and **Sign in**,
with a fresh CAPTCHA for both. This supersedes the earlier manual-only account
policy below. Registration creates participant accounts; researcher/admin access
still comes only from the protected sibling `users.txt`. Registered passwords
are salted PBKDF2-HMAC-SHA256 hashes (600,000 iterations) in
`C:\catalyst\tgap-sandbox\data\laboratory.sqlite3`. Never put credentials in
this memory file or the portable bundle. No email/password-reset flow exists.

Implementation: sibling `sandbox/security.py`, `sandbox/app.py`,
`static/auth.js`, welcome-page markup/styles and `sandbox/serve.py`.
CAPTCHA is local, single-use, five-minute, IP/cookie/purpose bound. Persistent
login/registration/CAPTCHA limits and bounded password hashing supplement it;
CAPTCHA alone does not prevent DoS or network-level DDoS. Request/body/worker/
queue/storage limits are documented in the sibling README. New job admission
stops at 5,000 saved jobs, over 512 MiB DB+WAL or below 256 MiB free disk.
Registration defaults open; `registration_enabled: false` closes it on restart.
`registration_attempts_per_ip_hour` defaults 20, bounded 1-100 for shared labs.
The existing HTTP public address still needs HTTPS/upstream protection before
handling real study credentials. A proxy currently shares the peer-IP limits.

Scientific audit: 270 configurations across all 13 datasets, six web models,
five built-in transformations and multiple deltas/seeds passed 142,651 numerical
checks. Independent calculations cover bridge counts, density, Freeman degree
centralization, triangle-based average clustering, closed-form OLS forecast/slope,
normalization, exact graph histories and measured attribution figures. A separate
78-case check verified 2,178 valid live sweep samples. Invalid tests remain null,
not zero; no-op interpretations remain distinct. Mathematical agreement establishes
faithfulness on tested inputs, not causal truth, forecast accuracy or peer-review
approval. All 78 real API endurance jobs across 13 datasets/six models completed with zero
failures using three concurrent participants. Website regression: 38 passed;
research/CLI: 539 tests, 521 passed/18 optional or intentional skips. See
`docs/14-scientific-reliability-audit-2026-10-08.md` for final evidence.

Corrections made during testing: SQLite connections now close explicitly;
zero-baseline relative concepts show absolute achieved-change units and retain
`requested_delta_mode`/`property_baseline`; polling backs off, retries temporary
429/503 responses, and allows four minutes for the bounded queue instead of
prematurely stopping at 55 seconds. The original research core was unchanged.
Older saved runs should be rerun to acquire the corrected unit metadata.

Tests/scripts persist in sibling `tests/`: `test_workbench.py`,
`test_security.py`, `test_worker_reliability.py`, `browser_check.py`,
`scientific_audit.py`, `sweep_audit.py`, `reliability_audit.py`, and
`api_soak_audit.py`. `serve_test_instance.py` mocks CAPTCHA only in a disposable
**loopback-only test process**; it must never be used as the public server and
is not bundled. Production CAPTCHA has no test bypass. Evidence is copied into
`docs/verification/2026-10-08/`; raw operational logs remain in sibling
`verification/`. Browser tests cover self-registration, CAPTCHA error recovery,
sign-out/sign-in, tutorial-first flow, numerical/visual/custom results, multiple
models/datasets/settings, exports, privacy and mobile layouts, plus a simulated
429 during polling. Reliability tests deliberately kill a worker/API process
on a disposable clone and check supervisor/queue/session/database recovery.

Live boot task `TGAP-Laboratory` remains enabled and running on port 8080.
Protected backup: sibling `data/backups/before-self-service-auth-2026-10-08.sqlite3`
and previous portable app ZIP. The self-host bundle is refreshed for the same
new features. Read the audit and sibling README before further security changes.

## Previous conversation handoff — 2026-10-07

The user plans to continue later. Read this file and `CODEBASE_MEMORY.md`
before future changes. Research checkout: `C:\catalyst\tgap`; independent
live website source: `C:\catalyst\tgap-sandbox`. The service is running at
`http://144.172.97.105:8080`, with boot startup/recovery through the
`TGAP-Laboratory` Windows scheduled task. Credentials remain in the sibling
`users.txt`; do not copy passwords into documentation or the bundle.

Accepted user requirements and completed follow-up changes:

1. Make experiment outputs visual: prediction/sensitivity charts, original
   versus transformed networks and histories, SVG/PNG downloads.
2. Improve navigation and put tutorials/information first after login.
   Start here now offers a prominent prepared first-experiment action,
   numbered click instructions, expected outputs and contextual Laboratory
   guidance before/after a run. Every menu has page instructions.
3. Increase readability: larger body/menu/control/help/chart-label fonts,
   darker instructional text, responsive layouts and mobile checks.
4. Emphasize that TGAP is an explainer. Results lead with the actual model,
   dataset and baseline; a plain-language concept-level explanation lists
   measured responses, no response after effective changes, no-ops and
   excluded tests separately. Save explanation exports a text report.
5. Add easy What this means descriptions under result cells, explanation
   cards, figures, networks, histories and relationships, using actual values.
6. Add existing publication charts: the Paper figures navigation menu is a
   private reference gallery of 12 reviewed PNG/PDF artifacts copied from
   `output/publication`. Superseded charts are omitted; scope/provenance is
   preserved. It is not the participant's own output.
7. Add graph relationships from the actual experiment: community diagrams,
   before/after connection matrices and node-degree comparisons, selectable
   by tested concept/direction in Relationships.
8. The user clarified that the publication-style charts must ALSO be drawn
   for their own selected model/data. This is implemented: each new run
   computes bounded node/edge occlusion, one-snapshot responses, edge-time
   tests and delta sweeps. Paper-style figures in the RESULTS shows actual
   run-specific workflow, local bars/attributed network, temporal responses,
   heatmap, independent per-concept beeswarms/boxplots/request-size curves,
   dependence scatters and community plots. Never substitute saved paper
   images for those generated results.

### How the user views their own publication-style charts

Sign in → Laboratory → select Ecosystem (dataset), Prediction model and
Transformations → Run experiment → wait for completion → click Open my
paper-style figures or the Paper-style figures result tab → expand the
sections → download SVG/PNG as desired. Rerun older saved experiments to
obtain new measurements. Full JSON includes the measured rows and coverage.
The separate Paper figures menu displays reference charts from the paper.

### Verification and implementation state at handoff

Latest checks: 15 API/engine tests passed (about 27 seconds), six launcher/
distribution checks passed, and functional Playwright checks passed for live
chart families, image exports, legacy rerun prompts and mobile layout.
Earlier original research suite: 533 tests, 531 passed and two skipped.
No core mathematical implementation was changed by these website additions.
The live service health was checked successfully. No real VPS reboot or
independent external-network reachability test was completed.

Authoritative new modules: `sandbox/analyses.py`, `static/live-figures.js`,
`static/relationships.js`, `static/onboarding.js` and `static/figures.js` in
the sibling source. Supporting changes are in engine/app/static HTML/CSS/JS.
Portable distribution refreshed: `tgap_cli/data/sandbox.zip` plus SHA256,
51 bundled files at the latest build, excluding credentials and live data.
Refresh after sibling edits using `python scripts/bundle-sandbox.py`.
Refresh the reference gallery with `python scripts/publish-paper-figures.py`
first if publication artifacts change. Existing personal installs receive
updates by stopping, rerunning `tgap install`, and starting again.

Scientific boundaries to preserve: main concept scores remain normalized
perturbation responses, not baseline additive contributions or causal
claims. Occlusion plots are distinct additional local explanations.
Coverage is partial and explicitly labeled; missing measurements are not
zero. Distributions summarize tested request sizes on a fixed input/model,
not independent participants or training seeds. Trained TGN seed stability
requires a separate multi-seed research workflow and is marked unavailable
for the transparent web models. Additional live-figure calls are bounded
and reported separately from the original 1+2K concept explanation calls.

Windows Chromium screenshots can stall intermittently; functional browser
checks support `--no-screenshots` and background-throttling disable flags.
This does not disable SVG/PNG download assertions. The service remains HTTP;
HTTPS/domain configuration and cross-platform runtime checks are still
outside the completed verification. Details and operator instructions follow.

Updated 2026-10-07. This document supplements `CODEBASE_MEMORY.md` and records
the implementation for future questions and changes. The core explanation
algorithm and original research protocol were preserved.

## Visual-output and navigation update

## Paper gallery and graph relationships

### Live publication-style figures for every user experiment

The paper gallery is a reference only. Newly completed experiments now also
generate actual publication-style figures from their own selected dataset,
model, concepts, delta and seed. The Figures view has a prominent Open my
paper-style figures button; the Paper-style figures result tab organizes
the charts into workflow, local explanations, temporal responses,
distributions, dependence and community relations. This uses no saved paper
image. Older saved experiments must be rerun for these measurements.

`sandbox/analyses.py` performs bounded additional measurements:
- Node isolation: up to 12 nodes selected by total degree, with the node set
  preserved; edge occlusion: up to 16 structurally preselected candidate
  edges removed across the full sequence. Existing core attribution APIs
  supply measured responses and coverage.
- One-snapshot concept edits for the first three selected concepts' increase
  direction, using the exact captured transformed graphs. Invalid global
  perturbations are excluded; edge-count checks also apply per snapshot.
  Up to eight original time steps are evaluated, always including the last.
- Up to four actually evaluated edges, selected by measured whole-sequence
  response, are removed one at a time in those selected snapshots. Absent
  edges are recorded no-ops; missing measurements are not represented as zero.
- A delta sweep at half the chosen amount (floor 2%), chosen amount, and
  twice the amount (ceiling 50%), in both directions for each concept.
  The chosen-amount results reuse the main run; extra requests use the
  original feasibility/trend gates. Only valid completed rows enter plots.

The detailed model-call/time budget is 128 calls and 10 seconds. Completed
sections are preserved if another reaches its budget. The original concept
score still costs 1+2K calls; `figure_model_calls` and `total_model_calls`
report the extra actual prediction calls separately. Results schema 3 stores
`analyses`, measured rows, partial coverage, selection rules, missing-section
reasons and timing. All are included in Full JSON. Main concept scores and
original core source are unchanged.

`static/live-figures.js` draws downloadable SVG/PNG workflow diagrams,
node-colored graphs, node/edge local response bars, temporal response plots,
edge-time heatmaps, independent per-concept beeswarms/boxplots/request-size
curves, separate node/edge dependence scatters and community plots. Each has
an easy description and a method/coverage note. Distributions summarize
tested request amounts on ONE dataset/model/seed, not users, repeated trials
or training seeds. Per-time impacts are not summed. Element occlusion is
distinct from normalized concept sensitivity. Untested nodes remain gray.
Boxplot whiskers show measured min/max, not a confidence interval.

Learned-model seed stability cannot be generated from the deterministic web
models: that panel explains its unavailability rather than fabricating seed
variation. Multi-dataset and multi-model paper aggregates likewise are not
presented as single-run results. The existing research workflows supply
those experiments separately.

Verification includes measured bridge/node/edge/time-step ground truth on
the stable fixture, extra-call bounds, invalid sweep handling, rendered live
chart families, SVG export, old-result handling and mobile overflow.
All 15 API/engine checks passed in about 27 seconds. Functional browser
checks passed for the live chart families, including a downloaded live
beeswarm SVG, legacy rerun prompts and mobile layout. The portable bundle
includes the new measurement and plotting modules.

The Paper figures menu displays 12 existing top-level charts from
`output/publication`, with original PNG/PDF files, easy descriptions, scope
notes and provenance. `scripts/publish-paper-figures.py` copies reviewed
artifacts into sibling `publication/` and creates a checksum manifest.
Superseded figures are deliberately excluded. The exploratory pooled
`fig6_impact_distribution` is included with an explicit mixed-model/unit
limitation; it is not offered as a quantitative cross-concept ranking.
Paper element-occlusion charts are labeled separately from concept impacts.
These are saved paper artifacts, never presented as a participant's run.

Authenticated endpoints `/api/publication` and
`/api/publication/{figure_id}/{png|pdf}` serve only manifest-listed artifacts.
They are outside the public static directory. `static/relationships.js`
implements the gallery and a Relationships tab in experiment results.
This tab uses actual last-snapshot nodes/edges from the selected concept and
direction, with a before/after community diagram, community count matrix,
and node-degree scatterplot. Matrix diagonal counts internal edges once;
mirrored off-diagonal entries represent the same cross-community edges.
All nodes/edges enter these calculations. Degree points may overlap.
These are graph-structure views, not inferred node/edge attribution or
correlation/causation claims. Invalid transformations remain diagnostic.
SVG/PNG downloads and easy-language descriptions work for all three plots.

To refresh paper assets, run `python scripts/publish-paper-figures.py`, then
`python scripts/bundle-sandbox.py`. The portable bundle and developer source
override now include `publication/`. Publication API verification checks
login requirements, PNG hashes, PDF signatures and rejected unknown files.
Browser verification checks the stable bridge matrix (8 original, 9 after
increase), relationship controls, gallery and mobile layout. Workbench tests
now total 14; launcher checks remain six.
All 14 API/engine tests and six launcher checks passed for this addition.
Functional browser checks also passed, including publication images,
relationship counts/selectors, SVG/PNG exports and mobile overflow. Windows
Chromium page screenshots can intermittently stall on this VPS; the operator
check supports `--no-screenshots` to run all functional assertions without
optional page captures. Existing relationship and gallery screenshots are
available in sibling `verification`.

Every result now includes an easy-language What this means block: each
increase/decrease cell in Numbers, each concept's explanation card, every
sensitivity/prediction figure, and the selected Network/History comparison.
`easyResult`, `easyConcept`, and `easyHistory` in `static/figures.js` derive
descriptions from actual run values. They describe higher/lower answers,
unchanged answers after effective changes, no-ops and excluded tests
separately. Network text reports connections added/removed; history text
reports time steps changed and whether the final value changed. They avoid
claiming larger predictions are better, or that a zero proves irrelevance.

Result output now prominently includes a TGAP explanation summary above the
figures/tabs, preserved while switching evidence views. It identifies the
actual run's model/dataset and original prediction, describes which concepts
produced a valid prediction response, and lists per-direction evidence with
original/transformed predictions, achieved deltas and normalized impacts.
Concept labels distinguish response, no response after an effective change,
no-op and no valid evidence. Invalid directions are excluded and partial
evidence is labeled. The narrative does not rank incompatible normalized
scores, claim causation, or claim an additive decomposition of the baseline.
`explanationContent` / `renderExplanation` in `static/figures.js` build this
from existing result rows; Save explanation downloads a text report with
seed and request hash. It works for saved older results as well as new runs.
Browser checks verify the stable explanation/report and the all-invalid and
all-no-op interpretation boundaries.

Start-here onboarding now uses `static/onboarding.js`: a prominent prepared
first-experiment button, illustrated question preview, four-stage overview,
and five numbered walkthrough cards with exact clicks and expected outputs.
The first button loads the stable example without automatically running it.
A Laboratory banner offers Run experiment and changes to reading guidance
after completion. Tutorial progress is in-memory and resets on sign-out;
it is independent of study consent and scoring. Further cards cover reading
Figures/Network/Numbers, changing a request to 25%, comparing history models,
and saving figures/data or trying custom code. Secondary next-step links
lead to examples, reference and optional study. Expected 8 baseline, +1/-1
prediction change and +8/-8 impact refer specifically to the seed-42 initial
stable bridge model, not arbitrary settings. Desktop and mobile screenshots
are recorded by the browser smoke check.

Readability update: base text is 18px, typical controls/navigation 16–18px,
help and captions 14–16px, and figure SVG labels are four units larger.
Muted instructional text uses darker contrast. Results use a single-column
figure gallery; the laboratory stacks controls above results below 1150px.
Mobile uses two-column summary statistics, stacked direction cards, and
larger touch controls. The updated self-host bundle includes these styles.

The first page after sign-in is now Start here: an overview, learning path,
and five-step tutorial. Navigation is ordered Start here, Example library,
Laboratory, Guided study, Documentation, Researcher; desktop entries include
descriptions and mobile uses a compact grid. Each page includes contextual
instructions; active navigation exposes `aria-current`.

Figures is the default experiment result tab. It shows raw prediction-change
bars in common model output units plus separate normalized-sensitivity panels
with independent scales per concept. Numbers retains all detailed outputs.
Network compares original and transformed last snapshots side by side using
the same positions; History overlays original and transformed sequences for
bridge width, density, centralization and edge count. Both views let users
select every tested concept and direction. Invalid rows are excluded from
quantitative charts; structural plots label invalid changes as diagnostic.
Each figure downloads as vector SVG or PNG rendered at twice its viewBox
resolution. The browser generates images without third-party services.
Exported figures include a visible title, dataset/model IDs, seed and request
hash so they remain identifiable outside the website.

`static/figures.js` implements charts, comparisons, exports and page help.
`sandbox/engine.py` now emits schema version 2 with `comparisons`: per-row
transformed history, last-snapshot edges, added/removed edges and validity.
A local explainer subclass captures the exact transformed graphs from
original prediction calls, preserving the 1+2K model-call budget without
rerunning transformations for figures. Core files remain unchanged. Version
1 saved experiments still render figures/networks; their transformed history
is unavailable until rerun. Network drawings limit nodes to 80 and edges to
1,600 per panel, with those limits disclosed. Real predictions use full data.

Verification adds a graph/history consistency test (13 workbench tests total)
and browser checks for tutorial-first login, figure downloads, comparison
selectors, legacy results and mobile overflow. Self-host bundle includes the
same updated interface. Existing personal installations receive it by
rerunning `tgap install`; stop the local service first and start it afterward.
All 13 workbench tests and six launcher checks passed for this update.
Browser verification passed for SVG and PNG file contents, every result tab,
legacy saved results, tutorial routing, custom code and 390-pixel mobile
layout. Screenshots include `tutorial-desktop.png`, `results-desktop.png`,
`network-comparison.png`, `history-comparison.png` and `laboratory-mobile.png`
in the sibling `verification` directory. The VPS service remains running.

## Locations and operation

- Research Git checkout: `C:\catalyst\tgap`.
- Independent VPS web source: `C:\catalyst\tgap-sandbox` (outside Git).
- VPS address: `http://144.172.97.105:8080`.
- Account file: `C:\catalyst\tgap-sandbox\users.txt`.
- First administrator username: `researcher`; its generated password is in
  the account file and the delivery message, deliberately omitted here.
- Add one `username:password:participant` line per invited user; use `admin`
  for researchers. Edits take effect without restarting and password changes
  invalidate existing sessions. Names and passwords cannot contain colons.
- Runtime configuration: sibling `config.json`, binding `0.0.0.0:8080`.
- Windows startup task: `TGAP-Laboratory`, running as SYSTEM at boot.
- Operator commands: `powershell -File C:\catalyst\tgap-sandbox\service.ps1
  Start`, `Stop`, or `Status`. Stop disables boot startup and writes a stop
  marker; Start clears it and enables startup again.
- Account file and data directory permissions restrict access to Windows
  Administrators and SYSTEM. Firewall permits inbound TCP 8080.

The supervisor restarts a failed API process. Task Scheduler also restarts
the supervisor. This service is configured to remain running until stopped.
The address currently uses HTTP. Configure a domain and HTTPS reverse proxy
before sending sensitive credentials across an untrusted network. External
reachability also depends on the VPS provider's firewall.

## Self-host commands

The bootstrap requires Python 3.10+; Windows offers a signed Python installer
when no Python is present. The install command is `tgap install`; during first
setup, run the checkout launcher (`.\tgap.cmd install` on Windows or
`sh ./tgap install` on Unix). It prompts for optional Torch/PyG and finance
libraries, creates an isolated environment under `~/.tgap`, installs the
research checkout and bundled web source, and prints a fresh account. Open a
new terminal after PATH registration.

Use `tgap start` to launch the workbench locally on loopback and open the
browser, `tgap stop` to stop it while keeping data and packages, and
`tgap status` to check health.
`tgap run` exposes research workflows including examples, evaluation,
real-data, learned-model experiments, publication, tests and finance.
`TGAP_HOME` or global `--home` selects a separate installation. `start --port`
chooses the port, `--no-browser` suppresses browser launch, and `--host`
allows an intentional remote binding. Personal installs do not register a
boot service. See `docs/12-installation-and-self-hosting.md` for details.

Implementation: `bootstrap.py`, root launchers, `tgap_cli/cli.py`,
`pyproject.toml`, `scripts/bootstrap-python.ps1`. The CLI imports only the
standard library before installation. Reinstall preserves optional package
flags, account files and results.

## Website structure and experiment flow

The sibling uses FastAPI with local HTML/CSS/JavaScript assets, without CDN
dependencies. Navigation includes Laboratory, Examples, Guide, Study,
Documentation and Researcher. An academic blue/slate visual style supports
desktop and mobile screens.

1. Select one of five synthetic sequences or eight prepared real-data
   sequences, a transparent model, transformation concepts, perturbation
   amount, temporal window and seed.
2. The server generates a Python program using the existing TGAP classes.
3. Run the experiment in a separate bounded worker process.
4. Inspect concept impacts, achieved changes, validity flags, original and
   transformed networks, temporal metrics, model-call counts and sparsity.
5. Export JSON, CSV or executable Python; revisit account-owned history.

`sandbox/engine.py` connects the web selections to `core.TgapExplainer` and
existing real-data validity gates. Invalid perturbations have blank impacts;
the interface does not imply valid explanations when a gate fails. Six
worked examples include history, communities, custom code and validity.
The generated program editor is for local export; changes to it do not
execute online. Online custom transformer code uses its separate editor.

`sandbox/restricted.py` interprets a constrained graph-only Python AST.
Participant code is never passed to Python exec/eval. It rejects filesystem,
network, process and reflection operations; graph operations, simple loops
and arithmetic are bounded. This supports educational transformer classes,
not arbitrary Python or a hardened container service. Worker time and
memory are monitored; Unix additionally applies resource limits. The private
invited-user service is the intended deployment boundary.

`sandbox/app.py` implements authentication, CSRF checks, input limits,
account-owned jobs, consent/study APIs and administrator exports. Cookies
are HttpOnly/SameSite; session tokens are hashed in SQLite. Passwords are
intentionally stored in the operator's protected plaintext account file,
as requested. No credentials are exposed as static assets or in exports.
`sandbox/worker.py` runs experiments and `sandbox/serve.py` supervises the
API. `static/app.js`, `index.html`, and `style.css` contain the interface.

## Data and packaging

SQLite and generated results live under sibling `data`; logs include
`server.log` and `server.previous.log`. Back up account/config files and
the data directory. Do not publish those files.

Eight small prepared real-data fixtures are generated by
`scripts/prepare_datasets.py` from original adapters. Runtime uses local
fixtures and requires no download. They are demonstration windows, not
complete raw datasets or substitutes for the original research evaluation.

The self-host distribution contains `tgap_cli/data/sandbox.zip` plus its
SHA256. Refresh it after editing sibling source with
`python scripts/bundle-sandbox.py`. The bundle includes application code,
assets, fixtures and requirements; it excludes live accounts, configuration,
sessions, study records, logs and the Python environment. The sibling source
is authoritative; Git stores a distribution snapshot. Python/package edits
in the research checkout stay editable in personal installations.

## Guided user study

This is a 10–15 minute single-condition pilot, distinct from the original
longer research protocol. `C:\catalyst\tgap-sandbox\STUDY_PROTOCOL.md`
specifies consent, timing, task instructions, scoring and analysis limits.
Participants complete bridge, temporal-history and validity tasks, then
run a custom transformer and provide reflection/confidence ratings.
Each task requires an experiment run after its stage started. Reflection
requires a fresh custom-code run. No participant results were invented.

Records use pseudonymous IDs. Researcher exports include sessions,
responses and study experiment metadata, not credentials or usernames.
Consent is required; participants can withdraw and delete their records.
The admin view offers CSV exports with spreadsheet formula escaping.
Use the pilot to assess usability and concept understanding; causal claims
about superiority require a separate controlled study and appropriate
institutional review.

## Verification and remaining limits

Delivery checks passed: original research suite 533 tests (531 passed,
two skipped), six new bootstrap/distribution tests, and 12 workbench API/
engine tests. Playwright checks passed against both the deployed VPS service
and a fresh base-dependency installation. Fresh installation, start, status
and stop were exercised; a distributable wheel was built and inspected.
Killing the VPS API process demonstrated automatic supervisor recovery.
Port 8080 responds through the server's public interface from the VPS;
independent external reachability was not established by the available web
tool. No VPS reboot was performed.

Workbench verification: `tests/test_workbench.py` covers engine truth,
custom-code constraints, real-data validity, login/session changes,
ownership, CSRF, consent, complete study flow, exports and withdrawal.
`tests/browser_check.py` exercises login, results, custom code, examples,
tutorial/docs and mobile layout with Playwright. Screenshots are in sibling
`verification`. These are developer checks, not participant study findings.

Windows is the verified host. Linux/macOS launchers are implemented but
need platform-specific smoke testing. Optional TGN/finance installs are
available; a fresh installation smoke uses only base dependencies. A
missing-Python Windows installation requires a separate clean-machine
check. Provider-side public access and a real reboot cannot be established
solely by local health checks. The startup task configuration and worker
recovery can be verified without rebooting the VPS.

## Git publication handoff - 2026-10-08

The full website source and tests are now preserved in `workbench/` inside the
research repository, alongside the portable ZIP. The running deployment remains
in the sibling `C:\catalyst\tgap-sandbox`; credentials, config, runtime data,
logs and environments are excluded from Git. `scripts/bundle-sandbox.py` now
prefers repository `workbench/` and accepts `--source` for the sibling. Source
tests detect the repository layout as well as the original sibling layout.
See `workbench/DEVELOPMENT.md`. Keep the source mirror and deployed application
in sync deliberately when making future changes.
