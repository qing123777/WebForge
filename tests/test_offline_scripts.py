"""Run the script-style checks under pytest (ticket 05).

    pytest tests/test_offline_scripts.py

These files check things with their own runner and exit non-zero on a
failure, but define no test_ function, so pytest would collect nothing from
them. Each runs here as its own process, exactly as `python tests/<file>`
does, and a non-zero exit fails the test with the script's last lines.
"""
import ast
import pathlib
import subprocess
import sys

import pytest

from conftest import REQUIRES_LOCAL_DEV

HERE = pathlib.Path(__file__).resolve().parent
SCRIPTS = ["test_config.py", "test_package_split.py",
           "test_state_schemas.py", "test_ui_baseline.py"]


@pytest.mark.parametrize("script", SCRIPTS)
def test_script_exits_zero(script):
    needs = REQUIRES_LOCAL_DEV.get(script)
    if needs and not (HERE.parent / needs).exists():
        pytest.skip(f"{script} reads {needs}/, which a fresh clone does not have")
    proc = subprocess.run([sys.executable, str(HERE / script)], cwd=HERE.parent,
                          capture_output=True, text=True, timeout=600)
    tail = "\n".join((proc.stdout + proc.stderr).splitlines()[-25:])
    assert proc.returncode == 0, f"{script} exited {proc.returncode}:\n{tail}"


def test_every_script_style_file_is_listed():
    """A new tests/test_*.py with no test_ function must be added above, or
    pytest would silently run nothing from it."""
    unlisted = []
    for path in sorted(HERE.glob("test_*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        collectable = any(
            (isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name.startswith("test"))
            or (isinstance(n, ast.ClassDef) and n.name.startswith("Test"))
            for n in tree.body)
        if not collectable and path.name not in SCRIPTS:
            unlisted.append(path.name)
    assert not unlisted, f"script-style tests not run by pytest: {unlisted}"


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
