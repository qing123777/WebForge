# Ported from fyp.ipynb cell 364 (ticket 05). The notebook is frozen;
# edit this file. Run by tests/test_notebook_cells.py.
# Rescued (ticket 05): the notebook marked this cell LIVE-LLM, so it never ran
# offline. It makes no model call (the model is scripted or mocked).
from types import SimpleNamespace
from unittest.mock import MagicMock

def _run_cca(chunks, query="build styles", session_id="s001",
             tool_call_id="tc001", state_extra=None, **kw):
    global css_agent, get_stream_writer
    _orig, _orig_gsw = css_agent, get_stream_writer
    _writes, _mock   = [], MagicMock()
    _mock.stream.return_value = iter(chunks)
    try:
        css_agent        = _mock
        get_stream_writer = lambda: (lambda d: _writes.append(d))
        # A plain DICT, because that is what LangGraph passes. This shim used to
        # build a SimpleNamespace, so `state.session_id` worked here and raised
        # AttributeError in production.
        _st = {"session_id": session_id, **(state_extra or {})}
        rt = SimpleNamespace(state=_st, tool_call_id=tool_call_id)
        result = call_css_agent.func(rt, query, **kw)
    finally:
        css_agent, get_stream_writer = _orig, _orig_gsw
    return result, _writes, _mock

# Case 1: default params → payload has intent=generate, empty target_component
result, _, mock = _run_cca([])
p = mock.stream.call_args[0][0]
assert p["intent"]           == "generate"
assert p["target_component"] == ""
print("[Case 1] PASS: default params → intent=generate, empty target_component")

# Case 2: modification params flow into payload
result, _, mock = _run_cca([], intent="modify", target_component="product-card")
p = mock.stream.call_args[0][0]
assert p["intent"]           == "modify"
assert p["target_component"] == "product-card"
print("[Case 2] PASS: modify params flow into payload")

# Case 3: session_id from runtime.state in payload
result, _, mock = _run_cca([], session_id="abc99")
p = mock.stream.call_args[0][0]
assert p["session_id"] == "abc99"
print("[Case 3] PASS: session_id forwarded to payload")

# Case 4: custom chunk forwarded to writer
result, writes, _ = _run_cca([("custom", "css-progress")])
assert "css-progress" in writes
print("[Case 4] PASS: custom chunk forwarded to writer")

# Case 5: indent +1 at start, -1 in finally
result, writes, _ = _run_cca([])
indents = [w for w in writes if isinstance(w, dict) and w.get("type") == "indent"]
assert indents[0]["delta"]  ==  1
assert indents[-1]["delta"] == -1
print("[Case 5] PASS: indent +1 start, -1 finally")

# Case 6: ToolMessage content mentions 'CSS Agent'
result, _, _ = _run_cca([])
assert "CSS Agent" in result.update["messages"][0].content
print("[Case 6] PASS: ToolMessage mentions CSS Agent")

# Case 7: target_instance forwarded to payload
result, _, mock = _run_cca([], intent="modify", target_component="navbar", target_instance=2)
p = mock.stream.call_args[0][0]
assert p["target_instance"] == 2
print("[Case 7] PASS: target_instance forwarded to payload")

# Case 8: decoration_specification forwarded verbatim from orch state
_deco = {"add-to-cart-btn": {"baseStyles": {"background-color": "#1a73e8"}}}
result, _, mock = _run_cca([], state_extra={"decoration_specification": _deco})
p = mock.stream.call_args[0][0]
assert p["decoration_specification"] == _deco, "FAIL: decoration spec not forwarded"
print("[Case 8] PASS: decoration_specification forwarded verbatim")

# Case 9: missing spec defaults to empty dict (no crash)
result, _, mock = _run_cca([])
p = mock.stream.call_args[0][0]
assert p["decoration_specification"] == {}, "FAIL: missing spec should be {}"
print("[Case 9] PASS: missing decoration spec defaults to {}")

# Case 10: modify intent captures the work order into modification_history
result, _, mock = _run_cca([], query="scope a fix", intent="modify",
                       state_extra={"modification_history": []})
assert result.update["modification_history"] == ["[css_agent] scope a fix"], \
    f"FAIL: {result.update.get('modification_history')}"
print("[Case 10] PASS: modify appends work order")

# Case 11: generate intent does NOT touch modification_history
result, _, mock = _run_cca([])
assert "modification_history" not in result.update
print("[Case 11] PASS: generate leaves modification_history untouched")

print("\nAll 11 call_css_agent tests passed.")


# ── Suggestion 2 (batching) additions ───────────────────────────────────────
# Case 12: a target_components list is forwarded; target_component is its head
result, _, mock = _run_cca([], intent="modify",
                           target_components=["comp-a", "comp-b", "comp-c"])
p = mock.stream.call_args[0][0]
assert p["target_components"] == ["comp-a", "comp-b", "comp-c"]
assert p["target_component"] == "comp-a", "primary must be the first of the list"
print("[Case 12] PASS: target_components forwarded; target_component is the head")

# Case 13: a lone target_component still becomes a one-item list (back-compat)
result, _, mock = _run_cca([], intent="modify", target_component="comp-a")
p = mock.stream.call_args[0][0]
assert p["target_components"] == ["comp-a"] and p["target_component"] == "comp-a"
print("[Case 13] PASS: single target_component normalized to a one-item list")

# Case 14: the batch is capped at _MODIFY_BATCH_CAP
_many = [f"c{i}" for i in range(_MODIFY_BATCH_CAP + 4)]
result, _, mock = _run_cca([], intent="modify", target_components=_many)
p = mock.stream.call_args[0][0]
assert p["target_components"] == _many[:_MODIFY_BATCH_CAP], "batch must be capped"
assert len(p["target_components"]) == _MODIFY_BATCH_CAP
print(f"[Case 14] PASS: batch capped at _MODIFY_BATCH_CAP ({_MODIFY_BATCH_CAP})")

# Case 15: generate mode yields an empty target_components list
result, _, mock = _run_cca([])
p = mock.stream.call_args[0][0]
assert p["target_components"] == []
print("[Case 15] PASS: generate mode -> empty target_components")

print("call_css_agent batching cases passed.")

# ── Outcome reporting (added 2026-08-09 after E2E-SO-01) ─────────────────────
# The tool used to return a hardcoded "CSS file saved to file system" ToolMessage whatever the sub-agent
# did. In SO-01 the CSS agent wrote nothing and said so in the progress stream,
# while the ToolMessage -- the only channel the orchestrator reads -- claimed a
# save, and the orchestrator duly reported a fix that never happened.
# The harness mocks the stream, so no file is ever written: that IS the case.
import uuid as _oc_uuid_c, os as _oc_os_c

_oc_sid_c  = "utest_" + _oc_uuid_c.uuid4().hex[:8]
_oc_path_c = _PREVIEW_ROOT / f"preview_{_oc_sid_c}.css"
try:
    print("[Outcome 1 · GUARD] No file written -> the tool must NOT claim a save.")
    _r, _, _ = _run_cca([], session_id=_oc_sid_c)
    _m = _r.update["messages"][0].content
    assert "DOES NOT EXIST" in _m and "NOT APPLIED" in _m, _m
    assert "saved to file system" not in _m, "FAIL: the old hardcoded claim survives"
    print("   ", _m[:96])
    print("PASS: an absent artefact is reported as not applied\n")

    print("[Outcome 2 · GUARD] File present but untouched -> reported as unchanged.")
    _PREVIEW_ROOT.mkdir(parents=True, exist_ok=True)
    _oc_path_c.write_text("/* seeded */", encoding="utf-8")
    _r, _, _ = _run_cca([], session_id=_oc_sid_c, intent="modify")
    _m = _r.update["messages"][0].content
    assert "was NOT modified" in _m and "Do NOT report" in _m, _m
    print("   ", _m[:96])
    print("PASS: this is the EXACT SO-01 shape, now reported truthfully\n")

    print("[Outcome 3 · NORMAL] A real write is reported as an update.")
    _oc_before_c = _preview_fingerprint(_oc_sid_c, "css")
    _oc_path_c.write_text("/* seeded and then some */", encoding="utf-8")
    _m = _artifact_outcome("CSS Agent", "css", _oc_sid_c, _oc_before_c,
                           _preview_fingerprint(_oc_sid_c, "css"))
    assert "updated" in _m and "->" in _m, _m
    print("   ", _m[:96])
    print("PASS: a genuine change reads as a change\n")
finally:
    if _oc_path_c.exists():
        _oc_os_c.remove(_oc_path_c)

print("call_css_agent: 3 outcome-reporting cases passed.")
