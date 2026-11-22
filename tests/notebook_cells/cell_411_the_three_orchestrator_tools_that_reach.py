# Ported from fyp.ipynb cell 411 (ticket 05). The notebook is frozen;
# edit this file. Run by tests/test_notebook_cells.py.
# Unit tests: the three orchestrator tools that reach a sub-agent
#
# Each tool is driven against a stand-in sub-agent, so nothing here calls a
# model. What is being checked is the wiring the orchestrator depends on: the
# sub-run's result reaches working_memory, an existing working memory is not
# wiped by a later stage, the progress pane's indent is restored even when the
# sub-run raises, and every channel these tools write is one the state schema
# can actually hold.
#
# The accept path of the whole chain needs the real agents and is covered by
# the live scenarios instead.
from tests.package_source import package_cells, package_notebook  # Ticket 05: the package source, not the frozen notebook
import ast as _o_ast
import json as _o_json
import pathlib as _o_path
import typing as _o_typing
from types import SimpleNamespace as _SN_ORC


class _StubSubAgent:
    """Stands in for a sub-agent: replays fixed chunks, or raises."""

    def __init__(self, updates=None, custom=None, boom=False):
        self._updates = updates or {}
        self._custom = custom or []
        self._boom = boom

    def stream(self, payload, **kwargs):
        for message in self._custom:
            yield ("custom", message)
        if self._boom:
            raise RuntimeError("sub-agent exploded")
        yield ("updates", {"tools": self._updates})


# Preconditions. Everything below drives an object one of the cells above
# defines, so a kernel that has not run them should say which cell to run
# rather than name whichever object it reached first.
_STATE_CELL = ("the cell whose first line is '# WorkingMemory and "
               "OrchestratorState - what the Primary Orchestrator carries'")
_o_absent = [_n for _n in ("OrchestratorState", "call_context_engineering_agent",
                           "call_system_design_planning_agent", "update_input")
             if _n not in globals()]
if _o_absent:
    raise NameError(
        f"{_o_absent} are not in this kernel. Run the cells above this one "
        f"first, starting at {_STATE_CELL}.")
if "design_schema" not in _o_typing.get_type_hints(OrchestratorState):
    raise AssertionError(
        "This kernel holds an OLDER OrchestratorState, one with no "
        f"design_schema channel. Re-run {_STATE_CELL}, then the three tool "
        "cells directly above this one, then this cell again.")


_orc_events = []


class _OrcWriter:
    def __call__(self, x):
        _orc_events.append(x)


def _rt_orc(state):
    return _SN_ORC(state=state, tool_call_id="orc-1")


# Remember whether each name was there at all, not just its value. Restoring
# only the ones that existed would leave a stand-in bound under a real agent's
# name, and a live run afterwards would stream the stand-in and report success.
_NOT_BOUND = object()
_orc_saved = {_n: globals().get(_n, _NOT_BOUND)
              for _n in ("get_stream_writer", "context_engineering_agent",
                         "run_planning_pipeline")}
globals()["get_stream_writer"] = lambda: _OrcWriter()
try:
    print("[Case 1 · NORMAL] The context agent's schema reaches BOTH places it is read from.")
    globals()["context_engineering_agent"] = _StubSubAgent(
        updates={"design_schema": {"ui": {"type": "storefront"}}},
        custom=["[Context] working..."])
    _r = call_context_engineering_agent.func(
        _rt_orc({"working_memory": {"layout_specification": {"pages": [1]}}}),
        query="build a shop")
    assert _r.update["design_schema"] == {"ui": {"type": "storefront"}}, _r.update
    assert _r.update["working_memory"]["design_schema"] == {"ui": {"type": "storefront"}}
    # the planning tool reads working_memory first, so anything already there
    # has to survive -- a plain overwrite would lose it
    assert _r.update["working_memory"]["layout_specification"] == {"pages": [1]}, \
        "FAIL: an existing working_memory key was dropped"
    assert "[Context] working..." in _orc_events, "FAIL: sub-agent progress not forwarded"
    print("PASS: schema stored twice over, existing memory kept, progress forwarded\n")

    print("[Case 2 · NORMAL] The planner's four specifications arrive as ONE working memory.")
    def _fake_pipeline_ok(input_query, design_schema, *, progress=None, tool_call_id="x"):
        if progress:
            progress("\t[Design Pipeline] Generating layout specification...")
        return ({
            "design_schema": design_schema,
            "layout_specification": {"pages": ["p"]},
            "components_specification": {"pages": ["c"]},
            "interactions_specification": {"pages": ["i"]},
            "decoration_specification": {"pages": ["d"]},
        }, None)
    globals()["run_planning_pipeline"] = _fake_pipeline_ok
    _r = call_system_design_planning_agent.func(
        _rt_orc({"working_memory": {"design_schema": {"ui": {}}}, "input_query": "q"}),
        query="")
    _wm = _r.update["working_memory"]
    assert set(_wm) == {"design_schema", "layout_specification", "components_specification",
                        "interactions_specification", "decoration_specification"}, _wm
    assert all(_wm[k] for k in _wm), f"FAIL: a specification came back empty: {_wm}"
    assert list(_r.update) == ["working_memory", "messages"], \
        f"FAIL: the four specs must land in one write, got {list(_r.update)}"
    print("PASS: four specifications in a single working_memory write\n")

    print("[Case 3 · EDGE] A planner that produces nothing keeps the design schema it was given.")
    def _fake_pipeline_empty(input_query, design_schema, *, progress=None, tool_call_id="x"):
        return ({
            "layout_specification": {},
            "components_specification": {},
            "interactions_specification": {},
            "decoration_specification": {},
        }, "[planning] the layout_specification stage produced no output and the run stopped.")
    globals()["run_planning_pipeline"] = _fake_pipeline_empty
    _r = call_system_design_planning_agent.func(
        _rt_orc({"working_memory": {}, "design_schema": {"theme": {"mode": "dark"}}}),
        query="q")
    _wm = _r.update["working_memory"]
    assert _wm["design_schema"] == {"theme": {"mode": "dark"}}, \
        "FAIL: the top-level design_schema fallback was not used"
    assert _wm["layout_specification"] == {}, _wm
    print("PASS: empty sub-run degrades to empty specs, schema preserved\n")

    print("[Case 4 · GUARD] A sub-agent that raises still closes the indent it opened.")
    # writer({'indent': +1}) runs before the sub-run. Without the matching -1
    # the Streamlit progress pane stays indented for the rest of the session.
    _orc_events.clear()
    globals()["context_engineering_agent"] = _StubSubAgent(boom=True)
    try:
        call_context_engineering_agent.func(_rt_orc({"working_memory": {}}), query="q")
    except RuntimeError:
        pass
    else:
        raise AssertionError("FAIL: the sub-agent error was swallowed")
    _deltas = [e.get("delta") for e in _orc_events if isinstance(e, dict) and "delta" in e]
    assert sum(_deltas) == 0, f"FAIL: indent left open, deltas={_deltas}"
    print(f"     the error propagates, deltas {_deltas} sum to 0")
    print("PASS: failure path restores the indent level\n")

    print("[Case 5 · NORMAL] update_input commits the request and echoes the call id.")
    _r = update_input.func(_rt_orc({"input_query": "build a shop"}))
    assert _r.update["input_query"] == "build a shop", _r.update
    assert _r.update["messages"][0].tool_call_id == "orc-1", "FAIL: tool_call_id not echoed"
    _r = update_input.func(_rt_orc(None))
    assert _r.update["input_query"] == "", "FAIL: a missing state should give an empty query"
    print("PASS: request committed, call id echoed, empty state survived\n")

finally:
    for _n, _v in _orc_saved.items():
        if _v is _NOT_BOUND:
            globals().pop(_n, None)
        else:
            globals()[_n] = _v
    assert not isinstance(globals().get("context_engineering_agent"), _StubSubAgent), \
        "FAIL: a stand-in is still bound to context_engineering_agent"

print("[Case 6 · GUARD] Every channel these tools write is one OrchestratorState declares.")
# Read from the notebook file rather than from memory. A kernel that still
# holds an older schema would otherwise pass a check the saved notebook fails.
_o_nb = package_notebook()
_o_written = set()
for _c in _o_nb["cells"]:
    if _c["cell_type"] != "code":
        continue
    _s = "".join(_c["source"])
    if "ToolRuntime[OrchestratorState]" not in _s:
        continue
    for _node in _o_ast.walk(_o_ast.parse(_s)):
        if not (isinstance(_node, _o_ast.Call) and getattr(_node.func, "id", "") == "Command"):
            continue
        for _kw in _node.keywords:
            if _kw.arg == "update" and isinstance(_kw.value, _o_ast.Dict):
                for _k in _kw.value.keys:
                    if isinstance(_k, _o_ast.Constant) and isinstance(_k.value, str):
                        _o_written.add(_k.value)
assert _o_written, "FAIL: no orchestrator tool found in the notebook file"
_o_declared = set(_o_typing.get_type_hints(OrchestratorState, include_extras=True))
_o_dropped = sorted(_o_written - _o_declared)
assert not _o_dropped, (
    f"FAIL: {_o_dropped} would be written and silently dropped -- "
    f"declare them in OrchestratorState")
print(f"     written by the tools: {sorted(_o_written)}")
print("PASS: no orchestrator write can be dropped\n")

print("Orchestrator tools: 6/6 cases PASSED")
