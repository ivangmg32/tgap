# Scientific, end-to-end and reliability audit - 2026-10-08

## Conclusion and scope

The tested website outputs agree with independent mathematical calculations for
all **270 audited configurations**: **142,651 numerical comparisons,
zero mismatches**. An additional 78-case audit verified **2,178
valid request-size sweep samples** with independent predictions, achieved-change
calculations and normalization. These results support numerical faithfulness of
the six transparent web models on the included fixtures and tested settings.

This is not scientific peer-review approval, proof of real-world causality,
validation of predictive accuracy, or validation of a trained TGN. A forecast
here is a linear extrapolation and can exceed a metric's natural range; it is
not automatically a calibrated or constrained forecasting model. Real fixture
partitions, projections and node selection define the meaning of the results.
No observed real-world causal ground truth or participant-study results were
invented. These checks do not establish research ethics approval.

The research `core/` was unchanged. Website source remains outside the research
checkout at `C:\catalyst\tgap-sandbox`; its updated portable ZIP is bundled
with the self-host launcher. This report and evidence persist in the research
checkout for future conversations.

## Scientific coverage

The primary matrix is 13 datasets (five synthetic, eight prepared real fixtures)
x six web models x three request sizes (0.02, 0.10, 0.50), seed 42: 234 runs.
Another 36 runs test three synthetic datasets x six models x seeds 0 and 17
at request size 0.25. Every run tests all five built-in concepts in both
directions, giving 2,700 primary perturbation rows. Of those,
252 were appropriately excluded by validity gates
and 259 valid rows were no-ops.

Independent checks use direct edge counting for bridge width, 2E/[N(N-1)] for
density, the Freeman degree-centralization formula, explicit neighbor-pair
triangle counting for average clustering, and closed-form ordinary least
squares for slope and one-step forecasts. The oracle does not call TGAP's
metric/model prediction methods to obtain the expected answers.

Checks cover original and transformed predictions, raw differences, measured
property changes, normalized impacts, node-set/no-self-loop invariants, promised
edge-count preservation, present anchors for history-only concepts, bridge
preservation, and every saved history metric. Node occlusion, edge occlusion,
one-snapshot hybrid responses and edge-time responses are independently
recomputed from the actual graphs captured by the engine. Primary model calls
are checked separately from figure calls. Invalid quantities must be null;
JSON must contain no NaN or infinity. Numerical comparison tolerances are
relative 2e-9 and absolute 2e-10.

The supplementary sweep audit regenerates each tested perturbation and uses the
independent oracle for every completed valid sample: 2,178 samples x three
numerical comparisons. It checks all 13 datasets and six models at selected
delta 0.10, with the actual half/current/double request amounts.

No additional-figure budget was exhausted in the primary matrix. The slowest
in-process engine run took 11.906 seconds on
this VPS during concurrent verification. This is a measured maximum, not a
performance guarantee. Detailed-figure outputs retain explicit coverage and
unavailable reasons when a future run reaches its time/call budget.

Distributions summarize tested deltas, not independent subjects, repeated
training trials or confidence intervals. One-snapshot hybrid charts report raw
model responses, not an additive decomposition or independent validation of a
full temporal concept's direction. Node/edge panels use bounded selected
subsets; unmeasured elements must not be read as zero. Main normalization is a
finite perturbation sensitivity and does not generally equal a derivative.

## Defects found and corrected

1. **Zero-baseline units:** TGAP correctly falls back to absolute property units
   when relative change from zero is undefined, but the website could label the
   value as a percentage. Primary and sweep rows now report the effective
   `delta_mode`; primary rows additionally retain `requested_delta_mode` and
   `property_baseline`. A regular-cycle zero-centralization fixture verifies the
   correction and deterministic repeated outputs. Rerun older saved results to
   acquire the new unit metadata.
2. **SQLite resource cleanup:** a SQLite connection's transaction context does
   not itself close the connection. The shared database context now explicitly
   closes connections on success and failure. Windows temporary database
   cleanup exposed this issue during security testing.
3. **Polling and queue wait:** the former 55-second browser polling limit could
   expire before a full ten-job/two-worker queue completed. Polling now backs off
   from 0.75 to 2.5 seconds, allows four minutes, and retries temporary 429/503
   read responses using bounded Retry-After delays. Browser E2E injects a 429
   during a real job and verifies recovery without duplicate submission.

## Authentication and abuse controls

The welcome screen now has Sign in and Create account. Registration accepts
ASCII usernames (3-32 characters, starts with a letter; stored lowercase) and
passwords of 15-128 characters. It creates participant accounts only. New
passwords use random salts and PBKDF2-HMAC-SHA256 with 600,000 iterations.
Existing protected `users.txt` researcher/operator accounts remain supported.
Registered accounts reside in the protected SQLite database. No email is
collected and no self-service password-reset flow is currently implemented.

Both sign-in and registration require a six-character image CAPTCHA, expiring
in five minutes and consumed on the first submission. It is bound to purpose,
cookie and actual peer IP. Only an HMAC answer digest is stored. The production
application has no deterministic CAPTCHA bypass. Test-only generation is mocked
inside trusted tests and a disposable loopback-only browser fixture.

Persistent fixed-window limits cover authentication, CAPTCHA issuance and
experiment submissions. Password derivation has four concurrent slots. General
requests, active connections, body bytes/read duration, worker runtime/memory,
queue size and experiment-storage admission are bounded. Detailed values and
operator controls are in the sibling README. `registration_enabled: false`
closes new registration; `registration_attempts_per_ip_hour` defaults to 20
and can be set from 1 to 100 for shared participant networks.

CAPTCHA is a friction layer and may be solved by OCR; the visual-only challenge
also has an accessibility limitation. It does not prevent network-level DDoS.
The public URL is currently **HTTP**, so passwords lack transport encryption.
HTTPS termination and upstream network protection remain required for internet
study credentials. A future reverse proxy currently shares its peer-IP limits;
untrusted forwarded-IP headers are deliberately ignored. Existing file-managed
passwords remain plaintext by the user's earlier explicit requirement and need
OS protection. These are remaining deployment limits, not solved claims.

Implementation choices follow the OWASP
[authentication guidance](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html),
[password storage guidance](https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html)
and [DoS guidance](https://cheatsheetseries.owasp.org/cheatsheets/Denial_of_Service_Cheat_Sheet.html).
This is not a penetration-test or compliance certification.

## Automated test results

- Research/CLI discovery: **539 tests, 521 passed, 18 skipped, no failures**.
  Six are launcher tests. Sixteen skips require optional PyTorch/PyTorch
  Geometric unavailable in this web environment; the other two are intentional
  fixture/base-class skips. No trained-model coverage is claimed here.
- Website regression suite: **38 tests passed** (15 workbench, 17 security,
  six worker/reproducibility tests). Coverage includes CAPTCHA absence/wrong/
  expired/reused/purpose/cookie-IP binding, PNG/no-answer-leak, salted hashing,
  role restrictions, case-insensitive duplicates, concurrent duplicate creation,
  registration limits, disabled-account session revocation, generic sign-in
  errors, persistent throttle restart, request bounds, cross-origin/CSRF,
  result ownership, research export access, consent/withdrawal and custom-code
  restrictions. Worker deadline/memory/output failure paths are fault-injected.
- Chromium browser E2E passed with no JavaScript errors: account creation,
  wrong CAPTCHA and retry, sign-out/sign-in, tutorial-first experience, actual
  known-truth results and explanation, text/SVG/PNG export behavior,
  custom transformation, several models/datasets/deltas/seeds, graph/history/
  relationship/detailed figures, older-result handling, publication gallery,
  study entry, documentation and desktop/mobile overflow checks. A temporary
  polling 429 is explicitly injected and recovered.

## Reliability and recovery results

Tests run only against disposable loopback instances, never as a load attack on
the public endpoint. The actual production supervisor and worker launcher are
used for recovery tests. **24 recovery/load checks passed**:
normal and repeated jobs; one-active-account/global-queue rejection; forced
worker failure with explicit failed status and successful next job; forced API
process kill with automatic supervisor restart; persisted login/session/result;
interrupted jobs explicitly failed after restart; new job success; malformed/
oversized input; scratch-file cleanup and SQLite integrity check.

Supervisor restart plus health recovery took **5.219
seconds** in the measured run. API process-tree RSS afterward was
67.82 MiB (point measurement, not a worst-case bound).
A bounded burst of 200 health requests with ten concurrent clients returned
55 HTTP 200 and 145 intentional HTTP 429 responses, with no connection failures
or unexpected statuses. All-response latency was p50 15.0 ms,
p95 31.0 ms and p99 31.0 ms. These figures
include rejected requests and must not be described as successful-experiment
throughput. Health recovered after the burst.

An initial 0.25-second-polling endurance test exhausted
the shared 600-request/minute peer limit after 42 successful experiments; 36
subsequent operations were rejected rather than crashing the service. Its raw
evidence is preserved. This prompted normal-paced endurance verification and
the browser backoff/retry fix above. Final endurance results are recorded below.

These are bounded functional/load/recovery checks, not an exhaustive guarantee,
24-hour soak, distributed network attack, disk-failure simulation or formal
penetration test. Worker memory is a monitored ceiling rather than an OS-enforced
hard quota; storage thresholds admit/refuse new jobs rather than enforce a hard
filesystem quota. Backups and a research-data retention policy remain operational
responsibilities.

## Evidence and rerunning

Evidence: `docs/verification/2026-10-08/` in this research checkout; original
logs and full scripts: `C:\catalyst\tgap-sandbox\verification` and `tests`.
All test accounts and deterministic challenges are disposable; they are not
production credentials and are excluded from the portable bundle.

From the sibling app directory:

```powershell
.venv\Scripts\python.exe -m unittest discover -s tests -p test_*.py -v
.venv\Scripts\python.exe tests\scientific_audit.py
.venv\Scripts\python.exe tests\sweep_audit.py
.venv\Scripts\python.exe tests\reliability_audit.py
```

For browser/API endurance tests, start `tests/serve_test_instance.py` on its
hardcoded loopback port 8093. It writes `verification/browser-test-home.txt`.
Pass that fixture's `users.txt` with `--account-file`, and `--captcha-answer
ABC234 --no-screenshots` to `tests/browser_check.py --url http://127.0.0.1:8093`.
Run `tests/api_soak_audit.py` against that same disposable fixture. Never expose
this deterministic fixture server publicly. The primary matrix can take about
ten minutes; measurements vary with machine load.

Live service: `http://144.172.97.105:8080`. Boot task `TGAP-Laboratory` remains
enabled/running. An actual live image CAPTCHA was visually solved, the existing
operator account signed in successfully, the protected catalogue returned all
13 datasets/six models, and sign-out revoked access. Protected pre-deployment
DB/previous-bundle backups remain under sibling `data/backups/`.

## Final paced API endurance result

All **78 of 78 real API experiments completed successfully**, with zero failures:
all 13 datasets x all six web models, delta 0.25, seed 17, Bridge Width and
Bridge Trend in both directions. Three separate participant accounts submitted
concurrently through the actual queue/subprocess workers. Every result retained
its submitted configuration, finite JSON and the five-call primary budget;
other accounts received 404 when requesting another user's result. Accounts and
results exist only in a disposable loopback fixture.

Elapsed: 130.204 seconds. Per-experiment end-to-end latency
(including queueing and one-second polling): p50 4.1175 s,
p95 10.140 s, maximum 11.281 s. This
is a bounded endurance sample, not a production SLA or day-long soak.

The refreshed portable bundle contains 53 files and passed all six launcher
checks, including authentication assets, explicit Pillow dependency, checksum
validation, eight fixtures, twelve publication PNGs and exclusion of live
accounts/configuration/study records.
