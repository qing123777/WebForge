# Ported from fyp.ipynb cell 300 (ticket 05). The notebook is frozen;
# edit this file. Run by tests/test_notebook_cells.py.
# Needs: cell 182 (it defines ScriptedChatModel, _run_scripted, _assert_state_fields).
# Rescued (ticket 05): the notebook marked this cell LIVE-LLM, so it never ran
# offline. It makes no model call (the model is scripted or mocked).
# ═══════════════════════════════════════════════════════════════════════════
# TIER 2 — TURN-BASED EVALUATION: CSS AGENT  (5 scenarios, NO real LLM calls)
#
# Exercises the CSS sub-agent as a whole — tool sequencing, the self-correction
# loop, write-time guard feedback, modify-mode routing, and fallback on an
# infrastructure failure — with every model reply pre-scripted. Free to run,
# deterministic, repeatable.
#
#   TB-CSS-1  Happy path (generation)   — tool order, lint gate, file on disk
#   TB-CSS-2  Self-correction loop      — lint fails once, agent revises, passes
#   TB-CSS-3  Coverage-guard rejection  — guard names the missing className, retry accepted
#   TB-CSS-4  Modify mode               — Step 0 -> extract -> diff, no re-store
#   TB-CSS-5  Linter infra error        — npx missing: degrades, no file written
#
# Requires the harness cell (ScriptedChatModel) to have been run.
# ═══════════════════════════════════════════════════════════════════════════
from types import SimpleNamespace as _NS4  # stub runtime for expected-content setup
import os as _os, re as _re, shutil as _shutil, uuid as _uuid, pathlib as _pathlib
from unittest.mock import patch as _patch, MagicMock as _Magic

_assert_state_fields(CssState, ["css_specification", "css_code", "decoration_specification"], "CSS")

# Ticket 05: was a hardcoded C:/Users/Lenovo/Desktop/FYP path; the same folder
# now comes from webforge/config.py.
from webforge.config import PREVIEW_DIR as _TBC_PREVIEW_DIR
_TBC_ROOT = str(_TBC_PREVIEW_DIR)
_os.makedirs(_TBC_ROOT, exist_ok=True)

_TBC_DECO = {"pages": [{"pageName": "plp", "componentDecorations": [
    {"componentId": "product-card", "className": "product-card",
     "baseStyles": {"border-radius": "8px"}},
    {"componentId": "add-to-cart-button", "className": "add-to-cart-btn",
     "baseStyles": {"background-color": "#1a73e8"}},
]}]}
_TBC_CLASSNAMES = ["product-card", "add-to-cart-btn"]

# The :root block is not decoration: store_css_code enforces the Design Token
# Contract in generation mode (>= _DESIGN_TOKEN_MIN custom properties), so a
# fixture without one is refused before the scenario under test even starts.
_TBC_TOKENS = (":root { --color-primary: #1a73e8; --color-surface: #ffffff;\n"
               "        --color-text: #1f2933; --color-border: #d9e2ec;\n"
               "        --radius: 8px; --space: 8px; }\n")
# .add-to-cart-btn deliberately keeps its literals: TB-CSS-4 builds its diff by
# replacing '#1a73e8' inside this block, and two literals sit under the
# _TOKEN_FREE_LITERALS allowance, so no advisory fires either.
# Since commit 28b6811 (spec-base CSS) store_css_code stores the submitted
# sheet plus a Python-written spec-base block, ending in one newline. These
# cases check that the submitted sheet is what is stored (ticket 05).
def _sheet(text):
    return _SPEC_BLOCKS_RE.sub("", text or "").strip()


_TBC_GOOD_CSS = (_TBC_TOKENS +
                 ".product-card { border-radius: var(--radius); "
                 "background-color: var(--color-surface); }\n"
                 ".add-to-cart-btn { background-color: #1a73e8; color: #ffffff; }")
# Missing .add-to-cart-btn -> the coverage guard must reject this (scenario 3)
_TBC_INCOMPLETE_CSS = ".product-card { border-radius: 8px; }"
# Empty block -> a real stylelint error (block-no-empty)
_TBC_LINT_BAD_CSS = _TBC_GOOD_CSS + "\n.dead {}"

_CSS_CLEAN_REPORT = '[{"source":"x.css","parseErrors":[],"warnings":[]}]'
_CSS_ERROR_REPORT = ('[{"source":"x.css","parseErrors":[],"warnings":['
                     '{"line":3,"column":1,"rule":"block-no-empty","severity":"error",'
                     '"text":"Empty block (block-no-empty)"}]}]')

_TBC_TOOLS = [store_css_code, run_stylelint, extract_css_component, apply_and_lint_css, save_css_file]
_TBC_MW = [FilesystemMiddleware(backend=_preview_backend), css_prompt_selector,
           css_agent_progress, css_tool_progress]

_TBC_REAL_LINTER = _shutil.which("npx") is not None
if not _TBC_REAL_LINTER:
    print("[note] npx not found -> TB-CSS-1 will mock the linter instead of "
          "running the real one (scenario still valid, integration not exercised)")


def _tbc_payload(sid, query, intent="generate", target_component=""):
    """Mirrors call_css_agent's payload construction exactly."""
    return {
        "messages":          [{"role": "user", "content": query}],
        "session_id":        sid,
        "intent":            intent,
        "target_component":  target_component,
        "target_instance":   1,
        "css_specification": query,
        "css_code":          "",
        "lint_passed":       False,
        "decoration_specification": _TBC_DECO,
    }


def _tbc_fixture(sid):
    """The HTML the CSS agent reads at Step 0 for selector context."""
    html = (f'<!DOCTYPE html><html lang="en"><head><meta charset="utf-8">'
            f'<title>PLP</title><link rel="stylesheet" href="preview_{sid}.css"></head>'
            f'<body><article class="product-card"><button class="add-to-cart-btn" '
            f'type="button">Add</button></article>'
            f'<script src="preview_{sid}.js" defer></script></body></html>')
    with open(_os.path.join(_TBC_ROOT, f"preview_{sid}.html"), "w", encoding="utf-8") as f:
        f.write(html)
    return html


_tbc_passed, _tbc_sessions = 0, []


def _tbc_new_session():
    sid = _uuid.uuid4().hex[:8]
    _tbc_sessions.append(sid)
    _tbc_fixture(sid)
    return sid


# ── TB-CSS-1  Happy path ────────────────────────────────────────────────────
print("=" * 68)
print("TB-CSS-1  Happy path — generation")
print("=" * 68)
_sid = _tbc_new_session()
_script = [
    _tc("read_file",      {"file_path": f"preview_{_sid}.html"}),
    _tc("store_css_code", {"css_code": _TBC_GOOD_CSS}),
    _tc("run_stylelint",  {}),
    _tc("save_css_file"),
    _done(),
]
_model, _agent = _scripted_agent(_script, _TBC_TOOLS, _TBC_MW, CssState, agent_var="css_agent")

if _TBC_REAL_LINTER:
    _st, _calls, _msgs = _run_scripted(_agent, _tbc_payload(_sid, "Style the PLP."), _sid)
else:
    with _patch("subprocess.run") as _m:
        _m.return_value = _Magic(returncode=0, stdout="", stderr=_CSS_CLEAN_REPORT)
        _st, _calls, _msgs = _run_scripted(_agent, _tbc_payload(_sid, "Style the PLP."), _sid)

assert _calls == ["read_file", "store_css_code", "run_stylelint", "save_css_file"], \
    f"TB-CSS-1 FAIL: tool order was {_calls}"
assert _sheet(_st.get("css_code")) == _sheet(_TBC_GOOD_CSS), "TB-CSS-1 FAIL: css_code not stored"
assert _st.get("lint_passed") is True, f"TB-CSS-1 FAIL: lint_passed={_st.get('lint_passed')}"
_disk = open(_os.path.join(_TBC_ROOT, f"preview_{_sid}.css"), encoding="utf-8").read()
# Ticket 05: compared to the submitted sheet before; the stored sheet now
# carries the spec-base block, and disk must match the stored one.
assert _disk == _st.get("css_code"), "TB-CSS-1 FAIL: file on disk != css_code in state"
assert _model.turns_used == len(_script), "TB-CSS-1 FAIL: unexpected model turns"
_tbc_passed += 1
print(f"PASS TB-CSS-1  order={_calls}  lint=True  file matches state  "
      f"(real linter: {_TBC_REAL_LINTER})\n")


# ── TB-CSS-2  Self-correction loop ──────────────────────────────────────────
print("=" * 68)
print("TB-CSS-2  Self-correction loop — lint fails once, then passes")
print("=" * 68)
_sid = _tbc_new_session()
_script = [
    _tc("read_file",      {"file_path": f"preview_{_sid}.html"}),
    _tc("store_css_code", {"css_code": _TBC_LINT_BAD_CSS}),
    _tc("run_stylelint",  {}),                                   # -> errors
    _tc("store_css_code", {"css_code": _TBC_GOOD_CSS}),          # agent revises
    _tc("run_stylelint",  {}),                                   # -> clean
    _tc("save_css_file"),
    _done(),
]
_model, _agent = _scripted_agent(_script, _TBC_TOOLS, _TBC_MW, CssState, agent_var="css_agent")
with _patch("subprocess.run") as _m:
    _m.side_effect = [
        _Magic(returncode=2, stdout="", stderr=_CSS_ERROR_REPORT),
        _Magic(returncode=0, stdout="", stderr=_CSS_CLEAN_REPORT),
    ]
    _st, _calls, _msgs = _run_scripted(_agent, _tbc_payload(_sid, "Style the PLP."), _sid)

assert _calls.count("store_css_code") == 2, \
    f"TB-CSS-2 FAIL: expected 2 store_css_code calls, got {_calls.count('store_css_code')}"
assert _calls.count("run_stylelint") == 2, "TB-CSS-2 FAIL: linter not re-run after the fix"
assert _st.get("lint_passed") is True, "TB-CSS-2 FAIL: loop did not end clean"
assert _sheet(_st.get("css_code")) == _sheet(_TBC_GOOD_CSS), "TB-CSS-2 FAIL: revised code not stored"
assert any("block-no-empty" in m for m in _msgs), \
    "TB-CSS-2 FAIL: the linter error was never surfaced to the agent"
_tbc_passed += 1
print(f"PASS TB-CSS-2  store x2, lint x2, ends lint_passed=True  "
      f"(error text reached the agent)\n")


# ── TB-CSS-3  Coverage-guard rejection ──────────────────────────────────────
print("=" * 68)
print("TB-CSS-3  Coverage-guard rejection — feedback names the missing className")
print("=" * 68)
_sid = _tbc_new_session()
_script = [
    _tc("read_file",      {"file_path": f"preview_{_sid}.html"}),
    _tc("store_css_code", {"css_code": _TBC_INCOMPLETE_CSS}),    # -> rejected
    _tc("store_css_code", {"css_code": _TBC_GOOD_CSS}),          # -> accepted
    _tc("run_stylelint",  {}),
    _tc("save_css_file"),
    _done(),
]
_model, _agent = _scripted_agent(_script, _TBC_TOOLS, _TBC_MW, CssState, agent_var="css_agent")
# Ticket 05: since commit 28b6811 Python writes a rule for every component
# whose decoration pins a style, so the coverage guard can only refuse one that
# pins none. This scenario runs with add-to-cart-btn pinning nothing.
_TBC_DECO_PINNED = _TBC_DECO
_TBC_DECO = {"pages": [{"pageName": "plp", "componentDecorations": [
    dict(_TBC_DECO_PINNED["pages"][0]["componentDecorations"][0]),
    dict(_TBC_DECO_PINNED["pages"][0]["componentDecorations"][1], baseStyles={}),
]}]}
try:
    with _patch("subprocess.run") as _m:
        _m.return_value = _Magic(returncode=0, stdout="", stderr=_CSS_CLEAN_REPORT)
        _st, _calls, _msgs = _run_scripted(_agent, _tbc_payload(_sid, "Style the PLP."), _sid)
finally:
    _TBC_DECO = _TBC_DECO_PINNED

_reject = [m for m in _msgs if "Coverage check failed" in m]
assert _reject, "TB-CSS-3 FAIL: incomplete CSS was accepted — the guard never fired"
assert "add-to-cart-btn" in _reject[0], \
    f"TB-CSS-3 FAIL: rejection did not name the missing className: {_reject[0][:120]}"
assert _sheet(_st.get("css_code")) == _sheet(_TBC_GOOD_CSS), "TB-CSS-3 FAIL: retry not stored"
assert _st.get("lint_passed") is True, "TB-CSS-3 FAIL: did not recover after rejection"
_tbc_passed += 1
print(f"PASS TB-CSS-3  guard rejected and named 'add-to-cart-btn'; retry accepted\n")


# ── TB-CSS-4  Modify mode ───────────────────────────────────────────────────
print("=" * 68)
print("TB-CSS-4  Modify mode — Step 0 seed, extract, diff, no re-store")
print("=" * 68)
_sid = _tbc_new_session()
with open(_os.path.join(_TBC_ROOT, f"preview_{_sid}.css"), "w", encoding="utf-8") as _f:
    _f.write(_TBC_GOOD_CSS)

# Build the diff programmatically off the real extractor, so it stays valid if
# the CSS fixture above is ever edited.
# store_css_diff patches EVERY matching block as one marked document, so the
# diff has to be written against the joined text, not against blocks[0].
_blk = _join_blocks(_extract_css_blocks(_TBC_GOOD_CSS, ".add-to-cart-btn"))
_old = next(l for l in _blk.splitlines() if "background-color" in l)
_new = _old.replace("#1a73e8", "#0b5cd5")
_idx = _blk.splitlines().index(_old) + 1
_diff = f"--- original\n+++ revised\n@@ -{_idx},1 +{_idx},1 @@\n-{_old}\n+{_new}"

# A scripted model cannot read runtime state, so the content it "writes" has to
# be computed up front. Ask the real tool rather than re-implementing the splice:
# an inline copy silently drifts from the implementation (it did, when the tool
# started trimming the newline _apply_patch appends). The disk == state assertion
# below then proves the agent actually persisted this exact text.
_TBC_EXPECTED_CSS = store_css_diff.func(_diff, _NS4(
    state={"css_code": _TBC_GOOD_CSS, "target_component": ".add-to-cart-btn"},
    tool_call_id="tbc4-expected")).update["css_code"]
assert "#0b5cd5" in _TBC_EXPECTED_CSS and _TBC_EXPECTED_CSS != _TBC_GOOD_CSS, \
    "TB-CSS-4 setup FAIL: the expected content is not actually a modification"

_script = [
    _tc("read_file",      {"file_path": f"preview_{_sid}.css"}),
    _tc("store_css_code", {"css_code": _TBC_GOOD_CSS}),           # Step 0 seed only
    _tc("extract_css_component", {}),
    _tc("apply_and_lint_css", {"diff_output": _diff}),
    _tc("save_css_file"),
    _done(),
]
_model, _agent = _scripted_agent(_script, _TBC_TOOLS, _TBC_MW, CssState, agent_var="css_agent")
with _patch("subprocess.run") as _m:
    _m.return_value = _Magic(returncode=0, stdout="", stderr=_CSS_CLEAN_REPORT)
    _st, _calls, _msgs = _run_scripted(
        _agent,
        _tbc_payload(_sid, "Make the add-to-cart button darker.",
                     intent="modify", target_component=".add-to-cart-btn"),
        _sid)

assert _calls.count("store_css_code") == 1, \
    f"TB-CSS-4 FAIL: store_css_code called {_calls.count('store_css_code')}x — modify mode " \
    f"must seed once at Step 0 and then use apply_and_lint_css only. calls={_calls}"
assert "apply_and_lint_css" in _calls, f"TB-CSS-4 FAIL: apply_and_lint tool never called. calls={_calls}"
assert "#0b5cd5" in _st.get("css_code", ""), \
    f"TB-CSS-4 FAIL: diff did not apply. tool messages={_msgs}"
assert ".product-card" in _st.get("css_code", ""), \
    "TB-CSS-4 FAIL: untargeted rule lost during modification"

# Regression guard for the modify-mode write bug (found 2026-07-18, fixed by
# OverwritingFilesystemBackend). deepagents' stock FilesystemBackend.write()
# refuses when the target already exists, so a modify-mode change used to be
# correct in state, lint clean, report success — and never reach disk.
assert not any("already exists" in m for m in _msgs), \
    "TB-CSS-4 FAIL: save_css_file was refused — the modify-mode overwrite bug is back. " \
    "Check that this agent still uses OverwritingFilesystemBackend."
_disk_after = open(_os.path.join(_TBC_ROOT, f"preview_{_sid}.css"), encoding="utf-8").read()
assert "#0b5cd5" in _disk_after, \
    "TB-CSS-4 FAIL: modification did not reach disk"
assert _disk_after == _st.get("css_code"), \
    "TB-CSS-4 FAIL: file on disk does not match css_code in state"

_tbc_passed += 1
print(f"PASS TB-CSS-4  order={_calls}  diff applied, sibling rule intact, "
      f"persisted to disk\n")


# ── TB-CSS-5  Linter infrastructure error (fallback) ────────────────────────
print("=" * 68)
print("TB-CSS-5  Fallback — linter infra error is distinguishable, no file written")
print("=" * 68)
_sid = _tbc_new_session()
_script = [
    _tc("read_file",      {"file_path": f"preview_{_sid}.html"}),
    _tc("store_css_code", {"css_code": _TBC_GOOD_CSS}),
    _tc("run_stylelint",  {}),                       # -> npx missing
    _done("Cannot lint: the stylelint toolchain is unavailable."),
]
_model, _agent = _scripted_agent(_script, _TBC_TOOLS, _TBC_MW, CssState, agent_var="css_agent")
with _patch("subprocess.run") as _m:
    _m.return_value = _Magic(returncode=1, stdout="", stderr="'npx' is not recognized")
    _st, _calls, _msgs = _run_scripted(_agent, _tbc_payload(_sid, "Style the PLP."), _sid)

assert _st.get("lint_passed") is not True, "TB-CSS-5 FAIL: infra error must not pass the gate"
assert any("npx" in m for m in _msgs), \
    "TB-CSS-5 FAIL: infra error not distinguishable from a CSS error in the feedback"
assert "save_css_file" not in _calls and "write_file" not in _calls, "TB-CSS-5 FAIL: wrote a file despite lint never passing"
assert not _os.path.exists(_os.path.join(_TBC_ROOT, f"preview_{_sid}.css")), \
    "TB-CSS-5 FAIL: CSS file exists on disk despite the failure"
_tbc_passed += 1
print(f"PASS TB-CSS-5  infra error surfaced, gate held, no file written\n")


# ── cleanup ─────────────────────────────────────────────────────────────────
for _s in _tbc_sessions:
    for _ext in ("html", "css"):
        _p = _os.path.join(_TBC_ROOT, f"preview_{_s}.{_ext}")
        if _os.path.exists(_p):
            _os.remove(_p)

print("=" * 68)
print(f"TIER 2 — CSS AGENT: {_tbc_passed}/5 PASSED   (0 LLM calls)")
print("=" * 68)
