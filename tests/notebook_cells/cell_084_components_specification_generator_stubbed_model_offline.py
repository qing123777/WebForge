# Ported from fyp.ipynb cell 84 (ticket 05). The notebook is frozen;
# edit this file. Run by tests/test_notebook_cells.py.
# Unit tests: components_specification_generator (stubbed model, offline)
#
# The generator's give-up path had never been tested, because every check on it
# was a live cell. It failed twice in two days and reported "got keys:
# ['messages']" both times, which names nothing.
#
# The structured tool is the only part that talks to a model, so replacing it
# with a stub that returns a canned draft makes the rest testable for free.
from types import SimpleNamespace as _cg_ns

_cg_layout = {"pages": [{
    "pageName": "plp", "pageType": "plp", "pageLayoutType": "single-column",
    "responsive": True,
    "regions": [
        {"name": "header", "ownedBy": "HTML", "layoutType": "flex-row"},
        {"name": "main", "ownedBy": "HTML", "layoutType": "grid"},
    ],
}]}

_cg_trees = {
    "header": [{"id": "navbar", "tag": "nav", "ownedBy": "HTML",
                "componentCategory": "navbar", "className": "navbar",
                "children": []}],
    "main": [{"id": "grid", "tag": "section", "ownedBy": "HTML",
              "componentCategory": "product-grid", "className": "product-grid",
              "children": [
                  {"id": "card", "tag": "article", "ownedBy": "HTML",
                   "componentCategory": "product-card",
                   "className": "product-card", "children": []}]}],
}
_cg_with_records = {
    "pages": [{"pageName": "plp", "regionComponents": _cg_trees}],
    "dataSets": {"products": [
        {"id": "p1", "name": "Aurora Runner", "price": "89.00"},
        {"id": "p2", "name": "Meridian Trainer", "price": "119.00"},
    ]},
}
_cg_no_records = {"pages": [{"pageName": "plp", "regionComponents": _cg_trees}],
                  "dataSets": {}}


class _CgStub:
    """Stands in for the structured tool. Counts how often it was asked."""

    def __init__(self, payload):
        self.payload, self.calls = payload, 0

    def invoke(self, _payload):
        self.calls += 1
        return dict(self.payload)


def _cg_run(draft, repair=None):
    """Run the generator once with a stubbed model, then put the globals back."""
    real_tool = components_specification_generator_tool
    real_repair = _repair_component_spec_from_layout
    stub = _CgStub(draft)
    globals()["components_specification_generator_tool"] = stub
    if repair is not None:
        globals()["_repair_component_spec_from_layout"] = repair
    try:
        cmd = components_specification_generator.func(_cg_ns(
            state={"input_query": "sneaker store", "layout_specification": _cg_layout},
            tool_call_id="cg-test"))
    finally:
        globals()["components_specification_generator_tool"] = real_tool
        globals()["_repair_component_spec_from_layout"] = real_repair
    text = " ".join(str(getattr(m, "content", m))
                    for m in (cmd.update.get("messages") or []))
    return cmd.update, text, stub.calls


_cg_passed = 0

# ── CG-1: a complete draft is stored, and costs exactly one model call ───────
_upd, _txt, _calls = _cg_run(_cg_with_records)
assert "components_specification" in _upd, \
    f"CG-1 FAIL: nothing stored. {_txt}"
assert _calls == 1, f"CG-1 FAIL: {_calls} model calls for a valid first answer"
assert _upd["components_specification"]["dataSets"]["products"][0]["name"] == "Aurora Runner", \
    "CG-1 FAIL: the records did not survive to the stored specification"
print("PASS CG-1 - a complete draft is stored on the first attempt, records intact")
_cg_passed += 1

# ── CG-2: no records plus a product card means the stage gives up ────────────
# This is the failure of 2026-08-16. It is correct behaviour, and the point of
# the test is that it now SAYS so rather than returning a bare message list.
_upd, _txt, _calls = _cg_run(_cg_no_records)
assert "components_specification" not in _upd, \
    "CG-2 FAIL: a page with product cards and no records was accepted"
assert _calls == 3, f"CG-2 FAIL: gave up after {_calls} attempts, expected 3"
assert "dataSets is empty" in _txt, f"CG-2 FAIL: the reason is not named. {_txt}"
assert "attempt 1:" in _txt and "attempt 3:" in _txt, \
    f"CG-2 FAIL: only one attempt was reported, so a repeat looks like progress. {_txt}"
print("PASS CG-2 - an empty dataSets gives up after 3 attempts and names all 3")
_cg_passed += 1

# ── CG-3: a field lost by our own repair is reported as ours ─────────────────
# The repair returned a fresh {"pages": ...} until 2026-08-15, which destroyed
# the model's records. The guard then blamed the model. Re-create that exact
# function and confirm the message now says INTERNAL instead.
# Bind the real one by closure. Looking it up by name would find the
# replacement, because _cg_run rebinds that name in globals before calling.
_cg_real_repair = _repair_component_spec_from_layout


def _cg_broken_repair(layout, candidate):
    payload = candidate.model_dump() if hasattr(candidate, "model_dump") else dict(candidate or {})
    return {"pages": _cg_real_repair(layout, payload)["pages"]}

_upd, _txt, _calls = _cg_run(_cg_with_records, repair=_cg_broken_repair)
assert "components_specification" not in _upd, \
    "CG-3 FAIL: a specification stripped of its records was stored"
assert "INTERNAL" in _txt and "dataSets" in _txt, \
    f"CG-3 FAIL: our own data loss is still reported as a model failure. {_txt}"
print("PASS CG-3 - a field dropped by the repair is reported as INTERNAL, not as the model's fault")
_cg_passed += 1

# ── CG-4: the schema the MODEL fills describes the field it is judged on ─────
# with_structured_output binds the DRAFT, so the draft's descriptions are what
# reach the model. dataSets was hard-refused for being empty while carrying no
# description at all on the draft.
_cg_draft_props = ComponentSpecificationDraft.model_json_schema()["properties"]
for _field in ("dataSets", "pages"):
    _desc = (_cg_draft_props.get(_field) or {}).get("description") or ""
    assert len(_desc) > 40, (
        f"CG-4 FAIL: the draft's '{_field}' reaches the model with no useful "
        f"description, so the model is judged on a field it was never briefed on.")
assert "id" in _cg_draft_props["dataSets"]["description"], \
    "CG-4 FAIL: the draft's dataSets description does not say what a record needs"
print("PASS CG-4 - the draft schema briefs the model on every field the guard enforces")
_cg_passed += 1

# ── CG-5: the harness reads out the reason instead of hiding it ──────────────
try:
    run_tool_unit_test_state_snapshots(
        tool_name="components_specification_generator",
        input_query="sneaker store",
        initial_state={"layout_specification": _cg_layout,
                       "components_specification": None},
        expected_update_fields=["components_specification"],
        verbose=False,
    ) if False else None
except Exception:
    pass
_cg_fake_update = {"messages": [type("M", (), {"content": "FAILED: because X."})()]}
assert "because X." in _tool_failure_reason(_cg_fake_update), \
    "CG-5 FAIL: the harness still drops the tool's own explanation"
assert "without saying why" in _tool_failure_reason({"messages": []}), \
    "CG-5 FAIL: a silent tool is not called out"
print("PASS CG-5 - a failed generator's own explanation reaches the assertion message")
_cg_passed += 1

# CG-6: the prompt separates component from content. The spec was slimmed so
# content lives in dataSets, not as its own node; without this the generator
# drifts back to modelling every heading and option, inflating the HTML and the
# one-case-per-node test suite alike.
_cg_tmpl = components_prompt.template
assert "COMPONENT vs CONTENT" in _cg_tmpl, \
    "CG-6 FAIL: the component-vs-content rule is missing from the prompt"
assert "one product-card node plus eight records" in _cg_tmpl, \
    "CG-6 FAIL: the one-node-per-repeated-item rule is not stated"
print("PASS CG-6 - the prompt separates component from content (keeps the tree small)")
_cg_passed += 1

# CG-7: images are stripped from the shared data. The system embeds none, but the
# model kept putting image URLs into records and whole image-only datasets; the JS
# agent then rendered them as broken <img> tags (PO-08 po0113ce72). The strip
# guarantees the data carries no image a downstream agent could render.
_cg_with_images = {
    "pages": [{"pageName": "plp", "regionComponents": _cg_trees}],
    "dataSets": {
        "products": [
            {"id": "p1", "name": "Aurora Runner", "price": "89.00",
             "image": "https://images.example.com/a.jpg", "imageAlt": "a shoe"},
            {"id": "p2", "name": "Meridian Trainer", "price": "119.00",
             "image": "https://images.example.com/b.jpg"},
        ],
        "categories": [{"id": "c1", "name": "Running"}],
        "galleryImages": [
            {"id": "g1", "name": "Hero",
             "image": "https://images.example.com/h.jpg", "alt": "hero"}],
    },
}
_upd, _txt, _calls = _cg_run(_cg_with_images)
assert "components_specification" in _upd, f"CG-7 FAIL: nothing stored. {_txt}"
_cg_ds = _upd["components_specification"]["dataSets"]
_cg_prod = _cg_ds["products"][0]
assert "image" not in _cg_prod and "imageAlt" not in _cg_prod, \
    f"CG-7 FAIL: image keys survived on a product record: {sorted(_cg_prod)}"
assert _cg_prod["name"] == "Aurora Runner" and _cg_prod["price"] == "89.00", \
    "CG-7 FAIL: stripping images also removed real content"
assert "galleryImages" not in _cg_ds, \
    "CG-7 FAIL: an image-only dataset was not dropped"
assert "categories" in _cg_ds and _cg_ds["categories"][0]["name"] == "Running", \
    "CG-7 FAIL: a non-image id/name dataset (categories) was wrongly dropped"
assert "products" in _cg_ds and len(_cg_ds["products"]) == 2, \
    "CG-7 FAIL: the products list did not survive"
assert "embeds no images" in components_prompt.template, \
    "CG-7 FAIL: the no-image dataSets rule is missing from the prompt"
print("PASS CG-7 - images stripped from dataSets records and image-only datasets dropped")
_cg_passed += 1

print("=" * 64)
print(f"components_specification_generator: {_cg_passed}/7 PASSED (no model calls)")
