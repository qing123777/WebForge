"""Ticket 18: run_live_suite.py runs the live suites on the webforge/ package.

    python -m pytest tests/test_live_runner.py

Before this ticket the runner executed the frozen fyp.ipynb top to bottom, so
a paid run tested the notebook's code, not the package. Now each live cell is
a file under tests/live_cells/ (copied once out of the notebook) and runs in
the package's flat namespace, like the ported unit cells.

Nothing here calls a model. The suites themselves are never executed: the
execution test runs a fake free suite built in a temp folder.

    LR-1  the plan for a suite: its live cells plus the scaffolding they
          name with `# Needs: cell N`, in cell order, all files under tests/
    LR-2  every name a live cell reads exists: in the package, in builtins,
          or in a file that runs before it
    LR-3  --list and --dry-run never open fyp.ipynb and never import webforge
    LR-4  a run executes on the package: a write reaches the package module,
          is undone afterwards, and the [proof] digest and transcript appear
"""
from __future__ import annotations

import ast
import json
import builtins
import pathlib
import subprocess
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
TESTS = ROOT / "tests"

import run_live_suite as live_runner  # noqa: E402


def _names(paths):
    return [f"{live_runner.cell_runner.cell_number(p):03d}" for p in paths]


# LR-1 ------------------------------------------------------------------------

def test_plan_html_runs_scaffolding_then_the_two_live_cells():
    plan = live_runner.plan(["html"])
    assert _names(plan.steps) == ["188", "189", "191"]
    assert _names(plan.targets) == ["189", "191"]
    assert all(TESTS in p.parents for p in plan.steps)


def test_plan_only_keeps_one_case_and_its_scaffolding_but_no_other_live_cell():
    plan = live_runner.plan(["so"], only="SO-02")
    # 392 is the SO scaffolding, 182 the shared Tier 2 helpers it needs. The
    # case's dependency on SO-01 (393) is the cell's own business: pulling a
    # paid cell in silently would change the bill.
    assert _names(plan.steps) == ["182", "392", "395"]
    assert _names(plan.targets) == ["395"]


def test_every_suite_resolves():
    for name in live_runner.SUITES:
        plan = live_runner.plan([name])
        assert plan.targets, name


# LR-2 ------------------------------------------------------------------------
# A live cell cannot be run here, so the next best check is static: every name
# it reads must exist when it runs. A name the package dropped (ticket 06
# deleted assert_*_is_current, which the SO and PO scaffolding called) would
# otherwise surface only after the user has paid for the cells before it.

def _defined_and_read(source: str):
    tree = ast.parse(source)
    defined, read = set(), set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            (read if isinstance(node.ctx, ast.Load) else defined).add(node.id)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            defined.add(node.name)
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            defined |= {(a.asname or a.name).split(".")[0] for a in node.names}
        elif isinstance(node, ast.arg):
            defined.add(node.arg)
        elif isinstance(node, ast.ExceptHandler) and node.name:
            defined.add(node.name)
        elif (isinstance(node, ast.Subscript) and isinstance(node.ctx, ast.Load)
              and isinstance(node.value, ast.Call)
              and getattr(node.value.func, "id", None) == "globals"
              and isinstance(node.slice, ast.Constant)):
            read.add(node.slice.value)       # globals()["name"]
    return defined, read


@pytest.fixture(scope="module")
def package_names():
    import webforge.primary_orchestrator  # noqa: F401
    from webforge.core import _flat_namespace
    return set(_flat_namespace()) | set(dir(builtins)) | {"__name__", "__file__"}


@pytest.mark.parametrize("suite", list(live_runner.SUITES))
def test_every_name_a_live_cell_reads_exists(suite, package_names):
    known = set(package_names)
    missing = {}
    for step in live_runner.plan([suite]).steps:
        defined, read = _defined_and_read(step.read_text(encoding="utf-8"))
        lost = sorted(read - defined - known)
        if lost:
            missing[step.name] = lost
        known |= defined
    assert not missing, f"names nothing defines before they are read: {missing}"


def test_no_live_cell_holds_a_hardcoded_pc_path():
    """The notebook cells pointed at C:/Users/Lenovo/Desktop/FYP. The package
    takes every path from webforge/config.py, and a live cell writing or
    reading another folder would check files the agents never wrote."""
    files = {step for name in live_runner.SUITES for step in live_runner.plan([name]).steps}
    hits = {p.name: n for p in files
            for n, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1)
            if "Desktop/FYP" in line and not line.lstrip().startswith("#")}
    assert not hits, f"hardcoded PC paths: {hits}"


# LR-3 ------------------------------------------------------------------------
# Run as the user runs it, in its own process, with an audit hook that logs
# every file opened. Planning must touch neither the notebook nor the package:
# importing webforge builds the models, and on a paid run that must happen
# only after .env is loaded.

_PROBE = """
import runpy, sys
opened = []
sys.addaudithook(lambda ev, args: opened.append(str(args[0])) if ev == "open" else None)
sys.argv = ["run_live_suite.py", *sys.argv[1:]]
try:
    runpy.run_path("run_live_suite.py", run_name="__main__")
except SystemExit as exc:
    code = exc.code
print("PROBE notebook-opened:", any(p.endswith("fyp.ipynb") for p in opened))
print("PROBE webforge-imported:", any(m.startswith("webforge") for m in sys.modules))
print("PROBE exit:", code)
"""


@pytest.mark.parametrize("args", [["--list"], ["html", "--dry-run"],
                                  ["so", "--only", "SO-02", "--dry-run"]])
def test_planning_reads_no_notebook_and_imports_no_package(args):
    proc = subprocess.run([sys.executable, "-c", _PROBE, *args], cwd=ROOT,
                          capture_output=True, text=True, encoding="utf-8",
                          timeout=120)
    out = proc.stdout
    assert "PROBE notebook-opened: False" in out, out[-2000:] + proc.stderr[-2000:]
    assert "PROBE webforge-imported: False" in out, out[-2000:]
    assert "PROBE exit: 0" in out, out[-2000:] + proc.stderr[-2000:]
    if "--dry-run" in args:
        assert "nothing was executed" in out
        assert "tests/live_cells/" in out


# LR-4 ------------------------------------------------------------------------
# The real suites cost money, so a fake free suite stands in: one scaffolding
# file and one suite file in a temp folder. The suite file swaps a package
# function the way the JS and CSS suites swap _read_preview_source.

_SCAFFOLD = """# NOTEBOOK-ONLY: scaffolding
def _fake_helper():
    return "helper"
"""

_SUITE = """# Needs: cell 900
# FAKE-SUITE-ANCHOR
import os
import webforge.css_agent as _css, webforge.js_agent as _js
assert _fake_helper() == "helper"
assert os.environ["OPENAI_API_KEY"] == "sk-DISABLED-free-suite-must-not-call-any-api"
assert os.environ["LANGSMITH_TRACING"] == "false"     # as under pytest
globals()["_read_preview_source"] = lambda sid, ext: "SWAPPED"
assert _css._read_preview_source("x", "html") == "SWAPPED"
assert _js._read_preview_source("x", "html") == "SWAPPED"
print("[proof] fake: the swap reached 2 package modules")
"""


@pytest.fixture
def fake_suite(tmp_path, monkeypatch):
    cells = tmp_path / "cells"
    cells.mkdir()
    (cells / "cell_900_scaffold.py").write_text(_SCAFFOLD, encoding="utf-8")
    (cells / "cell_901_fake.py").write_text(_SUITE, encoding="utf-8")
    monkeypatch.setattr(live_runner, "CELL_DIRS", [cells])
    monkeypatch.setattr(live_runner, "LOG_DIR", tmp_path / "logs")
    monkeypatch.setattr(live_runner, "SUITES", {"fake": {
        "cost": "free", "free": True, "anchors": ["FAKE-SUITE-ANCHOR"]}})
    for key in live_runner.cell_runner.API_KEYS:
        monkeypatch.setenv(key, "sk-pretend-this-is-real")
    for flag in ("LANGSMITH_TRACING", "LANGCHAIN_TRACING_V2"):
        monkeypatch.setenv(flag, "true")
    return cells


def test_a_run_executes_on_the_package_and_undoes_its_writes(fake_suite, capsys):
    import webforge.css_agent
    original = webforge.css_agent._read_preview_source
    assert live_runner.main(["fake", "--write-back"]) == 0
    out = capsys.readouterr().out
    assert webforge.css_agent._read_preview_source is original
    assert "1 [proof] line(s)" in out
    assert "[proof] fake: the swap reached 2 package modules" in out
    logs = live_runner.LOG_DIR
    (log,) = logs.glob("live_fake_*.log")
    assert "[proof] fake" in log.read_text(encoding="utf-8")
    (nb,) = logs.glob("live_fake_*.ipynb")
    cells = json.loads(nb.read_text(encoding="utf-8"))["cells"]
    assert [c["source"][0] for c in cells] == ["# NOTEBOOK-ONLY: scaffolding\n",
                                               "# Needs: cell 900\n"]


def test_a_failing_file_stops_the_run_and_still_undoes_its_writes(fake_suite, capsys):
    import webforge.css_agent
    original = webforge.css_agent._read_preview_source
    target = fake_suite / "cell_901_fake.py"
    target.write_text(target.read_text(encoding="utf-8").replace(
        'print("[proof]', 'raise RuntimeError("boom")\nprint("[proof]'), encoding="utf-8")
    assert live_runner.main(["fake"]) == 1
    out = capsys.readouterr().out
    assert "FAIL cell_901_fake.py  RuntimeError: boom" in out
    assert webforge.css_agent._read_preview_source is original
    (log,) = live_runner.LOG_DIR.glob("live_fake_*.log")
    assert "FAILED in cell_901_fake.py" in log.read_text(encoding="utf-8")


def test_a_package_that_fails_to_import_still_writes_a_transcript(fake_suite, monkeypatch,
                                                                 capsys):
    def broken():
        raise ImportError("webforge would not import")
    monkeypatch.setattr(live_runner.cell_runner, "CellSession", broken)
    assert live_runner.main(["fake"]) == 1
    assert "FAIL loading webforge/  ImportError" in capsys.readouterr().out
    (log,) = live_runner.LOG_DIR.glob("live_fake_*.log")
    assert "FAILED loading webforge/" in log.read_text(encoding="utf-8")


def test_an_anchor_that_matches_no_file_stops_with_exit_code_2(fake_suite, monkeypatch):
    monkeypatch.setitem(live_runner.SUITES["fake"], "anchors", ["NO-FILE-SAYS-THIS"])
    with pytest.raises(SystemExit) as stop:
        live_runner.plan(["fake"])
    assert stop.value.code == 2


def test_a_live_cell_may_not_need_another_live_cell(fake_suite):
    (fake_suite / "cell_900_scaffold.py").write_text("# LIVE-LLM: costs credits\n",
                                                     encoding="utf-8")
    with pytest.raises(SystemExit, match="a live cell"):
        live_runner.plan(["fake"])


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
