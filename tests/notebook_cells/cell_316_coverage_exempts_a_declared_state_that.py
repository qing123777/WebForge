# Ported from fyp.ipynb cell 316 (ticket 05). The notebook is frozen;
# edit this file. Run by tests/test_notebook_cells.py.
# Unit test: coverage EXEMPTS a declared state that no interaction flow can produce.
# po2r117e13f asserted data-state=compact (header, scroll-only) and =highlighted
# (banner, decorative); no click/type flow produces either, so demanding coverage of
# them was a guard the model could never satisfy. With an interaction spec present,
# such states drop from the demand; with none, the old behaviour is unchanged; a
# state a flow DOES produce stays required.
from types import SimpleNamespace as _C1SNS
_C1_COMPONENTS = {"pages": [{"pageName": "p", "regionComponents": {"main": [
    {"id": "header-cart-link", "tag": "a"},
    {"id": "mini-cart-drawer", "tag": "aside", "states": [{"name": "open"}, {"name": "closed"}]},
    {"id": "site-header", "tag": "header", "states": [{"name": "default"}, {"name": "compact"}]},
]}}]}
_C1_INTX = {"pages": [{"pageName": "p", "flows": [
    {"name": "open-cart", "trigger": {"event": "click", "targetId": "header-cart-link"},
     "stateTransitions": [{"componentId": "mini-cart-drawer", "toState": "open"}]}]}]}
def _c1_tc(i, comp, action, sel, expected="visible", **kw):
    d = {"id": i, "component": comp, "description": "d", "action": action,
         "selector": sel, "expected": expected, "passed": None}
    d.update(kw); return d
_C1_SUITE = [
    _c1_tc("v1", "header-cart-link", "assert_visible", "#header-cart-link"),
    _c1_tc("v2", "mini-cart-drawer", "assert_visible", "#mini-cart-drawer"),
    _c1_tc("v3", "site-header", "assert_visible", "#site-header"),
    _c1_tc("o1", "mini-cart-drawer", "assert_attribute", "#mini-cart-drawer",
           "data-state=open", covers_state="open"),
]
def _c1_rt(intx):
    st = {"components_specification": _C1_COMPONENTS}
    if intx is not None: st["interaction_specification"] = intx
    return _C1SNS(state=st, tool_call_id="c1")
def _c1_msg(cmd): return cmd.update["messages"][0].content
_c1_with    = _c1_msg(store_test_cases.func(_C1_SUITE, _c1_rt(_C1_INTX)))
_c1_without = _c1_msg(store_test_cases.func(_C1_SUITE, _c1_rt(None)))
_c1_drop    = _c1_msg(store_test_cases.func([c for c in _C1_SUITE if c["id"] != "o1"], _c1_rt(_C1_INTX)))
assert "compact" not in _c1_with, f"compact (no producing flow) must be exempt WITH interaction spec: {_c1_with}"
assert "compact" in _c1_without, f"WITHOUT interaction spec, coverage must be unchanged (compact demanded): {_c1_without}"
assert "open" in _c1_drop, f"a flow-produced state must still be required: {_c1_drop}"
print("PASS: coverage exemption -- a state no flow produces (compact) drops from the demand when "
      "an interaction spec is present, stays when it is absent; a flow-produced state (open) stays required.")
