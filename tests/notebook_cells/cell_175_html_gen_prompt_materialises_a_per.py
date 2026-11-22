# Ported from fyp.ipynb cell 175 (ticket 05). The notebook is frozen;
# edit this file. Run by tests/test_notebook_cells.py.
# Unit test: HTML gen prompt materialises a per-record LOAD condition (C2 sold-out bug).
# The State Materialization Contract only set the RESTING/default value, so a sold-out
# record shipped data-state="default" + aria-disabled="false" -- buyable in the DOM while
# its text said sold out (preview_po2r117e13f, card p-sonivox-micpro).
_hp = _html_generation_prompt
assert "### Per-Record Load State" in _hp, "per-record load-state section missing"
assert "is still buyable in the DOM and contradicts its" in _hp, "defect statement missing"
assert "native disabled attribute" in _hp, "native-disabled ban cross-reference missing"
assert "A record whose data marks it sold out" in _hp, "self-check bullet missing"
print("PASS: HTML gen prompt materialises a per-record sold-out/out-of-stock/unavailable "
      "condition on the instance (data-state + aria-disabled=true), not just in prose.")
