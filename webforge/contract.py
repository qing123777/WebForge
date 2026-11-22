"""The typed contract between the UI and the agents (refactor ticket 12).

Two things cross that boundary, and this module is the one place each is
defined:

- the MODIFY MARKER: the prefix the Select panel puts in front of a modify
  request, ``[intent=modify | target_component=<selector> |
  target_instance=<n>] <request>``. The panel builds it (in the browser, from
  ``modify_marker_js``), the UI strips it for display (``split_modify_message``)
  and the Primary Orchestrator's middleware reads it (``modify_marker_fields``).
- the PROGRESS EVENT: what ``bridge.StreamSession.stream_events`` yields to the
  UI, a ``(kind, text)`` pair, and how the UI reads a progress line.

It imports the standard library only. The UI imports it, and ticket 13 makes
the UI import nothing agent-related, so no langchain and no other webforge
module may be imported here.

The strings are on the wire: the marker reaches the model inside the user's
message, and the UI baseline records what the progress lines produce. Change
none of them in a refactor.
"""
from __future__ import annotations

import re
from typing import NamedTuple

# ---------------------------------------------------------------------------
# Modify marker
# ---------------------------------------------------------------------------

# The marker as the panel writes it, tolerant about spacing and case because it
# is produced by an interface that may be rewritten later. Found anywhere in
# the message: the agent side reads it wherever it is.
MODIFY_MARKER_RE = re.compile(r"\[\s*intent\s*=\s*modify\b([^\]]*)\]", re.I)
MARKER_FIELD_RE = re.compile(r"(\w+)\s*=\s*([^|\]]+)")

# The UI side: a message that STARTS with a marker, split into the marker and
# the request the user typed after it.
MODIFY_MESSAGE_RE = re.compile(
    r"^\s*(\[\s*intent\s*=\s*modify\b[^\]]*\])\s*(.*)$",
    re.IGNORECASE | re.DOTALL,
)

# The three literal pieces of the marker. format_modify_marker and
# modify_marker_js both build from these, so Python and the browser cannot
# drift apart.
_MARKER_HEAD = "[intent=modify | target_component="
_MARKER_MID = " | target_instance="
_MARKER_TAIL = "] "


def format_modify_marker(target_component, target_instance, request) -> str:
    """The message the Select panel sends for one modify request."""
    return (f"{_MARKER_HEAD}{target_component}{_MARKER_MID}{target_instance}"
            f"{_MARKER_TAIL}{request}")


def modify_marker_js(component_expr: str, instance_expr: str, request_expr: str) -> str:
    """A JavaScript expression that builds the same string as format_modify_marker.

    Each argument is a JS expression (``"info.selector"``), pasted in as is.
    """
    def lit(s: str) -> str:
        return "'" + s.replace("\\", "\\\\").replace("'", "\\'") + "'"
    return (f"{lit(_MARKER_HEAD)} + {component_expr} + {lit(_MARKER_MID)} + "
            f"{instance_expr} + {lit(_MARKER_TAIL)} + {request_expr}")


def modify_marker_fields(text: str) -> dict:
    """The fields of an [intent=modify | ...] marker, or {} if there is none.

    Returned rather than acted on, so the same parse can be read by a test and
    by the middleware without either owning it.
    """
    m = MODIFY_MARKER_RE.search(text or "")
    if not m:
        return {}
    fields = {"intent": "modify"}
    for key, value in MARKER_FIELD_RE.findall(m.group(1)):
        fields[key.strip().lower()] = value.strip()
    return fields


def split_modify_message(text: str):
    """``(marker, request)`` for a message that starts with a marker, else None.

    The request is stripped. The marker is returned as written.
    """
    m = MODIFY_MESSAGE_RE.match(text or "")
    if not m:
        return None
    return m.group(1), m.group(2).strip()


# ---------------------------------------------------------------------------
# Progress event
# ---------------------------------------------------------------------------

# The kinds bridge.StreamSession.stream_events yields.
ANSWER = "answer"                    # a token of the assistant's reply
ANSWER_BOUNDARY = "answer_boundary"  # a new narration message began: clear the bubble
PROCESSING = "processing"            # one progress line a middleware or tool wrote


class ProgressEvent(NamedTuple):
    """One streamed event. A tuple, so ``for kind, text in ...`` still works."""
    kind: str
    text: str


# Progress verbosity. Only high-level milestones reach the UI; low-level tool
# detail (tool verdicts, per-batch coverage) is filtered out. Heuristic
# classifier for now — to be replaced by explicit level tags once the
# middleware moves into the exported module (see the migration plan doc).
DETAIL_MARKERS = ("SUITE COMPLETE", "INCOMPLETE", "Saved ", "left)",
                  "target", "Coverage", "missing")

# Stages carry each actor's full name. The match scans the WHOLE step line, not
# just its "[Actor]" bracket, and dev/phase keywords are listed BEFORE the two
# orchestrators on purpose: a line like "[Orchestrator] Invoking Context Agent"
# or "[Secondary Orchestrator] Calling HTML Agent" then maps to the phase it is
# about (Context / HTML), so the orchestrators only claim the timeline for their
# own generic lines ("[Orchestrator] Processing request"). That keeps the "now"
# marker from bouncing back to an orchestrator between every sub-step while still
# showing both orchestrators as real stages, which is what the user asked for.
STAGE_MATCH = (
    ("Context Agent", "Context Engineering Agent"),
    ("Context Engineering", "Context Engineering Agent"),
    ("System Design", "System Planning and Design"),
    ("System Planning", "System Planning and Design"),
    ("Design Pipeline", "System Planning and Design"),
    ("HTML Agent", "HTML Agent"),
    ("CSS Agent", "CSS Agent"),
    ("JS Agent", "JS Agent"),
    ("Test Gen", "Test Generation Agent"),
    ("Test Generation", "Test Generation Agent"),
    ("Test Execution", "Test Execution Pipeline"),
    ("Secondary Orchestrator", "Secondary Orchestrator"),
    ("Orchestrator", "Primary Orchestrator"),
)
STAGE_ORDER = (
    "Primary Orchestrator",
    "Context Engineering Agent",
    "System Planning and Design",
    "Secondary Orchestrator",
    "HTML Agent",
    "CSS Agent",
    "JS Agent",
    "Test Generation Agent",
    "Test Execution Pipeline",
)
# The three developer/test stages the backend runs CONCURRENTLY (one fan-out).
# They start together, so a per-stage duration measured as "gap until the next
# stage started" is ~0 for the first two -- which is why the old timeline showed
# CSS/JS as a fake 0s. The step box no longer shows any time; these three are
# grouped under one "Parallel build" bracket instead.
PARALLEL_STAGES = ("CSS Agent", "JS Agent", "Test Generation Agent")

# Markers that mean a fix was given up on. Matched case-insensitively so the
# live line can be flagged (amber) instead of reading like ordinary progress.
WARN_MARKERS = ("cap reached", "best effort", "leaving this component")


def stage_label(line: str):
    """The canonical stage a progress line is about, or None."""
    for needle, label in STAGE_MATCH:
        if needle in line:
            return label
    return None


def is_warning(line: str) -> bool:
    """True when a progress line reports a fix that was given up on."""
    low = line.lower()
    return any(mk in low for mk in WARN_MARKERS)


def is_detail_step(line: str) -> bool:
    """True for a low-level tool line the UI hides (case-sensitive match)."""
    return any(m in line for m in DETAIL_MARKERS)
