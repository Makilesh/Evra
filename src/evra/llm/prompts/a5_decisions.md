<!-- version: a5-v2 -->
# A5 — Decisions → Decisions

## Prompt

List the decisions made in the meeting above: explicit agreements, approvals or choices between options.

Rules:
1. Each decision has: statement (under 25 words), made_by ("You", "Them", or null when both agreed or it is unclear), and citations: the lines where it was agreed (u:<id>).
2. A proposal, a suggestion or a tentative plan ("maybe", "we could", "let's see") is not a decision.
3. A task someone took on or was given is an action item, not a decision: leave it out.
4. List each decision once. Return only JSON matching the Decisions schema.

The Decisions schema:
{schema}
