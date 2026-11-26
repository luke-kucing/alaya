"""LongMemEval retrieval eval for memory_recall (#173). Opt-in: ``make eval``.

For each question, its haystack sessions become notes in a fresh vault, the
vault is indexed, and ``memory_recall(question, budget_tokens=N)`` is scored
on whether the gold evidence sessions are among the notes it returned:

- recall_any: at least one evidence session returned
- recall_all: every evidence session returned

No LLM or API key is needed. Abstention questions (``*_abs``) have no
evidence sessions and are skipped. Full output goes to a log file; only the
summary is printed.

    uv run python -m tests.eval.longmemeval.run --per-type 5 --budgets 1000,2000,4000

Each question needs a fresh vault and index, so indexing (CPU embedding, which
already uses most cores) dominates: the full 470 questions take about 3.5 h.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import logging
import random
import re
import statistics
import subprocess
import sys
import tempfile
import time
from collections import defaultdict
from datetime import date
from functools import lru_cache, partial
from pathlib import Path
from unittest.mock import patch

HERE = Path(__file__).parent
DATA = HERE / "data" / "longmemeval_s_cleaned.json"
RESULTS = HERE.parent / "results"
logger = logging.getLogger("longmemeval")
# Pipeline stages memory_recall can toggle; each is keyless (template HyDE,
# local cross-encoder). memory_recall has no graph expansion to toggle.
# "threshold" overrides corrective.filter_relevant's cutoff (#190: the 0.2 default drops gold hits).
VARIANTS = {"base": {}, "hyde": {"hyde": True}, "rerank": {"rerank": True}, "base-t0": {"threshold": 0.0}}

_RECALLED_RE = re.compile(r"`sessions/([^`]+)\.md`")


def note_name(session_id: str) -> str:
    return re.sub(r"[^\w-]", "_", session_id)


def session_note(session_id: str, when: str, turns: list[dict]) -> str:
    lines = ["---", f"title: Session {session_id}", f"date: {json.dumps(when)}", "---", "",
             f"# Session {session_id} ({when})", ""]
    for t in turns:
        lines += [f"**{t['role']}:** {t['content']}", ""]
    return "\n".join(lines)


def recalled_sessions(output: str) -> list[str]:
    """Note names memory_recall returned, in order."""
    return _RECALLED_RE.findall(output)


def score(recalled: list[str], gold: list[str]) -> dict:
    got = set(recalled) & set(gold)
    return {"recall_any": bool(got), "recall_all": got == set(gold), "returned": len(set(recalled))}


def sample(entries: list[dict], per_type: int | None, seed: int) -> list[dict]:
    """Up to *per_type* questions of each type (all when None), abstention excluded."""
    by_type: dict[str, list[dict]] = defaultdict(list)
    for e in entries:
        if not e["question_id"].endswith("_abs") and e["answer_session_ids"]:
            by_type[e["question_type"]].append(e)
    rng = random.Random(seed)
    out = []
    for qtype in sorted(by_type):
        group = by_type[qtype]
        out += group if per_type is None or per_type >= len(group) else rng.sample(group, per_type)
    return out


def ranked_recall(ranked: list[str], gold: list[str], k: int) -> dict:
    """Session-level recall of the top-k ranked sessions, budget-independent."""
    return score(ranked[:k], gold)


def summarize(rows: list[dict], retrieval: list[dict] | None = None, questions: list[dict] | None = None) -> dict:
    """Mean recall per (variant, budget), overall and per question type, plus cost and ranked recall."""
    groups: dict[tuple, list[dict]] = defaultdict(list)
    for r in rows:
        groups[(r["variant"], r["budget"], "all")].append(r)
        groups[(r["variant"], r["budget"], r["question_type"])].append(r)
    out = []
    for (variant, budget, qtype), rs in sorted(groups.items(), key=lambda kv: (kv[0][0], kv[0][1], kv[0][2] != "all", kv[0][2])):
        n = len(rs)
        out.append({
            "variant": variant, "budget": budget, "question_type": qtype, "n": n,
            "recall_any": round(sum(r["recall_any"] for r in rs) / n, 3),
            "recall_all": round(sum(r["recall_all"] for r in rs) / n, 3),
            "avg_returned": round(sum(r["returned"] for r in rs) / n, 1),
            "avg_context_tokens": round(sum(r.get("context_tokens", 0) for r in rs) / n),
        })
    ranked_rows = []
    by_variant: dict[str, list[dict]] = defaultdict(list)
    for r in retrieval or []:
        by_variant[r["variant"]].append(r)
    for variant, rs in sorted(by_variant.items()):
        n = len(rs)
        row = {"variant": variant, "n": n,
               "median_query_ms": round(statistics.median(r["query_ms"] for r in rs), 1),
               "p95_query_ms": round(sorted(r["query_ms"] for r in rs)[int(0.95 * (n - 1))], 1)}
        for k in (5, 10):
            for key in ("recall_any", "recall_all"):
                row[f"{key}@{k}"] = round(sum(ranked_recall(r["ranked"], r["gold"], k)[key] for r in rs) / n, 3)
        ranked_rows.append(row)
    cost = {}
    if questions:
        nq = len(questions)
        cost = {"mean_haystack_tokens": round(sum(q["haystack_tokens"] for q in questions) / nq),
                "mean_index_seconds": round(sum(q["index_seconds"] for q in questions) / nq, 1),
                "mean_chunks": round(sum(q["chunks"] for q in questions) / nq)}
    return {"rows": out, "ranked": ranked_rows, "cost": cost}


def markdown(summary: dict, meta: dict) -> str:
    lines = [
        f"# LongMemEval-S retrieval — {meta['date']} @ {meta['git_sha']}",
        "",
        (f"{meta['questions']} questions ({meta['per_type'] or 'all'} per type, seed {meta['seed']}), "
         f"embedder `{meta['embedder']}`, {meta['minutes']} min."),
        "",
    ]
    cost = summary.get("cost") or {}
    if cost:
        lines += [(f"Per question: {cost['mean_haystack_tokens']} haystack tokens, {cost['mean_chunks']} chunks, "
                   f"indexed in {cost['mean_index_seconds']} s."), ""]
    if summary.get("ranked"):
        lines += ["| variant | recall_any@5 | recall_all@5 | recall_any@10 | recall_all@10 | median query ms | p95 query ms |",
                  "|---|---|---|---|---|---|---|"]
        for r in summary["ranked"]:
            lines.append(f"| {r['variant']} | {r['recall_any@5']:.3f} | {r['recall_all@5']:.3f} | "
                         f"{r['recall_any@10']:.3f} | {r['recall_all@10']:.3f} | {r['median_query_ms']} | {r['p95_query_ms']} |")
        lines.append("")
    lines += [
        "| variant | budget | question type | n | recall_any | recall_all | sessions returned | context tokens |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for r in summary["rows"]:
        lines.append(
            f"| {r['variant']} | {r['budget']} | {r['question_type']} | {r['n']} | "
            f"{r['recall_any']:.3f} | {r['recall_all']:.3f} | {r['avg_returned']} | {r.get('avg_context_tokens', '')} |"
        )
    return "\n".join(lines) + "\n"


def run_question(entry: dict, budgets: list[int], variants: dict[str, dict]) -> tuple[list[dict], list[dict], dict]:
    """Rows per (variant, budget), ranked retrieval per variant, and per-question cost."""
    from alaya.index import corrective as corrective_mod
    from alaya.index.reindex import reindex_all
    from alaya.index.store import get_store, reset_store
    from alaya.tokens import count_tokens
    from alaya.tools import memory, search
    from alaya.tools.memory import memory_recall

    gold = [note_name(s) for s in entry["answer_session_ids"]]
    rows, retrieval = [], []
    with tempfile.TemporaryDirectory(prefix="alaya-lme-") as tmp:
        vault = Path(tmp)
        (vault / "sessions").mkdir()
        haystack_tokens = 0
        for sid, when, turns in zip(entry["haystack_session_ids"], entry["haystack_dates"],
                                    entry["haystack_sessions"]):
            text = session_note(sid, when, turns)
            haystack_tokens += count_tokens(text)
            (vault / "sessions" / f"{note_name(sid)}.md").write_text(text)
        t0 = time.monotonic()
        indexed = reindex_all(vault, get_store(vault))
        cost = {"question_id": entry["question_id"], "haystack_tokens": haystack_tokens,
                "index_seconds": round(time.monotonic() - t0, 2), "chunks": indexed.chunks_created}
        corrective = search._run_corrective_search
        relevant = corrective_mod.filter_relevant
        for variant, opts in variants.items():
            opts = dict(opts)
            threshold = opts.pop("threshold", None)
            filt = relevant if threshold is None else partial(relevant, threshold=threshold)
            # Budgets only change how the same hits are trimmed: search once per variant.
            cached = lru_cache(maxsize=None)(memory.get_memory_context)
            seen: dict = {}

            def fetch_once(*a, cached=cached, seen=seen, **kw):
                t = time.perf_counter()
                hits = cached(*a, **kw)
                seen.setdefault("ms", (time.perf_counter() - t) * 1000)  # first call is the real search
                seen["hits"] = hits
                return hits

            with patch.object(search, "_run_corrective_search", partial(corrective, **opts)), \
                 patch.object(corrective_mod, "filter_relevant", filt), \
                 patch.object(memory, "get_memory_context", fetch_once):
                for budget in budgets:
                    out = memory_recall(entry["question"], vault, budget_tokens=budget)
                    rows.append({
                        "question_id": entry["question_id"],
                        "question_type": entry["question_type"],
                        "variant": variant, "budget": budget,
                        **score(recalled_sessions(out), gold),
                        "context_tokens": count_tokens(out),
                    })
            ranked = list(dict.fromkeys(Path(h["path"]).stem for h in seen.get("hits") or []))[:20]
            retrieval.append({"question_id": entry["question_id"], "question_type": entry["question_type"],
                              "variant": variant, "gold": gold, "ranked": ranked,
                              "query_ms": round(seen.get("ms", 0.0), 1)})
        reset_store()  # drop this vault's LanceDB handle before the next
    return rows, retrieval, cost


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--data", type=Path, default=DATA)
    p.add_argument("--per-type", type=int, default=None, help="questions per type (default: all)")
    p.add_argument("--budgets", default="1000,2000,4000")
    p.add_argument("--variants", default=",".join(VARIANTS))
    p.add_argument("--seed", type=int, default=0)
    args = p.parse_args(argv)

    if not args.data.exists():
        print(f"No data at {args.data}. Run `make eval-data` first.", file=sys.stderr)
        return 2
    budgets = [int(b) for b in args.budgets.split(",")]
    variants = {v: VARIANTS[v] for v in args.variants.split(",")}
    if "rerank" in variants and importlib.util.find_spec("sentence_transformers") is None:
        # Without the extra, rerank silently falls back to base and measures nothing.
        print("Skipping rerank: install the `rerank` extra (uv sync --extra rerank).", file=sys.stderr)
        del variants["rerank"]

    sha = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, check=False).stdout.strip() or "nogit"
    stem = RESULTS / f"{date.today().isoformat()}-{sha}"
    RESULTS.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(filename=f"{stem}.log", level=logging.INFO, force=True,
                        format="%(asctime)s %(name)s %(levelname)s %(message)s")

    questions = sample(json.loads(args.data.read_text()), args.per_type, args.seed)
    start = time.monotonic()
    rows, retrieval, costs = [], [], []
    for i, entry in enumerate(questions, 1):
        logger.info("question %d/%d %s", i, len(questions), entry["question_id"])
        r, ret, cost = run_question(entry, budgets, variants)
        rows += r
        retrieval += ret
        costs.append(cost)

    from alaya.index.models import get_active_model
    meta = {
        "date": date.today().isoformat(), "git_sha": sha, "questions": len(questions),
        "per_type": args.per_type, "seed": args.seed, "budgets": budgets,
        "variants": list(variants), "embedder": get_active_model().key,
        "minutes": round((time.monotonic() - start) / 60, 1),
    }
    summary = summarize(rows, retrieval, costs)
    Path(f"{stem}.json").write_text(json.dumps(
        {"meta": meta, "summary": summary, "rows": rows, "retrieval": retrieval, "questions": costs}, indent=1))
    text = markdown(summary, meta)
    Path(f"{stem}.md").write_text(text)
    print(text)
    print(f"Results: {stem}.json, log: {stem}.log")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
