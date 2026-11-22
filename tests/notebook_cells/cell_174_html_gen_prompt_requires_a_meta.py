# Ported from fyp.ipynb cell 174 (ticket 05). The notebook is frozen;
# edit this file. Run by tests/test_notebook_cells.py.
# Unit test: HTML gen prompt requires a <meta name="description"> in <head> (Lighthouse L1).
# preview_po2r117e13f shipped only charset + viewport, so Lighthouse SEO flagged a missing
# meta description. The head-metadata rule + a Self-Check bullet now require it.
_hp = _html_generation_prompt
assert 'name="description"' in _hp, "meta description rule missing"
assert "concise one-sentence summary of THIS page" in _hp, "description content guidance missing"
assert '<head> carries a <meta name="description">' in _hp, "self-check bullet missing"
print("PASS: HTML gen prompt requires a <head> meta description summarising the page.")
