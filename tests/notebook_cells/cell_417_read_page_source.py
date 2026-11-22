# Ported from fyp.ipynb cell 417 (ticket 05). The notebook is frozen;
# edit this file. Run by tests/test_notebook_cells.py.
# Unit tests: read_page_source
# Grounded answers must rest on what is ON DISK, so every branch is checked
# against a real file under _PREVIEW_ROOT (written and cleaned up here).
from types import SimpleNamespace as _SN_RP
import uuid as _rp_uuid


def _rt_rp(sid):
    return _SN_RP(state={"session_id": sid}, tool_call_id="rp-1")


_PREVIEW_ROOT.mkdir(parents=True, exist_ok=True)
_rp_sid  = "utestrp" + _rp_uuid.uuid4().hex[:6]
_rp_file = _PREVIEW_ROOT / f"preview_{_rp_sid}.html"

# Case 1: no session id -> REFUSED, nothing read
_r = read_page_source.func(_rt_rp(""))
assert "REFUSED" in _r.update["messages"][0].content, "FAIL: missing id not refused"
print("PASS read_page_source - missing session id refused")

# Case 2: an unknown part is refused before any read
_r = read_page_source.func(_rt_rp("okid"), part="exe")
_m = _r.update["messages"][0].content
assert "REFUSED" in _m and "html, css or js" in _m, "FAIL: bad part not refused"
print("PASS read_page_source - unknown part refused")

# Case 3: no file on disk -> not-built message, not a crash and not invented
_r = read_page_source.func(_rt_rp("no_such_rp_session"))
assert "has not\n" not in _r.update["messages"][0].content  # sanity on wrapping
assert "not been built yet" in _r.update["messages"][0].content, "FAIL: missing file not reported"
print("PASS read_page_source - missing file reported, not invented")

# Case 4: a real file -> its content comes back, and only messages are written
try:
    _rp_file.write_text("<title>Umbrella World</title>", encoding="utf-8")
    _r = read_page_source.func(_rt_rp(_rp_sid), part="html")
    _m = _r.update["messages"][0].content
    assert "Umbrella World" in _m, "FAIL: file content not returned"
    assert set(_r.update.keys()) == {"messages"}, f"FAIL: extra state written: {_r.update.keys()}"
    print("PASS read_page_source - existing page content returned, only messages written")
finally:
    if _rp_file.exists():
        _rp_file.unlink()

# Case 5: a traversing id cannot read outside the preview dir
_r = read_page_source.func(_rt_rp("../../fyp"), part="html")
_m = _r.update["messages"][0].content
assert "REFUSED" in _m or "not been built" in _m, "FAIL: traversal not contained"
assert "def " not in _m, "FAIL: a traversing id read Python source"
print("PASS read_page_source - traversing id cannot read outside the preview dir")

print("read_page_source: 5/5 PASSED")
