"""Ticket 15: the backend loads from the package, not from the fyp.py shim.

    python -m pytest tests/test_entry_point.py     (or python tests/test_entry_point.py)

Offline, no model calls: building the graph calls no model, and the child
process gets the same dead API keys as conftest.py.

  EP-1  langgraph.json's graph entry is a file under webforge/, and loading
        that file BY PATH, as LangGraph does, from a cwd outside the repo and
        with no PYTHONPATH, gives the package's compiled graph (the same object
        as webforge.primary_orchestrator.graph), and never imports `fyp`.
  EP-2  webforge.entry exposes what bridge loads, graph and _spec_model, as
        the package's own objects.

tests/test_no_fyp.py checks that the shim stays deleted.
"""
import json
import os
import pathlib
import subprocess
import sys
import tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import conftest  # noqa: E402,F401  (repo on sys.path, dead API keys) when run with python

import pytest  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parent.parent


def _graph_entry():
    spec = json.loads((ROOT / "langgraph.json").read_text(encoding="utf-8"))["graphs"]["agent"]
    path, _, attr = spec.rpartition(":")
    return path, attr


# EP-1 ------------------------------------------------------------------------

_LOAD_BY_PATH = r'''
import importlib.util, json, sys
path, attr = sys.argv[1], sys.argv[2]
spec = importlib.util.spec_from_file_location("langgraph_graph_entry", path)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
g = getattr(mod, attr)
po = sys.modules["webforge.primary_orchestrator"]
print(json.dumps({
    "type": type(g).__name__,
    "same_as_package": g is po.graph,
    "fyp_imported": "fyp" in sys.modules,
    "has_invoke": callable(getattr(g, "invoke", None)),
}))
'''


def test_langgraph_json_entry_loads_by_path():
    path, attr = _graph_entry()
    file = (ROOT / path).resolve()
    assert file.is_file(), f"langgraph.json points at a missing file: {path}"
    assert file.is_relative_to(ROOT / "webforge"), f"entry is outside the package: {path}"
    # os.environ already holds conftest's dead keys; the child inherits them.
    env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
    with tempfile.TemporaryDirectory() as foreign:
        out = subprocess.run([sys.executable, "-c", _LOAD_BY_PATH, str(file), attr],
                             cwd=foreign, env=env, capture_output=True, text=True,
                             timeout=300)
    assert out.returncode == 0, out.stderr[-3000:]
    res = json.loads(out.stdout.strip().splitlines()[-1])
    assert res == {"type": "CompiledStateGraph", "same_as_package": True,
                   "fyp_imported": False, "has_invoke": True}, res


# EP-2 ------------------------------------------------------------------------

def test_entry_exposes_the_package_graph_and_label_model():
    import contextlib
    import io
    with contextlib.redirect_stdout(io.StringIO()):
        import webforge.entry as entry
        import webforge.primary_orchestrator as po
    assert entry.__all__ == ["graph", "_spec_model"]
    assert entry.graph is po.graph and entry._spec_model is po._spec_model


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
