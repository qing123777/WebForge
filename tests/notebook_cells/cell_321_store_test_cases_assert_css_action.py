# Ported from fyp.ipynb cell 321 (ticket 05). The notebook is frozen;
# edit this file. Run by tests/test_notebook_cells.py.
# Unit tests: store_test_cases -- assert_css action validation
from types import SimpleNamespace

# css-style and attribute actions have validator-enforced expected formats,
# so the fixture supplies a format-valid expected per action.
_EXPECTED_BY_ACTION = {
    "assert_css":       "background-color=#1a73e8",
    "assert_hover_css": "background-color=#1557b0",
    "assert_attribute": "aria-expanded=true",
    "assert_url":       "#section",
    "assert_count":     ">=1",
}
_mk_tc = lambda action: [{
    "id": "TC-001", "component": "btn", "description": "test",
    "action": action, "selector": "#btn",
    "expected": _EXPECTED_BY_ACTION.get(action, "visible"),
    "passed": None
}]

# Case 1: assert_css is accepted as a valid action
r1 = store_test_cases.func(_mk_tc("assert_css"), SimpleNamespace(state={}, tool_call_id="css-001"))
assert "1 test case(s)" in r1.update["messages"][0].content, "FAIL: assert_css rejected"
print(f"[Case 1] {r1.update['messages'][0].content}")
print("PASS: assert_css accepted\n")

# Case 2: all other valid actions are accepted
for act in ("assert_visible", "assert_text", "assert_hover_css",
            "assert_attribute", "assert_url", "assert_count", "click", "type"):
    r = store_test_cases.func(_mk_tc(act), SimpleNamespace(state={}, tool_call_id=f"act-{act}"))
    assert "test case(s)" in r.update["messages"][0].content, f"FAIL: {act} rejected"
print("PASS: all valid actions accepted\n")

# Case 3: invalid action is rejected
r3 = store_test_cases.func(_mk_tc("hover"), SimpleNamespace(state={}, tool_call_id="act-bad"))
assert "invalid action" in r3.update["messages"][0].content.lower(), "FAIL: invalid action not caught"
print(f"[Case 3] {r3.update['messages'][0].content}")
print("PASS: invalid action rejected\n")

# Case 4: assert_css with valid pipe-separated expected is stored correctly
_css_tc = [{
    "id": "TC-CSS-001", "component": "add-to-cart-btn",
    "description": "Button background matches brand colour",
    "action": "assert_css",
    "selector": ".add-to-cart-btn",
    "expected": "background-color=#1a73e8|color=#ffffff",
    "passed": None
}]
r4 = store_test_cases.func(_css_tc, SimpleNamespace(state={}, tool_call_id="css-style-001"))
assert r4.update["test_cases"] == _css_tc
print(f"[Case 4] {r4.update['messages'][0].content}")
print("PASS: assert_css with valid pipe-separated expected stored correctly\n")

# Case 5: assert_css with expected that has no "=" in any segment is rejected
_bad_expected_tc = [{
    "id": "TC-CSS-BAD", "component": "btn", "description": "bad format",
    "action": "assert_css",
    "selector": "#btn",
    "expected": "red",
    "passed": None
}]
r5 = store_test_cases.func(_bad_expected_tc, SimpleNamespace(state={}, tool_call_id="css-fmt-bad"))
assert "property=value" in r5.update["messages"][0].content.lower(), \
    f"FAIL: expected format error message, got: {r5.update['messages'][0].content}"
print(f"[Case 5] {r5.update['messages'][0].content}")
print("PASS: assert_css invalid expected format rejected")


# Case 6: an assert_attribute pinning a TRANSIENT state is rejected; the stable
# end-state is accepted. A transient value reverts before the pipeline reads it,
# so asserting it is a timing false failure (PO-10 TC-056).
_transient_tc = [{
    "id": "TC-TRANSIENT", "component": "btn", "description": "loading state",
    "action": "assert_attribute", "selector": "#btn",
    "expected": "data-state=loading", "passed": None,
}]
r6 = store_test_cases.func(_transient_tc, SimpleNamespace(state={}, tool_call_id="transient-bad"))
assert "test_cases" not in r6.update, "FAIL: a transient assert was stored"
assert "transient" in r6.update["messages"][0].content.lower(), \
    f"FAIL: expected a transient rejection, got: {r6.update['messages'][0].content}"
print(f"[Case 6] {r6.update['messages'][0].content}")
_stable_tc = [{
    "id": "TC-STABLE", "component": "btn", "description": "added state",
    "action": "assert_attribute", "selector": "#btn",
    "expected": "data-state=added", "passed": None,
}]
r6b = store_test_cases.func(_stable_tc, SimpleNamespace(state={}, tool_call_id="transient-ok"))
assert r6b.update.get("test_cases") == _stable_tc, "FAIL: a stable end-state assert was wrongly rejected"
print("PASS: transient assert_attribute rejected, stable end-state accepted")
