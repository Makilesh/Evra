"""Make the 60-minute synthetic 1:1 fixture for the note bake-off (BUILD.md §9.5: note ready
after a 60-minute 1:1). A local model writes the call in 24 parts of about two and a half
minutes; known facts are planted word for word at set points, so the bake-off can check that a
fact from minute 55 still reaches the note. Long turns are split at sentence ends, as voice
detection cuts real speech at pauses. Everything in it is made up, so it is safe to commit.

    uv run python tools/make_long_fixture.py gemma4:12b
"""

from __future__ import annotations

import argparse
import json
import random
import re
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from evra.config import LlmSettings
from evra.console import safe_console
from evra.llm.ollama import OllamaProvider
from evra.llm.provider import ChatMessage, LlmError, LlmProvider

OUT = (
    Path(__file__).resolve().parents[1]
    / "tests"
    / "fixtures"
    / "notes"
    / "one_on_one_60min_synthetic.json"
)
YOU, THEM = 0, 1  # channels: 0 = microphone, 1 = system audio
SPEAKERS = {YOU: "You", THEM: "Them"}
MEETING_MS = 60 * 60 * 1000
STARTED_AT = 1790600000000
SENTENCE_END = re.compile(r"(?<=[.?!])\s+")

Line = tuple[int, str]  # (channel, text)


@dataclass(frozen=True)
class Fact:
    what: str
    keywords: tuple[str, ...]  # the bake-off's rule: every keyword in one line, "a|b" = either
    lines: tuple[Line, ...]  # planted word for word


@dataclass(frozen=True)
class Part:
    topic: str
    facts: tuple[Fact, ...] = ()


PARTS = (
    Part("Opening small talk: the weekend and how each of them is doing."),
    Part("How the team feels this week: energy, morale, anything worrying."),
    Part(
        "Status of the Atlas beta: sign-ups and readiness.",
        (
            Fact(
                "38 customers signed up for the beta",
                ("38", "customer"),
                ((YOU, "We have 38 customers signed up for the beta so far."),),
            ),
        ),
    ),
    Part(
        "What still blocks the Atlas beta, and settling its date.",
        (
            Fact(
                "Atlas beta moves to March 3",
                ("atlas", "march 3|3 march|march third"),
                (
                    (THEM, "Okay, let's lock it in: the Atlas beta moves to March 3."),
                    (YOU, "Yes, March 3 works for us."),
                ),
            ),
        ),
    ),
    Part("What early beta testers said about the product."),
    Part("The two biggest risks the team sees for the beta, and how to reduce them."),
    Part(
        "Hiring for the data pipeline work.",
        (
            Fact(
                "two contractors approved for the data pipeline",
                ("two|2", "contractor"),
                ((THEM, "Good news, I got approval for two contractors for the data pipeline."),),
            ),
        ),
    ),
    Part(
        "Onboarding the new hire smoothly.",
        (
            Fact(
                "Dana starts on the 14th",
                ("dana", "14"),
                ((THEM, "Dana starts on the 14th, so please plan her first week."),),
            ),
        ),
    ),
    Part("Team workload this sprint."),
    Part("Who is stretched thin, and how to rebalance the work."),
    Part(
        "The weekend outage: what broke and how it was found.",
        (
            Fact(
                "the outage lasted 47 minutes",
                ("47",),
                (
                    (
                        YOU,
                        "The outage on Saturday lasted 47 minutes from the first alert to the fix.",
                    ),
                ),
            ),
        ),
    ),
    Part(
        "Follow-ups from the outage.",
        (
            Fact(
                "You write the postmortem by Friday",
                ("postmortem|post-mortem", "friday"),
                (
                    (THEM, "Can you write the postmortem by Friday?"),
                    (YOU, "Yes, I'll have the postmortem done by Friday."),
                ),
            ),
        ),
    ),
    Part("Gaps in monitoring that the outage exposed."),
    Part("Alerting improvements so the next incident is caught sooner."),
    Part(
        "Budget for tools.",
        (
            Fact(
                "18,000 approved for the load-testing tool",
                ("18,000|18000|18k|18 thousand", "load"),
                ((THEM, "Finance approved 18,000 for the load-testing tool."),),
            ),
        ),
    ),
    Part(
        "Changes to the team's meeting schedule.",
        (
            Fact(
                "standup moves to 10:30",
                ("standup|stand-up", "10:30"),
                (
                    (YOU, "Let's move standup to 10:30 starting next week."),
                    (THEM, "Agreed, standup at 10:30 it is."),
                ),
            ),
        ),
    ),
    Part("Friction with another team over code reviews."),
    Part("How to handle the code-review friction from here."),
    Part(
        "Career growth: a conference trip.",
        (
            Fact(
                "conference in Lisbon in May approved",
                ("lisbon",),
                ((THEM, "Your trip to the conference in Lisbon in May is approved."),),
            ),
        ),
    ),
    Part(
        "Career growth: the promotion process.",
        (
            Fact(
                "promotion packet due by the end of the quarter",
                ("promotion", "quarter"),
                ((THEM, "Send me your promotion packet by the end of the quarter."),),
            ),
        ),
    ),
    Part("Small admin items: equipment and expenses."),
    Part(
        "The team's laptops.",
        (
            Fact(
                "Them asks finance about the laptop refresh",
                ("laptop", "finance"),
                ((THEM, "I'll ask finance about the laptop refresh this week."),),
            ),
        ),
    ),
    Part(
        "What is still undecided.",
        (
            Fact(
                "open question: whether to sunset the legacy API",
                ("legacy", "sunset"),
                (
                    (YOU, "We still haven't decided whether to sunset the legacy API."),
                    (THEM, "Right, we don't have an answer on that yet."),
                ),
            ),
        ),
    ),
    Part(
        "What to cover next time.",
        (
            Fact(
                "next time: the roadmap offsite",
                ("roadmap", "offsite"),
                ((THEM, "Next time let's talk about the roadmap offsite."),),
            ),
        ),
    ),
)

SYSTEM = (
    "You write realistic transcripts of spoken work conversations, the way speech recognition"
    " hears them: everyday spoken English with contractions, fillers (uh, um, you know), false"
    " starts, short replies (Yeah. Okay. Right. Mm-hmm.) and the occasional tangent. No stage"
    " directions, no narration, no speaker names inside the text."
)
SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "lines": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "speaker": {"type": "string", "enum": ["You", "Them"]},
                    "text": {"type": "string"},
                },
                "required": ["speaker", "text"],
            },
        }
    },
    "required": ["lines"],
}


def has_fact(text: str, fact: Fact) -> bool:
    text = text.lower()
    return all(any(alt in text for alt in k.lower().split("|")) for k in fact.keywords)


def plant(lines: Sequence[Line], facts: Sequence[Fact]) -> tuple[list[Line], int]:
    """Facts the model left out go in word for word, mid-part."""
    out = list(lines)
    planted = 0
    for fact in facts:
        if any(has_fact(text, fact) for _, text in out):
            continue
        middle = len(out) // 2
        out[middle:middle] = fact.lines
        planted += 1
    return out, planted


def split_long(lines: Sequence[Line], *, max_words: int = 12) -> list[Line]:
    """Long turns split at sentence ends, as voice detection cuts speech at pauses: sentences
    are joined while they fit in `max_words`; a longer sentence stays whole."""
    out: list[Line] = []
    for channel, text in lines:
        chunk: list[str] = []
        for sentence in SENTENCE_END.split(text):
            if chunk and len(" ".join([*chunk, sentence]).split()) > max_words:
                out.append((channel, " ".join(chunk)))
                chunk = []
            chunk.append(sentence)
        out.append((channel, " ".join(chunk)))
    return out


def part_prompt(parts: Sequence[Part], index: int, *, words: int) -> str:
    part = parts[index]
    lines = [
        f"This is part {index + 1} of {len(parts)} of a one-hour weekly 1:1 video call between"
        " You (a software team lead) and Them (their manager). Write the next"
        f" {60 / len(parts):g} minutes of the call: about {words} spoken words.",
        "",
        f"Topic of this part: {part.topic}",
    ]
    if index:
        lines.append("Earlier parts covered: " + " ".join(p.topic for p in parts[:index]))
    if part.facts:
        lines.append(
            "Work these exact sentences into the conversation, each said once, word for word,"
            " by the speaker shown:"
        )
        lines += [f'- {SPEAKERS[ch]}: "{text}"' for f in part.facts for ch, text in f.lines]
    lines.append("Mention no other dates, money amounts, durations or people's names.")
    if index == 0:
        lines.append("The call starts here: begin with greetings.")
    elif index == len(parts) - 1:
        lines.append("The call ends here: finish with goodbyes.")
    else:
        lines.append("The call is already under way: no greetings, no goodbyes.")
    lines.append('Return JSON: {"lines": [{"speaker": "You" or "Them", "text": "..."}]}')
    return "\n".join(lines)


def generate_part(
    provider: LlmProvider, model: str, parts: Sequence[Part], index: int, *, words: int
) -> tuple[list[Line], int]:
    messages = [
        ChatMessage("system", SYSTEM),
        ChatMessage("user", part_prompt(parts, index, words=words)),
    ]
    result = provider.chat_json(model, messages, SCHEMA)
    if result.truncated:
        raise ValueError("the reply was cut off at the output-token limit")
    reply = json.loads(result.content)
    lines: list[Line] = []
    for line in reply["lines"]:
        text = " ".join(str(line["text"]).split())
        if text:
            lines.append((YOU if line["speaker"] == "You" else THEM, text))
    return plant(split_long(lines), parts[index].facts)


def assign_times(
    lines: Sequence[Line],
    *,
    total_ms: int,
    gap_ms: tuple[int, int] = (300, 900),
    seed: int = 7,
) -> tuple[list[dict[str, Any]], float]:
    """Lines one after another with pauses between them; speaking time is shared out by word
    count so the call lasts exactly `total_ms`. Returns the utterances and the speaking rate in
    words per minute."""
    rng = random.Random(seed)
    gaps = [rng.uniform(*gap_ms) for _ in lines[1:]]
    words = [len(text.split()) for _, text in lines]
    ms_per_word = (total_ms - sum(gaps)) / sum(words)
    utterances = []
    t = 0.0
    for i, ((channel, text), count) in enumerate(zip(lines, words, strict=True)):
        if i:
            t += gaps[i - 1]
        start = t
        t += count * ms_per_word
        utterances.append(
            {"ch": channel, "start_ms": round(start), "end_ms": round(t), "text": text}
        )
    return utterances, 60_000 / ms_per_word


def expected_facts(
    utterances: Sequence[Mapping[str, Any]], parts: Sequence[Part]
) -> list[dict[str, Any]]:
    expected = []
    for fact in (f for p in parts for f in p.facts):
        start = next(int(u["start_ms"]) for u in utterances if has_fact(str(u["text"]), fact))
        expected.append(
            {"what": fact.what, "keywords": list(fact.keywords), "minute": start // 60_000}
        )
    return expected


def to_json(fixture: Mapping[str, Any]) -> str:
    """One utterance per line, so the fixture stays readable and diffs stay small."""
    items = []
    for key, value in fixture.items():
        if isinstance(value, list):
            rows = ",\n".join(f"    {json.dumps(v, ensure_ascii=False)}" for v in value)
            items.append(f"  {json.dumps(key)}: [\n{rows}\n  ]")
        else:
            items.append(f"  {json.dumps(key)}: {json.dumps(value, ensure_ascii=False)}")
    return "{\n" + ",\n".join(items) + "\n}\n"


def main(argv: Sequence[str] | None = None) -> int:
    safe_console()
    parser = argparse.ArgumentParser(description="Make the 60-minute synthetic 1:1 fixture")
    parser.add_argument("model")
    # the model writes about 70% of the words it is asked for; 550 gives ~155 words a minute
    parser.add_argument("--words", type=int, default=550, help="spoken words asked per part")
    parser.add_argument("--out", type=Path, default=OUT)
    args = parser.parse_args(argv)
    provider = OllamaProvider(LlmSettings(max_output_tokens=8192, keep_alive="5m"))
    lines: list[Line] = []
    for index in range(len(PARTS)):
        try:
            got, planted = generate_part(provider, args.model, PARTS, index, words=args.words)
        except (LlmError, ValueError, KeyError) as exc:
            print(f"part {index + 1} failed: {type(exc).__name__}: {exc}", file=sys.stderr)
            return 1
        count = sum(len(text.split()) for _, text in got)
        print(f"part {index + 1}: {len(got)} lines, {count} words, {planted} planted", flush=True)
        lines += got
    utterances, wpm = assign_times(lines, total_ms=MEETING_MS)
    fixture = {
        "synthetic": True,
        "generated_by": f"tools/make_long_fixture.py with {args.model}",
        "title": "Weekly 1:1 (60 min)",
        "situation": "call_headphones",
        "template": "one_on_one",
        "started_at": STARTED_AT,
        "utterances": utterances,
        "expected": expected_facts(utterances, PARTS),
    }
    args.out.write_text(to_json(fixture), encoding="utf-8", newline="\n")
    words = sum(len(text.split()) for _, text in lines)
    print(
        f"{len(utterances)} lines, {words} words ({words / 60:.0f} per minute of call,"
        f" {wpm:.0f} while speaking) -> {args.out}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
