# Ported from fyp.ipynb cell 376 (ticket 05). The notebook is frozen;
# edit this file. Run by tests/test_notebook_cells.py.
# Unit tests: sync_css_test_cases
from types import SimpleNamespace

_DECO_SPEC = {
    "add-to-cart-btn": {
        "baseStyles": {"background-color": "#ff0000", "color": "#ffffff"}
    }
}
_SYNC_TCS = [
    {"id": "TC-001", "component": "navbar",          "action": "assert_visible",
     "selector": "s", "expected": "e",               "passed": None, "description": "d"},
    {"id": "TC-002", "component": "add-to-cart-btn", "action": "assert_css",
     "selector": ".add-to-cart-btn",
     "expected": "background-color=#0000ff|color=#ffffff",
     "passed": None, "description": "d"},
]

def _merged(before, cmd):
    """Apply the delta a sync tool returns, exactly as the state reducer does.

    The tools return only the cases they changed, so a test that wants to reason
    about the WHOLE suite has to merge first. This is the same _merge_test_cases
    the State channel uses, so the tests see what production sees.
    """
    return _merge_test_cases(before, cmd.update.get("test_cases", []))


def _rt_sync(component, test_cases, deco_spec):
    return SimpleNamespace(
        state={"decoration_specification": deco_spec, "test_cases": test_cases},
        tool_call_id="sync-001"
    )

# Case 1: assert_css expected rebuilt from baseStyles
r1 = sync_css_test_cases.func("add-to-cart-btn",
                               _rt_sync("add-to-cart-btn", _SYNC_TCS, _DECO_SPEC))
_m1 = _merged(_SYNC_TCS, r1)
assert _m1[1]["expected"] == "background-color=#ff0000|color=#ffffff", f"FAIL: {_m1[1]['expected']}"
assert _m1[0]["expected"] == "e", "FAIL: unrelated TC mutated"
# and the DELTA carries only the case that actually changed
assert [t["id"] for t in r1.update["test_cases"]] == ["TC-002"], \
    f"FAIL: delta should hold only the patched case, got {r1.update['test_cases']}"
print(f"[Case 1] {r1.update['messages'][0].content}")
print("PASS: assert_css expected rebuilt correctly\n")

# Case 2: non-assert_css tests for same component untouched
_SYNC_TCS2 = [{"id": "TC-003", "component": "add-to-cart-btn", "action": "assert_visible",
               "selector": "s", "expected": "visible", "passed": None, "description": "d"}]
r2 = sync_css_test_cases.func("add-to-cart-btn",
                               _rt_sync("add-to-cart-btn", _SYNC_TCS2, _DECO_SPEC))
assert _merged(_SYNC_TCS2, r2)[0]["expected"] == "visible", "FAIL: assert_visible mutated"
assert r2.update["test_cases"] == [], "FAIL: nothing changed, so the delta must be empty"
print(f"[Case 2] {r2.update['messages'][0].content}")
print("PASS: non-assert_css cases untouched\n")

# Case 3: component missing from decoration_specification → graceful skip
r3 = sync_css_test_cases.func("unknown-btn",
                               _rt_sync("unknown-btn", _SYNC_TCS, _DECO_SPEC))
assert "no basestyles" in r3.update["messages"][0].content.lower()
print(f"[Case 3] {r3.update['messages'][0].content}")
print("PASS: missing component handled gracefully\n")

# Case 4: REAL nested DecorationSpecification shape (pages[].componentDecorations[]).
# Before the _find_component_decoration fix the flat lookup found nothing here, so the
# tool skipped silently and assert_css expectations stayed stale after a style change.
_DECO_SPEC_REAL = {"globalTokens": {}, "pages": [{"pageName": "plp",
    "componentDecorations": [
        {"componentId": "add-to-cart-button", "className": "add-to-cart-btn",
         "baseStyles": {"background-color": "#ff0000", "color": "#ffffff"},
         "stateVariants": [{"stateName": "disabled", "styles": {"opacity": "0.5"}}]}]}]}
_TCS_REAL = [{"id": "TC-010", "component": "add-to-cart-button", "action": "assert_css",
              "selector": ".add-to-cart-btn", "expected": "background-color=#0000ff",
              "passed": None, "description": "d"}]
r4 = sync_css_test_cases.func("add-to-cart-button",
                               _rt_sync("add-to-cart-button", _TCS_REAL, _DECO_SPEC_REAL))
assert _merged(_TCS_REAL, r4)[0]["expected"] == "background-color=#ff0000|color=#ffffff", \
    f"FAIL real shape: {_merged(_TCS_REAL, r4)[0]['expected']}"
print(f"[Case 4] {r4.update['messages'][0].content}")
print("PASS: real nested decoration shape resolved by componentId\n")

# Case 5: same real spec, looked up by className instead of the component id
_TCS_REAL2 = [{**_TCS_REAL[0], "component": "add-to-cart-btn"}]
r5 = sync_css_test_cases.func("add-to-cart-btn",
                               _rt_sync("add-to-cart-btn", _TCS_REAL2, _DECO_SPEC_REAL))
assert _merged(_TCS_REAL2, r5)[0]["expected"] == "background-color=#ff0000|color=#ffffff"
print(f"[Case 5] {r5.update['messages'][0].content}")
print("PASS: real nested decoration shape also resolved by className")

# ── Rebasing from the PAGE, not from a stale specification (2026-08-11) ──────
# E2E-SO-04: the scenario asks for the button to become #d93025. The CSS agent
# applies it. sync then rebuilt `expected` from decoration_specification, which
# nothing updates in modify mode, so it rebased the assertion to #1a73e8 -- the
# colour the page had just stopped having. The suite failed twice, the cap was
# exhausted, and the scenario still PASSED because its assertions only checked
# that the tools had been CALLED.
_SY2_CSS = (":root {\n  --color-primary: #d93025;\n  --color-surface: #ffffff;\n}\n"
            ".add-to-cart-btn { background-color: var(--color-primary);"
            " color: var(--color-surface); }\n"
            ".add-to-cart-btn:hover { background-color: #b3261e; }\n"
            '.add-to-cart-btn[aria-disabled="true"] { background-color: #999; }\n')
_SY2_SPEC = {"pages": [{"pageName": "plp", "componentDecorations": [
    {"componentId": "add-to-cart-button", "className": "add-to-cart-btn",
     "baseStyles": {"background-color": "#1a73e8", "color": "#ffffff"}}]}]}
_SY2_TCS = [
    {"id": "TC-005", "component": "add-to-cart-button", "action": "assert_css",
     "selector": ".add-to-cart-btn",
     "expected": "background-color=#1a73e8|color=#ffffff", "passed": None,
     "description": "d"},
    {"id": "TC-008", "component": "add-to-cart-button", "action": "assert_css",
     "selector": ".add-to-cart-btn",
     "expected": "background-color=#1a73e8|color=#ffffff", "passed": None,
     "description": "d"},
]


def _sy2_rt(**over):
    st = {"decoration_specification": _SY2_SPEC, "test_cases": _SY2_TCS,
          "session_id": "sy2", "modification_context": ""}
    st.update(over)
    return SimpleNamespace(state=st, tool_call_id="sy2")


_sy2_real = globals().get("_read_preview_source")
globals()["_read_preview_source"] = lambda sid, ext: _SY2_CSS if ext == "css" else ""
try:
    print("[Case A \u00b7 GUARD] The new value comes from the PAGE, not the stale spec.")
    _r = sync_css_test_cases.func("add-to-cart-button", _sy2_rt())
    _ch = _r.update["test_cases"]
    assert len(_ch) == 2, "both assert_css cases must be rebased, got %d" % len(_ch)
    for _c in _ch:
        assert "#d93025" in _c["expected"], _c["expected"]
        assert "#1a73e8" not in _c["expected"], "the stale colour survived: %s" % _c["expected"]
    print("   ", _ch[0]["expected"])
    print("PASS: both cases now expect the colour the page actually has\n")

    print("[Case B \u00b7 NORMAL] The specification is NOT written -- modify mode never updates it.")
    assert "decoration_specification" not in _r.update, \
        "sync_css must write only test_cases; the un-reduced spec channel is the SO-06 collision"
    assert set(_r.update) == {"test_cases", "messages"}, _r.update
    assert _SY2_SPEC["pages"][0]["componentDecorations"][0]["baseStyles"][
        "background-color"] == "#1a73e8", "the caller's spec was not touched"
    print("PASS: only test_cases + messages written; the spec is left alone\n")

    print("[Case C \u00b7 EDGE] State variants never leak into the resting value.")
    # :hover and [aria-disabled] are exactly what assert_css must NOT compare
    # against -- they are the styles the component has only while acted upon.
    _live = _live_component_styles(_SY2_CSS, "add-to-cart-button", _SY2_SPEC,
                                   {"background-color", "color"})
    assert _live["background-color"] == "#d93025", "var() not resolved via :root"
    assert "#b3261e" not in _live.values() and "#999" not in _live.values(), _live
    print("PASS: var() resolved through :root, hover and disabled ignored\n")

    print("[Case D \u00b7 GUARD] A correction round may NOT rebase.")
    # Rebasing is only honest when the USER asked for the change. Inside the
    # correction loop the PAGE is what is wrong, so moving the goalposts would
    # make the suite pass while the defect remains -- silently.
    _r2 = sync_css_test_cases.func("add-to-cart-button", _sy2_rt(
        modification_context="TC-005 failed: background-color mismatch"))
    assert "test_cases" not in _r2.update, "a correction round was allowed to rebase"
    assert "REFUSED" in _r2.update["messages"][0].content
    print("PASS: refused inside a correction round, so a real failure stays visible\n")
finally:
    if _sy2_real is not None:
        globals()["_read_preview_source"] = _sy2_real

print("[Case E \u00b7 EDGE] No stylesheet on disk -> fall back, and change nothing extra.")
globals()["_read_preview_source"] = lambda sid, ext: ""
try:
    _r3 = sync_css_test_cases.func("add-to-cart-button", _sy2_rt())
    assert _r3.update["test_cases"] == [], "the fallback invented a change"
    assert "decoration_specification" not in _r3.update, "spec rewritten with no evidence"
finally:
    if _sy2_real is not None:
        globals()["_read_preview_source"] = _sy2_real
print("PASS: with no page to read, nothing is patched and the spec is left alone\n")

print("sync_css_test_cases: 5 page-rebase cases passed.")
