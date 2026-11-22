# Ported from fyp.ipynb cell 354 (ticket 05). The notebook is frozen;
# edit this file. Run by tests/test_notebook_cells.py.
# Unit tests: _merge_work_orders (modification_history reducer)
# This key is written by call_html_agent, call_css_agent and call_js_agent. The
# orchestrator runs CSS and JS in PARALLEL, so two writes land in the SAME
# superstep. Without a reducer LangGraph raises InvalidUpdateError rather than
# picking a winner -- correct behaviour, since silently dropping one agent's work
import typing as _t_wo

_passed_wo = 0
def _ok_wo(tid, desc):
    global _passed_wo
    _passed_wo += 1
    print(f"PASS  {tid:<4} {desc}")

# W1: plain append
assert _merge_work_orders(["a"], ["b"]) == ["a", "b"]
assert _merge_work_orders([], ["b"]) == ["b"]
_ok_wo("W1", "appends the incoming entry to the existing list")

# W2: None on either side (first write of a run, or a node returning nothing)
assert _merge_work_orders(None, ["b"]) == ["b"]
assert _merge_work_orders(["a"], None) == ["a"]
assert _merge_work_orders(None, None) == []
_ok_wo("W2", "None on either side is treated as empty, never raises")

# W3: THE CASE THAT BROKE THE LIVE RUN -- css and js in one parallel step.
# Each contributes only its OWN entry, so both survive and neither is replayed.
_before = ["[html_agent] earlier fix"]
_after  = _merge_work_orders(_merge_work_orders(_before, ["[css_agent] fix colour"]),
                             ["[js_agent] fix handler"])
assert _after == ["[html_agent] earlier fix",
                  "[css_agent] fix colour",
                  "[js_agent] fix handler"], _after
_ok_wo("W3", "two parallel branches both land, earlier history kept once")

# W4: the shape that was WRONG. Each tool used to return the accumulated list
# (_hist + [entry]). With a concatenating reducer that replays the history once
# per branch, which is why the writers now return a delta.
_bad = _merge_work_orders(_merge_work_orders(_before, _before + ["[css_agent] x"]),
                          _before + ["[js_agent] y"])
assert _bad.count("[html_agent] earlier fix") == 3, _bad
_ok_wo("W4", "returning the whole list would triple the history — delta is required")

# W5: the reducer is actually WIRED to the field. A drift guard: this test is
# worthless if someone drops the Annotated wrapper and leaves the function here.
_hints = _t_wo.get_type_hints(SecondaryOrchState, include_extras=True)
_mh    = _hints["modification_history"]
assert _t_wo.get_origin(_mh) is not None and _merge_work_orders in _t_wo.get_args(_mh), \
    f"FAIL: modification_history is not Annotated with _merge_work_orders: {_mh}"
_ok_wo("W5", "State.modification_history is Annotated with this reducer")

# W6: test_cases carries a reducer too. Three sync tools write it, and the
# orchestrator prompt says a hover-touching style change calls sync_css AND
# sync_hover -- one superstep, two writes. They now return DELTAS, so the
# dedup-by-id reducer merges both without either overwriting the other.
assert _t_wo.get_origin(_hints["test_cases"]) is not None, \
    "FAIL: test_cases lost its reducer — two sync tools in one step would collide"
assert _merge_test_cases in _t_wo.get_args(_hints["test_cases"]), \
    "FAIL: test_cases is Annotated, but not with _merge_test_cases"
_ok_wo("W6", "test_cases is Annotated with _merge_test_cases (parallel sync safe)")

print("=" * 76)
print(f"State reducers: {_passed_wo}/6 PASSED")
print("=" * 76)
