# Ported from fyp.ipynb cell 435 (ticket 18). The notebook is frozen;
# edit this file. Run only by run_live_suite.py, on the webforge/ package.
# NOTEBOOK-ONLY: scaffolding for manual runs, never exported to fyp.py
# ═══════════════════════════════════════════════════════════════════════════
# E2E (live LLM): THE PRIMARY ORCHESTRATOR CHAIN
#
# Thirteen cases. Most are one or a few turns and cost almost nothing. Two run the whole
# system and cost real money, and one sits in between, so they are separated
# and clearly labelled.
#
#   PO-01  generate, one-noun brief      cheap       must ask ONCE, not guess
#   PO-02  out of scope                  cheap       declines, calls NO tool
#   PO-03  asks for a fixed limit        cheap       explains, offers the real shape
#   PO-04  structural modify             cheap       the refusal itself, reason and offer
#   PO-05  a greeting and a question     cheap       answers it, calls NO tool
#   PO-06  an unsupported theme asked    cheap       says no, offers the nearest real one
#   PO-07  gibberish / nonsense input    cheap       no build, asks or explains plainly
#   PO-08  generate, full brief          expensive   the happy path end to end
#   PO-09  modify via the select flow    medium      the edit reaches the file on disk
#   PO-09b the accept/reject boundary    cheap       property yes, structural no
#   PO-10  provoke a failure (may pass)  expensive   IF it fails, reported as broken
#   PO-10b a forced, unfixable failure  medium      provably ends broken at the cap
#   PO-11  questions about the page      cheap       answered from the file, not the specs
#   PO-11b a question, no page built     cheap       says no page, does not fabricate
#
# Nothing here raises. Every check records a line into _PO_RESULTS and the run
# continues, so one bad case does not hide the five that came after it. The
# summary cell at the end reports honestly no matter which cases were run.
#
# WHAT IS HARD-CHECKED AND WHAT IS NOT
# Structure is hard-checked: which tools were called, in what order, with what
# arguments, and what reached disk. Wording is printed for the reader and never
# asserted, because the model phrases the same correct behaviour differently on
# every run and an assertion on phrasing fails a passing system.
# ═══════════════════════════════════════════════════════════════════════════
import json as _po_json
import pathlib as _po_pl
import time as _po_time
import uuid as _po_uuid

_PO_RESULTS = {}          # case id -> list of (passed, description)
# Ticket 18: the preview folder comes from webforge/config.py (was C:/Users/Lenovo/Desktop/FYP/static/preview).
from webforge.config import PREVIEW_DIR as _PO_PREVIEW


def _po_new_session(tag):
    """A session id is what the application layer issues, and the thread id is
    the same string. Nothing inside the system mints one, so the test supplies
    it exactly as Streamlit would."""
    return f"po{tag}{_po_uuid.uuid4().hex[:6]}"


def _po_modify_marker(component, instance, instruction):
    """The canonical message a component click produces.

    This is the ONE definition of that string. The preview panel is not built
    yet (it is the select-mode work), so when it is, it must emit this shape and
    should call this function rather than format its own. A second copy of the
    format is how the panel and the orchestrator drift apart silently.
    """
    return (f"[intent=modify | target_component={component} "
            f"| target_instance={instance}] {instruction}")


def _stream_orchestrator(case_id, message, session_id, seed=None,
                         recursion_limit=100, quiet=False, stop_after=None,
                         run_name=None):
    """Run one turn and return what happened, not what was said about it.

    Returns {"calls": [(tool_name, args)], "text": str, "state": dict,
             "seconds": float, "stopped_early": bool}. `calls` is in invocation
    order, which is what every ordering check below reads.

    `stop_after` names a tool and cuts the run the moment the orchestrator emits
    a call to it. Use it where a case asks only WHETHER a tool was reached and
    never inspects what it produced. LangGraph publishes the agent node's
    messages on the `updates` stream before the tools node runs, so the break
    lands before the named tool executes and no sub-agent spends anything. Leave
    it None for any case that reads state, disk or a later tool in the chain,
    because those need the run to finish.
    """
    payload = {"messages": [{"role": "user", "content": message}],
               "session_id": session_id}
    if seed:
        payload.update(seed)

    calls, texts, state = [], [], {}
    stopped_early = False
    cfg = {"configurable": {"thread_id": session_id},
           "run_name": run_name or f"Primary Orchestrator - {case_id}",
           "recursion_limit": recursion_limit}

    print(f"\n{'=' * 74}\n[{case_id}] {message[:110]}\n{'=' * 74}")
    _t0 = _po_time.time()
    _stream = orchestrator_agent.stream(
        payload, stream_mode=["updates", "custom"], version="v2", config=cfg)
    try:
        for chunk in _stream:
            kind, data = (chunk if isinstance(chunk, tuple)
                          else (chunk.get("type"), chunk.get("data")))
            if kind == "custom":
                # Only the human-readable progress lines are strings. The
                # build tools also emit structural events like
                # {"type": "indent", "delta": 1}, which the real Streamlit
                # pane consumes to indent the tree. In the console they are
                # noise, so they are dropped rather than printed.
                if not quiet and isinstance(data, str):
                    print(data)
            elif kind == "updates" and isinstance(data, dict):
                for _node, up in data.items():
                    if not isinstance(up, dict):
                        continue
                    for k, v in up.items():
                        if k != "messages":
                            state[k] = v
                    for msg in (up.get("messages") or []):
                        for tc in (getattr(msg, "tool_calls", None) or []):
                            calls.append((tc.get("name", ""), tc.get("args") or {}))
                        content = getattr(msg, "content", None)
                        if isinstance(content, str) and content.strip():
                            texts.append(content)
                        elif isinstance(content, list):
                            for blk in content:
                                if isinstance(blk, dict) and blk.get("type") == "text":
                                    texts.append(blk["text"])
            if stop_after and any(n == stop_after for n, _ in calls):
                stopped_early = True
                break
    finally:
        # Closing the generator is what actually cancels the run. Falling out of
        # the loop without it leaves the graph alive until garbage collection,
        # which is exactly the spend this is here to avoid.
        _close = getattr(_stream, "close", None)
        if callable(_close):
            _close()
    secs = _po_time.time() - _t0
    print(f"\n[{case_id}] tools called, in order: {[c[0] for c in calls] or 'none'}")
    if stopped_early:
        print(f"[{case_id}] CUT after {stop_after} was called, "
              f"before it ran. Nothing downstream was spent.")
    print(f"[{case_id}] wall clock: {secs:.1f}s")
    return {"calls": calls, "text": "\n".join(texts), "state": state,
            "seconds": secs, "stopped_early": stopped_early}


def _po(case_id, passed, description):
    """Record one check. Never raises, so a failure does not hide what follows."""
    _PO_RESULTS.setdefault(case_id, []).append((bool(passed), description))
    print(f"  {'PASS' if passed else 'FAIL'}  [{case_id}] {description}")
    return bool(passed)


def _po_names(run):
    return [name for name, _ in run["calls"]]


def _po_args(run, tool_name):
    """The arguments of the first call to that tool, or None."""
    for name, args in run["calls"]:
        if name == tool_name:
            return args
    return None


def _po_files(session_id):
    """Which of the three preview files exist for this session."""
    return {ext: (_PO_PREVIEW / f"preview_{session_id}.{ext}").exists()
            for ext in ("html", "css", "js")}


def _po_visible(text):
    """The reply as the user would see it, with internal notes removed.

    A tool returns a bookkeeping ToolMessage ("[Orchestrator] ...", such as
    ask_user's "Say nothing further this turn") so the model ends its turn. The
    real UI never shows these: bridge surfaces only AIMessageChunk text. These
    test prints glue every message together, so drop those lines here to match
    what actually reaches the chat. Display only; no assertion reads this.
    """
    return "\n".join(_l for _l in (text or "").splitlines()
                      if "[Orchestrator]" not in _l)


# The panel's marker and the middleware's parser are defined in different
# cells and neither reads the other. If the format drifts on one side, a modify
# request silently stops being recognised and the planning tools come back.
_marker_probe = modify_marker_fields(_po_modify_marker("hero-banner", 3, "green"))
assert _marker_probe.get("target_component") == "hero-banner" \
    and _marker_probe.get("target_instance") == "3", (
        "The marker _po_modify_marker writes is no longer one force_modify_routing "
        "can read, so a modify request would be routed as a generate. Got: %r"
        % (_marker_probe,))

print("[E2E] Primary Orchestrator harness ready.")
print("      run names are 'Primary Orchestrator - PO-0N', matching the other suites")
print("      cheap cases: PO-01, PO-02, PO-03, PO-04, PO-05, PO-06, PO-07, PO-09b, PO-11, PO-11b")
print("                   one turn each, except PO-01, whose second turn is")
print("                   cut as soon as it proceeds, so it stays cheap")
print("      medium:      PO-09")
print("      expensive:   PO-08, PO-10")


# Ticket 18: the notebook checked here that neither orchestrator was built
# before a tool's cell was re-run (assert_orchestrator_is_current,
# assert_secondary_orch_is_current). Ticket 06 deleted those guards: the
# package is imported once per process, so every agent is built from the tool
# objects that run. Nothing can be stale here.
