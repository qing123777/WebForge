"""secondary_orchestrator: the Secondary Orchestrator: SecondaryOrchState, the correction loop, its tools and agent.

Lines 15469-16754 of the flat fyp.py at commit 6e8c14b, moved
verbatim by refactor ticket 04 (tools/split_fyp.py).
"""
from __future__ import annotations

from webforge.test_exec import *  # noqa: F401,F403

# ==========================================================================
# State
# ==========================================================================
from typing import Annotated, Literal


def _merge_work_orders(left, right):
    """Append-only reducer for modification_history.

    The orchestrator runs CSS and JS in PARALLEL, so both land in the same
    superstep. Without a reducer LangGraph raises InvalidUpdateError rather than
    picking a winner, which is the correct behaviour: silently dropping one
    agent's work order would corrupt the running history the orchestrator reads
    this list. Each writer contributes only its OWN entry, so plain concatenation
    is right. Order between two parallel branches is not defined, and does not
    need to be -- these are a set of fixes applied in one round.
    """
    return (left or []) + (right or [])


class SecondaryOrchState(AgentState):
    session_id:                str
    user_query:                str = ""
    layout_specification:      dict = {}
    components_specification:  dict = {}
    interaction_specification: dict = {}
    decoration_specification:  dict = {}
    test_cases:                Annotated[list, _merge_test_cases] = []
    test_report:               str = ""
    modification_context:      str = ""
    modification_attempts:     int = 0
    # Calls made to each developer agent since the last test run. Reset
    # by call_test_exec_pipeline, which is what starts a new round.
    # Separate fields on purpose: css and js are called in one assistant
    # message, so a shared key would be two writes in one superstep.
    html_round_calls:          int = 0
    css_round_calls:           int = 0
    js_round_calls:            int = 0
    intent:                    Literal["generate", "modify"] = "generate"
    target_component:          str = ""
    target_instance:           int = 1
    modification_history:      Annotated[list, _merge_work_orders] = []


# ==========================================================================
# call_html_agent
# ==========================================================================
@tool
def call_html_agent(
    runtime:          ToolRuntime[SecondaryOrchState],
    query:            str,
    intent:           str = "generate",
    target_component: str = "",
    target_instance:  int = 1,
    target_components: Optional[List[str]] = None,
) -> Command:
    """
    Invoke the HTML agent.
    For Generation Mode: call with intent='generate' (default).
    For Modification Mode: call with intent='modify' and the target fields
    captured from Streamlit's click-to-select.
    target_components: OPTIONAL list of components to fix in ONE batched
    modify call, capped at _MODIFY_BATCH_CAP, exactly as for CSS and JS.
    Prefer it over one call per component: eight separate sessions in the
    2026-08-31 PO-08 run re-sent the whole page eight times and produced
    7,417 output tokens, of which 5,822 were reasoning.
    target_instance still applies to the FIRST component only, so a fix
    aimed at the Nth copy of a repeated element should be sent on its own.
    """
    writer     = get_stream_writer()
    writer({"type": "indent", "delta": 1})
    # LangGraph hands the tool a DICT state, never an object. Every other field
    # here is already read with .get(); session_id was the one attribute access,
    # and it raised AttributeError on the first real call.
    session_id = runtime.state.get("session_id", "")
    # Forward the specs from secondary-orch state. The HTML agent's prompt and
    # State expect them, and the Naming Contract needs the exact ComponentNode
    # id/className values — a paraphrased query is not enough. Sub-agents have
    # no checkpointer: anything not in this payload does not exist for them.
    _st = runtime.state
    layout_spec     = (_st.get("layout_specification")     if hasattr(_st, "get")
                       else getattr(_st, "layout_specification", None)) or {}
    components_spec = (_st.get("components_specification") if hasattr(_st, "get")
                       else getattr(_st, "components_specification", None)) or {}
    try:
        # One call per agent per round (C). Checked before any work, so a
        # refused call spends nothing. Generation is exempt: it makes one
        # call per agent by construction.
        _rc = runtime.state.get("html_round_calls", 0)
        if intent == "modify" and _rc >= _ROUND_CALL_CAP:
            return Command(update={"messages": [ToolMessage(
                content=(
                    "[ROUND CAP] The HTML Agent has already run once since "
                    "the last test run, and one call per agent per round is "
                    "the budget. Nothing it did is lost. "
                    f"Send them TOGETHER in one call: call_html_agent(target_components=[...], intent='modify') takes up to {_MODIFY_BATCH_CAP}. "
                    "For now either finish the other agents' fixes for this "
                    "round, or call call_test_exec_pipeline to verify what is "
                    "fixed so far and open the next round."),
                tool_call_id=runtime.tool_call_id)]})

        # Normalize the modify targets into a capped list, mirroring
        # call_css_agent and call_js_agent key for key. A lone
        # target_component becomes a one-item list, so every existing
        # single-target caller is unchanged.
        _comps   = list(target_components) if target_components else (
                       [target_component] if target_component else [])
        # A click-to-select modify arrives with its target ALREADY in state:
        # call_secondary_orchestrator wrote target_component/target_instance
        # there from the Streamlit marker. The model never sees state, so on
        # 13b71045 (2026-09-15) it passed target_component='' twice, the agent
        # got no target, guessed six names, and an unchanged page was saved
        # and reported as updated. When a modify call names nothing, take the
        # target from state. The correction loop always names its components,
        # so a routed batch is never overridden.
        if intent == "modify" and not _comps:
            _st_target = str(runtime.state.get("target_component") or "").strip()
            if _st_target:
                _comps = [_st_target]
                target_instance = int(runtime.state.get("target_instance")
                                      or target_instance or 1)
        _comps   = _comps[:_MODIFY_BATCH_CAP]
        _primary = _comps[0] if _comps else target_component
        payload = {
            "messages":         [{"role": "user", "content": query}],
            "user_query":       query,
            "session_id":       session_id,
            "intent":           intent,
            "target_component": _primary,
            "target_components": _comps,
            "target_instance":  target_instance,
            "html_code":        _read_preview_source(session_id, "html") if intent == "modify" else "",
            "layout_specification":     layout_spec,
            "components_specification": components_spec,
        }

        # recursion_limit is set explicitly rather than inheriting LangGraph's
        # default, which in 1.0.10 is 10000 supersteps (see
        # langgraph/_internal/_config.py DEFAULT_RECURSION_LIMIT) — effectively no
        # bound at all, and thousands of paid model calls before it trips.
        # Sizing: the worst LAWFUL run is modify mode — read_file, store (seed;
        # since 2026-11-11 only when state arrives empty),
        # then extract/diff/lint x_LINT_ATTEMPT_CAP, then the save tool = 12 tool
        # calls. Each tool-calling turn costs 2 supersteps (model node + tools
        # node), so ~25 supersteps. 50 gives 2x headroom while still stopping a
        # runaway in seconds rather than hours.
        sub_config: Dict[str, Any] = {
            "configurable":   {"session_id": session_id},
            # Sized to the batch, not to one component. A six-component
            # session that keeps the budget for one exhausts it and the
            # graceful degrade returns a half-fixed page.
            "recursion_limit": _dev_agent_recursion_limit(max(1, len(_comps))),
            "callbacks": []
        }

        captured: Dict[str, Any] = {}

        def _merge(update: Any) -> None:
            if not isinstance(update, dict):
                return
            for k, v in update.items():
                if k == "messages":
                    continue
                captured[k] = v

        # Fingerprint either side of the stream -- see _artifact_outcome.
        _fp_before = _preview_fingerprint(session_id, "html")
        _recursion_hit = _stream_dev_agent(
            html_agent, payload, sub_config, writer, on_update=_merge)

        _fp_after = _preview_fingerprint(session_id, "html")
        cmd_update = {
            "messages": [ToolMessage(
                content=(_artifact_outcome("HTML Agent", "html", session_id,
                                           _fp_before, _fp_after)
                         + _partial_fix_note(_recursion_hit, "HTML")),
                tool_call_id=runtime.tool_call_id
            )]
        }
        if intent == "modify":
            cmd_update["html_round_calls"] = _rc + 1
            # Capture the work order: the fix instruction this tool just carried
            # later uses it as the episode's fix_summary (see store middleware) —
            # reusing text the orchestrator already wrote, no extra LLM call.
            # Contribute ONLY this call's entry. The state key carries an append
            # reducer (_merge_work_orders), so returning the whole list here
            # would replay the earlier history and duplicate it whenever CSS and
            # JS run in parallel.
            cmd_update["modification_history"] = [f"[html_agent] {query}"]
        return Command(update=cmd_update)
    finally:
        writer({"type": "indent", "delta": -1})


# ==========================================================================
# call_css_agent
# ==========================================================================
@tool
def call_css_agent(
    runtime:          ToolRuntime[SecondaryOrchState],
    query:            str,
    intent:           str = "generate",
    target_component: str = "",
    target_instance:  int = 1,
    target_components: Optional[List[str]] = None,
) -> Command:
    """
    Invoke the CSS Agent.
    Generation: intent='generate' (default).
    Modification: intent='modify' + target_component, target_instance.
    """
    writer     = get_stream_writer()
    writer({"type": "indent", "delta": 1})
    # LangGraph hands the tool a DICT state, never an object. Every other field
    # here is already read with .get(); session_id was the one attribute access,
    # and it raised AttributeError on the first real call.
    session_id = runtime.state.get("session_id", "")
    # Forward the decoration_specification verbatim (deterministic Python copy — the
    # LLM never re-types values, so transcription drift is impossible for this
    # field). The work-order query still carries intent and direction.
    _st = runtime.state
    decoration_spec  = (_st.get("decoration_specification") if hasattr(_st, "get")
                       else getattr(_st, "decoration_specification", None)) or {}
    # Same verbatim copy, for the same reason. Without it the CSS stage
    # cannot see a region that owns no components (B2).
    layout_spec      = (_st.get("layout_specification") if hasattr(_st, "get")
                       else getattr(_st, "layout_specification", None)) or {}
    # The selector allowlist in css_prompt_selector reads this; without it
    # the block renders empty and the CSS stage guesses the componentCategory
    # (.add-to-cart-button) over the real className (.add-to-cart-btn). HTML
    # and JS forward it the same way; CSS was the gap (2026-09-01).
    components_spec  = (_st.get("components_specification") if hasattr(_st, "get")
                       else getattr(_st, "components_specification", None)) or {}
    try:
        # One call per agent per round (C). Checked before any work, so a
        # refused call spends nothing. Generation is exempt: it makes one
        # call per agent by construction.
        _rc = runtime.state.get("css_round_calls", 0)
        if intent == "modify" and _rc >= _ROUND_CALL_CAP:
            return Command(update={"messages": [ToolMessage(
                content=(
                    "[ROUND CAP] The CSS Agent has already run once since "
                    "the last test run, and one call per agent per round is "
                    "the budget. Nothing it did is lost. "
                    f"Send them TOGETHER in one call: call_css_agent(target_components=[...], intent='modify') takes up to {_MODIFY_BATCH_CAP}. "
                    "For now either finish the other agents' fixes for this "
                    "round, or call call_test_exec_pipeline to verify what is "
                    "fixed so far and open the next round."),
                tool_call_id=runtime.tool_call_id)]})

        # Normalize modify targets into a capped list. A single
        # target_component becomes a one-item list (back-compat); a
        # target_components list lets the orchestrator batch several
        # components into one warm session. The cap bounds session size.
        _comps   = list(target_components) if target_components else (
                       [target_component] if target_component else [])
        # A click-to-select modify arrives with its target ALREADY in state:
        # call_secondary_orchestrator wrote target_component/target_instance
        # there from the Streamlit marker. The model never sees state, so on
        # 13b71045 (2026-09-15) it passed target_component='' twice, the agent
        # got no target, guessed six names, and an unchanged page was saved
        # and reported as updated. When a modify call names nothing, take the
        # target from state. The correction loop always names its components,
        # so a routed batch is never overridden.
        if intent == "modify" and not _comps:
            _st_target = str(runtime.state.get("target_component") or "").strip()
            if _st_target:
                _comps = [_st_target]
                target_instance = int(runtime.state.get("target_instance")
                                      or target_instance or 1)
        _comps   = _comps[:_MODIFY_BATCH_CAP]
        _primary = _comps[0] if _comps else target_component
        payload = {
            "messages":         [{"role": "user", "content": query}],
            "session_id":       session_id,
            "intent":           intent,
            "target_component": _primary,
            "target_components": _comps,
            "target_instance":  target_instance,
            "css_specification": query,
            "css_code":         _read_preview_source(session_id, "css") if intent == "modify" else "",
            "lint_passed":      False,
            "layout_specification": layout_spec,
            "decoration_specification": decoration_spec,
            "components_specification": components_spec,
        }
        # Explicit rather than LangGraph's default of 25 — see call_html_agent
        # for the superstep arithmetic behind the value.
        sub_config = {"configurable": {"session_id": session_id},
                      "callbacks": [],
                      "recursion_limit": _dev_agent_recursion_limit(len(_comps))}
        # Fingerprint either side of the stream -- see _artifact_outcome.
        _fp_before = _preview_fingerprint(session_id, "css")
        _recursion_hit = _stream_dev_agent(
            css_agent, payload, sub_config, writer)

        _fp_after = _preview_fingerprint(session_id, "css")
        cmd_update = {
            "messages": [ToolMessage(
                content=(_artifact_outcome("CSS Agent", "css", session_id,
                                           _fp_before, _fp_after)
                         + _partial_fix_note(_recursion_hit, "CSS")),
                tool_call_id=runtime.tool_call_id
            )]
        }
        if intent == "modify":
            cmd_update["css_round_calls"] = _rc + 1
            # Capture the work order: the fix instruction this tool just carried
            # later uses it as the episode's fix_summary (see store middleware) —
            # reusing text the orchestrator already wrote, no extra LLM call.
            # Contribute ONLY this call's entry. The state key carries an append
            # reducer (_merge_work_orders), so returning the whole list here
            # would replay the earlier history and duplicate it whenever CSS and
            # JS run in parallel.
            cmd_update["modification_history"] = [f"[css_agent] {query}"]
        return Command(update=cmd_update)
    finally:
        writer({"type": "indent", "delta": -1})


# ==========================================================================
# call_js_agent
# ==========================================================================
@tool
def call_js_agent(
    runtime:          ToolRuntime[SecondaryOrchState],
    query:            str,
    intent:           str = "generate",
    target_component: str = "",
    target_instance:  int = 1,
    target_components: Optional[List[str]] = None,
) -> Command:
    """
    Invoke the JS Agent.
    Generation: intent='generate' (default).
    Modification: intent='modify' + target_component, target_instance.
    """
    writer     = get_stream_writer()
    writer({"type": "indent", "delta": 1})
    # LangGraph hands the tool a DICT state, never an object. Every other field
    # here is already read with .get(); session_id was the one attribute access,
    # and it raised AttributeError on the first real call.
    session_id = runtime.state.get("session_id", "")
    # Forward the interaction_specification verbatim (deterministic Python copy — the
    # LLM never re-types values, so transcription drift is impossible for this
    # field). The work-order query still carries intent and direction.
    _st = runtime.state
    interaction_spec = (_st.get("interaction_specification") if hasattr(_st, "get")
                       else getattr(_st, "interaction_specification", None)) or {}
    components_spec  = (_st.get("components_specification") if hasattr(_st, "get")
                       else getattr(_st, "components_specification", None)) or {}
    try:
        # One call per agent per round (C). Checked before any work, so a
        # refused call spends nothing. Generation is exempt: it makes one
        # call per agent by construction.
        _rc = runtime.state.get("js_round_calls", 0)
        if intent == "modify" and _rc >= _ROUND_CALL_CAP:
            return Command(update={"messages": [ToolMessage(
                content=(
                    "[ROUND CAP] The JS Agent has already run once since "
                    "the last test run, and one call per agent per round is "
                    "the budget. Nothing it did is lost. "
                    f"Send them TOGETHER in one call: call_js_agent(target_components=[...], intent='modify') takes up to {_MODIFY_BATCH_CAP}. "
                    "For now either finish the other agents' fixes for this "
                    "round, or call call_test_exec_pipeline to verify what is "
                    "fixed so far and open the next round."),
                tool_call_id=runtime.tool_call_id)]})

        # Normalize modify targets into a capped list. A single
        # target_component becomes a one-item list (back-compat); a
        # target_components list lets the orchestrator batch several
        # components into one warm session. The cap bounds session size.
        _comps   = list(target_components) if target_components else (
                       [target_component] if target_component else [])
        # A click-to-select modify arrives with its target ALREADY in state:
        # call_secondary_orchestrator wrote target_component/target_instance
        # there from the Streamlit marker. The model never sees state, so on
        # 13b71045 (2026-09-15) it passed target_component='' twice, the agent
        # got no target, guessed six names, and an unchanged page was saved
        # and reported as updated. When a modify call names nothing, take the
        # target from state. The correction loop always names its components,
        # so a routed batch is never overridden.
        if intent == "modify" and not _comps:
            _st_target = str(runtime.state.get("target_component") or "").strip()
            if _st_target:
                _comps = [_st_target]
                target_instance = int(runtime.state.get("target_instance")
                                      or target_instance or 1)
        _comps   = _comps[:_MODIFY_BATCH_CAP]
        _primary = _comps[0] if _comps else target_component
        payload = {
            "messages":         [{"role": "user", "content": query}],
            "session_id":       session_id,
            "intent":           intent,
            "target_component": _primary,
            "target_components": _comps,
            "target_instance":  target_instance,
            "js_specification": query,
            "js_code":          _read_preview_source(session_id, "js") if intent == "modify" else "",
            "lint_passed":      False,
            "interaction_specification": interaction_spec,
            "components_specification": components_spec,
        }
        # Explicit rather than LangGraph's default of 25 — see call_html_agent
        # for the superstep arithmetic behind the value.
        sub_config = {"configurable": {"session_id": session_id},
                      "callbacks": [],
                      "recursion_limit": _dev_agent_recursion_limit(len(_comps))}
        # Fingerprint either side of the stream -- see _artifact_outcome.
        _fp_before = _preview_fingerprint(session_id, "js")
        _recursion_hit = _stream_dev_agent(
            js_agent, payload, sub_config, writer)

        _fp_after = _preview_fingerprint(session_id, "js")
        cmd_update = {
            "messages": [ToolMessage(
                content=(_artifact_outcome("JS Agent", "js", session_id,
                                           _fp_before, _fp_after)
                         + _partial_fix_note(_recursion_hit, "JS")),
                tool_call_id=runtime.tool_call_id
            )]
        }
        if intent == "modify":
            cmd_update["js_round_calls"] = _rc + 1
            # Capture the work order: the fix instruction this tool just carried
            # later uses it as the episode's fix_summary (see store middleware) —
            # reusing text the orchestrator already wrote, no extra LLM call.
            # Contribute ONLY this call's entry. The state key carries an append
            # reducer (_merge_work_orders), so returning the whole list here
            # would replay the earlier history and duplicate it whenever CSS and
            # JS run in parallel.
            cmd_update["modification_history"] = [f"[js_agent] {query}"]
        return Command(update=cmd_update)
    finally:
        writer({"type": "indent", "delta": -1})


# ==========================================================================
# call_test_gen_agent
# ==========================================================================
@tool
def call_test_gen_agent(
    runtime: ToolRuntime[SecondaryOrchState],
    query:   str = "",
) -> Command:
    """
    Invoke the Test Generation Agent.
    Reads all 4 specifications and user_query from secondary orchestrator state.
    Stores test_cases back into state via Command.update.
    """
    writer     = get_stream_writer()
    writer({"type": "indent", "delta": 1})
    state      = runtime.state
    # LangGraph hands the tool a DICT state, never an object. Every other field
    # here is already read with .get(); session_id was the one attribute access,
    # and it raised AttributeError on the first real call.
    session_id = state.get("session_id", "")
    try:
        payload = {
            "messages":                 [{"role": "user", "content": query}],
            "user_query":               state.get("user_query", query),
            "layout_specification":     state.get("layout_specification", {}),
            "components_specification": state.get("components_specification", {}),
            "interaction_specification":state.get("interaction_specification", {}),
            "decoration_specification": state.get("decoration_specification", {}),
            "session_id":               session_id,
            "test_cases":               [],
        }
        # Explicit rather than LangGraph's default of 25 — see call_html_agent
        # for the superstep arithmetic behind the value.
        sub_config = {"configurable": {"session_id": session_id},
                      "callbacks": [], "recursion_limit": 50}
        captured: dict = {}

        def _merge(update):
            if not isinstance(update, dict):
                return
            for k, v in update.items():
                if k == "messages":
                    continue
                if k == "test_cases":
                    # test_cases streams one CHUNK per store_test_cases call (the
                    # agent generates in batches). Accumulate with the same
                    # dedup-by-id reducer the agent state uses, so the captured
                    # suite is the UNION of all batches, not just the last one.
                    captured["test_cases"] = _merge_test_cases(
                        captured.get("test_cases", []), v)
                else:
                    captured[k] = v

        # recursion_limit BOUNDS the loop but does not end it gracefully -- when
        # the budget runs out LangGraph RAISES GraphRecursionError, which would
        # abort the whole orchestrator run. The suite generated so far is still
        # valid (every batch was schema-checked before it was saved), it is only
        # coverage that may be short, so degrade to the partial suite instead of
        # crashing. Batches are already accumulated in `captured` by _merge, so
        # nothing is lost by catching this here.
        from langgraph.errors import GraphRecursionError as _GraphRecursionError
        _recursion_hit = False
        try:
            for chunk in test_gen_agent.stream(
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
                        _merge(up)
        except _GraphRecursionError:
            _recursion_hit = True
            writer("   [Test Gen Agent] Stopped at the generation limit; "
                   "keeping the test cases written so far.")

        test_cases = captured.get("test_cases", [])
        if _recursion_hit:
            _content = (
                f"[Secondary Orchestrator] Test Gen Agent hit its generation limit "
                f"(recursion_limit=50) before reporting SUITE COMPLETE. Returning the "
                f"PARTIAL suite: {len(test_cases)} test case(s) stored. Every case is "
                f"schema-valid, but spec coverage may be incomplete. Continue with this "
                f"suite and note the limitation in your final message -- do NOT call the "
                f"Test Generation Agent again.")
        else:
            _content = (f"[Secondary Orchestrator] Test Gen Agent completed. "
                        f"{len(test_cases)} test case(s) stored.")
        return Command(update={
            "test_cases": test_cases,
            "messages":   [ToolMessage(content=_content,
                                       tool_call_id=runtime.tool_call_id)]
        })
    finally:
        writer({"type": "indent", "delta": -1})


# ==========================================================================
# call_test_exec_agent
# ==========================================================================
def _routed_agents_from_report(report: str) -> set:
    """Developer agents the report's 'Action required:' lines route work to.

    Returns a subset of {'html', 'css', 'js'}, empty when there is no
    Action-required section (a clean run or a baseline). The routing is
    deterministic data _build_report already computed via _route_agent; this
    reads which agents appear so the dispatch-completeness guard can tell a
    routed-but-uncalled agent (a dropped fix) from an agent with no work.
    """
    agents = set()
    in_actions = False
    for raw in (report or "").splitlines():
        line = raw.strip()
        if line.startswith("Action required:"):
            in_actions = True
            continue
        if in_actions and line.startswith("- ") and "_agent" in line:
            head = line[2:].split("|", 1)[0].strip()
            for key in ("html", "css", "js"):
                if head == f"{key}_agent":
                    agents.add(key)
    return agents


@tool
def call_test_exec_pipeline(
    runtime:              ToolRuntime[SecondaryOrchState],
    query:                str = "Execute all test cases",
    modification_context: str = "",
) -> Command:
    """
    Run the Playwright test suite directly (deterministic pipeline — no sub-agent).
    Reads test_cases and session_id from secondary orchestrator state.
    modification_context (optional): describes which component was just modified.
    Stores test_report back into state and increments modification_attempts
    on any re-run (any call after the baseline, i.e. once a report already
    exists in state).
    Hard cap: refuses to run (no Playwright execution) once
    modification_attempts has already reached the cap on a re-run -- independent of
    whether the caller passed modification_context.
    """
    writer     = get_stream_writer()
    writer({"type": "indent", "delta": 1})
    state      = runtime.state
    # LangGraph hands the tool a DICT state, never an object. Every other field
    # here is already read with .get(); session_id was the one attribute access,
    # and it raised AttributeError on the first real call.
    session_id = state.get("session_id", "")
    try:
        # Hard enforcement of the modification_attempts cap. The system
        # prompt instructs the LLM to stop at cap, but a reasoning lapse could
        # still re-invoke this tool — this guard makes the cap non-negotiable
        # in code, independent of whether the LLM honors the instruction.
        # Checked FIRST, before any setup work, so a refused call does nothing.
        current_attempts = state.get("modification_attempts", 0)
        # A re-run is any pipeline call after the baseline -- the baseline is
        # the first call, when state carries no report yet. Keying the cap on
        # modification_context was the hole: an UNLABELED re-run left the
        # counter frozen, so "stop at 2" never fired and the loop ran on to
        # recursion_limit (PO-08 runaway, 2026-08-29, ~1M tokens). Any re-run
        # now counts and is refused past the cap, labelled or not. The
        # baseline (no prior report) is never refused: refusing it would
        # leave the page untested.
        is_rerun = bool(str(state.get("test_report", "") or "").strip())
        if is_rerun and current_attempts >= _MODIFICATION_ATTEMPT_CAP:
            return Command(update={
                "messages": [ToolMessage(
                    content=(
                        "[Secondary Orchestrator] Test Execution Pipeline call REFUSED — "
                        f"modification_attempts cap ({_MODIFICATION_ATTEMPT_CAP}) already reached.\n"
                        "The correction loop must stop now. Report the partial "
                        "result to the user and END; do not call "
                        "call_test_exec_pipeline again."
                    ),
                    tool_call_id=runtime.tool_call_id
                )]
            })

        # ── Dispatch-completeness guard (2026-09-05) ───────────────────
        # The prior report already routed each failure to an agent. The LLM
        # Secondary Orchestrator is told to call every routed agent, but on
        # PO-10 po0735889c it skipped html_agent ENTIRELY though the report
        # routed two fixes to it, so the URL and cart-count failures were never
        # attempted. The routing is deterministic data -- only the LLM's
        # dispatch is unreliable -- so on a re-run, if the report routed work to
        # an agent that got ZERO calls this round, refuse and name it: a routed
        # agent with no call is a dropped work order, not a finished round.
        # Fires ONLY when the agent was routed work (a failure needs it); an
        # agent with no routed line is correctly absent. The refusal returns
        # before the run, so it neither tests nor spends a correction attempt.
        if is_rerun:
            _routed = _routed_agents_from_report(state.get("test_report", "") or "")
            _skipped = sorted(
                a for a in _routed
                if state.get(f"{a}_round_calls", 0) == 0)
            if _skipped:
                _names = ", ".join(f"{a}_agent" for a in _skipped)
                _was = "was" if len(_skipped) == 1 else "were"
                return Command(update={
                    "messages": [ToolMessage(
                        content=(
                            "[Secondary Orchestrator] Test Execution Pipeline call "
                            f"REFUSED -- the last report routed work to {_names}, but "
                            f"{_names} {_was} not called this round. A routed agent "
                            "with no call is a dropped fix, not a finished round. Call "
                            f"{_names} with the target_components from its 'Action "
                            "required:' lines (HTML first if present), THEN re-run "
                            "call_test_exec_pipeline. This refusal did not use a "
                            "correction attempt."
                        ),
                        tool_call_id=runtime.tool_call_id
                    )]
                })

        import pathlib as _pl
        _preview_path = _wf_config.PREVIEW_DIR / f"preview_{session_id}.html"
        preview_url   = _preview_path.as_uri()

        # ── Deterministic pipeline (2026-07-08): test execution needs no LLM ──
        # The former test_exec_agent's only permitted behaviour was calling
        # run_test_suite exactly once, so the sub-agent turn was pure overhead
        # (one LLM round-trip of latency + tokens + a stochastic failure
        # surface) on every test run, including each correction re-run. The
        # suite is now invoked directly. Every external contract is unchanged:
        # tool signature, cap guard, report format, attempt counting,
        # ToolMessage shape.
        from types import SimpleNamespace as _SNS
        writer("[Test Execution Pipeline] Running Playwright test suite...")
        _suite_rt = _SNS(
            state={
                "test_cases":           state.get("test_cases", []),
                "preview_url":          preview_url,
                "modification_context": modification_context,
                "session_id":           session_id,
            },
            tool_call_id=runtime.tool_call_id,
        )
        _suite_up   = run_test_suite.func(_suite_rt).update
        test_report = _suite_up.get("test_report", "")
        # current_attempts was already read for the cap check above and the
        # state has not changed since, so re-reading it would be redundant.
        new_attempts     = current_attempts + 1 if is_rerun else current_attempts
        cmd_update  = {
            "test_report": test_report,
            "messages": [ToolMessage(
                content=(
                    "[Secondary Orchestrator] Test Execution Pipeline completed.\n"
                    f"modification_attempts: {new_attempts} / cap: {_MODIFICATION_ATTEMPT_CAP}\n"
                    f"Report:\n{_digest_test_report(test_report)}"
                ),
                tool_call_id=runtime.tool_call_id
            )]
        }
        # A test run IS the round boundary, so every per-round call counter
        # restarts here. Written on the baseline too: that call opens round
        # one. Safe to write all three from one tool because the pipeline is
        # never called alongside a developer agent.
        cmd_update["html_round_calls"] = 0
        cmd_update["css_round_calls"]  = 0
        cmd_update["js_round_calls"]   = 0
        if is_rerun:
            cmd_update["modification_attempts"] = new_attempts
        return Command(update=cmd_update)
    finally:
        writer({"type": "indent", "delta": -1})


# ==========================================================================
# call_test_exec_agent
# ==========================================================================
def _known_decoration_ids(decoration_spec) -> list:
    """componentId/className pairs the spec defines. Named in a skip message so
    the model can correct the name instead of guessing again."""
    spec = _coerce_spec(decoration_spec or {}) or {}
    out = []
    if isinstance(spec, dict):
        for page in spec.get("pages", []) or []:
            for d in (page.get("componentDecorations") or []) if isinstance(page, dict) else []:
                if isinstance(d, dict) and d.get("componentId"):
                    out.append(d["componentId"] + (
                        f" (.{d['className']})" if d.get("className") else ""))
    return out


def _find_component_decoration(decoration_spec, component):
    """Return the ComponentDecoration dict for `component`, or {}.

    DecorationSpecification is NESTED: pages[].componentDecorations[], each joined
    to a component by `componentId` (and carrying its `className`). Looking the
    component up as a top-level key finds nothing on a real spec, so the caller
    would silently skip the patch and leave assert_css expectations STALE.
    Matches componentId first, then className, and still accepts the legacy flat
    {component: {...}} shape so older fixtures keep working.
    """
    spec = _coerce_spec(decoration_spec or {}) or {}
    if not isinstance(spec, dict):
        return {}
    # The orchestrator has been seen to write "add-to-cart button" for the
    # component id `add-to-cart-button` (E2E-SO-02, 2026-08-09), which skipped
    # the sync silently and left assert_css expectations stale.
    import re as _re_sync
    _norm = _re_sync.sub(r"\s+", "-", (component or "").strip())
    for page in spec.get("pages", []) or []:
        if not isinstance(page, dict):
            continue
        for d in page.get("componentDecorations") or []:
            if isinstance(d, dict) and (
                    component in (d.get("componentId"), d.get("className"))
                    or _norm in (d.get("componentId"), d.get("className"))):
                return d
    legacy = spec.get(component)
    return legacy if isinstance(legacy, dict) else {}


# ── Reading the styles a component ACTUALLY has ─────────────────────────────
# sync_css_test_cases rebases assert_css expectations after a user asks for a
# style change. It used to take the new value from decoration_specification --
# but nothing updates that specification in modify mode, so it rebased to the
# value the page had just stopped having. E2E-SO-04 on 2026-08-11: the button
# was changed to #d93025, sync wrote back #1a73e8, the suite failed twice, and
# the correction cap was exhausted on a value no agent could ever satisfy.
#
# The stylesheet on disk is the only honest source here, because the user's
# change has already been applied to it and reviewed by the linter.
import copy as _copy_sync

_CSS_VAR_REF = _re_cssres.compile(r"var\(\s*(--[\w-]+)\s*(?:,[^)]*)?\)")


def _css_root_vars(css_code: str) -> dict:
    """--name -> literal value, from every :root block."""
    out = {}
    for block in _extract_css_blocks(css_code, ":root"):
        body = block[block.find("{") + 1:block.rfind("}")]
        for line in body.split(";"):
            if ":" not in line:
                continue
            name, _, val = line.partition(":")
            name, val = name.strip(), val.strip()
            if name.startswith("--") and val:
                out[name] = val
    return out


def _resolve_css_value(value: str, root_vars: dict, depth: int = 0) -> str:
    """Substitute var(--x) with the literal :root declares, up to 3 levels."""
    if depth > 3 or "var(" not in (value or ""):
        return (value or "").strip()
    def rep(m):
        return root_vars.get(m.group(1), m.group(0))
    return _resolve_css_value(_CSS_VAR_REF.sub(rep, value), root_vars, depth + 1)


def _live_component_styles(css_code: str, component: str, decoration_spec,
                           props) -> dict:
    """prop -> the value the SAVED stylesheet gives `component`, for `props` only.

    State variants are skipped: a `:hover` or `[aria-disabled]` rule is not the
    resting value assert_css compares against. Later blocks win, matching the
    cascade for rules of equal specificity.
    """
    if not css_code or not props:
        return {}
    _, blocks = _resolve_css_component(css_code, component, decoration_spec)
    if not blocks:
        return {}
    root_vars = _css_root_vars(css_code)
    wanted, found = set(props), {}
    for block in blocks:
        prelude = block[:block.find("{")]
        if any(mark in prelude for mark in _VARIANT_MARKERS):
            continue
        body = block[block.find("{") + 1:block.rfind("}")]
        for decl in body.split(";"):
            if ":" not in decl:
                continue
            prop, _, val = decl.partition(":")
            prop = prop.strip().lower()
            if prop in wanted and val.strip():
                found[prop] = _resolve_css_value(val, root_vars)
    return found


def _live_hover_styles(css_code: str, component: str, decoration_spec,
                       props) -> dict:
    """prop -> the value the SAVED stylesheet gives `component` ON HOVER.

    The mirror of _live_component_styles. That one skips every variant block
    because a :hover rule is not the resting value assert_css compares against.
    This one keeps only the :hover blocks, for the same reason in reverse.

    It exists because sync_hover_test_cases had no way to read the page and so
    took its value from the specification instead. A modify run never updates
    the specification, so that value is the one from generation, and rebasing
    onto it moves the expectation BACKWARDS onto a colour the page no longer
    uses. That is the defect this pair of functions already fixed once, for
    resting styles, in SO-04.

    Later blocks win, matching the cascade for rules of equal specificity.
    """
    if not css_code or not props:
        return {}
    _, blocks = _resolve_css_component(css_code, component, decoration_spec)
    if not blocks:
        return {}
    root_vars = _css_root_vars(css_code)
    wanted, found = set(props), {}
    for block in blocks:
        prelude = block[:block.find("{")]
        if ":hover" not in prelude:
            continue
        body = block[block.find("{") + 1:block.rfind("}")]
        for decl in body.split(";"):
            if ":" not in decl:
                continue
            prop, _, val = decl.partition(":")
            prop = prop.strip().lower()
            if prop in wanted and val.strip():
                found[prop] = _resolve_css_value(val, root_vars)
    return found


@tool
def sync_css_test_cases(component: str, runtime: ToolRuntime[SecondaryOrchState]) -> Command:
    """
    Rebuild assert_css expected values for one component from decoration_specification.
    Call after a user-requested style change, before re-running call_test_exec_pipeline.
    Avoids re-invoking call_test_gen_agent for a full test suite regeneration.
    """
    decoration_spec = runtime.state.get("decoration_specification", {})
    test_cases      = runtime.state.get("test_cases", [])
    session_id      = runtime.state.get("session_id", "")

    # Rebasing is only ever legitimate when the USER asked for the change. In an
    # internal correction round the page is the thing that is wrong and the
    # specification is the thing that is right, so moving the goalposts would
    # hide the failure the loop exists to fix -- and it would do so silently,
    # since the suite would then pass. modification_context is set only on a
    # correction round, so it is the exact discriminator.
    if (runtime.state.get("modification_context") or "").strip():
        return Command(update={"messages": [ToolMessage(
            content=(
                "REFUSED: sync_css_test_cases rebases assert_css expectations onto "
                "the current page, which is only correct when the USER requested "
                "the style change. This is a correction round -- the page is what "
                "is wrong here, not the test -- so rebasing would hide the very "
                "failure being repaired. Fix the CSS instead."),
            tool_call_id=runtime.tool_call_id)]})

    comp_styles = _find_component_decoration(decoration_spec, component).get("baseStyles", {})
    if not comp_styles:
        return Command(update={"messages": [ToolMessage(
            content=(
                f"No baseStyles found for '{component}' in decoration_specification. "
                f"Skipping sync — existing assert_css expected values unchanged. "
                f"The specification decorates: {_known_decoration_ids(decoration_spec)}."
            ),
            tool_call_id=runtime.tool_call_id
        )]})

    # The SPECIFICATION says which properties to assert. The PAGE says what they
    # are now. Taking the value from the specification is what broke SO-04: the
    # user's change never reaches it, so it holds the pre-change value.
    live = _live_component_styles(_read_preview_source(session_id, "css"),
                                  component, decoration_spec, set(comp_styles))
    resolved = {p: live.get(p, v) for p, v in comp_styles.items()}
    new_expected = "|".join(f"{p}={v}" for p, v in resolved.items())

    updated = [
        {**tc, "expected": new_expected}
        if tc["component"] == component and tc["action"] == "assert_css"
        else tc
        for tc in test_cases
    ]

    # Return ONLY the cases this call changed. The state key carries
    # _merge_test_cases, which appends new ids and replaces re-sent ones, so a
    # delta merges cleanly even when two sync tools land in the same parallel
    # step. Returning the whole suite would make the second write replace every
    # id with its pre-patch version and silently undo the first tool's work.
    changed = [n for o, n in zip(test_cases, updated) if o != n]
    patched = len(changed)

    # Modify mode does not update the specifications, so this rebases the TEST
    # expectations only. It returns the changed cases and writes just test_cases
    # (a _merge_test_cases-reduced channel), so it stays safe even when sync_css
    # and sync_hover land in the same parallel step. It does NOT write
    # decoration_specification -- that un-reduced channel is what made two syncs
    # in one step raise InvalidUpdateError (SO-06, 2026-09-01).
    update = {"test_cases": changed}

    update["messages"] = [ToolMessage(
        content=(
            f"Patched {patched} assert_css case(s) for '{component}'. "
            f"New expected: '{new_expected}'."
        ),
        tool_call_id=runtime.tool_call_id
    )]
    return Command(update=update)


# ==========================================================================
# call_test_exec_agent
# ==========================================================================
@tool
def sync_text_test_cases(component: str, new_text: str, runtime: ToolRuntime[SecondaryOrchState]) -> Command:
    """
    Rebuild assert_text expected values for one component after a user-requested
    text change. new_text is the text the user asked for — it is the new source of
    truth (modification mode does not update the specifications).
    Call after the change is applied, before re-running call_test_exec_pipeline.
    """
    test_cases = runtime.state.get("test_cases", [])

    # Rebasing is only ever legitimate when the USER asked for the change. In an
    # internal correction round the page is the thing that is wrong and the test
    # is the thing that is right, so moving the goalposts would hide the failure
    # the loop exists to fix -- and it would do so silently, since the suite
    # would then pass. modification_context is set only on a correction round,
    # so it is the exact discriminator. Same guard as sync_css_test_cases and
    # sync_hover_test_cases.
    if (runtime.state.get("modification_context") or "").strip():
        return Command(update={"messages": [ToolMessage(
            content=(
                "REFUSED: sync_text_test_cases rebases assert_text expectations "
                "onto text the caller supplies, which is only correct when the "
                "USER requested the wording change. This is a correction round "
                "-- the page is what is wrong here, not the test -- so rebasing "
                "would hide the very failure being repaired. Fix the markup "
                "instead."),
            tool_call_id=runtime.tool_call_id)]})

    if not new_text:
        return Command(update={"messages": [ToolMessage(
            content=(
                f"No new_text provided for '{component}'. "
                f"Skipping sync — existing assert_text expected values unchanged."
            ),
            tool_call_id=runtime.tool_call_id
        )]})

    updated = [
        {**tc, "expected": new_text}
        if tc["component"] == component and tc["action"] == "assert_text"
        else tc
        for tc in test_cases
    ]

    # Return ONLY the cases this call changed. The state key carries
    # _merge_test_cases, which appends new ids and replaces re-sent ones, so a
    # delta merges cleanly even when two sync tools land in the same parallel
    # step. Returning the whole suite would make the second write replace every
    # id with its pre-patch version and silently undo the first tool's work.
    changed = [n for o, n in zip(test_cases, updated) if o != n]
    patched = len(changed)

    return Command(update={
        "test_cases": changed,
        "messages": [ToolMessage(
            content=(
                f"Patched {patched} assert_text case(s) for '{component}'. "
                f"New expected: '{new_text}'"
            ),
            tool_call_id=runtime.tool_call_id
        )]
    })


# ==========================================================================
# call_test_exec_agent
# ==========================================================================
@tool
def sync_hover_test_cases(component: str, runtime: ToolRuntime[SecondaryOrchState]) -> Command:
    """
    Rebuild assert_hover_css expected values for one component from the hover
    style the SAVED stylesheet actually carries. Call after a user-requested
    hover-style change, before re-running call_test_exec_pipeline. The twin of
    sync_css_test_cases: that one rebases resting styles onto assert_css, this
    one rebases the hover variant onto assert_hover_css. Without it a
    hover-style change leaves those cases stale, and the pipeline reports a
    false failure against correct code.
    """
    decoration_spec = runtime.state.get("decoration_specification", {})
    test_cases      = runtime.state.get("test_cases", [])
    session_id      = runtime.state.get("session_id", "")

    # Rebasing is only ever legitimate when the USER asked for the change. In an
    # internal correction round the page is the thing that is wrong and the
    # specification is the thing that is right, so moving the goalposts would
    # hide the failure the loop exists to fix -- and it would do so silently,
    # since the suite would then pass. modification_context is set only on a
    # correction round, so it is the exact discriminator. Same guard, same
    # wording, as sync_css_test_cases.
    if (runtime.state.get("modification_context") or "").strip():
        return Command(update={"messages": [ToolMessage(
            content=(
                "REFUSED: sync_hover_test_cases rebases assert_hover_css "
                "expectations onto the current page, which is only correct when "
                "the USER requested the hover-style change. This is a correction "
                "round -- the page is what is wrong here, not the test -- so "
                "rebasing would hide the very failure being repaired. Fix the "
                "CSS instead."),
            tool_call_id=runtime.tool_call_id)]})

    # Generation derives assert_hover_css from stateVariants (NOT from
    # baseStyles), so the sync must read the same source or it would rewrite the
    # expectation into a different shape than the suite was built with.
    decoration = _find_component_decoration(decoration_spec, component)
    hover_styles = {}
    for sv in decoration.get("stateVariants") or []:
        if isinstance(sv, dict) and sv.get("stateName") == "hover":
            hover_styles = sv.get("styles") or {}
            break

    if not hover_styles:
        return Command(update={"messages": [ToolMessage(
            content=(
                f"No hover stateVariant found for '{component}' in decoration_specification. "
                f"Skipping sync — existing assert_hover_css expected values unchanged. "
                f"The specification decorates: {_known_decoration_ids(decoration_spec)}."
            ),
            tool_call_id=runtime.tool_call_id
        )]})

    # The SPECIFICATION says which properties to assert. The PAGE says what they
    # are now. Taking the value from the specification is what broke SO-04 for
    # resting styles, and it is what broke SO-06 here: a modify run never writes
    # back to the specification, so it still holds the pre-change colour and the
    # rebase runs BACKWARDS onto a value the page no longer uses.
    live = _live_hover_styles(_read_preview_source(session_id, "css"),
                              component, decoration_spec, set(hover_styles))
    resolved = {p: live.get(p, v) for p, v in hover_styles.items()}
    new_expected = "|".join(f"{p}={v}" for p, v in resolved.items())

    updated = [
        {**tc, "expected": new_expected}
        if tc["component"] == component and tc["action"] == "assert_hover_css"
        else tc
        for tc in test_cases
    ]

    # Return ONLY the cases this call changed. The state key carries
    # _merge_test_cases, which appends new ids and replaces re-sent ones, so a
    # delta merges cleanly even when two sync tools land in the same parallel
    # step. Returning the whole suite would make the second write replace every
    # id with its pre-patch version and silently undo the first tool's work.
    changed = [n for o, n in zip(test_cases, updated) if o != n]
    patched = len(changed)

    # Modify mode does not update the specifications, so this rebases the TEST
    # expectations only. It returns the changed cases and writes just test_cases
    # (a _merge_test_cases-reduced channel), so it stays safe even when sync_css
    # and sync_hover land in the same parallel step. It does NOT write
    # decoration_specification -- that un-reduced channel is what made two syncs
    # in one step raise InvalidUpdateError (SO-06, 2026-09-01).
    update = {"test_cases": changed}

    update["messages"] = [ToolMessage(
        content=(
            f"Patched {patched} assert_hover_css case(s) for '{component}'. "
            f"New expected: '{new_expected}'."
        ),
        tool_call_id=runtime.tool_call_id
    )]
    return Command(update=update)


# ==========================================================================
# Middlewares
# ==========================================================================
@before_agent
def deep_agent_progress(state, runtime):
    get_stream_writer()("   [Secondary Orchestrator] Processing request...")
    return None


@wrap_tool_call
def deep_agent_tool_progress(request, handler):
    writer = get_stream_writer()
    tool_name = ""
    try:
        tool_name = (request.tool_call or {}).get("name") or ""
    except Exception:
        tool_name = ""

    if tool_name == "call_html_agent":
        writer("   [Secondary Orchestrator] Calling HTML Agent...")
    elif tool_name == "call_css_agent":
        writer("   [Secondary Orchestrator] Calling CSS Agent...")
    elif tool_name == "call_js_agent":
        writer("   [Secondary Orchestrator] Calling JS Agent...")
    elif tool_name == "call_test_gen_agent":
        writer("   [Secondary Orchestrator] Calling Test Generation Agent...")
    elif tool_name == "call_test_exec_pipeline":
        writer("   [Secondary Orchestrator] Calling Test Execution Pipeline...")
    # The three sync tools rebase an EXISTING suite after a style or text change,
    # so Test Generation never re-runs. Without a line here that step was silent
    # and a rebase looked like a stall.
    elif tool_name == "sync_css_test_cases":
        writer("   [Secondary Orchestrator] Updating style test expectations...")
    elif tool_name == "sync_hover_test_cases":
        writer("   [Secondary Orchestrator] Updating hover-style test expectations...")
    elif tool_name == "sync_text_test_cases":
        writer("   [Secondary Orchestrator] Updating text test expectations...")
    return handler(request)


# ==========================================================================
# System Prompt
# ==========================================================================
_secondary_orch_system_prompt = """
You are the Secondary Orchestrator for a B2C e-commerce UI generation system. Coordinate HTML, CSS, JS, TestGen, and TestExec to produce a tested, standards-compliant e-commerce page.

## Tools
- call_html_agent(query, intent, target_component, target_components, target_instance)
- call_css_agent(query, intent, target_component, target_components, target_instance)
- call_js_agent(query, intent, target_component, target_components, target_instance)
  - target_components: OPTIONAL list of component names to fix in ONE batched modify call; supported by all three agents, max 12. Prefer it over many single-component calls.
- call_test_gen_agent(query) — reads all 4 specs from state automatically
- call_test_exec_pipeline(query, modification_context)
- sync_css_test_cases(component)
- sync_text_test_cases(component, new_text)
- sync_hover_test_cases(component)

## Core control flow
Generation:
1. Run call_html_agent and wait for it to finish.
2. Then run call_css_agent, call_js_agent, and call_test_gen_agent in parallel. CSS and JS read the generated HTML as Step 0.
3. Only after all three complete, run call_test_exec_pipeline.

Never skip TestExec after any generation or modification.
session_id is issued by the application layer and arrives in state. Never create or read it; the call_*_agent tools pass it through in Python. If any tool reports the session id is missing, STOP and report it.
Act only on test_report content; never infer test outcomes. A call_*_agent ToolMessage saying the file "was NOT modified" or "DOES NOT EXIST" means the request was not applied. Never report or count such a call as a fix.

## Correction loop
If tests fail:
1. Read only the "Action required:" lines in test_report. Each already names the correct agent (css_agent / js_agent / html_agent) and target_component; trust that routing.
2. Group failing components by agent.
3. For each affected agent, make ONE call per round with target_components=[that agent's components], max 12. If more than 12 fail for an agent, fix the first 12; remaining failures surface after the next TestExec.
4. Each developer agent accepts only one call before the next call_test_exec_pipeline; a second call to the same agent is refused.
5. If html_agent and css_agent/js_agent are needed in the same round, run HTML first, then CSS and JS, because CSS and JS read the updated HTML.
6. End every round with call_test_exec_pipeline(modification_context=<summary of what was fixed>).
7. Repeat from the new test_report until pass or cap.

When a ToolMessage reports the modification_attempts cap is reached, stop the correction loop, report the partial result, and END. If call_test_exec_pipeline returns a REFUSED ToolMessage, stop immediately. Always provide modification_context when re-running TestExec after fixes.
Done only when test_report contains `ALL TESTS PASSED — no action required.`

## User-requested style or text changes
For colour, font, spacing, wording, or similar non-structural changes, call the relevant developer agent(s) with intent="modify".
The request ends with a "[Click-to-select target: ...]" line naming target_component and target_instance. Pass both to the developer agent unchanged, and use that target_component as `component` in every sync_*_test_cases call. Never pass an empty target_component and never guess another name.
After a style change:
- call sync_css_test_cases(component)
- if hover styling changed, ALSO call sync_hover_test_cases(component)
After a text change:
- call sync_text_test_cases(component, new_text)
Then run call_test_exec_pipeline with modification_context. Do NOT regenerate the full test suite.

## Unsupported structural changes
Adding or removing a component or changing interactions is not supported in this modify flow. Do not apply the request. Respond that structural changes go through the generation flow, where specs and tests are rebuilt, then END.
"""


# ==========================================================================
# Agent
# ==========================================================================
# parallel_tool_calls=False is a CORRECTNESS guard here, exactly as on the
# three developer agents. sync_css_test_cases and sync_hover_test_cases both
# write the decoration_specification channel back when the page has drifted
# from the spec (css touches baseStyles, hover touches the hover stateVariant).
# That channel is a plain LastValue with no reducer, so two of them landing in
# ONE parallel step -- exactly the SO-06 hover-modify path -- raises
# InvalidUpdateError at 'decoration_specification'. Serial is also MORE correct:
# the second sync reads the first's spec update and layers on top, so both
# edits survive, where a parallel last-wins would silently drop one.
_secondary_orch_model = ChatOpenAI(
    model="gpt-5.4",
    reasoning=_reasoning_for("secondary_orchestrator"),
    timeout=120,
    max_retries=2,
    parallel_tool_calls=True,
)

secondary_orch = create_agent(
    model=_secondary_orch_model,
    system_prompt=_secondary_orch_system_prompt,
    tools=[
        call_html_agent,
        call_css_agent,
        call_js_agent,
        call_test_gen_agent,
        call_test_exec_pipeline,
        sync_css_test_cases,
        sync_text_test_cases,
        sync_hover_test_cases,
    ],
    middleware=[deep_agent_progress, deep_agent_tool_progress],
    state_schema=SecondaryOrchState,
)


# Re-export this module's whole namespace, so the next module
# starts from it. Part of the mechanical split of ticket 04.
__all__ = [_n for _n in list(globals())
           if not (_n.startswith("__") and _n.endswith("__"))]
