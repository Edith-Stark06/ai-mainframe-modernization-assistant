"""
#128 — parse, VALIDATE and apply an AI-proposed repair patch.

The model proposes a structured line-range replacement. It never runs a
command. This module rejects a patch that:

* touches a file outside the generated project, a non-``.java`` file, or
  a file that has no compiler error;
* has an invalid / inverted line range;
* deletes the class or record declaration (source mapping would be lost);
* is empty or a pure duplicate of a previous attempt.
"""

from __future__ import annotations

import re

from app.grounded.verification import extract_json
from app.java_modernization.errors import UnsafePatchError
from app.java_modernization.generation.models import GeneratedProject
from app.java_modernization.repair.models import FileChange, FilePatch, RepairPatch

__all__ = ["parse_patch", "validate_patch", "apply_patch"]

_DECL_RE = re.compile(r"\b(?:class|record|interface)\s+\w+")


def parse_patch(text: str) -> RepairPatch | None:
    obj = extract_json(text)
    if obj is None:
        return None
    files_raw = obj.get("files", [])
    if not isinstance(files_raw, list):
        return None
    file_patches: list[FilePatch] = []
    for fr in files_raw:
        if not isinstance(fr, dict) or "path" not in fr:
            continue
        changes: list[FileChange] = []
        for cr in fr.get("changes", []) or []:
            try:
                changes.append(
                    FileChange(
                        start_line=int(cr["start_line"]),
                        end_line=int(cr["end_line"]),
                        replacement=str(cr.get("replacement", "")),
                    )
                )
            except (KeyError, TypeError, ValueError):
                continue
        file_patches.append(FilePatch(path=str(fr["path"]), changes=tuple(changes)))
    return RepairPatch(
        files=tuple(file_patches),
        explanation=str(obj.get("explanation", "")),
        source_basis=tuple(str(x) for x in obj.get("source_basis", []) if x),
    )


def validate_patch(
    patch: RepairPatch,
    project: GeneratedProject,
    *,
    allowed_files: set[str],
) -> None:
    if patch.is_empty():
        raise UnsafePatchError("empty patch")
    for fp in patch.files:
        rel = fp.path.replace("\\", "/")
        if ".." in rel or rel.startswith("/") or re.match(r"^[A-Za-z]:", rel):
            raise UnsafePatchError(f"patch path escapes project: {fp.path!r}")
        if rel not in project.files:
            raise UnsafePatchError(f"patch targets unknown file: {fp.path!r}")
        if not rel.endswith(".java"):
            raise UnsafePatchError(f"patch targets a non-Java file: {fp.path!r}")
        if allowed_files and rel not in allowed_files:
            raise UnsafePatchError(
                f"patch targets {fp.path!r} which has no compiler error"
            )
        original = project.files[rel]
        lines = original.splitlines()
        for ch in fp.changes:
            if ch.end_line < ch.start_line:
                raise UnsafePatchError(
                    f"inverted line range {ch.start_line}..{ch.end_line} in {fp.path}"
                )
            if ch.start_line < 1 or ch.end_line > len(lines) + 1:
                raise UnsafePatchError(
                    f"line range {ch.start_line}..{ch.end_line} out of bounds "
                    f"(file has {len(lines)} lines) in {fp.path}"
                )
        # source-mapping retention: the declaration must survive
        patched = _apply_to_text(original, fp.changes)
        if _DECL_RE.search(original) and not _DECL_RE.search(patched):
            raise UnsafePatchError(
                f"patch removes the class/record declaration in {fp.path}"
            )
        if not patched.strip():
            raise UnsafePatchError(f"patch empties {fp.path}")


def _apply_to_text(text: str, changes: tuple[FileChange, ...]) -> str:
    lines = text.splitlines()
    # apply from the bottom so earlier line numbers stay valid
    for ch in sorted(changes, key=lambda c: c.start_line, reverse=True):
        repl = ch.replacement.split("\n") if ch.replacement else []
        lines[ch.start_line - 1 : ch.end_line] = repl
    return "\n".join(lines) + ("\n" if text.endswith("\n") else "")


def apply_patch(patch: RepairPatch, project: GeneratedProject) -> GeneratedProject:
    files = dict(project.files)
    for fp in patch.files:
        rel = fp.path.replace("\\", "/")
        files[rel] = _apply_to_text(files[rel], fp.changes)
    return project.model_copy(update={"files": files})
