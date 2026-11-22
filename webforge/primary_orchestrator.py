"""primary_orchestrator: the Primary Orchestrator: working memory, its tools, middleware, the planning pipeline and the graph.

Lines 16755-18359 of the flat fyp.py at commit 6e8c14b, moved
verbatim by refactor ticket 04 (tools/split_fyp.py).
"""
from __future__ import annotations

from webforge.secondary_orchestrator import *  # noqa: F401,F403

# ==========================================================================
# Memory & State
# ==========================================================================
# ═══════════════════════════════════════════════════════════════════════════
# WorkingMemory and OrchestratorState - what the Primary Orchestrator carries
#
# The requirements come out of the Context Engineering Agent, and the four
# specifications come out of the planning chain. This is where they sit in
# between, so the orchestrator can hand the whole set to the sub-workflow in
# one piece.
#
# THE SCHEMA IS DECLARED ABOVE THE TOOLS THAT ANNOTATE IT
# ------------------------------------------------------
# LangGraph drops a write to a field the schema does not declare. It logs the
# drop and carries on, so an undeclared channel costs no error and produces no
# visible difference until something downstream reads an empty value.
#
# `design_schema` was one of those drops. The context tool has always written
# it at top level as well as inside working_memory, and the top-level write has
# never landed, because the schema this agent borrowed declared two fields. It
# is declared here now, and reset_before clears it every turn so the schema
# from one request cannot bleed into the next.
# ═══════════════════════════════════════════════════════════════════════════
from typing import Any, Dict, Literal

from langchain.agents.middleware import AgentState
from pydantic import BaseModel, Field


class WorkingMemory(BaseModel):
    design_schema: Dict[str, Any] = Field(default_factory=dict)
    layout_specification: Dict[str, Any] = Field(default_factory=dict)
    components_specification: Dict[str, Any] = Field(default_factory=dict)
    interactions_specification: Dict[str, Any] = Field(default_factory=dict)
    decoration_specification: Dict[str, Any] = Field(default_factory=dict)


# Which voice the user picked in the interface. Carried, never chosen here, for
# the same reason session_id is: the application layer owns what the user set.
ToneName = Literal["friendly", "concise", "professional"]


class OrchestratorState(AgentState):
    input_query:      str = ""
    tone:             ToneName = "friendly"
    # Issued by the application layer (the Streamlit conversation's
    # thread_id) and carried, not created, here. It names the preview files
    # a later modify has to re-open, so it must outlive a single build.
    session_id:       str = ""
    design_schema:    Dict[str, Any] = Field(default_factory=dict)
    working_memory:   WorkingMemory = Field(default_factory=WorkingMemory)
    intent:           Literal["generate", "modify"] = "generate"
    target_component: str = ""
    target_instance:  int = 1
    # The one clarifying question, as data rather than as a sentence, so the
    # application layer can draw controls for it. reset_before clears it every
    # turn: a question already answered must not be drawn a second time.
    pending_question: Dict[str, Any] = Field(default_factory=dict)
    # Whether the gate has been spent on this thread. Deliberately NOT reset
    # between turns, unlike everything else above. Asking once is the rule the
    # gate exists to enforce, and a per-turn reset would hand the model a fresh
    # question on every reply, which is the interrogation the prompt forbids.
    clarifier_used:   bool = False


# Every channel the four orchestrator tools write. Checked against the schema
# next to create_agent, which is the one cheap place a dropped write shows up.
_ORCHESTRATOR_CHANNELS = ["input_query", "design_schema", "working_memory",
                          "pending_question", "clarifier_used"]


# ==========================================================================
# Tools
# ==========================================================================
# ═══════════════════════════════════════════════════════════════════════════
# call_context_engineering_agent - the orchestrator's door to the first agent
#
# The two agent-calling tools below repeat the same twenty lines of streaming:
# forward every custom event to the parent's writer so the Streamlit pane keeps
# showing progress, and merge every state update into a local dict so the tool
# can read the sub-run's result. The repetition is deliberate. A shared helper
# would sit between the orchestrator and its sub-agents, which is the one
# boundary every guard in this system hangs off.
# ═══════════════════════════════════════════════════════════════════════════
import uuid
from typing import Any, Dict

from langchain.messages import ToolMessage
from langchain.tools import ToolRuntime, tool
from langgraph.config import get_stream_writer
from langgraph.types import Command


@tool
def call_context_engineering_agent(runtime: ToolRuntime[OrchestratorState], query: str) -> Command:
    """Invoke the context_engineering_agent and persist its design_schema into the orchestrator state."""
    writer = get_stream_writer()
    s = runtime.state or {}
    working_memory = s.get("working_memory") if isinstance(s, dict) and isinstance(s.get("working_memory"), dict) else {}

    writer({"type": "indent", "delta": 1})
    try:
        payload = {
            "messages": [{"role": "user", "content": query}],
            "input_query": query,
            "design_schema": {},
            "tavily_search_result": "",
        }

        sub_config = {"configurable": {"thread_id": f"ctx_{uuid.uuid4().hex[:8]}"}}

        captured_sub_state: Dict[str, Any] = {}

        def _merge_state_update(update: Any) -> None:
            if not isinstance(update, dict):
                return
            for key, value in update.items():
                if key == "messages":
                    continue
                captured_sub_state[key] = value

        for chunk in context_engineering_agent.stream(
            payload,
            stream_mode=["updates", "custom"],
            version="v2",
            config=sub_config,
        ):
            if isinstance(chunk, tuple) and len(chunk) == 2:
                chunk_type, data = chunk
            else:
                chunk_type = chunk.get("type")
                data = chunk.get("data")

            if chunk_type == "custom":
                if isinstance(data, (str, dict)):
                    writer(data)
                else:
                    writer(str(data))
            elif chunk_type == "updates" and isinstance(data, dict):
                for _step, update in data.items():
                    _merge_state_update(update)

        design_schema = captured_sub_state.get("design_schema") or {}
        next_working_memory = {**working_memory, "design_schema": design_schema}

        return Command(
            update={
                "design_schema": design_schema,
                "working_memory": next_working_memory,
                "messages": [
                    ToolMessage(
                        content="\t[Orchestrator] Context Engineering Agent completed. Returned design_schema backed to orchestrator.",
                        tool_call_id=runtime.tool_call_id,
                    )
                ],
            }
        )
    finally:
        writer({"type": "indent", "delta": -1})


# ==========================================================================
# Tools
# ==========================================================================
# ═══════════════════════════════════════════════════════════════════════════
# call_system_design_planning_agent - the orchestrator's door to the planner
#
# It reads the design schema out of working_memory, falling back to the
# top-level field, runs the four specification generators as a deterministic
# pipeline (run_planning_pipeline), and writes all four specifications back as
# one working memory. One write, so the four cannot arrive half-updated.
#
# The name still says "agent" because it is the orchestrator's tool name and
# other cells and tests refer to it; the work behind it is now the
# pipeline, not a create_agent sub-agent.
# ═══════════════════════════════════════════════════════════════════════════
from langchain.messages import ToolMessage
from langchain.tools import ToolRuntime, tool
from langgraph.config import get_stream_writer
from langgraph.types import Command


@tool
def call_system_design_planning_agent(runtime: ToolRuntime[OrchestratorState], query: str) -> Command:
    """Run the system design planning pipeline and persist its outputs into orchestrator working_memory."""
    writer = get_stream_writer()
    s = runtime.state or {}
    working_memory = s.get("working_memory") if isinstance(s, dict) and isinstance(s.get("working_memory"), dict) else {}
    input_query = query or (s.get("input_query", "") if isinstance(s, dict) else "")
    design_schema = working_memory.get("design_schema") or (s.get("design_schema") if isinstance(s, dict) else {}) or {}

    writer({"type": "indent", "delta": 1})
    try:
        writer("\t[Design Pipeline] Processing request...")

        # The pipeline threads the four generators in order and stops if one
        # cannot produce its field. progress forwards each stage's line to the
        # chat exactly as the planning agent's middleware used to.
        state, error = run_planning_pipeline(
            input_query, design_schema, progress=writer)

        next_working_memory = {
            "design_schema": state.get("design_schema") or design_schema,
            "layout_specification": state.get("layout_specification") or {},
            "components_specification": state.get("components_specification") or {},
            "interactions_specification": state.get("interactions_specification") or {},
            "decoration_specification": state.get("decoration_specification") or {},
        }

        if error:
            report = ("\t[Orchestrator] System Design & Planning stopped before "
                      "finishing and returned what it had. " + error)
        else:
            report = ("\t[Orchestrator] System Design & Planning Chain completed. "
                      "Returned planning outputs backed to orchestrator.")

        return Command(
            update={
                "working_memory": next_working_memory,
                "messages": [
                    ToolMessage(content=report, tool_call_id=runtime.tool_call_id),
                ],
            }
        )
    finally:
        writer({"type": "indent", "delta": -1})


# ==========================================================================
# Tools
# ==========================================================================
# ═══════════════════════════════════════════════════════════════════════════
# update_input - records the request the orchestrator is working on
#
# reset_before has already lifted the request out of the message list by the
# time any tool runs, so this reads state rather than a parameter. Calling it
# is what commits that value for the rest of the turn.
# ═══════════════════════════════════════════════════════════════════════════
from langchain.messages import ToolMessage
from langchain.tools import ToolRuntime, tool
from langgraph.types import Command


@tool
def update_input(runtime: ToolRuntime[OrchestratorState]) -> Command:
    """Persist the current input query into agent state."""
    s = runtime.state or {}
    input_query = s.get("input_query", "") if isinstance(s, dict) else ""

    return Command(
        update={
            "input_query": input_query,
            "messages": [
                ToolMessage(
                    content="\t[Orchestrator] Recorded request.",
                    tool_call_id=runtime.tool_call_id,
                )
            ],
        }
    )


# ==========================================================================
# Tools
# ==========================================================================
# ── Outcome helpers for call_secondary_orchestrator ─────────────────────────
# Same lesson as _artifact_outcome one layer down: the ToolMessage is the ONLY
# channel the Primary Orchestrator reads, so anything it hardcodes is something
# the orchestrator will repeat as fact. This tool used to return
# "Secondary Orchestrator completed." whether the suite passed, failed, or never
# produced a file.

def _layout_page_count(layout_spec) -> int:
    """Number of pages a LayoutSpecification asks for, 0 when unknown."""
    if isinstance(layout_spec, str):
        try:
            layout_spec = json.loads(layout_spec)
        except Exception:
            return 0
    if not isinstance(layout_spec, dict):
        return 0
    pages = layout_spec.get("pages")
    return len(pages) if isinstance(pages, list) else 0


def _failed_lines(test_report: str, limit: int = 6) -> list:
    """The FAILED lines of a report, capped. _build_report emits one per case."""
    lines = [ln.strip() for ln in (test_report or "").splitlines()
             if ln.strip().startswith("FAILED:")]
    if len(lines) > limit:
        lines = lines[:limit] + [f"... and {len(lines) - limit} more"]
    return lines


def _secondary_outcome(session_id: str, captured: dict) -> str:
    """Build the ToolMessage from what the sub-graph actually produced."""
    report   = captured.get("test_report", "") or ""
    attempts = captured.get("modification_attempts", 0) or 0
    written  = [e for e in ("html", "css", "js")
                if _preview_fingerprint(session_id, e)]

    if not written:
        return ("[Orchestrator] Secondary Orchestrator produced NO artefacts for "
                f"session '{session_id}'. Nothing was written to disk. Report "
                "this as a FAILED build -- do not describe a page to the user.")

    files = ", ".join(f"preview_{session_id}.{e}" for e in written)
    rounds = ("first pass, no correction round"
              if attempts == 0 else
              f"{attempts} correction round(s) of a maximum {_MODIFICATION_ATTEMPT_CAP}")

    if not report:
        return ("[Orchestrator] Secondary Orchestrator returned NO test report. "
                f"Files on disk: {files}. The build is UNVERIFIED -- say so "
                "rather than reporting it as working.")

    if "ALL TESTS PASSED" in report:
        return ("[Orchestrator] Secondary Orchestrator completed. Files: "
                f"{files}. Test suite: ALL TESTS PASSED ({rounds}).")

    failures = _failed_lines(report)
    detail   = "\n".join("  " + ln for ln in failures) if failures else \
               "  (report present but no FAILED line parsed)"
    return ("[Orchestrator] Secondary Orchestrator ENDED WITH FAILING TESTS "
            f"after {rounds}. Files: {files}. Do NOT report this build as "
            f"working. Unresolved:\n{detail}")


import json as _tc_json


def _test_cases_path(session_id: str):
    """Where a session's test suite lives between runs: beside its page."""
    return _PREVIEW_ROOT / f"tests_{session_id}.json"


def _load_test_cases_file(session_id: str) -> list:
    """The suite the last run left for this session, or [] if there is none.

    A user-requested modify has no Test Gen step (regenerating the suite
    would cost a full model call for a one-word change), so without this the
    Secondary Orchestrator ran Playwright on an empty list and every modify
    ended "(no report produced)" / unverified (13b71045, 2026-09-15). The
    primary's own state cannot hold it: _reset_before wipes working_memory
    at the start of every turn. A file keyed to session_id follows the page
    itself, so it also survives a deleted-and-reopened thread.
    Unreadable or malformed -> [] and the run proceeds unverified, as before.
    """
    try:
        data = _tc_json.loads(_test_cases_path(session_id).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    return [tc for tc in data if isinstance(tc, dict)] if isinstance(data, list) else []


def _save_test_cases_file(session_id: str, test_cases: list) -> int:
    """Write the suite for the next run. Returns the number written (0 = skipped)."""
    if not test_cases:
        return 0
    try:
        _test_cases_path(session_id).write_text(
            _tc_json.dumps(test_cases, ensure_ascii=False, indent=1), encoding="utf-8")
    except OSError:
        return 0
    return len(test_cases)


@tool
def call_secondary_orchestrator(
    runtime:          ToolRuntime[OrchestratorState],
    query:            str,
    intent:           str = "generate",
    target_component: str = "",
    target_instance:  int = 1,
) -> Command:
    """
    Invoke the Secondary Orchestrator to generate or modify e-commerce pages.
    Generation: intent='generate' (default) — full pipeline (HTML→CSS+JS+TestGen→TestExec).
    Modification: intent='modify' + target_component, target_instance
                  — skips context and planning, routes directly to dev agents.
    """
    writer = get_stream_writer()
    writer({"type": "indent", "delta": 1})
    state  = runtime.state
    # Fail LOUDLY on a missing or unsafe id rather than letting the sub-graph
    # run with "": _read_preview_source would return "" for every modify and
    # the run would report success having edited nothing. Validated here, at
    # the one boundary the id crosses into the multi-agent system.
    session_id = _safe_session_id(state.get("session_id", ""))
    if not session_id:
        writer({"type": "indent", "delta": -1})
        return Command(update={"messages": [ToolMessage(
            content=("[Orchestrator] REFUSED: no usable session_id in state. "
                     "It is issued by the application layer and must reach the "
                     "graph in the input payload (letters, digits, '-' and '_', "
                     "1-64 chars). Report this and END -- do not retry."),
            tool_call_id=runtime.tool_call_id)]})
    wm     = state.get("working_memory") or WorkingMemory()
    if isinstance(wm, dict):
        wm = WorkingMemory(**wm)

    # Single-document contract. Every artefact this system writes is keyed to
    # session_id alone -- preview_<sid>.{html,css,js} -- so there is nowhere to
    # put a second page. store_html_code would still reject an N-page run, but
    # only after the HTML agent had generated it, and with a per-component
    # coverage message that names the symptom instead of the cause. Refusing
    # here names the cause. Multi-section navigation is the supported shape:
    # one document, in-page anchors.
    _pages = _layout_page_count(wm.layout_specification)
    if _pages > 1:
        writer({"type": "indent", "delta": -1})
        return Command(update={"messages": [ToolMessage(
            content=(f"[Orchestrator] REFUSED: layout_specification asks for "
                     f"{_pages} pages. This system builds ONE document per "
                     "session -- the artefact layer keys every file to "
                     "session_id alone. Re-plan as a single page whose regions "
                     "are sections reached by in-page anchor links, then call "
                     "again. Do not retry unchanged."),
            tool_call_id=runtime.tool_call_id)]})

    # Generation must run on real specifications. If the model skipped
    # context engineering and planning and called this tool directly,
    # working_memory still holds only the empty specs reset_before wrote,
    # and a build from them invents a page from the query alone -- which is
    # exactly what a one-noun brief was supposed to prevent. Refuse here and
    # name the two steps that were skipped. Modify is exempt: it reads the
    # page from disk, not from the specs, so empty specs there are expected.
    if intent != "modify" and not wm.layout_specification:
        writer({"type": "indent", "delta": -1})
        return Command(update={"messages": [ToolMessage(
            content=("[Orchestrator] REFUSED: no specifications in working "
                     "memory, so there is nothing to build from. Generation "
                     "runs call_context_engineering_agent, then "
                     "call_system_design_planning_agent, then this tool -- "
                     "each consumes what the one before produced. Run those "
                     "two first, then call again. Do not retry unchanged."),
            tool_call_id=runtime.tool_call_id)]})

    try:
        # The SO model reads messages, not state. A click-to-select target that
        # lives only in state is invisible to it, and on 13b71045 it dispatched
        # the HTML agent with target_component='' and synced tests for
        # 'header'/'footer' it had guessed. Name the target in the request.
        # user_query stays the bare query: it is the work-order text.
        _seed_tests = _load_test_cases_file(session_id) if intent == "modify" else []
        _so_request = query
        if intent == "modify" and target_component:
            _so_request = (f"{query}\n\n[Click-to-select target: "
                           f"target_component={target_component}, "
                           f"target_instance={target_instance}. Pass both to the "
                           f"developer agent, and use the same target_component "
                           f"as `component` for sync_*_test_cases.]")
        payload = {
            "messages":                  [{"role": "user", "content": _so_request}],
            "session_id":                session_id,
            "user_query":                query,
            "intent":                    intent,
            "target_component":          target_component,
            "target_instance":           target_instance,
            "layout_specification":      wm.layout_specification,
            "components_specification":  wm.components_specification,
            # map interactions_specification (WorkingMemory) -> interaction_specification (secondary orch State)
            "interaction_specification": wm.interactions_specification,
            "decoration_specification":  wm.decoration_specification,
            # Modify reuses the suite the generation run left on disk (see
            # _load_test_cases_file). Generation starts empty: Test Gen fills it.
            "test_cases":                _seed_tests,
            "modification_history":      [],
            "test_report":               "",
            "modification_attempts":     0,
        }

        # Drives HTML -> CSS/JS/TestGen -> TestExec plus up to
        # up to _MODIFICATION_ATTEMPT_CAP correction round(s), so it needs a larger budget
        # than the agents beneath it. Explicit for the same reason as those:
        # LangGraph's default 25 was inherited, not chosen.
        sub_config = {
            # The real session id, not a second unrelated value under the same
            # name -- this used to be f"sec_{uuid4}", which read like the
            # preview id and was not.
            "configurable":    {"session_id": session_id},
            "callbacks":       [],
            "recursion_limit": 100,
        }

        # test_cases starts from what was seeded, because the sub-graph's
        # writes are DELTAS: Test Gen stores in batches and the sync tools
        # return only the cases they changed. The channel's reducer merges by
        # id, so the same reducer is applied here, or the file would end up
        # holding just the last batch.
        captured: dict = {"test_cases": list(_seed_tests)}

        def _merge(update: dict) -> None:
            for k, v in update.items():
                if k == "messages":
                    continue
                if k == "test_cases":
                    captured[k] = _merge_test_cases(captured.get(k, []), v)
                else:
                    captured[k] = v

        for chunk in secondary_orch.stream(
            payload,
            stream_mode=["updates", "custom"],
            version="v2",
            config=sub_config,
        ):
            if isinstance(chunk, tuple) and len(chunk) == 2:
                chunk_type, data = chunk
            else:
                chunk_type = chunk.get("type")
                data       = chunk.get("data")
            if chunk_type == "custom":
                writer(data if isinstance(data, (str, dict)) else str(data))
            elif chunk_type == "updates" and isinstance(data, dict):
                for _, up in data.items():
                    if isinstance(up, dict):
                        _merge(up)

        _n_saved = _save_test_cases_file(session_id, captured.get("test_cases") or [])
        _outcome = _secondary_outcome(session_id, captured)
        if _n_saved:
            _outcome += (f"\n[Orchestrator] {_n_saved} test case(s) kept in "
                         f"tests_{session_id}.json for later modifies.")
        return Command(update={
            "messages": [ToolMessage(
                content=_outcome,
                tool_call_id=runtime.tool_call_id,
            )]
        })
    finally:
        writer({"type": "indent", "delta": -1})


# ==========================================================================
# Tools
# ==========================================================================
# ═══════════════════════════════════════════════════════════════════════════
# ask_user - the one clarifying question, as data instead of as a sentence
#
# The gate in the prompt already makes the orchestrator ask once when a request
# gives it too little to build from. That question currently arrives as prose,
# which means the application layer cannot tell a question from an ordinary
# reply, and cannot tell which answers are being offered. Both facts exist only
# inside an English sentence the model rewords on every run.
#
# This tool asks nobody. It records the question as structured data and the turn
# ends. The panel renders a control from it, the user picks, and their choice
# comes back as an ordinary message. Nothing below this orchestrator learns that
# a control was involved.
#
# WHY THE MODEL SUPPLIES THE OPTIONS
# ----------------------------------
# Scanning the reply for known values was the alternative, and it was rejected:
# the gate also establishes the core user flow, the sections wanted and any
# specific features, and the prompt states outright that those are free text and
# not a fixed list. A scan can never offer a control for them. Letting the model
# write the options covers both, because for the four closed choices it copies
# them out of the choice list already in its prompt.
#
# WHAT PYTHON GUARANTEES
# ----------------------
# 1. An option that names one of the four closed fields must carry a value the
#    schema accepts. Otherwise the model can offer style="super_fancy", which
#    the panel would render happily and the schema would reject later, with the
#    user having already chosen it.
# 2. One call per thread. Asking once is currently a prompt instruction alone,
#    and handing the model a control to draw makes a second round more tempting
#    rather than less, so the cap lives in code here, the same way
#    call_test_exec_pipeline holds the correction cap rather than trusting the
#    prompt to hold it.
#
# A refusal writes no state, so the model may fix the call and try again. Only a
# question that is actually renderable spends the gate.
# ═══════════════════════════════════════════════════════════════════════════
from typing import Any, Dict, List

from langchain.messages import ToolMessage
from langchain.tools import ToolRuntime, tool
from langgraph.types import Command

# Generated, never written by hand, for the same reason the prompt's choice list
# is: adding a value to a Literal must reach this guard without anyone editing
# it. An option naming none of these is free text and is not value-checked.
_CLOSED_CHOICE_FIELDS = tuple(user_choice_options())

# One option is not a choice, and zero is the open question this tool replaces.
_ASK_MIN_OPTIONS = 2


def _legal_choice_values(field: str) -> set:
    """The values the schema accepts for one closed field."""
    return {v["value"] for v in user_choice_options()[field]["values"]}


@tool
def ask_user(question: str, options: List[Dict[str, Any]],
             runtime: ToolRuntime[OrchestratorState]) -> Command:
    """Ask the user ONE clarifying question and stop, when the request is too thin to build from.

    question: one short question in plain words.
    options:  the concrete answers to offer, at least two. Each is an object:
                value  the exact word to send back
                label  what the user reads
                help   one line saying what that answer means
                field  optional. One of commerce_type, style, type or
                       responsiveness when the option sets that field, and the
                       value must then be one the schema accepts. Leave it out
                       for a free-text subject such as which sections or which
                       features, where there is no fixed list.

    The user is always given a free-text box as well, so the options do not have
    to cover every answer. Calling this ends your turn: do not call another tool
    afterwards, and do not repeat the question as prose in the same message.
    """
    raw = runtime.state or {}
    state = raw if isinstance(raw, dict) else {}

    def refuse(reason: str) -> Command:
        """Nothing ran and nothing was spent, so the model may call again."""
        return Command(update={"messages": [ToolMessage(
            content="REFUSED: " + reason, tool_call_id=runtime.tool_call_id)]})

    # Guard 2 first: if the gate is already spent, the shape of the call does
    # not matter and saying so is the more useful message.
    if state.get("clarifier_used"):
        return refuse(
            "you have already asked once on this thread, and the gate allows "
            "one question only. Proceed with the stated defaults and say in "
            "your first line what you assumed, so the user can correct it.")

    q = (question or "").strip()
    if not q:
        return refuse("the question was empty. Ask something, or do not call "
                      "this tool at all.")

    given = len(options) if isinstance(options, list) else 0
    if given < _ASK_MIN_OPTIONS:
        return refuse(
            f"{given} option(s) were given and at least {_ASK_MIN_OPTIONS} are "
            "needed. One option is not a choice, and none of them is the open "
            "question this tool exists to replace.")

    cleaned, problems = [], []
    for n, opt in enumerate(options, 1):
        if not isinstance(opt, dict):
            problems.append(f"option {n} is not an object.")
            continue
        value = str(opt.get("value", "") or "").strip()
        if not value:
            problems.append(f"option {n} has no value, so there is nothing to "
                            "send back when the user picks it.")
            continue
        field = str(opt.get("field", "") or "").strip()
        if field:
            if field not in _CLOSED_CHOICE_FIELDS:
                problems.append(
                    f"option {n} names field {field!r}, which is not a field "
                    "the user chooses. Use one of "
                    + ", ".join(_CLOSED_CHOICE_FIELDS)
                    + ", or leave field out to ask something free-text.")
                continue
            legal = _legal_choice_values(field)
            if value not in legal:
                problems.append(
                    f"option {n} offers {value!r} for {field}, which the schema "
                    "does not accept, so the user could choose something that "
                    "cannot be built. Accepted: " + ", ".join(sorted(legal)) + ".")
                continue
        cleaned.append({
            "field": field,
            "value": value,
            "label": str(opt.get("label") or value.replace("_", " ").capitalize()),
            "help":  str(opt.get("help") or ""),
        })

    if problems:
        return refuse("the options cannot be rendered as they stand. "
                      + " ".join(problems)
                      + " Nothing was asked. Fix them and call again.")

    return Command(update={
        "pending_question": {
            "question": q,
            "options": cleaned,
            # Never a closed set. The gate exists to learn what the user wants,
            # so an answer that is not on the list must still be givable.
            "allow_free_text": True,
        },
        "clarifier_used": True,
        "messages": [ToolMessage(
            content=(f"\t[Orchestrator] Asked the user one question with "
                     f"{len(cleaned)} options. Waiting for their answer. Say "
                     f"nothing further this turn."),
            tool_call_id=runtime.tool_call_id)],
    })


# ==========================================================================
# Tools
# ==========================================================================
# ═══════════════════════════════════════════════════════════════════════════
# read_page_source - the orchestrator reads the page it built, to answer grounded
#
# The Primary Orchestrator is the only part that talks to the user, and once a
# page exists the user asks about it: "what does the buy button look like", "is
# there a search bar". The four specifications are the wrong source for that
# answer. A modify run never writes them back, so they describe the page as it
# was PLANNED, not as it stands on disk. This tool reads the actual file, so a
# grounded answer rests on what shipped.
#
# It writes only messages -- the answer is the model's job -- so it declares no
# new channel. It never builds, plans or modifies. On a modify turn the tool
# list is narrowed to the build route, so this is a generate/answer-turn tool by
# design. Reads go through _read_preview_source, which sanitises the id and never
# escapes the preview directory.
# ═══════════════════════════════════════════════════════════════════════════
@tool
def read_page_source(
    runtime: ToolRuntime[OrchestratorState],
    part: str = "html",
) -> Command:
    """Read the current session's generated page, to answer a question about it.

    part: which file to read -- "html" for structure and text, "css" for styling
          and colours, "js" for behaviour. Read the one the question needs; call
          again with a different part if you need more than one.

    Use this before answering any question about the page that was built. The
    specifications describe what was planned, not what is on disk after a modify,
    so read the file rather than answering from memory. Returns the file's
    contents, or says the page has not been built yet.
    """
    state = runtime.state if isinstance(runtime.state, dict) else {}
    session_id = _safe_session_id(state.get("session_id", ""))
    if not session_id:
        return Command(update={"messages": [ToolMessage(
            content=("REFUSED: no usable session_id in state, so there is no "
                     "page to read. It is issued by the application layer."),
            tool_call_id=runtime.tool_call_id)]})

    ext = str(part or "").strip().lower()
    if ext not in ("html", "css", "js"):
        return Command(update={"messages": [ToolMessage(
            content=f"REFUSED: part must be html, css or js, not {part!r}.",
            tool_call_id=runtime.tool_call_id)]})

    source = _read_preview_source(session_id, ext)
    if not source:
        return Command(update={"messages": [ToolMessage(
            content=(f"No preview_{session_id}.{ext} on disk. The page has not "
                     f"been built yet, or has no {ext} file. Tell the user "
                     "rather than inventing content."),
            tool_call_id=runtime.tool_call_id)]})

    return Command(update={"messages": [ToolMessage(
        content=f"preview_{session_id}.{ext} ({len(source)} chars):\n{source}",
        tool_call_id=runtime.tool_call_id)]})


print("read_page_source ready -- the orchestrator can read the built page to answer grounded")


# ==========================================================================
# Middleware
# ==========================================================================
# ═══════════════════════════════════════════════════════════════════════════
# reset_before - clears last turn's answer before this turn starts
#
# The checkpointer keeps the whole state between turns, so anything not cleared
# here is still there on the next request. A schema, a set of specifications or
# an intent left over from the previous turn would be read as though it
# described the new one, which is why every field a tool writes is reset.
#
# input_query is the exception. It is lifted out of the newest human message
# so update_input has something to commit.
# ═══════════════════════════════════════════════════════════════════════════
from langchain.agents.middleware import before_agent


def _reset_before(state, runtime):
    input_query = ""
    if isinstance(state, dict) and isinstance(state.get("input_query"), str):
        input_query = state.get("input_query", "") or ""

    if not input_query and isinstance(state, dict):
        msgs = state.get("messages") or []
        try:
            for m in reversed(list(msgs)):
                if hasattr(m, "type") and getattr(m, "type") == "human" and hasattr(m, "content"):
                    input_query = str(getattr(m, "content") or "")
                    break
                if isinstance(m, dict) and m.get("role") == "user" and isinstance(m.get("content"), str):
                    input_query = m.get("content") or ""
                    break
        except Exception:
            pass

    return {
        "input_query":      input_query,
        "design_schema":    {},
        "working_memory":   {
            "design_schema":              {},
            "layout_specification":       {},
            "components_specification":   {},
            "interactions_specification": {},
            "decoration_specification":   {},
        },
        # A stale intent="modify" would send the next request straight to the
        # sub-workflow with no specifications behind it.
        "intent":           "generate",
        "target_component": "",
        "target_instance":  1,
        # Last turn's question, cleared so the panel does not redraw a control
        # the user has already answered. clarifier_used is cleared too, so the
        # one-question gate is per turn, not per session: a new build request
        # later in the same conversation may ask its own question. Within a
        # single turn ask_user still sets the flag and refuses a second call.
        "pending_question": {},
        "clarifier_used":   False,
    }


reset_before = before_agent(_reset_before)


# ==========================================================================
# Middleware
# ==========================================================================
# ═══════════════════════════════════════════════════════════════════════════
# Progress messages from the Primary Orchestrator
#
# A generation run takes minutes, and most of that time is spent inside a
# sub-agent. Without these lines the Streamlit pane shows nothing at all
# between the request and the finished page.
# ═══════════════════════════════════════════════════════════════════════════
from langchain.agents.middleware import before_agent, wrap_tool_call
from langgraph.config import get_stream_writer


@before_agent
def orchestrator_progress(state, runtime):
    writer = get_stream_writer()
    writer("[Orchestrator] Processing request...")
    return None


@wrap_tool_call
def orchestrator_tool_progress(request, handler):
    writer = get_stream_writer()
    tool_name = ""
    try:
        tool_name = (request.tool_call or {}).get("name") or ""
    except Exception:
        tool_name = ""

    if tool_name == "update_input":
        writer("[Orchestrator] Recording request...")
    elif tool_name == "call_context_engineering_agent":
        writer("[Orchestrator] Invoking Context Agent...")
    elif tool_name == "call_system_design_planning_agent":
        writer("[Orchestrator] Invoking System Design & Planning Chain...")
    elif tool_name == "call_secondary_orchestrator":
        # The longest stage by far, and the one that used to announce nothing.
        writer("[Orchestrator] Invoking Secondary Orchestrator...")
    return handler(request)


# ==========================================================================
# Create Agent
# ==========================================================================
# ═══════════════════════════════════════════════════════════════════════════
# The Primary Orchestrator's voice
#
# It is the only part of this system a user ever hears. The prompt described its
# job in full and said nothing about how it should sound, so it sounded like a
# specification: accurate, and cold.
#
# Three rules hold across all three voices.
#
#   1. Voice changes WORDING ONLY. None of these blocks may change which tool
#      runs, what is built, or what is reported. The test cell below asserts the
#      behavioural sections are byte-identical whichever voice is selected.
#   2. The voice DROPS when a build fails. A cheerful report of a broken page is
#      spin, and VERIFICATION exists to stop exactly that. Warmth belongs to
#      conversation and to success.
#   3. The user picks it. It arrives as a state field, the same way session_id
#      does, so nothing in the graph invents one.
# ═══════════════════════════════════════════════════════════════════════════

_TONE_SHARED_FLOOR = """
These hold whichever voice is selected.
- Report the outcome accurately. The voice never changes WHAT you say, only how.
- When a build ended with failing tests, or produced nothing, drop the warmth
  entirely. Plain, short, factual sentences. No emoji, no exclamation marks, no
  encouraging framing. The user needs to know it is broken, not to feel good.
- Never let a greeting or a flourish push the actual answer below the fold. Say
  the thing, then decorate it.
"""

TONE_PROMPTS = {
    "friendly": """
VOICE: FRIENDLY
Warm, lively, and genuinely pleased to help. Talk like a capable person who
enjoys their work, not like a document.
- Open a conversational reply with a greeting when the user greets you or asks a
  question. "Hi!" or "Good question!" is right. Do not greet in the middle of a
  build report.
- Use contractions. Short sentences. A little energy is welcome.
- Emoji are welcome where they add something: a thinking face while you weigh a
  choice, a party popper when a build passes, a shop for what you make. Put them
  where they help the eye, including headings and list items.
- When you ask the user a question, make it feel like a choice you are offering,
  not a form to complete.
- Never emoji, and never exclamation marks, in a failure report. See the floor.
""" + _TONE_SHARED_FLOOR,

    "concise": """
VOICE: CONCISE
Short and direct. The user wants the answer, not the conversation.
- No greeting, no sign-off, no restating the question.
- Lead with the answer in the first sentence. Detail after, only if it changes
  what the user would do next.
- No emoji. Plain punctuation.
- When you must ask something, ask it as a single line with the options listed.
- Aim for a reply that could be read in one breath, unless the content genuinely
  needs more.
""" + _TONE_SHARED_FLOOR,

    "professional": """
VOICE: PROFESSIONAL
Neutral, measured, and precise. This is the voice for a demonstration, a viva, or
a screenshot in a written report.
- Complete sentences. No contractions where the full form reads naturally.
- No emoji, no exclamation marks, no colloquialism.
- Name components and stages by their proper names.
- State outcomes without either enthusiasm or apology.
""" + _TONE_SHARED_FLOOR,
}

# What the interface offers. Kept beside the prompts so a new voice cannot be
# added to one and forgotten in the other, which is the same rule the choice
# list follows.
TONE_OPTIONS = [
    {"value": "friendly",
     "label": "Friendly",
     "help": "Warm and lively, with emoji. Good for a live demo."},
    {"value": "concise",
     "label": "Concise",
     "help": "Short and direct. No greetings, no emoji."},
    {"value": "professional",
     "label": "Professional",
     "help": "Neutral and formal. Good for a viva or a report screenshot."},
]
_TONE_DEFAULT = "friendly"


def tone_block(name: str) -> str:
    """The voice block for a selected tone, falling back to the default.

    An unknown value returns the default rather than raising. The tone reaches
    the graph from the interface, and a stale value in a saved session must not
    be able to stop a run that is otherwise fine.
    """
    return TONE_PROMPTS.get(str(name or "").strip().lower(),
                            TONE_PROMPTS[_TONE_DEFAULT])


print("Orchestrator voices ready:", ", ".join(TONE_PROMPTS))


# ==========================================================================
# Create Agent
# ==========================================================================
# ═══════════════════════════════════════════════════════════════════════════
# force_modify_routing - a modify request cannot reach the planning agents
#
# When the user clicks a component in the preview panel and types a change, the
# panel sends a message carrying [intent=modify | target_component=... |
# target_instance=...]. Exactly one thing should happen next: the Secondary
# Orchestrator runs with that target. The specifications and the test suite were
# built once, during generation, and re-deriving them would discard the design
# the page on disk was actually built from.
#
# Written as a prompt rule, that is an instruction the model follows most of the
# time, and the only way to find out is to pay for a run. wrap_model_call
# rewrites the request before the model sees it, so on a modify turn the planning
# tools are simply not in the list. The wrong route stops being unlikely and
# becomes impossible, which is the same trade the lint cap and the correction cap
# already make elsewhere in this system.
#
# WHY THE MARKER AND NOT state["intent"]
# --------------------------------------
# reset_before sets intent to "generate" at the top of every turn, so a stale
# modify from the previous request cannot leak into this one. state["intent"]
# therefore only becomes "modify" AFTER the model has read the marker and acted,
# which is after the decision being constrained here. Reading the marker off the
# newest human message fires on the turn that matters. PO-07 also seeds the
# state directly, and both routes are covered.
#
# WHAT IS LEFT ALONE, ON PURPOSE
# ------------------------------
# tool_choice is untouched, so the model may still answer with no tool call at
# all. It has to be able to: a structural change (adding or removing a
# component) must be declined in words, and forcing a tool call would take that
# ending away. update_input survives the narrowing too, because it is how the
# request is committed and removing it changes the shape of a working flow for
# no gain. Only the two planning tools and ask_user are withheld.
# ═══════════════════════════════════════════════════════════════════════════
from langchain.agents.middleware import wrap_model_call

# The marker's format and its parse live in webforge.contract (ticket 12), the
# one definition the UI that writes it and this middleware that reads it share.
from webforge.contract import modify_marker_fields

# What a modify turn may still reach for. call_secondary_orchestrator is the
# route; update_input is the bookkeeping that precedes it.
_MODIFY_TOOLS = ("update_input", "call_secondary_orchestrator")


def _fmr_tool_name(t) -> str:
    """The name of a tool, whether it arrives as an object or as a dict."""
    if isinstance(t, dict):
        return str(t.get("name") or (t.get("function") or {}).get("name") or "")
    return str(getattr(t, "name", "") or "")


def _fmr_newest_human_text(messages) -> str:
    """The newest human message's text, or an empty string."""
    for m in reversed(list(messages or [])):
        try:
            if getattr(m, "type", None) == "human":
                return str(getattr(m, "content", "") or "")
            if isinstance(m, dict) and m.get("role") == "user":
                return str(m.get("content") or "")
        except Exception:
            continue
    return ""


def _force_modify_routing(request, handler):
    """Narrow the tool list when this turn is a modify request.

    Defined as a plain function and wrapped below, so the unit tests can call
    the logic directly instead of standing up an agent to reach it.
    """
    state = request.state if isinstance(request.state, dict) else {}

    fields = modify_marker_fields(_fmr_newest_human_text(state.get("messages")))
    target = fields.get("target_component") or (
        state.get("target_component") if state.get("intent") == "modify" else "")

    # No marker, or a marker with nothing to aim at. A malformed marker is left
    # alone deliberately: the model should answer the user about it, and it
    # cannot do that from a tool list built for a modify it cannot perform.
    if not target:
        return handler(request)

    tools = list(request.tools or [])
    kept = [t for t in tools if _fmr_tool_name(t) in _MODIFY_TOOLS]

    # Never hand the model a list without the one route it is being pushed
    # towards. If the agent was built without it, narrowing would trap the model
    # with no way to do the thing it is now the only allowed thing to do.
    if not any(_fmr_tool_name(t) == "call_secondary_orchestrator" for t in kept):
        return handler(request)

    return handler(request.override(tools=kept))


force_modify_routing = wrap_model_call(_force_modify_routing)


# ==========================================================================
# Create Agent
# ==========================================================================
# ═══════════════════════════════════════════════════════════════════════════
# enforce_modify_target - the marker decides, not the model's copy of it
#
# The panel knows exactly which component was clicked and which instance of it.
# It writes both into the marker. Everything after that is the model reading two
# strings and typing them out again into a tool call, and a paraphrase there is
# the worst failure this system has: the Secondary Orchestrator edits a
# different element, every downstream check passes against THAT element, and the
# run reports success while the thing the user clicked is untouched.
#
# So the marker is treated as the truth and the tool call is corrected to match
# it before the tool runs. The model's copy is only ever a retyping of a value
# that was already known, so overwriting it discards nothing.
#
# THIS DOES NOT FORCE THE CALL
# ---------------------------
# The model may still answer with no tool call at all, and it must be able to.
# A structural change (adding or removing a component) has to be declined in
# words, because the specifications and the tests are not rebuilt in this mode.
# That is what PO-04 covers. The guarantee here is deliberately conditional: IF
# the Secondary Orchestrator is called, it receives the marker's values. WHETHER
# it is called stays a judgement.
#
# THE COST, RECORDED HONESTLY
# ---------------------------
# The marker becomes a single point of truth. Before this, a model could quietly
# repair a malformed marker; now a panel bug travels straight through. That is
# the right trade, because a silent repair is indistinguishable from a silent
# corruption from the outside, but it does mean the panel's marker format is now
# load-bearing. The drift guard in the E2E harness exists for that reason.
# ═══════════════════════════════════════════════════════════════════════════
from langchain.agents.middleware import wrap_tool_call
from langgraph.config import get_stream_writer


def _emt_marker_truth(state: dict) -> dict:
    """What the panel said, from the marker, or from a seeded state.

    PO-07 seeds the state instead of sending a marker, and the real panel sends
    a marker with nothing seeded. Both have to resolve to the same answer.
    """
    fields = modify_marker_fields(_fmr_newest_human_text(state.get("messages")))
    target = fields.get("target_component") or ""
    instance = fields.get("target_instance")

    if not target and state.get("intent") == "modify":
        target = str(state.get("target_component") or "")
        instance = state.get("target_instance")

    if not target:
        return {}

    # The marker is text, so the instance arrives as a string. A missing or
    # unreadable one means the first instance, which is what the panel sends
    # when a component appears only once.
    try:
        instance_n = int(str(instance).strip())
    except (TypeError, ValueError, AttributeError):
        instance_n = 1

    return {"intent": "modify", "target_component": target,
            "target_instance": instance_n}


def _enforce_modify_target(request, handler):
    """Correct a modify dispatch to match the marker.

    A plain function, wrapped below, so the tests can call the logic without
    standing up an agent to reach it.
    """
    call = request.tool_call or {}
    if call.get("name") != "call_secondary_orchestrator":
        return handler(request)

    state = request.state if isinstance(request.state, dict) else {}
    truth = _emt_marker_truth(state)
    if not truth:
        # A generation run. There is no marker to be faithful to, and intent
        # must stay whatever the model asked for.
        return handler(request)

    args = dict(call.get("args") or {})
    wrong = {k: args.get(k) for k, v in truth.items() if args.get(k) != v}
    if not wrong:
        return handler(request)

    args.update(truth)
    try:
        get_stream_writer()(
            "\t[Orchestrator] Modify target corrected from the marker. "
            f"The model sent {wrong}, the panel said "
            f"{ {k: truth[k] for k in wrong} }.")
    except Exception:
        # Outside a runnable context there is no stream. The correction still
        # happens; only the narration is lost.
        pass

    return handler(request.override(tool_call={**call, "args": args}))


enforce_modify_target = wrap_tool_call(_enforce_modify_target)


# ==========================================================================
# System prompt
# ==========================================================================
# ════════════════════════════════════════════════════════════════════════════
# The Primary Orchestrator
#
# It owns the whole turn: it decides whether the request is in scope, gathers
# the design schema and the four specifications, hands the build to the
# Secondary Orchestrator, and reports what came back. It is also the ONLY part
# of the system that talks to the user, which is why the choice list and the
# fixed limits are in its prompt and nowhere else.
#
# The prompt is organised around the five things a prompt has to carry:
# OUTCOME (what done looks like), VERIFICATION (how it knows), CONSTRAINTS
# (the forbidden edges), ITERATION POLICY (what to record per step) and ERROR
# HANDLING (when to stop rather than keep trying). gpt-5.4 plans internally, so
# a numbered script fights the model. Order is stated only where it is a data
# dependency rather than a preference.
#
# The choice list and the fixed list are GENERATED from the schema by
# choices_for_prompt() and fixed_for_prompt(). Writing them out by hand would
# put a second copy of the vocabulary in the system, and the copy would be
# wrong the first time anyone added a value to a Literal.
#
# VERIFICATION is the section that earns its length. The sub-workflow can finish
# four different ways, and only its tool message says which. An orchestrator
# that reads "it returned" as "it worked" reports a broken page as a finished
# one, which is exactly what happened on the first live run.
# ════════════════════════════════════════════════════════════════════════════
import pathlib as _pl_ckpt
import sqlite3 as _sqlite_ckpt

from langchain.agents import create_agent
from langchain.agents.middleware import dynamic_prompt
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.sqlite import SqliteSaver

_orchestrator_prompt = """
ROLE
You are the Primary Orchestrator of a system that generates and modifies a
single-page B2C e-commerce storefront in plain HTML, CSS and JavaScript. You are
the only part that speaks to the user. Do not write code, schemas or
specifications yourself. Choose which specialist runs and report truthfully what
came back.

OUTCOME
The turn ends when exactly one of these is true.
1. call_secondary_orchestrator returned and you reported its real outcome.
2. You declined a BUILD request and gave an actionable reason.
3. You asked for specific missing information required to proceed.
4. You simply answered. For questions, explanations, greetings or thanks, reply
   in plain words, call no tool, and build nothing. Not every message requests a
   page.

VERIFICATION
Your closing message must match the tool output. Re-read the
call_secondary_orchestrator message before replying; it is your only evidence of
what reached disk and what testing did.
- ALL TESTS PASSED: summarise what was built.
- ENDED WITH FAILING TESTS: say the page was built but did not pass verification,
  and never call it working. Describe what is wrong in plain user terms, grouped
  into a few areas (e.g. "the cart panel does not open and close"), worst-first.
  No test ids, CSS property names, or expected-vs-got values. A few short bullets
  at most.
- UNVERIFIED: files exist but no test report returned. Say it is unverified.
- NO ARTEFACTS: nothing was written. Report a FAILED build and do not describe a
  page you never received.
Never name a feature absent from that output. Never promote a partial result into
a success.

TOOLS
- update_input                       records the request into state
- call_context_engineering_agent     request -> design schema
- call_system_design_planning_agent  design schema -> four specifications
- call_secondary_orchestrator(query, intent, target_component,
  target_instance)                   specifications -> a tested page
- read_page_source(part)             read the built page to answer questions
                                     about its html/css/js

Generation requires the first four in order because each consumes the prior
result. Modification uses only call_secondary_orchestrator; specifications are
rebuilt only during generation.

ENOUGH TO BUILD FROM
Judge this before any tool call. A buildable brief names the product or category
AND at least TWO of: buyer or occasion; an action beyond browsing; look, mood or
brand feeling; a named feature, section or component. A one-noun brief such as
"an umbrella shop" is insufficient because the missing design would be invented.
If fewer than two are present, ask ONE short question with ask_user, the only way
to ask. It carries concrete options as data rendered as buttons, so use options
from the lists below, state what you will assume, then stop and wait. Prose is
not a choice.
Ask once. If the reply is genuinely unusable, meaning empty, gibberish or
self-contradictory, you may ask ONE more time. If it is merely thin, or the user
says "you decide", PROCEED with the defaults below: state your assumptions in
your first line, then run the full generation chain through context engineering,
planning and the build. Proceeding never means calling call_secondary_orchestrator directly,
because no specifications exist yet. Do not exceed two clarifying rounds for one
build request, and never refuse a request merely for being brief. The gate is per
request: a new build request later in the conversation starts fresh and may ask
its own one question.

WHAT THE USER MAY CHOOSE
Ask only about unsettled items from this list. Decide the rest using the stated
defaults. Never ask about anything the user explicitly delegated to you.

{{CHOICES}}

A page type is the ONE page's primary identity, not another deliverable. The run
builds one document; areas associated with other types, such as listings, cart or
checkout, appear as sections reached by in-page anchor links, never separate
pages. A type's checklist is a floor, so other sections may still appear.
Also establish the core user flow or desired sections and any required features
or components. These are free text, not fixed choices.

VISUAL THEME
The look must use one predefined theme by name; never invent a new theme.
Available themes are:
{{THEMES}}
If the user names a mood or theme, map it to the closest one and confirm the
choice in your opening line. If they request an unavailable theme, say so and
offer the nearest one from this list instead of promising it. If unstated, use
the system default.

WHAT IS FIXED, AND WHY
Never offer these as choices or accept a request that depends on changing one.
If asked, give its reason in one sentence and offer the nearest supported
alternative.
Each entry below is written as "what: value. why". Give the why, not merely a
restatement of the limit, so the user understands the system constraint.

{{FIXED}}

CONSTRAINTS
- You BUILD e-commerce storefront user interfaces and nothing else. A request to
  build something else is declined in one sentence without calling a tool.
- This limit concerns what you BUILD, never about what you will discuss.
  Questions, greetings and explanations are answered normally in plain words
  using the supported choices and fixed limits. Do not turn a conversation into a refusal,
  and do not start a build nobody asked for.
- For questions about the current page's actual content, structure or styling,
  use read_page_source and answer from its result. Specifications describe what
  was planned, not what is on disk after a modify, so do not answer those
  questions from specifications.
- Front end only. No server, database or API code.
- ONE tool call per message. Tools write shared state fields that do not merge;
  multiple calls in one message collide.
- A modify request carries an [intent=modify | ...] marker. Copy
  target_component and target_instance exactly as written.
- Modification may change only something INSIDE an existing component: styling,
  text, content or a property of behaviour it already has. It cannot add or
  remove components or add, remove or rewire interactions. Those are structural;
  specifications and tests are not rebuilt in modify mode. Decline such edits in
  one sentence, explain why, and offer regeneration with the change included.
- On modify turns, planning tools are intentionally unavailable because existing
  specifications must be preserved. A short tool list is expected. For a
  structural request, decline it rather than searching for a missing tool.
- target_component and target_instance are also enforced in code. Copy them
  accurately; a mismatch means the request was misread.
- One page exists per conversation, and a second generation overwrites it.
  Session-id filenames are reused. If a page was already built and the user asks
  to generate another, warn that it will overwrite the current one and build only after they confirm.
  This applies to new generation, not a modify, which edits the current page, and
  not a question about the page, which you simply answer.
- A request to build something else is declined.

ITERATION POLICY
Before each tool call, state in one sentence which stage you are entering and
what you expect back. After it returns, state in one sentence what you actually
got. Keep both lines brief.

ERROR HANDLING
- A tool message beginning with REFUSED means Python rejected the call and
  nothing ran. Never repeat it unchanged. Follow what it asks for if possible;
  otherwise tell the user and end the turn. The session id is issued by the
  application layer and cannot be invented.
- If the same stage fails twice, STOP. Do not attempt it a third time. Report
  what failed, what changed between attempts, and end the turn.
- If a tool returns something unexpected, say so plainly and stop. Do not work
  around it silently.
"""

# The choice list and the fixed list come from the schema, so this prompt and the
# preview panel can never disagree about what the user is allowed to ask for.
_orchestrator_prompt = (_orchestrator_prompt
                        .replace("{{CHOICES}}", choices_for_prompt())
                        .replace("{{FIXED}}", fixed_for_prompt())
                        .replace("{{THEMES}}", _theme_choice_catalog()))

# One tool call per message, for the same reason as the developer agents.
# OrchestratorState.working_memory is a plain field with NO reducer, and three
# of the four tools write it. Two of them in one assistant message raise
# InvalidUpdateError at key 'working_memory'. A reducer would be the wrong fix:
# it would turn a loud crash into a silently lost specification.
_orc_model = ChatOpenAI(
    model="gpt-5.4",
    reasoning=_reasoning_for("primary_orchestrator"),
    timeout=120,
    max_retries=2,
    parallel_tool_calls=False,
)

_assert_channels(OrchestratorState, _ORCHESTRATOR_CHANNELS, "orchestrator_agent")


@dynamic_prompt
def orchestrator_voice(request) -> str:
    """Append the selected voice to the prompt, per turn.

    A dynamic prompt rather than three separately built agents: the behaviour is
    identical in all three cases, and three agents would be three places for the
    behaviour to drift. The base prompt is always first, so a voice block can
    only add to it and never displace a rule.
    """
    state = request.state or {}
    return _orchestrator_prompt + tone_block(state.get("tone", _TONE_DEFAULT))


# ── Where the conversation lives between turns ───────────────────────────────
#
# It used to live in an InMemorySaver, so it lasted exactly as long as the Python
# process. A browser refresh survived that, because the backend keeps running,
# but a kernel restart, a crash or a redeploy did not: the page was still on disk
# and the system had forgotten the design schema behind it, so the next request
# was answered as if the user had never asked for anything.
#
# The thread id IS the session id, issued by Streamlit. Nothing here mints one.
#
# Two connection settings, both load-bearing.
#
#   check_same_thread=False   Streamlit serves each request on a worker thread,
#                             and sqlite3 refuses a connection used from a thread
#                             other than the one that opened it. LangGraph
#                             serialises its own writes, so sharing is safe.
#   journal_mode=WAL          A write-ahead log commits without rewriting the
#                             main file, which makes each checkpoint write cheap
#                             and lets a reader run while a write is in flight.
#                             Without it, the checkpoint write is the slowest
#                             thing in a superstep that otherwise only waits on
#                             the model.
_CHECKPOINT_DB = _wf_config.CHECKPOINT_DB
_ckpt_conn = _sqlite_ckpt.connect(str(_CHECKPOINT_DB), check_same_thread=False)
_ckpt_conn.execute("PRAGMA journal_mode=WAL")
_orchestrator_checkpointer = SqliteSaver(_ckpt_conn)

orchestrator_agent = create_agent(
    model=_orc_model,
    system_prompt=_orchestrator_prompt,
    tools=[
        update_input,
        ask_user,
        read_page_source,
        call_context_engineering_agent,
        call_system_design_planning_agent,
        call_secondary_orchestrator,
    ],
    middleware=[orchestrator_progress, reset_before, orchestrator_tool_progress,
                orchestrator_voice, force_modify_routing, enforce_modify_target],
    state_schema=OrchestratorState,
    checkpointer=_orchestrator_checkpointer,
)

graph = orchestrator_agent

print("Primary Orchestrator built")
print("  threads: ", _CHECKPOINT_DB.name, "(SQLite, WAL)")
print("  voices:  ", ", ".join(TONE_PROMPTS),
      f"(default {_TONE_DEFAULT})")
print("  tools:   ", ", ".join(sorted(
    graph.nodes["tools"].bound.tools_by_name)))
print("  channels:", ", ".join(_assert_channels(
    OrchestratorState, _ORCHESTRATOR_CHANNELS, "orchestrator_agent")))


# ==========================================================================
# PO-08
# ==========================================================================
# ═══════════════════════════════════════════════════════════════════════════
# run_planning_pipeline - the four generators as a deterministic chain
#
# This is what the create_agent planning agent used to do, without the agent.
# The agent only ever DECIDED three things, and all three are fixed: the call
# order, threading each stage's output into the next, and stopping when a stage
# cannot produce its field. A Python chain gives the same result without paying
# for the outer agent's reasoning on every run.
#
# Each stage is the generator's plain function (generate_<stage>_specification
# in specs): it reads the prior specifications from the state dict and returns
# (spec, message), the same code the @tool adapter runs. The driver threads the
# spec back into the state dict and hands it to the next stage, so spec CONTENT
# is unchanged from the agent path. The generators keep their own internal
# retry (three attempts each), so nothing is retried a second time here.
# ═══════════════════════════════════════════════════════════════════════════
def run_planning_pipeline(input_query, design_schema, *, progress=None,
                          run_name_prefix=None):
    """Run the four specification generators in order and return their output.

    Returns (state, error).
    - state: a dict carrying the four *_specification fields. A field is an
      empty dict when its stage never produced it.
    - error: None when all four stages produced their field, otherwise the
      reason the run stopped, taken from the failing stage's tool message. This
      mirrors the agent's 'stop and report, do not continue' rule.

    progress, when given, is called with one human-readable line before each
    stage, so the caller can forward it to the chat exactly as the planning
    agent's middleware used to.

    The stage list is built here, at call time, so the names resolve to whatever
    the four generate_*_specification globals currently hold. That is what lets
    a unit test swap in fakes without reaching inside this function.

    run_name_prefix, when given, names each stage's LangSmith run
    "<prefix> - <stage>" (e.g. "E2E-SD-01 - decoration"). It is left unset
    on the graph path, where the calls keep their default names.
    """
    stages = (
        ("layout_specification",
         "\t[Design Pipeline] Generating layout specification...",
         generate_layout_specification),
        ("components_specification",
         "\t[Design Pipeline] Generating component specifications...",
         generate_components_specification),
        ("interactions_specification",
         "\t[Design Pipeline] Generating interaction specifications...",
         generate_interactions_specification),
        ("decoration_specification",
         "\t[Design Pipeline] Generating decoration specifications...",
         generate_decoration_specification),
    )

    state = {
        "input_query": input_query or "",
        "design_schema": design_schema or {},
        "layout_specification": {},
        "components_specification": {},
        "interactions_specification": {},
        "decoration_specification": {},
    }

    # Tag every stage's LLM call with this run's name in LangSmith. Set
    # once, read by each generator's structured .invoke, reset when the run
    # ends so a later run in the same kernel starts clean.
    _rn_token = _RUN_NAME_PREFIX.set(run_name_prefix)
    try:
        for field, line, generator in stages:
            if progress is not None:
                progress(line)

            spec, message = generator(state)
            if spec is not None:
                state[field] = spec

            # A stage that did not fill its field has stopped the run. The
            # generator already spent its own three internal attempts, so
            # retrying it here would only repeat them.
            if not state.get(field):
                return state, (f"[planning] the {field} stage produced no "
                               f"output and the run stopped. {message or ''}").strip()

        return state, None
    finally:
        _RUN_NAME_PREFIX.reset(_rn_token)


print("run_planning_pipeline ready (four generators, deterministic order)")


# Re-export this module's whole namespace, so the next module
# starts from it. Part of the mechanical split of ticket 04.
__all__ = [_n for _n in list(globals())
           if not (_n.startswith("__") and _n.endswith("__"))]
