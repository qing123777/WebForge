# Ported from fyp.ipynb cell 133 (ticket 05). The notebook is frozen;
# edit this file. Run by tests/test_notebook_cells.py.
# Unit tests: html_before_model_progress (@before_model)
#
# The REAL decorated middleware object. This hook derives its label from
# the last COMPLETED tool call, so its cases build small real message
# histories (HumanMessage, AIMessage with tool_calls, ToolMessage).
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


_RT_html = SimpleNamespace()
_BM_html = html_before_model_progress.before_model


def _hist_html(tool_name, content, intent="modify"):
    """State whose last message is a completed call of `tool_name`."""
    return {"intent": intent, "messages": [
        HumanMessage(content="request"),
        AIMessage(content="", tool_calls=[
            {"name": tool_name, "args": {}, "id": "tc1"}]),
        ToolMessage(content=content, tool_call_id="tc1"),
    ]}


# ── html_before_model_progress (@before_model) ────────────────────────────────
# Case 1 [NORMAL] fresh generation run announces generation
msgs, ret = _run_html_mw(_BM_html, {"intent": "generate", "messages": []}, _RT_html)
print("[Case 1 - NORMAL] run start in generate mode announces generation")
print("  emitted:", msgs)
assert msgs == ["   [HTML Agent] Generating HTML code..."], f"FAIL: got {msgs}"
assert ret is None
print("PASS: generation announced at the start of the run\n")

# Case 2 [NORMAL] fresh modification run announces the read, not a diff.
# Step 0 of modify mode reads the file from disk, so "Reading..." is what
# actually happens next. The old label promised a diff nine turns early.
msgs, ret = _run_html_mw(_BM_html, {"intent": "modify", "messages": []}, _RT_html)
print("[Case 2 - NORMAL] run start in modify mode announces the file read")
print("  emitted:", msgs)
assert msgs == ["   [HTML Agent] Reading the current page..."], f"FAIL: got {msgs}"
assert ret is None
print("PASS: modify start announces Step 0, not a premature diff\n")

# Case 3 [NORMAL] a real lint failure means the model will now revise
msgs, ret = _run_html_mw(_BM_html, _hist_html("run_html_validate",
    "  Line 4, Col 2 [rule]: problem\n\n[Lint attempt 1/3] "
    "Fix the reported lines and re-lint."), _RT_html)
print("[Case 3 - NORMAL] after a lint failure the turn is announced as revision")
print("  emitted:", msgs)
assert msgs == ["   [HTML Agent] Revising after linter feedback..."], f"FAIL: {msgs}"
assert ret is None
print("PASS: the fix turn is now visible (old hook was silent or wrong here)\n")

# Case 4 [NORMAL] the lint cap message means the model will save best effort
msgs, ret = _run_html_mw(_BM_html, _hist_html("run_html_validate",
    "  Line 4, Col 2 [rule]: problem\n\n[LINT CAP REACHED] 3/3 lint attempts "
    "used and problems remain. STOP the fix loop."), _RT_html)
print("[Case 4 - NORMAL] after the cap the turn is announced as best-effort save")
print("  emitted:", msgs)
assert msgs == ["   [HTML Agent] Lint cap reached, saving best effort..."], f"FAIL: {msgs}"
assert ret is None
print("PASS: escalation is announced instead of guessed at\n")

# Case 5 [NORMAL] a guard rejection means the model will complete the code
msgs, ret = _run_html_mw(_BM_html, _hist_html("store_html_code",
    "Missing required include tag(s). Fix the issue(s) above and call "
    "store_html_code again.", intent="generate"), _RT_html)
print("[Case 5 - NORMAL] after a coverage-guard rejection the retry is announced")
print("  emitted:", msgs)
assert msgs == ["   [HTML Agent] Completing the items the guard reported..."], f"FAIL: {msgs}"
assert ret is None
print("PASS: guard rejection turn labelled (was invisible before)\n")

# Case 6 [NORMAL] a successful extract means the model will write the diff
msgs, ret = _run_html_mw(_BM_html, _hist_html("extract_component", '<nav id="navbar"><a href="#">Home</a></nav>'), _RT_html)
print("[Case 6 - NORMAL] after a successful extract the diff turn is announced")
print("  emitted:", msgs)
assert msgs == ["   [HTML Agent] Writing the modification diff..."], f"FAIL: {msgs}"
assert ret is None
print("PASS: 'Writing the modification diff' now fires exactly when true\n")

# Case 7 [INVARIANT] success paths and dead ends stay SILENT. The next tool's
# own label tells the story; a guessed label here would promise work that may
# never come (the wrap-up turn after write_file ends the run with no tool).
_silent_html = [
    ("lint clean",       _hist_html("run_html_validate", "No issues found.")),
    ("lint infra",       _hist_html("run_html_validate", "`npx` was not found. Install Node.js and re-run.")),
    ("store accepted",   _hist_html("store_html_code", "HTML code saved to state.")),
    ("diff applied clean", _hist_html("apply_and_lint_html", "Diff applied. '#navbar' instance 1 on page 'plp' updated.\nNo issues found.")),
    ("diff internal",    _hist_html("apply_and_lint_html", "[INTERNAL] NameError: name x is not defined")),
    ("extract failed",   _hist_html("extract_component", "No element found matching '#navbar' (tried as CSS selector, #id, and .class).")),
    ("file written",     _hist_html("write_file", "Updated file preview_x.html")),
]
print("[Case 7 - INVARIANT] success paths and dead ends emit no label")
for _lbl, _st in _silent_html:
    msgs, ret = _run_html_mw(_BM_html, _st, _RT_html)
    assert msgs == [], f"FAIL: {_lbl} produced a label: {msgs}"
    assert ret is None
    print(f"  silent as designed: {_lbl}")
print("PASS: no label ever promises work that may not happen\n")

# Case 8 [EDGE] state=None must not raise; treated as a fresh generate run
msgs, ret = _run_html_mw(_BM_html, None, _RT_html)
print("[Case 8 - EDGE] state=None handled by the (state or {}) guard")
print("  emitted:", msgs, "| returned:", repr(ret))
assert msgs == ["   [HTML Agent] Generating HTML code..."] and ret is None
print("PASS: no AttributeError on a missing state\n")

# Case 9 [NORMAL] apply_and_lint_html merges apply+lint, so its one result must
# drive the same labels the separate tools used to: patch fail -> re-diff,
# lint attempt -> revise, lint cap -> best-effort save.
_alh_bm_cases = [
    ("Patch failed: hunk mismatch\nRegenerate the diff against the CURRENT "
     "element below:\n\n<nav id=\"navbar\"></nav>", "Regenerating the diff..."),
    ("Diff applied. '#navbar' instance 1 on page 'plp' updated.\n"
     "  Line 4, Col 2 [rule]: problem\n\n[Lint attempt 1/3] Fix and re-lint.",
     "Revising after linter feedback..."),
    ("Diff applied. '#navbar' instance 1 on page 'plp' updated.\n"
     "  Line 4, Col 2 [rule]: problem\n\n[LINT CAP REACHED] 3/3 used.",
     "Lint cap reached, saving best effort..."),
]
print("[Case 9 - NORMAL] apply_and_lint_html result drives the merged-tool labels")
for _c, _exp in _alh_bm_cases:
    msgs, ret = _run_html_mw(_BM_html, _hist_html("apply_and_lint_html", _c), _RT_html)
    assert msgs == [f"   [HTML Agent] {_exp}"], f"FAIL: {_exp!r} <- {msgs}"
    assert ret is None
print("PASS: patch-fail / lint-attempt / lint-cap all labelled for apply_and_lint_html\n")

print("All 9 cases passed - html_before_model_progress (@before_model, observation-based labels).")
