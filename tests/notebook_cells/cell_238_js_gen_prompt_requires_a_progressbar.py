# Ported from fyp.ipynb cell 238 (ticket 05). The notebook is frozen;
# edit this file. Run by tests/test_notebook_cells.py.
# Unit test: JS gen prompt requires a progressbar role wherever it writes aria-valuenow
# (Lighthouse L2). preview_po2r117e13f set aria-valuenow/aria-valuetext on the bare stock
# <div class="flash-sale-stock-remaining"> with no role, invalid ARIA that Lighthouse
# Accessibility (and Agent Accessibility) flagged.
_jp = _js_generation_prompt
assert "### Progress Value Contract" in _jp, "progress-value section missing"
assert 'set role="progressbar", aria-valuemin, and aria-valuemax' in _jp, "role/min/max rule missing"
assert "a stock bar div with aria-valuenow and no role is invalid ARIA" in _jp, "bare-div defect statement missing"
print("PASS: JS gen prompt requires role=progressbar + aria-valuemin/valuemax wherever it "
      "writes aria-valuenow/aria-valuetext; a bare div with aria-valuenow is refused as invalid ARIA.")
