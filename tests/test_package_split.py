"""Ticket 04: the webforge/ package behaves like the flat fyp.py it came from.

    python tests/test_package_split.py

No model call (dead API keys are set before the import). Checks:

  PK-1  every module of the split imports, and the last one, primary_orchestrator,
        holds every name any LOAD_ORDER module defines: it is the flat
        namespace. (Until ticket 15: the fyp shim exposed every name of the
        last module as the same object. The shim is gone.)
  PK-2  no function reads a global its own module lacks. In the flat file every
        name was visible at call time; split, a name defined in a LATER module
        would be a NameError waiting for the first call. Found with symtable.
  PK-3  no function reads a global whose object differs from the one the flat
        file would give it at call time (the final namespace). The one
        exception the split made, _pretty (tools/split_fyp.py, case 2), is gone:
        ticket 06 deleted the string that overwrote it.
  PK-4  webforge.set_everywhere("X", v) reaches every module that holds X, as
        one namespace did. (Until ticket 15 the write was fyp.X = v, which the
        shim forwarded to set_everywhere.)
  PK-5  fyp.py is gone (ticket 15; until then: it is only the shim, it defines
        no agent). tests/test_no_fyp.py checks that nothing imports it.
  PK-6  no code calls globals() itself, except core._flat_namespace and the
        __all__ footers. symtable cannot see a name looked up by string, so a
        globals()["x"] for an x defined in a later module passes PK-2 and then
        silently finds nothing; every such lookup goes through
        core._flat_namespace(), the namespace the flat file had.
  PK-7  every .py file under webforge/ is a module these checks cover: in
        LOAD_ORDER or in SUBMODULES (ticket 11's test_execution package), so
        code moved into a new file cannot escape PK-2..PK-6. The files in
        OUTSIDE_CHAIN are not in the chain on purpose, each for its reason.

PK-2, PK-3, PK-4 and PK-6 run over LOAD_ORDER and SUBMODULES alike.

Exits non-zero on any failure.
"""
from __future__ import annotations

import ast
import builtins
import contextlib
import importlib
import io
import os
import pathlib
import symtable
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

for _k in ("OPENAI_API_KEY", "TAVILY_API_KEY", "LANGSMITH_API_KEY", "LANGCHAIN_API_KEY"):
    os.environ[_k] = "sk-dead-package-split-test"
os.environ["LANGSMITH_TRACING"] = "false"

import webforge  # noqa: E402  -- only LOAD_ORDER; the modules load in main()

MODULES = [*webforge.LOAD_ORDER, *webforge.SUBMODULES]

# Names whose call-time object is allowed to differ from the flat file's,
# with the reason. Keep this list short and explained.
ALLOWED_DIVERGENCE: dict = {}

# webforge files deliberately outside LOAD_ORDER: they start from no other
# module's namespace and hold no agent code, so the split checks do not apply.
OUTSIDE_CHAIN = {
    "config": "paths only; every module imports it (ticket 02)",
    "contract": "the UI-agent wire contract; the UI imports it without loading "
                "agent code (ticket 12, checked by tests/test_contract.py CT-2)",
    "entry": "the backend's entry point for langgraph.json and bridge; it only "
             "re-exports two names of primary_orchestrator (ticket 15, checked "
             "by tests/test_entry_point.py)",
}

failures: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + (f"  ({detail})" if detail else ""))
    if not ok:
        failures.append(name)


def module_path(name: str) -> pathlib.Path:
    """webforge/<name>.py; a dotted name is a file inside a sub-package."""
    return ROOT / "webforge" / (name.replace(".", "/") + ".py")


def global_reads(source: str, filename: str) -> set[str]:
    """Every name a function or method in this source reads as a module global."""
    out: set[str] = set()

    def walk(table):
        for child in table.get_children():
            if child.get_type() != "module":
                for sym in child.get_symbols():
                    if sym.is_referenced() and sym.is_global():
                        out.add(sym.get_name())
            walk(child)

    walk(symtable.symtable(source, filename, "exec"))
    return out


def raw_globals_calls(source: str) -> list[int]:
    """Lines that call globals() outside _flat_namespace and the __all__ footer."""
    tree = ast.parse(source)
    allowed: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "_flat_namespace":
            allowed |= set(range(node.lineno, node.end_lineno + 1))
        if isinstance(node, ast.Assign) and any(
                isinstance(t, ast.Name) and t.id == "__all__" for t in node.targets):
            allowed |= set(range(node.lineno, node.end_lineno + 1))
    return sorted(n.lineno for n in ast.walk(tree)
                  if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
                  and n.func.id == "globals" and n.lineno not in allowed)


def main() -> int:
    # PK-1
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            mods = {n: importlib.import_module(f"webforge.{n}") for n in MODULES}
    except Exception as e:  # noqa: BLE001 -- report, then fail
        check("PK-1 the package imports", False, f"{type(e).__name__}: {e}")
        return 1
    last = vars(mods["primary_orchestrator"])
    # Ticket 15: this was "the fyp shim exposes every name of the last module".
    # The shim is gone; what it re-exported is the last module itself, so the
    # check is now that the star-import chain carries every name to it.
    defined = {k for n in webforge.LOAD_ORDER for k in vars(mods[n])
               if not (k.startswith("__") and k.endswith("__"))}
    lost = sorted(defined - set(last))
    check("PK-1 primary_orchestrator holds every name the load order defines",
          not lost, f"{len(defined) - len(lost)}/{len(defined)}" + (f": {lost[:10]}" if lost else ""))

    # PK-2 and PK-3
    builtin = set(dir(builtins))
    missing, diverged, reads = [], [], 0
    for n, m in mods.items():
        path = module_path(n)
        for g in sorted(global_reads(path.read_text(encoding="utf-8"), str(path))):
            reads += 1
            if g in builtin and g not in vars(m):
                continue
            if g not in vars(m):
                missing.append(f"{n}.{g}")
            elif g in last and vars(m)[g] is not last[g] and (n, g) not in ALLOWED_DIVERGENCE:
                diverged.append(f"{n}.{g}")
    check("PK-2 no function reads a global its module lacks", not missing, ", ".join(missing))
    check("PK-3 every global a function reads is the flat file's object",
          not diverged, ", ".join(diverged))
    for (n, g), why in ALLOWED_DIVERGENCE.items():
        differs = vars(mods[n]).get(g) is not last.get(g)
        check(f"PK-3 allowed divergence {n}.{g} is still real",
              differs, why)

    # PK-4
    holders = [n for n, m in mods.items() if "_PREVIEW_ROOT" in vars(m)]
    old, sentinel = last["_PREVIEW_ROOT"], object()
    try:
        webforge.set_everywhere("_PREVIEW_ROOT", sentinel)
        reached = [n for n in holders if vars(mods[n])["_PREVIEW_ROOT"] is sentinel]
    finally:
        webforge.set_everywhere("_PREVIEW_ROOT", old)
    restored = all(vars(mods[n])["_PREVIEW_ROOT"] is old for n in holders)
    check("PK-4 set_everywhere('_PREVIEW_ROOT', x) reaches every module holding it",
          bool(holders) and reached == holders and restored, f"{len(reached)}/{len(holders)}")

    # PK-6
    raw, routed = [], 0
    for n in mods:
        text = module_path(n).read_text(encoding="utf-8")
        raw += [f"{n}:{line}" for line in raw_globals_calls(text)]
        routed += sum(isinstance(c, ast.Call) and getattr(c.func, "id", "") == "_flat_namespace"
                      for c in ast.walk(ast.parse(text)))
    check("PK-6 every globals() lookup goes through _flat_namespace", not raw, ", ".join(raw))

    # PK-7
    files = {".".join(p.relative_to(ROOT / "webforge").with_suffix("").parts)
             for p in (ROOT / "webforge").rglob("*.py")}
    files = {f.removesuffix(".__init__") for f in files} - {"__init__", *OUTSIDE_CHAIN}
    covered = set(MODULES) | {m.rsplit(".", 1)[0] for m in MODULES if "." in m}
    check("PK-7 every webforge file is a checked module", files <= covered,
          ", ".join(sorted(files - covered)))

    # PK-5 (ticket 15: was "fyp.py is only the shim"; tests/test_no_fyp.py
    # also fails if any file imports fyp again)
    check("PK-5 fyp.py is gone", not (ROOT / "fyp.py").exists())

    print(f"[proof] split: {len(mods)} modules, {reads} global reads by functions checked; "
          f"{len(missing)} would be NameError, {len(diverged)} see a different object "
          f"(+{len(ALLOWED_DIVERGENCE)} allowed); {len(raw)} raw globals() calls, "
          f"{routed} lookups routed through _flat_namespace (each would see only its own "
          f"module without it); {len(defined)} names carried to primary_orchestrator; "
          f"set_everywhere('_PREVIEW_ROOT') "
          f"reached {len(reached)}/{len(holders)} modules. fyp.py: deleted (was about "
          f"18,300 lines, then a 33-line shim until ticket 15).")
    print(f"{'FAILED' if failures else 'OK'}: {len(failures)} failure(s)")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
