# Security policy

## Supported versions

Quant Time Machine is under active development and has no published supported release series. Security fixes are applied to the latest `main` and deployed from there. Older commits, feature branches, and forks do not receive separate backports. The `0.1.0` package/API version identifies development software, not a long-term support release.

## Report a vulnerability privately

Use GitHub's [Report a vulnerability](https://github.com/nfiasco/Quant-Time-Machine/security/advisories/new) form. If that route is unavailable, email the repository maintainer, Nico Fiasco, at [nfiasco@udel.edu](mailto:nfiasco@udel.edu) with the subject `Quant Time Machine security report`.

Do not disclose an unpatched vulnerability in a public issue, discussion, or pull request. Include:

- The affected commit, component, endpoint, or deployment.
- A minimal reproduction with synthetic data and the expected security boundary.
- The observed impact, prerequisites, and any suggested mitigation.
- A way to contact you and your preference for public credit.

Do not send live credentials, personal data, or restricted provider datasets. If a credential is exposed, its owner should revoke or rotate it immediately; removing the file does not remove the credential from Git history. Coordinate any history cleanup with maintainers.

## How reports are handled

Maintainers aim to acknowledge reports within three business days and provide an initial assessment within seven business days. These are response targets for a student-maintained project, not a guaranteed service level. If there is no acknowledgement, follow up through the other private channel.

Maintainers reproduce the issue, assess reachable impact, agree on a fix or mitigation, and add regression coverage where practical. They coordinate disclosure with the reporter after the fix is available, publish a GitHub security advisory when warranted, and arrange a CVE when appropriate. Release timing depends on severity and a safe fix; unresolved reports receive progress updates. Credit is given only with the reporter's consent.

## System boundary and security expectations

The current system consists of a Next.js frontend on Vercel, a FastAPI read API on Railway, and a maintainer-run ingestion CLI that writes a Parquet/DuckDB point-in-time store. Configuration and provider credentials come from local environment files or hosting settings. Supabase accounts, saved private research, and the research assistant are planned; the current sign-in forms are placeholders and do not provide access control.

Security-sensitive boundaries include browser and API input, downloaded provider responses, URLs and identifiers used for data access, deployment credentials, and GitHub Actions. In particular:

- Untrusted input must not execute code, select arbitrary filesystem paths, escape query parameterization, or cause unintended outbound requests. Public API operations must validate inputs and bound their work.
- Credentials and private data must not appear in responses, logs, committed fixtures, or browser bundles. CORS is a browser restriction, not authentication or authorization.
- Public deployments must keep `SERVE_RAW_PRICES=false` while redistribution rights are unresolved. Provider data and credentials must stay within their permitted use.
- Workflows that process contributions must not execute untrusted PR code with write tokens or secrets. Privileged metadata automation reads trusted default-branch code and API metadata only.
- Before accounts or private research are introduced, authorization and user-data isolation must be implemented and tested at the API/storage boundary. A sign-in page alone is not such a boundary.

Report reachable credential exposure, injection, access-control failures, unintended data disclosure, supply-chain compromise, and practical denial of service. Include the conditions needed to demonstrate impact; scanners are useful leads, not proof. Point-in-time correctness or accessibility bugs normally belong in public issues unless they also break a security boundary. There are no blanket exclusions for particular components or tools.

Use local copies and synthetic data for reproductions. Do not access another person's data, degrade shared deployments, or test third-party providers without their permission. Repository policies cannot authorize testing of those providers.

## Preventive controls

The repository uses CodeQL, Dependabot alerts, secret scanning with push protection, dependency review, and required CI checks. Bots report findings and run checks; team members make code and dependency changes. Their scope and maintenance are documented in [GitHub settings](doc/github-settings.md). These controls do not establish that the application has passed a security audit; feature-specific reviews remain part of implementation.
