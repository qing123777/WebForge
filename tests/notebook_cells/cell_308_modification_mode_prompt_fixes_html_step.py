# Ported from fyp.ipynb cell 308 (ticket 05). The notebook is frozen;
# edit this file. Run by tests/test_notebook_cells.py.
# Unit tests: Modification Mode prompt fixes (HTML Step 0 bug fix, strict-rule
# consistency fix, shared-dependency awareness constraint) across all 3 developer agents.

# ── T1: HTML Step 0 exists, and since speed-cost ticket 03 it says the file is
# already loaded (the orchestrator pre-loads it). read_file + store_html_code
# survive only as the fallback for an empty state. See tests/test_modify_no_echo.py.
# Headings and single-line code snippets are checked raw: neither wraps.
assert "### Step 0 — The current page is already loaded" in _html_modification_prompt,     "HTML Step 0 missing"
assert 'read_file(f"preview_{state.session_id}.html")' in _html_modification_prompt,     "HTML Step 0 fallback does not name read_file on the correct path"
assert "store_html_code(html_code=<file content>)" in _html_modification_prompt,     "HTML Step 0 fallback does not seed html_code via store_html_code"
print("[T1] PASS: HTML Modification Mode has Step 0 (already loaded, with the empty-state fallback)")

# ── T2: Step 0 for HTML comes BEFORE Step 1 (ordering matters) ───────────────
_step0_idx = _html_modification_prompt.find("Step 0")
_step1_idx = _html_modification_prompt.find("Step 1")
assert 0 <= _step0_idx < _step1_idx, "Step 0 must precede Step 1 in HTML prompt"
print("[T2] PASS: HTML Step 0 appears before Step 1")

# Normalize whitespace before any multi-word check. The prompts wrap long
# sentences across lines, so a literal substring check false-negatives on the
# line break even when the sentence is present and correct. This bit T3 for real:
# the apply_and_lint refactor rewrapped "NEVER call store_html_code / again after
# Step 0" across two lines and the assertion started failing on a prompt that was
# entirely correct. Assertions test WORDING, never wrapping.
import re as _re


def _norm(text: str) -> str:
    return _re.sub(r"\s+", " ", text)


_html_norm = _norm(_html_modification_prompt)
_css_norm  = _norm(_css_modification_prompt)
_js_norm   = _norm(_js_modification_prompt)

# ── T3: strict-rule wording no longer self-contradicts (HTML/CSS/JS) ─────────
for _name, _prompt, _fn in [
    ("HTML", _html_norm, "store_html_code"),
    ("CSS",  _css_norm,  "store_css_code"),
    ("JS",   _js_norm,   "store_js_code"),
]:
    assert f"NEVER call {_fn} in this mode, except in the empty-state case Step 0 names" in _prompt,         f"{_name}: strict-rule wording not updated"
    assert f"NEVER call {_fn} in Modification Mode" not in _prompt,         f"{_name}: old contradictory wording still present"
    # Step 0 must actually name the function the rule's exception refers to --
    # otherwise "the empty-state case Step 0 names" would point at nothing.
    assert f"{_fn}(" in _prompt.split("### Step 1")[0],         f"{_name}: Step 0 does not name {_fn}, so the rule wording is inconsistent"
print("[T3] PASS: HTML/CSS/JS strict-rule wording is consistent with their own Step 0")

# ── T4: shared-dependency awareness constraint present in all 3 prompts ──────
# Reuses the normalized prompts built above T3, for the reason documented there.

assert "also referenced elsewhere in html_code" in _html_norm, \
    "HTML awareness constraint missing"
assert "Do NOT rename or remove an existing id/class" in _html_norm, \
    "HTML awareness constraint missing the concrete guardrail"

assert "shared with other components" in _css_norm, \
    "CSS awareness constraint missing"
assert "do NOT edit the shared rule directly" in _css_norm, \
    "CSS awareness constraint missing the concrete guardrail"

assert "shared with other components" in _js_norm, \
    "JS awareness constraint missing"
assert "do NOT edit the shared function's logic directly" in _js_norm, \
    "JS awareness constraint missing the concrete guardrail"
print("[T4] PASS: shared-dependency awareness constraint present in HTML, CSS, and JS")

# ── T5: awareness constraint is phrased as a conditional constraint, not a ───
#        rigid numbered step (GPT-5.4 alignment: constraints > scripted steps)
for _name, _prompt in [
    ("HTML", _html_modification_prompt),
    ("CSS",  _css_modification_prompt),
    ("JS",   _js_modification_prompt),
]:
    _rules_section = _prompt.split("Modification Mode Strict Rules")[-1]
    assert "if" in _rules_section.lower() or "check whether" in _rules_section.lower(), \
        f"{_name}: awareness rule not framed as a conditional constraint"
    assert "### Step 8" not in _prompt and "### Step 9" not in _prompt, \
        f"{_name}: awareness rule was added as a new numbered step, not a constraint"
print("[T5] PASS: awareness rules are conditional constraints, not new numbered steps")

# ── T6: generation prompts (untouched) are unaffected by these edits ─────────
assert "Step 0" not in _html_generation_prompt.split("Generation Mode Strict Rules")[0] \
    or "Load HTML" not in _html_generation_prompt, \
    "HTML generation prompt should not have gained a spurious Step 0 load-file step"
assert _html_generation_prompt != _html_modification_prompt
assert _css_generation_prompt  != _css_modification_prompt
assert _js_generation_prompt   != _js_modification_prompt
print("[T6] PASS: generation prompts remain distinct and unaffected")

print("\nAll 6 Modification Mode prompt fix tests passed.")
