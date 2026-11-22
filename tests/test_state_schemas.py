"""The state-schema guards: no write can be dropped silently.

    python tests/test_state_schemas.py

LangGraph drops a write to a channel the agent's state schema does not declare,
with no error (see CLAUDE.md, "State schemas"). Two guards keep that from
happening, ported from the frozen notebook's PS-5 and PS-6 so they run again:

  SS-5  every agent schema declares the channels its tools write
  SS-6  no `class State`, and no schema is bound to two agents

Both read the SOURCE of the system (every webforge/**/*.py module; the flat
fyp.py until ticket 04, then its shim until ticket 15), so they need no import
and no model. Each
checker is first run on a planted violation, to prove it can go red.
Exits non-zero on any failure.
"""
from __future__ import annotations

import ast
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent

# The channels each schema must declare (from notebook PS-5). A tool writing a
# channel missing here would lose the write with no error.
REQUIRED_CHANNELS = {
    "ContextState": ["design_schema", "tavily_search_result"],
    "HtmlState": ["html_code", "lint_passed", "lint_attempts",
                  "last_extracted_component", "patch_attempts"],
    # layout_specification is written into the CSS agent's INITIAL state by
    # call_css_agent, not by a CssState tool, but the drop is just as silent.
    "CssState": ["css_code", "lint_passed", "coverage_attempts", "css_pending"],
    "JsState": ["js_code", "lint_passed"],
}


# The calls that build an agent. build_dev_agent (ticket 08) wraps create_agent
# for the developer agents and takes the same state_schema= keyword.
AGENT_BUILDERS = ("create_agent", "build_dev_agent")


def schema_binding_problems(source: str) -> tuple[list[str], dict[str, list[str]]]:
    """Return (problems, {schema: [agent, ...]}) for one module's source."""
    tree = ast.parse(source)
    problems = []
    used: dict[str, list[str]] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == "State":
            problems.append(f"`class State` at line {node.lineno}: give it an "
                            "agent-specific name")
        if (isinstance(node, ast.Assign) and isinstance(node.value, ast.Call)
                and getattr(node.value.func, "id", None) in AGENT_BUILDERS):
            agent = ast.unparse(node.targets[0])
            for kw in node.value.keywords:
                if kw.arg == "state_schema":
                    used.setdefault(ast.unparse(kw.value), []).append(agent)
    for schema, agents in used.items():
        if len(agents) > 1:
            problems.append(f"{schema} is bound to several agents: {agents}")
    return problems, used


def missing_channels(source: str, required: dict[str, list[str]]) -> list[str]:
    """Return one line per required channel a schema does not declare."""
    declared: dict[str, set[str]] = {}
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.ClassDef):
            declared[node.name] = {
                s.target.id for s in node.body
                if isinstance(s, ast.AnnAssign) and isinstance(s.target, ast.Name)}
    out = []
    for schema, needs in required.items():
        if schema not in declared:
            out.append(f"{schema} is not declared")
            continue
        out += [f"{schema} has no channel for {n!r}" for n in needs
                if n not in declared[schema]]
    return out


failures: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + (f"  ({detail})" if detail else ""))
    if not ok:
        failures.append(name)


PLANTED_STATE = """
class State(AgentState):
    x: str
a = create_agent(model=m, state_schema=State)
"""
PLANTED_SHARED = """
class AState(AgentState):
    x: str
a = create_agent(model=m, state_schema=AState)
b = create_agent(model=m, state_schema=AState)
"""
PLANTED_MISSING = """
class JsState(AgentState):
    js_code: str
"""


def main() -> int:
    # The checkers go red on planted violations.
    p, _ = schema_binding_problems(PLANTED_STATE)
    check("SS-6 planted `class State` is caught", any("class State" in x for x in p))
    p, _ = schema_binding_problems(PLANTED_SHARED)
    check("SS-6 planted shared schema is caught", any("several agents" in x for x in p))
    m = missing_channels(PLANTED_MISSING, {"JsState": ["js_code", "lint_passed"]})
    check("SS-5 planted missing channel is caught", m == ["JsState has no channel for 'lint_passed'"], str(m))

    # The real source.
    src = "\n".join(p.read_text(encoding="utf-8")
                    for p in sorted((ROOT / "webforge").rglob("*.py")))
    problems, used = schema_binding_problems(src)
    check("SS-6 system: no `class State`, one schema per agent", not problems, "; ".join(problems))
    n_agents = sum(len(v) for v in used.values())
    check("SS-6 system: create_agent calls found", n_agents >= 7, f"{n_agents} agents")
    missing = missing_channels(src, REQUIRED_CHANNELS)
    check("SS-5 system: every required channel declared", not missing, "; ".join(missing))

    n_channels = sum(len(v) for v in REQUIRED_CHANNELS.values())
    print(f"[proof] schemas: {len(used)} schemas bound to {n_agents} agents, "
          f"{sum(len(v) > 1 for v in used.values())} shared, "
          f"{sum('class State' in x for x in problems)} `class State`; "
          f"{n_channels - len(missing)}/{n_channels} required channels declared; "
          f"3/3 planted violations caught. Before this file, 0 of these checks ran "
          f"offline (PS-5/PS-6 lived only in the frozen notebook).")
    print(f"{'FAILED' if failures else 'OK'}: {len(failures)} failure(s)")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
