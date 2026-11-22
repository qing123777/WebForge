"""The backend's entry point: what LangGraph and the UI bridge load (ticket 15).

    langgraph.json   "agent": "./webforge/entry.py:graph"   (loaded by file path)
    bridge.py        from webforge.entry import graph, _spec_model

It replaced the fyp.py re-export shim. It builds nothing itself: importing it
imports webforge.primary_orchestrator, which loads every module in LOAD_ORDER
and builds the agents and the compiled graph. Building calls no model.

It sits outside LOAD_ORDER on purpose (tests/test_package_split.py,
OUTSIDE_CHAIN): it starts from no module's namespace and re-exports two names.
Code that needs the whole flat namespace imports webforge.primary_orchestrator;
code that patches a global uses webforge.set_everywhere(name, value).
"""
import pathlib as _pathlib
import sys as _sys

# LangGraph loads this file by its path, not as webforge.entry, so the repo
# root may not be on sys.path yet. The fyp.py shim did the same. This is the
# one path not taken from webforge.config: config cannot be imported until the
# root is on sys.path.
_ROOT = str(_pathlib.Path(__file__).resolve().parent.parent)
if _ROOT not in _sys.path:
    _sys.path.insert(0, _ROOT)

from webforge.primary_orchestrator import _spec_model, graph  # noqa: E402

__all__ = ["graph", "_spec_model"]
