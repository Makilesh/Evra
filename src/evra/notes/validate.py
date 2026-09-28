"""Mechanical grounding (BUILD.md §7.5), lexical part. A kept bullet cites utterances that exist,
shares at least 20% of its content words with them (5-letter prefixes, so "agreed" matches
"agree"), and every number and name in it appears in what it cites ("twelve thousand" counts
for 12,000, and so does "12k"). Conversation carries context across turns, so a name or number
said up to three lines from a cited line gets that line added as a citation. The embedding
check (cosine >= 0.55) joins in M5 with the embedding model."""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from evra.llm.schemas import NoteBullet, NoteDraft
from evra.notes.templates import Template

MIN_OVERLAP = 0.2
NEARBY = 3  # a name or number said up to 3 lines away is cited from there
_THOUSANDS = re.compile(r"(\d+(?:\.\d+)?)\s?[kK]\b")
_RSQUO = chr(0x2019)  # typographic apostrophe
_TYPOGRAPHIC_OPENERS = "".join(
    map(chr, (0x201C, 0x2018, 0x2013, 0x2014, 0x2022))
)  # quotes, dashes, bullet
CITATION_RE = re.compile(r"^(u:[\w-]+|user|n:[\w-]+|m:\d+|d:\d+|w:\d+|g)$")
_INLINE = re.compile(r"\s*\[((?:u:[\w-]+|user)(?:\s*,\s*(?:u:[\w-]+|user))*)\]")
_WORD = re.compile(rf"[A-Za-z0-9]+(?:['{_RSQUO}][A-Za-z]+)?")
_NUMBER = re.compile(r"\d+(?:[.,:]\d+)*")
_CAPITALISED = re.compile(r"\b[A-Z][A-Za-z]+\b")
_SENTENCE_START = ".!?:;(\"'-*" + _TYPOGRAPHIC_OPENERS
_NOT_NAMES = {"you", "them", "i"}


def _wordlist(text: str) -> list[str]:
    return text.split()


STOPWORDS = frozenset(
    _wordlist(
        """a an the and or but if then so of to in on at by for with from as is are was were be
        been being am do does did done have has had having i me my we our us you your yours they
        them their he him his she her it its this that these those there here what which who whom
        whose when where why how all any both each few more most other some such no not nor only
        own same than too very can could will would shall should may might must just also about
        into over after before again further once up down out off under between during through
        above below because while until yes yeah okay ok right well like really think know get
        got going go let lets let's said says say mentioned discussed noted asked talked
        suggested explained shared raised agreed wants want plans need needs"""
    )
)

_SMALL = _wordlist(
    "zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen"
    " fifteen sixteen seventeen eighteen nineteen"
)
_SMALL_ORDINAL = _wordlist(
    "zeroth first second third fourth fifth sixth seventh eighth ninth tenth eleventh twelfth"
    " thirteenth fourteenth fifteenth sixteenth seventeenth eighteenth nineteenth"
)

_TENS = ["twenty", "thirty", "forty", "fifty", "sixty", "seventy", "eighty", "ninety"]
_VALUES = {
    **{w: i for i, w in enumerate(_SMALL)},
    **{w: i for i, w in enumerate(_SMALL_ORDINAL)},
    **{w: 20 + 10 * i for i, w in enumerate(_TENS)},
    "twentieth": 20,
    "thirtieth": 30,
}
_SCALES = {"hundred": 100, "thousand": 1_000, "million": 1_000_000}


@dataclass(frozen=True)
class CheckedBullet:
    text: str
    citations: tuple[str, ...]  # utterance ids, and "user"


@dataclass(frozen=True)
class CheckedSection:
    section_id: str
    title: str
    bullets: tuple[CheckedBullet, ...]


@dataclass(frozen=True)
class CheckedNote:
    summary: tuple[CheckedBullet, ...]
    sections: tuple[CheckedSection, ...]
    kept: int
    dropped: int
    drop_reasons: Mapping[str, int]


def _base(word: str) -> str:
    word = word.lower().replace(_RSQUO, "'")
    return word[:-2] if word.endswith("'s") else word


def _key(word: str) -> str:
    return _base(word)[:5]


def _content(words: Sequence[str]) -> set[str]:
    return {_key(w) for w in words if not w.isdigit() and len(w) > 1 and _base(w) not in STOPWORDS}


def _norm_number(text: str) -> str:
    return text.replace(",", "")


def _spoken_numbers(words: Sequence[str]) -> set[str]:
    found: set[str] = set()
    total = current = 0
    active = False
    for word in [*words, ""]:  # the empty sentinel flushes the last run
        if word in _VALUES:
            current += _VALUES[word]
            active = True
        elif word in _SCALES and active:
            if word == "hundred":
                current *= 100
            else:
                total += current * _SCALES[word]
                current = 0
        elif word == "and" and active:
            continue
        else:
            if active:
                found.add(str(total + current))
            total = current = 0
            active = False
    return found


def _names(text: str) -> set[str]:
    found: set[str] = set()
    for match in _CAPITALISED.finditer(text):
        before = text[: match.start()].rstrip()
        if not before or before[-1] in _SENTENCE_START:
            continue
        word = match.group(0).lower()
        if word in STOPWORDS or word in _NOT_NAMES:
            continue
        found.add(word)
    return found


def _citations(bullet: NoteBullet) -> tuple[str, list[str]]:
    raw = list(bullet.citations)
    for match in _INLINE.finditer(bullet.text):
        raw.extend(part.strip() for part in match.group(1).split(","))
    text = " ".join(_INLINE.sub("", bullet.text).split())
    return text, [c.strip().strip("[]").strip() for c in raw]


def _check(
    bullet: NoteBullet,
    aliases: Mapping[str, str],
    utterance_text: Mapping[str, str],
    user_notes: str,
) -> tuple[CheckedBullet | None, str]:
    text, raw = _citations(bullet)
    cited: list[str] = []
    for citation in raw:
        if not CITATION_RE.match(citation):
            continue
        if citation == "user":
            target = "user" if user_notes else None
        else:
            target = aliases.get(citation)
            if target is not None and target not in utterance_text:
                target = None
        if target is not None and target not in cited:
            cited.append(target)
    if not text:
        return None, "empty"
    if not cited:
        return None, "no_valid_citation"
    source = " ".join(user_notes if c == "user" else utterance_text[c] for c in cited)
    source_words = _WORD.findall(source)
    claim = _content(_WORD.findall(text))
    if not claim or len(claim & {_key(w) for w in source_words}) / len(claim) < MIN_OVERLAP:
        return None, "unsupported"
    numbers = _claim_numbers(text)
    names = _names(text)
    have_numbers, have_names = _facts(source)
    for extra in _nearby(cited, aliases, utterance_text):
        if numbers <= have_numbers and names <= have_names:
            break
        extra_numbers, extra_names = _facts(utterance_text[extra])
        if (numbers - have_numbers) & extra_numbers or (names - have_names) & extra_names:
            cited.append(extra)  # the detail was said there: cite it too
            have_numbers |= extra_numbers
            have_names |= extra_names
    if not numbers <= have_numbers:
        return None, "number_not_cited"
    if not names <= have_names:
        return None, "name_not_cited"
    return CheckedBullet(text, tuple(cited)), ""


def _claim_numbers(text: str) -> set[str]:
    def expand(match: re.Match[str]) -> str:
        value = float(match.group(1)) * 1000
        return str(int(value)) if value.is_integer() else str(value)

    return {_norm_number(n) for n in _NUMBER.findall(_THOUSANDS.sub(expand, text))}


def _facts(source: str) -> tuple[set[str], set[str]]:
    """Numbers (written or spoken) and word forms in a piece of transcript."""
    words = _WORD.findall(source)
    numbers = {_norm_number(n) for n in _NUMBER.findall(source)}
    numbers |= _spoken_numbers([w.lower() for w in words])
    return numbers, {_base(w) for w in words}


def _nearby(
    cited: Sequence[str], aliases: Mapping[str, str], utterance_text: Mapping[str, str]
) -> list[str]:
    """Utterances within NEARBY lines of the cited ones, closest first."""
    position = {uid: int(alias[2:]) for alias, uid in aliases.items() if alias[2:].isdigit()}
    by_position = {n: uid for uid, n in position.items()}
    anchors = [position[c] for c in cited if c in position]
    found: list[str] = []
    for distance in range(1, NEARBY + 1):
        for anchor in anchors:
            for n in (anchor - distance, anchor + distance):
                uid = by_position.get(n)
                if uid is not None and uid in utterance_text and uid not in (*cited, *found):
                    found.append(uid)
    return found


def check_note(
    draft: NoteDraft,
    *,
    aliases: Mapping[str, str],
    utterance_text: Mapping[str, str],
    template: Template,
    user_notes: str = "",
) -> CheckedNote:
    reasons: Counter[str] = Counter()

    def check_all(bullets: Sequence[NoteBullet]) -> list[CheckedBullet]:
        kept: list[CheckedBullet] = []
        for bullet in bullets:
            checked, reason = _check(bullet, aliases, utterance_text, user_notes)
            if checked is None:
                reasons[reason] += 1
            else:
                kept.append(checked)
        return kept

    summary = tuple(check_all(draft.summary))
    grouped: dict[str, list[CheckedBullet]] = {}
    given_titles: dict[str, str] = {}
    for section in draft.sections:
        grouped.setdefault(section.section_id, []).extend(check_all(section.bullets))
        given_titles.setdefault(section.section_id, section.title)
    titles = {s.id: s.title for s in template.sections}
    order = [s.id for s in template.sections] + [sid for sid in grouped if sid not in titles]
    sections = tuple(
        CheckedSection(sid, titles.get(sid) or given_titles[sid], tuple(grouped[sid]))
        for sid in order
        if grouped.get(sid)
    )
    kept = len(summary) + sum(len(s.bullets) for s in sections)
    return CheckedNote(summary, sections, kept, sum(reasons.values()), dict(reasons))
