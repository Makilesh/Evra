"""The window's note job as a pipeline (BUILD.md §7.3, D16): its stages, then the note."""

import json
from collections.abc import Sequence
from pathlib import Path

from tests.unit.notes.fakes import FakeProvider
from tests.unit.services.test_meeting_service import NOTE, make


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
