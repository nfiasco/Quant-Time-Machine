# Repository security and quality settings

This guide records the intended configuration for `nfiasco/Quant-Time-Machine`. Review it when the repository's visibility, deployment model, package managers, or GitHub plan changes. GitHub settings are managed through the repository APIs/CLI; files below are version-controlled.

## Community

The root README, MIT license, Code of Conduct, contributing guide, security policy, accessibility policy, and support guide provide the community entry points. `.github/ISSUE_TEMPLATE/` contains story, spike, bug, and accessibility forms plus links to questions, proposals, and private security reporting. The PR template follows the existing metadata workflow.

Discussions uses GitHub's six standard categories, with Q&A and Ideas forms and a [project-specific guide](discussions.md). GitHub's public Discussions API can create and edit posts, but does not expose category creation/renaming or pinning; those operations require GitHub's web interface. The current setup does not depend on custom categories or a pinned post.

The repository keeps its MIT license and existing project board. Funding, a CLA bot, a separate wiki, and additional planning bots are unnecessary for the current workflow. CODEOWNERS is deferred until the team explicitly assigns review responsibility by path; repository ownership alone should not silently assign every review to one person.

## Security controls

| Control | Configuration and purpose |
| --- | --- |
| Private vulnerability reporting | Enabled; [SECURITY.md](../SECURITY.md) also supplies a fallback contact. |
| Dependency graph | Enabled for supported manifests and lockfiles; inventories dependencies for alerts and review. |
| Dependabot alerts | Enabled. Maintainers assess reachability, prioritize fixes, and record the reason for any dismissal. |
| Automatic dependency changes | Disabled: no Dependabot security-update PRs and no version-update configuration. The team makes npm, uv, and Action updates through normal reviewed PRs. |
| Secret scanning and push protection | Enabled for supported secret patterns. A finding requires credential rotation and investigation, not just deletion. Non-provider pattern scanning and validity checks remain disabled; these are not needed for the baseline. |
| CodeQL | Default setup scans Actions, JavaScript/TypeScript, and Python with the standard query suite and remote threat model. GitHub manages the workflow and scheduled scans; no duplicate CodeQL YAML is needed. The main-branch ruleset requires results and blocks errors or high/critical security findings introduced by a PR. |
| Dependency review | The [PR workflow](../.github/workflows/dependency-review.yml) rejects newly introduced dependencies with known high or critical vulnerabilities. Lower-severity alerts still require triage. |

Alerts update as GitHub processes dependency changes and published advisories. Coverage depends on supported ecosystems and manifest parsing; an empty alert list is not proof that dependencies are safe. Check the alert dashboard regularly because automated fix PRs are intentionally disabled. Do not copy sensitive findings into public issues before coordinated disclosure.

## CI and merge controls

- The active **Protect main** ruleset requires a PR and the six checks listed in the [team workflow](github-workflow.md#automation-and-maintenance). It blocks branch deletion and force pushes and requires resolved review conversations. Its existing zero-required-approvals setting is retained; adopting the planned one-review requirement remains tracked in S1.4. Contributors should still request peer review.
- Actions tokens default to read access and cannot approve PRs. Individual jobs/workflows request only their needed permissions. The privileged organization workflow runs trusted default-branch code and never executes PR code or reads PR artifacts.
- Third-party Actions in repository workflows are pinned to full commit SHAs. Maintainers review upstream releases and update those pins manually, verifying the release's commit. Checkouts disable credential persistence; jobs have bounded timeouts.
- ESLint, Vitest, the Next.js production/type-checking build, Ruff, pytest, metadata-policy tests, and the container build/start check cover the current stack. Accessibility also requires the manual checks in [ACCESSIBILITY.md](../ACCESSIBILITY.md).
- Successfully merged branches are deleted automatically. There is no automatic merge policy for dependency PRs and no stale-issue bot.

## Optional products and agents

GitHub's Code Quality setup API reports that the product is unavailable for this repository. Its current availability requires GitHub Team or Enterprise Cloud, and it is a separate product from Copilot. The existing CI checks provide the project's quality gate without a new subscription, coverage threshold, or duplicate scanner. Reassess only if the team needs capabilities those checks cannot provide.

No Copilot subscription or AI agent is required for Discussions, community files, Dependabot alerts, secret scanning, CodeQL in this public repository, or the CI workflows here. The team policy is alerts and checks only: bots must not author code changes. Do not enable automatic dependency PRs, agent-generated fixes, or auto-merge. No additional issue-creation bot is needed; maintainers can turn a public advisory into an issue when tracking work would help.

## Routine maintenance

At milestone reviews, inspect the Security tab, CodeQL analysis health, failed Actions runs, and dependency PRs. Confirm reporting contacts and documentation links still work. Validate new workflows before making their checks required; keep job names and ruleset contexts synchronized. Revisit supported versions when the first release is published.

References: [GitHub community profiles](https://docs.github.com/en/communities/setting-up-your-project-for-healthy-contributions/about-community-profiles-for-public-repositories), [security quickstart](https://docs.github.com/en/code-security/getting-started/quickstart-for-securing-your-repository), [CodeQL default setup](https://docs.github.com/en/code-security/how-tos/find-and-fix-code-vulnerabilities/configure-code-scanning/configure-code-scanning), and [Code Quality availability](https://docs.github.com/en/code-security/how-tos/maintain-quality-code/enable-code-quality).
