"""The Streamlit UI's static CSS and JS, kept as real files (ticket 14).

Before ticket 14 these were Python string literals inside ``stream_lit.py``,
about 3,700 lines, one of them an f-string, so its JS and CSS had to double
every brace while the block next to it did not. Here every file is plain CSS
or JS with single braces. ``stream_lit.py`` wraps each one in its
``<style>``/``<script>`` tag, so the page receives the same text as before.

- ``app.css``: the app-wide stylesheet (``st.markdown`` at module level).
- ``chrome.js``: the parent-document script (``components.html`` at module
  level): theme, sidebar and layout chrome.
- ``preview_frame.css`` and ``preview_frame.js``: the preview iframe that
  ``_render_preview_iframe`` draws. The JS has two fields, filled by
  ``preview_frame_js``.

Standard library only, like ``webforge.config``: the UI imports no agent code.
"""
from __future__ import annotations

from webforge import config

# The two fields in preview_frame.js. Each appears exactly once.
SELECT_ENABLED_FIELD = "__WF_SELECT_ENABLED__"
MODIFY_MARKER_FIELD = "__WF_MODIFY_MARKER__"


def read(name: str) -> str:
    """The text of one asset file. Read on every call (about 170 KB per
    rerun), so an edited asset shows on the next rerun, no restart needed."""
    return (config.UI_ASSETS_DIR / name).read_text(encoding="utf-8")


def preview_frame_js(select_enabled_js: str, modify_marker_js: str) -> str:
    """preview_frame.js with its two fields filled: ``select_enabled_js`` is
    the JS literal ``true`` or ``false``, ``modify_marker_js`` the JS
    expression that builds the modify marker (``contract.modify_marker_js``)."""
    return (read("preview_frame.js")
            .replace(SELECT_ENABLED_FIELD, select_enabled_js)
            .replace(MODIFY_MARKER_FIELD, modify_marker_js))
