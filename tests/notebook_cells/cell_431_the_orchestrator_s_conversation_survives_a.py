# Ported from fyp.ipynb cell 431 (ticket 05). The notebook is frozen;
# edit this file. Run by tests/test_notebook_cells.py.
# Unit tests: the orchestrator's conversation survives a process restart
# The point of the swap is that state outlives the Python process, so a test
# that only writes and reads inside one process proves nothing. Each case below
# CLOSES the connection before reading, which is the closest thing to a restart
# that can happen inside one notebook run.

import sqlite3 as _t_sqlite
import tempfile as _t_tmp
import pathlib as _t_pl

_ck_passed = 0


def _ck_ok(tid, desc):
    global _ck_passed
    _ck_passed += 1
    print("PASS  %-5s %s" % (tid, desc))


_ck_dir = _t_pl.Path(_t_tmp.mkdtemp(prefix="fyp_ckpt_"))
_ck_path = _ck_dir / "probe.db"


def _open_saver(path):
    conn = _t_sqlite.connect(str(path), check_same_thread=False)
    conn.execute("PRAGMA journal_mode=WAL")
    return conn, SqliteSaver(conn)


# checkpoint_ns names the sub-graph a checkpoint belongs to. LangGraph fills it
# in at runtime; a hand-built config has to supply it or the write has no key.
_cfg = {"configurable": {"thread_id": "sid-restart-probe", "checkpoint_ns": ""}}
_conn, _saver = _open_saver(_ck_path)
_saver.put(
    _cfg,
    {"v": 1, "id": "ckpt-1", "ts": "2026-08-15T00:00:00+00:00",
     "channel_values": {"design_schema": {"ui": {"commerce_type": "marketplace"}}},
     "channel_versions": {}, "versions_seen": {}},
    {"source": "update", "step": 1, "parents": {}},
    {},
)
_conn.close()          # the process is "gone" from here on
_ck_ok("CK-1", "a checkpoint was written and the connection closed")

_conn2, _saver2 = _open_saver(_ck_path)
_back = _saver2.get(_cfg)
assert _back is not None, "CK-2 FAIL: nothing came back after reopening the file"
assert _back["channel_values"]["design_schema"]["ui"]["commerce_type"] == "marketplace", \
    "CK-2 FAIL: the value changed across the reopen"
_ck_ok("CK-2", "reopening the file returns the same design schema, so a restart is survivable")

_other = _saver2.get({"configurable": {"thread_id": "sid-someone-else",
                                       "checkpoint_ns": ""}})
assert _other is None, "CK-3 FAIL: a different thread id read another thread's state"
_ck_ok("CK-3", "a different session id sees nothing, so threads stay separate")

assert _conn2.execute("PRAGMA journal_mode").fetchone()[0].lower() == "wal", \
    "CK-4 FAIL: WAL is off, so every checkpoint rewrites the main database file"
_conn2.close()
_ck_ok("CK-4", "the write-ahead log is on, which is what keeps the write cheap")

# The swap is only real if the agent that actually runs holds the new object. An
# InMemorySaver here would pass every case above and still lose everything.
assert isinstance(orchestrator_agent.checkpointer, SqliteSaver), \
    ("CK-5 FAIL: the built orchestrator holds %s, not a SqliteSaver. The tests "
     "above would still pass while the running system forgot everything."
     % type(orchestrator_agent.checkpointer).__name__)
_ck_ok("CK-5", "the ORCHESTRATOR THAT RUNS holds the SQLite checkpointer, not a stand-in")

print("=" * 76)
print("orchestrator checkpointer: %d/5 PASSED  (file: %s)"
      % (_ck_passed, _CHECKPOINT_DB.name))
print("Only a real restart proves the rest. Generate a page, stop Python, start")
print("it again, then send a modify request on the same session id: it must not")
print("ask you anything it already knows.")
print("=" * 76)
