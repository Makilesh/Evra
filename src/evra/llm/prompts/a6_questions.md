<!-- version: a6-v1 -->
# A6 — Open questions → OpenQuestions

## Prompt

List the questions raised in the meeting above that were not answered by the end of it, and the user's notes containing "?" that the transcript does not answer.

Rules:
1. Each question has: question (under 25 words), raised_by ("You", "Them", or null), and citations: the lines where it was raised (u:<id>), and user for the user's notes.
2. Leave out questions answered later in the meeting, rhetorical questions and small talk ("How are you?").
3. A topic someone wants to pick up next time is not an open question.
4. Return only JSON matching the OpenQuestions schema.

The OpenQuestions schema:
{schema}
