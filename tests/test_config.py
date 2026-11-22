"""Ticket 02: every path comes from webforge.config, whatever the cwd is.

    python tests/test_config.py

No model call. It starts a child Python process whose working directory is a
fresh temp folder OUTSIDE the repo, imports the webforge package there, and checks:

  C-1  webforge.config derives every path from the repo root.
  C-2  the system's source (webforge/**/*.py) holds no absolute drive path
       (the flat fyp.py had 8 before ticket 02; ticket 15 deleted its shim).
  C-3  every filesystem backend the package built (the save backends and each developer
       agent's FilesystemMiddleware backend) is rooted at config.PREVIEW_DIR.
  C-4  the checkpoint DB is config.CHECKPOINT_DB.
  C-5  html-validate, stylelint and eslint, run from that foreign cwd, give the
       same result as the recorded baseline on pages where each one FAILS (a
       clean page could pass for the wrong reason, e.g. a linter that never ran).
       The baseline is the one made on the same kind of machine
       (baseline/README.md): `before` on Windows, `before-linux` elsewhere.

Exits non-zero on any failure.
"""
from __future__ import annotations

import json
import os
import pathlib
import re
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parent.parent
SNAPSHOT = ROOT / "baseline" / "snapshots" / (
    "before" if sys.platform == "win32" else "before-linux")

# One page per linter where the baseline records a lint FAILURE.
LINT_CASES = {
    "html": "po07332e0a",
    "css": "741c7b34-f21e-4f7c-8cc8-9d2635e24bde",
    "js": "po08b0c8462",
}

CHILD = r'''
import contextlib, gc, io, json, os, pathlib, sys
root = pathlib.Path(sys.argv[1])
sys.path.insert(0, str(root))
sys.path.insert(0, str(root / "baseline"))
import capture                      # sets dead API keys before webforge is imported
with contextlib.redirect_stdout(io.StringIO()):
    import webforge.primary_orchestrator as po
from webforge import config
backends = [o for o in gc.get_objects()
            if type(o).__name__ == "OverwritingFilesystemBackend"]
cases = json.loads(sys.argv[2])
lint = {}
for lang, sid in cases.items():
    code = (capture.FIXTURES / f"preview_{sid}.{lang}").read_text(encoding="utf-8")
    fn = {"html": po._lint_html_source, "css": po._lint_css_source,
          "js": po._lint_js_source}[lang]
    lint[lang] = capture.command_to_json(fn(code, capture.FakeRuntime({})))
print(json.dumps({
    "cwd": os.getcwd(),
    "backend_roots": [str(b.cwd) for b in backends],
    "checkpoint_db": str(po._CHECKPOINT_DB),
    "preview_root": str(po._PREVIEW_ROOT),
    "lint": lint,
}))
'''

failures: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + (f"  ({detail})" if detail else ""))
    if not ok:
        failures.append(name)


def main() -> int:
    sys.path.insert(0, str(ROOT))
    from webforge import config

    # C-1
    check("C-1 REPO_ROOT is the repo", config.REPO_ROOT == ROOT)
    check("C-1 PREVIEW_DIR", config.PREVIEW_DIR == ROOT / "static" / "preview")
    check("C-1 LINT_TMP_DIR", config.LINT_TMP_DIR == ROOT / ".lint_tmp")
    check("C-1 CHECKPOINT_DB", config.CHECKPOINT_DB == ROOT / "fyp_threads.db")
    check("C-1 UI_ASSETS_DIR", config.UI_ASSETS_DIR == ROOT / "ui_assets")

    # C-2
    src = "\n".join(p.read_text(encoding="utf-8")
                    for p in sorted((ROOT / "webforge").rglob("*.py")))
    drive_paths = re.findall(r"""["'][A-Za-z]:[\\/]""", src)
    check("C-2 no absolute drive path in the system source", not drive_paths,
          f"{len(drive_paths)} found")

    # C-3..C-5 run in a child process whose cwd is outside the repo.
    with tempfile.TemporaryDirectory() as foreign:
        env = dict(os.environ)
        env.pop("PYTHONPATH", None)
        proc = subprocess.run(
            [sys.executable, "-c", CHILD, str(ROOT), json.dumps(LINT_CASES)],
            cwd=foreign, env=env, capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=600)
    if proc.returncode != 0:
        print(proc.stderr[-3000:])
        check("child process imported webforge from a foreign cwd", False)
        return 1
    res = json.loads(proc.stdout.strip().splitlines()[-1])
    check("child cwd is outside the repo",
          not pathlib.Path(res["cwd"]).resolve().is_relative_to(ROOT), res["cwd"])

    roots = res["backend_roots"]
    rooted = sum(pathlib.Path(r) == config.PREVIEW_DIR for r in roots)
    check("C-3 every filesystem backend rooted at PREVIEW_DIR",
          bool(roots) and rooted == len(roots), f"{rooted}/{len(roots)}")
    check("C-3 _PREVIEW_ROOT", pathlib.Path(res["preview_root"]) == config.PREVIEW_DIR)

    check("C-4 checkpoint DB", pathlib.Path(res["checkpoint_db"]) == config.CHECKPOINT_DB)

    baseline = json.loads((SNAPSHOT / "lint.json").read_text(encoding="utf-8"))
    matched = 0
    for lang, sid in LINT_CASES.items():
        want, got = baseline[sid][lang], res["lint"][lang]
        same = want == got
        matched += same
        check(f"C-5 {lang} lint from foreign cwd matches baseline ({sid})", same,
              f"lint_passed={got.get('lint_passed')}")
        check(f"C-5 {lang} baseline case is a real failure", want.get("lint_passed") is False)

    print(f"[proof] paths: {len(drive_paths)} absolute drive paths in webforge/ "
          f"(8 before ticket 02); {rooted}/{len(roots)} filesystem backends rooted at "
          f"{config.PREVIEW_DIR} while cwd={res['cwd']}; {matched}/{len(LINT_CASES)} "
          f"failing-page lint results from that cwd equal {SNAPSHOT.name}.")
    print(f"{'FAILED' if failures else 'OK'}: {len(failures)} failure(s)")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
