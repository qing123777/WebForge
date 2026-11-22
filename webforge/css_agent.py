"""css_agent: the CSS developer agent: CssState, stylelint, its tools, prompts and agent; the cross-agent binding check.

Lines 9754-12300 of the flat fyp.py at commit 6e8c14b, moved
verbatim by refactor ticket 04 (tools/split_fyp.py).
"""
from __future__ import annotations

from webforge.js_agent import *  # noqa: F401,F403

# ==========================================================================
# state
# ==========================================================================
from typing import Literal

class CssState(AgentState):
    css_specification: str
    css_code:          str = ""
    lint_passed:       bool = False
    lint_attempts:        int = 0
    lint_escalated:       bool = False
    patch_attempts:       int = 0
    coverage_attempts:    int = 0
    # The stylesheet a drift refusal is holding, exactly as the model sent it,
    # so store_css_code(retarget=...) can fix one selector without the model
    # sending the whole file again (speed-cost ticket 05). "" when none is.
    css_pending:          str = ""
    session_id:        str
    intent:            Literal["generate", "modify"] = "generate"
    target_component:  str = ""
    target_components: list = []
    target_instance:   int = 1
    decoration_specification: dict = {}
    # Declared so the selector allowlist (css_prompt_selector) actually
    # reaches the agent. LangGraph drops a write to an undeclared channel,
    # and until 2026-09-01 CssState was the one dev-agent schema missing
    # this field, so _css_selector_allowlist_block read {} and rendered
    # empty in every run. HtmlState and JsState both declare it.
    components_specification: dict = {}
    # The CSS agent used to receive components + decoration only, so a
    # region with no components was invisible to it and shipped unstyled.
    layout_specification:     dict = {}


# ==========================================================================
# run_stylelint
# ==========================================================================
@tool
def run_stylelint(runtime: ToolRuntime[CssState]) -> Command:
    """
    Lint the current css_code in state using Stylelint (config auto-discovered:
    .stylelintrc.json in the repo root — built-in rules only, no plugins).
    Reads css_code from state — call store_css_code first.
    Updates lint_passed to True when no problems are found.
    """
    return _lint_css_source(runtime.state.get("css_code", ""), runtime)


# ── Duplicate-selector collapse (Group 3, PO-10 po0735889c, 2026-09-05) ──────
# The CSS modify agent, told to change one component, sometimes APPENDS a fresh
# `.selector { ... }` block instead of editing the existing one, so two rules
# ship for the same selector (po0735889c grew a second .product-rating /
# .deal-countdown / .add-to-cart at the tail, each holding the fix). stylelint's
# no-duplicate-selectors then fails, the fix loop caps at _LINT_ATTEMPT_CAP, and
# the duplicate ships. _dedupe_css_selectors collapses such duplicates BEFORE the
# linter sees the file, so the rule never fires and no attempt is spent. Only
# TOP-LEVEL rules are merged; @media/@supports/@keyframes, comments and at-
# statements are preserved verbatim (a selector inside @media is a different
# cascade context). The merged rule keeps the LAST occurrence's position with
# per-property last-wins (an !important value only yields to a later !important),
# which is exactly what the browser renders, so the collapse is visually
# identical. n_merged == 0 returns the input unchanged byte-for-byte.
import re as _re_dd
from collections import defaultdict as _dd_defaultdict, OrderedDict as _dd_OrderedDict


def _dd_norm_sel(sel):
    sel = _re_dd.sub(r"/\*.*?\*/", "", sel, flags=_re_dd.S)
    sel = _re_dd.sub(r"\s+", " ", sel).strip()
    sel = _re_dd.sub(r"\s*,\s*", ", ", sel)
    return sel


def _dd_split_decls(text):
    parts, depth, buf, i, n = [], 0, [], 0, len(text)
    while i < n:
        c = text[i]
        if c == "/" and i + 1 < n and text[i + 1] == "*":
            k = text.find("*/", i + 2); i = k + 2 if k != -1 else n; continue
        if c in "\"'":
            q = c; buf.append(c); i += 1
            while i < n:
                buf.append(text[i])
                if text[i] == "\\":
                    if i + 1 < n: buf.append(text[i + 1])
                    i += 2; continue
                if text[i] == q: i += 1; break
                i += 1
            continue
        if c == "(": depth += 1
        elif c == ")": depth -= 1
        if c == ";" and depth == 0:
            parts.append("".join(buf)); buf = []; i += 1; continue
        buf.append(c); i += 1
    if "".join(buf).strip():
        parts.append("".join(buf))
    return parts


def _dd_iter_decls(text):
    for p in _dd_split_decls(text):
        p = p.strip()
        if not p or ":" not in p:
            continue
        prop, val = p.split(":", 1)
        prop = prop.strip().lower()
        val = val.strip()
        imp = False
        m = _re_dd.search(r"!\s*important\s*$", val, _re_dd.I)
        if m:
            imp = True
            val = val[:m.start()].strip()
        yield prop, val, imp


def _dd_serialize_rule(sel, od):
    lines = [sel + " {"]
    for prop, (val, imp) in od.items():
        lines.append(f"  {prop}: {val}{' !important' if imp else ''};")
    lines.append("}")
    return "\n".join(lines)


def _dedupe_css_selectors(css):
    """Merge duplicate top-level selectors; return (css, n_duplicate_rules_removed)."""
    if not css or "{" not in css:
        return css, 0
    s = css; n = len(s)

    def _block_end(open_idx):
        depth, j = 0, open_idx
        while j < n:
            c = s[j]
            if c == "/" and j + 1 < n and s[j + 1] == "*":
                k = s.find("*/", j + 2); j = k + 2 if k != -1 else n; continue
            if c in "\"'":
                q = c; j += 1
                while j < n:
                    if s[j] == "\\": j += 2; continue
                    if s[j] == q: j += 1; break
                    j += 1
                continue
            if c == "{": depth += 1
            elif c == "}":
                depth -= 1
                if depth == 0:
                    return j + 1
            j += 1
        return n

    segs, prelude_start, i = [], 0, 0
    while i < n:
        c = s[i]
        if c == "/" and i + 1 < n and s[i + 1] == "*":
            k = s.find("*/", i + 2); i = k + 2 if k != -1 else n; continue
        if c in "\"'":
            q = c; i += 1
            while i < n:
                if s[i] == "\\": i += 2; continue
                if s[i] == q: i += 1; break
                i += 1
            continue
        if c == "{":
            end = _block_end(i)
            prelude = s[prelude_start:i]
            sel = prelude.strip()
            if sel.startswith("@"):
                segs.append({"kind": "at", "a": prelude_start, "b": end})
            else:
                segs.append({"kind": "rule", "a": prelude_start, "b": end,
                             "sel": _dd_norm_sel(sel), "decls": s[i + 1:end - 1]})
            prelude_start = end; i = end; continue
        if c == ";":
            segs.append({"kind": "stmt", "a": prelude_start, "b": i + 1})
            prelude_start = i + 1; i += 1; continue
        i += 1
    tail = s[prelude_start:n]

    counts = _dd_defaultdict(int)
    for seg in segs:
        if seg["kind"] == "rule":
            counts[seg["sel"]] += 1
    dups = {k for k, v in counts.items() if v > 1}
    if not dups:
        return css, 0

    merged = {}
    for seg in segs:
        if seg["kind"] != "rule" or seg["sel"] not in dups:
            continue
        od = merged.setdefault(seg["sel"], _dd_OrderedDict())
        for prop, val, imp in _dd_iter_decls(seg["decls"]):
            if prop in od:
                _pv, _pi = od[prop]
                if _pi and not imp:
                    continue
                od[prop] = (val, imp)
            else:
                od[prop] = (val, imp)

    last_idx = {}
    for idx, seg in enumerate(segs):
        if seg["kind"] == "rule" and seg["sel"] in dups:
            last_idx[seg["sel"]] = idx

    out = []
    for idx, seg in enumerate(segs):
        text = s[seg["a"]:seg["b"]]
        if seg["kind"] == "rule" and seg["sel"] in dups:
            if idx == last_idx[seg["sel"]]:
                lead = text[:len(text) - len(text.lstrip())]
                out.append(lead + _dd_serialize_rule(seg["sel"], merged[seg["sel"]]))
            # else: drop the earlier duplicate
        else:
            out.append(text)
    out.append(tail)
    return "".join(out), sum(counts[k] - 1 for k in dups)


def _lint_css_source(css_code: str, runtime) -> Command:
    """Collapse duplicate top-level selectors, THEN lint the collapsed CSS.

    Every developer-agent lint of CSS funnels through here -- generate
    (run_stylelint) and modify single/batch (apply_and_lint_css) -- so the
    collapse is universal. When a merge happened the collapsed CSS is written
    back through the returned Command's css_code, so the stored and served file
    is the collapsed one, not the duplicate-laden input the model produced. See
    _dedupe_css_selectors for why the modify agent emits the duplicates.
    """
    # The Spec Base Styles block repeats selectors ON PURPOSE (it must come
    # after the model's rule to win). Merging it into the model's rules would
    # move the model's declarations inside the block, and the next refresh of
    # the block would delete them. So only the model's part is collapsed.
    _m = _SPEC_BLOCKS_RE.search(css_code or "")
    _body = (css_code[:_m.start()] + css_code[_m.end():]) if _m else css_code
    _deduped, _n = _dedupe_css_selectors(_body)
    if _m:
        _deduped = _deduped.rstrip() + "\n\n" + _m.group(0).rstrip() + "\n"
        _n = _n or (_deduped != css_code and 1)
    _cmd = _lint_css_source_impl(_deduped, runtime)
    if _n and getattr(_cmd, "update", None) is not None:
        _cmd.update["css_code"] = _deduped
    return _cmd


def _lint_css_source_impl(css_code: str, runtime) -> Command:
    """
    Lint a CSS SOURCE STRING and return the same Command run_stylelint has always
    returned. Factored out so apply_and_lint_css can lint the code it JUST
    patched, in the same tool call, without a second run_stylelint round-trip.
    run_stylelint is now a thin wrapper that lints state's css_code. Behaviour is
    unchanged (escalation refusal, empty guard, config/parse handling, cap
    counting via _lint_failure). The refusal, the empty guard and the temp file
    are the engine's (webforge.dev_agent.lint_source, ticket 09);
    _stylelint_check is what Stylelint adds.
    """
    return lint_source(CSS, css_code, runtime, _stylelint_check)


def _stylelint_check(tmp_path: str, runtime) -> Command:
    """Run Stylelint on the temp file and turn its JSON report into the verdict."""
    result = _run_lint_subprocess(
        f'npx --no-install stylelint --formatter json "{tmp_path}"')
    if result.returncode == 78:
        # 78 = stylelint configuration error — an infra problem, not a CSS bug
        return Command(update={
            "lint_passed": False,
            "messages": [ToolMessage(
                content=("Stylelint configuration problem (exit 78) — check "
                         ".stylelintrc.json in the repo root:\n"
                         + (result.stderr or result.stdout)[:500]),
                tool_call_id=runtime.tool_call_id
            )]
        })
    # Stylelint v16+ writes the JSON report to STDERR (older versions used
    # stdout) — parse whichever stream holds it.
    raw = (result.stdout or "").strip() or (result.stderr or "").strip()
    try:
        results  = _json.loads(raw)
        entry    = results[0] if results else {}
        problems = list(entry.get("parseErrors", [])) + list(entry.get("warnings", []))
    except (ValueError, IndexError, KeyError):
        if "npx" in (result.stderr or "").lower() and result.returncode != 0:
            return Command(update={
                "lint_passed": False,
                "messages": [ToolMessage(
                    content=(
                        "Stylelint could not be executed because `npx` was not found. "
                        "Install Node.js and run `npm install` in this repo."
                    ),
                    tool_call_id=runtime.tool_call_id
                )]
            })
        return Command(update={
            "lint_passed": False,
            "messages": [ToolMessage(
                content=("Stylelint produced unparseable output:\n" + raw[:800]),
                tool_call_id=runtime.tool_call_id
            )]
        })
    if not problems:
        return Command(update={
            "lint_passed": True,
            "messages": [ToolMessage(content="No issues found.",
                                     tool_call_id=runtime.tool_call_id)]
        })
    lines = [f"Found {len(problems)} problem(s):"]
    for w in problems:
        lines.append(
            f"  Line {w.get('line','?')}, Col {w.get('column','?')} "
            f"[{w.get('rule','parse-error')}]: {w.get('text', w.get('message',''))}"
        )
    return _lint_failure(runtime, "\n".join(lines))


# ==========================================================================
# store_css_code
# ==========================================================================
import re
from bs4 import BeautifulSoup

# ── Design Token Contract ────────────────────────────────────────────────────
# WebCoderBench scores Component Style Consistency and Visual Harmony Degree:
# does the page use one small shared palette, or a scatter of one-off colours?
# Naming the values once in :root and referencing them everywhere is what makes
# consistency the default -- change --color-primary and every button, link and
# accent moves together.
#
# TWO RULES OF DIFFERENT STRENGTH, on purpose:
#   * the :root block is REQUIRED (objective, one edit fixes it);
#   * the tokenisation ratio only WARNS.
# The coverage-guard retry loop in store_css_code has no attempt cap -- it
# converges because every other guard asks for something objective. A ratio is
# a matter of degree, and refusing on a degree is exactly what could make that
# loop spin. So the ratio is reported, not enforced.
# Ablation switch. True = the :root rule REFUSES (the shipped behaviour).
# False = the rule is measured and reported in the ToolMessage but never blocks,
# so a run still produces an artifact. That is arm B of the design-token
# experiment: CSS prompt rule ON, Python guard OFF, which is the only way to
# show what the guard adds over the prompt alone. Do not ship it False.
_DESIGN_TOKEN_ENFORCED = True

_DESIGN_TOKEN_MIN   = 6      # custom properties :root must declare
_TOKEN_FREE_LITERALS = 4     # hard-coded colours allowed before the ratio applies
_TOKEN_COVERAGE_MIN  = 0.6   # of colour declarations outside :root

_COLOR_LITERAL_RE = re.compile(
    r"#[0-9a-fA-F]{3,8}\b"
    r"|\b(?:rgba?|hsla?|hwb|lab|lch|oklab|oklch|color-mix)\s*\(",
    re.I)
_NAMED_COLORS = {
    "white", "black", "red", "green", "blue", "yellow", "orange", "purple",
    "grey", "gray", "silver", "navy", "teal", "olive", "maroon", "lime",
    "aqua", "cyan", "magenta", "fuchsia", "pink", "brown", "gold", "beige",
    "ivory", "khaki", "indigo", "violet", "salmon", "tan", "coral", "crimson",
    "plum", "orchid", "turquoise", "lavender", "wheat", "snow", "azure",
    "linen", "tomato", "thistle", "sienna", "chocolate", "darkblue",
    "lightblue", "darkgray", "lightgray", "darkgrey", "lightgrey",
}
# Never colours, whatever the property: these carry no palette decision.
_COLOR_KEYWORDS_OK = {"transparent", "currentcolor", "inherit", "initial",
                      "unset", "revert", "none", "auto"}
_URL_RE = re.compile(r"url\([^)]*\)", re.I)


def _strip_root_blocks(css: str) -> tuple:
    """Split CSS into (root_block_text, everything_else).

    Any block whose prelude mentions :root counts, so a dark-mode override
    inside @media is treated as token declaration too, not as a violation."""
    roots, rest, i, n = [], [], 0, len(css)
    start = 0
    while i < n:
        if css[i] == "{":
            prelude = css[start:i]
            depth, j = 1, i + 1
            while j < n and depth:
                if css[j] == "{":
                    depth += 1
                elif css[j] == "}":
                    depth -= 1
                j += 1
            body = css[i:j]
            if ":root" in prelude:
                roots.append(prelude + body)
            else:
                # keep nested content reachable: an @media wrapper is stepped
                # over, not skipped, exactly as _css_prelude_blocks does
                if prelude.lstrip().startswith("@"):
                    inner_roots, inner_rest = _strip_root_blocks(body[1:-1])
                    roots.append(inner_roots)
                    rest.append(prelude + "{" + inner_rest + "}")
                else:
                    rest.append(prelude + body)
            i = start = j
            continue
        i += 1
    rest.append(css[start:])
    return "".join(roots), "".join(rest)


# border-* is a colour property only sometimes: border-radius, border-width and
# border-style start with "border" and carry no palette decision at all. Counting
# them would let var(--radius) inflate the colour-tokenisation ratio.
_BORDER_NON_COLOR = ("-radius", "-width", "-style", "-spacing", "-collapse",
                     "-image")


def _is_color_property(prop: str) -> bool:
    p = prop.strip().lower()
    if p.endswith("-color"):
        return True
    if p.startswith("border"):
        return not any(x in p for x in _BORDER_NON_COLOR)
    return p in {"color", "background", "outline", "fill", "stroke",
                 "box-shadow", "text-shadow", "filter"}


def _css_design_tokens(css: str) -> dict:
    """Report on the stylesheet's use of design tokens.

    Returns root_props (the custom properties :root declares), plus how many
    colour declarations outside :root reference a token versus hard-code a
    value, and up to five examples of the latter."""
    roots, rest = _strip_root_blocks(css or "")
    root_props = sorted(set(re.findall(r"(--[\w-]+)\s*:", roots)))

    tokenised, literal, examples = 0, 0, []
    for prop, value in re.findall(r"([-a-zA-Z]+)\s*:\s*([^;{}]+)", rest):
        clean = _URL_RE.sub("", value).strip()
        low = clean.lower()
        if low in _COLOR_KEYWORDS_OK:
            continue
        words = set(re.findall(r"[a-z-]+", low))
        has_literal = bool(_COLOR_LITERAL_RE.search(clean)) or bool(
            words & _NAMED_COLORS)
        if has_literal:
            literal += 1
            if len(examples) < 5:
                examples.append(f"{prop.strip()}: {clean[:44]}")
        elif "var(--" in low and _is_color_property(prop):
            tokenised += 1
    total = tokenised + literal
    return {"root_props": root_props, "tokenised": tokenised,
            "literal": literal, "total": total, "examples": examples,
            "coverage": (tokenised / total) if total else 1.0}


# Selectors that are SUPPOSED to match nothing while the page sits at rest: a
# state variant only applies after an interaction, and a pseudo-element is not a
# DOM node. Flagging them would train the agent to delete correct CSS.
_VARIANT_MARKERS = ("[aria-", "[data-", ":hover", ":focus", ":active",
                    ":checked", ":disabled", ":target", "::")


def _rule_preludes(css: str):
    """Yield the selector prelude of every rule, stepping INTO @media wrappers.

    Deliberately local rather than reusing _css_prelude_blocks: that helper is
    defined in a LATER cell, so calling it here would make the test cell
    directly below this one fail with NameError on a straight top-to-bottom run.
    """
    i = start = 0
    n = len(css)
    while i < n:
        if css[i] == "{":
            prelude = css[start:i].strip()
            depth, j = 1, i + 1
            while j < n and depth:
                if css[j] == "{":
                    depth += 1
                elif css[j] == "}":
                    depth -= 1
                j += 1
            if prelude.startswith("@"):
                for inner in _rule_preludes(css[i + 1:j - 1]):
                    yield inner
            else:
                yield prelude
            i = start = j
            continue
        i += 1


def _css_dead_selectors(css: str, html: str, limit: int = 8) -> list:
    """Rules whose selector matches no element in the page.

    The reverse of the coverage guard. store_css_code already checks every spec
    className HAS a rule; nothing checked that a rule HAS an element. On
    2026-08-10 the CSS agent styled the price with `.product-card strong` while
    the HTML agent wrote `<span>`, so the price silently inherited the muted
    paragraph colour and rendered as secondary text. Both files were valid, both
    linters were clean, and every test passed."""
    if not css or not html:
        return []
    try:
        soup = BeautifulSoup(html, "html.parser")
    except Exception:
        return []
    dead = []
    for prelude in _rule_preludes(css):
        for sel in (p.strip() for p in prelude.split(",")):
            if not sel or sel.startswith(("@", ":root", "*")):
                continue
            if any(m in sel for m in _VARIANT_MARKERS):
                continue
            try:
                if not soup.select(sel):
                    dead.append(sel)
            except Exception:
                continue          # a selector bs4 cannot parse is not evidence
    out = sorted(set(dead))
    return out[:limit] + ([f"(+{len(out) - limit} more)"] if len(out) > limit else [])


# Two fix attempts, then the stylesheet is saved with a loud note. The number
# matches _LINT_ATTEMPT_CAP's budget rather than its literal value: that
# counter counts lint RUNS (1 initial + 2 fixes = 3), this one counts
# REFUSALS, and a refusal IS a fix request, so two refusals is the same two
# attempts. Past the cap the guard stops refusing, because a stylesheet the
# agent cannot repair must still reach disk.
_CSS_DRIFT_ATTEMPT_CAP = 2


def _css_drifted_selectors(css: str, html: str, limit: int = 8) -> list:
    """The narrow, objective half of _css_dead_selectors: rules whose CONTAINER
    is on the page but whose descendant is not.

    The two look identical in a dead-selector list and are completely
    different defects:

        img                       -- a reset rule. The page simply has no
                                     <img>. Refusing this would train the
                                     agent to delete correct CSS.
        .roast-level-nav button   -- .roast-level-nav IS on the page, so the
                                     agent found the component and then
                                     guessed the wrong tag for its child. The
                                     markup says <a>.

    Only the second kind is refused, and only because the fix is a lookup
    rather than a judgement call: the container's real children are right
    there to name, so the message can hand them over. That is what keeps this
    a guard and not a wall.

    Run po018f8158 shipped 18 dead selectors. This rule splits them 14 drifted
    / 4 reset, and the 14 left the navigation, the pagination and the product
    headings unstyled while html-validate and stylelint both stayed clean.

    Returns (selector, missing_part, container, real_children) tuples.
    """
    import collections
    if not css or not html:
        return []                 # no page to compare against: fail OPEN
    try:
        soup = BeautifulSoup(html, "html.parser")
    except Exception:
        return []
    out, seen = [], set()
    for prelude in _rule_preludes(css):
        for sel in (p.strip() for p in prelude.split(",")):
            if not sel or sel in seen or sel.startswith(("@", ":root", "*")):
                continue
            if any(m in sel for m in _VARIANT_MARKERS):
                continue
            parts = sel.split()
            if len(parts) < 2:
                continue          # a bare element rule is a reset, never drift
            seen.add(sel)
            try:
                if soup.select(sel):
                    continue
            except Exception:
                continue          # a selector bs4 cannot parse is not evidence
            for k in range(len(parts) - 1, 0, -1):
                container = " ".join(parts[:k])
                try:
                    hit = soup.select(container)
                except Exception:
                    hit = []
                if not hit:
                    continue
                kids = collections.Counter()
                for el in hit[:12]:
                    for d in el.find_all(True):
                        kids[d.name] += 1
                real = ", ".join("<%s>" % t for t, _ in kids.most_common(6))
                out.append((sel, " ".join(parts[k:]), container,
                            real or "(no child elements at all)"))
                break
    return out[:limit]


# A rule counts as styling a region only if it NAMES something: an id, a class
# or an attribute. `*`, `body` and bare tag rules are the reset, and a reset
# gives no region its gutter -- treating them as coverage would let a page pass
# with every section unstyled, which is the exact defect this catches.
_CSS_SPECIFIC_SELECTOR = re.compile(r"[#.\[]")


def _layout_region_names(layout_spec) -> list:
    """(name, ownedBy) for every region this run's layout declares."""
    spec = _coerce_spec(layout_spec or {}) or {}
    out = []
    if not isinstance(spec, dict):
        return out
    for page in spec.get("pages") or []:
        if not isinstance(page, dict):
            continue
        for r in (page.get("regions") or []):
            if isinstance(r, dict) and r.get("name"):
                out.append((str(r["name"]), str(r.get("ownedBy") or "")))
    return out


def _css_unstyled_regions(css: str, html: str, layout_spec, limit: int = 8) -> list:
    """Layout regions whose ENTIRE subtree is reached by no specific rule.

    Deliberately not "the <section> itself must be styled". On this project the
    gutter usually sits on an inner panel (.hero-section inside #hero), so
    demanding a rule on the container would refuse seven correct regions out of
    nine. Asking whether ANYTHING inside the region is styled refuses two out of
    nine on run po018f8158 -- filter-sort-bar and cart-drawer, which are exactly
    the two that rendered flush against the window edge, and nothing else.

    Returns (name, ownedBy) tuples.
    """
    rows = _layout_region_names(layout_spec)
    if not rows or not css or not html:
        return []                 # nothing to compare against: fail OPEN
    try:
        soup = BeautifulSoup(html, "html.parser")
    except Exception:
        return []
    styled = set()
    for prelude in _rule_preludes(css):
        for sel in (p.strip() for p in prelude.split(",")):
            if not sel or sel.startswith(("@", ":root")):
                continue
            if not _CSS_SPECIFIC_SELECTOR.search(sel):
                continue
            try:
                for el in soup.select(sel):
                    styled.add(id(el))
            except Exception:
                continue
    bad = []
    for name, owner in rows:
        el = soup.select_one("#%s" % name) or soup.select_one(".%s" % name)
        if el is None:
            continue              # the page never emitted it; a different defect
        if not any(id(d) in styled for d in [el] + el.find_all(True)):
            bad.append((name, owner))
    return bad[:limit]


# ── Decoration Colour Contract ──────────────────────────────────────────────
# The Design Token Contract asks the agent to name its colours once and reuse
# them. The DecorationSpecification pins exact literal values. Until 2026-08-11
# nothing connected the two, so an agent could obey both and still disagree with
# the spec: in E2E-SO-01 session so2029f0 the card was specified
# `border: 1px solid #dddddd`, the agent tokenised it to its own --color-border
# (#d9e2ec), and assert_css compared the COMPUTED value and failed. One
# correction per run, every run, for a conflict between two of our own rules.
#
# The fix is symmetric with the rest of the system. The prompt seeds the palette
# from the spec (below, _decoration_token_seed) so the agent knows the values
# before it writes anything, and this guard refuses a stylesheet that lost one.
# Naming a value as a token is still encouraged -- only the VALUE is pinned.
_CSS_NAMED_COLORS = {
    "white": (255, 255, 255), "black": (0, 0, 0), "red": (255, 0, 0),
    "green": (0, 128, 0), "blue": (0, 0, 255), "gray": (128, 128, 128),
    "grey": (128, 128, 128), "silver": (192, 192, 192),
}


def _norm_colors(text: str) -> set:
    """Every colour in `text`, normalised to an (r, g, b) tuple.

    Alpha is dropped: assert_css compares the rendered colour, and two values
    differing only in alpha are a different problem from the one this guard is
    for. Anything unparseable is simply not returned, so an exotic notation in
    the spec fails OPEN (no colour recorded, so nothing to refuse) rather than
    producing a refusal the agent cannot act on.
    """
    out = set()
    if not isinstance(text, str):
        return out
    for h in re.findall(r"#([0-9a-fA-F]{3,8})\b", text):
        if len(h) in (3, 4):
            h = "".join(ch * 2 for ch in h[:3])
        elif len(h) in (6, 8):
            h = h[:6]
        else:
            continue
        out.add(tuple(int(h[k:k + 2], 16) for k in (0, 2, 4)))
    for body in re.findall(r"rgba?\(([^)]*)\)", text, re.I):
        parts = re.split(r"[,/\s]+", body.strip())
        nums = []
        for p in parts[:3]:
            p = p.strip()
            try:
                nums.append(int(round(float(p[:-1]) * 255 / 100)) if p.endswith("%")
                            else int(round(float(p))))
            except ValueError:
                break
        if len(nums) == 3 and all(0 <= n <= 255 for n in nums):
            out.add(tuple(nums))
    for word, rgb in _CSS_NAMED_COLORS.items():
        if re.search(r"\b%s\b" % word, text, re.I):
            out.add(rgb)
    return out


def _spec_pinned_colors(decoration_spec) -> list:
    """(componentId, property, value, {rgb}) for every spec style naming a colour."""
    spec = _coerce_spec(decoration_spec or {}) or {}
    pinned = []
    if not isinstance(spec, dict):
        return pinned
    for page in spec.get("pages") or []:
        if not isinstance(page, dict):
            continue
        for d in page.get("componentDecorations") or []:
            if not isinstance(d, dict):
                continue
            cid = d.get("componentId") or d.get("className") or "?"
            groups = [d.get("baseStyles") or {}]
            for sv in d.get("stateVariants") or []:
                if isinstance(sv, dict):
                    groups.append(sv.get("styles") or {})
            for styles in groups:
                if not isinstance(styles, dict):
                    continue
                for prop, val in styles.items():
                    cols = _norm_colors(val if isinstance(val, str) else "")
                    if cols:
                        pinned.append((cid, prop, val, cols))
    return pinned


def _decoration_color_gaps(css: str, decoration_spec) -> list:
    """One message per specified colour that never appears in the stylesheet.

    Presence anywhere counts, so `--color-card-border: #dddddd` in :root passes
    exactly as an inline literal does. The contract pins the VALUE, never the
    spelling, so tokenising stays free.
    """
    have = _norm_colors(css or "")
    bad = []
    for cid, prop, val, cols in _spec_pinned_colors(decoration_spec):
        missing = cols - have
        if missing:
            shown = ", ".join("rgb%s" % (m,) for m in sorted(missing))
            bad.append(
                f"'{cid}' is specified `{prop}: {val}` but {shown} appears nowhere "
                f"in the stylesheet")
    return bad


def _decoration_token_seed(state) -> str:
    """Prompt appendix: the exact colour values the test suite will assert."""
    pinned = _spec_pinned_colors((state or {}).get("decoration_specification"))
    if not pinned:
        return ""
    seen, rows = set(), []
    for cid, prop, val, _ in pinned:
        key = (cid, prop, val)
        if key in seen:
            continue
        seen.add(key)
        rows.append("  %-24s %-18s %s" % (cid, prop, val))
    return (
        "\n\n## Colour values pinned by the decoration specification\n"
        "The generated test suite asserts these as COMPUTED values, so a colour "
        "that is merely close will fail:\n\n"
        + "\n".join(rows) +
        "\n\nName them as custom properties -- that is what the Design Token "
        "Contract asks for -- but the property's VALUE must be the value above, "
        "not a neighbouring shade from a palette of your own. Seed `:root` with "
        "these first, then build the rest of the palette around them.\n"
        "store_css_code refuses a stylesheet in which one of these values does "
        "not appear at all.\n"
    )


# ═══════════════════════════════════════════════════════════════════════════
# Spec Base Styles - Python writes what the decoration specification pins
#
# The decoration specification already fixes each component's resting styles,
# and the test suite asserts exactly those values. Asking the model to copy them
# is "LLMs decide" applied to a job with nothing left to decide, and it failed
# the expensive way: on 741c7b34, 13 of the 22 failing components had NO rule in
# the stylesheet at all, and every such miss buys a correction round (~140 s,
# a second CSS pass and a second Playwright run).
#
# So Python writes them, in one block AFTER the model's own CSS: appearance
# (colour, type, spacing, borders, the :root tokens) then wins over a
# same-selector rule of the model's. On the saved pages, placing it first only
# cut assert_css failures 56 -> 47; placing it last, 56 -> 41. A higher-
# specificity rule of the model's (a state, `[data-state=open]`) still wins.
# ═══════════════════════════════════════════════════════════════════════════
_SPEC_BASE_START = "/* webforge:spec-base:start - written from decoration_specification */"
_SPEC_BASE_END = "/* webforge:spec-base:end */"
_SPEC_BLOCKS_RE = re.compile(
    re.escape(_SPEC_BASE_START) + r".*?" + re.escape(_SPEC_BASE_END) + r"\s*", re.S)
_SPEC_CLASS_RE = re.compile(r"^-?[A-Za-z_][A-Za-z0-9_-]*$")
_SPEC_PROP_RE = re.compile(r"^-{0,2}[A-Za-z][A-Za-z0-9-]*$")
# State names with a pseudo-class that needs no help from the HTML. Every other
# state (open, disabled, selected...) is materialised by HTML/JS attributes the
# model owns, so it stays the model's to style.
_SPEC_STATE_PSEUDO = {"hover": ":hover", "focus": ":focus-visible",
                      "focus-visible": ":focus-visible", "active": ":active"}
# Properties a component's open/closed/shown state is made of. A drawer's spec
# can describe its OPEN look; pinning that would force the closed drawer open
# (the PO-10 always-open drawer), and even as front-of-file defaults a spec
# value the model never restates goes live (a trial on 770d6ef0 left an overlay
# catching clicks). So on a STATEFUL component (one with an open/selected/...
# stateVariant) they are not written at all: state stays the model's job.
# Everything else (colour, type, spacing, borders) goes at the END, where it
# wins over a same-selector rule of the model's.
_SPEC_STATE_PROPS = frozenset({"display", "visibility", "opacity", "transform",
                               "translate", "pointer-events", "max-height"})


def _spec_declarations(styles) -> list:
    """(prop, 'prop: value;') pairs for one styles dict; anything unsafe is skipped."""
    out = []
    if not isinstance(styles, dict):
        return out
    for prop, val in styles.items():
        if isinstance(val, bool) or val is None or isinstance(val, (dict, list)):
            continue
        prop = re.sub(r"(?<!^)(?=[A-Z])", "-", str(prop).strip()).lower()
        val = str(val).strip()
        if not val or not _SPEC_PROP_RE.match(prop) or any(c in val for c in ";{}"):
            continue
        out.append((prop, f"{prop}: {val};"))
    return out


def _spec_media_query(rv: dict) -> str:
    parts = []
    if rv.get("minWidth"):
        parts.append(f"(min-width: {rv['minWidth']})")
    if rv.get("maxWidth"):
        parts.append(f"(max-width: {rv['maxWidth']})")
    return " and ".join(parts)


# A state name that shows or hides the component. Matched as a substring so
# 'is-open', 'menuOpen', 'collapsed' all count.
_SPEC_TOGGLE_STATE_RE = re.compile(r"open|clos|expand|collaps|hidden|visib|show", re.I)


def _toggle_classes(components_spec) -> set:
    """classNames of components whose states show or hide them, from the
    components specification (any depth)."""
    found, stack = set(), [_coerce_spec(components_spec or {}) or {}]
    while stack:
        node = stack.pop()
        if isinstance(node, list):
            stack.extend(node)
        elif isinstance(node, dict):
            names = [st.get("name", "") if isinstance(st, dict) else str(st)
                     for st in node.get("states") or []]
            if node.get("className") and any(_SPEC_TOGGLE_STATE_RE.search(n or "") for n in names):
                found.add(str(node["className"]).strip())
            stack.extend(v for v in node.values() if isinstance(v, (dict, list)))
    return found


def _spec_base_css(decoration_spec, components_spec=None) -> str:
    """The pinned stylesheet block the decoration specification implies, or ''.

    The global tokens as :root, then one rule per component on its Selector
    Contract name (`.className`): its baseStyles, its hover/focus/active
    stateVariants and its responsive variants. A stateful component's
    state-coupled properties (_SPEC_STATE_PROPS) are left out."""
    spec = _coerce_spec(decoration_spec or {}) or {}
    if not isinstance(spec, dict):
        return ""
    rules, media = [], []
    toggles = _toggle_classes(components_spec)

    tokens = []
    gt = spec.get("globalTokens") or {}
    if isinstance(gt, dict):
        for bucket in gt.values():
            if isinstance(bucket, dict):
                for k, v in bucket.items():
                    if (isinstance(k, str) and k.startswith("--") and _SPEC_PROP_RE.match(k)
                            and isinstance(v, (str, int, float)) and not isinstance(v, bool)
                            and str(v).strip() and not any(c in str(v) for c in ";{}")):
                        tokens.append(f"{k}: {str(v).strip()};")
    if tokens:
        rules.append(":root { " + " ".join(tokens) + " }")

    def rule(sel, styles, stateful):
        decls = [d for p, d in _spec_declarations(styles)
                 if not (stateful and p in _SPEC_STATE_PROPS)]
        return f"{sel} {{ " + " ".join(decls) + " }" if decls else ""

    for page in spec.get("pages") or []:
        if not isinstance(page, dict):
            continue
        for d in page.get("componentDecorations") or []:
            if not isinstance(d, dict):
                continue
            cls = str(d.get("className") or "").strip()
            if not _SPEC_CLASS_RE.match(cls):
                continue
            sel = "." + cls
            # A component the HTML/JS shows and hides (open, expanded,
            # collapsed...) is stateful: its display/visibility/transform are
            # the model's. A plain grid or card keeps them pinned.
            stateful = cls in toggles or any(
                isinstance(sv, dict) and
                _SPEC_TOGGLE_STATE_RE.search(str(sv.get("stateName", "")))
                for sv in d.get("stateVariants") or [])
            r = rule(sel, d.get("baseStyles"), stateful)
            if r:
                rules.append(r)
            for sv in d.get("stateVariants") or []:
                if not isinstance(sv, dict):
                    continue
                pseudo = _SPEC_STATE_PSEUDO.get(str(sv.get("stateName", "")).lower())
                r = rule(sel + pseudo, sv.get("styles"), stateful) if pseudo else ""
                if r:
                    rules.append(r)
            for rv in d.get("responsiveStyles") or []:
                if not isinstance(rv, dict):
                    continue
                mq, r = _spec_media_query(rv), rule(sel, rv.get("styles"), stateful)
                if mq and r:
                    media.append(f"@media {mq} {{ {r} }}")
    if not rules and not media:
        return ""
    # It repeats the model's selectors on purpose, so stylelint's duplicate-
    # selector rule is switched off for the block only.
    return "\n".join([_SPEC_BASE_START,
                      "/* stylelint-disable no-duplicate-selectors */",
                      *rules, *media,
                      "/* stylelint-enable no-duplicate-selectors */",
                      _SPEC_BASE_END]) + "\n"


def _spec_base_prompt_block(state) -> str:
    """Generation prompt appendix: the block Python will append, so the model
    neither repeats it nor fights it."""
    block = _spec_base_css((state or {}).get("decoration_specification"),
                           (state or {}).get("components_specification"))
    if not block:
        return ""
    return (
        "\n\n## Spec styles written for you\n"
        "store_css_code appends the block below to the END of your stylesheet. "
        "It carries the :root tokens and every value the decoration "
        "specification pins, and the test suite asserts exactly these values.\n"
        "- Do NOT restate these declarations. Spend your output on what the "
        "block leaves out: layout (grid/flex, widths, gutters, gaps), responsive "
        "rules, open/closed and other state rules, and anything the spec does "
        "not state.\n"
        "- A rule of yours with the SAME selector cannot change a value here, "
        "because the block comes later. A more specific selector (a state such "
        "as `[data-state=\"open\"]`, a descendant) still can.\n\n"
        + block)


def _close_truncated_css(css: str) -> str:
    """Make a stylesheet cut off mid-way safe to append to.

    A model output that stops early (741c7b34 ends `.featured-bean-price,
    .brew-method-price` with no block) would swallow whatever follows into its
    selector. A dangling selector with no `{` is dropped (it carries no
    declarations); an unclosed block is closed."""
    last = css.rfind("}")
    tail = css[last + 1:]
    if tail.strip() and "{" not in tail and ";" not in tail and "*/" not in tail:
        css = css[:last + 1]
    depth = css.count("{") - css.count("}")
    if depth > 0:
        css = css.rstrip() + "\n" + "}" * depth
    return css


def _retarget_css_selectors(css: str, mapping: dict) -> tuple:
    """Rewrite selectors in place: (new_css, names_not_found).

    mapping is {selector as written: replacement}. A selector is ONE
    comma-separated part of a rule's prelude, compared with whitespace
    collapsed, so 'a svg' matches the part `a   svg` and never the longer
    `nav a svg` or `a svg:hover`. Every occurrence is rewritten, inside @media
    blocks too. An empty replacement deletes that part, and the whole rule
    when no part is left. Declarations are never touched.

    This is what lets a drift refusal be answered with the selector alone. On
    PO-08 4fb17fbe the fix for one drifted selector was a second full
    stylesheet: 6,051 output tokens and 50.6 s to change one line.
    """
    def _norm(sel):
        return " ".join(str(sel).split())

    # A replacement is a selector and nothing else: one holding a brace or a
    # semicolon would rewrite the rule's body, so it is left unapplied and
    # its key is reported as not found.
    wanted = {_norm(k): str(v).strip() for k, v in (mapping or {}).items()
              if _norm(k) and not any(ch in str(v) for ch in "{};")}
    asked = [_norm(k) for k in (mapping or {}) if _norm(k)]
    found = set()

    def _lead(text):
        return text[:len(text) - len(text.lstrip())]

    def rewrite(text):
        out, i, start, n = [], 0, 0, len(text)
        while i < n:
            if text[i] != "{":
                i += 1
                continue
            prelude = text[start:i]
            depth, j = 1, i + 1
            while j < n and depth:
                if text[j] == "{":
                    depth += 1
                elif text[j] == "}":
                    depth -= 1
                j += 1
            if prelude.strip().startswith("@"):
                inner_end = j - 1 if depth == 0 else j
                inner = text[i + 1:inner_end]
                new_inner = rewrite(inner)
                if new_inner != inner and not new_inner.strip():
                    # the at-rule lost its only rule: an empty block is a
                    # stylelint error (block-no-empty), so it goes too
                    out.append(_lead(prelude).rstrip(" \t"))
                else:
                    out.append(prelude + "{" + new_inner + text[inner_end:j])
            else:
                parts = prelude.split(",")
                hit = {k for k, part in enumerate(parts) if _norm(part) in wanted}
                if not hit:
                    out.append(text[start:j])
                else:
                    kept = []
                    for k, part in enumerate(parts):
                        if k not in hit:
                            kept.append(part)
                            continue
                        found.add(_norm(part))
                        new = wanted[_norm(part)]
                        if new:
                            kept.append(_lead(part) + new + part[len(part.rstrip()):])
                    if kept:
                        # a deleted first part took the rule's leading blank
                        # space with it: the rule still starts where it did
                        # ...and a deleted last part took the space before
                        # the brace: the rule still ends as it did
                        tail = prelude[len(prelude.rstrip()):]
                        out.append(_lead(prelude) + ",".join(kept).strip() + tail + text[i:j])
                    else:
                        out.append(_lead(prelude).rstrip(" \t"))
            i = start = j
        out.append(text[start:])
        return "".join(out)

    new_css = rewrite(css or "")
    return new_css, [k for k in asked if k not in found]


def _with_spec_base(css_code: str, decoration_spec, components_spec=None) -> str:
    """css_code with a fresh pinned spec block at the end. Idempotent: an older
    block, wherever the model left it, is replaced rather than duplicated."""
    body = _SPEC_BLOCKS_RE.sub("", css_code or "").strip()
    body = _close_truncated_css(body)
    pinned = _spec_base_css(decoration_spec, components_spec)
    return body + ("\n\n" + pinned if pinned else "\n")


def _store_css_code_checked(css_code: str, runtime) -> Command:
    """Everything store_css_code checks and saves, for a stylesheet in hand.
    The tool below adds one step in front: turning a `retarget` answer into
    that stylesheet."""
    intent     = runtime.state.get("intent", "generate")
    session_id = runtime.state.get("session_id", "")
    _drift        = []
    _drift_n      = runtime.state.get("coverage_attempts", 0)
    css_code      = css_code or ""
    if not css_code.strip():
        return Command(update={"messages": [ToolMessage(
            content="store_css_code needs css_code: the full stylesheet.",
            tool_call_id=runtime.tool_call_id)]})
    # What the model wrote, before the spec base goes in: the copy a drift
    # refusal holds, so a retarget is applied to the model's own text.
    _submitted = css_code

    if intent == "generate":
        decoration_spec = _coerce_spec(
            runtime.state.get("decoration_specification") or {})
        if decoration_spec is None:
            return Command(update={"messages": [ToolMessage(
                content=(
                    "[INTERNAL] decoration_specification is a string that is "
                    "not valid JSON, so the coverage check cannot run. This is "
                    "a pipeline configuration error, not a defect in your CSS. "
                    "Report it in your final message and stop."
                ),
                tool_call_id=runtime.tool_call_id
            )]})
        # Spec Base Styles: the pinned values go in by code, ahead of every
        # check below, so each check sees the stylesheet that will be saved.
        css_code = _with_spec_base(
            css_code, decoration_spec,
            runtime.state.get("components_specification"))
        class_names = set()
        for page in (decoration_spec.get("pages") or []):
            for cd in (page.get("componentDecorations") or []):
                cn = cd.get("className")
                if cn:
                    class_names.add(cn)
        missing = sorted(
            cn for cn in class_names
            if not re.search(rf"\.{re.escape(cn)}\b", css_code)
        )
        if missing:
            return Command(update={"messages": [ToolMessage(
                content=(
                    f"Coverage check failed — decoration_specification component(s) "
                    f"with NO matching CSS rule: {missing}. Add a '.<className>' rule "
                    f"for each (from baseStyles) and call store_css_code again."
                ),
                tool_call_id=runtime.tool_call_id
            )]})

        # ── CSS/DOM Drift Contract ───────────────────────────────────────
        # The reverse of the coverage check above: that one asks whether every
        # specified component HAS a rule, this one asks whether every rule HAS
        # an element. Only the objective half is refused (see
        # _css_drifted_selectors); the rest stays advisory below.
        _drift = _css_drifted_selectors(
            css_code, _read_preview_source(session_id, "html"))
        if _drift and _drift_n < _CSS_DRIFT_ATTEMPT_CAP:
            _rows = "\n".join(
                f"  {sel}\n"
                f"      '{cont}' is on the page, but nothing inside it matches "
                f"'{miss}'. Its real children are: {real}"
                for sel, miss, cont, real in _drift)
            _example = json.dumps({_drift[0][0]: "<selector that matches>"})
            return Command(update={
                "coverage_attempts": _drift_n + 1,
                "css_pending": _submitted,
                "messages": [ToolMessage(
                    content=(
                        "CSS/DOM drift - each of these rules names a container "
                        "that EXISTS and then a descendant that does not, so "
                        "every declaration inside them applies to nothing:\n"
                        + _rows +
                        "\n\nRewrite each against the tag the page actually "
                        "uses (the page you read at Step 0), or delete the rule "
                        "if the element is genuinely gone. A rule that matches "
                        "nothing is not harmless leftover weight: on run "
                        "po018f8158 fourteen of them left the navigation, the "
                        "pagination and the product headings unstyled while "
                        "html-validate and stylelint both reported clean.\n\n"
                        "Do NOT send the stylesheet again: it is held exactly "
                        "as you wrote it. Answer with the selectors alone, "
                        "store_css_code(retarget=" + _example + "), one entry "
                        "per rule above, keyed by the selector as printed. An "
                        "empty string deletes that rule. "
                        f"(attempt {_drift_n + 1} of {_CSS_DRIFT_ATTEMPT_CAP})"),
                    tool_call_id=runtime.tool_call_id)]})

        # ── Region Coverage Contract ─────────────────────────────────────
        # Shares _drift_n, so drift and region gaps together get two fix
        # attempts, not two each. Both are "the stylesheet does not match the
        # page", and letting them each spend a budget could stall a run.
        _bare = _css_unstyled_regions(
            css_code, _read_preview_source(session_id, "html"),
            runtime.state.get("layout_specification"))
        if _bare and _drift_n < _CSS_DRIFT_ATTEMPT_CAP:
            _rows = "\n".join(
                f"  #{name}   (ownedBy: {owner or 'unspecified'})"
                for name, owner in _bare)
            return Command(update={
                "coverage_attempts": _drift_n + 1,
                "messages": [ToolMessage(
                    content=(
                        "Region coverage - these layout regions are on the page "
                        "and NOTHING inside them is reached by any rule of "
                        "yours, so they render with no gutter, no width and no "
                        "background:\n" + _rows +
                        "\n\nGive each one container styling through its id, "
                        "the same page gutter and max-width the other regions "
                        "use. A region marked ownedBy: JavaScript still needs "
                        "this: JavaScript inserts its CONTENTS at runtime and "
                        "never supplies the container's inset. On run "
                        "po018f8158 the two JavaScript-owned regions were left "
                        "unstyled for exactly that reason and rendered flush "
                        "against the window edge. Fix and call store_css_code "
                        f"again. (attempt {_drift_n + 1} of "
                        f"{_CSS_DRIFT_ATTEMPT_CAP})"),
                    tool_call_id=runtime.tool_call_id)]})

        # ── Design Token Contract ────────────────────────────────────────
        tok = _css_design_tokens(css_code)
        color_gaps = _decoration_color_gaps(css_code, decoration_spec)
        if color_gaps:
            return Command(update={"messages": [ToolMessage(
                content=(
                    "Decoration Colour Contract violation(s) - the decoration "
                    "specification pins these exact values and the test suite "
                    "asserts the COMPUTED result, so a nearby shade fails: "
                    + "; ".join(color_gaps) +
                    ". Keep using custom properties, but give the property the "
                    "specified value (e.g. `--color-card-border: #dddddd`) rather "
                    "than a colour of your own. Fix and call store_css_code again."),
                tool_call_id=runtime.tool_call_id)]})

        if _DESIGN_TOKEN_ENFORCED and len(tok["root_props"]) < _DESIGN_TOKEN_MIN:
            return Command(update={"messages": [ToolMessage(
                content=(
                    f"Design Token Contract violation - the stylesheet declares "
                    f"{len(tok['root_props'])} custom propert(ies) in :root, and at "
                    f"least {_DESIGN_TOKEN_MIN} are required. Open the stylesheet "
                    "with a :root block naming the palette and scale ONCE, then "
                    "reference those names instead of repeating values:\n"
                    "  :root {\n"
                    "    --color-primary: #0f62fe;\n"
                    "    --color-surface: #ffffff;\n"
                    "    --color-text:    #1f2933;\n"
                    "    --color-border:  #d9e2ec;\n"
                    "    --radius:        12px;\n"
                    "    --space:         8px;\n"
                    "  }\n"
                    "  .product-card { background: var(--color-surface); "
                    "border: 1px solid var(--color-border); }\n"
                    "Declared so far: "
                    + (", ".join(tok["root_props"]) or "(none)")
                    + "\nAdd the block and call store_css_code again."),
                tool_call_id=runtime.tool_call_id
            )]})

    saved = "CSS code saved to state."
    if intent == "generate" and not _DESIGN_TOKEN_ENFORCED \
            and len(tok["root_props"]) < _DESIGN_TOKEN_MIN:
        # Arm B: measured, reported, not blocked. Never silent -- an unenforced
        # run that said nothing would look like a passing one in the transcript.
        saved += (f"\n\n[UNENFORCED] Design Token Contract would have REFUSED this "
                  f"submission: {len(tok['root_props'])} of {_DESIGN_TOKEN_MIN} "
                  f"required custom properties in :root. Recorded, not blocked "
                  f"(_DESIGN_TOKEN_ENFORCED is False).")
    if intent == "generate" and _drift:
        # Reached only past _CSS_DRIFT_ATTEMPT_CAP. Never silent: a stylesheet
        # saved with known drift must say so, or the transcript reads like a
        # clean run.
        saved += ("\n\n[DRIFT CAP REACHED] Saved with "
                  f"{len(_drift)} rule(s) still matching no element: "
                  + ", ".join(d[0] for d in _drift) +
                  ". Two fix attempts were spent and the drift remains, so the "
                  "stylesheet was stored rather than lost. Report this in your "
                  "final message.")
    if intent == "generate":
        # What is left after the refusal above: bare element rules in a reset,
        # and defensive selectors (.card h1, h2, h3 covering whichever level is
        # used). Both are legitimate, which is exactly why this half stays
        # advisory -- it is a matter of degree, and refusing on a degree could
        # spin the uncapped coverage-retry loop.
        _drifted_sels = {d[0] for d in _drift}
        _dead = [d for d in _css_dead_selectors(
            css_code, _read_preview_source(session_id, "html"), limit=10 ** 6)
            if d not in _drifted_sels][:8]
        if _dead:
            saved += ("\n\nADVISORY (not a rejection - the CSS is saved): "
                      f"{len(_dead)} rule(s) match no element in the page: "
                      + ", ".join(_dead) +
                      ". Either the HTML uses a different tag (styling `strong` "
                      "when the markup says `span` leaves the text unstyled and "
                      "no test can see it) or the rule is dead weight. Check the "
                      "page you read at Step 0 before deciding.")

    # Advisory, never a refusal -- see the note on _TOKEN_COVERAGE_MIN.
    if intent == "generate" and tok["literal"] > _TOKEN_FREE_LITERALS \
            and tok["coverage"] < _TOKEN_COVERAGE_MIN:
        saved += (
            f"\n\nADVISORY (not a rejection - the CSS is saved): only "
            f"{tok['coverage']:.0%} of the {tok['total']} colour declarations "
            f"outside :root use var(--...), below the {_TOKEN_COVERAGE_MIN:.0%} "
            f"target. Hard-coded colours make the palette impossible to change "
            f"in one place. Examples: " + "; ".join(tok["examples"]) +
            ". If you revise, replace those literals with the :root tokens and "
            "call store_css_code again. Do NOT add new rules for this.")

    return Command(update={
        "css_code": css_code,
        "css_pending": "",
        "messages": [ToolMessage(
            content=saved,
            tool_call_id=runtime.tool_call_id
        )]
    })


@tool
def store_css_code(css_code: str = "", runtime: ToolRuntime[CssState] = None,
                   retarget: dict = None) -> Command:
    """
    Store the generated or revised CSS code into agent state.
    Must be called every time after generating or revising CSS,
    before calling run_css_validate.

    On Generation Mode calls (intent="generate"), also enforces a coverage
    check: every component in decoration_specification must have at least
    one matching '.<className>' rule in the CSS. Modification Mode is exempt
    (an existing component's styles are edited via apply_and_lint_css, not
    this tool).

    retarget: use ONLY to answer a "CSS/DOM drift" refusal, and then leave
    css_code empty. The refused stylesheet is held; pass
    {"<drifted selector>": "<selector that matches the page>"} and each named
    selector is rewritten in it (an empty string deletes that rule). The
    stylesheet is not sent again.
    """

    if not retarget or (css_code or "").strip():
        return _store_css_code_checked(css_code, runtime)

    # ── Answering a drift refusal with the selector alone (ticket 05) ────
    def _refuse(msg, **extra):
        return Command(update={**extra, "messages": [ToolMessage(
            content=msg, tool_call_id=runtime.tool_call_id)]})

    if not isinstance(retarget, dict):
        return _refuse('retarget must be an object: {"<drifted selector>": '
                       '"<selector that matches the page>"}.')
    _held = runtime.state.get("css_pending") or ""
    if not _held.strip():
        return _refuse(
            "retarget rewrites selectors in a stylesheet a drift refusal is "
            "holding, and nothing is held. Send the full stylesheet as "
            "css_code instead.")
    _new_css, _unknown = _retarget_css_selectors(_held, retarget)
    if _unknown:
        _now = [d[0] for d in _css_drifted_selectors(
            _with_spec_base(_held, _coerce_spec(
                runtime.state.get("decoration_specification") or {}) or {},
                runtime.state.get("components_specification")),
            _read_preview_source(runtime.state.get("session_id", ""), "html"))]
        # A wrong answer spends an attempt, so the drift cap ends a loop of
        # them, and the message names the other way out.
        return _refuse(
            "retarget could not be applied to: "
            f"{_unknown}. Each key must be a selector that is in the held "
            "stylesheet, written exactly as the refusal printed it"
            + (f" ({_now})" if _now else "")
            + ", and each value a selector alone, with no braces or "
            "semicolons. Nothing was changed. Answer again, or send the full "
            "stylesheet as css_code.",
            coverage_attempts=runtime.state.get("coverage_attempts", 0) + 1)

    out = _store_css_code_checked(_new_css, runtime)
    # The model's own copy of the stylesheet still has the old selectors. Say
    # what changed, so a later full send (a lint fix) keeps it, and on any
    # refusal hold the retargeted text, never the one before it.
    _changes = "; ".join(
        f"'{k}' -> " + (f"'{' '.join(str(v).split())}'" if str(v).strip() else "(rule deleted)")
        for k, v in retarget.items())
    update = dict(out.update)
    if "css_code" not in update:
        update["css_pending"] = _new_css
    _msg = update["messages"][0]
    update["messages"] = [ToolMessage(
        content=_msg.content + "\n\nYour retarget is applied to the held "
        "stylesheet: " + _changes + ". If you send css_code again, keep "
        "these changes in it.",
        tool_call_id=runtime.tool_call_id)]
    return Command(update=update)


# ==========================================================================
# extract_css_component
# ==========================================================================
import re as _re_cssres


def _css_component_aliases(component: str, decoration_spec=None) -> list:
    """Every name this component could appear under in the stylesheet.

    A correction work order names the specification ID (`add-to-cart-button`),
    while the stylesheet uses the className the Naming Contract requires
    (`.add-to-cart-btn`). A literal lookup therefore finds nothing and the CSS
    agent reports "no CSS blocks referenced that component" for a component that
    is right there -- observed in all four live Secondary Orchestrator scenarios
    on 2026-08-09, wasting a correction attempt every time.

    DecorationSpecification already carries both halves of the mapping
    (`componentId` and `className` on the same ComponentDecoration) and is
    already in the CSS agent's state, so nothing new has to be plumbed through.
    The space-collapsed form is included because the orchestrator has been seen
    to write "add-to-cart button" for `add-to-cart-button`.
    """
    seen, out = set(), []

    def add(name):
        if isinstance(name, str) and name.strip() and name not in seen:
            seen.add(name)
            out.append(name)

    add(component)
    norm = _re_cssres.sub(r"\s+", "-", (component or "").strip())
    add(norm)

    spec = _coerce_spec(decoration_spec or {}) or {}
    if isinstance(spec, dict):
        for page in spec.get("pages") or []:
            if not isinstance(page, dict):
                continue
            for d in page.get("componentDecorations") or []:
                if not isinstance(d, dict):
                    continue
                cid, cls = d.get("componentId"), d.get("className")
                if component in (cid, cls) or norm in (cid, cls):
                    add(cls)
                    add(cid)
    return out


def _resolve_css_component(css_code: str, component: str, decoration_spec=None):
    """Return (the alias that actually matched, its blocks). Falls back to the
    name given, with no blocks, so callers keep their existing not-found path.
    The search is the engine's (webforge.dev_agent.loop_resolve, ticket 09)."""
    label, spans = loop_resolve(CSS_LOOP, css_code, component, decoration_spec)
    return label, [css_code[a:b] for a, b in spans]


# A rule's selector may span several lines. Both functions below therefore
# accumulate the PRELUDE -- every line since the last block boundary -- and only
# inspect it once the opening brace arrives.
#
# Why this exists: the one-line version tested `component in line and "{" in
# line`, which cannot match a group the CSS agent writes as
#
#     .add-to-cart-btn,
#     button.add-to-cart-btn,
#     .product-card button {
#
# Line 1 carries the name and no brace, line 3 the brace and no name, so the
# extractor reported ZERO blocks for a stylesheet holding five. Because
# extract_css_component, store_css_diff and apply_and_lint_css all go through
# _extract_css_block_spans, that silently disabled the ENTIRE CSS modification
# path for any component styled by a group -- observed live in E2E-SO-01 on
# 2026-08-09, where it burned half a correction round and _css_selectors_present
# (same defect) then told the model the class did not exist.
_CSS_INLINE_COMMENT = _re_cssres.compile(r"/\*.*?\*/", _re_cssres.S)


def _css_prelude_blocks(css_code: str):
    """Yield (first_line, brace_line, selector_prelude) for every rule.

    A line carrying `{` whose prelude does NOT match is stepped over rather than
    skipped wholesale, so an `@media (...) {` wrapper still exposes the rules
    nested inside it -- the behaviour the one-line version had by accident and
    which must be preserved.
    """
    lines = css_code.splitlines(keepends=True)
    start, prelude = None, ""
    i = 0
    while i < len(lines):
        raw = lines[i]
        text = _CSS_INLINE_COMMENT.sub(" ", raw).strip()
        if start is None:
            if not text:
                i += 1
                continue
            start, prelude = i, text
        else:
            prelude += " " + text
        if "{" in raw:
            yield start, i, prelude.split("{", 1)[0].strip()
            start, prelude = None, ""
            i += 1
            continue
        if "}" in raw:                  # end of an @media wrapper resets the scan
            start, prelude = None, ""
        i += 1


def _css_selectors_present(css_code: str, limit: int = 12, prefer: str = "") -> list:
    """The selectors the stylesheet actually defines. Named in a not-found
    message so the model can correct itself instead of guessing again.

    A group is reported as its individual selectors, because that is what the
    model has to type back.

    `prefer` is the component that was being looked for. Selectors resembling it
    are listed FIRST, and a truncated list ends with a "(+N more)" marker. Both
    matter: on the real E2E-SO-01 stylesheet `.add-to-cart-btn` was the 20th
    selector, so a plain first-12 list omitted the exact name the model needed
    while reading as if it were the complete set -- a message that actively
    misleads is worse than no message.
    """
    out = []
    for _s, _b, sel in _css_prelude_blocks(css_code or ""):
        if not sel or sel.startswith(("@", "}")):
            continue
        for one in sel.split(","):
            one = one.strip()
            if one and one not in out:
                out.append(one)

    key = (prefer or "").strip().lstrip("#.").lower()
    if key:
        out.sort(key=lambda s: 0 if key in s.lower() else 1)   # stable
    if len(out) > limit:
        return out[:limit] + [f"(+{len(out) - limit} more)"]
    return out


def _extract_css_block_spans(css_code: str, component: str) -> list:
    """
    Return the (start, end) character span of every CSS rule block whose
    selector line references the component. Spans are used rather than plain
    text so blocks can be spliced back into their own positions even when two
    of them are textually identical.
    component may be a CSS selector (#id, .class, tag) or a bare component name.
    For bare names, also tries #name and .name patterns.
    Uses brace-depth counting to handle multi-line blocks correctly.
    """
    if component.startswith(('#', '.')):
        targets = [component]
    else:
        targets = [f'#{component}', f'.{component}', component]

    lines = css_code.splitlines(keepends=True)
    starts, pos = [], 0
    for ln in lines:
        starts.append(pos)
        pos += len(ln)
    starts.append(pos)                      # sentinel: end of file

    spans, consumed_to = [], -1
    for first, brace, sel in _css_prelude_blocks(css_code):
        if first <= consumed_to:            # nested inside a block already taken
            continue
        if not any(t in sel for t in targets):
            continue
        # Walk to the matching close. `seen` is required: a prelude spanning
        # three lines starts at depth 0, and testing depth <= 0 before the
        # opening brace is read would end the block on its first line.
        depth, j, seen = 0, first, False
        while j < len(lines):
            opens = lines[j].count('{')
            depth += opens - lines[j].count('}')
            if opens:
                seen = True
            j += 1
            if seen and depth <= 0:
                break
        # Trim the block's own trailing newline so the span text matches
        # what the old line-joining extractor produced.
        segment = css_code[starts[first]:starts[j]]
        spans.append((starts[first], starts[first] + len(segment.rstrip('\r\n'))))
        consumed_to = j - 1
    return spans


def _extract_css_blocks(css_code: str, component: str) -> list:
    """
    Return CSS rule blocks whose selector line contains the component reference.
    Thin wrapper over _extract_css_block_spans, kept for callers that only need
    the text.
    """
    return [css_code[a:b] for a, b in _extract_css_block_spans(css_code, component)]


@tool
def extract_css_component(runtime: ToolRuntime[CssState], component: str = "",
                          components: Optional[List[str]] = None) -> Command:
    """
    Extract EVERY CSS rule block for target_component from css_code in state --
    the base rule plus any state variants (:hover, :focus) and media-query
    overrides. Multiple blocks come back as one document separated by
    '/* @@ WebForge block N of M @@ */' marker lines; diff against it as a whole.
    target_component may be a CSS selector (#id, .class) or a bare component name.
    Call this in Modification Mode before generating a diff.

    `components` extracts SEVERAL components in one call -- pass the whole
    target_components list and get every block back in one message, each
    under a "===== WebForge component n of m: <name> =====" line. Prefer
    it: five separate extracts are five re-sends of the whole stylesheet.
    """
    # The body is the engine's (webforge.dev_agent.loop_extract, ticket 09);
    # CSS_LOOP below carries what CSS differs by.
    return loop_extract(CSS_LOOP, runtime, component, components)


# ==========================================================================
# store_css_diff
# ==========================================================================
def _apply_css_component_diff(css_code: str, component: str, diff_output: str,
                              decoration_spec=None) -> dict:
    """
    Apply a unified diff to EVERY css_code block for `component` and splice the
    results back. Pure function — no state, no ToolMessage — so both
    store_css_diff and apply_and_lint_css format their own responses from ONE
    source of truth.

    `decoration_spec` is optional and is passed IN rather than read from state,
    which is what keeps this function pure: it is only needed to map a
    specification id to the className the stylesheet actually uses (see
    _css_component_aliases), and both callers already hold it. Omitting it falls
    back to literal matching, so every existing call site keeps working.

    Returns one of:
      {"status": "empty"}                                         css_code was empty
      {"status": "noblock"}                                       no block matched component
      {"status": "diff_fault", "error": <str>}                    stale/malformed diff — regenerate
      {"status": "internal", "etype": <str>, "error": <str>}      wiring/env fault — regenerating won't help
      {"status": "ok", "new_css_code": <str>, "n_blocks": <int>}  applied cleanly
    """
    # The body is the engine's (webforge.dev_agent.loop_apply_diff, ticket 09).
    return loop_apply_diff(CSS_LOOP, css_code, component, diff_output, decoration_spec)


@tool
def store_css_diff(diff_output: str, runtime: ToolRuntime[CssState]) -> Command:
    """
    Apply a unified diff to ALL CSS blocks for target_component and splice the
    results back into css_code in state. The diff must be relative to the exact
    text returned by extract_css_component, including any
    '/* @@ WebForge block N of M @@ */' separator lines, which must be preserved
    as context. In Modification Mode apply every change through this tool, not store_css_code (which is only the one-time Step 0 seed the orchestrator now pre-loads).
    """
    component = runtime.state.get("target_component", "")
    css_code  = runtime.state.get("css_code", "")
    res = _apply_css_component_diff(
        css_code, component, diff_output,
        runtime.state.get("decoration_specification"))
    st  = res["status"]

    if st == "empty":
        return Command(update={"messages": [ToolMessage(
            content="css_code is empty. Cannot apply diff.",
            tool_call_id=runtime.tool_call_id)]})
    if st == "noblock":
        return Command(update={"messages": [ToolMessage(
            content=f"No CSS blocks found for [data-component='{component}']. "
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
        "css_code": res["new_css_code"],
        "messages": [ToolMessage(
            content=f"Diff applied. {n} CSS {plural} for '{component}' updated.",
            tool_call_id=runtime.tool_call_id)]
    })


# ==========================================================================
# store_css_diff
# ==========================================================================
@tool
def apply_and_lint_css(diff_output: str = "",
                       runtime: ToolRuntime[CssState] = None,
                       component: str = "",
                       diffs: Optional[List[dict]] = None) -> Command:
    """
    Modification Mode: apply a unified diff to the target component's CSS block(s)
    AND lint the result in ONE call, so a fix comes back with its lint verdict
    already attached — no separate run_stylelint round-trip.

    `component` may be passed explicitly (a '#id'/'.class' selector or bare name)
    so several components can be fixed in one agent session; if omitted it falls
    back to target_component in state. The diff must be relative to the exact
    text extract_css_component returned for that component.

    On a patch failure OR a lint failure the CURRENT block is returned in the
    message so the model regenerates the diff against it WITHOUT re-extracting.

    `diffs` applies SEVERAL components in one call and lints ONCE at the
    end: [{"component": ".product-card", "diff_output": "--- original..."},
    ...]. Prefer it -- five separate calls are five re-sends of the whole
    stylesheet and five stylelint runs. They are applied in order, each on
    the result of the last, so the ones that apply are KEPT even if a later
    one fails; the reply names which landed and hands back the current
    block for each that did not.
    """
    # The body is the engine's (webforge.dev_agent.loop_apply_and_lint,
    # ticket 09); CSS_LOOP below carries what CSS differs by.
    return loop_apply_and_lint(CSS_LOOP, runtime, diff_output, component, diffs)


# ==========================================================================
# save_css_file, progress hooks, filesystem guard: made by webforge.dev_agent
# ==========================================================================
# The save path goes through the same KIND of backend the agent's
# FilesystemMiddleware uses (its own instance, same root from webforge.config),
# so traversal protection and overwrite semantics stay in one class.
_css_save_backend = new_preview_backend()

CSS = DevLanguage(key="css", tag="CSS", noun="stylesheet", linter="Stylelint",
                  lint_tool="run_stylelint", extract_none="No CSS blocks found",
                  save_backend=lambda: _css_save_backend)
_css_parts = dev_parts(CSS, CssState)
save_css_file             = _css_parts.save_tool
css_agent_progress        = _css_parts.agent_progress
css_before_model_progress = _css_parts.before_model_progress
css_tool_progress         = _css_parts.tool_progress
css_fs_guard              = _css_parts.fs_guard

CSS_LOOP = DevLoop(
    lang=CSS, spec_field="decoration_specification",
    aliases=lambda name, spec: _css_component_aliases(name, spec),
    spans=lambda code, name: _extract_css_block_spans(code, name),
    extract_miss=lambda code, name, spec: (
        f"No CSS blocks found for '{name}'. Tried: {_css_component_aliases(name, spec)}. "
        f"The stylesheet defines: {_css_selectors_present(code, prefer=name)}. "
        f"Per the Naming Contract a component is written as its "
        f"className when it has one, and only as #id otherwise - use "
        f"the name from that list, not the specification id."),
    batch_miss=lambda code, wanted: (
        f"No CSS blocks found for any of {wanted}. The stylesheet "
        f"defines: {_css_selectors_present(code)}. Per the "
        f"Naming Contract a component is written as its className "
        f"when it has one, and only as #id otherwise."),
    skipped_phrase="No blocks found",
    apply_miss=lambda code, name: (
        f"No CSS block found for '{name}'. The stylesheet "
        f"defines: {_css_selectors_present(code, prefer=name)}. Per the "
        "Naming Contract use the className where one exists, not "
        "the specification id, then extract and diff again."),
    lint=lambda code, runtime: _lint_css_source(code, runtime),
)


# ==========================================================================
# css_prompt_selector
# ==========================================================================
from langchain.agents.middleware.types import dynamic_prompt


def _css_selector_allowlist_block(state) -> str:
    """The exact component selectors THIS run's HTML carries, one per line, by the
    Selector Contract (.className when the node declares one, else #id). Injected
    as DATA so the CSS stage styles real selectors instead of inventing component
    class names -- the CSS<->DOM drift that left 47 dead selectors and an unstyled
    layout on run po015b2ac9. Empty when there is no component spec, so a spec-less
    run is unchanged. (The className-else-id rule is the same one _spec_selector_map
    uses; inlined here to keep this prompt helper independent of cell order.)"""
    spec = (state or {}).get("components_specification") or {}
    if isinstance(spec, str):
        try:
            spec = json.loads(spec)
        except Exception:
            return ""
    out = {}
    def _walk(node):
        if isinstance(node, dict):
            if isinstance(node.get("id"), str) and "tag" in node:
                cls = node.get("className")
                out[node["id"]] = f".{cls}" if cls else f"#{node['id']}"
            for v in node.values():
                _walk(v)
        elif isinstance(node, list):
            for it in node:
                _walk(it)
    _walk(spec)
    if not out:
        return ""
    lines = "\n".join(f"- {cid}: {sel}" for cid, sel in sorted(out.items()))
    return (
        "\n\n## Selector allowlist for THIS run (authoritative)\n"
        "These are the exact selectors the HTML carries for each component "
        "(.className when it has one, else #id). Style a component through its "
        "selector from this list, verbatim. Do NOT invent a component class the "
        "HTML never emits. Element selectors (body, header, h2, a) and real "
        "descendants (e.g. #product-grid .price) are fine; a made-up component "
        "class is not.\n"
        "A descendant counts as real only if that tag is actually inside "
        "that container in the page you read at Step 0. Writing "
        "`.roast-level-nav button` when the markup says `<a>` styles "
        "nothing, passes every linter, and no test can see it. "
        "store_css_code REFUSES a stylesheet that does this, and names "
        "the container's real children for you.\n\n" + lines
    )


def _css_region_block(state) -> str:
    """The layout regions this run declares, as a prompt appendix.

    The CSS stage used to receive components + decoration only. A region with no
    components -- which is every JavaScript-owned region, by the components
    generator's own rule -- was therefore invisible to it, and no prompt wording
    could have helped. This is the data half of the Region Coverage Contract;
    store_css_code is the guard half.
    """
    rows = _layout_region_names((state or {}).get("layout_specification"))
    if not rows:
        return ""
    listing = "\n".join("- #%s   (ownedBy: %s)" % (n, o or "unspecified")
                         for n, o in rows)
    return (
        "\n\n## Layout regions on this page (authoritative)\n"
        "Each of these is a section in the document, addressed by #name. Every "
        "one needs container styling of its own: the shared page gutter, the max "
        "width, the background. Nothing else supplies it.\n\n" + listing +
        "\n\nA region marked ownedBy: JavaScript is NOT exempt. JavaScript "
        "inserts that region's CONTENTS at runtime; it never gives the container "
        "its inset or its width. On run po018f8158 the two JavaScript-owned "
        "regions received no CSS at all and rendered flush against the window "
        "edge. store_css_code refuses a stylesheet in which nothing inside a "
        "region is reached by any rule.\n"
    )


def _css_html_context_block(state) -> str:
    """Inject the real generated HTML into the CSS agent's context in generate
    mode, so it lays out the ACTUAL element tree instead of guessing it from the
    flat spec list (the hero-hole / filter-offset failure of po01c67a49). The HTML
    agent runs and saves before the CSS agent, and the file does not change during
    CSS generation, so reading it per render is stable. Returns "" (no change to
    the prompt) when no page is on disk yet -- which is what keeps the
    css_prompt_selector unit tests, run on fake sessions, unaffected."""
    sid = state.get("session_id", "") if hasattr(state, "get") else getattr(
        state, "session_id", "")
    html = _read_preview_source(sid, "html")
    if not html:
        return ""
    return ("\n\n---\n\n## The actual HTML for this page "
            "(authoritative for structure)\n"
            "Lay out the REAL direct children you see below; the specs give the "
            "intent, this gives the tree.\n\n```html\n" + html + "\n```\n")


@dynamic_prompt
def css_prompt_selector(request) -> str:
    state = request.state or {}
    if state.get("intent", "generate") == "modify":
        # The allowlist goes into modify mode too: a correction work order
        # names a component, and without the real selector map the agent
        # guesses the componentCategory (`.add-to-cart-button`) over the real
        # className (`.add-to-cart-btn`). That was E2E-SO-01's wasted rounds.
        return (_css_modification_prompt + _targets_block(state)
                + _css_selector_allowlist_block(state))
    # _specs_prompt_block: defined with html_prompt_selector (runs earlier in
    # the notebook); see its docstring for why injection is generation-only.
    return (_css_generation_prompt
            + _specs_prompt_block(
                state, ["components_specification", "decoration_specification"])
            + _css_selector_allowlist_block(state)
            + _css_region_block(state)
            + _decoration_token_seed(state)
            + _spec_base_prompt_block(state)
            + _css_html_context_block(state))


# ==========================================================================
# System Prompt
# ==========================================================================
_css_shared_base = """
You are the CSS Developer Agent for an unattended multi-agent website builder.
Produce or modify one CSS stylesheet for the page the HTML agent already built.
The stylesheet must be syntactically valid, lint-clean, visually faithful to the
supplied specifications, compatible with the ACTUAL HTML, and saved only when the
validation state permits. Your scope is CSS only.

## Context you can use
- The user's request.
- Agent state: css_code, lint_passed, css_specification, intent, target_component,
  decoration_specification.
- The HTML file the HTML agent already wrote, available through
  read_file(f"preview_{state.session_id}.html") and injected into your context.

The HTML currently on disk is AUTHORITATIVE for DOM structure. Use each source for
what it can establish: the actual HTML for elements, wrappers, parent/child and
sibling relationships, classes, ids and attributes; the structured specifications
for intended layout, components, decoration, state variants, breakpoints and design
values (copy values from decoration_specification, never re-derive the style); the
user request for the outcome. The specifications describe INTENT; they do not
guarantee the actual HTML nesting.

## Hard constraints (both modes)
- NEVER modify HTML or JavaScript — your scope is CSS only.
- Save to the file system only after the linter reports no issues (each mode's
  steps below say exactly when).
- Honor the selector allowlist. Element selectors (body, header, h2, a, *) and REAL
  descendants of an allowlisted selector are fine; only a made-up component class is
  a defect. A dead-selector sweep hands back any selector that matches nothing.
- Honor [hidden] and every state and overlay attribute the HTML/runtime contract
  defines. CSS must never force an element visible, hidden, open, closed, enabled or
  disabled contrary to those attributes.
- An [INTERNAL] ToolMessage is a pipeline fault, not a defect in your code: say so
  in your final message and end your turn; do not revise the code or re-lint.

## Accessibility (WCAG 2.1 AA - never violate)
- Colour contrast >= 4.5:1 for normal text (< 18pt); >= 3:1 for large text (>= 18pt
  or bold 14pt+).
- Never convey information through colour alone - pair with a text label or icon.
- Focus indicators must be visible - never outline:none / outline:0 without a custom
  replacement.
- Text readable at 200% zoom (no fixed-height container that clips text).
- All styles work at viewport widths 320px-1440px with no horizontal scrolling;
  interactive touch targets >= 44x44px.
- Conflict order: WCAG 2.1 AA > W3C responsive > Baymard e-commerce > user
  aesthetic. If a requested colour fails contrast, substitute the nearest compliant
  colour silently.

## State variant selectors
Style a stateVariant through the attribute the State Materialization Contract puts
on the element: [aria-disabled="true"], [aria-expanded="true"],
[aria-pressed="true"], or [data-state="<stateName>"]. Do not use :disabled (the JS
never sets the native disabled property, so it matches nothing). Never express a
disabled look with pointer-events: none (it makes the element unreachable by the
test pipeline). :hover and :focus stay pseudo-classes. Do not make CSS the sole
carrier of state - keep the existing text/icon cues.

## Design tokens
Open the stylesheet with one :root block that names the palette and scales once,
then reference those names everywhere instead of repeating values
(background: var(--color-surface), not #ffffff). At least 6 custom properties are
REQUIRED or store_css_code refuses: a primary colour, a surface colour, a text
colour, a border colour, a corner radius, a spacing unit. transparent, currentColor
and inherit are never counted as colours. A dark-mode or high-contrast override is a
second :root block. A token-usage ADVISORY is not a rejection (the CSS is already
saved) - replace the named literals with tokens and call store_css_code once more,
adding no new rules for it.

## E-commerce visual standards (Baymard)
- Every product image sits in a FIXED-RATIO box: the box has
  aspect-ratio: var(--card-aspect); overflow: hidden, and the <img> uses
  object-fit:cover; width:100%; height:100%. The ratio lives on the BOX, never the
  image, so every card is one size whatever the source.
- This system embeds no photographs, so a product's image slot is a
  <div class="product-image-placeholder"> holding the product name as text, not an
  <img>. Style it as the IMAGE AREA of the card: the same fixed aspect ratio as the
  image container, a muted surface token, the name centred and legible
  (contrast >= 4.5:1), wrapping rather than clipping, a real box with size - never
  display:none, never zero height. Accessibility wins: let the box grow if needed to
  avoid clipping at 200% zoom.
- Decorative areas ONLY (a hero, a promo strip, a section or the page background) MAY
  show a real photograph through CSS background-image, including a direct Unsplash CDN
  URL you recall. Two rules keep it safe. (1) Use ONLY images.unsplash.com, the direct
  CDN - never source.unsplash.com (a redirect API that no longer resolves) and never a
  remote <img>. (2) ALWAYS give the same rule a solid background-color token BEHIND the
  photo, so a URL that fails to load shows the colour, not a blank rectangle:
  background-color: var(--color-surface-muted); background-image:
  url("https://images.unsplash.com/photo-..."); background-size: cover. Never ship a
  background-image with no colour behind it. This is decoration only - a product's image
  slot stays the text placeholder above, never a background photo.
- Primary CTAs (Add to Cart, Proceed to Checkout): high contrast, min-height
  >= 44px. Form inputs: visible border, clear label spacing, adequate padding.
  Price typographically distinct; a sale price clearly differentiated. Error state:
  colour + icon + text (never colour alone).
- An inline <svg> inside a button or link is DECORATIVE: give it
  pointer-events: none, size it with width/height (not font size), and recolour it
  through the parent control's color (the markup carries stroke="currentColor") -
  never set stroke or fill on the icon directly.
"""

_css_generation_prompt = _css_shared_base + """
---

## Your Task: Generation Mode

## How you work
Read the HTML first. Then generate the FULL stylesheet, call store_css_code, then
run_stylelint; fix ONLY the reported lines and re-lint until it returns
"No issues found."; then save_css_file. ALWAYS call store_css_code before
run_stylelint, passing the exact content from your last message. NEVER save before
the linter returns "No issues found." - the one exception is a [LINT CAP REACHED]
ToolMessage: stop calling the linter, save the current best effort with
save_css_file, and end your turn with a short summary of what is unresolved. Do not
truncate, summarise or omit any section - produce the full stylesheet.

## Lay out the REAL tree, not the spec's list (this decides the layout)
Before writing any grid or flex container, look at that region in the HTML and lay
out its ACTUAL direct children. Never infer sibling / parent / child / wrapper
relationships from a flat component list when the HTML can be inspected.
- PUT THE GRID ON THE ELEMENT WHOSE DIRECT CHILDREN ARE THE REPEATING ITEMS. A
  region's layoutType tells you the region CONTAINS a grid; it does not say the grid
  belongs on the region's own box. If a region's direct children are a heading and a
  wrapper, the grid belongs on the wrapper.
- A two-column region (a hero of text | image) works only if those two are the
  region's REAL direct children. If the HTML wrapped them under one child, put the
  grid on THAT wrapper, or one column comes out empty - the empty column is on you.
- A section heading is never a grid item - leave it outside the grid, or span it with
  grid-column: 1 / -1.
- Never declare more columns than the grid has items. On run po01e9a8b4 a six-column
  grid over two children (an <h2> and a <ul>) squeezed the list into one 168px
  column and piled its items on top of one another. The build runs a grid sweep and
  hands back a grid whose declared column count exceeds its item count.
- If the spec's implied structure differs from the HTML, keep the spec's visual
  INTENT by adapting the CSS to the HTML that exists. Do not edit HTML/JS to fit the
  spec, and do not paper over a wrong structural selector with arbitrary widths,
  spans, positioning or descendant hacks.

## Layout system (apply these tokens; do not invent layout math)
- The page is ONE centered column: put max-width: var(--page-max-width);
  margin-inline: auto on the page wrapper, and padding-inline: var(--page-gutter) on
  every top-level region - every direct child of <body> and of <main>, whatever its
  tag: <header>, <nav>, <section>, <aside> and <footer>. Every region ends the same
  width and the same left edge. Separate top-level sections with var(--section-gap).
- A landmark that PAINTS a page-spanning background (a header, a footer, a colour
  band) stays width: 100% with the background - never put max-width on the painted
  element, which caps the colour and leaves bare strips on wide screens (a footer
  capped at 1200px leaves two bare strips on a 1900px screen). Inset its content
  instead: padding-inline: max(var(--page-gutter), calc((100% -
  var(--page-max-width)) / 2)), so the content sits in the same centered column while
  the background stays full-bleed.
- Any <ul> or <ol> used as NAVIGATION or a row of tiles, chips or links gets
  list-style: none; margin: 0; padding: 0 and flex or grid layout - an unreset nav
  list renders as a bulleted vertical strip however wide its container is.
- A horizontal nav or a row of links, tiles or chips WRAPS on its own: on a flex
  row add flex-wrap: wrap with the same gap, so the links reflow onto more rows
  when the viewport is narrow. Do not hold it on one line with overflow-x: auto -
  on a phone that ships a nav wider than the screen the shopper has to drag
  sideways (five links sit near 590px on a 375px viewport). Like the product grid,
  it reflows on its own with no per-count media query.
- A product or card grid is display:grid; grid-template-columns: repeat(auto-fill,
  minmax(var(--grid-min), 1fr)); gap: var(--grid-gap) - it reflows on its own, no
  per-count media query.
- Use the var(--*) names from the run globalTokens; do not hardcode the numbers.

## Honor the states and overlays the HTML and JS declare
- Reset [hidden]: include [hidden] { display: none !important; } and never give a
  component a base display that overrides it. The JS shows and hides items through
  the hidden attribute (a search or filter sets el.hidden = true on the
  non-matches), so a card ruled display:flex with no [hidden] reset can never be
  hidden and the page looks dead. The build hands back any component that stays
  visible when its hidden attribute is set.
- A drawer, off-canvas panel or modal dialog is out of flow: position: fixed (or
  absolute) and hidden at rest. The JS opens and closes it by toggling the drawer's
  OWN hidden attribute (el.hidden = false to open), so the on-screen state MUST key
  off #<drawerId>:not([hidden]) - give THAT selector visibility: visible,
  pointer-events: auto, full opacity and the on-screen transform, plus a backdrop
  when modal. You may additionally honor [data-state="open"], but never make
  [data-state="open"], or an `aria-expanded` on the toggle BUTTON, the ONLY route to
  visible: the JS sets aria-expanded on the button, not on the drawer, so a drawer
  keyed only to those has its hidden attribute removed on open yet stays
  visibility: hidden - opened, but the visitor still sees nothing. The build hands
  back any drawer still in normal flow, or one that does not become visible when its
  toggle is activated.
- A header, footer or nav that groups several parts - brand, links, search and cart,
  or a footer's columns - lays that grouping container out as a flex or grid ROW. A
  grouping container left as the default block stacks its parts vertically and the
  bar swells to a large fraction of the viewport. The build hands back a
  header/footer/nav container left stacking its parts.

## Sticky (optional)
position: sticky is for two cases only: a genuine sidebar in its own column of a
multi-column layout, and the site header / top nav bar. To pin the header, put
position: sticky; top: 0 on the <header> LANDMARK itself, never on an inner nav bar
- a sticky element holds only while its containing block is on screen, so sticky on
a bar inside a short header un-sticks the instant the header scrolls past and the
nav disappears. Give the sticky header a z-index BELOW the cart drawer or any modal
overlay (for example 30 when the drawer is 40) so an open drawer still covers it,
and add scroll-margin-top equal to the header height to every in-page anchor target
so a jump link does not land hidden under the header. Every OTHER full-width,
single-column region (a filter panel, a toolbar, a banner) must NOT be sticky and
must scroll normally.

## Selector fidelity
A SELECTOR ALLOWLIST for this run is provided below: the exact selector each
component carries (.className when it has one, else #id). Style components through
the Selector allowlist verbatim; never invent a component class the HTML does not
emit. Use id selectors for unique elements and class selectors for repeated
components, matching the attributes the HTML agent set. do not invent selector names
- confirm against the HTML you already read if unsure. Every selector you write must
match a real element.

## Output contract
Return and store exactly ONE complete CSS stylesheet that matches the actual HTML on
disk, implements the intended design, uses only allowed selectors (with the
element/descendant carve-out), preserves runtime visibility/state/overlay behaviour,
satisfies the accessibility and responsive constraints, contains the required :root
tokens, changes no HTML or JavaScript, and passes linting before storage.

## Done when
run_stylelint returns "No issues found." and the complete stylesheet is saved with
save_css_file. Never save a truncated or partial stylesheet.
"""

_css_modification_prompt = _css_shared_base + """
---

## Your Task: Modification Mode

state carries target_components — the list of components to fix in THIS call. It
always holds at least one entry. target_component holds the first one. Do not ask
the user to clarify the targets.

Fix them ALL IN ONE PASS, not one at a time. Three tool calls, whether the list
holds one component or six:

    extract_css_component(components=[...])
    -> apply_and_lint_css(diffs=[...]) -> save_css_file()


Your FIRST tool call is
extract_css_component(components=[<the ENTIRE target_components list>]).
Never call it once per component, and never call it a second time.

Every extra round trip re-sends the whole stylesheet. Doing six components one at a
time costs thirteen calls and six linter runs instead of three and one.

### Step 0 — The current stylesheet is already loaded
- The orchestrator has already put the current file in state. Do NOT call
  read_file and do NOT call store_css_code: sending the file back costs a full
  copy of it and changes nothing.
- Go straight to Step 1.
- Only if extract_css_component answers "css_code is empty": call
  read_file(f"preview_{state.session_id}.css"), then
  store_css_code(css_code=<file content>), once, and continue with Step 1.

### Step 1 — Extract EVERY Target in ONE Call
- Call extract_css_component(components=[<every entry in target_components>]) once.
- The reply holds each component's CSS under a line reading
      ===== WebForge component 1 of 3: .product-card =====
- Within one component you may get SEVERAL rule blocks — the base rule
  plus its :hover / :focus variants and media-query overrides —
  separated by /* @@ WebForge block N of M @@ */ lines.
- The reply is your ONLY working scope. Do not read or touch any other part of
  css_code, and do not call extract_css_component again.
- It may answer instead of extracting, in which case do what it says:
    * "Refusing this batch: 'X' and 'Y' share a rule block" — the two overlap, so one diff
      would invalidate the other. Write ONE diff for the first that carries both
      changes, or drop the second from this call and send it in a later round.
    * "No blocks found, so not included" — those names are stale. Skip them, and say so at the end.
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
  relative to the full css file, and NOT to the joined message.
- Two marker kinds, opposite rules, so read this twice:
    * /* @@ WebForge block N of M @@ */ — KEEP it, as an unchanged context line.
      It marks where a block is spliced back. Never add, remove or edit one.
    * ===== WebForge component n of m: name ===== — NEVER put one in a diff. It
      is a label for you, not part of the file.
- Include 2–3 unchanged context lines around each change.
- Output the diffs ONLY — never the full revised block.
- Apply the change consistently across every block a component has. A
  colour change normally needs the :hover variant updated too, or the
  component ends up inconsistent between states.

### Step 3 — Apply Them All in One Call, Then Read the Table
- Call apply_and_lint_css with the whole set:

    apply_and_lint_css(diffs=[
        {"component": ".product-card", "diff_output": "--- original\n..."},
        {"component": "#navbar", "diff_output": "--- original\n..."},
    ])

  It applies them in order, each on the result of the last, and lints the whole
  file ONCE at the end.
- The reply opens with a table saying what happened to each diff:

    Applied 2 of 3 diff(s) in one call.
      OK      .product-card
      OK      #navbar
      FAILED  .price -- Patch failed: no unique context match

  Then read the rest of the message:
  - "No issues found." and every row OK -> go to Step 4.
  - Any FAILED row -> the diffs that say OK ARE ALREADY APPLIED and must NOT be
    resent. Write a new diff ONLY for the failed components, against the CURRENT
    block the message hands back at the bottom, and call apply_and_lint_css again with just
    those. Do NOT call extract_css_component again. NEVER re-add a selector, property or rule that is already
    present — re-adding causes a duplicate-selector or duplicate-property error. If the error IS a duplicate, your
    fix is to DELETE the extra copy, not add more.
  - Lint problems with every row OK -> the message ends with the current text of
    each block you changed. Diff against THAT, again in one batched call.
  - "[LINT CAP REACHED]" or "[PATCH CAP REACHED]" -> stop. Save best-effort
    (Step 4), then end with a short summary of what is still unresolved.

### Step 4 — Save Once (after every component is handled)
- If AT LEAST ONE component was actually changed, call save_css_file() ONCE, after the
  whole batch — never per component. It saves css_code from state; you never
  paste content.
- If NOTHING changed at all, do NOT call save_css_file — skip to Step 5 and report the
  targets as not found.

### Step 5 — End
- End with a short summary: which components were fixed, and which (if any) were
  not found or hit a cap and are still unresolved.

---

## Modification Mode Strict Rules
- ONE extract_css_component call and ONE apply_and_lint_css call for the whole batch. Calling either
  once per component is the slow path this prompt exists to avoid, and it spends
  the round's budget on round trips.
- Call extract_css_component ONCE, with `components`, before any diff. After that, reuse the
  block apply_and_lint_css returns on any failure — never re-extract.
- Every entry in `diffs` names its own component. Do not rely on any fallback:
  in a batch that is the wrong block.
- Never resend a diff whose row said OK. It is already applied, and re-adding
  what is already there produces a duplicate error.
- Apply every change through apply_and_lint_css. NEVER call store_css_code in this mode, except in
  the empty-state case Step 0 names.
- Save EXACTLY ONCE, at the very end, with save_css_file — never per component.
- NEVER write a diff against the full css file, or against the joined message.
  A diff is relative to one component's own extracted text.
- Output diffs only — never a full revised block.
- Before finalizing a diff, check whether a component's current styles come
  from a rule shared with other components (a generic class like .btn,
  .container). If so, do NOT edit the shared rule directly — add a more
  specific selector (combine it with the component's own id/class) so the
  fix does not affect other elements using the shared rule.
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
_css_model = ChatOpenAI(model="gpt-5.4",
    reasoning=_reasoning_for("css"),
    timeout=120,
    max_retries=2,
    parallel_tool_calls=False)

_preview_backend = new_preview_backend()

css_agent = build_dev_agent(
    _css_parts,
    model=_css_model,
    tools=[store_css_code, run_stylelint, extract_css_component, apply_and_lint_css],
    prompt_selector=css_prompt_selector,
    state_schema=CssState,
    backend=_preview_backend,
)


# Re-export this module's whole namespace, so the next module
# starts from it. Part of the mechanical split of ticket 04.
__all__ = [_n for _n in list(globals())
           if not (_n.startswith("__") and _n.endswith("__"))]
