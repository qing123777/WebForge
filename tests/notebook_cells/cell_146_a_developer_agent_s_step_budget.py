# Ported from fyp.ipynb cell 146 (ticket 05). The notebook is frozen;
# edit this file. Run by tests/test_notebook_cells.py.
# Unit tests: a developer agent's step budget and its graceful degrade
# (2026-08-30). REGRESSION for the PO-08 po019a8c61 crash: recursion_limit=50 was
# sized for ONE component, batched correction hands over up to _MODIFY_BATCH_CAP,
# and the raise nothing caught destroyed a finished 558s / $2.33 run.
_rec_passed = 0

# The historic single-component value is preserved, so nothing that used to fit
# starts behaving differently.
assert _dev_agent_recursion_limit(1) == 50, _dev_agent_recursion_limit(1)
assert _dev_agent_recursion_limit(0) == 50 and _dev_agent_recursion_limit(None) == 50
print("PASS REC-1 - a one-component session keeps the historic budget of 50")
_rec_passed += 1

# A full batch must fit. 6 components needed ~50 supersteps in the real run, so
# the budget has to be comfortably above that, and it must grow with the batch.
# formula pin at the historical n=6 (catches a change to the formula itself)
assert _dev_agent_recursion_limit(6) == 132, _dev_agent_recursion_limit(6)
assert _dev_agent_recursion_limit(_MODIFY_BATCH_CAP) > 50 * 2, "REC-2 FAIL: a full batch still has no headroom"
_seq = [_dev_agent_recursion_limit(n) for n in range(1, _MODIFY_BATCH_CAP + 1)]
assert _seq == sorted(_seq) and len(set(_seq)) > 1, \
    "REC-2 FAIL: the budget must grow with the batch, got %s" % _seq
print(f"PASS REC-2 - the budget grows with the batch; the full batch of "
      f"{_MODIFY_BATCH_CAP} gets {_dev_agent_recursion_limit(_MODIFY_BATCH_CAP)}")
_rec_passed += 1

# The degrade: an exhausted budget is reported, not raised.
from langgraph.errors import GraphRecursionError as _RecErr


class _RecAgent:
    """Streams a couple of chunks, then exhausts its budget the way LangGraph does."""

    def __init__(self, boom=True):
        self.boom = boom

    def stream(self, payload, **kwargs):
        yield ("custom", "   [X Agent] working...")
        yield ("updates", {"step": {"k": "v"}})
        if self.boom:
            raise _RecErr("Recursion limit of 50 reached without hitting a stop condition.")


_seen = []
_hit = _stream_dev_agent(_RecAgent(boom=True), {}, {}, _seen.append)
assert _hit is True, "REC-3 FAIL: an exhausted budget must be reported as True"
assert _seen == ["   [X Agent] working..."], \
    "REC-3 FAIL: progress before the limit must still reach the user, got %s" % _seen
print("PASS REC-3 - an exhausted budget returns True instead of destroying the run")
_rec_passed += 1

_seen2 = []
assert _stream_dev_agent(_RecAgent(boom=False), {}, {}, _seen2.append) is False, \
    "REC-4 FAIL: a normal finish must report False"
# on_update is optional, and is called only when the caller asks for it
_ups = []
_stream_dev_agent(_RecAgent(boom=False), {}, {}, _seen2.append, on_update=_ups.append)
assert _ups == [{"k": "v"}], "REC-4 FAIL: on_update not delivered, got %s" % _ups
print("PASS REC-4 - a normal finish reports False; on_update is optional and delivered")
_rec_passed += 1

# Any other error must still travel: the degrade covers the step budget only,
# never a real fault.
class _BoomAgent:
    def stream(self, payload, **kwargs):
        raise ValueError("a real fault")
        yield  # pragma: no cover


try:
    _stream_dev_agent(_BoomAgent(), {}, {}, _seen2.append)
    raise AssertionError("REC-5 FAIL: a non-recursion error was swallowed")
except ValueError:
    pass
print("PASS REC-5 - only the step-limit error is caught; real faults still raise")
_rec_passed += 1

# The note has to tell the orchestrator that saved work is real and the rest
# simply did not happen -- otherwise it reads a partial fix as a failed round.
assert _partial_fix_note(False, "JS") == ""
_note = _partial_fix_note(True, "JS")
assert "JS Agent hit its step limit" in _note and "IS saved to disk" in _note \
    and "PARTIAL" in _note and "re-run the test suite" in _note, _note
print("PASS REC-6 - the partial-fix note states what is saved and what to do next")
_rec_passed += 1

print("=" * 64)
print("developer-agent step budget: %d/6 PASSED (no model calls)" % _rec_passed)
