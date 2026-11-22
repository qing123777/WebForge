"""Test Execution pipeline: unit tests that need no browser.

    python tests/test_test_exec.py        (or pytest tests/test_test_exec.py)

Offline, no model calls.

  TE-1  _ensure_reachable still fails open when opening the drawer times out,
        and now RETURNS the error it swallowed. Before ticket 05 a bare
        `except Exception: pass` dropped it, which is why the cold-start flake
        in notebook cell 338 never said what timed out.
  TE-2  it returns None when it had nothing to do or opened the drawer.
  TE-3  the page-health sweeps run from one registry (ticket 11), in the order
        run_test_suite called them one by one before, none skipped, and only
        _sweep_dropped_shipped_id gets the shipped HTML.
  TE-4  run_page_sweeps calls each registered sweep once, in registry order,
        and returns their findings concatenated in that order.
  TE-5  webforge.test_execution is its own package: importing it in a fresh
        process loads no module of the load order (no agent, no LLM client),
        and gives the same run_test_suite the load order re-exports. Its
        __init__ re-exports every name of every module webforge.SUBMODULES
        lists (the two lists are kept by hand; this keeps them equal).
"""
import contextlib
import io
import sys
import pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import conftest  # noqa: E402,F401  (repo on sys.path, dead API keys) when run with python
from unittest.mock import MagicMock

import pytest

with contextlib.redirect_stdout(io.StringIO()):
    from webforge.test_exec import _ensure_reachable


def _page(visible=False, opener="#opener", click_error=None):
    page = MagicMock()
    loc = page.locator.return_value.first
    loc.count.return_value = 1
    loc.is_visible.return_value = visible
    page.evaluate.return_value = opener
    if click_error is not None:
        page.click.side_effect = click_error
    return page


def test_a_failed_open_is_returned_not_raised():
    boom = TimeoutError("Timeout 2000ms exceeded clicking #opener")
    page = _page(click_error=boom)
    assert _ensure_reachable(page, "#inside-btn") is boom
    page.click.assert_called_once_with("#opener", timeout=2000)


def test_nothing_to_report_when_it_works_or_has_nothing_to_do():
    assert _ensure_reachable(_page(visible=True), "#visible-btn") is None
    assert _ensure_reachable(_page(opener=None), "#lonely-btn") is None
    assert _ensure_reachable(_page(), "#inside-btn") is None


# The order run_test_suite called the sweeps in before ticket 11, copied from
# its `auto = (...)` expression at commit f34f3a0. A literal, not derived from
# the code, so a reordered or dropped registration goes red.
SWEEPS_BEFORE_TICKET_11 = [
    "_sweep_resources", "_sweep_dead_selectors", "_sweep_geometry",
    "_sweep_grid_targets", "_sweep_bulleted_nav", "_sweep_hidden_not_honored",
    "_sweep_row_container_unstyled", "_sweep_drawer_not_overlay",
    "_sweep_filter_value_dead", "_sweep_dropped_shipped_id",
]


def test_the_registry_holds_every_sweep_in_the_old_order():
    from webforge.test_execution import PAGE_SWEEPS
    assert [s.fn.__name__ for s in PAGE_SWEEPS] == SWEEPS_BEFORE_TICKET_11
    assert [s.fn.__name__ for s in PAGE_SWEEPS if s.needs_html_source] == [
        "_sweep_dropped_shipped_id"]
    print(f"[proof] sweep registry: {len(PAGE_SWEEPS)} sweeps registered, "
          f"order equal to the {len(SWEEPS_BEFORE_TICKET_11)} calls run_test_suite "
          f"spelled out one by one before ticket 11.")


def test_run_page_sweeps_runs_each_once_in_order(monkeypatch):
    import webforge.test_execution.sweeps as sw
    calls = []

    def fake(name):
        def fn(page, *rest):
            calls.append((name, page, rest))
            return [f"{name}-finding"]
        fn.__name__ = name
        return fn

    fakes = tuple(sw.Sweep(fake(n), needs_html_source=(n == "c"))
                  for n in ("a", "b", "c"))
    monkeypatch.setattr(sw, "PAGE_SWEEPS", fakes)
    page = object()
    assert sw.run_page_sweeps(page, "<html>") == ["a-finding", "b-finding", "c-finding"]
    assert calls == [("a", page, ()), ("b", page, ()), ("c", page, ("<html>",))]


_ALONE = r'''
import json, sys
import webforge, webforge.test_execution as te
loaded = [m for m in webforge.LOAD_ORDER if f"webforge.{m}" in sys.modules]
import importlib
subs = [n for m in webforge.SUBMODULES
        for n in importlib.import_module(f"webforge.{m}").__all__ if not hasattr(te, n)]
print(json.dumps({"loaded": loaded, "tool": te.run_test_suite.name,
                  "openai": "langchain_openai" in sys.modules,
                  "not_reexported": subs}))
'''


def test_the_package_imports_without_the_agents():
    import json
    import subprocess
    root = pathlib.Path(__file__).resolve().parent.parent
    out = subprocess.run([sys.executable, "-c", _ALONE], cwd=root, capture_output=True,
                         text=True, check=True, timeout=120)
    got = json.loads(out.stdout.strip().splitlines()[-1])
    assert got == {"loaded": [], "tool": "run_test_suite", "openai": False,
                   "not_reexported": []}, got
    import webforge.test_exec
    import webforge.test_execution
    assert webforge.test_exec.run_test_suite is webforge.test_execution.run_test_suite
    print(f"[proof] own package: importing webforge.test_execution loads "
          f"{len(got['loaded'])} of the {len(webforge.LOAD_ORDER)} load-order modules "
          f"(before ticket 11 the pipeline sat in test_exec, after all 8 before it).")


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
