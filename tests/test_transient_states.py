"""Speed-cost ticket 02: transient states follow one rule in Test Generation.

    pytest tests/test_transient_states.py   (or python tests/test_transient_states.py)

Offline, no model calls. Every test goes through store_test_cases, the tool
the model calls.

  TS-1  a transient state is never a coverage target: the guard reports
        SUITE COMPLETE without a case for it, even when a flow produces it.
  TS-2  a case whose covers_state is transient is refused for EVERY action,
        and the refusal tells the model to assert the stable end-state.
  TS-3  the two guards agree: for each transient state, coverage does not
        ask for it AND the store guard refuses a case for it.

Before this ticket the two disagreed. On the 2026-11-10 PO-08 run (session
4fb17fbe) coverage demanded featured-coffee-add-to-cart:loading, the store
guard refused it as assert_attribute (TC-064), and the model wrote the same
check as assert_css (TC-065), which passed both guards and failed on every
correct page.
"""
import contextlib
import io
import pathlib
import sys
from types import SimpleNamespace

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import conftest  # noqa: E402,F401  (repo on sys.path, dead API keys) when run with python

import pytest  # noqa: E402

with contextlib.redirect_stdout(io.StringIO()):
    import webforge.test_gen_agent as tg  # noqa: E402

# The list as the ticket found it. Pinned here so a change to the list is a
# deliberate edit to this test, not a silent change to what the guards accept.
TRANSIENT = ["adding", "loading", "saving", "submitting", "sending",
             "pending", "processing"]


def _spec(state):
    """One add-to-cart button that declares a transient state and its stable
    end-state, and one flow that produces BOTH (the shape of session 4fb17fbe)."""
    comps = {"pages": [{"pageName": "p", "regionComponents": {"main": [
        {"id": "add-btn", "tag": "button", "className": "add-btn",
         "states": [{"name": "default"}, {"name": state}, {"name": "added"}],
         "events": []},
    ]}}]}
    intx = {"pages": [{"pageName": "p", "flows": [
        {"name": "addToCart", "trigger": {"event": "onClick", "targetId": "add-btn"},
         "stateTransitions": [{"componentId": "add-btn", "toState": state},
                              {"componentId": "add-btn", "toState": "added"}]}]}]}
    return comps, intx


def _tc(i, action, expected, **kw):
    d = {"id": i, "component": "add-btn", "description": "d", "action": action,
         "selector": ".add-btn", "expected": expected, "passed": None}
    d.update(kw)
    return d


def _store(cases, state):
    comps, intx = _spec(state)
    rt = SimpleNamespace(state={"components_specification": comps,
                                "interaction_specification": intx},
                         tool_call_id="ts")
    return tg.store_test_cases.func(cases, rt)


def _said(cmd):
    return cmd.update["messages"][0].content


# The suite a correct model writes: the button is visible, and after the click
# it settles into 'added'. Nothing about the transient state.
_STABLE_SUITE = [
    _tc("v1", "assert_visible", "visible"),
    _tc("a1", "assert_attribute", "data-state=added", covers_state="added"),
]


@pytest.mark.parametrize("state", TRANSIENT)
def test_coverage_never_demands_a_transient_state(state):
    got = _store(_STABLE_SUITE, state)
    msg = _said(got)
    assert "SUITE COMPLETE" in msg, msg
    assert f"add-btn:{state}" not in msg, msg
    assert got.update.get("test_cases") == _STABLE_SUITE


# One well-formed case per action, so the only thing wrong with it is the
# transient covers_state tag. TC-065 is the assert_css row.
_ANY_ACTION = {
    "assert_visible":   ("visible", {}),
    "assert_text":      ("Adding...", {}),
    "assert_css":       ("opacity=0.9", {}),
    "assert_hover_css": ("opacity=0.9", {}),
    "assert_attribute": ("aria-busy=true", {}),
    "assert_url":       ("#cart", {}),
    "assert_count":     (">=1", {}),
    "click":            ("clicked", {}),
    "type":             ("typed", {"input": "x"}),
}


def test_every_action_is_listed():
    assert set(_ANY_ACTION) == tg.VALID_ACTIONS


def _refused(cmd, case_id):
    msg = _said(cmd)
    assert "test_cases" not in cmd.update, f"a transient case was saved: {msg}"
    assert case_id in msg and "TRANSIENT" in msg, msg
    assert "STABLE end-state" in msg, msg
    return msg


@pytest.mark.parametrize("state", TRANSIENT)
@pytest.mark.parametrize("action", sorted(_ANY_ACTION))
def test_transient_covers_state_is_refused_for_every_action(state, action):
    expected, extra = _ANY_ACTION[action]
    case = _tc("t1", action, expected, covers_state=state, **extra)
    _refused(_store([case], state), "t1")


def test_transient_covers_state_ignores_case():
    case = _tc("t1", "assert_css", "opacity=0.9", covers_state="Loading")
    _refused(_store([case], "loading"), "t1")


def test_transient_value_in_assert_attribute_is_still_refused():
    # The check the ticket keeps: an UNTAGGED assert_attribute pinning a
    # transient value (PO-10 TC-056).
    case = _tc("t1", "assert_attribute", "data-state=loading")
    _refused(_store([case], "loading"), "t1")


def test_transient_state_variant_value_never_asks_for_a_transient_tag():
    # The stateVariant guard refuses an untagged assert_css on a value that
    # only exists inside a stateVariant, and used to say "Tag this case
    # covers_state='<variant>'". For a transient variant that advice walks
    # straight into the refusal above, a guard the model cannot satisfy.
    comps, intx = _spec("loading")
    deco = {"pages": [{"pageName": "p", "componentDecorations": [
        {"componentId": "add-btn", "baseStyles": {"opacity": "1"},
         "stateVariants": [{"stateName": "loading", "styles": {"opacity": "0.9"}}]}]}]}
    rt = SimpleNamespace(state={"components_specification": comps,
                                "interaction_specification": intx,
                                "decoration_specification": deco},
                         tool_call_id="ts")
    msg = _refused(tg.store_test_cases.func(
        [_tc("t1", "assert_css", "opacity=0.9")], rt), "t1")
    assert "Tag this case covers_state='loading'" not in msg, msg


@pytest.mark.parametrize("order", ["transient_first", "stable_first"])
def test_shared_variant_value_tagged_with_the_stable_state_is_saved(order):
    # Review of ticket 02: 'loading' and 'added' share a non-resting value.
    # A case tagged covers_state='added' asserts exactly the stable end-state,
    # yet the loop over variants refused it on the 'loading' variant, and the
    # refusal told it to assert the stable end-state: a wall.
    comps, intx = _spec("loading")
    variants = [{"stateName": "loading", "styles": {"color": "white"}},
                {"stateName": "added", "styles": {"color": "white"}}]
    if order == "stable_first":
        variants.reverse()
    deco = {"pages": [{"pageName": "p", "componentDecorations": [
        {"componentId": "add-btn", "baseStyles": {"color": "black"},
         "stateVariants": variants}]}]}
    rt = SimpleNamespace(state={"components_specification": comps,
                                "interaction_specification": intx,
                                "decoration_specification": deco},
                         tool_call_id="ts")
    got = tg.store_test_cases.func(
        [_tc("t1", "assert_css", "color=white", covers_state="added")], rt)
    assert "test_cases" in got.update, _said(got)


@pytest.mark.parametrize("state", TRANSIENT)
def test_the_two_guards_agree(state):
    # TS-3. The coverage guard does not ask for the state AND the store guard
    # refuses a case for it. Either alone is the old contradiction: asked for
    # and refused (the wall), or not asked for and accepted (TC-065).
    asked = _said(_store(_STABLE_SUITE[:1], state))
    assert "Coverage INCOMPLETE" in asked and "add-btn:added" in asked, asked
    assert f"add-btn:{state}" not in asked, asked
    case = _tc("t1", "assert_css", "opacity=0.9", covers_state=state)
    _refused(_store(_STABLE_SUITE + [case], state), "t1")


def test_the_list_is_the_one_both_guards_read():
    assert sorted(tg._TRANSIENT_STATES) == sorted(TRANSIENT)


# TS-4. Replay the four store_test_cases calls of PO-08 session 4fb17fbe
# through today's guard. The fixture was cut from the run's LangSmith trace
# (runs/20261110-1110_po08-ui_01a1c526/trace.jsonl.gz): the Test Generation
# state's three specifications, each call's test_cases, and the reply the old
# guard gave. The recorded replies are the "before"; this replay is the "after".
_REPLAY = pathlib.Path(__file__).resolve().parent / "fixtures" / "po08_4fb17fbe_store_test_cases.json"


def test_replay_po08_4fb17fbe():
    import json
    rec = json.loads(_REPLAY.read_text(encoding="utf-8"))
    state = dict(rec["state"], test_cases=[])
    before, after = [c["reply"] for c in rec["calls"]], []
    for n, call in enumerate(rec["calls"]):
        got = tg.store_test_cases.func(call["test_cases"],
                                       SimpleNamespace(state=state, tool_call_id=f"r{n}"))
        if "TC-059" in _said(got) and "starts at" in _said(got):
            # Ticket 01 refuses TC-059's '1' (the spec starts the cart at 3).
            # Retry with the number it asks for, as the model would, so this
            # replay still measures the transient rule alone.
            fixed = [dict(c, expected="4") if c["id"] == "TC-059" else c
                     for c in call["test_cases"]]
            got = tg.store_test_cases.func(fixed, SimpleNamespace(state=state,
                                                                  tool_call_id=f"r{n}b"))
        if "test_cases" in got.update:
            state["test_cases"] = tg._merge_test_cases(state["test_cases"],
                                                       got.update["test_cases"])
        after.append(_said(got))

    demand = "featured-coffee-add-to-cart:loading"
    # Before: the second call was told to add a loading case, and TC-065 was saved.
    assert demand in before[1] and "Coverage INCOMPLETE" in before[1]
    assert rec["calls"][3]["saved"] and "SUITE COMPLETE" in before[3]
    # After: the second call already completes the suite, and TC-065 is refused.
    assert "Selector Contract" in after[0]               # unchanged
    assert "SUITE COMPLETE" in after[1] and demand not in after[1], after[1]
    assert "TC-064" in after[2] and "TRANSIENT" in after[2]   # unchanged
    assert "TC-065" in after[3] and "TRANSIENT" in after[3], after[3]
    suite = state["test_cases"]
    on_transient = [t["id"] for t in suite
                    if tg._is_transient_state(t.get("covers_state"))
                    or tg._is_transient_state(str(t.get("expected", "")).split("=", 1)[-1])]
    assert len(suite) == 63 and not on_transient, on_transient
    old_suite = []
    for call in rec["calls"]:
        if call["saved"]:
            old_suite = tg._merge_test_cases(old_suite, call["test_cases"])
    old_transient = [t["id"] for t in old_suite if tg._is_transient_state(t.get("covers_state"))]
    print(f"\n[proof] replay of PO-08 session {rec['session_id'][:8]}, "
          f"{len(rec['calls'])} store_test_cases calls. Before: call 2 demanded "
          f"'{demand}', call 4 saved TC-065 (assert_css, covers_state='loading'); "
          f"suite {len(old_suite)} cases, {len(old_transient)} on a transient state "
          f"{old_transient}. After: call 2 reaches SUITE COMPLETE with no demand, "
          f"call 4 refuses TC-065; suite {len(suite)} cases, {len(on_transient)} on "
          f"a transient state.")


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
