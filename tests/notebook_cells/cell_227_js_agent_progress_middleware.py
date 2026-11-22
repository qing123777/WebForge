# Ported from fyp.ipynb cell 227 (ticket 05). The notebook is frozen;
# edit this file. Run by tests/test_notebook_cells.py.
# Unit tests: JS agent progress middleware
# (js_agent_progress / js_before_model_progress / js_tool_progress)
#
# These are the REAL decorated middleware objects, not re-implemented copies.
# @before_agent/@before_model/@wrap_tool_call return an AgentMiddleware whose
# hook is exposed as a method, so each one is invoked exactly the way the
# agent runtime invokes it.
#
# get_stream_writer() raises outside a LangGraph runnable context, so the
# tests swap it for a collector. That is the ONLY substitution.
#
# js_before_model_progress derives its label from the last COMPLETED tool
# call, so its cases build small real message histories (HumanMessage,
# AIMessage with tool_calls, ToolMessage) rather than bare state dicts.
from types import SimpleNamespace

_real_gsw_js = get_stream_writer
_emitted_js = []


def _run_js_mw(fn, *args):
    """Call a middleware hook with a captured stream writer."""
    global get_stream_writer
    _emitted_js.clear()
    get_stream_writer = lambda: _emitted_js.append          # noqa: E731
    try:
        result = fn(*args)
    finally:
        get_stream_writer = _real_gsw_js
    return list(_emitted_js), result


_RT_js = SimpleNamespace()          # progress hooks never touch runtime
_BM_js = js_before_model_progress.before_model


def _hist_js(tool_name, content, intent="modify"):
    """State whose last message is a completed call of `tool_name`."""
    return {"intent": intent, "messages": [
        HumanMessage(content="request"),
        AIMessage(content="", tool_calls=[
            {"name": tool_name, "args": {}, "id": "tc1"}]),
        ToolMessage(content=content, tool_call_id="tc1"),
    ]}


# ── js_agent_progress (@before_agent) ───────────────────────────────────────
# Case 1 [NORMAL] entry announcement fires once per agent invocation
msgs, ret = _run_js_mw(js_agent_progress.before_agent, {"intent": "generate"}, _RT_js)
print("[Case 1 · NORMAL] before_agent announces the agent has started")
print("  emitted:", msgs)
assert len(msgs) == 1, f"FAIL: expected exactly 1 message, got {msgs}"
assert "[JS Agent]" in msgs[0], "FAIL: message is not tagged with the agent name"
print("PASS: exactly one tagged start message emitted\n")

# Case 2 [INVARIANT] the hook must not write to state
print("[Case 2 · INVARIANT] before_agent returns None, so no state key is overwritten")
print("  returned:", repr(ret))
assert ret is None, f"FAIL: progress middleware returned a state update: {ret!r}"
print("PASS: returns None - progress reporting has no side effect on state\n")


# ── js_before_model_progress (@before_model) ────────────────────────────────
# Case 3 [NORMAL] fresh generation run announces generation
msgs, ret = _run_js_mw(_BM_js, {"intent": "generate", "messages": []}, _RT_js)
print("[Case 3 · NORMAL] run start in generate mode announces generation")
print("  emitted:", msgs)
assert msgs == ["   [JS Agent] Generating JS code..."], f"FAIL: got {msgs}"
assert ret is None
print("PASS: generation announced at the start of the run\n")

# Case 4 [NORMAL] fresh modification run announces the read, not a diff.
# Step 0 of modify mode reads the file from disk, so "Reading..." is what
# actually happens next. The old label promised a diff nine turns early.
msgs, ret = _run_js_mw(_BM_js, {"intent": "modify", "messages": []}, _RT_js)
print("[Case 4 · NORMAL] run start in modify mode announces the file read")
print("  emitted:", msgs)
assert msgs == ["   [JS Agent] Reading the current script..."], f"FAIL: got {msgs}"
assert ret is None
print("PASS: modify start announces Step 0, not a premature diff\n")

# Case 5 [NORMAL] a real lint failure means the model will now revise
msgs, ret = _run_js_mw(_BM_js, _hist_js("run_eslint",
    "  Line 4, Col 2 [rule]: problem\n\n[Lint attempt 1/3] "
    "Fix the reported lines and re-lint."), _RT_js)
print("[Case 5 · NORMAL] after a lint failure the turn is announced as revision")
print("  emitted:", msgs)
assert msgs == ["   [JS Agent] Revising after linter feedback..."], f"FAIL: {msgs}"
assert ret is None
print("PASS: the fix turn is now visible (old hook was silent or wrong here)\n")

# Case 6 [NORMAL] the lint cap message means the model will save best effort
msgs, ret = _run_js_mw(_BM_js, _hist_js("run_eslint",
    "  Line 4, Col 2 [rule]: problem\n\n[LINT CAP REACHED] 3/3 lint attempts "
    "used and problems remain. STOP the fix loop."), _RT_js)
print("[Case 6 · NORMAL] after the cap the turn is announced as best-effort save")
print("  emitted:", msgs)
assert msgs == ["   [JS Agent] Lint cap reached, saving best effort..."], f"FAIL: {msgs}"
assert ret is None
print("PASS: escalation is announced instead of guessed at\n")

# Case 7 [NORMAL] a guard rejection means the model will complete the code
msgs, ret = _run_js_mw(_BM_js, _hist_js("store_js_code",
    "Missing required include tag(s). Fix the issue(s) above and call "
    "store_js_code again.", intent="generate"), _RT_js)
print("[Case 7 · NORMAL] after a coverage-guard rejection the retry is announced")
print("  emitted:", msgs)
assert msgs == ["   [JS Agent] Completing the items the guard reported..."], f"FAIL: {msgs}"
assert ret is None
print("PASS: guard rejection turn labelled (was invisible before)\n")

# Case 8 [NORMAL] a successful extract means the model will write the diff
msgs, ret = _run_js_mw(_BM_js, _hist_js("extract_js_component", "document.querySelector('#navbar').addEventListener('click', fn);"), _RT_js)
print("[Case 8 · NORMAL] after a successful extract the diff turn is announced")
print("  emitted:", msgs)
assert msgs == ["   [JS Agent] Writing the modification diff..."], f"FAIL: {msgs}"
assert ret is None
print("PASS: 'Writing the modification diff' now fires exactly when true\n")

# Case 9 [INVARIANT] success paths and dead ends stay SILENT. The next tool's
# own label tells the story; a guessed label here would promise work that may
# never come (the wrap-up turn after write_file ends the run with no tool).
_silent_js = [
    ("lint clean",       _hist_js("run_eslint", "No issues found.")),
    ("lint infra",       _hist_js("run_eslint", "`npx` was not found. Install Node.js and re-run.")),
    ("store accepted",   _hist_js("store_js_code", "JavaScript code saved to state.")),
    # Ticket 05: two rows for store_js_diff were deleted. That tool is bound
    # to no agent, so its silence here was guaranteed and proved nothing.
    ("extract failed",   _hist_js("extract_js_component", "No JS code found referencing 'mini-cart'.")),
    ("file written",     _hist_js("write_file", "Updated file preview_x.js")),
]
print("[Case 9 · INVARIANT] success paths and dead ends emit no label")
for _lbl, _st in _silent_js:
    msgs, ret = _run_js_mw(_BM_js, _st, _RT_js)
    assert msgs == [], f"FAIL: {_lbl} produced a label: {msgs}"
    assert ret is None
    print(f"  silent as designed: {_lbl}")
print("PASS: no label ever promises work that may not happen\n")

# Case 10 [EDGE] state=None must not raise; treated as a fresh generate run
msgs, ret = _run_js_mw(_BM_js, None, _RT_js)
print("[Case 10 · EDGE] state=None handled by the (state or {}) guard")
print("  emitted:", msgs, "| returned:", repr(ret))
assert msgs == ["   [JS Agent] Generating JS code..."] and ret is None
print("PASS: no AttributeError on a missing state\n")


# ── js_tool_progress (@wrap_tool_call) ──────────────────────────────────────
_HANDLER_SENTINEL_js = object()


def _handler_js(request):
    return _HANDLER_SENTINEL_js


def _call_js_tool_mw(tool_call):
    return _run_js_mw(js_tool_progress.wrap_tool_call,
                       SimpleNamespace(tool_call=tool_call), _handler_js)


# Case 11 [NORMAL] every registered JS tool has its own progress line
_EXPECTED_js = {
    "store_js_code":           "Storing JS code",
    "run_eslint":              "Linting JS code with ESLint",
    "extract_js_component":    "Extracting JS block for component",
    "apply_and_lint_js":       "Applying diff and linting",
    "save_js_file":            "Saving JS to filesystem",
}
print("[Case 11 · NORMAL] each tool name maps to its own distinct progress line")
for _name, _fragment in _EXPECTED_js.items():
    msgs, out = _call_js_tool_mw({"name": _name})
    assert len(msgs) == 1, f"FAIL: {_name} emitted {msgs}"
    assert _fragment in msgs[0], f"FAIL: {_name} -> {msgs[0]!r}, expected {_fragment!r}"
    assert out is _HANDLER_SENTINEL_js, f"FAIL: {_name} did not reach the handler"
    print(f"  {_name:<24} -> {msgs[0].strip()}")
assert len({v for v in _EXPECTED_js.values()}) == len(_EXPECTED_js)
print(f"PASS: all {len(_EXPECTED_js)} tools announced distinctly, all reached the handler\n")

# Case 12 [EDGE] write_file is unmapped in ALL agents now; save_*_file carries the save label
msgs, out = _call_js_tool_mw({"name": "write_file"})
print("[Case 12 · EDGE] unmapped tool name produces no line but still runs")
print("  emitted:", msgs, "| handler reached:", out is _HANDLER_SENTINEL_js)
assert msgs == [], f"FAIL: invented a progress line for an unmapped tool: {msgs}"
assert out is _HANDLER_SENTINEL_js, "FAIL: unmapped tool was not executed"
print("PASS: unmapped tools pass through untouched\n")

# Case 13 [INVARIANT] a malformed tool_call must never swallow the tool call.
for _lbl, _bad in (("None", None), ("a string", "not-a-dict")):
    msgs, out = _call_js_tool_mw(_bad)
    assert out is _HANDLER_SENTINEL_js, f"FAIL: tool_call={_lbl} swallowed the call"
    assert msgs == []
print("[Case 13 · INVARIANT] malformed tool_call never blocks the underlying tool")
print("  tool_call=None and tool_call='not-a-dict' both reached the handler")
print("PASS: cosmetic middleware cannot cause a silent no-op\n")

# Case 14 [INFRA] the writer is restored even when the wrapped tool raises,
# and the tool's exception propagates unmasked.
class _ToolExploded_js(RuntimeError):
    pass


def _raising_handler_js(request):
    raise _ToolExploded_js("tool failed")


_caught_js = None
try:
    _run_js_mw(js_tool_progress.wrap_tool_call,
                SimpleNamespace(tool_call={"name": "run_eslint"}),
                _raising_handler_js)
except _ToolExploded_js as _e:
    _caught_js = _e
print("[Case 14 · INFRA] a failing tool propagates; middleware adds no masking")
print("  propagated:", type(_caught_js).__name__ if _caught_js else None)
assert _caught_js is not None, "FAIL: middleware swallowed the tool's exception"
assert get_stream_writer is _real_gsw_js, "FAIL: stream writer left patched"
print("PASS: exception propagated, real stream writer restored\n")

print("All 14 cases passed - JS progress middleware (3 hooks, observation-based labels).")
