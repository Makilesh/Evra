<!-- version: a2-v1 -->
# A2 — Digest of one part of a long meeting → WindowDigest

## Prompt

Summarise this part of the meeting for a later step that combines every part into one note.

Rules:
1. Return points of these kinds: "topic" (what was discussed, one per topic), "point" (a specific thing said: a fact, number, date, update, problem or piece of feedback), "decision" (explicitly agreed; a task someone took on is a commitment, not a decision), "commitment" (a task someone accepted or was given, written as an imperative without the owner or the due date; an agreed date, time or choice on its own is a decision; owner "You" or "Them", due as it was said, else null) and "question" (raised and not answered in this part, or said to be still undecided; phrased as a question).
2. Each point is under 30 words and specific (who, what, when; names and numbers exactly as said; a commitment's who and when go in owner and due). Cite every line the point draws on (u:<id>): the lines that say it and the lines its names, numbers and dates come from, or user for the user's notes.
3. supports_notes lists the user's notes (n:<id>) this part supports.
4. Return only JSON matching the WindowDigest schema, with window_index {window_index}.

The WindowDigest schema:
{schema}
