# Ported from fyp.ipynb cell 345 (ticket 05). The notebook is frozen;
# edit this file. Run by tests/test_notebook_cells.py.
# Unit tests: _order_test_cases -- an assertion tagged covers_event runs late
# The outcome half of an event pair asserts what the click PRODUCED, so it must
# run after phase 1. The click itself carries the same tag and stays in phase 1,
# because the click is what performs the interaction.

_ot_passed = 0


def _ot_ok(tid, desc):
    global _ot_passed
    _ot_passed += 1
    print(f"PASS  {tid:<4} {desc}")


_ot_cases = [
    {"id": "O1", "action": "assert_count", "covers_event": "onClick"},   # outcome
    {"id": "O2", "action": "assert_visible"},                            # baseline
    {"id": "O3", "action": "click", "covers_event": "onClick"},          # trigger
    {"id": "O4", "action": "assert_attribute", "covers_state": "selected"},
    {"id": "O5", "action": "assert_hover_css", "covers_state": "hover"},
]
_order = [tc["id"] for tc in _order_test_cases(_ot_cases)]
assert _order.index("O3") < _order.index("O1"), _order
_ot_ok("O-1", "the click runs before the assert_count that checks its outcome")

assert _order.index("O2") < _order.index("O3"), _order
assert _order.index("O5") < _order.index("O3"), _order
_ot_ok("O-2", "baseline cases and assert_hover_css still run before any click")

assert _order.index("O3") < _order.index("O4"), _order
_ot_ok("O-3", "a covers_state assertion still runs after the click, unchanged")

# O-4: two single-select controls. Each active-assert must sit right after ITS
# OWN click and before the next click. The old 'all clicks first' order put both
# clicks ahead of both asserts, so the second click cleared the first and its
# active-assert failed -- po015df552 TC-023/026/029. This case passes on the new
# pairing order and FAILS on the old one, so it is what proves the change.
_ot_ms = [
    {"id": "L-click",  "action": "click",            "component": "filter-light",  "covers_event": "onClick"},
    {"id": "L-active", "action": "assert_attribute", "component": "filter-light",  "covers_state": "active"},
    {"id": "M-click",  "action": "click",            "component": "filter-medium", "covers_event": "onClick"},
    {"id": "M-active", "action": "assert_attribute", "component": "filter-medium", "covers_state": "active"},
]
_om = [tc["id"] for tc in _order_test_cases(_ot_ms)]
assert _om.index("L-active") < _om.index("M-click"), _om
assert _om.index("M-click")  < _om.index("M-active"), _om
_ot_ok("O-4", "each single-select active-assert runs right after its own click, before the next")
print(f"[proof] pairing keeps click+assert adjacent: new order {_om}; the old "
      f"batch-all-clicks order was ['L-click','M-click','L-active','M-active'], "
      f"where L-active ran after M-click had cleared it -- po015df552 TC-023/026/029.")

_OT_TOTAL = 4
assert _ot_passed == _OT_TOTAL, f"expected {_OT_TOTAL} ordering cases, ran {_ot_passed}"
print("=" * 76)
print(f"_order_test_cases: {_ot_passed}/{_OT_TOTAL} PASSED")
print("=" * 76)
