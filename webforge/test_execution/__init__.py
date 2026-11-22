"""test_execution: the Test Execution pipeline (Playwright, no LLM), as its own
package (ticket 11).

It runs the structured test cases Test Generation wrote, sweeps the page as it
ships, and writes the report the Secondary Orchestrator routes. It imports no
agent module: only libraries and webforge.config. webforge.test_exec puts it
into the load order.

Modules, lowest first (webforge.SUBMODULES lists them): state, browser, css_values, actions, sweeps (the
page-health sweeps and PAGE_SWEEPS, their registry), report, suite
(run_test_suite).
"""
from __future__ import annotations

from webforge.test_execution.state import *  # noqa: E402,F401,F403
from webforge.test_execution.browser import *  # noqa: E402,F401,F403
from webforge.test_execution.css_values import *  # noqa: E402,F401,F403
from webforge.test_execution.actions import *  # noqa: E402,F401,F403
from webforge.test_execution.sweeps import *  # noqa: E402,F401,F403
from webforge.test_execution.report import *  # noqa: E402,F401,F403
from webforge.test_execution.suite import *  # noqa: E402,F401,F403

__all__ = [_n for _n in list(globals())
           if not (_n.startswith("__") and _n.endswith("__"))
           and _n not in ("state", "browser", "css_values", "actions",
                          "sweeps", "report", "suite")]
