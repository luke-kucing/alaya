"""Self-check for the LongMemEval eval harness's scoring (#173)."""
from tests.eval.longmemeval.run import (
    note_name,
    recalled_sessions,
    sample,
    score,
    summarize,
)


def test_recalled_sessions_read_from_recall_headers() -> None:
    out = (
        "## Recall: q\n\n### [[Session a]] — `sessions/a_1.md` (score 0.90)\n\ntext\n\n"
        "### [[Other]] — `ideas/x.md` (score 0.50)\n\n### [[Session b]] — `sessions/b.md` (score 0.40)"
    )
    assert recalled_sessions(out) == ["a_1", "b"]


def test_score_any_and_all() -> None:
    assert score(["a", "b"], ["a", "c"]) == {"recall_any": True, "recall_all": False, "returned": 2}
    assert score(["a", "c"], ["a", "c"])["recall_all"] is True
    assert score([], ["a"])["recall_any"] is False


def test_note_name_is_one_safe_segment() -> None:
    assert note_name("answer/4be1 b6:2") == "answer_4be1_b6_2"


def test_sample_drops_abstention_and_caps_per_type() -> None:
    entries = [
        {"question_id": f"q{i}", "question_type": t, "answer_session_ids": ["s"]}
        for i, t in enumerate(["temporal"] * 5 + ["multi"] * 2)
    ] + [{"question_id": "q9_abs", "question_type": "temporal", "answer_session_ids": []}]
    picked = sample(entries, per_type=3, seed=0)
    assert sorted(e["question_type"] for e in picked) == ["multi"] * 2 + ["temporal"] * 3
    assert all(not e["question_id"].endswith("_abs") for e in picked)
    assert len(sample(entries, None, 0)) == 7


def test_summarize_groups_overall_and_by_type() -> None:
    rows = [
        {"variant": "base", "budget": 1000, "question_type": "t", "recall_any": True, "recall_all": False, "returned": 2},
        {"variant": "base", "budget": 1000, "question_type": "u", "recall_any": False, "recall_all": False, "returned": 4},
    ]
    s = summarize(rows)["rows"]
    assert s[0] == {"variant": "base", "budget": 1000, "question_type": "all", "n": 2,
                    "recall_any": 0.5, "recall_all": 0.0, "avg_returned": 3.0}
    assert [r["question_type"] for r in s] == ["all", "t", "u"]
