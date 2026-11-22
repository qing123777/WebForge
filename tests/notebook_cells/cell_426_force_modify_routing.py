# Ported from fyp.ipynb cell 426 (ticket 05). The notebook is frozen;
# edit this file. Run by tests/test_notebook_cells.py.
# Unit tests: force_modify_routing
# The whole point of this middleware is that it can be proved without paying for
# a run, so every branch is exercised here against a stand-in request.
_fmr_passed = 0


def _fmr_ok(case, description):
    global _fmr_passed
    _fmr_passed += 1
    print(f"  PASS  {case}  {description}")


class _FMRTool:
    def __init__(self, name):
        self.name = name


class _FMRRequest:
    """Only the three attributes the middleware touches."""

    ALL = ("update_input", "ask_user", "call_context_engineering_agent",
           "call_system_design_planning_agent", "call_secondary_orchestrator")

    def __init__(self, state, tools=None):
        self.state = state
        self.tools = [_FMRTool(n) for n in (tools if tools is not None else self.ALL)]

    def override(self, **kw):
        clone = _FMRRequest(self.state, [])
        clone.tools = self.tools
        for k, v in kw.items():
            setattr(clone, k, v)
        return clone


def _fmr_human(text):
    return {"role": "user", "content": text}


def _fmr_run(state, tools=None):
    """Return the tool names the model would actually be offered."""
    seen = {}

    def handler(req):
        seen["names"] = [_fmr_tool_name(t) for t in (req.tools or [])]
        return "model-response"

    out = _force_modify_routing(_FMRRequest(state, tools), handler)
    assert out == "model-response", "the middleware must return the handler's result"
    return seen["names"]


# Written out rather than built with _po_modify_marker, which lives in the
# Primary Orchestrator E2E harness far below this cell. Calling it from here
# would raise NameError on a straight top-to-bottom run, which is the one thing
# a test cell placed under its code must never do. The shape is asserted against
# that function in the harness instead, where both names exist.
_MARKER = ("[intent=modify | target_component=add-to-cart-button "
           "| target_instance=1] make this button green")

# FMR-1  THE POINT. A modify turn cannot reach the planning agents.
_names = _fmr_run({"messages": [_fmr_human(_MARKER)]})
assert "call_context_engineering_agent" not in _names, \
    "FMR-1 FAIL: a modify turn can still rebuild the design schema"
assert "call_system_design_planning_agent" not in _names, \
    "FMR-1 FAIL: a modify turn can still rebuild the specifications"
assert "call_secondary_orchestrator" in _names, \
    "FMR-1 FAIL: the one allowed route was removed"
_fmr_ok("FMR-1", "a modify marker withholds both planning tools")

# FMR-2  ask_user goes too. The user has already said what to change, so a
# clarifying dialogue here is a second question about a settled request.
assert "ask_user" not in _names, "FMR-2 FAIL: a modify turn can still open a dialogue"
assert set(_names) == set(_MODIFY_TOOLS), \
    f"FMR-2 FAIL: expected exactly {_MODIFY_TOOLS}, got {_names}"
_fmr_ok("FMR-2", "exactly update_input and call_secondary_orchestrator remain")

# FMR-3  A generate turn is untouched. This middleware must be invisible to
# every case that is not a modify.
_names = _fmr_run({"messages": [_fmr_human("Generate an umbrella shop.")]})
assert set(_names) == set(_FMRRequest.ALL), \
    f"FMR-3 FAIL: a generate turn lost tools: {_names}"
_fmr_ok("FMR-3", "a request with no marker keeps every tool")

# FMR-4  A marker with no target is malformed. Narrowing there would trap the
# model with a route it cannot aim, so it is left alone to answer the user.
for _bad in ("[intent=modify] make it green",
             "[intent=modify | target_component= | target_instance=1] green"):
    assert set(_fmr_run({"messages": [_fmr_human(_bad)]})) == set(_FMRRequest.ALL), \
        f"FMR-4 FAIL: narrowed on a marker with no target: {_bad!r}"
_fmr_ok("FMR-4", "a marker naming no component changes nothing")

# FMR-5  The parse survives the spacing and casing an interface might produce.
for _variant in ("[intent=modify | target_component=hero | target_instance=2]",
                 "[ intent = modify | target_component = hero | target_instance = 2 ]",
                 "[INTENT=MODIFY | TARGET_COMPONENT=hero | TARGET_INSTANCE=2]"):
    _f = modify_marker_fields(_variant)
    assert _f.get("target_component") == "hero", f"FMR-5 FAIL: {_variant!r} -> {_f}"
    assert _f.get("target_instance") == "2", f"FMR-5 FAIL: instance lost in {_variant!r}"
_fmr_ok("FMR-5", "the marker parses despite spacing and case")

# FMR-6  PO-07 seeds the state directly rather than sending a marker, and the
# real panel sends a marker with no seed. Both have to work.
_names = _fmr_run({"messages": [_fmr_human("make this button green")],
                   "intent": "modify", "target_component": "add-to-cart-button"})
assert set(_names) == set(_MODIFY_TOOLS), \
    f"FMR-6 FAIL: a seeded modify was not narrowed: {_names}"
_fmr_ok("FMR-6", "a seeded modify narrows even with no marker in the text")

# FMR-7  A stale intent must not narrow a fresh generate. reset_before clears
# intent every turn, and this is the belt to that braces.
_names = _fmr_run({"messages": [_fmr_human("Generate a shoe shop.")],
                   "intent": "generate", "target_component": "add-to-cart-button"})
assert set(_names) == set(_FMRRequest.ALL), \
    f"FMR-7 FAIL: a leftover target_component narrowed a generate turn: {_names}"
_fmr_ok("FMR-7", "a target left over from a previous turn does not narrow a generate")

# FMR-8  Never hand the model a list without the route it is being pushed to.
_names = _fmr_run({"messages": [_fmr_human(_MARKER)]},
                  tools=["update_input", "ask_user"])
assert set(_names) == {"update_input", "ask_user"}, \
    f"FMR-8 FAIL: narrowed to a list with no way to dispatch: {_names}"
_fmr_ok("FMR-8", "with no dispatch tool present, nothing is narrowed")

# FMR-9  Declining stays possible. tool_choice is never set, so the model can
# still answer in words, which is how a structural modify is refused.
_probe = _FMRRequest({"messages": [_fmr_human(_MARKER)]})
_captured = {}


def _probe_handler(req):
    _captured["tool_choice"] = getattr(req, "tool_choice", None)
    return "ok"


_force_modify_routing(_probe, _probe_handler)
assert _captured["tool_choice"] is None, \
    "FMR-9 FAIL: tool_choice was forced, so the model can no longer decline"
_fmr_ok("FMR-9", "tool_choice is untouched, so a structural modify can be declined")

print("=" * 76)
print(f"force_modify_routing: {_fmr_passed}/9 PASSED  "
      f"(modify turns keep: {', '.join(_MODIFY_TOOLS)})")
print("=" * 76)
