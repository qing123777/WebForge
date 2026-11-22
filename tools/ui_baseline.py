"""Record the UI baseline on the zero-credit mock backend, and compare a later run.

    python tools/ui_baseline.py record  --out baseline/ui/after
    python tools/ui_baseline.py compare baseline/ui/before baseline/ui/after
    python tools/ui_baseline.py noise   DIR1 DIR2 [DIR3 ...]   # re-measure noise

Ticket 03. ``record`` runs the nine ``tools/ui_smoke.py`` steps on the mock app
(no model call, about 30 s) and writes a snapshot:

    shots/NN_<step>.png   the screen after each step, once the UI has settled
    timings.json          send -> preview, send -> reply, click -> select,
                          modify -> preview (seconds); the clicked target and
                          the modify marker; per-step pass and duration

``compare`` exits 0 and prints IDENTICAL when every screenshot, timing and fact
is within measured run-to-run noise. Otherwise it prints one CHANGED line per
difference and exits 1. A slower timing is a change; a faster one is a NOTE.
Both print a ``[proof]`` line with the worst diff found beside the tolerance
and the measured noise. The tolerances and how they were measured are below;
``noise`` re-measures them from any number of recordings of unchanged code.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import re
import shutil
import sys

TOOLS = pathlib.Path(__file__).resolve().parent
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

# Tolerances, and the noise they were set against. Noise was measured on
# 2026-11-09 with back-to-back ``record`` runs on unchanged code (Linux cloud
# container, headless Chromium, WEBFORGE_MOCK_SPEED=0.3): the final code, six
# runs, all fifteen pairs, plus earlier sets for the timings. Re-measure the
# same way if the machine or the speed changes.
#
# A pixel counts as changed when any channel moved by more than PIXEL_DELTA
# (0-255). A screenshot counts as changed when more than SHOT_TOLERANCE of its
# pixels did. Measured worst: 0.025% (shot 08, a few anti-aliased glyph edges).
# 0.1% of 1440x900 is 1,296 px, about one changed word of chat text.
PIXEL_DELTA = 32
SHOT_TOLERANCE = 0.001
SHOT_NOISE = 0.00025
# A timing counts as slower when it grew by more than max(TIME_ABS_S, TIME_REL
# x before). TIME_ABS_S is a floor for the short timings, about six times the
# 0.04 s that click_to_select_s moved. Measured worst spread: send_to_reply_s 7.54 -> 8.78 s (+1.24 s,
# +16%). It lands on one of two values about 1 s apart (7.6 or 8.7 s), a step,
# not a drift: step 3 can match the reply sentence while it still streams.
# send_to_preview_s moved by 0.27 s, the other two by 0.04 s or less. A faster
# timing is reported, never a failure.
TIME_ABS_S = 0.25
TIME_REL = 0.25
TIME_NOISE_S = 1.24


def shot_diff(a: pathlib.Path, b: pathlib.Path) -> float:
    """Fraction of pixels that changed between two screenshots (1.0 if sizes differ)."""
    from PIL import Image, ImageChops
    ia, ib = Image.open(a).convert("RGB"), Image.open(b).convert("RGB")
    if ia.size != ib.size:
        return 1.0
    diff = ImageChops.difference(ia, ib).convert("L").point(
        lambda v: 255 if v > PIXEL_DELTA else 0)
    return diff.histogram()[255] / (ia.size[0] * ia.size[1])


def _load(snap: pathlib.Path) -> dict:
    p = snap / "timings.json"
    return json.loads(p.read_text()) if p.exists() else {}


def compare(before, after) -> int:
    """Print every difference beyond noise; return 1 if there is any, else 0."""
    before, after = pathlib.Path(before), pathlib.Path(after)
    changed, notes = [], []
    shots_b = {p.name for p in (before / "shots").glob("*.png")}
    shots_a = {p.name for p in (after / "shots").glob("*.png")}
    jb, ja = _load(before), _load(after)
    if not shots_b or not jb:
        print(f"CHANGED  {before} holds no screenshots or no timings.json: "
              "not a recorded snapshot")
        return 1
    if jb.get("speed") != ja.get("speed"):
        changed.append(f"speed: recorded at WEBFORGE_MOCK_SPEED {jb.get('speed')!r} "
                       f"vs {ja.get('speed')!r}, so the timings cannot be compared")

    for name in sorted(shots_b - shots_a):
        changed.append(f"shot {name[:-4]}: missing from {after}")
    for name in sorted(shots_a - shots_b):
        changed.append(f"shot {name[:-4]}: new, not in {before}")
    worst_shot = 0.0
    for name in sorted(shots_b & shots_a):
        frac = shot_diff(before / "shots" / name, after / "shots" / name)
        worst_shot = max(worst_shot, frac)
        if frac > SHOT_TOLERANCE:
            changed.append(f"shot {name[:-4]}: {frac:.3%} of pixels changed "
                           f"(tolerance {SHOT_TOLERANCE:.3%})")

    tb, ta = jb.get("timings", {}), ja.get("timings", {})
    worst_time = 0.0
    for k in sorted(set(tb) | set(ta)):
        if k not in ta or k not in tb:
            changed.append(f"timing {k}: only in {before if k in tb else after}")
            continue
        delta = ta[k] - tb[k]
        allowed = max(TIME_ABS_S, TIME_REL * tb[k])
        worst_time = max(worst_time, delta)
        if delta > allowed:
            changed.append(f"timing {k}: {tb[k]:.2f}s -> {ta[k]:.2f}s "
                           f"(+{delta:.2f}s, allowed +{allowed:.2f}s)")
        elif -delta > allowed:
            notes.append(f"timing {k}: {tb[k]:.2f}s -> {ta[k]:.2f}s (faster)")

    fb, fa = jb.get("facts", {}), ja.get("facts", {})
    for k in sorted(set(fb) | set(fa)):
        if fb.get(k) != fa.get(k):
            changed.append(f"fact {k}: {fb.get(k)!r} -> {fa.get(k)!r}")
    for k, v in ja.get("steps", {}).items():
        if not v.get("pass"):
            changed.append(f"step {k!r} FAILED in {after}")

    for line in changed:
        print(f"CHANGED  {line}")
    for line in notes:
        print(f"NOTE     {line}")
    print(f"[proof] worst screenshot diff {worst_shot:.3%} of pixels vs tolerance "
          f"{SHOT_TOLERANCE:.3%} (measured run-to-run noise {SHOT_NOISE:.3%}); "
          f"worst slowdown {worst_time:+.2f}s vs allowed max({TIME_ABS_S}s, "
          f"{TIME_REL:.0%}) (measured noise {TIME_NOISE_S:.2f}s); "
          f"{len(shots_b & shots_a)} shots, {len(set(tb) & set(ta))} timings, "
          f"{len(fb)} facts compared")
    if changed:
        print(f"\n{len(changed)} change(s) beyond noise")
        return 1
    print("IDENTICAL")
    return 0


# ctx key written by tools/ui_smoke.py -> timing name in timings.json
TIMINGS = {
    "send_to_preview_s": "preview_s",        # Confirm click -> this thread's preview iframe
    "send_to_reply_s": "build_s",            # Confirm click -> final "ready" reply
    "click_to_select_s": "select_s",         # click a card in Select mode -> edit pocket open
    "modify_to_preview_s": "modify_preview_s",  # send the chip -> modified page shown
}


def noise(dirs) -> int:
    """Print the worst screenshot diff and timing spread over every pair of recordings.

    Feed it two or more ``record`` runs of unchanged code. The numbers it prints
    are what SHOT_NOISE and TIME_NOISE_S above hold.
    """
    import itertools
    dirs = [pathlib.Path(d) for d in dirs]
    if len(dirs) < 2:
        print("noise needs at least two recordings")
        return 1
    worst, where = 0.0, ""
    for a, b in itertools.combinations(dirs, 2):
        for pa in sorted((a / "shots").glob("*.png")):
            pb = b / "shots" / pa.name
            frac = shot_diff(pa, pb) if pb.exists() else 1.0
            if frac > worst:
                worst, where = frac, f"{pa.stem} ({a.name} vs {b.name})"
    runs = [_load(d).get("timings", {}) for d in dirs]
    spreads = {}
    for k in sorted(set().union(*runs)):
        vals = [t[k] for t in runs if k in t]
        spreads[k] = (min(vals), max(vals))
        print(f"timing {k}: {min(vals):.2f}s .. {max(vals):.2f}s, "
              f"spread {max(vals) - min(vals):.2f}s")
    top = max(spreads.items(), key=lambda kv: kv[1][1] - kv[1][0], default=None)
    print(f"[proof] {len(dirs)} recordings, "
          f"{len(dirs) * (len(dirs) - 1) // 2} pairs: worst screenshot diff "
          f"{worst:.3%} {where} vs tolerance {SHOT_TOLERANCE:.3%}"
          + (f"; worst timing spread {top[1][1] - top[1][0]:.2f}s ({top[0]}) vs "
             f"allowed max({TIME_ABS_S}s, {TIME_REL:.0%})" if top else ""))
    return 0


def _open_preview_panel(page) -> bool:
    """Open the preview panel if it is closed; return True if it had to.

    From step 4 on this thread has a page, so the panel should be open. After a
    browser reload it opens only if the app's ``webforgeSetPreviewState('ready')``
    runs after the page rebuilt; in 5 of 12 runs (measured 2026-11-09) it
    does not, and steps 8 and 9 then show the chat full width. That is a race in
    ``stream_lit.py``, not noise, so it is not hidden: record opens the panel the
    same way that function does (check the toggle, fire ``change``) and lists the
    step under ``observations`` in timings.json.
    """
    return page.evaluate("""() => {
        const input = document.getElementById('webforge-preview-toggle-input');
        if (!input || input.checked) return false;
        input.checked = true;
        input.dispatchEvent(new Event('change', {bubbles: true}));
        return true;
    }""")


_STABLE_GAP_MS = 700


def _settle(page, timeout_s: float = 30.0) -> tuple[bytes, bool]:
    """Wait for the page's end state and return a screenshot of it.

    A step can pass on text that streams in before the turn ends (step 3 matches
    the "ready" sentence while the live status box is still open), and after a
    reload the preview panel paints a moment after the chat. So the screenshot
    waits until no build is streaming, then until two screenshots taken
    ``_STABLE_GAP_MS`` apart are byte-identical. Returns the screenshot and
    whether it settled; one that did not is the last frame seen.
    """
    import time
    page.get_by_text("WebForge is working").first.wait_for(
        state="hidden", timeout=timeout_s * 1000)
    end = time.time() + timeout_s
    prev = None
    while True:
        page.wait_for_timeout(_STABLE_GAP_MS)
        cur = page.screenshot(animations="disabled", caret="hide")
        if cur == prev:
            return cur, True
        if time.time() > end:
            return cur, False
        prev = cur


def record(out, speed: str = "0.3") -> int:
    import ui_smoke
    out = pathlib.Path(out)
    if out.exists():
        shutil.rmtree(out)
    (out / "shots").mkdir(parents=True)

    reopened: list[int] = []
    unsettled: list[int] = []

    def shoot(i, page, ctx):
        label = [r[0] for r in ui_smoke.RESULTS][-1]
        slug = re.sub(r"\W+", "_", label.split(" ", 1)[1]).strip("_")[:40]
        if i >= 4 and _open_preview_panel(page):
            reopened.append(i)
        png, settled = _settle(page)
        if not settled:
            unsettled.append(i)
            print(f"WARNING  step {i}: the screen never held still for "
                  f"{_STABLE_GAP_MS} ms; its screenshot is the last frame seen")
        (out / "shots" / f"{i:02d}_{slug}.png").write_bytes(png)

    ctx, results = ui_smoke.run_flow(speed=speed, after_step=shoot)
    data = {
        "steps": {r[0]: {"pass": r[1], "s": round(r[2], 2)} for r in results},
        "timings": {k: round(ctx[v], 2) for k, v in TIMINGS.items() if v in ctx},
        "facts": {"clicked": ctx.get("target"), "marker": ctx.get("marker_target")},
        "speed": speed,
        # Not compared. Steps after which the preview panel was closed although
        # this thread has a page, so record opened it (see _open_preview_panel).
        # unsettled: steps whose screen never held still (see _settle).
        "observations": {"preview_panel_reopened_after_steps": reopened,
                         "unsettled_steps": unsettled},
    }
    (out / "timings.json").write_text(json.dumps(data, indent=2) + "\n")
    ok = sum(1 for r in results if r[1])
    print(f"recorded {out}: {ok}/{len(ui_smoke.STEPS)} steps passed, "
          f"{len(list((out / 'shots').glob('*.png')))} screenshots, timings {data['timings']}")
    return 0 if ok == len(ui_smoke.STEPS) else 1


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("record")
    r.add_argument("--out", required=True)
    r.add_argument("--speed", default="0.3", help="WEBFORGE_MOCK_SPEED for the mock app")
    c = sub.add_parser("compare")
    c.add_argument("before")
    c.add_argument("after")
    n = sub.add_parser("noise")
    n.add_argument("dirs", nargs="+")
    args = ap.parse_args(argv)
    if args.cmd == "record":
        return record(args.out, args.speed)
    if args.cmd == "noise":
        return noise(args.dirs)
    return compare(args.before, args.after)


if __name__ == "__main__":
    sys.exit(main())
