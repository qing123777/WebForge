# Ported from fyp.ipynb cell 188 (ticket 18). The notebook is frozen;
# edit this file. Run only by run_live_suite.py, on the webforge/ package.
# NOTEBOOK-ONLY: scaffolding for manual runs, never exported to fyp.py
import uuid, json, os, re, pathlib

# ═══════════════════════════════════════════════════════════════════════════
# END-TO-END HTML AGENT TESTS  (no mocking — real LLM)
#
# E2E-GM-01  Generation  normal — lint passes, html_code non-empty, file on disk

# E2E-MM-01  Modification normal — navbar change applied, siblings intact,
#                                   updated file on disk
# E2E-MM-02  Modification edge   — instance 2 only changed (auto-skipped
#                                   when generated HTML has < 2 product-cards)
# E2E-GM-02  Generation contract — spec exercises ALL contract clauses
#                                   (className half of the Naming Contract,
#                                   state materialization, clickable events);
#                                   fresh session, does not touch GM-01's page
# E2E-MM-03  Modification dead end — target selector matches nothing (the
#                                   stale-spec scenario): agent must stop
#                                   gracefully and change NOTHING on disk
# ═══════════════════════════════════════════════════════════════════════════

# Ticket 18: the preview folder comes from webforge/config.py (was C:/Users/Lenovo/Desktop/FYP/static/preview).
from webforge.config import PREVIEW_DIR as _WF_PREVIEW_DIR
_HTML_PREVIEW_ROOT = str(_WF_PREVIEW_DIR)
print(f"[E2E] Test _HTML_PREVIEW_ROOT={_HTML_PREVIEW_ROOT}")

# Specs are plain dicts: State types them as dict, and a json.dumps
# string here silently disabled store_html_code's spec walks (2026-07-21).
_layout_spec = {
    "pages": [{
        "pageName": "plp",
        "regions": [
            {"name": "header", "ownedBy": "HTML",
             "componentRefs": [{"id": "navbar"}]},
            {"name": "main",   "ownedBy": "HTML",
             "componentRefs": [{"id": "product-grid"}, {"id": "product-card"}]},
            {"name": "footer", "ownedBy": "HTML",
             "componentRefs": [{"id": "footer"}]},
        ]
    }]
}

_components_spec = {
    "dataSets": {"products": [
        {"id": "p1", "name": "Aurora Headphones", "price": "89.00"},
        {"id": "p2", "name": "Meridian Desk Lamp", "price": "42.00"},
        {"id": "p3", "name": "Cobalt Water Bottle", "price": "24.00"},
    ]},
    "pages": [{
        "pageName": "plp",
        "rootComponents": [
            {
                "id": "navbar", "tag": "nav",
                "componentCategory": "navbar", "ownedBy": "HTML",
                "role": ["structure"], "props": {}, "states": [], "events": [], "children": []
            },
            {
                "id": "product-grid", "tag": "section",
                "componentCategory": "product-grid", "ownedBy": "HTML",
                "role": ["structure"], "props": {}, "states": [], "events": [],
                "children": [
                    {
                        # Repeated component -> addressable by className (ids cannot repeat)
                        "className": "product-card",
                        "id": "product-card", "tag": "article",
                        "componentCategory": "product-card", "ownedBy": "HTML",
                        "role": ["content"], "props": {},
                        "states": [{"name": "hover"}, {"name": "selected"}],
                        "events": [], "children": []
                    }
                ]
            },
            {
                "id": "footer", "tag": "footer",
                "componentCategory": "footer", "ownedBy": "HTML",
                "role": ["structure"], "props": {}, "states": [], "events": [], "children": []
            },
        ]
    }]
}


def _stream_html_agent(session_id, query, intent,
                       target_component="", target_instance=1,
                       components_spec=None, layout_spec=None,
                       target_components=None, run_name=None):
    print(f"\n[E2E] _stream_html_agent called with intent={intent}")
    captured_tools_called = []
    captured_tool_results = []
    captured_tool_calls_full = []
    # Key for key with call_html_agent, including the cap. A harness that
    # assembles a different payload tests a contract that never runs.
    _cap   = globals().get("_MODIFY_BATCH_CAP", 12)
    _comps = list(target_components) if target_components else (
                 [target_component] if target_component else [])
    _comps = _comps[:_cap]
    payload = {
        "messages":                 [{"role": "user", "content": query}],
        "user_query":               query,
        "session_id":               session_id,
        "intent":                   intent,
        "target_component":         (_comps[0] if _comps else target_component),
        "target_components":        _comps,
        "target_instance":          target_instance,
        "layout_specification":     layout_spec if layout_spec is not None else _layout_spec,
        "components_specification": components_spec if components_spec is not None else _components_spec,
        "lint_passed":              False,
        "html_code":                _read_preview_source(session_id, "html") if intent == "modify" else "",
    }
    captured = {}

    def _merge(update):
        if isinstance(update, dict):
            for k, v in update.items():
                if k != "messages":
                    captured[k] = v

    for chunk in html_agent.stream(
        payload,
        stream_mode=["updates", "custom"],
        version="v2",
        config={
            "configurable": {"session_id": session_id},
            **({"run_name": run_name} if run_name else {}),
        },
    ):
        chunk_type, data = (
            chunk if isinstance(chunk, tuple)
            else (chunk.get("type"), chunk.get("data"))
        )
        if chunk_type == "custom":
            print(data if isinstance(data, str) else str(data))
        elif chunk_type == "updates" and isinstance(data, dict):
            for _step, up in data.items():
                if isinstance(up, dict):
                    # Capture tool calls from the AIMessages' tool_calls, in
                    # order. Never parse the progress labels for this: labels
                    # are cosmetic, and the old string match ("write_file" in
                    # the label text) never fired because the label says
                    # "Saving HTML to filesystem...".
                    for _m in (up.get("messages") or []):
                        for _tc in (getattr(_m, "tool_calls", None) or []):
                            captured_tools_called.append(_tc.get("name"))
                            # The ARGUMENTS, not just the name: two
                            # extract_component calls prove the loop ran
                            # twice, never that it visited both components.
                            captured_tool_calls_full.append(
                                {"name": _tc.get("name"),
                                 "args": _tc.get("args") or {}})
                        if getattr(_m, "type", None) == "tool":
                            captured_tool_results.append(
                                (getattr(_m, "name", "?"), str(getattr(_m, "content", ""))))
                _merge(up)
    
    captured["tools_called"] = captured_tools_called
    captured["tool_calls_full"] = captured_tool_calls_full
    print(f"[E2E] Tools called during stream: {captured_tools_called}")
    # D-debug 2026-08-30: on a lint_passed=False run this tells us WHY --
    # "Patch failed" (whole-page line numbers off) vs a lint error list still
    # dirty (the model cannot fix the error). One line per fix-loop tool call.
    for _tname, _tcontent in captured_tool_results:
        if _tname in ("apply_and_lint_html_full", "store_html_code"):
            _oneline = " ".join(str(_tcontent).split())
            print(f"[E2E] <- {_tname}: {_oneline[:600]}")
    _full_stores = captured_tools_called.count("store_html_code")
    _diff_fixes  = captured_tools_called.count("apply_and_lint_html_full")
    captured["full_stores"], captured["diff_fixes"] = _full_stores, _diff_fixes
    if intent != "modify":
        print(f"[E2E] generation-fix profile: {_full_stores} full store_html_code "
              f"call(s), {_diff_fixes} diff fix(es) via apply_and_lint_html_full "
              f"(D wants few full stores, fixes as diffs)")
        if _full_stores > 1 and _diff_fixes == 0:
            print("[E2E] NOTE: a fix went through a FULL re-emission "
                  "(store_html_code >1x, no diff) - D did not engage this run.")
    print(f"[E2E] Final state - lint_passed={captured.get('lint_passed')}, html_code length={len(captured.get('html_code', ''))}")
    return captured


_session_id   = uuid.uuid4().hex[:8]
_preview_path = os.path.join(_HTML_PREVIEW_ROOT, f"preview_{_session_id}.html")
_e2e_passed   = 0
_card_count   = 0
print(f"Session ID   : {_session_id}")
print(f"Preview path : {_preview_path}\n")
