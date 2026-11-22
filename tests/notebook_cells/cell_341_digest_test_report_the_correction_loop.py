# Ported from fyp.ipynb cell 341 (ticket 05). The notebook is frozen;
# edit this file. Run by tests/test_notebook_cells.py.
# Unit tests: _digest_test_report -- the correction loop's input (2026-08-30).
# REGRESSION for the PO-08 po01e49777 defect: call_test_exec_pipeline sent the
# orchestrator `test_report[:500]`, and _build_report opens with one long
# "PASSED: <every id>" line, so the whole budget went to passing ids. With 17
# real failures on disk the orchestrator saw none of them, reported the build as
# finished, and the correction loop ran ZERO times. These cases pin the property
# that broke: whatever the suite's size, the FAILED lines and the routed
# "Action required:" entries must survive into the message.
_dig_passed = 0

# A report shaped exactly like _build_report writes one: a long PASSED line
# (well over the old 500-character budget on its own), then failures, then the
# routed work orders.
_DIG_IDS   = ", ".join("TC-%03d" % n for n in range(1, 65))     # 64 passing ids
_DIG_REPORT = (
    "PASSED: " + _DIG_IDS + "\n"
    "FAILED: TC-006 [assert_css] - height: expected '44px', got '50px'\n"
    "FAILED: TC-015 [assert_css] - background-color: expected 'rgb(250, 245, 238)'\n"
    "\nAction required:\n"
    "- css_agent | intent=modify | target_component=product-card | reason=height\n"
    "- js_agent | intent=modify | target_component=mini-cart | reason=not found\n"
)
assert len("PASSED: " + _DIG_IDS) > 500, \
    "the fixture must reproduce the bug: the PASSED line alone must exceed the old 500-char slice"

_dig = _digest_test_report(_DIG_REPORT)
assert "TC-006" in _dig and "TC-015" in _dig, \
    f"D-1 FAIL: a failure was lost from the digest:\n{_dig}"
assert "css_agent" in _dig and "js_agent" in _dig, \
    f"D-1 FAIL: the routed work orders were lost, so the loop cannot dispatch:\n{_dig}"
assert _DIG_IDS not in _dig and "PASSED: 64 case(s)" in _dig, \
    f"D-1 FAIL: the passing ids must collapse to a count, not be reprinted:\n{_dig}"
assert "FAILED: 2 case(s)" in _dig, f"D-1 FAIL: failure count missing:\n{_dig}"
print("PASS D-1 - failures and work orders survive a report whose PASSED line alone exceeds 500 chars")
_dig_passed += 1

# The exact regression: the OLD behaviour on this same report showed no failure
# at all. This asserts the two are genuinely different, so the test cannot pass
# by accident if the slice is ever reintroduced.
assert "FAILED" not in _DIG_REPORT[:500], \
    "D-2 FAIL: the fixture no longer reproduces the original defect"
assert "FAILED" in _dig, "D-2 FAIL: the digest must show what the slice hid"
print("PASS D-2 - the old 500-char slice showed no failure on this report; the digest does")
_dig_passed += 1

# Done Condition: the orchestrator's prompt ends the run on this exact string.
_dig_ok = _digest_test_report(
    "PASSED: TC-001, TC-002\n\nALL TESTS PASSED - no action required.")
assert "ALL TESTS PASSED" in _dig_ok, f"D-3 FAIL: the done condition was lost:\n{_dig_ok}"
assert "FAILED: 0 case(s)" in _dig_ok, f"D-3 FAIL: clean run must report zero failures:\n{_dig_ok}"
print("PASS D-3 - a clean run keeps the ALL TESTS PASSED done condition")
_dig_passed += 1

# A cap may bite, but it must ANNOUNCE itself and must never eat the work orders
# -- that is the whole lesson of the original defect.
_DIG_MANY = ("PASSED: TC-000\n"
             + "".join("FAILED: TC-%03d [assert_css] - wrong\n" % n for n in range(1, 101))
             + "\nAction required:\n"
             + "- css_agent | intent=modify | target_component=card | reason=wrong\n")
_dig_many = _digest_test_report(_DIG_MANY)
assert "more failure(s)" in _dig_many, f"D-4 FAIL: a bitten cap must say so:\n{_dig_many[:400]}"
assert "css_agent" in _dig_many, \
    "D-4 FAIL: 100 failures pushed the work orders out -- the original bug, one layer up"
print("PASS D-4 - a capped failure list is announced, and never displaces the work orders")
_dig_passed += 1

assert _digest_test_report("") == "(no report produced)"
assert _digest_test_report(None) == "(no report produced)"
print("PASS D-5 - an empty or missing report degrades safely")
_dig_passed += 1

print("=" * 64)
print(f"_digest_test_report: {_dig_passed}/5 PASSED (no model calls)")
