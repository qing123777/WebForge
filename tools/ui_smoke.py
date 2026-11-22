"""End-to-end UI check on the zero-credit mock backend.

    python tools/ui_smoke.py              # starts its own server, headless
    python tools/ui_smoke.py --headed     # watch it
    python tools/ui_smoke.py --url http://localhost:8599   # reuse a running app

Starts ``tools/mock_ui.py`` (the real ``stream_lit.py`` + real ``bridge`` on a
fake ``webforge.entry``), then drives a browser through every user-facing path:

    1  empty state renders
    2  a brief raises the question box (ask_user)
    3  answering it runs a build: live status box, then the final reply
    4  the preview panel shows the page for THIS thread
    5  Select mode -> click a card -> edit pocket -> annotation chip
    6  sending the chip produces a modify marker with the clicked target
    7  the preview shows the modified page without a manual reload
    8  a browser reload keeps the conversation and the page
    9  New chat gives an empty thread; the old thread is still in the sidebar

Each step prints PASS/FAIL and the seconds it took. Exit code 1 on any FAIL.
Screenshots of failures go to logs/ui_smoke/.
"""
import argparse
import os
import pathlib
import re
import socket
import sqlite3
import subprocess
import sys
import tempfile
import time

ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from webforge import contract  # noqa: E402  -- stdlib only, loads no agent code

SHOTS = ROOT / "logs" / "ui_smoke"

RESULTS = []


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _wait_http(url: str, timeout: float) -> None:
    import urllib.request
    end = time.time() + timeout
    while time.time() < end:
        try:
            urllib.request.urlopen(url, timeout=2)
            return
        except Exception:
            time.sleep(0.5)
    raise RuntimeError(f"app did not come up at {url}")


def step(name):
    def deco(fn):
        def run(page, ctx):
            t = time.time()
            try:
                fn(page, ctx)
                RESULTS.append((name, True, time.time() - t, ""))
                print(f"PASS  {time.time() - t:5.1f}s  {name}", flush=True)
            except Exception as e:  # noqa: BLE001
                SHOTS.mkdir(parents=True, exist_ok=True)
                shot = SHOTS / (re.sub(r"\W+", "_", name)[:40] + ".png")
                try:
                    page.screenshot(path=str(shot))
                except Exception:
                    pass
                lines = str(e).splitlines()
                msg = " | ".join([lines[0][:200]] + [l.strip()[:160] for l in lines[-3:] if l.strip()] if len(lines) > 1 else lines[:1])
                RESULTS.append((name, False, time.time() - t, msg))
                print(f"FAIL  {time.time() - t:5.1f}s  {name}\n      {msg}\n      {shot}",
                      flush=True)
                raise
        return run
    return deco


def _clock(ctx) -> float:
    """Wall time minus the time spent in ``after_step`` hooks.

    A timing that spans two steps (send -> preview, modify -> preview) would
    otherwise include whatever a hook did between them, e.g. a screenshot.
    """
    return time.time() - ctx.get("hook_s", 0.0)


def _watch_preview(page, tid: str) -> None:
    """Record, inside the page, when this thread's preview iframe first appears.

    Sets ``window.__wfPreviewSeenS`` to the seconds from now (the send click)
    until an iframe in any same-origin frame has a src containing
    ``preview_<tid>.html?v=``. Polled every 50 ms by the page itself, so it
    times the preview, not when step 4 got round to looking.
    """
    page.evaluate("""tid => {
        window.__wfPreviewSeenS = null;
        const t0 = performance.now();
        const want = 'preview_' + tid + '.html?v=';
        const scan = doc => {
            for (const f of doc.querySelectorAll('iframe')) {
                if ((f.getAttribute('src') || '').includes(want)) return true;
                try { if (f.contentDocument && scan(f.contentDocument)) return true; }
                catch (e) {}
            }
            return false;
        };
        const timer = setInterval(() => {
            if (scan(document)) {
                window.__wfPreviewSeenS = (performance.now() - t0) / 1000;
                clearInterval(timer);
            }
        }, 50);
    }""", tid)


def _preview_frame(page, select: bool):
    """The generated page inside the Streamlit component iframe."""
    for f in page.frames:
        if f.name == "" and "preview_" in (f.url or ""):
            if not select:
                return f
    # Select mode loads the page as srcdoc: find the frame by title.
    for f in page.frames:
        try:
            el = f.frame_element()
            if el.get_attribute("title") == "WebForge generated preview":
                return f
        except Exception:
            continue
    return None


def _composer(page):
    return page.get_by_placeholder(re.compile(r"Message WebForge|Answer the question"))


def _send(page, text):
    box = page.get_by_placeholder("Message WebForge...")
    box.click()
    box.fill(text)
    box.press("Enter")


@step("1 empty state renders")
def s1(page, ctx):
    page.get_by_text("What storefront should we").wait_for(timeout=90_000)
    _composer(page).wait_for()
    ctx["tid"] = re.search(r"[?&]t=([\w-]+)", page.url).group(1)


@step("2 brief raises the question box")
def s2(page, ctx):
    _send(page, "Build a storefront for a specialty coffee roaster selling whole beans.")
    page.get_by_text("What should the build prioritise?").wait_for(timeout=30_000)
    page.get_by_text("Confirm and continue").wait_for()


@step("3 answer runs a build with live status")
def s3(page, ctx):
    t = time.time()
    ctx["send_t0"] = _clock(ctx)
    _watch_preview(page, ctx["tid"])
    page.get_by_text("Confirm and continue").click()
    page.get_by_text("WebForge is working").first.wait_for(timeout=20_000)
    page.get_by_text("The storefront is ready in Preview").first.wait_for(timeout=180_000)
    ctx["build_s"] = time.time() - t
    page.get_by_text(re.compile(r"Steps · \d+")).last.wait_for()


@step("4 preview shows this thread's page")
def s4(page, ctx):
    tid = ctx["tid"]
    end = time.time() + 20
    while time.time() < end:
        srcs = [f.frame_element().get_attribute("src") or "" for f in page.frames[1:]
                if _safe_title(f) == "WebForge generated preview"]
        if any(f"preview_{tid}.html?v=" in s for s in srcs):
            seen = page.evaluate("() => window.__wfPreviewSeenS")
            # The in-page watcher saw the iframe appear; step 4 only starts
            # after step 3 waited for the reply, so its own clock is late.
            ctx["preview_s"] = seen if seen is not None else _clock(ctx) - ctx["send_t0"]
            return
        time.sleep(0.5)
    raise AssertionError(f"no preview iframe for preview_{tid}.html?v=...; saw {srcs}")


def _safe_title(f):
    try:
        return f.frame_element().get_attribute("title")
    except Exception:
        return None


def _select_doc(page, timeout=20):
    end = time.time() + timeout
    while time.time() < end:
        for f in page.frames[1:]:
            if _safe_title(f) == "WebForge generated preview":
                try:
                    if f.frame_element().get_attribute("srcdoc"):
                        return f
                except Exception:
                    pass
        time.sleep(0.3)
    raise AssertionError("Select-mode preview (srcdoc) never loaded")


@step("5 select a card -> edit pocket -> annotation chip")
def s5(page, ctx):
    page.locator(".st-key-webforge_preview_mode_control").get_by_text("Select").click()
    doc = _select_doc(page)
    card = doc.get_by_text("Morning Tide Ethiopia").first
    card.wait_for(timeout=15_000)
    t_click = time.time()
    card.click()
    pocket = None
    end = time.time() + 10
    while time.time() < end and pocket is None:
        for f in page.frames:
            loc = f.locator("#modificationRequest")
            try:
                if loc.count() and loc.is_visible():
                    pocket = f
                    break
            except Exception:
                pass
        time.sleep(0.3)
    assert pocket is not None, "edit pocket did not open after clicking the card"
    ctx["select_s"] = time.time() - t_click
    ctx["target"] = pocket.locator("#selectedName").inner_text(timeout=2000)
    pocket.locator("#modificationRequest").fill(
        'Change "Morning Tide Ethiopia" to "Dark Tide Ethiopia".')
    pocket.locator("#submitModification").click()
    page.get_by_text(re.compile(r"Annotation 1")).wait_for(timeout=10_000)


@step("6 sending the chip runs a modify with the clicked target")
def s6(page, ctx):
    ctx["modify_t0"] = _clock(ctx)
    _send(page, "do it")
    page.get_by_text("The selected component has been updated").first.wait_for(timeout=120_000)
    db = sqlite3.connect(ctx["db"])
    from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
    typ, blob = db.execute(
        "select type, checkpoint from checkpoints where thread_id=? "
        "order by checkpoint_id desc limit 1", (ctx["tid"],)).fetchone()
    msgs = JsonPlusSerializer().loads_typed((typ, blob))["channel_values"]["messages"]
    human = [m.content for m in msgs if m.type == "human"][-1]
    fields = contract.modify_marker_fields(human)
    target, instance = fields.get("target_component"), fields.get("target_instance")
    assert target and instance, f"last user message carries no modify marker: {human[:120]!r}"
    # Byte for byte the contract's format: what the panel wrote is what
    # format_modify_marker gives, so the orchestrator parses what the UI sends.
    assert human.startswith(contract.format_modify_marker(target, instance, "")), (
        f"the panel's marker drifted from the contract: {human[:120]!r}")
    ctx["marker_target"] = target


@step("7 preview shows the modified page without a reload")
def s7(page, ctx):
    end = time.time() + 15
    while time.time() < end:
        doc = _select_doc(page)
        srcdoc = doc.frame_element().get_attribute("srcdoc") or ""
        if "Dark Tide Ethiopia" in srcdoc:
            ctx["modify_preview_s"] = _clock(ctx) - ctx["modify_t0"]
            return
        time.sleep(0.5)
    raise AssertionError("preview still shows the old text 15 s after the modify finished")


@step("8 reload keeps conversation and page")
def s8(page, ctx):
    page.reload()
    page.get_by_text("Confirmed, continue with the brief.").wait_for(timeout=90_000)
    page.get_by_text("The selected component has been updated").first.wait_for()
    assert any(_safe_title(f) == "WebForge generated preview" for f in page.frames[1:]), \
        "preview panel missing after reload"


@step("9 New chat is empty and the old thread stays listed")
def s9(page, ctx):
    page.locator(".st-key-btn_new_chat button").click()
    page.get_by_text("What storefront should we").wait_for(timeout=30_000)
    assert page.locator(f".st-key-thread_{ctx['tid']}").count() == 1, \
        "first thread vanished from the sidebar"
    thread_btn = page.locator(f".st-key-thread_{ctx['tid']} button")
    page.wait_for_timeout(1500)  # sidebar settles after the rerun
    info = thread_btn.evaluate(
        "b => { const r = b.getBoundingClientRect();"
        " const t = document.elementFromPoint(r.x + r.width/2, r.y + r.height/2);"
        " return [Math.round(r.x), Math.round(r.y), Math.round(r.width),"
        " Math.round(r.height), !!t && b.contains(t),"
        " t ? t.tagName + '.' + String(t.className).slice(0, 40) : null]; }")
    ctx["thread_btn"] = info
    # Click where a person would: the middle of the visible icon, real mouse.
    page.mouse.click(info[0] + info[2] / 2, info[1] + info[3] / 2)
    try:
        page.get_by_text("Confirmed, continue with the brief.").wait_for(timeout=10_000)
    except Exception as e:
        raise AssertionError(
            f"clicking the old chat's icon did not open it; box/top-element {info}") from e
    page.get_by_text("Confirmed, continue with the brief.").wait_for(timeout=30_000)


STEPS = (s1, s2, s3, s4, s5, s6, s7, s8, s9)


def run_flow(url=None, headed=False, speed="0.3", after_step=None):
    """Start the mock app (unless ``url`` is given) and run every step.

    ``after_step(index, page, ctx)`` runs after each step that PASSED, with the
    page still in that step's end state. Returns ``(ctx, RESULTS)``.
    """
    from playwright.sync_api import sync_playwright

    RESULTS.clear()
    proc = None
    tmp = tempfile.mkdtemp(prefix="webforge_ui_")
    db = os.path.join(tmp, "threads.db")
    if url:
        db = str(ROOT / "logs" / "mock_threads.db")
    else:
        port = _free_port()
        url = f"http://localhost:{port}"
        env = dict(os.environ, WEBFORGE_MOCK_SPEED=speed, WEBFORGE_MOCK_DB=db,
                   WEBFORGE_PREVIEW_SERVER_PORT=str(_free_port()))
        proc = subprocess.Popen(
            [sys.executable, "-m", "streamlit", "run", str(ROOT / "tools" / "mock_ui.py"),
             "--server.port", str(port), "--server.headless", "true"],
            cwd=str(ROOT), env=env, stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)
        _wait_http(url, 60)

    ctx = {"db": db}
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=not headed)
            page = browser.new_page(viewport={"width": 1440, "height": 900})
            page.goto(url)
            for i, s in enumerate(STEPS, 1):
                try:
                    s(page, ctx)
                except Exception:
                    if s in (s1, s2, s3):
                        break  # later steps need the build
                    continue
                if after_step:
                    h = time.time()
                    after_step(i, page, ctx)
                    ctx["hook_s"] = ctx.get("hook_s", 0.0) + time.time() - h
            browser.close()
    finally:
        if proc:
            proc.terminate()
        tid = ctx.get("tid")
        if tid and proc:
            for ext in ("html", "css", "js"):
                (ROOT / "static" / "preview" / f"preview_{tid}.{ext}").unlink(missing_ok=True)
    return ctx, RESULTS


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url")
    ap.add_argument("--headed", action="store_true")
    ap.add_argument("--speed", default="0.3", help="WEBFORGE_MOCK_SPEED for the server")
    args = ap.parse_args()

    t0 = time.time()
    ctx, _ = run_flow(args.url, args.headed, args.speed)

    ok = sum(1 for r in RESULTS if r[1])
    print(f"\n{ok}/{len(STEPS)} passed in {time.time() - t0:.0f}s"
          + (f"; build turn {ctx['build_s']:.1f}s" if "build_s" in ctx else "")
          + (f"; clicked {ctx.get('target')!r} -> marker {ctx.get('marker_target')!r}"
             if "marker_target" in ctx else ""))
    sys.exit(0 if ok == len(STEPS) else 1)


if __name__ == "__main__":
    main()
