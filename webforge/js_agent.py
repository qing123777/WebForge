"""js_agent: the JavaScript developer agent: JsState, eslint, its tools, prompts and agent.

Lines 7950-9753 of the flat fyp.py at commit 6e8c14b, moved
verbatim by refactor ticket 04 (tools/split_fyp.py).
"""
from __future__ import annotations

from webforge.html_agent import *  # noqa: F401,F403

# ==========================================================================
# state
# ==========================================================================
from typing import Literal

class JsState(AgentState):
    js_specification: str
    js_code:          str = ""
    lint_passed:      bool = False
    lint_attempts:       int = 0
    lint_escalated:      bool = False
    patch_attempts:       int = 0
    session_id:       str
    intent:           Literal["generate", "modify"] = "generate"
    target_component: str = ""
    target_components: list = []
    target_instance:  int = 1
    interaction_specification: dict = {}
    # DOM Ownership Contract (2026-08-31). Its own counter rather than
    # a shared one: this refusal and a lint failure are different
    # problems and must not spend each other's budget.
    dom_attempts:     int = 0
    components_specification: dict = {}


# ==========================================================================
# run_eslint
# ==========================================================================
@tool
def run_eslint(runtime: ToolRuntime[JsState]) -> Command:
    """
    Lint the current js_code in state using ESLint (flat config:
    eslint.config.fyp.mjs in the repo root — declares browser globals).
    Reads js_code from state — call store_js_code first.
    lint_passed gates on ERRORS only (severity 2 / fatal); warnings are
    reported as advisory so cosmetic issues cannot trap the fix loop.
    """
    return _lint_js_source(runtime.state.get("js_code", ""), runtime)


def _lint_js_source(js_code: str, runtime) -> Command:
    """
    Lint a JavaScript SOURCE STRING and return the same Command run_eslint has
    always returned. Factored out of run_eslint so apply_and_lint_js can lint the
    code it JUST patched, in the same tool call, without a second run_eslint
    round-trip. run_eslint is now a thin wrapper that lints state's js_code.
    Behaviour is unchanged: escalation refusal, empty guard, error/warning
    formatting, and cap counting via _lint_failure. The refusal, the empty guard
    and the temp file are the engine's (webforge.dev_agent.lint_source, ticket
    09); _eslint_check is what ESLint adds.
    """
    return lint_source(JS, js_code, runtime, _eslint_check)


def _eslint_check(tmp_path: str, runtime) -> Command:
    """Run ESLint on the temp file and turn its JSON report into the verdict."""
    result = _run_lint_subprocess(
        f'npx --no-install eslint --format json --config eslint.config.fyp.mjs "{tmp_path}"')
    if "npx" in result.stderr.lower() and result.returncode != 0 and not result.stdout.strip():
        return Command(update={
            "lint_passed": False,
            "messages": [ToolMessage(
                content=(
                    "ESLint could not be executed because `npx` was not found. "
                    "Install Node.js and run `npm install` in this repo."
                ),
                tool_call_id=runtime.tool_call_id
            )]
        })
    try:
        results = _json.loads(result.stdout)
        msgs    = results[0].get("messages", []) if results else []
    except (ValueError, IndexError, KeyError):
        return Command(update={
            "lint_passed": False,
            "messages": [ToolMessage(
                content=("ESLint produced unparseable output:\n"
                         + (result.stdout or result.stderr)[:800]),
                tool_call_id=runtime.tool_call_id
            )]
        })
    errors   = [m for m in msgs if m.get("severity") == 2 or m.get("fatal")]
    warnings = [m for m in msgs if m.get("severity") == 1 and not m.get("fatal")]

    def _fmt(m):
        return (f"  Line {m.get('line','?')}, Col {m.get('column','?')} "
                f"[{m.get('ruleId') or 'fatal'}]: {m.get('message','')}")

    if not errors:
        content = "No issues found."
        if warnings:
            content = ("No blocking issues found. Advisory warnings "
                       "(no fix required):\n"
                       + "\n".join(_fmt(m) for m in warnings))
        return Command(update={
            "lint_passed": True,
            "messages": [ToolMessage(content=content,
                                     tool_call_id=runtime.tool_call_id)]
        })
    lines = [f"Found {len(errors)} error(s):"] + [_fmt(m) for m in errors]
    if warnings:
        lines += [f"Also {len(warnings)} advisory warning(s):"]
        lines += [_fmt(m) for m in warnings]
    return _lint_failure(runtime, "\n".join(lines))


# ==========================================================================
# store_js_code
# ==========================================================================
import re

# Disabled-State Contract: a disabled state is aria-disabled, never the native
# property. WRITES only -- a read such as `if (el.disabled)` is harmless once
# nothing sets it, and flagging reads would send the model chasing a non-defect.
_NATIVE_DISABLED_PATTERNS = (
    (re.compile(r"\.disabled\s*=(?!=)"),
     "assignment to the native `.disabled` property"),
    (re.compile(r"(?:set|remove|toggle)Attribute\(\s*['\"]disabled['\"]"),
     "set/remove/toggleAttribute for the native 'disabled' attribute"),
)


def _native_disabled_writes(js_code: str) -> list:
    """Return one message per kind of native-disabled write found in the code."""
    found = []
    for pattern, label in _NATIVE_DISABLED_PATTERNS:
        hits = len(pattern.findall(js_code))
        if hits:
            found.append(f"{hits} x {label}")
    return found


# No-image contract on the JS side (2026-08-30). The HTML agent is forbidden to
# emit <img>, but the JS agent can build one at runtime -- createElement("img"),
# an innerHTML "<img ...>" template, or new Image() -- and inject it into the
# page. That is exactly how fabricated product photos reached PO-08 (po0113ce72)
# and clobbered the HTML agent's placeholder cards. The system embeds no images,
# so generated JS must create none either.
_JS_IMAGE_PATTERNS = (
    (re.compile(r"createElement\(\s*['\"]img['\"]", re.IGNORECASE),
     "createElement('img')"),
    (re.compile(r"<img\b", re.IGNORECASE),
     "an '<img' tag in a string or template"),
    (re.compile(r"\bnew\s+Image\s*\("),
     "new Image()"),
)


def _js_image_creation(js_code: str) -> list:
    """Return one message per kind of <img> creation found in the code."""
    found = []
    for pattern, label in _JS_IMAGE_PATTERNS:
        hits = len(pattern.findall(js_code))
        if hits:
            found.append(f"{hits} x {label}")
    return found


# DOM Ownership Contract (2026-08-31). The HTML agent renders the page; the JS
# agent gives it behaviour. A class name the script INVENTS is a component the
# other two agents know nothing about: the CSS agent never styles it, so it
# renders unstyled, and the HTML agent has usually already shipped the same
# thing under its own name, so the page ends up with two of them.
#
# Only ASSIGNMENTS count, never queries. Querying a class the script creates is
# ordinary JavaScript and refusing it would be a wall; creating a class nobody
# else has ever heard of is the defect.
_JS_CLASS_ASSIGN = re.compile(
    r"""(?:\.className\s*=\s*|classList\.add\(\s*)['"]([^'"]+)['"]""")
_HTML_CLASS_ATTR = re.compile(r"""class\s*=\s*['"]([^'"]*)['"]""")

_JS_DOM_ATTEMPT_CAP = 2


def _html_class_names(html: str) -> set:
    """Every class name the generated page actually carries."""
    out = set()
    for group in _HTML_CLASS_ATTR.findall(html or ""):
        out.update(group.split())
    return out


def _spec_class_names(components_spec) -> set:
    """Every className the component specification declares, at any depth.

    A name that is in the spec but not yet in the markup is not an invention --
    it is a component the HTML agent owes. Allowing it keeps this a guard on the
    JS agent rather than a way for one agent's omission to block another.
    """
    out = set()

    def walk(node):
        if isinstance(node, dict):
            cn = node.get("className")
            if isinstance(cn, str) and cn.strip():
                out.update(cn.split())
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)

    walk(_coerce_spec(components_spec or {}) or {})
    return out


def _js_invented_classes(js_code: str, html: str, components_spec=None,
                         limit: int = 10) -> list:
    """Class names the script creates that exist neither on the page nor in the
    component specification.

    Fails OPEN with no page to compare against, the same way the CSS drift
    guard does: a missing file is a pipeline problem, not a defect in the code
    being checked, and refusing on it would deadlock the run.

    Measured over the 53 preview pairs on disk: 46 runs score 0, 7 score at
    least one, and PO-08 po01e9a8b4 -- the run whose cart never worked -- scores
    19. There is no threshold; the rule is zero.
    """
    if not js_code or not html:
        return []
    known = _html_class_names(html) | _spec_class_names(components_spec)
    seen, out = set(), []
    for group in _JS_CLASS_ASSIGN.findall(js_code):
        for name in group.split():
            if name in seen or name in known:
                continue
            seen.add(name)
            out.append(name)
    return sorted(out)[:limit]


@tool
def store_js_code(js_code: str, runtime: ToolRuntime[JsState]) -> Command:
    """
    Store the generated or revised JavaScript code into agent state.
    Must be called every time after generating or revising JavaScript,
    before calling run_js_validate.

    On Generation Mode calls (intent="generate"), enforces two checks:
      1. Disabled-State Contract — the code must not write the native disabled
         property or attribute. aria-disabled is the only disabled state, because
         the native one removes the control from the tab order, from the
         accessibility tree, and from the test pipeline's reach.
      2. Coverage — every interaction trigger/action target in
         interaction_specification must be referenced in the JS by its resolved
         selector value (className if the component has one, else its id — per
         the Naming Contract, resolved via components_specification).
    Modification Mode is exempt from both, for the same reason store_html_code
    is: modify mode edits the file already on disk, and rejecting
    that file over code it already contained would deadlock the correction loop.
    """
    intent = runtime.state.get("intent", "generate")

    if intent == "generate":
        # ── DOM Ownership Contract ───────────────────────────────────────
        # Runs before the others because it is the one that decides whether
        # this script is a behaviour layer at all. On PO-08 po01e9a8b4 the
        # script rebuilt the cart, the card actions and the card meta under
        # 20 invented names; the rebuild was skipped at runtime because its
        # own "already built?" probe found the HTML agent's heading, so the
        # cart could never render a single line item.
        _invented = _js_invented_classes(
            js_code,
            _read_preview_source(runtime.state.get("session_id", ""), "html"),
            runtime.state.get("components_specification"))
        _dom_n = runtime.state.get("dom_attempts", 0)
        if _invented and _dom_n < _JS_DOM_ATTEMPT_CAP:
            _real = sorted(_html_class_names(_read_preview_source(
                runtime.state.get("session_id", ""), "html")))
            return Command(update={
                "dom_attempts": _dom_n + 1,
                "messages": [ToolMessage(
                    content=(
                        f"DOM Ownership Contract - your script CREATES element(s) "
                        f"carrying class name(s) that exist neither on the page "
                        f"nor in the component specification: {_invented}.\n\n"
                        f"The HTML agent renders the page; your job is behaviour "
                        f"on the markup it already shipped. An invented class is "
                        f"a component nobody else knows: the CSS agent never "
                        f"writes a rule for it, so it renders unstyled, and the "
                        f"page usually already contains the same thing under its "
                        f"real name, so the visitor sees two of them.\n\n"
                        f"The class names actually on the page are: {_real}\n\n"
                        f"Read preview_{runtime.state.get('session_id', '')}.html, "
                        f"find the element you meant, and query it by the name it "
                        f"already has instead of building a replacement. Create an "
                        f"element only for a repeated DATA ROW inside a container "
                        f"the page already ships (a cart line item), and give that "
                        f"row a class the page or the specification already names.\n\n"
                        f"This is not style advice. On run po01e9a8b4 the script "
                        f"guarded its rebuild with "
                        f"`if (!region.querySelector('#cart-heading'))`, the HTML "
                        f"had already shipped that heading, so the block never "
                        f"ran, `.cart-item-list` was never created, and renderCart "
                        f"returned on its first line for the life of the page. The "
                        f"cart was dead, eslint was clean and every generated "
                        f"assertion passed. "
                        f"(attempt {_dom_n + 1} of {_JS_DOM_ATTEMPT_CAP})"),
                    tool_call_id=runtime.tool_call_id)]})

        bad_images = _js_image_creation(js_code)
        if bad_images:
            return Command(update={"messages": [ToolMessage(
                content=(
                    f"Image contract violation(s): {bad_images}. This system "
                    f"embeds no images, so the JavaScript must not create an "
                    f"<img> element (createElement('img'), an '<img>' "
                    f"template, or new Image()). Render a product image slot "
                    f"the same way the HTML does: a labelled "
                    f"<div class=\"product-image-placeholder\">Product Name"
                    f"</div> built from the record's name. A remote photo URL "
                    f"only renders blank for a real visitor. Remove the image "
                    f"element and call store_js_code again."
                ),
                tool_call_id=runtime.tool_call_id
            )]})

        native_disabled = _native_disabled_writes(js_code)
        if native_disabled:
            return Command(update={"messages": [ToolMessage(
                content=(
                    f"Disabled-State Contract violation(s): {native_disabled}. "
                    f"Express a disabled state with aria-disabled only - "
                    f"setAttribute('aria-disabled', 'true'|'false') - and stop the "
                    f"behaviour by returning early from the handler while "
                    f"getAttribute('aria-disabled') === 'true'. The native property "
                    f"takes the control out of the tab order, out of the "
                    f"accessibility tree, and out of the test pipeline's reach, so "
                    f"a later test case fails for a reason unrelated to your code. "
                    f"Fix this and call store_js_code again."
                ),
                tool_call_id=runtime.tool_call_id
            )]})

        interaction_spec = _coerce_spec(
            runtime.state.get("interaction_specification") or {})
        components_spec  = _coerce_spec(
            runtime.state.get("components_specification") or {})
        if interaction_spec is None or components_spec is None:
            return Command(update={"messages": [ToolMessage(
                content=(
                    "[INTERNAL] a specification is a string that is not valid "
                    "JSON, so the coverage check cannot run. This is a pipeline "
                    "configuration error, not a defect in your JavaScript. "
                    "Report it in your final message and stop."
                ),
                tool_call_id=runtime.tool_call_id
            )]})
        target_ids = set()
        rewrites_data = False
        for page in (interaction_spec.get("pages") or []):
            for flow in (page.get("flows") or []):
                trig = flow.get("trigger") or {}
                if trig.get("targetId"):
                    target_ids.add(trig["targetId"])
                for act in (flow.get("actions") or []):
                    if act.get("targetId"):
                        target_ids.add(act["targetId"])
                    # Only a flow that REWRITES content needs the records in the
                    # script. A page that merely displays them is fully served by
                    # the markup, and demanding a duplicate array there would be
                    # dead weight the linter would then flag as unused.
                    if act.get("type") in ("updateData", "applyFilter", "addToCart",
                                           "submitOrder"):
                        rewrites_data = True

        if rewrites_data:
            records = _dataset_records(components_spec)
            absent = [f"{key}:'{name}'" for key, rid, name in records
                      if rid not in js_code and name not in js_code]
            if absent:
                return Command(update={"messages": [ToolMessage(
                    content=(
                        f"Shared Data Contract violation(s): {absent}. An "
                        f"interaction in this run rewrites content (updateData, "
                        f"applyFilter or addToCart), so the script needs the same "
                        f"records the page was rendered from. They live in "
                        f"components_specification.dataSets. Declare that list as "
                        f"a const array at the top of the file, keeping each "
                        f"record's id and name verbatim, and read from it instead "
                        f"of inventing your own products. Without the shared list "
                        f"a click on a card cannot resolve to a record, so the "
                        f"detail section can only ever show one fixed product. "
                        f"Fix and call store_js_code again."
                    ),
                    tool_call_id=runtime.tool_call_id
                )]})

        if target_ids:
            # Reuse the HTML agent's identity walk (cell runs earlier in the
            # notebook) rather than duplicating the recursive walk a third time.
            identity_map = dict(_spec_component_identities(components_spec))
            missing = []
            for tid in sorted(target_ids):
                cname = identity_map.get(tid)
                selector_value = cname if cname else tid
                if selector_value not in js_code:
                    missing.append(tid)
            if missing:
                return Command(update={"messages": [ToolMessage(
                    content=(
                        f"Coverage check failed — interaction_specification target "
                        f"component(s) never referenced in the generated JS: {missing}. "
                        f"Wire up their triggers/actions (per the Naming Contract "
                        f"selector) and call store_js_code again."
                    ),
                    tool_call_id=runtime.tool_call_id
                )]})

    return Command(update={
        "js_code": js_code,
        "messages": [ToolMessage(
            content="JavaScript code saved to state.",
            tool_call_id=runtime.tool_call_id
        )]
    })


# ==========================================================================
# store_js_code
# ==========================================================================
import pathlib as _pathlib_seed
import hashlib as _hashlib_seed

# ── Deterministic modification-mode seed (disk -> state) ─────────────────
# In modification mode a developer agent edits an existing preview file. Its
# extract/diff tools read that file from the *_code state field, so disk must be
# copied INTO state before the agent runs. Leaving that to the model (Step 0
# read_file + store_*_code) is fragile: at reasoning effort "high" the JS agent
# skipped the store call, so js_code stayed "" and extract_js_component /
# store_js_diff both dead-ended on empty input (found live by E2E-JS-MM-01).
# Python guarantees the seed here instead -- the orchestrator already knows the
# session_id and the preview root, so no model call is involved. Same
# "LLMs decide, Python guarantees" split the save step already uses. The
# prompt's Step 0 read_file+store stays as a fallback for the "" case (a modify
# against a file that was never generated).
_PREVIEW_ROOT = _wf_config.PREVIEW_DIR

import re as _re_sid

# ── Session id: validated, never generated here ───────────────────────────────
# The id names preview_{session_id}.html/.css/.js, the Playwright screenshot,
# the preview_url and the registry entry, and the developer-agent prompts tell
# each agent to read "only your own preview_{session_id}" file. It is issued by
# the presentation layer (the Streamlit conversation's thread_id) and travels
# down as state. The multi-agent system validates it and never mints one, so an
# id-less call fails loudly instead of quietly writing a brand-new orphan page.
#
# The pattern is a FILENAME-SAFETY check, not a uniqueness check. Uniqueness is
# uuid4's job upstream. str(uuid.uuid4()) is 36 chars of hex and hyphens, so it
# always passes; the pattern is deliberately wider so an E2E harness can pass a
# readable id like "so01" while standing in for Streamlit. Without it, an id of
# "../../x" walks straight out of the preview root below -- the save tools go
# through OverwritingFilesystemBackend, which blocks traversal, but this read
# path joins the string directly.
_SESSION_ID_RE = _re_sid.compile(r"^[A-Za-z0-9_-]{1,64}$")


def _safe_session_id(session_id) -> str:
    """Return session_id unchanged when it is safe to put in a filename, else ""."""
    if not isinstance(session_id, str):
        return ""
    return session_id if _SESSION_ID_RE.match(session_id) else ""


# ── What did the sub-agent actually do to its file? ──────────────────────────
# The three call_*_agent tools used to return a HARDCODED "file saved to file
# system" ToolMessage whatever happened. In E2E-SO-01 the CSS agent reported "No
# changes were applied, so no file was saved" into the progress stream, while the
# ToolMessage -- the only channel the orchestrator reads -- claimed a save. The
# orchestrator then told the user it had updated the CSS. It had not.
#
# A file fingerprint answers this deterministically, with no state capture and no
# cooperation from the sub-agent, so a model that forgets to save cannot hide it.
# Reporting only: what to DO about an unchanged file stays the orchestrator's
# decision (a bad work order often succeeds when reworded, so a tool that marked
# the component unfixable would give up too early).


def _preview_fingerprint(session_id: str, ext: str):
    """(size, sha1) of preview_{session_id}.{ext}, or None if it is not there."""
    sid = _safe_session_id(session_id)
    if not sid:
        return None
    try:
        blob = (_PREVIEW_ROOT / f"preview_{sid}.{ext}").read_bytes()
    except OSError:
        return None
    return len(blob), _hashlib_seed.sha1(blob).hexdigest()


def _artifact_outcome(agent_label: str, ext: str, session_id: str,
                      before, after) -> str:
    """The ToolMessage body for a finished call_*_agent, stating the truth.

    `before` / `after` are _preview_fingerprint results taken either side of the
    sub-agent's stream. The unchanged wording is deliberately blunt: it is read
    by a model that is about to write a summary for the user.
    """
    name = f"preview_{_safe_session_id(session_id) or session_id}.{ext}"
    head = f"[Secondary Orchestrator] {agent_label} completed."
    if after is None:
        return (f"{head} {name} DOES NOT EXIST -- nothing was written. "
                f"Treat this request as NOT APPLIED. Read the agent's own reply "
                f"for the reason, and do NOT report it as fixed.")
    if before is None:
        return f"{head} {name} created ({after[0]} bytes)."
    if before[1] == after[1]:
        return (f"{head} {name} was NOT modified -- {after[0]} bytes, byte-for-byte "
                f"unchanged. Nothing was applied. Do NOT report this request as "
                f"fixed; read the agent's own reply for why it could not act.")
    return f"{head} {name} updated ({before[0]} -> {after[0]} bytes)."


def _read_preview_source(session_id: str, ext: str) -> str:
    """Return the contents of preview_{session_id}.{ext}, or "" if it is missing
    or unreadable. ext is "html" | "css" | "js". Never raises: a modify against a
    file that was never generated must degrade to the empty seed (the prompt's
    Step 0 fallback then applies), not crash the orchestrator."""
    session_id = _safe_session_id(session_id)
    if not session_id:
        return ""
    try:
        return (_PREVIEW_ROOT / f"preview_{session_id}.{ext}").read_text(
            encoding="utf-8")
    except OSError:
        return ""


# ==========================================================================
# extract_js_component
# ==========================================================================
def _js_resolve_component(js_code: str, component: str, components_spec=None):
    """Return (the alias that matched, its spans). The JS references a component
    by whatever selector string the HTML rendered -- '.add-to-cart-btn' -- while
    the work order names the specification id, so a literal search finds nothing.
    See _component_name_aliases. The search is the engine's
    (webforge.dev_agent.loop_resolve, ticket 09)."""
    return loop_resolve(JS_LOOP, js_code, component, components_spec)


def _js_selectors_present(js_code: str, limit: int = 12) -> list:
    """Quoted selector strings the script actually uses. Named in a not-found
    message so the model can correct itself rather than guess again."""
    out = []
    for m in re.finditer(r"""['\"]([#.][A-Za-z0-9_-]+)['\"]""", js_code or ""):
        if m.group(1) not in out:
            out.append(m.group(1))
    return out[:limit]


def _js_block_spans(js_code: str, component: str) -> list:
    """Return the (start, end) character span of every JS paragraph (blank-line
    section) referencing the target component.
    component may be a CSS selector (#id, .class) or a bare name; a leading
    # or . is stripped so the raw name is searched inside selector strings.
    Spans are used rather than plain text so that non-contiguous paragraphs can
    be spliced back into their own positions -- joining them and calling
    str.replace would find no match and silently leave js_code unchanged."""
    raw  = component.lstrip('#.')
    body = js_code.strip()
    if not body:
        return []
    lead = len(js_code) - len(js_code.lstrip())

    spans, pos = [], 0
    for m in re.finditer(r'\n{2,}', body):
        spans.append((pos, m.start()))
        pos = m.end()
    spans.append((pos, len(body)))

    return [(a + lead, b + lead) for a, b in spans if raw in body[a:b]]


def _js_blocks_for_component(js_code: str, component: str) -> list:
    """Return JS paragraphs (blank-line sections) referencing the target component.
    Thin wrapper over _js_block_spans, kept for callers that only need the text."""
    return [js_code[a:b] for a, b in _js_block_spans(js_code, component)]


@tool
def extract_js_component(runtime: ToolRuntime[JsState], component: str = "",
                         components: Optional[List[str]] = None) -> Command:
    """
    Extract EVERY JS code block for target_component from js_code in state --
    all paragraphs that reference the component's id or class name, not just the
    first. Multiple blocks come back as one document separated by
    '/* @@ WebForge block N of M @@ */' marker lines; diff against it as a whole.
    target_component may be a CSS selector (#id, .class) or a bare component name.
    Call this in Modification Mode before generating a diff.

    `components` extracts SEVERAL components in one call -- pass the whole
    target_components list and get every block back in one message, each
    under a "===== WebForge component n of m: <name> =====" line. Prefer
    it: five separate extracts are five re-sends of the whole script.
    """
    # The body is the engine's (webforge.dev_agent.loop_extract,
    # ticket 09); JS_LOOP below carries what JS differs by.
    return loop_extract(JS_LOOP, runtime, component, components)


# ==========================================================================
# store_js_diff
# ==========================================================================
def _apply_js_component_diff(js_code: str, component: str, diff_output: str,
                            components_spec=None) -> dict:
    """
    Apply a unified diff to EVERY js_code block for `component` and splice the
    results back. Pure function — no state, no ToolMessage — so both
    store_js_diff and apply_and_lint_js format their own responses from ONE
    source of truth. Returns one of:
      {"status": "empty"}                                        js_code was empty
      {"status": "noblock"}                                      no block matched component
      {"status": "diff_fault", "error": <str>}                   stale/malformed diff — regenerate
      {"status": "internal", "etype": <str>, "error": <str>}     wiring/env fault — regenerating won't help
      {"status": "ok", "new_js_code": <str>, "n_blocks": <int>}  applied cleanly
    """
    # The body is the engine's (webforge.dev_agent.loop_apply_diff, ticket 09).
    return loop_apply_diff(JS_LOOP, js_code, component, diff_output, components_spec)


@tool
def store_js_diff(diff_output: str, runtime: ToolRuntime[JsState]) -> Command:
    """
    Apply a unified diff to ALL JS blocks for target_component and splice the
    results back into js_code in state. The diff must be relative to the exact
    text returned by extract_js_component, including any
    '/* @@ WebForge block N of M @@ */' separator lines, which must be preserved
    as context. In Modification Mode apply every change through this tool, not store_js_code (which is only the one-time Step 0 seed the orchestrator now pre-loads).
    """
    component = runtime.state.get("target_component", "")
    js_code   = runtime.state.get("js_code", "")
    res = _apply_js_component_diff(
        js_code, component, diff_output,
        runtime.state.get("components_specification"))
    st  = res["status"]

    if st == "empty":
        return Command(update={"messages": [ToolMessage(
            content="js_code is empty. Cannot apply diff.",
            tool_call_id=runtime.tool_call_id)]})
    if st == "noblock":
        return Command(update={"messages": [ToolMessage(
            content=f"No JS block found for data-component='{component}'. "
                    "Re-extract and regenerate the diff.",
            tool_call_id=runtime.tool_call_id)]})
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

    n = res["n_blocks"]
    plural = "block" if n == 1 else "blocks"
    return Command(update={
        "js_code": res["new_js_code"],
        "messages": [ToolMessage(
            content=f"Diff applied. {n} JS {plural} for '{component}' updated.",
            tool_call_id=runtime.tool_call_id)]
    })


# ==========================================================================
# apply_and_lint_js
# ==========================================================================
@tool
def apply_and_lint_js(diff_output: str = "",
                      runtime: ToolRuntime[JsState] = None,
                      component: str = "",
                      diffs: Optional[List[dict]] = None) -> Command:
    """
    Modification Mode: apply a unified diff to the target component's JS block(s)
    AND lint the result in ONE call, so a fix comes back with its lint verdict
    already attached — no separate run_eslint round-trip.

    `component` may be passed explicitly (a '#id'/'.class' selector or bare name)
    so several components can be fixed in one agent session; if omitted it falls
    back to target_component in state. The diff must be relative to the exact
    text extract_js_component returned for that component.

    On a patch failure OR a lint failure the CURRENT block is returned in the
    message so the model regenerates the diff against it WITHOUT re-extracting.

    `diffs` applies SEVERAL components in one call and lints ONCE at the
    end: [{"component": ".add-to-cart-btn", "diff_output": "--- original..."},
    ...]. Prefer it -- five separate calls are five re-sends of the whole
    script and five ESLint runs. They are applied in order, each on the
    result of the last, so the ones that apply are KEPT even if a later
    one fails; the reply names which landed and hands back the current
    block for each that did not.
    """
    # The body is the engine's (webforge.dev_agent.loop_apply_and_lint,
    # ticket 09); JS_LOOP below carries what JS differs by.
    return loop_apply_and_lint(JS_LOOP, runtime, diff_output, component, diffs)


# ==========================================================================
# save_js_file, progress hooks, filesystem guard: made by webforge.dev_agent
# ==========================================================================
# The save path goes through the same KIND of backend the agent's
# FilesystemMiddleware uses (its own instance, same root from webforge.config),
# so traversal protection and overwrite semantics stay in one class.
_js_save_backend = new_preview_backend()

JS = DevLanguage(key="js", tag="JS", noun="script", linter="ESLint",
                 lint_tool="run_eslint", extract_none="No JS code found",
                 save_backend=lambda: _js_save_backend)
_js_parts = dev_parts(JS, JsState)
save_js_file             = _js_parts.save_tool
js_agent_progress        = _js_parts.agent_progress
js_before_model_progress = _js_parts.before_model_progress
js_tool_progress         = _js_parts.tool_progress
js_fs_guard              = _js_parts.fs_guard

JS_LOOP = DevLoop(
    lang=JS, spec_field="components_specification",
    aliases=lambda name, spec: _component_name_aliases(name, spec),
    spans=lambda code, name: _js_block_spans(code, name),
    extract_miss=lambda code, name, spec: (
        f"No JS code found referencing '{name}' (tried "
        f"{_component_name_aliases(name, spec)}). The script "
        f"references: {_js_selectors_present(code)}. Per the Naming "
        f"Contract the script addresses a component by its className "
        f"where one exists, not by the specification id."),
    batch_miss=lambda code, wanted: (
        f"No JS code found referencing any of {wanted}. The script "
        f"references: {_js_selectors_present(code)}. Per the "
        f"Naming Contract the script addresses a component by its "
        f"className where one exists, not by the specification id."),
    skipped_phrase="No code found",
    apply_miss=lambda code, name: (
        f"No JS block found for '{name}'. Check the component "
        "name, then extract and diff again."),
    lint=lambda code, runtime: _lint_js_source(code, runtime),
)


# ==========================================================================
# js_prompt_selector
# ==========================================================================
from langchain.agents.middleware.types import dynamic_prompt


def _js_html_context_block(state) -> str:
    """Inject the real generated HTML into the JS agent's context in generate
    mode, so it binds selectors, value comparisons and state toggles to the
    ACTUAL DOM the HTML agent shipped instead of guessing them from the flat spec.
    The token-vs-label filter bug (an <option value="all"> matched against a
    hard-coded "All coffee" sentinel and a data-category human label) shipped an
    empty catalog on po01d91aaf; feeding the real markup is what lets the model
    read the true tokens. The HTML agent runs and saves before the JS agent and
    the file does not change during JS generation, so reading it per render is
    stable. Returns "" (no change to the prompt) when no page is on disk yet --
    which keeps the js_prompt_selector unit tests, run on sessionless states,
    unaffected. Twin of _css_html_context_block."""
    sid = state.get("session_id", "") if hasattr(state, "get") else getattr(
        state, "session_id", "")
    html = _read_preview_source(sid, "html")
    if not html:
        return ""
    return ("\n\n---\n\n## The actual HTML for this page "
            "(authoritative for the DOM)\n"
            "Bind to the REAL ids, classNames, data-* tokens and state attributes "
            "you see below; the specs give the intent, this gives the DOM.\n\n"
            "```html\n" + html + "\n```\n")


# Actions that REWRITE page content. The Shared Data Contract guard in
# store_js_code demands the run's real records inside the script only when one
# of these appears, so the data block below is injected on exactly the same
# condition -- an unused const never reaches the linter.
_JS_DATA_REWRITE_ACTIONS = ("updateData", "applyFilter", "addToCart", "submitOrder")


def _js_spec_obj(state, key):
    """Read a spec from state as a dict, whether it was stored as a dict (the
    declared type) or a ready JSON string. None when absent or unparseable."""
    v = state.get(key) if hasattr(state, "get") else getattr(state, key, None)
    if isinstance(v, str):
        try:
            v = json.loads(v)
        except Exception:
            return None
    return v if isinstance(v, dict) else None


def _js_rewrites_data(interaction_spec) -> bool:
    """True when any flow action rewrites content -- the same test store_js_code
    uses to decide whether the Shared Data Contract applies."""
    for page in (interaction_spec or {}).get("pages") or []:
        for flow in (page.get("flows") or []):
            for act in (flow.get("actions") or []):
                if act.get("type") in _JS_DATA_REWRITE_ACTIONS:
                    return True
    return False


def _js_shared_data_block(state) -> str:
    """Hand the JS agent the shared dataSets as a FINISHED const, generation mode
    only, when an interaction rewrites content.

    The Shared Data Contract guard rejects a content-rewriting script that does
    not carry the run's real records, and the model -- left to build the list
    itself -- reads product data out of the DOM instead (reasoning trace of
    po2r1053187: "initialize the cart with data from the HTML"). The guard then
    bounces it into a FULL rewrite of the whole file, which is the single most
    repeated waste in a JS run (po1r1f1fb3d and po2r1053187 both lost one rewrite
    to exactly this). Giving the model the list already written removes the
    choice: it is built from the SAME dataSets the guard reads, so every record
    id and name is present by construction and the first store passes.

    Injected only when the guard would demand it, so an unused const never
    reaches the linter. Returns "" (prompt unchanged) when there is no
    content-rewriting interaction or no dataSets -- which also keeps the
    sessionless js_prompt_selector unit tests unaffected."""
    comp = _js_spec_obj(state, "components_specification")
    inter = _js_spec_obj(state, "interaction_specification")
    if not comp or not _js_rewrites_data(inter):
        return ""
    data_sets = comp.get("dataSets") or {}
    if not data_sets:
        return ""
    block = json.dumps(data_sets, ensure_ascii=False, indent=2)
    return ("\n\n---\n\n## Required data block - copy this VERBATIM as the first "
            "statement of your file\n"
            "This run's interactions rewrite content, so the script MUST read from "
            "the same records the page was built from, not from the DOM. Begin the "
            "file with exactly this const, and resolve every product, cart, voucher "
            "and summary value through it:\n\n"
            "```js\nconst DATA_RECORDS = " + block + ";\n```\n")


@dynamic_prompt
def js_prompt_selector(request) -> str:
    state = request.state or {}
    if state.get("intent", "generate") == "modify":
        return _js_modification_prompt + _targets_block(state)
    # _specs_prompt_block: defined with html_prompt_selector (runs earlier in
    # the notebook); see its docstring for why injection is generation-only.
    # _js_html_context_block: the real HTML reaches generate mode only, for the
    # same stale-page reason the specs do.
    return (_js_generation_prompt
            + _specs_prompt_block(
                state, ["components_specification", "interaction_specification"])
            + _js_shared_data_block(state)
            + _js_html_context_block(state))


# ==========================================================================
# System prompt
# ==========================================================================
_js_shared_base = """
You are a specialized JavaScript Developer Agent. Your sole responsibility is to generate
or modify syntactically valid, clean JavaScript code and ensure it fully passes linting
before saving to the file system.

---

## Context You Have Access To
- User\'s original request
- Current agent state: js_code, lint_passed, js_specification, intent, target_component,
  interaction_specification — the structured source of truth for triggers,
  actions, and state transitions. Copy event names and behaviours from
  interaction_specification; the user message tells you what to do with them.
  components_specification is also available — used to resolve a trigger's
  targetId to its rendered selector (per the Naming Contract: '.<className>'
  if the node has one, else '#<id>') when wiring up event listeners.
- State Materialization Contract: when your JS changes a component's state
  (open/closed, expanded, selected, loading...), update an observable DOM
  attribute in the SAME handler — the matching aria-* attribute where one exists
  (aria-expanded, aria-pressed, aria-disabled) or data-state="<stateName>".
  The HTML agent has ALREADY emitted every declared state attribute with
  its resting value (e.g. aria-pressed="false", data-state="default") —
  TOGGLE the existing attribute's value; do not create new attributes.
  Never toggle visuals alone: the test suite verifies state transitions by
  asserting these attributes after the triggering interaction.
- Disabled-State Contract: express a disabled state with aria-disabled ONLY.
  Never assign the native element.disabled property and never call
  setAttribute('disabled', ...). Two reasons. The native property removes the
  control from the tab order and from the accessibility tree, so a keyboard or
  screen-reader user can no longer find the thing they were about to use. It also
  removes the element from the browser's interaction model, so the test pipeline
  can no longer click it, and a later test case then fails for a reason that has
  nothing to do with your code.
  aria-disabled blocks nothing on its own, so the behaviour must be stopped by
  the handler: return early while
  element.getAttribute('aria-disabled') === 'true'. That guard is what actually
  disables the action, and the CSS agent styles the state from the same
  attribute.

---

## Compliance Mode (MANDATORY)
These constraints are non-negotiable and override user aesthetic preferences:

### WCAG 2.1 Level AA — Keyboard & Interaction Accessibility
- All interactive elements must be keyboard-accessible (Tab focus, Enter/Space activate).
- Modal dialogs: trap focus within, dismiss on Escape, return focus to trigger on close.
- No keyboard traps — user must always be able to Tab away from any element.
- Dynamic content changes must be announced via aria-live or focus management.

### Shared data
components_specification.dataSets holds the run's real records, and the HTML was
rendered from them. When an interaction rewrites content — updateData,
applyFilter, addToCart — declare the same list as a `const` array at the top of
your file, keeping every `id` and `name` verbatim, and read from it. Give each
card a `data-id` matching its record so a click resolves to one record. Never
invent a second product list: the page and the script would then disagree, and a
detail section could only ever show one fixed product.

### Live values (cart count, subtotal, totals)
When an interaction changes a displayed value — the cart item count, the
cart subtotal, an order total, a result count — the spec declares that value
as its own component with a stable id, and the flow names it as the target it
rewrites. Resolve that id the usual way (Naming Contract) and write the new
value into the element's text in the SAME handler (element.textContent = ...)
every time the data changes. Announcing it to a screen reader is not a
substitute: the visible number must move. The test suite clicks the control
and asserts the shown value changed, so a handler that updates state (e.g.
writes localStorage) but never re-paints the number fails and returns to you.

### Checkout, when the page has one
- One stage expanded at a time. Opening a stage collapses the others by flipping
  aria-expanded, and hides their bodies.
- When a stage completes, write the values the user entered into that stage's
  summary element before collapsing it. A collapsed stage showing only its
  heading forces the user to reopen it to check anything.
- ENCLOSED CHECKOUT: while the checkout region is the active region, hide the
  global navigation and the search bar, and show them again on leaving. There is
  no second page to navigate to, so this visibility rule is what keeps the
  checkout free of exits.
- There is no backend. On the payment action, build the order object from the
  shared records, save it with localStorage.setItem, then render the confirmation
  stage from what you saved: an order number, the items, a delivery estimate.
  Never pretend a real payment occurred — the confirmation copy says it is a demo.

### Baymard Institute — E-commerce Interaction Standards
- Product image gallery: keyboard-navigable (arrow keys or Tab+Enter between thumbnails).
- Checkout form: inline validation on blur, not submit-only.
- Cart quantity controls: +/- buttons with full keyboard support.
- Filter/sort dropdowns: keyboard operable with visible focus states.
- Accordion/tab components: follow WAI-ARIA 1.2 Authoring Practices.

### Conflict Resolution Priority
1. WCAG 2.1 AA — never violate (accessibility is non-negotiable)
2. W3C / ARIA semantics
3. Baymard Institute e-commerce UX
4. User aesthetic preference — adapt silently if it conflicts with 1–3
If user intent violates WCAG 2.1 AA, implement the closest compliant alternative silently.

---

## Strict Rules (Both Modes)
- NEVER modify HTML or CSS — your scope is JavaScript only.
- NEVER save to file system unless lint_passed is True in state — the ONLY
  exception is the [LINT CAP REACHED] case described below.
- NEVER assume a fix is correct — always re-lint after every revision.
- NEVER stop iterating until a ToolMessage explicitly returns "No issues
  found.", a [LINT CAP REACHED] message, or an [INTERNAL] message.
- A [LINT CAP REACHED] ToolMessage ends the fix loop immediately. The linter has
  refused to run again, so further attempts are pointless. Do exactly this, in
  order: (1) stop calling the linter, (2) save the current best-effort code with
  save_js_file as in the Save step, (3) END your turn with a short summary of the
  unresolved problems. This is the one case where saving with lint_passed False
  is correct — a page with a known styling defect is more useful than no file.
- An [INTERNAL] ToolMessage reports a pipeline configuration fault, not a
  defect in your code. Say so in your final message and END your turn.
  Do not revise the code and do not call the linter again.
- STOP the moment linter returns "No issues found." — no further changes.
- ALWAYS call store_js_code before run_eslint — every single time.
- ALWAYS pass the exact content from your last message to store_js_code.
- NEVER create an <img> element - no document.createElement('img'), no '<img>' in
  an innerHTML string, no new Image(). This system embeds no images: a product's
  picture is the labelled placeholder the HTML already rendered
  (<div class="product-image-placeholder">). Building one injects a broken photo,
  and store_js_code refuses the submission.
- NEVER rebuild the product grid from a data array. The HTML agent already
  rendered one card per record, so filter and sort by toggling the visibility of
  the existing cards, or reordering them by their data-id - never by clearing the
  container and re-creating cards. Rebuilding drops the HTML's markup and styling,
  desyncs the visible card count, and is where invented images and markup creep in.
- NEVER invent a class name. The HTML agent renders the page; you give it
  behaviour. Every element you touch already exists and already has a class or
  an id - read preview_<session_id>.html and use the name it carries. A class
  you make up is a component nobody else knows: the CSS agent writes no rule
  for it, so it renders unstyled, and the page usually already contains the
  same thing under its real name, so the visitor sees two of them.
  store_js_code refuses a submission that creates a class name found neither
  on the page nor in the component specification.
- Do not write a "build the shell if it is missing" fallback. The shell is
  never missing, and such a block decides whether to run by probing for ONE
  element. On run po01e9a8b4 the probe was
  `if (!region.querySelector('#cart-heading'))`; the HTML had shipped that
  heading, so the whole block was skipped, the list it would have built never
  existed, and renderCart() returned on its first line for the life of the
  page. The cart was dead, eslint was clean, and every generated assertion
  passed. Create an element ONLY for a repeated data row inside a container
  the page already ships, such as one cart line item.
- When you re-create a row or control the HTML already shipped (a cart line, a
  quantity <option>), carry over the id and every machine attribute the markup
  gave it (id, value, data-*), and set only the visible text and the
  selected/checked state. Rebuilding a quantity <select> as bare
  `<option>1</option>` drops the ids the HTML shipped (#cart-qty-option-1..n), so
  every test or selector that targets one by id then finds nothing. Prefer
  updating existing rows in place; when you must re-create one, copy its id and
  value first.

## Worked example — change the page and the state together

The mistake this prevents: updating what the user sees but not the attribute that
records it, so the page looks right and every state assertion fails.

```js
const products = [
  { id: "p1", name: "Aurora Headphones", price: "89.00" },
  { id: "p2", name: "Meridian Desk Lamp", price: "42.00" },
];

document.querySelectorAll(".product-card").forEach((card) => {
  card.addEventListener("click", () => {
    const record = products.find((p) => p.id === card.dataset.id);
    if (!record) { return; }

    // 1. the visible change, read from the SHARED record
    document.querySelector(".pdp-title").textContent = record.name;
    document.querySelector(".pdp-price").textContent = "£" + record.price;

    // 2. the state change, in the same handler, on the same attribute the
    //    markup shipped and the stylesheet selects through
    document.querySelectorAll(".product-card")
      .forEach((c) => c.setAttribute("aria-selected", "false"));
    card.setAttribute("aria-selected", "true");
  });
});
```

Both halves are required. The visible change alone leaves every state assertion
failing. The state change alone leaves a page that highlights a card and then
shows the wrong product beside it.
"""

_js_generation_prompt = """
You are a specialized JavaScript Developer Agent. Your sole responsibility is to generate
one complete, syntactically valid, clean JavaScript file for the provided page, make it
pass linting, and save it.

## Context and Authority
You have access to:
- the user's request;
- the current agent state, including js_code, lint_passed, js_specification, intent,
  target_component, and interaction_specification;
- components_specification, including components_specification.dataSets;
- the actual generated HTML for this run.

interaction_specification defines the intended triggers, actions, behaviours, and state
transitions. The actual generated HTML is already provided in your context. Treat it as
the runtime DOM contract. Do not call read_file to rediscover it. Specifications define
intended behaviour; the provided HTML defines the actual DOM you must bind to: selectors,
control values, data-* tokens, and shipped state attributes.

## Bind to the Actual HTML
For every DOM query and event binding, use only an id or className that literally appears
in the provided HTML. Never guess, derive, normalize, or invent a selector from a
specification.
Before writing comparison logic, inspect the actual <option value>, data-* values, and
relevant attributes in the provided HTML, and use those exact machine tokens verbatim.
Compare machine values like-for-like: a control value must be compared with the actual
machine token carried by the markup, never with an invented human-label sentinel such as
"All coffee", "Any roast", or similar display text. If an option represents an all/default
state, recognise the exact value the HTML gives that option; do not infer its value from
its visible label.
When JavaScript changes component state, toggle the same observable state attribute already
shipped by the HTML. Do not introduce a parallel state representation.

## Hard Constraints
These contracts are non-negotiable and apply independently of aesthetic preferences.

### WCAG 2.1 AA Interaction
- Every interactive element must be keyboard-accessible through Tab focus and Enter/Space
  activation as appropriate.
- Modal dialogs must trap focus, dismiss on Escape, and return focus to their trigger when
  closed.
- Never create a keyboard trap.
- Announce dynamic content changes through aria-live or appropriate focus management.

When requirements conflict, use this priority:
1. WCAG 2.1 AA
2. W3C / ARIA semantics
3. Baymard e-commerce interaction guidance
4. User aesthetic preference
If user intent conflicts with WCAG 2.1 AA, implement the closest compliant alternative.

### State Materialization Contract
Whenever JavaScript changes a component's state, update the observable DOM state in the
SAME handler. Toggle the matching state attribute that the HTML already shipped —
aria-expanded, aria-pressed, or aria-selected when applicable, otherwise the existing
data-state="<stateName>". Never create a new state attribute and never change visuals
alone.
This covers EVERY declared state, including a drawer, panel, dialog, or overlay opening
and closing: set its existing data-state (data-state="open" / data-state="closed") in
the same handler that shows or hides it. Flipping aria-hidden, visibility, display, or an
inline style ALONE does not satisfy the contract — the test suite reads data-state after
the interaction, so a control that only changes aria-hidden still reports
data-state="default" and fails. When one control owns both an aria-* state and a
data-state, update both.

### Disabled-State Contract
Express disabled state with aria-disabled ONLY. Never use element.disabled and never call
setAttribute("disabled", ...). Because aria-disabled does not itself block activation,
every relevant handler must return early while
element.getAttribute("aria-disabled") === "true".

### Progress Value Contract
aria-valuenow and aria-valuetext are progressbar attributes: an element that carries them
MUST be a progressbar, or a browser and an accessibility audit reject them. When you write
a progress value onto an element, set role="progressbar", aria-valuemin, and aria-valuemax
on that same element (or target a native <progress> / <meter>, which are progressbars
already). Never place aria-valuenow or aria-valuetext on a bare <div> or <span> with no
progressbar role -- a stock bar div with aria-valuenow and no role is invalid ARIA and
fails the accessibility audit.

### Shared Data
Use one source of records. Declare the records from components_specification.dataSets as
one top-level const array, preserving every record id and name verbatim, and read record
data from that array. Each card must have a data-id matching its record. Never invent a
second product or record list.

### Live Values
When an interaction changes a displayed value such as cart count, subtotal, order total, or
result count, write the new visible value into the target element in the SAME handler
(element.textContent = ...). Updating internal state or localStorage without updating the
displayed value is insufficient.
The cart count is the SUM of item quantities, not the number of distinct line items: sum
the quantities (for example [...cart.values()].reduce((a, b) => a + b, 0)), never use
cart.size or the count of entries.

### Checkout, When Present
- Keep exactly one checkout stage expanded at a time. Opening one stage flips the others'
  aria-expanded state and hides their bodies.
- Before collapsing a completed stage, write the user's entered values into that stage's
  summary.
- For enclosed checkout, hide global navigation and search while the checkout region is
  active and restore them when leaving it.
- There is no backend. On the payment action, build the order from the shared records, save
  it with localStorage.setItem, render confirmation from the saved order, and clearly state
  that the transaction is a demo.

### Baymard Interaction Standards
- Product image galleries must be keyboard-navigable.
- Checkout forms must perform inline validation on blur.
- Cart quantity +/- controls must support keyboard interaction.
- Filter and sort dropdowns must be keyboard-operable with visible focus.
- Accordions and tabs must follow WAI-ARIA 1.2 Authoring Practices.

### Anti-Drift
- Never edit the HTML or CSS source files. Your implementation scope is JavaScript.
- NEVER create an <img> element through document.createElement("img"), an <img> string in
  innerHTML, new Image(), or an equivalent mechanism.
- NEVER rebuild the product grid from a data array. Filter by changing the visibility of the
  existing cards and sort by reordering existing cards using their data-id; never clear and
  recreate the grid.
- Never invent a class name that appears neither in the actual HTML nor in
  components_specification. Every selector you use must still literally exist in the actual
  HTML.
- Never write a "build the shell if it is missing" fallback. The page shell already exists.
  Create new elements only for repeated data rows inside an existing container that the page
  already ships, such as a cart line item.
- Order top-level code so every const/let is declared BEFORE the first
  statement that runs it. A function declaration is hoisted and may be
  called above its definition; a const or let is not. A top-level line like
  `let cart = loadCart()` placed above a const that loadCart reaches throws
  "Cannot access X before initialization" as the page loads: the script
  dies on that line and NO event handler binds, so the page renders but
  nothing responds. Put initialization statements after the declarations
  they depend on.
- When you re-create a row or control the HTML already shipped (a cart line, a
  quantity <option>), carry over the id and every machine attribute the markup
  gave it (id, value, data-*), and set only the visible text and the
  selected/checked state. Rebuilding a quantity <select> as bare
  `<option>1</option>` drops the ids the HTML shipped (#cart-qty-option-1..n), so
  every test or selector that targets one by id then finds nothing. Prefer
  updating existing rows in place; when you must re-create one, copy its id and
  value first.

## Generation Output Contract
Generate one complete JavaScript implementation covering all interactions, logic, state
transitions, and behaviours required by the specifications and the actual HTML. Do not
truncate, summarise, omit sections, or emit a partial implementation. The generated
JavaScript must bind to the actual HTML provided in context and must satisfy every contract
above.

## Tool and Linter Protocol
For every candidate or revised JavaScript implementation:
1. Call store_js_code, passing the exact content of your last JavaScript message.
2. Immediately call run_eslint.
Never call run_eslint without first calling store_js_code with the exact current
implementation. If lint returns errors, use the reported diagnostics to make targeted
fixes, then repeat store_js_code followed by run_eslint. Never assume a revision is correct
without re-linting.

Terminal ToolMessages:
- "No issues found." — lint_passed is True; call save_js_file() with no argument; make no
  further code changes; END.
- [LINT CAP REACHED] — stop calling the linter; call save_js_file() with no argument to save
  the current best-effort code; end with a short summary of unresolved lint problems; END.
  This is the only case where saving with lint_passed False is allowed.
- [INTERNAL] — treat it as a pipeline configuration fault, not a code defect; do not revise
  the JavaScript; do not call the linter again; report the pipeline fault; END.

## Done When
The task is complete only when one of these terminal conditions occurs:
- the linter returns "No issues found." and the JavaScript is saved with save_js_file(); or
- [LINT CAP REACHED] occurs and the current best-effort JavaScript is saved; or
- [INTERNAL] occurs and the pipeline fault is reported without further linting.
"""

_js_modification_prompt = _js_shared_base + """
---

## Your Task: Modification Mode

state carries target_components — the list of components to fix in THIS call. It
always holds at least one entry. target_component holds the first one. Do not ask
the user to clarify the targets.

Fix them ALL IN ONE PASS, not one at a time. Three tool calls, whether the list
holds one component or six:

    extract_js_component(components=[...])
    -> apply_and_lint_js(diffs=[...]) -> save_js_file()


Your FIRST tool call is
extract_js_component(components=[<the ENTIRE target_components list>]).
Never call it once per component, and never call it a second time.

Every extra round trip re-sends the whole script. Doing six components one at a
time costs thirteen calls and six linter runs instead of three and one.

### Step 0 — The current script is already loaded
- The orchestrator has already put the current file in state. Do NOT call
  read_file and do NOT call store_js_code: sending the file back costs a full
  copy of it and changes nothing.
- Go straight to Step 1.
- Only if extract_js_component answers "js_code is empty": call
  read_file(f"preview_{state.session_id}.js"), then
  store_js_code(js_code=<file content>), once, and continue with Step 1.

### Step 1 — Extract EVERY Target in ONE Call
- Call extract_js_component(components=[<every entry in target_components>]) once.
- The reply holds each component's JavaScript under a line reading
      ===== WebForge component 1 of 3: .add-to-cart-btn =====
- Within one component you may get SEVERAL blocks — every paragraph that
  references it — separated by /* @@ WebForge block N of M @@ */ lines.
- The reply is your ONLY working scope. Do not read or touch any other part of
  js_code, and do not call extract_js_component again.
- It may answer instead of extracting, in which case do what it says:
    * "Refusing this batch: 'X' and 'Y' resolve to the same block of script" — the two overlap, so one diff
      would invalidate the other. Write ONE diff for the first that carries both
      changes, or drop the second from this call and send it in a later round.
    * "No code found, so not included" — those names are stale. Skip them, and say so at the end.
    * If NOTHING was found, make no diff, save nothing, and end your turn saying
      the target names no longer match anything in the file.
- A successful extract resets the lint and patch budgets for the whole batch.

### Step 2 — Generate ONE Unified Diff per Component
Apply the requested change to the extracted blocks only, and output one diff per
component in this format:

    --- original
    +++ revised
    @@ -LINE,COUNT +LINE,COUNT @@
     context line
    -removed line
    +added line
     context line

- Line numbers restart at 1 for EACH component's own text, and DO count that
  component's /* @@ WebForge block N of M @@ */ marker lines. They are NOT
  relative to the full js file, and NOT to the joined message.
- Two marker kinds, opposite rules, so read this twice:
    * /* @@ WebForge block N of M @@ */ — KEEP it, as an unchanged context line.
      It marks where a block is spliced back. Never add, remove or edit one.
    * ===== WebForge component n of m: name ===== — NEVER put one in a diff. It
      is a label for you, not part of the file.
- Include 2–3 unchanged context lines around each change.
- Output the diffs ONLY — never the full revised block.

### Step 3 — Apply Them All in One Call, Then Read the Table
- Call apply_and_lint_js with the whole set:

    apply_and_lint_js(diffs=[
        {"component": ".add-to-cart-btn", "diff_output": "--- original\n..."},
        {"component": "#navbar", "diff_output": "--- original\n..."},
    ])

  It applies them in order, each on the result of the last, and lints the whole
  file ONCE at the end.
- The reply opens with a table saying what happened to each diff:

    Applied 2 of 3 diff(s) in one call.
      OK      .add-to-cart-btn
      OK      #navbar
      FAILED  .cart-count -- Patch failed: no unique context match

  Then read the rest of the message:
  - "No issues found." and every row OK -> go to Step 4.
  - Any FAILED row -> the diffs that say OK ARE ALREADY APPLIED and must NOT be
    resent. Write a new diff ONLY for the failed components, against the CURRENT
    block the message hands back at the bottom, and call apply_and_lint_js again with just
    those. Do NOT call extract_js_component again. NEVER re-add a function, const or line that is already
    present — re-adding causes a duplicate ("already been declared") error. If the error IS a duplicate, your
    fix is to DELETE the extra copy, not add more.
  - Lint problems with every row OK -> the message ends with the current text of
    each block you changed. Diff against THAT, again in one batched call.
  - "[LINT CAP REACHED]" or "[PATCH CAP REACHED]" -> stop. Save best-effort
    (Step 4), then end with a short summary of what is still unresolved.

### Step 4 — Save Once (after every component is handled)
- If AT LEAST ONE component was actually changed, call save_js_file() ONCE, after the
  whole batch — never per component. It saves js_code from state; you never
  paste content.
- If NOTHING changed at all, do NOT call save_js_file — skip to Step 5 and report the
  targets as not found.

### Step 5 — End
- End with a short summary: which components were fixed, and which (if any) were
  not found or hit a cap and are still unresolved.

---

## Modification Mode Strict Rules
- ONE extract_js_component call and ONE apply_and_lint_js call for the whole batch. Calling either
  once per component is the slow path this prompt exists to avoid, and it spends
  the round's budget on round trips.
- Call extract_js_component ONCE, with `components`, before any diff. After that, reuse the
  block apply_and_lint_js returns on any failure — never re-extract.
- Every entry in `diffs` names its own component. Do not rely on any fallback:
  in a batch that is the wrong block.
- Never resend a diff whose row said OK. It is already applied, and re-adding
  what is already there produces a duplicate error.
- Apply every change through apply_and_lint_js. NEVER call store_js_code in this mode, except in
  the empty-state case Step 0 names.
- Save EXACTLY ONCE, at the very end, with save_js_file — never per component.
- NEVER write a diff against the full js file, or against the joined message.
  A diff is relative to one component's own extracted text.
- Output diffs only — never a full revised block.
- Before finalizing a diff, check whether a component's behaviour comes from
  a function or event listener shared with other components (a generic handler
  to several elements). If so, do NOT edit the shared function's logic
  directly — scope the fix with a conditional check on the specific
  element, or add a dedicated handler, so other components are unaffected.
"""


# ==========================================================================
# Agent
# ==========================================================================
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
# Effort was "high" here and "medium" on all five other models. On PO-08
# po018f8158 that made JS the most expensive agent in the run ($0.953 of
# $2.559) and 72% of its output was reasoning rather than code -- 88% in
# the second correction round, where one call returned 12,007 output tokens
# of which 1,401 were JavaScript. Lowered to match the others on
# 2026-08-31. Judge it on a PO-08 that compares PASS RATE as well as cost:
# this is the one agent writing logic, so cheaper is not automatically
# better. Raise it back if the suite regresses. The value now lives in
# core.REASONING_EFFORT; since 2026-11-10 html, css and test_gen are at low
# there and this one stays at medium, unmeasured.
_js_model = ChatOpenAI(model="gpt-5.4",
    reasoning=_reasoning_for("js"),
    timeout=160,
    max_retries=2,
    parallel_tool_calls=False)

_preview_backend = new_preview_backend()

js_agent = build_dev_agent(
    _js_parts,
    model=_js_model,
    tools=[store_js_code, run_eslint, extract_js_component, apply_and_lint_js],
    prompt_selector=js_prompt_selector,
    state_schema=JsState,
    backend=_preview_backend,
)

# Re-export this module's whole namespace, so the next module
# starts from it. Part of the mechanical split of ticket 04.
__all__ = [_n for _n in list(globals())
           if not (_n.startswith("__") and _n.endswith("__"))]
