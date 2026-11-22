"""Bridge between the Streamlit frontend (``stream_lit.py``) and the
LangGraph backend (the ``webforge`` package, through ``webforge.entry``).

Design rules
------------
- This module is a pure, importable Python module.
- It has NO dependency on Streamlit and NEVER touches ``st.session_state``.
- It has NO side effects on import: heavy backend imports (``webforge.entry.graph``,
  LangChain message classes) happen lazily inside the functions that
  actually need them.
- It is stateless: it holds no module-level mutable state. All state
  flows in as arguments and out as return values.
- It only ever returns plain Python types — strings, dicts, lists of
  dicts, or a small ``StreamSession`` helper. LangChain ``BaseMessage``
  objects are converted to ``{"role", "content"}`` dicts before they
  leave this module. One exception, on purpose (ticket 15 left it):
  ``label_model()`` hands the UI the backend's model object, which the UI
  only passes back to ``stream_message`` as ``llm``.
- ``ThreadStore`` is the one place that reads or rewrites the saved
  threads (the graph's checkpointer): list, history, delete, heal, repair,
  and the pending question a turn ends on.
  The public functions below are thin calls into it.
- The UI (``stream_lit.py``) uses only the public names below and imports
  no agent code itself (ticket 13, ``tests/test_bridge.py``).

Public interface (``__all__``; ticket 13: the UI uses these and nothing else)
----------------------------------------------------------------------------
- ``PLACEHOLDER_LABEL``: the sidebar label of a thread with no message yet
- ``warm_up() -> None``: load the backend ahead of the first message
- ``label_model()``: the model ``stream_message`` titles a new thread with
- ``initialize_session() -> dict``
- ``new_chat(current_threads: dict) -> dict``
- ``stream_message(query, thread_id, threads, llm) -> StreamSession``  # streaming
- ``switch_chat(thread_id: str) -> list[dict]``
- ``list_threads(limit) -> dict``, ``delete_thread(thread_id) -> None``

Behind it, also in ``__all__``: ``StreamSession`` (what ``stream_message``
returns) and ``ThreadStore`` (the checkpointer adapter, used directly only by
tests).
"""

from __future__ import annotations

import uuid
from typing import Any, Dict, Iterator, List

# The UI/agent contract: stdlib only, so importing it loads no agent code.
from webforge.contract import ANSWER, ANSWER_BOUNDARY, PROCESSING, ProgressEvent

# The narrow interface: what the UI uses, plus the two classes behind it.
# tests/test_bridge.py BR-2 fails if the UI uses a name not listed here, or
# if a listed function is one the UI no longer uses.
__all__ = [
    "PLACEHOLDER_LABEL", "warm_up", "label_model",
    "initialize_session", "new_chat", "stream_message", "switch_chat",
    "list_threads", "delete_thread",
    "StreamSession", "ThreadStore",
]


# Sidebar label shown for any thread that hasn't received its first
# message yet. The frontend writes this into ``st.session_state.threads``
# until ``stream_message`` returns a generated label.
PLACEHOLDER_LABEL = "New Chat"


# ---------------------------------------------------------------------------
# Internal helpers (private)
# ---------------------------------------------------------------------------

def _get_graph():
    """Return the compiled LangGraph graph exported by ``webforge.entry``.

    Imported lazily so that ``import bridge`` itself does not pull in the
    full backend (which loads models, env vars, tools, etc.).
    """
    from webforge.entry import graph  # local import — avoids import-time side effects
    return graph


def warm_up() -> None:
    """Load the backend now (models, tools, the compiled graph), so the first
    message does not wait for it. The UI calls this from a background thread
    after its first paint. Raises whatever loading the backend raises."""
    _get_graph()


def label_model():
    """The cheap model the backend already built, for titling a new thread.
    Pass it to ``stream_message`` as ``llm``. Loads the backend if needed."""
    from webforge.entry import _spec_model  # local import — avoids import-time side effects
    return _spec_model


def _config(thread_id: str) -> Dict[str, Any]:
    """Build the per-thread config dict expected by LangGraph."""
    return {"configurable": {"thread_id": thread_id}}


def _pending_tool_call_ids(messages: List[Any]) -> List[str]:
    """Return tool call ids that do not yet have matching tool outputs."""
    pending_order: List[str] = []
    completed = set()

    for msg in messages or []:
        msg_type = getattr(msg, "type", None)
        if msg_type == "ai":
            for tool_call in getattr(msg, "tool_calls", None) or []:
                if isinstance(tool_call, dict):
                    tool_call_id = tool_call.get("id")
                else:
                    tool_call_id = getattr(tool_call, "id", None)
                if isinstance(tool_call_id, str) and tool_call_id:
                    pending_order.append(tool_call_id)
        elif msg_type == "tool":
            tool_call_id = getattr(msg, "tool_call_id", None)
            if isinstance(tool_call_id, str) and tool_call_id:
                completed.add(tool_call_id)

    return [tool_call_id for tool_call_id in pending_order if tool_call_id not in completed]


def _msg_role(msg: Any) -> str:
    """Map a LangChain ``BaseMessage`` to a flat ``user``/``assistant`` role."""
    msg_type = getattr(msg, "type", None)
    if msg_type == "human":
        return "user"
    return "assistant"


def _msg_content(msg: Any) -> str:
    """Best-effort extraction of plain text from a ``BaseMessage``."""
    content = getattr(msg, "content", "")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: List[str] = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict):
                text = block.get("text") or block.get("content") or ""
                if isinstance(text, str) and text:
                    parts.append(text)
        return "".join(parts)
    return str(content) if content is not None else ""


def _to_plain(messages: List[Any]) -> List[Dict[str, str]]:
    """Convert a list of ``BaseMessage`` objects to plain dicts."""
    plain: List[Dict[str, str]] = []
    for msg in messages:
        msg_type = getattr(msg, "type", None)
        if msg_type not in ("human", "ai"):
            continue
        # An AI message carrying tool_calls is a step narration the orchestrator
        # emits right before calling a sub-agent tool ("recording your brief",
        # "entering planning", ...). The user-facing reply is the FINAL AI message,
        # which has no tool_calls. Drop the narrations so a refreshed/reopened
        # thread shows the same summary-only bubble the live stream settles on,
        # instead of a stack of progress lines.
        if msg_type == "ai" and getattr(msg, "tool_calls", None):
            continue
        content = _msg_content(msg)
        if not content:
            continue
        plain.append({"role": _msg_role(msg), "content": content})
    return plain


def _generate_label(query: str, llm) -> str:
    """Use ``llm`` to summarise ``query`` into a 5-word-or-fewer chat title."""
    if llm is None:
        return ""
    prompt = (
        "Summarize this in 5 words or fewer, as a chat title. "
        "Return only the title text - no surrounding quotes, no trailing "
        "punctuation, no prefix like 'Title:'.\n\n"
        f"Message: {query}"
    )
    try:
        result = llm.invoke(prompt)
    except Exception:
        return ""

    text = getattr(result, "content", result)
    if isinstance(text, list):
        parts: List[str] = []
        for block in text:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict):
                t = block.get("text") or ""
                if isinstance(t, str) and t:
                    parts.append(t)
        text = "".join(parts)
    if not isinstance(text, str):
        text = str(text)

    label = text.strip().strip('"').strip("'").strip()
    label = label[:60].strip()
    return label


# ---------------------------------------------------------------------------
# ThreadStore — the saved conversations, through the graph's checkpointer
# ---------------------------------------------------------------------------

def _values(snapshot: Any) -> Dict[str, Any]:
    """A state snapshot's channel values, ``{}`` when it has none."""
    return getattr(snapshot, "values", None) or {}


def _messages(snapshot: Any) -> List[Any]:
    """A state snapshot's ``messages`` channel, as a new list."""
    return list(_values(snapshot).get("messages", []) or [])


class ThreadStore:
    """Every saved thread, read and written through one compiled graph.

    The conversation lives in the graph's checkpointer (a SqliteSaver on
    disk in production), so it survives a browser refresh and a server
    restart. This class is the one place that reads or rewrites it: the
    bridge's public functions and ``StreamSession`` go through it.
    """

    def __init__(self, graph) -> None:
        self.graph = graph

    @property
    def _checkpointer(self) -> Any:
        return getattr(self.graph, "checkpointer", None)

    def messages(self, thread_id: str) -> List[Any]:
        """Return the raw ``BaseMessage`` list stored for ``thread_id``.

        Returns an empty list if the thread has never been invoked (the
        checkpointer has no checkpoint for it yet). A tail left by a
        cancelled run is rewound first (``repair``).
        """
        self.repair(thread_id)
        try:
            state = self.graph.get_state(config=_config(thread_id))
        except Exception:
            return []
        return _messages(state)

    def history(self, thread_id: str) -> List[Dict[str, str]]:
        """The thread as the UI shows it: plain ``{"role", "content"}`` dicts."""
        return _to_plain(self.messages(thread_id))

    def delete(self, thread_id: str) -> None:
        """Permanently remove one thread's saved state from the checkpointer.

        After this, ``labels`` no longer returns the thread and a refresh will
        not resurrect it. Preview files on disk (``preview_<id>.{html,css,js}``)
        are deliberately NOT touched here — whether to delete the generated
        page is a separate app-layer decision. Best-effort: swallows errors so
        a delete never crashes the UI.
        """
        delete = getattr(self._checkpointer, "delete_thread", None)
        if callable(delete):
            try:
                delete(thread_id)
            except Exception:
                pass

    def labels(self, limit: int = 30) -> Dict[str, str]:
        """Return ``{thread_id: label}`` for the most recent ``limit`` threads
        the checkpointer holds, newest first.

        The chat title does NOT survive a restart, because ``_generate_label``
        writes it only into the frontend session, never into a checkpoint. So
        the label is re-derived here from each thread's first user message.
        Returns an empty dict if the checkpointer cannot be enumerated (e.g. an
        InMemorySaver, or a saver with no ``conn``), so the caller falls back
        to minting a fresh session.
        """
        conn = getattr(self._checkpointer, "conn", None)
        if conn is None:
            return {}

        try:
            cur = conn.cursor()
            # SqliteSaver keeps one row per checkpoint in ``checkpoints``; the
            # newest checkpoint_id per thread orders threads by recency.
            # Cap the count: each thread costs one get_state below to re-derive
            # its label, so an unbounded list makes cold start O(threads) state
            # reads and an unusably long sidebar. Newest first, most recent
            # `limit` only.
            cur.execute(
                "SELECT thread_id, MAX(checkpoint_id) AS c FROM checkpoints "
                "GROUP BY thread_id ORDER BY c DESC LIMIT ?",
                (max(1, int(limit)),),
            )
            rows = cur.fetchall()
        except Exception:
            return {}

        out: Dict[str, str] = {}
        for row in rows:
            tid = row[0] if row else None
            if not isinstance(tid, str) or not tid:
                continue
            label = PLACEHOLDER_LABEL
            try:
                state = self.graph.get_state(config=_config(tid))
                for msg in _messages(state):
                    if getattr(msg, "type", None) == "human":
                        label = _shorten_label(_msg_content(msg))
                        break
            except Exception:
                pass
            out[tid] = label
        return out

    def heal(self, thread_id: str) -> int:
        """Satisfy any tool_call left without a result before a thread resumes.

        Root cause of a real bug: when a run is terminated mid-tool-call, the
        checkpoint keeps the AIMessage whose ``tool_calls`` fired but never
        keeps a matching ToolMessage (the tool was killed before it returned).
        On the NEXT turn the graph replays that history to the model, and
        OpenAI rejects the whole request with ``No tool output found for
        function call call_...`` (400), so every message after a Terminate
        fails.

        We append one synthetic ToolMessage per unanswered ``tool_call_id`` so
        the saved history is valid again, then the next turn resumes normally.
        Called at the start of every stream, so it self-heals a dangling call
        whatever caused it (a Terminate, a crash, a dropped connection).

        Best-effort: never raises into the caller. Returns how many were
        healed. Operates on the top-level graph state, which is where the
        orchestrator's own tool calls to its sub-agents live -- the usual
        place a long run is stopped.
        """
        from langchain_core.messages import ToolMessage  # lazy

        config = _config(thread_id)
        try:
            state = self.graph.get_state(config=config)
        except Exception:
            return 0
        messages = _messages(state)
        answered = {
            getattr(m, "tool_call_id", None)
            for m in messages
            if getattr(m, "type", None) == "tool"
        }
        patch = []
        for m in messages:
            for tc in (getattr(m, "tool_calls", None) or []):
                tc_id = tc.get("id") if isinstance(tc, dict) else getattr(tc, "id", None)
                if tc_id and tc_id not in answered:
                    patch.append(
                        ToolMessage(
                            content="Cancelled by the user before this step returned.",
                            tool_call_id=tc_id,
                        )
                    )
        if not patch:
            return 0
        try:
            self.graph.update_state(config, {"messages": patch})
        except Exception:
            return 0
        return len(patch)

    def pending_question(self, thread_id: str) -> Dict[str, Any]:
        """The clarifying question the orchestrator raised this turn, or ``{}``.

        ask_user writes it into OrchestratorState.pending_question and ends the
        turn; reset_before clears it on the next turn, so reading it after a
        stream catches exactly that turn's question. Never raises.
        """
        try:
            snapshot = self.graph.get_state(config=_config(thread_id))
            pq = _values(snapshot).get("pending_question") or {}
            return pq if isinstance(pq, dict) else {}
        except Exception:
            return {}

    def repair(self, thread_id: str) -> bool:
        """Rewind a thread if cancellation left an unmatched tool call in history."""
        graph = self.graph
        config = _config(thread_id)

        try:
            current_snapshot = graph.get_state(config=config)
        except Exception:
            return False

        if not _pending_tool_call_ids(_messages(current_snapshot)):
            return False

        safe_snapshot = None
        try:
            for snapshot in graph.get_state_history(config):
                if not _pending_tool_call_ids(_messages(snapshot)):
                    safe_snapshot = snapshot
                    break
        except Exception:
            return False

        if safe_snapshot is None:
            delete_thread = getattr(self._checkpointer, "delete_thread", None)
            if callable(delete_thread):
                delete_thread(thread_id)
                return True
            return False

        latest_cfg = getattr(current_snapshot, "config", None) or {}
        safe_cfg = getattr(safe_snapshot, "config", None) or {}
        latest_conf = latest_cfg.get("configurable", {}) if isinstance(latest_cfg, dict) else {}
        safe_conf = safe_cfg.get("configurable", {}) if isinstance(safe_cfg, dict) else {}

        latest_id = latest_conf.get("checkpoint_id")
        safe_id = safe_conf.get("checkpoint_id")
        checkpoint_ns = latest_conf.get("checkpoint_ns", "")

        if not isinstance(latest_id, str) or not isinstance(safe_id, str):
            return False

        return self._prune_tail(thread_id, checkpoint_ns, latest_id, safe_id)

    def _prune_tail(self, thread_id: str, checkpoint_ns: str, latest_id: str,
                    safe_id: str) -> bool:
        """Drop checkpoint entries newer than ``safe_id`` for one thread.

        Only an in-memory saver exposes its ``storage``; on any other saver
        this does nothing and returns False.
        """
        storage = getattr(self._checkpointer, "storage", None)
        writes = getattr(self._checkpointer, "writes", None)

        if not isinstance(storage, dict) or not latest_id or latest_id == safe_id:
            return False

        thread_storage = storage.get(thread_id)
        if not isinstance(thread_storage, dict):
            return False

        ns_storage = thread_storage.get(checkpoint_ns)
        if not isinstance(ns_storage, dict):
            return False

        current_id = latest_id
        pruned = False

        while current_id and current_id != safe_id:
            entry = ns_storage.pop(current_id, None)
            if isinstance(writes, dict):
                writes.pop((thread_id, checkpoint_ns, current_id), None)
            pruned = pruned or entry is not None
            if not entry:
                break
            current_id = entry[2] if len(entry) >= 3 else None

        return pruned


def _store() -> ThreadStore:
    """The ThreadStore over the production graph (loads the backend)."""
    return ThreadStore(_get_graph())


# ---------------------------------------------------------------------------
# Public API — session lifecycle + non-streaming send
# ---------------------------------------------------------------------------

def initialize_session() -> Dict[str, Any]:
    """Produce a fresh session-state payload for first app load."""
    thread_id = str(uuid.uuid4())
    return {
        "active_thread": thread_id,
        "threads": {thread_id: PLACEHOLDER_LABEL},
    }


def new_chat(current_threads: Dict[str, str]) -> Dict[str, Any]:
    """Append a new thread to the sidebar without hitting the backend."""
    threads = dict(current_threads or {})
    thread_id = str(uuid.uuid4())
    threads[thread_id] = PLACEHOLDER_LABEL
    return {"active_thread": thread_id, "threads": threads}


def switch_chat(thread_id: str) -> List[Dict[str, str]]:
    """Fetch ``thread_id``'s history from LangGraph as plain dicts."""
    return _store().history(thread_id)


def delete_thread(thread_id: str) -> None:
    """Permanently remove one thread's saved state (``ThreadStore.delete``).
    Backs the sidebar's delete action; never raises."""
    if not thread_id:
        return
    _store().delete(thread_id)


def list_threads(limit: int = 30) -> Dict[str, str]:
    """``{thread_id: label}`` for the most recent ``limit`` threads, newest
    first (``ThreadStore.labels``). Rebuilds the sidebar after a browser
    refresh or a server restart."""
    return _store().labels(limit)


def _shorten_label(text: str, limit: int = 40) -> str:
    """Collapse whitespace and clip a message to a one-line sidebar label."""
    text = " ".join((text or "").split())
    if not text:
        return PLACEHOLDER_LABEL
    return text if len(text) <= limit else text[:limit].rstrip() + "…"


# ---------------------------------------------------------------------------
# Streaming
# ---------------------------------------------------------------------------

def _extract_token_text(raw: Any) -> str:
    """Pull the user-visible text out of one ``graph.stream`` chunk.

    With ``stream_mode='messages'`` LangGraph yields tuples of
    ``(AIMessageChunk, metadata)``. ``AIMessageChunk.content`` may be a
    plain string or a list of provider content blocks (reasoning,
    tool_call, text, ...). We surface only the user-facing ``text``
    portion so the UI doesn't print intermediate reasoning or tool
    payloads as if they were the answer.
    """
    try:
        from langchain_core.messages import AIMessageChunk  # lazy
    except Exception:
        AIMessageChunk = None  # type: ignore

    token = raw[0] if isinstance(raw, tuple) and raw else raw

    if AIMessageChunk is not None and not isinstance(token, AIMessageChunk):
        return ""

    content = getattr(token, "content", "")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: List[str] = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict):
                if block.get("type") == "text":
                    text = block.get("text", "")
                    if isinstance(text, str):
                        parts.append(text)
        return "".join(parts)
    return ""


def _extract_token_id(raw: Any) -> Any:
    """Return the message id of one ``stream_mode='messages'`` chunk.

    All ``AIMessageChunk`` deltas that belong to ONE assistant message share the
    same ``.id``; the id changes when the graph moves on to a new message. The
    frontend uses that change as a boundary: the Primary Orchestrator narrates
    each step as its own short message before a tool call, so a new id means "a
    new narration line started" — the cue to REPLACE the live bubble rather than
    keep appending (otherwise every step piles up into one long blob). Returns
    None when there is no id (some providers), in which case the caller falls
    back to plain accumulation.
    """
    token = raw[0] if isinstance(raw, tuple) and raw else raw
    return getattr(token, "id", None)


class StreamSession:
    """Wrapper over ``graph.stream`` for one user query.

    :meth:`stream_events` yields typed ``(kind, text)`` tuples where
    ``kind`` is either ``"answer"`` (real assistant tokens) or
    ``"processing"`` (orchestrator middleware progress strings). The
    Streamlit frontend uses this to render processing steps in a
    separate, collapsible block from the final answer.

    After the iterator is exhausted these attributes are populated:

    - ``response``         — the full concatenated assistant reply.
    - ``processing_steps`` — list of progress strings emitted via
      ``get_stream_writer()`` from the LangGraph middlewares.
    - ``threads``          — the (possibly relabelled) threads dict.
    - ``label_updated``    — True iff this was the thread's first
      message and a non-empty label was generated.
    """

    def __init__(
        self,
        query: str,
        thread_id: str,
        threads: Dict[str, str],
        llm,
        tone: str = "friendly",
    ) -> None:
        self.query = query
        self.thread_id = thread_id
        self.threads: Dict[str, str] = dict(threads or {})
        self._llm = llm
        # The Primary Orchestrator's voice for this turn. A declared
        # OrchestratorState channel that reset_before does NOT clear, so the
        # frontend passes the current selection every turn to keep it in sync
        # (same pattern as session_id). Defaults to the schema default.
        self.tone = tone or "friendly"

        self.response: str = ""
        self.processing_steps: List[str] = []
        self.label_updated: bool = False
        # The one clarifying question the orchestrator raised this turn, if any.
        # ask_user writes {question, options:[{field,value,label,help}],
        # allow_free_text} into OrchestratorState.pending_question and ends the
        # turn. We read it back after the stream so the frontend can draw the
        # option box. Empty dict means no question was asked.
        self.pending_question: Dict[str, Any] = {}
        self._consumed: bool = False

    def stream_events(self) -> Iterator[ProgressEvent]:
        """Yield typed ``(kind, text)`` tuples.

        ``kind`` is ``"answer"`` for real assistant tokens and
        ``"processing"`` for orchestrator progress strings.
        """
        # Detect first-message status BEFORE invoking — once the graph
        # runs, the message list is no longer empty.
        store = _store()
        was_first = len(store.messages(self.thread_id)) == 0

        from langchain_core.messages import HumanMessage  # lazy

        graph = store.graph
        config = _config(self.thread_id)

        # A previous run terminated mid-tool-call can leave a dangling tool_call
        # in this thread's checkpoint. Heal it before resuming, or the model
        # rejects this turn with 'No tool output found for function call ...'.
        store.heal(self.thread_id)

        chunks: List[str] = []
        # Message-boundary tracking. The orchestrator emits one short narration
        # message per step (each with its own id); when the id changes we yield
        # an ("answer_boundary", "") so the frontend clears the live bubble and
        # shows only the CURRENT step. `chunks` is reset at the same moment, so
        # after the stream `self.response` holds only the LAST message's text —
        # the final summary — never the whole pile. A sentinel start id means the
        # very first text token always opens with a (harmless) boundary.
        cur_msg_id: Any = object()
        try:
            # Multi-mode streaming: "messages" gives us LLM token
            # deltas; "custom" gives us anything the orchestrator's
            # middlewares pushed via ``get_stream_writer()`` (e.g.
            # "[Context Agent] Processing request..."). Without
            # "custom" those progress lines never reach the UI.
            stream_iter = graph.stream(
                # session_id is a declared OrchestratorState channel, distinct
                # from the config's thread_id: thread_id keys the checkpointer,
                # session_id names the preview_<sid>.{html,css,js} files a modify
                # re-opens. reset_before never sets it, so the caller must seed
                # it in the input payload or call_secondary_orchestrator refuses
                # the whole build. The thread_id issued by the app layer IS the
                # session id (a uuid4 -> safe for _safe_session_id).
                {"messages": [HumanMessage(content=self.query)],
                 "session_id": self.thread_id,
                 "tone": self.tone},
                config=config,
                stream_mode=["messages", "custom"],
            )
            for raw in stream_iter:
                # When multiple modes are requested, LangGraph yields
                # (mode_name, payload) tuples. Defensive fallback: if
                # we somehow get a bare payload, treat it as messages.
                if (
                    isinstance(raw, tuple)
                    and len(raw) == 2
                    and isinstance(raw[0], str)
                    and raw[0] in ("messages", "custom", "updates")
                ):
                    mode, payload = raw
                else:
                    mode, payload = "messages", raw

                if mode == "messages":
                    text = _extract_token_text(payload)
                    if text:
                        msg_id = _extract_token_id(payload)
                        if msg_id != cur_msg_id:
                            # A new narration line began -> tell the frontend to
                            # replace the bubble, and start accumulating fresh so
                            # self.response ends as the final message only.
                            cur_msg_id = msg_id
                            chunks = []
                            yield ProgressEvent(ANSWER_BOUNDARY, "")
                        chunks.append(text)
                        yield ProgressEvent(ANSWER, text)
                elif mode == "custom":
                    # Middlewares emit strings ("Processing...") or
                    # formatting dicts ({"type": "indent", ...}). Only
                    # yield the human-readable strings; skip layout
                    # dicts entirely.
                    if isinstance(payload, str):
                        s = payload.strip()
                        if s:
                            self.processing_steps.append(s)
                            yield ProgressEvent(PROCESSING, s)
        finally:
            self.response = "".join(chunks)

            # Read the clarifying question (if any) back from the graph state.
            self.pending_question = store.pending_question(self.thread_id)

            # Label generation runs strictly AFTER the stream finishes
            # so the user sees the assistant reply first.
            if was_first:
                new_label = _generate_label(self.query, self._llm)
                if new_label:
                    self.threads[self.thread_id] = new_label
                    self.label_updated = True

            self._consumed = True


def stream_message(
    query: str,
    thread_id: str,
    threads: "dict",
    llm,
    tone: str = "friendly",
) -> "StreamSession":
    """Start streaming one user query.

    Returns a :class:`StreamSession`. Its :meth:`StreamSession.stream_events`
    yields the chunks produced by ``graph.stream(..., stream_mode='messages')``.
    Once exhausted, the session exposes ``response``, ``threads``, and
    ``label_updated`` for the frontend to write back into session state.
    """
    return StreamSession(query, thread_id, threads, llm, tone=tone)
