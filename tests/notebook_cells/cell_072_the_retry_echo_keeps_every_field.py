# Ported from fyp.ipynb cell 72 (ticket 05). The notebook is frozen;
# edit this file. Run by tests/test_notebook_cells.py.
# Unit tests: the retry echo keeps every field (2026-08-31).
# REGRESSION for PO-08 po015c7e79. The components stage was rejected three
# times. Attempt 1 failed on two empty regions and had a CORRECT dataSets;
# attempts 2 and 3 failed on the same two regions PLUS "dataSets is empty".
# Nothing about the model changed between them. _retry_feedback rendered the
# previous answer at indent=2 and kept the first 60,000 characters, and a real
# component specification measured 90,457 characters indented with "dataSets"
# starting at 86,780 -- always the last top-level field, so always the first
# thing a tail cut removes. The model was told to keep what was not criticised
# while looking at an echo where that field was gone. The retry loop broke a
# field the model had already got right, and the guard then blamed the model.
_re_passed = 0


def _re_spec(n_regions=140, n_products=8):
    """A component-specification-shaped answer: one huge field, one small one."""
    pages = [{
        "pageName": "shop",
        "regionComponents": {
            f"region-{r}": [{
                "id": f"c-{r}-{k}", "tag": "section", "ownedBy": "HTML",
                "className": f"cls-{r}-{k}", "props": {"note": "x" * 120},
                "children": [],
            } for k in range(4)]
            for r in range(n_regions)
        },
    }]
    data_sets = {"products": [{"id": f"p{k}", "name": f"Roast {k}",
                              "price": "18.00"} for k in range(n_products)]}
    # dataSets LAST, exactly as the schema serialises it.
    return {"pages": pages, "dataSets": data_sets}


# A small answer is echoed whole, with no note and no indentation.
_small = {"pages": [{"pageName": "shop", "regionComponents": {}}],
          "dataSets": {"products": [{"id": "p1", "name": "Roast"}]}}
_body, _note = _render_previous_answer(_small)
assert _note == "", _note
assert json.loads(_body) == _small, "RE-1 FAIL: a small answer was altered"
assert "\n" not in _body, "RE-1 FAIL: the echo is still indented, which doubles it"
print("PASS RE-1 - a small answer is echoed compact and unchanged")
_re_passed += 1

# THE REGRESSION. An over-long answer must still carry dataSets in full.
_big = _re_spec()
assert len(json.dumps(_big)) > _RETRY_ANSWER_LIMIT, "fixture too small to test the cut"
_body, _note = _render_previous_answer(_big)
assert '"dataSets"' in _body, "RE-2 FAIL: dataSets was cut off the echo again"
for _rec in _big["dataSets"]["products"]:
    assert _rec["name"] in _body, \
        "RE-2 FAIL: record %r is missing, so the next attempt cannot keep it" % _rec["name"]
print("PASS RE-2 - an over-long answer still shows every record in dataSets")
_re_passed += 1

# Only the biggest field is shortened, and the echo says so in words that stop
# the model emptying the fields it CAN see.
assert _note, "RE-3 FAIL: the answer was shortened without saying so"
assert "'pages'" in _note, _note
assert "COMPLETE" in _note and "never empty one" in _note, _note
assert "dataSets" not in _note, "RE-3 FAIL: the note blames the wrong field"
print("PASS RE-3 - the note names the shortened field and protects the rest")
_re_passed += 1

# The echo stays inside its budget, or the saving is only theoretical.
assert len(_body) <= _RETRY_ANSWER_LIMIT + 4000, len(_body)
# Compact really is the cheaper rendering -- this is the reason for the change,
# so it is asserted rather than assumed.
_indented = json.dumps(_big, ensure_ascii=False, indent=2)
_compact = json.dumps(_big, ensure_ascii=False)
assert len(_compact) < len(_indented) * 0.75, (len(_compact), len(_indented))
print("PASS RE-4 - the echo stays within budget and compact is far cheaper")
_re_passed += 1

# A shape with nothing to protect falls back to the old tail cut, still bounded.
_flat = {"pages": _re_spec()["pages"]}
_body, _note = _render_previous_answer(_flat)
assert len(_body) <= _RETRY_ANSWER_LIMIT + 4000, len(_body)
assert _note, "RE-5 FAIL: a truncated single-field answer said nothing"
print("PASS RE-5 - a single-field answer is bounded and reports the cut")
_re_passed += 1

# An answer that never parsed has nothing to edit, so only the complaint goes.
assert _retry_feedback(None, "the answer could not be parsed", 2) == \
    "the answer could not be parsed"
_fb = _retry_feedback(_small, "dataSets is empty", 1)
assert "YOUR PREVIOUS ANSWER (attempt 1)" in _fb and "dataSets is empty" in _fb
print("PASS RE-6 - _retry_feedback still frames the answer and the complaint")
_re_passed += 1

print("=" * 64)
print("retry echo keeps every field: %d/6 PASSED (no model calls)" % _re_passed)
