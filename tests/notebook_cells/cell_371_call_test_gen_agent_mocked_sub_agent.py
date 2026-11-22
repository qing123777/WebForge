# Ported from fyp.ipynb cell 371 (ticket 05). The notebook is frozen;
# edit this file. Run by tests/test_notebook_cells.py.
# Rescued (ticket 05): the notebook marked this cell LIVE-LLM, so it never ran
# offline. It makes no model call (the model is scripted or mocked).
from types import SimpleNamespace
from unittest.mock import MagicMock

_SAMPLE_TCS = [
    {"id": "TC-001", "component": "navbar", "description": "navbar visible",
     "action": "assert_visible", "selector": "#navbar",
     "expected": "visible", "passed": None}
]

def _run_ctga(chunks, session_id="s001", tool_call_id="tc001",
              user_query="build a shop", layout=None, **kw):
    global test_gen_agent, get_stream_writer
    _orig, _orig_gsw = test_gen_agent, get_stream_writer
    _writes, _mock   = [], MagicMock()
    _mock.stream.return_value = iter(chunks)
    try:
        test_gen_agent    = _mock
        get_stream_writer = lambda: (lambda d: _writes.append(d))
        # A plain DICT, because that is what LangGraph passes. This shim used to
        # build a SimpleNamespace carrying BOTH a session_id attribute and a .get,
        # so the tool's mixed access worked here and raised in production.
        rt = SimpleNamespace(
            state={
                "session_id":                session_id,
                "user_query":                user_query,
                "layout_specification":      layout or {},
                "components_specification":  {},
                "interaction_specification": {},
                "decoration_specification":  {},
            },
            tool_call_id = tool_call_id
        )
        result = call_test_gen_agent.func(rt, **kw)
    finally:
        test_gen_agent, get_stream_writer = _orig, _orig_gsw
    return result, _writes, _mock

# Case 1: test_cases captured from sub-agent state and returned in Command.update
_tc_chunk = ("updates", {"agent": {"test_cases": _SAMPLE_TCS}})
result, _, _ = _run_ctga([_tc_chunk])
assert result.update["test_cases"] == _SAMPLE_TCS
print("[Case 1] PASS: test_cases captured and returned in Command.update")

# Case 2: no test_cases in sub-agent update → empty list returned
result, _, _ = _run_ctga([("updates", {"agent": {"lint_passed": True}})])
assert result.update["test_cases"] == []
print("[Case 2] PASS: missing test_cases defaults to empty list")

# Case 3: user_query from state forwarded to payload
result, _, mock = _run_ctga([], user_query="B2C shop with cart")
p = mock.stream.call_args[0][0]
assert p["user_query"] == "B2C shop with cart"
print("[Case 3] PASS: user_query from state forwarded to payload")

# Case 4: session_id from runtime.state in payload + sub_config
result, _, mock = _run_ctga([], session_id="abc123")
p  = mock.stream.call_args[0][0]
sc = mock.stream.call_args.kwargs["config"]
assert p["session_id"]  == "abc123"
assert sc["configurable"]["session_id"] == "abc123"
print("[Case 4] PASS: session_id in payload and sub_config")

# Case 5: custom chunk forwarded to writer
result, writes, _ = _run_ctga([("custom", "gen-progress")])
assert "gen-progress" in writes
print("[Case 5] PASS: custom chunk forwarded to writer")

# Case 6: ToolMessage count reflects captured test_cases length
result, _, _ = _run_ctga([("updates", {"agent": {"test_cases": _SAMPLE_TCS}})])
assert "1 test case(s)" in result.update["messages"][0].content
print("[Case 6] PASS: ToolMessage reflects test case count")

print("\nAll 6 call_test_gen_agent tests passed.")

# ── Recursion guard (added 2026-08-08) ────────────────────────────────────────
# recursion_limit BOUNDS the loop but does not end it gracefully: when the budget
# runs out LangGraph RAISES GraphRecursionError, which would abort the whole
# orchestrator run. Every batch was schema-checked before it was saved, so the
# partial suite is still usable -- degrade to it rather than crash.
from langgraph.errors import GraphRecursionError as _GRE_T

_B1 = [{"id": "TC-001", "component": "navbar", "description": "d",
        "action": "assert_visible", "selector": "#navbar", "expected": "", "passed": None}]
_B2 = [{"id": "TC-002", "component": "footer", "description": "d",
        "action": "assert_visible", "selector": "#footer", "expected": "", "passed": None}]


def _ctga_blowup():
    """Two good batches, then the recursion limit trips."""
    yield ("updates", {"agent": {"test_cases": _B1}})
    yield ("updates", {"agent": {"test_cases": _B2}})
    raise _GRE_T("Recursion limit of 50 reached")


result, _writes7, _ = _run_ctga(_ctga_blowup())
assert [t["id"] for t in result.update["test_cases"]] == ["TC-001", "TC-002"], \
    f"partial suite lost: {result.update['test_cases']}"
print("[Case 7] PASS: batches accumulated before the raise are kept, not discarded")

_m7 = result.update["messages"][0].content
assert "recursion_limit" in _m7 and "PARTIAL" in _m7, _m7
assert "do NOT call the Test Generation Agent again" in _m7, _m7
print("[Case 8] PASS: the orchestrator is told the suite is partial and not to retry")

assert any("generation limit" in str(w) for w in _writes7), _writes7
print("[Case 9] PASS: the progress stream reports the early stop in plain words")

result, _, _ = _run_ctga([("updates", {"agent": {"test_cases": _B1}})])
assert "completed" in result.update["messages"][0].content
assert "PARTIAL" not in result.update["messages"][0].content
print("[Case 10] PASS: a normal run is unchanged -- no warning is added")

print("\nAll 10 call_test_gen_agent tests passed.")
