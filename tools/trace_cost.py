"""What one run actually cost, from its LangSmith trace.

    python tools/trace_cost.py po01e9a8b4            one run, broken down by agent
    python tools/trace_cost.py --name "CSS Agent"    one agent, or one E2E case
    python tools/trace_cost.py --last                the most recent root run
    python tools/trace_cost.py --list                what roots are there to pick from

WHY THIS EXISTS AND THE LANGSMITH UI DOES NOT DO IT

The UI shows one number, the token total, and that number points at the wrong
thing. Measured on PO-08 po018f8158:

                      tokens        $      rate
    input (uncached)   270,288    0.676   $2.50/M
    cache read       1,288,064    0.322   $0.25/M
    output             104,059    1.561  $15.00/M
      of which
      reasoning         57,813    0.867
                     ---------   ------
    total            1,662,411    2.559

Cache read is 77% of the tokens and 13% of the bill. Output is 6% of the tokens
and 61% of the bill. Reading the total makes you optimise the wrong half. The
per-agent split is what found the JS agent sitting alone on effort="high":
JS $0.953 (37%), HTML $0.600, CSS $0.532, TestGen $0.270, planning $0.186,
context $0.017.

It also feeds Metric 9 of the evaluation campaign, which needs cost and latency
for 15 prompts through the MAS plus 15 through the single-LLM baseline. Thirty
runs is not something to add up by hand.

NOT WIRED INTO ANY TEST SUITE, ON PURPOSE

LangSmith ingests traces asynchronously. A query issued the moment a run ends
comes back `status: pending, end_time: None`, and a cost printed from that reads
$0.00 -- which looks exactly like "free" rather than "not there yet". This
project has already lost a week to a check whose empty result was
indistinguishable from a clean result (_sweep_dead_selectors), so nothing here
prints a zero it cannot vouch for: an empty or still-pending trace is reported
as such and exits non-zero.

The per-agent suites are also the wrong place to print a cost. One of them is
one or two model calls, around $0.02, where run-to-run variance is larger than
any change worth measuring. The number only means something at PO-08 scale.

Read-only. Spends no OpenAI credits.
"""
import argparse
import json
import os
import re
import sys
from collections import defaultdict

# USD per million tokens. GPT-5.4, the backbone every agent in this project
# shares. One place to edit when the price list moves.
PRICES = {
    "input":      2.50,
    "cache_read": 0.25,
    "output":    15.00,
}


def _client():
    try:
        from langsmith import Client
    except ImportError:
        sys.exit("langsmith is not installed:  pip install langsmith")
    try:
        from dotenv import load_dotenv
        load_dotenv(os.path.join(os.path.dirname(os.path.dirname(
            os.path.abspath(__file__))), ".env"))
    except ImportError:
        pass
    if not os.environ.get("LANGSMITH_API_KEY") and not os.environ.get("LANGCHAIN_API_KEY"):
        sys.exit("no LANGSMITH_API_KEY in the environment or in .env")
    return Client()


def _project():
    return (os.environ.get("LANGSMITH_PROJECT")
            or os.environ.get("LANGCHAIN_PROJECT")
            or "default")


def _usage(run):
    """(input, cache_read, output, reasoning) for one run, or None if it has none.

    LangSmith carries usage in more than one shape depending on how the run was
    logged, so every path is tried and the first that yields a token count wins.
    A run with no usage at all returns None rather than four zeros: a zero here
    would be averaged into the totals as if the call were free.
    """
    # 1. the modern shape: usage_metadata on the run itself
    um = getattr(run, "usage_metadata", None)
    if not um:
        # 2. LangChain writes it into the output message
        out = getattr(run, "outputs", None) or {}
        gens = out.get("generations") or []
        while isinstance(gens, list) and gens and isinstance(gens[0], list):
            gens = gens[0]
        for g in (gens if isinstance(gens, list) else []):
            if isinstance(g, dict):
                msg = (g.get("message") or {}).get("kwargs") or g.get("message") or {}
                um = msg.get("usage_metadata") or um
                if um:
                    break
        if not um and isinstance(out, dict):
            um = out.get("usage_metadata")
    if um:
        total_in = int(um.get("input_tokens") or 0)
        cache = int((um.get("input_token_details") or {}).get("cache_read") or 0)
        out_t = int(um.get("output_tokens") or 0)
        reason = int((um.get("output_token_details") or {}).get("reasoning") or 0)
        # input_tokens INCLUDES the cached part; the two are billed differently,
        # so split them rather than double-counting the cheap half at the dear rate.
        return max(total_in - cache, 0), cache, out_t, reason

    # 3. the legacy flat fields
    pt = getattr(run, "prompt_tokens", None)
    ct = getattr(run, "completion_tokens", None)
    if pt or ct:
        return int(pt or 0), 0, int(ct or 0), 0
    return None


def _agent_of(run, roots):
    """Which agent a leaf run belongs to: the nearest named ancestor.

    Falls back to the run's own name. The live suites already pass
    run_name="CSS Agent - GM-02" and the orchestrator tools name their
    sub-configs, so most runs resolve without guessing.
    """
    seen = set()
    cur = run
    while cur is not None:
        name = (getattr(cur, "name", "") or "").strip()
        for key in ("html", "css", "js", "test gen", "test_gen", "context",
                    "planning", "design", "orchestrator", "secondary", "primary"):
            if key in name.lower():
                return name
        pid = getattr(cur, "parent_run_id", None)
        if not pid or pid in seen:
            break
        seen.add(pid)
        cur = roots.get(str(pid))
    return (getattr(run, "name", "") or "unnamed").strip()


def _fmt_money(x):
    return f"${x:,.3f}"


def _report(runs, label, roots=None):
    """roots is the root run(s) this selection came from. With more than one,
    min(start)..max(end) spans the idle time BETWEEN them and is not a wall
    clock at all, so their own durations are summed instead and the line says
    so. Reporting 796s for two 40-second runs an hour apart would be a number
    that looks like a measurement and is not one."""
    by_agent = defaultdict(lambda: [0, 0, 0, 0, 0])   # in, cache, out, reasoning, calls
    # EVERY run is indexed, because the ancestor walk needs the chain and tool
    # runs to find an agent's name -- but only run_type == "llm" is SUMMED.
    # A LangGraph trace is a tree and each parent carries the total of its
    # children, so adding every level counted PO-08 po01e9a8b4 as 11.7M tokens
    # and $38.65 across 260 "calls" when it made 40. Leaves only.
    index = {str(r.id): r for r in runs}
    priced = 0
    for r in runs:
        if (getattr(r, "run_type", "") or "") != "llm":
            continue
        u = _usage(r)
        if u is None:
            continue
        priced += 1
        a = by_agent[_agent_of(r, index)]
        for i in range(4):
            a[i] += u[i]
        a[4] += 1

    if not priced:
        n_llm = sum(1 for r in runs if (getattr(r, "run_type", "") or "") == "llm")
        print(f"\n{label}: {len(runs)} run(s) found, {n_llm} of them model calls, "
              f"and NONE carries token usage.")
        print("Either the trace is still being ingested (LangSmith is async -- wait "
              "a minute and try again) or these runs are not model calls.")
        return 1

    tin = sum(v[0] for v in by_agent.values())
    tca = sum(v[1] for v in by_agent.values())
    tou = sum(v[2] for v in by_agent.values())
    tre = sum(v[3] for v in by_agent.values())
    c_in = tin / 1e6 * PRICES["input"]
    c_ca = tca / 1e6 * PRICES["cache_read"]
    c_ou = tou / 1e6 * PRICES["output"]
    c_re = tre / 1e6 * PRICES["output"]        # reasoning is billed as output
    total = c_in + c_ca + c_ou

    # wall clock across the whole selection
    unfinished = sum(1 for r in runs if getattr(r, "end_time", None) is None)
    wall, wall_label = None, "wall clock"
    if roots and len(roots) > 1:
        spans = [(r.end_time - r.start_time).total_seconds() for r in roots
                 if getattr(r, "end_time", None) and getattr(r, "start_time", None)]
        if spans:
            wall, wall_label = sum(spans), f"summed run time over {len(spans)} run(s)"
    else:
        starts = [r.start_time for r in runs if getattr(r, "start_time", None)]
        ends = [r.end_time for r in runs if getattr(r, "end_time", None)]
        if starts and ends:
            wall = (max(ends) - min(starts)).total_seconds()

    print()
    print("=" * 68)
    print(f"  {label}")
    print("=" * 68)
    print(f"  {'':<20} {'tokens':>12} {'$':>9}   rate")
    print(f"  {'input (uncached)':<20} {tin:>12,} {c_in:>9.3f}   ${PRICES['input']:.2f}/M")
    print(f"  {'cache read':<20} {tca:>12,} {c_ca:>9.3f}   ${PRICES['cache_read']:.2f}/M")
    print(f"  {'output':<20} {tou:>12,} {c_ou:>9.3f}   ${PRICES['output']:.2f}/M")
    print(f"  {'  of which reasoning':<20} {tre:>12,} {c_re:>9.3f}   (billed as output)")
    print(f"  {'':<20} {'-' * 12} {'-' * 9}")
    print(f"  {'TOTAL':<20} {tin + tca + tou:>12,} {total:>9.3f}")
    if total:
        print(f"\n  output is {c_ou / total * 100:.0f}% of the bill on "
              f"{tou / max(tin + tca + tou, 1) * 100:.0f}% of the tokens; "
              f"reasoning alone is {c_re / total * 100:.0f}%")
    if wall is not None:
        print(f"  {wall_label} {wall:,.0f}s over {priced} model call(s)"
              + (f", {unfinished} run(s) still unfinished" if unfinished else ""))

    print(f"\n  {'agent':<34} {'calls':>5} {'output':>9} {'$':>8}  {'share':>6}")
    rows = sorted(by_agent.items(),
                  key=lambda kv: -(kv[1][0] / 1e6 * PRICES["input"]
                                   + kv[1][1] / 1e6 * PRICES["cache_read"]
                                   + kv[1][2] / 1e6 * PRICES["output"]))
    for name, v in rows:
        cost = (v[0] / 1e6 * PRICES["input"] + v[1] / 1e6 * PRICES["cache_read"]
                + v[2] / 1e6 * PRICES["output"])
        share = f"{cost / total * 100:.0f}%" if total else "-"
        print(f"  {name[:34]:<34} {v[4]:>5} {v[2]:>9,} {cost:>8.3f}  {share:>6}")
    print()
    return 0


def _latency_report(runs, label, root):
    """Where the wall clock goes, by pipeline STEP -- a different question from
    cost. Test Execution runs Playwright and spends no tokens, so it never shows
    in the cost table, yet it can be minutes of the run. And the developer agents
    run in PARALLEL (CSS, JS and Test Gen fire together), so their own spans add
    up to MORE than the wall clock: the run is only as slow as the slowest branch
    plus the sequential parts. This prints each `call_*` step's own active time
    and says so, rather than pretending the parts are sequential.

    Read-only, like the rest of this tool."""
    root_start = getattr(root, "start_time", None)
    root_end = getattr(root, "end_time", None)
    wall = ((root_end - root_start).total_seconds()
            if root_start and root_end else None)

    by_step = defaultdict(lambda: [0.0, 0])   # name -> [summed seconds, count]
    timeline = []
    for r in runs:
        name = (getattr(r, "name", "") or "")
        st, en = getattr(r, "start_time", None), getattr(r, "end_time", None)
        if not name.startswith("call_") or not (st and en):
            continue
        dur = (en - st).total_seconds()
        by_step[name][0] += dur
        by_step[name][1] += 1
        timeline.append((st, dur, name))

    if not by_step:
        print(f"\n{label}: no `call_*` step spans found (nothing to time).")
        return 1

    print()
    print("=" * 68)
    print(f"  {label}   -- LATENCY by pipeline step")
    print("=" * 68)
    if wall is not None:
        print(f"  wall clock (root span): {wall:,.0f}s")
    summed = sum(v[0] for v in by_step.values())
    print(f"  sum of step active time: {summed:,.0f}s  "
          f"(> wall clock because developer agents run in parallel)\n")

    print(f"  {'step':<38} {'runs':>4} {'active s':>9} {'share of wall':>14}")
    for name, (secs, n) in sorted(by_step.items(), key=lambda kv: -kv[1][0]):
        share = f"{secs / wall * 100:.0f}%" if wall else "-"
        print(f"  {name[:38]:<38} {n:>4} {secs:>9,.0f} {share:>14}")

    # a compact timeline so the critical path and the parallel block are visible
    print(f"\n  timeline (offset from run start, each step's own duration):")
    for st, dur, name in sorted(timeline, key=lambda t: t[0]):
        off = (st - root_start).total_seconds() if root_start else 0
        print(f"    +{off:>6,.0f}s  [{dur:>6,.0f}s]  {name[:44]}")
    print()
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("session_id", nargs="?",
                    help="a run's session id, matched against the trace's inputs")
    ap.add_argument("--name", help="only runs whose name contains this (an agent, "
                                   "or one E2E case such as 'CSS Agent - GM-02')")
    ap.add_argument("--last", action="store_true", help="the most recent root run")
    ap.add_argument("--list", action="store_true", help="show recent root runs and exit")
    ap.add_argument("--latency", action="store_true",
                    help="report wall-clock by pipeline step instead of cost by agent")
    # The API refuses a limit above 100 per request with a 400, so it is clamped
    # here rather than left to fail halfway through a report.
    ap.add_argument("--limit", type=int, default=40,
                    help="how many recent root runs to search (default 40, max 100)")
    ap.add_argument("--project", help="LangSmith project (default: from the environment)")
    args = ap.parse_args()

    if not (args.session_id or args.name or args.last or args.list):
        ap.error("give a session id, or --name, or --last, or --list")

    client = _client()
    project = args.project or _project()
    args.limit = max(1, min(args.limit, 100))

    roots = list(client.list_runs(project_name=project, is_root=True,
                                  limit=args.limit))
    if not roots:
        sys.exit(f"no runs found in LangSmith project {project!r}. "
                 f"Set LANGSMITH_PROJECT if that is the wrong project.")

    if args.list:
        print(f"\n  recent root runs in {project!r}:\n")
        for r in roots:
            when = r.start_time.strftime("%Y-%m-%d %H:%M") if r.start_time else "?"
            print(f"    {when}  {(r.name or '?')[:38]:<38} {str(r.id)[:8]}")
        print()
        return 0

    # --name on its own selects by ROOT name, and unions those roots' traces.
    # The live suites already name their roots -- "CSS Agent - GM-02",
    # "JS Agent - GM-01", "Primary Orchestrator - PO-08" -- so this needs no
    # scan of every run in the project. Scanning was the first version and the
    # API refuses it: list_runs caps limit at 100 per request.
    if args.name and not (args.session_id or args.last):
        picked = [r for r in roots if args.name.lower() in (r.name or "").lower()]
        if not picked:
            sys.exit(f"no root run whose name contains {args.name!r} among the last "
                     f"{args.limit}. Try --limit 100, or --list to see the names.")
        kids = []
        for r in picked:
            kids.extend(client.list_runs(project_name=project, trace_id=r.id))
        return _report(kids, f"root name contains {args.name!r}  "
                             f"({len(picked)} run(s), newest "
                             f"{picked[0].start_time:%Y-%m-%d %H:%M})", picked)

    if args.last:
        target = roots[0]
    else:
        target = None
        for r in roots:
            blob = json.dumps(getattr(r, "inputs", None) or {}, default=str)
            if args.session_id in blob or args.session_id in (r.name or ""):
                target = r
                break
        if target is None:
            sys.exit(f"no root run in the last {args.limit} mentions "
                     f"{args.session_id!r}. Try --limit 200, or --list to see what "
                     f"is there. A run started minutes ago may not be ingested yet.")

    kids = list(client.list_runs(project_name=project, trace_id=target.id))
    if args.name:
        kids = [k for k in kids if args.name.lower() in (k.name or "").lower()]
    when = target.start_time.strftime("%Y-%m-%d %H:%M") if target.start_time else "?"
    label = f"{target.name or '?'}  {when}  trace {str(target.id)[:8]}"
    if args.session_id:
        label = f"{args.session_id}  |  " + label
    if args.latency:
        return _latency_report(kids, label, target)
    return _report(kids, label, [target])


if __name__ == "__main__":
    sys.exit(main())
