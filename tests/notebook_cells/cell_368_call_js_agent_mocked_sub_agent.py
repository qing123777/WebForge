# Ported from fyp.ipynb cell 368 (ticket 05). The notebook is frozen;
# edit this file. Run by tests/test_notebook_cells.py.
# Rescued (ticket 05): the notebook marked this cell LIVE-LLM, so it never ran
# offline. It makes no model call (the model is scripted or mocked).
from types import SimpleNamespace
from unittest.mock import MagicMock

def _run_cja(chunks, query="build interactions", session_id="s002",
             tool_call_id="tc002", state_extra=None, **kw):
    global js_agent, get_stream_writer
    _orig, _orig_gsw = js_agent, get_stream_writer
    _writes, _mock   = [], MagicMock()
    _mock.stream.return_value = iter(chunks)
    try:
        js_agent         = _mock
        get_stream_writer = lambda: (lambda d: _writes.append(d))
        # A plain DICT, because that is what LangGraph passes. This shim used to
        # build a SimpleNamespace, so `state.session_id` worked here and raised
        # AttributeError in production.
        _st = {"session_id": session_id, **(state_extra or {})}
        rt = SimpleNamespace(state=_st, tool_call_id=tool_call_id)
        result = call_js_agent.func(rt, query, **kw)
    finally:
        js_agent, get_stream_writer = _orig, _orig_gsw
    return result, _writes, _mock

# Case 1: default params → payload intent=generate, empty target_component
result, _, mock = _run_cja([])
p = mock.stream.call_args[0][0]
assert p["intent"]           == "generate"
assert p["target_component"] == ""
print("[Case 1] PASS: default params → intent=generate")

# Case 2: modify params forwarded
result, _, mock = _run_cja([], intent="modify", target_component="cart-item")
p = mock.stream.call_args[0][0]
assert p["intent"] == "modify" and p["target_component"] == "cart-item"
print("[Case 2] PASS: modify params forwarded")

# Case 3: session_id from runtime.state
result, _, mock = _run_cja([], session_id="xyz42")
assert mock.stream.call_args[0][0]["session_id"] == "xyz42"
print("[Case 3] PASS: session_id forwarded")

# Case 4: custom chunk forwarded to writer
result, writes, _ = _run_cja([("custom", "js-progress")])
assert "js-progress" in writes
print("[Case 4] PASS: custom chunk forwarded")

# Case 5: indent written at start and end
result, writes, _ = _run_cja([])
indents = [w for w in writes if isinstance(w, dict) and w.get("type") == "indent"]
assert indents[0]["delta"] == 1 and indents[-1]["delta"] == -1
print("[Case 5] PASS: indent +1 start, -1 finally")

# Case 6: ToolMessage content mentions 'JS Agent'
result, _, _ = _run_cja([])
assert "JS Agent" in result.update["messages"][0].content
print("[Case 6] PASS: ToolMessage mentions JS Agent")

# Case 7: target_instance forwarded to payload
result, _, mock = _run_cja([], intent="modify", target_component="cart-item", target_instance=3)
p = mock.stream.call_args[0][0]
assert p["target_instance"] == 3
print("[Case 7] PASS: target_instance forwarded to payload")

# Case 8: interaction_specification forwarded verbatim from orch state
_ixn = {"add-to-cart-button": {"trigger": "click", "action": "increment_cart_count"}}
result, _, mock = _run_cja([], state_extra={"interaction_specification": _ixn})
p = mock.stream.call_args[0][0]
assert p["interaction_specification"] == _ixn, "FAIL: interaction spec not forwarded"
print("[Case 8] PASS: interaction_specification forwarded verbatim")

# Case 9: missing spec defaults to empty dict (no crash)
result, _, mock = _run_cja([])
p = mock.stream.call_args[0][0]
assert p["interaction_specification"] == {}, "FAIL: missing spec should be {}"
print("[Case 9] PASS: missing interaction spec defaults to {}")

# Case 10: modify intent captures the work order into modification_history
result, _, mock = _run_cja([], query="scope a fix", intent="modify",
                       state_extra={"modification_history": []})
assert result.update["modification_history"] == ["[js_agent] scope a fix"], \
    f"FAIL: {result.update.get('modification_history')}"
print("[Case 10] PASS: modify appends work order")

# Case 11: generate intent does NOT touch modification_history
result, _, mock = _run_cja([])
assert "modification_history" not in result.update
print("[Case 11] PASS: generate leaves modification_history untouched")

print("\nAll 11 call_js_agent tests passed.")


# ── Suggestion 2 (batching) additions ───────────────────────────────────────
# Case 12: a target_components list is forwarded; target_component is its head
result, _, mock = _run_cja([], intent="modify",
                           target_components=["comp-a", "comp-b", "comp-c"])
p = mock.stream.call_args[0][0]
assert p["target_components"] == ["comp-a", "comp-b", "comp-c"]
assert p["target_component"] == "comp-a", "primary must be the first of the list"
print("[Case 12] PASS: target_components forwarded; target_component is the head")

# Case 13: a lone target_component still becomes a one-item list (back-compat)
result, _, mock = _run_cja([], intent="modify", target_component="comp-a")
p = mock.stream.call_args[0][0]
assert p["target_components"] == ["comp-a"] and p["target_component"] == "comp-a"
print("[Case 13] PASS: single target_component normalized to a one-item list")

# Case 14: the batch is capped at _MODIFY_BATCH_CAP
_many = [f"c{i}" for i in range(_MODIFY_BATCH_CAP + 4)]
result, _, mock = _run_cja([], intent="modify", target_components=_many)
p = mock.stream.call_args[0][0]
assert p["target_components"] == _many[:_MODIFY_BATCH_CAP], "batch must be capped"
assert len(p["target_components"]) == _MODIFY_BATCH_CAP
print(f"[Case 14] PASS: batch capped at _MODIFY_BATCH_CAP ({_MODIFY_BATCH_CAP})")

# Case 15: generate mode yields an empty target_components list
result, _, mock = _run_cja([])
p = mock.stream.call_args[0][0]
assert p["target_components"] == []
print("[Case 15] PASS: generate mode -> empty target_components")

print("call_js_agent batching cases passed.")

# ── Outcome reporting (added 2026-08-09 after E2E-SO-01) ─────────────────────
# The tool used to return a hardcoded "JS file saved to file system" ToolMessage whatever the sub-agent
# did. In SO-01 the CSS agent wrote nothing and said so in the progress stream,
# while the ToolMessage -- the only channel the orchestrator reads -- claimed a
# save, and the orchestrator duly reported a fix that never happened.
# The harness mocks the stream, so no file is ever written: that IS the case.
import uuid as _oc_uuid_j, os as _oc_os_j

_oc_sid_j  = "utest_" + _oc_uuid_j.uuid4().hex[:8]
_oc_path_j = _PREVIEW_ROOT / f"preview_{_oc_sid_j}.js"
try:
    print("[Outcome 1 · GUARD] No file written -> the tool must NOT claim a save.")
    _r, _, _ = _run_cja([], session_id=_oc_sid_j)
    _m = _r.update["messages"][0].content
    assert "DOES NOT EXIST" in _m and "NOT APPLIED" in _m, _m
    assert "saved to file system" not in _m, "FAIL: the old hardcoded claim survives"
    print("   ", _m[:96])
    print("PASS: an absent artefact is reported as not applied\n")

    print("[Outcome 2 · GUARD] File present but untouched -> reported as unchanged.")
    _PREVIEW_ROOT.mkdir(parents=True, exist_ok=True)
    _oc_path_j.write_text("/* seeded */", encoding="utf-8")
    _r, _, _ = _run_cja([], session_id=_oc_sid_j, intent="modify")
    _m = _r.update["messages"][0].content
    assert "was NOT modified" in _m and "Do NOT report" in _m, _m
    print("   ", _m[:96])
    print("PASS: this is the EXACT SO-01 shape, now reported truthfully\n")

    print("[Outcome 3 · NORMAL] A real write is reported as an update.")
    _oc_before_j = _preview_fingerprint(_oc_sid_j, "js")
    _oc_path_j.write_text("/* seeded and then some */", encoding="utf-8")
    _m = _artifact_outcome("JS Agent", "js", _oc_sid_j, _oc_before_j,
                           _preview_fingerprint(_oc_sid_j, "js"))
    assert "updated" in _m and "->" in _m, _m
    print("   ", _m[:96])
    print("PASS: a genuine change reads as a change\n")
finally:
    if _oc_path_j.exists():
        _oc_os_j.remove(_oc_path_j)

print("call_js_agent: 3 outcome-reporting cases passed.")
