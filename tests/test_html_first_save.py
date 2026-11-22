"""Speed-cost ticket 04: the HTML agent's first save passes.

    pytest tests/test_html_first_save.py   (or python tests/test_html_first_save.py)

Offline, no model calls. On the 2026-11-10 PO-08 run (session 4fb17fbe) the
HTML agent wrote the whole page three times: 133 s, then 68 s after the Shared
Data Contract refused it, then 75 s after html-validate found 19 errors.

  FS-1  _summary_data_sets names the data sets that hold one VALUE record
        (cartSummary.itemCount), not content to print.
  FS-2  the Shared Data Contract no longer demands a summary record's name on
        the page; a content record's name is still demanded.
  FS-3  the prompt and the guard agree: the prompt states the exception, and
        the refusal message never names a summary set.
  FS-4  _strip_invalid_aria_labels drops props.ariaLabel from the spec nodes
        html-validate refuses it on (span, p, div, headings), and nothing else.
  FS-5  replay: the run's own first save, refused then, is accepted now; and
        with the stripped labels gone its 19 lint errors fall to 3.
"""
import contextlib
import copy
import io
import json
import pathlib
import re
import sys
from types import SimpleNamespace

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import conftest  # noqa: E402,F401  (repo on sys.path, dead API keys) when run with python

import pytest  # noqa: E402

with contextlib.redirect_stdout(io.StringIO()):
    import webforge.html_agent as h  # noqa: E402
    import webforge.specs as specs  # noqa: E402

_FIX = pathlib.Path(__file__).resolve().parent / "fixtures"
_REC = json.loads((_FIX / "po08_4fb17fbe_store_test_cases.json").read_text(encoding="utf-8"))
_SPEC = _REC["state"]["components_specification"]
_SID = _REC["session_id"]
_FIRST_SAVE = (_FIX / "po08_4fb17fbe_html_first_save.html").read_text(encoding="utf-8")


def _spec(bindings, data_sets):
    nodes = [{"id": f"c{i}", "tag": "span", "className": f"c{i}", "dataBinding": b,
              "states": [], "events": []} for i, b in enumerate(bindings)]
    return {"dataSets": data_sets,
            "pages": [{"pageName": "p", "regionComponents": {"main": nodes}}]}


_ONE = [{"id": "s", "name": "Cart Summary", "itemCount": 3}]
_TWO = [{"id": "a", "name": "Aurora"}, {"id": "b", "name": "Night"}]


# ---- FS-1 -----------------------------------------------------------------

def test_summary_sets_of_the_4fb17fbe_spec():
    assert h._summary_data_sets(_SPEC) == {"cartSummary", "searchResults"}


@pytest.mark.parametrize("bindings,records,summary", [
    ([{"source": "cartSummary.itemCount"}], _ONE, True),
    ([{"source": "cartSummary.itemCount"}, {"source": "cartSummary.subtotal"}], _ONE, True),
    # read as a list, or by its name: it is content
    ([{"source": "cartSummary"}], _ONE, False),
    ([{"source": "cartSummary.itemCount"}, {"source": "cartSummary.name"}], _ONE, False),
    # several records are a list to render, however they are bound
    ([{"source": "cartSummary.itemCount"}], _TWO, False),
    # nothing binds it: nothing says it is only a value
    ([], _ONE, False),
    ([None], _ONE, False),
])
def test_summary_set_shapes(bindings, records, summary):
    got = h._summary_data_sets(_spec(bindings, {"cartSummary": records}))
    assert got == ({"cartSummary"} if summary else set())


def test_a_single_product_read_by_value_is_still_content():
    # Review of ticket 04: a product-detail page has ONE product record, read
    # as product.price and product.rating. That record is merchandise; its
    # name must still be on the page.
    spec = _spec([{"source": "product.price"}], {"product": [{"id": "p", "name": "Aurora", "price": "$1"}]})
    spec["pages"][0]["regionComponents"]["main"][0]["componentCategory"] = "product-price"
    assert h._summary_data_sets(spec) == set()


def test_summary_sets_tolerate_junk():
    assert h._summary_data_sets({}) == set()
    assert h._summary_data_sets(None) == set()
    assert h._summary_data_sets({"dataSets": "junk", "pages": "junk"}) == set()


# ---- FS-2 / FS-3 ----------------------------------------------------------

def _store(html, spec=_SPEC):
    rt = SimpleNamespace(state={"components_specification": spec, "session_id": _SID,
                                "intent": "generate"}, tool_call_id="fs")
    return h.store_html_code.func(html, rt).update["messages"][0].content


def test_first_save_is_no_longer_refused_for_summary_names():
    # FS-5 (replay). Recorded reply: "Shared Data Contract violation(s) ...
    # cartSummary:'Cart Summary', searchResults:'Featured Coffee Results'".
    assert "Cart Summary" not in _FIRST_SAVE and "Featured Coffee Results" not in _FIRST_SAVE
    reply = _store(_FIRST_SAVE)
    assert "Shared Data Contract" not in reply, reply
    assert reply == "HTML code saved to state.", reply


def test_a_content_record_is_still_demanded():
    html = _FIRST_SAVE.replace("Aurora Bloom", "Morning Glory")
    reply = _store(html)
    assert "Shared Data Contract" in reply and "Aurora Bloom" in reply, reply
    # the refusal never names a summary set, and says why they are exempt
    assert "cartSummary" not in reply and "searchResults" not in reply, reply


def test_prompt_states_the_exception_the_guard_makes():
    # The guard exempts summary sets; the prompt must say so in its Data rule
    # and in its final checklist, or "every record, name verbatim" contradicts
    # the guard the other way (the model prints 'Cart Summary' on the page).
    prompt = h.html_agent_generate_prompt if hasattr(h, "html_agent_generate_prompt") else None
    text = "\n".join(v for k, v in vars(h).items()
                     if isinstance(v, str) and "components_specification.dataSets is the run's content" in v)
    assert text, "the Data rule moved: update this test"
    data_rule = text[text.index("components_specification.dataSets is the run's content"):][:900]
    assert "summary" in data_rule and "need not be printed" in data_rule, data_rule
    assert "never its name" not in data_rule, data_rule
    checklist = text[text.index("Every dataSets record is rendered once"):][:200]
    assert "summary" in checklist, checklist


# ---- FS-4 -----------------------------------------------------------------

def _nodes(spec):
    out = {}

    def walk(n):
        if isinstance(n, dict):
            if isinstance(n.get("id"), str) and "tag" in n:
                out[n["id"]] = n
            for v in n.values():
                walk(v)
        elif isinstance(n, list):
            for v in n:
                walk(v)
    walk(spec.get("pages"))
    return out


def test_strip_invalid_aria_labels_on_the_4fb17fbe_spec():
    before = _nodes(_SPEC)
    spec_in = copy.deepcopy(_SPEC)
    after = _nodes(specs._strip_invalid_aria_labels(spec_in))
    assert spec_in == _SPEC                                   # input not mutated
    dropped = sorted(i for i, n in before.items()
                     if "ariaLabel" in (n.get("props") or {})
                     and "ariaLabel" not in (after[i].get("props") or {}))
    assert dropped == ["featured-coffee-price", "featured-coffee-rating"], dropped
    # every other prop, and every label on a control or landmark, survives
    for i, n in before.items():
        if i not in dropped:
            assert after[i].get("props") == n.get("props"), i
    assert after["site-search"]["props"]["ariaLabel"] == "Search coffees"
    assert after["featured-coffee-add-to-cart"]["props"]["ariaLabel"]


@pytest.mark.parametrize("tag,props,kept", [
    ("span", {"ariaLabel": "x"}, False),
    ("p", {"ariaLabel": "x"}, False),
    ("div", {"ariaLabel": "x"}, False),
    ("h2", {"ariaLabel": "x"}, False),
    ("SPAN", {"ariaLabel": "x"}, False),
    ("span", {"ariaLabel": "x", "role": "status"}, True),    # a role makes it valid
    ("div", {"ariaLabel": "x", "tabIndex": "0"}, True),
    ("button", {"ariaLabel": "x"}, True),
    ("nav", {"ariaLabel": "x"}, True),
    ("fieldset", {"ariaLabel": "x"}, True),
    ("input", {"ariaLabel": "x"}, True),
    # Review of ticket 04: html-validate ALLOWS a short list and refuses the
    # rest, so the strip keeps a list too. These were probed on run_html_validate.
    ("ul", {"ariaLabel": "x"}, False),
    ("li", {"ariaLabel": "x"}, False),
    ("strong", {"ariaLabel": "x"}, False),
    ("small", {"ariaLabel": "x"}, False),
    ("a", {"ariaLabel": "x"}, False),                        # no href: not a link
    ("a", {"ariaLabel": "x", "href": "#top"}, True),
])
def test_strip_invalid_aria_label_by_tag(tag, props, kept):
    spec = {"dataSets": {}, "pages": [{"pageName": "p", "regionComponents": {"main": [
        {"id": "c", "tag": tag, "props": dict(props), "children": []}]}}]}
    got = specs._strip_invalid_aria_labels(spec)["pages"][0]["regionComponents"]["main"][0]
    assert ("ariaLabel" in got["props"]) == kept
    assert {k: v for k, v in got["props"].items() if k != "ariaLabel"} == \
           {k: v for k, v in props.items() if k != "ariaLabel"}


def _form(events, **props):
    return {"dataSets": {}, "pages": [{"pageName": "p", "regionComponents": {"main": [
        {"id": "f", "tag": "form", "className": "f", "props": dict(props),
         "events": events, "children": [
             {"id": "b", "tag": "button", "props": {"type": "button"}, "events": []}]}]}}]}


def test_a_form_nothing_submits_becomes_a_div():
    # html-validate's wcag/h32 wants a submit button in every <form>. A filter
    # panel of type="button" toggles is a form in name only: the model had to
    # add a submit button nobody asked for, and pressing it reloads the page.
    got = specs._retag_unsubmitted_forms(_form([], ariaLabel="Filter"))
    node = got["pages"][0]["regionComponents"]["main"][0]
    assert node["tag"] == "div" and node["children"][0]["tag"] == "button"
    # ...and a div cannot carry the label, so the two steps run in this order
    node = specs._strip_invalid_aria_labels(got)["pages"][0]["regionComponents"]["main"][0]
    assert "ariaLabel" not in node["props"]


@pytest.mark.parametrize("events", [
    [{"event": "onSubmit", "flowName": "search"}],
    [{"event": "submit", "flowName": "search"}],
    [{"name": "onSubmit"}],
])
def test_a_form_with_a_submit_event_stays_a_form(events):
    spec = _form(events, role="search")
    assert specs._retag_unsubmitted_forms(spec) == spec


def test_a_form_holding_a_submit_button_stays_a_form():
    spec = _form([])
    spec["pages"][0]["regionComponents"]["main"][0]["children"][0]["props"]["type"] = "submit"
    assert specs._retag_unsubmitted_forms(spec) == spec


def test_retag_forms_on_the_4fb17fbe_spec():
    spec_in = copy.deepcopy(_SPEC)
    after = _nodes(specs._retag_unsubmitted_forms(spec_in))
    assert spec_in == _SPEC
    changed = sorted(i for i, n in _nodes(_SPEC).items() if after[i]["tag"] != n["tag"])
    assert changed == ["featured-sort-bar", "roast-filter-panel"], changed
    assert after["site-search"]["tag"] == "form"              # it has onSubmit


def test_strip_invalid_aria_labels_tolerates_junk():
    assert specs._retag_unsubmitted_forms("junk") == "junk"
    assert specs._strip_invalid_aria_labels("junk") == "junk"
    assert specs._strip_invalid_aria_labels({"pages": "junk"}) == {"pages": "junk"}


# ---- FS-5 -----------------------------------------------------------------

def _lint(html):
    rt = SimpleNamespace(state={"html_code": html, "session_id": _SID, "intent": "generate",
                                "lint_attempts": 0}, tool_call_id="fs")
    msg = h.run_html_validate.func(rt).update["messages"][0].content
    m = re.search(r"Found (\d+) error", msg)
    return (int(m.group(1)) if m else 0), msg


def test_replay_first_save_lint_errors():
    n_before, msg = _lint(_FIRST_SAVE)
    if "Found" not in msg and "No issues" not in msg:
        pytest.skip(f"html-validate unavailable: {msg[:80]}")
    misuse = msg.count("[aria-label-misuse]")
    assert (n_before, misuse) == (19, 16), msg
    # Each misuse sits on a span whose spec node carried props.ariaLabel. With
    # the labels stripped from the spec the model has nothing to copy there.
    stripped = _nodes(specs._strip_invalid_aria_labels(copy.deepcopy(_SPEC)))
    html = _FIRST_SAVE
    for cid, node in _nodes(_SPEC).items():
        label = (node.get("props") or {}).get("ariaLabel")
        if label and "ariaLabel" not in (stripped[cid].get("props") or {}):
            html = re.sub(r'(<[^>]*class="%s"[^>]*?) aria-label="[^"]*"' % re.escape(node["className"]),
                          r"\1", html)
            html = re.sub(r'(<[^>]*?) aria-label="[^"]*"([^>]*class="%s")' % re.escape(node["className"]),
                          r"\1\2", html)
    n_after, msg_after = _lint(html)
    assert n_after == 3 and "[aria-label-misuse]" not in msg_after, msg_after
    print(f"\n[proof] PO-08 session {_SID[:8]}, the HTML agent's own first save. Before: "
          f"refused by the Shared Data Contract for 2 summary records (a 68 s rewrite), "
          f"then {n_before} html-validate errors, {misuse} of them aria-label-misuse copied "
          f"from the spec (a 75 s rewrite). After: the same save is accepted, and with "
          f"the spec's invalid labels removed from the markup (simulated: it assumes the "
          f"model adds none of its own) the page lints with {n_after} errors.")


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q", "-s"]))
