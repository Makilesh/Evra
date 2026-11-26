<!-- version: a4-v1 -->
# A4 — Action items → ActionItems

## Prompt

List the action items in the meeting above: specific tasks someone agreed to do or was asked to do.

Rules:
1. Each item has: text (an imperative under 20 words, without the owner: "Send the vendor quote"), owner ("You", "Them", or null when it is unclear who took it on), due (as it was said, for example "by Friday", or null), confidence (0 to 1), and citations: the lines where it was asked for and where it was accepted (u:<id>), or user for the user's notes.
2. The owner is the person who accepted the task or was given it, not the person who asked for it.
3. Include items in the user's notes marked "TODO", "->", "AI:" or similar.
4. Leave out vague intentions ("we should think about…") unless someone committed to them, and anything already done during the call.
5. List each item once. Return only JSON matching the ActionItems schema.

The ActionItems schema:
{schema}
