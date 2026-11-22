# Ported from fyp.ipynb cell 103 (ticket 05). The notebook is frozen;
# edit this file. Run by tests/test_notebook_cells.py.
# Unit tests: shared schema and rule guards  (offline)
#
# This cell used to test the System Design Planning AGENT's own state schema
# (PlanningState) and system prompt. That agent was replaced by
# run_planning_pipeline on 2026-08-23, so the PlanningState channel checks
# (old PS-1, PS-2, PS-4) and the prompt-shape checks (old PS-10, PS-11) went
# with it. What remains are the guards that outlived the agent:
#   PS-3  _assert_channels still refuses a missing channel (the orchestrator
#         and developer builds rely on it)
#   PS-5  every remaining agent schema declares the channels its tools write
#   PS-6  no schema name is shared by two agents (the class State trap)
#   PS-7  the responsiveness field is still read
#   PS-9  the checkout vocabulary still agrees with the schema
# PS-7 and PS-9 used to read the planning prompt; the rules moved into the data
# tables (_SPEC_HOUSE_RULES, _BAYMARD_CHECKLISTS), so the checks now read those.
from tests.package_source import package_cells, package_notebook  # Ticket 05: the package source, not the frozen notebook
import typing as _pt_typing
import ast as _ps_ast
import json as _pt_json
import pathlib as _pt_path
import re as _pt_re
from langchain.agents.middleware import AgentState


_pt_pass = 0

print("[PS-3] _assert_channels raises on a missing channel, not silently.")


class _PtBad(AgentState):
    input_query: str = ""


try:
    _assert_channels(_PtBad, ["input_query", "not_a_channel"], "deliberately-wrong")
    raise SystemExit("FAIL: a missing channel was accepted")
except AssertionError as _e:
    assert "no channel for" in str(_e), _e
    print("    ", str(_e)[:96])
print("PASS\n")
_pt_pass += 1

print("[PS-5] Every remaining agent schema declares the channels its tools write.")
_PT_REQUIRED = {
    "ContextState": ["design_schema", "tavily_search_result"],
    "HtmlState": ["html_code", "lint_passed", "lint_attempts",
                  "last_extracted_component", "patch_attempts"],
    "CssState": ["css_code", "lint_passed", "coverage_attempts"],
        # layout_specification is written into the sub-agent's INITIAL
        # state by call_css_agent, not by a CssState tool, but the drop is
        # just as silent, so it is checked in the same place.
    "JsState": ["js_code", "lint_passed"],
}
_pt_text = "\n".join(
    "".join(c["source"])
    for c in package_cells()
    if c["cell_type"] == "code")
for _schema, _needs in _PT_REQUIRED.items():
    _m = _pt_re.search(r"class %s\(AgentState\):(.*?)(?=\nclass |\n@|\n\S)" % _schema,
                       _pt_text, _pt_re.S)
    assert _m, f"{_schema} is not declared anywhere in the notebook"
    for _need in _needs:
        assert _need in _m.group(1), (
            f"{_schema} has no channel for {_need!r}. A tool writing it would "
            f"have the write dropped with no error.")
    print(f"     {_schema:<14} declares {', '.join(_needs)}")
print("PASS\n")
_pt_pass += 1

print("[PS-6] REGRESSION: no schema name is shared by two agents.")
_ps_cells = package_cells()
_ps_generic = []
_ps_used = {}
for _i, _c in enumerate(_ps_cells):
    if _c["cell_type"] != "code":
        continue
    _s = "".join(_c["source"])
    try:
        _tree = _ps_ast.parse(_s)
    except SyntaxError:
        continue
    for _n in _tree.body:
        if isinstance(_n, _ps_ast.ClassDef) and _n.name == "State":
            _ps_generic.append(_i)
    for _mm in _pt_re.finditer(r"(\w+)\s*=\s*create_agent\(", _s):
        _sm = _pt_re.search(r"state_schema\s*=\s*(\w+)", _s[_mm.end():_mm.end() + 2000])
        if _sm and _sm.group(1) != "state_schema":
            _ps_used.setdefault(_sm.group(1), []).append((_i, _mm.group(1)))
assert not _ps_generic, (
    f"`class State` is back at cell(s) {_ps_generic}. Give it an agent-specific "
    "name -- a shared name makes the captured schema depend on run order.")
_ps_shared = {k: v for k, v in _ps_used.items() if len(v) > 1}
assert not _ps_shared, f"one schema serves several agents: {_ps_shared}"
for _k in sorted(_ps_used):
    print("     %-22s <- cell %-4d %s" % (_k, _ps_used[_k][0][0], _ps_used[_k][0][1]))
print("     no `class State` anywhere; %d schemas, %d agents, one each"
      % (len(_ps_used), sum(len(v) for v in _ps_used.values())))
print("PASS\n")
_pt_pass += 1

print("[PS-7] Responsive is FIXED: always on, never a user-selectable field.")
assert "responsiveness" not in _pt_typing.get_type_hints(UI), \
    "PS-7 FAIL: ui.responsiveness came back as a user-selectable field"
assert "always built responsive" in layout_prompt.template, \
    "PS-7 FAIL: the layout prompt no longer states the page is always responsive"
assert "MOBILE" in _SPEC_HOUSE_RULES, \
    "PS-7 FAIL: the house rules no longer mention the mobile breakpoint"
print("PASS\n")
_pt_pass += 1

print("[PS-9] The checkout checklist and the schema vocabulary still agree.")
# The checklist moved from the planning prompt into _BAYMARD_CHECKLISTS, so this
# reads the data table. Each role/action/state it names still needs a home in
# the schema, or the planner is told to specify something it cannot express.
_ck = " ".join(_BAYMARD_CHECKLISTS["checkout"]).lower()
for _phrase in ("five stages", "order confirmation", "summary",
                "togglevisibility", "submitorder", "aria-current"):
    assert _phrase in _ck, f"PS-9 FAIL: the checkout checklist no longer says {_phrase!r}"
for _needed in ("checkout-steps", "order-confirmation"):
    assert _needed in _pt_typing.get_args(ComponentCategory), \
        f"PS-9 FAIL: ComponentCategory has no '{_needed}' value."
for _needed in ("advanceStep", "submitOrder", "toggleVisibility"):
    assert _needed in _pt_typing.get_args(ActionType), \
        f"PS-9 FAIL: ActionType has no '{_needed}' value."
for _st in ("expanded", "collapsed", "success"):
    assert _st in RECOMMENDED_STATES, \
        f"PS-9 FAIL: '{_st}' is not in RECOMMENDED_STATES."
print("PASS  checklist phrases + 2 roles + 3 actions + 3 stage states all present\n")
_pt_pass += 1

print(f"shared schema/rule guards: {_pt_pass}/5 PASSED")
