"""Computed-style comparison: normalise CSS values, resolve var(), probe what
the browser itself computes for an expected value (assert_css, assert_hover_css)."""
from __future__ import annotations

# ── Helpers ────────────────────────────────────────────────────────────────────

import re as _re_css

# Any 3- or 6-digit hex token, wherever it sits in a value. 6 is tried first so
# '#dddddd' is not read as '#ddd' followed by 'ddd'.
_HEX_TOKEN = _re_css.compile(r"#(?:[0-9a-fA-F]{6}|[0-9a-fA-F]{3})\b")


def _hex_to_rgb(hex_val: str) -> str:
    """Convert '#rrggbb' or '#rgb' to 'rgb(r, g, b)' for getComputedStyle comparison."""
    h = hex_val.lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return f"rgb({r}, {g}, {b})"


def _normalize_css_value(val: str) -> str:
    """Put an expected value into the form getComputedStyle reports.

    The browser always returns colours as rgb(), so a hex has to be converted
    before comparison. The old check only converted a value that STARTED with
    '#', which is true of `background-color=#1a73e8` and false of
    `border=1px solid #dddddd` -- and a shorthand is exactly where a hex sits in
    the middle. The consequence was not a wrong message but an UNWINNABLE FIX
    LOOP: the CSS agent wrote the requested declaration, it linted clean, the
    comparison still failed, and both correction attempts were spent on a
    stylesheet that was already correct (E2E-SO-01/03/04, 2026-08-09). Same
    shape as the serializer defect in report section 6.4 challenge 1 -- the
    model is innocent and no sequence of correct actions can pass.

    Whitespace is collapsed for the same class of reason: a spec may write
    '1px  solid #ddd' while the browser reports single spaces.
    """
    val = _HEX_TOKEN.sub(lambda m: _hex_to_rgb(m.group(0)), val)
    # 'transparent' is the keyword the browser reports as rgba(0, 0, 0, 0); the
    # authored keyword can never string-match the computed rgba otherwise
    # (PO-10 TC-006). Whole word only, so a token like 'transparent-ish' is safe.
    val = _re_css.sub(r"(?i)\btransparent\b", "rgba(0, 0, 0, 0)", val)
    return _re_css.sub(r"\s+", " ", val).strip()


# A var(--x) reference, e.g. var(--page-max-width).
_VAR_TOKEN = _re_css.compile(r"var\(\s*(--[A-Za-z0-9_-]+)\s*\)")

# getComputedStyle reports the browser's USED value, which never contains any
# of these: 'auto' resolves to a used length, and the CSS-wide keywords are
# substituted before computing. An expected value that still carries one
# cannot be matched against the used value, so it is not a computable
# assertion -- the var()/'auto' twin of the hex/rgb unwinnable loop
# (PO-08 TC-021, 2026-08-29). Skip it rather than fail it forever.
_NONCOMPUTABLE_KEYWORDS = ("auto", "inherit", "initial", "unset", "revert",
                            "fit-content", "max-content", "min-content")

# getComputedStyle also resolves every RELATIVE length and every track-list or
# math function to an absolute used value: 'repeat(2, minmax(0, 1fr))' comes
# back as pixel tracks ('262px 262px 262px'), '1rem' as '16px', clamp()/calc()
# as the single computed length. An expected value that still carries one of
# these can never string-match the used value -- the exact 'auto' situation, one
# class wider. Skip it rather than fail it forever (PO-08 TC-080 grid tracks and
# gap-in-rem, 2026-08-29).
_UNCOMPUTABLE_VALUE = _re_css.compile(
    r"(?:\b(?:repeat|minmax|fit-content|clamp|calc)\s*\()"   # track-list / math fns
    r"|(?:\bauto-fi(?:ll|t)\b)"                               # grid auto-fill / auto-fit
    r"|(?:\d*\.?\d+(?:fr|rem|em|vw|vh|vmin|vmax)\b)"          # relative length units
    r"|(?:\d*\.?\d+%)")                                       # percentages -> used px

# A handful of shorthand properties the browser ALWAYS re-serialises to a form no
# authored string matches: box-shadow moves the colour first and pads to four
# lengths; transition/animation reorder and fill in defaults; background/font expand
# into assembled longhands. getComputedStyle on these can never equal the spec's
# text, exactly like the transform and grid-track cases already handled, so an
# assert_css pair on one of these is SKIPPED by property name (fail-open) rather
# than failing forever (po015df552 box-shadow false failure). A wrong LONGHAND
# (color, an absolute px width) is unaffected and still caught.
_RESERIALIZED_SHORTHANDS = frozenset(
    {"box-shadow", "background", "font", "transition", "animation"})

# CSS blockification: an INLINE-level display on a flex or grid ITEM is USED
# as its block-level twin, and getComputedStyle reports that used value. So an
# authored 'inline-flex' on a child of a display:flex/grid parent reads back
# 'flex', 'inline-grid' reads 'grid', 'inline-block' reads 'block'. The authored
# inline keyword can then never string-match -- the used-value twin of the
# auto/var/transform loops. Maps each inline form to what it blockifies to.
_BLOCKIFY = {"inline-flex": "flex", "inline-grid": "grid",
             "inline-block": "block", "inline": "block", "inline-table": "table"}


# background-position / object-position keywords the browser re-serialises to
# percentages ('center' -> '50% 50%', doubled per background layer), so an
# authored keyword can never string-match. Used to skip a keyword-only position.
_POSITION_KEYWORD = _re_css.compile(r"(?i)\b(?:center|left|right|top|bottom)\b")


def _resolve_css_vars(page, val: str) -> str:
    """Replace every var(--x) with the value :root computes for it.

    getComputedStyle resolves custom properties, so an expected string that
    still literally reads 'var(--page-max-width)' can never equal the
    browser's '1200px'. Resolving it here compares like with like."""
    def _sub(m):
        name = m.group(1)
        resolved = page.evaluate(
            "getComputedStyle(document.documentElement)"
            f".getPropertyValue('{name}')"
        )
        resolved = (resolved or "").strip()
        return resolved if resolved else m.group(0)
    return _VAR_TOKEN.sub(_sub, val)


# A transform written as functions -- translateY(-2px), scale(1.02), rotate(3deg)
# -- is reported by getComputedStyle ONLY as a matrix, e.g.
# 'matrix(1, 0, 0, 1, 0, -2)'. A string compare against the authored form can
# never pass, so a correct stylesheet failed every run and the correction loop
# had nothing it could do (PO-08 TC-064, 2026-08-30). Same class as the
# hex/rgb and var()/auto unwinnable loops above.
_TRANSFORM_FN = _re_css.compile(
    r"\b(?:translate[XYZ3d]*|scale[XYZ3d]*|rotate[XYZ3d]*|skew[XY]?|matrix3?d?|perspective)\s*\(",
    _re_css.IGNORECASE)


def _resolve_transform_value(page, prop: str, val: str):
    """Return `val` as the browser would compute it for a transform property.

    Returns the matrix string on success, the value unchanged when this is not a
    transform, or None when the pair must be SKIPPED. A percentage translate
    resolves against the element's own box, which a probe element does not
    share, so those stay unanswerable and are skipped rather than mismatched.
    """
    if "transform" not in prop.lower():
        return val
    if not _TRANSFORM_FN.search(val):
        return val                       # 'none', a bare keyword: compare as-is
    if "%" in val:
        return None                      # box-relative: not resolvable on a probe
    resolved = page.evaluate(
        "(v) => { const el = document.createElement('div');"
        " el.style.position = 'absolute'; el.style.transform = v;"
        " document.body.appendChild(el);"
        " const m = getComputedStyle(el).transform;"
        " el.remove(); return m; }", val)
    resolved = (resolved or "").strip()
    return resolved if resolved and resolved != "none" else val


def _has_noncomputable_keyword(val: str) -> bool:
    """True when a value carries a token getComputedStyle never returns."""
    return any(t in _NONCOMPUTABLE_KEYWORDS
               for t in _re_css.split(r"[\s,]+", val.lower()))


def _has_uncomputable_value(val: str) -> bool:
    """True when a value carries a unit or function getComputedStyle resolves
    away (relative lengths, track-list / math functions), so it can never
    string-match the used value. Companion to _has_noncomputable_keyword."""
    return bool(_UNCOMPUTABLE_VALUE.search(val.lower()))


def _css_prop_to_kebab(prop: str) -> str:
    """Return a CSS property name in the hyphenated form getPropertyValue needs.

    getComputedStyle(el).getPropertyValue recognises ONLY the dashed name:
    getPropertyValue('border-radius') returns '10px', getPropertyValue(
    'borderRadius') returns '' -- the empty string, not an error. The Test
    Generation model sometimes emits the JS camelCase form ('borderRadius',
    'fontSize') even though the prompt and every spec use the dashed form. An
    empty computed value can never string-match, so a correct stylesheet fails
    forever -- the exact 'unwinnable fix loop' shape of the hex/rgb and
    var()/auto cases already handled here (PO-10 borderRadius/fontSize/
    fontWeight/minWidth/whiteSpace, all read back as ''). A name already dashed,
    or a --custom-property, carries no uppercase and passes through unchanged.
    """
    return _re_css.sub(r"(?<!^)(?=[A-Z])", "-", prop.strip()).lower()


_PROBE_EXPECTED_JS = """([sel, prop, v]) => {
    const el = document.querySelector(sel);
    if (!el || !el.parentNode) return null;
    const twin = el.cloneNode(false);
    twin.style.setProperty(prop, v);
    if (!twin.style.getPropertyValue(prop)) return null;   // browser rejected v
    el.parentNode.insertBefore(twin, el.nextSibling);
    const out = getComputedStyle(twin).getPropertyValue(prop);
    twin.remove();
    return out;
}"""


def _probe_expected_css(page, selector: str, prop: str, val: str):
    """The used value `val` would have on a shallow twin of the element.

    The twin keeps the element's classes, id and parent, so font-size, the
    containing block and every stylesheet rule resolve exactly as for the
    element; only `prop` is forced to `val` inline. Returns None when the
    browser rejects the value or the element is gone."""
    try:
        return page.evaluate(_PROBE_EXPECTED_JS, [selector, prop, val])
    except Exception:
        return None


def _css_pair_mismatches(page, selector: str, expected: str) -> list:
    """Check pipe-separated 'property=value' pairs against computed styles.
    Shared by assert_css (normal state) and assert_hover_css (while hovering)."""
    mismatches = []
    for pair in expected.split("|"):
        prop, val = pair.split("=", 1)
        # getPropertyValue needs the dashed name; the model sometimes writes
        # the JS camelCase form ('borderRadius'). Normalise ONCE and use it
        # for every property test and the read below, so a camelCase name is
        # MEASURED, not read back as '' -- a permanent false failure (PO-10).
        _prop = _css_prop_to_kebab(prop)
        if _prop in _RESERIALIZED_SHORTHANDS:
            # a re-serialised shorthand can never string-match; skip, do not fail
            continue
        val = _resolve_css_vars(page, val)
        # An authored transform is resolved to the matrix the browser reports,
        # BEFORE the skip checks below -- otherwise translateY(-0.5rem) would be
        # discarded as a relative unit instead of being compared properly.
        val = _resolve_transform_value(page, _prop, val)
        if val is None:
            continue
        # A value the browser never reports back -- a bare 'auto', a CSS-wide
        # keyword -- is not a computable assertion. Comparing it against the
        # used value fails forever, so skip the pair (PO-08 TC-021).
        _norm = _normalize_css_value(val)
        # A keyword-only background-position / object-position ('center',
        # 'left top') is re-serialised to percentages by getComputedStyle and
        # can never string-match; skip it fail-open, like 'auto'. An explicit
        # length is still compared (PO-10 TC-010).
        if _prop in ("background-position", "object-position") and \
                _POSITION_KEYWORD.search(_norm):
            continue
        if _has_noncomputable_keyword(_norm) or _has_uncomputable_value(_norm):
            continue
        actual = page.evaluate(
            f"getComputedStyle(document.querySelector('{selector}')"
            f").getPropertyValue('{_prop}')"
        )
        want = _normalize_css_value(val)
        got  = _re_css.sub(r"\s+", " ", str(actual)).strip()
        # font-family: the browser drops quotes it does not need ("Inter" ->
        # Inter), so compare both sides unquoted (PO-10 TC-035).
        if _prop == "font-family":
            want = want.replace('"', "").replace("'", "")
            got = got.replace('"', "").replace("'", "")
        # `display: inline-flex` (or inline-grid/inline-block/inline) blockifies
        # to its block twin when the element is a flex or grid ITEM, and the
        # browser reports that used value. The authored inline keyword can then
        # never string-match, so treat the blockified twin as a match (PO-08
        # TC-016/018/022/024/027/031/035/048, all authored inline-flex, all 'got
        # flex'). A genuinely different display (grid vs flex) has no _BLOCKIFY
        # entry mapping to `got`, so it is still CAUGHT.
        if _prop == "display" and _BLOCKIFY.get(want) == got:
            continue
        # Last resort before failing: let the browser compute the EXPECTED value
        # on a twin of the element and compare used value with used value. A
        # unitless line-height ('1.8' reads back '32.4px' at 18px) or a 'ch'
        # width can never string-match, and every such case cost a correction
        # round on a stylesheet that was already right (eaf0304e: 3 of its 4
        # failures). display is excluded (a [hidden] !important rule would make
        # the twin read "none" too). A var() is excluded: an undefined token computes to the
        # initial value and could fake a match.
        if want not in got and "var(" not in val and _prop != "display":
            probed = _probe_expected_css(page, selector, _prop, val)
            if probed is not None and \
                    _re_css.sub(r"\s+", " ", probed).strip() == got:
                continue
        if want not in got:
            mismatches.append(f"{prop}: expected '{want}', got '{actual}'")
    return mismatches


# Every name this module defines or imports, for the package's __init__ and
# from there for webforge.test_exec, which re-exports it into the load order.
__all__ = [_n for _n in list(globals())
           if not (_n.startswith("__") and _n.endswith("__"))]
