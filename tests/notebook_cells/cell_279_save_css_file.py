# Ported from fyp.ipynb cell 279 (ticket 05). The notebook is frozen;
# edit this file. Run by tests/test_notebook_cells.py.
# Unit tests: save_css_file
# Writes go to a throwaway temp root: the module-level backend is swapped for
# the duration and restored in finally, so the real static/preview tree is
# never touched.
import shutil as _sv_sh_css
import tempfile as _sv_tmp_css
from pathlib import Path as _SvPath_css
from types import SimpleNamespace

_sv_root_css = _SvPath_css(_sv_tmp_css.mkdtemp(prefix="wf_save_css_"))
_sv_real_css = _css_save_backend
_css_save_backend = OverwritingFilesystemBackend(
    root_dir=str(_sv_root_css), virtual_mode=True)
try:
    _rt = lambda **kw: SimpleNamespace(state=kw, tool_call_id="t-save")
    _F  = _sv_root_css / "preview_s1.css"

    # Case 1 [NORMAL] clean lint -> file on disk is byte-identical to state
    _r = save_css_file.func(_rt(session_id="s1", css_code='body { margin: 0; }',
                                lint_passed=True))
    print("[Case 1 · NORMAL] lint clean: state is written to disk verbatim")
    print("  message:", _r.update["messages"][0].content)
    assert "Saved" in _r.update["messages"][0].content
    assert _F.read_text(encoding="utf-8") == 'body { margin: 0; }', \
        "FAIL: disk differs from state"
    print("PASS: disk == state by construction\n")

    # Case 2 [GUARD] unsettled lint gate -> refused, nothing written
    _F.unlink()
    _r = save_css_file.func(_rt(session_id="s1", css_code='body { margin: 0; }',
                                lint_passed=False, lint_escalated=False))
    print("[Case 2 · GUARD] lint not passed and not escalated: save refused")
    print("  message:", _r.update["messages"][0].content[:70])
    assert "Save refused" in _r.update["messages"][0].content
    assert not _F.exists(), "FAIL: file written despite the refused gate"
    print("PASS: unlinted code cannot reach disk\n")

    # Case 3 [NORMAL] escalated cap -> best-effort save allowed
    _r = save_css_file.func(_rt(session_id="s1", css_code='body { margin: 0; }',
                                lint_passed=False, lint_escalated=True))
    print("[Case 3 · NORMAL] lint cap escalated: best-effort save allowed")
    print("  message:", _r.update["messages"][0].content)
    assert "Saved" in _r.update["messages"][0].content and _F.exists()
    print("PASS: the cap's save-best-effort instruction is honoured\n")

    # Case 4 [INVARIANT] modify mode: an existing file is REPLACED exactly.
    # This is the OverwritingFilesystemBackend doing the work — with the stock
    # parent backend this save would be refused ("already exists").
    _r = save_css_file.func(_rt(session_id="s1", css_code='body { margin: 8px; }',
                                lint_passed=True))
    print("[Case 4 · INVARIANT] second save replaces the first (modify mode)")
    print("  on disk now:", _F.read_text(encoding="utf-8")[:44])
    assert "Save failed" not in _r.update["messages"][0].content
    assert _F.read_text(encoding="utf-8") == 'body { margin: 8px; }'
    print("PASS: revised artifact persisted over the original\n")

    # Case 5 [GUARD] empty code -> refused
    _r = save_css_file.func(_rt(session_id="s1", css_code="", lint_passed=True))
    print("[Case 5 · GUARD] empty css_code refused")
    print("  message:", _r.update["messages"][0].content)
    assert "empty" in _r.update["messages"][0].content
    print("PASS: nothing to save is an error, not a blank file\n")

    # Case 6 [GUARD] missing session_id -> refused (never guess the filename)
    _r = save_css_file.func(_rt(session_id="", css_code='body { margin: 0; }',
                                lint_passed=True))
    print("[Case 6 · GUARD] missing session_id refused")
    print("  message:", _r.update["messages"][0].content)
    assert "session_id" in _r.update["messages"][0].content
    print("PASS: the preview filename is never guessed\n")

    print("All 6 cases passed - save_css_file.")
finally:
    _css_save_backend = _sv_real_css
    _sv_sh_css.rmtree(_sv_root_css, ignore_errors=True)
