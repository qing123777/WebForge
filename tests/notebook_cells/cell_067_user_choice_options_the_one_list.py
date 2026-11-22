# Ported from fyp.ipynb cell 67 (ticket 05). The notebook is frozen;
# edit this file. Run by tests/test_notebook_cells.py.
# Unit tests: user_choice_options -- the one list three consumers read
# The Primary Orchestrator asks the user what they want, the preview panel shows
# the choices, and the documentation lists them. A hand-written copy of the
# values would be wrong the first time anyone added one to a Literal, so the list
# is derived from the schema and these cases prove it stays derived.
import typing

_uo = user_choice_options()
_uo_passed = 0


def _uo_ok(tid, desc):
    global _uo_passed
    _uo_passed += 1
    print(f"PASS  {tid:<5} {desc}")


assert set(_uo) == {"commerce_type", "style", "type"}, sorted(_uo)
_uo_ok("UO-1", "three choices offered, and no fourth appears by accident")

for _field, _literal in (("commerce_type", CommerceType), ("style", DesignStyle),
                         ("type", PageType)):
    _listed = [v["value"] for v in _uo[_field]["values"]]
    assert _listed == list(typing.get_args(_literal)), (
        f"UO-2 FAIL: {_field} offers {_listed} but the schema accepts "
        f"{list(typing.get_args(_literal))}. The list is meant to be DERIVED.")
_uo_ok("UO-2", "every offered value is exactly what the schema accepts, all three")

for _field, _spec in _uo.items():
    for _v in _spec["values"]:
        assert _v["help"].strip(), f"UO-3 FAIL: {_field}/{_v['value']} has no help text"
        assert _v["label"].strip(), f"UO-3 FAIL: {_field}/{_v['value']} has no label"
    assert _spec["default_when_unset"], f"UO-3 FAIL: {_field} has no stated default"
_uo_ok("UO-3", "every value carries a plain-English line and every field a default")

# A value added to a Literal but not to the help table must fail LOUDLY here
# rather than reaching the panel as a blank row.
try:
    USER_CHOICE_HELP["style"].pop("visual_first")
    user_choice_options()
except KeyError:
    pass
else:
    raise AssertionError("UO-4 FAIL: a value with no help text was rendered blank")
finally:
    USER_CHOICE_HELP["style"]["visual_first"] = (
        "Photography leads; the picture fills the card.")
_uo_ok("UO-4", "a value with no help text raises instead of showing a blank row")

assert [f["what"] for f in FIXED_BY_DESIGN] == [
    "Number of pages", "Technology", "Server", "Structural changes after generation",
    "Responsive design"]
for _f in FIXED_BY_DESIGN:
    assert _f["why"].strip(), f"UO-5 FAIL: '{_f['what']}' is fixed with no reason given"
_uo_ok("UO-5", "the five fixed limits each state why, so a refusal is never a surprise")

print("=" * 76)
print(f"user_choice_options: {_uo_passed}/5 PASSED")
print("=" * 76)
