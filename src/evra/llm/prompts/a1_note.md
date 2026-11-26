<!-- version: a1-v4 -->
# A1 — Note synthesis (single pass) → NoteDraft

## Prompt

Write the note for the meeting above.

Rules:
1. The user's typed notes are the strongest signal of what mattered. Every topic the user wrote about gets its own bullet or section, expanded with detail from the transcript lines aligned to that note. Keep the user's own words and terminology.
2. Parts of the transcript the user did not annotate get short treatment, unless they contain a decision, a commitment, a deadline, a number or an unresolved question.
3. Every factual sentence ends with one or more citations of the form [u:<utterance_id>] pointing at lines in <transcript>. Text taken from the user's notes ends with [user]. If you cannot cite a statement, leave it out.
4. Keep generic speaker labels (for example "Room B") when no name is given.
5. Write in {output_language}. Be terse: bullets over paragraphs, no filler, no praise, no commentary about the meeting's quality.
6. Follow the template sections in order. Omit a non-required section if there is nothing to put in it.
7. The summary is one to three short bullets: what the meeting was mainly about and what came out of it. Do not repeat a point a section already makes; the sections carry the detail.
8. Every bullet states one specific point: what was said, agreed, asked or promised, with who, what and when wherever the transcript gives them. Start with the point itself, never with a "Topic:" label. A bullet that only names a topic ("Budget discussion.") is not allowed.
9. Leave decisions, action items and open questions out: they are listed separately. A topic someone wants to come back to later goes in the section for next time when the template has one, not under open questions.
10. Cite every line the bullet draws on: the lines that say what it says, and the lines its names, numbers and dates come from. When a short reply ("Yeah, I can do that.") confirms something said just before it, cite both lines.
11. Return only JSON matching the NoteDraft schema.

<template name="{template_name}">
{template_sections_yaml}
</template>

The NoteDraft schema:
{schema}
