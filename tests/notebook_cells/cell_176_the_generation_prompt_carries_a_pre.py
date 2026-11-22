# Ported from fyp.ipynb cell 176 (ticket 05). The notebook is frozen;
# edit this file. Run by tests/test_notebook_cells.py.
# Unit test: the generation prompt carries a pre-submit self-check (Bucket 1,
# 2026-08-30). It lists the coverage-guard requirements AND the html-validate
# (recommended) rules that most often reject a first attempt, so the agent spends
# fewer full-page resends. Every rule id below was confirmed to fire live via
# `npx html-validate`. Modify mode is untouched.
assert "Step 1b" in _html_generation_prompt, \
    "GEN-SELFCHECK FAIL: the self-check step is missing"
for _rule in ("no-inline-style", "aria-label-misuse", "no-raw-characters",
              "no-implicit-button-type", "attribute-boolean-style", "no-dup-id"):
    assert _rule in _html_generation_prompt, \
        f"GEN-SELFCHECK FAIL: linter pitfall {_rule!r} not named"
assert "Every dataSets record is rendered" in _html_generation_prompt, \
    "GEN-SELFCHECK FAIL: record-completeness line missing"
assert "BOTH include tags" in _html_generation_prompt, \
    "GEN-SELFCHECK FAIL: include-tag completeness line missing"
# The block is generation-only: modify mode never regenerates every component,
# so its prompt must not grow this step.
assert "Step 1b" not in _html_modification_prompt, \
    "GEN-SELFCHECK FAIL: the self-check leaked into modify mode"
# Off-canvas panels ship CLOSED: the drawer/modal carries `hidden` at rest, or it
# covers the page from first paint (PO-10 po0735889c shipped <aside id="cart-drawer">
# with no hidden attribute, so the cart drawer sat open over the content).
assert "Off-Canvas Panels Ship Closed" in _html_generation_prompt, \
    "DRAWER-CLOSED FAIL: the off-canvas ship-closed rule is missing"
assert 'cart-drawer" hidden' in _html_generation_prompt, \
    "DRAWER-CLOSED FAIL: the rule must show the hidden attribute on the panel element"
# A search / filter input must ship with an EMPTY value (PO-08 po019fa283 shipped
# value="coffee", filtering the store to zero products at load).
assert "filters the page the moment it loads" in _html_generation_prompt, \
    "SEARCH-EMPTY FAIL: the search-input empty-value rule is missing"
print("PASS SEARCH-EMPTY - a search/filter input ships with no value")
print("PASS DRAWER-CLOSED - off-canvas panels ship with the hidden attribute at rest")
print("PASS GEN-SELFCHECK - generation self-check lists coverage + linter pitfalls; modify unchanged")
