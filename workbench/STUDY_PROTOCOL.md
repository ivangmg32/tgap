# TGAP 10–15 minute guided pilot

Version 1.0 · prepared 2026-10-07 · design and executable pilot, no participant
results claimed. This short protocol supplements the longer study design in
the TGAP repository; it does not silently replace it.

## Purpose

Evaluate whether an invited participant can configure a graph explanation,
interpret achieved change and model dependence, recognize invalid evidence,
and run a small custom transformation without setting up Python.

This first implementation has one condition: `concept-guided-pilot`. Its
three tasks and ratings support usability feedback and feasibility testing.
They cannot establish superiority over element-level explanations or a control
condition. Add randomized conditions and a separately approved analysis plan
before testing that comparative claim.

## Session script

| Time | Activity | What is observed |
|---|---|---|
| 0–2 min | Introduction, account sign-in, consent | Consent version and server start timestamp |
| 2–5 min | Stable ecosystem; bridge-width explanation | Experiment selection, reading baseline and achieved delta; direction answer/confidence |
| 5–8 min | Bridge decay; compare present-only and forecast models | History dependence answer/confidence, task elapsed time |
| 8–10 min | Decentraland validity example | Recognition that infeasible rows must be excluded, answer/confidence |
| 10–13 min | Load custom starter; change concept name or selected edge, run | Custom experiment configuration and success/error record |
| 13–15 min | Ease, understanding, trust, optional feedback | Three 1–7 ratings, free text, end timestamp |

Ask participants to explain what they expected before running. Do not coach
their scored answers. Explain controls but avoid telling them which answer is
correct. Give the same introduction to every participant. Answers are not
scored visibly during the journey. Tell participants that exported script edits
run locally, while online custom code belongs in the transformer editor.

## Recorded tasks and objective scoring

1. A present-only bridge model sees one additional crossing edge in the last
   snapshot: its prediction increases. This is a known-definition task, not
   an empirical causal claim.
2. Bridge Trend changes only earlier snapshots: a present-only model stays the
   same. This checks an expected anchor invariant.
3. An edge-count-infeasible row cannot support a conclusion about the declared
   concept: exclude it, rather than include it or replace it with zero.

Each answer has confidence on a 1–7 scale and server-measured elapsed time.
The task clock includes exploration, reading, pauses and time in other tabs;
do not label it active interaction time. The pilot requires one completed
experiment after each task starts and a successful custom run before completion.

## Reflection

Ease, understanding and trust are single exploratory 1–7 items, not validated
multi-item scales. Optional feedback asks what was useful or confusing. Do not
claim NASA-TLX or a validated trust instrument from these responses. The longer
protocol names instruments that are not implemented in this short pilot.

## Analysis for a small pilot

Report recruitment, completed/withdrawn counts, task accuracy counts, median
and range of task/session durations, distributions of ratings, execution errors,
and coded qualitative themes. Do not manufacture participant observations or
perform significance tests merely because the interface can export a CSV.
Within-person confidence calibration needs more than three tasks for a robust
estimate; treat it as exploratory at this scale.

## Privacy and recruitment

Before recruitment, obtain applicable institutional approval and supply the
contact person, study purpose, data retention period, and withdrawal procedure.
Assign separate participant accounts. Use HTTPS for remote participant login.
Do not include personal details in account names or feedback. The text account
file is operator-controlled and separate from research exports.

Exports use random participant IDs and include consent version and condition.
The operator still controls credentials and can associate an account with a
person, so this is pseudonymity, not a guarantee of irreversible anonymity.
Do not retain external account-to-person mappings unless justified by the
approved protocol. Keep backups private and apply the same retention policy.

Participants may explore without joining the recorded study and may withdraw
through the study page. Withdrawal deletes their study/session/experiment rows
from the live database; it does not remove their login account or independently
held backups. Operators must manage those under the communicated policy.

## Researcher checklist

- Test every example and the custom starter before the session.
- Verify the connection, account and browser zoom; prefer desktop for the editor.
- Invite participants individually; avoid shared accounts.
- Explain the 10–15 minute target, and allow slower participants to finish.
- Export sessions, task responses and experiment logs after the approved pilot.
- Keep outputs separate from synthetic correctness and learned-model benchmarks.

## Research dashboard and consent clarification (pilot-1.1)

New consent notices explicitly describe researcher inspection/export of
study-linked experiment results and custom transformer code, and pseudonymous
linking of repeat visits. Historical records retain their recorded consent
version. The dashboard does not expose personal, non-study experiments.

Analysis is descriptive: submitted-answer accuracy with displayed denominators;
median confidence/time with sample sizes; ordinal 1-7 rating distributions;
completed-visit duration; selection/job/validity counts. Visits and experiments
are not independent subjects. Date filters define cohorts by UTC study start.
Exports retain raw records, missing values, validity flags, provenance and code.
Review free text/code for identifying information before publication. A withdrawal
removes future API/export records, but does not erase previously downloaded files.
