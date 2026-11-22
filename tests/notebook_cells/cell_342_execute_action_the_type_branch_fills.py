# Ported from fyp.ipynb cell 342 (ticket 05). The notebook is frozen;
# edit this file. Run by tests/test_notebook_cells.py.
# Unit tests: _execute_action -- the `type` branch fills the case's own value
# A fake page records what Playwright would have been asked to do, so the branch
# is exercised with no browser and no network. The old branch ignored the case
# entirely and always filled "test input", which is the defect these cover.


class _FakeMouse:
    def __init__(self): self.moves = []
    def move(self, x, y): self.moves.append((x, y))


class _FakePage:
    """Records fill/press/wait calls. url is fixed; nothing here navigates."""
    def __init__(self):
        self.filled = []
        self.pressed = []
        self.waited = []
        self.mouse = _FakeMouse()
        self.matches = {}          # selector -> the list query_selector_all returns
        self.url = "http://localhost/preview_x.html"

    def fill(self, selector, value): self.filled.append((selector, value))
    def query_selector_all(self, selector): return self.matches.get(selector, [])
    def press(self, selector, key): self.pressed.append((selector, key))
    def wait_for_timeout(self, ms): self.waited.append(ms)


_ea_passed = 0


def _ea_ok(tid, desc):
    global _ea_passed
    _ea_passed += 1
    print(f"PASS  {tid:<4} {desc}")


def _ea_case(**over):
    tc = {"id": "TC-100", "component": "search-bar", "description": "d",
          "action": "type", "selector": ".search-input",
          "expected": "one result", "passed": False}
    tc.update(over)
    return tc


_p = _FakePage()
_res = _execute_action(_p, _ea_case(input="Aurora Headphones"), "sid")
assert _res["passed"] is True, _res
assert _p.filled == [(".search-input", "Aurora Headphones")], _p.filled
assert _p.pressed == [], _p.pressed
_ea_ok("EA1", "type fills the case's own input, and presses nothing by default")

_p = _FakePage()
_execute_action(_p, _ea_case(input="Aurora", press="Enter"), "sid")
assert _p.pressed == [(".search-input", "Enter")], _p.pressed
assert _p.waited == [250], _p.waited
_ea_ok("EA2", "press submits the field and the handler is given time to run")

_p = _FakePage()
_execute_action(_p, _ea_case(), "sid")
assert _p.filled == [(".search-input", "test input")], _p.filled
_ea_ok("EA3", "a case with no input still falls back to the old literal")

# The pointer must still be parked after a click, or :hover leaks into the next
# assertion. Unrelated to this change, and exactly the kind of thing a nearby
# edit breaks silently.
_p = _FakePage()
_p.click = lambda sel: _p.filled.append(("click", sel))
_execute_action(_p, _ea_case(action="click", expected="cart opens"), "sid")
assert _p.mouse.moves == [(0, 0)], _p.mouse.moves
_ea_ok("EA4", "click still parks the mouse afterwards")

# ── assert_count: the first assertion that can observe an outcome ────────────

def _count_case(exp, **over):
    tc = {"id": "TC-200", "component": "cart-item", "description": "d",
          "action": "assert_count", "selector": ".cart-item",
          "expected": exp, "passed": False}
    tc.update(over)
    return tc


_p = _FakePage()
_p.matches = {".cart-item": ["a", "b", "c"]}
assert _execute_action(_p, _count_case(">=1"), "sid")["passed"] is True
assert _execute_action(_p, _count_case("=3"), "sid")["passed"] is True
assert _execute_action(_p, _count_case("<4"), "sid")["passed"] is True
_ea_ok("EA5", "assert_count passes on >=, = and < when the count satisfies them")

_r = _execute_action(_p, _count_case("=1"), "sid")
assert _r["passed"] is False
assert "matched 3" in _r["reason"], _r["reason"]
_ea_ok("EA6", "a wrong count fails and the reason states what was matched")

# The defect this exists for: nothing was added to the cart.
_p = _FakePage()
_p.matches = {".cart-item": []}
_r = _execute_action(_p, _count_case(">=1", covers_event="onClick"), "sid")
assert _r["passed"] is False, "FAIL: an empty cart passed an at-least-one check"
_ea_ok("EA7", "a click that added nothing to the cart now FAILS")

# A tagged count failure belongs to JS. Untagged it is resting markup, so HTML.
# Routing it to HTML while tagged invites a fix that hardcodes the element.
assert _route_agent({"action": "assert_count", "reason": "matched 0",
                     "covers_event": "onClick"}) == "js_agent"
assert _route_agent({"action": "assert_count", "reason": "matched 7"}) == "html_agent"
assert _route_agent({"action": "assert_count",
                     "reason": "'.cart-item' not found"}) == "html_agent"
_ea_ok("EA8", "a tagged count failure routes to JS, untagged and not-found to HTML")

print("=" * 76)
print(f"_execute_action type + assert_count: {_ea_passed}/8 PASSED")
print("=" * 76)
