import json
from pathlib import Path

from app.cli.analyze_calls import aggregate, build_draft, transcript_text

V1 = json.loads((Path(__file__).parents[1] / "scripts" / "v1.json").read_text())


def test_transcript_text_handles_shapes():
    assert (
        transcript_text([{"transcript": "hi", "mediaChannel": 1}, {"text": "yo"}])
        == "[1] hi\nyo"
    )
    assert transcript_text({"transcriptions": [{"sentence": "a"}]}) == "a"
    assert transcript_text({}) == ""


def test_aggregate_counts():
    e = {
        "outcome": "booked",
        "analysis": {
            "objections": [
                {
                    "type": "Timing",
                    "landed": True,
                    "prospect_said": "x",
                    "rep_reply": "y",
                }
            ],
            "good_phrases": ["p"],
            "drop_off": "",
        },
    }
    a = aggregate([e, e])
    assert a["objections"][0]["count"] == 2 and a["outcomes"] == {"booked": 2}


def test_build_draft_applies_safe_changes_only():
    synth = {
        "new_responses": [
            {
                "section_id": "opener",
                "label": "Already have agency",
                "text": "Fair. What are they not covering?",
            },
            {
                "section_id": "opener",
                "label": "Bad",
                "text": "We guarantee 30% more patients",
            },
            {"section_id": "nope", "label": "X", "text": "y"},
        ],
        "faq_items": [{"q": "Contract?", "a": "Month to month."}],
        "flows": {
            "r-looking": {
                "ask": "How many a month?",
                "options": [
                    {
                        "id": "a",
                        "label": "Under 10",
                        "say": "Doable.",
                        "next": {
                            "options": [
                                {"id": "b", "label": "HRT", "say": "Strong area."}
                            ]
                        },
                    },
                    {"id": "c", "label": "Bad", "say": "We guarantee results"},
                ],
            },
            "r-new-4-1": {"options": [{"id": "n", "label": "Today", "say": "Great."}]},
            "ghost": {"options": [{"id": "z", "label": "x", "say": "y"}]},
        },
    }
    draft, notes = build_draft(V1, synth)
    assert draft["version"] == V1["version"] + 1
    opener = next(s for s in draft["sections"] if s["id"] == "opener")
    labels = [b.get("label") for b in opener["blocks"]]
    assert "Already have agency" in labels and "Bad" not in labels
    assert labels.index("Already have agency") > labels.index("Not interested – firm")
    assert list(draft["flows"]) == ["r-looking", "r-new-4-1"]
    node = draft["flows"]["r-looking"]
    assert [o["id"] for o in node["options"]] == ["a"]
    assert node["options"][0]["next"]["options"][0]["id"] == "b"
    assert len(notes) == 3
    assert "followups" not in draft
    assert V1["version"] == 3 and "flows" not in V1  # input untouched


def test_draft_file_is_never_served(tmp_path, monkeypatch):
    from app.api.v1 import ext

    (tmp_path / "v1.json").write_text('{"version": 1, "sections": []}')
    (tmp_path / "v9.draft.json").write_text('{"version": 9, "sections": []}')
    monkeypatch.setattr(ext, "_SCRIPTS", tmp_path)
    assert ext._load_script()["version"] == 1


def test_placeholder_transcript_is_empty_and_screening_skipped():
    assert transcript_text([{"transcript": "No transcript found"}]) == ""
    scr = {
        "outcome": "unknown",
        "analysis": {
            "conversation_type": "voicemail_or_screening",
            "objections": [{"type": "x"}],
        },
    }
    a = aggregate([scr])
    assert a["objections"] == [] and a["conversation_types"] == {
        "voicemail_or_screening": 1
    }
