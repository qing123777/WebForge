# Ported from fyp.ipynb cell 374 (ticket 05). The notebook is frozen;
# edit this file. Run by tests/test_notebook_cells.py.
# Rescued (ticket 05): the notebook marked this cell NOTEBOOK-ONLY, so it never ran
# offline. It makes no model call (the model is scripted or mocked).
from types import SimpleNamespace
from unittest.mock import MagicMock

_SAMPLE_TCS = [{"id": "TC-001", "component": "navbar", "description": "d",
                "action": "assert_visible", "selector": "s",
                "expected": "e", "passed": None}]
_PASS_REPORT = "PASSED: TC-001\nALL TESTS PASSED — no action required."

def _mk_state_exec(session_id="s001", test_cases=None, attempts=0, test_report="", round_calls=None):
    # A plain DICT, because that is what LangGraph passes. This used to be a
    # SimpleNamespace carrying BOTH a session_id attribute and a .get, so the
    # tool's `state.session_id` worked here and raised in production.
    return {
        "session_id":            session_id,
        "test_cases":            test_cases or _SAMPLE_TCS,
        "modification_attempts": attempts,
        "test_report":           test_report,
        **(round_calls or {}),
    }

def _run_ctea(report=_PASS_REPORT, session_id="s001", tool_call_id="tc001",
              modification_context="", attempts=0, state_report="", round_calls=None, **kw):
    """Run call_test_exec_pipeline with run_test_suite mocked.
    Pipeline form: the suite is invoked directly — no sub-agent, no stream."""
    global run_test_suite, get_stream_writer
    _orig, _orig_gsw = run_test_suite, get_stream_writer
    _writes, _mock   = [], MagicMock()
    _mock.func.return_value = SimpleNamespace(
        update={"test_report": report, "test_cases": []})
    try:
        run_test_suite    = _mock
        get_stream_writer = lambda: (lambda d: _writes.append(d))
        rt = SimpleNamespace(
            state        = _mk_state_exec(session_id, attempts=attempts, test_report=state_report, round_calls=round_calls),
            tool_call_id = tool_call_id
        )
        result = call_test_exec_pipeline.func(
            rt, modification_context=modification_context, **kw
        )
    finally:
        run_test_suite, get_stream_writer = _orig, _orig_gsw
    return result, _writes, _mock

# Case 1: suite's test_report returned in Command.update
result, _, _ = _run_ctea(report=_PASS_REPORT)
assert result.update["test_report"] == _PASS_REPORT
print("[Case 1] PASS: test_report from suite returned in Command.update")

# Case 2: test_cases from state passed to the suite
result, _, mock = _run_ctea()
suite_state = mock.func.call_args[0][0].state
assert suite_state["test_cases"] == _SAMPLE_TCS
print("[Case 2] PASS: test_cases from state passed to run_test_suite")

# Case 3: preview_url derived from session_id
result, _, mock = _run_ctea(session_id="abc42")
suite_state = mock.func.call_args[0][0].state
assert "abc42" in suite_state["preview_url"]
assert suite_state["preview_url"].startswith("file:///")
print(f"[Case 3] preview_url: {suite_state['preview_url']}")
print("PASS: preview_url contains session_id and file:/// scheme")

# Case 4: modification_context passed to the suite
result, _, mock = _run_ctea(modification_context="product-card colour change")
suite_state = mock.func.call_args[0][0].state
assert suite_state["modification_context"] == "product-card colour change"
print("[Case 4] PASS: modification_context passed to run_test_suite")

# Case 5: modification_attempts incremented on a RE-RUN (a report already in
# state means the baseline has run). No modification_context needed -- that is
# the B1 fix: counting no longer depends on the caller labelling the re-run.
result, _, _ = _run_ctea(state_report="PASSED: TC-001\nFAILED: TC-002", attempts=_MODIFICATION_ATTEMPT_CAP - 1)
assert result.update.get("modification_attempts") == _MODIFICATION_ATTEMPT_CAP
print(f"[Case 5] PASS: attempts incremented on a re-run ({_MODIFICATION_ATTEMPT_CAP - 1} -> {_MODIFICATION_ATTEMPT_CAP}), label not required")

# Case 6: NOT incremented on the baseline run (no prior report in state).
result, _, _ = _run_ctea(state_report="", attempts=0)
assert "modification_attempts" not in result.update
print("[Case 6] PASS: attempts not changed on the baseline run")

# Case 7: pipeline progress line written (replaces old custom-chunk forwarding)
result, writes, _ = _run_ctea()
assert any("Running Playwright test suite" in str(w) for w in writes), \
    f"FAIL: progress line missing: {writes}"
print("[Case 7] PASS: pipeline progress line written to stream")

# Case 8: indent +1 at start, -1 in finally
result, writes, _ = _run_ctea()
indents = [w for w in writes if isinstance(w, dict) and w.get("type") == "indent"]
assert indents[0]["delta"] == 1 and indents[-1]["delta"] == -1
print("[Case 8] PASS: indent +1 start, -1 finally")

# Case 9: ToolMessage contains modification_attempts count and cap on a re-run
result, _, _ = _run_ctea(state_report="FAILED: TC-002", attempts=_MODIFICATION_ATTEMPT_CAP - 1)
msg_content = result.update["messages"][0].content
assert f"modification_attempts: {_MODIFICATION_ATTEMPT_CAP} / cap: {_MODIFICATION_ATTEMPT_CAP}" in msg_content, f"Count missing: {msg_content}"
print("[Case 9] PASS: ToolMessage shows modification_attempts count and cap")

# Case 10: ToolMessage shows 0 attempts on the baseline run
result, _, _ = _run_ctea(state_report="", attempts=0)
msg_content = result.update["messages"][0].content
assert f"modification_attempts: 0 / cap: {_MODIFICATION_ATTEMPT_CAP}" in msg_content, f"Missing: {msg_content}"
print("[Case 10] PASS: ToolMessage shows 0 attempts on the baseline run")

# Case 11: cap already reached (at the cap) on a re-run -> REFUSED, suite never runs
result, _, mock = _run_ctea(state_report="FAILED: TC-002", attempts=_MODIFICATION_ATTEMPT_CAP)
mock.func.assert_not_called()
msg_content = result.update["messages"][0].content
assert "REFUSED" in msg_content and f"cap ({_MODIFICATION_ATTEMPT_CAP})" in msg_content, f"Wrong message: {msg_content}"
assert "test_report" not in result.update, "test_report should not be set on refusal"
assert "modification_attempts" not in result.update, "attempts must not increment on refusal"
print("[Case 11] PASS: call refused at cap, suite never invoked")

# Case 12 (B1 hole closed): an UNLABELED re-run at cap is ALSO refused now.
# This is the exact hole that produced the PO-08 runaway -- an empty
# modification_context used to slip past the cap and the loop ran on to
# recursion_limit. modification_context is empty here on purpose.
result, _, mock = _run_ctea(modification_context="", state_report="FAILED: TC-002", attempts=_MODIFICATION_ATTEMPT_CAP)
mock.func.assert_not_called()
assert "REFUSED" in result.update["messages"][0].content
assert "modification_attempts" not in result.update
print("[Case 12] PASS: an unlabeled re-run at cap is refused (the closed hole)")

# Case 13: indent balanced (+1/-1) on the refusal path too
result, writes, _ = _run_ctea(state_report="FAILED: TC-002", attempts=_MODIFICATION_ATTEMPT_CAP)
indents = [w for w in writes if isinstance(w, dict) and w.get("type") == "indent"]
assert indents[0]["delta"] == 1 and indents[-1]["delta"] == -1, f"Indent not balanced: {indents}"
print("[Case 13] PASS: indent +1/-1 balanced even when refused")

# Case 14 (pipeline-specific): suite invoked exactly once, directly, with the
# tool_call_id forwarded -- no LLM anywhere in the path
result, _, mock = _run_ctea(tool_call_id="tc-pipeline")
mock.func.assert_called_once()
assert mock.func.call_args[0][0].tool_call_id == "tc-pipeline"
print("[Case 14] PASS: run_test_suite invoked once, directly, tool_call_id forwarded")

# Case 15 (baseline is never refused): even if attempts is somehow already over the cap, a
# first run with no prior report must still execute -- refusing the baseline
# would leave the page untested. is_rerun is False here, so the cap does not bite.
result, _, mock = _run_ctea(state_report="", attempts=_MODIFICATION_ATTEMPT_CAP + 1)
mock.func.assert_called_once()
assert "REFUSED" not in result.update["messages"][0].content
assert "modification_attempts" not in result.update
print(f"[Case 15] PASS: the baseline run is never refused, even at attempts={_MODIFICATION_ATTEMPT_CAP + 1}")

# Case 16: dispatch-completeness -- the last report routed work to html_agent
# but html was not called this round (html_round_calls 0) -> REFUSED, suite
# never runs, no attempt spent. This is the PO-10 po0735889c hole: html_agent
# was routed two fixes and never called.
_ROUTED_HTML = ("PASSED: TC-001\nFAILED: TC-018\n\nAction required:\n"
                "- html_agent | intent=modify | target_component=hero-main | reason=url\n"
                "- css_agent | intent=modify | target_component=hdr | reason=css")
result, _, mock = _run_ctea(state_report=_ROUTED_HTML,
                            round_calls={"css_round_calls": 1, "html_round_calls": 0})
mock.func.assert_not_called()
_msg = result.update["messages"][0].content
assert "REFUSED" in _msg and "html_agent" in _msg, f"Wrong message: {_msg}"
assert "css_agent" not in _msg, "css was called, must not be named as skipped"
assert "test_report" not in result.update and "modification_attempts" not in result.update
print("[Case 16] PASS: a routed-but-uncalled agent (html) refuses the re-run, names only it")

# Case 17: every routed agent WAS called -> guard passes, suite runs.
result, _, mock = _run_ctea(state_report=_ROUTED_HTML,
                            round_calls={"css_round_calls": 1, "html_round_calls": 1})
mock.func.assert_called_once()
assert "REFUSED" not in result.update["messages"][0].content
print("[Case 17] PASS: when every routed agent was called, the re-run proceeds")

# Case 18: an agent with NO routed work is correctly absent -- js was never
# routed, so js_round_calls==0 must NOT refuse.
result, _, mock = _run_ctea(state_report=_ROUTED_HTML,
                            round_calls={"css_round_calls": 1, "html_round_calls": 1, "js_round_calls": 0})
mock.func.assert_called_once()
print("[Case 18] PASS: an un-routed agent's 0 calls does not refuse (only routed-but-skipped does)")

# Case 19: _routed_agents_from_report reads exactly the agents in Action required
assert _routed_agents_from_report(_ROUTED_HTML) == {"html", "css"}
assert _routed_agents_from_report("PASSED: TC-001\nALL TESTS PASSED — no action required.") == set()
assert _routed_agents_from_report("") == set()
print("[Case 19] PASS: _routed_agents_from_report extracts routed agents, empty on clean/baseline")

print("\nAll 19 call_test_exec_pipeline (pipeline) tests passed.")
