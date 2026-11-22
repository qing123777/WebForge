# Ported from fyp.ipynb cell 165 (ticket 05). The notebook is frozen;
# edit this file. Run by tests/test_notebook_cells.py.
# Unit tests: _apply_search_replace (exact-text applicator) + apply_and_lint_html_full
#
# The applicator is pure and runs for real. The tool composes it with
# store_html_code's guard + _lint_html_source, both stubbed here so the test
# exercises THIS tool's wiring -- the guard is already covered by store_html_code's
# 37 cases and the linter by run_html_validate's.
from types import SimpleNamespace as _alf_ns

# ---- _apply_search_replace: the safety invariant lives here ------------------
_SR_HTML = "<html>\n<body>\n<p>old</p>\n<span>keep</span>\n</body>\n</html>\n"
_sr_passed = 0

# SR-1 unique match -> replaced
_t, _e = _apply_search_replace(_SR_HTML, [{"old": "<p>old</p>", "new": "<p>new</p>"}])
assert _e is None and "<p>new</p>" in _t and "<p>old</p>" not in _t, "SR-1"
print("PASS SR-1 - a unique match is replaced"); _sr_passed += 1

# SR-2 not found -> unchanged, error explains
_t, _e = _apply_search_replace(_SR_HTML, [{"old": "<p>MISSING</p>", "new": "x"}])
assert _t == _SR_HTML and _e and "not found" in _e, "SR-2"
print("PASS SR-2 - a miss changes nothing and says so"); _sr_passed += 1

# SR-3 ambiguous (appears twice) -> unchanged, error counts them
_dup = "<li>x</li>\n<li>x</li>\n"
_t, _e = _apply_search_replace(_dup, [{"old": "<li>x</li>", "new": "<li>y</li>"}])
assert _t == _dup and _e and "appears 2 times" in _e, "SR-3"
print("PASS SR-3 - an ambiguous match changes nothing"); _sr_passed += 1

# SR-4 several edits all apply, in order
_t, _e = _apply_search_replace(_SR_HTML, [
    {"old": "<p>old</p>", "new": "<p>A</p>"},
    {"old": "<span>keep</span>", "new": "<span>B</span>"}])
assert _e is None and "<p>A</p>" in _t and "<span>B</span>" in _t, "SR-4"
print("PASS SR-4 - several edits all apply"); _sr_passed += 1

# SR-5 one good + one bad -> WHOLE batch reverts, original returned
_t, _e = _apply_search_replace(_SR_HTML, [
    {"old": "<p>old</p>", "new": "<p>A</p>"},
    {"old": "<p>MISSING</p>", "new": "x"}])
assert _t == _SR_HTML and _e and "Edit 2" in _e, "SR-5"
print("PASS SR-5 - one bad edit reverts the whole batch (no partial corruption)"); _sr_passed += 1

# SR-6 malformed edit -> error, unchanged
_t, _e = _apply_search_replace(_SR_HTML, [{"old": "<p>old</p>"}])
assert _t == _SR_HTML and _e and "malformed" in _e, "SR-6"
print("PASS SR-6 - a malformed edit is rejected"); _sr_passed += 1

# SR-7 empty list -> error, unchanged
_t, _e = _apply_search_replace(_SR_HTML, [])
assert _t == _SR_HTML and _e and "No edits" in _e, "SR-7"
print("PASS SR-7 - an empty edit list is rejected"); _sr_passed += 1

print(f"_apply_search_replace: {_sr_passed}/7 PASSED")

# ---- apply_and_lint_html_full: wiring around the applicator ------------------
_ALF_HTML = "<html>\n<body>\n<p>old</p>\n</body>\n</html>\n"
_ALF_GOOD = [{"old": "<p>old</p>", "new": "<p>new</p>"}]
_ALF_MISS = [{"old": "<p>WRONG</p>", "new": "<p>new</p>"}]


def _alf_rt(html):
    return _alf_ns(state={"html_code": html, "intent": "generate",
                          "session_id": "s1"}, tool_call_id="alf-1")


def _alf_run(html, edits, guard_pass=True, guard_msg="ok"):
    """Run apply_and_lint_html_full with store_html_code + _lint_html_source stubbed."""
    real_store, real_lint = store_html_code, _lint_html_source

    def _store_stub(code, rt):
        if guard_pass:
            return Command(update={"html_code": code, "messages": [
                ToolMessage(content="HTML code saved to state.", tool_call_id="x")]})
        return Command(update={"messages": [
            ToolMessage(content=guard_msg, tool_call_id="x")]})

    def _lint_stub(code, rt):
        return Command(update={"lint_passed": True, "messages": [
            ToolMessage(content="No issues found.", tool_call_id="x")]})

    globals()["store_html_code"] = _alf_ns(func=_store_stub)
    globals()["_lint_html_source"] = _lint_stub
    try:
        return apply_and_lint_html_full.func(edits, _alf_rt(html))
    finally:
        globals()["store_html_code"] = real_store
        globals()["_lint_html_source"] = real_lint


_alf_passed = 0

# A: a good edit whose page passes the guard -> patched page stored, lint attached
_rA = _alf_run(_ALF_HTML, _ALF_GOOD, guard_pass=True)
assert "<p>new</p>" in _rA.update.get("html_code", ""), "ALF-A FAIL: edited html not stored"
assert _rA.update.get("lint_passed") is True, "ALF-A FAIL: lint verdict not attached"
assert "No issues found." in _rA.update["messages"][0].content, "ALF-A FAIL: lint message missing"
print("PASS ALF-A - good edit: page stored, guard run, lint attached"); _alf_passed += 1

# B: the edited page fails the guard -> wrapped message, nothing stored
_rB = _alf_run(_ALF_HTML, _ALF_GOOD, guard_pass=False,
               guard_msg="Image contract violation(s): an <img> has no supported source")
assert "html_code" not in _rB.update, "ALF-B FAIL: a page failing the guard was stored"
_mB = _rB.update["messages"][0].content
assert "still fails a generation check" in _mB and "Image contract" in _mB, _mB
print("PASS ALF-B - guard rejection after edit is surfaced, page not stored"); _alf_passed += 1

# C: an edit whose 'old' is not found -> page untouched, told why
_rC = _alf_run(_ALF_HTML, _ALF_MISS, guard_pass=True)
assert "html_code" not in _rC.update, "ALF-C FAIL: a missing-target edit still stored something"
_mC = _rC.update["messages"][0].content
assert "not found" in _mC and "UNCHANGED" in _mC, "ALF-C FAIL: no-op not reported"
print("PASS ALF-C - an edit that matches nothing leaves the page unchanged"); _alf_passed += 1

# D: empty html_code -> told to store the full page first
_rD = _alf_run("", _ALF_GOOD, guard_pass=True)
assert "html_code" not in _rD.update, "ALF-D FAIL: stored from an empty page"
assert "Store the full page" in _rD.update["messages"][0].content, "ALF-D FAIL"
print("PASS ALF-D - an empty page is told to store the full page first"); _alf_passed += 1

# E: an ambiguous edit -> page untouched (the corruption D suffered is impossible)
_rE = _alf_run("<li>x</li>\n<li>x</li>\n", [{"old": "<li>x</li>", "new": "<li>y</li>"}],
               guard_pass=True)
assert "html_code" not in _rE.update, "ALF-E FAIL: an ambiguous edit still stored something"
assert "appears 2 times" in _rE.update["messages"][0].content, "ALF-E FAIL"
print("PASS ALF-E - an ambiguous edit is refused, page unchanged"); _alf_passed += 1

print("=" * 64)
print(f"apply_and_lint_html_full: {_alf_passed}/5 PASSED (no model calls)")
