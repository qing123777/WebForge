# Ported from fyp.ipynb cell 21 (ticket 05). The notebook is frozen;
# edit this file. Run by tests/test_notebook_cells.py.
# Unit tests: the schema-generated worked example
#
# The example used to be typed by hand and drifted illegal without a sound. These
# cases exist so the same drift is a failure here instead of a weaker extraction
# in production.
import json as _ex_json
import typing as _ex_typing

_EX_CASES = 0

# ── EX-1: the example is a VALID DesignSchema ──────────────────────────────
# This is the whole point. A hand-written example can name a word the schema
# rejects. One built by the schema cannot.
_ex_obj = _ex_json.loads(_schema_example_json())
_ex_round = DesignSchema(**_ex_obj)
assert _ex_round.model_dump() == _ex_obj, \
    "EX-1 FAIL: the example does not survive a round trip through DesignSchema"
_EX_CASES += 1
print("PASS EX-1 - the worked example is a valid DesignSchema")

# ── EX-2: it fills the three fields added on 2026-08-15 ────────────────────
# An example that leaves them null teaches the model to leave them null, and a
# null in any of them silently switches off a planner branch.
for _f in ("commerce_type", "style"):
    assert _ex_obj["ui"].get(_f), (
        f"EX-2 FAIL: the example leaves ui.{_f} empty, which teaches the model "
        f"to leave it empty too. The planner then falls back to its defaults "
        f"with nothing reporting that the user's request was dropped.")
_EX_CASES += 1
print(f"PASS EX-2 - the example fills commerce_type and style")

# ── EX-3: every fixed list reaches the prompt, in full ─────────────────────
# The model can only pick a word it has been shown. A list that stopped being
# printed would look identical and quietly halve the vocabulary.
_ex_vocab = _schema_vocabularies()
for _label, _lit in (("commerce_type", CommerceType), ("style", DesignStyle)):
    for _v in _ex_typing.get_args(_lit):
        assert _v in _ex_vocab, \
            f"EX-3 FAIL: {_label} value {_v!r} never reaches the prompt"
_EX_CASES += 1
print(f"PASS EX-3 - all {sum(len(_ex_typing.get_args(l)) for l in (CommerceType, DesignStyle))} allowed words reach the prompt")

# ── EX-4: the two-way inference rule replaced the blanket ban ──────────────
# The old prompt said "do not infer unspecified attributes (e.g., colors,
# features, styles)" while the field descriptions said to map loose words onto
# the lists. Faced with a contradiction the safe answer is null, which is the
# failure E2E-CE-02 tests for.
_ex_tpl = _build_intent_extraction_template()
assert "conservative extraction" not in _ex_tpl, \
    "EX-4 FAIL: the conservative-extraction rule is back, and it fights the lists"
assert "ALWAYS map the words the user DID use" in _ex_tpl, \
    "EX-4 FAIL: the prompt no longer tells the model to map what the user said"
assert "Never invent a brand, a colour, or a feature" in _ex_tpl, \
    "EX-4 FAIL: the prompt no longer forbids inventing what the user did not say"
_EX_CASES += 1
print("PASS EX-4 - inventing is forbidden and mapping is required, with no contradiction")

# ── EX-5: only {query} is a placeholder ────────────────────────────────────
# The example is JSON, so it is full of braces. Any one left unescaped would be
# read as a placeholder and the template would fail to render at all.
assert set(_intent_extraction_prompt.input_variables) == {"query", "theme_catalog"}, (
    f"EX-5 FAIL: the template expects {_intent_extraction_prompt.input_variables}. "
    f"An unescaped brace in the example JSON is the usual cause.")
_rendered = _intent_extraction_prompt.format(query="build a tea shop", theme_catalog="- warm-artisanal: warm")
assert "build a tea shop" in _rendered and '"tech_stack"' in _rendered, \
    "EX-5 FAIL: the rendered prompt lost either the query or the example"
_EX_CASES += 1
print("PASS EX-5 - the template renders; {query} and {theme_catalog} are its placeholders")

print("=" * 64)
print(f"Schema-generated example: {_EX_CASES}/5 cases PASSED "
      f"({len(_rendered)} chars rendered)")
print("=" * 64)
