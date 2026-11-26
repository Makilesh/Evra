import json
import random

from evra.config import LlmSettings
from tests.unit.notes.fakes import FakeProvider, utt
from tools.bakeoff_notes import FIXTURES, load_case
from tools.calibrate_semantic import (
    calibrate,
    far_lines,
    percentile,
    pick_threshold,
    share_at_or_above,
)

SHORT = FIXTURES / "one_on_one_synthetic.json"


def test_far_lines_skip_cited_and_nearby_lines() -> None:
    lines = [utt(f"l{i}", 0, i * 1000, i * 1000 + 900, f"line {i}", seq=i) for i in range(21)]
    picked = far_lines(lines, {"l10"}, random.Random(7), count=3)
    assert len(picked) == 3 and len(set(picked)) == 3
    assert not {f"line {i}" for i in range(7, 14)} & set(picked)
    assert picked == far_lines(lines, {"l10"}, random.Random(7), count=3)  # seeded
    assert far_lines(lines[:5], {"l2"}, random.Random(7), count=3) == []  # nothing far enough


def test_percentile_share_and_the_threshold_rule() -> None:
    assert percentile([0.1, 0.2, 0.3, 0.4, 0.5], 0.5) == 0.3
    assert percentile([0.1, 0.5], 0.95) == 0.48
    assert percentile([0.7], 0.05) == 0.7
    assert share_at_or_above([0.5, 0.6, 0.7, 0.8], 0.6) == 0.75
    # the smallest of 0.55 ... 0.75 at which at most 2% of mismatched pairs pass
    mismatched = [0.3] * 97 + [0.56, 0.61, 0.66]
    assert pick_threshold(mismatched) == 0.6  # 2 of 100 at or above 0.60, 3 at 0.55
    assert pick_threshold([0.9] * 10) is None


def test_calibrate_reports_every_group_with_a_fake_model() -> None:
    reply = json.dumps(
        {
            "summary": [{"text": "The launch moves to October 14.", "citations": ["u:9"]}],
            "sections": [
                {
                    "section_id": "discussion",
                    "title": "Discussion",
                    "bullets": [
                        {"text": "Everyone loved the cake at lunch.", "citations": ["u:2"]},
                        {"text": "Latency spiked.", "citations": ["u:99"]},
                    ],
                }
            ],
        }
    )
    provider = FakeProvider([reply])
    lines = calibrate(provider, "fake:1b", [load_case(SHORT)], LlmSettings())
    text = "\n".join(lines)
    assert "| supported | 1 |" in text
    assert "| mismatched | 3 |" in text
    assert "| unsupported | 1 |" in text
    assert "1 points kept, 1 unsupported, 1 other" in text
    # every candidate threshold, and two below them for reference (never the rule's pick)
    assert [line.split(" |")[0] for line in lines if line.startswith("| 0.")] == [
        "| 0.45 (not a candidate)",
        "| 0.50 (not a candidate)",
        "| 0.55",
        "| 0.60",
        "| 0.65",
        "| 0.70",
        "| 0.75",
    ]
    assert "Everyone loved the cake at lunch." in text  # an unsupported point is listed
    assert "I finished the search migration on Tuesday" in text  # with the line it cites
    assert len(provider.embed_calls) == 1  # every pair in one batch
