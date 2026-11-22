"""Run cells copied out of the frozen fyp.ipynb on the webforge/ package.

Shared by tests/test_notebook_cells.py (the offline unit cells, ticket 05) and
run_live_suite.py (the paid live suites, ticket 18), so both run a cell the
same way.

HOW A CELL RUNS

In the notebook every cell shared one flat namespace, so a cell that wrote
`run_eslint = fake` changed what every tool saw. The package split that
namespace into modules. So a cell runs with:

  - globals: a fresh copy of the package's flat namespace (what the last
    module re-exports, `core._flat_namespace()`), so a cell sees every name;
  - writes: a write to a name (top level, `globals()[name] = v`, or
    `global name` in a function the cell defines) is also made in each package
    module that holds the name, as the flat file had one binding. The old
    values are put back when the session closes.
  - `# Needs: cell N` in a file's header runs cell N first, in the same
    namespace, for a helper that an earlier notebook cell defined. N is looked
    up in every folder of CELL_DIRS.

Importing this module imports nothing from the package; `CellSession` does,
when it opens. run_live_suite.py relies on that: it loads `.env` first, so
the models the package builds at import get the real key.
"""
from __future__ import annotations

import ast
import contextlib
import io
import os
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
NOTEBOOK_CELLS = ROOT / "tests" / "notebook_cells"
LIVE_CELLS = ROOT / "tests" / "live_cells"
CELL_DIRS = [NOTEBOOK_CELLS, LIVE_CELLS]

# Every key a run could spend with. pytest (conftest.py) and a free live suite
# replace them all with a dead string, so a slip fails with a rejected key
# instead of a charge, and switch tracing off.
API_KEYS = ("OPENAI_API_KEY", "AZURE_OPENAI_API_KEY", "ANTHROPIC_API_KEY",
            "GOOGLE_API_KEY", "TAVILY_API_KEY", "LANGSMITH_API_KEY",
            "LANGCHAIN_API_KEY")


def disable_api_keys(dead: str) -> None:
    for key in API_KEYS:
        os.environ[key] = dead
    os.environ["LANGCHAIN_TRACING_V2"] = "false"
    os.environ["LANGSMITH_TRACING"] = "false"


def _package():
    with contextlib.redirect_stdout(io.StringIO()):
        import webforge
        import webforge.primary_orchestrator  # noqa: F401  (loads every module)
        from webforge.core import _flat_namespace
    return webforge, _flat_namespace


class ForwardingGlobals(dict):
    """The cell's globals. A write by name at the cell's top level, or through
    `globals()[name] = value`, also goes to every package module that holds
    the name; the first old value per module is kept for undo.

    One write cannot be seen here: `global x; x = v` inside a function the
    cell defines stores straight into the dict, past __setitem__.
    `forward_global_writes` rewrites those before the cell runs."""

    def __init__(self, namespace: dict, webforge) -> None:
        super().__init__(namespace)
        self._wf = webforge
        self.undo: dict[str, dict[str, object]] = {}

    def __setitem__(self, name, value):
        super().__setitem__(name, value)
        for short in (*self._wf.LOAD_ORDER, *self._wf.SUBMODULES):
            mod = sys.modules.get(f"webforge.{short}")
            if mod is None or name not in vars(mod):
                continue
            old = vars(mod)[name]
            if old is value:
                continue
            self.undo.setdefault(name, {}).setdefault(short, old)
            setattr(mod, name, value)

    def restore(self) -> None:
        for name, per_module in self.undo.items():
            for short, old in per_module.items():
                setattr(sys.modules[f"webforge.{short}"], name, old)


class _ForwardGlobalWrites(ast.NodeTransformer):
    """After `x = v` in a function that declared `global x`, add
    `globals()["x"] = x`, so the write passes through __setitem__ and reaches
    the package. Only names the package holds are touched.

    The cell's top level counts as declaring every name that any of its
    functions declares global: CPython then compiles the top-level write as
    STORE_GLOBAL too, which skips __setitem__ the same way."""

    def __init__(self, package_names) -> None:
        self._package = package_names
        self._declared: list[set] = []

    def visit_Module(self, node):
        self._declared.append({n for stmt in ast.walk(node) if isinstance(stmt, ast.Global)
                               for n in stmt.names if n in self._package})
        self.generic_visit(node)
        return node

    def _visit_function(self, node):
        declared = {n for stmt in ast.walk(node) if isinstance(stmt, ast.Global)
                    for n in stmt.names if n in self._package}
        self._declared.append(declared)
        self.generic_visit(node)
        self._declared.pop()
        return node

    visit_FunctionDef = visit_AsyncFunctionDef = _visit_function

    def _forwarded(self, node, targets):
        names = sorted({t.id for tgt in targets for t in ast.walk(tgt)
                        if isinstance(t, ast.Name) and t.id in self._declared[-1]})
        if not names:
            return node
        extra = [ast.parse(f"globals()[{n!r}] = {n}").body[0] for n in names]
        for stmt in extra:
            ast.copy_location(stmt, node)
            ast.fix_missing_locations(stmt)
        return [node, *extra]

    def visit_Assign(self, node):
        return self._forwarded(node, node.targets)

    def visit_AugAssign(self, node):
        return self._forwarded(node, [node.target])


def forward_global_writes(source: str, package_names) -> ast.Module:
    tree = ast.parse(source)
    return ast.fix_missing_locations(_ForwardGlobalWrites(package_names).visit(tree))


_NEEDS = re.compile(r"^# Needs: cell (\d+)", re.M)


def cell_number(path: pathlib.Path) -> int:
    return int(path.name.split("_")[1])


def cell_path(index: int, dirs=None) -> pathlib.Path:
    """The one ported file for notebook cell `index`, in any of `dirs`."""
    found = sorted(p for d in (dirs or CELL_DIRS) for p in d.glob(f"cell_{index:03d}_*.py"))
    # Raised, not asserted: run_live_suite.py relies on it, and `python -O`
    # strips asserts.
    if not found:
        raise LookupError(f"'# Needs: cell {index}' names no ported cell")
    if len(found) > 1:
        raise LookupError(f"'# Needs: cell {index}' names {len(found)} ported "
                          f"cells: {[p.name for p in found]}")
    return found[0]


def needs(path: pathlib.Path) -> list[int]:
    return [int(n) for n in _NEEDS.findall(path.read_text(encoding="utf-8"))]


def run_order(path: pathlib.Path, seen=None, dirs=None) -> list[pathlib.Path]:
    """The cells to run, in order: every `# Needs: cell N` first (depth
    first), then the cell itself. A notebook cell could use a helper an
    earlier cell defined; this is how a ported one says so."""
    seen = set() if seen is None else seen
    order = []
    for index in needs(path):
        dep = cell_path(index, dirs)
        if dep not in seen:
            seen.add(dep)
            order += run_order(dep, seen, dirs)
    return order + [path]


class CellSession:
    """One shared namespace, built from the package, that cells run in one
    after another, as notebook cells shared a kernel. `close()` puts back
    every package name a cell replaced and the working directory."""

    def __init__(self) -> None:
        self.webforge, flat = _package()
        self.namespace = flat()
        self.globals = ForwardingGlobals(self.namespace, self.webforge)
        dict.__setitem__(self.globals, "__name__", "__main__")
        dict.__setitem__(self.globals, "__builtins__", __builtins__)
        self._cwd = os.getcwd()
        os.chdir(ROOT)

    def run(self, path: pathlib.Path) -> None:
        """Run one file. Its output goes to whatever sys.stdout is now."""
        tree = forward_global_writes(path.read_text(encoding="utf-8"), set(self.namespace))
        exec(compile(tree, str(path), "exec"), self.globals)

    def close(self) -> None:
        os.chdir(self._cwd)
        self.globals.restore()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
