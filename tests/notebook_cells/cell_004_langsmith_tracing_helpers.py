# Ported from fyp.ipynb cell 4 (ticket 05). The notebook is frozen;
# edit this file. Run by tests/test_notebook_cells.py.
# Unit tests: LangSmith tracing helpers
#
# Every case restores os.environ afterwards. These functions write to the real
# process environment, so a test that leaked would change how the rest of the
# notebook traces.
import os as _ls_os

_LS_KEYS = ("LANGSMITH_API_KEY", "LANGCHAIN_API_KEY", "LANGSMITH_TRACING",
            "LANGCHAIN_TRACING_V2", "LANGSMITH_ENDPOINT", "LANGCHAIN_ENDPOINT",
            "LANGCHAIN_PROJECT", "LANGSMITH_PROJECT")
_LS_SAVED = {k: _ls_os.environ.get(k) for k in _LS_KEYS}


def _ls_reset(**overrides):
    for k in _LS_KEYS:
        _ls_os.environ.pop(k, None)
    for k, v in overrides.items():
        _ls_os.environ[k] = v


def _ls_restore():
    for k, v in _LS_SAVED.items():
        if v is None:
            _ls_os.environ.pop(k, None)
        else:
            _ls_os.environ[k] = v


try:
    # ── Case 1: no key anywhere means tracing stays off ──────────────────────
    _ls_reset()
    assert enable_langsmith() is False, \
        "Case 1 FAIL: enable_langsmith reported success with no API key"
    assert "LANGCHAIN_TRACING_V2" not in _ls_os.environ, \
        "Case 1 FAIL: tracing was switched on despite there being no key"
    print("PASS Case 1 - no API key, so tracing stays off and nothing is set")

    # ── Case 2: a LANGSMITH_ key is mirrored to the LANGCHAIN_ name ──────────
    # This is the whole point of the bootstrap. LangChain's tracer reads the
    # LANGCHAIN_ name, so a key set only under LANGSMITH_ would be ignored.
    _ls_reset(LANGSMITH_API_KEY="ls-test-key")
    assert enable_langsmith() is True, "Case 2 FAIL: a valid key was not accepted"
    assert _ls_os.environ["LANGCHAIN_API_KEY"] == "ls-test-key", \
        "Case 2 FAIL: the key was not mirrored to the name LangChain reads"
    assert _ls_os.environ["LANGCHAIN_TRACING_V2"] == "true", \
        "Case 2 FAIL: tracing was not switched on"
    assert _ls_os.environ["LANGSMITH_ENDPOINT"].startswith("https://"), \
        "Case 2 FAIL: no endpoint was defaulted"
    print("PASS Case 2 - a LANGSMITH_ key reaches the LANGCHAIN_ name and enables tracing")

    # ── Case 3: an existing value is never overwritten ───────────────────────
    # Every write is a setdefault. A user who points at a private LangSmith
    # deployment must not have it replaced by the public default.
    _ls_reset(LANGSMITH_API_KEY="ls-test-key",
              LANGCHAIN_ENDPOINT="https://langsmith.internal.example")
    enable_langsmith()
    assert _ls_os.environ["LANGCHAIN_ENDPOINT"] == "https://langsmith.internal.example", \
        "Case 3 FAIL: a user-supplied endpoint was overwritten"
    print("PASS Case 3 - a value the user already set survives untouched")

    # ── Case 4: the tracing flag is read in its several written forms ────────
    for _flag in ("1", "true", "TRUE", "yes", "on"):
        _ls_reset(LANGSMITH_TRACING=_flag)
        _bootstrap_langsmith_env()
        assert _ls_os.environ.get("LANGCHAIN_TRACING_V2") == "true", \
            f"Case 4 FAIL: LANGSMITH_TRACING={_flag!r} did not switch tracing on"
    for _flag in ("0", "false", "off", "no"):
        _ls_reset(LANGSMITH_TRACING=_flag)
        _bootstrap_langsmith_env()
        assert "LANGCHAIN_TRACING_V2" not in _ls_os.environ, \
            f"Case 4 FAIL: LANGSMITH_TRACING={_flag!r} switched tracing on anyway"
    print("PASS Case 4 - '1'/'true'/'yes'/'on' enable tracing, '0'/'false'/'off'/'no' do not")

    # ── Case 5: a run config always carries a thread id ──────────────────────
    # LangGraph refuses to run with a checkpointer and no thread id, so one is
    # generated rather than left to the caller to remember.
    _ls_reset(LANGSMITH_API_KEY="ls-test-key")
    _cfg = langsmith_config()
    assert _cfg["configurable"]["thread_id"].startswith("run_"), \
        f"Case 5 FAIL: no thread id was generated: {_cfg}"
    assert "run_name" not in _cfg and "tags" not in _cfg, \
        f"Case 5 FAIL: empty optional fields should be absent, not empty: {_cfg}"
    print("PASS Case 5 - a thread id is generated and unused fields stay out of the config")

    # ── Case 6: an explicit thread id is kept ────────────────────────────────
    _cfg = langsmith_config(run_name="HTML Agent - GM-01", thread_id="gm-01-abc",
                            tags=["e2e"], metadata={"suite": "tier2"})
    assert _cfg["configurable"]["thread_id"] == "gm-01-abc", \
        "Case 6 FAIL: the caller's thread id was replaced by a generated one"
    assert _cfg["run_name"] == "HTML Agent - GM-01" and _cfg["tags"] == ["e2e"], \
        f"Case 6 FAIL: the caller's fields did not survive: {_cfg}"
    print("PASS Case 6 - a caller-supplied thread id, run name, tags and metadata all survive")

    # ── Case 7: two configs never share a thread id ──────────────────────────
    # Two runs sharing a thread would append to one conversation and corrupt
    # each other's history.
    _ids = {langsmith_config()["configurable"]["thread_id"] for _ in range(50)}
    assert len(_ids) == 50, f"Case 7 FAIL: {50 - len(_ids)} generated thread id(s) collided"
    print("PASS Case 7 - 50 generated thread ids, all distinct")

finally:
    _ls_restore()

print("=" * 64)
print("LangSmith helpers: 7/7 cases PASSED (environment restored)")
print("=" * 64)
