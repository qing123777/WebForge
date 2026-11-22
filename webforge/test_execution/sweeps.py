"""The page-health sweeps: deterministic checks of the page as it ships.

Each sweep reads the restored page and returns findings shaped like failed test
cases. run_test_suite runs every sweep in PAGE_SWEEPS, in that order (ticket 11:
before, it called them one by one in a single expression).
"""
from __future__ import annotations

from typing import NamedTuple, Callable

from bs4 import BeautifulSoup


def _sweep_dropped_shipped_id(page, html_source: str, limit: int = 12) -> list:
    """Deterministic page-health sweep: the script deleted ids the HTML shipped.

    The HTML agent renders every spec id into the markup, and Test Generation
    selects components by those ids. When the script RE-RENDERS a region and
    rebuilds its rows with text only, those ids vanish: on po015df552 renderCart()
    rebuilt the quantity <option>s as `<option>1</option>`, wiping
    #cart-qty-option-1..4, so every case that selected one by id then found
    nothing (TC-073..076). The page still looked fine, and no single agent could
    see the fault -- the HTML shipped the ids, the JS dropped them, the CSS was
    innocent.

    Compares the ids the STATIC html shipped (parsed from html_source, the page as
    delivered, before any script ran) against the ids present in the live DOM after
    the script has run. Any shipped id now absent was deleted by the script. Ids
    inside a <template> are excluded: the browser never exposes template content
    through document.querySelectorAll, so they are legitimately absent from the
    live set. Fails OPEN -- no html_source, a parse error, or a page read error
    yields no finding rather than a false one. Routed to the JS agent (the deletion
    is the script's), severity high: it breaks every id selector the suite uses."""
    if not html_source:
        return []
    try:
        _soup = BeautifulSoup(html_source, "html.parser")
        shipped = []
        for _el in _soup.select("[id]"):
            _iid = (_el.get("id") or "").strip()
            if not _iid or _el.find_parent("template") is not None:
                continue
            if _iid not in shipped:
                shipped.append(_iid)
    except Exception:
        return []
    if not shipped:
        return []
    try:
        live = page.evaluate(
            "() => Array.from(document.querySelectorAll('[id]')).map(e => e.id)")
    except Exception:
        return []
    _live = {str(i) for i in (live or [])}
    dropped = [i for i in shipped if i not in _live]
    if not dropped:
        return []
    shown = ", ".join("#" + d for d in dropped[:limit])
    more  = "" if len(dropped) <= limit else f" (+{len(dropped) - limit} more)"
    reason = (
        f"the script deleted {len(dropped)} element id(s) that the HTML shipped, so "
        f"every test and selector that targets them now finds nothing. This is a "
        f"re-render that rebuilds rows without carrying their ids -- for example "
        f"renderCart() rebuilding a quantity <select> as plain <option>text</option>, "
        f"wiping #cart-qty-option-1..n. When you re-create a row or control the HTML "
        f"already shipped, copy its id and machine attributes (value, data-*) verbatim; "
        f"set only the visible text and the selected/checked state. Dropped ids: "
        f"{shown}{more}.")
    return [{
        "id":          "AUTO-DROPID-01",
        "component":   "#" + dropped[0],
        "description": "the script removed element id(s) the HTML shipped (re-render dropped ids)",
        "action":      "dropped_shipped_id",
        "selector":    "#" + dropped[0],
        "expected":    "every id the HTML shipped is still present after the script runs",
        "passed":      False,
        "severity":    "high",
        "reason":      reason,
    }]


def _sweep_resources(page) -> list:
    """Deterministic page-health sweep: which images failed to load?

    This is the Python half of the pattern at PAGE level. The suite the Test
    Generation Agent writes is one kind of verification and a model chooses what
    goes in it; this is the other kind, and no model decides whether it runs.
    It exists because assert_visible resolves to `query_selector(...) is not
    None`, so a broken <img> is still in the DOM and passes -- the page can
    satisfy its whole suite while showing nothing (report section 6.4,
    challenge 9).

    Deliberately NOT written into test_cases. Three reasons:
      1. these are findings, not cases -- nothing re-runs them next round, and
         _execute_action has no "image_load" branch, so a stored one would fail
         permanently as an unknown action;
      2. the final test pass rate must stay a measurement of the authored suite;
      3. the AUTO-IMG- prefix lets a network blip be told apart from a code
         defect when the evaluation campaign is analysed.

    They still reach the Secondary Orchestrator: _build_report takes them as a
    separate argument and emits the same work-order line, so _route_agent sends
    them to the HTML agent and the existing correction loop repairs them.

    The component a finding names is the image's own id/class when it has one,
    otherwise its nearest addressable ancestor -- see the closest() call below.
    """
    try:
        # Give a slow image a moment to finish, but never block on a hung one --
        # a hung image is exactly the finding we are here to report.
        page.wait_for_function(
            "() => Array.from(document.images).every(i => i.complete)",
            timeout=5000)
    except Exception:
        pass

    try:
        # An <img> usually carries no id or class of its own, so fall back to the
        # nearest addressable ANCESTOR -- for a product photo that is the product
        # card, which is what the specification names and what the HTML agent can
        # actually aim a modification at. Without this the work order reads
        # `target_component=image`, which points at nothing.
        broken = page.evaluate("""() => Array.from(document.images)
            .filter(i => !i.complete || i.naturalWidth === 0)
            .map(i => {
                const a   = i.closest('[id],[class]') || i;
                const own = (typeof i.className === 'string' ? i.className : '').trim();
                const anc = (typeof a.className === 'string' ? a.className : '').trim();
                return {src: i.getAttribute('src') || '',
                        id:  i.id || a.id || '',
                        cls: own || anc,
                        alt: i.getAttribute('alt') || ''};
            })""")
    except Exception:
        return []
    if not isinstance(broken, list):
        return []          # a mocked page returns a stub, not a list

    try:
        total = int(page.evaluate("() => document.images.length"))
    except Exception:
        total = 0
    # Every image down = environment, not code. See _INFRA_ACTIONS above.
    all_down = bool(broken) and total > 0 and len(broken) >= total

    out = []
    for n, im in enumerate([b for b in broken if isinstance(b, dict)], 1):
        cls  = (im.get("cls") or "").split()
        # Selector Contract shape: .className when there is one, else #id.
        sel  = f".{cls[0]}" if cls else (f"#{im['id']}" if im.get("id") else "img")
        comp = (cls[0] if cls else im.get("id")) or "image"
        src  = im.get("src") or "<no src>"
        if all_down:
            reason = (f"EVERY image on the page failed to load ({total} of "
                      f"{total}), including src={src[:60]}. That is an "
                      f"environment or network fault, not a defect in the HTML. "
                      f"Do NOT edit the page. Report it and continue.")
        else:
            reason = (f"image failed to load (src={src[:80]}). Replace the src "
                      f"with a bundled local photograph listed in the prompt, "
                      f"e.g. img/coffee-beans.jpg, used verbatim -- remote "
                      f"images are not allowed. Do NOT substitute a data: URI, "
                      f"an inline <svg> or any drawn placeholder - that hides "
                      f"the failure instead of fixing it, and ships a page with "
                      f"no product photo. Other images on this page loaded, so "
                      f"this src is the one to fix.")
        out.append({
            "id":          f"AUTO-IMG-{n:02d}",
            "component":   comp,
            "description": f"Image resource loads: {im.get('alt') or src[:40]}",
            "action":      "image_load_infra" if all_down else "image_load",
            "selector":    sel,
            "expected":    "the image renders (naturalWidth > 0)",
            "passed":      False,
            "reason":      reason,
        })
    return out




def _sweep_grid_targets(page, limit: int = 8) -> list:
    """Deterministic page-health sweep: is each grid on the right element?

    The Grid Target Contract. A region's layoutType says HOW its child components
    are arranged, and on PO-08 po01e9a8b4 the CSS agent read that literally and
    put display:grid on the region -- whose direct children were a heading and a
    wrapper, not the repeating items:

        #category-navigation   repeat(6, minmax(0, 1fr))   children: <h2>, <ul>

    Six columns, two items. The heading took column one, the <ul> took column two
    at 168px, and its six <li> piled on top of one another, which is why
    Playwright refused to click the category tiles. The same shape appeared twice
    more on that page: #roast-level-guide 3 cols / 2 items, and
    .footer-trust-banner 4 cols / 2 items -- the white band across the dark footer.

    Reads the AUTHORED grid-template-columns off document.styleSheets, never the
    computed one. getComputedStyle resolves repeat() into a track list, so an
    honest `repeat(auto-fill, minmax(var(--grid-min), 1fr))` holding two products
    reads as "4 tracks, 2 items" and looks identical to the defect -- creating
    empty tracks is what auto-fill is FOR. The first version of this check read
    the computed value and flagged seven healthy fixture pages for exactly that.
    auto-fill and auto-fit are therefore skipped outright.

    Over the 129 preview pages on disk, 125 score 0. The four that fire are
    po01e9a8b4 (3), po0113ce72 (3), po01ba89e9 (2) and po01e49777 (1), and every
    hit is a grid asking for more fixed columns than it has items. There is no
    threshold to tune.

    NOTE it needs the --allow-file-access-from-files launch flag, for the reason
    given in _get_browser: without it document.styleSheets is unreadable from a
    file:// page and this returns [] on every run, exactly as
    _sweep_dead_selectors silently did for a week.
    """
    JS = r'''() => {
        const name = e => e.id ? '#' + e.id
            : (typeof e.className === 'string' && e.className.trim()
               ? '.' + e.className.trim().split(/\s+/)[0] : e.tagName.toLowerCase());
        const authored = [];
        const walk = (rules) => {
            for (const r of rules) {
                if (r.selectorText === undefined) {
                    if (r.cssRules) { try { walk(r.cssRules); } catch (e) {} }
                    continue;
                }
                const v = r.style && r.style.getPropertyValue('grid-template-columns');
                if (v) authored.push([r.selectorText, v.trim()]);
            }
        };
        for (const sh of document.styleSheets) {
            let rs; try { rs = sh.cssRules; } catch (e) { continue; }
            if (rs) walk(rs);
        }
        const seen = {}, bad = [];
        for (const pair of authored) {
            const sel = pair[0], val = pair[1];
            if (/auto-fill|auto-fit/.test(val)) continue;
            const m = val.match(/repeat\(\s*(\d+)/);
            const n = m ? parseInt(m[1], 10)
                        : val.split(/\s+(?![^(]*\))/).filter(Boolean).length;
            if (n < 2) continue;
            let els; try { els = document.querySelectorAll(sel); } catch (e) { continue; }
            for (const e of els) {
                if (!getComputedStyle(e).display.includes('grid')) continue;
                const kids = [...e.children].filter(k => {
                    const kc = getComputedStyle(k);
                    return kc.display !== 'none' && kc.position !== 'absolute'
                        && kc.position !== 'fixed';
                });
                if (!kids.length || n <= kids.length) continue;
                const key = name(e) + '|' + n;
                if (seen[key]) continue;
                seen[key] = 1;
                const tags = kids.map(k => '<' + k.tagName.toLowerCase() + '>').join(', ');
                bad.push(name(e) + ' declares ' + n + ' columns (' + val + ') but has '
                         + kids.length + ' item(s): ' + tags);
            }
        }

        // ---- check 2: the grid is on the wrong LEVEL ---------------------
        // Check 1 above skips auto-fill/auto-fit, so an honest reflowing grid
        // whose items are WRAPPERS rather than cards passes it untouched. This
        // asks a different question: does any single grid item contain two or
        // more of the repeating component? If it does, those two were not laid
        // out by the grid -- they stacked inside one cell.
        const wrong = [];
        for (const g of document.querySelectorAll('*')) {
            const gc = getComputedStyle(g);
            if (!gc.display.includes('grid')) continue;
            const tracks = (gc.gridTemplateColumns || '').trim()
                .split(/\s+/).filter(t => t && t !== 'none').length;
            if (tracks < 2) continue;      // one column is a gap, not a layout
            const kids = [...g.children].filter(k => {
                const kc = getComputedStyle(k);
                return kc.display !== 'none' && kc.position !== 'absolute'
                    && kc.position !== 'fixed';
            });
            if (kids.length < 3) continue;
            const classOf = e => (typeof e.className === 'string'
                ? e.className.trim().split(/\s+/).filter(Boolean) : []);
            const onKids = {};
            kids.forEach(k => classOf(k).forEach(n => onKids[n] = (onKids[n] || 0) + 1));
            // a class shared by 3+ DIRECT children means the items ARE the
            // children, which is the whole point of the grid. Nothing to say.
            if (Object.values(onKids).some(v => v >= 3)) continue;
            const below = {};
            for (const d of g.querySelectorAll('[class]')) {
                if (d.parentElement === g) continue;
                classOf(d).forEach(n => below[n] = (below[n] || 0) + 1);
            }
            const top = Object.keys(below).filter(n => below[n] >= 3)
                .sort((a, b) => below[b] - below[a])[0];
            if (!top) continue;
            let per;
            try { per = kids.map(k => k.querySelectorAll('.' + CSS.escape(top)).length); }
            catch (e) { continue; }
            // One wrapper per item (<li><thumb></li>) is the ordinary list
            // idiom and is fine. Two inside one cell is the defect.
            if (Math.max.apply(null, per) < 2) continue;
            wrong.push(name(g) + ' lays out ' + kids.length + ' item(s) ['
                + kids.map(k => '<' + k.tagName.toLowerCase() + '>').join(', ')
                + '] but the ' + below[top] + ' .' + top
                + ' you meant to arrange are one level below, '
                + per.join('/') + ' per item');
        }
        return {cols: bad, level: wrong};
    }'''
    try:
        got = page.evaluate(JS)
    except Exception:
        return []
    if not isinstance(got, dict):
        return []
    bad = [b for b in (got.get("cols") or []) if isinstance(b, str) and b.strip()]
    wrong = [w for w in (got.get("level") or []) if isinstance(w, str) and w.strip()]
    out = []
    shown = "; ".join(bad[:limit])
    more = "" if len(bad) <= limit else f" (+{len(bad) - limit} more)"
    if bad:
        out.append({
        "id":          "AUTO-GRID-01",
        "component":   _first_selector(bad),
        "description": "A grid declares more columns than it has items",
        "action":      "grid_target",
        "selector":    "(stylesheet)",
        "expected":    "a grid's direct children are its repeating items",
        "passed":      False,
        "reason": (
            f"{len(bad)} grid(s) declare more fixed columns than they have "
            f"items, so the grid is on the wrong element: its direct children "
            f"are a heading and a wrapper, and the items you meant to lay out "
            f"are one level further down. The heading takes column one, the "
            f"wrapper is squeezed into a single narrow column, and its contents "
            f"pile up inside it -- which is how a row of category tiles becomes "
            f"an unreadable, unclickable stack. Put display:grid on the element "
            f"whose DIRECT CHILDREN are the repeating items, leave the section "
            f"heading outside the grid (or span it with grid-column: 1 / -1), "
            f"and prefer repeat(auto-fill, minmax(var(--grid-min), 1fr)) so the "
            f"count never has to match by hand. Offending: {shown}{more}."),
        })

    if wrong:
        w_shown = "; ".join(wrong[:limit])
        w_more = "" if len(wrong) <= limit else f" (+{len(wrong) - limit} more)"
        out.append({
            "id":          "AUTO-GRID-02",
            "component":   _first_selector(wrong),
            "description": "A grid is one level above the items it should arrange",
            "action":      "grid_target",
            "selector":    "(stylesheet)",
            "expected":    "the repeating component is a DIRECT child of its grid",
            "passed":      False,
            "reason": (
                f"{len(wrong)} grid(s) are on the wrong element. The column "
                f"count is fine, but the components you meant to arrange are "
                f"one level below the grid, so the grid is laying out their "
                f"WRAPPERS instead. Two components inside one grid cell are not "
                f"arranged by the grid at all -- they stack, and the cell "
                f"stretches to hold them, which is how one product group "
                f"becomes a 2863px column that overflows onto the row beneath. "
                f"Move display:grid down to the element whose DIRECT CHILDREN "
                f"are those components. If the wrappers exist only to carry "
                f"anchor ids, the ids belong on the components themselves and "
                f"the wrappers should not exist; if the groups are real, give "
                f"EACH group its own grid and stack the groups normally. "
                f"Offending: {w_shown}{w_more}."),
        })

    return out


def _sweep_geometry(page, limit: int = 12) -> list:
    """Deterministic page-health sweep: can a visitor actually reach the controls?

    The third of the page-level sweeps, and the only one that measures WHERE
    things are. Every assertion the Test Generation Agent can write resolves
    through query_selector -- assert_text, assert_attribute, assert_count,
    assert_css, assert_url -- so each asks whether an element exists and what it
    says. None asks whether a click would land on it.

    On PO-08 po01e9a8b4 a grid applied to the wrong element squeezed six category
    tiles into a 168px column, the <li> covered one another, and Playwright
    refused the click with "<li> intercepts pointer events". assert_text on those
    same tiles passed: the elements were in the DOM with the right words in them.
    The page was untappable and its whole suite reported green.

    Two checks, chosen by measurement over the 127 preview pages on disk:

        covered control      125 of 127 pages score 0. The two that fire are
                             po0108202d (11 of 32 controls) and po01e9a8b4
                             (5 of 41), both known broken.
        horizontal overflow  126 of 127 score 0.

    A third candidate -- every top-level region shares one column width -- was
    dropped: its best variant scored 0 on only 34 of 45 pages, because a
    full-bleed band with a centred inner wrapper is a legitimate design and reads
    as a mismatch. A guard that fires on a quarter of healthy pages buys a
    correction round and fixes nothing.

    Returns at most one consolidated finding per check, never one per element,
    for the reason _sweep_dead_selectors gives.

    Two details in the browser half are load-bearing:
      * scrollIntoView must be behaviour "instant". The generated stylesheets set
        `html { scroll-behavior: smooth }`, which makes the default an animation,
        so the rectangle is read before the scroll lands and every centre point
        falls outside the viewport. The first version of this check reported 34
        of 41 controls unreachable on a page where the true number was 5.
      * a hit counts when the topmost element IS the control, CONTAINS it, is
        CONTAINED by it, or resolves to the same <a>/<button> ancestor. An icon
        or a label span inside a button is the normal case, not a defect.
    """
    JS = r'''() => {
        const blocked = [];
        let considered = 0;
        for (const e of document.querySelectorAll('a[href], button')) {
            const c = getComputedStyle(e);
            if (c.display === 'none' || c.visibility === 'hidden' || c.opacity === '0') continue;
            const r0 = e.getBoundingClientRect();
            if (r0.width < 2 || r0.height < 2) continue;
            e.scrollIntoView({block: 'center', behavior: 'instant'});
            const r = e.getBoundingClientRect();
            const cx = r.x + r.width / 2, cy = r.y + r.height / 2;
            if (cx < 0 || cy < 0 || cx > innerWidth || cy > innerHeight) continue;
            considered++;
            const top = document.elementFromPoint(cx, cy);
            if (!top) continue;
            if (top === e || e.contains(top) || top.contains(e)) continue;
            if (top.closest('a,button') === e) continue;
            // '#' on the id, to match the shape `over` uses below. Without it
            // the message read `link-one is covered by #link-two` and
            // _first_selector picked the COVERER as the component to fix.
            // The mocked unit case fed a string that already had the '#',
            // so it passed while the browser half produced the other shape.
            const label = (e.id ? '#' + e.id
                : (typeof e.className === 'string' && e.className.trim()
                   ? '.' + e.className.trim().split(/\s+/)[0]
                   : e.tagName.toLowerCase()));
            const over = top.id ? '#' + top.id
                       : (typeof top.className === 'string' && top.className.trim()
                          ? '.' + top.className.trim().split(/\s+/)[0]
                          : '<' + top.tagName.toLowerCase() + '>');
            blocked.push(label + ' is covered by ' + over);
        }
        const d = document.documentElement;
        return {blocked: blocked, considered: considered,
                overflow: d.scrollWidth - d.clientWidth,
                width: d.clientWidth};
    }'''
    try:
        got = page.evaluate(JS)
    except Exception:
        return []
    if not isinstance(got, dict):
        return []             # a mocked page returns a stub, not a dict

    out = []

    blocked = [b for b in (got.get("blocked") or []) if isinstance(b, str)]
    considered = int(got.get("considered") or 0)
    if blocked:
        shown = "; ".join(blocked[:limit])
        more = "" if len(blocked) <= limit else f" (+{len(blocked) - limit} more)"
        out.append({
            "id":          "AUTO-GEO-01",
            # The covered control. The FIX is usually on its container,
            # but starting at the control is how the agent reaches the
            # container, and it extracts, which "stylesheet" does not.
            "component":   _first_selector(blocked),
            "description": "Controls a visitor cannot click",
            "action":      "layout_unclickable",
            "selector":    "(layout)",
            "expected":    "a click at each control's own centre reaches it",
            "passed":      False,
            "reason": (
                f"{len(blocked)} of {considered} link(s)/button(s) on screen "
                f"cannot be clicked: at each one's own centre the topmost "
                f"element is something else, so the browser sends the click "
                f"there instead. This is a LAYOUT fault -- boxes overlapping, a "
                f"container too narrow for its children, or a sticky element "
                f"lying over the page -- not a markup or script fault, and no "
                f"DOM assertion can see it: the elements exist and their text "
                f"is correct, so the suite reports green while the page is "
                f"untappable. Give each control room: check the container's "
                f"display and grid-template-columns, and make sure a grid is on "
                f"the element whose CHILDREN are the repeating items. "
                f"Covered: {shown}{more}."),
        })

    try:
        overflow = int(got.get("overflow") or 0)
        width = int(got.get("width") or 0)
    except (TypeError, ValueError):
        overflow, width = 0, 0
    if overflow > 1:
        out.append({
            "id":          "AUTO-GEO-02",
            "component":   "stylesheet",
            "description": "The page scrolls sideways",
            "action":      "layout_overflow",
            "selector":    "(layout)",
            "expected":    "the document is no wider than the viewport",
            "passed":      False,
            "reason": (
                f"the document is {overflow}px wider than the {width}px "
                f"viewport, so the whole page scrolls sideways and part of "
                f"every section is off screen. Something is set to a fixed "
                f"width, has a negative margin, or is a grid whose columns add "
                f"up to more than its container. Use the shared page container "
                f"(max-width plus padding-inline) and let grids reflow with "
                f"repeat(auto-fill, minmax(...))."),
        })

    return out



def _first_selector(rows, fallback="stylesheet"):
    """The first #id or .class mentioned in a sweep's offender list.

    A finding's `component` becomes target_component in the work order, and the
    CSS agent's modify loop calls extract_css_component on it. "stylesheet" is
    not a component: it extracts nothing and costs a turn out of a round that
    only has one. Every sweep here knows a real selector -- the dead rule, the
    misplaced grid, the covered control -- so it hands that over instead and
    leaves the rest of the list in the reason.
    """
    import re as _re
    for row in rows or []:
        m = _re.search(r"[#.][A-Za-z_][\w-]*", str(row))
        if m:
            return m.group(0)
    return fallback



def _sweep_evidence(page) -> str:
    """One line saying what the sweeps could SEE. Evidence, never a finding.

    An empty sweep result means "nothing wrong" or "I could not look", and those
    are opposite facts that looked identical until this line existed. Two bills
    were paid for that: a dead sweep that ran silently for a week from
    2026-08-24, and an evening spent on SO-01 trying to decide, after the fact,
    which of the two had happened.

    Deliberately NOT a finding: it carries no `action`, so _route_agent never
    sees it, no work order is built from it, and it cannot consume a correction
    round. It is a footer, in the same report, so it survives in the transcript
    next to the result it explains.
    """
    JS = """() => {
        let sheets = 0, readable = 0, rules = 0;
        for (const s of document.styleSheets) {
            sheets++;
            let r;
            try { r = s.cssRules; } catch (e) { continue; }
            if (r) { readable++; rules += r.length; }
        }
        return {sheets: sheets, readable: readable, rules: rules,
                controls: document.querySelectorAll('a[href], button').length,
                grids: Array.from(document.querySelectorAll('*')).filter(
                    e => getComputedStyle(e).display.indexOf('grid') === 0).length,
                w: document.documentElement.scrollWidth,
                h: document.documentElement.scrollHeight};
    }"""
    try:
        s = page.evaluate(JS)
    except Exception as e:
        return (f"[sweep] COULD NOT MEASURE THE PAGE: {type(e).__name__}: {e}. "
                f"Every sweep below returned nothing because it could not look, "
                f"not because the page is sound.")
    if not isinstance(s, dict):
        return "[sweep] the page returned an unexpected shape; treat the sweeps as blind."
    unread = s["sheets"] - s["readable"]
    warn = ""
    if unread:
        warn = (f"  <-- {unread} stylesheet(s) UNREADABLE, so the dead-selector "
                f"and grid sweeps are blind. On a file:// page that means the "
                f"browser lost --allow-file-access-from-files.")
    return (f"[sweep] read {s['readable']}/{s['sheets']} stylesheet(s), "
            f"{s['rules']} rule(s); page {s['w']}x{s['h']}px with "
            f"{s['controls']} control(s) and {s['grids']} grid(s).{warn}")


def _sweep_dead_selectors(page, limit: int = 25) -> list:
    """Deterministic page-health sweep: which CSS selectors match NO element?

    The companion to _sweep_resources. A stylesheet rule whose selector matches
    nothing never applies, so the page can lint clean, pass every DOM assertion
    (the suite targets the ids the HTML emits, which exist), and still look
    unstyled -- the CSS agent styled class names the HTML never produced. This is
    the CSS<->DOM Naming/Selector Contract drift: on one real run 47 of the
    stylesheet's class selectors matched nothing, so the whole layout fell back
    to plain block flow. The suite structurally cannot catch it, so a page-level
    browser check is the only place it surfaces.

    Runs in the browser: reads document.styleSheets, and for each style rule
    strips pseudo-classes, pseudo-elements and attribute qualifiers (which depend
    on runtime STATE, not on whether the base element exists) down to the
    structural selector, then counts querySelectorAll matches. Only a structural
    selector matching 0 elements is 'dead' -- a state selector like
    .btn[aria-disabled='true'] is NOT flagged while .btn exists.

    Returns at most ONE consolidated finding (routed to the CSS agent), never one
    per selector: a drifted stylesheet has dozens of dead rules and one work
    order per rule would bury the report and exhaust the correction loop."""
    JS = r"""() => {
        const dead = [];
        const walk = (rules) => {
            for (const rule of rules) {
                if (rule.selectorText === undefined) {
                    if (rule.cssRules) { try { walk(rule.cssRules); } catch (e) {} }
                    continue;
                }
                for (let sel of rule.selectorText.split(',')) {
                    sel = sel.trim();
                    if (!sel) continue;
                    const base = sel
                        .replace(/::?[a-zA-Z-]+(\([^)]*\))?/g, '')
                        .replace(/\[[^\]]*\]/g, '')
                        .trim();
                    if (!base || base === '*' || base === 'html' || base === 'body') continue;
                    let n = 0;
                    try { n = document.querySelectorAll(base).length; } catch (e) { continue; }
                    if (n === 0 && !dead.includes(sel)) dead.push(sel);
                }
            }
        };
        for (const sheet of document.styleSheets) {
            let rules;
            try { rules = sheet.cssRules; } catch (e) { continue; }
            if (rules) walk(rules);
        }
        return dead;
    }"""
    try:
        dead = page.evaluate(JS)
    except Exception:
        return []
    if not isinstance(dead, list) or not dead:
        return []
    dead = [d for d in dead if isinstance(d, str) and d.strip()]
    if not dead:
        return []
    shown = ", ".join(dead[:limit])
    more = "" if len(dead) <= limit else f" (+{len(dead) - limit} more)"
    reason = (
        f"{len(dead)} CSS selector(s) match NO element in the rendered page, so "
        f"their styling never applies. This is the usual cause of an unstyled or "
        f"irregular layout: the stylesheet targets names the HTML never emits. Fix "
        f"the CSS to target the ids and classes the HTML actually uses (Selector "
        f"Contract: .className when the component has one, else #id), or drop the "
        f"rule -- never keep a rule that matches nothing. Dead selectors: "
        f"{shown}{more}."
    )
    return [{
        "id":          "AUTO-CSS-01",
        # The first dead rule, not "stylesheet" -- see _first_selector.
        # A dead selector matches no ELEMENT but it IS in the stylesheet,
        # so extract_css_component finds its block and the agent can
        # rewrite or delete it.
        "component":   _first_selector(dead),
        "description": "CSS selectors that match no element in the DOM",
        "action":      "css_dead_selector",
        "selector":    "(stylesheet)",
        "expected":    "every CSS rule matches at least one element",
        "passed":      False,
        "reason":      reason,
    }]


def _sweep_bulleted_nav(page, limit: int = 8) -> list:
    """Deterministic page-health sweep: a navigation list left as default bullets.

    The CSS prompt already asks for it -- a <ul>/<ol> used as navigation gets
    `list-style: none` and a flex/grid row -- but that is a "decide", and nothing
    guaranteed it. On PO-08 po01e82f54 the CSS agent skipped it: both <nav> lists
    shipped as a bulleted vertical strip. No other sweep sees this, because the
    rule is not DEAD (there simply is no rule) and every selector the suite
    asserts still resolves. This is the guarantee half.

    Runs in the browser. Flags a <ul>/<ol> inside a <nav> whose computed
    list-style-type is not 'none' AND whose display is not a flex/grid row -- i.e.
    left completely unreset. A list laid out as a row, or already reset, is not
    flagged, so a properly styled nav passes. Each offender is reported at its
    STYLED OWNER -- the nearest [data-component] ancestor, whose Selector-Contract
    selector already has a decoration rule -- so the CSS agent can extract that
    block and add a `<owner> ul` reset beside it rather than hunt for a rule that
    does not exist yet. Returns at most ONE consolidated finding, routed to CSS."""
    JS = r"""() => {
        const bad = [];
        const isRow = d => ['flex','inline-flex','grid','inline-grid'].includes(d);
        const selOf = el => {
            if (el.classList && el.classList.length) return '.' + el.classList[0];
            if (el.id) return '#' + el.id;
            return el.tagName.toLowerCase();
        };
        for (const nav of document.querySelectorAll('nav')) {
            for (const list of nav.querySelectorAll('ul, ol')) {
                const cs = getComputedStyle(list);
                if (cs.listStyleType !== 'none' && !isRow(cs.display)) {
                    const owner = list.closest('[data-component]') || nav;
                    const entry = selOf(owner) + ' ' + list.tagName.toLowerCase();
                    if (!bad.includes(entry)) bad.push(entry);
                }
            }
        }
        return bad;
    }"""
    try:
        bad = page.evaluate(JS)
    except Exception:
        return []
    if not isinstance(bad, list):
        return []
    bad = [b for b in bad if isinstance(b, str) and b.strip()]
    if not bad:
        return []
    shown = ", ".join(bad[:limit])
    more = "" if len(bad) <= limit else f" (+{len(bad) - limit} more)"
    owner = bad[0].rsplit(" ", 1)[0]
    reason = (
        f"{len(bad)} navigation list(s) render as a default bulleted vertical "
        f"strip: the <ul>/<ol> has no list-style reset and is not laid out as a "
        f"flex/grid row. For each, extract its styled owner's block and add a rule "
        f"that gives the list `list-style: none; margin: 0; padding: 0` and lays "
        f"its items out with flex or grid, so the links sit in a row without "
        f"bullets. A <ul> is a real descendant of its owning component, so the "
        f"selector is allowed even though the list carries no className. Lists: "
        f"{shown}{more}."
    )
    return [{
        "id":          "AUTO-NAV-01",
        "component":   owner,
        "description": "navigation list(s) left as default bullets (no list-style reset)",
        "action":      "nav_list_unreset",
        "selector":    "(nav lists)",
        "expected":    "navigation <ul>/<ol> reset with list-style:none and laid out as a row",
        "passed":      False,
        "reason":      reason,
    }]


def _sweep_hidden_not_honored(page, limit: int = 8) -> list:
    """Deterministic page-health sweep: does the page honor the [hidden] attribute?

    The idiomatic way JS shows and hides an element is the `hidden` property --
    setCardVisibility does `card.hidden = !isVisible`. The attribute is supposed
    to force `display:none`, but a component rule with a real display value wins
    over the UA `[hidden]{display:none}` by specificity. On PO-08 po0118d1da the
    stylesheet carried `.coffee-product-card{display:flex}` and no [hidden]
    reset, so every `card.hidden = true` set the attribute and changed nothing on
    screen: the search and roast filter hid non-matches in the DOM while the page
    looked identical -- a filter that is fully wired and looks completely dead.
    No other sweep sees this: the selector is not dead, no geometry is wrong, and
    the authored suite asserts on the resting page where nothing is hidden yet.

    Runs in the browser. PROBES every [data-component] element: sets `hidden`,
    reads the computed display, restores it. An element whose display stays
    non-none does not honor [hidden] -- its owner selector is collected. The page
    is about to close, and the probe restores as it goes, so the delivered page
    is untouched. Returns at most ONE consolidated finding routed to the CSS
    agent, whose one-line fix (`[hidden]{display:none !important}`) heals every
    offender at once. Severity high: it kills a whole interaction.

    GATED on real use: a component that overrides [hidden] is only a defect
    when the page's own script hides something with the hidden property --
    otherwise nothing ever sets it and the missing reset is harmless. The
    page is served from file://, where fetch of a sibling is blocked, so the
    sibling preview_<sid>.js is read off disk (its path derived from
    page.url) and checked for a `.hidden =` or setAttribute('hidden', ...)
    write. Unreadable or absent -> stay silent, the _sweep_evidence rule that
    an empty result must never conflate "clean" with "could not look". A
    non-file page (a test double) skips the gate and probes directly."""
    import re as _re_h, pathlib as _pl_h
    from urllib.parse import urlparse as _urlparse_h, unquote as _unquote_h
    try:
        _url = page.url or ""
    except Exception:
        return []
    if isinstance(_url, str) and _url.startswith("file:"):
        # A test double gives page.url a MagicMock, whose .startswith returns a
        # truthy MagicMock; without the isinstance check that mock is parsed as a
        # file path and urlparse raises. The docstring's "a non-file page (a test
        # double) skips the gate" is only true with this guard -- same defensive
        # style as the isinstance(bad, list) check below.
        _pstr = _unquote_h(_urlparse_h(_url).path)
        if _re_h.match(r"^/[A-Za-z]:", _pstr):   # file:///C:/... -> C:/...
            _pstr = _pstr[1:]
        try:
            _js = _pl_h.Path(_pstr).with_suffix(".js").read_text(
                encoding="utf-8", errors="ignore")
        except Exception:
            return []
        if not _re_h.search(r"\.hidden\s*=|setAttribute\(\s*['\"]hidden['\"]", _js):
            return []
    JS = r"""() => {
        const selOf = el => {
            if (el.classList && el.classList.length) return '.' + el.classList[0];
            if (el.id) return '#' + el.id;
            return el.tagName.toLowerCase();
        };
        const bad = [];
        const seen = new Set();
        for (const el of document.querySelectorAll('[data-component]')) {
            const wasHidden = el.hasAttribute('hidden');
            if (!wasHidden) el.setAttribute('hidden', '');
            const disp = getComputedStyle(el).display;
            if (!wasHidden) el.removeAttribute('hidden');
            if (disp !== 'none') {
                const s = selOf(el);
                if (!seen.has(s)) { seen.add(s); bad.push(s); }
            }
        }
        return bad;
    }"""
    try:
        bad = page.evaluate(JS)
    except Exception:
        return []
    if not isinstance(bad, list):
        return []
    bad = [b for b in bad if isinstance(b, str) and b.strip()]
    if not bad:
        return []
    shown = ", ".join(bad[:limit])
    more = "" if len(bad) <= limit else f" (+{len(bad) - limit} more)"
    owner = bad[0]
    reason = (
        f"{len(bad)} component(s) stay visible after the hidden attribute is set: "
        f"their computed display is not none, so a component rule (such as "
        f"display:flex on the class) overrides the [hidden] reset. JS that hides "
        f"an element with `el.hidden = true` then changes nothing on screen, so a "
        f"search or filter that hides its non-matching items looks completely "
        f"dead. Add a `[hidden]{{display:none !important}}` rule to the stylesheet "
        f"-- one rule heals every one of these -- or make sure these components' "
        f"display declaration does not override [hidden]. Components: "
        f"{shown}{more}."
    )
    return [{
        "id":          "AUTO-HIDDEN-01",
        "component":   owner,
        "description": "component(s) do not honor the [hidden] attribute (display overrides it)",
        "action":      "hidden_not_honored",
        "selector":    "(hidden probe)",
        "expected":    "an element carrying the hidden attribute computes display:none",
        "passed":      False,
        "severity":    "high",
        "reason":      reason,
    }]


def _sweep_row_container_unstyled(page, limit: int = 8) -> list:
    """Deterministic page-health sweep: a header/footer/nav bar left stacking.

    A landmark groups its parts in a container that is meant to be a flex or grid
    ROW -- the header's brand/nav/search/cart, the footer's columns. When the CSS
    agent never styles that container it stays display:block, so the parts stack
    vertically and the landmark swells. On PO-08 po0118d1da the header ran 223px
    (25% of a 900px viewport) because .site-header-shell was unstyled and its four
    parts sat in four rows, and the footer ran 512px (57%) for the same reason on
    .footer-columns. _sweep_geometry sees a covered control or an overflow, not a
    region that is merely too tall, and _sweep_bulleted_nav only sees a <ul>; a
    plain <div> container falls between them.

    Runs in the browser. For each header/footer/nav landmark it looks only at its
    DIRECT-child containers (a nested <ul> of links is a real vertical list, not a
    mislaid row, so it is out of scope). A direct child is flagged when it is NOT
    a flex/grid row AND holds 3+ element children that sit on 3+ distinct top
    offsets -- i.e. a multi-part bar left stacking. Each offender is reported at
    its styled owner (nearest [data-component]) so the CSS agent can extract that
    block and give it a row. One consolidated finding, routed to CSS, severity
    medium (a layout fault, not a dead interaction)."""
    JS = r"""() => {
        const selOf = el => {
            if (el.classList && el.classList.length) return '.' + el.classList[0];
            if (el.id) return '#' + el.id;
            return el.tagName.toLowerCase();
        };
        const isRow = d => ['flex','inline-flex','grid','inline-grid'].includes(d);
        const bad = [];
        const seen = new Set();
        for (const lm of document.querySelectorAll('header, footer, nav')) {
            for (const box of lm.children) {
                const cs = getComputedStyle(box);
                if (isRow(cs.display)) continue;
                const kids = Array.from(box.children).filter(k => k.nodeType === 1);
                if (kids.length < 3) continue;
                const tops = new Set(kids.map(k => Math.round(
                    k.getBoundingClientRect().top)));
                if (tops.size >= 3) {
                    const sel = (box.classList.length || box.id)
                        ? selOf(box)
                        : selOf(box.closest('[data-component]') || box);
                    if (!seen.has(sel)) { seen.add(sel); bad.push(sel); }
                }
            }
        }
        return bad;
    }"""
    try:
        bad = page.evaluate(JS)
    except Exception:
        return []
    if not isinstance(bad, list):
        return []
    bad = [b for b in bad if isinstance(b, str) and b.strip()]
    if not bad:
        return []
    shown = ", ".join(bad[:limit])
    more = "" if len(bad) <= limit else f" (+{len(bad) - limit} more)"
    owner = bad[0]
    reason = (
        f"{len(bad)} structural container(s) in a header/footer/nav stack their "
        f"3+ parts vertically instead of sitting in a row: the container is "
        f"display:block with no flex/grid, which swells the landmark (a header "
        f"stacking brand/nav/search/cart runs a quarter of the viewport tall). "
        f"For each, extract its styled owner's block and give the container "
        f"`display:flex` (or grid) with an alignment and gap, so its parts sit "
        f"side by side and the bar collapses to a normal height. Containers: "
        f"{shown}{more}."
    )
    return [{
        "id":          "AUTO-ROW-01",
        "component":   owner,
        "description": "header/footer/nav container left stacking (no flex/grid row)",
        "action":      "row_container_unstyled",
        "selector":    "(row container)",
        "expected":    "a landmark's multi-part container is laid out as a flex/grid row",
        "passed":      False,
        "severity":    "medium",
        "reason":      reason,
    }]


def _sweep_filter_value_dead(page, limit: int = 6) -> list:
    """Deterministic page-health sweep: a filter <select> whose values match nothing.

    A filter control's <option> should carry the machine TOKEN the script compares
    ('all', 'light'), never the human label. On PO-08 po0118d1da the roast select
    shipped `<option value="All roasts">`, the JS treated a value as show-all only
    when it equalled "all", and roastMatches("light", "all roasts") was false for
    every product -- so the roast filter, and every search that inherits its value
    at load, emptied the whole grid. The page looked completely dead. No selector
    is broken and every element is present, so no other sweep sees it.

    Departs from the "sweeps read the page at rest" norm on purpose: this fault
    only exists once the control acts, and the check is a single deterministic,
    self-restoring interaction. For each <select> it drives the 'show all' option
    (text/value naming all/any, else the first) and counts how many products the
    FILTER chose to show -- by the `hidden` property it sets, not computed display,
    so a stylesheet that also fails to honor [hidden] (AUTO-HIDDEN-01) cannot mask
    this. Showing zero means the value matched nothing. It snapshots and restores
    the select value and every card's hidden flag, so the delivered page and the
    later sweeps are untouched. One consolidated finding routed to the HTML agent
    (the option value is markup), severity high: it kills the whole filter."""
    JS = r"""() => {
        const selOf = el => el.classList && el.classList.length ? '.' + el.classList[0]
                            : (el.id ? '#' + el.id : el.tagName.toLowerCase());
        const products = document.querySelectorAll('[data-component="product-card"]');
        if (!products.length) return [];
        const filterVisible = () =>
            Array.from(products).filter(c => !c.hidden).length;
        const bad = [];
        for (const sel of document.querySelectorAll('select')) {
            if (!sel.options.length) continue;
            const savedValue  = sel.value;
            const savedHidden = Array.from(products).map(c => c.hidden);
            let allOpt = Array.from(sel.options).find(o =>
                /\ball\b|\bany\b/i.test(o.textContent) || /\ball\b|\bany\b/i.test(o.value));
            if (!allOpt) allOpt = sel.options[0];
            sel.value = allOpt.value;
            sel.dispatchEvent(new Event('change', {bubbles: true}));
            const shown = filterVisible();
            sel.value = savedValue;
            sel.dispatchEvent(new Event('change', {bubbles: true}));
            Array.from(products).forEach((c, i) => { c.hidden = savedHidden[i]; });
            if (shown === 0) {
                const s = selOf(sel);
                if (!bad.includes(s)) bad.push(s);
            }
        }
        return bad;
    }"""
    try:
        bad = page.evaluate(JS)
    except Exception:
        return []
    if not isinstance(bad, list):
        return []
    bad = [b for b in bad if isinstance(b, str) and b.strip()]
    if not bad:
        return []
    shown = ", ".join(bad[:limit])
    more = "" if len(bad) <= limit else f" (+{len(bad) - limit} more)"
    owner = bad[0]
    reason = (
        f"{len(bad)} filter select(s) empty the whole product grid when set to "
        f"their 'show all' option: the option's value is a human label, but the "
        f"script compares it against a machine token (such as 'all'), so it "
        f"matches no product and every card is filtered out -- and any search "
        f"that inherits the select's value at load dies with it. Change each "
        f"<option>'s value to the token the script expects (a lowercase word with "
        f"no spaces, e.g. value=\"all\" / \"light\"), leaving the human wording as "
        f"the option's visible text. Selects: {shown}{more}."
    )
    return [{
        "id":          "AUTO-FILTER-01",
        "component":   owner,
        "description": "filter select option value is a label, not the token the script compares",
        "action":      "filter_value_dead",
        "selector":    "(filter select)",
        "expected":    "a filter select's 'show all' option leaves the products visible",
        "passed":      False,
        "severity":    "high",
        "reason":      reason,
    }]


def _sweep_drawer_not_overlay(page, limit: int = 6) -> list:
    """Deterministic page-health sweep: a drawer/modal that never opens.

    An element named or marked as a drawer or dialog is meant to sit OUTSIDE the
    normal flow -- fixed, off-canvas at rest, slid on-screen when opened. This
    sweep catches TWO ways that breaks, both cross-agent contract faults no single
    generating agent can see:

      1. Still in normal flow. On PO-08 po0118d1da the cart drawer
         (#cart-drawer-region, an <aside>) was position:static, full width, parked
         at the very bottom -- opening it changed nothing near the top.
      2. Positioned but never revealed. On PO-08 po0105c9d9 the same drawer WAS
         position:fixed, but the JS opened it by clearing the drawer's `hidden`
         attribute and setting `aria-expanded="true"` on the TOGGLE BUTTON, while
         the stylesheet only lifted `visibility:hidden` on the drawer's OWN
         `[data-state="open"]`/`[aria-expanded="true"]`. The two never met, so a
         click flipped `display` to block but `visibility` stayed hidden and the
         visitor saw nothing. The selector is not dead and the element is present,
         so no other sweep sees either fault.

    Runs in the browser. A candidate declares overlay intent (role="dialog",
    aria-modal, or an id/class naming drawer/off-canvas/modal/dialog/flyout) and
    holds content (>= 1 child). A NON-positioned candidate is flagged outright. A
    positioned candidate that is hidden at rest is driven: its toggle
    (`[aria-controls="<id>"]`) is clicked, and if the drawer does not actually
    become visible (display none, visibility hidden, ~zero opacity,
    pointer-events none, or off-screen) it is flagged. The interaction is
    self-restoring -- it snapshots and puts back the drawer's `hidden`/data-state/
    aria-hidden and the toggle's aria-expanded -- so the delivered page and later
    sweeps are untouched. One consolidated finding routed to the CSS agent,
    severity high: the cart is a primary path and a drawer that never appears
    reads as broken."""
    JS = r"""async () => {
        const selOf = el => el.id ? '#' + el.id
            : (el.classList && el.classList.length ? '.' + el.classList[0]
               : el.tagName.toLowerCase());
        const isOverlayName = s => /drawer|off-?canvas|modal|dialog|flyout/i.test(s || '');
        const sleep = ms => new Promise(r => setTimeout(r, ms));
        const cands = new Set();
        document.querySelectorAll('[role="dialog"], [aria-modal="true"]').forEach(
            e => cands.add(e));
        document.querySelectorAll('[id], [class]').forEach(e => {
            const cls = typeof e.className === 'string' ? e.className : '';
            if (isOverlayName(e.id) || isOverlayName(cls)) cands.add(e);
        });
        const bad = [];
        const push = el => { const s = selOf(el); if (!bad.includes(s)) bad.push(s); };
        for (const el of cands) {
            if (el.children.length < 1) continue;
            const cs = getComputedStyle(el);
            const positioned = ['fixed', 'absolute', 'sticky'].includes(cs.position);
            if (!positioned) { push(el); continue; }
            // Positioned + hidden at rest: prove its toggle actually reveals it.
            const restHidden = cs.display === 'none' || cs.visibility === 'hidden'
                || parseFloat(cs.opacity) < 0.05 || el.hasAttribute('hidden');
            if (!restHidden) continue;
            const id = el.id;
            const toggle = id ? document.querySelector('[aria-controls="' + id + '"]') : null;
            if (!toggle) continue;   // cannot drive it deterministically; do not guess
            const snap = {
                h: el.hasAttribute('hidden'),
                ds: el.getAttribute('data-state'),
                ah: el.getAttribute('aria-hidden'),
                te: toggle.getAttribute('aria-expanded'),
            };
            try {
                toggle.click();
                await sleep(380);           // let any open transition settle
                const o = getComputedStyle(el);
                const r = el.getBoundingClientRect();
                const onScreen = r.width > 1 && r.height > 1 && r.bottom > 0
                    && r.right > 0 && r.top < innerHeight && r.left < innerWidth;
                const revealed = o.display !== 'none' && o.visibility === 'visible'
                    && parseFloat(o.opacity) > 0.05 && o.pointerEvents !== 'none'
                    && onScreen;
                if (!revealed) push(el);
            } catch (e) { /* ignore */ }
            try { toggle.click(); await sleep(20); } catch (e) { /* ignore */ }
            if (snap.h) el.setAttribute('hidden', ''); else el.removeAttribute('hidden');
            if (snap.ds === null) el.removeAttribute('data-state'); else el.setAttribute('data-state', snap.ds);
            if (snap.ah === null) el.removeAttribute('aria-hidden'); else el.setAttribute('aria-hidden', snap.ah);
            if (snap.te === null) toggle.removeAttribute('aria-expanded'); else toggle.setAttribute('aria-expanded', snap.te);
        }
        return bad;
    }"""
    try:
        bad = page.evaluate(JS)
    except Exception:
        return []
    if not isinstance(bad, list):
        return []
    bad = [b for b in bad if isinstance(b, str) and b.strip()]
    if not bad:
        return []
    shown = ", ".join(bad[:limit])
    more = "" if len(bad) <= limit else f" (+{len(bad) - limit} more)"
    owner = bad[0]
    reason = (
        f"{len(bad)} drawer/dialog element(s) fail as an overlay. Either the "
        f"element sits in the normal document flow (position static or relative), "
        f"or it is positioned but never becomes visible when its toggle is "
        f"activated -- the open signal does not line up between JS and CSS: the JS "
        f"clears the drawer's `hidden` attribute and sets `aria-expanded` on the "
        f"toggle BUTTON, while the stylesheet lifts `visibility: hidden` only on "
        f"the drawer's own `[data-state=\"open\"]`, so opening it shows nothing. "
        f"Give each `position: fixed` (or absolute), off-canvas at rest (e.g. "
        f"transform: translateX(100%)) with a transition, and reveal the on-screen "
        f"state via `#drawer:not([hidden])` -- visibility: visible, "
        f"pointer-events: auto, the slid-in transform -- plus a backdrop when it "
        f"is modal. Elements: {shown}{more}."
    )
    return [{
        "id":          "AUTO-DRAWER-01",
        "component":   owner,
        "description": "drawer/dialog not usable as an overlay (in normal flow, or does not open)",
        "action":      "drawer_not_overlay",
        "selector":    "(drawer/dialog)",
        "expected":    "a drawer/dialog is positioned as an overlay and becomes visible when opened",
        "passed":      False,
        "severity":    "high",
        "reason":      reason,
    }]



# ==========================================================================
# The sweep registry
# ==========================================================================
class Sweep(NamedTuple):
    """One page-health sweep. `fn(page)` returns a list of findings;
    `needs_html_source` sweeps get the shipped HTML too: `fn(page, html)`."""
    fn: Callable[..., list]
    needs_html_source: bool = False


# The sweeps run_test_suite runs, in this order. Findings keep this order in
# the report. A new sweep is one line here; nothing else calls a sweep.
PAGE_SWEEPS = (
    Sweep(_sweep_resources),
    Sweep(_sweep_dead_selectors),
    Sweep(_sweep_geometry),
    Sweep(_sweep_grid_targets),
    Sweep(_sweep_bulleted_nav),
    Sweep(_sweep_hidden_not_honored),
    Sweep(_sweep_row_container_unstyled),
    Sweep(_sweep_drawer_not_overlay),
    Sweep(_sweep_filter_value_dead),
    Sweep(_sweep_dropped_shipped_id, needs_html_source=True),
)


def run_page_sweeps(page, html_source: str, tick=None) -> list:
    """Run every registered sweep on `page`, in order; their findings, concatenated.
    `tick`, when given, is called before each sweep: run_test_suite's progress
    mark, so its no-progress limit covers one sweep, not all of them."""
    findings = []
    for sweep in PAGE_SWEEPS:
        if tick is not None:
            tick()
        if sweep.needs_html_source:
            findings = findings + sweep.fn(page, html_source)
        else:
            findings = findings + sweep.fn(page)
    return findings

# Every name this module defines or imports, for the package's __init__ and
# from there for webforge.test_exec, which re-exports it into the load order.
__all__ = [_n for _n in list(globals())
           if not (_n.startswith("__") and _n.endswith("__"))]
