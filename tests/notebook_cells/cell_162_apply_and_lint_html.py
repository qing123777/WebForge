# Ported from fyp.ipynb cell 162 (ticket 05). The notebook is frozen;
# edit this file. Run by tests/test_notebook_cells.py.
# Unit tests: apply_and_lint_html
# Run in the live kernel (uses real html-validate for the clean-apply case; no LLM).
import types as _t_alh

_ALH_HTML = (
    '<!DOCTYPE html>\n<html lang="en">\n<head>\n<meta charset="utf-8">\n'
    '<title>Shop</title>\n</head>\n<body>\n'
    '<nav id="navbar"><a href="index.html">Home</a></nav>\n'
    '<main><p id="tagline">Old tagline</p></main>\n'
    '</body>\n</html>\n'
)

def _alh_rt(html=_ALH_HTML, selector="#tagline", instance=1):
    return _t_alh.SimpleNamespace(
        state={"html_code": html, "target_component": selector,
               "target_instance": instance,
               "lint_attempts": 0, "lint_escalated": False},
        tool_call_id="t1")

_alh_block = _html_element_for(_ALH_HTML, "#tagline", 1)
assert _alh_block == '<p id="tagline">Old tagline</p>', f"setup serialization: {_alh_block!r}"
_alh_diff = ("--- original\n+++ revised\n@@ -1,1 +1,1 @@\n"
             f"-{_alh_block}\n+{_alh_block.replace('Old tagline', 'New tagline')}\n")

# 1. clean apply — merged tool applies AND reports (lint verdict appended, not asserted)
_r = apply_and_lint_html.func(_alh_diff, _alh_rt()).update
assert "Diff applied." in _r["messages"][0].content, _r["messages"][0].content
assert "New tagline" in _r.get("html_code", ""), "case 1: html not updated"
print("[apply_and_lint_html 1] PASS clean apply updates html and reports")

# 2. patch fault — hand back the CURRENT element, leave html unchanged
_bad = ("--- original\n+++ revised\n@@ -1,1 +1,1 @@\n"
        '-<p id="tagline">DOES NOT MATCH</p>\n+<p id="tagline">x</p>\n')
_r = apply_and_lint_html.func(_bad, _alh_rt()).update
_m = _r["messages"][0].content
assert _m.startswith("Patch failed:") and 'id="tagline"' in _m and "CURRENT element" in _m, _m
assert "html_code" not in _r, "case 2: html must not change on patch fault"
print("[apply_and_lint_html 2] PASS patch fault hands back element, no html change")

# 3. selector not found
_r = apply_and_lint_html.func(_alh_diff, _alh_rt(selector="#missing")).update
assert "No element found" in _r["messages"][0].content and "html_code" not in _r
print("[apply_and_lint_html 3] PASS not-found reported")

# 4. instance out of range
_r = apply_and_lint_html.func(_alh_diff, _alh_rt(instance=5)).update
assert "out of range" in _r["messages"][0].content
print("[apply_and_lint_html 4] PASS instance out of range reported")

# 5/6. unset selector, empty html
assert "target_component not set" in apply_and_lint_html.func(_alh_diff, _alh_rt(selector="")).update["messages"][0].content
assert "html_code is empty" in apply_and_lint_html.func(_alh_diff, _alh_rt(html="")).update["messages"][0].content
print("[apply_and_lint_html 5-6] PASS unset selector and empty html reported")
# 7. an empty call is refused, not applied (13b71045: diffs=[] was "applied")
for _empty_kw in ({"diffs": []}, {"diffs": None}):
    _r = apply_and_lint_html.func("", _alh_rt(), **_empty_kw).update
    assert "No diff supplied" in _r["messages"][0].content, _r["messages"][0].content
    assert "html_code" not in _r and "lint_passed" not in _r, "case 7: empty call must change nothing"
print("[apply_and_lint_html 7] PASS empty diffs=[] / blank diff_output refused, nothing applied")
print("apply_and_lint_html: 7/7 passed")
