"""Ticket 05: the machinery that ports and runs the notebook's test cells.

    pytest tests/test_notebook_port.py        (or python tests/test_notebook_port.py)

Offline, no model calls. tests/test_notebook_cells.py runs 109 cells through
this machinery (tests/cell_runner.py since ticket 18, shared with
run_live_suite.py); these tests pin the machinery itself, so a bug in it shows as
a failure here rather than as cells that pass for the wrong reason.

  NP-1  a cell's top-level write reaches every package module holding the
        name, and is undone after the cell.
  NP-2  `global x; x = v` inside a cell's function reaches the package too,
        and so does the top-level write CPython then compiles as STORE_GLOBAL.
  NP-3  a write to a name the package does not hold stays in the cell.
  NP-4  `# Needs: cell N` runs cell N first, once, depth first.
  NP-6  a write reaches the test_execution package's modules too (ticket 11):
        run_test_suite reads _get_browser from webforge.test_execution.suite.
  (NP-5 tested the one-off port tool, tools/port_notebook_tests.py, which was
  deleted with the notebook it read.)
"""
import contextlib
import io
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import conftest  # noqa: E402,F401  (repo on sys.path, dead API keys) when run with python

import pytest  # noqa: E402

import cell_runner  # noqa: E402
import test_notebook_cells as runner  # noqa: E402

with contextlib.redirect_stdout(io.StringIO()):
    import webforge.html_agent as html_mod  # noqa: E402
    import webforge.test_exec as te_mod  # noqa: E402


def _cell(tmp_path, name, source):
    path = tmp_path / name
    path.write_text(source, encoding="utf-8")
    return path


def test_top_level_write_reaches_every_module_and_is_undone(tmp_path, monkeypatch):
    real = te_mod.get_stream_writer
    seen = {}
    cell = _cell(tmp_path, "cell_901_w.py",
                 "get_stream_writer = 'patched'\n"
                 "import webforge.html_agent as h, webforge.test_exec as t\n"
                 "SEEN['html'], SEEN['te'] = h.get_stream_writer, t.get_stream_writer\n")
    monkeypatch.setattr(runner, "CELLS", tmp_path)
    monkeypatch.setitem(cell_runner._package()[1](), "SEEN", seen)
    runner.run_cell(cell)
    assert seen == {"html": "patched", "te": "patched"}
    assert te_mod.get_stream_writer is real and html_mod.get_stream_writer is real


def test_global_statement_writes_reach_the_package(tmp_path, monkeypatch):
    real = te_mod.get_stream_writer
    seen = {}
    cell = _cell(tmp_path, "cell_902_g.py",
                 "import webforge.test_exec as t\n"
                 "def patch():\n"
                 "    global get_stream_writer\n"
                 "    get_stream_writer = 'in-function'\n"
                 "patch()\n"
                 "SEEN['function'] = t.get_stream_writer\n"
                 "get_stream_writer = 'top-level'\n"     # compiled as STORE_GLOBAL
                 "SEEN['top'] = t.get_stream_writer\n")
    monkeypatch.setattr(runner, "CELLS", tmp_path)
    monkeypatch.setitem(cell_runner._package()[1](), "SEEN", seen)
    runner.run_cell(cell)
    assert seen == {"function": "in-function", "top": "top-level"}
    assert te_mod.get_stream_writer is real


def test_a_cell_only_name_stays_in_the_cell(tmp_path, monkeypatch):
    cell = _cell(tmp_path, "cell_903_l.py", "_np3_only_here = 1\n")
    monkeypatch.setattr(runner, "CELLS", tmp_path)
    runner.run_cell(cell)
    assert not any(hasattr(sys.modules[f"webforge.{m}"], "_np3_only_here")
                   for m in ("core", "test_exec", "primary_orchestrator"))


def test_a_write_reaches_the_test_execution_package(tmp_path, monkeypatch):
    import webforge.test_execution.browser as browser
    import webforge.test_execution.suite as suite
    real = suite._get_browser
    seen = {}
    cell = _cell(tmp_path, "cell_904_p.py",
                 "_get_browser = 'patched'\n"
                 "import webforge.test_execution.suite as s\n"
                 "import webforge.test_execution.browser as b\n"
                 "SEEN['suite'], SEEN['browser'] = s._get_browser, b._get_browser\n")
    monkeypatch.setattr(runner, "CELLS", tmp_path)
    monkeypatch.setitem(cell_runner._package()[1](), "SEEN", seen)
    runner.run_cell(cell)
    assert seen == {"suite": "patched", "browser": "patched"}
    assert suite._get_browser is real and browser._get_browser is real


def test_needs_runs_the_named_cells_first_once(tmp_path, monkeypatch):
    a = _cell(tmp_path, "cell_010_a.py", "# x\n")
    b = _cell(tmp_path, "cell_020_b.py", "# Needs: cell 10\n")
    c = _cell(tmp_path, "cell_030_c.py", "# Needs: cell 20\n# Needs: cell 10\n")
    assert cell_runner.run_order(c, dirs=[tmp_path]) == [a, b, c]
    missing = _cell(tmp_path, "cell_040_d.py", "# Needs: cell 99\n")
    with pytest.raises(LookupError, match="names no ported cell"):
        cell_runner.run_order(missing, dirs=[tmp_path])


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
