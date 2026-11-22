"""html_agent: the HTML developer agent: HtmlState, linting, patching, its tools, prompts and agent.

Lines 4767-7949 of the flat fyp.py at commit 6e8c14b, moved
verbatim by refactor ticket 04 (tools/split_fyp.py).
"""
from __future__ import annotations

from webforge.dev_agent import *  # noqa: F401,F403

# ==========================================================================
# state
# ==========================================================================
class HtmlState(AgentState):
    user_query:               str
    layout_specification:     dict
    components_specification: dict
    html_code:                str
    lint_passed:              bool = False
    lint_attempts:               int = 0
    lint_escalated:              bool = False
    patch_attempts:       int = 0
    session_id:               str
    intent:                   Literal["generate", "modify"] = "generate"
    target_component:         str = ""
    target_components:        list = []
    target_instance:          int
    last_extracted_component: str = ""
    last_extracted_instance:  int = 0


# ==========================================================================
# save_html_file, progress hooks, filesystem guard: made by webforge.dev_agent
# ==========================================================================
# The save path goes through the same KIND of backend the agent's
# FilesystemMiddleware uses (its own instance, same root from webforge.config),
# so traversal protection and overwrite semantics stay in one class.
#
# The guard matters most here: live E2E-MM-03 caught this agent using ls /
# glob / grep to hunt for a stale modification target (21 tool calls, 9
# foreign files read). The prompt asks the model to stop at a dead end; the
# guard makes sure it cannot search regardless.
_html_save_backend = new_preview_backend()

HTML = DevLanguage(key="html", tag="HTML", noun="page", linter="html-validate",
                   lint_tool="run_html_validate",
                   extract_none=("No element found", "out of range"),
                   save_backend=lambda: _html_save_backend,
                   extract_tool="extract_component",
                   extract_label="Extracting target component...",
                   lint_label="Linting HTML...",
                   extra_tool_labels=(("apply_and_lint_html_full",
                                       "Applying edits and re-checking the page..."),))
_html_parts = dev_parts(HTML, HtmlState)
save_html_file             = _html_parts.save_tool
html_agent_progress        = _html_parts.agent_progress
html_before_model_progress = _html_parts.before_model_progress
html_tool_progress         = _html_parts.tool_progress
html_fs_guard              = _html_parts.fs_guard


# ==========================================================================
# Dynamic Prompt
# ==========================================================================
from langchain.agents.middleware.types import dynamic_prompt
import json


def _specs_prompt_block(state, fields) -> str:
    """Render the run's specifications as a prompt appendix.

    Nothing else surfaces agent state to the model: without this block the
    model never sees the specs at all, and could only learn their ids,
    classNames, and states from coverage-guard rejections (E2E-GM-02,
    2026-07-21). Generation mode only - in modification mode the stored spec
    may be stale relative to the hand-edited page, which is exactly why
    structural changes are excluded from modify mode.

    fields is a list of state keys. A spec may be a dict (State's declared
    type) or a ready JSON string; absent or empty specs are skipped, so a
    run without specs gets the base prompt unchanged.
    """
    parts = []
    for key in fields:
        spec = (state or {}).get(key)
        if isinstance(spec, str):
            text = spec.strip()
        elif spec:
            # Compact separators, not indent=2: the model parses either,
            # but pretty-printing spends ~25% of this block's tokens on
            # indent whitespace and newlines. components_specification is
            # injected into all three developer agents, so the saving is
            # paid three times per run. Semantics are byte-identical.
            text = json.dumps(spec, separators=(",", ":"), ensure_ascii=False)
        else:
            continue
        if text and text not in ("{}", "[]"):
            parts.append(f"### {key}\n{text}")
    if not parts:
        return ""
    return (
        "\n\n## Binding specifications for THIS run\n"
        "These are the authoritative specifications. Their ids, classNames, "
        "states, and events are contracts, not suggestions - the coverage "
        "guard and the test suite resolve against them verbatim.\n\n"
        + "\n\n".join(parts)
    )


def _targets_block(state) -> str:
    """Render the components to fix this call as a modify-mode prompt appendix.

    Modify mode injects nothing else (see _specs_prompt_block: the stored spec
    may be stale after a hand-edit). But the batch loop needs the model to SEE
    which components to fix, and in what order, so it can pass each as the
    component= argument to extract/apply_and_lint. Falls back to the single
    target_component when no list was supplied, so a one-component modify
    degrades to the old behaviour.
    """
    state = state or {}
    parts = []
    # The modify prompts say read_file(f"preview_{state.session_id}.html"),
    # and nothing else in modify mode ever substitutes the value: the
    # include-tags block that carries it is generation-only. On 13b71045
    # (2026-09-15) the HTML agent called
    # read_file('/workspace/default/preview_{session_id}.html') verbatim.
    # Name the files here, once, for all three developer agents.
    sid = str(state.get("session_id") or "").strip()
    if sid:
        parts.append(
            "\n\n## This run's files\n"
            f"session_id is {sid}. Your page files are preview_{sid}.html, "
            f"preview_{sid}.css and preview_{sid}.js. Wherever a step says "
            "preview_{state.session_id}, use that exact name. Never send the "
            "placeholder text itself.\n"
        )
    comps = state.get("target_components") or (
        [state.get("target_component")] if state.get("target_component") else [])
    comps = [c for c in comps if c]
    if comps:
        listing = "\n".join(f"{i}. {c}" for i, c in enumerate(comps, 1))
        parts.append(
            "\n\n## Components to fix in THIS call\n"
            "Fix these components, one at a time, in this exact order. Pass each one "
            "as the component= argument to extract and to apply_and_lint:\n"
            f"{listing}\n"
        )
    return "".join(parts)


import pathlib as _pl_img

_PREVIEW_IMG_SUBDIR = "img"


# Lucide v1.31.0, ISC License, Copyright (c) 2026 Lucide Icons and Contributors.
# Extracted once from the lucide-static npm package (a devDependency); the
# generated page inlines this markup, so the output itself has no dependency
# and no icon file that can 404.
#
# WHY A LIBRARY RATHER THAN LETTING THE MODEL DRAW ONE: a wrong curve command in
# a hand-written `d` attribute renders as a scribble. html-validate accepts it,
# the coverage guard accepts it, and assert_visible accepts it -- the exact
# silent-failure class this project exists to remove. The geometry is therefore
# copied, never generated.
#
# The values are the INNER markup, not just path data: several icons use
# <circle> and the wrapper carries stroke="currentColor", which is what lets a
# CSS colour change reach the icon without editing the HTML.
_LUCIDE_ICONS = {
    'check':           ('confirm, selected',
     '<path d="M20 6 9 17l-5-5"/>'),
    'chevron-down':    ('dropdown, expand',
     '<path d="m6 9 6 6 6-6"/>'),
    'chevron-right':   ('forward, breadcrumb',
     '<path d="m9 18 6-6-6-6"/>'),
    'funnel':          ('filter',
     '<path d="M10 20a1 1 0 0 0 .553.895l2 1A1 1 0 0 0 14 21v-7a2 2 0 0 1 .517-1.341L21.74 4.67A1 1 0 0 0 21 3H3a1 1 0 0 0-.742 1.67l7.225 7.989A2 2 0 0 1 10 14z"/>'),
    'heart':           ('wishlist, save',
     '<path d="M2 9.5a5.5 5.5 0 0 1 9.591-3.676.56.56 0 0 0 .818 0A5.49 5.49 0 0 1 22 9.5c0 2.29-1.5 4-3 5.5l-5.492 5.313a2 2 0 0 1-3 .019L5 15c-1.5-1.5-3-3.2-3-5.5"/>'),
    'menu':            ('mobile navigation',
     '<path d="M4 5h16"/><path d="M4 12h16"/><path d="M4 19h16"/>'),
    'minus':           ('decrease quantity',
     '<path d="M5 12h14"/>'),
    'plus':            ('increase quantity',
     '<path d="M5 12h14"/><path d="M12 5v14"/>'),
    'search':          ('search field',
     '<path d="m21 21-4.34-4.34"/><circle cx="11" cy="11" r="8"/>'),
    'shopping-bag':    ('bag',
     '<path d="M16 10a4 4 0 0 1-8 0"/><path d="M3.103 6.034h17.794"/><path d="M3.4 5.467a2 2 0 0 0-.4 1.2V20a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2V6.667a2 2 0 0 0-.4-1.2l-2-2.667A2 2 0 0 0 17 2H7a2 2 0 0 0-1.6.8z"/>'),
    'shopping-cart':   ('cart',
     '<circle cx="8" cy="21" r="1"/><circle cx="19" cy="21" r="1"/><path d="M2.05 2.05h2l2.66 12.42a2 2 0 0 0 2 1.58h9.78a2 2 0 0 0 1.95-1.57l1.65-7.43H5.12"/>'),
    'star':            ('rating',
     '<path d="M11.525 2.295a.53.53 0 0 1 .95 0l2.31 4.679a2.123 2.123 0 0 0 1.595 1.16l5.166.756a.53.53 0 0 1 .294.904l-3.736 3.638a2.123 2.123 0 0 0-.611 1.878l.882 5.14a.53.53 0 0 1-.771.56l-4.618-2.428a2.122 2.122 0 0 0-1.973 0L6.396 21.01a.53.53 0 0 1-.77-.56l.881-5.139a2.122 2.122 0 0 0-.611-1.879L2.16 9.795a.53.53 0 0 1 .294-.906l5.165-.755a2.122 2.122 0 0 0 1.597-1.16z"/>'),
    'trash-2':         ('remove from cart',
     '<path d="M10 11v6"/><path d="M14 11v6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6"/><path d="M3 6h18"/><path d="M8 6V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/>'),
    'user':            ('account',
     '<path d="M19 21v-2a4 4 0 0 0-4-4H9a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/>'),
    'x':               ('close / dismiss',
     '<path d="M18 6 6 18"/><path d="m6 6 12 12"/>'),
}

_LUCIDE_WRAPPER = (
    '<svg viewBox="0 0 24 24" width="20" height="20" fill="none" '
    'stroke="currentColor" stroke-width="2" stroke-linecap="round" '
    'stroke-linejoin="round" aria-hidden="true" focusable="false">')


def _icon_catalogue_block() -> str:
    """Render the icon set as a prompt appendix.

    In both modes, for the same reason as the image catalogue: a correction work
    order can be about an icon, and modify mode has no other channel for this.
    """
    if not _LUCIDE_ICONS:
        return ""
    lines = []
    for name in sorted(_LUCIDE_ICONS):
        purpose, inner = _LUCIDE_ICONS[name]
        lines.append("  %-15s %s\n    %s" % (name, purpose, inner))
    return (
        "\n\n## Icons available to this page (Lucide v1.31.0, ISC)\n"
        "Inline these directly. There is no icon font and no stylesheet to "
        "fetch, so nothing here can fail to arrive. Wrap the inner markup in "
        "exactly this element:\n\n"
        "  " + _LUCIDE_WRAPPER + "INNER</svg>\n\n"
        "stroke=\"currentColor\" makes the icon inherit the CSS color of its "
        "parent, so styling is the CSS agent's job and this markup never has to "
        "change for a colour or size tweak.\n"
        "An icon is DECORATIVE: keep aria-hidden=\"true\" on the <svg> and put "
        "the aria-label on the button around it, so a screen reader announces "
        "the action rather than the glyph.\n"
        "Never use a unicode character (\u2315, \u2311, \u2605) for these. They "
        "render differently on every font stack and some render as a blank "
        "box.\n\n"
        + "\n".join(lines) + "\n"
    )


def _include_tags_block(state) -> str:
    """The two include tags for THIS run, already filled in.

    store_html_code requires a <link> to preview_<sid>.css and a <script> to
    preview_<sid>.js, matched by exact filename. The prompt used to show them as
    "preview_{state.session_id}.css" and ask for the EXACT filenames shown, but
    nothing substitutes a placeholder in a plain prompt string and the selector
    injected only the specs -- so session_id never reached the model at all. The
    model could not know the id, copied the placeholder, and the guard refused;
    the fix then cost a full re-emission of the whole page, on EVERY generation
    run observed (2026-08-30). Handing over the finished tags removes the guess.

    Returns "" when there is no session_id, so the prompt degrades to its old
    wording rather than advertising a filename built from an empty id.
    """
    sid = (state or {}).get("session_id", "")
    if not sid:
        return ""
    return (
        "\n\n---\n\n"
        "## This Run's Include Tags (copy these two lines verbatim)\n"
        f'    <link rel="stylesheet" href="preview_{sid}.css">      -> in <head>\n'
        f'    <script src="preview_{sid}.js" defer></script>        -> before </body>\n'
        "These filenames are fixed for this run. Do not build them yourself, do\n"
        "not shorten them, and never emit a placeholder such as\n"
        "{state.session_id} - store_html_code matches the filename exactly and\n"
        "refuses the page otherwise.\n"
    )


@dynamic_prompt
def html_prompt_selector(request) -> str:
    state = request.state or {}
    # The image feature was removed (2026-08-29): the page embeds no photographs,
    # so there is no photo catalogue to inject. Products use a labelled
    # .product-image-placeholder and decoration is drawn in CSS or inline SVG
    # (see the shared base prompt). The icon catalogue still goes into BOTH modes.
    if state.get("intent", "generate") == "modify":
        return (_html_modification_prompt + _icon_catalogue_block()
                + _targets_block(state))
    return (_html_generation_prompt
            + _specs_prompt_block(
                state, ["layout_specification", "components_specification"])
            + _icon_catalogue_block()
            + _include_tags_block(state))


# ==========================================================================
# run_html_validate
# ==========================================================================
# The lint and patch caps, the batch helpers and _run_lint_subprocess live in
# webforge.dev_agent since ticket 09: the CSS and JS agents share them, and
# dev_agent loads before this module.

# Calls one developer agent may receive between two test runs. The batch
# cap (_MODIFY_BATCH_CAP, now in dev_agent) says how much ONE call may carry; this says how many calls a
# round may contain, and the two only work together. Capping the calls
# without the batch would be a wall: five failing HTML components and one
# permitted call would leave four unfixable. HTML gained batching in the
# same session this constant was added, for exactly that reason.

_ROUND_CALL_CAP = 1

# Correction rounds: how many times the pipeline re-runs and hands failures
# back to the developer agents before it refuses and reports a partial
# result. 1 = generate, test once, correct at most once, test again.
# Enforced in call_test_exec_pipeline on a re-run (a prior test_report
# exists in state); the baseline run is never refused.
_MODIFICATION_ATTEMPT_CAP = 1


def _dev_agent_recursion_limit(component_count: int) -> int:
    """Supersteps to allow a developer agent, sized to the work it was handed.

    Each tool-calling turn costs 2 supersteps (model node + tools node). Fixed
    overhead per session: read the file, seed it into state (both only when
    state arrives empty, since 2026-11-11), save at the end =
    3 calls = 6 supersteps. Per component: extract, apply-and-lint, plus up to
    _LINT_ATTEMPT_CAP re-lints = ~5 calls = ~10 supersteps. A batch of n
    therefore needs about 6 + 10n, and this doubles it for headroom the way the
    original single-component value did.

    n=1 keeps the historic 50. n=12, the batch cap, gives 252 -- the case that
    raised GraphRecursionError at 50 and destroyed a whole PO-08 run
    (po019a8c61, 2026-08-30). The limit still stops a runaway in seconds rather
    than hours, which is the only job it has.
    """
    n = max(1, int(component_count or 1))
    return max(50, 2 * (6 + 10 * n))


def _stream_dev_agent(agent, payload, sub_config, writer, on_update=None) -> bool:
    """Stream a developer agent, surviving an exhausted step budget.

    recursion_limit BOUNDS a session but does not end it gracefully: LangGraph
    RAISES, and an uncaught raise here travels up through the Secondary
    Orchestrator and destroys the whole run. Whatever the agent already saved to
    disk stays valid and is still reported by _artifact_outcome, so the caller
    degrades to a partial result the orchestrator can act on.

    on_update is called with each state update when the caller needs them (only
    the HTML tool does). Returns True when the budget ran out, False otherwise.
    """
    from langgraph.errors import GraphRecursionError
    try:
        for chunk in agent.stream(payload, stream_mode=["updates", "custom"],
                                  version="v2", config=sub_config):
            if isinstance(chunk, tuple) and len(chunk) == 2:
                chunk_type, data = chunk
            else:
                chunk_type = chunk.get("type")
                data       = chunk.get("data")
            if chunk_type == "custom":
                writer(data if isinstance(data, (str, dict)) else str(data))
            elif (on_update is not None and chunk_type == "updates"
                  and isinstance(data, dict)):
                for _step, up in data.items():
                    on_update(up)
        return False
    except GraphRecursionError:
        return True


def _partial_fix_note(recursion_hit: bool, label: str) -> str:
    """The line appended to a developer agent's outcome when its budget ran out.

    It has to say two things the orchestrator needs and cannot infer: the work
    that IS saved is real, and the rest simply did not happen -- so the right
    next move is to re-run the suite and read the report, not to assume the
    whole correction round failed.
    """
    if not recursion_hit:
        return ""
    return ("\n[Secondary Orchestrator] " + label + " Agent hit its step limit "
            "before finishing every component. Anything reported as modified "
            "above IS saved to disk; the remaining components were not reached. "
            "Treat this as a PARTIAL fix: re-run the test suite and let the "
            "report say what is still failing. Do not re-dispatch the same "
            "batch blind.")

# ==========================================================================
# run_html_validate
# ==========================================================================
import json as _json


@tool
def run_html_validate(runtime: ToolRuntime[HtmlState]) -> Command:
    """
    Lint the current html_code in state using html-validate. Thin wrapper over
    _lint_html_source so apply_and_lint_html can lint the HTML it JUST patched in
    the same tool call. Behaviour unchanged.
    """
    return _lint_html_source(runtime.state.get("html_code", ""), runtime)


def _lint_html_source(html_code: str, runtime) -> Command:
    """
    Lint an HTML SOURCE STRING and return the same Command run_html_validate has
    always returned. Factored out of run_html_validate so apply_and_lint_html can
    lint the code it just patched without a second run_html_validate round-trip.
    Behaviour unchanged: escalation refusal, empty guard, npx-missing guard,
    error formatting, and cap counting via _lint_failure. The refusal, the empty
    guard and the temp file are the engine's (webforge.dev_agent.lint_source,
    ticket 10); _html_validate_check is what html-validate adds.
    """
    return lint_source(HTML, html_code, runtime, _html_validate_check)


def _html_validate_check(tmp_path: str, runtime) -> Command:
    """Run html-validate on the temp file and turn its JSON report into the verdict."""
    result = _run_lint_subprocess(
        f'npx --no-install html-validate --formatter json "{tmp_path}"')
    if "npx" in result.stderr.lower() and result.returncode != 0 and not result.stdout.strip():
        return Command(update={
            "lint_passed": False,
            "messages": [ToolMessage(
                content=(
                    "html-validate could not be executed because `npx` was not found. "
                    "Install Node.js (which provides npx) and ensure it is on PATH, "
                    "then run `npm install` in this repo."
                ),
                tool_call_id=runtime.tool_call_id
            )]
        })
    if result.returncode == 0:
        return Command(update={
            "lint_passed": True,
            "messages": [ToolMessage(
                content="No issues found.",
                tool_call_id=runtime.tool_call_id
            )]
        })
    output = result.stdout or result.stderr
    try:
        results  = _json.loads(output)
        errors   = results[0].get("messages", []) if results else []
        lines    = [f"Found {len(errors)} error(s):"]
        for e in errors:
            lines.append(
                f"  Line {e['line']}, Col {e['column']} [{e['ruleId']}]: {e['message']}"
            )
        formatted = "\n".join(lines)
    except (ValueError, IndexError, KeyError):
        formatted = output
    return _lint_failure(runtime, formatted)


# ==========================================================================
# store_html_code
# ==========================================================================
def _dataset_records(components_spec) -> list:
    """[(setKey, id, name)] for every record in ComponentSpecification.dataSets.

    One reader for both the HTML and the JS guard, so the two cannot disagree
    about what the run's content is -- which is the whole point of the field.
    """
    out = []
    sets = (components_spec or {}).get("dataSets") or {}
    if not isinstance(sets, dict):
        return out
    for key, records in sets.items():
        for rec in (records or []):
            if not isinstance(rec, dict):
                continue
            rid = str(rec.get("id") or "").strip()
            name = str(rec.get("name") or "").strip()
            if rid and name:
                out.append((str(key), rid, name))
    return out


def _summary_data_sets(components_spec) -> set:
    """Names of the data sets that hold one VALUE record, not content to print.

    A set is a summary when it has exactly one record, at least one component
    reads a value out of it ('cartSummary.itemCount'), and no component reads
    it as a list ('cartSummary'), by its name ('cartSummary.name'), or from a
    product component (componentCategory 'product-price': the one record of a
    product-detail page is merchandise, and its name belongs on the page).

    The schema gives every record a 'name', so a planner writing
    cartSummary = [{itemCount: 3}] must invent one ('Cart Summary'). The Shared
    Data Contract then demanded that invented name on the page: on PO-08
    4fb17fbe it refused a correct first save for 'Cart Summary' and 'Featured
    Coffee Results', a 68 s rewrite that ended with those labels printed on
    the page and a submit button nobody asked for (speed-cost ticket 04).
    """
    if not isinstance(components_spec, dict):
        return set()
    sets = components_spec.get("dataSets")
    if not isinstance(sets, dict):
        return set()
    by_value, as_content = set(), set()

    def walk(node):
        if isinstance(node, dict):
            binding = node.get("dataBinding")
            source = binding.get("source") if isinstance(binding, dict) else None
            if isinstance(source, str) and source.strip():
                name, _, field = source.strip().partition(".")
                category = str(node.get("componentCategory") or "").strip().lower()
                if not field or field == "name" or category.startswith("product"):
                    as_content.add(name)
                else:
                    by_value.add(name)
            for v in node.values():
                if isinstance(v, (dict, list)):
                    walk(v)
        elif isinstance(node, list):
            for it in node:
                walk(it)
    walk(components_spec.get("pages"))
    return {key for key, records in sets.items()
            if isinstance(records, list) and len(records) == 1
            and key in by_value and key not in as_content}


from bs4 import BeautifulSoup
import json
import re

def _spec_component_identities(spec) -> list:
    """Collect (id, className) for every ComponentNode in components_specification.
    className is None for nodes without one (rendered via id per the Naming
    Contract). A local, self-contained walk — not shared with store_test_cases'
    identically-shaped _spec_component_names — because this cell executes
    earlier in the notebook."""
    found = []
    if isinstance(spec, dict):
        if isinstance(spec.get("id"), str) and "tag" in spec:
            found.append((spec["id"], spec.get("className")))
        for v in spec.values():
            found.extend(_spec_component_identities(v))
    elif isinstance(spec, list):
        for item in spec:
            found.extend(_spec_component_identities(item))
    return found


def _component_name_aliases(component: str, components_spec=None) -> list:
    """Every name a component can be addressed by, best guess first.

    A correction work order names the specification id (`add-to-cart-button`),
    but the Naming Contract renders a node by its className whenever it declares
    one and emits no id at all -- so the page carries only
    class="add-to-cart-btn" and a literal lookup finds nothing. In the SO-01 run
    of 2026-08-09 both the HTML and the JS agent reported the target as no
    longer on the page for a component that was right there, and both correction
    attempts were spent on a lookup that could not succeed.

    components_specification carries both halves of the mapping and is in every
    developer agent's payload, so nothing new has to be plumbed through. The
    space-collapsed form is included because the orchestrator has been seen to
    write "add-to-cart button".
    """
    seen, out = set(), []

    def add(name):
        if isinstance(name, str) and name.strip() and name not in seen:
            seen.add(name)
            out.append(name)

    raw = (component or "").strip()
    add(raw)
    norm = re.sub(r"\s+", "-", raw)
    add(norm)
    bare = norm.lstrip("#.")
    add(bare)

    spec = _coerce_spec(components_spec or {}) or {}
    if spec:
        for cid, cname in _spec_component_identities(spec):
            if bare in (cid, cname):
                add(cname)
                add(cid)
    return out


def _html_select_component(soup, selector: str, components_spec=None):
    """Return (the alias that matched, its elements). Tries each alias as a CSS
    selector, then as #id, then as .class -- the same ladder the bare-word
    fallback always used, now walked for every alias rather than only the name
    the caller happened to pass."""
    for cand in _component_name_aliases(selector, components_spec):
        try:
            found = soup.select(cand)
        except Exception:
            found = []                      # not valid CSS; the ladder continues
        if not found and not cand.startswith(("#", ".")):
            found = soup.select(f"#{cand}") or soup.select(f".{cand}")
        if found:
            return cand, found
    return selector, []


def _html_addressables(soup, limit: int = 14) -> list:
    """The ids and classNames the page actually offers. Named in a not-found
    message, since that message is the model's only channel to the fix."""
    out = {f"#{el['id']}" for el in soup.find_all(id=True)}
    for el in soup.find_all(class_=True):
        for c in el.get("class", []):
            out.add(f".{c}")
    return sorted(out)[:limit]


def _coerce_spec(spec):
    """State schemas type the specification fields as dict, but a spec that
    arrives as a JSON string must not silently disable a coverage walk (the
    dict-walk finds nothing inside a str - E2E-GM-02, 2026-07-21). Parse it;
    return None for an unparseable string so callers fail loudly instead of
    checking nothing."""
    if isinstance(spec, str):
        try:
            return json.loads(spec)
        except ValueError:
            return None
    return spec


def _spec_component_states(spec) -> list:
    """Collect (id, className, [state names]) for every ComponentNode that
    declares states. Kept separate from _spec_component_identities because
    that function's 2-tuple shape is consumed via dict() by store_js_code
    and the JS live harness - widening it would break both."""
    found = []
    if isinstance(spec, dict):
        if isinstance(spec.get("id"), str) and "tag" in spec and spec.get("states"):
            names = []
            for st in spec["states"]:
                name = st.get("name") if isinstance(st, dict) else st
                if isinstance(name, str) and name.strip():
                    names.append(name.strip())
            if names:
                found.append((spec["id"], spec.get("className"), names))
        for v in spec.values():
            found.extend(_spec_component_states(v))
    elif isinstance(spec, list):
        for item in spec:
            found.extend(_spec_component_states(item))
    return found


def _spec_component_categories(spec) -> list:
    """Collect (id, className, componentCategory) for every ComponentNode that
    declares a category.

    componentCategory says what a component IS; id/className say what it is
    CALLED. The Naming Contract already guarantees the name reaches the DOM, but
    nothing carried the category there: on 2026-08-11 a sweep of the notebook
    found data-component only in test fixtures and in fyp.py's schema
    description, never in a generated page, because no prompt asked for it and
    no guard required it.

    The role-aware image rule needs it (a product card must show a real
    photograph, a hero banner may be drawn), and the preview's select mode needs
    it to resolve a click on a decorative icon up to the component that owns it.
    Kept separate from _spec_component_identities for the same reason
    _spec_component_states is: that function's 2-tuple shape is consumed via
    dict() by store_js_code and the JS live harness."""
    found = []
    if isinstance(spec, dict):
        cat = spec.get("componentCategory")
        if (isinstance(spec.get("id"), str) and "tag" in spec
                and isinstance(cat, str) and cat.strip()):
            found.append((spec["id"], spec.get("className"), cat.strip()))
        for v in spec.values():
            found.extend(_spec_component_categories(v))
    elif isinstance(spec, list):
        for item in spec:
            found.extend(_spec_component_categories(item))
    return found


# State Materialization Contract: state names with a native aria-* attribute,
# and the transient pointer states that stay CSS pseudo-classes (never
# materialized as attributes).
_ARIA_STATES   = {"expanded", "pressed", "disabled", "selected"}
_PSEUDO_STATES = {"hover", "focus"}


# No-image contract (2026-08-29): the generated page embeds no photographs.
#
# WHY THE IMAGE FEATURE WAS REMOVED. The system used to bundle photographs on
# disk, list them into the HTML prompt, and police every <img> src: it had to be
# a bundled local file (checked to resolve) or a data: URI, because a remote host
# can rate-limit, move, or die and still loads at test time yet blanks later for a
# real visitor (PO-06 shipped exactly that on 2026-08-23). That whole apparatus
# was a large silent-failure surface -- a blank <img> passes every DOM assertion --
# for a feature a user cannot realistically supply: they would have to pre-load and
# correctly name every product photo before the run. So the feature is gone. An
# <img> now has NO supported source and is refused outright; products carry a
# labelled placeholder and decoration is drawn in CSS or an inline <svg> element.
# This is a documented Limitation of the system, not a defect.


def _image_source_violations(soup) -> list:
    """Return one message per <img>. The system embeds no images.

    An inline <svg> is untouched: it is not an <img>, carries no src, and cannot
    fail to load. Only the <img> tag is refused, because it has no source the
    system supports any more."""
    bad = []
    for tag in soup.find_all("img"):
        src = (tag.get("src") or "").strip()
        shown = src[:70] if src else "(no src)"
        bad.append(
            "'%s' -- this system does not embed images. For a product use a "
            "labelled <div class=\"%s\">Product Name</div>; for decoration draw "
            "it in CSS or an inline <svg> element."
            % (shown, _PRODUCT_PLACEHOLDER_CLASS))
    return bad


# Product Image Contract: the component roles whose image slot must be a
# labelled placeholder. Everything else -- a hero banner, a promo strip, an
# icon -- may be drawn in CSS or inline SVG.
#
# The rule is scoped by ROLE, not by technique. Drawn artwork is not inherently
# wrong: an independent single-shot model asked for the same page produced a
# phone store with zero images, drawing every handset in CSS, and it looked good.
# But drawn art has no lower bound either, and nothing can measure which one you
# got. So a product role must NAME its product in real text rather than leave a
# shopper looking at an anonymous box.
_PRODUCT_IMAGE_ROLES = ("product-card", "product-image-gallery", "cart-item")


# The product image slot. Since the image feature was removed (2026-08-29) this
# is the ONLY product-image path -- there is no photograph tier above it.
#
# It is deliberately NOT a grey box. The tile carries the product name as real
# DOM text, so it says "Orchid Bouquet" rather than pretending to be a picture of
# one. That also keeps it reachable: assert_text can read it and a screen reader
# can announce it, neither of which is true of a drawn rectangle.
_PRODUCT_PLACEHOLDER_CLASS = "product-image-placeholder"


def _placeholder_label(el) -> str:
    """The visible text of a product-image placeholder inside el, or ""."""
    for ph in el.select(".%s" % _PRODUCT_PLACEHOLDER_CLASS):
        text = " ".join((ph.get_text() or "").split())
        if text:
            return text
    return ""


def _product_image_violations(soup) -> list:
    """Return one message per product-bearing component missing a labelled
    placeholder.

    Driven off the data-component attribute rather than the specification. By the
    time this runs the Component Category Contract has already refused a page
    whose spec declares a category the markup does not carry, so reading the
    attribute cannot miss a component -- and reading the DOM also covers a page
    generated without a spec.

    Since the image feature was removed a product role can no longer show a
    photograph; its image slot is a labelled .product-image-placeholder carrying
    the product name. An empty placeholder is the grey box this contract has
    always refused, just with a class name on it -- the label is the whole
    difference."""
    bad = []
    for role in _PRODUCT_IMAGE_ROLES:
        for el in soup.select('[data-component="%s"]' % role):
            label = (el.get("id") or " ".join(el.get("class") or []) or role)
            if _placeholder_label(el):
                continue
            if el.select(".%s" % _PRODUCT_PLACEHOLDER_CLASS):
                bad.append(
                    "'%s' (data-component=\"%s\") has an EMPTY .%s. Put the "
                    "product name in as real text -- that is what makes it honest "
                    "rather than a grey box"
                    % (label, role, _PRODUCT_PLACEHOLDER_CLASS))
            else:
                bad.append(
                    "'%s' (data-component=\"%s\") has no .%s. The system embeds "
                    "no photographs; add <div class=\"%s\">Product Name</div> "
                    "carrying the product name as real text"
                    % (label, role, _PRODUCT_PLACEHOLDER_CLASS,
                       _PRODUCT_PLACEHOLDER_CLASS))
    return bad


def _icon_accessibility_violations(soup) -> list:
    """Return one message per interactive element whose icon is announced, or
    whose only content is an icon with no accessible name.

    Two rules that turn out to be one rule.

    The ACCESSIBILITY rule: a screen reader on <button><svg>...</svg></button>
    should announce "Search", not the glyph. So the <svg> carries
    aria-hidden="true" and the button carries the label.

    The SELECT MODE rule: clicking the search icon in the preview should select
    the SEARCH BAR, not the icon. Colour and size changes to an icon do work --
    Lucide draws with stroke="currentColor", so a CSS colour change reaches it --
    but swapping the glyph means rewriting SVG path data, which is a structural
    markup change that modification mode excludes by design and that a model
    cannot author safely. So the click must resolve to the owning component.

    Both are satisfied by the same markup: aria-hidden on the icon, the label on
    the control, and (from the CSS agent) pointer-events: none on the icon, so
    the click lands on the control rather than on the glyph.
    """
    bad = []
    for el in soup.find_all(["button", "a"]):
        svgs = el.find_all("svg")
        if not svgs:
            continue
        name = " ".join((el.get_text() or "").split())
        label = (el.get("aria-label") or "").strip()
        what = el.get("id") or " ".join(el.get("class") or []) or f"<{el.name}>"
        loud = [s for s in svgs
                if str(s.get("aria-hidden", "")).strip().lower() != "true"]
        if loud:
            bad.append(
                f"'{what}' has {len(loud)} <svg> without aria-hidden=\"true\". "
                f"A decorative icon must not be announced, and it must not be "
                f"the click target of the preview's select mode")
        if not name and not label:
            bad.append(
                f"'{what}' contains only an icon and has no accessible name. "
                f"Add aria-label to the {el.name}, since the icon itself is "
                f"hidden from assistive technology")
    return bad


def _dangling_anchors(soup) -> list:
    """Return one message per in-page link whose target section does not exist.

    Anchor navigation is how this system does multi-section pages: one document,
    <a href="#shop"> scrolling to <section id="shop">. A dangling link is SILENT
    -- the click succeeds, the URL gains the fragment, and the page simply does
    not move -- so no DOM assertion can catch it. Same shape as the broken-image
    problem: present in the document, useless on screen.

    "#" alone and "#top" are conventional and always allowed."""
    ids = {t.get("id") for t in soup.find_all(attrs={"id": True})}
    ids.discard(None)
    bad = []
    for a in soup.find_all("a"):
        href = (a.get("href") or "").strip()
        if not href.startswith("#") or href in ("#", "#top"):
            continue
        target = href[1:]
        if target in ids:
            continue
        label = " ".join((a.get_text() or "").split())[:30] or "<a>"
        bad.append(f"'{label}' links to '{href}' but no element has id=\"{target}\"")
    return bad


def _is_pagination_nav(nav) -> bool:
    """True when this <nav> is a pagination control rather than a menu.

    data-component is the primary signal because the Component Category Contract
    puts componentCategory there verbatim, so a spec-driven page always carries
    it. class / id / aria-label are accepted as fallbacks for hand-written or
    modified markup that predates the contract.
    """
    fields = [nav.get("data-component") or "", nav.get("id") or "",
              nav.get("aria-label") or ""]
    cls = nav.get("class") or []
    fields.append(" ".join(cls) if isinstance(cls, list) else str(cls))
    return any("pagination" in f.lower() for f in fields)


def _duplicate_nav_anchors(soup) -> list:
    """Return one message per <nav> whose in-page links share a target.

    The Anchor Navigation Contract below only checks that a fragment RESOLVES.
    On 2026-08-10 the HTML agent satisfied it the cheapest way available and
    pointed Shop, New Arrivals, Best Sellers and Cart all at #main -- four links,
    one destination, every one of them resolving. A guard that can be satisfied
    by collapsing the thing it protects is not a guard.

    PAGINATION is exempt. It is the one nav where sharing a destination is the
    correct markup: page 1, 2 and 3 all scroll back to the same product grid, so
    there is no second section for them to point at and no collapsing going on.
    Refusing it cost a full-page re-emission on PO-08 po019a8c61 (the guard read
    ['1','2','3'] all link to '#coffee-grid'), for markup that was already right.

    '#' and '#top' are conventional and may repeat."""
    bad = []
    for nav in soup.find_all("nav"):
        if _is_pagination_nav(nav):
            continue
        seen = {}
        for a in nav.find_all("a"):
            href = (a.get("href") or "").strip()
            if not href.startswith("#") or href in ("#", "#top"):
                continue
            label = " ".join((a.get_text() or "").split())[:24] or "<a>"
            seen.setdefault(href, []).append(label)
        for href, labels in seen.items():
            if len(labels) > 1:
                bad.append(f"{labels} all link to '{href}' - give each nav item "
                           f"its own section id")
    return bad


# Links that leave the document, and where they are allowed to.
#
#   #x                  a section of this page, checked by _dangling_anchors
#   https://... http:// an external site, allowed
#   mailto: tel:        allowed
#   javascript:void(0)  a placeholder for a button, allowed
#   / ./ ../ x.html     a SECOND DOCUMENT, which cannot exist
_LEAVES_DOCUMENT_OK = ("http://", "https://", "mailto:", "tel:", "sms:",
                       "javascript:", "data:", "//")


def _cross_document_links(soup) -> list:
    """Return one message per link pointing at a document that cannot exist.

    The two checks above both open by skipping any href that is not a fragment,
    because they were written to ask whether a fragment resolves. That left the
    opposite mistake unguarded. A run builds ONE document, named after the
    session, so `<a href="checkout.html">` can only ever be a 404 -- and it is
    silent in the same way a dangling fragment is, because the click succeeds.

    An external site, an email link, a phone link and a javascript: placeholder
    all stay allowed. Only a path to another local page is refused."""
    bad = []
    for a in soup.find_all("a"):
        href = (a.get("href") or "").strip()
        if not href or href.startswith("#"):
            continue
        if href.lower().startswith(_LEAVES_DOCUMENT_OK):
            continue
        label = " ".join((a.get_text() or "").split())[:30] or "<a>"
        bad.append(f"'{label}' links to '{href}', which is a second document - "
                   f"link to a section of this one with href=\"#<regionId>\"")
    return bad


def _sold_out_buyable_violations(soup) -> list:
    """A product-card whose stock is visibly ZERO -- a <progress value="0">, or text
    like "0 remaining" / "0% left" -- is sold out at load, yet its add-to-cart still
    reads aria-disabled="false", so it stays buyable in the DOM while its own content
    says sold out (preview_po2r117e13f card p-sonivox-micpro). Return one message per
    such card. Keyed on an unambiguous zero, so an "almost sold out" urgency card
    (stock still > 0) never trips it."""
    bad = []
    for card in soup.select('[data-component="product-card"]'):
        zero = any(str(pr.get("value", "")).strip() in ("0", "0.0")
                   for pr in card.find_all("progress"))
        if not zero and re.search(r"\b0\s*%?\s*(?:left|remaining)\b",
                                  card.get_text(" ", strip=True), re.I):
            zero = True
        if not zero:
            continue
        for btn in card.select('[data-component="add-to-cart-button"]'):
            if str(btn.get("aria-disabled", "")).strip().lower() == "false":
                label = (card.get("data-id") or card.get("id")
                         or " ".join(card.get("class") or []) or "product-card")
                bad.append(
                    "'%s' shows zero stock (sold out) but its add-to-cart is "
                    "aria-disabled=\"false\", so it is still buyable in the DOM. Ship "
                    "the sold-out card's add-to-cart with aria-disabled=\"true\" and "
                    "set the card's data-state to the declared unavailable state" % label)
    return bad


@tool
def store_html_code(html_code: str, runtime: ToolRuntime[HtmlState]) -> Command:
    """
    Store the generated or revised HTML code into agent state.
    Must be called every time after generating or revising HTML,
    before calling run_html_validate.

    On Generation Mode calls (intent="generate") with a session_id set, this
    also enforces the checks below before accepting the code — the CSS/JS agents'
    files are useless if the HTML never loads them, and a missing component
    means the Naming Contract silently failed:
      1. The HTML must <link>/<script> its own preview_{session_id}.css and
         preview_{session_id}.js.
      2. Every component in components_specification must be addressable in
         the HTML (per the Naming Contract).
      3. Every declared component state (except hover/focus) must already
         be materialized on every instance as its resting DOM attribute
         (State Materialization Contract).
      4. Every component declaring componentCategory must carry it verbatim
         as data-component on the element the Naming Contract addresses
         (Component Category Contract) — the role-aware image rule and the
         preview's select mode both resolve through that attribute.
      5. Every component whose data-component names a product-bearing role
         must contain a LABELLED .product-image-placeholder carrying the
         product name as text (Product Image Contract). The image feature was
         removed, so a photograph is no longer an option here. Decorative
         regions may still be drawn in CSS or inline SVG.
      6. Every inline <svg> inside a button or link must be aria-hidden, and
         an icon-only control must carry an aria-label (Icon Accessibility
         Contract) — the same markup that keeps a screen reader on the action
         also keeps the preview's select mode off the glyph.
      7. No <img> tag is admitted at all (no-image contract) -- the image
         feature was removed on 2026-08-29, so an <img> has no supported
         source and would only render blank. Products use a labelled
         .product-image-placeholder; decoration is drawn in CSS or an inline
         <svg> element. This runs in generation mode ONLY: modification mode
         edits the page already on disk, and rejecting a
         pre-existing <img> would deadlock the correction loop that exists to
         repair it. Modification-mode regressions are caught by the pipeline's
         resource sweep.
    Modification Mode (editing an already-validated file) is
    exempt — no session_id/components_specification round-trip is expected
    there, and re-validating a file that already passed this check on
    generation would only block the modify flow for no benefit.
    """
    intent     = runtime.state.get("intent", "generate")
    session_id = runtime.state.get("session_id", "")

    soup = BeautifulSoup(html_code, "html.parser")

    # ── Anchor Navigation Contract ───────────────────────────────────────────
    # Checked in BOTH modes, unlike every guard below it. Those need a
    # specification and are exempt in modify mode; this one compares the
    # document with itself, needs no spec, and a modify can introduce a dangling
    # link just as easily as a generation can.
    dangling = (_dangling_anchors(soup) + _duplicate_nav_anchors(soup)
                + _cross_document_links(soup))
    if dangling:
        return Command(update={"messages": [ToolMessage(
            content=(
                "Anchor Navigation Contract violation(s) - this system builds ONE "
                "document, so every nav link must point at a section that exists in "
                "it AND no two nav links may point at the same one. A dangling link "
                "fails silently: the click succeeds, the URL gains the fragment, and "
                "nothing scrolls, so no DOM assertion can catch it. Duplicated "
                "targets fail the same way - four links that all scroll to #main are "
                "not navigation. A link to another .html file fails the same way "
                "again, because there is no second file to reach. Give each nav "
                "item its own section with a matching "
                "id: " + "; ".join(dangling) +
                "\nFix and call store_html_code again."),
            tool_call_id=runtime.tool_call_id)]})

    # ── Search-input Prefill Contract (PO-08 po019fa283, 2026-09-05) ─────────
    # A type="search" input that ships with a non-empty value applies that
    # filter the moment the page loads. po019fa283 shipped value="coffee"; the
    # storefront's own applyProductFilters ran it at load and HID all 8 product
    # cards (no product name contains "coffee"), so the store rendered EMPTY and
    # every add-to-cart / cart test failed on an unclickable hidden button -- a
    # silent blank page no DOM assertion names as "the search box was prefilled".
    # Checked in BOTH modes: a modify can set a value just as easily. Example
    # text belongs in the placeholder; the value must ship empty.
    _prefilled_search = []
    for _inp in soup.find_all("input"):
        if (_inp.get("type") or "text").strip().lower() != "search":
            continue
        _sval = (_inp.get("value") or "").strip()
        if _sval:
            _who = _inp.get("id") or _inp.get("name") or "search"
            _prefilled_search.append(f'{_who}="{_sval}"')
    if _prefilled_search:
        return Command(update={"messages": [ToolMessage(
            content=(
                'Search-input Prefill violation - a type="search" input ships with '
                'a non-empty value, which filters the whole page at load and can '
                'hide every result (PO-08 po019fa283 shipped value="coffee" and the '
                'storefront rendered with ZERO products, so every cart test failed '
                'on a hidden button). Put example text in the placeholder, never in '
                'value; ship the value empty. Offending input(s): '
                + "; ".join(_prefilled_search) +
                '. Remove the value attribute (or set value="") and call '
                'store_html_code again.'),
            tool_call_id=runtime.tool_call_id)]})

    if intent == "generate" and session_id:
        expected_css = f"preview_{session_id}.css"
        expected_js  = f"preview_{session_id}.js"

        has_css_link  = any(expected_css in (tag.get("href") or "")
                            for tag in soup.find_all("link"))
        has_js_script = any(expected_js in (tag.get("src") or "")
                            for tag in soup.find_all("script"))
        missing_includes = []
        if not has_css_link:
            missing_includes.append(f'<link rel="stylesheet" href="{expected_css}">')
        if not has_js_script:
            missing_includes.append(f'<script src="{expected_js}" defer></script>')

        components_spec = _coerce_spec(
            runtime.state.get("components_specification") or {})
        if components_spec is None:
            return Command(update={"messages": [ToolMessage(
                content=(
                    "[INTERNAL] components_specification is a string that is not "
                    "valid JSON, so the coverage guard cannot run. This is a "
                    "pipeline configuration error, not a defect in your HTML. "
                    "Report it in your final message and stop - do not revise "
                    "the code."
                ),
                tool_call_id=runtime.tool_call_id
            )]})
        identities = _spec_component_identities(components_spec)
        missing_components = []
        for cid, cname in identities:
            found = soup.find(class_=cname) if cname else soup.find(id=cid)
            if not found:
                missing_components.append(
                    f"'{cid}' (expected class=\"{cname}\")" if cname
                    else f"'{cid}' (expected id=\"{cid}\")")

        unmaterialized, native_disabled = [], []
        for cid, cname, state_names in _spec_component_states(components_spec):
            elements = soup.find_all(class_=cname) if cname else soup.find_all(id=cid)
            if not elements:
                continue  # already reported by the addressability check above
            for name in state_names:
                low = name.lower()
                if low in _PSEUDO_STATES:
                    continue
                if low == "disabled":
                    # Disabled-State Contract: the resting aria-disabled="false"
                    # is required (checked below), the native attribute is not
                    # allowed at all -- it removes the control from the tab order
                    # and from the test pipeline's reach.
                    native = sum(1 for el in elements if el.has_attr("disabled"))
                    if native:
                        native_disabled.append(
                            f"'{cid}': {native} of {len(elements)} instance(s) carry "
                            f"the native disabled attribute")
                attr    = f"aria-{low}" if low in _ARIA_STATES else "data-state"
                resting = "false" if low in _ARIA_STATES else "default"
                bare    = sum(1 for el in elements if not el.has_attr(attr))
                if bare:
                    unmaterialized.append(
                        f"state '{name}' of '{cid}': {bare} of {len(elements)} "
                        f"instance(s) missing {attr}=\"{resting}\"")
                # Presence was never enough. The check above says "missing
                # aria-disabled=false" but accepted ANY value, so the SO-01 page
                # shipped aria-disabled="true" on the add-to-cart button: opacity
                # 0.5, cursor not-allowed, click refused by the browser. The page
                # was delivered unusable and every assertion still passed, because
                # a state attribute that is present but WRONG is invisible to a
                # presence test. Same family as the coverage guard that silently
                # checked nothing (report section 6.4 challenge 7).
                wrong = [str(el.get(attr)).strip()
                         for el in elements
                         if el.has_attr(attr)
                         and str(el.get(attr)).strip().lower() != resting]
                if wrong:
                    unmaterialized.append(
                        f"state '{name}' of '{cid}': {len(wrong)} of {len(elements)} "
                        f"instance(s) ship {attr}=\"{wrong[0]}\" but the RESTING "
                        f"value must be {attr}=\"{resting}\". The page is served "
                        f"with the state already active, so the control is unusable "
                        f"before any script runs. JavaScript flips it at runtime; "
                        f"the markup must start at rest.")

        # Component Category Contract. Presence is not enough, for the same
        # reason the state check stopped accepting any aria-disabled value: a
        # data-component that is present but WRONG routes the image rule and the
        # select-mode walk to the wrong component, and nothing downstream can
        # tell. Both halves are checked.
        miscategorized = []
        for cid, cname, category in _spec_component_categories(components_spec):
            elements = soup.find_all(class_=cname) if cname else soup.find_all(id=cid)
            if not elements:
                continue  # already reported by the addressability check above
            bare = sum(1 for el in elements if not el.has_attr("data-component"))
            if bare:
                miscategorized.append(
                    f"'{cid}': {bare} of {len(elements)} instance(s) missing "
                    f'data-component="{category}"')
            wrong = [str(el.get("data-component")).strip() for el in elements
                     if el.has_attr("data-component")
                     and str(el.get("data-component")).strip() != category]
            if wrong:
                miscategorized.append(
                    f"'{cid}': {len(wrong)} of {len(elements)} instance(s) ship "
                    f'data-component="{wrong[0]}" but components_specification '
                    f'declares componentCategory "{category}"')

        # Every record in dataSets must actually appear on the page. Before this
        # check the agent read the component tree, saw "a product card goes
        # here", and invented its own products -- so the JS agent's list and the
        # page disagreed and no click could ever resolve to a record.
        _page_text = " ".join(soup.get_text(" ").split()).lower()
        # A summary set is a value the page prints (the cart count), not a
        # record to list, so its invented name is not demanded (ticket 04).
        _summary_sets = _summary_data_sets(components_spec)
        missing_records = [
            f"{key}:'{name}'" for key, _rid, name in _dataset_records(components_spec)
            if key not in _summary_sets and name.lower() not in _page_text]

        bad_images     = _image_source_violations(soup)
        drawn_products = _product_image_violations(soup)
        loud_icons     = _icon_accessibility_violations(soup)
        sold_out_buyable = _sold_out_buyable_violations(soup)

        if (missing_includes or missing_components or unmaterialized
                or native_disabled or miscategorized or bad_images
                or drawn_products or loud_icons or missing_records
                or sold_out_buyable):
            lines = []
            if missing_includes:
                lines.append(
                    "Missing required include tag(s) — the generated CSS/JS files "
                    "are never loaded without them: " + "; ".join(missing_includes)
                )
            if missing_components:
                lines.append(
                    f"Component(s) from components_specification missing from the "
                    f"HTML (per the Naming Contract): {sorted(missing_components)}"
                )
            if unmaterialized:
                lines.append(
                    "State Materialization Contract violation(s) - every declared "
                    "state (except hover/focus) must already be present as a DOM "
                    "attribute with its resting value on EVERY instance: "
                    + "; ".join(unmaterialized)
                )
            if native_disabled:
                lines.append(
                    "Disabled-State Contract violation(s) - a disabled state is "
                    "carried by aria-disabled alone. The native disabled attribute "
                    "removes the control from the tab order, from the accessibility "
                    "tree, and from the test pipeline's reach: "
                    + "; ".join(native_disabled)
                )
            if miscategorized:
                lines.append(
                    "Component Category Contract violation(s) - a node that "
                    "declares componentCategory must carry that value verbatim as "
                    "data-component on the SAME element the Naming Contract "
                    "addresses. componentCategory says what a component IS; "
                    "id/className only say what it is called. The image rule and "
                    "the preview's select mode both resolve through it: "
                    + "; ".join(miscategorized)
                )
            if missing_records:
                lines.append(
                    "Shared Data Contract violation(s) - components_specification "
                    "carries dataSets, which is the ONE list of real content every "
                    "agent renders from. These record names appear nowhere in the "
                    "page, so you invented your own content instead of using it, "
                    "and the JavaScript agent's copy of the list will not match "
                    "what you rendered: " + ", ".join(missing_records) +
                    ". Render every record from dataSets, using its name verbatim."
                )
            if bad_images:
                lines.append(
                    "Image contract violation(s) - this system does not embed "
                    "images. An <img> has no supported source: for a product use a "
                    "labelled <div class=\"" + _PRODUCT_PLACEHOLDER_CLASS +
                    "\">Product Name</div>, and for decoration draw it in CSS or "
                    "an inline <svg> element: " + "; ".join(bad_images)
                )
            if drawn_products:
                lines.append(
                    "Product Image Contract violation(s) - a component whose "
                    "data-component is one of "
                    + ", ".join(_PRODUCT_IMAGE_ROLES) +
                    " must contain a LABELLED <div class=\""
                    + _PRODUCT_PLACEHOLDER_CLASS +
                    "\">Product Name</div> carrying the product name as real "
                    "text. The image feature was removed, so a photograph is no "
                    "longer an option and a drawn or empty box is refused. "
                    "Decorative regions (hero banners, promo strips, icons) are "
                    "unaffected and may still be drawn: "
                    + "; ".join(drawn_products)
                )
            if loud_icons:
                lines.append(
                    "Icon Accessibility Contract violation(s) - an inline <svg> "
                    "inside a button or link is decorative: it carries "
                    "aria-hidden=\"true\" and the control around it carries the "
                    "aria-label. A screen reader then announces the action rather "
                    "than the glyph, and the preview's select mode resolves a "
                    "click to the component that owns the icon rather than to the "
                    "icon itself: "
                    + "; ".join(loud_icons)
                )
            if sold_out_buyable:
                lines.append(
                    "Sold-Out Materialization violation(s) - a product-card at zero "
                    "stock is sold out at load, so its add-to-cart must ship "
                    "aria-disabled=\"true\" (never the native disabled attribute) and "
                    "the card's data-state must be the declared unavailable state, not "
                    "\"default\". These cards are still buyable in the DOM: "
                    + "; ".join(sold_out_buyable)
                )
            lines.append("Fix the issue(s) above and call store_html_code again.")
            return Command(update={"messages": [ToolMessage(
                content="\n".join(lines),
                tool_call_id=runtime.tool_call_id
            )]})

    return Command(update={
        "html_code": html_code,
        "messages": [ToolMessage(
            content="HTML code saved to state.",
            tool_call_id=runtime.tool_call_id
        )]
    })


# ==========================================================================
# extract_component
# ==========================================================================
from bs4 import BeautifulSoup
from bs4.formatter import HTMLFormatter as _HTMLFormatter
from bs4.dammit import EntitySubstitution as _EntitySubstitution

# How this project serialises HTML back out of BeautifulSoup.
#
# Every serialisation in the HTML agent goes through this, and they must all
# agree: extract_component hands the model a block, the model diffs against
# THAT text, and store_html_diff has to rebuild the identical string to find it
# again. A second formatter anywhere is a diff that silently stops matching.
#
# The html5 formatter was the original choice, for its TAG shape: it leaves
# <meta charset="utf-8"> alone instead of writing <meta/>, and keeps `checked`
# a boolean instead of `checked=""`. html-validate rejects both of those, so
# that part must stay.
#
# It also has an ENTITY rule nobody asked for. On bs4 4.14 it leaves an
# unambiguous ampersand bare, so `&amp;` in the page comes back as `&` the
# first time the document is re-serialised, and html-validate's
# no-raw-characters refuses it. E2E-MM-01 on 2026-08-31 lost all three lint
# attempts to exactly that: the damage landed in the product grid while the
# model was editing the navbar, so it could not reach it, and another apply
# would have undone any repair anyway. Only the cap ended it. "Terms &
# Conditions" is ordinary shop copy, so this was never a rare case.
#
# So: html5's tag shape, minimal's entity rule. Measured against the html5
# formatter on the same input, the ampersand is the ONLY difference --
# void tags, boolean attributes and named entities come out byte-identical.
_HTML_FORMATTER = _HTMLFormatter(
    entity_substitution=_EntitySubstitution.substitute_html,
    void_element_close_prefix="",
    empty_attributes_are_booleans=True,
)



def _extract_html_batch(runtime, wanted: list, dropped: list, upgraded: bool = False) -> Command:
    """Extract several elements in ONE call, or refuse the batch and say why.

    Two batches are refused rather than served, and both refusals name the way
    out -- a guard the model cannot satisfy is a wall, not a guard.

      NESTING. If .product-card and .product-card__name are both targets, the
      second lives inside the first. Applying the first diff re-serialises that
      subtree, so the text the second diff was written against no longer exists
      in the document and its apply fails on a stale context match. The way out
      is one diff against the OUTER element, which contains both changes.

      Nothing else here can go stale. The applies run sequentially inside one
      Python call, each on the result of the last, so two DISJOINT elements
      cannot interfere -- which is exactly what parallel tool calls could not
      promise.

    A target that does not resolve is NOT a refusal: it is reported in the
    message and the rest are returned. The prompt already treats a stale
    selector as something to skip, not to solve.
    """
    html = runtime.state.get("html_code", "")
    if not html:
        return Command(update={"messages": [ToolMessage(
            content="html_code is empty. Cannot extract component.",
            tool_call_id=runtime.tool_call_id)]})

    soup   = BeautifulSoup(html, "html.parser")
    _spec  = runtime.state.get("components_specification")
    picked, missing = [], []
    for name in wanted:
        sel, matches = _html_select_component(soup, name, _spec)
        if matches:
            picked.append((sel, matches[0]))
        else:
            missing.append(name)

    if not picked:
        return Command(update={"messages": [ToolMessage(
            content=(f"None of {wanted} matched an element. The page offers: "
                     f"{_html_addressables(soup)}. Per the Naming Contract a "
                     f"component is addressed by its className when it declares "
                     f"one, and by #id only otherwise."),
            tool_call_id=runtime.tool_call_id)]})

    # Nested targets are MERGED, not refused. A diff against the outer element
    # re-serialises the inner one, so the inner element's own diff would be
    # written against text that no longer exists -- but the answer to that is
    # one diff against the outer element, which is exactly what serving the
    # outer element once asks for.
    def _nested(_i, _j):
        _a, _b = picked[_i][1], picked[_j][1]
        return any(_p is _a for _p in _b.parents) or any(_p is _b for _p in _a.parents)

    items, covered = [], []
    for _g in _conflict_groups(len(picked), _nested):
        # The OUTERMOST element is the keeper: it contains the others, so its
        # text is the only text that holds every change.
        _keep = min(_g, key=lambda _k: len(list(picked[_k][1].parents)))
        _lab = picked[_keep][0]
        items.append((_lab, picked[_keep][1].decode(formatter=_HTML_FORMATTER)))
        _others = [picked[_k][0] for _k in _g if _k != _keep]
        if _others:
            covered.append((_lab, _others))
    note  = _merged_note(covered)
    if upgraded:
        note += ("\n\nYou asked for ONE component; this call carries "
                 f"{len(wanted)}, and all {len(wanted)} are above. Do NOT call "
                 "this tool again. Write one diff per component and send them "
                 "together in a single apply_and_lint_html call using its `diffs` argument.")
    if missing:
        note += (f"\n\nNot found, so not included (treat as stale selectors and "
                 f"skip them; do not search for them): {', '.join(missing)}.")
    if dropped:
        note += f"\n\nDropped from this call: {'; '.join(dropped)}."
    note += ("\n\nWrite ONE diff per component, each with line numbers starting "
             "at 1 for its own block, and never include a '=====' separator line "
             "in a hunk. Then send them together in a single apply_and_lint_html "
             "call using its `diffs` argument.")

    # One reset for the whole batch, not one per component: the batch is a
    # single apply and a single lint, so it is a single budget.
    return Command(update={
        "last_extracted_component": picked[0][0],
        "last_extracted_instance":  1,
        "lint_attempts":            0,
        "patch_attempts":           0,
        "messages": [ToolMessage(
            content=_join_components(items) + note,
            tool_call_id=runtime.tool_call_id)]})


@tool
def extract_component(runtime: ToolRuntime[HtmlState],
                      component: str = "",
                      instance: int = 0,
                      components: Optional[List[str]] = None) -> Command:
    """
    Extract the target component block from html_code.
    target_component in state can be:
    - A CSS selector starting with # (id) or . (class): matched directly
    - A bare word: tried as #word then .word (backwards-compatible with test-report names)
    target_instance in state (1-based, default 1) picks which match to return when the
    selector matches several elements — it must agree with store_html_diff, which patches
    the same instance.
    Call this in Modification Mode before generating a diff.

    `components` extracts SEVERAL elements in one call -- pass the whole
    target_components list and get every block back in one message, each
    under a "===== WebForge component n of m: <name> =====" line. Prefer it:
    five separate extracts are five re-sends of the whole page. Batch mode
    takes instance 1 of each selector, so a fix aimed at the Nth copy of a
    repeated element must be sent on its own.
    """
    if components:
        _batch, _dropped = _clean_batch(components)
        if len(_batch) > 1:
            return _extract_html_batch(runtime, _batch, _dropped)
        if _batch:
            component = component or _batch[0]
    elif len(runtime.state.get("target_components", []) or []) > 1:
        # Asked for ONE while the call carries several. Hand over the whole
        # batch rather than the one: the prompt already asks for it, and on
        # 2026-08-31 the HTML agent ignored that ask on its first live run
        # while the other two obeyed it. Making the first call complete is what
        # leaves the second call nothing to fetch.
        _batch, _dropped = _clean_batch(runtime.state["target_components"])
        if len(_batch) > 1:
            return _extract_html_batch(runtime, _batch, _dropped, upgraded=True)

    # component/instance are ARGUMENTS so one session can walk a batch:
    # the state fields carry only the FIRST target, and a batched modify
    # has to be able to name the second. Both fall back to state, so every
    # single-target call and every existing test is unchanged.
    selector = component or runtime.state.get("target_component", "")
    instance = instance or runtime.state.get("target_instance", 1) or 1
    html     = runtime.state.get("html_code", "")

    if not html:
        return Command(update={"messages": [ToolMessage(
            content="html_code is empty. Cannot extract component.",
            tool_call_id=runtime.tool_call_id
        )]})
    if not selector:
        return Command(update={"messages": [ToolMessage(
            content="target_component not set in state.",
            tool_call_id=runtime.tool_call_id
        )]})

    soup = BeautifulSoup(html, "html.parser")
    # Naming Contract: the work order names the specification id while the page
    # carries the className. _html_select_component walks every alias through
    # the same selector/#id/.class ladder the bare-word fallback used to walk
    # for one name only. See _component_name_aliases.
    _spec = runtime.state.get("components_specification")
    selector, matches = _html_select_component(soup, selector, _spec)

    if not matches:
        return Command(update={"messages": [ToolMessage(
            content=(
                f"No element found matching '{selector}' (tried "
                f"{_component_name_aliases(selector, _spec)}, each as a CSS "
                f"selector, then #id, then .class). The page offers: "
                f"{_html_addressables(soup)}. Per the Naming Contract a component "
                f"is addressed by its className when it declares one, and by #id "
                f"only otherwise - use a name from that list."
            ),
            tool_call_id=runtime.tool_call_id
        )]})
    # Same range check as store_html_diff, so the model never sees an element
    # that store_html_diff would refuse (or worse, silently patch elsewhere).
    if instance < 1 or instance > len(matches):
        return Command(update={"messages": [ToolMessage(
            content=f"Instance {instance} out of range. Found {len(matches)} instance(s).",
            tool_call_id=runtime.tool_call_id
        )]})

    # formatter=_HTML_FORMATTER: str() would restyle the block (<meta/>, checked="")
    # into forms html-validate rejects. The block returned here is what the
    # model diffs against, so it must match store_html_diff's serialization.
    block = matches[instance - 1].decode(formatter=_HTML_FORMATTER)
    note  = f"  ({len(matches)} match(es) found; returning instance {instance})" if len(matches) > 1 else ""
    # Remember what was just extracted, for two reasons.
    # 1. apply_and_lint_html falls back to THIS rather than to
    #    target_component, so a model that forgets to repeat the argument
    #    patches the element it actually extracted instead of silently
    #    patching the batch's first component. A forgotten argument has to
    #    be harmless, not corrupting.
    # 2. The lint and patch budgets are per COMPONENT, not per session --
    #    without the reset the first component in a batch of six spends
    #    the whole allowance and the other five get none. This mirrors
    #    extract_css_component, whose prompt already promises the reset.
    return Command(update={
        "last_extracted_component": selector,
        "last_extracted_instance":  instance,
        "lint_attempts":            0,
        "patch_attempts":           0,
        "messages": [ToolMessage(
            content=block + note,
            tool_call_id=runtime.tool_call_id
        )]})


# ==========================================================================
# store_html_diff
# ==========================================================================
def _html_element_for(html_code: str, selector: str, instance: int,
                      components_spec=None):
    """Return the html5-serialized text of the (selector, Nth-instance) element,
    or None if it does not resolve. Used to hand the current element back to the
    model on a failed apply, so it re-diffs without a separate extract_component.
    Resolution mirrors extract_component / store_html_diff exactly."""
    if not html_code or not selector:
        return None
    soup = BeautifulSoup(html_code, "html.parser")
    selector, matches = _html_select_component(soup, selector, components_spec)
    if not matches or instance < 1 or instance > len(matches):
        return None
    return matches[instance - 1].decode(formatter=_HTML_FORMATTER)


def _apply_html_component_diff(html_code: str, selector: str, instance: int,
                               diff_output: str, components_spec=None) -> dict:
    """
    Apply a unified diff to the (selector, Nth-instance) element and splice the
    result back into the full document. Pure function -- no state, no ToolMessage
    -- so both store_html_diff and apply_and_lint_html format their own responses
    from ONE source of truth. Returns one of:
      {"status": "empty"}                                          html_code empty
      {"status": "noselector"}                                     target_component unset
      {"status": "noblock", "reason": "notfound"}                  selector matched nothing
      {"status": "noblock", "reason": "range", "n_matches": <int>} instance out of range
      {"status": "diff_fault", "error": <str>}                     stale/malformed diff
      {"status": "internal", "etype": <str>, "error": <str>}       wiring/env fault
      {"status": "ok", "new_html_code": <str>}                     applied cleanly
    """
    if not html_code:
        return {"status": "empty"}
    if not selector:
        return {"status": "noselector"}
    soup = BeautifulSoup(html_code, "html.parser")
    selector, matches = _html_select_component(soup, selector, components_spec)
    if not matches:
        return {"status": "noblock", "reason": "notfound"}
    if instance < 1 or instance > len(matches):
        return {"status": "noblock", "reason": "range", "n_matches": len(matches)}
    el             = matches[instance - 1]
    original_block = el.decode(formatter=_HTML_FORMATTER)   # must match extract_component
    try:
        patched_block = _apply_patch(original_block, diff_output)
    except (ValueError, IndexError, KeyError) as e:
        return {"status": "diff_fault", "error": str(e)}
    except (NameError, ImportError, AttributeError, TypeError) as e:
        return {"status": "internal", "etype": type(e).__name__, "error": str(e)}
    el.replace_with(BeautifulSoup(patched_block, "html.parser"))
    # formatter=_HTML_FORMATTER, NOT str(): the default serializer restyles the ENTIRE
    # document (<meta/> for void tags, checked="" for boolean attributes) which
    # html-validate rejects, landing errors outside the modify scope.
    return {"status": "ok", "new_html_code": soup.decode(formatter=_HTML_FORMATTER)}


@tool
def store_html_diff(
    diff_output: str,
    runtime:     ToolRuntime[HtmlState],
) -> Command:
    """
    Apply a unified diff to the target component and splice the result back into
    html_code in state. Thin wrapper over _apply_html_component_diff (shared with
    apply_and_lint_html); messages unchanged. Reads target_component
    (a CSS selector) and target_instance from state. In Modification Mode apply
    every change through apply_and_lint_html, not store_html_code.
    """
    selector = runtime.state.get("target_component", "")
    instance = runtime.state.get("target_instance", 1)
    html     = runtime.state.get("html_code", "")
    res = _apply_html_component_diff(
        html, selector, instance, diff_output,
        runtime.state.get("components_specification"))
    st  = res["status"]
    if st == "empty":
        return Command(update={"messages": [ToolMessage(
            content="html_code is empty. Cannot apply diff.",
            tool_call_id=runtime.tool_call_id)]})
    if st == "noselector":
        return Command(update={"messages": [ToolMessage(
            content="target_component not set in state.",
            tool_call_id=runtime.tool_call_id)]})
    if st == "noblock":
        msg = (f"Instance {instance} out of range. Found {res['n_matches']} instance(s)."
               if res.get("reason") == "range"
               else (f"Component not found: no element matches '{selector}' "
                     f"(tried as CSS selector, #id, and .class)."))
        return Command(update={"messages": [ToolMessage(
            content=msg, tool_call_id=runtime.tool_call_id)]})
    if st == "diff_fault":
        return Command(update={"messages": [ToolMessage(
            content=f"Patch failed: {res['error']}\nRe-extract and regenerate the diff.",
            tool_call_id=runtime.tool_call_id)]})
    if st == "internal":
        return Command(update={"messages": [ToolMessage(
            content=(f"[INTERNAL] {res['etype']}: {res['error']}\n"
                     "This is a wiring or environment fault, not a defective diff. "
                     "Regenerating the diff will not help. In a notebook session "
                     "this usually means the cell defining the missing name has "
                     "not been run."),
            tool_call_id=runtime.tool_call_id)]})
    return Command(update={
        "html_code": res["new_html_code"],
        "messages":  [ToolMessage(
            content=f"Diff applied. '{selector}' instance {instance} updated.",
            tool_call_id=runtime.tool_call_id)]})


# ==========================================================================
# apply_and_lint_html
# ==========================================================================
def _apply_html_batch(runtime, diffs: list) -> Command:
    """Apply several diffs to one document, then lint ONCE.

    Sequential, inside one Python call, each diff applied to the result of the
    last. That is the whole reason this is a batch ARGUMENT rather than several
    parallel tool calls: parallel applies would each start from the same stale
    html_code and one fix would silently overwrite another.

    PARTIAL COMMIT is deliberate. All-or-nothing would throw away four good
    fixes because a fifth diff miscounted its line numbers, and the model would
    have to rewrite all five. Sequential application makes the successes safe to
    keep, so they are kept and the reply says exactly which ones they are.
    """
    html   = runtime.state.get("html_code", "")
    if not html:
        return Command(update={"messages": [ToolMessage(
            content="html_code is empty. Cannot apply diff.",
            tool_call_id=runtime.tool_call_id)]})
    _cspec = runtime.state.get("components_specification")

    rows, failed, n_ok = [], [], 0
    for entry in diffs:
        if not isinstance(entry, dict):
            rows.append(("FAILED", str(entry)[:40], "not a {component, diff_output} object"))
            continue
        sel  = str(entry.get("component") or "").strip()
        inst = int(entry.get("instance") or 1)
        body = entry.get("diff_output") or entry.get("diff") or ""
        if not sel:
            rows.append(("FAILED", "(unnamed)", "no component named"))
            failed.append((sel, inst))
            continue
        res = _apply_html_component_diff(html, sel, inst, body, _cspec)
        st  = res["status"]
        if st == "ok":
            html = res["new_html_code"]
            n_ok += 1
            rows.append(("OK", sel, ""))
        elif st == "internal":
            rows.append(("FAILED", sel, f"[INTERNAL] {res['etype']}: {res['error']}"))
            failed.append((sel, inst))
        elif st == "noblock":
            why = (f"instance {inst} out of range, {res.get('n_matches')} found"
                   if res.get("reason") == "range" else "no element matched")
            rows.append(("SKIPPED", sel, why))
        else:
            rows.append(("FAILED", sel, res.get("error", st)))
            failed.append((sel, inst))

    header = (f"Applied {n_ok} of {len(diffs)} diff(s) in one call.\n"
              + _batch_status_table(rows))

    # Nothing landed: html_code is untouched, so this is a plain patch failure
    # and must count against the patch budget like the single-component path.
    if n_ok == 0:
        tail = ""
        for sel, inst in failed:
            blk = _html_element_for(html, sel, inst, _cspec)
            if blk:
                tail += (f"\n\nCurrent element for '{sel}' (diff against THIS, "
                         f"do NOT re-extract):\n\n{blk}")
        return _patch_failure(runtime, header + tail)

    lint_cmd = _lint_html_source(html, runtime)
    upd = dict(lint_cmd.update)
    upd["html_code"] = html
    lint_msg = upd["messages"][0]
    combined = f"{header}\n\n{lint_msg.content}"

    if failed:
        # Some landed and some did not, so the budget is counted here rather
        # than through _patch_failure, which would discard the ones that landed.
        attempts = runtime.state.get("patch_attempts", 0) + 1
        upd["patch_attempts"] = attempts
        if attempts >= _PATCH_ATTEMPT_CAP:
            combined += (f"\n\n[PATCH CAP REACHED] {attempts}/{_PATCH_ATTEMPT_CAP} "
                         "calls in a row left a diff unapplied. Do NOT rewrite the "
                         "failed diffs. Save the current best-effort code and END "
                         "your turn, naming what is unfixed.")
        else:
            for sel, inst in failed:
                blk = _html_element_for(html, sel, inst, _cspec)
                if blk:
                    combined += (f"\n\nCurrent element for '{sel}' AFTER the diffs "
                                 f"that did apply (diff against THIS, do NOT "
                                 f"re-extract):\n\n{blk}")
    else:
        upd["patch_attempts"] = 0

    if (not upd.get("lint_passed", False)
            and _LINT_CAP_MARKER not in lint_msg.content
            and not failed):
        # Lint errors with every diff applied: the model needs current text for
        # the components it just changed, exactly as the single path hands back
        # its one element.
        for _ok, _lab, _why in rows:
            if _ok != "OK":
                continue
            blk = _html_element_for(html, _lab, 1, _cspec)
            if blk:
                combined += (f"\n\nCurrent element for '{_lab}' AFTER this patch "
                             f"(diff against THIS, do NOT re-extract):\n\n{blk}")

    upd["messages"] = [ToolMessage(content=combined,
                                   tool_call_id=runtime.tool_call_id)]
    return Command(update=upd)


@tool
def apply_and_lint_html(diff_output: str = "",
                        runtime: ToolRuntime[HtmlState] = None,
                        component: str = "",
                        instance: int = 0,
                        diffs: Optional[List[dict]] = None) -> Command:
    """
    Modification Mode: apply a unified diff to the target element AND lint the
    whole document in ONE call, so a fix comes back with its html-validate
    verdict already attached -- no separate run_html_validate round-trip.

    Reads target_component (a CSS selector) and target_instance from state, like
    store_html_diff. The diff must be relative to the exact text extract_component
    returned. On a patch failure OR a lint failure the CURRENT element is handed
    back in the message so the model regenerates the diff against it WITHOUT
    re-extracting. If the element can no longer be located (e.g. the diff changed
    the id used as the selector), the message says so and the model may
    re-extract as a last resort.

    `diffs` applies SEVERAL components in one call and lints ONCE at the
    end: [{"component": ".product-card", "diff_output": "--- original..."},
    ...]. Prefer it -- five separate calls are five re-sends of the whole
    page and five linter runs. They are applied in order, each on the result
    of the last, so the ones that apply are KEPT even if a later one fails;
    the reply names which landed and hands back the current element for each
    that did not.
    """
    # An EMPTY call is refused, never applied. diffs=[] is falsy, so before
    # this guard it fell through to the single-diff path with nothing to
    # apply, and patching nothing "succeeded": on 13b71045 (2026-09-15) the
    # agent read "Diff applied ... No issues found.", saved the unchanged
    # page, and the orchestrator reported the change as done.
    if not diffs and not (diff_output or "").strip():
        return Command(update={"messages": [ToolMessage(
            content=("No diff supplied: diffs is empty and diff_output is blank. "
                     "Nothing was applied and the code did not change. Write the "
                     "unified diff against the extracted block and call again. "
                     "If there is genuinely nothing to change, do not save; end "
                     "your turn and say the request needs no edit."),
            tool_call_id=runtime.tool_call_id)]})
    if diffs:
        return _apply_html_batch(runtime, diffs)

    # Resolution order matters. The explicit argument wins; then what
    # extract_component last handed back, which is the element this diff
    # was actually written against; then state, for a single-target call
    # that never extracted. Putting last_extracted_* AHEAD of state is
    # what stops a forgotten argument from patching a different element
    # in a batch, silently and successfully.
    selector = (component
                or runtime.state.get("last_extracted_component", "")
                or runtime.state.get("target_component", ""))
    instance = (instance
                or runtime.state.get("last_extracted_instance", 0)
                or runtime.state.get("target_instance", 1) or 1)
    html     = runtime.state.get("html_code", "")

    _cspec = runtime.state.get("components_specification")
    res = _apply_html_component_diff(html, selector, instance, diff_output, _cspec)
    st  = res["status"]

    if st == "empty":
        return Command(update={"messages": [ToolMessage(
            content="html_code is empty. Cannot apply diff.",
            tool_call_id=runtime.tool_call_id)]})
    if st == "noselector":
        return Command(update={"messages": [ToolMessage(
            content="target_component not set in state.",
            tool_call_id=runtime.tool_call_id)]})
    if st == "noblock":
        msg = (f"Instance {instance} out of range. Found {res['n_matches']} instance(s)."
               if res.get("reason") == "range"
               else (f"No element found for '{selector}' (tried as CSS selector, "
                     "#id, and .class). Check the target, then extract and diff again."))
        return Command(update={"messages": [ToolMessage(
            content=msg, tool_call_id=runtime.tool_call_id)]})
    if st == "internal":
        return Command(update={"messages": [ToolMessage(
            content=(f"[INTERNAL] {res['etype']}: {res['error']}\n"
                     "This is a wiring or environment fault, not a defective diff. "
                     "Regenerating the diff will not help."),
            tool_call_id=runtime.tool_call_id)]})
    if st == "diff_fault":
        # html_code did NOT change -- hand back the current element so the model
        # re-diffs without a separate extract_component round-trip.
        block = _html_element_for(html, selector, instance, _cspec)
        tail  = (("\nRegenerate the diff against the CURRENT element below "
                  "(do NOT re-extract):\n\n" + block) if block else
                 "\n(Could not re-locate the element; re-extract with extract_component.)")
        # Counted and capped: this path used to count nothing, so a model
        # that kept miscounting line numbers could re-diff forever.
        return _patch_failure(runtime,
            f"Patch failed: {res['error']}\n" + tail)

    # Applied cleanly -- lint the NEW document in the same call.
    new_html     = res["new_html_code"]
    applied_note = f"Diff applied. '{selector}' instance {instance} updated."
    lint_cmd = _lint_html_source(new_html, runtime)
    upd = dict(lint_cmd.update)
    upd["html_code"] = new_html
    upd["patch_attempts"] = 0      # applied: the run of failures is over
    lint_msg = upd["messages"][0]
    combined = f"{applied_note}\n{lint_msg.content}"
    # On a lint FAILURE the code changed, so hand back the NEW element too -- the
    # next diff is written against current text, again with no re-extract. The
    # cap-reached message is left alone (the loop must stop, not re-diff).
    if not upd.get("lint_passed", False) and _LINT_CAP_MARKER not in lint_msg.content:
        new_block = _html_element_for(new_html, selector, instance, _cspec)
        if new_block:
            combined += ("\n\nCurrent element AFTER this patch (diff against THIS, "
                         "do NOT re-extract):\n\n" + new_block)
    upd["messages"] = [ToolMessage(content=combined, tool_call_id=runtime.tool_call_id)]
    return Command(update=upd)


# ==========================================================================
# apply_and_lint_html
# ==========================================================================
# ═══════════════════════════════════════════════════════════════════════════
# apply_and_lint_html_full - generation-mode fix by EXACT-TEXT edits
#
# Generation mode's store_html_code takes the ENTIRE page every time, so each
# lint error made the model re-emit the whole document. On the coffee build that
# was several full emissions, each one re-feeding the specs and the prior page as
# input (PO-08, 2026-08-29).
#
# This lets the model FIX the page it last submitted with a list of {old, new}
# text edits, instead of re-sending the whole document. Each `old` is located by
# EXACT STRING MATCH, not by line number:
#   - found exactly once -> replaced;
#   - not found, or found more than once -> the WHOLE batch aborts and the page
#     is returned UNCHANGED, with a message naming the edit and why.
# A line-numbered whole-page diff was tried first and rolled back: the model
# miscounts line numbers on a large document and the patch applied at the wrong
# place, silently corrupting the page (GM-01, 2026-08-30). Content matching cannot
# do that -- a bad edit is a no-op, never a corruption.
#
# It composes three proven pieces and changes none of them:
#   _apply_search_replace - the exact-text applicator defined just below
#   store_html_code       - the ONE source of truth for the generation guard
#   _lint_html_source     - the linter apply_and_lint_html already reuses
# The first submission stays a full store_html_code; every fix after is edits.
# ═══════════════════════════════════════════════════════════════════════════
def _apply_search_replace(text, edits):
    """Apply exact-text edits to `text`. Each edit is {"old": str, "new": str}.

    An edit whose `old` occurs EXACTLY ONCE in the running text is applied. Zero
    matches or more than one match aborts the whole batch and returns the ORIGINAL
    text unchanged, so a bad edit can never corrupt the page. Edits apply in order,
    so a later edit searches the result of the earlier ones.

    Returns (new_text, error). error is None on success, else a human-readable
    string and new_text == text (unchanged).
    """
    if not isinstance(edits, list) or not edits:
        return text, ("No edits given. Pass a non-empty list of "
                      '{"old": <exact current text>, "new": <replacement>} objects.')
    work = text
    for i, e in enumerate(edits, 1):
        if not isinstance(e, dict) or "old" not in e or "new" not in e:
            return text, (f"Edit {i} is malformed: each edit needs an 'old' and a "
                          "'new' string.")
        old, new = e["old"], e["new"]
        if not isinstance(old, str) or not isinstance(new, str):
            return text, f"Edit {i}: both 'old' and 'new' must be strings."
        if old == "":
            return text, (f"Edit {i}: 'old' is empty. Give the exact current text "
                          "to replace (to insert, anchor on a nearby existing line).")
        count = work.count(old)
        if count == 0:
            return text, (f"Edit {i}: the 'old' text was not found, so nothing was "
                          "changed. Copy the exact current text, including "
                          "whitespace, and try again.")
        if count > 1:
            return text, (f"Edit {i}: the 'old' text appears {count} times, so the "
                          "target is ambiguous and nothing was changed. Extend "
                          "'old' with surrounding lines until it is unique.")
        work = work.replace(old, new, 1)
    return work, None


@tool
def apply_and_lint_html_full(edits: list, runtime: ToolRuntime[HtmlState]) -> Command:
    """
    Generation Mode: fix the current page with a list of exact-text edits, re-run
    the generation guard, and lint -- all in one call. Use this to FIX the page
    AFTER the first store_html_code, instead of re-sending the whole document.

    edits is a list of {"old": <exact current text>, "new": <replacement>}. Each
    'old' must appear on the page EXACTLY ONCE. If an 'old' is missing or not
    unique, the page is left UNCHANGED and the message names the edit and why, so
    you resend that edit with more surrounding context (or, as a fallback, re-send
    the whole corrected page with store_html_code). This cannot corrupt the page:
    an edit applies only where its 'old' text is found in exactly one place. You
    may pass several edits to fix several places in one call; to INSERT, set 'old'
    to a unique existing line and 'new' to that line plus the added markup.
    """
    html = runtime.state.get("html_code", "")
    if not html:
        return Command(update={"messages": [ToolMessage(
            content=("html_code is empty. Store the full page with store_html_code "
                     "once before fixing it by edits."),
            tool_call_id=runtime.tool_call_id)]})

    patched, err = _apply_search_replace(html, edits)
    if err is not None:
        return Command(update={"messages": [ToolMessage(
            content=(err + "\nThe page is UNCHANGED. Fix the edit and call "
                     "apply_and_lint_html_full again, or re-send the whole "
                     "corrected page with store_html_code."),
            tool_call_id=runtime.tool_call_id)]})

    # The SAME generation guard store_html_code enforces, on the edited page. It
    # reads intent/session_id/specs from state and takes the code as its argument,
    # so calling it here runs the identical checks with zero duplication.
    guard_cmd = store_html_code.func(patched, runtime)
    gupd = guard_cmd.update or {}
    if "html_code" not in gupd:
        detail = (gupd["messages"][0].content if gupd.get("messages")
                  else "a generation check failed.")
        return Command(update={"messages": [ToolMessage(
            content=("The edited page still fails a generation check.\n" + detail +
                     "\nFix it with another edit and call apply_and_lint_html_full "
                     "again, or re-send the whole corrected page with "
                     "store_html_code."),
            tool_call_id=runtime.tool_call_id)]})

    # Guard passed; lint the edited page the same way apply_and_lint_html does.
    lint_cmd = _lint_html_source(patched, runtime)
    update = {"html_code": patched}
    for k, v in (lint_cmd.update or {}).items():
        if k != "html_code":
            update[k] = v
    return Command(update=update)


# ==========================================================================
# System prompt
# ==========================================================================
# ── Shared base (loaded in BOTH modes) ───────────────────────────────────────
_html_shared_base = """
You are a specialized HTML Developer Agent. Your sole responsibility is to generate
or modify syntactically valid, semantic HTML code and ensure the final output fully
passes linting before saving to the file system.

---

## Context You Have Access To
- User\'s original request
- Current agent state: html_code, lint_passed, layout_specification,
  components_specification, intent, target_component

---

## Compliance Mode (MANDATORY)
These constraints are non-negotiable and override user aesthetic preferences:

### W3C Semantic HTML
- Use <nav>, <main>, <header>, <footer>, <section>, <article>, <aside> — not bare <div> for layout
- One <h1> per page; heading levels must not skip (h1 → h2 → h3)
- Use <button> for actions, <a href> for navigation — never <div onclick> or <span onclick>

### WCAG 2.1 Level AA
- This system embeds no <img> photographs; a product's image slot is a labelled
  .product-image-placeholder carrying the product name (see Image Policy below)
- Every form <input> must have an associated <label for="..."> or aria-label
- All interactive elements reachable by Tab (no tabindex="-1" on focusable elements)
- Use aria-label on icon-only buttons (cart icon, search icon, close icon)
- Icons come from the catalogue at the end of this prompt. Inline the SVG shown
  there. Never use a unicode glyph as an icon: it renders differently on every
  font stack and can render as a blank box.

### Image Policy (no photographs)
This system does NOT embed images. Bundling and hosting product photos was
removed as a system Limitation: a user cannot realistically pre-load and name a
photo for every product, and a broken <img> renders blank while still passing
every DOM assertion. So:
- Do NOT use <img> tags. store_html_code refuses every <img> in generation mode,
  because it has no supported source.
- A product's image slot is a LABELLED placeholder:
      <div class="product-image-placeholder">Orchid Bouquet</div>
  The product name must be there as REAL text, not painted into an SVG. That is
  what separates an honest placeholder from a grey box: it says which product it
  stands for, assert_text can read it, and a screen reader can announce it. An
  empty .product-image-placeholder is refused. Every component whose
  data-component is product-card, product-image-gallery or cart-item MUST carry
  one.
- Everywhere else you are free to draw. Hero artwork, promo strips, background
  shapes and icons may be built from CSS or an inline <svg> element, and doing
  that well is encouraged - it costs no requests and cannot fail to load. An
  inline <svg> is not an <img>: it has no src to break and is allowed anywhere.

### Baymard Institute — B2C E-commerce Structure
- Product cards: always include a labelled product-image placeholder, name, price, primary CTA
- Navigation: persistent cart icon with item count badge
- Product detail: show shipping cost estimate near add-to-cart button
- Checkout: include progress indicator (<ol> with steps) at the top
- Forms: mark required fields with *, include <legend> in fieldsets
- Guest checkout option must appear before account creation is pushed

### Anchor Navigation Contract (single-document navigation)
This system builds ONE document per run. A site with several areas is that one
document with several sections, not several files.
- Every region in the layout specification becomes an element with `id="<regionId>"`
  (a `<section>` unless the spec says otherwise).
- A navigation link to a region is `<a href="#<regionId>">`, never a `.html` path.
- `store_html_code` REFUSES any link to another local document, in both modes.
  That covers `checkout.html`, `/checkout`, `./cart.html` and `pages/pdp.html`.
  There is no second file to reach, so such a link is a guaranteed dead end and
  it fails silently: the click succeeds and the user lands on nothing.
- Links that genuinely leave the page are still fine: `https://`, `http://`,
  `mailto:`, `tel:` and `javascript:void(0)` as a control placeholder.
- Every in-page `href="#x"` MUST have a matching `id="x"` in the same document.
  `store_html_code` refuses the submission otherwise, in generation AND
  modification mode, because a dangling link fails silently: the click succeeds,
  the URL gains the fragment, and the page does not move.
- An anchor target is an ATTRIBUTE, never a new wrapper. Put the `id` on an
  element that is already there -- `<article id="light-roast"
  class="product-card">` -- and do NOT wrap groups of elements in extra
  `<section>`s just to hold the ids. On run po01e9a8b4 six invented wrapper
  sections became the items of the product grid, so the eight real cards sat
  two levels below it and never reached the grid at all; each wrapper then
  stretched to 2863px and its cards overflowed onto the row beneath. A
  wrapper that exists only to carry an id is what breaks the layout.
- `href="#"` and `href="#top"` are allowed and are never checked.

### Conflict Resolution Priority
1. WCAG 2.1 AA — never violate
2. W3C HTML5 semantic structure
3. Baymard Institute e-commerce structure
4. User aesthetic preference — adapt silently if it conflicts with 1–3

---

## Strict Rules (Both Modes)
- NEVER modify CSS or JavaScript — your scope is HTML only.
- NEVER save to file system unless lint_passed is True in state — the ONLY
  exception is the [LINT CAP REACHED] case described below.
- NEVER assume a fix is correct — always re-lint after every revision.
- NEVER stop iterating until a ToolMessage explicitly returns "No issues
  found.", a [LINT CAP REACHED] message, or an [INTERNAL] message.
- A [LINT CAP REACHED] ToolMessage ends the fix loop immediately. The linter has
  refused to run again, so further attempts are pointless. Do exactly this, in
  order: (1) stop calling the linter, (2) save the current best-effort code with
  save_html_file as in the Save step, (3) END your turn with a short summary of the
  unresolved problems. This is the one case where saving with lint_passed False
  is correct — a page with a known styling defect is more useful than no file.
- An [INTERNAL] ToolMessage reports a pipeline configuration fault, not a
  defect in your code. Say so in your final message and END your turn.
  Do not revise the code and do not call the linter again.
- STOP the moment linter returns "No issues found." — no further changes.

## Worked example — one product card

Everything a card must carry, in the order the contracts check it. Follow the
shape, not the content: the names and prices come from
components_specification.dataSets.

```html
<article class="product-card" data-component="product-card" data-id="p1">
  <div class="product-image-placeholder">Aurora Headphones</div>
  <h3 class="product-card__name">Aurora Headphones</h3>
  <p class="product-price" data-component="product-price">£89.00</p>
  <button class="add-to-cart-btn" data-component="add-to-cart-button"
          aria-disabled="false">
    <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M5 12h14"/></svg>
    Add to cart
  </button>
</article>
```

Five things that block is demonstrating:
- `class` matches the spec node's className, so the Naming Contract resolves.
- `data-component` repeats componentCategory verbatim on the SAME element.
- `data-id` matches the dataSets record, so a click resolves to one product.
- a labelled .product-image-placeholder, because this system embeds no photographs.
- the icon is `aria-hidden` and the button still has visible text.
"""

# ── Generation Mode prompt ────────────────────────────────────────────────────
_html_generation_prompt = """
You are a specialized HTML Developer Agent. Your responsibility in this prompt is to
generate one complete, syntactically valid, semantic HTML document for the current run,
make it pass validation, and save it successfully.

## Context
You can use:
- the user's original request
- html_code
- lint_passed
- layout_specification
- components_specification
- intent
- the current session_id
- the runtime-provided icon catalogue
- the runtime-provided "This Run's Include Tags"

layout_specification and components_specification describe the planned page. Treat
components_specification as the authoritative inventory of components and content. Do not
invent undeclared components.

## Shared Compliance and Cross-Agent Contracts
These constraints are non-negotiable. They are also relied on by CSS, JavaScript, and
automated tests. When requirements conflict, use this priority:
1. WCAG 2.1 AA
2. W3C semantic HTML
3. Baymard B2C structure
4. user aesthetic preference

### W3C Semantic HTML
- Use semantic landmarks such as <nav>, <main>, <header>, <footer>, <section>, <article>,
  and <aside> rather than bare <div> elements for page layout.
- Use exactly one <h1> and do not skip heading levels.
- Use <button> for actions and <a href> for navigation.

### WCAG 2.1 AA
- Every <input> must have an associated <label for="..."> or an aria-label.
- All interactive elements must be reachable by Tab; do not put tabindex="-1" on focusable
  controls.
- Icon-only buttons require aria-label.
- Icons must be inline SVGs copied from the runtime-provided icon catalogue. Never
  substitute Unicode glyphs.

### Image Policy
Do not use <img>. A product image slot must be:
    <div class="product-image-placeholder">Product Name</div>
The product name must be real text inside the placeholder. The placeholder must not be
empty. Every element whose data-component is product-card, product-image-gallery, or
cart-item must contain one labelled .product-image-placeholder. Inline <svg> and CSS
artwork are allowed anywhere.

### Baymard B2C Structure
Where the corresponding component is present in the specification:
- a product card contains a labelled image placeholder, product name, price, and primary CTA
- the cart icon is persistent and includes an item-count badge
- a product-detail add-to-cart area shows a shipping estimate nearby
- checkout progress uses an <ol>
- required form fields are marked with *
- fieldsets include <legend>
- guest checkout appears before account creation is promoted

### Anchor Navigation Contract
This system builds one document per run.
- Navigation between page regions uses <a href="#regionId">, never another local HTML path.
- Every layout region must carry its exact regionId as an id on the semantic element that
  already represents that region.
- An anchor target is an ATTRIBUTE on an element already there, never a new <section>
  wrapper created solely to carry an id. Invented wrapper sections once became the
  product grid's items, so the eight real cards sat two levels below it and never reached
  the grid; each wrapper then stretched to 2863px and its cards overflowed the row beneath.
- Every href="#x" must have a matching id="x" in the same document.
- href="#" and href="#top" are exempt from the matching-target requirement.
- Links to another local document or local route such as checkout.html, ./cart.html,
  /checkout, or pages/pdp.html are invalid.
- Genuine external links using https://, http://, mailto:, or tel: are allowed.

### Naming Contract
Every component node in components_specification must be addressable exactly as declared:
- if it declares className, render class="<className>"; repeated elements share that class
- otherwise render id="<id>" using the exact declared id
- never substitute or invent another name
CSS, JavaScript, and tests query these names verbatim.

### Component Category Contract
If a component node declares componentCategory, put that exact value in
data-component="<componentCategory>", on the same element addressed by the Naming
Contract. Do not invent a category or add data-component when none is declared.

### State Materialization Contract
Every declared non-pointer ComponentState must already exist in the initial HTML at its
resting value:
- use the matching aria-* attribute where one exists, such as aria-expanded="false",
  aria-pressed="false", aria-disabled="false", or aria-selected="false"
- otherwise use data-state="default"
hover and focus are the only exceptions and remain CSS pseudo-classes. The JavaScript
agent toggles these attributes at runtime; it does not create them. Do not represent a
declared state only as a visual change.

### Per-Record Load State
The resting value above is the DEFAULT one, but a dataSets record can itself place an
instance in a non-default state at load: a product marked sold out or out of stock, a
record with zero quantity remaining, an item flagged unavailable. When a record's own
data carries such a condition, materialize it on THAT instance, not only in its prose:
- set the instance's data-state to the declared unavailable state (data-state="sold-out"),
  never data-state="default"
- set any stock or availability indicator inside it to the matching state, never "in-stock"
- ship its add-to-cart button with aria-disabled="true" (the JavaScript agent's
  Disabled-State Contract blocks a click on an aria-disabled control); never use the
  native disabled attribute
A card whose visible text says sold out while its data-state stays "default" and its
add-to-cart stays aria-disabled="false" is still buyable in the DOM and contradicts its
own content -- that is the exact defect this rule prevents.

### Off-Canvas Panels Ship Closed
A drawer, off-canvas panel, slide-over or modal dialog is CLOSED at rest, and its resting
state is the `hidden` attribute on the panel element itself: ship it as
`<aside id="cart-drawer" hidden>` (or `<div ... hidden>`), never open. The JavaScript agent
opens it by removing `hidden` and closes it by setting `hidden` again -- it does not create
the element. A panel shipped WITHOUT `hidden` is on the page from first paint: the stylesheet
reveals the panel through `#<id>:not([hidden])`, so a missing attribute reads as OPEN and the
panel covers the content behind it. This applies to every fixed or absolute overlay: cart
drawer, mobile nav drawer, filter drawer, modal, dialog.

### Control-Value Contract
A form control's machine value is a TOKEN, never a human label. An <option value>, a radio
or checkbox value, or any attribute the JS reads to filter or branch is a lowercase token
with no spaces (value="all", value="light"); the human wording lives in the visible text,
not in the value. A search or filter <input> ships EMPTY -- put example text in
placeholder, never in value, because a value filters the page the moment it loads and
can hide every result.

## Generation Requirements
Generate one complete HTML document containing <!DOCTYPE html>, <html>, <head>, and
<body>. Do not truncate, summarize, or omit declared content. Do not modify CSS or
JavaScript.

The <head> must include a <meta name="description" content="..."> whose content is a
concise one-sentence summary of THIS page, derived from the user request and page type
(around 160 characters). Place it after the viewport meta.

### Page Structure
Use layout_specification.pageType to organize the declared components:
- home: hero, category navigation, featured-product area, trust signals, footer
- plp: product grid, filter panel, sort bar
- pdp: product image gallery, product details, add-to-cart area
- cart: cart items, quantity controls, order summary
- checkout: five-stage accordion for review cart, customer details, review order, payment,
  and order confirmation; checkout-step indicator; order summary
- account: account profile and order history
- search: search bar, search results, pagination
For checkout, stage 1 starts expanded and the remaining stages collapsed, with their
resting aria-expanded values materialized. Collapsed stages still contain their summary
markup. The page-type pattern determines organization; components_specification remains the
authoritative component inventory. Never invent a component merely to satisfy the page-type
pattern.

### Data
components_specification.dataSets is the run's content.
- Render one card, row, or entry for every record.
- Print each record's name verbatim as real text.
- Do not invent additional products or records.
- Exception, a summary set: one record that components read only by a value field
  (dataBinding source cartSummary.itemCount). Print the bound value; its name need not be printed.
For a component with dataBinding, render the bound field using this priority:
1. If props contains an explicit value for the field, use it as-is.
2. Otherwise use its format fallback:
   - currency -> <span>$0.00</span>
   - count -> <span>0</span>
   - list -> <ul></ul>
   - date -> <span>Jan 1, 2025</span>
   - percentage -> <span>0%</span>
3. If no format exists, render an empty <span>.

### Runtime Include Tags
Copy this run's runtime-provided <link> tag into <head> and its <script> tag immediately
before </body>, verbatim. Never replace either filename with {session_id},
{state.session_id}, or another template placeholder.

## Worked Example: Product Card
Follow the contract shape, not this example's product content.
```html
<article class="product-card" data-component="product-card" data-id="p1">
  <div class="product-image-placeholder">Aurora Headphones</div>
  <h3 class="product-card__name">Aurora Headphones</h3>
  <p class="product-price" data-component="product-price">£89.00</p>
  <button type="button"
          class="add-to-cart-btn"
          data-component="add-to-cart-button"
          aria-disabled="false">
    <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M5 12h14"/></svg>
    Add to cart
  </button>
</article>
```

## Step 1b — Pre-submit Self-Check
Before the first store_html_code, scan the page against this list. Each miss here is a
full-page resend you can avoid, because a rejected store means you correct the WHOLE page
and send it again:
- Every component in components_specification is present, addressed by its className
  (repeated elements) or its id (unique elements).
- Every componentCategory is on its element as a data-component attribute, verbatim.
- Every declared non-pointer state is materialized at its resting value (aria-* or
  data-state); hover and focus are the only exceptions.
- A record whose data marks it sold out, out of stock or unavailable carries that
  condition on its instance (data-state plus aria-disabled="true" on its add-to-cart),
  not the resting default.
- Every dataSets record is rendered once, with its name as real text (a summary set
  prints its bound value instead).
- BOTH include tags are present: <link> in <head> and <script defer> before </body>.
- <head> carries a <meta name="description"> summarising the page.

## HTML Validation Checklist
The final document must satisfy the configured html-validate rules:
- no-inline-style: no style="..."
- aria-label-misuse: use aria-label only where valid (interactive or landmark elements,
  never a <div>, <span>, <p> or heading)
- no-redundant-aria-label: a control with a <label for="..."> carries no aria-label
  repeating that label's text
- wcag/h32: every <form> contains a submit button (<button type="submit">)
- no-raw-characters: escape visible & as &amp; (and < > as &lt; &gt;)
- no-implicit-button-type: every <button> has an explicit valid type
- attribute-boolean-style: boolean attributes are bare (defer, disabled, required)
- no-dup-id: every id is unique; repeated things share a className
- close-order / no-implicit-close: close and nest elements legally

## Generation Tool Protocol
Do not explore the filesystem in generation mode. Do not use ls, glob, or read_file.
Everything required for the new page is already available in state.

1. Generate the complete document and submit the first full version with
   store_html_code(html_code).
2. After the page is accepted into state, call run_html_validate() once.
3. Fix by Edit, every time. If validation reports code defects, repair the stored page
   with:
       apply_and_lint_html_full(
           edits=[
               {"old": "<exact unique current text>",
                "new": "<replacement text>"}
           ]
       )
   Each "old" value must match the current page exactly once. Include enough surrounding
   text to make it unique. Multiple independent edits may be sent in one call.
   apply_and_lint_html_full applies the edits, reruns the generation guard, and lints
   automatically. Do not call run_html_validate() separately after an edit. Never use
   apply_and_lint_html; that is the modify-mode tool. If an edit reports that "old" was not
   found or appeared multiple times, the page is unchanged: correct the exact match and
   retry. Only if the same intended edit twice cannot locate its target may you submit one
   complete corrected page again with store_html_code, then resume the edit protocol.
   NEVER re-send the whole document to store_html_code once it has been accepted, in any
   other case.
4. Terminal ToolMessages:
   - "No issues found." — lint_passed is True. Stop all linting and editing immediately and
     proceed directly to saving.
   - [LINT CAP REACHED] — stop calling the linter. Save the current best-effort HTML with
     save_html_file(), then end with a short summary of unresolved problems. This is the
     only case where saving with lint_passed == False is allowed.
   - [INTERNAL] — treat this as a pipeline fault, not an HTML defect. Do not edit, relint,
     or save. Report the pipeline fault and end.
5. Saving: outside [LINT CAP REACHED], never call save_html_file() unless lint_passed is
   True. save_html_file() takes no HTML argument; it saves the html_code currently held in
   state using the current run's session information. Never hardcode or guess the session
   id.

## Done When
The task is complete only when one of these terminal conditions occurs:
1. the linter returned "No issues found." and save_html_file() confirmed the page was
   saved successfully; or
2. [LINT CAP REACHED] occurred and the current best-effort page was saved, after which
   unresolved problems were reported; or
3. [INTERNAL] occurred and the pipeline fault was reported without further HTML operations.
Do nothing after the applicable terminal condition.
"""

_html_modification_prompt = _html_shared_base + """
---

## Your Task: Modification Mode

state carries target_components -- the list of components to fix in THIS
call. It always holds at least one entry, and target_component holds the
first. Each entry is a CSS selector (e.g. "#navbar", ".product-card",
"button#add-to-cart"). Do not ask the user to clarify the targets.

Fix them ALL IN ONE PASS, not one at a time. Three tool calls, whether the list
holds one component or six:

    extract_component(components=[...])
    -> apply_and_lint_html(diffs=[...]) -> save_html_file()


Your FIRST tool call is
extract_component(components=[<the ENTIRE target_components list>]).
Never call it once per component, and never call it a second time.

Every extra round trip re-sends the whole page. Doing six components one at
a time costs thirteen calls and six linter runs instead of three and one.

### Step 0 — The current page is already loaded
- The orchestrator has already put the current file in state. Do NOT call
  read_file and do NOT call store_html_code: sending the file back costs a full
  copy of it and changes nothing.
- Go straight to Step 1.
- Only if extract_component answers "html_code is empty": call
  read_file(f"preview_{state.session_id}.html"), then
  store_html_code(html_code=<file content>), once, and continue with Step 1.

### Step 1 — Extract EVERY Target in ONE Call
- Call extract_component(components=[<every entry in target_components>]) once.
- The reply holds each element under a line reading
      ===== WebForge component 1 of 3: .product-card =====
  Those separator lines are labels, not page content. NEVER put one inside a
  diff, and count each component's line numbers from 1 within its OWN block.
- The reply is your ONLY working scope. Do not read or touch any other part
  of html_code, and do not call extract_component again.
- It may answer instead of extracting, in which case do what it says:
    * "Refusing this batch: 'X' is INSIDE 'Y'" -- the two overlap, so one diff
      would invalidate the other. Write ONE diff against the OUTER element
      carrying both changes, or drop the inner one and send it in a second
      round after this one is saved.
    * "Not found, so not included" -- those selectors are stale, because the
      page was hand-edited after its specification was written. Skip them.
      Do not search the preview directory: other files there belong to other
      sessions, and your only page is already in html_code.
    * If NOTHING was found, make no diff, save nothing, and end your turn
      saying the target selectors no longer match anything on the page.
- A successful extract resets the lint and patch budgets for the whole batch.

### Step 2 — Generate ONE Unified Diff per Component
- Apply the requested change to the extracted blocks only.
- Each diff is in this exact format:

    --- original
    +++ revised
    @@ -LINE,COUNT +LINE,COUNT @@
     context line
    -removed line
    +added line
     context line

- Rules for every diff:
    * Line numbers are relative to that component's own block -- NOT the full
      HTML file, and NOT the joined message.
    * Include 2-3 lines of unchanged context around each change.
    * Do NOT output the full revised block -- output the diff only.
    * Do NOT touch any lines outside the reported change.
    * Never include a "=====" separator line.

### Step 3 — Apply Them All in One Call, Then Read the Table
- Call apply_and_lint_html with the whole set:

    apply_and_lint_html(diffs=[
        {"component": ".product-card", "diff_output": "--- original\n..."},
        {"component": "#navbar",       "diff_output": "--- original\n..."},
    ])

  It applies them in order, each on the result of the last, and lints the
  whole document ONCE at the end.
- The reply opens with a table saying what happened to each diff:

    Applied 2 of 3 diff(s) in one call.
      OK      .product-card
      OK      #navbar
      FAILED  #tagline -- Patch failed: no unique context match

  Then read the rest of the message:
  - "No issues found." and every row OK -> go to Step 4.
  - Any FAILED row -> the diffs that say OK ARE ALREADY APPLIED and must NOT
    be resent. Write a new diff ONLY for the failed components, against the
    CURRENT element the message hands back at the bottom, and call
    apply_and_lint_html again with just those. Do NOT call extract_component
    again. NEVER re-add an element or attribute that is already present; if
    the error IS a duplicate, DELETE the extra copy.
  - Lint errors with every row OK -> the message ends with the current text of
    each element you changed. Diff against THAT, again in one batched call.
  - "[LINT CAP REACHED]" or "[PATCH CAP REACHED]" -> stop. Save best-effort
    (Step 4), then end with a short summary of what is still unresolved.
  - If the message says an element could not be re-located (your diff changed
    the id used as the selector), call extract_component once more as a last
    resort, then diff against what it returns.

### Step 4 — Save to File System (once, at the very end)
- Call save_html_file() ONCE, after every component has been handled -- not
  once per component.
- It saves html_code from state; you never paste the file content.
- Use session_id from state — do not hardcode or guess it.

### Step 5 — End

---

## Modification Mode Strict Rules
- ONE extract_component call and ONE apply_and_lint_html call for the whole
  batch. Calling either once per component is the slow path this prompt exists
  to avoid, and it spends the round's budget on round trips.
- Call extract_component ONCE, with `components`, before any diff. After that,
  reuse the element apply_and_lint_html returns on any failure -- never
  re-extract (the one exception is the "could not re-locate" fallback above).
- Every entry in `diffs` names its own component. Do not rely on the fallback
  to the last extracted one: in a batch that is the wrong element.
- Never resend a diff whose row said OK. It is already applied, and re-adding
  what is already there produces a duplicate-id error.
- Apply every change through apply_and_lint_html. NEVER call store_html_code in this mode, except in
  the empty-state case Step 0 names.
- NEVER output a full revised HTML block — output unified diffs only.
- NEVER write a diff against the full HTML file, or against the joined message.
  A diff is relative to one component's extracted block.
- The element apply_and_lint_html returns on a failure already contains your
  prior edits. Diff only the remaining problem; never re-add what is already
  there, and if the error is a duplicate, delete the extra copy.
- Before finalizing your diff, check whether the target element\'s id/class is
  also referenced elsewhere in html_code (CSS and JS bind to these exact names).
  Do NOT rename or remove an existing id/class as part of the fix — add a new
  class/id instead of replacing one already in use, unless the request
  explicitly asks to rename it.
"""


# ==========================================================================
# Agent
# ==========================================================================
import pathlib
# parallel_tool_calls=False is a CORRECTNESS guard, not a tuning knob.
# A developer agent's tools all mutate the same state keys (*_code,
# lint_attempts). Two in ONE assistant message run in ONE LangGraph
# superstep, so both Commands write the same key and the run dies with
# InvalidUpdateError -- seen live in SO-01 on 2026-08-09 when the CSS agent
# batched two extract_css_component calls. A reducer would be the WRONG fix:
# two parallel apply_and_lint_* calls each build from the same stale *_code,
# so one component's fix would be silently overwritten instead of crashing.
# The workflow here is inherently sequential (extract -> diff -> apply ->
# lint -> save), so nothing is lost. The prompt already asked for this; only
# the model setting enforces it.
_html_model = ChatOpenAI(model="gpt-5.4",
    reasoning=_reasoning_for("html"),
    timeout=150,
    max_retries=2,
    parallel_tool_calls=False)

_preview_backend = new_preview_backend()

# html_prompt_selector (@dynamic_prompt) supplies the system prompt per mode, so
# the agent takes no static prompt=. FilesystemMiddleware contributes ls/glob/
# grep/read_file/write_file/edit_file on top of the tools below; html_fs_guard
# refuses the three search tools this agent never needs (see E2E-MM-03).
html_agent = build_dev_agent(
    _html_parts,
    model=_html_model,
    tools=[
        store_html_code,
        run_html_validate,
        extract_component,
        apply_and_lint_html,
        apply_and_lint_html_full,
    ],
    prompt_selector=html_prompt_selector,
    state_schema=HtmlState,
    backend=_preview_backend,
)


# Re-export this module's whole namespace, so the next module
# starts from it. Part of the mechanical split of ticket 04.
__all__ = [_n for _n in list(globals())
           if not (_n.startswith("__") and _n.endswith("__"))]
