"""The window's note job as a pipeline (BUILD.md §7.3, D16): its stages, then the note."""

import json
from collections.abc import Sequence
from pathlib import Path

from evra.config import LlmSettings, Settings
from evra.notes.title import TITLE_TIMEOUT_S
from evra.paths import AppPaths
from evra.services.meetings import MeetingService
from evra.store.db import connect
from evra.store.meetings import MeetingStore
from evra.store.migrate import migrate
from tests.unit.notes.fakes import FakeProvider, title_reply
from tests.unit.notes.test_mapreduce import PART1, PART2, SAID, combined
from tests.unit.services.test_meeting_service import (
    NOTE,
    Events,
    FakeKit,
    make,
    wait_for_note_jobs,
)


def test_the_note_shows_each_stage_and_checks_meaning_with_the_embedding_model(
    tmp_path: Path,
) -> None:
    embedded_with: list[str] = []

    class Embeds(FakeProvider):
        def embed(self, model: str, texts: Sequence[str]) -> list[list[float]]:
            embedded_with.append(model)
            return super().embed(model, texts)

    said = {"text": "Some words were said.", "citations": ["u:1"]}
    unlike = {"text": "Speech came through clearly.", "citations": ["u:1"]}  # a meaning check
    note = json.dumps({"summary": [said, unlike], "sections": []})
    service, events, _, _ = make(tmp_path, provider=lambda s: Embeds([note, *NOTE[1:]]))
    mid = service.start("")["meeting_id"]
    events.wait_for("transcript.utterance")
    service.stop()
    events.wait_for("note.ready", meeting_id=mid)
    items = list(events.items)
    stages = [(i, p["stage"]) for i, (n, p) in enumerate(items) if n == "note.stage"]
    assert [stage for _, stage in stages] == ["writing", "items"]
    ready_at = next(i for i, (n, _) in enumerate(items) if n == "note.ready")
    assert stages[-1][0] < ready_at  # D16: every stage ends before the note appears
    assert embedded_with and set(embedded_with) == {"qwen3-embedding:0.6b"}


def test_a_long_call_shows_each_part_then_combining(tmp_path: Path) -> None:
    """A call longer than one pass is read in parts (A2), then combined (A3): the window says
    which part it is reading, and the note still appears once, after every stage."""
    paths = AppPaths.under(tmp_path)
    paths.ensure()
    conn = connect(paths.db_path)
    migrate(conn)
    store = MeetingStore(conn)
    mid = store.create_meeting(
        title="Recording 2026-11-27 10:00",
        mode="one_on_one",
        situation="call_headphones",
        template="one_on_one",
    )
    vid = store.create_transcript_version(mid, kind="live", model="fake")
    for k in range(90):  # 15 minutes, two parts
        store.add_utterance(
            version_id=vid,
            meeting_id=mid,
            channel=k % 2,
            start_ms=k * 10_000,
            end_ms=(k + 1) * 10_000,
            text=SAID.get(k, "Some small talk."),
        )
    store.finish_meeting(mid)
    conn.close()
    events = Events()
    titler = FakeProvider([title_reply("Atlas beta and the postmortem")])
    service = MeetingService(
        paths=paths,
        settings=Settings(llm=LlmSettings(single_pass_minutes=10)),
        emit=events,
        kit=FakeKit(paths),
        provider_factory=lambda s: (
            titler if s.timeout_s == TITLE_TIMEOUT_S else FakeProvider([PART1, PART2, combined()])
        ),
        level_interval_s=0.02,
    )
    try:
        assert service.write_note(mid) == {"ok": True}
        events.wait_for("note.ready", meeting_id=mid)
        wait_for_note_jobs()
        items = list(events.items)
        stages = [(i, p["stage"]) for i, (n, p) in enumerate(items) if n == "note.stage"]
        assert [stage for _, stage in stages] == ["writing", "part:1:2", "part:2:2", "combining"]
        ready_at = next(i for i, (n, _) in enumerate(items) if n == "note.ready")
        assert stages[-1][0] < ready_at
        renamed = [p for n, p in items if n == "meeting.renamed"]
        assert renamed == [{"meeting_id": mid, "title": "Atlas beta and the postmortem"}]
    finally:
        service.shutdown()
