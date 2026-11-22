# Ported from fyp.ipynb cell 329 (ticket 05). The notebook is frozen;
# edit this file. Run by tests/test_notebook_cells.py.
# Needs: cell 182 (it defines ScriptedChatModel, _run_scripted, _assert_state_fields).
# Rescued (ticket 05): the notebook marked this cell LIVE-LLM, so it never ran
# offline. It makes no model call (the model is scripted or mocked).
# ═══════════════════════════════════════════════════════════════════════════
# TIER 2 — TURN-BASED EVALUATION: TEST GENERATION AGENT  (4 scenarios, NO real LLM)
#
# Exercises the Test Generation sub-agent as a whole — chunked generation, the
# accumulate-and-report loop, schema rejection with recovery, and the dedup-by-id
# reducer — with every model reply pre-scripted. Free to run, deterministic.
#
#   TB-TG-1  Happy path            — one batch covers everything, SUITE COMPLETE
#   TB-TG-2  Chunked generation    — batch 1 INCOMPLETE, batch 2 completes it
#   TB-TG-3  Schema rejection      — malformed batch NOT saved, retry accepted
#   TB-TG-4  Reducer dedup by id   — a re-sent id REPLACES, it does not duplicate
#
# Requires the Tier-2 harness cell (ScriptedChatModel) to have been run.
# Unlike the developer agents there is no filesystem or linter here, so nothing
# is mocked at all: the real store_test_cases validator runs on every batch.
# ═══════════════════════════════════════════════════════════════════════════
import uuid as _tgt_uuid

_assert_state_fields(
    TestGenState,
    ["test_cases", "components_specification", "interaction_specification",
     "decoration_specification"],
    "Test Generation",
)

# navbar (plain) + add-to-cart-button (1 declared state + 1 declared event)
_TGT_SPEC = {"pages": [{"pageName": "plp", "regionComponents": {"main": [
    {"id": "navbar", "tag": "nav"},
    {"id": "add-to-cart-button", "tag": "button", "className": "add-to-cart-btn",
     "states": [{"name": "disabled"}], "events": [{"event": "click"}]},
]}}]}

_TGT_TOOLS = [store_test_cases]
_TGT_MW = [test_gen_prompt_selector, test_gen_agent_progress,
           test_gen_before_model_progress, test_gen_tool_progress]


def _tgt_tc(tid, comp, action="assert_visible", sel="s", exp="", **extra):
    return {"id": tid, "component": comp, "description": "d", "action": action,
            "selector": sel, "expected": exp, "passed": None, **extra}


# The three cases that together satisfy component + state + event coverage.
_TGT_NAVBAR = _tgt_tc("TC-001", "navbar", sel="#navbar")
_TGT_STATE  = _tgt_tc("TC-002", "add-to-cart-button", action="assert_attribute",
                      sel=".add-to-cart-btn", exp="aria-disabled=true",
                      covers_state="disabled")
_TGT_EVENT  = _tgt_tc("TC-003", "add-to-cart-button", action="click",
                      sel=".add-to-cart-btn", covers_event="click")
_TGT_FULL = [_TGT_NAVBAR, _TGT_STATE, _TGT_EVENT]


def _tgt_payload(sid, query="Generate the test suite for the PLP."):
    """Mirrors call_test_gen_agent's payload construction exactly."""
    return {
        "messages":                  [{"role": "user", "content": query}],
        "user_query":                query,
        "layout_specification":      {},
        "components_specification":  _TGT_SPEC,
        "interaction_specification": {},
        "decoration_specification":  {},
        "test_cases":                [],
        "session_id":                sid,
    }


def _run_tgt(agent, payload, sid):
    """Stream a scripted run, ACCUMULATING test_cases the way the reducer does.

    The shared _run_scripted overwrites each state key, which is correct for the
    developer agents but wrong here: `test_cases` carries a dedup-by-id reducer
    and the "updates" stream yields one raw BATCH per store_test_cases call, not
    the merged channel. Overwriting would keep only the last batch and make a
    chunked run look like it lost everything but the final chunk.
    """
    state, calls, tool_msgs = {}, [], []
    for chunk in agent.stream(
        payload, stream_mode=["updates", "custom"], version="v2",
        config={"configurable": {"session_id": sid}},
    ):
        ctype, data = (chunk if isinstance(chunk, tuple)
                       else (chunk.get("type"), chunk.get("data")))
        if ctype != "updates" or not isinstance(data, dict):
            continue
        for _step, up in data.items():
            if not isinstance(up, dict):
                continue
            for k, v in up.items():
                if k == "messages":
                    for m in (v or []):
                        for call in (getattr(m, "tool_calls", None) or []):
                            calls.append(call["name"])
                        if isinstance(m, _LCToolMessage):
                            tool_msgs.append(str(m.content))
                elif k == "test_cases":
                    state["test_cases"] = _merge_test_cases(state.get("test_cases", []), v)
                else:
                    state[k] = v
    return state, calls, tool_msgs


_tgt_passed = 0


# ── TB-TG-1  Happy path ─────────────────────────────────────────────────────
print("=" * 68)
print("TB-TG-1  Happy path — one batch covers component + state + event")
print("=" * 68)
_sid = _tgt_uuid.uuid4().hex[:8]
_script = [_tc("store_test_cases", {"test_cases": _TGT_FULL}), _done()]
_model, _agent = _scripted_agent(_script, _TGT_TOOLS, _TGT_MW, TestGenState,
                                 agent_var="test_gen_agent")
_st, _calls, _msgs = _run_tgt(_agent, _tgt_payload(_sid), _sid)

assert _calls == ["store_test_cases"], f"TB-TG-1 FAIL: tool order was {_calls}"
assert [t["id"] for t in _st.get("test_cases", [])] == ["TC-001", "TC-002", "TC-003"], \
    f"TB-TG-1 FAIL: suite is {_st.get('test_cases')}"
assert any("SUITE COMPLETE" in m for m in _msgs), \
    f"TB-TG-1 FAIL: never reported SUITE COMPLETE -- {_msgs}"
assert _model.turns_used == len(_script), "TB-TG-1 FAIL: unexpected model turns"
_tgt_passed += 1
print(f"PASS TB-TG-1  1 store call, 3 cases, SUITE COMPLETE on the first batch\n")


# ── TB-TG-2  Chunked generation ─────────────────────────────────────────────
print("=" * 68)
print("TB-TG-2  Chunked generation — batch 1 incomplete, batch 2 completes it")
print("=" * 68)
_sid = _tgt_uuid.uuid4().hex[:8]
_script = [
    _tc("store_test_cases", {"test_cases": [_TGT_NAVBAR]}),            # -> INCOMPLETE
    _tc("store_test_cases", {"test_cases": [_TGT_STATE, _TGT_EVENT]}),  # -> COMPLETE
    _done(),
]
_model, _agent = _scripted_agent(_script, _TGT_TOOLS, _TGT_MW, TestGenState,
                                 agent_var="test_gen_agent")
_st, _calls, _msgs = _run_tgt(_agent, _tgt_payload(_sid), _sid)

assert _calls.count("store_test_cases") == 2, f"TB-TG-2 FAIL: {_calls}"
# the first batch is SAVED even though it is incomplete, and the gaps are named
assert "INCOMPLETE" in _msgs[0], f"TB-TG-2 FAIL: batch 1 verdict was {_msgs[0][:120]}"
assert "add-to-cart-button" in _msgs[0], "TB-TG-2 FAIL: the gap was not named"
assert "SUITE COMPLETE" in _msgs[-1], f"TB-TG-2 FAIL: never completed -- {_msgs[-1][:120]}"
# and the batches ACCUMULATED rather than the second replacing the first
assert [t["id"] for t in _st["test_cases"]] == ["TC-001", "TC-002", "TC-003"], \
    f"TB-TG-2 FAIL: batches did not accumulate: {[t['id'] for t in _st['test_cases']]}"
_tgt_passed += 1
print(f"PASS TB-TG-2  2 batches accumulated to 3 cases; gaps named, then SUITE COMPLETE\n")


# ── TB-TG-3  Schema rejection ───────────────────────────────────────────────
print("=" * 68)
print("TB-TG-3  Schema rejection — malformed batch NOT saved, retry accepted")
print("=" * 68)
_sid = _tgt_uuid.uuid4().hex[:8]
_BAD = [{"id": "TC-900", "component": "navbar", "description": "missing keys"}]  # no action/selector/...
_script = [
    _tc("store_test_cases", {"test_cases": _BAD}),        # -> hard reject, nothing saved
    _tc("store_test_cases", {"test_cases": _TGT_FULL}),   # -> accepted
    _done(),
]
_model, _agent = _scripted_agent(_script, _TGT_TOOLS, _TGT_MW, TestGenState,
                                 agent_var="test_gen_agent")
_st, _calls, _msgs = _run_tgt(_agent, _tgt_payload(_sid), _sid)

assert _calls.count("store_test_cases") == 2, f"TB-TG-3 FAIL: {_calls}"
assert "SUITE COMPLETE" not in _msgs[0], "TB-TG-3 FAIL: a malformed batch was accepted"
assert "TC-900" not in [t["id"] for t in _st.get("test_cases", [])], \
    "TB-TG-3 FAIL: the rejected batch was saved anyway"
assert [t["id"] for t in _st["test_cases"]] == ["TC-001", "TC-002", "TC-003"], \
    f"TB-TG-3 FAIL: retry not stored cleanly: {[t['id'] for t in _st['test_cases']]}"
assert "SUITE COMPLETE" in _msgs[-1], "TB-TG-3 FAIL: did not recover after rejection"
_tgt_passed += 1
print(f"PASS TB-TG-3  schema error rejected (nothing saved), retry accepted\n")


# ── TB-TG-4  Reducer dedup by id ────────────────────────────────────────────
print("=" * 68)
print("TB-TG-4  Reducer — a re-sent id REPLACES its earlier version")
print("=" * 68)
_sid = _tgt_uuid.uuid4().hex[:8]
# Mutate DESCRIPTION, not selector: store_test_cases now enforces the Selector
# Contract, so ".navbar-fixed" on a node that declares no className would be
# rejected before the reducer was ever reached, and this test would silently
# stop testing the reducer.
_REVISED = dict(_TGT_NAVBAR, description="revised description")
_script = [
    _tc("store_test_cases", {"test_cases": [_TGT_NAVBAR, _TGT_STATE, _TGT_EVENT]}),
    _tc("store_test_cases", {"test_cases": [_REVISED]}),   # same id, new description
    _done(),
]
_model, _agent = _scripted_agent(_script, _TGT_TOOLS, _TGT_MW, TestGenState,
                                 agent_var="test_gen_agent")
_st, _calls, _msgs = _run_tgt(_agent, _tgt_payload(_sid), _sid)

_ids = [t["id"] for t in _st["test_cases"]]
assert _ids == ["TC-001", "TC-002", "TC-003"], f"TB-TG-4 FAIL: duplicate ids: {_ids}"
assert _st["test_cases"][0]["description"] == "revised description", \
    "TB-TG-4 FAIL: the re-sent case did not replace the earlier version"
_tgt_passed += 1
print(f"PASS TB-TG-4  re-sent id replaced in place, order preserved, no duplicate\n")


print("=" * 68)
print(f"  Test Generation agent turn-based suite: {_tgt_passed}/4 PASSED "
      f"(no real LLM calls)")
print("=" * 68)
