# Ported from fyp.ipynb cell 163 (ticket 05). The notebook is frozen;
# edit this file. Run by tests/test_notebook_cells.py.
# Unit tests: batched HTML modification (2026-08-31)
# Run in the live kernel (uses real html-validate; no LLM).
#
# What is being proved: five components used to cost 13 model calls (read,
# store, 5 extracts, 5 apply-and-lints, save). Batching makes it 5 and ONE
# linter run. The risk that buys is that a diff is written against text a
# previous diff already changed, so the cases below are mostly about which
# batches are refused and what survives a partial failure.
import types as _t_bh

_bh_passed = 0

def _bh_ok(tag, msg):
    global _bh_passed
    _bh_passed += 1
    print(f"PASS {tag} - {msg}")

_BH_HTML = (
    '<!DOCTYPE html>\n<html lang="en">\n<head>\n<meta charset="utf-8">\n'
    '<title>Shop</title>\n</head>\n<body>\n'
    '<nav id="navbar"><a href="#main">Home</a></nav>\n'
    '<main id="main">\n'
    '<article class="product-card"><h3 class="product-name">Old name</h3>'
    '<p class="price">$1.00</p></article>\n'
    '<p id="tagline">Old tagline</p>\n'
    '</main>\n</body>\n</html>\n'
)

def _bh_rt(html=_BH_HTML, **extra):
    st = {"html_code": html, "target_component": "#tagline", "target_instance": 1,
          "lint_attempts": 0, "lint_escalated": False, "patch_attempts": 0}
    st.update(extra)
    return _t_bh.SimpleNamespace(state=st, tool_call_id="bh1")

def _bh_diff(sel, old, new, html=_BH_HTML):
    """A one-line unified diff turning `old` into `new` inside `sel`."""
    blk = _html_element_for(html, sel, 1)
    assert blk and old in blk, f"fixture: {old!r} not in {blk!r}"
    return ("--- original\n+++ revised\n@@ -1,1 +1,1 @@\n"
            f"-{blk}\n+{blk.replace(old, new)}\n")

# ── extract ────────────────────────────────────────────────────────────────
_r = extract_component.func(_bh_rt(), components=["#navbar", "#tagline"]).update
_m = _r["messages"][0].content
assert "WebForge component 1 of 2: #navbar" in _m, _m
assert "WebForge component 2 of 2: #tagline" in _m, _m
assert 'id="navbar"' in _m and 'id="tagline"' in _m, _m
# One reset for the whole batch: it is one apply and one lint, so it is one budget.
assert _r["lint_attempts"] == 0 and _r["patch_attempts"] == 0, _r
_bh_ok("BH-1", "two disjoint components come back in one message, separated and labelled")

# A single-entry list must be byte-identical to the old single-component call.
# The separator would otherwise become context the model copies into its hunk,
# and the apply would then fail to find it inside the element.
_one  = extract_component.func(_bh_rt(), components=["#tagline"]).update["messages"][0].content
_same = extract_component.func(_bh_rt(), component="#tagline").update["messages"][0].content
assert _one == _same == '<p id="tagline">Old tagline</p>', (_one, _same)
assert "=====" not in _one
_bh_ok("BH-2", "a one-entry batch returns exactly what the single call returns")

# NESTING is MERGED, not refused. .product-name is inside .product-card, so a
# diff against the card re-serialises the heading and the heading's own diff
# would go stale. The answer is one diff against the card -- so the card is
# served once and the note says the heading is inside it. Refusing instead was
# the first design, and on JS it meant batching could never engage at all.
_m = extract_component.func(
    _bh_rt(), components=[".product-card", ".product-name"]).update["messages"][0].content
assert "Refusing" not in _m, _m
assert _m.count("WebForge component") == 0, (
    f"a merge leaves ONE item, and _join_components returns one item "
    f"untouched -- a separator here would break the byte-identical text "
    f"a single-component call depends on:\n{_m}")
assert "SINGLE diff for '.product-card'" in _m, _m
assert "product-name" in _m, "the note must name what the block also covers"
# The label the model passes back has to be the bare keeper name, or the apply
# cannot resolve it.
assert "SINGLE diff for '.product-card'" in _m, _m
_bh_ok("BH-3", "a nested pair is served once as the outer element, with the inner named")

# The OUTER element keeps the label whichever way round the pair is listed: it
# is the only text that can hold both changes.
_m = extract_component.func(
    _bh_rt(), components=[".product-name", ".product-card"]).update["messages"][0].content
assert "SINGLE diff for '.product-card'" in _m, _m
_bh_ok("BH-4", "the outermost element keeps the label, whatever order they were listed")

# A duplicate is dropped, not refused, and never silently.
_m = extract_component.func(
    _bh_rt(), components=["#navbar", "#navbar", "#tagline"]).update["messages"][0].content
assert "named twice" in _m and "#navbar" in _m, _m
assert _m.count("WebForge component") == 2, _m
_bh_ok("BH-5", "a component named twice is dropped once and the drop is reported")

# Over the cap: kept ones are served, dropped ones are NAMED. A silent cap reads
# as "all of it was handled".
_over = [f"#navbar" if n == 0 else f"#nope{n}" for n in range(_MODIFY_BATCH_CAP + 2)]
_wanted, _dropped = _clean_batch(_over)
assert len(_wanted) == _MODIFY_BATCH_CAP and len(_dropped) == 2, (_wanted, _dropped)
assert "over the batch cap" in _dropped[0], _dropped
_bh_ok("BH-6", f"a batch over {_MODIFY_BATCH_CAP} keeps {_MODIFY_BATCH_CAP} and names what it dropped")

# A stale selector is skipped, not fatal -- the page was hand-edited, and the
# other components are still fixable.
_m = extract_component.func(
    _bh_rt(), components=["#navbar", "#gone", "#tagline"]).update["messages"][0].content
assert "Not found" in _m and "#gone" in _m, _m
assert _m.count("WebForge component") == 2, _m
_bh_ok("BH-7", "one stale selector does not cost the whole batch")

# ── apply ──────────────────────────────────────────────────────────────────
_r = apply_and_lint_html.func(runtime=_bh_rt(), diffs=[
    {"component": "#tagline", "diff_output": _bh_diff("#tagline", "Old tagline", "New tagline")},
    {"component": "#navbar",  "diff_output": _bh_diff("#navbar", "Home", "Start")},
]).update
_m = _r["messages"][0].content
assert "Applied 2 of 2 diff(s) in one call." in _m, _m
assert "New tagline" in _r["html_code"] and "Start" in _r["html_code"], _r["html_code"]
assert _r["patch_attempts"] == 0, _r
# ONE linter verdict for the whole batch -- that is the round trip being saved.
assert _m.count("No issues found.") + _m.count("error(s)") == 1, _m
_bh_ok("BH-8", "two diffs land in one call and the page is linted once")

# PARTIAL COMMIT. All-or-nothing would throw away a good fix because a later
# diff miscounted its line numbers, and the model would rewrite both.
_stale = ("--- original\n+++ revised\n@@ -1,1 +1,1 @@\n"
          '-<nav id="navbar">THIS TEXT IS NOT ON THE PAGE</nav>\n'
          '+<nav id="navbar">x</nav>\n')
_r = apply_and_lint_html.func(runtime=_bh_rt(), diffs=[
    {"component": "#tagline", "diff_output": _bh_diff("#tagline", "Old tagline", "New tagline")},
    {"component": "#navbar",  "diff_output": _stale},
]).update
_m = _r["messages"][0].content
assert "Applied 1 of 2 diff(s) in one call." in _m, _m
assert "OK" in _m and "FAILED" in _m and "#navbar" in _m, _m
assert "New tagline" in _r["html_code"], "the diff that applied must be KEPT"
assert _r["patch_attempts"] == 1, _r
assert "Current element for '#navbar'" in _m, _m
_bh_ok("BH-9", "a failed diff keeps the ones that landed, is named, and counts once")

# Nothing landed: html_code must not change, and the patch budget still counts,
# exactly as the single-component path does.
_r = apply_and_lint_html.func(runtime=_bh_rt(), diffs=[
    {"component": "#navbar", "diff_output": _stale},
]).update
assert "html_code" not in _r, "nothing applied, so nothing may be committed"
assert _r["patch_attempts"] == 1, _r
_bh_ok("BH-10", "a batch where nothing applies commits nothing and counts an attempt")

# The single-diff path is untouched by any of this.
_r = apply_and_lint_html.func(
    _bh_diff("#tagline", "Old tagline", "New tagline"), _bh_rt()).update
assert "Diff applied." in _r["messages"][0].content and "New tagline" in _r["html_code"]
_bh_ok("BH-11", "the single-diff call still behaves exactly as before")

# A single-component ask inside a batched call returns the WHOLE batch.
# E2E-JS-MM-04's first live run called extract twice while HTML and CSS called it
# once, on the same afternoon and the same prompt shape -- model variance, not a
# missing instruction. The tool cannot stop a second call, so it makes the first
# one complete and the second one pointless.
_r = extract_component.func(
    _bh_rt(target_components=["#navbar", "#tagline"]), component="#navbar").update
_m = _r["messages"][0].content
assert "WebForge component 1 of 2: #navbar" in _m and "#tagline" in _m, _m
assert "You asked for ONE component" in _m and "Do NOT call this tool again" in _m, _m
assert "apply_and_lint_html" in _m, _m
_bh_ok("BH-12", "asking for one component in a batched call returns all of them")

# A genuinely single-target call is untouched: one entry in target_components
# means there is no batch to upgrade to.
_m = extract_component.func(
    _bh_rt(target_components=["#navbar"]), component="#navbar").update["messages"][0].content
assert _m == '<nav id="navbar"><a href="#main">Home</a></nav>', _m
_bh_ok("BH-13", "a one-target call is not upgraded and returns the bare element")

print("=" * 64)
print(f"batched HTML modification: {_bh_passed}/13 PASSED (no model calls)")
