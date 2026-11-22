"""The four specification generators as plain functions (ticket 07).

    pytest tests/test_planning_generators.py   (or python tests/test_planning_generators.py)

Offline, no model calls. The structured chain each generator calls is the
model boundary, so it is the one thing swapped for a stand-in.

Seams:
  - generate_<stage>_specification(state) -> (spec, message): the plain
    function. Takes the planning state as a plain dict, no ToolRuntime.
  - <stage>_specification_generator.func(runtime): the @tool adapter, kept
    because tools.json in the baseline records its schema. It must return the
    same Command the generator returned before the split into function + adapter.
  - run_planning_pipeline: calls the plain functions; there is no runtime
    stand-in any more (its order/threading/stop cases live in notebook cell 452).
"""
import contextlib
import io
import pathlib
import sys
from types import SimpleNamespace

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import conftest  # noqa: E402,F401  (repo on sys.path, dead API keys) when run with python

with contextlib.redirect_stdout(io.StringIO()):
    import webforge
    import webforge.primary_orchestrator as wf

STAGES = ("layout", "components", "interactions", "decoration")

ONE_PAGE = {"pages": [
    {"pageName": "ListingPage", "pageType": "plp", "pageLayoutType": "grid",
     "responsive": True,
     "regions": [{"name": "grid", "ownedBy": "HTML", "layoutType": "grid"}]},
]}
TWO_PAGES = {"pages": ONE_PAGE["pages"] + [
    {"pageName": "CartPage", "pageType": "cart", "pageLayoutType": "flex-column",
     "responsive": True,
     "regions": [{"name": "items", "ownedBy": "HTML", "layoutType": "flex-column"}]},
]}


class _Chain:
    """Stands in for a structured chain: always answers with the same object."""

    def __init__(self, answer):
        self.answer = answer
        self.calls = 0

    def invoke(self, payload, config=None):
        self.calls += 1
        return self.answer


@contextlib.contextmanager
def _patched(name, value):
    """Bind a global in every package module that holds it, then restore."""
    real = getattr(wf, name)
    webforge.set_everywhere(name, value)
    try:
        yield value
    finally:
        webforge.set_everywhere(name, real)


def _gen(stage):
    return getattr(wf, f"generate_{stage}_specification")


# ── the plain functions ───────────────────────────────────────────────────

def test_layout_plain_function_takes_a_dict_and_returns_the_spec():
    state = {"input_query": "build a shoe shop", "design_schema": {}}
    with _patched("layout_specification_generator_tool", _Chain(ONE_PAGE)):
        spec, message = _gen("layout")(state)
    assert spec["pages"][0]["pageName"] == "ListingPage"
    assert spec["pages"][0]["regions"][0]["name"] == "grid"
    assert message == "Stored layout_specification."


def test_layout_plain_function_refuses_two_pages_and_says_why():
    state = {"input_query": "a shop and a cart page", "design_schema": {}}
    with _patched("layout_specification_generator_tool", _Chain(TWO_PAGES)) as chain:
        spec, message = _gen("layout")(state)
    assert spec is None
    assert message.startswith("FAILED to generate layout_specification.\n")
    assert "EXACTLY ONE" in message and "got 2" in message
    assert chain.calls == 3  # the generator's own retry, unchanged


def test_every_plain_function_reports_failure_without_a_spec():
    def _always_fails(**kwargs):
        return None, f"[{kwargs['stage']}] planner never returned a usable result"

    with _patched("_invoke_structured_with_retries", _always_fails):
        for stage in STAGES:
            spec, message = _gen(stage)({"input_query": "build a shop"})
            assert spec is None, stage
            assert message == (f"FAILED to generate {stage}_specification.\n"
                               f"[{stage}] planner never returned a usable result")


def test_plain_functions_do_not_mutate_the_state_they_read():
    state = {"input_query": "build a shoe shop", "design_schema": {}}
    before = dict(state)
    with _patched("layout_specification_generator_tool", _Chain(ONE_PAGE)):
        _gen("layout")(state)
    assert state == before


# ── the @tool adapters keep their old Command ─────────────────────────────

def test_tool_adapter_success_command_is_unchanged():
    runtime = SimpleNamespace(state={"input_query": "shoes", "design_schema": {}},
                              tool_call_id="tc-1")
    with _patched("layout_specification_generator_tool", _Chain(ONE_PAGE)):
        command = wf.layout_specification_generator.func(runtime)
    update = command.update
    assert set(update) == {"layout_specification", "messages"}
    assert update["layout_specification"]["pages"][0]["pageName"] == "ListingPage"
    (msg,) = update["messages"]
    assert msg.content == "Stored layout_specification."
    assert msg.tool_call_id == "tc-1"


def test_tool_adapter_failure_command_is_unchanged():
    def _always_fails(**kwargs):
        return None, "[x] nope"

    with _patched("_invoke_structured_with_retries", _always_fails):
        for stage in STAGES:
            tool = getattr(wf, f"{stage}_specification_generator")
            runtime = SimpleNamespace(state={}, tool_call_id=f"tc-{stage}")
            update = tool.func(runtime).update
            assert set(update) == {"messages"}, stage
            (msg,) = update["messages"]
            assert msg.content == f"FAILED to generate {stage}_specification.\n[x] nope"
            assert msg.tool_call_id == f"tc-{stage}"


# ── the pipeline needs no runtime stand-in ────────────────────────────────

def test_planning_runtime_stand_in_is_gone():
    assert not hasattr(wf, "_PlanningRuntime")
    import inspect
    assert "tool_call_id" not in inspect.signature(wf.run_planning_pipeline).parameters


def test_pipeline_error_names_the_stage_and_the_generator_message():
    def _ok(field):
        return lambda state: ({"pages": [{"pageName": "p1"}]}, f"Stored {field}.")

    def _fails(state):
        return None, "FAILED to generate components_specification.\n[reason] forced"

    with _patched("generate_layout_specification", _ok("layout_specification")), \
         _patched("generate_components_specification", _fails):
        state, error = wf.run_planning_pipeline("shoes", {})
    assert error == ("[planning] the components_specification stage produced no "
                     "output and the run stopped. FAILED to generate "
                     "components_specification.\n[reason] forced")
    assert state["layout_specification"] == {"pages": [{"pageName": "p1"}]}
    assert state["components_specification"] == {}


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__, "-q"]))
