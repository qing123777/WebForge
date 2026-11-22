# Ported from fyp.ipynb cell 112 (ticket 18). The notebook is frozen;
# edit this file. Run only by run_live_suite.py, on the webforge/ package.
# Needs: cell 109
# LIVE-LLM: costs credits, run manually only
# ══ E2E-SD-03  A storefront plan, with real product records ══════════════════
# WHY THIS SCENARIO EXISTS
# -----------------------
# Two things were added to the planner on 2026-08-15 and neither has ever been
# produced by a real model.
#
# 1. THE 'home' PAGE TYPE. The prompt carried a full storefront checklist for
#    months while 'home' was missing from PageType, so the checklist the system
#    most needs could never be selected and a storefront had to masquerade as a
#    product listing page. This checks the planner now picks it.
#
# 2. dataSets -- THE RUN'S ACTUAL CONTENT. Without it the component tree says
#    "a product card goes here" and nothing says WHICH products, so the HTML
#    agent invented eight teas and the JS agent invented eight different ones.
#    A click on a card then had no shared record to open a detail view from.
#
# NEITHER FAILURE IS LOUD. An empty dataSets is a valid specification. The page
# builds, it lints clean, and its tests pass, because every guard downstream
# checks that a component is ADDRESSABLE, never that it renders shared content.
# SD-02 cannot see any of this: it was written before both changes.
print("\n" + "=" * 68)
print("[E2E] SD-03  a storefront plan — the 'home' page type and REAL records")
print("=" * 68)
_t0 = _sd_time.perf_counter()
_sd2_state, _sd2_err = run_planning_pipeline(_SD_QUERY_2, {}, progress=print, run_name_prefix="E2E-SD-03")
_sd2_el = _sd_time.perf_counter() - _t0
assert _sd2_err is None, f"SD-03 FAIL: the planning chain stopped early: {_sd2_err}"

_layout2 = _sd_spec(_sd2_state, "layout_specification") or {}
_comps2  = _sd_spec(_sd2_state, "components_specification") or {}
assert _layout2 and _comps2, (
    f"SD-03 FAIL: layout or components specification empty. State keys: "
    f"{sorted(_sd2_state)[:20]}")

# 1. still exactly one page, and it is a STOREFRONT
_pages2 = _layout2.get("pages") or []
assert len(_pages2) == 1, (
    f"SD-03 FAIL: {len(_pages2)} page(s) planned, and this system builds one "
    f"document per run.")
_ptype = _pages2[0].get("pageType")
print(f"[E2E] page {_pages2[0].get('pageName')!r} planned as {_ptype!r}")
assert _ptype == "home", (
    f"SD-03 FAIL: the brief says 'home page for an online tea shop' and the plan "
    f"is a {_ptype!r}. The Baymard storefront checklist -- hero, categories, "
    f"featured strip -- only applies to 'home', so it never ran for this plan.")

# 2. THE POINT OF THIS SCENARIO -- real, shared records exist
_ds = _comps2.get("dataSets") or {}
print(f"[E2E] dataSets: { {k: len(v) for k, v in _ds.items()} or 'NONE' }")
assert _ds, (
    "SD-03 FAIL: dataSets is empty. Nothing tells the HTML and JS agents WHICH "
    "teas to render, so each invents its own list and a click on a card has no "
    "shared record behind it. This is the exact defect dataSets was added for, "
    "and no linter, guard or generated test would report it.")

_records = [r for recs in _ds.values() for r in recs]
assert len(_records) >= 3, (
    f"SD-03 FAIL: only {len(_records)} record(s) across all datasets. The brief "
    f"asks for six teas.")

# Every record needs a unique id and a name. The schema validator enforces this,
# so a breach here means the specification reached state without validation.
_ids = [str(r.get("id") or "").strip() for r in _records]
_names = [str(r.get("name") or "").strip() for r in _records]
assert all(_ids) and all(_names), (
    "SD-03 FAIL: a record is missing 'id' or 'name'. Every downstream guard "
    "matches records on those two fields.")
assert len(set(_ids)) == len(_ids), (
    f"SD-03 FAIL: duplicate record ids {_ids}. Ids say which record a card was "
    f"clicked for.")

# 3. the records must be real CONTENT, not scaffolding. "Product 1" passes every
#    structural check above and is useless on a page a human looks at.
import re as _sd_re
_placeholder = [n for n in _names
                if _sd_re.fullmatch(r"(product|item|tea|name)\s*\d*", n,
                                    _sd_re.I)]
assert not _placeholder, (
    f"SD-03 FAIL: placeholder names {_placeholder}. The field asks for real, "
    f"plausible content and these render as filler on the finished page.")

_priced = [r for r in _records
           if any("price" in str(k).lower() for k in r)]
assert _priced, (
    f"SD-03 FAIL: no record carries a price, and the brief asks for a price on "
    f"every tea. Record keys seen: {sorted({k for r in _records for k in r})}")

# 4. and something must actually READ them, or the records sit unused
_bound = [c for c in _sd_walk_components(_comps2) if c.get("dataBinding")]
print(f"[E2E] {len(_bound)} component(s) declare a dataBinding")
_sd2_rows, _sd2_empty = _sd_region_coverage(
    _layout2, _comps2)
print("[E2E] region coverage: " + " | ".join(_sd2_rows))
assert not _sd2_empty, (
    "SD-03 FAIL: the layout declared these regions and the components "
    "generator left them EMPTY, so nothing downstream can build or style them: "
    + ", ".join(_sd2_empty))
print("[E2E] every HTML-owned region received components")


_c3, _st3, _ev3, _tot3 = _sd_target_count(_comps2)
print(f"[E2E] coverage targets: {_c3} components + {_st3} states + {_ev3} events "
      f"= {_tot3} total (one test case per target -- the suite size C' shrinks)")
assert _bound, (
    "SD-03 FAIL: no component declares a dataBinding, so nothing in the tree "
    "says it renders from the shared records.")

print(f"[E2E] sample records: {[n for n in _names[:4]]}")
print(f"[E2E] Profile SD-03 - {_sd2_el:.0f}s, {len(_records)} record(s) in "
      f"{len(_ds)} dataset(s)")
# 5. DESIGN TOKENS -- the theme bundle plus the shared layout preset must reach
#    the decoration spec's globalTokens (mirrors the SD-02 check). globalTokens
#    is bucketed (colors/typography/spacing/...); flatten it and require EVERY
#    _LAYOUT_PRESET key, since that preset rides in every theme.
_deco2 = _sd_spec(_sd2_state, "decoration_specification") or {}
_gt2 = _deco2.get("globalTokens") or {}
_gt2_keys = {k for _bucket in _gt2.values() if isinstance(_bucket, dict) for k in _bucket}
assert _gt2_keys, (
    "SD-03 FAIL: globalTokens is empty. The decoration stage must copy the "
    "theme bundle verbatim; an empty bundle means the CSS agent gets no tokens.")
_preset_missing2 = [k for k in _LAYOUT_PRESET if k not in _gt2_keys]
assert not _preset_missing2, (
    f"SD-03 FAIL: layout preset key(s) missing from globalTokens: {_preset_missing2}. "
    f"The shared layout preset must ride in every theme's bundle.")
_has_colour2 = any(k.startswith("--color-") for k in _gt2_keys)
assert _has_colour2, (
    "SD-03 FAIL: globalTokens carries no --color-* token, so the CSS agent has "
    "no theme colour to reference.")
print(f"[E2E] globalTokens: {len(_gt2_keys)} token(s); all {len(_LAYOUT_PRESET)} "
      f"layout-preset keys present; colour tokens present")
_ic3_qt, _ic3_qo, _ic3_ct, _ic3_co = _interactive_completeness(_sd_walk_components(_comps2))
print(f"[E2E][proof] interactive completeness: {_ic3_qo}/{_ic3_qt} quantity-selector(s) carry a "
      f"+/- control, {_ic3_co}/{_ic3_ct} mini-cart(s) carry a close control. Before the components "
      f"guard PO-10 po07cdf97e shipped 0/1 and 0/1; the guard now refuses such a spec, so any that "
      f"reaches here MUST be complete. A 0 total means this brief produced no cart drawer.")
assert _ic3_qo == _ic3_qt, (
    f"SD-03 FAIL: {_ic3_qt - _ic3_qo} quantity-selector(s) reached the spec with no +/- control -- "
    f"the components guard should have refused it.")
assert _ic3_co == _ic3_ct, (
    f"SD-03 FAIL: {_ic3_ct - _ic3_co} mini-cart(s) reached the spec with no close control -- "
    f"the components guard should have refused it.")
_SD_RESULTS["SD-03"] = True
print("=" * 68)
print(f"PASS E2E-SD-03  storefront planned as 'home', {len(_records)} real "
      f"records shared across the agents")
print("=" * 68)

# All four stages, in the order they ran. The planner is only as fast as its
# slowest stage, and this is the one place that shows which one that is.
print()
spec_timing_report()
