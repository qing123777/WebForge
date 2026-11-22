"""Ticket 15: the fyp.py re-export shim is deleted and stays deleted.

    python -m pytest tests/test_no_fyp.py     (or python tests/test_no_fyp.py)

Offline: reads source files only, imports nothing from the package.

  NF-1  the checker below finds each way a file can load `fyp` (planted).
  NF-2  fyp.py does not exist.
  NF-3  no Python file outside docs/ loads `fyp`: an import, `from fyp import`,
        importlib.import_module("fyp"), __import__("fyp"), or a sys.modules
        entry named "fyp" (how the mock UI backend used to fake it). The frozen
        fyp.ipynb is not a .py file, so it is not read.
  NF-4  no config file (langgraph.json and the like) names fyp.py.

To read the system's flat namespace, import webforge.primary_orchestrator. To
patch a global everywhere, as `fyp.X = v` did, call webforge.set_everywhere.
"""
import ast
import os
import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent

# Folders not read: history docs (ticket 16 owns them), dependencies, caches,
# generated output. .claude/worktrees/ holds other checkouts of this repo.
_SKIP_DIRS = {"docs", "node_modules", ".git", "__pycache__", ".lint_tmp", "static",
              ".venv", "venv"}


def _files(*suffixes):
    for dirpath, dirnames, filenames in os.walk(ROOT):
        rel_dir = pathlib.Path(dirpath).relative_to(ROOT)
        dirnames[:] = [d for d in dirnames if d not in _SKIP_DIRS
                       and (rel_dir / d).parts != (".claude", "worktrees")]
        for f in filenames:
            if pathlib.Path(f).suffix in suffixes:
                yield pathlib.Path(dirpath) / f, rel_dir / f


def fyp_imports(source: str) -> list:
    """Every place this Python source loads the fyp module, as (what, line)."""
    found = []
    for n in ast.walk(ast.parse(source)):
        if isinstance(n, ast.Import):
            found += [(f"import {a.name}", n.lineno) for a in n.names
                      if a.name == "fyp" or a.name.startswith("fyp.")]
        elif isinstance(n, ast.ImportFrom) and n.level == 0 and n.module \
                and (n.module == "fyp" or n.module.startswith("fyp.")):
            found.append((f"from {n.module} import", n.lineno))
        elif isinstance(n, ast.Call) and n.args and isinstance(n.args[0], ast.Constant) \
                and n.args[0].value == "fyp":
            name = getattr(n.func, "attr", getattr(n.func, "id", ""))
            if name in ("import_module", "__import__") \
                    or ast.unparse(n.func) == "sys.modules.get":
                found.append((f"{name}('fyp')", n.lineno))
        elif isinstance(n, ast.Call) and len(n.args) >= 2 \
                and isinstance(n.args[1], ast.Constant) and n.args[1].value == "fyp" \
                and ast.unparse(n.args[0]) == "sys.modules":
            found.append(("sys.modules entry 'fyp'", n.lineno))
        elif isinstance(n, ast.Subscript) and ast.unparse(n.value) == "sys.modules" \
                and isinstance(n.slice, ast.Constant) and n.slice.value == "fyp":
            found.append(("sys.modules['fyp']", n.lineno))
    return found


# NF-1 ------------------------------------------------------------------------

def test_the_checker_catches_each_way_to_load_fyp():
    planted = ("import fyp\nfrom fyp import graph\nimport importlib\n"
               "importlib.import_module('fyp')\n__import__('fyp')\n"
               "import sys\nsys.modules['fyp'] = 1\n"
               "monkeypatch.setitem(sys.modules, 'fyp', None)\n"
               "sys.modules.get('fyp')\n")
    assert [line for _, line in fyp_imports(planted)] == [1, 2, 4, 5, 7, 8, 9]
    assert fyp_imports("import fyplike\nx = 'fyp.ipynb'\nimport webforge.entry\n"
                       "settings.get('fyp')\n") == []


# NF-2 ------------------------------------------------------------------------

def test_the_shim_stays_deleted():
    assert not (ROOT / "fyp.py").exists(), "fyp.py is back; the code lives in webforge/"


# NF-3 ------------------------------------------------------------------------

def test_no_file_loads_fyp():
    bad, read = [], 0
    for p, rel in _files(".py"):
        try:
            hits = fyp_imports(p.read_text(encoding="utf-8"))
        except (SyntaxError, UnicodeDecodeError) as exc:
            # A file this check cannot read is a file it cannot vouch for.
            bad.append(f"{rel.as_posix()}: unreadable ({type(exc).__name__})")
            continue
        read += 1
        bad += [f"{rel.as_posix()}:{line} {what}" for what, line in hits]
    assert read > 100, f"only {read} .py files read; the walk is skipping the repo"
    assert not bad, ("these load the deleted fyp shim; use webforge.primary_orchestrator "
                     "(read) or webforge.set_everywhere (write) instead:\n" + "\n".join(bad))


# NF-4 ------------------------------------------------------------------------

def test_no_config_names_fyp_py():
    bad = [rel.as_posix()
           for p, rel in _files(".json", ".toml", ".ini", ".cfg", ".sh", ".yaml", ".yml")
           if rel.parts[:2] != ("baseline", "snapshots")
           and "fyp.py" in p.read_text(encoding="utf-8", errors="replace")]
    assert not bad, f"config still names fyp.py: {bad}"


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
