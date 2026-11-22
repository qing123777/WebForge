"""The one shared Chromium and the one Playwright worker thread that touches it."""
from __future__ import annotations


# ==========================================================================
# Browser setup and helper functions
# ==========================================================================
# ── Browser setup ─────────────────────────────────────────────────────────────
_browser_instance = None
_pages: dict      = {}

def _get_browser():
    global _browser_instance
    if _browser_instance is None:
        import os, sys, asyncio
        # Windows + Jupyter: the kernel installs a Selector event-loop policy,
        # but Playwright's worker-thread loop must be a Proactor loop to spawn
        # the browser subprocess (a Selector loop raises NotImplementedError on
        # subprocess launch). Force Proactor for NEW loops here; the kernel's
        # already-running loop is untouched, so the kernel keeps working.
        if sys.platform == "win32":
            asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
        from playwright.sync_api import sync_playwright
        _pw               = sync_playwright().start()
        # WEBFORGE_HEADED=1 opens a visible browser window (watch the test run);
        # unset or "0" runs headless (default, faster, no window). Read here so a
        # single env var flips it with no code change, from notebook or Streamlit.
        _headed           = os.environ.get("WEBFORGE_HEADED") == "1"
        # --allow-file-access-from-files is what lets a file:// page read the
        # cssRules of a file:// stylesheet. Without it Chromium raises
        # SecurityError, _sweep_dead_selectors swallows it in its own
        # `catch (e) { continue; }` and returns [], and an empty list is
        # indistinguishable from a clean page. That sweep therefore reported
        # nothing on every real run from 2026-08-24 until this line was added
        # on 2026-08-31. Same page, same sweep, only the flag different:
        # PO-08 po01e9a8b4 went from 0 findings to 7 dead selectors.
        _browser_instance = _pw.chromium.launch(
            headless=not _headed,
            args=["--allow-file-access-from-files"])
    return _browser_instance


import concurrent.futures as _cf
_pw_executor = None   # one dedicated Playwright thread; created lazily


class PlaywrightHung(Exception):
    """`_pw_run` gave up: the worker did not answer within the deadline."""


def _playwright_children() -> list:
    """This process's Playwright processes: the driver and the browsers it
    launched. Empty when psutil is missing, so callers fail open."""
    try:
        import psutil
    except ImportError:
        return []
    found = []
    try:
        children = psutil.Process().children(recursive=True)
    except psutil.Error:
        return []
    for proc in children:
        try:
            line = " ".join(proc.cmdline()).lower()
        except psutil.Error:
            continue
        if "playwright" in line:      # .../playwright/driver/... and .../ms-playwright/...
            found.append(proc)
    return found


def _abandon_browser() -> None:
    """Drop the browser and the worker thread after a hang, so the next call
    starts clean.

    The worker is stuck inside a sync Playwright call that waits on a page
    that will never answer, and Playwright's objects may only be touched from
    that thread, so nothing can be closed politely from here. Killing the
    processes is the one thing another thread can do: the stuck call then
    raises, the thread ends, and a spinning renderer stops using a core. On
    PO-08 7141dce4 that renderer had used 428 CPU-seconds in six minutes.
    """
    global _browser_instance, _pw_executor
    for proc in _playwright_children():
        try:
            proc.kill()
        except Exception:
            pass
    _browser_instance = None
    if _pw_executor is not None:
        # cancel_futures: a run queued behind the hung one must not start
        # later on this abandoned thread and bind a new browser to it.
        _pw_executor.shutdown(wait=False, cancel_futures=True)
        _pw_executor = None


class _Abandoned(BaseException):
    """Raised INSIDE the worker thread to end an abandoned run. A
    BaseException on purpose: the suite wraps its Playwright calls in
    `except Exception`, which must not swallow it."""


def _stop_worker(ident, future, tries: int = 40) -> bool:
    """End the abandoned worker thread. True once its call has returned.

    Killing the browser is not enough. With the driver gone, Playwright's
    dispatcher greenlet is finished, and the next sync call the suite makes
    (it carries on after a failed action) sits in
    `while not task.done(): dispatcher.switch()` for ever: a pure-Python busy
    loop that holds the GIL. Seen here: the thread span in page.reload and a
    package import on the main thread took over two minutes. Python has no
    thread kill; the supported way to interrupt Python-level code in another
    thread is to schedule an exception in it, which is what this does, again
    until the call has unwound.
    """
    import ctypes
    import time
    if ident is None:
        return False
    for _ in range(tries):
        if future.done():
            return True
        ctypes.pythonapi.PyThreadState_SetAsyncExc(
            ctypes.c_ulong(ident), ctypes.py_object(_Abandoned))
        time.sleep(0.25)
    return future.done()


_retired_loops: list = []


def _retire_loop(loop) -> None:
    """Make the abandoned Playwright event loop safe to forget.

    The loop still holds reads on the pipes of the driver that was just
    killed. When it is garbage-collected, `BaseEventLoop.__del__` closes it,
    and on Windows `IocpProactor.close` then polls until every pending
    operation completes, which these never do: the collection happened on
    the main thread in the middle of an import and blocked it for good. So
    the loop is marked closed, its proactor's port is dropped so that close
    returns at once, and a reference is kept so nothing is torn down half
    way. One leaked port per hang.
    """
    if loop is None:
        return
    try:
        proactor = getattr(loop, "_proactor", None)
        if proactor is not None and hasattr(proactor, "_iocp"):
            proactor._iocp = None
        loop._closed = True
    except Exception:
        pass
    _retired_loops.append(loop)


def _pw_run(fn, timeout=None, heartbeat=None):
    """Run `fn` on the dedicated Playwright worker thread and return its result.

    Playwright's SYNC API refuses to start inside a running asyncio loop (a
    Jupyter kernel always has one). A worker thread has no running loop, so the
    sync API works there — from a notebook, Streamlit, or a plain script alike.
    Using ONE persistent thread also keeps the cached browser warm across calls,
    since the browser lives in (and is only touched from) that single thread.

    `timeout` (seconds) is how long `fn` may go WITHOUT PROGRESS. `heartbeat`
    returns the time.monotonic() of fn's last sign of progress; without it,
    the clock starts when fn starts running (not when it was queued). When
    the limit passes with fn still running, the browser is abandoned (see
    _abandon_browser) and PlaywrightHung is raised. None waits for ever, as
    before.
    """
    global _pw_executor
    if _pw_executor is None:
        _pw_executor = _cf.ThreadPoolExecutor(max_workers=1,
                                              thread_name_prefix="playwright")
    import threading
    import time
    _ident = []
    _started = []

    def _on_worker():
        _ident.append(threading.get_ident())
        _started.append(time.monotonic())
        return fn()

    future = _pw_executor.submit(_on_worker)
    if timeout is None:
        return future.result()
    while True:
        try:
            return future.result(timeout=1.0)
        except _cf.TimeoutError:
            if future.done():         # finished in the gap: return its outcome
                return future.result()
        if not _started:              # still queued behind another run
            continue
        last = max(_started[0], heartbeat() if heartbeat else 0.0)
        if time.monotonic() - last > timeout:
            break
    _loop = getattr(_browser_instance, "_loop", None)
    _abandon_browser()
    if not _stop_worker(_ident[0] if _ident else None, future):
        import sys
        print("[test_exec] WARNING: the abandoned Playwright worker did not stop; "
              "a browser may still be running. Is psutil installed?",
              file=sys.stderr, flush=True)
    _retire_loop(_loop)
    raise PlaywrightHung(f"no progress from the browser for {timeout} s")


# Every name this module defines or imports, for the package's __init__ and
# from there for webforge.test_exec, which re-exports it into the load order.
__all__ = [_n for _n in list(globals())
           if not (_n.startswith("__") and _n.endswith("__"))]
