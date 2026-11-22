# Ported from fyp.ipynb cell 134 (ticket 05). The notebook is frozen;
# edit this file. Run by tests/test_notebook_cells.py.
# Unit tests: html_tool_progress (@wrap_tool_call)
#
# The REAL decorated middleware object. @wrap_tool_call wraps tool
# execution; each case drives it with a fake request + handler and checks
# both the emitted progress line AND that the handler is still reached — a
# cosmetic hook must never swallow a tool call.
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


# ── html_tool_progress (@wrap_tool_call) ──────────────────────────────────────
_HANDLER_SENTINEL_html = object()


def _handler_html(request):
    return _HANDLER_SENTINEL_html


def _call_html_tool_mw(tool_call):
    return _run_html_mw(html_tool_progress.wrap_tool_call,
                       SimpleNamespace(tool_call=tool_call), _handler_html)


# Case 1 [NORMAL] every registered HTML tool has its own progress line
_EXPECTED_html = {
    "store_html_code":         "Storing HTML code",
    "run_html_validate":       "Linting HTML",
    "extract_component":       "Extracting target component",
    "apply_and_lint_html":     "Applying diff and linting",
    "apply_and_lint_html_full": "Applying edits and re-checking",
    "save_html_file":          "Saving HTML to filesystem",
}
print("[Case 1 - NORMAL] each tool name maps to its own distinct progress line")
for _name, _fragment in _EXPECTED_html.items():
    msgs, out = _call_html_tool_mw({"name": _name})
    assert len(msgs) == 1, f"FAIL: {_name} emitted {msgs}"
    assert _fragment in msgs[0], f"FAIL: {_name} -> {msgs[0]!r}, expected {_fragment!r}"
    assert out is _HANDLER_SENTINEL_html, f"FAIL: {_name} did not reach the handler"
    print(f"  {_name:<24} -> {msgs[0].strip()}")
assert len({v for v in _EXPECTED_html.values()}) == len(_EXPECTED_html)
print(f"PASS: all {len(_EXPECTED_html)} tools announced distinctly, all reached the handler\n")

# Case 2 [EDGE] unknown tool name produces no line but still runs
msgs, out = _call_html_tool_mw({"name": "some_future_tool"})
print("[Case 2 - EDGE] unmapped tool name produces no line but still runs")
print("  emitted:", msgs, "| handler reached:", out is _HANDLER_SENTINEL_html)
assert msgs == [], f"FAIL: invented a progress line for an unmapped tool: {msgs}"
assert out is _HANDLER_SENTINEL_html, "FAIL: unmapped tool was not executed"
print("PASS: unmapped tools pass through untouched\n")

# Case 3 [INVARIANT] a malformed tool_call must never swallow the tool call.
for _lbl, _bad in (("None", None), ("a string", "not-a-dict")):
    msgs, out = _call_html_tool_mw(_bad)
    assert out is _HANDLER_SENTINEL_html, f"FAIL: tool_call={_lbl} swallowed the call"
    assert msgs == []
print("[Case 3 - INVARIANT] malformed tool_call never blocks the underlying tool")
print("  tool_call=None and tool_call='not-a-dict' both reached the handler")
print("PASS: cosmetic middleware cannot cause a silent no-op\n")

# Case 4 [INFRA] the writer is restored even when the wrapped tool raises,
# and the tool's exception propagates unmasked.
class _ToolExploded_html(RuntimeError):
    pass


def _raising_handler_html(request):
    raise _ToolExploded_html("tool failed")


_caught_html = None
try:
    _run_html_mw(html_tool_progress.wrap_tool_call,
                SimpleNamespace(tool_call={"name": "run_html_validate"}),
                _raising_handler_html)
except _ToolExploded_html as _e:
    _caught_html = _e
print("[Case 4 - INFRA] a failing tool propagates; middleware adds no masking")
print("  propagated:", type(_caught_html).__name__ if _caught_html else None)
assert _caught_html is not None, "FAIL: middleware swallowed the tool's exception"
assert get_stream_writer is _real_gsw_html, "FAIL: stream writer left patched"
print("PASS: exception propagated, real stream writer restored\n")

print("All 4 cases passed - html_tool_progress (@wrap_tool_call).")
