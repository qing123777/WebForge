"""Three UI feedback checks on the zero-credit mock, each one a number.

    python tools/ui_feedback.py            # starts its own mock app, headless
    python tools/ui_feedback.py --headed

Found by watching the real app on the 2026-11-10 PO-08 run (session 4fb17fbe):

  F1 echo      After Enter, the chat showed nothing for ~8 s: the input cleared
               but the message did not appear. Measured: seconds from Enter until
               the user's own text is in the chat. Pass: under 2 s, while the
               backend is still loading (the real import takes ~26 s).
  F2 preview   The Preview panel said "no preview" until the run ended, though
               the HTML was on disk from minute 10. Measured: does this thread's
               preview iframe appear BEFORE the final reply? Pass: yes.
  F3 round     The correction round re-used the ticked HTML/CSS/JS rows, so
               nothing showed a second pass was running. Measured: does the live
               status box show a "Correction round" row? Pass: yes.

The mock runs with WEBFORGE_MOCK_LOAD_S, WEBFORGE_MOCK_STAGED_FILES and
WEBFORGE_MOCK_CORRECTION (tools/mock_backend.py), which make it load, write
files and correct the way the real backend does. Exit 1 on any FAIL.
"""
import argparse
import os
import re
import subprocess
import sys
import tempfile
import time

from ui_smoke import ROOT, _free_port, _wait_http, _composer

BRIEF = "Build a storefront for a specialty coffee roaster selling whole beans."
FINAL = "The storefront is ready in Preview"

# Installed in the page before a send. Every timer runs in the page itself
# (50 ms poll), so it times what the user sees, not when Python looked.
_WATCH = r"""([tid, brief, finalText]) => {
    if (window.__wfTimer) clearInterval(window.__wfTimer);   // one watcher at a time
    const t0 = performance.now();
    const s = () => (performance.now() - t0) / 1000;
    window.__wf = {echo: null, preview: null, round: null, final: null};
    const want = 'preview_' + tid + '.html?v=';
    const hasPreview = doc => {
        for (const f of doc.querySelectorAll('iframe')) {
            if ((f.getAttribute('src') || '').includes(want)) return true;
            try { if (f.contentDocument && hasPreview(f.contentDocument)) return true; }
            catch (e) {}
        }
        return false;
    };
    const timer = window.__wfTimer = setInterval(() => {
        const w = window.__wf;
        const msgs = [...document.querySelectorAll('[data-testid="stChatMessage"]')];
        if (w.echo === null && msgs.some(m => m.innerText.includes(brief))) w.echo = s();
        if (w.preview === null && hasPreview(document)) w.preview = s();
        if (w.round === null && [...document.querySelectorAll('.wf-st-box')]
                .some(b => b.innerText.toLowerCase().includes('correction round'))) w.round = s();
        if (w.final === null && msgs.some(m => m.innerText.includes(finalText))) w.final = s();
        if (w.final !== null && w.preview !== null) clearInterval(timer);
    }, 50);
}"""


def run(headed=False, speed="0.3", load_s="12"):
    from playwright.sync_api import sync_playwright

    tmp = tempfile.mkdtemp(prefix="webforge_fb_")
    port = _free_port()
    url = f"http://localhost:{port}"
    env = dict(os.environ, WEBFORGE_MOCK_SPEED=speed,
               WEBFORGE_MOCK_DB=os.path.join(tmp, "threads.db"),
               WEBFORGE_PREVIEW_SERVER_PORT=str(_free_port()),
               WEBFORGE_MOCK_LOAD_S=load_s, WEBFORGE_MOCK_STAGED_FILES="1",
               WEBFORGE_MOCK_CORRECTION="1")
    proc = subprocess.Popen(
        [sys.executable, "-m", "streamlit", "run", str(ROOT / "tools" / "mock_ui.py"),
         "--server.port", str(port), "--server.headless", "true"],
        cwd=str(ROOT), env=env, stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)
    out, tid = {}, None
    try:
        _wait_http(url, 60)
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=not headed)
            page = browser.new_page(viewport={"width": 1440, "height": 900})
            t_open = time.time()
            page.goto(url)
            page.get_by_text("What storefront should we").wait_for(timeout=90_000)
            box = page.get_by_placeholder("Message WebForge...")
            box.wait_for(timeout=30_000)
            tid = re.search(r"[?&]t=([\w-]+)", page.url).group(1)

            # F1: send at once, as a person does, while the backend still loads.
            box.click()
            box.fill(BRIEF)
            page.evaluate(_WATCH, [tid, BRIEF, FINAL])
            out["sent_after_open_s"] = time.time() - t_open
            box.press("Enter")
            page.wait_for_function("() => window.__wf.echo !== null", timeout=120_000)
            out["echo_s"] = page.evaluate("() => window.__wf.echo")

            # F2 + F3: the build, after the mock's one clarifying question.
            page.get_by_text("Confirm and continue").wait_for(timeout=120_000)
            page.evaluate(_WATCH, [tid, BRIEF, FINAL])
            page.get_by_text("Confirm and continue").click()
            page.wait_for_function("() => window.__wf.final !== null", timeout=240_000)
            page.wait_for_timeout(3000)       # a preview may land just after
            w = page.evaluate("() => window.__wf")
            out.update(preview_s=w["preview"], round_s=w["round"], final_s=w["final"])
            browser.close()
    finally:
        proc.terminate()
        if tid:
            for ext in ("html", "css", "js"):
                (ROOT / "static" / "preview" / f"preview_{tid}.{ext}").unlink(missing_ok=True)
    return out


def verdicts(out, load_s=None):
    e, p, r, f = (out.get(k) for k in ("echo_s", "preview_s", "round_s", "final_s"))
    load_s = float(load_s if load_s is not None else os.environ.get("FB_LOAD_S", "12"))
    # F1 only means something if the send happened WHILE the backend loaded. On
    # a slow machine the page may take longer than the load to appear; then the
    # echo is fast for the wrong reason, so the check refuses to pass.
    sent = out.get("sent_after_open_s")
    in_window = sent is not None and sent < load_s
    if sent is None or e is None:
        f1_why = "message never shown"
    elif not in_window:
        f1_why = (f"INVALID: sent {sent:.0f}s after the page opened, after the "
                  f"{load_s:.0f}s backend load had finished; raise --load-s")
    else:
        f1_why = (f"message shown {e:.1f}s after Enter (sent {sent:.0f}s after the "
                  f"page opened; backend load {load_s:.0f}s)")
    return [
        ("F1 echo", in_window and e is not None and e < 2.0, f1_why),
        ("F2 preview", p is not None and f is not None and p < f,
         f"preview at {p:.1f}s, final reply at {f:.1f}s" if p is not None and f is not None
         else f"preview {p}, final reply {f}"),
        ("F3 round", r is not None,
         f"'Correction round' shown at {r:.1f}s" if r is not None
         else "no 'Correction round' row during the run"),
    ]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--headed", action="store_true")
    ap.add_argument("--speed", default="0.3")
    ap.add_argument("--load-s", default="12")
    a = ap.parse_args()
    os.environ["FB_LOAD_S"] = a.load_s
    out = run(a.headed, a.speed, a.load_s)
    bad = 0
    for name, ok, why in verdicts(out):
        bad += not ok
        print(f"{'PASS' if ok else 'FAIL'}  {name:<11} {why}")
    print(f"[proof] {out}")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
