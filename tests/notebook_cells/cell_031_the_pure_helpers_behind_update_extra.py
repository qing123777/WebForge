# Ported from fyp.ipynb cell 31 (ticket 05). The notebook is frozen;
# edit this file. Run by tests/test_notebook_cells.py.
# Unit tests: the pure helpers behind update_extra_requirements
#
# These three functions never call a model or the network, so they can be
# tested offline. The tool that wraps them is covered by the live test cell
# below this one.
_ER_CASES = 0

# ── Case 1: a schema arrives in three different shapes ──────────────────────
# The tool is handed whatever is sitting in state. That may be a model object,
# a plain dict, or nothing at all if extraction has not run yet.
assert _normalize_schema_payload(None) == {}, "Case 1 FAIL: None should become an empty dict"
assert _normalize_schema_payload("not a schema") == {}, \
    "Case 1 FAIL: a stray string should become an empty dict, not raise"
assert _normalize_schema_payload({"ui": {"type": "cart"}}) == {"ui": {"type": "cart"}}, \
    "Case 1 FAIL: a dict should pass through untouched"
assert _normalize_schema_payload(DesignSchema())["ui"]["type"] is None, \
    "Case 1 FAIL: a schema object should be converted to a dict"
_ER_CASES += 1
print("PASS Case 1 - a missing, stray, dict or object payload all normalise safely")

# ── Case 2: an item longer than twelve words is cut ─────────────────────────
# These strings are read by the planning chain. A paragraph pasted from a
# search result would drown the requirements the user actually stated.
_long = " ".join(str(n) for n in range(20))
assert len(_clean_item(_long).split()) == 12, \
    f"Case 2 FAIL: expected 12 words, got {len(_clean_item(_long).split())}"
assert _clean_item("  sticky promo banner  ") == "sticky promo banner", \
    "Case 2 FAIL: surrounding spaces were not removed"
assert _clean_item("") == "" and _clean_item(None) == "" and _clean_item("   ") == "", \
    "Case 2 FAIL: an empty item should stay empty rather than raise"
_ER_CASES += 1
print("PASS Case 2 - a long item is cut to 12 words, an empty one stays empty")

# ── Case 3: nothing the user asked for is ever overwritten ──────────────────
# This is the whole safety property of the tool. Web findings are appended.
_base = DesignSchema(
    ui=UI(type="product_listing"),
    theme=Theme(mode="dark"),
    extra_requirements=["sticky promo banner"],
).model_dump()
_merged = _merge_extra_requirements(_base, ["free shipping badge"])
assert _merged["ui"]["type"] == "product_listing" and _merged["theme"]["mode"] == "dark", \
    "Case 3 FAIL: a stated requirement was overwritten by the merge"
assert _merged["extra_requirements"] == ["sticky promo banner", "free shipping badge"], \
    f"Case 3 FAIL: the new item was not appended in order: {_merged['extra_requirements']}"
_ER_CASES += 1
print("PASS Case 3 - existing fields survive and the new item is appended")

# ── Case 4: the same finding is never added twice ──────────────────────────
# The search runs on every generation, so the same trend comes back repeatedly.
# Without this the list would grow without bound across a conversation.
_dupes = _merge_extra_requirements(_base, ["Sticky Promo Banner", "sticky promo banner",
                                           "  STICKY promo banner  "])
assert _dupes["extra_requirements"] == ["sticky promo banner"], \
    f"Case 4 FAIL: a repeat in different case was added again: {_dupes['extra_requirements']}"
_ER_CASES += 1
print("PASS Case 4 - a repeat is refused whatever its capitalisation or spacing")

# ── Case 5: empty and blank findings are ignored ───────────────────────────
_empty = _merge_extra_requirements(_base, ["", "   ", None])
assert _empty["extra_requirements"] == ["sticky promo banner"], \
    f"Case 5 FAIL: a blank finding was added: {_empty['extra_requirements']}"
assert _merge_extra_requirements(_base, [])["extra_requirements"] == ["sticky promo banner"], \
    "Case 5 FAIL: an empty finding list changed the schema"
_ER_CASES += 1
print("PASS Case 5 - blank and empty findings are dropped")

# ── Case 6: an absent schema is built rather than crashed on ────────────────
# The search can finish before extraction has written anything.
_fresh = _merge_extra_requirements(None, ["dark mode is standard in 2026"])
assert _fresh["extra_requirements"] == ["dark mode is standard in 2026"], \
    "Case 6 FAIL: merging into a missing schema lost the item"
assert _fresh["constraints"]["tech_stack"] == ["html", "css", "javascript"], \
    "Case 6 FAIL: the rebuilt schema does not carry the fixed technology list"
_ER_CASES += 1
print("PASS Case 6 - merging into a missing schema builds a valid one")

# ── Case 7: a long finding is cut before it is stored ──────────────────────
_cut = _merge_extra_requirements(DesignSchema().model_dump(), [_long])
assert len(_cut["extra_requirements"][0].split()) == 12, \
    "Case 7 FAIL: the 12-word limit was not applied on the way into the schema"
_ER_CASES += 1
print("PASS Case 7 - the word limit is applied when the item is stored, not only when cleaned")

print("=" * 64)
print(f"update_extra_requirements helpers: {_ER_CASES}/7 cases PASSED")
print("=" * 64)
