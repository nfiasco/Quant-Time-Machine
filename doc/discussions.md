# Using GitHub Discussions

[Open Discussions](https://github.com/nfiasco/Quant-Time-Machine/discussions) for questions, proposals, and shared learning. Issues track actionable work and acceptance criteria; the [delivery project](https://github.com/users/nfiasco/projects/2) tracks that work's status. Do not create duplicate planning trackers in Discussions.

## Categories

| Category | Use it for | Format |
| --- | --- | --- |
| [Announcements](https://github.com/nfiasco/Quant-Time-Machine/discussions/categories/announcements) | Maintainer updates, demos, milestones, and changes contributors need to know about | Maintainer-created announcements; community replies |
| [Q&A](https://github.com/nfiasco/Quant-Time-Machine/discussions/categories/q-a) | Setup, API usage, data availability, and methodology questions | Questions with a marked answer |
| [Ideas](https://github.com/nfiasco/Quant-Time-Machine/discussions/categories/ideas) | Proposed features, design alternatives, and research directions before committing to work | Open discussion |
| [General](https://github.com/nfiasco/Quant-Time-Machine/discussions/categories/general) | Team coordination and project conversations that do not fit another category | Open discussion |
| [Show and tell](https://github.com/nfiasco/Quant-Time-Machine/discussions/categories/show-and-tell) | Demos, reproducible experiments, and lessons learned | Open discussion |
| [Polls](https://github.com/nfiasco/Quant-Time-Machine/discussions/categories/polls) | Gathering preferences when a concrete choice would benefit from a vote | Poll |

Use Q&A, Ideas, and Announcements as the main entry points. General, Show and tell, and Polls are optional; they do not need recurring posts. The repository uses GitHub's standard categories to keep navigation familiar. Category forms in `.github/DISCUSSION_TEMPLATE/` match the category slugs.

## Posting and responding

- Search for an existing thread first. Give a thread one clear topic and a descriptive title.
- Explain the question or problem, what you tried, and relevant constraints. For technical help include the commit, command or route, and environment. Use the Q&A form's synthetic reproduction field instead of uploading raw datasets.
- Follow the [Code of Conduct](../CODE_OF_CONDUCT.md). Explain disagreements with evidence, make space for different experience levels, and avoid personal remarks.
- Never post tokens, `.env` contents, private research, or restricted provider data. Vulnerabilities go through [private reporting](../SECURITY.md); behavioral concerns use the conduct policy's contact.
- When a Q&A reply solves the problem, the author or a maintainer should mark it as the answer. Add a short resolution when the eventual fix differs from earlier replies.
- When an idea becomes agreed work, open or link the existing story/spike/bug issue and summarize the decision. A poll records preferences; a maintainer records the actual decision and its rationale in the issue or relevant project document.

## Maintainer moderation

Move misplaced threads to the appropriate category, link duplicates to the canonical thread, and close resolved or superseded discussions with a short explanation. Keep useful historical context. Use announcement posts for durable guidance and meaningful updates, not every CI run or dependency update.

Apply the conduct policy consistently, limit exposure of private information, and explain moderation decisions when appropriate. Delete abusive or sensitive content when necessary; do not routinely delete unanswered questions or automatically close quiet threads. Repository maintainers handle moderation; no agent or bot is required.
