# Ported from fyp.ipynb cell 110 (ticket 18). The notebook is frozen;
# edit this file. Run only by run_live_suite.py, on the webforge/ package.
# Needs: cell 109
# LIVE-LLM: costs credits, run manually only
# ══ E2E-SD-02  System Design Planning, normal brief ══════════════════════════
# Depends on CE-01 only for its design schema; falls back to the raw brief so the
# scenario can be run on its own.
print("\n" + "=" * 68)
print("[E2E] SD-02  planning — four specifications, ONE page, components LABELLED")
print("=" * 68)
_t0 = _sd_time.perf_counter()
_sd_state, _sd_err = run_planning_pipeline(
    _SD_QUERY, globals().get("_CE_SCHEMA") or {}, progress=print,
    run_name_prefix="E2E-SD-02")
_sd_el = _sd_time.perf_counter() - _t0
assert _sd_err is None, f"SD-02 FAIL: the planning chain stopped early: {_sd_err}"

# 1. all four specifications exist
# The planning side spells it interactionS_specification (plural); the
# sub-workflow's own state uses the singular. That is deliberate, and
# call_secondary_orchestrator maps between them explicitly at the boundary.
# This scenario reads the PLANNER's state, so it must use the plural.
_SPEC_KEYS = ["layout_specification", "components_specification",
              "interactions_specification", "decoration_specification"]
_specs = {}
for _k in _SPEC_KEYS:
    _v = _sd_spec(_sd_state, _k)
    assert _v is not None, f"SD-02 FAIL: {_k} is a string that is not valid JSON"
    _specs[_k] = _v
_missing = [k for k, v in _specs.items() if not v]
assert not _missing, (
    f"SD-02 FAIL: {_missing} empty. State keys present: {sorted(_sd_state)[:20]}. "
    f"An empty specification here usually means a write was dropped -- check the "
    f"state schema declares every channel the generators write.")
print(f"[E2E] all four specifications written "
      f"({', '.join(f'{k.split(chr(95))[0]}={len(_sd_json.dumps(v))}c' for k, v in _specs.items())})")

# 1b. DESIGN TOKENS -- the theme bundle plus the shared layout preset must reach
#     the decoration spec's globalTokens (added 2026-08-25). globalTokens is
#     bucketed (colors/typography/spacing/...); flatten it and require EVERY
#     _LAYOUT_PRESET key, since that preset rides in every theme. A theme's own
#     colour tokens must be present too, or the CSS agent has no var(--*) to
#     reference and would hardcode colours.
_gt = (_specs["decoration_specification"] or {}).get("globalTokens") or {}
_gt_keys = {k for _bucket in _gt.values() if isinstance(_bucket, dict) for k in _bucket}
assert _gt_keys, (
    "SD-02 FAIL: globalTokens is empty. The decoration stage must copy the "
    "theme bundle verbatim; an empty bundle means the CSS agent gets no tokens.")
_preset_missing = [k for k in _LAYOUT_PRESET if k not in _gt_keys]
assert not _preset_missing, (
    f"SD-02 FAIL: layout preset key(s) missing from globalTokens: {_preset_missing}. "
    f"The shared layout preset must ride in every theme's bundle.")
_has_colour = any(k.startswith("--color-") for k in _gt_keys)
assert _has_colour, (
    "SD-02 FAIL: globalTokens carries no --color-* token, so the CSS agent has "
    "no theme colour to reference.")
print(f"[E2E] globalTokens: {len(_gt_keys)} token(s); all {len(_LAYOUT_PRESET)} "
      f"layout-preset keys present; colour tokens present")

# 2. exactly one page -- the artefact layer keys every file to session_id alone,
#    so there is nowhere to put a second page and the Secondary Orchestrator
#    refuses a multi-page layout outright
_pages = (_specs["layout_specification"] or {}).get("pages") or []
assert len(_pages) == 1, (
    f"SD-02 FAIL: {len(_pages)} page(s) planned. This system builds ONE document "
    f"per run and call_secondary_orchestrator refuses more: "
    f"{[p.get('pageName') for p in _pages if isinstance(p, dict)]}")
print(f"[E2E] one page planned: {_pages[0].get('pageName')!r}")

# 3. THE POINT OF THIS SCENARIO -- components must be LABELLED
_comps = _sd_walk_components(_specs["components_specification"])
assert _comps, "SD-02 FAIL: components_specification contains no ComponentNode"
_labelled   = [c for c in _comps if str(c.get("componentCategory") or "").strip()]
_categories = {str(c["componentCategory"]).strip() for c in _labelled}
_load_bearing_used = _categories & _SD_LOAD_BEARING

print(f"[E2E] {len(_labelled)} of {len(_comps)} component(s) labelled; "
      f"categories: {sorted(_categories)}")

_c, _st, _ev, _tot = _sd_target_count(_specs["components_specification"])
print(f"[E2E] coverage targets: {_c} components + {_st} states + {_ev} events "
      f"= {_tot} total (one test case per target -- the suite size C' shrinks)")

assert _labelled, (
    "SD-02 FAIL: NOT ONE component carries componentCategory. Every image, icon "
    "and select-mode rule resolves through that attribute, so all of them are "
    "inert for this plan -- and nothing downstream would report it.")
assert _load_bearing_used, (
    f"SD-02 FAIL: no load-bearing category was used. Got {sorted(_categories)}, "
    f"none of which is in {sorted(_SD_LOAD_BEARING)}.")
# Every region the layout declares must be PLANNED. A region owned by JavaScript
# is exempt: it is built at runtime and has no authored components. This is the
# invariant that failed unseen on PO-08 po01c3d233 -- 4 of 7 HTML regions came
# back empty, the run was accepted, and the whole lower half of the page shipped
# with no CSS because the decoration stage had nothing there to decorate.
def _sd_region_coverage(layout_spec, component_spec):
    """Return (rows, empty) for the first page: per-region counts, and the
    HTML-owned regions that received nothing."""
    _lp = ((layout_spec or {}).get("pages") or [{}])[0]
    _cp = ((component_spec or {}).get("pages") or [{}])[0]
    _rc = _cp.get("regionComponents") or {}
    rows, empty = [], []
    for _r in (_lp.get("regions") or []):
        _name  = _r.get("name")
        _owner = str(_r.get("ownedBy") or "HTML")
        _n     = len(_rc.get(_name) or [])
        rows.append("%s (%s): %d" % (_name, _owner, _n))
        if _n == 0 and _owner.strip().lower() != "javascript":
            empty.append("%s (%s)" % (_name, _owner))
    return rows, empty


_sd_rows, _sd_empty = _sd_region_coverage(
    _specs["layout_specification"], _specs["components_specification"])
print("[E2E] region coverage: " + " | ".join(_sd_rows))
assert not _sd_empty, (
    "SD-02 FAIL: the layout declared these regions and the components "
    "generator left them EMPTY, so nothing downstream can build or style them: "
    + ", ".join(_sd_empty))
print("[E2E] every HTML-owned region received components")

assert "product-card" in _categories, (
    f"SD-02 FAIL: the brief asks for product cards but none is categorised "
    f"'product-card', so the Product Image Contract cannot require a product image "
    f"for them. Categories present: {sorted(_categories)}")

# 4. a labelled component must also be addressable, or the guard refuses the page
_unaddressable = [c["id"] for c in _labelled
                  if not (c.get("className") or c.get("id"))]
assert not _unaddressable, (
    f"SD-02 FAIL: labelled but not addressable: {_unaddressable}")

_icq_t, _icq_ok, _icc_t, _icc_ok = _interactive_completeness(_comps)
print(f"[E2E][proof] interactive completeness: {_icq_ok}/{_icq_t} quantity-selector(s) carry a "
      f"+/- control, {_icc_ok}/{_icc_t} mini-cart(s) carry a close control. Before the components "
      f"guard PO-10 po07cdf97e shipped 0/1 and 0/1 (a static number, an un-closable drawer); the "
      f"guard now refuses such a spec, so any that reaches here MUST be complete. A 0 total means "
      f"this brief produced no cart drawer.")
assert _icq_ok == _icq_t, (
    f"SD-02 FAIL: {_icq_t - _icq_ok} quantity-selector(s) reached the spec with no +/- control -- "
    f"the components guard should have refused it.")
assert _icc_ok == _icc_t, (
    f"SD-02 FAIL: {_icc_t - _icc_ok} mini-cart(s) reached the spec with no close control -- "
    f"the components guard should have refused it.")
print(f"[E2E] Profile SD-02 - {_sd_el:.0f}s, {len(_comps)} component(s), "
      f"{len(_labelled)} labelled")
_SD_RESULTS["SD-02"] = True
print("=" * 68)
print(f"PASS E2E-SD-02  4 specifications, 1 page, {len(_labelled)}/{len(_comps)} "
      f"components labelled")
print("=" * 68)

# All four stages, in the order they ran. The planner is only as fast as its
# slowest stage, and this is the one place that shows which one that is.
print()
spec_timing_report()
