# Ported from fyp.ipynb cell 325 (ticket 05). The notebook is frozen;
# edit this file. Run by tests/test_notebook_cells.py.
# Unit tests: Test Generation agent middleware
# (test_gen_agent_progress / _tg_remaining / test_gen_before_model_progress /
#  test_gen_prompt_selector / test_gen_tool_progress)
#
# These are the REAL decorated middleware objects, not re-implemented copies.
# @before_agent/@before_model/@wrap_tool_call expose their hook as a method, and
# @dynamic_prompt compiles into a wrap_model_call hook, so each is invoked the
# way the agent runtime invokes it.
#
# get_stream_writer() raises outside a LangGraph runnable context, so the tests
# swap it for a collector. That is the ONLY substitution.
from types import SimpleNamespace

_real_gsw_tg = get_stream_writer
_emitted_tg  = []


def _run_tg_mw(fn, *args):
    """Call a middleware hook with a captured stream writer."""
    global get_stream_writer
    _emitted_tg.clear()
    get_stream_writer = lambda: _emitted_tg.append          # noqa: E731
    try:
        result = fn(*args)
    finally:
        get_stream_writer = _real_gsw_tg
    return list(_emitted_tg), result


_RT_tg = SimpleNamespace()          # progress hooks never touch runtime

# navbar (plain) + add-to-cart-button (1 declared state + 1 declared event)
# -> 2 component targets + 1 state target + 1 event target = 4 in total.
_TGM_SPEC = {"pages": [{"pageName": "plp", "regionComponents": {"main": [
    {"id": "navbar", "tag": "nav"},
    {"id": "add-to-cart-button", "tag": "button", "className": "add-to-cart-btn",
     "states": [{"name": "disabled"}], "events": [{"event": "click"}]},
]}}]}


def _tgm_tc(tid, comp, **extra):
    return {"id": tid, "component": comp, "description": "d",
            "action": "assert_visible", "selector": "s", "expected": "",
            "passed": None, **extra}


_TGM_FULL = [
    _tgm_tc("TC-001", "navbar"),
    _tgm_tc("TC-002", "add-to-cart-button", covers_state="disabled"),
    _tgm_tc("TC-003", "add-to-cart-button", action="click",
            selector=".add-to-cart-btn", covers_event="click"),
]

# ── test_gen_agent_progress (@before_agent) ─────────────────────────────────
# Case 1 [NORMAL] entry announcement fires once per agent invocation
msgs, ret = _run_tg_mw(test_gen_agent_progress.before_agent, {}, _RT_tg)
print("[Case 1 · NORMAL] before_agent announces the agent has started")
print("  emitted:", msgs)
assert len(msgs) == 1, f"FAIL: expected exactly 1 message, got {msgs}"
assert "[Test Gen Agent]" in msgs[0], "FAIL: message is not tagged with the agent name"
print("PASS: exactly one tagged start message emitted\n")

# Case 2 [INVARIANT] the hook must not write to state
print("[Case 2 · INVARIANT] before_agent returns None, so no state key is overwritten")
assert ret is None, f"FAIL: progress middleware returned a state update: {ret!r}"
print("PASS: returns None - progress reporting has no side effect on state\n")


# ── _tg_remaining (the label's source of truth) ─────────────────────────────
# Case 3 [NORMAL] no spec means nothing to complete
print("[Case 3 · NORMAL] no components_specification -> 0 remaining")
assert _tg_remaining({}) == 0, "FAIL: invented targets without a spec"
assert _tg_remaining({"components_specification": {}}) == 0
print("PASS: an absent spec yields 0, so the label stays silent\n")

# Case 4 [NORMAL] an empty suite leaves every target open
_left = _tg_remaining({"components_specification": _TGM_SPEC, "test_cases": []})
print(f"[Case 4 · NORMAL] empty suite against the fixture spec -> {_left} remaining")
assert _left == 4, f"FAIL: expected 4 (2 components + 1 state + 1 event), got {_left}"
print("PASS: counts components AND declared states AND declared events\n")

# Case 5 [NORMAL] covering one component closes exactly one target
_left = _tg_remaining({"components_specification": _TGM_SPEC,
                       "test_cases": [_tgm_tc("TC-001", "navbar")]})
print(f"[Case 5 · NORMAL] one component covered -> {_left} remaining")
assert _left == 3, f"FAIL: expected 3, got {_left}"
print("PASS: the count drops by exactly the targets that were closed\n")

# Case 6 [NORMAL] full coverage closes everything
_left = _tg_remaining({"components_specification": _TGM_SPEC, "test_cases": _TGM_FULL})
print(f"[Case 6 · NORMAL] component+state+event all tagged -> {_left} remaining")
assert _left == 0, f"FAIL: expected 0, got {_left}"
print("PASS: covers_state / covers_event tags are what close state and event targets\n")

# Case 7 [EDGE] an untagged case does NOT close a state or event target
_untagged = [_tgm_tc("TC-001", "navbar"), _tgm_tc("TC-002", "add-to-cart-button")]
_left = _tg_remaining({"components_specification": _TGM_SPEC, "test_cases": _untagged})
print(f"[Case 7 · EDGE] both components covered but untagged -> {_left} remaining")
assert _left == 2, f"FAIL: expected 2 (the state and the event), got {_left}"
print("PASS: touching a component is not the same as exercising its state/event\n")

# Case 8 [EDGE] a JSON-string spec is coerced, and state=None does not raise
import json as _tgm_json
_left = _tg_remaining({"components_specification": _tgm_json.dumps(_TGM_SPEC),
                       "test_cases": []})
print(f"[Case 8 · EDGE] JSON-string spec coerced -> {_left} remaining; state=None -> "
      f"{_tg_remaining(None)}")
assert _left == 4, f"FAIL: string spec silently disabled the count: {_left}"
assert _tg_remaining(None) == 0
print("PASS: string specs still counted; no AttributeError on a missing state\n")


# ── test_gen_before_model_progress (@before_model) ──────────────────────────
_BM_tg = test_gen_before_model_progress.before_model

# Case 9 [NORMAL] the first turn announces generation
msgs, ret = _run_tg_mw(_BM_tg, {"components_specification": _TGM_SPEC,
                                "test_cases": []}, _RT_tg)
print("[Case 9 · NORMAL] no test cases yet -> the run start is announced")
print("  emitted:", msgs)
assert msgs == ["   [Test Gen Agent] Generating test suite..."], f"FAIL: got {msgs}"
assert ret is None
print("PASS: generation announced at the start of the run\n")

# Case 10 [NORMAL] a later turn with gaps reports progress AND what is left
msgs, ret = _run_tg_mw(_BM_tg, {"components_specification": _TGM_SPEC,
                                "test_cases": [_tgm_tc("TC-001", "navbar")]}, _RT_tg)
print("[Case 10 · NORMAL] chunked run mid-flight reports written and remaining")
print("  emitted:", msgs)
assert msgs == ["   [Test Gen Agent] Generating more test cases "
                "(1 written, 3 target(s) left)..."], f"FAIL: got {msgs}"
assert ret is None
print("PASS: the mid-run turns are visible (the old hook went quiet here)\n")

# Case 11 [INVARIANT] once coverage is complete the hook is SILENT. The wrap-up
# turn does no more generation, and a guessed label would promise work that
# never comes - the same lesson the developer-agent hooks learned live.
msgs, ret = _run_tg_mw(_BM_tg, {"components_specification": _TGM_SPEC,
                                "test_cases": _TGM_FULL}, _RT_tg)
print("[Case 11 · INVARIANT] coverage complete -> no label on the wrap-up turn")
print("  emitted:", msgs)
assert msgs == [], f"FAIL: labelled a turn that does no generation: {msgs}"
assert ret is None
print("PASS: no label ever promises work that will not happen\n")

# Case 12 [EDGE] cases written but no spec -> nothing to report, stay silent
msgs, _ = _run_tg_mw(_BM_tg, {"test_cases": [_tgm_tc("TC-001", "navbar")]}, _RT_tg)
print("[Case 12 · EDGE] test cases but no spec -> silent (nothing measurable left)")
assert msgs == [], f"FAIL: got {msgs}"
print("PASS: a spec-less run does not fabricate a remaining count\n")

# Case 13 [EDGE] state=None is treated as a fresh run, not an error
msgs, ret = _run_tg_mw(_BM_tg, None, _RT_tg)
print("[Case 13 · EDGE] state=None handled by the (state or {}) guard")
print("  emitted:", msgs, "| returned:", repr(ret))
assert msgs == ["   [Test Gen Agent] Generating test suite..."] and ret is None
print("PASS: no AttributeError on a missing state\n")


# ── test_gen_prompt_selector (@dynamic_prompt) ─────────────────────────────
# @dynamic_prompt compiles into a wrap_model_call hook, so the tests go through
# that hook and read back the system message it installs.
_MODEL_SENTINEL_tg = object()


class _FakeRequest_tg:
    """Stand-in for ModelRequest: records the system message the hook installs."""

    def __init__(self, state):
        self.state = state
        self.system_message = None

    def override(self, system_message=None, **kwargs):
        self.system_message = system_message
        return self


def _select_tg_prompt(state):
    req, seen = _FakeRequest_tg(state), {}

    def _handler(request):
        seen["request"] = request
        return _MODEL_SENTINEL_tg

    out = test_gen_prompt_selector.wrap_model_call(req, _handler)
    assert seen.get("request") is req, "FAIL: middleware never called the model handler"
    return req.system_message.content, out


_TGM_INTER = {"pages": [{"pageName": "plp", "flows": [
    {"name": "atc", "trigger": {"event": "click", "targetId": "add-to-cart-button"},
     "actions": [{"type": "addToCart"}],
     "stateTransitions": [{"componentId": "add-to-cart-button", "toState": "disabled"}]}]}]}
_TGM_DECO = {"pages": [{"pageName": "plp", "componentDecorations": [
    {"componentId": "add-to-cart-button", "className": "add-to-cart-btn",
     "baseStyles": {"color": "#ffffff"},
     "stateVariants": [{"stateName": "hover", "styles": {"opacity": "0.8"}}]}]}]}

# Case 14 [NORMAL] the sheet is appended to the base prompt, joined by id
_prompt, _out = _select_tg_prompt({"components_specification": _TGM_SPEC,
                                   "interaction_specification": _TGM_INTER,
                                   "decoration_specification": _TGM_DECO})
print("[Case 14 · NORMAL] the pre-joined sheet is appended to the base prompt")
assert _prompt.startswith(_test_gen_system_prompt), "FAIL: base prompt was replaced, not extended"
assert "Pre-joined component sheet" in _prompt, "FAIL: sheet missing"
assert "is a BASELINE fact, not a transition" in _test_gen_system_prompt, \
    "FAIL: Rule B (resting-state must NOT be tagged covers_state) missing from Test Gen prompt"
assert "Copy each value VERBATIM from the decoration spec" in _test_gen_system_prompt, \
    "FAIL: assert_css copy-verbatim rule (never compute a px value) missing from Test Gen prompt"
assert "A TRANSIENT / in-flight state" in _test_gen_system_prompt, \
    "FAIL: transient-state rule (assert only the stable end-state) missing from Test Gen prompt"
assert _out is _MODEL_SENTINEL_tg, "FAIL: model call was not forwarded"
print("PASS: base prompt preserved, sheet appended, model call forwarded\n")

# Case 15 [NORMAL] each component is joined to ITS OWN styling and behaviour
print("[Case 15 · NORMAL] joins resolve by componentId / trigger.targetId")
assert ".add-to-cart-btn" in _prompt and "#navbar" in _prompt, "FAIL: Selector Contract not applied"
assert "color=#ffffff" in _prompt, "FAIL: decoration not joined by componentId"
assert "opacity=0.8" in _prompt, "FAIL: state variant not joined"
assert "flow 'atc'" in _prompt and "->disabled" in _prompt, "FAIL: interaction not joined"
print("PASS: styling and behaviour are matched to the right component in Python\n")

# Case 16 [EDGE] no components -> the base prompt is handed over unchanged
_prompt_empty, _ = _select_tg_prompt({})
print("[Case 16 · EDGE] a spec-less run gets the base prompt, unchanged")
assert _prompt_empty == _test_gen_system_prompt, "FAIL: appended a sheet with no components"
assert _build_component_join_sheet({"components_specification": {}}) == ""
print("PASS: the sheet is omitted rather than emitted empty\n")


# ── test_gen_tool_progress (@wrap_tool_call) ───────────────────────────────
_HANDLER_SENTINEL_tg = object()


def _call_tg_tool_mw(tool_call, result=_HANDLER_SENTINEL_tg, raises=None):
    def _handler(request):
        if raises:
            raise raises
        return result
    return _run_tg_mw(test_gen_tool_progress.wrap_tool_call,
                      SimpleNamespace(tool_call=tool_call), _handler)


def _cmd(content):
    """A Command-shaped result carrying one ToolMessage."""
    return SimpleNamespace(update={"messages": [SimpleNamespace(content=content)]})


# Case 17 [NORMAL] a saved-but-incomplete batch announces the call only. The
# validator's own text (counts, missing targets, stop instruction) is written for
# the MODEL and is far too detailed for the progress stream; the remaining work is
# already narrated by the before_model hook.
msgs, out = _call_tg_tool_mw({"name": "store_test_cases"},
                             _cmd("Saved 1 test case(s) (suite now 1). Coverage "
                                  "INCOMPLETE \u2014 keep going: add-to-cart-button"))
print("[Case 17 \u00b7 NORMAL] an incomplete batch does not leak validator detail")
print("  emitted:", msgs)
assert msgs == ["   [Test Gen Agent] Storing test cases..."], f"FAIL: got {msgs}"
print("PASS: only the call is announced; the gap list stays out of the stream\n")

# Case 18 [NORMAL] completion emits one plain, user-facing line
msgs, _ = _call_tg_tool_mw({"name": "store_test_cases"},
                           _cmd("Saved 11 test case(s) (suite now 11). SUITE COMPLETE "
                                "\u2014 every component, state, and event in the spec is "
                                "covered. Stop calling store_test_cases."))
print("[Case 18 \u00b7 NORMAL] completion is reported in plain words")
print("  emitted:", msgs)
assert msgs[-1] == "   [Test Gen Agent] All test cases have been saved.", f"FAIL: {msgs}"
assert not any("SUITE COMPLETE" in m for m in msgs), "FAIL: raw validator text leaked"
assert not any("Stop calling" in m for m in msgs), "FAIL: model-facing instruction leaked"
print("PASS: the finished signal is short and carries no validator jargon\n")

# Case 19 [EDGE] a plain .content result is read too (not only Command.update)
msgs, _ = _call_tg_tool_mw({"name": "store_test_cases"},
                           SimpleNamespace(content="Saved 3. SUITE COMPLETE. Stop."))
print("[Case 19 \u00b7 EDGE] a result exposing .content instead of .update still reports")
assert msgs[-1] == "   [Test Gen Agent] All test cases have been saved.", f"FAIL: {msgs}"
print("PASS: both result shapes are handled\n")

# Case 20 [EDGE] a rejection or an unrecognised result must not raise or invent a line
for _lbl, _res in (("schema rejection", _cmd("Test case at index 0 must be a dict.")),
                   ("unknown shape",    object())):
    msgs, out = _call_tg_tool_mw({"name": "store_test_cases"}, _res)
    assert msgs == ["   [Test Gen Agent] Storing test cases..."], f"FAIL: {_lbl} -> {msgs}"
print("[Case 20 \u00b7 EDGE] rejections and unknown result shapes are tolerated")
print("PASS: the announce line stands alone; nothing is fabricated\n")

# Case 21 [EDGE] an unmapped tool name produces no line but still runs
msgs, out = _call_tg_tool_mw({"name": "some_other_tool"})
print("[Case 21 · EDGE] unmapped tool name produces no line but still runs")
assert msgs == [], f"FAIL: invented a progress line for an unmapped tool: {msgs}"
assert out is _HANDLER_SENTINEL_tg, "FAIL: unmapped tool was not executed"
print("PASS: unmapped tools pass through untouched\n")

# Case 22 [INVARIANT] a malformed tool_call must never swallow the tool call
for _lbl, _bad in (("None", None), ("a string", "not-a-dict")):
    msgs, out = _call_tg_tool_mw(_bad)
    assert out is _HANDLER_SENTINEL_tg, f"FAIL: tool_call={_lbl} swallowed the call"
    assert msgs == []
print("[Case 22 · INVARIANT] malformed tool_call never blocks the underlying tool")
print("PASS: cosmetic middleware cannot cause a silent no-op\n")


# Case 23 [INFRA] the writer is restored even when the wrapped tool raises,
# and the tool's exception propagates unmasked.
class _ToolExploded_tg(RuntimeError):
    pass


_caught_tg = None
try:
    _call_tg_tool_mw({"name": "store_test_cases"}, raises=_ToolExploded_tg("tool failed"))
except _ToolExploded_tg as _e:
    _caught_tg = _e
print("[Case 23 · INFRA] a failing tool propagates; middleware adds no masking")
assert _caught_tg is not None, "FAIL: middleware swallowed the tool's exception"
assert get_stream_writer is _real_gsw_tg, "FAIL: stream writer left patched"
print("PASS: exception propagated, real stream writer restored\n")

print("All 23 cases passed - Test Generation agent middleware "
      "(4 hooks: before_agent, before_model, dynamic_prompt, wrap_tool_call).")
