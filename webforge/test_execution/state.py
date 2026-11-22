"""The Test Execution tool's state schema."""
from __future__ import annotations

from langchain.agents.middleware import AgentState

# ==========================================================================
# Memory & State
# ==========================================================================
class TestExecState(AgentState):
    test_cases:           list
    preview_url:          str
    test_report:          str
    session_id:           str
    modification_context: str = ""


# Every name this module defines or imports, for the package's __init__ and
# from there for webforge.test_exec, which re-exports it into the load order.
__all__ = [_n for _n in list(globals())
           if not (_n.startswith("__") and _n.endswith("__"))]
