# Ported from fyp.ipynb cell 424 (ticket 05). The notebook is frozen;
# edit this file. Run by tests/test_notebook_cells.py.
# Unit tests: the orchestrator's three voices
# The risk a voice block introduces is not that it sounds wrong. It is that it
# quietly changes behaviour, or that it lets a broken build be reported
# cheerfully. Both are checked here.

_tone_passed = 0


def _tone_ok(tid, desc):
    global _tone_passed
    _tone_passed += 1
    print("PASS  %-5s %s" % (tid, desc))


assert set(TONE_PROMPTS) == {"friendly", "concise", "professional"}, sorted(TONE_PROMPTS)
assert [o["value"] for o in TONE_OPTIONS] == list(TONE_PROMPTS), (
    "TN-1 FAIL: the interface offers %s but the prompts define %s. A voice in one "
    "and not the other is a dropdown entry that does nothing."
    % ([o["value"] for o in TONE_OPTIONS], list(TONE_PROMPTS)))
_tone_ok("TN-1", "the three voices offered are exactly the three that exist")

for _o in TONE_OPTIONS:
    assert _o["label"].strip() and _o["help"].strip(), \
        "TN-2 FAIL: %r has no label or no help text" % _o["value"]
_tone_ok("TN-2", "every voice carries a label and a plain-English line for the panel")

# An unknown value must fall back, not raise. The tone arrives from the
# interface, and a stale value in a saved session must not break a good run.
assert tone_block("nonsense-value") == TONE_PROMPTS[_TONE_DEFAULT]
assert tone_block("") == TONE_PROMPTS[_TONE_DEFAULT]
assert tone_block(None) == TONE_PROMPTS[_TONE_DEFAULT]
assert tone_block("PROFESSIONAL") == TONE_PROMPTS["professional"], \
    "TN-3 FAIL: the lookup is case-sensitive, so a capitalised value falls back"
_tone_ok("TN-3", "an unknown, empty or capitalised value resolves instead of raising")

# The floor is what stops a cheerful report of a broken page.
for _name, _blk in TONE_PROMPTS.items():
    for _rule in ("drop the warmth", "No emoji, no exclamation marks",
                  "Report the outcome accurately"):
        assert _rule in _blk, \
            "TN-4 FAIL: the %r voice lost the rule %r" % (_name, _rule)
_tone_ok("TN-4", "all three voices carry the drop-the-warmth-on-failure floor")

# Only ONE voice may invite emoji, and it must still forbid them on failure.
_emoji_yes = [n for n, b in TONE_PROMPTS.items() if "Emoji are welcome" in b]
assert _emoji_yes == ["friendly"], \
    "TN-5 FAIL: emoji are invited by %s, expected only friendly" % _emoji_yes
for _name in ("concise", "professional"):
    assert "No emoji" in TONE_PROMPTS[_name], \
        "TN-5 FAIL: the %r voice no longer rules emoji out" % _name
_tone_ok("TN-5", "only the friendly voice invites emoji, the other two forbid them")

# The load-bearing one. A voice may not smuggle in behaviour.
_BEHAVIOUR_WORDS = ("call_secondary_orchestrator", "call_context_engineering_agent",
                    "call_system_design_planning_agent", "update_input",
                    "ALL TESTS PASSED", "NO ARTEFACTS", "intent=modify",
                    "target_component", "REFUSED")
for _name, _blk in TONE_PROMPTS.items():
    _found = [w for w in _BEHAVIOUR_WORDS if w in _blk]
    assert not _found, (
        "TN-6 FAIL: the %r voice mentions %s. A voice block changes WORDING only. "
        "Anything that names a tool or an outcome belongs in the base prompt, "
        "where all three voices share it." % (_name, _found))
_tone_ok("TN-6", "no voice block names a tool, an outcome or a state field")

print("=" * 76)
print("orchestrator voices: %d/6 PASSED  (%d voices, floor shared by all)"
      % (_tone_passed, len(TONE_PROMPTS)))
print("=" * 76)
