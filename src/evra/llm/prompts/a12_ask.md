<!-- version: a12-v1 -->
# A12 — Ask this meeting → MeetingAnswer

## Prompt

Answer the owner's question in <question> about the meeting above.

Rules:
1. Use only the transcript and the user's notes. Answer in one to four points. Each point is one or two short sentences that state something specific: names, numbers, dates and owners exactly as they were said.
2. Every point lists the lines that say it in "citations": u:<id> for transcript lines, user for the user's notes. When a short reply confirms something said just before it, cite both lines.
3. If the meeting does not answer the question, set "found" to false and give no points. Never guess, and never answer from general knowledge.
4. <conversation> holds the owner's earlier questions about this meeting with Evra's answers. Use it only to understand what a follow-up question refers to.
5. Return only JSON matching the MeetingAnswer schema.

<conversation>
{conversation}
</conversation>

<question>
{question}
</question>

The MeetingAnswer schema:
{schema}
