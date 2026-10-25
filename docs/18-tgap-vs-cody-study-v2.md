# TGAP vs CoDy — rigorous comparison study (v2, 2026-10-25)

## Audit of the reported demonstration values (verified against record `cmp-2fd0359ddb42`)
All values in the brief were confirmed from the stored record. Unrounded:
original score 0.540403 (logit 0.161963), the same through 4 independent
paths (difference 0.0), same history fingerprint `2c3bc4ac…`, same weights
fingerprint `d68eb3e7…`, checkpoint file hash matches. TGAP: requested −20%,
achieved −11.80%, score 0.540403 → 0.532373 (−0.80 points); opposite direction
→ 0.541741 (+0.13 points — the old "+0.1" label next to 54.0 → 54.2 came from
one-decimal rounding; scores now use two decimals and differences are computed
from raw values). CoDy: `no_class_change`, 2 distinct events (ids 58872,
58873, 160 s apart), score → 0.529474 (−1.09 points), step budget exhausted.
Re-running the same case in a separate worker process reproduced every value
bit for bit.
Corrections: the output is sigmoid(logit) and not calibrated, so it is called
"model score" with the 50% threshold shown. The earlier sentence "the data only
allowed that much" was unverified; the shortfall is now measured per period
(`churnFeasibility`): in 5 of 16 periods fewer swaps were possible than
requested (the latest period has ~190 connections to copy), and Churn is a ratio,
so it does not move by exactly the requested share.

## Technical set (preregistered rule, every attempt kept)
First 30 eligible test targets (`python -m compare_explainers batch`), batch
`b-43f780813076`: baseline verified 30/30; TGAP valid 30/30 (achieved churn
change −10.5% to −13.5%, median −12.1%; class changed 0/30); CoDy valid
counterfactual 0/30, no class change 26/30, no counterfactual 4/30, timeout 0,
failure 0. Median runtime TGAP 538 s, CoDy 391 s. These rates describe this
model and configuration only (eligibility = correctly predicted positives).

## Case bank (human study)
`uci-58894` (demonstration, CoDy no class change) and `uci-53069` (first CoDy
no-counterfactual case). No valid-counterfactual case exists in the technical
set, so that category is reported absent and nothing was invented. The bank is
stratified and must not be used to estimate CoDy's success rate.

## Study design
Within-participant, counterbalanced (group from SHA-256 parity of the
participant code), seeded case order. Per case: the case → first method →
second method → side by side + preference. After each method: three questions
(what was investigated; score and class change; conclusion — keys derived from
the record, never sent to the browser) and four 0–7 ratings. The side-by-side
view only follows both separate reviews. The observed outcome is withheld from
all pages until every required answer is stored (guards against
outcome-revelation effects). Both methods use one layout: summary, what was
changed/investigated, the same score chart with threshold, what this means,
what it does not mean, technical details. Researcher summary
(`/api/admin/compare/summary`) keeps objective correctness, subjective ratings
(with paired TGAP−CoDy differences), preferences and technical outcomes
separate; descriptive only.

Research basis: Rong et al. 2024 (TPAMI) and Kim, Maathuis & Sent 2024
(Front. AI) motivate separating objective task performance from subjective
ratings; Amara et al. 2022 (GraphFramEx) motivates keeping technical validity
apart from user evaluation; Qu, Gomm & Färber 2025 (ICML) define CoDy. None of
them validates these custom questions.

## Tests (run 2026-10-25)
Research `tests/test_compare_explainers.py` 29 passed; workbench
`test_compare_model.py` 14, `test_compare_study.py` 3 (full flow through the
real endpoint functions, incl. outcome withheld until the last answer, pairing,
exports, withdrawal), `test_easy.py` 6 — all passed.

## Limitations
No case in this configuration produced a CoDy counterfactual, so the bank lacks
that category. Two cases is small; results are exploratory. TGAP never flipped
the class with a −20% churn request. Pre/post Google Form links are still mocks
(`workbench/static/study-links.js`).

## Study v3 (consent version `compare-pilot-3`)

- **One case, six stages:** Introduction, The case, TGAP explains, CoDy explains (order counterbalanced), Side by side, Finish. Only Case 1 (`uci-58894`, student 492 → 463, 27 September 2004 23:14 UTC) is shown (`compare.STUDY_CASES = 1`); the rest of the case bank is kept.
- **Ratings only:** four 0–7 agreement items after each method (parallel wording, shared ids `changed`, `response`, `easy`, `scope`), two after the side-by-side view (`side_helped`, `side_describe`). There are no multiple-choice or preference questions.
- **Finish:** one optional free-text field. The real outcome is revealed only after it is submitted (or skipped).
- **Explanations:** TGAP and CoDy each open with "The Result in Three Steps" cards built from the record (`compare.tgap_plain`, `compare.cody_plain`). Formulas, hashes and search metadata are in collapsed sections.
- **Exports:** `compare_responses` has one `rating_<id>` column per item and a `feedback` column. The researcher summary covers only `compare-pilot-3` sessions; earlier pilot sessions stay in the database under their own bank id.

## Study v4 (consent version `compare-pilot-4`)

- **Before We Begin** (pre-study questionnaire, version `pre-1`) is shown before the six stages and is not counted as one of them. It has the consent checkbox, two optional single-choice questions (age group, highest education) and seven 0–7 familiarity ratings (0 = Not at all familiar, 7 = Extremely familiar). There is no gender, name or e-mail question. It is stored once per session in `cmp_pre`; editing it before the first rating updates that row.
- The ten post-study ratings stay where they were: 4 after TGAP, 4 after CoDy, 2 after the side-by-side view (0 = Strongly disagree, 7 = Strongly agree). The Finish stage keeps one optional text field.
- The Google Form links (`static/study-links.js`) are removed from the app.
- **Study files:** after every change the server rewrites `<workbench home>/study-data/` (by default `~/.tgap/workbench/study-data/`) from the database: `sessions.csv`, `pre_survey.csv`, `ratings.csv` (one row per question), `feedback.csv` and `study.json` (everything plus the question texts). The files use the random participant code only. Withdrawal removes a participant from them too. Researchers can also download `/api/admin/export/compare_pre`.
- **Accounts:** new accounts register with an e-mail address (stored in lowercase). Existing username accounts, such as those in `users.txt`, can still sign in.
