"""The spend-approval hook: paid calls ask, free calls pass through."""
import importlib.util
import json
import pathlib
import subprocess
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
HOOK = ROOT / ".claude" / "hooks" / "paid_gate.py"
_spec = importlib.util.spec_from_file_location("paid_gate", HOOK)
gate = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(gate)


def _shell(cmd, tool="Bash"):
    return {"tool_name": tool, "tool_input": {"command": cmd}}


@pytest.mark.parametrize("cmd", [
    "python run_live_suite.py po08",
    "python run_live_suite.py po08 --yes",
    "python run_live_suite.py css --only CSS-GM-01",
    "python run_live_suite.py po08 --dry-run; python run_live_suite.py po08 --yes",
    "python run_live_suite.py po08 --dry-run && python run_live_suite.py po08",
    "python tests/live_cells/cell_453_po_08_generate_full_brief_end.py",
    'python -c "from webforge.entry import graph; graph.invoke({})"',
    "python -m streamlit run stream_lit.py --server.port 8501",
    "streamlit run stream_lit.py",
])
def test_paid_shell_commands_ask(cmd):
    assert gate.classify(_shell(cmd))
    assert gate.classify(_shell(cmd, "PowerShell"))


@pytest.mark.parametrize("cmd", [
    "python run_live_suite.py po08 --dry-run",
    "python run_live_suite.py --list",
    "python -m pytest -q",
    "python -m pytest -q tests/test_live_runner.py",
    "python tools/trace_cost.py abc --latency",
    "python baseline/compare.py baseline/snapshots/before x",
    "python -m streamlit run tools/mock_ui.py --server.port 8599",
    "ls tests/live_cells",
    "git status",
])
def test_free_shell_commands_pass(cmd):
    assert gate.classify(_shell(cmd)) is None


def test_live_preview_asks_mock_preview_passes():
    start = "mcp__Claude_Browser__preview_start"
    assert gate.classify({"tool_name": start, "tool_input": {"name": "webforge-live"}})
    assert gate.classify({"tool_name": start, "tool_input": {"name": "webforge-mock-ui"}}) is None


def _click():
    return {"tool_name": "mcp__Claude_Browser__computer",
            "tool_input": {"action": "left_click", "coordinate": [1, 1]}}


def test_browser_clicks_ask_only_while_live_app_is_up():
    assert gate.classify(_click(), live_app_up=lambda: True)
    assert gate.classify(_click(), live_app_up=lambda: False) is None


def test_browser_reads_stay_free_while_live_app_is_up():
    shot = {"tool_name": "mcp__Claude_Browser__computer", "tool_input": {"action": "screenshot"}}
    page = {"tool_name": "mcp__Claude_Browser__read_page", "tool_input": {}}
    assert gate.classify(shot, live_app_up=lambda: True) is None
    assert gate.classify(page, live_app_up=lambda: True) is None


def test_browser_batch_with_typing_asks():
    batch = {"tool_name": "mcp__Claude_Browser__browser_batch", "tool_input": {"actions": [
        {"name": "computer", "input": {"action": "screenshot"}},
        {"name": "computer", "input": {"action": "type", "text": "hi"}}]}}
    assert gate.classify(batch, live_app_up=lambda: True)


def test_hook_prints_ask_json_for_paid_and_nothing_for_free():
    def run(event):
        return subprocess.run([sys.executable, str(HOOK)], input=json.dumps(event),
                              capture_output=True, text=True, encoding="utf-8", timeout=30)
    paid = run(_shell("python run_live_suite.py po08"))
    assert paid.returncode == 0
    out = json.loads(paid.stdout)["hookSpecificOutput"]
    assert out["permissionDecision"] == "ask" and "CREDITS" in out["permissionDecisionReason"]
    free = run(_shell("git status"))
    assert free.returncode == 0 and free.stdout.strip() == ""
