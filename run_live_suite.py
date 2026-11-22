"""Run the live suites you ask for, on the webforge/ package.

    python run_live_suite.py --list             what suites exist, and what each costs
    python run_live_suite.py pipeline           free: mocked + real-browser, no LLM
    python run_live_suite.py html css js        the three developer agents
    python run_live_suite.py so                 Secondary Orchestrator
    python run_live_suite.py po08               the full-system run
    python run_live_suite.py html --dry-run     resolve the plan, spend nothing

WHAT IT RUNS (ticket 18)

Each live suite is a few files under tests/live_cells/, copied once out of the
frozen fyp.ipynb (tools/port_live_cells.py). They run in one fresh Python
process, in the flat namespace of the webforge/ package, the same way pytest
runs the ported unit cells (tests/cell_runner.py). So a paid run tests the
package's code. fyp.ipynb is never read.

Before ticket 18 this script executed every cell of the notebook in file
order, so a suite tested the notebook's copy of the system, which the package
has since moved away from.

A suite runs its own cells plus the scaffolding they name in `# Needs: cell N`
lines (helpers such as _stream_html_agent), in cell order. Nothing else runs:
no other live cell, and none of the unit cells the old notebook run executed
first. A live cell never Needs another live cell, so `--only` cannot pull a
paid case in behind your back; a case that needs an earlier one says so
loudly when it starts (SO-02 opens with _so_require_so01).

THE KEYS

`.env` is loaded before the package is imported, because the package builds
its models at import and they read OPENAI_API_KEY then. A free suite
(`pipeline`) runs with every API key replaced by a dead string, so it cannot
spend even by mistake. A paid suite asks before it starts.

WHAT IT IS NOT

It runs in its own process. When it finishes there are no variables left to
poke at. Every cell's output goes to logs/live_<suites>_<stamp>.log, and the
[proof] lines are gathered at the end so they can be copied in one block.
--write-back also writes logs/live_<suites>_<stamp>.ipynb: one cell per file
that ran, its source and its output, to open in VS Code.
"""
from __future__ import annotations

import contextlib
import io
import json
import os
import pathlib
import re
import sys
import time
from typing import NamedTuple

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "tests"))
import cell_runner  # noqa: E402  (imports nothing from webforge)

LOG_DIR = ROOT / "logs"
# Where suite files are looked for. A test points this at a temp folder.
CELL_DIRS = cell_runner.CELL_DIRS


# Suites are addressed by CONTENT: each anchor must match EXACTLY ONE file in
# CELL_DIRS or the run refuses to start. A wrong match would run the wrong
# cell with real credentials. `free` suites make no model call.
SUITES = {
    "pipeline": {
        "cost": "free (mocked browser + real Chromium, no LLM)",
        "free": True,
        "anchors": [
            "TIER 1 — TOOL UNIT TESTS: TEST EXECUTION PIPELINE",
            "E2E (live browser, NO LLM): Test Execution pipeline + report routing.",
        ],
    },
    "html": {
        "cost": "~6-12 model calls",
        "anchors": [
            "E2E-GM-01  Generation mode — normal case",
            "E2E-MM-01  Modification mode — single component, single instance",
        ],
    },
    "css": {
        "cost": "~6-12 model calls",
        "anchors": [
            "END-TO-END CSS AGENT TESTS",
            "E2E-CSS-MM-01  Modification mode — targeted change, siblings intact",
        ],
    },
    "js": {
        "cost": "~6-12 model calls",
        "anchors": [
            "END-TO-END JS AGENT TESTS",
            "E2E-JS-MM-01  Modification mode — targeted change, wiring intact",
        ],
    },
    "tg": {
        "cost": "~3-4 model calls",
        "anchors": ["E2E (live LLM): Test Generation agent + progress middleware."],
    },
    "sd": {
        "cost": "~6-9 model calls",
        "anchors": [
            "E2E-SD-01  Smoke",
            "E2E-SD-02  System Design Planning, normal brief",
            "E2E-SD-03  A storefront plan, with real product records",
        ],
    },
    "so": {
        "cost": "~20-40 model calls",
        # The leading box character matters. Without it these also match the
        # scaffolding file, which carries a comment INDEX naming every case.
        "anchors": [
            "══ E2E-SO-01 ",
            "══ E2E-SO-02 ",
            "══ E2E-SO-03 ",
            "══ E2E-SO-04 ",
            "══ E2E-SO-05 ",
            "══ E2E-SO-06 ",
        ],
    },
    "po08": {
        "cost": "~100-170 model calls, roughly $2.50 and 13-16 minutes",
        "anchors": ["══ PO-08 "],
    },
}

_LIVE = re.compile(r"^# LIVE-LLM:", re.M)


def is_live(path: pathlib.Path) -> bool:
    """A file copied from a `# LIVE-LLM:` cell: it calls the real model."""
    return bool(_LIVE.search(path.read_text(encoding="utf-8")))


class Plan(NamedTuple):
    steps: list          # every file to run, in cell order
    targets: dict        # the suite files among them -> their label


def _suite_files() -> list[pathlib.Path]:
    return sorted(p for d in CELL_DIRS for p in d.glob("cell_*.py"))


def resolve(names) -> dict:
    """Anchor text -> suite file, refusing anything ambiguous."""
    files = _suite_files()
    texts = {p: p.read_text(encoding="utf-8") for p in files}
    picked, problems = {}, []
    for name in names:
        for anchor in SUITES[name]["anchors"]:
            hits = [p for p in files if anchor in texts[p]]
            if len(hits) != 1:
                problems.append(f"  {name}: {anchor!r} matched {len(hits)} file(s)")
                continue
            picked[hits[0]] = f"{name}: {anchor[:56]}"
    if problems:
        print("Cannot start -- an anchor no longer identifies exactly one file.")
        print("Someone edited or duplicated a suite header; fix SUITES in this file.")
        print("\n".join(problems))
        raise SystemExit(2)
    return picked


def plan(names, only=None) -> Plan:
    """The files a run of `names` executes. `only` narrows to particular cases
    inside a suite (`SO-02`, or a comma list); their scaffolding still runs,
    the sibling cases do not."""
    targets = resolve(names)
    if only:
        wanted = [w.strip().lower() for w in only.split(",") if w.strip()]
        kept = {p: lbl for p, lbl in targets.items()
                if any(w in lbl.lower() for w in wanted)}
        if not kept:
            raise SystemExit(f"--only {only!r} matches none of:\n    "
                             + "\n    ".join(sorted(targets.values())))
        targets = kept
    steps = set(targets)
    for target in targets:
        for dep in cell_runner.run_order(target, dirs=CELL_DIRS)[:-1]:
            if is_live(dep):
                raise SystemExit(f"{target.name} Needs {dep.name}, a live cell. A live "
                                 f"cell may Need only scaffolding: running another "
                                 f"live cell would spend money nobody chose.")
            steps.add(dep)
    return Plan(sorted(steps, key=cell_runner.cell_number),
                {p: targets[p] for p in sorted(targets, key=cell_runner.cell_number)})


def _log_path(tag: str, suffix: str) -> pathlib.Path:
    """logs/live_<tag>_<stamp><suffix>; the folder is made if missing."""
    LOG_DIR.mkdir(exist_ok=True)
    return LOG_DIR / f"live_{tag}_{time.strftime('%Y%m%d-%H%M%S')}{suffix}"


def save_transcript(captured, targets, tag, header, footer):
    r"""Write every file's output to logs/live_<tag>_<stamp>.log.

    Unconditional. A live run costs money and produces more output than a
    terminal can be searched by hand, so the transcript is the artefact, not a
    convenience: `Select-String -Path <file> -Pattern "FAIL|\[proof\]"` answers
    in one line what scrolling answers in ten minutes.

    Files that produced nothing are listed but not printed, so the file reads as
    the run's shape rather than as a wall.
    """
    out = _log_path(tag, ".log")
    parts = [header, ""]
    for path, text in captured.items():
        body = text.rstrip()
        label = targets.get(path, "")
        head = path.name + (f"  [LIVE] {label}" if label else "")
        if not body:
            parts.append(f"----- {head}  (no output)")
            continue
        parts.append(f"\n{'=' * 74}\n  {head}\n{'=' * 74}")
        parts.append(body)
    parts.append("\n" + footer)
    out.write_text("\n".join(parts), encoding="utf-8", errors="replace")
    return out


def write_back(captured, tag):
    """Write this run as a notebook under logs/: one code cell per file that
    ran, holding that file's source and output. The source is the code that
    ran, so the outputs never sit under code that did not produce them."""
    nb_cells = []
    for n, (path, text) in enumerate(captured.items(), 1):
        nb_cells.append({
            "cell_type": "code", "execution_count": n, "metadata": {},
            "source": path.read_text(encoding="utf-8").splitlines(keepends=True),
            "outputs": ([{"output_type": "stream", "name": "stdout",
                          "text": text.splitlines(keepends=True)}] if text else []),
        })
    nb = {"cells": nb_cells, "metadata": {}, "nbformat": 4, "nbformat_minor": 5}
    out = _log_path(tag, ".ipynb")
    out.write_text(json.dumps(nb, ensure_ascii=False, indent=1), encoding="utf-8")
    return f"--write-back: {len(nb_cells)} cell(s) written to {out}"


class _Tee:
    """Write through to the terminal AND keep the [proof] lines.

    Live suites take minutes, so their output has to appear as it happens --
    a silent terminal looks like a hang. But the [proof] lines are the reason
    the suite was run, and they arrive scattered through hundreds of lines of
    agent chatter, so they are also collected for a digest at the end.
    """

    def __init__(self, stream, sink):
        self._s, self._sink, self._buf = stream, sink, ""
        self.text = ""

    def getvalue(self):
        return self.text

    def write(self, text):
        self._s.write(text)
        self.text += text
        self._buf += text
        while "\n" in self._buf:
            line, self._buf = self._buf.split("\n", 1)
            if "[proof]" in line:
                self._sink.append(line.strip())

    def flush(self):
        self._s.flush()

    def isatty(self):
        return getattr(self._s, "isatty", lambda: False)()


def _take_value(args, name):
    """Pull `--name X` or `--name=X` out of the argument list, or None.

    Hand-rolled rather than argparse because the positional arguments are a
    variable list of suite names, and `--only SO-02` must not be mistaken for
    a suite called SO-02.
    """
    for i, a in enumerate(list(args)):
        if a == name and i + 1 < len(args):
            val = args[i + 1]
            del args[i:i + 2]
            return val
        if a.startswith(name + "="):
            val = a.split("=", 1)[1]
            args.remove(a)
            return val
    return None


def _set_keys(paid: bool) -> None:
    if not paid:
        # A free suite gets dead keys, as pytest does: nothing it runs may
        # reach a model, and if something does it fails with a rejected key.
        cell_runner.disable_api_keys("sk-DISABLED-free-suite-must-not-call-any-api")
        return
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
    if not os.environ.get("OPENAI_API_KEY"):
        raise SystemExit("no OPENAI_API_KEY in the environment or in .env")


def main(argv=None):
    raw = list(sys.argv[1:] if argv is None else argv)
    only = _take_value(raw, "--only")
    names = [a for a in raw if not a.startswith("--")]
    flags = {a for a in raw if a.startswith("--")}

    if "--list" in flags or not names:
        print("\n  suites (give one or more):\n")
        for name, spec in SUITES.items():
            p = plan([name])
            cells = [cell_runner.cell_number(f) for f in p.targets]
            print(f"    {name:<10} {spec['cost']:<52} cells {cells}")
        print("\n  each suite runs on the webforge/ package, after the scaffolding "
              "its\n  files name in '# Needs: cell N'. Add --dry-run to see the plan "
              "without\n  spending, --yes to skip the confirmation.\n")
        return 0

    unknown = [a for a in names if a not in SUITES]
    if unknown:
        raise SystemExit(f"unknown suite(s) {unknown}. Run --list to see what exists.")

    p = plan(names, only)
    paid = [n for n in names if not SUITES[n].get("free")]
    tag = "-".join(names) + (f"-{only.replace(',', '-')}" if only else "")

    plan_header = (f"{'=' * 74}\n  plan: {' '.join(names)}   "
                   f"({time.strftime('%Y-%m-%d %H:%M:%S')})\n{'=' * 74}")
    print()
    print(plan_header)
    for step in p.steps:
        role = p.targets.get(step) or "scaffolding"
        shown = step.relative_to(ROOT) if step.is_relative_to(ROOT) else step
        print(f"    {shown.as_posix():<64} {role}")
    print("\n    runs on the webforge/ package (fyp.ipynb is not read)")
    if paid:
        bill = "; ".join(n + " " + SUITES[n]["cost"] for n in paid)
        if only:
            # The per-suite estimate is for the WHOLE suite. Saying "so ~20-40
            # calls" while running one of its six cases would overstate the bill
            # by a factor of six, and an estimate nobody believes gets ignored.
            whole = sum(len(SUITES[n]["anchors"]) for n in names)
            bill += (f"  -- but narrowed to {len(p.targets)} of {whole} case(s), "
                     f"so expect roughly {len(p.targets)}/{whole} of that")
        print(f"\n    THIS SPENDS REAL CREDITS: {bill}")
    else:
        print("\n    no LLM calls in this plan")
    print()

    if "--dry-run" in flags:
        print("  --dry-run: nothing was executed.\n")
        return 0

    if paid and "--yes" not in flags:
        try:
            if input("  type 'run' to start: ").strip().lower() != "run":
                print("  cancelled.\n")
                return 1
        except (EOFError, KeyboardInterrupt):
            print("\n  cancelled.\n")
            return 1

    _set_keys(bool(paid))

    proofs, captured, t0 = [], {}, time.time()
    try:
        session = cell_runner.CellSession()
    except Exception as exc:
        # Nothing has been spent yet, but a paid run that dies here still owes
        # the user a FAIL line and a transcript, as any failing file does.
        print(f"\n  FAIL loading webforge/  {type(exc).__name__}: {str(exc)[:200]}")
        print("  full transcript: " + str(save_transcript(
            captured, p.targets, tag, plan_header,
            f"FAILED loading webforge/: {type(exc).__name__}: {exc}")))
        return 1
    try:
        for step in p.steps:
            selected = step in p.targets
            if selected:
                # Live files stream straight to the terminal: these take minutes
                # and a silent terminal is indistinguishable from a hung one.
                print(f"\n{'=' * 74}\n  {step.name}  {p.targets[step]}\n{'=' * 74}")
                sink = _Tee(sys.stdout, proofs)
            else:
                sink = io.StringIO()
            try:
                with contextlib.redirect_stdout(sink):
                    session.run(step)
            except Exception as exc:
                text = sink.getvalue()
                captured[step] = text + f"\n{type(exc).__name__}: {exc}\n"
                print(f"\n  FAIL {step.name}  {type(exc).__name__}: {str(exc)[:200]}")
                if not selected:
                    tail = "\n".join(text.splitlines()[-8:])
                    if tail.strip():
                        print("  last output before the failure:\n    "
                              + tail.replace("\n", "\n    "))
                print(f"\n  stopped after {time.time() - t0:.0f}s. "
                      f"Everything above this file did run.")
                # The failing run is the one whose transcript matters most, so
                # it is written on the way out rather than only on success.
                print("  full transcript: " + str(save_transcript(
                    captured, p.targets, tag, plan_header,
                    f"FAILED in {step.name}: {type(exc).__name__}: {exc}")))
                return 1
            captured[step] = sink.getvalue()
            if not selected:
                for line in captured[step].splitlines():
                    if line.startswith("FAIL") or " FAILED" in line:
                        print(f"       {step.name}  {line[:110]}")
    finally:
        session.close()

    print(f"\n{'=' * 74}")
    print(f"  ran {len(captured)} file(s), {time.time() - t0:.0f}s")
    print("=" * 74)

    log = save_transcript(captured, p.targets, tag, plan_header,
                          f"ran {len(captured)}, {time.time() - t0:.0f}s")
    print(f"  full transcript: {log}")
    print(f"  search it:  Select-String -Path \"{log}\" "
          f"-Pattern \"FAIL|\\[proof\\]|AUTO-\"")

    if "--write-back" in flags:
        print("  " + write_back(captured, tag))

    # The digest. A suite passes identically whether the change under test is
    # present or absent -- a healthy run exercises none of the guards -- so the
    # [proof] lines are the only output that makes a change visible.
    if proofs:
        print(f"\n  {len(proofs)} [proof] line(s):\n")
        for line in proofs:
            print("   " + line)
        print()
    elif paid:
        print("\n  NO [proof] line was printed. Either the suites you ran carry "
              "none yet,\n  or a guard's proof block was removed. Green without a "
              "proof line means\n  the run passed, not that the change works.\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
