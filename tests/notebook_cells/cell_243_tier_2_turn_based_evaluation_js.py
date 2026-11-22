# Ported from fyp.ipynb cell 243 (ticket 05). The notebook is frozen;
# edit this file. Run by tests/test_notebook_cells.py.
# Needs: cell 182 (it defines ScriptedChatModel, _run_scripted, _assert_state_fields).
# Rescued (ticket 05): the notebook marked this cell LIVE-LLM, so it never ran
# offline. It makes no model call (the model is scripted or mocked).
# ═══════════════════════════════════════════════════════════════════════════
# TIER 2 — TURN-BASED EVALUATION: JS AGENT  (5 scenarios, NO real LLM calls)
#
#   TB-JS-1  Happy path (generation)   — tool order, lint gate, file on disk
#   TB-JS-2  Self-correction loop      — errors block, then warnings-only passes
#                                        (also proves advisory warnings never trap the loop)
#   TB-JS-3  Coverage-guard rejection  — guard names the unwired interaction target
#   TB-JS-4  Modify mode               — Step 0 -> extract -> diff, no re-store
#   TB-JS-5  Linter infra error        — npx missing: degrades, no file written
#
# Requires the scripted-model harness cell to have been run.
# ═══════════════════════════════════════════════════════════════════════════
from types import SimpleNamespace as _NS4  # stub runtime for expected-content setup
import os as _os, re as _re, shutil as _shutil, uuid as _uuid, pathlib as _pathlib
from unittest.mock import patch as _patch, MagicMock as _Magic

_assert_state_fields(JsState, ["js_specification", "js_code", "interaction_specification"], "JS")

# Ticket 05: was a hardcoded C:/Users/Lenovo/Desktop/FYP path; the same folder
# now comes from webforge/config.py.
from webforge.config import PREVIEW_DIR as _TBJ_PREVIEW_DIR
_TBJ_ROOT = str(_TBJ_PREVIEW_DIR)
_os.makedirs(_TBJ_ROOT, exist_ok=True)

# Exercises BOTH Naming Contract branches store_js_code resolves through:
#   add-to-cart-button -> has className -> JS must reference "add-to-cart-btn"
#   mini-cart          -> no className  -> falls back to the raw id "mini-cart"
_TBJ_INTERACTION = {"pages": [{"pageName": "plp", "flows": [
    {"name": "add-to-cart-flow",
     "trigger": {"event": "click", "targetId": "add-to-cart-button"},
     "actions": [{"type": "addToCart", "targetId": "mini-cart"}]},
]}]}
_TBJ_COMPONENTS = {"pages": [{"pageName": "plp", "rootComponents": [
    {"id": "add-to-cart-button", "tag": "button", "className": "add-to-cart-btn"},
    {"id": "mini-cart", "tag": "div"},
]}]}

# Blank-line-separated paragraphs: extract_js_component locates blocks that way.
_TBJ_GOOD_JS = (
    'const miniCart = document.getElementById("mini-cart");\n'
    '\n'
    'document.querySelectorAll(".add-to-cart-btn").forEach(function (btn) {\n'
    '  btn.addEventListener("click", function () {\n'
    '    if (miniCart) { miniCart.setAttribute("aria-live", "polite"); }\n'
    '  });\n'
    '});'
)
# References the button but never the mini-cart target -> guard must reject
_TBJ_INCOMPLETE_JS = (
    'document.querySelectorAll(".add-to-cart-btn").forEach(function (btn) {\n'
    '  btn.addEventListener("click", function () {});\n'
    '});'
)
# Lint-BAD but coverage-COMPLETE: calls an undefined helper (no-undef error)
# while still referencing both interaction targets. It has to satisfy the
# coverage guard, otherwise store_js_code rejects it at write time and the
# linter never runs — which is not the path this scenario means to exercise.
_TBJ_LINT_BAD_JS = (
    'const miniCart = document.getElementById("mini-cart");\n'
    '\n'
    'document.querySelectorAll(".add-to-cart-btn").forEach(function (btn) {\n'
    '  btn.addEventListener("click", function () { undefinedHelper(miniCart); });\n'
    '});'
)

# eslint writes its JSON report to STDOUT (unlike stylelint, which uses stderr)
_JS_CLEAN = '[{"filePath":"x.js","messages":[],"errorCount":0,"warningCount":0}]'
_JS_WARN  = ('[{"filePath":"x.js","messages":['
             '{"ruleId":"no-unused-vars","severity":1,"message":"unused","line":1,"column":7}],'
             '"errorCount":0,"warningCount":1}]')
_JS_ERR   = ('[{"filePath":"x.js","messages":['
             '{"ruleId":"no-undef","severity":2,"message":"foo is not defined","line":2,"column":1},'
             '{"ruleId":"no-unused-vars","severity":1,"message":"unused","line":1,"column":7}],'
             '"errorCount":1,"warningCount":1}]')

_TBJ_TOOLS = [store_js_code, run_eslint, extract_js_component, apply_and_lint_js, save_js_file]
_TBJ_MW = [FilesystemMiddleware(backend=_preview_backend), js_prompt_selector,
           js_agent_progress, js_tool_progress]

_TBJ_REAL_LINTER = _shutil.which("npx") is not None
if not _TBJ_REAL_LINTER:
    print("[note] npx not found -> TB-JS-1 will mock the linter instead of running "
          "the real one (scenario still valid, integration not exercised)")


def _tbj_payload(sid, query, intent="generate", target_component=""):
    """Mirrors call_js_agent's payload construction exactly."""
    return {
        "messages":         [{"role": "user", "content": query}],
        "session_id":       sid,
        "intent":           intent,
        "target_component": target_component,
        "target_instance":  1,
        "js_specification": query,
        "js_code":          "",
        "lint_passed":      False,
        "interaction_specification": _TBJ_INTERACTION,
        "components_specification":  _TBJ_COMPONENTS,
    }


def _tbj_fixture(sid):
    """The HTML the JS agent reads at Step 0 for DOM context."""
    html = (f'<!DOCTYPE html><html lang="en"><head><meta charset="utf-8">'
            f'<title>PLP</title><link rel="stylesheet" href="preview_{sid}.css"></head>'
            f'<body><div id="mini-cart" data-count="0">Cart: 0</div>'
            f'<button class="add-to-cart-btn" type="button">Add</button>'
            f'<script src="preview_{sid}.js" defer></script></body></html>')
    with open(_os.path.join(_TBJ_ROOT, f"preview_{sid}.html"), "w", encoding="utf-8") as f:
        f.write(html)


_tbj_passed, _tbj_sessions = 0, []


def _tbj_new_session():
    sid = _uuid.uuid4().hex[:8]
    _tbj_sessions.append(sid)
    _tbj_fixture(sid)
    return sid


# ── TB-JS-1  Happy path ─────────────────────────────────────────────────────
print("=" * 68)
print("TB-JS-1  Happy path — generation")
print("=" * 68)
_sid = _tbj_new_session()
_script = [
    _tc("read_file",     {"file_path": f"preview_{_sid}.html"}),
    _tc("store_js_code", {"js_code": _TBJ_GOOD_JS}),
    _tc("run_eslint",    {}),
    _tc("save_js_file"),
    _done(),
]
_model, _agent = _scripted_agent(_script, _TBJ_TOOLS, _TBJ_MW, JsState, agent_var="js_agent")

if _TBJ_REAL_LINTER:
    _st, _calls, _msgs = _run_scripted(_agent, _tbj_payload(_sid, "Wire up add-to-cart."), _sid)
else:
    with _patch("subprocess.run") as _m:
        _m.return_value = _Magic(returncode=0, stdout=_JS_CLEAN, stderr="")
        _st, _calls, _msgs = _run_scripted(_agent, _tbj_payload(_sid, "Wire up add-to-cart."), _sid)

assert _calls == ["read_file", "store_js_code", "run_eslint", "save_js_file"], \
    f"TB-JS-1 FAIL: tool order was {_calls}"
assert _st.get("js_code") == _TBJ_GOOD_JS, "TB-JS-1 FAIL: js_code not stored"
assert _st.get("lint_passed") is True, f"TB-JS-1 FAIL: lint_passed={_st.get('lint_passed')}"
_disk = open(_os.path.join(_TBJ_ROOT, f"preview_{_sid}.js"), encoding="utf-8").read()
assert _disk == _TBJ_GOOD_JS, "TB-JS-1 FAIL: file on disk != js_code in state"
assert _model.turns_used == len(_script), "TB-JS-1 FAIL: unexpected model turns"
_tbj_passed += 1
print(f"PASS TB-JS-1  order={_calls}  lint=True  file matches state  "
      f"(real linter: {_TBJ_REAL_LINTER})\n")


# ── TB-JS-2  Self-correction loop + warnings never block ────────────────────
print("=" * 68)
print("TB-JS-2  Self-correction loop — errors block, warnings-only passes")
print("=" * 68)
_sid = _tbj_new_session()
_script = [
    _tc("read_file",     {"file_path": f"preview_{_sid}.html"}),
    _tc("store_js_code", {"js_code": _TBJ_LINT_BAD_JS}),   # coverage OK, no-undef error
    _tc("run_eslint",    {}),                              # -> 1 error + 1 warning: blocks
    _tc("store_js_code", {"js_code": _TBJ_GOOD_JS}),       # agent revises
    _tc("run_eslint",    {}),                              # -> warnings only: must PASS
    _tc("save_js_file"),
    _done(),
]
_model, _agent = _scripted_agent(_script, _TBJ_TOOLS, _TBJ_MW, JsState, agent_var="js_agent")
with _patch("subprocess.run") as _m:
    _m.side_effect = [
        _Magic(returncode=1, stdout=_JS_ERR,  stderr=""),
        _Magic(returncode=0, stdout=_JS_WARN, stderr=""),
    ]
    _st, _calls, _msgs = _run_scripted(_agent, _tbj_payload(_sid, "Wire up add-to-cart."), _sid)

assert _calls.count("store_js_code") == 2, \
    f"TB-JS-2 FAIL: expected 2 store_js_code calls, got {_calls.count('store_js_code')}"
assert _calls.count("run_eslint") == 2, "TB-JS-2 FAIL: linter not re-run after the fix"
assert _st.get("lint_passed") is True, \
    "TB-JS-2 FAIL: warnings-only must NOT block — a cosmetic no-unused-vars warning " \
    "would otherwise trap the agent's fix loop forever"
assert any("no-undef" in m for m in _msgs), \
    "TB-JS-2 FAIL: the blocking error was never surfaced to the agent"
assert any("dvisory" in m for m in _msgs), \
    "TB-JS-2 FAIL: warnings not reported as advisory"
_tbj_passed += 1
print("PASS TB-JS-2  errors blocked, warnings-only passed, loop closed cleanly\n")


# ── TB-JS-3  Coverage-guard rejection ───────────────────────────────────────
print("=" * 68)
print("TB-JS-3  Coverage-guard rejection — feedback names the unwired target")
print("=" * 68)
_sid = _tbj_new_session()
_script = [
    _tc("read_file",     {"file_path": f"preview_{_sid}.html"}),
    _tc("store_js_code", {"js_code": _TBJ_INCOMPLETE_JS}),   # -> rejected
    _tc("store_js_code", {"js_code": _TBJ_GOOD_JS}),         # -> accepted
    _tc("run_eslint",    {}),
    _tc("save_js_file"),
    _done(),
]
_model, _agent = _scripted_agent(_script, _TBJ_TOOLS, _TBJ_MW, JsState, agent_var="js_agent")
with _patch("subprocess.run") as _m:
    _m.return_value = _Magic(returncode=0, stdout=_JS_CLEAN, stderr="")
    _st, _calls, _msgs = _run_scripted(_agent, _tbj_payload(_sid, "Wire up add-to-cart."), _sid)

_reject = [m for m in _msgs if "Coverage check failed" in m]
assert _reject, "TB-JS-3 FAIL: incomplete JS was accepted — the guard never fired"
assert "mini-cart" in _reject[0], \
    f"TB-JS-3 FAIL: rejection did not name the unwired target: {_reject[0][:140]}"
assert _st.get("js_code") == _TBJ_GOOD_JS, "TB-JS-3 FAIL: retry not stored"
assert _st.get("lint_passed") is True, "TB-JS-3 FAIL: did not recover after rejection"
_tbj_passed += 1
print("PASS TB-JS-3  guard rejected and named 'mini-cart'; retry accepted\n")


# ── TB-JS-4  Modify mode ────────────────────────────────────────────────────
print("=" * 68)
print("TB-JS-4  Modify mode — Step 0 seed, extract, diff, no re-store")
print("=" * 68)
_sid = _tbj_new_session()
with open(_os.path.join(_TBJ_ROOT, f"preview_{_sid}.js"), "w", encoding="utf-8") as _f:
    _f.write(_TBJ_GOOD_JS)

# Build the diff off the real extractor so it stays valid if the fixture changes.
# store_js_diff joins ALL matching blocks with a blank line before patching —
# mirror that exactly rather than taking blocks[0].
# store_js_diff patches EVERY matching block as one marked document, so the diff
# has to be written against the joined text.
_blk = _join_blocks(_js_blocks_for_component(_TBJ_GOOD_JS, "#mini-cart"))
_old = next(l for l in _blk.splitlines() if "getElementById" in l)
_new = _old.replace('document.getElementById("mini-cart")',
                    'document.querySelector("#mini-cart")')
_idx = _blk.splitlines().index(_old) + 1
_diff = f"--- original\n+++ revised\n@@ -{_idx},1 +{_idx},1 @@\n-{_old}\n+{_new}"

# A scripted model cannot read runtime state, so the content it "writes" has to
# be computed up front. Ask the real tool rather than re-implementing the splice:
# an inline copy silently drifts from the implementation. The disk == state
# assertion below then proves the agent actually persisted this exact text.
_TBJ_EXPECTED_JS = store_js_diff.func(_diff, _NS4(
    state={"js_code": _TBJ_GOOD_JS, "target_component": "#mini-cart"},
    tool_call_id="tbj4-expected")).update["js_code"]
assert 'querySelector("#mini-cart")' in _TBJ_EXPECTED_JS and _TBJ_EXPECTED_JS != _TBJ_GOOD_JS, \
    "TB-JS-4 setup FAIL: the expected content is not actually a modification"

_script = [
    _tc("read_file",     {"file_path": f"preview_{_sid}.js"}),
    _tc("store_js_code", {"js_code": _TBJ_GOOD_JS}),          # Step 0 seed only
    _tc("extract_js_component", {}),
    _tc("apply_and_lint_js", {"diff_output": _diff}),
    _tc("save_js_file"),
    _done(),
]
_model, _agent = _scripted_agent(_script, _TBJ_TOOLS, _TBJ_MW, JsState, agent_var="js_agent")
with _patch("subprocess.run") as _m:
    _m.return_value = _Magic(returncode=0, stdout=_JS_CLEAN, stderr="")
    _st, _calls, _msgs = _run_scripted(
        _agent,
        _tbj_payload(_sid, "Use querySelector for the mini-cart lookup.",
                     intent="modify", target_component="#mini-cart"),
        _sid)

assert _calls.count("store_js_code") == 1, \
    f"TB-JS-4 FAIL: store_js_code called {_calls.count('store_js_code')}x — modify mode must " \
    f"seed once at Step 0 then use apply_and_lint_js only. calls={_calls}"
assert "apply_and_lint_js" in _calls, f"TB-JS-4 FAIL: apply_and_lint tool never called. calls={_calls}"
assert 'querySelector("#mini-cart")' in _st.get("js_code", ""), \
    f"TB-JS-4 FAIL: diff did not apply. tool messages={_msgs}"
assert "add-to-cart-btn" in _st.get("js_code", ""), \
    "TB-JS-4 FAIL: untargeted wiring lost during modification"

# Regression guard for the modify-mode write bug — see the CSS suite for the
# full diagnosis. Fixed by OverwritingFilesystemBackend.
assert not any("already exists" in m for m in _msgs), \
    "TB-JS-4 FAIL: save_js_file was refused — the modify-mode overwrite bug is back. " \
    "Check that this agent still uses OverwritingFilesystemBackend."
_disk_after = open(_os.path.join(_TBJ_ROOT, f"preview_{_sid}.js"), encoding="utf-8").read()
assert 'querySelector("#mini-cart")' in _disk_after, \
    "TB-JS-4 FAIL: modification did not reach disk"
assert _disk_after == _st.get("js_code"), \
    "TB-JS-4 FAIL: file on disk does not match js_code in state"

_tbj_passed += 1
print(f"PASS TB-JS-4  order={_calls}  diff applied, other wiring intact, "
      f"persisted to disk\n")


# ── TB-JS-5  Linter infrastructure error (fallback) ─────────────────────────
print("=" * 68)
print("TB-JS-5  Fallback — linter infra error is distinguishable, no file written")
print("=" * 68)
_sid = _tbj_new_session()
_script = [
    _tc("read_file",     {"file_path": f"preview_{_sid}.html"}),
    _tc("store_js_code", {"js_code": _TBJ_GOOD_JS}),
    _tc("run_eslint",    {}),                       # -> npx missing
    _done("Cannot lint: the eslint toolchain is unavailable."),
]
_model, _agent = _scripted_agent(_script, _TBJ_TOOLS, _TBJ_MW, JsState, agent_var="js_agent")
with _patch("subprocess.run") as _m:
    _m.return_value = _Magic(returncode=1, stdout="", stderr="'npx' is not recognized")
    _st, _calls, _msgs = _run_scripted(_agent, _tbj_payload(_sid, "Wire up add-to-cart."), _sid)

assert _st.get("lint_passed") is not True, "TB-JS-5 FAIL: infra error must not pass the gate"
assert any("npx" in m for m in _msgs), \
    "TB-JS-5 FAIL: infra error not distinguishable from a JS error in the feedback"
assert "save_js_file" not in _calls and "write_file" not in _calls, "TB-JS-5 FAIL: wrote a file despite lint never passing"
assert not _os.path.exists(_os.path.join(_TBJ_ROOT, f"preview_{_sid}.js")), \
    "TB-JS-5 FAIL: JS file exists on disk despite the failure"
_tbj_passed += 1
print("PASS TB-JS-5  infra error surfaced, gate held, no file written\n")


# ── cleanup ─────────────────────────────────────────────────────────────────
for _s in _tbj_sessions:
    for _ext in ("html", "js"):
        _p = _os.path.join(_TBJ_ROOT, f"preview_{_s}.{_ext}")
        if _os.path.exists(_p):
            _os.remove(_p)

print("=" * 68)
print(f"TIER 2 — JS AGENT: {_tbj_passed}/5 PASSED   (0 LLM calls)")
print("=" * 68)
