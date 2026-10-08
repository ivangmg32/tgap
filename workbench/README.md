# TGAP Laboratory

A private web workbench for TGAP experiments and a 10–15 minute guided pilot.
Application source and VPS state live outside the TGAP research Git checkout.

## VPS deployment

- Application: `C:\catalyst\tgap-sandbox`
- Research source: `C:\catalyst\tgap`
- Address: `http://144.172.97.105:8080`
- Runtime: `.venv\Scripts\python.exe`
- Startup task: **TGAP-Laboratory**, runs at Windows startup as SYSTEM.
- Server configuration: `config.json`; default binding `0.0.0.0:8080`.
- Credentials: `users.txt`; secret/session/study files: `data/`.

```powershell
cd C:\catalyst\tgap-sandbox
.\service.ps1 -Action Status
.\service.ps1 -Action Stop     # also disables automatic startup
.\service.ps1 -Action Start    # re-enables automatic startup
.\service.ps1 -Action Install  # register task and TCP 8080 firewall rule
```

The supervisor restarts the server if it exits unexpectedly. Log files rotate
at five MiB. Do not run multiple API workers: the queue and startup recovery
are deliberately owned by one process. Stop the service before editing backend
files; frontend assets are served directly and do not require a build step.

## Self-service accounts (2026-10-08)

The welcome screen now offers **Sign in** and **Create account**. Registration
creates participant accounts only and automatically opens the tutorial. New
passwords (15-128 characters) use independently salted PBKDF2-HMAC-SHA256 hashes
with 600,000 iterations, stored in `data/laboratory.sqlite3`, never `users.txt`.
No email is collected. There is currently no self-service password recovery.

Both actions require a local six-character image CAPTCHA: five-minute expiry,
one use, session-cookie/IP/purpose binding, HMAC-only answer storage, no answer
returned to the browser. Wrong answers invalidate the image. CAPTCHA has no
external provider dependency; it is a deterrent, and may be solved by OCR.

Set `registration_enabled: false` in `config.json` and restart to close new
registrations. `registration_attempts_per_ip_hour` defaults to 20 and is bounded
between 1 and 100, to support participants sharing a campus/NAT connection.
Persistent limits also cover 100 registration attempts/day globally, 20 sign-in
attempts/15 minutes per IP/account, 120 sign-in attempts/minute globally, and
30 CAPTCHA requests/minute per IP (300/minute globally). These fixed-window
limits survive API restarts. CAPTCHA failure counts as an attempt.

General requests are limited to 60/second and 600/minute per peer, 200/second
globally, and 64 concurrent requests. The supervisor limits connections and
keep-alive time and ignores untrusted forwarded-IP headers. Bodies are bounded
to 64 KiB and ten seconds. Password derivation has four concurrent slots.
Experiments have two workers, a ten-job queue, one active job per account, and
30 submissions/hour/account. New jobs are refused at 5,000 saved jobs, over
512 MiB database-plus-WAL size, or under 256 MiB free disk. These are admission
thresholds, not hard filesystem quotas. Back up/archive records before reaching
them; do not delete participant research records without your retention policy.

The account database can be inspected with SQLite. Operators can set
`registered_accounts.disabled=1` for a specific username to revoke that account
and its existing sessions. File-managed accounts below remain supported and take
precedence over a matching registered name. Keep administrator accounts in the
protected file; browser registration cannot grant that role.

Application limits do not stop network-volume DDoS attacks. Use an upstream
firewall/provider protection and HTTPS termination for an internet deployment.
The current public address is HTTP: credentials are not encrypted in transit.
When adding a reverse proxy, all clients currently share its peer-IP limits;
do not enable arbitrary forwarded-header trust. Set secure cookies with HTTPS.

## Operator-managed accounts

Edit `users.txt` manually. One account per line:

```text
# username:password:role
researcher:YOUR_PRIVATE_PASSWORD:admin
participant01:ANOTHER_PRIVATE_PASSWORD:participant
```

Use `admin` for researcher exports; use `participant` for study access. Do not
use a colon or whitespace surrounding username/password values. Comments and
empty lines are ignored. The account file is re-read on every authenticated
request, so new accounts are immediate. A password change or account removal
invalidates existing sessions. Each participant should have a separate account.
The operator's first account is generated at setup; its password is stored only
in the private account file and the private handoff, never in this document.

This requested editable plaintext account file must remain protected by OS
permissions. The deployed file/data directory are restricted to Administrator
and SYSTEM. Cookies are HttpOnly and SameSite Strict, sessions expire after
12 hours, API writes require a CSRF token, and login attempts are rate-limited.
TLS is not terminated by this initial IP-and-port service. Use a trusted HTTPS
reverse proxy before sending participant credentials across the public internet;
set `secure_cookies` to true in that deployment. Do not expose user/data files
through a proxy: forward only the application port.

## Experience

1. **Laboratory:** choose a dataset, model, concepts, request size and seed.
2. **Examples:** six complete scenarios, including real-data validity and a
   custom transformer.
3. **Getting started:** a five-step introduction designed for approximately
   13 minutes, with concrete example launch buttons.
4. **Guided study:** explicit consent, three tasks, a custom experiment,
   confidence, task timing, reflection and withdrawal.
5. **Documentation:** measurement semantics, custom language, data preprocessing,
   local installation and privacy.
6. **Researcher:** participation overview and CSV exports for sessions, task
   responses and study-linked experiment choices.

Results include measured concept impacts with validity status, a last-snapshot
network, original metric trajectories, generated editable Python, CSV and JSON.
Generated script edits are for local execution; browser runs use the selection
form and bounded custom-transformer editor. No result ranking mixes incompatible
delta units. All calculations use the existing research library.

## Custom transformers and limits

The editor accepts one Python-syntax class extending TemporalGraphTransformation.
Its AST is interpreted by `sandbox/restricted.py`: participant code is never
passed to Python `exec` or `eval`. Only documented graph and collection
operations are exposed. Arbitrary imports, private attributes, files, shell,
network access, decorators, while loops and lambda expressions are unavailable.

Each experiment is a separate worker process, with a 40-second timeout, a
monitored 768 MiB RSS ceiling, 120,000 interpreted custom operations, and
bounded collections/source. Linux workers also set CPU/address-space limits.
The application admits one active job per account, at most ten pending/running
jobs globally, and uses two worker threads. This is a **private invited-user
educational environment**, not a hardened arbitrary-Python public execution
service. It is not container isolation. Investigate a separate OS/container
execution boundary before extending it to untrusted public users.

Custom transformations must preserve snapshot count/node sets, not mutate
inputs, and return finite property measurements. Feasibility gates blank invalid
impacts. The concept explainer still uses its original achieved-change math.

## Data and reproducibility

Five synthetic datasets are generated from seeds. Eight processed real-data
fixtures preserve `temporal_evaluation` adapter output and original metadata,
including retention and the frozen partition. Raw inputs remain in the research
checkout's ignored `realdata/data/`. Participant requests never fetch raw data.

Refresh fixtures only as an operator:

```powershell
python scripts/prepare_datasets.py --tgap-source C:/catalyst/tgap
```

Fixtures are in `fixtures/`, copied to `data/datasets/`. After updating the
application or fixtures, refresh the portable distribution from the research
checkout:

```powershell
python scripts/bundle-sandbox.py --source C:/catalyst/tgap-sandbox
```

This produces a deterministic compressed snapshot in
`tgap_cli/data/sandbox.zip`, with a SHA-256 sidecar. It excludes users, config,
session keys, logs, verification images, study database and virtual environments.
The sibling application remains the web source of truth; the archive is a
portable release artifact, not a second editable source tree.

## Study records

`data/laboratory.sqlite3` stores hashed session tokens, private experiments,
pseudonymous study sessions, answers and reflections. The account-derived
owner key is an HMAC; exports never include usernames or passwords. Experiment
results can contain custom source and public dataset identifiers. Account owners
see only their own results. Admin exports include only study-linked experiment
logs. Free text is escaped against spreadsheet formula execution.

Study stages: bridge → history → validity → reflection → complete. Task clocks
start on stage entry and stop on submission. Each task requires a completed
experiment during that stage, and reflection requires a custom-transformer run.
Study start/resume preserves the active stage. Withdrawal deletes the account's
study responses, sessions and saved experiment records. Backups must follow the
operator's stated retention/withdrawal policy too.

The short pilot is explicitly distinct from `docs/09-user-study-design.md`'s
45-minute three-condition research protocol. Read `STUDY_PROTOCOL.md` before
recruitment. No participant outcomes or claims are fabricated.

## Verification and development

```powershell
.venv/Scripts/python.exe -m pip install -r requirements.txt
.venv/Scripts/python.exe -m pip install httpx playwright
.venv/Scripts/python.exe -m playwright install chromium
.venv/Scripts/python.exe -m unittest discover -s tests -v
# Start a temporary preview, then test the browser:
.venv/Scripts/python.exe -m uvicorn sandbox.app:app --host 127.0.0.1 --port 8091
.venv/Scripts/python.exe tests/browser_check.py --url http://127.0.0.1:8091
```

Tests use a separate temporary database and test-only accounts. Browser checks
read the private operator account without printing it, and write screenshots
under `verification/`. Treat those screenshots as operator artifacts rather
than participant data. `requirements-lock.txt` records the deployed environment.
# Visual results and navigation

Every new user experiment now computes bounded live publication-style
explanation measurements. Open Paper-style figures in its results for local
node/edge explanations, temporal responses, edge-time heatmaps, sensitivity
sweeps, per-concept beeswarms/boxplots, dependence and community plots.
These use the user's actual input, not the saved paper images. Additional
calls, partial coverage and excluded tests are reported; measured data is
saved in Full JSON. Training-seed figures require a trained multi-seed
experiment and are explicitly unavailable for the web's transparent models.

Paper figures displays the 12 reviewed top-level PNG/PDF publication
artifacts through authenticated endpoints. Superseded charts are excluded.
Relationships in each experiment displays community ties, a connection
matrix and node-degree changes for the selected concept/direction. These
views describe structure; they do not claim node/edge importance. Refresh
the gallery with the research checkout's `scripts/publish-paper-figures.py`,
then rebuild its portable bundle with `scripts/bundle-sandbox.py`.

Sign-in opens the overview and tutorial. Each menu includes instructions.
Experiments open Figures first: prediction changes and concept sensitivity
plots, with SVG/PNG downloads. Network and History allow selecting each
concept/direction for original-versus-transformed comparisons. Numbers keeps
the full numerical explanation. Existing saved runs remain readable; rerun
older experiments to obtain transformed temporal histories.

## Research dashboard (2026-10-08)

Sign in with an operator-managed `admin` account and open **Researcher**.
Participants cannot access this page or its APIs. The dashboard shows only
explicitly consented study sessions and experiments linked to those sessions;
personal exploration is excluded. Counts distinguish unique pseudonymous
participants from repeat sessions and experiment attempts.

Filter study starts by inclusive UTC dates and all/completed/in-progress visits.
The 12 charts cover completion, task accuracy, confidence, task time, three
ordinal experience ratings, dataset/model usage, job states, validity exclusions
and study starts. Charts export as SVG or PNG. Detail tabs provide searchable,
paged session/feedback, response, experiment and concept-result records. Inspect
an experiment for its saved configuration, raw response chart and full JSON.

**Download research data ZIP** exports the selected cohort as four CSV tables,
full report JSON, metadata (source/core/fixture hashes, package versions, task
answer key and data dictionary) and interpretation notes. JSON and analysis-note
exports are also available. Dates filter session starts, not job timestamps;
linked jobs remain included. Maximum cohort: 2,000 sessions; truncation is
explicit and requires narrower dates. Missing and invalid values stay null;
accuracy excludes unanswered tasks; final ratings/durations use completed visits.
Repeated visits are not independent participants. No significance tests,
causal effects, pooled incompatible impacts or invented user results are shown.

Consent notice `pilot-1.1` explains result/code inspection and repeat-visit
pseudonyms. Older records retain their original version. Review free text and
custom code before publication. Withdrawal removes records from future reports;
already-downloaded copies must be handled separately under the retention policy.
See research repo `docs/15-research-dashboard.md` for the complete handoff.
