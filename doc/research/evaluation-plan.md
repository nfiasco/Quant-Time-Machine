# Success measures and evaluation plan

> **Story S2.4.** Set on 2026-11-16. The team skipped user interviews (S2.1 was removed from scope that day), so the research-effort baseline comes from the hands-on [tool comparison](existing-tools.md) (S2.2) instead of interview notes. The usability-test protocol is for round 1 (S15.3) and is reused for round 2 (S15.8).

## The measures

These replace the table in [roadmap §1.5](../roadmap.md#15-success-measures). Three are confirmed as they were, one is changed, and one is new.

| Measure | Target | How we check | Change |
| --- | --- | --- | --- |
| Point-in-time correctness | All golden cases pass; zero audit violations in every run | Golden tests in CI (S3.6); the audit every run saves (S7.7); the audit invariant check (S12.1) | Confirmed; the audit already exists |
| Deliberate look-ahead is caught | Every case in the biased-strategy suite is flagged | The suite in CI (S12.5) | Confirmed |
| Reproducibility | Re-running a saved run gives the same run ID and byte-identical files | Determinism test (S7.7); re-run and verify (S13.2) | Confirmed |
| Less research effort | A first-time user runs the canonical example from the UI in under 5 minutes without code (NFR-10), and answers a point-in-time question in the explorer in under 3 minutes: each by at least 4 of 5 participants, unaided | Usability sessions (S15.3, S15.8), against the [baseline below](#research-effort-baseline) | Changed: the baseline comes from S2.2, not interviews |
| Results can be checked | At least 3 of 5 participants find, unaided, the filing behind one decision of a run | Usability task T5 | New, from S2.2's third takeaway: a matching number isn't an audit |
| AI translation quality | Set after a baseline, for example at least 85% of eval questions produce the correct spec | Eval suite (S11.7) | Confirmed; spring |

## Research-effort baseline

S2.2 tried the canonical question without Quant Time Machine, in a pandas notebook and in backtrader, on the same raw downloads. Writing time wasn't measured, so the baseline is the code each needed, the decisions it left to the researcher, and what happened when one was wrong.

| How | What it took | Result | Warning when wrong |
| --- | --- | --- | --- |
| A notebook, written the obvious way | About 300 lines of pandas for all of its versions | 25.1% a year: 6.6 points too high | None |
| A notebook, written carefully | The same script, with eight date and data decisions made correctly ([listed in S2.2](existing-tools.md#a-notebook)) | 18.5% a year, but the engine's exact holdings at only 36 of 192 decisions | None |
| backtrader, with the careful notebook's signals | About 100 more lines and three workarounds | 17.0% a year at first, 1.5 points low, with 190 orders quietly rejected; 18.5% after the workarounds | None |
| Quant Time Machine | One spec and one command, or one API request | 18.5% a year, with 340 warnings and an audit of every read | Every missing value is a warning; every read is audited |

Usability round 1 measures our side in minutes. To compare the two, it ends by asking each participant how they would have answered tasks T1 and T3 without the tool, and how long that would have taken them. Those answers are self-reported estimates, not measurements, and the report says so.

## Usability test protocol, round 1 (S15.3)

**Goal.** Can a first-time user, without reading code, see what was known at a past moment, run the canonical example, and check one of its decisions?

**Participants.** Five people from the primary personas ([roadmap §1.4](../roadmap.md#14-users)): students who have taken a finance or quantitative course, or belong to an investment club, including at least one who doesn't program. Not teammates. Each session is 30 minutes, in person or by video.

**Consent and data.**

- Read the consent script before starting: what we test (the tool, not them), what we record (notes and timings; a screen recording only with a yes), that they can stop at any time, and that nothing identifies them in our results.
- Participants are P1 to P5. No names, emails, or recordings go into the repository or a public issue; notes stay in the team's private drive and are deleted after the S15.4 report.
- Only the aggregated results, and issues that quote no one, are committed.

**Setup.** The deployed site in a fresh browser profile, signed out, on a laptop. One moderator and one note-taker. Participants think aloud. The moderator doesn't help unless a participant is stuck for 2 minutes; help makes that task "assisted".

**Tasks.** Read each one aloud exactly as written. A task whose feature isn't deployed by the session is skipped and recorded as "not tested".

| Task | Read aloud | Success | Time limit | Needs |
| --- | --- | --- | --- | --- |
| T1 | "It's 9:30 in the morning on June 5, 2020. What was the latest unemployment rate anyone could have known, and when was it published?" | 13.3%, for May, published at 08:30 ET that morning | 3 min | Explorer (S9.2) |
| T2 | "At that moment, had Apple filed its report for the quarter that ended in March? When?" | Yes: its 10-Q, accepted April 30, 2020, at 18:03 ET | 3 min | Explorer (S9.2) |
| T3 | "Run the example backtest: revenue growth and momentum, 2010 to 2025." | A run started from the canonical preset, with its results on screen | 5 min (NFR-10) | Builder and results (S9.5, S9.6) |
| T4 | "Did that strategy beat the market? By how much a year?" | The run's CAGR against SPY's (18.5% against 13.9% for the canonical run) | 2 min | Results (S9.6) |
| T5 | "On June 1, 2020, the strategy didn't buy Apple. Why not, and which filing told it so?" | Apple's revenue growth slowed by 8.39 points, from its 10-Q accepted April 30, 2020 | 4 min | The results page's drill-down (S9.6) |
| T6 | "Run it again with trading costs of 25 basis points instead of 10. What changed?" | A second run with 25 bps, and a correct statement of how its return changed | 4 min | Builder and results (S9.5, S9.6) |

**What to record.**

- Per task: unaided, assisted, or failed; time on task, from the end of the reading to the answer; wrong answers or wrong turns, in a few words; and the Single Ease Question ("Overall, how easy was this task?", 1 to 7).
- At the end: the System Usability Scale (10 items), then three questions. "What would you use this for?" "What was confusing?" "Without this tool, how would you have answered T1 and T3, and how long would it have taken you?"

**Pass marks for round 1.**

- T1 and T2: at least 4 of 5 unaided, each within its limit.
- T3: at least 4 of 5 unaided within 5 minutes (NFR-10).
- T5: at least 3 of 5 unaided (the new "results can be checked" measure).
- A mean SUS score of 68 or more, the commonly cited average.

**Afterward.** Within a week, write up the results by task, with the counts, the median times, and the problems ranked by how many participants hit them. Open a bug or story for each problem, and put the summary in the S15.4 report. Round 2 (S15.8) repeats the protocol, adds the assistant's tasks, and compares the two rounds.
