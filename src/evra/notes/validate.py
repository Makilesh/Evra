"""Mechanical grounding (BUILD.md §7.5), lexical part. A kept bullet cites utterances that exist,
shares at least 20% of its content words with them (5-letter prefixes, so "agreed" matches
"agree"), and every number and name in it appears in what it cites ("twelve thousand" counts
for 12,000, and so does "12k"). Conversation carries context across turns, so a name or number
said up to three lines from a cited line gets that line added as a citation. The embedding
check (cosine >= 0.55) joins in M5 with the embedding model."""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass

from evra.llm.schemas import NoteBullet, NoteDraft
from evra.notes.templates import Template

MIN_OVERLAP = 0.2
NEARBY = 3  # a name or number said up to 3 lines away is cited from there
_THOUSANDS = re.compile(r"(\d+(?:\.\d+)?)\s?[kK]\b")
_RSQUO = chr(0x2019)  # typographic apostrophe
CITATION_RE = re.compile(r"^(u:[\w-]+|user|n:[\w-]+|m:\d+|d:\d+|w:\d+|g)$")
_INLINE = re.compile(r"\s*\[((?:u:[\w-]+|user)(?:\s*,\s*(?:u:[\w-]+|user))*)\]")
_WORD = re.compile(rf"[A-Za-z0-9]+(?:['{_RSQUO}][A-Za-z]+)?")
_NUMBER = re.compile(r"\d+(?:[.,:]\d+)*")
_CAPITALISED = re.compile(r"\b[A-Z][A-Za-z]+\b")
_HARD_STOPS = ".!?"  # only these start a new sentence; after : ; ( - a capital is a name
_LEADING_LABEL = re.compile(r"^(?:[A-Za-z']+ ?){1,3}:\s+")  # "Owner: ", "Them: "
# How an unknown capitalised word at a sentence start reads as a name: alone ("Owner: Marcus.")
# or followed by what people do ("Marcus will ...", "Marcus's deck").
_NAME_FOLLOWERS = re.compile(
    r"^(?:'s\b|\s*(?:[.,;)]|$)|\s+(?:will|and|has|is|was|said|agreed|asked|from)\b)"
)
_AMBIGUOUS = {"one", "first", "second"}  # alone they are rarely numbers ("the one thing")
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


def _spoken_numbers(words: Sequence[str], *, lone_ambiguous: bool = True) -> set[str]:
    found: set[str] = set()
    total = current = 0
    run: list[str] = []
    for word in [*words, ""]:  # the empty sentinel flushes the last run
        if word in _VALUES:
            current += _VALUES[word]
            run.append(word)
        elif word in _SCALES and run:
            if word == "hundred":
                current *= 100
            else:
                total += current * _SCALES[word]
                current = 0
            run.append(word)
        elif word == "and" and run:
            continue
        else:
            if run and (lone_ambiguous or len(run) > 1 or run[0] not in _AMBIGUOUS):
                found.add(str(total + current))
            total = current = 0
            run = []
    return found


@dataclass(frozen=True)
class _Vocabulary:
    lower: frozenset[str]  # word forms the meeting uses in lowercase: ordinary words
    said: frozenset[str]  # every word form said in the meeting


def _vocabulary(texts: Iterable[str]) -> _Vocabulary:
    lower: set[str] = set()
    said: set[str] = set()
    for text in texts:
        for word in _WORD.findall(text):
            said.add(_base(word))
            if word[0].islower():
                lower.add(_base(word))
    return _Vocabulary(frozenset(lower), frozenset(said))


def _names(text: str, vocabulary: _Vocabulary) -> set[str]:
    """Capitalised words that must come from the transcript. At a sentence start a capital
    means nothing, so there a word counts only if the meeting never uses it in lowercase
    (a name it said, like "Priya") or it is unknown and reads like a name ("Marcus will")."""
    label = _LEADING_LABEL.match(text)
    found: set[str] = set()
    for match in _CAPITALISED.finditer(text):
        word = match.group(0).lower()
        if word in STOPWORDS or word in _NOT_NAMES:
            continue
        before = text[: match.start()].rstrip()
        at_start = not before or before[-1] in _HARD_STOPS
        at_start = at_start or (label is not None and match.start() == label.end())
        if at_start and (
            word in vocabulary.lower
            or (word not in vocabulary.said and not _NAME_FOLLOWERS.match(text[match.end() :]))
        ):
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
    vocabulary: _Vocabulary,
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
    have_numbers, have_names = _facts(source)
    missing_numbers = _claim_numbers(text) - have_numbers
    missing_names = _names(text, vocabulary) - have_names
    contexts = _number_contexts(text)
    for extra in _nearby(cited, aliases, utterance_text):
        if not missing_numbers and not missing_names:
            break
        line = utterance_text[extra]
        numbers, names = _facts(line, lone_ambiguous=False)
        keys = {_key(w) for w in _WORD.findall(line)}
        # a number counts only from a line about the same thing ("October 14", not "180 ms")
        found_numbers = {n for n in missing_numbers & numbers if contexts.get(n, set()) & keys}
        found_names = missing_names & names
        if found_numbers or found_names:
            cited.append(extra)  # the detail was said there: cite it too
            missing_numbers -= found_numbers
            missing_names -= found_names
    if missing_numbers:
        return None, "number_not_cited"
    if missing_names:
        return None, "name_not_cited"
    return CheckedBullet(text, tuple(cited)), ""


def _expand_thousands(text: str) -> str:
    def expand(match: re.Match[str]) -> str:
        value = float(match.group(1)) * 1000
        return str(int(value)) if value.is_integer() else str(value)

    return _THOUSANDS.sub(expand, text)


def _claim_numbers(text: str) -> set[str]:
    numbers = {_norm_number(n) for n in _NUMBER.findall(_expand_thousands(text))}
    words = [w.lower() for w in _WORD.findall(text)]
    return numbers | _spoken_numbers(words, lone_ambiguous=False)


def _is_content(word: str) -> bool:
    return not word.isdigit() and len(word) > 1 and _base(word) not in STOPWORDS


def _number_contexts(text: str) -> dict[str, set[str]]:
    """For each written number in a claim, the content words right before and after it."""
    expanded = _expand_thousands(text)
    contexts: dict[str, set[str]] = {}
    for match in _NUMBER.finditer(expanded):
        before = [w for w in _WORD.findall(expanded[: match.start()]) if _is_content(w)]
        after = [w for w in _WORD.findall(expanded[match.end() :]) if _is_content(w)]
        keys = {_key(w) for w in before[-1:] + after[:1]}
        contexts.setdefault(_norm_number(match.group(0)), set()).update(keys)
    return contexts


def _facts(source: str, *, lone_ambiguous: bool = True) -> tuple[set[str], set[str]]:
    """Numbers (written or spoken) and word forms in a piece of transcript."""
    words = _WORD.findall(source)
    numbers = {_norm_number(n) for n in _NUMBER.findall(source)}
    numbers |= _spoken_numbers([w.lower() for w in words], lone_ambiguous=lone_ambiguous)
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
    vocabulary = _vocabulary([*utterance_text.values(), user_notes])

    def check_all(bullets: Sequence[NoteBullet]) -> list[CheckedBullet]:
        kept: list[CheckedBullet] = []
        for bullet in bullets:
            checked, reason = _check(bullet, aliases, utterance_text, user_notes, vocabulary)
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
