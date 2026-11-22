# Ported from fyp.ipynb cell 360 (ticket 05). The notebook is frozen;
# edit this file. Run by tests/test_notebook_cells.py.
# Rescued (ticket 05): the notebook marked this cell LIVE-LLM, so it never ran
# offline. It makes no model call (the model is scripted or mocked).
from types import SimpleNamespace
from unittest.mock import MagicMock

def _run_cla(stream_chunks, query="build a product listing page",
             session_id="s001", tool_call_id="tc001", state_extra=None, **kw):
    """
    Run call_html_agent.func with mocked html_agent and get_stream_writer.
    Saves and restores both globals between calls.
    Returns (command_result, writes_list, mock_agent).
    """
    global html_agent, get_stream_writer
    _orig_agent = html_agent
    _orig_gsw   = get_stream_writer
    _writes     = []
    _mock_agent = MagicMock()
    _mock_agent.stream.return_value = iter(stream_chunks)
    try:
        html_agent        = _mock_agent
        get_stream_writer = lambda: (lambda d: _writes.append(d))
        # A plain DICT, because that is what LangGraph passes. This shim used to
        # build a SimpleNamespace, so `state.session_id` worked here and raised
        # AttributeError in production.
        _st = {"session_id": session_id, **(state_extra or {})}
        rt = SimpleNamespace(state=_st, tool_call_id=tool_call_id)
        result = call_html_agent.func(rt, query, **kw)
    finally:
        html_agent        = _orig_agent
        get_stream_writer = _orig_gsw
    return result, _writes, _mock_agent

# Case 1: default params → payload has intent=generate, empty targets
result, writes, mock_agent = _run_cla([])
payload = mock_agent.stream.call_args[0][0]
assert payload["intent"]           == "generate", "FAIL: expected intent=generate"
assert payload["target_component"] == "",          "FAIL: expected empty target_component"
assert payload["target_instance"]  == 1,           "FAIL: expected target_instance=1"
print("[Case 1] PASS: default params → intent=generate, empty targets")

# Case 2: explicit intent=modify + target fields flow into payload
result, writes, mock_agent = _run_cla(
    [], intent="modify",
    target_component="product-card", target_instance=2
)
payload = mock_agent.stream.call_args[0][0]
assert payload["intent"]           == "modify",       "FAIL: intent not passed"
assert payload["target_component"] == "product-card", "FAIL: target_component not passed"
assert payload["target_instance"]  == 2,              "FAIL: target_instance not passed"
print("[Case 2] PASS: explicit modify params flow into payload")

# Case 3: session_id from runtime.state placed in payload
result, writes, mock_agent = _run_cla([], session_id="abc123")
payload = mock_agent.stream.call_args[0][0]
assert payload["session_id"] == "abc123", "FAIL: session_id not in payload"
print("[Case 3] PASS: session_id from runtime.state → payload")

# Case 4: sub_config configurable uses same session_id
result, writes, mock_agent = _run_cla([], session_id="cfg-42")
sub_config = mock_agent.stream.call_args.kwargs["config"]
assert sub_config["configurable"]["session_id"] == "cfg-42", \
    "FAIL: configurable session_id wrong"
print("[Case 4] PASS: sub_config configurable session_id matches")

# Case 5: custom chunk (tuple form) forwarded to writer
result, writes, _ = _run_cla([("custom", "progress text")])
assert "progress text" in writes, "FAIL: custom tuple chunk not forwarded to writer"
print("[Case 5] PASS: custom chunk (tuple) forwarded to writer")

# Case 6: custom chunk (dict form) forwarded to writer
result, writes, _ = _run_cla([{"type": "custom", "data": "dict-chunk"}])
assert "dict-chunk" in writes, "FAIL: custom dict chunk not forwarded to writer"
print("[Case 6] PASS: custom chunk (dict) forwarded to writer")

# Case 7: updates chunk — captured state NOT returned in Command.update
result, writes, _ = _run_cla([
    ("updates", {"agent": {"html_code": "<html>mock</html>", "lint_passed": True}})
])
assert "html_code"   not in result.update, "FAIL: html_code must not be in Command.update"
assert "lint_passed" not in result.update, "FAIL: lint_passed must not be in Command.update"
print("[Case 7] PASS: captured state not returned in Command.update")

# Case 8: messages key inside updates skipped — only explicit ToolMessage returned
result, writes, _ = _run_cla([
    ("updates", {"agent": {"messages": [{"role": "assistant", "content": "hi"}],
                           "html_code": "<p>hi</p>"}})
])
assert all(isinstance(m, ToolMessage) for m in result.update["messages"]), \
    "FAIL: non-ToolMessage found in Command.update messages"
print("[Case 8] PASS: messages key skipped by _merge, only ToolMessage returned")

# Case 9: non-dict update silently skipped by _merge (no exception raised)
result, writes, _ = _run_cla([("updates", {"agent": "not-a-dict"})])
assert "messages" in result.update, "FAIL: Command.update must still have messages key"
print("[Case 9] PASS: non-dict update silently skipped")

# Case 10: the ToolMessage names the agent AND the artefact it is reporting on.
# It used to assert "file system", which passed on a hardcoded success line that
# was false whenever the agent wrote nothing (E2E-SO-01). The content is now
# derived from the file, so the check is that both facts are present; WHAT it
# says about the file is covered by the three Outcome cases at the end of this
# cell.
result, writes, _ = _run_cla([])
msg_content = result.update["messages"][0].content
assert "HTML Agent" in msg_content, "FAIL: ToolMessage missing 'HTML Agent'"
assert ".html" in msg_content, f"FAIL: ToolMessage does not name the artefact: {msg_content}"
print("[Case 10] PASS: ToolMessage names the agent and its artefact")

# Case 11: Command.update has ONLY 'messages' key (captured never returned)
result, writes, _ = _run_cla([
    ("updates", {"agent": {"html_code": "<html/>", "session_id": "x"}})
])
assert set(result.update.keys()) == {"messages"}, \
    f"FAIL: unexpected keys in Command.update: {set(result.update.keys())}"
print("[Case 11] PASS: Command.update contains only 'messages' key")

# Case 12: indent +1 written at start, -1 in finally
result, writes, _ = _run_cla([])
indent_writes = [w for w in writes if isinstance(w, dict) and w.get("type") == "indent"]
assert len(indent_writes) >= 2,           "FAIL: expected at least 2 indent writes"
assert indent_writes[0]["delta"]  ==  1,  "FAIL: first indent must be +1"
assert indent_writes[-1]["delta"] == -1,  "FAIL: last indent must be -1"
print("[Case 12] PASS: indent +1 at start, -1 in finally")


# Case 13: query appears in both payload["user_query"] and payload["messages"][0]["content"]
result, writes, mock_agent = _run_cla([], query="show me a cart page")
payload = mock_agent.stream.call_args[0][0]
assert payload["user_query"]               == "show me a cart page", "FAIL: user_query wrong"
assert payload["messages"][0]["content"]   == "show me a cart page", "FAIL: messages content wrong"
print("[Case 13] PASS: query in payload[user_query] and payload[messages][0][content]")

# Case 14: tool_call_id forwarded to the returned ToolMessage
result, writes, _ = _run_cla([], tool_call_id="specific-tc-99")
assert result.update["messages"][0].tool_call_id == "specific-tc-99", \
    "FAIL: tool_call_id not forwarded to ToolMessage"
print("[Case 14] PASS: tool_call_id forwarded to returned ToolMessage")

# Case 15: exception during stream → indent -1 still fires in finally
_orig_agent_15 = html_agent
_orig_gsw_15   = get_stream_writer
_writes_15     = []
_mock_exc      = MagicMock()
_mock_exc.stream.side_effect = RuntimeError("stream blew up")
try:
    html_agent        = _mock_exc
    get_stream_writer = lambda: (lambda d: _writes_15.append(d))
    _rt15 = SimpleNamespace(state={"session_id": "s-exc"}, tool_call_id="tc-exc")
    call_html_agent.func(_rt15, "some query")
except RuntimeError:
    pass
finally:
    html_agent        = _orig_agent_15
    get_stream_writer = _orig_gsw_15
_indent_15 = [w for w in _writes_15 if isinstance(w, dict) and w.get("type") == "indent"]
assert any(w["delta"] == -1 for w in _indent_15), "FAIL: indent -1 not fired after exception"
print("[Case 15] PASS: indent -1 fires in finally even when stream raises")

# Case 16: stream_mode=["updates","custom"] and version="v2" passed to html_agent.stream
result, writes, mock_agent = _run_cla([])
_call_kw = mock_agent.stream.call_args.kwargs
assert _call_kw["stream_mode"] == ["updates", "custom"], \
    f"FAIL: stream_mode wrong: {_call_kw.get('stream_mode')}"
assert _call_kw["version"]     == "v2", \
    f"FAIL: version wrong: {_call_kw.get('version')}"
print("[Case 16] PASS: stream_mode and version passed correctly to html_agent.stream")

# Case 17: specs in secondary-orch state forwarded into the payload
_specs = {
    "layout_specification":     {"pages": [{"name": "listing"}]},
    "components_specification": {"pages": [{"pageName": "listing",
        "regionComponents": {"main": [{"id": "navbar", "tag": "nav"}]}}]},
}
result, writes, mock_agent = _run_cla([], state_extra=_specs)
payload = mock_agent.stream.call_args[0][0]
assert payload["layout_specification"]     == _specs["layout_specification"], \
    "FAIL: layout_specification not forwarded"
assert payload["components_specification"] == _specs["components_specification"], \
    "FAIL: components_specification not forwarded"
print("[Case 17] PASS: layout + components specs forwarded to HTML agent payload")

# Case 18: specs absent from state -> payload gets empty dicts (no crash)
result, writes, mock_agent = _run_cla([])
payload = mock_agent.stream.call_args[0][0]
assert payload["layout_specification"] == {},     "FAIL: missing layout should be {}"
assert payload["components_specification"] == {}, "FAIL: missing components should be {}"
print("[Case 18] PASS: missing specs default to empty dicts")

# Case 19: modify intent captures the work order into modification_history
result, writes, mock_agent = _run_cla(
    [], query="fix the navbar colour", intent="modify", target_component="#navbar",
    state_extra={"modification_history": ["[css_agent] earlier fix"]}
)
# Only THIS call's entry is returned. The state key carries an append reducer
# (_merge_work_orders), so returning the accumulated list here would duplicate the
# earlier history whenever CSS and JS run in the same parallel step.
assert result.update["modification_history"] == ["[html_agent] fix the navbar colour"], \
    f"FAIL: expected this call's entry only: {result.update.get('modification_history')}"
print("[Case 19] PASS: modify appends work order to modification_history")

# Case 20: generate intent does NOT touch modification_history
result, writes, mock_agent = _run_cla([], query="build a page")
assert "modification_history" not in result.update, \
    "FAIL: generate mode must not write modification_history"
print("[Case 20] PASS: generate leaves modification_history untouched")

print("\nAll 20 call_html_agent tests passed.")

# ── Outcome reporting (added 2026-08-09 after E2E-SO-01) ─────────────────────
# The tool used to return a hardcoded "Updated html code saved to file system" ToolMessage whatever the sub-agent
# did. In SO-01 the CSS agent wrote nothing and said so in the progress stream,
# while the ToolMessage -- the only channel the orchestrator reads -- claimed a
# save, and the orchestrator duly reported a fix that never happened.
# The harness mocks the stream, so no file is ever written: that IS the case.
import uuid as _oc_uuid_h, os as _oc_os_h

_oc_sid_h  = "utest_" + _oc_uuid_h.uuid4().hex[:8]
_oc_path_h = _PREVIEW_ROOT / f"preview_{_oc_sid_h}.html"
try:
    print("[Outcome 1 · GUARD] No file written -> the tool must NOT claim a save.")
    _r, _, _ = _run_cla([], session_id=_oc_sid_h)
    _m = _r.update["messages"][0].content
    assert "DOES NOT EXIST" in _m and "NOT APPLIED" in _m, _m
    assert "saved to file system" not in _m, "FAIL: the old hardcoded claim survives"
    print("   ", _m[:96])
    print("PASS: an absent artefact is reported as not applied\n")

    print("[Outcome 2 · GUARD] File present but untouched -> reported as unchanged.")
    _PREVIEW_ROOT.mkdir(parents=True, exist_ok=True)
    _oc_path_h.write_text("/* seeded */", encoding="utf-8")
    _r, _, _ = _run_cla([], session_id=_oc_sid_h, intent="modify")
    _m = _r.update["messages"][0].content
    assert "was NOT modified" in _m and "Do NOT report" in _m, _m
    print("   ", _m[:96])
    print("PASS: this is the EXACT SO-01 shape, now reported truthfully\n")

    print("[Outcome 3 · NORMAL] A real write is reported as an update.")
    _oc_before_h = _preview_fingerprint(_oc_sid_h, "html")
    _oc_path_h.write_text("/* seeded and then some */", encoding="utf-8")
    _m = _artifact_outcome("HTML Agent", "html", _oc_sid_h, _oc_before_h,
                           _preview_fingerprint(_oc_sid_h, "html"))
    assert "updated" in _m and "->" in _m, _m
    print("   ", _m[:96])
    print("PASS: a genuine change reads as a change\n")
finally:
    if _oc_path_h.exists():
        _oc_os_h.remove(_oc_path_h)

print("call_html_agent: 3 outcome-reporting cases passed.")
