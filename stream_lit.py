"""Streamlit frontend for WebForge.

UI architecture
---------------
1. **Streaming.** ``st.chat_input`` submits a query and the frontend
   manually iterates ``bridge.stream_message`` so it can route the two
   kinds of stream events (real assistant tokens vs. orchestrator
   "processing" progress strings) to different UI containers.
2. **Always-visible sidebar.** Streamlit's native collapse (which fully
   hides the panel) is disabled. Instead the sidebar is forced to always
   render and toggles between two widths - expanded 280px and collapsed
   64px - driven by ``html.sidebar-collapsed`` on the document element.
3. **Custom edge toggle.** A small arrow button is fixed to the
   sidebar's right edge. JS flips ``html.sidebar-collapsed`` and
   persists to localStorage; CSS transitions move the sidebar and the
   button together. Arrow points LEFT when expanded (click to shrink),
   RIGHT when collapsed (click to expand).
4. **Client-side theme.** Both palettes ship in one stylesheet, scoped
   to ``html.dark`` / ``html.light`` (with the dark palette also set on
   ``:root`` as a default so the page is fully styled even before JS
   attaches a class). The theme toggle is pure JS, so flipping
   mid-stream never interrupts streaming.
5. **Sidebar WebForge heading.** A prominent brand mark sits above
    ``+ New Chat`` in the sidebar. When the sidebar collapses, only the
    circular icon remains visible.
6. **Persistent processing log.** Each assistant reply's intermediate
   "[Context Agent] Processing..." style strings are archived in
   ``st.session_state.processing_logs`` keyed by ``(thread_id, msg_idx)``
   so they survive ``st.rerun()`` and re-render in a collapsible
   ``st.expander`` next to the message on every subsequent visit.
"""

from __future__ import annotations

import ctypes
import os
import re
import socket
import threading
import time
import uuid
from functools import partial
from html import escape
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import quote

import streamlit as st
import streamlit.components.v1 as components

import bridge
import ui_assets
from webforge import config as _wf_config
from webforge import contract


# Same folders the agents write to: one definition in webforge/config.py.
_ROOT_DIR = _wf_config.REPO_ROOT
_PREVIEW_DIR = _wf_config.PREVIEW_DIR
_PREVIEW_TEST_SESSION_ID = "po0142c544"
_PREVIEW_SERVER_BASE_PORT = 8766
_PREVIEW_SERVER_PORT_KEY = "WEBFORGE_PREVIEW_SERVER_PORT"
# The Select panel builds the modify marker in the browser. The expression comes
# from the contract, so the panel writes what the orchestrator parses.
_MODIFY_MARKER_JS = contract.modify_marker_js("info.selector", "info.instance", "request")


st.set_page_config(
    page_title="WebForge - Chat",
    layout="wide",
    initial_sidebar_state="expanded",
)


@st.cache_resource
def _get_thread_restore_state() -> dict[str, object]:
    """Hold one non-blocking saved-thread restore across UI reruns."""
    return {
        "lock": threading.Lock(),
        "started": False,
        "done": False,
        "threads": {},
        "error": None,
        "worker": None,
    }


def _ensure_thread_restore_started() -> None:
    """Restore saved conversations without blocking the first page render."""
    state = _get_thread_restore_state()
    with state["lock"]:
        if state["started"]:
            return
        state["started"] = True

        def _restore_threads() -> None:
            restored: dict[str, str] = {}
            error: Exception | None = None
            try:
                restored = bridge.list_threads()
            except Exception as exc:  # pragma: no cover - defensive fallback
                error = exc
            with state["lock"]:
                state["threads"] = restored
                state["error"] = error
                state["done"] = True

        worker = threading.Thread(
            target=_restore_threads,
            name="webforge-thread-restore",
            daemon=True,
        )
        state["worker"] = worker

    worker.start()


def _thread_restore_snapshot() -> dict[str, object]:
    """Return a detached view of the background restore state."""
    state = _get_thread_restore_state()
    with state["lock"]:
        return {
            "done": bool(state["done"]),
            "threads": dict(state["threads"]),
            "error": state["error"],
        }


# First-paint boot curtain. The initial script run blocks on bridge.list_threads()
# used to stay up while bridge.list_threads() synchronously built the backend and
# restored up to 30 complete LangGraph states. Thread restoration now runs in the
# background, so this curtain only covers the brief first paint until the custom
# chrome attaches. Rendered once per session (first run only); the dismiss script
# at the very end adds `wf-booted` to <html>, fading it out. A browser refresh
# starts a fresh session, so the curtain shows again on reload.
if not st.session_state.get("_wf_boot_curtain_shown"):
    st.session_state._wf_boot_curtain_shown = True
    st.markdown(
        """
        <style>
        #wf-boot-overlay {
            position: fixed; inset: 0; z-index: 2147483647;
            background: #050505;
            display: flex; flex-direction: column;
            align-items: center; justify-content: center; gap: 20px;
            font-family: Inter, system-ui, -apple-system, sans-serif;
            transition: opacity .5s ease;
        }
        html.wf-booted #wf-boot-overlay { opacity: 0; pointer-events: none; }
        #wf-boot-overlay .wf-boot-mark {
            width: 48px; height: 48px; border-radius: 14px;
            display: flex; align-items: center; justify-content: center;
            background: linear-gradient(135deg, #d9741f 0%, #f6ac66 100%);
            border: 1px solid rgba(255, 255, 255, 0.18);
            box-shadow: 0 10px 34px rgba(224, 128, 54, .30);
        }
        #wf-boot-overlay .wf-boot-mark svg { width: 27px; height: 27px; display: block; }
        #wf-boot-overlay .wf-boot-name {
            color: #f4f4f5; font-size: 18px; font-weight: 600; letter-spacing: .2px;
        }
        #wf-boot-overlay .wf-boot-name b { color: #e6893f; font-weight: 700; }
        #wf-boot-overlay .wf-boot-spin {
            width: 24px; height: 24px; border-radius: 50%;
            border: 2px solid rgba(255, 255, 255, .14);
            border-top-color: #e6893f;
            animation: wf-boot-rot .7s linear infinite;
        }
        @keyframes wf-boot-rot { to { transform: rotate(360deg); } }
        </style>
        <div id="wf-boot-overlay" role="status" aria-label="Loading WebForge">
            <div class="wf-boot-mark">
                <svg viewBox="0 0 24 24" fill="none" stroke="#ffffff" stroke-width="2"
                     stroke-linecap="round" stroke-linejoin="round">
                    <path d="M12 3l9 4-9 4-9-4z"></path>
                    <path d="M3 12l9 4 9-4M3 17l9 4 9-4"></path>
                </svg>
            </div>
            <div class="wf-boot-name">Web<b>Forge</b></div>
            <div class="wf-boot-spin"></div>
        </div>
        """,
        unsafe_allow_html=True,
    )


# ---------------------------------------------------------------------------
# 1. Session state.
# ---------------------------------------------------------------------------
if "threads" not in st.session_state or "active_thread" not in st.session_state:
    # Paint a usable shell immediately. Saved conversations are merged in by the
    # polling fragment below after the background restore completes; doing those
    # graph.get_state(...) reads here used to freeze the boot page for minutes.
    _url_tid = st.query_params.get("t")
    if _url_tid:
        _threads = {_url_tid: bridge.PLACEHOLDER_LABEL}
        _active = _url_tid
    else:
        _init = bridge.initialize_session()
        _active = _init["active_thread"]
        _threads = _init["threads"]
    st.session_state.active_thread = _active
    st.session_state.threads = _threads
    st.session_state._thread_restore_seed_id = _active
    st.session_state._thread_restore_applied = False
    st.query_params["t"] = _active


_ensure_thread_restore_started()


@st.fragment(run_every="2s")
def _poll_thread_restore() -> None:
    """Merge restored chats once, then stop polling with a full UI rerun."""
    if st.session_state.get("_thread_restore_applied"):
        return
    snapshot = _thread_restore_snapshot()
    if not snapshot["done"]:
        return

    restored = snapshot["threads"]
    if isinstance(restored, dict) and restored:
        current = dict(st.session_state.get("threads", {}))
        merged = dict(restored)
        merged.update(current)

        # With no thread pinned in the incoming URL, preserve the old behaviour
        # of opening the most recent saved chat. Only replace the temporary seed
        # if the user has not already moved to or started another conversation.
        seed_id = st.session_state.get("_thread_restore_seed_id")
        active_id = st.session_state.get("active_thread")
        can_replace_seed = (
            active_id == seed_id
            and not st.session_state.get("active_run_id")
            and not st.session_state.get("thread_messages", {}).get(seed_id)
        )
        if can_replace_seed and seed_id not in restored:
            merged.pop(seed_id, None)
            active_id = next(iter(restored))
            st.session_state.active_thread = active_id
            st.query_params["t"] = active_id

        st.session_state.threads = merged

    st.session_state._thread_restore_applied = True
    st.rerun()


_poll_thread_restore()

if "processing_logs" not in st.session_state:
    st.session_state.processing_logs = {}

# Per-agent timings for a FINISHED run, keyed by (thread_id, msg_idx), same as
# processing_logs. The live status box reads stage_times off the active run, but
# that run is discarded when it completes; persisting it here lets the finished
# "Steps" view show each agent's own seconds after the run is over.
if "stage_time_logs" not in st.session_state:
    st.session_state.stage_time_logs = {}

# Which conversations' pages the user has already downloaded this session. The
# delete guard warns before removing a page that is not in this set.
if "webforge_downloaded" not in st.session_state:
    st.session_state.webforge_downloaded = set()


# Progress verbosity. Only high-level milestones reach the UI; low-level tool
# detail is filtered out by contract.is_detail_step (webforge/contract.py).


def _visible_steps(steps):
    """Return the progress steps to show, dropping low-level tool detail."""
    steps = steps or []
    return [s for s in steps if not contract.is_detail_step(s)]


# Live "generating" box. The pretty timeline is a PROJECTION of the real
# processing-step strings, never a script of its own: each stage row and the
# live line come straight from what the graph streamed.
#
# Which stage a line is about, the canonical stage order, the three parallel
# stages and the 'gave up' markers are the progress-event contract:
# contract.stage_label, STAGE_ORDER, PARALLEL_STAGES, is_warning.

_STREAM_STATUS_CSS = """
<style>
.wf-st-box{background:var(--assistant-bubble);border:1px solid rgba(230,137,63,.5);
  border-radius:13px;padding:11px 13px;margin-bottom:6px}
.wf-st-title{display:flex;align-items:center;gap:8px;font-weight:600;font-size:13px;
  color:var(--text-primary);margin-bottom:8px}
.wf-st-spin{width:13px;height:13px;border:2px solid rgba(230,137,63,.3);
  border-top-color:#e6893f;border-radius:50%;display:inline-block;flex:0 0 auto;
  animation:wf-st-spin 1s linear infinite}
.wf-st-row{display:flex;align-items:center;gap:9px;font-size:12.5px;padding:2px 0}
.wf-st-name{flex:1 1 auto;min-width:0}
.wf-st-dur{flex:0 0 auto;font-size:11.5px;color:var(--text-muted);
  font-variant-numeric:tabular-nums;padding-left:8px}
.wf-st-r-now .wf-st-dur{color:#e6893f}
.wf-st-dot{width:15px;height:15px;border-radius:50%;flex:0 0 auto;display:flex;
  align-items:center;justify-content:center}
.wf-st-dot svg{width:9px;height:9px}
.wf-st-done{background:rgba(91,191,123,.14)}
.wf-st-now{border:2px solid #e6893f;animation:wf-st-pulse 1.2s ease-in-out infinite}
.wf-st-r-done{color:var(--text-muted)}
.wf-st-r-now{color:var(--text-primary);font-weight:600}
.wf-st-par{border-left:2px solid rgba(230,137,63,.6);margin:3px 0 3px 6px;
  padding-left:11px}
.wf-st-par-h{display:flex;align-items:center;gap:7px;font-size:10.5px;
  letter-spacing:.05em;text-transform:uppercase;color:#e6893f;padding:3px 0 4px}
.wf-st-par-i{width:13px;height:13px;flex:0 0 auto}
.wf-st-round{font-size:10.5px;letter-spacing:.05em;text-transform:uppercase;
  color:#e6893f;margin:7px 0 2px;padding-top:6px;border-top:1px dashed rgba(230,137,63,.45)}
.wf-st-live{display:flex;align-items:flex-start;gap:7px;margin-top:9px;line-height:1.5;
  font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Inter,Roboto,Arial,sans-serif;
  font-size:12px;color:var(--text-secondary);border-top:1px solid var(--border);
  padding-top:9px;word-break:break-word}
.wf-st-ld{width:6px;height:6px;border-radius:50%;background:#e6893f;flex:0 0 auto;
  margin-top:4px;animation:wf-st-pulse 1.1s ease-in-out infinite}
.wf-st-warn{color:#e6893f}
.wf-st-timer{display:flex;align-items:center;margin-top:9px;
  font-size:11.5px;color:var(--text-muted);font-variant-numeric:tabular-nums}
/* Finished-run per-agent timeline: same rows as the live box, but quiet -- no
   orange border/fill, sits inside the "Steps" expander above the raw log. */
.wf-st-fin{background:transparent;border:none;border-radius:0;padding:0;
  margin:0 0 8px 0;border-bottom:1px solid var(--border);padding-bottom:6px}
.wf-st-fin .wf-st-timer{margin-top:6px}
.wf-st-rawlog{margin-top:9px;border-top:1px solid var(--border);padding-top:9px}
.wf-st-rawlog>summary{cursor:pointer;font-size:12px;color:var(--text-muted);
  list-style:none;user-select:none}
.wf-st-rawlog>summary::-webkit-details-marker{display:none}
.wf-st-rawlog>summary::before{content:"\\25b8 ";color:var(--text-muted)}
.wf-st-rawlog[open]>summary::before{content:"\\25be "}
.wf-st-rawlog .wf-fin-log{max-height:150px;overflow:auto;margin-top:7px}
@keyframes wf-st-spin{to{transform:rotate(360deg)}}
@keyframes wf-st-pulse{0%,100%{opacity:1}50%{opacity:.3}}
@media (prefers-reduced-motion:reduce){
  .wf-st-spin,.wf-st-now,.wf-st-ld{animation:none!important}
}
</style>
"""


_CORRECTION_ROW = "Correction round"
# A round opens only on the orchestrator's own "Calling X Agent" line AFTER the
# tests really ran. "Running Playwright test suite" is printed only past the
# cap and refusal checks; the agents' own lines (an in-flight "[CSS Agent]
# Linting..." from a parallel batch) never open one.
_TESTS_RAN = "[Test Execution Pipeline] Running Playwright test suite"
_RECALL = re.compile(r"\[Secondary Orchestrator\] Calling (HTML|CSS|JS) Agent")


def _stream_timeline(steps):
    """Project already-filtered step strings into the live status view.

    Returns ``(rows, live_line, live_warn)``:
      * ``rows``      - ``[(label, "done"|"now")]`` in canonical order, only for
                        stages that actually appeared; the most-recent stage is
                        ``"now"`` and every earlier one ``"done"``. No fabricated
                        "pending" rows, so a modify run that never touches CSS/JS
                        simply never shows them.
      * ``live_line`` - the newest step, verbatim (or ``""``).
      * ``live_warn`` - True when that newest line reports a given-up fix.

    The orchestrator calling a developer agent again AFTER the tests ran is the
    correction round: its stages get their own block under a ``("Correction
    round", "header")`` row, instead of landing on the first pass's ticked rows,
    where nothing showed that a second pass was running.
    """
    steps = [str(s) for s in (steps or []) if str(s).strip()]
    rounds: list[list[str]] = [[]]
    current = None
    tested = False      # the tests really ran in the current round
    for s in steps:
        m = re.match(r"\s*\[([^\]]+)\]", s)
        if not m:
            continue
        if _TESTS_RAN in s:
            tested = True
        elif tested and _RECALL.search(s):
            rounds.append([])
            tested = False
        label = contract.stage_label(s)
        if label:
            if label not in rounds[-1]:
                rounds[-1].append(label)
            current = (len(rounds) - 1, label)
    rows = []
    for i, seen in enumerate(rounds):
        if i:
            rows.append((_CORRECTION_ROW if i == 1 else f"{_CORRECTION_ROW} {i}", "header"))
        rows += [
            (label, "now" if current == (i, label) else "done")
            for label in contract.STAGE_ORDER
            if label in seen
        ]
    live_line = steps[-1].strip() if steps else ""
    live_warn = contract.is_warning(live_line)
    return rows, live_line, live_warn


def _fmt_elapsed(seconds: float) -> str:
    """Elapsed as ``Ns`` under a minute, ``Xm Ys`` under an hour, else ``Xh Ym Zs``."""
    secs = max(0, int(seconds))
    if secs < 60:
        return f"{secs}s"
    if secs < 3600:
        return f"{secs // 60}m {secs % 60}s"
    return f"{secs // 3600}h {(secs % 3600) // 60}m {secs % 60}s"


# A right-pointing "one flow splits into branches" glyph (Tabler arrows-split-2),
# orange, used as the Parallel build header icon.
_PAR_ICON = (
    '<svg class="wf-st-par-i" viewBox="0 0 24 24" fill="none" stroke="#e6893f" '
    'stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
    '<path d="M21 17h-8l-3.5 -5h-6.5"/><path d="M21 7h-8l-3.5 5"/>'
    '<path d="M18 10l3 -3l-3 -3"/><path d="M18 20l3 -3l-3 -3"/></svg>'
)
_STEP_TICK = (
    '<svg viewBox="0 0 24 24" fill="none" stroke="#5bbf7b" stroke-width="3" '
    'stroke-linecap="round" stroke-linejoin="round"><path d="M20 6L9 17l-5-5"/></svg>'
)


def _steps_rows_html(rows) -> str:
    """Render ``[(label, "done"|"now")]`` as name + status ONLY, no times.

    The three concurrent stages (``contract.PARALLEL_STAGES``) are wrapped in one
    "Parallel build" bracket. They are contiguous in ``contract.STAGE_ORDER``, so
    the group opens at the first of them seen and closes at the next non-parallel
    stage (Test Execution Pipeline) or at the end.
    """
    def _row(label: str, state: str) -> str:
        if state == "done":
            dot = f'<span class="wf-st-dot wf-st-done">{_STEP_TICK}</span>'
            cls = "wf-st-row wf-st-r-done"
        else:
            dot = '<span class="wf-st-dot wf-st-now"></span>'
            cls = "wf-st-row wf-st-r-now"
        return f'<div class="{cls}">{dot}<span class="wf-st-name">{escape(label)}</span></div>'

    out: list[str] = []
    in_par = False
    for label, state in rows:
        if state == "header":
            if in_par:
                out.append('</div>')
                in_par = False
            out.append(f'<div class="wf-st-round">{escape(label)}</div>')
            continue
        is_par = label in contract.PARALLEL_STAGES
        if is_par and not in_par:
            out.append('<div class="wf-st-par"><div class="wf-st-par-h">'
                       + _PAR_ICON + 'Parallel build</div>')
            in_par = True
        elif not is_par and in_par:
            out.append('</div>')
            in_par = False
        out.append(_row(label, state))
    if in_par:
        out.append('</div>')
    return "".join(out)


def _render_stream_status(vis_steps, started_at=None, stage_times=None) -> None:
    """Draw the live 'generating' box for the message being generated RIGHT NOW.

    Layers, all from the same stream: an agent timeline (which stage is live) as
    names + a check/spinner ONLY -- no per-stage seconds and no overall timer.
    The CSS/JS/Test Generation fan-out made per-stage durations meaningless (the
    first two always read a fake 0s), and dropping the ticking number also removes
    the timer afterimage. Then the newest raw line in full (amber if a fix was
    given up), and the complete raw log kept in the collapsed expander. The three
    concurrent stages are grouped under one "Parallel build" bracket.

    ``started_at`` / ``stage_times`` are accepted for call-site compatibility but
    no longer drive any on-screen time. The box's HTML now only changes when a
    real new step or token arrives; its CSS is injected once at module level, not
    here. Finished messages do not use this box.
    """
    rows, live_line, live_warn = _stream_timeline(vis_steps)

    # Names + status only, no times: the parallel fan-out (CSS/JS/Test Generation)
    # made per-stage seconds meaningless, and with no ticking number on screen the
    # timer afterimage cannot occur. _steps_rows_html brackets the parallel group.
    tl_html = _steps_rows_html(rows)

    live_html = ""
    if live_line:
        warn = " wf-st-warn" if live_warn else ""
        live_html = (f'<div class="wf-st-live{warn}"><span class="wf-st-ld"></span>'
                     f'{escape(live_line)}</div>')

    st.markdown(
        '<div class="wf-st-box">'
        + '<div class="wf-st-title"><span class="wf-st-spin"></span>'
        + 'WebForge is working&hellip;</div>'
        + tl_html
        + live_html
        + "</div>",
        unsafe_allow_html=True,
    )

    if vis_steps:
        # Raw log as a DIRECT fragment child (a native <details>), NOT
        # st.expander. An expander's nested body does not reliably re-render on
        # the periodic run_every reruns, so it froze on the first line while the
        # timeline and live line (direct children) kept updating. A plain
        # markdown element re-renders every tick like the live line, so the log
        # stays current. It is open by default so a streaming log stays visible;
        # its own scroll keeps the box compact.
        st.markdown(
            '<details class="wf-st-rawlog" open>'
            '<summary>Raw Log</summary>'
            + _finished_steps_html(vis_steps)
            + '</details>',
            unsafe_allow_html=True,
        )


def _finished_steps_html(steps) -> str:
    """Form A: a finished reply's steps as one dark mono log block.

    Lines are shown verbatim with their indentation kept, the same look as the
    live box's raw log, and any 'gave up' line (a cap / best-effort message) in
    amber. Rendered inside the quiet ``Steps . N`` expander that replaces the
    old grey Processing-details box. Steps come from our own writer() calls, but
    every line is html-escaped anyway.
    """
    out = []
    for s in steps:
        s = str(s).replace("\t", "   ").rstrip("\n")
        warn = contract.is_warning(s)
        stripped = s.lstrip(" ")
        indent = len(s) - len(stripped)
        line = ("&nbsp;" * indent) + escape(stripped)
        out.append(f'<span class="wf-fin-warn">{line}</span>' if warn else line)
    return '<div class="wf-fin-log">' + "<br>".join(out) + "</div>"


def _finished_timeline_html(stage_times, steps=None) -> str:
    """A finished run's agent list as a compact, static timeline: names + a check
    only, NO times.

    ``stage_times`` is used solely to know WHICH stages actually ran (a modify run
    that never touches CSS/JS simply omits them); the timestamps inside it are
    ignored now that no duration is shown. The three concurrent stages are
    bracketed under "Parallel build" by ``_steps_rows_html``. Returns ``""`` when
    there are no stages (an older run, or one that ended before any stage was
    seen), in which case the finished view just shows the raw log as before.
    """
    seen = {str(t["label"]) for t in (stage_times or []) if t.get("label")}
    if not seen:
        return ""
    if steps:
        # From the steps, so a correction round keeps its own block here too
        # (stage_times records each stage once, at its first appearance).
        rows = [(label, state if state == "header" else "done")
                for label, state in _stream_timeline(steps)[0]]
    else:
        rows = [(label, "done") for label in contract.STAGE_ORDER if label in seen]
    if not rows:
        return ""
    return '<div class="wf-st-box wf-st-fin">' + _steps_rows_html(rows) + "</div>"


class _PreviewRequestHandler(SimpleHTTPRequestHandler):
    """Serve generated preview files without noisy terminal logs."""

    def end_headers(self) -> None:
        self.send_header("Cache-Control", "no-store")
        self.send_header("Access-Control-Allow-Origin", "*")
        super().end_headers()

    def log_message(self, format: str, *args) -> None:  # noqa: A002
        return


def _is_port_alive(port: int) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=0.25):
            return True
    except OSError:
        return False


def _ensure_preview_server() -> int | None:
    """Start a local server for static/preview if one is not already alive."""
    if not _PREVIEW_DIR.exists():
        return None

    saved_port = os.environ.get(_PREVIEW_SERVER_PORT_KEY)
    if saved_port and saved_port.isdigit():
        port = int(saved_port)
        if _is_port_alive(port):
            return port

    handler = partial(_PreviewRequestHandler, directory=str(_PREVIEW_DIR))
    for port in range(_PREVIEW_SERVER_BASE_PORT, _PREVIEW_SERVER_BASE_PORT + 10):
        try:
            server = ThreadingHTTPServer(("127.0.0.1", port), handler)
        except OSError:
            continue
        thread = threading.Thread(
            target=server.serve_forever,
            name=f"webforge-preview-server-{port}",
            daemon=True,
        )
        thread.start()
        os.environ[_PREVIEW_SERVER_PORT_KEY] = str(port)
        return port

    return None


def _normalize_preview_session_id(raw: str | None) -> str | None:
    if not raw:
        return None
    value = raw.strip()
    if value.startswith("preview_"):
        value = value[len("preview_"):]
    if value.endswith(".html"):
        value = value[:-5]
    cleaned = "".join(ch for ch in value if ch.isalnum() or ch in ("_", "-"))
    return cleaned or None


def _preview_file_for_session(session_id: str | None) -> Path | None:
    normalized = _normalize_preview_session_id(session_id)
    if not normalized:
        return None
    path = _PREVIEW_DIR / f"preview_{normalized}.html"
    return path if path.exists() else None


def _current_preview_artifact() -> tuple[str, Path] | None:
    session_ids = [
        st.session_state.get("webforge_preview_session_id"),
        st.session_state.get("active_thread"),
    ]
    for session_id in session_ids:
        path = _preview_file_for_session(str(session_id) if session_id else None)
        if path:
            return (_normalize_preview_session_id(str(session_id)) or "", path)
    return None


def _preview_url_for(path: Path) -> str | None:
    port = _ensure_preview_server()
    if port is None:
        return None
    # The version tag changes whenever the page's html/css/js changes on disk.
    # Without it a modify rewrites the files under the SAME url, the iframe
    # markup is byte-identical, and the panel keeps showing the old page.
    version = max(
        (p.stat().st_mtime_ns for p in path.parent.glob(f"{path.stem}.*") if p.is_file()),
        default=0,
    )
    return f"http://127.0.0.1:{port}/{quote(path.name)}?v={version}"


def _preview_complete(session_id: str | None) -> bool:
    """True when the page's html, css AND js are all on disk.

    During a run the files land one agent at a time (HTML first, CSS and JS
    minutes later). The panel waits for all three, so it never shows an
    unstyled page as if it were the result."""
    normalized = _normalize_preview_session_id(str(session_id) if session_id else None)
    if not normalized:
        return False
    return all((_PREVIEW_DIR / f"preview_{normalized}.{ext}").exists()
               for ext in ("html", "css", "js"))


def _preview_files_present(session_id: str | None) -> bool:
    """True if a generated page exists on disk for this session/thread."""
    normalized = _normalize_preview_session_id(str(session_id) if session_id else None)
    if not normalized:
        return False
    return (_PREVIEW_DIR / f"preview_{normalized}.html").exists()


def _build_preview_zip(session_id: str | None) -> bytes | None:
    """Bundle a session's generated page into one downloadable zip.

    The HTML becomes ``index.html``; the CSS/JS keep their ``preview_<sid>``
    names so the HTML's own <link>/<script> references still resolve inside the
    zip and the page opens straight away. Returns None if there is no page.
    """
    import io
    import zipfile

    normalized = _normalize_preview_session_id(str(session_id) if session_id else None)
    if not normalized:
        return None
    html_path = _PREVIEW_DIR / f"preview_{normalized}.html"
    if not html_path.exists():
        return None

    def _entry(name: str, path: Path) -> zipfile.ZipInfo:
        # Stamped with the file's own mtime, not the clock: the panel rebuilds
        # this zip every 2 s during a run, and a clock stamp made every build's
        # bytes differ, so the download button registered a new file each tick.
        stamp = time.localtime(path.stat().st_mtime)[:6]
        info = zipfile.ZipInfo(name, date_time=max(stamp, (1980, 1, 1, 0, 0, 0)))
        info.compress_type = zipfile.ZIP_DEFLATED
        return info

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(_entry("index.html", html_path), html_path.read_text(encoding="utf-8"))
        for ext in ("css", "js"):
            part = _PREVIEW_DIR / f"preview_{normalized}.{ext}"
            if part.exists():
                zf.writestr(_entry(f"preview_{normalized}.{ext}", part),
                            part.read_text(encoding="utf-8"))
    return buf.getvalue()


def _chat_display_text(query: str) -> str:
    split = contract.split_modify_message(query)
    if split is None:
        return query
    _marker, visible_text = split
    return visible_text or query


def _render_preview_iframe(preview_url: str, session_id: str, *, select_enabled: bool = False) -> None:
    safe_url = escape(preview_url, quote=True)
    safe_session_id = escape(session_id)
    select_enabled_js = "true" if select_enabled else "false"
    # The viewport toolbar (Fit / Desktop / 16:9 / Tablet / Phone) belongs to
    # Preview mode only. In Select mode it is not emitted at all, and the
    # preview stays locked at the Desktop size.
    bar_html = "" if select_enabled else f"""
            <div class="bar">
                <div class="meta"><span id="modeLabel">Preview</span> <span id="label">Desktop</span></div>
                <div class="controls" aria-label="Viewport presets">
                    <button type="button" data-mode="fit" title="Fit panel"><span class="ico fit"></span></button>
                    <button type="button" data-mode="desktop" title="Desktop · 1440 × 900" class="active"><span class="ico desktop"></span></button>
                    <button type="button" data-mode="wide" title="16:9 · 1440 × 810"><span class="ico wide"></span></button>
                    <button type="button" data-mode="tablet" title="Tablet · iPad 9.7 · 768 × 1024"><span class="ico tablet"></span></button>
                    <span class="phone-picker" id="phonePicker">
                        <button type="button" id="phoneMenuButton" title="Phone preview · more options" aria-expanded="false"><span class="ico phone"></span></button>
                        <span class="phone-options" id="phoneOptions">
                            <button type="button" data-mode="iphone-standard" title="iPhone Standard · iPhone 15 / iPhone 16 · 393 × 852"><span class="ico phone-option ios"></span></button>
                            <button type="button" data-mode="iphone-pro-max" title="iPhone Pro Max · iPhone 15 Pro Max / iPhone 14 Pro Max · 430 × 932"><span class="ico phone-option ios"></span></button>
                            <button type="button" data-mode="android-large" title="Android Large · Pixel 7 class · 412 × 915"><span class="ico phone-option android"></span></button>
                            <button type="button" data-mode="android-compact" title="Android Compact · Samsung Galaxy S24 class · 360 × 780"><span class="ico phone-option android"></span></button>
                            <button type="button" data-mode="small-phone" title="Small Phone · iPhone SE class · 375 × 667"><span class="ico phone-option ios"></span></button>
                        </span>
                    </span>
                </div>
            </div>"""
    # Only the markup lives here; its CSS and JS are ui_assets/preview_frame.css
    # and preview_frame.js (ticket 14), so neither has to double its braces.
    components.html(
        f"""
        <style>{ui_assets.read("preview_frame.css")}</style>
        <div class="preview-lab">
            <div class="canvas" id="canvas">
                <div class="device-shell" id="deviceShell">
                    <div class="device" id="device">
                        <iframe data-src="{safe_url}" title="WebForge generated preview"></iframe>
                    </div>
                </div>
                <div class="select-overlay" id="hoverOverlay"></div>
                <div class="select-overlay selected" id="selectedOverlay" style="display:none;"></div>
                <div class="select-tooltip" id="selectTooltip"></div>
                <div class="select-pocket" id="selectPocket" aria-live="polite">
                    <div class="select-pocket-header">
                        <div class="select-pocket-title">
                            <span class="select-pocket-kicker">Edit component</span>
                            <strong id="selectedName">component</strong>
                            <span class="select-pocket-selector" id="selectedSummary"></span>
                        </div>
                        <button type="button" class="select-pocket-close" id="closePocket" title="Close">×</button>
                    </div>
                    <textarea id="modificationRequest" placeholder="Describe the change for this component..."></textarea>
                    <div class="select-pocket-actions">
                        <span class="select-pocket-hint"><kbd id="submitModKey">Ctrl</kbd><kbd>↵</kbd> to submit</span>
                        <button type="button" class="select-pocket-submit" id="submitModification" disabled>Submit</button>
                    </div>
                </div>
            </div>
{bar_html}
        </div>
        <script>{ui_assets.preview_frame_js(select_enabled_js, _MODIFY_MARKER_JS)}</script>
        """,
        height=720,
        scrolling=False,
    )

if "thread_messages" not in st.session_state:
    # Start empty so the lazy loader (_get_thread_messages) fetches the active
    # thread's history from the checkpointer on first access. Seeding the active
    # thread as [] here would mark it "already cached" and suppress that fetch,
    # so a refresh onto ?t=<existing id> would show an empty conversation.
    st.session_state.thread_messages = {}

if "active_run_id" not in st.session_state:
    st.session_state.active_run_id = None

if "webforge_preview_mode_control" not in st.session_state:
    st.session_state.webforge_preview_mode_control = "Preview"

if "webforge_selected_component" not in st.session_state:
    st.session_state.webforge_selected_component = None

if "webforge_modification_annotation" not in st.session_state:
    st.session_state.webforge_modification_annotation = None

if "webforge_preview_artifact_ready" not in st.session_state:
    st.session_state.webforge_preview_artifact_ready = False

if "webforge_preview_session_id" not in st.session_state:
    # Default to None so the preview panel resolves to the ACTIVE thread's own
    # page (preview_<thread_id>.*), not a hard-wired test session. A fresh
    # session has never built a page, so Preview Mode correctly shows the empty
    # state; a thread that did build one shows its own. This used to default to
    # _PREVIEW_TEST_SESSION_ID, a scaffold that made every session -- new ones
    # included -- always show the same fixed test page.
    st.session_state.webforge_preview_session_id = None


class _RunCancelled(BaseException):
    """Internal control-flow signal for user-requested termination."""


def _raise_thread_exception(thread_id: int | None, exc_type: type[BaseException]) -> bool:
    """Ask CPython to raise ``exc_type`` in the target worker thread.

    The worker is dedicated to one background graph stream, so this is
    used only for explicit user termination. If the thread is currently
    blocked inside a provider call, delivery still depends on the next
    interpreter checkpoint.
    """
    if not thread_id:
        return False

    result = ctypes.pythonapi.PyThreadState_SetAsyncExc(
        ctypes.c_ulong(thread_id),
        ctypes.py_object(exc_type),
    )
    if result == 0:
        return False
    if result > 1:
        ctypes.pythonapi.PyThreadState_SetAsyncExc(ctypes.c_ulong(thread_id), None)
        return False
    return True


def _get_label_llm():
    """Reuse an already-initialised cheap LLM from the backend."""
    return bridge.label_model()


@st.cache_resource
def _get_backend_warmup_state() -> dict[str, object]:
    """Persist one backend warm-up worker across reruns."""
    return {
        "lock": threading.Lock(),
        "started": False,
        "done": False,
        "error": None,
        "worker": None,
    }


def _ensure_backend_warmup_started() -> None:
    """Preload the heavy backend in the background after the UI shell renders."""
    state = _get_backend_warmup_state()
    with state["lock"]:
        if state["started"]:
            return
        state["started"] = True

        def _warm_backend() -> None:
            try:
                bridge.warm_up()
            except Exception as exc:  # pragma: no cover - best effort only
                with state["lock"]:
                    state["error"] = exc
                    state["done"] = True
                return

            with state["lock"]:
                state["done"] = True

        worker = threading.Thread(
            target=_warm_backend,
            name="uigpt-backend-warmup",
            daemon=True,
        )
        state["worker"] = worker

    worker.start()


@st.cache_resource
def _get_background_run_store() -> dict[str, object]:
    """Persist background worker state across Streamlit reruns."""
    return {
        "lock": threading.Lock(),
        "runs": {},
    }


def _get_thread_messages(thread_id: str, *, refresh: bool = False) -> list[dict[str, str]]:
    """Return cached display messages for a thread, loading once on demand.

    The sidebar already renders purely from ``st.session_state``. By
    caching the main-panel messages alongside it, we avoid a synchronous
    ``graph.get_state(...)`` call on every rerun and only hit the backend
    when a thread is first opened or explicitly refreshed after a stream.
    """
    cache = st.session_state.thread_messages
    # The very first page render must not wait for the same heavy graph import
    # that the background thread restore is already performing. Show the empty
    # conversation shell now; the restore poll schedules a full rerun once the
    # backend is ready, at which point this lazy read is safe and fast.
    if not refresh and thread_id not in cache:
        restore = _thread_restore_snapshot()
        if not restore["done"]:
            return []
    if refresh or thread_id not in cache:
        cache[thread_id] = bridge.switch_chat(thread_id)
    return cache.get(thread_id, [])


def _get_run_snapshot(run_id: str | None) -> dict[str, object] | None:
    """Return a detached snapshot of one background run."""
    if not run_id:
        return None
    store = _get_background_run_store()
    with store["lock"]:
        run = store["runs"].get(run_id)
        if not run:
            return None
        return {
            "id": run["id"],
            "thread_id": run["thread_id"],
            "assistant_idx": run["assistant_idx"],
            "response": run["response"],
            "processing_steps": list(run["processing_steps"]),
            "pending_question": dict(run.get("pending_question") or {}),
            "status": run["status"],
            "threads": dict(run["threads"]),
            "error": run["error"],
            "started_at": run.get("started_at"),
            "stage_times": list(run.get("stage_times") or []),
        }


def _discard_run(run_id: str | None) -> None:
    if not run_id:
        return
    store = _get_background_run_store()
    with store["lock"]:
        store["runs"].pop(run_id, None)


def _cancel_background_run(run_id: str | None) -> None:
    """Terminate one active background run as soon as the worker can stop."""
    if not run_id:
        return

    store = _get_background_run_store()
    cancel_event = None
    worker = None
    with store["lock"]:
        state = store["runs"].pop(run_id, None)
        if not state:
            return
        cancel_event = state.get("cancel_event")
        worker = state.get("worker")

    if isinstance(cancel_event, threading.Event):
        cancel_event.set()
    if isinstance(worker, threading.Thread) and worker.is_alive():
        _raise_thread_exception(worker.ident, _RunCancelled)


def _start_background_run(
    *,
    query: str,
    thread_id: str,
    assistant_idx: int,
    threads: dict[str, str],
) -> str:
    """Consume one StreamSession in a daemon thread.

    Streamlit reruns must stay cheap so RECENT buttons remain usable
    while a response is being generated. The worker owns the blocking
    stream iteration; the UI just polls shared state and re-renders.
    """
    run_id = str(uuid.uuid4())
    # No backend call here. This runs in the submit handler, before the rerun
    # that shows the user's message; the label model lives in webforge.entry,
    # and while the warm-up thread is still importing it (~26 s on a cold
    # start) any import here waits for it, so the message stayed invisible
    # for that long. The worker fetches it instead (tools/ui_feedback.py F1).
    threads_snapshot = dict(threads)
    store = _get_background_run_store()
    cancel_event = threading.Event()

    with store["lock"]:
        store["runs"][run_id] = {
            "id": run_id,
            "thread_id": thread_id,
            "assistant_idx": assistant_idx,
            "response": "",
            "processing_steps": [],
            "pending_question": {},
            "status": "running",
            "threads": dict(threads_snapshot),
            "error": None,
            "cancel_event": cancel_event,
            "worker": None,
            # Wall-clock start, used to show a live elapsed-seconds timer in the
            # generating message's status box (see _render_stream_status).
            "started_at": time.time(),
            # Per-stage first-seen wall-clock times, in arrival order:
            # [{"label": <full stage name>, "at": <epoch>}]. Each timeline row
            # times itself from its own start to the next stage's start (the
            # current stage ticks to now), so every step shows its own seconds.
            "stage_times": [],
        }

    # Optional latency probe. OFF unless WEBFORGE_TIMING is set, so normal runs
    # pay nothing. When on, it logs, per backend event, the seconds since the run
    # started and the gap since the previous event, to webforge_timing.log. The
    # gap between two [Actor] step lines is how long that step took, so the log
    # pins the slow stage. Events surface here straight from graph.stream (which
    # yields as the backend produces), so a large gap = backend/LLM time, not the
    # UI: the UI only polls this shared state on the chat fragment's measured
    # cadence afterwards.
    _timing_log = None
    if os.getenv("WEBFORGE_TIMING"):
        try:
            _timing_log = open(_ROOT_DIR / "webforge_timing.log", "a", encoding="utf-8")
            _timing_log.write(
                f"\n=== run {run_id[:8]} {time.strftime('%H:%M:%S')} "
                f"query={query[:70]!r} ===\n"
                f"{'elapsed':>9} {'+gap':>8}  event\n"
            )
            _timing_log.flush()
        except Exception:
            _timing_log = None

    def worker() -> None:
        _t0 = time.perf_counter()
        _tprev = _t0
        _answer_started = False
        _answer_chars = 0
        _seen_stage_labels = set()
        try:
            # Inside the try: loading the backend can raise (no .env, a bad
            # key), and only the except below turns that into status "error".
            # Outside it the thread died and the run spun forever.
            session = bridge.stream_message(
                query=query,
                thread_id=thread_id,
                threads=threads_snapshot,
                llm=_get_label_llm(),
                tone="friendly",
            )
            for kind, text in session.stream_events():
                if cancel_event.is_set():
                    raise _RunCancelled()

                if _timing_log is not None:
                    _now = time.perf_counter()
                    if kind == contract.PROCESSING:
                        _timing_log.write(
                            f"{_now - _t0:8.2f}s {_now - _tprev:7.2f}s  {str(text)[:100]}\n")
                        _timing_log.flush()
                        _tprev = _now
                    elif kind == contract.ANSWER:
                        _answer_chars += len(text)
                        if not _answer_started:
                            _answer_started = True
                            _timing_log.write(
                                f"{_now - _t0:8.2f}s {_now - _tprev:7.2f}s  "
                                f"[reply tokens start streaming]\n")
                            _timing_log.flush()
                            _tprev = _now

                # Stamp the first time each pipeline stage is seen, so every
                # timeline row can show its own elapsed seconds. Mapped with the
                # same contract.stage_label the timeline uses, so the recorded
                # labels line up with the rows.
                _new_stage = None
                if kind == contract.PROCESSING:
                    _lbl = contract.stage_label(str(text))
                    if _lbl and _lbl not in _seen_stage_labels:
                        _seen_stage_labels.add(_lbl)
                        _new_stage = {"label": _lbl, "at": time.time()}

                with store["lock"]:
                    state = store["runs"].get(run_id)
                    if not state or cancel_event.is_set():
                        raise _RunCancelled()
                    if kind == contract.ANSWER:
                        state["response"] = str(state["response"]) + text
                    elif kind == contract.ANSWER_BOUNDARY:
                        # A new orchestrator narration line started: replace the
                        # bubble instead of stacking. The stream settles on the
                        # final summary because that is the last message's text.
                        state["response"] = ""
                    elif kind == contract.PROCESSING:
                        state["processing_steps"] = list(session.processing_steps)
                        if _new_stage is not None:
                            state["stage_times"] = list(state.get("stage_times") or []) + [_new_stage]

            if _timing_log is not None:
                _end = time.perf_counter()
                _timing_log.write(
                    f"{_end - _t0:8.2f}s {'':7}   [done] reply={_answer_chars} chars\n")
                _timing_log.flush()

            if cancel_event.is_set():
                raise _RunCancelled()

            with store["lock"]:
                state = store["runs"].get(run_id)
                if not state or cancel_event.is_set():
                    raise _RunCancelled()
                state["response"] = session.response
                state["processing_steps"] = list(session.processing_steps)
                state["pending_question"] = dict(session.pending_question or {})
                state["threads"] = dict(session.threads)
                # Stamp a terminal marker so the LAST stage has an end time and
                # can show its own duration in the finished view (each stage's
                # duration is next.start - this.start; the last stage has no
                # next, so it borrows this run-end time). Not a stage itself, so
                # the timeline never renders it as a row.
                if state.get("stage_times"):
                    state["stage_times"] = list(state["stage_times"]) + [
                        {"label": "__end__", "at": time.time()}
                    ]
                state["status"] = "complete"
        except _RunCancelled:
            return
        except Exception as exc:
            with store["lock"]:
                state = store["runs"].get(run_id)
                if not state:
                    return
                state["status"] = "error"
                state["error"] = f"{type(exc).__name__}: {exc}"
        finally:
            if _timing_log is not None:
                try:
                    _timing_log.close()
                except Exception:
                    pass

    worker_thread = threading.Thread(
        target=worker,
        name=f"uigpt-stream-{run_id}",
        daemon=True,
    )
    with store["lock"]:
        state = store["runs"].get(run_id)
        if state:
            state["worker"] = worker_thread
    worker_thread.start()
    return run_id


def _delete_conversation(thread_id: str, allow_fragment_rerun: bool = False) -> None:
    """Delete one conversation, then reflow the sidebar.

    Steps: stop it if a generation is in flight on it (its state is about to
    disappear), drop it from the SqliteSaver via bridge, clear its caches, pick
    a sensible active thread if we just deleted the one on screen, and rerun so
    the remaining rows move up to fill the gap. Preview files are left on disk
    for now (that cleanup is a separate, still-to-discuss decision).

    ``allow_fragment_rerun`` lets the caller opt into a fragment-scoped rerun.
    A full ``st.rerun`` re-runs the whole script, which re-injects the entire
    chrome (sidebar + preview panel) and every CSS block, and that churn is what
    makes a delete feel janky. Deleting a NON-active conversation only changes
    the sidebar list, so when the caller lives inside the recent-threads
    fragment we can rerun just that fragment and skip all of it. Deleting the
    active conversation still needs a full rerun, because the main chat area
    (outside the fragment) has to switch to the new active thread.
    """
    if not thread_id:
        return

    deleted_active = st.session_state.active_thread == thread_id

    # Stop a run on this thread before its checkpoints are removed.
    run_id = st.session_state.get("active_run_id")
    if run_id:
        snap = _get_run_snapshot(run_id)
        if snap and str(snap.get("thread_id")) == thread_id:
            _cancel_background_run(run_id)
            st.session_state.active_run_id = None

    bridge.delete_thread(thread_id)

    threads = dict(st.session_state.threads)
    threads.pop(thread_id, None)
    st.session_state.thread_messages.pop(thread_id, None)
    for key in [k for k in st.session_state.processing_logs
                if isinstance(k, tuple) and k and k[0] == thread_id]:
        st.session_state.processing_logs.pop(key, None)
    for key in [k for k in st.session_state.stage_time_logs
                if isinstance(k, tuple) and k and k[0] == thread_id]:
        st.session_state.stage_time_logs.pop(key, None)

    # If we deleted the thread being viewed, move to the next most recent one,
    # or mint a fresh empty chat when nothing is left.
    if deleted_active:
        st.session_state.webforge_pending_question = None
        if threads:
            new_active = next(iter(threads))
        else:
            fresh = bridge.new_chat(threads)
            new_active = fresh["active_thread"]
            threads = fresh["threads"]
            st.session_state.thread_messages[new_active] = []
        st.session_state.active_thread = new_active
        st.query_params["t"] = new_active

    st.session_state.threads = threads
    # Non-active delete: only the sidebar list changed, so rerun just the
    # recent-threads fragment and skip re-injecting the chrome. Active delete:
    # the main chat area must follow the new active thread, so full rerun.
    if allow_fragment_rerun and not deleted_active:
        st.rerun(scope="fragment")
    else:
        st.rerun()


@st.dialog("Download before deleting?")
def _delete_warn_dialog(thread_id: str) -> None:
    """Center-screen modal (background dimmed + blurred via CSS) shown when the
    user deletes a conversation whose generated page they have not downloaded.
    Three choices: Download saves the zip and then deletes; Delete removes the
    chat now without saving; Cancel keeps the chat and returns to the state
    before the delete click.
    """
    st.markdown(
        "This chat has a generated page you haven't downloaded yet. "
        "Download a copy before it's deleted?"
    )
    zip_bytes = _build_preview_zip(thread_id)
    c1, c2, c3 = st.columns(3)
    with c1:
        if st.download_button(
            "Download",
            data=(zip_bytes or b""),
            file_name=f"webforge_{thread_id}.zip",
            mime="application/zip",
            key="webforge_delete_warn_dl",
            icon=":material/download:",
            use_container_width=True,
            disabled=zip_bytes is None,
        ):
            st.session_state.webforge_downloaded.add(thread_id)
            st.session_state.webforge_delete_warn = None
            _delete_conversation(thread_id)
    with c2:
        if st.button("Delete", key="webforge_delete_warn_delete",
                     icon=":material/delete:", use_container_width=True):
            st.session_state.webforge_delete_warn = None
            _delete_conversation(thread_id)
    with c3:
        if st.button("Cancel", key="webforge_delete_warn_cancel",
                     use_container_width=True):
            st.session_state.webforge_delete_warn = None
            st.rerun()


def _sync_active_run() -> dict[str, object] | None:
    """Project the current background run into session-state caches."""
    run_id = st.session_state.active_run_id
    snapshot = _get_run_snapshot(run_id)
    if not snapshot:
        st.session_state.active_run_id = None
        return None

    thread_id = str(snapshot["thread_id"])
    assistant_idx = int(snapshot["assistant_idx"])
    cache = st.session_state.thread_messages.setdefault(thread_id, [])

    while len(cache) <= assistant_idx:
        cache.append({"role": "assistant", "content": ""})

    cache[assistant_idx]["content"] = str(snapshot["response"] or "")

    processing_steps = list(snapshot["processing_steps"])
    if processing_steps:
        st.session_state.processing_logs[(thread_id, assistant_idx)] = processing_steps

    stage_times = list(snapshot.get("stage_times") or [])
    if stage_times:
        st.session_state.stage_time_logs[(thread_id, assistant_idx)] = stage_times

    status = snapshot["status"]
    if status == "complete":
        st.session_state.threads = dict(snapshot["threads"])
        # Surface any clarifying question the orchestrator raised this turn so
        # _render_ask_user_box can draw it. Empty dict -> clear it, so a box
        # from a previous turn does not linger once this turn asked nothing.
        pq = snapshot.get("pending_question") or {}
        st.session_state.webforge_pending_question = pq if pq else None
        # 3.7: the run just stopped. If a preview page for this thread exists on
        # disk, arm the one-shot "preview ready" signal; the module-level trigger
        # (fired on the full rerun this completion schedules) flashes the green
        # bubble once and auto-opens the panel. Skip it when nothing was produced
        # (a no-op / question-only turn), so the bubble means "a page is ready".
        ready_session_id = str(thread_id)
        if _preview_files_present(ready_session_id):
            st.session_state.webforge_fire_preview_ready = thread_id
        st.session_state.active_run_id = None
        _discard_run(run_id)
    elif status == "error":
        cache[assistant_idx]["content"] = str(snapshot["error"] or "Generation failed.")
        st.session_state.active_run_id = None
        _discard_run(run_id)

    return snapshot


_PREVIEW_TEST_COMPONENTS = (
    {
        "id": "hero",
        "name": "Hero section",
        "summary": "#hero · .hero-section · data-component=hero",
    },
    {
        "id": "nav",
        "name": "Navigation bar",
        "summary": "#site-nav · .nav-shell · data-component=navigation",
    },
    {
        "id": "products",
        "name": "Product grid",
        "summary": "#products · .product-grid · data-component=product-list",
    },
    {
        "id": "cta",
        "name": "Primary CTA",
        "summary": "#shop-now · .primary-button · data-component=cta",
    },
)


def _component_by_id(component_id: str | None) -> dict[str, str] | None:
    return next(
        (
            component
            for component in _PREVIEW_TEST_COMPONENTS
            if component["id"] == component_id
        ),
        None,
    )


# While a run is going, the panel re-renders every 2 s so a page that lands
# mid-run shows up then, not after the run ends (it used to say "no preview"
# for the last ~11 minutes of the 2026-11-10 PO-08 run). An unchanged page gives
# byte-identical markup (the iframe url carries the files' mtime), so these
# ticks do not reload it; a rewritten file changes the url and reloads it once.
# Idle, there is no timer, like the chat panel.
_preview_refresh_interval = "2s" if st.session_state.get("active_run_id") else None


def _running_thread_id() -> str | None:
    snapshot = _get_run_snapshot(st.session_state.get("active_run_id"))
    if snapshot and snapshot.get("status") == "running":
        return str(snapshot["thread_id"])
    return None


@st.fragment(run_every=_preview_refresh_interval)
def _render_preview_panel() -> None:
    """Render the right-side preview/select panel shell.

    A fragment on purpose: switching Preview<->Select (and the download button)
    then reruns only THIS panel, not the whole app. Before, the segmented
    control was a top-level widget, so every switch was a FULL rerun -- it
    re-created the sidebar and chat and re-ran the global chrome script, which
    fired the layout MutationObserver storm. That storm is the visible lag, the
    right panel nudging open, and the freeze on switching back. Scoped to a
    fragment, the sidebar/chat stay put and only the panel re-renders; the
    persistent observer still re-appends the expand button when the panel DOM is
    swapped, so it keeps working. Full app reruns (e.g. a generation finishing)
    still run this fragment, so a freshly built preview appears exactly as before.
    """
    preview_artifact = _current_preview_artifact()
    building = _running_thread_id() == st.session_state.get("active_thread")
    if building and preview_artifact is not None and not _preview_complete(preview_artifact[0]):
        preview_artifact = None          # only the HTML so far: wait for CSS and JS
    preview_ready = preview_artifact is not None
    st.session_state.webforge_preview_artifact_ready = preview_ready

    with st.container(key="webforge_preview_panel"):
        selected_mode = st.segmented_control(
            "Preview mode",
            ["Preview", "Select"],
            key="webforge_preview_mode_control",
            label_visibility="collapsed",
            width="content",
        )
        mode = (selected_mode or "Preview").lower()

        # Download key, in the header next to Preview/Select (CSS pins it to the
        # top-right, just left of the expand key). It bundles the active page
        # into one zip; clicking it marks this conversation as downloaded so the
        # delete guard no longer warns for it.
        if preview_ready:
            dl_sid = str(preview_artifact[0])
            with st.container(key="webforge_download_btn"):
                if st.download_button(
                    "",
                    data=(_build_preview_zip(dl_sid) or b""),
                    file_name=f"webforge_{dl_sid}.zip",
                    mime="application/zip",
                    key="webforge_download_active",
                    icon=":material/download:",
                    help="Download this page (HTML/CSS/JS) as a zip",
                ):
                    st.session_state.webforge_downloaded.add(dl_sid)

        if not preview_ready:
            empty_text = (
                "Building your page. It appears here as soon as the HTML, CSS "
                "and JavaScript are written, while the checks still run."
                if building else
                "There is no preview available to show right now.")
            st.markdown(
                f"""
                <div class="webforge-preview-frame webforge-preview-empty"
                     aria-label="Preview is empty">
                    <span class="webforge-preview-empty-text">{empty_text}</span>
                </div>
                """,
                unsafe_allow_html=True,
            )
            return

        session_id, preview_path = preview_artifact
        preview_url = _preview_url_for(preview_path)
        if preview_url:
            _render_preview_iframe(preview_url, session_id, select_enabled=(mode == "select"))
        elif mode == "preview":
            st.markdown(
                """
                <div class="webforge-preview-frame webforge-preview-empty"
                     aria-label="Preview is empty">
                    <span class="webforge-preview-empty-text">There is no preview available to show right now.</span>
                </div>
                """,
                unsafe_allow_html=True,
            )
            return

        if mode == "select":
            return


def _render_modification_annotation() -> None:
    annotation = st.session_state.get("webforge_modification_annotation")
    if not annotation:
        return

    component = escape(str(annotation.get("component", "Selected component")), quote=True)
    request = escape(str(annotation.get("request", "")), quote=True)
    st.markdown(
        f"""
        <div class="webforge-annotation-chip" title="Target: {component}\nRequest: {request}">
            <span>Annotation 1</span>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _submit_ask_answer(answer: str) -> None:
    """Send a clarifying-question answer as an ordinary user message.

    Mirrors the main ``st.chat_input`` submit path (append the user turn, open
    a background run, lock the composer) so an answer chosen in the box travels
    the exact same route as a typed message. Clears the pending question first
    so the box disappears on the rerun.
    """
    answer = (answer or "").strip()
    if not answer:
        return
    origin_thread_id = st.session_state.active_thread
    cached = list(_get_thread_messages(origin_thread_id))
    cached.append({"role": "user", "content": _chat_display_text(answer)})
    assistant_idx = len(cached)
    cached.append({"role": "assistant", "content": ""})
    st.session_state.thread_messages[origin_thread_id] = cached
    st.session_state.webforge_pending_question = None
    st.session_state.active_run_id = _start_background_run(
        query=answer,
        thread_id=origin_thread_id,
        assistant_idx=assistant_idx,
        threads=st.session_state.threads,
    )
    _set_stream_interaction_lock(True)
    st.rerun()


def _render_ask_user_box() -> bool:
    """The ask_user box: the orchestrator's one clarifying question, drawn as
    option buttons plus a free-text field. Clicking an option sends its value;
    typing an answer and pressing Send (or Enter) sends that. Both go through
    _submit_ask_answer, the same route as a typed message.

    Native Streamlit controls are used on purpose. A pure-HTML button cannot
    submit back to Python, and a reliable submit matters more than the
    dot-then-send two-step the HTML mockup showed, so an option click is now a
    one-tap submit. Returns True when a box was drawn (so the caller locks the
    main composer). Reads the real pending_question; renders nothing when there
    is none."""
    question = st.session_state.get("webforge_pending_question")
    if not question:
        return False

    with st.container(key="wf_ask_box"):
        q_txt = escape(str(question.get("question", "")))
        cap = escape(str(question.get("caption", "")))
        cap_html = f'<div class="wf-ask-qsub">{cap}</div>' if cap else ""
        st.markdown(
            f'<div class="wf-ask-head"><div class="wf-ask-q">{q_txt}</div>'
            f"{cap_html}</div>",
            unsafe_allow_html=True,
        )
        for i, opt in enumerate(question.get("options", []) or []):
            label = str(opt.get("label") or opt.get("value") or "")
            helptext = str(opt.get("help") or "")
            value = str(opt.get("value") or label)
            btn_label = f"**{label}**" + (f"  \n{helptext}" if helptext else "")
            if st.button(btn_label, key=f"wf_ask_opt_{i}",
                         use_container_width=True):
                _submit_ask_answer(value)
        st.markdown('<div class="wf-ask-ownlbl">or type your own answer</div>',
                    unsafe_allow_html=True)
        with st.form("wf_ask_form", clear_on_submit=True, border=False):
            fcol, scol = st.columns([6, 1], vertical_alignment="center")
            with fcol:
                typed = st.text_input(
                    "Your answer", key="wf_ask_text",
                    label_visibility="collapsed",
                    placeholder="Type your answer here…",
                )
            with scol:
                sent = st.form_submit_button("Send", use_container_width=True)
        if sent and (typed or "").strip():
            _submit_ask_answer(typed)
    return True


def _set_stream_interaction_lock(locked: bool) -> None:
    """Clear any stale client-side sidebar lock from older UI logic.

    Responses now stream from a background worker that survives reruns,
    so sidebar navigation must stay available while a reply is in
    flight. We therefore never apply the old sidebar lock and only use
    this bridge to make sure a previously-set lock class is removed.
    """
    _ = locked
    components.html(
        """
        <script>
        (function() {
            try {
                var pwin = window.parent;
                if (typeof pwin.setUigptStreamLock === 'function') {
                    pwin.setUigptStreamLock(false);
                }
            } catch (e) {
                console.error('WebForge: failed to toggle stream lock', e);
            }
        })();
        </script>
        """,
        height=0,
    )


# ---------------------------------------------------------------------------
# 2. Pre-flight JS via components.html (st.markdown does NOT execute scripts).
# The script lives in ui_assets/chrome.js (ticket 14). The newline and four
# spaces around each tag here and in section 3 are the old literal's, kept so the
# page gets the same bytes (python tools/ui_render_probe.py <rev> checks it).
# ---------------------------------------------------------------------------
components.html(
    "\n    <script>" + ui_assets.read("chrome.js") + "</script>\n    ",
    height=0,
)


# ---------------------------------------------------------------------------
# 3. Static stylesheet, in ui_assets/app.css (ticket 14).
# ---------------------------------------------------------------------------
st.markdown(
    "\n    <style>" + ui_assets.read("app.css") + "</style>\n    ",
    unsafe_allow_html=True,
)

# The live status box's CSS, injected ONCE here at module level (a full rerun),
# not inside the chat-panel fragment. The fragment reruns every 250ms while a
# reply streams; if it re-emitted this <style> each time, the browser would
# re-insert the stylesheet and repaint the box on every tick (visible flicker).
# Injected once, it just persists, and the fragment only re-renders the small
# dynamic HTML. See _render_stream_status.
st.markdown(_STREAM_STATUS_CSS, unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# 4. Sidebar toggle + theme toggle.
# ---------------------------------------------------------------------------
st.markdown(
    """
    <input class="webforge-preview-toggle-input"
           id="webforge-preview-toggle-input"
           type="checkbox"
           aria-label="Toggle preview panel" />
    <label class="webforge-preview-toggle"
           for="webforge-preview-toggle-input"
           aria-label="Toggle preview panel"></label>
    <div class="webforge-preview-resizer"
         role="separator"
         aria-orientation="vertical"
         aria-label="Resize preview panel"></div>
    <input class="uigpt-sidebar-toggle-input"
           id="uigpt-sidebar-toggle-input"
           type="checkbox"
           autocomplete="off"
           aria-label="Toggle sidebar" />
    <label class="uigpt-sidebar-toggle"
           for="uigpt-sidebar-toggle-input"
           aria-label="Toggle sidebar"
           title="Collapse sidebar">
        <svg class="sidebar-toggle-chevron" viewBox="0 0 24 24" fill="none"
             stroke="currentColor" stroke-width="2" stroke-linecap="round"
             stroke-linejoin="round" aria-hidden="true">
            <path d="M15 6l-6 6 6 6"></path>
        </svg>
    </label>
    <div class="uigpt-sidebar-resizer"
         role="separator"
         aria-orientation="vertical"
         aria-label="Resize sidebar"></div>
    <div class="uigpt-floating-toggle">
        <button type="button" onclick="window.toggleUigptTheme()" aria-label="Toggle theme">
            <span class="uigpt-theme-icon"></span>
        </button>
    </div>
    """,
    unsafe_allow_html=True,
)


# ---------------------------------------------------------------------------
# 5. Sidebar.
# ---------------------------------------------------------------------------
@st.fragment
def _render_recent_threads() -> None:
    """The sidebar's "Recent" conversation list, isolated in a fragment.

    Kept separate from the rest of the sidebar so a delete of a NON-active
    conversation reruns only this list (``st.rerun(scope="fragment")`` inside
    ``_delete_conversation``) instead of the whole app. A full app rerun
    re-injects the entire chrome and every CSS block, and that churn is what
    made deleting feel janky. Switching the active thread and the warn-dialog
    delete still trigger a full rerun on purpose, because both change state that
    lives outside this fragment (the main chat area / the module-level dialog).
    """
    for tid, label in list(st.session_state.threads.items()):
        is_active = tid == st.session_state.active_thread
        display_label = f"{label or 'New Chat'}"
        with st.container(key=f"threadrow_{tid}"):
            c_main, c_kebab = st.columns([0.82, 0.18], gap="small",
                                         vertical_alignment="center")
            with c_main:
                if st.button(
                    display_label,
                    key=f"thread_{tid}",
                    use_container_width=True,
                    type="primary" if is_active else "secondary",
                    icon=":material/history:",
                ):
                    _get_thread_messages(tid)
                    st.session_state.active_thread = tid
                    st.query_params["t"] = tid  # pin so a refresh reopens this
                    st.rerun()
            with c_kebab:
                # ⋮ menu, revealed on row hover (see CSS). Its only content is
                # one red Delete; clicking outside the popover cancels.
                with st.container(key=f"kebab_{tid}"):
                    with st.popover("⋮", use_container_width=True):
                        if st.button("Delete chat", key=f"del_{tid}",
                                     use_container_width=True,
                                     icon=":material/delete:"):
                            # Guard: if this chat has a page the user hasn't
                            # downloaded, warn first (centered modal). Otherwise
                            # delete straight away. The warn path needs a FULL
                            # rerun (the dialog is opened at module level, outside
                            # this fragment); the direct delete can stay scoped.
                            if (_preview_files_present(tid)
                                    and tid not in st.session_state.webforge_downloaded):
                                st.session_state.webforge_delete_warn = tid
                                st.rerun()
                            else:
                                _delete_conversation(tid, allow_fragment_rerun=True)


with st.sidebar:
    st.markdown(
        """
        <div class="uigpt-brand" role="heading" aria-level="1">
            <span class="cloud-icon" aria-hidden="true">
                <svg viewBox="0 0 24 24" fill="none" stroke="#ffffff" stroke-width="2"
                     stroke-linecap="round" stroke-linejoin="round">
                    <path d="M12 3l9 4-9 4-9-4z"></path>
                    <path d="M3 12l9 4 9-4M3 17l9 4 9-4"></path>
                </svg>
            </span>
            <span class="name">Web<span class="brand-accent">Forge</span></span>
        </div>
        """,
        unsafe_allow_html=True,
    )

    if st.button("New chat", key="btn_new_chat", use_container_width=True):
        result = bridge.new_chat(st.session_state.threads)
        st.session_state.active_thread = result["active_thread"]
        st.session_state.threads = result["threads"]
        st.session_state.thread_messages[result["active_thread"]] = []
        st.session_state.webforge_selected_component = None
        st.session_state.webforge_modification_annotation = None
        st.session_state.webforge_pending_question = None
        st.query_params["t"] = result["active_thread"]  # pin new thread in URL
        st.rerun()


    st.markdown(
        '<div class="uigpt-recent-label">Recent</div>',
        unsafe_allow_html=True,
    )

    _render_recent_threads()


# Open the "download before deleting?" modal (outside the sidebar context) when a
# delete was gated above.
if st.session_state.get("webforge_delete_warn"):
    _delete_warn_dialog(st.session_state.webforge_delete_warn)


_render_preview_panel()


# ---------------------------------------------------------------------------
# 6. Main chat area - history with persistent processing-step expanders.
# ---------------------------------------------------------------------------
# A 250 ms fragment cadence can queue reruns faster than Streamlit/React can
# paint a long conversation. The browser then appears frozen and catches up
# only after a tab switch throttles timers, so a running build polls once a
# second and an idle panel has no timer.
_chat_panel_refresh_interval = "1s" if st.session_state.active_run_id else None

_ensure_backend_warmup_started()


@st.fragment(run_every=_chat_panel_refresh_interval)
def _render_chat_panel() -> None:
    active_run = _sync_active_run()
    has_running_generation = bool(active_run and active_run.get("status") == "running")
    active_run_thread_id = str(active_run["thread_id"]) if active_run else None
    is_current_thread_generating = bool(
        has_running_generation
        and active_run_thread_id == st.session_state.active_thread
    )

    _set_stream_interaction_lock(has_running_generation)

    messages = _get_thread_messages(st.session_state.active_thread)

    if not messages:
        st.markdown(
            """
            <div class="uigpt-welcome">
                <h1>What storefront should we <span class="hero-accent">forge</span> today?</h1>
                <p>Describe the shop you want WebForge to shape.</p>
            </div>
            """,
            unsafe_allow_html=True,
        )
    else:
        for idx, msg in enumerate(messages):
            with st.chat_message(msg["role"]):
                if msg["role"] == "assistant":
                    steps = st.session_state.processing_logs.get(
                        (st.session_state.active_thread, idx)
                    )
                    _vis = _visible_steps(steps)
                    # Only the message being generated RIGHT NOW gets the live
                    # status box; every finished message keeps the plain log.
                    _live_idx = int(active_run["assistant_idx"]) if active_run else -1
                    if is_current_thread_generating and idx == _live_idx:
                        _started = active_run.get("started_at") if active_run else None
                        _render_stream_status(
                            _vis,
                            started_at=_started if isinstance(_started, (int, float)) else None,
                            stage_times=active_run.get("stage_times") if active_run else None,
                        )
                    elif _vis:
                        # Form A: a quiet "Steps · N" toggle that opens a dark
                        # mono log (same look as the live box's raw log), instead
                        # of the old grey Processing-details box. Above the log we
                        # keep the per-agent timeline (each agent + its seconds)
                        # that the live box showed, so the timings survive the run.
                        _st_times = st.session_state.stage_time_logs.get(
                            (st.session_state.active_thread, idx)
                        )
                        with st.expander(f"Steps · {len(_vis)}", expanded=False):
                            st.markdown(
                                _finished_timeline_html(_st_times, _vis)
                                + _finished_steps_html(_vis),
                                unsafe_allow_html=True,
                            )
                st.markdown(msg["content"])

    if has_running_generation:
        if active_run_thread_id != st.session_state.active_thread:
            st.caption(
                "A reply is still generating in another chat. You can switch "
                "threads without losing it, but you need to wait for that run "
                "to finish before sending another message."
            )
            st.text_input(
                "Message WebForge...",
                value="",
                placeholder="Another chat is still generating a reply...",
                disabled=True,
                label_visibility="collapsed",
                key="processing_chat_input",
            )
        else:
            composer_col, action_col = st.columns([5, 1])
            with composer_col:
                st.text_input(
                    "Message WebForge...",
                    value="",
                    placeholder="WebForge is processing your request...",
                    disabled=True,
                    label_visibility="collapsed",
                    key="processing_chat_input",
                )
            with action_col:
                if st.button(
                    "Terminate",
                    key="btn_terminate_generation",
                    use_container_width=True,
                    type="secondary",
                ):
                    active_thread_id = st.session_state.active_thread
                    _cancel_background_run(st.session_state.active_run_id)
                    st.session_state.active_run_id = None
                    try:
                        st.session_state.thread_messages[active_thread_id] = bridge.switch_chat(active_thread_id)
                    except Exception:
                        pass
                    _set_stream_interaction_lock(False)
                    st.rerun()
    else:
        box_active = _render_ask_user_box()
        _render_modification_annotation()
        if box_active:
            # A clarifying question is open: lock the main composer so the user
            # answers inside the box, not here.
            st.chat_input(
                "Answer the question above to continue…",
                disabled=True,
                key="locked_chat_input",
            )
        elif query := st.chat_input("Message WebForge..."):
            origin_thread_id = st.session_state.active_thread
            display_query = _chat_display_text(query)
            cached_messages = list(_get_thread_messages(origin_thread_id))
            cached_messages.append({"role": "user", "content": display_query})
            assistant_idx = len(cached_messages)
            cached_messages.append({"role": "assistant", "content": ""})
            st.session_state.thread_messages[origin_thread_id] = cached_messages
            if display_query != query:
                st.session_state.webforge_modification_annotation = None
            st.session_state.active_run_id = _start_background_run(
                query=query,
                thread_id=origin_thread_id,
                assistant_idx=assistant_idx,
                threads=st.session_state.threads,
            )
            _set_stream_interaction_lock(True)
            st.rerun()

    if active_run is not None and not has_running_generation:
        st.rerun()


_render_chat_panel()


# Lift the boot curtain once the custom chrome has attached: add `wf-booted` to
# <html> in the parent document so #wf-boot-overlay fades out. Polls for the
# styled brand + sidebar toggle so the curtain lifts only after the layout is
# clean, with an 8s fallback so it can never stick. Idempotent, so re-running it
# on every rerun is harmless.
components.html(
    """
    <script>
    (function () {
      try {
        var pdoc = window.parent.document;
        var pwin = window.parent;
        var html = pdoc.documentElement;
        if (html.classList.contains('wf-booted')) return;
        var start = Date.now();
        function chromeReady() {
          return pdoc.querySelector('.uigpt-brand')
              && pdoc.querySelector('.uigpt-sidebar-toggle');
        }
        function reveal() {
          // Add the class directly (not via requestAnimationFrame): rAF is
          // paused while the tab is hidden/backgrounded, which would leave the
          // curtain stuck up until the tab gains focus. setTimeout still fires
          // in background tabs, so the fade lifts regardless of visibility.
          pwin.setTimeout(function () { html.classList.add('wf-booted'); }, 0);
        }
        (function tick() {
          if (chromeReady() || Date.now() - start > 8000) { reveal(); return; }
          pwin.setTimeout(tick, 60);
        })();
      } catch (e) {}
    })();
    </script>
    """,
    height=0,
)


# 3.7: fire the green "preview ready" bubble once, right after a generation that
# produced a page. The flag is armed at the completion transition in
# _sync_active_run (which schedules a full rerun), so this module-level block runs
# on that rerun and clears the flag so it never re-pops on a later rerun/reload.
# webforgeSetPreviewState('ready') both shows the green bubble (auto-hiding after
# ~6s) and opens the panel if it is closed. Poll for the chrome fn in case this
# rerun runs before the chrome script (re)defines it.
_fire_ready_for = st.session_state.get("webforge_fire_preview_ready")
if _fire_ready_for is not None:
    st.session_state.webforge_fire_preview_ready = None
    if _fire_ready_for == st.session_state.get("active_thread"):
        components.html(
            """
            <script>
            (function () {
              try {
                var pwin = window.parent;
                var start = Date.now();
                (function tick() {
                  if (typeof pwin.webforgeSetPreviewState === 'function') {
                    pwin.webforgeSetPreviewState('ready');
                    return;
                  }
                  if (Date.now() - start > 8000) return;
                  pwin.setTimeout(tick, 80);
                })();
              } catch (e) {}
            })();
            </script>
            """,
            height=0,
        )


# TEMP (screenshot aid, 2026-09-06): on page LOAD, if a preview exists for the
# active thread, show the green "preview ready" bubble and KEEP it up (sets the
# sticky flag so webforgeSetPreviewState skips its 6s auto-hide). Fires once per
# session so an ordinary rerun does not re-pop it. To restore the 6s behaviour,
# DELETE this whole block -- the completion trigger above already uses 6s.
if _current_preview_artifact() is not None:
    if not st.session_state.get("webforge_ready_shown_once"):
        st.session_state.webforge_ready_shown_once = True
        components.html(
            """
            <script>
            (function () {
              try {
                var pwin = window.parent;
                var start = Date.now();
                (function tick() {
                  if (typeof pwin.webforgeSetPreviewState === 'function') {
                    pwin.__wfStickyReady = true;
                    pwin.webforgeSetPreviewState('ready');
                    return;
                  }
                  if (Date.now() - start > 8000) return;
                  pwin.setTimeout(tick, 80);
                })();
              } catch (e) {}
            })();
            </script>
            """,
            height=0,
        )
