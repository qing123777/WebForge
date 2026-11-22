# Ported from fyp.ipynb cell 177 (ticket 05). The notebook is frozen;
# edit this file. Run by tests/test_notebook_cells.py.
# Unit test: the generation prompt's fix loop uses apply_and_lint_html_full with
# EXACT-TEXT edits (Bucket 2, 2026-08-30) -- the safe replacement for the rolled-back
# whole-page line diff. Modify mode keeps its own component-scoped diff tool.
assert "apply_and_lint_html_full" in _html_generation_prompt, \
    "GEN-EDIT FAIL: the generation prompt never names the edit tool"
assert "Fix by Edit" in _html_generation_prompt, \
    "GEN-EDIT FAIL: the edit-fix step heading is missing"
assert '"old"' in _html_generation_prompt and '"new"' in _html_generation_prompt, \
    "GEN-EDIT FAIL: the {old, new} edit shape is not shown"
assert "NEVER re-send the whole document to store_html_code" in _html_generation_prompt, \
    "GEN-EDIT FAIL: the no-full-resend rule is missing"
assert "use store_html_code only" not in _html_generation_prompt, \
    "GEN-EDIT FAIL: the old 'store only' rule still contradicts the edit loop"
# Modify mode is untouched: component-scoped apply_and_lint_html, no whole-page tool.
assert "apply_and_lint_html_full" not in _html_modification_prompt, \
    "GEN-EDIT FAIL: the whole-page edit tool leaked into modify mode"
# What this guards is that modify still routes through the COMPONENT-scoped
# tool rather than the whole-page one -- and, since 2026-08-31, that it asks for
# the WHOLE batch in one call. A prompt that still said "one at a time" would
# leave the batch arguments unused and the 13-call shape in place.
assert "apply_and_lint_html(diffs=[" in _html_modification_prompt, \
    "GEN-EDIT FAIL: modify mode lost its component-scoped batched diff tool"
assert '"component": ".product-card"' in _html_modification_prompt, \
    ("GEN-EDIT FAIL: the worked example no longer shows each diff naming its own "
     "component, so a batched session would patch whichever element the "
     "last-extracted fallback happens to hold")
print("PASS GEN-EDIT - generation fixes go through apply_and_lint_html_full edits; modify unchanged")
