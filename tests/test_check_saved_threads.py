"""tools/check_saved_threads.py: does every saved chat still open?

    python -m pytest tests/test_check_saved_threads.py   (or python tests/test_check_saved_threads.py)

Offline, no model calls.

  CS-1  on a real SQLite checkpointer, every thread that opens is counted as
        good, and a thread whose state cannot be read is reported with its
        error. The app hides such a failure (ThreadStore.messages returns []),
        which is why this check exists: ticket 15 deleted the `fyp` module a
        saved object could name.
"""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import conftest  # noqa: E402,F401  (repo on sys.path, dead API keys) when run with python

import pytest  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))


def test_reports_the_threads_that_fail_to_open(tmp_path, monkeypatch):
    import sqlite3
    import check_saved_threads as cst
    from langchain_core.messages import HumanMessage
    from langgraph.checkpoint.sqlite import SqliteSaver
    from langgraph.graph import END, START, MessagesState, StateGraph
    conn = sqlite3.connect(str(tmp_path / "threads.db"), check_same_thread=False)
    g = StateGraph(MessagesState)
    g.add_node("echo", lambda s: {})
    g.add_edge(START, "echo")
    g.add_edge("echo", END)
    graph = g.compile(checkpointer=SqliteSaver(conn))
    for tid in ("good", "broken"):
        graph.invoke({"messages": [HumanMessage(content=tid)]},
                     {"configurable": {"thread_id": tid}})
    real = graph.get_state

    def get_state(config, *a, **k):
        if config["configurable"]["thread_id"] == "broken":
            raise ModuleNotFoundError("No module named 'fyp'")
        return real(config, *a, **k)

    monkeypatch.setattr(graph, "get_state", get_state)
    total, failures = cst.check(graph)
    assert total == 2
    assert failures == [("broken", "ModuleNotFoundError: No module named 'fyp'")]
    conn.close()


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
