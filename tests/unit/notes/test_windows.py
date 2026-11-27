"""Cutting a long call into parts (BUILD.md §7.4, spec §4.6): about 10 minutes each, at speaker
turns, with about 60 s of overlap; a short tail joins the last part."""

from itertools import pairwise

from evra.config import LlmSettings
from evra.notes.windows import (
    MIN_TAIL_MS,
    OVERLAP_MS,
    WINDOW_MS,
    Window,
    choose_path,
    split_windows,
)
from evra.store.meetings import Utterance
from tests.unit.notes.fakes import utt

STEP_MS = 10_000  # every line lasts 10 s and the next one starts as it ends


def call(lines: int, turn: int) -> list[Utterance]:
    """`lines` lines of 10 s; the speaker changes every `turn` lines."""
    return [
        utt(f"k{k}", (k // turn) % 2, k * STEP_MS, (k + 1) * STEP_MS, f"line {k}", seq=k)
        for k in range(lines)
    ]


def ids(first: int, last: int) -> tuple[str, ...]:
    return tuple(f"k{k}" for k in range(first, last + 1))


def test_the_part_sizes() -> None:
    assert (WINDOW_MS, OVERLAP_MS, MIN_TAIL_MS) == (600_000, 60_000, 180_000)


def test_short_call_is_one_window() -> None:
    lines = call(78, turn=1)  # 13 minutes: one part plus a short tail
    assert split_windows(list(reversed(lines))) == [Window(1, 0, 780_000, ids(0, 77))]
    assert split_windows([]) == []


def test_windows_overlap_at_turns() -> None:
    """A part ends with its speaker's turn and the next starts at a turn about 60 s earlier.
    Turns of 7 lines (70 s): the 10-minute mark falls inside lines 56-62, so the first part
    runs to line 62 (10:30); the next starts at the turn holding 09:30 (line 57), at line 56."""
    windows = split_windows(call(150, turn=7))  # 25 minutes
    assert windows == [
        Window(1, 0, 630_000, ids(0, 62)),
        Window(2, 560_000, 1_190_000, ids(56, 118)),
        Window(3, 1_120_000, 1_500_000, ids(112, 149)),
    ]


def test_windows_cover_every_line() -> None:
    for turn in (1, 2, 3, 7, 30):
        lines = call(360, turn=turn)  # an hour
        windows = split_windows(lines)
        assert [w.index for w in windows] == list(range(1, len(windows) + 1))
        covered = [uid for w in windows for uid in w.ids]
        assert set(covered) == {u.id for u in lines}, turn
        firsts = [int(w.ids[0][1:]) for w in windows]
        assert firsts == sorted(set(firsts))  # each part starts later than the one before
        for before, after in pairwise(windows):
            assert after.start_ms < before.end_ms  # they overlap
        for window, first in zip(windows, firsts, strict=True):  # lines in order, no gaps
            assert window.ids == ids(first, first + len(window.ids) - 1)


def test_short_tail_joins_last_window() -> None:
    """After the second part (to 19:50) under 3 minutes are left: that part takes them."""
    windows = split_windows(call(135, turn=7))  # 22:30
    assert windows == [
        Window(1, 0, 630_000, ids(0, 62)),
        Window(2, 560_000, 1_350_000, ids(56, 134)),
    ]


def test_a_call_on_one_channel_splits_by_time() -> None:
    """RB47: with no change of speaker, a part's turn stops 13 minutes after its first line and
    the next part starts at most 2 minutes before the last one ended: parts of at most 16
    minutes (with a short tail), overlapping by at most 2, covering every line."""
    lines = call(240, turn=1_000)  # 40 minutes, all on one channel
    windows = split_windows(lines)
    assert {uid for w in windows for uid in w.ids} == {u.id for u in lines}
    assert all(w.end_ms - w.start_ms <= 16 * 60_000 for w in windows)
    for before, after in pairwise(windows):
        assert 0 < before.end_ms - after.start_ms <= 2 * OVERLAP_MS
    assert windows == [
        Window(1, 0, 780_000, ids(0, 77)),
        Window(2, 660_000, 1_440_000, ids(66, 143)),
        Window(3, 1_320_000, 2_100_000, ids(132, 209)),
        Window(4, 1_980_000, 2_400_000, ids(198, 239)),
    ]


def test_a_long_turn_is_cut_and_the_overlap_stays_short() -> None:
    """A 5-minute turn across the 10-minute mark (08:50-14:00): the part stops at 13 minutes,
    and the next starts 2 minutes before that, not back at the start of the turn."""
    lines = [
        utt(f"k{k}", 1 if 54 <= k < 84 else k % 2, k * STEP_MS, (k + 1) * STEP_MS, "x", seq=k)
        for k in range(150)
    ]
    first, second = split_windows(lines)[:2]
    assert (first.ids[-1], first.end_ms) == ("k77", 780_000)
    assert second.ids[0] == "k66" and second.start_ms == 660_000


def test_choose_path() -> None:
    settings = LlmSettings(single_pass_minutes=30)
    limit = min(settings.context_budget, settings.num_ctx - settings.max_output_tokens)

    def path(minutes: float, tokens: int = 1_000) -> str:
        lines = [utt("a", 0, 0, round(minutes * 60_000), "words")]
        return choose_path(utterances=lines, prompt_tokens=tokens, settings=settings)

    assert path(29) == "single"
    assert path(30) == "single"  # not longer than 30 minutes
    assert path(30.5) == "windows"
    assert path(10, tokens=limit) == "single"
    assert path(10, tokens=limit + 1) == "windows"  # it would not fit one prompt
    room = LlmSettings(num_ctx=8192, max_output_tokens=4096, context_budget=28000)
    lines = [utt("a", 0, 0, 60_000, "words")]
    assert choose_path(utterances=lines, prompt_tokens=4097, settings=room) == "windows"
