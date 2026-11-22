# Ported from fyp.ipynb cell 43 (ticket 05). The notebook is frozen;
# edit this file. Run by tests/test_notebook_cells.py.
# Unit tests: ContextState and the Context Engineering Agent
#
# Case 1 is the important one. It is a direct guard against the bug this cell
# was written to remove.
from tests.package_source import package_cells, package_notebook  # Ticket 05: the package source, not the frozen notebook
import typing as _cs_typing

_CS_CASES = 0

# ── Case 1: every field written through this schema is declared ────────────
# LangGraph drops a write to an undeclared field. It logs the drop and carries
# on, so nothing raises and the field simply stays empty. A schema missing one
# of these would look like a model that refused to answer.
#
# The four specification fields are written by the planning chain's generators,
# not by this agent's three tools. They are here because those generators still
# annotate themselves with this schema. Step 7 gives them their own.
#
# ContextState is a TypedDict, so its fields are type hints, not model fields.
_WRITES = {"input_query", "design_schema", "tavily_search_result",
           "layout_specification", "components_specification",
           "interactions_specification", "decoration_specification"}
_declared = set(_cs_typing.get_type_hints(ContextState))
_missing = _WRITES - _declared
assert not _missing, (
    f"Case 1 FAIL: ContextState does not declare {sorted(_missing)}. A tool "
    f"writing one of those would have the write dropped with no error, and the "
    f"field would simply stay empty.")
assert "messages" in _declared, "Case 1 FAIL: the conversation channel is missing"
_CS_CASES += 1
print(f"PASS Case 1 - all {len(_WRITES)} fields written through this schema are declared, plus messages")

# ── Case 2: the old shared name is gone from the notebook ──────────────────
# Three different classes were once called `state`, and only the last was
# reachable by name. With distinct names a stale reference is a NameError,
# which is loud, instead of a silent bind to the wrong class.
#
# Read the FILE, not globals(). A kernel that ran the older notebook still has
# the old name bound, because deleting a cell does not unbind what it already
# put in memory. Checking globals() would fail on a correct notebook and pass
# on a broken one that had simply not been run yet.
import ast as _cs_ast
import json as _cs_json
import pathlib as _cs_path

_nb_cells = package_cells()
if _nb_cells:
    _offenders = []
    for _n, _c in enumerate(_nb_cells):
        if _c["cell_type"] != "code":
            continue
        try:
            _tree = _cs_ast.parse("".join(_c["source"]))
        except SyntaxError:
            continue
        for _st in _tree.body:
            if isinstance(_st, _cs_ast.ClassDef) and _st.name == "state":
                _offenders.append((_n, "class state"))
            if isinstance(_st, _cs_ast.Assign):
                for _t in _st.targets:
                    if isinstance(_t, _cs_ast.Name) and _t.id == "state":
                        _offenders.append((_n, "state = ..."))
    assert not _offenders, (
        f"Case 2 FAIL: the notebook binds a bare `state` at top level in "
        f"{_offenders}. Three classes once shared that name and the wrong one "
        f"won. Give each schema its own name.")
    print("PASS Case 2 - no cell in the notebook binds a bare `state` name")
else:
    print("SKIP Case 2 - run this from the folder holding fyp.ipynb to check the file")
_CS_CASES += 1

# ── Case 3: this notepad belongs to one agent, not to all of them ──────────
# The rule is one schema per agent, each with its own name. The orchestrator
# keeps its progress in a field called working_memory. If that appeared here,
# the two agents would be sharing a notepad again, which is how the original
# three-way name clash started.
assert "working_memory" not in _declared, (
    "Case 3 FAIL: ContextState declares working_memory, which belongs to the "
    "orchestrator. Two agents sharing one notepad is the clash this cell removed.")
_EXPECTED = _WRITES | {"compiled_query"}
_lost = _EXPECTED - _declared
assert not _lost, f"Case 3 FAIL: these fields were lost in the move: {sorted(_lost)}"
_CS_CASES += 1
print(f"PASS Case 3 - {len(_declared)} fields declared, and none of them belongs to another agent")

# ── Case 4: ask the BUILT agent what it is wired to ────────────────────────
# Read this from the agent itself, never from the tool objects. Listing the
# three tools and checking their names proves only that they are named what
# they are named. It would pass with the agent wired to nothing.
_registered = set(context_engineering_agent.nodes["tools"].bound.tools_by_name)
assert _registered == {"extract_intent_signals", "tavily_search_tool",
                       "update_extra_requirements"}, \
    f"Case 4 FAIL: the agent is wired to {sorted(_registered)}"
_CS_CASES += 1
print(f"PASS Case 4 - the built agent is wired to exactly its {len(_registered)} tools")

# ── Case 5: the reset hook is actually installed ───────────────────────────
# Middleware appears in the compiled graph as a node named after the function.
# A reset that was written but never passed to the agent would leave every
# second message building on the first message's schema.
_nodes = set(context_engineering_agent.nodes)
assert "context_reset_before.before_agent" in _nodes, (
    f"Case 5 FAIL: the reset hook is not installed on the agent. Nodes present: "
    f"{sorted(_nodes)}")
assert "context_agent_progress.before_agent" in _nodes, \
    "Case 5 FAIL: the progress hook is not installed on the agent"
_CS_CASES += 1
print("PASS Case 5 - the reset hook and the progress hook are both installed")

# ── Case 6: the reset clears the last run and keeps the query ──────────────
# Without this, a second message in one conversation would extend the first
# message's schema instead of replacing it.
_reset = context_reset_before.before_agent
_out = _reset({"input_query": "build a shop",
               "design_schema": {"ui": {"type": "cart"}},
               "tavily_search_result": "stale text"}, None)
assert _out["input_query"] == "build a shop", "Case 6 FAIL: the query was not preserved"
assert _out["design_schema"] == {}, "Case 6 FAIL: the previous schema was not cleared"
assert _out["tavily_search_result"] == "", "Case 6 FAIL: the previous search was not cleared"
_CS_CASES += 1
print("PASS Case 6 - the reset keeps the query and clears what the last run produced")

# ── Case 7: the query is recovered from the conversation ───────────────────
# The application layer does not always set the query field. When it does not,
# the last thing the user typed has to be found in the message history, or the
# agent would run against an empty request.
_out = _reset({"messages": [{"role": "user", "content": "make me a shop"}]}, None)
assert _out["input_query"] == "make me a shop", \
    f"Case 7 FAIL: the query was not recovered from the conversation: {_out}"
_CS_CASES += 1
print("PASS Case 7 - with no query set, the last user message is used instead")

# ── Case 8: the prompt still carries the rules the agent depends on ────────
import re as _cs_re
# Wording changed on 2026-08-16 when the prompt was rebuilt around the five
# elements. These are the phrases that carry behaviour, not style.
for _rule in ("extract_intent_signals", "runs FIRST, on every request",
              "Decline anything else in one sentence", "tech_stack",
              "You never write `design_schema` yourself",
              "only when ROUTING below is satisfied",
              "only when `tavily_search_result` is non-empty"):
    assert _rule in _cs_re.sub(r"\\s+", " ", _context_system_prompt), \
        f"Case 8 FAIL: the prompt no longer contains {_rule!r}"
_CS_CASES += 1
print("PASS Case 8 - the prompt still demands extraction first and still refuses off-topic work")

# ── Case 9: all five elements of a usable prompt are present ───────────────
# It had three. It was missing VERIFICATION, so a tool message that merely
# sounded successful ended the turn with an empty schema, and ITERATION POLICY,
# so a failed extraction had no defined number of retries at all.
# Match on the WORDING, never on the wrapping. The prompt wraps long sentences,
# so a literal check false-negatives on a line break even when the rule is
# present and correct. Three earlier suites here learned the same lesson.
import re as _cs_re
_cs_flat = _cs_re.sub(r"\s+", " ", _context_system_prompt)

for _section in ("OUTCOME", "VERIFICATION", "ITERATION POLICY",
                 "ERROR HANDLING", "CONSTRAINTS"):
    assert f"\n{_section}\n" in _context_system_prompt, \
        f"Case 9 FAIL: the prompt has no {_section} section"
assert "at most 2 further calls, so 3 for the turn in total" in _cs_flat.lower(), \
    "Case 9 FAIL: the retry budget is gone, so a failed extraction can loop"
assert "The state field is the only evidence." in _cs_flat, \
    "Case 9 FAIL: the verification rule no longer names the state field"
_CS_CASES += 1
print("PASS Case 9 - outcome, verification, constraints, iteration policy and error handling all present")

# ── Case 10: the prompt no longer contradicts the schema ───────────────────
# It used to say "DO NOT infer or assume unspecified attributes (e.g., colors,
# features, styles)". The style field's own description says to map "sale" onto
# promotion_heavy. A model reading both takes the safe route and writes null,
# which switches off a planner branch with nothing reporting it.
assert "DO NOT infer" not in _context_system_prompt, (
    "Case 10 FAIL: the blanket no-inference rule is back. It contradicts the "
    "field descriptions, which instruct the model to map loose words onto the "
    "fixed lists, and a contradiction resolves to null.")
assert "ALWAYS map the words they did use onto the fixed lists" in _cs_flat, \
    "Case 10 FAIL: the prompt no longer requires mapping"
assert "Never invent a brand, a colour or a feature" in _cs_flat, \
    "Case 10 FAIL: the prompt no longer forbids inventing what was not asked for"
_CS_CASES += 1
print("PASS Case 10 - inventing forbidden, mapping required, and the two do not conflict")

# ── Case 11: the middleware section is gone ────────────────────────────────
# It described a hook by a name that no longer exists, and the model cannot act
# on a middleware description in any case. Removing it is why the prompt got
# shorter while gaining two sections.
assert "MIDDLEWARE" not in _context_system_prompt, \
    "Case 11 FAIL: the middleware section is back. The model cannot act on it."
assert "reset_before` runs automatically" not in _cs_flat, \
    "Case 11 FAIL: the prompt describes a hook by a name that was changed"
_CS_CASES += 1
print(f"PASS Case 11 - no middleware description ({len(_context_system_prompt)} chars, was 3061)")

# ── Case 12: an empty or unintelligible request is refused, not guessed ────
# "Decline anything else" covered a request for something the system does not
# build. It never reached a request for NOTHING, because an empty string is not
# a request for something else. E2E-CE-05 and E2E-CE-06 send exactly that, so
# the behaviour they check has to be stated somewhere first.
assert "not intelligible as a request for anything" in _cs_flat, \
    "Case 12 FAIL: the prompt no longer covers an unintelligible request"
assert "never invent a page to fill the silence" in _cs_flat.lower() or \
       "never invent a page to fill the silence" in _cs_flat, \
    "Case 12 FAIL: the prompt no longer forbids inventing a page from nothing"
assert "Call no tool" in _cs_flat, \
    "Case 12 FAIL: an empty request may now spend a tool call"
_CS_CASES += 1
print("PASS Case 12 - an empty or unintelligible request is asked about, never guessed at")

print("=" * 64)
print(f"Context Engineering Agent: {_CS_CASES}/12 cases PASSED")
print("=" * 64)
