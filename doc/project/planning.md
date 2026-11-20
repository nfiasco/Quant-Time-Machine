# Planning record

[Delivery project](https://github.com/users/nfiasco/projects/2) · [Roadmap](../roadmap.md) · [Team workflow](github-workflow.md)

This page records the team's planning decisions: scope changes, owners for selected open work, and carry-over. The issues and the project hold the live state; this record says what was decided and when. Add a dated section at each sprint planning, and keep the old ones.

## November 16, 2026 (Sprint 4)

Recorded by the team lead. It completes S1.2's last task: owners, carry-over, and iterations for the open Fall work.

### Scope decisions

- **WRDS is unavailable.** The UD library denied our request for WRDS access, so CRSP and Compustat can't be used, even internally. S2.3 is closed with the answer recorded in [data sources](../reference/data-sources.md#wrds-crsp-at-the-university-of-delaware). Delisted coverage stays limited to Tiingo's (R1), and S6.7 reports the gaps in every run.
- **No user interviews.** The course doesn't require them, so S2.1 is removed from scope. S2.4 takes its research-effort baseline from the hands-on [tool comparison](../research/existing-tools.md) (S2.2) instead, and the usability tests (S15.3, S15.8) stay as the project's evidence from users.
- **Accounts may be postponed.** E16 (S16.1–S16.6) is left as it is for now, with its current owner and sprints, until the team decides.
- **M1 decisions are settled.** The team ratified the time model with D5 and D12 (S3.1); confirmed that the leaked FRED key was revoked and that MIT fits the course (S1.3); and adopted one required approval on `main`, which repository admins may bypass when merging a PR (S1.4).

### Open Fall work

Owners and iterations are the ones on the project on November 16, confirmed as the plan. Sprint 4 runs November 9 to 22, Sprint 5 November 23 to December 6, and Sprint 6 December 7 to the end of term.

| Story | Milestone | Iteration | Owner | Status | Decision |
| --- | --- | --- | --- | --- | --- |
| [S6.7](https://github.com/nfiasco/Quant-Time-Machine/issues/140) Delistings and coverage report | M4 | Sprint 4 | nfiasco | In progress | Keep in Sprint 4 |
| [S9.3](https://github.com/nfiasco/Quant-Time-Machine/issues/149) Macro revision viewer | M4 | Sprint 4 | ariudel | Backlog | Keep in Sprint 4 |
| [S9.5](https://github.com/nfiasco/Quant-Time-Machine/issues/33) Backtest builder | M5 | Sprint 5 | jacobchacko05 | In progress | Keep in Sprint 5 |
| [S9.6](https://github.com/nfiasco/Quant-Time-Machine/issues/34) Backtest results page | M5 | Sprint 5 | jacobchacko05 | Backlog | Keep in Sprint 5 |
| [S8.6](https://github.com/nfiasco/Quant-Time-Machine/issues/147) Typed client and response caching | M5 | Sprint 5 | Unassigned | Backlog | Unassigned; P2, first to cut (§5.5) |
| [S9.4](https://github.com/nfiasco/Quant-Time-Machine/issues/150) Company filing timeline | M5 | Sprint 5 | Unassigned | Backlog | Unassigned; P2, first to cut |
| [S9.7](https://github.com/nfiasco/Quant-Time-Machine/issues/151) Methodology page | M5 | Sprint 5 | Unassigned | Backlog | Unassigned |
| [S15.2](https://github.com/nfiasco/Quant-Time-Machine/issues/179) Performance baseline | M5 | Sprint 5 | Unassigned | Backlog | Unassigned |
| [S15.3](https://github.com/nfiasco/Quant-Time-Machine/issues/180) Usability test, round 1 | M5 | Sprint 6 | Unassigned | Backlog | Unassigned; the protocol is ready ([evaluation plan](../research/evaluation-plan.md)) |
| [S15.4](https://github.com/nfiasco/Quant-Time-Machine/issues/42) CISC 498 demo and final report | M5 | Sprint 6 | Unassigned | Backlog | Unassigned |
| [S1.1](https://github.com/nfiasco/Quant-Time-Machine/issues/1) Monorepo scaffold with CI | M0 | Sprint 0 | nfiasco | In review | Carried over from Sprint 0 and finished on November 16: the frontend format check is in CI |
| S16.1–S16.6 (E16, accounts) | M0–M5 | Sprints 2–5 | iguy1 | Mixed | Unchanged pending the decision on accounts |

Spring 2027 work (M6–M10) stays unassigned in the backlog until Sprint 7 planning.
