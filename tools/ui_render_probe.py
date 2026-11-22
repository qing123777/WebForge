"""Prove a stream_lit.py change leaves the HTML/JS/CSS it sends unchanged.

    python tools/ui_render_probe.py <git revision>      e.g. HEAD, 16acf37

Compares stream_lit.py at that revision with the working tree. It finds every
``components.html(...)`` and ``st.markdown(...)`` call, evaluates its first
argument the way the page builds it (literal, f-string, or ui_assets call), and
prints IDENTICAL or DIFFERENT per call. Names the text depends on (a session id,
a URL) get the same stand-in value on both sides, so a field that moved still
compares equal. A call that needs a real function to build its text is SKIPPED.

Written for ticket 14, which moved about 3,700 lines of JS and CSS out of
stream_lit.py into ui_assets/ and had to show the page gets the same bytes.
No model call, no Streamlit, no browser. Exits 1 on any DIFFERENT or on a
different number of calls.
"""
from __future__ import annotations

import ast
import difflib
import hashlib
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

CALLS = ("components.html", "st.markdown")


class _Stand(dict):
    """Every unknown name reads as a fixed string naming it."""

    def __missing__(self, name):
        return f"<{name}>"


def rendered_calls(src: str) -> list[tuple[str, str | None]]:
    """(where, text) for every call in CALLS, in file order. ``where`` is the
    enclosing function (or "module") and the call's index inside it; text is
    None when the argument cannot be built from stand-in values."""
    import ui_assets
    tree = ast.parse(src)
    owner: dict[int, str] = {}
    for fn in ast.walk(tree):
        if isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for node in ast.walk(fn):
                owner.setdefault(id(node), fn.name)
    out: list[tuple[str, str | None]] = []
    seen: dict[str, int] = {}
    calls = [n for n in ast.walk(tree) if isinstance(n, ast.Call) and n.args
             and ast.unparse(n.func) in CALLS]
    for call in sorted(calls, key=lambda n: (n.lineno, n.col_offset)):
        place = owner.get(id(call), "module")
        seen[place] = seen.get(place, 0) + 1
        where = f"{place}#{seen[place]}"
        try:
            text = eval(compile(ast.Expression(call.args[0]), where, "eval"),
                        {"__builtins__": __builtins__}, _Stand(ui_assets=ui_assets))
        except Exception:
            text = None
        out.append((where, text if isinstance(text, str) else None))
    return out


def compare(old_src: str, new_src: str) -> tuple[list[str], int]:
    """Report lines and the number of differences (DIFFERENT, ADDED or
    REMOVED calls). Calls are paired by their text, not their position, so a
    call added or removed elsewhere does not shift every later one."""
    old, new = rendered_calls(old_src), rendered_calls(new_src)
    key = lambda calls: [f"{w.split('#')[0]}\0{t}" for w, t in calls]  # noqa: E731
    lines, bad = [], 0
    matcher = difflib.SequenceMatcher(a=key(old), b=key(new), autojunk=False)
    for op, i1, i2, j1, j2 in matcher.get_opcodes():
        if op == "equal":
            for where, text in new[j1:j2]:
                if text is None:
                    lines.append(f"SKIPPED    {where}")
                else:
                    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()[:12]
                    lines.append(f"IDENTICAL  {where}: {len(text):,} chars, sha256 {digest}")
            continue
        pairs = list(zip(old[i1:i2], new[j1:j2]))
        for (w_old, a), (where, b) in pairs:
            if a is None or b is None:
                lines.append(f"SKIPPED    {where}")
            else:
                lines.append(f"DIFFERENT  {where} (was {w_old}): {len(a):,} -> {len(b):,} chars")
                bad += 1
        for where, a in old[i1 + len(pairs):i2]:
            lines.append(f"REMOVED    {where}: {len(a or ''):,} chars")
            bad += 1
        for where, b in new[j1 + len(pairs):j2]:
            lines.append(f"ADDED      {where}: {len(b or ''):,} chars")
            bad += 1
    same = sum(line.startswith("IDENTICAL") for line in lines)
    skipped = sum(line.startswith("SKIPPED") for line in lines)
    lines.append(f"[proof] {same} of {len(new)} calls render byte-identical to the "
                 f"revision, {bad} changed, {skipped} skipped")
    return lines, bad


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(__doc__)
        return 2
    old_src = subprocess.run(["git", "show", f"{argv[1]}:stream_lit.py"], cwd=ROOT,
                             capture_output=True, text=True, encoding="utf-8",
                             check=True).stdout
    new_src = (ROOT / "stream_lit.py").read_text(encoding="utf-8")
    lines, bad = compare(old_src, new_src)
    print("\n".join(lines))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
