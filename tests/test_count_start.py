"""Speed-cost ticket 01: count expectations start from the spec's own data.

    pytest tests/test_count_start.py   (or python tests/test_count_start.py)

Offline, no model calls. The guard tests go through store_test_cases, the
tool the model calls; the last test drives the saved page with Playwright.

  CS-1  _data_start_values reads, in one place, the number a data-bound
        component shows before any click, from the components specification.
  CS-2  the join sheet the model reads states that starting number.
  CS-3  store_test_cases refuses a number that provably ignores it: a resting
        check must expect the start; after a click, a count every flow
        increments must be above it, one every flow decrements below it. Any
        other count after a click (a filter, a search) is not checked.
  CS-4  replay of PO-08 session 4fb17fbe: TC-059 ('1' after one add) is
        refused, and the corrected expectation ('4') passes on the saved page.

On the 2026-11-10 PO-08 run the spec started the cart at 3
(dataSets.cartSummary[0].itemCount), TC-059 expected '1' after one add, the
page correctly read '4', and the correction round hard-coded '1' into the
page to satisfy the test.
"""
import contextlib
import copy
import io
import json
import pathlib
import sys
from types import SimpleNamespace

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import conftest  # noqa: E402,F401  (repo on sys.path, dead API keys) when run with python

import pytest  # noqa: E402

with contextlib.redirect_stdout(io.StringIO()):
    import webforge.test_gen_agent as tg  # noqa: E402

_FIX = pathlib.Path(__file__).resolve().parent / "fixtures"
_REPLAY = _FIX / "po08_4fb17fbe_store_test_cases.json"
_PAGE = _FIX / "po08_4fb17fbe_page"
_SID = "4fb17fbe-8431-4da5-965d-2235b86ba08c"


def _spec(binding, data_sets):
    """One cart-count badge bound to `binding`, one add button, and data_sets."""
    return {"dataSets": data_sets, "pages": [{"pageName": "p", "regionComponents": {"main": [
        {"id": "cart-count", "tag": "span", "className": "cart-count",
         "dataBinding": binding, "states": [], "events": []},
        {"id": "add-btn", "tag": "button", "className": "add-btn",
         "states": [], "events": [{"event": "onClick", "flowName": "add"}]},
    ]}}]}


_SUMMARY = {"cartSummary": [{"id": "s", "name": "Summary", "itemCount": 3}]}


# ---- CS-1 -----------------------------------------------------------------

def test_start_value_from_a_single_record_field():
    spec = _spec({"source": "cartSummary.itemCount", "format": "count"}, _SUMMARY)
    assert tg._data_start_values(spec) == {"cart-count": (3, "cartSummary.itemCount")}


def test_start_value_of_a_counted_list_sums_its_quantities():
    items = {"cartItems": [{"id": "a", "name": "A", "quantity": 1},
                           {"id": "b", "name": "B", "quantity": 2}]}
    spec = _spec({"source": "cartItems", "format": "count"}, items)
    assert tg._data_start_values(spec)["cart-count"][0] == 3


def test_start_value_of_a_counted_list_without_quantities_is_its_length():
    items = {"cartItems": [{"id": "a", "name": "A"}, {"id": "b", "name": "B"}]}
    spec = _spec({"source": "cartItems", "format": "count"}, items)
    assert tg._data_start_values(spec)["cart-count"][0] == 2


@pytest.mark.parametrize("binding,data_sets", [
    # a field of a many-record list is one value per card, not one start
    ({"source": "products.rating", "format": "count"},
     {"products": [{"id": "a", "name": "A", "rating": 4}, {"id": "b", "name": "B", "rating": 5}]}),
    # not a whole number
    ({"source": "cartSummary.subtotal", "format": "currency"},
     {"cartSummary": [{"id": "s", "name": "S", "subtotal": "$54.50"}]}),
    # a list that is not counted is rendered, not a number
    ({"source": "cartItems", "format": "list"},
     {"cartItems": [{"id": "a", "name": "A"}]}),
    # points at nothing
    ({"source": "missing.itemCount", "format": "count"}, {}),
    # a whole-number price is a price, not a count (review of ticket 01)
    ({"source": "cartSummary.subtotal", "format": "currency"},
     {"cartSummary": [{"id": "s", "name": "S", "subtotal": 54}]}),
    (None, _SUMMARY),
])
def test_no_start_value_when_the_binding_is_not_one_number(binding, data_sets):
    assert "cart-count" not in tg._data_start_values(_spec(binding, data_sets))


def test_start_value_reads_a_digit_string_and_tolerates_junk():
    spec = _spec({"source": "cartSummary.itemCount"},
                 {"cartSummary": [{"id": "s", "name": "S", "itemCount": "3"}]})
    assert tg._data_start_values(spec)["cart-count"][0] == 3
    assert tg._data_start_values({}) == {}
    assert tg._data_start_values({"dataSets": "junk", "pages": "junk"}) == {}


def test_start_values_of_the_4fb17fbe_spec():
    rec = json.loads(_REPLAY.read_text(encoding="utf-8"))
    got = tg._data_start_values(rec["state"]["components_specification"])
    assert got == {"header-cart-count": (3, "cartSummary.itemCount"),
                   "featured-results-count": (8, "searchResults.count")}


# ---- CS-2 -----------------------------------------------------------------

def _intx(mode):
    """One flow: clicking add-btn rewrites cart-count with this updateData mode."""
    if mode is None:
        return {}
    return {"pages": [{"pageName": "p", "flows": [
        {"name": "f", "trigger": {"event": "onClick", "targetId": "add-btn"},
         "actions": [{"type": "updateData", "targetId": "cart-count",
                      "payload": {"source": "cartSummary.itemCount", "mode": mode}}],
         "stateTransitions": []}]}]}


def _sheet_line(mode):
    spec = _spec({"source": "cartSummary.itemCount", "format": "count"}, _SUMMARY)
    sheet = tg._build_component_join_sheet({"components_specification": spec,
                                            "interaction_specification": _intx(mode)})
    return next(l for l in sheet.splitlines() if "starts at" in l)


def test_join_sheet_states_the_starting_number():
    line = _sheet_line("increment")
    assert "3" in line and "cartSummary.itemCount" in line and "more than 3" in line, line


def test_join_sheet_says_nothing_about_adds_for_a_filtered_count():
    # A results count rewritten by a filter can move by any amount.
    line = _sheet_line("filteredCount")
    assert "starts at: 3" in line and "add" not in line and "more than" not in line, line


def test_count_directions_read_the_update_mode():
    assert tg._count_directions(_intx("increment")) == {"cart-count": "up"}
    assert tg._count_directions(_intx("decrement")) == {"cart-count": "down"}
    assert tg._count_directions(_intx("filteredCount")) == {}
    assert tg._count_directions({}) == {} and tg._count_directions("junk") == {}
    both = _intx("increment")
    both["pages"][0]["flows"].append(_intx("decrement")["pages"][0]["flows"][0])
    assert tg._count_directions(both) == {}          # moves both ways: no rule


def test_count_directions_of_the_4fb17fbe_spec():
    rec = json.loads(_REPLAY.read_text(encoding="utf-8"))
    got = tg._count_directions(rec["state"]["interaction_specification"])
    assert got.get("header-cart-count") == "up", got
    assert "featured-results-count" not in got, got  # filteredCount


# ---- CS-3 -----------------------------------------------------------------

def _tc(i, expected, **kw):
    d = {"id": i, "component": "cart-count", "description": "d", "action": "assert_text",
         "selector": ".cart-count", "expected": expected, "passed": None}
    d.update(kw)
    return d


def _store(cases, mode="increment", binding=None):
    spec = _spec(binding or {"source": "cartSummary.itemCount", "format": "count"}, _SUMMARY)
    rt = SimpleNamespace(state={"components_specification": spec,
                                "interaction_specification": _intx(mode)},
                         tool_call_id="cs")
    return tg.store_test_cases.func(cases, rt)


def _said(cmd):
    return cmd.update["messages"][0].content


def _saved(cmd):
    return "test_cases" in cmd.update


# Only a provable error is refused. A resting check must read the start. After
# a click, a count the spec only ever INCREMENTS must be above the start (two
# adds, or a cart kept in localStorage across a reset, make 5 as right as 4),
# one it only DECREMENTS below it, and any other mode (a filter rewriting a
# results count to any number) is not checked.
@pytest.mark.parametrize("mode,expected,after_click,ok", [
    ("increment", "3", False, True),        # resting page shows the start
    ("increment", "1", False, False),       # resting page cannot show 1
    ("increment", "4", False, False),       # nor the count after a click
    ("increment", "4", True, True),         # one add
    ("increment", "5", True, True),         # two adds
    ("increment", "1", True, False),        # TC-059: assumes an empty cart
    ("increment", "3", True, False),        # an add cannot leave it at the start
    ("increment", "Cart (4)", True, True),  # the number is read out of the text
    ("decrement", "2", True, True),
    ("decrement", "0", True, True),         # emptied
    ("decrement", "4", True, False),
    ("filteredCount", "2", True, True),     # a filter narrows 3 to anything
    ("filteredCount", "7", True, True),
    ("filteredCount", "1", False, False),   # but the resting page still reads 3
    (None, "9", True, True),                # no flow says how it moves
])
def test_count_expectation_must_follow_the_start(mode, expected, after_click, ok):
    tag = {"covers_event": "onClick"} if after_click else {}
    got = _store([_tc("TC-1", expected, **tag)], mode=mode)
    assert _saved(got) == ok, _said(got)
    if not ok:
        msg = _said(got)
        assert "TC-1" in msg and "starts at 3" in msg and "cartSummary.itemCount" in msg, msg
        if not after_click:
            assert "expect 3" in msg, msg
        elif mode == "increment":
            assert "more than 3" in msg and "expect 4" in msg, msg
        else:
            assert "less than 3" in msg, msg
        # The page is reloaded before each click, but its storage is kept, so
        # the message must not promise a fresh page.
        assert "freshly loaded" not in msg, msg


@pytest.mark.parametrize("expected", ["Your cart", "3 of 12", ""])
def test_text_that_is_not_one_number_is_left_alone(expected):
    got = _store([_tc("TC-1", expected)])
    assert "starts at" not in _said(got), _said(got)


def test_other_actions_and_unbound_components_are_left_alone():
    css = _tc("TC-1", "1", action="assert_css")
    css["expected"] = "font-size=1px"
    assert "starts at" not in _said(_store([css]))
    other = _tc("TC-2", "1", component="add-btn", selector=".add-btn")
    assert "starts at" not in _said(_store([other]))


# ---- CS-4 -----------------------------------------------------------------

def _replay(fix_tc059):
    """Replay the four recorded calls. With fix_tc059, a call refused for
    TC-059 is retried once with expected '4', as the model would."""
    rec = json.loads(_REPLAY.read_text(encoding="utf-8"))
    state = dict(rec["state"], test_cases=[])
    replies = []
    for n, call in enumerate(rec["calls"]):
        cases = copy.deepcopy(call["test_cases"])
        got = tg.store_test_cases.func(cases, SimpleNamespace(state=state, tool_call_id=f"r{n}"))
        if fix_tc059 and not _saved(got) and "TC-059" in _said(got):
            replies.append(_said(got))
            for c in cases:
                if c["id"] == "TC-059":
                    c["expected"] = "4"
            got = tg.store_test_cases.func(cases, SimpleNamespace(state=state, tool_call_id=f"r{n}b"))
        if _saved(got):
            state["test_cases"] = tg._merge_test_cases(state["test_cases"], got.update["test_cases"])
        replies.append(_said(got))
    return rec, replies, state["test_cases"]


def test_replay_po08_4fb17fbe_refuses_tc059():
    rec, replies, suite = _replay(fix_tc059=True)
    k, refusal = next((k, r) for k, r in enumerate(replies)
                      if "TC-059" in r and "starts at" in r)
    assert "starts at 3" in refusal and "expect 4" in refusal, refusal
    # The retried call with '4' completes the suite (ticket 02 already
    # dropped the 'loading' demand, so nothing else is asked for).
    assert "SUITE COMPLETE" in replies[k + 1], replies[k + 1]
    assert next(t for t in suite if t["id"] == "TC-059")["expected"] == "4"


def _run_on_saved_page(cases, tmp_path):
    """Run cases through run_test_suite on the saved 4fb17fbe page, copied into
    a temp preview folder so the sweeps read its HTML from where they expect."""
    import webforge.test_execution.suite as suite
    for f in _PAGE.iterdir():
        (tmp_path / f.name).write_bytes(f.read_bytes())
    old_root = suite._PREVIEW_ROOT
    suite._PREVIEW_ROOT = tmp_path
    try:
        url = (tmp_path / f"preview_{_SID}.html").as_uri()
        rt = SimpleNamespace(state={"test_cases": cases, "preview_url": url,
                                    "session_id": _SID, "modification_context": ""},
                             tool_call_id="p")
        out = suite.run_test_suite.func(rt).update
    finally:
        suite._PREVIEW_ROOT = old_root
    return {c["id"]: c for c in out["test_cases"]}


def test_corrected_tc059_passes_on_the_saved_page(tmp_path):
    pytest.importorskip("playwright")
    rec = json.loads(_REPLAY.read_text(encoding="utf-8"))
    by_id = {c["id"]: c for call in rec["calls"] for c in call["test_cases"]}
    click = dict(by_id["TC-057"], passed=None)       # the one add-to-cart click
    old = dict(by_id["TC-059"], passed=None)
    new = dict(old, id="TC-059-fixed", expected="4")
    res = _run_on_saved_page([click, old, new], tmp_path)
    assert res["TC-057"]["passed"], res["TC-057"]
    assert not res["TC-059"]["passed"]
    assert res["TC-059-fixed"]["passed"], res["TC-059-fixed"]
    # The markup the correction round left: '1' written into the badge, which
    # the script rewrites from the cart on load.
    html = (_PAGE / f"preview_{_SID}.html").read_text(encoding="utf-8")
    assert 'class="header-cart-count">1<' in html
    _, replies, _ = _replay(fix_tc059=True)
    refusal = next(r for r in replies if "TC-059" in r and "starts at" in r)
    print(f"\n[proof] PO-08 session {rec['session_id'][:8]}: header-cart-count starts at 3 "
          f"(cartSummary.itemCount). Before: TC-059 expected '1' after one add, was saved, "
          f"failed on the correct page ('{res['TC-059'].get('reason', '')}'), and the "
          f"saved page's markup now holds the '1' the correction round wrote in. After: store_test_cases "
          f"refuses it ('{refusal[:60]}...'), and the corrected expectation '4' "
          f"passes on the saved page.")


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q", "-s"]))
