# Ported from fyp.ipynb cell 420 (ticket 05). The notebook is frozen;
# edit this file. Run by tests/test_notebook_cells.py.
# Unit tests: reset_before (the per-turn state reset)
# Tests the plain _reset_before; reset_before is before_agent(_reset_before),
# the object the orchestrator actually runs. runtime is unused by the body.
_rb_out = _reset_before({
    "input_query": "make a shoe shop",
    "intent": "modify",
    "target_component": "hero",
    "target_instance": 3,
    "clarifier_used": True,
    "pending_question": {"question": "old?"},
    "design_schema": {"x": 1},
    "messages": [],
}, None)
assert _rb_out["clarifier_used"] is False, \
    "FAIL: clarifier_used must be cleared each turn so the gate is per turn, not per session"
assert _rb_out["intent"] == "generate", "FAIL: a stale modify intent must not leak forward"
assert _rb_out["pending_question"] == {}, "FAIL: last turn's question must be cleared"
assert _rb_out["input_query"] == "make a shoe shop", "FAIL: the query must be preserved"
print("PASS reset_before - clarifier_used cleared, intent reset, query kept (gate is per turn)")

_rb_out2 = _reset_before(
    {"messages": [{"role": "user", "content": "a hat store"}]}, None)
assert _rb_out2["input_query"] == "a hat store", "FAIL: query not lifted from the last human message"
assert _rb_out2["clarifier_used"] is False
print("PASS reset_before - query lifted from the newest human message, flag still cleared")
