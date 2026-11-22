"""Save one run's LangSmith trace, and what it cost, to a local folder.

    python tools/record_run.py <session_id>            find the run by its session id
    python tools/record_run.py --last                  the most recent root run
    python tools/record_run.py --last --wait 600       wait until LangSmith has all of it
    python tools/record_run.py <sid> --note "po08 after lever 2" --transcript logs/live_po08_x.log

WHY A LOCAL COPY

LangSmith keeps a base trace for 14 days, then deletes it. On 2026-11-10 the
project `testing` still listed its last run (2026-10-17) but returned no runs:
every trace this project ever paid for was already gone. A cost number in a doc
can be checked against nothing. So every paid run gets recorded here, the day it
runs, with the exact trace it came from.

WHAT IT WRITES  runs/<YYYYmmdd-HHMM>_<label>_<trace8>/

  trace.jsonl.gz   every run in the trace, every field the SDK returns
                   (inputs, outputs, usage, metadata, errors, timings). Enough to
                   re-derive any number below, or to read a prompt again later.
  calls.csv        one row per model call: when, how long, agent, model,
                   input / cache-read / output / reasoning tokens, our $ estimate,
                   LangSmith's own $ when it has one, prompt size in characters.
  steps.csv        one row per `call_*` pipeline step: start offset and duration.
  tools.csv        how often each tool ran and how often it errored.
  summary.json     the totals, by agent and by token kind; wall clock; counts.
  report.txt       trace_cost.py's cost and latency tables for this trace.
  meta.json        git commit and branch (and whether the tree was dirty), the
                   prices used, the project, the trace URL, the note.
  preview/         static/preview/preview_<sid>.{html,css,js}, when they exist.
  transcript.log   the live runner's log, when --transcript names one.

and appends one line to runs/index.csv, the cost and time trend across runs.
The folders are gitignored (they hold full prompts and are large); index.csv is
committed, so the trend survives with the code that produced it.

Read-only against LangSmith and the model. Spends no OpenAI credits.
"""
from __future__ import annotations

import argparse
import contextlib
import csv
import datetime as dt
import gzip
import io
import json
import os
import pathlib
import shutil
import subprocess
import sys
import time
from collections import Counter, defaultdict

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import trace_cost as tc  # noqa: E402  same prices, same usage parsing, one place

RUNS_DIR = ROOT / "runs"
INDEX_COLUMNS = ["recorded", "run_start", "label", "session_id", "trace_id", "commit",
                 "dirty", "wall_s", "model_calls", "input_tok", "cache_tok",
                 "output_tok", "reasoning_tok", "cost_usd", "langsmith_cost_usd",
                 "tool_errors", "note", "folder"]


# ---------------------------------------------------------------- pure helpers
def cost_of(u):
    """$ for one (input, cache_read, output, reasoning) tuple, at trace_cost's prices."""
    i, c, o, _ = u
    p = tc.PRICES
    return i / 1e6 * p["input"] + c / 1e6 * p["cache_read"] + o / 1e6 * p["output"]


def _get(run, key, default=None):
    if isinstance(run, dict):
        return run.get(key, default)
    return getattr(run, key, default)


def _secs(a, b):
    return (b - a).total_seconds() if a and b else None


def model_of(run):
    meta = ((_get(run, "extra") or {}).get("metadata") or {})
    inv = ((_get(run, "extra") or {}).get("invocation_params") or {})
    return meta.get("ls_model_name") or inv.get("model") or inv.get("model_name") or ""


def prompt_chars(run):
    """Size of what was sent, in characters. Tokens are the bill; characters show
    which part of the prompt grew when the bill moves."""
    return len(json.dumps(_get(run, "inputs") or {}, default=str))


def summarise(runs, root):
    """Everything the CSVs and summary.json hold, from a list of runs.
    Separate from the I/O so it can be tested on plain objects."""
    index = {str(_get(r, "id")): r for r in runs}
    start = _get(root, "start_time")
    calls, by_agent = [], defaultdict(lambda: [0, 0, 0, 0, 0, 0.0])
    tools, tool_err = Counter(), Counter()
    steps = []
    ls_cost = 0.0
    for r in runs:
        rtype = _get(r, "run_type") or ""
        name = (_get(r, "name") or "").strip()
        st, en = _get(r, "start_time"), _get(r, "end_time")
        if rtype == "tool":
            tools[name] += 1
            if _get(r, "error"):
                tool_err[name] += 1
        if name.startswith("call_") and st and en:
            steps.append({"step": name, "start_offset_s": round(_secs(start, st) or 0, 1),
                          "duration_s": round(_secs(st, en), 1),
                          "error": bool(_get(r, "error"))})
        if rtype != "llm":
            continue
        u = tc._usage(r)
        if u is None:
            continue
        agent = tc._agent_of(r, index)
        c = cost_of(u)
        their = _get(r, "total_cost")
        if their is not None:
            ls_cost += float(their)
        a = by_agent[agent]
        for i in range(4):
            a[i] += u[i]
        a[4] += 1
        a[5] += c
        calls.append({
            "start_offset_s": round(_secs(start, st) or 0, 1),
            "duration_s": round(_secs(st, en) or 0, 1),
            "agent": agent, "name": name, "model": model_of(r),
            "input_tok": u[0], "cache_tok": u[1], "output_tok": u[2],
            "reasoning_tok": u[3], "cost_usd": round(c, 5),
            "langsmith_cost_usd": "" if their is None else round(float(their), 5),
            "prompt_chars": prompt_chars(r), "error": bool(_get(r, "error")),
        })
    calls.sort(key=lambda x: x["start_offset_s"])
    steps.sort(key=lambda x: x["start_offset_s"])
    tot = [sum(v[i] for v in by_agent.values()) for i in range(4)]
    summary = {
        "wall_s": _secs(start, _get(root, "end_time")),
        "root_status": _get(root, "status"),
        "root_error": _get(root, "error"),
        "runs_in_trace": len(runs),
        "model_calls": len(calls),
        "tokens": dict(zip(["input", "cache_read", "output", "reasoning"], tot)),
        "cost_usd": round(sum(c["cost_usd"] for c in calls), 4),
        "langsmith_cost_usd": round(ls_cost, 4) if ls_cost else None,
        "by_agent": {k: {"calls": v[4], "input": v[0], "cache_read": v[1],
                         "output": v[2], "reasoning": v[3], "cost_usd": round(v[5], 4)}
                     for k, v in sorted(by_agent.items(), key=lambda kv: -kv[1][5])},
        "steps": dict(Counter(s["step"] for s in steps)),
        "tool_calls": dict(tools.most_common()),
        "tool_errors": dict(tool_err.most_common()),
        "prices_per_million": tc.PRICES,
    }
    tool_rows = [{"tool": t, "calls": n, "errors": tool_err.get(t, 0)}
                 for t, n in tools.most_common()]
    return summary, calls, steps, tool_rows


# ---------------------------------------------------------------- I/O
def _git(*args):
    try:
        return subprocess.run(["git", *args], cwd=ROOT, capture_output=True,
                              text=True, timeout=20).stdout.strip()
    except Exception:  # noqa: BLE001  a missing git must not lose the trace
        return ""


def _dump_run(r):
    for attr in ("model_dump", "dict"):
        fn = getattr(r, attr, None)
        if fn:
            try:
                return fn()
            except Exception:  # noqa: BLE001
                pass
    return {k: v for k, v in vars(r).items() if not k.startswith("_")}


def _write_csv(path, rows, columns=None):
    columns = columns or (list(rows[0]) if rows else ["empty"])
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=columns)
        w.writeheader()
        w.writerows(rows)


def _find_root(client, project, args):
    roots = list(client.list_runs(project_name=project, is_root=True,
                                  limit=max(1, min(args.limit, 100))))
    if not roots:
        sys.exit(f"no root runs in LangSmith project {project!r}. Traces older "
                 f"than 14 days are deleted; set LANGSMITH_PROJECT if it is wrong.")
    if args.last:
        return roots[0]
    for r in roots:
        blob = json.dumps(_get(r, "inputs") or {}, default=str)
        if args.session_id in blob or args.session_id in (r.name or ""):
            return r
    return None


def _fetch(client, project, args):
    """The root and every run in its trace. With --wait, poll until the root has
    ended and two polls in a row return the same number of runs: LangSmith
    ingests asynchronously, and a trace read too early is silently short."""
    deadline = time.time() + max(args.wait, 0)
    last_n = -1
    while True:
        root = _find_root(client, project, args)
        if root is not None:
            runs = list(client.list_runs(project_name=project, trace_id=root.id))
            done = root.end_time is not None and len(runs) == last_n
            if done or time.time() >= deadline:
                return root, runs, done
            last_n = len(runs)
        elif time.time() >= deadline:
            sys.exit(f"no root run among the last {args.limit} mentions "
                     f"{args.session_id!r}. Use --wait if the run just ended.")
        print(f"  waiting for LangSmith ({'root not found' if root is None else f'{last_n} runs so far'})...")
        time.sleep(20)


def record(client, project, args):
    root, runs, complete = _fetch(client, project, args)
    summary, calls, steps, tool_rows = summarise(runs, root)
    if not calls:
        print("  WARNING: no model call in this trace carries token usage yet. "
              "It may still be ingesting; rerun with --wait 600.")

    sid = args.session_id or ""
    started = root.start_time or dt.datetime.now(dt.timezone.utc)
    label = "".join(ch if ch.isalnum() or ch in "-_" else "-"
                    for ch in (args.label or sid or root.name or "run"))[:40]
    folder = RUNS_DIR / f"{started:%Y%m%d-%H%M}_{label}_{str(root.id)[:8]}"
    folder.mkdir(parents=True, exist_ok=True)

    with gzip.open(folder / "trace.jsonl.gz", "wt", encoding="utf-8") as f:
        for r in runs:
            f.write(json.dumps(_dump_run(r), default=str) + "\n")
    _write_csv(folder / "calls.csv", calls)
    _write_csv(folder / "steps.csv", steps)
    _write_csv(folder / "tools.csv", tool_rows)
    summary["complete"] = complete
    (folder / "summary.json").write_text(json.dumps(summary, indent=2, default=str),
                                         encoding="utf-8")

    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        lab = f"{root.name or '?'}  {started:%Y-%m-%d %H:%M}  trace {str(root.id)[:8]}"
        tc._report(runs, lab, [root])
        tc._latency_report(runs, lab, root)
    (folder / "report.txt").write_text(buf.getvalue(), encoding="utf-8")

    try:
        url = client.get_run_url(run=root, project_name=project)
    except Exception:  # noqa: BLE001
        url = ""
    dirty = bool(_git("status", "--porcelain", "--untracked-files=no"))
    meta = {"recorded": dt.datetime.now().isoformat(timespec="seconds"),
            "project": project, "trace_id": str(root.id), "root_name": root.name,
            "session_id": sid, "trace_url": url, "commit": _git("rev-parse", "HEAD"),
            "branch": _git("rev-parse", "--abbrev-ref", "HEAD"), "dirty": dirty,
            "note": args.note or "", "complete": complete, "prices": tc.PRICES}
    (folder / "meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")

    if sid:
        prev = ROOT / "static" / "preview"
        got = [p for p in prev.glob(f"preview_{sid}.*") if p.is_file()]
        if got:
            (folder / "preview").mkdir(exist_ok=True)
            for p in got:
                shutil.copy2(p, folder / "preview" / p.name)
    if args.transcript:
        shutil.copy2(args.transcript, folder / "transcript.log")

    row = {"recorded": meta["recorded"], "run_start": f"{started:%Y-%m-%d %H:%M}",
           "label": label, "session_id": sid, "trace_id": str(root.id),
           "commit": meta["commit"][:9], "dirty": dirty,
           "wall_s": "" if summary["wall_s"] is None else round(summary["wall_s"]),
           "model_calls": summary["model_calls"],
           "input_tok": summary["tokens"]["input"],
           "cache_tok": summary["tokens"]["cache_read"],
           "output_tok": summary["tokens"]["output"],
           "reasoning_tok": summary["tokens"]["reasoning"],
           "cost_usd": summary["cost_usd"],
           "langsmith_cost_usd": summary["langsmith_cost_usd"] or "",
           "tool_errors": sum(summary["tool_errors"].values()),
           "note": args.note or "", "folder": folder.name}
    index = RUNS_DIR / "index.csv"
    new = not index.exists()
    with open(index, "a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=INDEX_COLUMNS)
        if new:
            w.writeheader()
        w.writerow(row)

    print(f"\n  recorded -> {folder}")
    print(f"  [proof] {summary['model_calls']} model call(s), {len(runs)} run(s) in the "
          f"trace, ${summary['cost_usd']:.3f} at our prices"
          + (f" (LangSmith says ${summary['langsmith_cost_usd']:.3f})"
             if summary["langsmith_cost_usd"] else "")
          + (f", wall {summary['wall_s']:,.0f}s" if summary["wall_s"] else "")
          + ("" if complete else "  -- NOT confirmed complete, rerun with --wait"))
    return folder


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("session_id", nargs="?")
    ap.add_argument("--last", action="store_true")
    ap.add_argument("--wait", type=int, default=0,
                    help="seconds to wait for LangSmith to finish ingesting")
    ap.add_argument("--limit", type=int, default=40)
    ap.add_argument("--project")
    ap.add_argument("--label", help="folder label (default: the session id)")
    ap.add_argument("--note", help="what this run was for, kept in index.csv")
    ap.add_argument("--transcript", help="a logs/live_*.log file to keep beside it")
    args = ap.parse_args()
    if not (args.session_id or args.last):
        ap.error("give a session id or --last")
    record(tc._client(), args.project or tc._project(), args)
    return 0


if __name__ == "__main__":
    sys.exit(main())
