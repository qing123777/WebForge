"""Speed-cost ticket 05: a drift refusal is fixed by naming the selector, not
by sending the stylesheet again.

    pytest tests/test_css_retarget.py   (or python tests/test_css_retarget.py)

Offline, no model calls. Measured free on the 2026-11-10 PO-08 run (session
4fb17fbe): the CSS agent's first save was refused for ONE drifted selector
(`a svg`). The fix was one line, but the only way to make it was to send the
whole stylesheet again: 6,051 output tokens, 50.6 s, $0.145.

  CR-1  _retarget_css_selectors rewrites, or deletes, one selector of a rule.
  CR-2  a drift refusal HOLDS the submitted stylesheet (css_pending) and tells
        the model to answer with store_css_code(retarget={...}).
  CR-3  store_css_code(retarget=...) applies the answer to the held
        stylesheet and runs every check on the result.
  CR-4  replay: the run's own first save, then the retarget the model in
        effect made, saves the same stylesheet its full resend did.
"""
import contextlib
import io
import json
import pathlib
import sys
from types import SimpleNamespace

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import conftest  # noqa: E402,F401  (repo on sys.path, dead API keys) when run with python

import pytest  # noqa: E402

with contextlib.redirect_stdout(io.StringIO()):
    import webforge.css_agent as c  # noqa: E402

_FIX = pathlib.Path(__file__).resolve().parent / "fixtures"
_REC = json.loads((_FIX / "po08_4fb17fbe_store_test_cases.json").read_text(encoding="utf-8"))
_SID = _REC["session_id"]
_FIRST = (_FIX / "po08_4fb17fbe_css_first_save.css").read_text(encoding="utf-8")
# The stylesheet the run really sent after the refusal, cut from the trace.
_SECOND = (_FIX / "po08_4fb17fbe_css_second_save.css").read_text(encoding="utf-8")
_HTML = (_FIX / "po08_4fb17fbe_page" / f"preview_{_SID}.html").read_text(encoding="utf-8")
# What the model changed between its refused save and its accepted one.
_FIXED_SELECTOR = ".featured-coffee-rating svg,\n.featured-sort-bar > div > svg"


# ---- CR-1 -----------------------------------------------------------------

def test_retarget_rewrites_one_selector():
    css = "a svg {\n  width: 1rem;\n}\n.b { color: red; }\n"
    got, missing = c._retarget_css_selectors(css, {"a svg": ".x svg"})
    assert got == ".x svg {\n  width: 1rem;\n}\n.b { color: red; }\n" and missing == []


def test_retarget_touches_only_the_named_part_of_a_selector_list():
    css = ".a,\na svg,\n.b { color: red; }\n"
    got, _ = c._retarget_css_selectors(css, {"a svg": ".x svg"})
    assert got == ".a,\n.x svg,\n.b { color: red; }\n"
    got, _ = c._retarget_css_selectors(css, {"a svg": ""})
    assert "a svg" not in got and ".a" in got and ".b" in got and "color: red" in got


def test_retarget_with_an_empty_value_deletes_the_rule():
    css = ".keep { color: red; }\na svg {\n  width: 1rem;\n}\n.also { color: blue; }\n"
    got, missing = c._retarget_css_selectors(css, {"a svg": ""})
    assert "svg" not in got and "width" not in got and missing == []
    assert ".keep { color: red; }" in got and ".also { color: blue; }" in got


def test_retarget_reaches_into_media_blocks_and_every_occurrence():
    css = "a svg { width: 1rem; }\n@media (min-width: 40rem) {\n  a svg { width: 2rem; }\n}\n"
    got, _ = c._retarget_css_selectors(css, {"a svg": ".x svg"})
    assert got.count(".x svg") == 2 and "a svg" not in got and "@media (min-width: 40rem)" in got


def test_retarget_matches_whitespace_loosely_and_reports_what_it_did_not_find():
    css = "a   svg { width: 1rem; }\n"
    got, missing = c._retarget_css_selectors(css, {"a svg": ".x svg", ".nope b": ".y"})
    assert ".x svg" in got and missing == [".nope b"]


def test_retarget_does_not_touch_a_longer_selector_that_contains_the_name():
    css = "nav a svg { width: 1rem; }\na svg:hover { width: 2rem; }\n"
    got, missing = c._retarget_css_selectors(css, {"a svg": ".x svg"})
    assert got == css and missing == ["a svg"]


def test_retarget_drops_an_at_rule_it_emptied():
    # stylelint's block-no-empty would refuse the leftover `@media (...) {}`.
    css = ".a { color: red; }\n@media (min-width: 40rem) {\n  a svg { width: 2rem; }\n}\n.b { color: blue; }\n"
    got, _ = c._retarget_css_selectors(css, {"a svg": ""})
    assert "@media" not in got and ".a { color: red; }" in got and ".b { color: blue; }" in got
    keep = "@media (min-width: 40rem) {\n  a svg { width: 2rem; }\n  .k { color: red; }\n}\n"
    got, _ = c._retarget_css_selectors(keep, {"a svg": ""})
    assert "@media (min-width: 40rem)" in got and ".k { color: red; }" in got


def test_retarget_keeps_the_space_before_the_brace():
    got, _ = c._retarget_css_selectors(".a,\na svg {\n  color: red;\n}\n", {"a svg": ""})
    assert got == ".a {\n  color: red;\n}\n", repr(got)


@pytest.mark.parametrize("bad", [".x { color: red }", ".x; .y", ".x } .y {"])
def test_retarget_refuses_a_replacement_that_is_not_a_selector(bad):
    css = "a svg { width: 1rem; }\n"
    got, missing = c._retarget_css_selectors(css, {"a svg": bad})
    assert got == css and missing == ["a svg"]


# ---- CR-2 / CR-3 ----------------------------------------------------------

@pytest.fixture
def page(monkeypatch):
    monkeypatch.setattr(c, "_read_preview_source",
                        lambda sid, ext: _HTML if ext == "html" else "")


def _state(**kw):
    st = {"intent": "generate", "session_id": _SID,
          "decoration_specification": _REC["state"]["decoration_specification"],
          "components_specification": _REC["state"]["components_specification"]}
    st.update(kw)
    return st


def _call(state, **args):
    return c.store_css_code.func(runtime=SimpleNamespace(state=state, tool_call_id="cr"),
                                 **args).update


def _said(update):
    return update["messages"][0].content


def test_drift_refusal_holds_the_stylesheet_and_asks_for_a_retarget(page):
    up = _call(_state(), css_code=_FIRST)
    msg = _said(up)
    assert "CSS/DOM drift" in msg and "a svg" in msg
    assert "css_code" not in up                       # not saved
    assert up["css_pending"] == _FIRST                # held, as the model wrote it
    # the refusal names the cheap way out, with the drifted selector as the key
    assert 'retarget={"a svg":' in msg and "Do NOT send the stylesheet again" in msg, msg


def test_retarget_fixes_the_held_stylesheet_and_saves_it(page):
    held = _call(_state(), css_code=_FIRST)
    up = _call(_state(css_pending=held["css_pending"], coverage_attempts=1),
               retarget={"a svg": _FIXED_SELECTOR})
    assert _said(up).startswith("CSS code saved to state."), _said(up)
    assert ".featured-coffee-rating svg" in up["css_code"] and "\na svg" not in up["css_code"]
    assert up["css_pending"] == ""                    # nothing left held


def test_retarget_result_still_goes_through_the_drift_check(page):
    held = _call(_state(), css_code=_FIRST)
    up = _call(_state(css_pending=held["css_pending"], coverage_attempts=1),
               retarget={"a svg": "a path"})          # still nothing there
    msg = _said(up)
    assert "CSS/DOM drift" in msg and "a path" in msg and "css_code" not in up
    assert "a path" in up["css_pending"]              # the held copy moves on


def test_retarget_refuses_a_selector_that_is_not_in_the_held_stylesheet(page):
    held = _call(_state(), css_code=_FIRST)
    up = _call(_state(css_pending=held["css_pending"], coverage_attempts=1),
               retarget={".not-there x": ".y"})
    msg = _said(up)
    assert ".not-there x" in msg and "a svg" in msg and "css_code" not in up, msg
    assert "css_pending" not in up or up["css_pending"] == held["css_pending"]
    # Review of ticket 05: a wrong answer spends an attempt (so the cap ends
    # it), and the message names the other way out.
    assert up["coverage_attempts"] == 2 and "full stylesheet as css_code" in msg, msg


def test_a_saved_retarget_says_what_changed(page):
    # The model's own copy of the stylesheet still says `a svg`. If it sends
    # css_code again later (a lint fix), it must know to keep the change.
    held = _call(_state(), css_code=_FIRST)
    up = _call(_state(css_pending=held["css_pending"], coverage_attempts=1),
               retarget={"a svg": ".featured-coffee-rating svg"})
    msg = _said(up)
    assert "a svg" in msg and ".featured-coffee-rating svg" in msg and "keep" in msg, msg


def test_a_retarget_that_meets_another_refusal_keeps_its_work(page, monkeypatch):
    # Drift fixed, then a different contract refuses: the held copy must be
    # the retargeted one, and the refusal must say the change is already in.
    monkeypatch.setattr(c, "_decoration_color_gaps", lambda css, spec: ["--x: want #fff"])
    held = _call(_state(), css_code=_FIRST)
    up = _call(_state(css_pending=held["css_pending"], coverage_attempts=1),
               retarget={"a svg": ".featured-coffee-rating svg"})
    msg = _said(up)
    assert "Decoration Colour Contract" in msg and "css_code" not in up
    assert ".featured-coffee-rating svg" in up["css_pending"] and "\na svg" not in up["css_pending"]
    assert "keep" in msg and ".featured-coffee-rating svg" in msg, msg


def test_retarget_with_nothing_held_says_to_send_the_stylesheet(page):
    msg = _said(_call(_state(), retarget={"a svg": ".x"}))
    assert "nothing is held" in msg and "css_code" in msg, msg


def test_a_full_resend_still_works_and_clears_the_held_copy(page):
    fixed = _FIRST.replace("a svg {", _FIXED_SELECTOR + " {")
    up = _call(_state(css_pending=_FIRST, coverage_attempts=1), css_code=fixed)
    assert _said(up).startswith("CSS code saved to state.") and up["css_pending"] == ""


def test_neither_argument_is_refused(page):
    assert "css_code" in _said(_call(_state()))


def test_css_state_declares_the_held_channel():
    assert "css_pending" in c.CssState.__annotations__


# ---- CR-4 -----------------------------------------------------------------

def test_replay_po08_4fb17fbe(page):
    # What the run did: a full second stylesheet with one selector changed.
    # _SECOND is that stylesheet from the trace, and it is exactly _FIRST with
    # the one selector rewritten.
    resend = _FIRST.replace("a svg {", _FIXED_SELECTOR + " {")
    assert resend != _FIRST and resend == _SECOND
    full = _call(_state(coverage_attempts=1), css_code=resend)
    # What it can do now: answer the refusal with the selector alone.
    held = _call(_state(), css_code=_FIRST)
    answer = {"a svg": _FIXED_SELECTOR}
    small = _call(_state(css_pending=held["css_pending"], coverage_attempts=1), retarget=answer)
    assert small["css_code"] == full["css_code"]
    assert len(full["css_code"]) == 24420       # "Saved 24420 characters" in the trace
    chars = len(json.dumps({"retarget": answer}))
    print(f"\n[proof] PO-08 session {_SID[:8]}, CSS first save refused for 1 drifted "
          f"selector ('a svg'). Before: the fix was a full resend, {len(resend):,} "
          f"characters of CSS (6,051 output tokens, 50.6 s, $0.145 in the trace). "
          f"After: a store_css_code(retarget=...) of {chars} characters saves the "
          f"stylesheet that resend saved, byte for byte ({len(small['css_code']):,} "
          f"characters with the spec base). Offline: whether the model answers "
          f"with retarget is for the paid E2E-CSS-GM run to show.")


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q", "-s"]))
