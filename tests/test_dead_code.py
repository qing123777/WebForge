"""Ticket 06: dead code is gone, and `_pretty` is a function everywhere.

    pytest tests/test_dead_code.py        (or python tests/test_dead_code.py)

Offline, no model calls.

  DC-1  `_pretty` is the specs debug printer (a function) in every package
        module. Before ticket 06 a module-level string in html_agent
        overwrote it there and in every module after it.
  DC-2  none of the dead-on-arrival names in docs/refactor_findings.md
        section A exists any more, in any package module or
        bridge.StreamSession.
  DC-3  _specs_prompt_block emits compact JSON. This check used to run at
        import time in html_agent (the block that held the `_pretty` string);
        it lives here now.

Until ticket 15, DC-1 and DC-2 also ran on the fyp shim. It re-exported
primary_orchestrator's namespace, which is in MODULES, so dropping it lost
no check.
"""
import contextlib
import importlib
import io
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import conftest  # noqa: E402,F401  (repo on sys.path, dead API keys) when run with python

import pytest  # noqa: E402

with contextlib.redirect_stdout(io.StringIO()):
    import bridge  # noqa: E402
    from webforge import LOAD_ORDER  # noqa: E402
    from webforge.html_agent import _specs_prompt_block  # noqa: E402
    import webforge.specs as specs  # noqa: E402

MODULES = [importlib.import_module(f"webforge.{m}") for m in LOAD_ORDER]

DEAD = [
    "_bound_tool_args", "_batch_binding", "_bt_unbound",
    "assert_orchestrator_is_current", "assert_secondary_orch_is_current",
    "_assert_tools_current", "_PO_TOOLS_AT_BUILD", "_SO_TOOLS_AT_BUILD",
    "to_do_list_middleware",
    "_PREVIEW_ROOT_DIR",
    "_PSAMPLE",  # the deleted proof block's sample; its generic helpers
                 # (_compact, _block, _pct) are not listed, a later module may reuse them
]


@pytest.mark.parametrize("mod", MODULES, ids=lambda m: m.__name__)
def test_pretty_is_the_function_everywhere(mod):
    if not hasattr(mod, "_pretty"):
        pytest.skip("module precedes specs")
    assert mod._pretty is specs._pretty and callable(mod._pretty), type(mod._pretty)


@pytest.mark.parametrize("mod", MODULES, ids=lambda m: m.__name__)
def test_no_dead_names(mod):
    left = [n for n in DEAD if n in vars(mod)]
    assert not left, f"{mod.__name__} still holds {left}"


def test_stream_session_has_no_legacy_paths():
    assert not hasattr(bridge.StreamSession, "__iter__")
    assert not hasattr(bridge, "send_message")


def test_specs_prompt_block_is_compact():
    spec = {"regions": [{"id": "hero", "children": [{"id": "cta", "label": "Buy"}]}]}
    block = _specs_prompt_block({"components_specification": spec},
                                ["components_specification"])
    assert '{"regions":[{"id":"hero","children":[{"id":"cta","label":"Buy"}]}]}' in block
    assert "\n  " not in block
    assert json.dumps(spec, indent=2) not in block


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
