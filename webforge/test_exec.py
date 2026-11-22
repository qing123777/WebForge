"""test_exec: the Test Execution pipeline's place in the load order.

The pipeline itself (Playwright, no LLM: browser helpers, the page-health
sweeps and their registry, run_test_suite) lives in the webforge/test_execution/
package since ticket 11. This module only chains it into the load order, so
every later module still sees each of its names.
"""
from __future__ import annotations

from webforge.test_gen_agent import *  # noqa: F401,F403
from webforge.test_execution import *  # noqa: F401,F403


# Re-export this module's whole namespace, so the next module
# starts from it. Part of the mechanical split of ticket 04.
__all__ = [_n for _n in list(globals())
           if not (_n.startswith("__") and _n.endswith("__"))]
