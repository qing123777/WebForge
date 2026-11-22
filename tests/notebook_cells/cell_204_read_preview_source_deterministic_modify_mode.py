# Ported from fyp.ipynb cell 204 (ticket 05). The notebook is frozen;
# edit this file. Run by tests/test_notebook_cells.py.
# Unit tests: _read_preview_source (deterministic modify-mode seed)
#
# Pure disk-read helper. Exercised offline against a temp file written into the
# real preview root, then removed. No LLM, no agent.
import uuid as _rps_uuid, os as _rps_os

_rps_sid  = "utest_" + _rps_uuid.uuid4().hex[:8]
_rps_path = _PREVIEW_ROOT / f"preview_{_rps_sid}.js"
_rps_body = "// seed-test\nconst x = 1;\n"
_PREVIEW_ROOT.mkdir(parents=True, exist_ok=True)
_rps_path.write_text(_rps_body, encoding="utf-8")
try:
    print("[Case 1 · NORMAL] Existing file: contents returned verbatim.")
    _got = _read_preview_source(_rps_sid, "js")
    assert _got == _rps_body, f"FAIL: {_got!r} != {_rps_body!r}"
    print(f"read {len(_got)} chars, identical to what was written")
    print("PASS: existing file read verbatim\n")

    print("[Case 2 · EDGE] Missing file: returns empty string, does not raise.")
    assert _read_preview_source(_rps_sid, "css") == "", "FAIL: missing .css not empty"
    assert _read_preview_source("no_such_session_xyz", "js") == "", "FAIL: missing session not empty"
    print("PASS: missing file -> empty string\n")

    print("[Case 3 · EDGE] Empty session_id: short-circuits to empty string.")
    assert _read_preview_source("", "js") == "", "FAIL: empty session_id not empty"
    print("PASS: empty session_id -> empty string\n")
finally:
    if _rps_path.exists():
        _rps_os.remove(_rps_path)

print("[Case 4 · NORMAL] _safe_session_id accepts what the UI actually issues.")
import uuid as _sid_uuid
_real_thread_id = str(_sid_uuid.uuid4())
assert _safe_session_id(_real_thread_id) == _real_thread_id, \
    "FAIL: a Streamlit thread_id (str(uuid4)) must pass unchanged"
for _ok in ("so01", "a", "A-b_C-9", "0" * 64, "utest_1a2b3c4d"):
    assert _safe_session_id(_ok) == _ok, f"FAIL: {_ok!r} should be accepted"
print(f"accepted str(uuid4) = {_real_thread_id} (36 chars) and 5 shorter forms")
print("PASS: valid ids pass through unchanged\n")

print("[Case 5 · MALICIOUS] Traversal and separators are rejected.")
# preview_{id}.css is built by string interpolation, so an id containing a
# separator escapes the preview root entirely.
for _bad in ("../../secrets", "..", "a/b", "a\\b", "C:/Windows/x", "a.b", "a b"):
    assert _safe_session_id(_bad) == "", f"FAIL: {_bad!r} should be rejected"
assert _read_preview_source("../../fyp", "py") == "", \
    "FAIL: _read_preview_source must refuse a traversing id, not read the file"
print("PASS: traversal, separators, dots and spaces all rejected\n")

print("[Case 6 · EDGE] Empty, over-length and non-string all return \"\".")
assert _safe_session_id("") == "", "FAIL: empty accepted"
assert _safe_session_id("0" * 65) == "", "FAIL: 65 chars accepted"
for _bad in (None, 123, b"abc", ["a"]):
    assert _safe_session_id(_bad) == "", f"FAIL: {_bad!r} accepted"
print("PASS: empty / 65-char / non-string all rejected\n")


print("[Case 7 · NORMAL] _preview_fingerprint sees a real file, and its changes.")
_fp_sid  = "utest_" + _rps_uuid.uuid4().hex[:8]
_fp_path = _PREVIEW_ROOT / f"preview_{_fp_sid}.css"
try:
    assert _preview_fingerprint(_fp_sid, "css") is None, "FAIL: missing file not None"
    _fp_path.write_text("a{color:red}", encoding="utf-8")
    _f1 = _preview_fingerprint(_fp_sid, "css")
    assert _f1 and _f1[0] == 12, f"FAIL: size wrong: {_f1}"
    assert _preview_fingerprint(_fp_sid, "css") == _f1, "FAIL: not stable"
    _fp_path.write_text("a{color:blue}", encoding="utf-8")
    _f2 = _preview_fingerprint(_fp_sid, "css")
    assert _f2[1] != _f1[1], "FAIL: a content change did not change the hash"
    print(f"absent -> None, then {_f1[0]}B, then {_f2[0]}B with a different hash")
    print("PASS: fingerprint tracks existence and content\n")

    print("[Case 8 · MALICIOUS] A traversing id fingerprints as absent.")
    assert _preview_fingerprint("../../fyp", "py") is None, "FAIL: traversal read"
    print("PASS: the validator gates this path too\n")

    print("[Case 9 · GUARD] _artifact_outcome refuses to call an unchanged file a fix.")
    # This is the exact E2E-SO-01 shape: the agent ran, said it could not act,
    # and the tool reported a save anyway.
    _same = _artifact_outcome("CSS Agent", "css", _fp_sid, _f2, _f2)
    assert "NOT modified" in _same and "Do NOT report" in _same, _same
    assert "saved to file system" not in _same, "FAIL: the old claim survives"
    print("   ", _same[:100])
    _new = _artifact_outcome("CSS Agent", "css", _fp_sid, None, _f2)
    assert "created" in _new, _new
    _upd = _artifact_outcome("CSS Agent", "css", _fp_sid, _f1, _f2)
    assert "updated" in _upd and "12 -> 13 bytes" in _upd, _upd
    _gone = _artifact_outcome("CSS Agent", "css", _fp_sid, _f1, None)
    assert "DOES NOT EXIST" in _gone and "NOT APPLIED" in _gone, _gone
    print("PASS: unchanged / created / updated / absent each report the truth\n")
finally:
    if _fp_path.exists():
        _rps_os.remove(_fp_path)

print("All 9 cases passed -- preview seed, session-id validator, artifact outcome.")
