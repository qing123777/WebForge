"""Ticket 05: the notebook's offline test cells, run by pytest.

    pytest tests/test_notebook_cells.py
    pytest tests/test_notebook_cells.py -k cell_153      one cell

Each file in tests/notebook_cells/ is one test cell copied out of the frozen
fyp.ipynb (by tools/port_notebook_tests.py, once). It is one pytest test here.

HOW A CELL RUNS

As the notebook did, in one flat namespace built from the package: see
tests/cell_runner.py (shared with run_live_suite.py since ticket 18). Each
test gets its own session, so the package names a cell replaced are put
back after it and no cell leaks a patch into the next one (in the notebook
they did leak). A `# Needs: cell N` line here may name only another unit
cell, never a live one under tests/live_cells/.

Where a ported cell differs from the notebook, a comment starting "Ticket 05"
says why (an intended change, a newer dependency, a hardcoded C:/Users path,
a stale test deleted). `grep -l "Ticket 05" tests/notebook_cells/` lists them.
The 11 rescued cells say so in their first lines.

Two checks besides the cells themselves:
  NB-COUNT  the ported cells hold at least as many asserts as the cells they
            replaced (the ticket's acceptance number, derived below).
  NB-FILES  every ported file names its source cell.
"""
from __future__ import annotations

import ast
import contextlib
import io
import pathlib
import re
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from cell_runner import NOTEBOOK_CELLS as CELLS, CellSession, run_order  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parent.parent


def _cell_files() -> list[pathlib.Path]:
    return sorted(CELLS.glob("cell_*.py"))


def _assert_count(path: pathlib.Path) -> int:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return sum(isinstance(n, ast.Assert) for n in ast.walk(tree))


def run_cell(path: pathlib.Path) -> str:
    """Run one ported cell as the notebook did. Returns what it printed.
    A `# Needs` line may name only another unit cell, never a live one."""
    out = io.StringIO()
    before = _preview_files()
    try:
        with CellSession() as session, contextlib.redirect_stdout(out):
            for step in run_order(path, dirs=[CELLS]):
                session.run(step)
    finally:
        for left in _preview_files() - before:
            left.unlink(missing_ok=True)
    return out.getvalue()


def _preview_files() -> set:
    """Files in the real preview folder. Several cells (the Tier 2 suites, the
    live-browser pipeline) write preview_<sid>.* there, as the notebook did;
    whatever a cell adds is deleted after it, so a test run leaves the folder
    as it found it."""
    from webforge.config import PREVIEW_DIR
    return set(PREVIEW_DIR.glob("*")) if PREVIEW_DIR.is_dir() else set()


@pytest.mark.parametrize("path", _cell_files(), ids=lambda p: p.stem)
def test_cell(path):
    run_cell(path)


# NB-COUNT. The number the port must reach, from the frozen notebook (counted
# with ast, one per assert statement, as _assert_count does):
#   99 cells the export marks as unit tests and that hold an assert   1,704
#   11 cells marked LIVE-LLM or NOTEBOOK-ONLY that make no model call
#      (184 243 300 329 360 364 368 371, 347 349 374), rescued          449
#   deleted as stale or vacuous: cells 166 213 271 (the store_*_diff
#      tools, bound to no agent) and 347's two asserts pinning the
#      removed image feature's wording                                  -57
#                                                                     -----
#                                                                     2,096
# The four "Diagnostic: SO-0x" cells are also marked as tests but hold no
# assert (print-only), so they are not ported and add nothing.
REPLACED_ASSERTS = 2096


def test_ported_cells_keep_every_assert():
    got = sum(_assert_count(p) for p in _cell_files())
    assert got >= REPLACED_ASSERTS, (
        f"the ported cells hold {got} asserts, fewer than the "
        f"{REPLACED_ASSERTS} they replaced")


_HEADER = re.compile(r"^# Ported from fyp\.ipynb cell \d+", re.M)


def test_every_ported_file_names_its_cell():
    files = _cell_files()
    assert files, "tests/notebook_cells/ holds no ported cell"
    missing = [p.name for p in files
               if not _HEADER.search(p.read_text(encoding="utf-8")[:400])]
    assert not missing, f"no 'Ported from fyp.ipynb cell N' header: {missing}"


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
