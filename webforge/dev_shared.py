"""dev_shared: helpers shared by the developer agents: _assert_channels, component extraction, the preview filesystem backend.

Lines 4487-4766 of the flat fyp.py at commit 6e8c14b, moved
verbatim by refactor ticket 04 (tools/split_fyp.py).
"""
from __future__ import annotations

from webforge.specs import *  # noqa: F401,F403

# ==========================================================================
# Pipeline
# ==========================================================================
# ═══════════════════════════════════════════════════════════════════════════
# _assert_channels - a build-time guard against LangGraph's silent channel drop
#
# A write to a state channel the schema does not declare is dropped silently by
# LangGraph: logged, then ignored. The only cheap place to catch it is next to
# create_agent, so every agent build calls this.
#
# The System Design Planning AGENT that used to live in this cell (its prompt,
# PlanningState, and the create_agent build) was replaced by
# run_planning_pipeline on 2026-08-23. The four generators now run as a
# deterministic chain that threads a plain dict, which has no channels to drop,
# so PlanningState and its channel list are gone. This helper stays because the
# other agent builds - context, the three developers, both orchestrators - still
# rely on it.
# ═══════════════════════════════════════════════════════════════════════════
def _assert_channels(schema, required, label):
    """Fail at build time if a tool writes a key the schema cannot hold.

    A write to a missing channel is silent in LangGraph, so the only place it
    can be caught cheaply is here, next to create_agent."""
    import typing
    have = set(typing.get_type_hints(schema, include_extras=True))
    missing = sorted(set(required) - have)
    if missing:
        raise AssertionError(
            f"{label}: state_schema {schema!r} has no channel for {missing}. "
            f"Writes to those keys would be dropped without an error.")
    return sorted(have)


# ==========================================================================
# Shared helper function
# ==========================================================================
import re

def _apply_patch(original: str, diff_text: str) -> str:
    """
    Pure-Python unified diff applicator.
    No subprocess or external patch command needed — works on Windows.
    """
    original_lines = original.splitlines(keepends=True)
    result_lines   = list(original_lines)

    hunk_re    = re.compile(r'^@@ -(\d+)(?:,(\d+))? \+\d+(?:,\d+)? @@')
    diff_lines = diff_text.splitlines()

    hunks = []
    i = 0
    while i < len(diff_lines):
        m = hunk_re.match(diff_lines[i])
        if m:
            orig_start = int(m.group(1)) - 1
            orig_count = int(m.group(2)) if m.group(2) else 1
            i += 1
            hunk_body = []
            while i < len(diff_lines) and not hunk_re.match(diff_lines[i]):
                hunk_body.append(diff_lines[i])
                i += 1
            hunks.append((orig_start, orig_count, hunk_body))
        else:
            i += 1

    def _hunk_expected(hunk_body):
        """The lines a hunk expects to find, newline-normalised for comparison."""
        return [ln[1:].rstrip("\n") for ln in hunk_body
                if ln.startswith(" ") or ln.startswith("-")]

    def _matches_at(lines, start, expected):
        if start < 0 or start + len(expected) > len(lines):
            return False
        return all(lines[start + k].rstrip("\n") == expected[k]
                   for k in range(len(expected)))

    def _relocate(lines, expected, stated):
        """Find the one place `expected` occurs, or None.

        The @@ header says WHERE and the context says WHAT, and a model that
        writes a good hunk still routinely gets the number wrong. Searching by
        context is what a real patch tool does. The match must be UNIQUE: with
        two candidates there is no way to tell which the author meant, and
        guessing is how a patch lands in the wrong place and silently corrupts
        the file. Ambiguous or absent both fall through to the original error.
        """
        if not expected:
            return None
        hits = [k for k in range(len(lines) - len(expected) + 1)
                if _matches_at(lines, k, expected)]
        if len(hits) != 1:
            return None
        return hits[0]

    for orig_start, stated_count, hunk_body in reversed(hunks):
        expected_lines = _hunk_expected(hunk_body)

        # How many lines this hunk consumes comes from its BODY, never from the
        # count in its @@ header.
        #
        # A unified diff states the length twice: the header counts it, the body
        # lists it. In a well-formed diff the two agree, so reading the body is
        # not a new rule -- it is the definition. They come apart when the model
        # miscounts, and then the header is wrong while the body, which is
        # transcription rather than arithmetic, is right.
        #
        # Splicing by the header is what produced the E2E-CSS-MM-01 failure on
        # 2026-08-31: a header saying 4 over a body listing 5 removed four lines
        # and wrote five back, so the fifth stayed. The leftover was a closing
        # brace, stylelint reported "133:1 Unexpected }", and the lint loop could
        # not win because the damage sat outside the block the model was handed.
        # Same mistake Fix 6 corrected for POSITION, left standing for LENGTH.
        orig_count = len(expected_lines)

        # The stated position is tried first and unchanged, so a correctly
        # numbered diff behaves exactly as it always has.
        if not _matches_at(result_lines, orig_start, expected_lines):
            found = _relocate(result_lines, expected_lines, orig_start)
            if found is None:
                src_i    = orig_start
                expected = (expected_lines[0] + "\n") if expected_lines else "<nothing>"
                raise ValueError(
                    f"Hunk at original line {orig_start + 1} does not match "
                    f"current content at line {src_i + 1}, and its context does "
                    f"not appear exactly once anywhere else in the block.\n"
                    f"  Expected : {repr(expected)}\n"
                    f"  Got      : {repr(result_lines[src_i]) if src_i < len(result_lines) else '<EOF>'}\n"
                    "Re-extract the component and regenerate the diff against "
                    "the current version."
                )
            orig_start = found

        replacement = []
        for line in hunk_body:
            if line.startswith("+"):
                text = line[1:]
                replacement.append(text if text.endswith("\n") else text + "\n")
            elif line.startswith(" "):
                text = line[1:]
                replacement.append(text if text.endswith("\n") else text + "\n")
        result_lines[orig_start : orig_start + orig_count] = replacement

    return "".join(result_lines)


# ==========================================================================
# Shared helper function
# ==========================================================================
import re

# ── Multi-block diff support (shared by the CSS and JS agents) ────────────────
# A component's code is rarely one block: a CSS rule usually has :hover and
# media-query variants, and a JS component can own several listeners. Only the
# first block used to be editable, so a "make the button darker" request left
# the hover state on the old colour.
#
# These helpers let every matching block be extracted, diffed and spliced back
# as one unit. The blocks are shown to the model as a single document joined by
# marker comment lines, which keeps unified-diff line numbers unambiguous across
# block boundaries. The markers are stripped on the way back and never reach the
# generated artifact.

_WF_BLOCK_MARK_RE = re.compile(
    r'^[ \t]*/\* @@ WebForge block \d+ of \d+ @@ \*/[ \t]*$', re.M)


def _join_blocks(blocks: list) -> str:
    """Join extracted blocks into one diffable document.

    A single block is returned untouched, so the common one-block case behaves
    exactly as it did before markers existed.
    """
    if len(blocks) <= 1:
        return blocks[0] if blocks else ""
    total = len(blocks)
    return "\n".join(f"/* @@ WebForge block {n} of {total} @@ */\n{b}"
                     for n, b in enumerate(blocks, 1))


def _split_blocks(joined: str, expected: int) -> list:
    """Inverse of _join_blocks.

    Raises if the marker lines were not preserved, rather than guessing at the
    boundaries — the same fail-loud rule _apply_patch applies to diff context.
    """
    # Trailing newlines are trimmed on every path. _apply_patch terminates each
    # added line with "\n", so patching a block's LAST line used to leave a
    # stray blank line behind once the block was spliced back. Extracted spans
    # never include the newline that follows a block, so the replacement text
    # must not either.
    if expected <= 1:
        return [joined.strip("\r\n")]

    # Compare the surviving markers against the exact sequence that was handed
    # out. A plain count check is not enough: deleting the FIRST marker still
    # leaves `expected` sections, and the blocks would silently merge.
    want  = [f"/* @@ WebForge block {n} of {expected} @@ */" for n in range(1, expected + 1)]
    found = [m.strip() for m in _WF_BLOCK_MARK_RE.findall(joined)]
    if found != want:
        raise ValueError(
            f"Block separator lines were altered: expected {want}, found {found}. "
            "Every '/* @@ WebForge block N of M @@ */' line must be kept unchanged "
            "as diff context. Re-extract the component and regenerate the diff.")

    parts = _WF_BLOCK_MARK_RE.split(joined)
    if parts[0].strip() != "":
        raise ValueError(
            "Text appeared before the first block separator. The patched text must "
            "begin with the '/* @@ WebForge block 1 of "
            f"{expected} @@ */' line, kept unchanged. Re-extract and regenerate.")
    return [p.strip("\r\n") for p in parts[1:]]


def _splice_spans(code: str, spans: list, new_blocks: list) -> str:
    """Replace each (start, end) character span in `code` with its new block.

    Applied right-to-left so earlier spans keep their offsets. Character spans
    are used rather than str.replace so that two textually identical blocks can
    never be confused, and so non-contiguous blocks splice back into their own
    positions instead of silently failing to match.
    """
    if len(spans) != len(new_blocks):
        raise ValueError(
            f"span/block count mismatch: {len(spans)} spans, {len(new_blocks)} blocks")
    out = code
    for (start, end), new in sorted(zip(spans, new_blocks), key=lambda p: -p[0][0]):
        out = out[:start] + new + out[end:]
    return out


# ==========================================================================
# Preview filesystem backend (overwrite-capable)
# ==========================================================================
# ═══════════════════════════════════════════════════════════════════════════
# Preview filesystem backend — overwrite-capable
#
# WHY THIS EXISTS
# deepagents' FilesystemBackend.write() refuses unconditionally when the target
# path already exists:
#
#     if resolved_path.exists():
#         return WriteResult(error="Cannot write to ... because it already exists.")
#
# There is no "was read first" exemption. That guard makes sense for a general
# coding agent (don't clobber a user's file), but it breaks this system's
# Modification Mode: every developer agent reads preview_{session_id}.{html,css,js}
# at Step 0 and writes the revised version back to that same path at Step 5.
# The write was silently refused, so a modification was correct in state, linted
# clean and reported success — while the file on disk never changed.
#
# Found 2026-07-18 by the tier-2 turn-based suites (TB-*-4). Every tool passed
# its own unit tests; the defect only existed in the SEQUENCE.
#
# The parent's write() already opens with O_TRUNC, so overwriting is safe once
# the guard is out of the way. Removing the file first is the smallest change
# that reuses all of the parent's handling (parent-dir creation, O_NOFOLLOW
# symlink protection, encoding).
#
# Scope: these preview files are owned exclusively by the agents and are
# regenerated per session_id, so overwriting is the intended semantic here.
# ═══════════════════════════════════════════════════════════════════════════
class OverwritingFilesystemBackend(FilesystemBackend):
    """FilesystemBackend that allows an existing file to be replaced.

    Only `write` differs from the parent: the pre-existing-path guard is lifted
    so Modification Mode can save the revised artifact back over the original.
    Path resolution, traversal protection and virtual_mode rooting are all
    inherited unchanged.
    """

    def write(self, file_path: str, content: str):
        resolved = self._resolve_path(file_path)
        if resolved.exists() and resolved.is_file():
            resolved.unlink()
        return super().write(file_path, content)


print("OverwritingFilesystemBackend ready — modify mode can now persist to disk")


# Re-export this module's whole namespace, so the next module
# starts from it. Part of the mechanical split of ticket 04.
__all__ = [_n for _n in list(globals())
           if not (_n.startswith("__") and _n.endswith("__"))]
