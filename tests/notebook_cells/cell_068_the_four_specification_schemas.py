# Ported from fyp.ipynb cell 68 (ticket 05). The notebook is frozen;
# edit this file. Run by tests/test_notebook_cells.py.
# Unit tests: the four specification schemas
#
# Case 1 and Case 2 exist because the notebook used to carry a second, looser
# copy of these classes. They assert the STRICT behaviour, so that if the loose
# copy is ever pasted back in, these fail loudly instead of the system quietly
# accepting plans it should refuse.
from tests.package_source import package_cells, package_notebook  # Ticket 05: the package source, not the frozen notebook
_SP_CASES = 0

_MIN_NODE = {"id": "cart-btn", "tag": "button", "ownedBy": "HTML"}

# ── Case 1: an invented HTML tag is refused ─────────────────────────────────
# Whatever goes in this field is written into the page as a real element. A
# made-up tag renders as nothing and no linter would flag it as wrong.
ComponentNode(**_MIN_NODE)                      # a real tag is fine
for _bad in ("my-widget", "productcard", "Button", ""):
    try:
        ComponentNode(id="x", tag=_bad, ownedBy="HTML")
    except Exception:
        pass
    else:
        raise AssertionError(
            f"Case 1 FAIL: tag={_bad!r} was accepted. The looser copy of these "
            f"classes has come back: it typed tag as a plain string.")
_SP_CASES += 1
print("PASS Case 1 - a real tag is accepted, an invented one is refused")

# ── Case 2: the owning agent must be stated, not guessed ────────────────────
# This field decides which developer agent writes the element. A default would
# silently hand every unlabelled component to the HTML agent.
try:
    ComponentNode(id="x", tag="div")
except Exception:
    pass
else:
    raise AssertionError(
        "Case 2 FAIL: ownedBy defaulted instead of being required. The looser "
        "copy of these classes has come back.")
_SP_CASES += 1
print("PASS Case 2 - the owning agent is required, never defaulted")

# ── Case 3: a styled component must be addressable ──────────────────────────
# The CSS agent writes rules against a class name. A CSS-owned component with
# no class name cannot be styled at all.
try:
    ComponentNode(id="banner", tag="div", ownedBy="CSS")
except Exception as _e:
    assert "className" in str(_e), f"Case 3 FAIL: refused for the wrong reason: {_e}"
else:
    raise AssertionError("Case 3 FAIL: a CSS-owned component with no class name was accepted")
ComponentNode(id="banner", tag="div", ownedBy="CSS", className="promo-banner")
_SP_CASES += 1
print("PASS Case 3 - a CSS-owned component must carry a class name")

# ── Case 4: repeated states and events are refused ──────────────────────────
# Two states with one name means the later one silently wins, and the styling
# written for the first never applies.
for _field, _dupes in (("states", [{"name": "hover"}, {"name": "hover"}]),
                       ("events", [{"event": "click"}, {"event": "click"}])):
    try:
        ComponentNode(**{**_MIN_NODE, _field: _dupes})
    except Exception as _e:
        assert "duplicate" in str(_e).lower(), f"Case 4 FAIL: wrong reason: {_e}"
    else:
        raise AssertionError(f"Case 4 FAIL: duplicate {_field} were accepted")
_SP_CASES += 1
print("PASS Case 4 - repeated state names and repeated event names are both refused")

# ── Case 5: components nest, and nesting is validated too ───────────────────
_tree = ComponentNode(id="card", tag="article", ownedBy="HTML",
                      componentCategory="product-card",
                      children=[{"id": "img", "tag": "img", "ownedBy": "HTML"},
                                {"id": "btn", "tag": "button", "ownedBy": "HTML",
                                 "componentCategory": "add-to-cart-button"}])
assert len(_tree.children) == 2 and _tree.children[1].componentCategory == "add-to-cart-button", \
    "Case 5 FAIL: children were not built as ComponentNode objects"
try:
    ComponentNode(**{**_MIN_NODE, "children": [{"id": "bad", "tag": "nope", "ownedBy": "HTML"}]})
except Exception:
    pass
else:
    raise AssertionError("Case 5 FAIL: an invalid child slipped through the parent")
_SP_CASES += 1
print("PASS Case 5 - children are validated with the same rules as their parent")

# ── Case 6: the four specifications must describe the same page ─────────────
# This is the whole job of the bundle. Four individually valid specifications
# can still describe four different pages.
def _bundle(component_page="plp"):
    return {
        "layout": {"pages": [{"pageName": "plp", "pageType": "plp",
                              "pageLayoutType": "grid",
                              "regions": [{"name": "main", "ownedBy": "HTML",
                                           "layoutType": "grid"}]}]},
        "component": {"pages": [{"pageName": component_page,
                                 "regionComponents": {"main": [_MIN_NODE]}}]},
        "interaction": {"pages": []},
        "decoration": {"pages": []},
    }


UISpecificationBundle.model_validate(_bundle())
try:
    UISpecificationBundle.model_validate(_bundle(component_page="checkout"))
except Exception as _e:
    assert "unknown page" in str(_e).lower(), f"Case 6 FAIL: wrong reason: {_e}"
else:
    raise AssertionError(
        "Case 6 FAIL: the component tree named a page the layout never declared, "
        "and the bundle accepted it")
_SP_CASES += 1
print("PASS Case 6 - a component tree naming a page the layout never declared is refused")

# ── Case 7: the draft classes exist and are permissive on purpose ───────────
# The planner writes a page in stages. The draft allows an empty tree; the
# final specification does not. The copy this cell replaced had no drafts at
# all, so the planner's staged output had nowhere to go.
_draft = ComponentSpecificationDraft(pages=[{"pageName": "plp"}])
assert _draft.pages[0].regionComponents == {}, \
    "Case 7 FAIL: the draft should allow an empty region map"
try:
    PageComponentTree(pageName="plp")
except Exception:
    pass
else:
    raise AssertionError("Case 7 FAIL: the FINAL tree accepted a missing region map")
_SP_CASES += 1
print("PASS Case 7 - a draft page may be empty, a final page may not")

# ── Case 8: the categories other rules depend on all exist ──────────────────
# Five code-enforced rules resolve through componentCategory. If a value is
# missing from this list, the plan cannot express it and the rule never fires.
for _cat in ("product-card", "product-image-gallery", "cart-item",
             "add-to-cart-button", "navbar", "footer"):
    ComponentNode(**{**_MIN_NODE, "componentCategory": _cat})
try:
    ComponentNode(**{**_MIN_NODE, "componentCategory": "widget"})
except Exception:
    pass
else:
    raise AssertionError("Case 8 FAIL: an invented component category was accepted")
_SP_CASES += 1
print("PASS Case 8 - every category the image and select rules rely on is available")

print("=" * 64)
print(f"Specification schemas: {_SP_CASES}/8 cases PASSED")

# ── Case 12: no cell anywhere hand-writes a value a schema refuses ────────
# It lives HERE, not beside the design-schema tests, because PageType and
# ComponentCategory are declared in the cell above this one. A check placed
# earlier raised NameError on a straight top-to-bottom run.
# The failure this catches was live on 2026-08-16. `style` became a fixed list of
# seven words, and two fixtures kept seeding a schema with the old free-text
# "modern". Both sat in cells marked `# LIVE-LLM:`, which the offline runner
# skips whole, so the fixture was never built by anything until it was run by
# hand and raised in the user's face.
#
# Read the notebook FILE, not globals(). The point is to reach the cells nothing
# executes. Only keyword arguments on a schema class are checked, so a CSS
# `style="color: red"` inside HTML test data cannot be mistaken for one of these.
import ast as _ds_ast
import json as _ds_json
import pathlib as _ds_path
import typing as _ds_typing

_DS_FIELDS = {"style": DesignStyle, "commerce_type": CommerceType,
              "pageType": PageType,
              "componentCategory": ComponentCategory}
_DS_CLASSES = {"UI", "DesignSchema", "Page", "ComponentNode", "Region"}

if True:
    _ds_bad = []
    for _n, _c in enumerate(package_cells()):
        if _c["cell_type"] != "code":
            continue
        try:
            _tree = _ds_ast.parse("".join(_c["source"]))
        except SyntaxError:
            continue
        # A "this must raise" test names an illegal value on purpose, and always
        # wraps it in try or in `with ... raises(...)`. Nothing else does. Exempt
        # those, or Case 8 of the design-schema tests would have to be rewritten
        # to stop proving the schema refuses a bad word.
        _ds_exempt = set()
        for _guard in _ds_ast.walk(_tree):
            _bodies = []
            if isinstance(_guard, _ds_ast.Try):
                _bodies = [_guard.body]
            elif isinstance(_guard, _ds_ast.With) and "raises" in _ds_ast.dump(_guard):
                _bodies = [_guard.body]
            for _b in _bodies:
                for _stmt in _b:
                    for _inner in _ds_ast.walk(_stmt):
                        if isinstance(_inner, _ds_ast.Call):
                            _ds_exempt.add(id(_inner))

        for _node in _ds_ast.walk(_tree):
            if not isinstance(_node, _ds_ast.Call) or id(_node) in _ds_exempt:
                continue
            _fn = getattr(_node.func, "id", None) or getattr(_node.func, "attr", None)
            if _fn not in _DS_CLASSES:
                continue
            for _kw in _node.keywords:
                _lit = _DS_FIELDS.get(_kw.arg)
                if _lit is None or not isinstance(_kw.value, _ds_ast.Constant):
                    continue
                _v = _kw.value.value
                if isinstance(_v, str) and _v not in _ds_typing.get_args(_lit):
                    _ds_bad.append((_n, _fn, _kw.arg, _v))
    assert not _ds_bad, (
        "Case 12 FAIL: a cell builds a schema with a value the schema refuses:\n"
        + "\n".join(f"  cell {n}: {fn}({arg}={v!r})" for n, fn, arg, v in _ds_bad)
        + "\nThese raise the moment the cell is run. A cell marked # LIVE-LLM: is "
          "skipped by run_notebook_offline.py, so nothing else looks at them.")
    print(f"PASS Case 12 - every hand-written schema value in the notebook is one "
          f"the schema accepts (deliberate must-raise tests exempted)")
else:
    print("SKIP Case 12 - run this from the folder holding fyp.ipynb to check the file")


# ── Case 13: every hand-written specification fixture still validates ─────────
# The failure this catches was live on 2026-08-16. The interactions generator's
# fixture named component trees "rootComponents" and gave its regions no
# layoutType, both of which the schema had stopped accepting. The tool coerces
# its inputs before it looks at the model's output, so all three attempts failed
# on the fixture and the error blamed the model.
#
# The convention is the check: a variable named *_layout_specification IS a
# LayoutSpecification, so it has to validate as one. Read the notebook FILE, not
# globals(), because these fixtures live in cells marked # LIVE-LLM: that the
# offline runner never executes. Only top-level assignments are examined, which
# leaves anything built inside a try block alone.
import ast as _fx_ast
import json as _fx_json
import pathlib as _fx_path

_fx_SUFFIXES = {
    "_layout_specification": LayoutSpecification,
    "_components_specification": ComponentSpecification,
    "_interactions_specification": InteractionSpecification,
    "_decoration_specification": DecorationSpecification,
}

if True:
    _fx_bad, _fx_seen = [], 0
    for _n, _c in enumerate(package_cells()):
        if _c["cell_type"] != "code":
            continue
        try:
            _tree = _fx_ast.parse("".join(_c["source"]))
        except SyntaxError:
            continue
        for _stmt in _tree.body:
            if not isinstance(_stmt, _fx_ast.Assign) or not isinstance(_stmt.value, _fx_ast.Dict):
                continue
            for _tgt in _stmt.targets:
                if not isinstance(_tgt, _fx_ast.Name):
                    continue
                _model = next((m for suf, m in _fx_SUFFIXES.items()
                               if _tgt.id.endswith(suf)), None)
                if _model is None:
                    continue
                try:
                    _payload = _fx_ast.literal_eval(_stmt.value)
                except ValueError:
                    continue          # references a name, so not a plain fixture
                _fx_seen += 1
                try:
                    _model.model_validate(_payload)
                except Exception as _e:
                    _fx_bad.append((_n, _tgt.id, _model.__name__,
                                    str(_e).splitlines()[0]))
    assert not _fx_bad, (
        "Case 13 FAIL: a hand-written specification fixture no longer validates:\n"
        + "\n".join(f"  cell {n}: {name} as {model} -> {msg}"
                     for n, name, model, msg in _fx_bad)
        + "\nThe generator coerces its inputs BEFORE it reads the model's output, "
          "so a fixture like this fails every retry and the error names the model.")
    print(f"PASS Case 13 - all {_fx_seen} hand-written specification fixtures validate")
else:
    print("SKIP Case 13 - run this from the folder holding fyp.ipynb to check the file")



# ── Case 15: nothing reads a field name that no schema declares ──────────
# Three of these were live on 2026-08-16. The decoration live test read
# "designTokens" when the field is globalTokens, so it warned on every run that
# the model had returned no design tokens. The layout display helper and the
# layout debug scaffold both read Region.componentRefs, which Region has never
# had, so every region printed an empty component list.
#
# A missing key on a dict is None rather than an error, so the whole class is
# silent: the code runs, prints something confident, and is wrong. Two of the
# three lived in cells marked # LIVE-LLM:, which run_notebook_offline.py skips,
# so this reads the notebook FILE like Case 12 and Case 13 do.
#
# Parse, do not grep. A regex over raw lines also matches the comment that
# explains an old bug, which is what the first draft of this check reported.
import ast as _gf_ast
import json as _gf_json
import pathlib as _gf_path

if True:
    _gf_cells = package_cells()

    _gf_trees = {}
    for _n, _c in enumerate(_gf_cells):
        if _c.get("cell_type") != "code":
            continue
        try:
            _gf_trees[_n] = _gf_ast.parse("".join(_c["source"]))
        except SyntaxError:
            pass

    # Every field declared on every BaseModel in the notebook.
    _gf_fields = set()
    for _tree in _gf_trees.values():
        for _node in _gf_ast.walk(_tree):
            if isinstance(_node, _gf_ast.ClassDef):
                for _stmt in _node.body:
                    if (isinstance(_stmt, _gf_ast.AnnAssign)
                            and isinstance(_stmt.target, _gf_ast.Name)):
                        _gf_fields.add(_stmt.target.id)

    # Keys belonging to somebody else's JSON. Add a name here only after
    # confirming the external tool really emits it.
    _GF_FOREIGN = {
        "parseErrors",           # stylelint's JSON report
        "invalidOptionWarnings",  # stylelint's JSON report
        "ruleId",                # eslint and html-validate message objects
    }

    def _gf_is_camel(name):
        return bool(name) and name[0].islower() and any(c.isupper() for c in name)

    _gf_bad = []
    for _n, _tree in _gf_trees.items():
        for _node in _gf_ast.walk(_tree):
            _key = None
            if (isinstance(_node, _gf_ast.Call)
                    and isinstance(_node.func, _gf_ast.Attribute)
                    and _node.func.attr == "get"
                    and _node.args
                    and isinstance(_node.args[0], _gf_ast.Constant)
                    and isinstance(_node.args[0].value, str)):
                _key = _node.args[0].value
            elif (isinstance(_node, _gf_ast.Subscript)
                  and isinstance(_node.slice, _gf_ast.Constant)
                  and isinstance(_node.slice.value, str)):
                _key = _node.slice.value
            if (_key and _gf_is_camel(_key)
                    and _key not in _gf_fields and _key not in _GF_FOREIGN):
                _gf_bad.append((_n, _node.lineno, _key))

    assert not _gf_bad, (
        "Case 15 FAIL: a cell reads a field name that no schema declares:\n"
        + "\n".join(f"  cell {n} line {ln}: {key!r}" for n, ln, key in _gf_bad)
        + "\nA missing key gives None instead of raising, so this runs clean and "
          "reports something untrue. Either the name is a typo, or the schema "
          "renamed the field, or it belongs to an external tool's JSON and "
          "should be named in _GF_FOREIGN above.")
    print(f"PASS Case 15 - every camelCase key read in the notebook is a field "
          f"some schema declares ({len(_gf_fields)} field names known)")
else:
    print("SKIP Case 15 - run this from the folder holding fyp.ipynb to check the file")


print("=" * 64)


# ── Case 14: the draft rescues records the model filed in the wrong place ────
# Both shapes below were produced live on 2026-08-16 and both killed the attempt
# inside the parser, so the repair step never ran and the reason blamed the
# model. The plan was right in each case. Only the filing was wrong.
_DR_NODE = {"id": "card", "tag": "article", "ownedBy": "HTML"}

# Shape 1: the records filed as though they were a region.
_dr1 = ComponentSpecificationDraft.model_validate({"pages": [{
    "pageName": "plp",
    "regionComponents": {
        "main": [_DR_NODE],
        "dataSets": {"products": [{"id": "p1", "name": "Snkr One"}]},
    }}]})
assert _dr1.dataSets == {"products": [{"id": "p1", "name": "Snkr One"}]}, \
    "Case 14 FAIL: records filed under regionComponents were not lifted out"
assert list(_dr1.pages[0].regionComponents) == ["main"], \
    "Case 14 FAIL: dataSets is still being treated as a region"

# Shape 2: the records filed on the page rather than beside pages.
_dr2 = ComponentSpecificationDraft.model_validate({"pages": [{
    "pageName": "plp",
    "regionComponents": {"main": [_DR_NODE]},
    "dataSets": {"products": [{"id": "p2", "name": "Snkr Two"}]},
}]})
assert _dr2.dataSets["products"][0]["name"] == "Snkr Two", \
    "Case 14 FAIL: records filed on the page were not lifted out"

# Shape 3: a torn answer leaves loose strings where components belong.
_dr3 = ComponentSpecificationDraft.model_validate({"pages": [{
    "pageName": "plp",
    "regionComponents": {"nav": [_DR_NODE, "dataSets={", "products"]},
}]})
assert [n.id for n in _dr3.pages[0].regionComponents["nav"]] == ["card"], \
    "Case 14 FAIL: loose text among the components is still fatal"

# And a correct answer passes through untouched, which is the point of a rescue.
_dr_ok = {"pages": [{"pageName": "plp", "regionComponents": {"main": [_DR_NODE]}}],
          "dataSets": {"products": [{"id": "p3", "name": "Snkr Three"}]}}
_dr4 = ComponentSpecificationDraft.model_validate(_dr_ok)
assert _dr4.dataSets == _dr_ok["dataSets"], \
    "Case 14 FAIL: a correctly filed answer was altered"
assert len(_dr4.pages[0].regionComponents["main"]) == 1, \
    "Case 14 FAIL: a correctly filed component was dropped"
print("PASS Case 14 - misfiled records are moved to the top level, correct ones are untouched")


# ── dataSets: the one shared content list (2026-08-15) ───────────────────────
# Before this field the component tree said "a product card goes here" and
# nothing said which products, so the HTML agent invented eight and the JS agent
# invented eight different ones.
_ds_ok = ComponentSpecification(dataSets={"products": [
    {"id": "p1", "name": "Aurora Headphones", "price": "89.00"},
    {"id": "p2", "name": "Meridian Desk Lamp", "price": "42.00"},
]})
assert len(_ds_ok.dataSets["products"]) == 2
assert ComponentSpecification().dataSets == {}, "dataSets must default to empty"
print("PASS  dataSets accepts real records and defaults to empty")

for _bad, _why in (
    ([{"id": "p1"}], "a record with no name"),
    ([{"name": "Aurora"}], "a record with no id"),
    ([{"id": "p1", "name": "A"}, {"id": "p1", "name": "B"}], "a duplicate id"),
    (["Aurora Headphones"], "a bare string instead of a record"),
    ([{"id": " ", "name": "A"}], "a whitespace-only id"),
):
    try:
        ComponentSpecification(dataSets={"products": _bad})
    except Exception:
        pass
    else:
        raise AssertionError(f"FAIL: dataSets accepted {_why}")
print("PASS  dataSets refuses a nameless, idless, duplicated or non-record entry")

# The draft carries it too, or the two-stage generator drops the records midway.
assert "dataSets" in ComponentSpecificationDraft.model_fields, \
    "FAIL: the draft would lose dataSets between stages"
print("PASS  the draft schema carries dataSets through the two-stage generator")
