# Ported from fyp.ipynb cell 453 (ticket 18). The notebook is frozen;
# edit this file. Run only by run_live_suite.py, on the webforge/ package.
# Needs: cell 109
# Needs: cell 435
# LIVE-LLM: costs credits, run manually only
# ══ PO-08  Generate, full brief, end to end ═══════════════════════════════════
# EXPENSIVE. Every agent in the system runs: context engineering, planning, then
# the whole sub-workflow (HTML, then CSS and JavaScript and Test Generation, then
# Test Execution, then up to the correction cap). Minutes, and many model calls.
#
# The brief deliberately satisfies the buildable gate: it names the product, who
# is buying, what the page must let them do, and a look. So the orchestrator must
# NOT ask a question here. Asking would be as wrong as guessing was in PO-01.

_PO06_SID = _po_new_session("01")
_po06 = _stream_orchestrator(
    "PO-08",
    "Build a storefront for a specialty coffee roaster selling whole beans to "
    "home brewers. Shoppers need to browse by roast level, read tasting notes, "
    "and add bags to a cart. Warm, minimal, lots of photography. Desktop and "
    "phone both matter.",
    _PO06_SID)

_names1 = _po_names(_po06)
_po("PO-08", "call_context_engineering_agent" in _names1,
    "extracted a design schema")
_po("PO-08", "call_system_design_planning_agent" in _names1,
    "produced the specifications")
_po("PO-08", "call_secondary_orchestrator" in _names1,
    "delegated the build")

# Order is a data dependency, not a preference: each stage consumes what the one
# before it produced.
try:
    _i_ctx = _names1.index("call_context_engineering_agent")
    _i_plan = _names1.index("call_system_design_planning_agent")
    _i_build = _names1.index("call_secondary_orchestrator")
    _po("PO-08", _i_ctx < _i_plan < _i_build,
        "ran them in dependency order, schema then specs then build")
except ValueError:
    _po("PO-08", False, "a stage never ran, so order could not be checked")

_po("PO-08", "?" not in _po06["text"].split("\n")[0],
    "did NOT ask a question, because the brief already answered the gate")

_files1 = _po_files(_PO06_SID)
_po("PO-08", all(_files1.values()),
    f"all three preview files reached disk {_files1}")

# The closing message must match the sub-run's own report. This checks the
# weaker half: it should not claim success while saying nothing about tests.
_low1 = _po06["text"].lower()
_po("PO-08", any(w in _low1 for w in ("test", "passed", "failed", "verified")),
    "reported the test outcome rather than only describing the page")

# C' proof, measured on THE RUN THAT BUILT THE PAGE (not the pipeline in
# isolation like SD-02/SD-03). This ties the spec size to the token cost of the
# same build. Before the COMPONENT vs CONTENT rule this brief produced ~195
# coverage targets and a 977.5K-token build; the goal is a much smaller number
# here with every real interactive component still present (not over-cut).
_wm08 = (_po06["state"].get("working_memory") or {})
_comps08 = _wm08.get("components_specification") or {}
if _comps08 and "_sd_target_count" in dir():
    _c08, _s08, _e08, _t08 = _sd_target_count(_comps08)
    _cats08 = sorted({str(_n.get("componentCategory")).strip()
                      for _n in _sd_walk_components(_comps08)
                      if str(_n.get("componentCategory") or "").strip()})
    print(f"\n[PO-08] components_specification: {_c08} node(s) = "
          f"{_c08} components + {_s08} states + {_e08} events = {_t08} "
          f"coverage target(s)   (before C': ~195)")
    print(f"[PO-08] component categories ({len(_cats08)}): {_cats08}")
    _q8t, _q8o, _c8t, _c8o = _interactive_completeness(_sd_walk_components(_comps08))
    print(f"[PO-08][proof] interactive completeness: {_q8o}/{_q8t} quantity-selector(s) carry a "
          f"+/- control, {_c8o}/{_c8t} mini-cart(s) carry a close control (0 total = this brief "
          f"produced no cart drawer). Before the guard PO-10 shipped 0/1 and 0/1.")
else:
    print("\n[PO-08] components_specification not captured from working_memory "
          "(run the whole notebook first so _sd_target_count exists)")

print(f"\n[PO-08] session {_PO06_SID}, preview file: "
      f"static/preview/preview_{_PO06_SID}.html")
print("\n[PO-08] closing message:\n" + _po_visible(_po06["text"])[-1400:])
