"""Is the run slow because it did more work, or because the service was slow?

    python tools/trace_speed.py                       every agent run, newest last
    python tools/trace_speed.py --name "HTML Agent"   just the runs whose name matches
    python tools/trace_speed.py --calls "CSS Agent - MM-03"   one run, call by call
    python tools/trace_speed.py --since 09:00          reach further back than
                                                      the newest 100 root runs

WHY THIS EXISTS

On 2026-08-31 a suite that had taken 47s took 245s, right after a batching
change, and "did my change do this" could not be answered from the wall clock.
It was answered from ONE number: output tokens per second.

    HTML GM-01 call 1     secs      in     out   reason   out/s
    10:07                 24.6   9,168   2,835    1,552   115.2
    13:09                130.5   9,528   2,797    1,867    21.4

Same input, same output, same reasoning, five times the time. Nothing a change
to this repo can do looks like that.

HOW TO READ IT

  out/s collapsed, token counts flat      the service slowed down. Wait.
  out/s flat, tokens up                   the change made the model do more work.
  out/s collapsed on BIG calls only,      also the service: a retry or a network
    small calls unchanged                 delay is a FIXED cost and would slow
                                          the small calls too.
  one call far slower than its siblings,  a retry with backoff hiding inside a
    same tokens                           single span.

trace_cost.py answers "what did it cost". This answers "why did it take so long".
Both read the same traces; neither runs the model.
"""
import os
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if load_dotenv:
    load_dotenv(os.path.join(ROOT, ".env"))

PROJECT = os.environ.get("LANGSMITH_PROJECT") or os.environ.get(
    "LANGCHAIN_PROJECT") or "testing"


def _reasoning(run):
    """Reasoning tokens, which are billed as output but reported separately.

    Worth its own column: a model that thinks harder produces the same visible
    answer and takes far longer, and that is indistinguishable from a slow
    service unless this number is on screen.
    """
    try:
        for gen in (run.outputs or {}).get("generations", [[]])[0]:
            md = (gen.get("message") or {}).get("kwargs", {}).get("usage_metadata") or {}
            return (md.get("output_token_details") or {}).get("reasoning", 0)
    except Exception:
        pass
    return 0


def _llm_children(client, root):
    kids = [k for k in client.list_runs(project_name=PROJECT,
                                        trace_id=root.trace_id, limit=100)
            if k.run_type == "llm" and k.end_time]
    kids.sort(key=lambda k: k.start_time)
    return kids


def main(argv):
    from langsmith import Client
    client = Client()

    name = None
    per_call = False
    if "--name" in argv:
        name = argv[argv.index("--name") + 1]
    if "--calls" in argv:
        name = argv[argv.index("--calls") + 1]
        per_call = True

    # 100 is the server's hard maximum ("Limit exceeds maximum allowed value of
    # 100"), so reaching further back is done with a TIME WINDOW, not a bigger
    # page. It matters: the project is full of unnamed "LangGraph" roots, so the
    # newest 100 roots can hold only a couple of hours of agent runs -- and the
    # before/after comparison this tool exists for needs both sides.
    since = None
    if "--since" in argv:
        import datetime as _dt
        raw = argv[argv.index("--since") + 1]           # "HH:MM" or "MM-DD HH:MM"
        today = _dt.datetime.now()
        try:
            if len(raw) <= 5:
                h, m = (int(x) for x in raw.split(":"))
                since = today.replace(hour=h, minute=m, second=0, microsecond=0)
            else:
                since = _dt.datetime.strptime(f"{today.year}-{raw}", "%Y-%m-%d %H:%M")
        except ValueError:
            print(f"  --since {raw!r}: use HH:MM or 'MM-DD HH:MM'.")
            return 1
    roots = [r for r in client.list_runs(project_name=PROJECT, is_root=True,
                                         limit=100, start_time=since)
             if r.end_time and r.name
             and (name in r.name if name else ("Agent -" in r.name
                                               or "Orchestrator -" in r.name))]
    if not roots:
        print(f"  no finished runs matching {name!r} in project {PROJECT!r}.")
        print("  LangSmith ingests asynchronously -- a run that just ended may "
              "not be queryable for a minute or two.")
        return 1
    roots.sort(key=lambda r: r.start_time)

    if per_call:
        for r in roots:
            kids = _llm_children(client, r)
            if not kids:
                continue
            ip = (kids[0].extra or {}).get("invocation_params", {})
            print(f"\n=== {r.start_time:%m-%d %H:%M}  {r.name} ===")
            print(f"    model={ip.get('model') or ip.get('model_name')}  "
                  f"reasoning={ip.get('reasoning')}  stream={ip.get('stream')}")
            print(f"    {'#':>2} {'secs':>7} {'in':>9} {'out':>7} {'reason':>7} {'out/s':>7}")
            for n, k in enumerate(kids, 1):
                d = (k.end_time - k.start_time).total_seconds()
                out = k.completion_tokens or 0
                print(f"    {n:2d} {d:7.1f} {k.prompt_tokens or 0:9,d} {out:7,d} "
                      f"{_reasoning(k):7,d} {(out / d if d else 0):7.1f}")
        return 0

    print(f"  project {PROJECT!r} -- output tokens per second is the column that "
          f"separates\n  'the change did more work' from 'the service was slow'.\n")
    print(f"  {'when':<16}{'run':<32}{'secs':>8}{'calls':>7}{'in':>10}"
          f"{'out':>8}{'reason':>8}{'out/s':>8}")
    for r in roots:
        kids = _llm_children(client, r)
        if not kids:
            continue
        secs = sum((k.end_time - k.start_time).total_seconds() for k in kids)
        inp = sum(k.prompt_tokens or 0 for k in kids)
        out = sum(k.completion_tokens or 0 for k in kids)
        rea = sum(_reasoning(k) for k in kids)
        print(f"  {r.start_time:%m-%d %H:%M:%S}  {r.name[:30]:<32}{secs:8.1f}"
              f"{len(kids):7d}{inp:10,d}{out:8,d}{rea:8,d}{(out / secs if secs else 0):8.1f}")
    print("\n  secs here is time spent INSIDE the model calls, so it excludes "
          "printing,\n  linting and browser work. If it tracks the wall clock, "
          "the terminal is not\n  the bottleneck.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
