# Ported from fyp.ipynb cell 319 (ticket 05). The notebook is frozen;
# edit this file. Run by tests/test_notebook_cells.py.
# Unit test: Test Gen prompt aligned with the flow-produced coverage guard (C1).
# The coverage guard (store_test_cases) now demands only states some interaction flow
# produces; the prompt must say the same, and must add the "no-flow state" branch
# without duplicating the two resting/producing rules it sits beside.
_p = _test_gen_system_prompt
assert "every state an `interaction_specification` flow produces" in _p, "new coverage phrase missing"
assert "- every declared state\n" not in _p, "stale 'every declared state' bullet still present"
assert "A declared state that NO flow produces is not a coverage target" in _p, "no-flow branch missing"
assert "`assert_hover_css` against its `stateVariant`" in _p, "hover/stateVariant guidance missing"
assert "the pipeline cannot reach it" in _p, "scroll/timer no-case guidance missing"
assert "fall back to covering every declared state" in _p, "no-interaction fallback missing"
assert _p.count("Tag covers_state ONLY on the state an interaction PRODUCES") == 1, "producing-state rule duplicated or lost"
assert _p.count("Assert it WITHOUT covers_state so it runs before any interaction") == 1, "resting-state rule duplicated or lost"
print("PASS: Test Gen prompt covers flow-produced states, drops 'every declared state', adds the "
      "no-flow branch once, and keeps the resting/producing rules single.")
