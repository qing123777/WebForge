# Ported from fyp.ipynb cell 124 (ticket 05). The notebook is frozen;
# edit this file. Run by tests/test_notebook_cells.py.
# Unit tests: OverwritingFilesystemBackend (FilesystemMiddleware backend)
#
# This backend is the storage half of the HTML agent's FilesystemMiddleware.
# It exists to lift one guard: the parent refuses to write to a path that
# already exists, which silently broke Modification Mode (the agent reported
# success while the file on disk never changed). Case 3 re-runs the same
# overwrite against the UNPATCHED parent to prove the override is load-bearing.
#
# Everything runs in a throwaway temp directory - the real static/preview tree
# is never touched.
import shutil
import tempfile
from pathlib import Path

_tmp_root = Path(tempfile.mkdtemp(prefix="wf_backend_test_"))
try:
    _be = OverwritingFilesystemBackend(root_dir=str(_tmp_root), virtual_mode=True)

    # Case 1 [NORMAL] a brand-new file is created (generation mode)
    _r = _be.write("preview_s1.html", "<html>v1</html>")
    print("[Case 1 - NORMAL] writing a new path creates the file (generation mode)")
    print("  write error:", _r.error)
    assert _r.error is None, f"FAIL: fresh write rejected: {_r.error}"
    assert (_tmp_root / "preview_s1.html").read_text(encoding="utf-8") == "<html>v1</html>"
    print("PASS: file created with the expected content\n")

    # Case 2 [NORMAL] an existing file is replaced (modification mode - the fix)
    _r = _be.write("preview_s1.html", "<html>v2</html>")
    _on_disk = (_tmp_root / "preview_s1.html").read_text(encoding="utf-8")
    print("[Case 2 - NORMAL] writing an existing path replaces it (modification mode)")
    print("  write error:", _r.error, "| on disk:", _on_disk)
    assert _r.error is None, f"FAIL: overwrite refused: {_r.error}"
    assert _on_disk == "<html>v2</html>", "FAIL: disk still holds the old revision"
    print("PASS: revised artifact persisted over the original\n")

    # Case 3 [INVARIANT] the parent still refuses, so Case 2 proves the override
    # is doing the work rather than the parent having changed upstream.
    _parent = FilesystemBackend(root_dir=str(_tmp_root), virtual_mode=True)
    _r_parent = _parent.write("preview_s1.html", "<html>v3</html>")
    print("[Case 3 - INVARIANT] the unpatched parent still refuses the same overwrite")
    print("  parent error:", _r_parent.error)
    # Ticket 05: a newer deepagents (0.7.34 on the Linux cloud checkout) lets
    # the parent overwrite. That says the subclass may be obsolete; it does not
    # say the system is broken, so it is a loud pytest warning, not a failure,
    # and Cases 4-6 still run. requirements.txt does not pin deepagents.
    if _r_parent.error is None:
        import warnings
        warnings.warn(
            "deepagents' FilesystemBackend now allows overwrites - "
            "OverwritingFilesystemBackend may be obsolete, recheck before deleting it")
    else:
        assert _r_parent.error is not None, (
            "FAIL: the parent now allows overwrites - this subclass may be obsolete, "
            "recheck before deleting it")
        assert "already exists" in _r_parent.error
        assert (_tmp_root / "preview_s1.html").read_text(encoding="utf-8") == "<html>v2</html>"
        print("PASS: override is load-bearing; parent left the file untouched\n")

    # Case 4 [EDGE] shrinking rewrite leaves no tail of the previous revision.
    # A modification that deletes markup must not leave orphaned bytes behind.
    _be.write("preview_s2.html", "<html>" + "x" * 500 + "</html>")
    _be.write("preview_s2.html", "<p>short</p>")
    _shrunk = (_tmp_root / "preview_s2.html").read_text(encoding="utf-8")
    print("[Case 4 - EDGE] a much shorter rewrite leaves no residue of the old file")
    print(f"  500+ chars -> {len(_shrunk)} chars: {_shrunk!r}")
    assert _shrunk == "<p>short</p>", f"FAIL: residual content on disk: {_shrunk[:80]!r}"
    print("PASS: file truncated, not partially patched\n")

    # Case 5 [NORMAL] nested parent directories are still created by the parent
    _r = _be.write("nested/deep/preview_s3.css", "body{}")
    print("[Case 5 - NORMAL] inherited parent-directory creation still works")
    print("  write error:", _r.error)
    assert _r.error is None, f"FAIL: {_r.error}"
    assert (_tmp_root / "nested" / "deep" / "preview_s3.css").exists()
    print("PASS: missing parent directories created by the inherited write path\n")

    # Case 6 [GUARD] containment survives the override. The override resolves
    # the path through the same inherited _resolve_path, so an escape attempt is
    # rejected BEFORE anything is unlinked.
    #
    # The asserted property is CONTAINMENT, not rejection. Upstream's resolver
    # also has a "~" branch, but in virtual_mode it is unreachable: the key is
    # prefixed with "/" first, so "~/x" becomes "/~/x" and never starts with
    # "~". It lands literally inside the root under a directory named "~" -
    # contained, therefore harmless. Asserting "all three raise" would bake that
    # upstream quirk into our suite and break on any deepagents release that
    # fixes it.
    _blocked, _contained = [], []
    for _evil in ("../escape.html", "~/escape.html", "a/../../escape.html"):
        try:
            _be.write(_evil, "pwned")
            _contained.append((_evil, _be._resolve_path(_evil)))
        except ValueError:
            _blocked.append(_evil)
    print("[Case 6 - GUARD] no write escapes the root directory")
    print("  rejected outright:", _blocked)
    for _evil, _where in _contained:
        print(f"  contained:  {_evil} -> inside root: {_where.is_relative_to(_tmp_root)}")
    assert "../escape.html" in _blocked and "a/../../escape.html" in _blocked, (
        f"FAIL: traversal not rejected, only {_blocked} were blocked")
    for _evil, _where in _contained:
        assert _where.is_relative_to(_tmp_root), f"FAIL: {_evil} escaped to {_where}"
    assert not (_tmp_root.parent / "escape.html").exists(), "FAIL: wrote outside the root"
    print("PASS: traversal rejected, every accepted write landed inside the root\n")

    # Case 7 [INVARIANT] deleting-then-writing must not destroy the old file when
    # the new write fails. A directory at the target path makes write fail, and
    # the unlink guard (is_file) must leave it in place rather than removing it.
    _dir_path = _tmp_root / "a_directory.html"
    _dir_path.mkdir()
    _r = _be.write("a_directory.html", "should not land")
    print("[Case 7 - INVARIANT] a directory at the target is not unlinked")
    print("  write error:", (_r.error or "")[:70])
    assert _r.error is not None, "FAIL: expected the write to fail against a directory"
    assert _dir_path.is_dir(), "FAIL: the override removed a directory"
    print("PASS: only regular files are replaced; the directory survived\n")

    print("All 7 cases passed - OverwritingFilesystemBackend.")
finally:
    shutil.rmtree(_tmp_root, ignore_errors=True)
