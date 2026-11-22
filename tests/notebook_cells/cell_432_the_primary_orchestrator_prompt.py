# Ported from fyp.ipynb cell 432 (ticket 05). The notebook is frozen;
# edit this file. Run by tests/test_notebook_cells.py.
# Unit tests: the Primary Orchestrator prompt
# It is the only agent that speaks to the user, so it is the only one that must
# know what may be asked for and what may not. Both lists are GENERATED from the
# schema. These cases prove they stayed generated, and that no placeholder was
# left behind for a user to read.

_op = _orchestrator_prompt
_op_passed = 0
_NL = "\n"


def _op_ok(tid, desc):
    global _op_passed
    _op_passed += 1
    print("PASS  %-5s %s" % (tid, desc))


assert "{{" not in _op and "}}" not in _op, \
    "OP-1 FAIL: a placeholder survived into the prompt the model actually reads"
_op_ok("OP-1", "both placeholders were substituted, none reaches the model")

for _field, _spec in user_choice_options().items():
    for _v in _spec["values"]:
        assert _v["value"] in _op, (
            "OP-2 FAIL: '%s' is a value the schema accepts but the orchestrator "
            "never offers, so a user cannot ask for it." % _v["value"])
    assert str(_spec["default_when_unset"]) in _op, (
        "OP-2 FAIL: %s has no stated default in the prompt, so the agent will "
        "ask about it even when the user does not care." % _field)
_op_ok("OP-2", "every schema value and every default is offered, all four fields")

for _f in FIXED_BY_DESIGN:
    assert _f["what"] in _op and _f["why"][:40] in _op, (
        "OP-3 FAIL: the fixed limit '%s' is missing its reason, so a refusal "
        "would arrive with no explanation." % _f["what"])
_op_ok("OP-3", "all four fixed limits appear WITH the reason to give the user")

# The five things a prompt has to carry. A missing one is the section the model
# silently invents for itself.
for _section in ("OUTCOME", "VERIFICATION", "CONSTRAINTS", "ITERATION POLICY",
                 "ERROR HANDLING"):
    assert _NL + _section + _NL in _op, \
        "OP-4 FAIL: the %s section is gone" % _section
_op_ok("OP-4", "outcome, verification, constraints, iteration and error handling present")

# VERIFICATION must still name all four sub-run outcomes. Dropping one is how a
# broken page gets reported to the user as a finished one.
for _outcome in ("ALL TESTS PASSED", "ENDED WITH FAILING TESTS", "UNVERIFIED",
                 "NO ARTEFACTS"):
    assert _outcome in _op, \
        "OP-5 FAIL: the '%s' outcome is no longer described" % _outcome
_op_ok("OP-5", "all four sub-run outcomes are still distinguished")

assert "STOP" in _op and "third time" in _op, \
    "OP-6 FAIL: the stop-after-two-failures rule is gone, so a stuck stage can loop"
_op_ok("OP-6", "the agent is still told to stop rather than retry a third time")

# The gate that stops a one-noun brief. Bounded on purpose: an unbounded version
# turns into an interrogation, and the prompt already forbids asking about
# anything the user delegated.
assert _NL + "ENOUGH TO BUILD FROM" + _NL in _op, \
    "OP-7 FAIL: the buildable gate is gone, so a one-noun brief is accepted again"
for _rule in ("at least TWO", "ask ONE short question", "Ask once", "two clarifying rounds",
              "never refuse a request merely",
              "starts fresh and may ask"):
    assert _rule in _op, "OP-7 FAIL: the gate no longer says %r" % _rule
_op_ok("OP-7", "the gate exists, asks once, and cannot refuse a brief request")

assert _op.index("ENOUGH TO BUILD FROM") < _op.index("WHAT THE USER MAY CHOOSE"), \
    "OP-8 FAIL: the gate must come before the choice list it draws its options from"
assert _op.index("ENOUGH TO BUILD FROM") < _op.index("CONSTRAINTS"), \
    "OP-8 FAIL: the gate must be read before any tool call, so it sits above CONSTRAINTS"
_op_ok("OP-8", "the gate is positioned before the choices and before the constraints")

# Talking is a legitimate ending. Without it the prompt allowed only build,
# decline or ask, so "what can you do?" fell through to the decline rule.
assert "4. You simply answered." in _op, \
    "OP-9 FAIL: answering a question is no longer one of the ways a turn can end"
# The prompt wraps long sentences, so a literal check false-negatives on the
# line break even when the wording is present and correct. Assertions test
# WORDING, never wrapping. Same lesson the modification-prompt suite learned.
import re as _op_re
_op_flat = _op_re.sub(r"\s+", " ", _op)
for _phrase in ("call no tool, and build nothing",
                "never about what you will discuss",
                "Do not turn a conversation into a refusal"):
    assert _phrase in _op_flat, "OP-9 FAIL: the prompt no longer says %r" % _phrase
_op_ok("OP-9", "plain conversation is an allowed ending, not something to refuse")

# The scope limit must read as a limit on BUILDING, not on talking. The old
# wording said "Decline anything else", which caught questions too.
assert "Decline anything else" not in _op, \
    "OP-10 FAIL: the blanket decline rule is back, so a greeting gets refused"
assert "A request to build something else is declined" in _op_flat, \
    "OP-10 FAIL: the scope limit no longer names BUILDING as the thing limited"
_op_ok("OP-10", "the scope limit applies to what it builds, not to what it discusses")

# Proceeding after a clarifier must run the full chain, not jump to the build
# tool. The model did exactly that on the first live PO-01b: it called
# call_secondary_orchestrator directly and built from empty specifications.
for _phrase in ("run the full generation chain",
                "Proceeding never means calling call_secondary_orchestrator directly"):
    assert _phrase in _op_flat, "OP-11 FAIL: the PROCEED branch no longer says %r" % _phrase
_op_ok("OP-11", "proceeding after a clarifier runs the chain, never the build tool alone")

# A second generation in the same conversation overwrites the first page, so
# the orchestrator must warn and wait for confirmation before building over
# it. Added 2026-08-22 with warn-and-confirm chosen over warn-and-proceed
# because the overwrite deletes the existing page.
for _phrase in ("a second generation overwrites",
                "build only after they confirm",
                "not a modify"):
    assert _phrase in _op_flat, "OP-12 FAIL: the overwrite rule is missing %r" % _phrase
_op_ok("OP-12", "a second generation warns about overwrite and waits for confirmation")

# The orchestrator can read the page it built, so a question about the current
# page is answered from disk, not from specifications that go stale after a
# modify. Added 2026-08-22 with the read_page_source tool.
for _phrase in ("read_page_source",
                "not what is on disk after a"):
    assert _phrase in _op_flat, "OP-13 FAIL: the read-the-page rule is missing %r" % _phrase
_op_ok("OP-13", "a question about the built page is answered from the file, not the specs")

# OP-14: the VISUAL THEME gate lists the real themes and the "we do not have
# it, suggest the nearest" rule, so the orchestrator can be honest about themes.
for _tn in _THEME_LIBRARY:
    assert _tn in _op, "OP-14 FAIL: theme %r is not offered in the prompt" % _tn
assert "VISUAL THEME" in _op and "nearest one" in _op_flat, \
    "OP-14 FAIL: the theme gate or its suggest-the-nearest rule is missing"
_op_ok("OP-14", "the theme gate lists real themes and offers the nearest when one is missing")

print("=" * 76)
print("Primary Orchestrator prompt: %d/14 PASSED  (%d chars, choice list "
      "generated from the schema)" % (_op_passed, len(_op)))
print("=" * 76)
