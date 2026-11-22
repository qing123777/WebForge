"""Every filesystem path WebForge uses, derived from the repo root.

One place owns where things live, so the system runs from any checkout folder
(the user's PC, a cloud checkout, a CI runner). Nothing here depends on the
process's working directory or on an absolute path written into the code.

Before refactor ticket 02 these were absolute Windows paths into the user's
old project folder, repeated eight times in ``fyp.py``, plus paths taken from
``os.getcwd()``.
"""
from __future__ import annotations

import pathlib

# The repo root: the folder that holds webforge/, bridge.py and package.json.
REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent

# Generated pages: preview_<session_id>.{html,css,js}. Streamlit serves this
# folder, the developer agents' FilesystemMiddleware is rooted here, and the
# save tools write here.
PREVIEW_DIR = REPO_ROOT / "static" / "preview"

# Scratch files for eslint and stylelint. They must sit INSIDE the repo:
# eslint v9+ ignores files outside its base path, and the linters find their
# config (eslint.config.fyp.mjs, .stylelintrc.json) by walking up from here.
LINT_TMP_DIR = REPO_ROOT / ".lint_tmp"

# The Streamlit UI's own stylesheet and scripts (ticket 14), read by
# ui_assets/__init__.py.
UI_ASSETS_DIR = REPO_ROOT / "ui_assets"

# The SqliteSaver database that keeps the orchestrator's conversations across
# a process restart.
CHECKPOINT_DB = REPO_ROOT / "fyp_threads.db"
