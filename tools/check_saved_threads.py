"""Does every saved chat in the checkpoint database still open?

    python tools/check_saved_threads.py

Opens each thread the app's checkpointer holds (config.CHECKPOINT_DB,
fyp_threads.db) and reads its state the way the app does, but lets an error
show: the app itself hides one, because ThreadStore.messages returns an empty
history when a read fails, so a broken chat just looks empty.

Why it exists: LangGraph saves a custom object by its module path. Ticket 15
deleted the `fyp` module (the old fyp.py shim), so a chat saved long ago that
held an object from module `fyp` would no longer decode. None is expected (the
state holds plain dicts and LangChain messages); this proves it on the PC that
has the real database.

Builds the graph (no model call), reads the database, writes nothing.
Prints one line per broken thread and a summary; exits 1 if any is broken.
"""
from __future__ import annotations

import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def check(graph, limit: int = 100_000) -> tuple[int, list[tuple[str, str]]]:
    """(threads read, [(thread_id, error)]) for every thread in the graph's
    checkpointer, newest first."""
    import bridge
    thread_ids = list(bridge.ThreadStore(graph).labels(limit))
    failures = []
    for tid in thread_ids:
        try:
            graph.get_state(config={"configurable": {"thread_id": tid}})
        except Exception as exc:  # noqa: BLE001  any failure is the finding
            failures.append((tid, f"{type(exc).__name__}: {exc}"))
    return len(thread_ids), failures


def main() -> int:
    from webforge.entry import graph
    total, failures = check(graph)
    for tid, error in failures:
        print(f"BROKEN  {tid}: {error}")
    print(f"[proof] {total - len(failures)} of {total} saved chats open; "
          f"{len(failures)} broken")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
