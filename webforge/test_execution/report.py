"""Turn results into the report: route each failure to the agent that owns the
fix, build the work orders, and digest an oversized report."""
from __future__ import annotations

# Map each failing test action to the developer agent that owns the likely fix.
# Styling checks -> CSS, behaviour/navigation checks -> JS, structure/DOM checks
# -> HTML. A "not found" reason OVERRIDES the action: a missing element is an HTML
# structure problem no matter which check happened to hit it.
_ACTION_TO_AGENT = {
    "assert_css": "css_agent", "assert_hover_css": "css_agent",
    "css_dead_selector": "css_agent",  # synthesized by _sweep_dead_selectors
    "click": "js_agent", "type": "js_agent", "assert_url": "js_agent",
    "assert_visible": "html_agent", "assert_attribute": "html_agent",
    "assert_text": "html_agent", "assert_count": "html_agent",
    # Synthesized by _sweep_resources, never by the Test Generation Agent and
    # never executed by _execute_action. Registered here so routing is explicit
    # rather than relying on the html_agent fallback.
    "image_load": "html_agent",
    # Synthesized by _sweep_geometry. Both are layout faults: an
    # element covered by a sibling and a page wider than its viewport
    # are produced by the stylesheet, not by the markup or the script.
    "layout_unclickable": "css_agent",
    "layout_overflow":    "css_agent",
    # Synthesized by _sweep_grid_targets. A grid with the wrong column
    # count is a stylesheet fault by construction.
    "grid_target":        "css_agent",
    # Synthesized by _sweep_bulleted_nav. A navigation list left as
    # default bullets is a stylesheet fault: the reset was never written.
    "nav_list_unreset":   "css_agent",
    # Synthesized by _sweep_hidden_not_honored. A component whose display
    # overrides the [hidden] attribute is a stylesheet fault: the reset is
    # missing, so JS that hides it changes nothing on screen.
    "hidden_not_honored":  "css_agent",
    # Synthesized by _sweep_row_container_unstyled. A landmark container
    # left stacking is a stylesheet fault: the row layout was never written.
    "row_container_unstyled": "css_agent",
    # Synthesized by _sweep_filter_value_dead. The option value is markup, so
    # the token fix (value="all") lives in the HTML, not the stylesheet or JS.
    "filter_value_dead":   "html_agent",
    # Synthesized by _sweep_drawer_not_overlay. A drawer left in normal flow
    # is a stylesheet fault: the off-canvas positioning + open-state rule
    # were never written.
    "drawer_not_overlay":  "css_agent",
    # Synthesized by _sweep_dropped_shipped_id. The JS deleted ids the HTML
    # shipped (a re-render that rebuilds rows without carrying their ids), so
    # the fix is in the script.
    "dropped_shipped_id":  "js_agent",
}

# Infrastructure actions: a failure here is NOT a code bug (the failure is in
# the environment, not the generated page), so no developer agent
# can fix it. _route_agent returns None for these and _build_report emits an
# [infra] note instead of a dev-agent work order.
# image_load_infra: EVERY image on the page failed. One broken <img> among
# several is a wrong src and the HTML agent can fix it. All of them failing
# is the network or a dead CDN, and no edit to the page helps. Live proof:
# E2E-SO-01 on 2026-08-10 spent BOTH correction attempts on images while
# loremflickr, picsum.photos and placehold.co were all unreachable, and
# "fixed" it by replacing the photo with a drawn placeholder.
_INFRA_ACTIONS = {"image_load_infra"}

def _route_agent(result: dict):
    """Pick the developer agent that should fix a failing test case.

    Returns None for infrastructure actions -- no dev agent can fix them.
    """
    action = result.get("action", "")
    if action in _INFRA_ACTIONS:
        return None
    reason = str(result.get("reason", "")).lower()
    if "not found" in reason or "not in dom" in reason:
        return "html_agent"
    # assert_attribute is ambiguous and the table can only guess. UNTAGGED it is
    # static markup (type="button"), which the HTML agent owns. TAGGED
    # covers_state it asserts the value a TRANSITION produced, which only the JS
    # handler can set -- routing that to the HTML agent invites a fix by
    # hardcoding the attribute into the markup, which makes the case pass while
    # the behaviour stays broken (E2E-SO-01, 2026-08-09).
    if action == "assert_attribute" and str(result.get("covers_state") or "").strip():
        return "js_agent"
    # assert_url is ambiguous for the same reason. In a single document the only
    # URL change possible is a hash fragment, and that comes from an <a href="#x">
    # in the markup -- no JavaScript is involved. A '#' expectation is therefore
    # an HTML fix. Anything else is a real navigation and stays with JS.
    if action == "assert_url" and str(result.get("expected") or "").strip().startswith("#"):
        return "html_agent"
    # assert_count is ambiguous in the same way assert_attribute is. UNTAGGED it
    # counts what the markup delivers at rest (eight product cards), which the
    # HTML agent owns. TAGGED, it counts what an interaction produced (a cart
    # line that was not there before), and only the JS handler can produce that.
    # Sending a tagged failure to the HTML agent invites a fix by hardcoding the
    # extra element into the markup, which passes the case and leaves the
    # behaviour broken -- the same trap E2E-SO-01 sprang on assert_attribute.
    if action == "assert_count" and (str(result.get("covers_state") or "").strip()
                                     or str(result.get("covers_event") or "").strip()):
        return "js_agent"
    return _ACTION_TO_AGENT.get(action, "html_agent")


_SEVERITY_RANK = {"high": 0, "medium": 1, "low": 2}

def _finding_severity_rank(r) -> int:
    """Worst-first sort key for sweep findings. A finding's own `severity`
    wins (the four 2026-09-02 sweeps carry it: a dead interaction is high, a
    layout fault medium); a finding without one defaults to medium, so an
    older sweep is neither buried nor jumped ahead of a known-high one. The
    sort is stable, so ties keep their original order.

    Only the ORDER of the report changes -- the same findings, the same work
    orders. It matters because the correction budget is finite: one round,
    each agent capped at _MODIFY_BATCH_CAP components, and the orchestrator's
    target list is truncated to that cap. Listing the worst first is what
    makes a dead cart outrank a cosmetic drift when only 12 of 20 fit."""
    return _SEVERITY_RANK.get(str(r.get("severity") or "").lower(), 1)


def _build_report(results: list, modification_context: str = "",
                  auto_results: list = None, evidence: str = "") -> str:
    """Format results into a structured test report string.

    `results` is the suite the Test Generation Agent authored. `auto_results` is
    what _sweep_resources found -- kept as a separate argument, not concatenated
    by the caller, so PASSED/FAILED stays a statement about the authored suite
    while the sweep's findings still produce work orders."""
    auto_results = auto_results or []
    # `evidence` is what the sweeps could SEE. It is appended last, always, and
    # it is never a work order -- see _sweep_evidence for why silence needed a
    # voice.
    passed = [r for r in results if r["passed"]]
    failed = [r for r in results if not r["passed"]]
    # Worst-first, so the orchestrator sees (and the batch-cap truncation
    # keeps) the most severe findings before the cosmetic ones.
    auto_failed = sorted((r for r in auto_results if not r["passed"]),
                         key=_finding_severity_rank)

    lines = []
    if passed:
        lines.append(f"PASSED: {', '.join(r['id'] for r in passed)}")
    for r in failed:
        lines.append(f"FAILED: {r['id']} [{r['action']}] — {r['reason']}")
    # An infra finding is not a test failure. Listing it as FAILED and then
    # printing ALL TESTS PASSED under it is a contradiction the orchestrator
    # has to resolve, so it is reported once, in the [infra] block below.
    for r in auto_failed:
        if _route_agent(r) is not None:
            lines.append(f"FAILED: {r['id']} [{r['action']}] — {r['reason']}")

    if modification_context:
        targeted = [r for r in results if modification_context in r.get("component", "")]
        if targeted:
            lines.append(f"\nTargeted re-check ({modification_context}):")
            for r in targeted:
                status = "PASS" if r["passed"] else f"FAIL — {r['reason']}"
                lines.append(f"  {r['id']}: {status}")

    # An infra finding is NOT a work order. Splitting them here is what keeps a
    # dead CDN from consuming a correction attempt: if the authored suite passed
    # and every sweep finding is infra, the run has nothing to fix and must say
    # ALL TESTS PASSED, with the environment fault reported alongside.
    auto_actionable = [r for r in auto_failed if _route_agent(r) is not None]

    if not failed and not auto_actionable:
        lines.append("\nALL TESTS PASSED — no action required.")
        for r in auto_failed:
            lines.append(
                f"- [infra] {r['id']} \u2014 {r['reason']} "
                f"(environment issue; no code fix, no correction attempt)")
    else:
        if not failed:
            lines.append(
                "\nEvery authored test case passed, but a page-health sweep "
                "found a fault the authored suite structurally cannot see. "
                "Every assertion it can write resolves through "
                "query_selector, so it asks whether an element EXISTS and "
                "what it SAYS -- never whether its image loaded, whether "
                "its styling applies, or whether a click would land on it. "
                "A page can satisfy its whole suite and still render blank, "
                "unstyled or untappable, so this must be fixed.")
        lines.append("\nAction required:")
        # Sweeps (structural, already severity-sorted worst-first) lead,
        # then authored failures. The Secondary Orchestrator groups this
        # list by agent and fixes the first _MODIFY_BATCH_CAP per agent, so
        # a high-severity sweep buried under cosmetic assert_css failures
        # got truncated away -- the cart-drawer layout fix among them on
        # PO-10 po0735889c. Leading with sweeps keeps the structural fix in
        # the kept window (lever 2, 2026-09-05).
        for r in auto_failed + failed:
            agent = _route_agent(r)
            if agent is None:
                lines.append(
                    f"- [infra] {r['id']} \u2014 {r['reason']} "
                    f"(test infrastructure issue; no code fix)"
                )
            else:
                lines.append(
                    f"- {agent} | intent=modify | "
                    f"target_component={r['component']} | reason={r['reason']}"
                )

    if evidence:
        lines.append("\n" + evidence)
    return "\n".join(lines)


# Caps are per SECTION, never one slice across the whole report -- see below.
_DIGEST_FAILURE_CAP  = 40
_DIGEST_ACTION_CAP   = 40
_DIGEST_TARGETED_CAP = 20


def _digest_test_report(report: str) -> str:
    """Condense a test report down to what the orchestrator must ACT on.

    The ToolMessage used to carry `test_report[:500]`. _build_report opens with
    a single "PASSED: <every id>" line, so on any run with a healthy suite those
    500 characters were spent entirely on passing ids: the Secondary
    Orchestrator saw a wall of PASSED cut off mid-id, never a FAILED line and
    never an "Action required:" entry. Its prompt says to act only on
    test_report content, so it correctly concluded there was nothing to fix,
    reported the build as done, and the correction loop -- the system's whole
    self-correction guarantee -- ran ZERO times against 17 real failures
    (PO-08 po01e49777, 2026-08-30). The bug got worse the more tests PASSED,
    which is why a healthy-looking suite hid it.

    So nothing is cut blindly. The passing ids collapse to a count, and every
    part the orchestrator's prompt actually reads -- the verdict, the FAILED
    lines, the routed "Action required:" entries -- is kept, each under its own
    generous cap. A cap is announced in the text when it bites, so a truncation
    can never again look like an absence.
    """
    if not report or not report.strip():
        return "(no report produced)"

    passed_count = 0
    failed, targeted, tail = [], [], []
    verdict, section = "", None

    for raw in report.splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.startswith("PASSED:"):
            passed_count = len([x for x in line[len("PASSED:"):].split(",")
                                if x.strip()])
            section = None
        elif line.startswith("FAILED:"):
            failed.append(line)
            section = None
        elif line.startswith("Targeted re-check"):
            targeted.append(line)
            section = "targeted"
        elif line.startswith("ALL TESTS PASSED"):
            verdict = line
            section = "tail"
        elif line.startswith("Action required:"):
            section = "tail"
        elif section == "targeted":
            targeted.append("  " + line)
        elif section == "tail":
            tail.append(line)

    out = [f"PASSED: {passed_count} case(s)", f"FAILED: {len(failed)} case(s)"]
    out.extend(failed[:_DIGEST_FAILURE_CAP])
    if len(failed) > _DIGEST_FAILURE_CAP:
        out.append(f"... and {len(failed) - _DIGEST_FAILURE_CAP} more failure(s) "
                   "not listed here; they are in test_report in state.")
    if targeted:
        out.extend(targeted[:_DIGEST_TARGETED_CAP])
    if verdict:
        out.append(verdict)
        out.extend(tail[:_DIGEST_ACTION_CAP])
    elif tail:
        out.append("Action required:")
        out.extend(tail[:_DIGEST_ACTION_CAP])
        if len(tail) > _DIGEST_ACTION_CAP:
            out.append(f"... and {len(tail) - _DIGEST_ACTION_CAP} more work "
                       "order(s); fix these first, the rest surface next round.")
    return "\n".join(out)


# Every name this module defines or imports, for the package's __init__ and
# from there for webforge.test_exec, which re-exports it into the load order.
__all__ = [_n for _n in list(globals())
           if not (_n.startswith("__") and _n.endswith("__"))]
