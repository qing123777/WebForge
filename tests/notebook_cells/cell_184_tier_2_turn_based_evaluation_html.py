# Ported from fyp.ipynb cell 184 (ticket 05). The notebook is frozen;
# edit this file. Run by tests/test_notebook_cells.py.
# Needs: cell 182 (it defines ScriptedChatModel, _run_scripted, _assert_state_fields).
# Rescued (ticket 05): the notebook marked this cell LIVE-LLM, so it never ran
# offline. It makes no model call (the model is scripted or mocked).
# ═══════════════════════════════════════════════════════════════════════════
# TIER 2 — TURN-BASED EVALUATION: HTML AGENT  (5 scenarios, NO real LLM calls)
#
#   TB-HTML-1  Happy path (generation)   — tool order, lint gate, file on disk
#   TB-HTML-2  Self-correction loop      — validator fails once, agent revises, passes
#   TB-HTML-3  Coverage-guard rejection  — guard names the missing <link> include tag
#   TB-HTML-4  Modify mode               — Step 0 -> extract -> diff, no re-store
#   TB-HTML-5  Validator infra error     — npx missing: degrades, no file written
#
# Note: HTML generation has no Step 0 read — HTML is the first artifact produced,
# so there is no sibling file to load for context (CSS and JS both read it).
#
# Requires the scripted-model harness cell to have been run.
# ═══════════════════════════════════════════════════════════════════════════
import os as _os, re as _re, shutil as _shutil, uuid as _uuid, pathlib as _pathlib
from unittest.mock import patch as _patch, MagicMock as _Magic

_assert_state_fields(HtmlState, ["html_code", "layout_specification", "components_specification"], "HTML")

# Ticket 05: was a hardcoded C:/Users/Lenovo/Desktop/FYP path; the same folder
# now comes from webforge/config.py.
from webforge.config import PREVIEW_DIR as _TBH_PREVIEW_DIR
_TBH_ROOT = str(_TBH_PREVIEW_DIR)
_os.makedirs(_TBH_ROOT, exist_ok=True)

# navbar renders via className, product-grid via id -> exercises both branches
# of the Naming Contract that store_html_code's coverage check resolves.
_TBH_LAYOUT = {"pages": [{"pageName": "plp", "regions": [
    {"name": "header", "ownedBy": "HTML", "componentRefs": [{"id": "navbar"}]},
    {"name": "main",   "ownedBy": "HTML", "componentRefs": [{"id": "product-grid"}]},
]}]}
_TBH_COMPONENTS = {"pages": [{"pageName": "plp", "rootComponents": [
    {"id": "navbar", "tag": "nav", "componentCategory": "navbar",
     "className": "site-navbar"},
    {"id": "product-grid", "tag": "section", "componentCategory": "product-grid"},
]}]}


def _tbh_good_html(sid, cols="3"):
    """Satisfies both halves of store_html_code's guard: include tags present,
    every spec component addressable. #product-grid is kept on one line so the
    modify-mode diff below stays a clean single-line hunk."""
    return (
        '<!DOCTYPE html>\n<html lang="en">\n<head>\n<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        f'<title>Product Listing</title>\n<link rel="stylesheet" href="preview_{sid}.css">\n'
        '</head>\n<body>\n'
        '<nav class="site-navbar" data-component="navbar" aria-label="Main navigation">'
        # Ticket 05: was href="index.html". The Anchor Navigation Contract,
        # added after this suite last ran, refuses a nav link to another
        # document (one page per run); an in-page anchor is the supported shape.
        '<a href="#product-grid">Shop</a></nav>\n'
        '<main>\n'
        f'<section id="product-grid" data-component="product-grid" data-cols="{cols}">'
        '<article class="product-card"><h2>Shoe</h2></article></section>\n'
        '</main>\n'
        f'<script src="preview_{sid}.js" defer></script>\n</body>\n</html>'
    )


def _tbh_missing_link_html(sid):
    """Everything valid except the stylesheet <link> — without it the generated
    CSS file is an orphan that never loads, so the guard must reject."""
    return _tbh_good_html(sid).replace(
        f'<link rel="stylesheet" href="preview_{sid}.css">\n', "")


_HTML_ERR_REPORT = ('[{"messages":[{"line":2,"column":1,"ruleId":"doctype-style",'
                    '"message":"Doctype should be lowercase"}]}]')

# Ticket 05: apply_and_lint_html_full joined the production HTML agent after
# this suite was last run; the drift guard below names it.
_TBH_TOOLS = [store_html_code, run_html_validate, extract_component,
              apply_and_lint_html, apply_and_lint_html_full, save_html_file]
_TBH_MW = [FilesystemMiddleware(backend=_preview_backend), html_fs_guard,
           html_prompt_selector, html_agent_progress, html_before_model_progress,
           html_tool_progress]

_TBH_REAL_LINTER = _shutil.which("npx") is not None
if not _TBH_REAL_LINTER:
    print("[note] npx not found -> TB-HTML-1 will mock the validator instead of "
          "running the real one (scenario still valid, integration not exercised)")


def _tbh_payload(sid, query, intent="generate", target_component=""):
    """Mirrors call_html_agent's payload construction exactly.

    The payload key is `user_query`, matching the field HTML State declares.
    (Production sent `input_query` until 2026-07-19; nothing read it, so the
    rename was inert. Upstream of the Secondary Orchestrator the field is still
    called `input_query` — see OrchestratorState.)
    """
    return {
        "messages":         [{"role": "user", "content": query}],
        "user_query":       query,
        "session_id":       sid,
        "intent":           intent,
        "target_component": target_component,
        "target_instance":  1,
        "layout_specification":     _TBH_LAYOUT,
        "components_specification": _TBH_COMPONENTS,
    }


_tbh_passed, _tbh_sessions = 0, []


def _tbh_new_session():
    sid = _uuid.uuid4().hex[:8]
    _tbh_sessions.append(sid)
    return sid


# ── TB-HTML-1  Happy path ───────────────────────────────────────────────────
print("=" * 68)
print("TB-HTML-1  Happy path")
print("Mode    : Generation")
print("Purpose : Confirm the normal generation trajectory — tool order is")
print("          store -> lint -> save, the lint gate opens, and the file on")
print("          disk is byte-identical to the artifact held in state.")
print()
print("Result:")
_sid = _tbh_new_session()
_good = _tbh_good_html(_sid)
_script = [
    _tc("store_html_code",  {"html_code": _good}),
    _tc("run_html_validate", {}),
    _tc("save_html_file"),
    _done(),
]
_model, _agent = _scripted_agent(_script, _TBH_TOOLS, _TBH_MW, HtmlState, agent_var="html_agent")

if _TBH_REAL_LINTER:
    _st, _calls, _msgs = _run_scripted(_agent, _tbh_payload(_sid, "Build a PLP."), _sid)
else:
    with _patch("subprocess.run") as _m:
        _m.return_value = _Magic(returncode=0, stdout="", stderr="")
        _st, _calls, _msgs = _run_scripted(_agent, _tbh_payload(_sid, "Build a PLP."), _sid)

assert _calls == ["store_html_code", "run_html_validate", "save_html_file"], \
    f"TB-HTML-1 FAIL: tool order was {_calls}"
assert _st.get("html_code") == _good, "TB-HTML-1 FAIL: html_code not stored"
assert _st.get("lint_passed") is True, \
    f"TB-HTML-1 FAIL: lint_passed={_st.get('lint_passed')} msgs={_msgs}"
_disk = open(_os.path.join(_TBH_ROOT, f"preview_{_sid}.html"), encoding="utf-8").read()
assert _disk == _good, "TB-HTML-1 FAIL: file on disk != html_code in state"
assert _model.turns_used == len(_script), "TB-HTML-1 FAIL: unexpected model turns"
_tbh_passed += 1
print(f"PASS TB-HTML-1  order={_calls}  lint=True  file matches state  "
      f"(real validator: {_TBH_REAL_LINTER})\n")
print("=" * 68)
print()


# ── TB-HTML-2  Self-correction loop ─────────────────────────────────────────
print("=" * 68)
print("TB-HTML-2  Self-correction loop")
print("Mode    : Generation")
print("Purpose : Confirm the self-correction loop — when the validator reports")
print("          an error the agent revises and re-lints until clean, and the")
print("          error text actually reaches the agent.")
print()
print("Result:")
_sid = _tbh_new_session()
_good = _tbh_good_html(_sid)
_bad  = _good.replace("<!DOCTYPE html>", "<!doctype html>")   # doctype-style error
_script = [
    _tc("store_html_code",  {"html_code": _bad}),
    _tc("run_html_validate", {}),                              # -> error
    _tc("store_html_code",  {"html_code": _good}),             # agent revises
    _tc("run_html_validate", {}),                              # -> clean
    _tc("save_html_file"),
    _done(),
]
_model, _agent = _scripted_agent(_script, _TBH_TOOLS, _TBH_MW, HtmlState, agent_var="html_agent")
with _patch("subprocess.run") as _m:
    _m.side_effect = [
        _Magic(returncode=1, stdout=_HTML_ERR_REPORT, stderr=""),
        _Magic(returncode=0, stdout="", stderr=""),
    ]
    _st, _calls, _msgs = _run_scripted(_agent, _tbh_payload(_sid, "Build a PLP."), _sid)

assert _calls.count("store_html_code") == 2, \
    f"TB-HTML-2 FAIL: expected 2 store_html_code calls, got {_calls.count('store_html_code')}"
assert _calls.count("run_html_validate") == 2, \
    "TB-HTML-2 FAIL: validator not re-run after the fix"
assert _st.get("lint_passed") is True, "TB-HTML-2 FAIL: loop did not end clean"
assert _st.get("html_code") == _good, "TB-HTML-2 FAIL: revised HTML not stored"
assert any("doctype-style" in m for m in _msgs), \
    "TB-HTML-2 FAIL: the validator error was never surfaced to the agent"
_tbh_passed += 1
print("PASS TB-HTML-2  store x2, validate x2, ends lint_passed=True\n")
print("=" * 68)
print()


# ── TB-HTML-3  Coverage-guard rejection (missing include tag) ───────────────
print("=" * 68)
print("TB-HTML-3  Coverage-guard rejection")
print("Mode    : Generation")
print("Purpose : Confirm the coverage guard rejects HTML that omits a required")
print("          include tag and names the exact missing file, and that the")
print("          agent recovers on the retry.")
print()
print("Result:")
_sid = _tbh_new_session()
_good = _tbh_good_html(_sid)
_script = [
    _tc("store_html_code",  {"html_code": _tbh_missing_link_html(_sid)}),   # -> rejected
    _tc("store_html_code",  {"html_code": _good}),                          # -> accepted
    _tc("run_html_validate", {}),
    _tc("save_html_file"),
    _done(),
]
_model, _agent = _scripted_agent(_script, _TBH_TOOLS, _TBH_MW, HtmlState, agent_var="html_agent")
with _patch("subprocess.run") as _m:
    _m.return_value = _Magic(returncode=0, stdout="", stderr="")
    _st, _calls, _msgs = _run_scripted(_agent, _tbh_payload(_sid, "Build a PLP."), _sid)

_reject = [m for m in _msgs if "Missing required include tag" in m or "missing" in m.lower()]
assert _reject, f"TB-HTML-3 FAIL: HTML without a <link> was accepted. msgs={_msgs}"
assert f"preview_{_sid}.css" in _reject[0], \
    f"TB-HTML-3 FAIL: rejection did not name the missing stylesheet: {_reject[0][:160]}"
assert _st.get("html_code") == _good, "TB-HTML-3 FAIL: retry not stored"
assert _st.get("lint_passed") is True, "TB-HTML-3 FAIL: did not recover after rejection"
_tbh_passed += 1
print(f"PASS TB-HTML-3  guard rejected and named 'preview_{_sid}.css'; retry accepted\n")
print("=" * 68)
print()


# ── TB-HTML-4  Modify mode ──────────────────────────────────────────────────
print("=" * 68)
print("TB-HTML-4  Modify mode")
print("Mode    : Modification")
print("Purpose : Confirm the modification trajectory — Step 0 seed, extract,")
print("          diff via apply_and_lint_html (store_html_code only once), sibling")
print("          components preserved, and the change persisted so disk == state.")
print()
print("Result:")
_sid = _tbh_new_session()
_good = _tbh_good_html(_sid)
with open(_os.path.join(_TBH_ROOT, f"preview_{_sid}.html"), "w", encoding="utf-8") as _f:
    _f.write(_good)

# store_html_diff patches str(el) for the selected element — build the diff the
# same way so it stays valid if the fixture markup changes.
_el   = BeautifulSoup(_good, "html.parser").select("#product-grid")[0]
_blk  = str(_el)
_newb = _blk.replace('data-cols="3"', 'data-cols="4"')
_diff = f"--- original\n+++ revised\n@@ -1,1 +1,1 @@\n-{_blk}\n+{_newb}"

# A scripted model cannot read runtime state, so the content it "writes" has to
# be computed up front. Mirror store_html_diff exactly: patch str(el), then
# replace_with and re-serialise the whole soup. The disk == state assertion
# below catches any drift between this expectation and the real tool.
_soup_exp = BeautifulSoup(_good, "html.parser")
_soup_exp.select("#product-grid")[0].replace_with(
    BeautifulSoup(_apply_patch(_blk, _diff), "html.parser"))
_TBH_EXPECTED_HTML = str(_soup_exp)

_script = [
    _tc("read_file",       {"file_path": f"preview_{_sid}.html"}),
    _tc("store_html_code", {"html_code": _good}),          # Step 0 seed only
    _tc("extract_component", {}),
    _tc("apply_and_lint_html", {"diff_output": _diff}),
    _tc("save_html_file"),
    _done(),
]
_model, _agent = _scripted_agent(_script, _TBH_TOOLS, _TBH_MW, HtmlState, agent_var="html_agent")
with _patch("subprocess.run") as _m:
    _m.return_value = _Magic(returncode=0, stdout="", stderr="")
    _st, _calls, _msgs = _run_scripted(
        _agent,
        _tbh_payload(_sid, "Show four product columns.",
                     intent="modify", target_component="#product-grid"),
        _sid)

assert _calls.count("store_html_code") == 1, \
    f"TB-HTML-4 FAIL: store_html_code called {_calls.count('store_html_code')}x — modify mode " \
    f"must seed once at Step 0 then use apply_and_lint_html only. calls={_calls}"
assert "apply_and_lint_html" in _calls, f"TB-HTML-4 FAIL: apply_and_lint tool never called. calls={_calls}"
assert 'data-cols="4"' in _st.get("html_code", ""), \
    f"TB-HTML-4 FAIL: diff did not apply. tool messages={_msgs}"
assert 'class="site-navbar"' in _st.get("html_code", ""), \
    "TB-HTML-4 FAIL: sibling component lost during modification"

# Regression guard for the modify-mode write bug — see the CSS suite for the
# full diagnosis. Fixed by OverwritingFilesystemBackend.
assert not any("already exists" in m for m in _msgs), \
    "TB-HTML-4 FAIL: save_html_file was refused — the modify-mode overwrite bug is back. " \
    "Check that this agent still uses OverwritingFilesystemBackend."
_disk_after = open(_os.path.join(_TBH_ROOT, f"preview_{_sid}.html"), encoding="utf-8").read()
assert 'data-cols="4"' in _disk_after, \
    "TB-HTML-4 FAIL: modification did not reach disk"
assert _disk_after == _st.get("html_code"), \
    "TB-HTML-4 FAIL: file on disk does not match html_code in state"

_tbh_passed += 1
print(f"PASS TB-HTML-4  order={_calls}  diff applied, sibling intact, "
      f"persisted to disk\n")
print("=" * 68)
print()


# ── TB-HTML-5  Validator infrastructure error (fallback) ────────────────────
print("=" * 68)
print("TB-HTML-5  Validator infrastructure error (fallback)")
print("Mode    : Generation")
print("Purpose : Confirm infrastructure-failure handling — a toolchain (npx)")
print("          error must not open the lint gate and must not write any file.")
print()
print("Result:")
_sid = _tbh_new_session()
_good = _tbh_good_html(_sid)
_script = [
    _tc("store_html_code",  {"html_code": _good}),
    _tc("run_html_validate", {}),                    # -> npx missing
    _done("Cannot validate: the html-validate toolchain is unavailable."),
]
_model, _agent = _scripted_agent(_script, _TBH_TOOLS, _TBH_MW, HtmlState, agent_var="html_agent")
with _patch("subprocess.run") as _m:
    _m.return_value = _Magic(returncode=1, stdout="", stderr="'npx' is not recognized")
    _st, _calls, _msgs = _run_scripted(_agent, _tbh_payload(_sid, "Build a PLP."), _sid)

assert _st.get("lint_passed") is not True, "TB-HTML-5 FAIL: infra error must not pass the gate"
assert "save_html_file" not in _calls and "write_file" not in _calls, "TB-HTML-5 FAIL: wrote a file despite lint never passing"
assert not _os.path.exists(_os.path.join(_TBH_ROOT, f"preview_{_sid}.html")), \
    "TB-HTML-5 FAIL: HTML file exists on disk despite the failure"
_tbh_passed += 1
print("PASS TB-HTML-5  gate held, no file written\n")
print("=" * 68)
print()


# ── cleanup ─────────────────────────────────────────────────────────────────
for _s in _tbh_sessions:
    _p = _os.path.join(_TBH_ROOT, f"preview_{_s}.html")
    if _os.path.exists(_p):
        _os.remove(_p)

print("=" * 68)
print(f"TIER 2 — HTML AGENT: {_tbh_passed}/5 PASSED   (0 LLM calls)")
print("=" * 68)
