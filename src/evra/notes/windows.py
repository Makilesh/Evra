"""A long call in parts (BUILD.md §7.4, spec §4.6): windows of about 10 minutes cut at speaker
turns, each starting about a minute before the last one ended; a tail of under 3 minutes joins
the last window. And the choice between writing a note in one pass and in parts."""

from __future__ import annotations

from bisect import bisect_left
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

from evra.config import LlmSettings
from evra.notes.writer import prompt_limit
from evra.store.meetings import Utterance

WINDOW_MS, OVERLAP_MS, MIN_TAIL_MS = 600_000, 60_000, 180_000
MINUTE_MS = 60_000

NotePath = Literal["single", "windows"]


@dataclass(frozen=True)
class Window:
    index: int  # 1, 2, ... in time order
    start_ms: int  # when its first line starts
    end_ms: int  # when the last of its lines ends
    ids: tuple[str, ...]  # its lines, in time order


def _turn_end(ordered: Sequence[Utterance], i: int, before_ms: int) -> int:
    """The last line of the speaker turn that line i is in, among the lines that start before
    `before_ms`."""
    while (
        i + 1 < len(ordered)
        and ordered[i + 1].channel == ordered[i].channel
        and ordered[i + 1].start_ms < before_ms
    ):
        i += 1
    return i


def _turn_start(ordered: Sequence[Utterance], i: int, floor: int) -> int:
    """The first line of the speaker turn that line i is in, no earlier than line `floor`."""
    while i > floor and ordered[i - 1].channel == ordered[i].channel:
        i -= 1
    return i


def _window(index: int, lines: Sequence[Utterance]) -> Window:
    return Window(
        index, lines[0].start_ms, max(u.end_ms for u in lines), tuple(u.id for u in lines)
    )


def _span_ms(lines: Sequence[Utterance]) -> int:
    return max(u.end_ms for u in lines) - lines[0].start_ms


def _part_end(ordered: Sequence[Utterance], starts: Sequence[int], first: int) -> int:
    """The last line of a part that starts at line `first`: the last line that starts within 10
    minutes of it, then the rest of that line's turn that starts within 13."""
    start_ms = ordered[first].start_ms
    mark = bisect_left(starts, start_ms + WINDOW_MS) - 1
    return _turn_end(ordered, mark, start_ms + WINDOW_MS + MIN_TAIL_MS)


def split_windows(utterances: Sequence[Utterance]) -> list[Window]:
    """Every line lands in at least one window, and every window adds a line. A call of one
    window plus a short tail is one window. A turn is cut 13 minutes after a window's first
    line, and the next window moves back at most 2 minutes, so a call with no change of speaker
    splits by time (RB47). After a silence longer than a window's reach, the next window starts
    at the first line after it (RB51)."""
    ordered = sorted(utterances, key=lambda u: (u.start_ms, u.seq))
    if not ordered:
        return []
    if _span_ms(ordered) <= WINDOW_MS + MIN_TAIL_MS:
        return [_window(1, ordered)]
    starts = [u.start_ms for u in ordered]
    windows: list[Window] = []
    first, previous_last = 0, -1
    while True:
        last = _part_end(ordered, starts, first)
        if last <= previous_last:  # nothing new is said within its reach: start after the silence
            first = previous_last + 1
            last = _part_end(ordered, starts, first)
        rest = ordered[last + 1 :]
        if not rest or _span_ms(rest) < MIN_TAIL_MS:  # a short tail joins this window
            windows.append(_window(len(windows) + 1, ordered[first:]))
            return windows
        window = _window(len(windows) + 1, ordered[first : last + 1])
        windows.append(window)
        previous_last = last
        # the next starts at the first line from a minute before this one ends (never after the
        # first line it leaves out), moved back to the start of that line's turn but not past
        # two minutes before the end, and always later than this window's first line
        overlap = min(bisect_left(starts, window.end_ms - OVERLAP_MS), last + 1)
        floor = min(bisect_left(starts, window.end_ms - 2 * OVERLAP_MS), overlap)
        first = max(_turn_start(ordered, overlap, floor), first + 1)


def choose_path(
    *, utterances: Sequence[Utterance], prompt_tokens: int, settings: LlmSettings
) -> NotePath:
    """Parts when the call is longer than `single_pass_minutes` or its one-pass prompt (A1's
    estimate, `prompt_tokens`) would not fit the budget; one pass otherwise."""
    length_ms = max((u.end_ms for u in utterances), default=0)
    if length_ms > settings.single_pass_minutes * MINUTE_MS:
        return "windows"
    return "windows" if prompt_tokens > prompt_limit(settings) else "single"
