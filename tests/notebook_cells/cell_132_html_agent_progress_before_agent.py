# Ported from fyp.ipynb cell 132 (ticket 05). The notebook is frozen;
# edit this file. Run by tests/test_notebook_cells.py.
# Unit tests: html_agent_progress (@before_agent)
#
# The REAL decorated middleware object, not a copy. @before_agent returns
# an AgentMiddleware whose hook is exposed as .before_agent, invoked exactly
# the way the agent runtime invokes it.
from types import SimpleNamespace

_real_gsw_html = get_stream_writer
_emitted_html = []


def _run_html_mw(fn, *args):
    """Call a middleware hook with a captured stream writer.

    get_stream_writer() raises outside a LangGraph runnable context, so the
    tests swap it for a collector and restore it in finally. That is the ONLY
    substitution — the decorated middleware object under test is the real one.
    """
    global get_stream_writer
    _emitted_html.clear()
    get_stream_writer = lambda: _emitted_html.append          # noqa: E731
    try:
        result = fn(*args)
    finally:
        get_stream_writer = _real_gsw_html
    return list(_emitted_html), result


_RT_html = SimpleNamespace()          # progress hooks never touch runtime


# ── html_agent_progress (@before_agent) ───────────────────────────────────────
# Case 1 [NORMAL] entry announcement fires once per agent invocation
msgs, ret = _run_html_mw(html_agent_progress.before_agent, {"intent": "generate"}, _RT_html)
print("[Case 1 - NORMAL] before_agent announces the agent has started")
print("  emitted:", msgs)
assert len(msgs) == 1, f"FAIL: expected exactly 1 message, got {msgs}"
assert "[HTML Agent]" in msgs[0], "FAIL: message is not tagged with the agent name"
print("PASS: exactly one tagged start message emitted\n")

# Case 2 [INVARIANT] the hook must not write to state
print("[Case 2 - INVARIANT] before_agent returns None, so no state key is overwritten")
print("  returned:", repr(ret))
assert ret is None, f"FAIL: progress middleware returned a state update: {ret!r}"
print("PASS: returns None - progress reporting has no side effect on state\n")

print("All 2 cases passed - html_agent_progress (@before_agent).")
