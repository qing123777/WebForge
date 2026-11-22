"""pytest setup shared by every file under tests/.

Dead API keys are set before anything imports the package, so a test that
reaches a model by mistake fails with a rejected key instead of a charge.
Never remove this to "make a test work".
"""
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

sys.path.insert(0, str(ROOT / "tests"))
from cell_runner import disable_api_keys  # noqa: E402  (imports nothing from webforge)

disable_api_keys("sk-DISABLED-offline-run-must-not-call-any-api")

# WEBFORGE_REASONING_<NAME> overrides one model's reasoning effort for a paid
# measurement (webforge/core.py). Left set in a shell it would make the
# offline tests check an effort the table does not hold, so it is cleared
# here. The live suites do not import this file and still see it.
import os  # noqa: E402

for _var in [v for v in os.environ if v.startswith("WEBFORGE_REASONING_")]:
    del os.environ[_var]

# baseline/ and .claude/ are development material that is not published, so a
# fresh clone has neither. The files that read them are skipped there instead
# of failing at import; on the development machine they run as before.
REQUIRES_LOCAL_DEV = {
    "test_config.py": "baseline",
    "test_spec_base.py": "baseline",
    "test_paid_gate.py": ".claude/hooks/paid_gate.py",
}
collect_ignore = [name for name, needs in REQUIRES_LOCAL_DEV.items()
                  if not (ROOT / needs).exists()]
