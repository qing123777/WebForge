"""WebForge: the multi-agent system, split out of the flat fyp.py (ticket 04).

LOAD_ORDER is the one list of the system's modules. Each one starts from the
namespace of the one before it (``from webforge.<previous> import *``), so the
last one, primary_orchestrator, holds every name the flat file had.

SUBMODULES are the modules of a package below the load order (ticket 11: the
Test Execution pipeline, webforge/test_execution/). They import no agent
module; a LOAD_ORDER module (test_exec) star-imports the package to chain it in.
"""
import sys as _sys

LOAD_ORDER = (
    "core", "context_agent", "specs", "dev_shared", "dev_agent", "html_agent", "js_agent",
    "css_agent", "test_gen_agent", "test_exec", "secondary_orchestrator",
    "primary_orchestrator",
)

SUBMODULES = tuple(f"test_execution.{m}" for m in (
    "state", "browser", "css_values", "actions", "sweeps", "report", "suite"))


def set_everywhere(name: str, value) -> list:
    """Bind `name` to `value` in every loaded module that holds the name.

    One flat namespace had one binding; the split copied it into every module
    after the one that defined it. A caller that patches a global (the baseline
    capture, tests/test_spec_base.py; the fyp.py shim until ticket 15) uses this so every
    module's functions see the new value, as before. Returns the module names.
    """
    reached = []
    for short in (*LOAD_ORDER, *SUBMODULES):
        mod = _sys.modules.get(f"{__name__}.{short}")
        if mod is not None and name in vars(mod):
            setattr(mod, name, value)
            reached.append(short)
    return reached
