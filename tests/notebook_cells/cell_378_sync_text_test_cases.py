# Ported from fyp.ipynb cell 378 (ticket 05). The notebook is frozen;
# edit this file. Run by tests/test_notebook_cells.py.
# Unit tests: sync_text_test_cases
from types import SimpleNamespace

_TEXT_TCS = [
    {"id": "TC-001", "component": "hero-title",      "action": "assert_text",
     "selector": "#hero-title", "expected": "Welcome to our store",
     "passed": None, "description": "d"},
    {"id": "TC-002", "component": "hero-title",      "action": "assert_css",
     "selector": "#hero-title", "expected": "color=#ffffff",
     "passed": None, "description": "d"},
    {"id": "TC-003", "component": "add-to-cart-btn", "action": "assert_text",
     "selector": ".add-to-cart-btn", "expected": "Add to Cart",
     "passed": None, "description": "d"},
]

def _merged(before, cmd):
    """Apply the delta a sync tool returns, exactly as the state reducer does.

    The tools return only the cases they changed, so a test that wants to reason
    about the WHOLE suite has to merge first. This is the same _merge_test_cases
    the State channel uses, so the tests see what production sees.
    """
    return _merge_test_cases(before, cmd.update.get("test_cases", []))


def _rt_text(test_cases):
    return SimpleNamespace(state={"test_cases": test_cases}, tool_call_id="stx-001")

# Case 1: assert_text expected replaced for target component only
r1 = sync_text_test_cases.func("hero-title", "Summer Sale — 50% Off", _rt_text(_TEXT_TCS))
_mt1 = _merged(_TEXT_TCS, r1)
assert _mt1[0]["expected"] == "Summer Sale — 50% Off", f"FAIL: {_mt1[0]['expected']}"
assert _mt1[2]["expected"] == "Add to Cart", "FAIL: other component's assert_text mutated"
assert [t["id"] for t in r1.update["test_cases"]] == ["TC-001"], \
    f"FAIL: delta should hold only the patched case, got {r1.update['test_cases']}"
print(f"[Case 1] {r1.update['messages'][0].content}")
print("PASS: assert_text expected rebuilt for target component only\n")

# Case 2: non-assert_text cases for the same component untouched
assert _mt1[1]["expected"] == "color=#ffffff", "FAIL: assert_css case mutated by text sync"
print("PASS: assert_css case for same component untouched\n")

# Case 3: empty new_text -> skip, nothing patched
r3 = sync_text_test_cases.func("hero-title", "", _rt_text(_TEXT_TCS))
assert "test_cases" not in r3.update, "FAIL: must not update on empty new_text"
assert "Skipping sync" in r3.update["messages"][0].content
print(f"[Case 3] {r3.update['messages'][0].content}")
print("PASS: empty new_text skipped safely\n")

# Case 4: component with no assert_text cases -> patched 0, suite unchanged
r4 = sync_text_test_cases.func("navbar", "New Text", _rt_text(_TEXT_TCS))
assert r4.update["test_cases"] == [], "FAIL: nothing changed, so the delta must be empty"
assert _merged(_TEXT_TCS, r4) == _TEXT_TCS, "FAIL: the merged suite must be unchanged"
assert "Patched 0" in r4.update["messages"][0].content
print(f"[Case 4] {r4.update['messages'][0].content}")
print("PASS: component without assert_text cases handled gracefully")


# ── A correction round is refused, the same as sync_css and sync_hover ───────
# Found by sweeping for the defect that failed E2E-SO-06 on 2026-08-16. This
# tool never had that bug, because new_text comes from the user's request rather
# than from a specification a modify run leaves stale. It was the only one of
# the three sync tools that would still rebase inside a repair round, which
# turns a genuinely broken page into a passing suite.
_txt_corr = SimpleNamespace(
    state={"test_cases": _TEXT_TCS,
           "modification_context": "the button label was missing"},
    tool_call_id="txt-corr")
_h_corr = sync_text_test_cases.func("add-to-cart-button", "Add to bag", _txt_corr)
assert "test_cases" not in _h_corr.update, \
    ("FAIL: the suite was rebased during a correction round, so a page that is "
     "genuinely broken would now report a pass.")
assert "refused" in _h_corr.update["messages"][0].content.lower(), \
    "FAIL: the refusal does not say it refused"
print("PASS: refused inside a correction round, so a real failure stays visible")
