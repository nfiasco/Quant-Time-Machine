# GitHub team workflow

[Delivery project](https://github.com/users/nfiasco/projects/2) · [Roadmap](roadmap.md) · [Contribution history](contribution-history.md)

Issues describe work and acceptance criteria. PRs describe a proposed code or documentation change. The project organizes both using filtered views; it is not a second issue database.

## When an issue is useful

Use the existing story issue for related implementation and small fixes. Create a bug issue when a defect needs independent reproduction, prioritization, ownership, or follow-up. Create a new story only for an independently planned deliverable. A typo, dependency maintenance, or focused documentation correction may have no issue: explain the reason in the PR instead of creating a redundant tracker.

Use `Refs #123` for partial work and `Closes #123` only when the PR satisfies all acceptance criteria. Closing links populate GitHub's Development relationship and close the issue when merged into the default branch. A related reference records context without promising completion. Branches and commit associations belong to the PR's native record; do not rewrite old branches to retrofit a story ID.

## Before opening and merging a PR

Fill the PR template's Summary, Linked work, and Validation sections. State what changed, why, the actual test results, and any remaining scope. Select one primary milestone, one `area: ...` label, one `priority: P0/P1/P2` label, and the responsible assignee(s). Request a suitable teammate's review when appropriate. A new assignee initially identifies who will shepherd the PR; completed-story contributors are verified from actual authored changes.

The template cannot force sidebar fields before creation. The required **PR metadata** status enforces them before merge. It accepts either a valid repository issue reference or `No issue: <specific reason>` for small maintenance. It does not verify acceptance criteria on the team's behalf. A green metadata check is not code review or proof of feature completion.

The automation fills missing area, priority, and milestone when linked issues provide one unambiguous value, and assigns an eligible PR author when no assignee is selected. It preserves explicit choices. Multiple linked milestones require a chosen primary milestone. Documentation/test labels may be added from changed paths. Closed historical PR descriptions, authorship assignments, and milestones are not rewritten by the automation.

## Views and status

| View | Purpose |
| --- | --- |
| Story backlog | Open stories and spikes; excludes bugs, epics, and PRs. |
| Delivery board / Current sprint / My work / Fall delivery | Issue delivery, ownership, and planning. |
| Roadmap | Epic windows and sub-issue progress. |
| Completed | Completed canonical issues and bugs, excluding PRs and historical trackers. |
| Needs attention | Open issues with a recorded blocker. |
| Bug tracker | All bug issues, including resolved bugs; shows status, priority, assignee, milestone, linked PRs, and closure dates. Add `is:open` to focus on unresolved reports. |
| Pull requests | Current and historical PRs, reviewers, assignees, labels, and milestones. Use `is:open`, `is:merged`, or `label:"not merged"` to focus the view. |

For issues, Done requires all acceptance criteria in merged work. For PRs, Done means the PR lifecycle has ended: the native icon and `not merged` label distinguish a merge from closure without merging. A closed-unmerged PR does not complete its story. Native project workflows place newly added/reopened items in Backlog and closed/merged items in Done. Set In review when the remaining acceptance scope is ready for review. The unconditional PR-linked transition is disabled: it moved closed, completed issues backwards when historical links were added. Moving an issue to Done also closes it; check its criteria first.

Each PR carries its primary milestone, including historical PRs. GitHub milestone counts include both issues and PRs. Roadmap counts include stories only, so use the issue views to assess product progress. Epics span milestones and historical trackers remain unmilestoned.

## Automation and maintenance

- The project's seven enabled built-in workflows include an auto-add workflow watches this repository with `is:issue,pr -label:historical`. It also adds sub-issues and updates lifecycle statuses. It needs no repository secret or personal token.
- Story, spike, and bug forms require useful scope and priority/area selections. The trusted repository workflow applies those selected labels to new/edited open issues when that label category is missing. Explicit labels remain the source of truth after triage.
- `PR metadata request` is an unprivileged notification workflow: no checkout, secrets, or write permissions. On completion, `Repository organization` runs the default-branch script, reads current PR metadata through the API, fills safe defaults, and publishes **PR metadata** on the PR head commit. It never executes PR code or downloads PR artifacts. This separation also avoids dependence on `pull_request_target` event-policy exceptions.
- The repository workflow uses the built-in token with narrowly scoped repository write permissions. Projects are handled by native workflows because the repository token does not grant Projects access. Custom Priority/Size/Iteration/Semester fields remain planning fields; keep Priority consistent with labels during triage.
- Closed-unmerged PRs receive `not merged`; reopening or merging removes it. Historical reviews remain historical: no automation creates retroactive reviewer requests or approvals.
- CI runs the policy's unit tests alongside the existing frontend, backend, and container checks. Main requires **Frontend (lint + test + build)**, **Backend (lint + test)**, **Backend image (build + start)**, **Organization policy tests**, and **PR metadata**; the remaining one-approval policy decision stays visible in S1.4 until adopted. The ruleset matches each check by its job name, so rename a job in `ci.yml` and in the "Protect main" ruleset together.

If a PR metadata check fails, open its linked Actions run for the unmet requirements and edit the PR. Metadata changes trigger a new check. After an infrastructure failure, rerun `Repository organization` using **Run workflow**, set `pr_number`, and leave `issue_number` empty; use the inverse to recategorize an issue. For a fork, GitHub may require approval of the unprivileged workflow before it runs. Do not bypass that approval policy.

At each milestone review, reconcile story tasks and contributors against merged commits, confirm future owners and dates, and refresh the roadmap. Do not infer delivery from a merged placeholder, schema, disabled form, or the person who clicked Merge.
