"""The webforge/ package source, shaped like a notebook's cell list (ticket 05).

Several ported notebook cells check the CODE as text: that a prompt names
the variables its tool feeds, that no serialisation uses formatter="html5",
that a tool list matches. In the notebook they read fyp.ipynb's cells. The
notebook is frozen now, so a check on it can never catch a change to the
package. They read this instead: one code "cell" per webforge module, in
load order, then the test_execution package's modules (ticket 11), then
config, with the same "cell_type" and "source" keys a notebook cell has.
"""
from webforge import LOAD_ORDER, SUBMODULES
from webforge.config import REPO_ROOT


def package_cells() -> list:
    cells = []
    for short in (*LOAD_ORDER, *SUBMODULES, "config"):
        path = REPO_ROOT / "webforge" / (short.replace(".", "/") + ".py")
        cells.append({"cell_type": "code", "source": [path.read_text(encoding="utf-8")],
                      "module": short})
    return cells


def package_notebook() -> dict:
    """The same, as a parsed .ipynb (`{"cells": [...]}`)."""
    return {"cells": package_cells()}
