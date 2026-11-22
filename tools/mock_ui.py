"""Run the real Streamlit UI on the zero-credit mock backend.

    python -m streamlit run tools/mock_ui.py --server.port 8599 --server.headless true

Streamlit re-executes this file on every rerun. ``install()`` is idempotent,
so the fake ``webforge.entry`` module (and its thread database) survives reruns exactly
as the real one does.
"""
import os
import pathlib
import runpy
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
for p in (str(ROOT), str(ROOT / "tools")):
    if p not in sys.path:
        sys.path.insert(0, p)

# Dead keys: if anything reaches a real client it fails instead of charging.
for _k in ("OPENAI_API_KEY", "LANGSMITH_API_KEY", "TAVILY_API_KEY"):
    os.environ[_k] = "sk-mock-dead-key"
os.environ["LANGSMITH_TRACING"] = "false"

import mock_backend  # noqa: E402

mock_backend.install()
runpy.run_path(str(ROOT / "stream_lit.py"), run_name="__main__")
