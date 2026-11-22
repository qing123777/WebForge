"""Ticket 03: the UI baseline record and compare commands.

    python tests/test_ui_baseline.py           # offline, about 1 s
    python tests/test_ui_baseline.py --record  # also runs one real recording on
                                               # the mock backend, about 30 s

No model call. Tests drive the two public commands only:

    python tools/ui_baseline.py record  --out DIR
    python tools/ui_baseline.py compare BEFORE AFTER

  UB-1  compare of a snapshot against an identical copy exits 0.
  UB-2  a screenshot that really changed makes compare exit non-zero and names it.
  UB-3  a screenshot that differs only by run-to-run noise still exits 0.
  UB-4  a timing that got much slower makes compare exit non-zero and names it.
  UB-5  a timing that moved within noise still exits 0.
  UB-6  a flow fact that changed (clicked target, modify marker) exits non-zero.
  UB-7  a screenshot missing from the later run exits non-zero.
  UB-8  (--record) record writes a snapshot that compares IDENTICAL to itself.
  UB-9  two snapshots recorded at different mock speeds exit non-zero.
  UB-10 noise reports the worst screenshot diff and timing spread over all pairs.

The noise command is how the tolerances in tools/ui_baseline.py were measured:

    python tools/ui_baseline.py noise DIR1 DIR2 [DIR3 ...]

Exits non-zero on any failure.
"""
from __future__ import annotations

import json
import pathlib
import shutil
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parent.parent
TOOL = ROOT / "tools" / "ui_baseline.py"

FAILS: list[str] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    print(f"{'PASS' if cond else 'FAIL'}  {name}" + (f"\n      {detail}" if not cond else ""))
    if not cond:
        FAILS.append(name)


def run(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(TOOL), *args], cwd=str(ROOT),
                          capture_output=True, text=True, timeout=600)


def make_snapshot(d: pathlib.Path) -> pathlib.Path:
    """A small hand-built snapshot in the format record writes."""
    from PIL import Image, ImageDraw
    (d / "shots").mkdir(parents=True)
    for name in ("01_empty", "03_built"):
        img = Image.new("RGB", (400, 300), "white")
        ImageDraw.Draw(img).rectangle([20, 20, 380, 120], fill=(30, 60, 200))
        img.save(d / "shots" / f"{name}.png")
    (d / "timings.json").write_text(json.dumps({
        "timings": {"send_to_preview_s": 9.2, "click_to_select_s": 1.4},
        "facts": {"clicked": "product-card", "marker": ".featured-bean-card"},
        "speed": "0.3",
    }, indent=2))
    return d


def ub1(tmp: pathlib.Path) -> None:
    a, b = _pair(tmp)
    r = run("compare", str(a), str(b))
    check("UB-1 identical snapshots exit 0", r.returncode == 0, r.stdout + r.stderr)


def _pair(tmp: pathlib.Path):
    a = make_snapshot(tmp / "a")
    b = tmp / "b"
    shutil.copytree(a, b)
    return a, b


def _edit_shot(snap: pathlib.Path, name: str, box, colour) -> None:
    from PIL import Image, ImageDraw
    p = snap / "shots" / f"{name}.png"
    img = Image.open(p).convert("RGB")
    ImageDraw.Draw(img).rectangle(box, fill=colour)
    img.save(p)


def ub2(tmp: pathlib.Path) -> None:
    a, b = _pair(tmp)
    # A whole new block appears: a layout change a UI ticket could cause.
    _edit_shot(b, "03_built", [20, 150, 380, 280], (200, 40, 40))
    r = run("compare", str(a), str(b))
    check("UB-2 a changed screenshot exits non-zero and is named",
          r.returncode != 0 and "03_built" in r.stdout and "01_empty" not in r.stdout,
          r.stdout + r.stderr)


def _edit_json(snap: pathlib.Path, section: str, key: str, value) -> None:
    p = snap / "timings.json"
    d = json.loads(p.read_text())
    d[section][key] = value
    p.write_text(json.dumps(d))


def ub3(tmp: pathlib.Path) -> None:
    a, b = _pair(tmp)
    # 8x7 = 56 px of 120,000 (0.047%): about twice the worst noise measured
    # between back-to-back recordings (0.025%), and still under the 0.1%
    # tolerance. A few anti-aliased glyph edges, not a UI change.
    _edit_shot(b, "01_empty", [200, 200, 207, 206], (0, 0, 0))
    r = run("compare", str(a), str(b))
    check("UB-3 screenshot noise below tolerance exits 0", r.returncode == 0,
          r.stdout + r.stderr)


def ub4(tmp: pathlib.Path) -> None:
    a, b = _pair(tmp)
    _edit_json(b, "timings", "send_to_preview_s", 14.0)  # 9.2 -> 14.0, +52%
    r = run("compare", str(a), str(b))
    check("UB-4 a much slower timing exits non-zero and is named",
          r.returncode != 0 and "send_to_preview_s" in r.stdout
          and "click_to_select_s" not in r.stdout, r.stdout + r.stderr)


def ub5(tmp: pathlib.Path) -> None:
    a, b = _pair(tmp)
    _edit_json(b, "timings", "send_to_preview_s", 10.4)  # +1.2 s, the worst spread seen
    _edit_json(b, "timings", "click_to_select_s", 1.6)   # +0.2 s on a short one
    r = run("compare", str(a), str(b))
    check("UB-5 timings within noise exit 0", r.returncode == 0, r.stdout + r.stderr)


def ub6(tmp: pathlib.Path) -> None:
    a, b = _pair(tmp)
    _edit_json(b, "facts", "marker", "#hero")
    r = run("compare", str(a), str(b))
    check("UB-6 a changed flow fact exits non-zero and is named",
          r.returncode != 0 and "marker" in r.stdout, r.stdout + r.stderr)


def ub7(tmp: pathlib.Path) -> None:
    a, b = _pair(tmp)
    (b / "shots" / "03_built.png").unlink()
    r = run("compare", str(a), str(b))
    empty = tmp / "empty"
    empty.mkdir()
    r2 = run("compare", str(empty), str(empty))
    check("UB-7 a missing screenshot, or an empty snapshot, exits non-zero",
          r.returncode != 0 and "03_built" in r.stdout and r2.returncode != 0,
          r.stdout + r.stderr + r2.stdout + r2.stderr)


def ub9(tmp: pathlib.Path) -> None:
    a, b = _pair(tmp)
    p = b / "timings.json"
    d = json.loads(p.read_text())
    d["speed"] = "0.6"
    p.write_text(json.dumps(d))
    r = run("compare", str(a), str(b))
    check("UB-9 snapshots at different mock speeds exit non-zero",
          r.returncode != 0 and "speed" in r.stdout, r.stdout + r.stderr)


def ub10(tmp: pathlib.Path) -> None:
    a, b = _pair(tmp)
    c = tmp / "c"
    shutil.copytree(a, c)
    _edit_shot(b, "01_empty", [200, 200, 207, 206], (0, 0, 0))   # 56 px = 0.047%
    _edit_json(c, "timings", "send_to_preview_s", 10.4)            # 9.2 -> 10.4
    r = run("noise", str(a), str(b), str(c))
    out = r.stdout
    check("UB-10 noise reports the worst shot diff and timing spread over all pairs",
          r.returncode == 0 and "[proof]" in out and "0.047%" in out
          and "send_to_preview_s" in out and "1.20s" in out and "3 recordings" in out,
          out + r.stderr)


def ub8(tmp: pathlib.Path) -> None:
    out = tmp / "rec"
    r = run("record", "--out", str(out))
    shots = sorted(p.stem for p in (out / "shots").glob("*.png"))
    data = json.loads((out / "timings.json").read_text()) if (out / "timings.json").exists() else {}
    t = data.get("timings", {})
    check("UB-8a record exits 0 and writes screenshots and timings",
          r.returncode == 0 and len(shots) >= 4
          and t.get("send_to_preview_s", 0) > 0 and t.get("click_to_select_s", 0) > 0
          and data.get("facts", {}).get("marker"),
          f"rc={r.returncode} shots={shots} data={data}\n{r.stdout[-1500:]}{r.stderr[-1500:]}")
    r2 = run("compare", str(out), str(out))
    check("UB-8b a recording compares IDENTICAL to itself",
          r2.returncode == 0 and "IDENTICAL" in r2.stdout, r2.stdout + r2.stderr)


def main() -> None:
    tests = [ub1, ub2, ub3, ub4, ub5, ub6, ub7, ub9, ub10]
    if "--record" in sys.argv:
        tests.append(ub8)
    with tempfile.TemporaryDirectory() as t:
        tmp = pathlib.Path(t)
        for i, fn in enumerate(tests):
            d = tmp / str(i)
            d.mkdir()
            fn(d)
    print(f"\n{'OK' if not FAILS else 'FAILED: ' + ', '.join(FAILS)}")
    sys.exit(1 if FAILS else 0)


if __name__ == "__main__":
    main()
