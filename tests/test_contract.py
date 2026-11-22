"""Ticket 12: webforge.contract owns the typed contract between UI and agents.

    python tests/test_contract.py        (or pytest)

No model call. Seams under test (the module's public interface):

  CT-1  the modify marker: format, parse (both the agent-side search and the
        UI-side anchored split), and the JS expression the Select panel runs.
        Expected strings are the literals the panel produced before ticket 12.
  CT-2  importing webforge.contract loads no agent code (ticket 13 makes the
        UI import nothing agent-related).
  CT-3  the progress event: its kinds, and how a progress line is classified
        (stage, warning, low-level detail), on lines a real run streams.
"""
from __future__ import annotations

import json
import pathlib
import shutil
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from webforge import contract  # noqa: E402

# What the Select panel wrote before ticket 12, character for character.
MARKER = ("[intent=modify | target_component=add-to-cart-button "
          "| target_instance=2] make this button green")


# ---------------------------------------------------------------- CT-1
def test_format_modify_marker_matches_the_panel_literal():
    assert contract.format_modify_marker(
        "add-to-cart-button", 2, "make this button green") == MARKER


def test_modify_marker_fields_reads_the_marker():
    assert contract.modify_marker_fields(MARKER) == {
        "intent": "modify", "target_component": "add-to-cart-button",
        "target_instance": "2"}


def test_modify_marker_fields_is_tolerant_and_empty_without_marker():
    loose = "  [ INTENT = Modify |Target_Component= hero-banner ] bigger"
    assert contract.modify_marker_fields(loose) == {
        "intent": "modify", "target_component": "hero-banner"}
    assert contract.modify_marker_fields("make the hero bigger") == {}
    assert contract.modify_marker_fields("") == {}
    assert contract.modify_marker_fields(None) == {}


def test_split_modify_message_separates_marker_from_request():
    assert contract.split_modify_message(MARKER) == (
        "[intent=modify | target_component=add-to-cart-button | target_instance=2]",
        "make this button green")
    assert contract.split_modify_message(
        "[intent=modify | target_component=x]\nline one\nline two") == (
        "[intent=modify | target_component=x]", "line one\nline two")


def test_split_modify_message_only_accepts_a_leading_marker():
    assert contract.split_modify_message("make it green") is None
    assert contract.split_modify_message(
        "please [intent=modify | target_component=x] do it") is None


def test_modify_marker_js_builds_the_same_string_in_a_browser_engine():
    js = contract.modify_marker_js("info.selector", "info.instance", "request")
    node = shutil.which("node")
    if node is None:  # pragma: no cover -- node ships with the lint toolchain
        import pytest
        pytest.skip("node is not installed")
    prog = ("var info = {selector: 'add-to-cart-button', instance: 2};"
            "var request = 'make this button green';"
            f"process.stdout.write(JSON.stringify({js}));")
    out = subprocess.run([node, "-e", prog], capture_output=True, text=True, check=True)
    assert json.loads(out.stdout) == MARKER


# ---------------------------------------------------------------- CT-2
def test_importing_the_contract_loads_no_agent_code():
    probe = (
        "import sys, json\n"
        "from webforge import contract\n"
        "heavy = sorted(m for m in sys.modules if m.split('.')[0] in "
        "('langchain', 'langchain_core', 'langgraph', 'deepagents', 'openai')"
        " or (m.startswith('webforge.') and m not in ('webforge.contract',)))\n"
        "print(json.dumps(heavy))\n")
    out = subprocess.run([sys.executable, "-c", probe], cwd=ROOT,
                         capture_output=True, text=True, check=True)
    assert json.loads(out.stdout) == []


# ---------------------------------------------------------------- CT-3
def test_progress_event_kinds_are_the_wire_strings():
    assert (contract.ANSWER, contract.ANSWER_BOUNDARY, contract.PROCESSING) == (
        "answer", "answer_boundary", "processing")


def test_progress_event_is_a_plain_kind_text_pair():
    ev = contract.ProgressEvent(contract.PROCESSING, "[Orchestrator] Processing request...")
    kind, text = ev
    assert (kind, text) == ("processing", "[Orchestrator] Processing request...")
    assert ev == ("processing", "[Orchestrator] Processing request...")


def test_stage_label_maps_a_line_to_the_phase_it_is_about():
    cases = {
        "[Orchestrator] Processing request...": "Primary Orchestrator",
        "[Orchestrator] Invoking Context Agent...": "Context Engineering Agent",
        "[Orchestrator] Invoking System Design & Planning Chain...":
            "System Planning and Design",
        "[Orchestrator] Invoking Secondary Orchestrator...": "Secondary Orchestrator",
        "   [CSS Agent] Lint cap reached, saving best effort...": "CSS Agent",
        "[Test Execution Pipeline] Running Playwright test suite...":
            "Test Execution Pipeline",
        "[Test Gen] Saved 12 cases": "Test Generation Agent",
        "no actor here": None,
    }
    assert {line: contract.stage_label(line) for line in cases} == cases


def test_stage_order_lists_the_nine_stages_and_the_parallel_three():
    assert contract.STAGE_ORDER == (
        "Primary Orchestrator", "Context Engineering Agent",
        "System Planning and Design", "Secondary Orchestrator", "HTML Agent",
        "CSS Agent", "JS Agent", "Test Generation Agent", "Test Execution Pipeline")
    assert contract.PARALLEL_STAGES == ("CSS Agent", "JS Agent", "Test Generation Agent")


def test_is_warning_flags_a_given_up_fix_in_any_case():
    assert contract.is_warning("   [HTML Agent] Lint cap reached, saving best effort...")
    assert contract.is_warning("   [JS Agent] Patch cap reached, leaving this component as it is...")
    assert contract.is_warning("BEST EFFORT")
    assert not contract.is_warning("[HTML Agent] Lint clean, saved")


def test_is_detail_step_drops_low_level_tool_detail():
    assert contract.is_detail_step("[Test Gen] SUITE COMPLETE")
    assert contract.is_detail_step("[Test Gen] Saved 4 cases (2 left)")
    assert contract.is_detail_step("Coverage check failed")
    assert not contract.is_detail_step("[Orchestrator] Processing request...")
    # Case-sensitive, as the UI has always matched it.
    assert not contract.is_detail_step("suite complete")


class _FakeGraph:
    """Just enough of a compiled graph for StreamSession: one scripted stream."""

    def __init__(self, chunks):
        self._chunks = chunks

    def stream(self, *_a, **_k):
        return iter(self._chunks)

    def get_state(self, config=None):
        return type("Snap", (), {"values": {}})()

    def update_state(self, *_a, **_k):
        pass


def test_bridge_streams_progress_events(monkeypatch):
    import bridge
    from langchain_core.messages import AIMessageChunk

    graph = _FakeGraph([
        ("custom", "  [Orchestrator] Processing request...  "),
        ("custom", {"type": "indent"}),
        ("messages", (AIMessageChunk(content="Hel", id="m1"), {})),
        ("messages", (AIMessageChunk(content="lo", id="m1"), {})),
    ])
    monkeypatch.setattr(bridge, "_get_graph", lambda: graph)
    events = list(bridge.StreamSession("hi", "t1", {}, None).stream_events())
    assert events == [
        ("processing", "[Orchestrator] Processing request..."),
        ("answer_boundary", ""),
        ("answer", "Hel"),
        ("answer", "lo"),
    ]
    assert all(isinstance(e, contract.ProgressEvent) for e in events)


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-q"]))
