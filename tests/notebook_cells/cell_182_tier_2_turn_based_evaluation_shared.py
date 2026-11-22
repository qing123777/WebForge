# Ported from fyp.ipynb cell 182 (ticket 05). The notebook is frozen;
# edit this file. Run by tests/test_notebook_cells.py.
# ═══════════════════════════════════════════════════════════════════════════
# TIER 2 — TURN-BASED EVALUATION: shared scripted-model harness
#
# Supervisor's evaluation frame: tool-level -> turn-based -> task-based.
# This cell provides the machinery the three turn-based suites below share.
#
# Turn-based tests exercise a WHOLE SUB-AGENT (tool sequencing, self-correction
# loop, guard feedback, fallback) but must NOT call the real model API. The
# model's replies are pre-scripted, so every run is deterministic and free.
#
# TWO REASONS A STOCK LANGCHAIN FAKE MODEL CANNOT BE USED DIRECTLY
#   1. FakeChatModel / FakeListChatModel / FakeMessagesListChatModel /
#      GenericFakeChatModel all inherit BaseChatModel.bind_tools, whose body is
#      `raise NotImplementedError`. create_agent binds tools to the model, so a
#      stock fake cannot drive a tool-calling agent at all.
#   2. FakeMessagesListChatModel CYCLES: when its scripted responses run out it
#      wraps back to response 0 instead of stopping. A runaway agent loop would
#      repeat forever and still look like a pass.
# ScriptedChatModel below fixes both.
# ═══════════════════════════════════════════════════════════════════════════
import json as _sj, uuid as _suuid
from typing import Any, Sequence

from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
from langchain_core.messages import AIMessage, ToolMessage as _LCToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult


class ScriptedChatModel(FakeMessagesListChatModel):
    """A fake chat model that can actually drive a tool-calling agent.

    `responses` is the exact sequence of model turns the agent is expected to
    take. Asking for one more turn than was scripted is an error, not a wrap-
    around — that is what turns "the agent looped when it shouldn't have" into
    a visible failure instead of a silent pass.
    """
    turns_used: int = 0

    def bind_tools(self, tools: Sequence[Any], **kwargs: Any):
        # Tool schemas are irrelevant: every reply is pre-scripted.
        return self

    def _generate(self, messages, stop=None, run_manager=None, **kwargs) -> ChatResult:
        if self.turns_used >= len(self.responses):
            raise AssertionError(
                f"Agent requested model turn #{self.turns_used + 1} but only "
                f"{len(self.responses)} were scripted — unexpected extra loop."
            )
        msg = self.responses[self.turns_used]
        self.turns_used += 1
        return ChatResult(generations=[ChatGeneration(message=msg)])


def _tc(name: str, args: dict | None = None) -> AIMessage:
    """One scripted model turn that calls exactly one tool."""
    return AIMessage(content="", tool_calls=[{
        "name": name, "args": args or {},
        "id": f"tc_{name}_{_suuid.uuid4().hex[:6]}",
    }])


def _done(text: str = "Finished.") -> AIMessage:
    """The final scripted model turn: plain text, no tool call -> loop ends."""
    return AIMessage(content=text)


# Ticket 08: the drift guard asks the PRODUCTION agent object which tools it
# holds. It used to regex the `<agent> = create_agent(tools=[...])` call out of
# the source (ticket 05: the package's; before that, the frozen notebook's at a
# hardcoded C:/Users/Lenovo/... path). Since ticket 08 the JS agent is built by
# webforge.dev_agent.build_dev_agent, which a text match on create_agent cannot
# see, and the live object is the truth either way.
def _production_tool_names(agent_var: str) -> set:
    """The tools the PRODUCTION agent registers, without the ones its
    FilesystemMiddleware adds (ls, read_file, ...).

    Drift guard: if a tool is later added to a developer agent without updating
    its turn-based suite, the suite must fail loudly rather than quietly
    testing an agent that no longer resembles production.
    """
    agent = _flat_namespace()[agent_var]
    held = set(agent.nodes["tools"].bound.tools_by_name)
    fs = {t.name for t in FilesystemMiddleware(backend=_preview_backend).tools}
    return held - fs


def _assert_state_fields(state_cls, required: list, agent_label: str) -> None:
    """Check a state schema declares the channels a suite is about to write.

    Until 2026-08-10 every agent's schema was called `State`, so the name bound
    when this suite ran could belong to a DIFFERENT agent if cells were executed
    out of order -- and LangGraph drops a write to an undeclared channel without
    raising. The schemas now have distinct names (HtmlState, JsState, CssState,
    TestGenState, TestExecState, SecondaryOrchState), so that particular
    confusion is gone and a stale binding is a NameError instead.

    This stays as a field-level check: a schema can be the right one and still
    be missing a field the suite depends on.
    """
    ann = getattr(state_cls, "__annotations__", {})
    missing = [f for f in required if f not in ann]
    assert not missing, (
        f"{getattr(state_cls, '__name__', state_cls)} does not declare {missing}, "
        f"which the {agent_label} suite writes. Re-run that agent's state-schema "
        f"cell, then re-run this suite."
    )


def _scripted_agent(responses, tools, middleware, state_schema, agent_var=None):
    """Rebuild a developer agent identically to production but model-scripted."""
    if agent_var:
        prod = _production_tool_names(agent_var)
        mine = {getattr(t, "name", getattr(t, "__name__", str(t))) for t in tools}
        assert prod == mine, (
            f"TOOL DRIFT for {agent_var}: production registers {sorted(prod)} but this "
            f"suite rebuilds with {sorted(mine)}. Update the suite's tool list."
        )
    model = ScriptedChatModel(responses=responses)
    agent = create_agent(model=model, tools=tools,
                         middleware=middleware, state_schema=state_schema)
    return model, agent


def _run_scripted(agent, payload, session_id):
    """Stream a scripted agent to completion.

    Returns (state, tool_calls, tool_messages):
      state         — non-message state fields the agent produced
      tool_calls    — ordered list of tool names the agent invoked
      tool_messages — ordered list of ToolMessage contents (the feedback the
                      agent received; scenario 3 asserts against these)
    """
    state, tool_calls, tool_messages = {}, [], []
    for chunk in agent.stream(
        payload,
        stream_mode=["updates", "custom"],
        version="v2",
        config={"configurable": {"session_id": session_id}},
    ):
        chunk_type, data = (
            chunk if isinstance(chunk, tuple)
            else (chunk.get("type"), chunk.get("data"))
        )
        if chunk_type != "updates" or not isinstance(data, dict):
            continue
        for _step, up in data.items():
            if not isinstance(up, dict):
                continue
            for k, v in up.items():
                if k == "messages":
                    for m in (v or []):
                        for call in (getattr(m, "tool_calls", None) or []):
                            tool_calls.append(call["name"])
                        if isinstance(m, _LCToolMessage):
                            tool_messages.append(str(m.content))
                else:
                    state[k] = v
    return state, tool_calls, tool_messages


print("Tier-2 scripted harness ready: ScriptedChatModel, _tc, _done, "
      "_scripted_agent, _run_scripted, _assert_state_fields")
