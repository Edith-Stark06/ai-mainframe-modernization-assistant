"""
#126 — assemble a generated Java project from analysis + architecture.

The **translated logic** is the existing deterministic Java backend's
output (``AnalysisBundle.java_backend_output``) — Phase 9 does not
re-translate COBOL. This layer:

* lays the class out as a small project (``src/…``),
* adds a mechanical ``<Program>State`` record for the WORKING-STORAGE data,
* attaches per-class and per-method :class:`GeneratedJavaArtifact`
  traceability back to COBOL paragraphs / business rules (via #125),
* carries every :class:`UnsupportedBehavior` and assumption forward,
* records ``semantic_equivalence_verified = False``.

No line-by-line re-translation, no LLM.
"""

from __future__ import annotations

import hashlib
import re

from app.dataset.analysis_bundle import AnalysisBundle
from app.java_modernization.architecture.models import (
    JavaArchitecture,
    SourceRef,
)
from app.java_modernization.generation.models import (
    GeneratedJavaArtifact,
    GeneratedProject,
    MappingStatus,
)
from app.java_modernization.version import GENERATION_VERSION

__all__ = ["generate_project"]

_CLASS_RE = re.compile(r"^\s*(?:public\s+)?class\s+(\w+)", re.MULTILINE)
_METHOD_RE = re.compile(
    r"^[ \t]{2,}(?:public|private|protected)\s+(?:static\s+)?[\w<>\[\], ]+?\s+(\w+)\s*\("
    r"[^;{]*\)\s*\{",
    re.MULTILINE,
)


def _decamel(name: str) -> str:
    s = re.sub(r"(?<!^)(?=[A-Z])", "-", name)
    return s.upper()


def _java_type(t: str) -> str:
    return {"int": "long", "String": "String"}.get(t, t)


def generate_project(
    bundle: AnalysisBundle, architecture: JavaArchitecture
) -> GeneratedProject:
    sid = bundle.source_id
    main_src = bundle.java_backend_output or (
        f"public class {sid.title()} {{\n    public static void main(String[] a) {{}}\n}}\n"
    )
    m = _CLASS_RE.search(main_src)
    main_class = m.group(1) if m else f"{sid.title()}"
    main_path = f"src/{main_class}.java"

    files: dict[str, str] = {main_path: main_src}
    artifacts: list[GeneratedJavaArtifact] = []

    # -- class-level artifact ------------------------------------------
    top = next(
        (c for c in architecture.components if c.component_id.endswith("-main")), None
    )
    artifacts.append(
        GeneratedJavaArtifact(
            artifact_id=f"art-{sid}-class-{main_class.lower()}",
            file_path=main_path,
            class_name=main_class,
            kind="class",
            source_locations=top.source_refs if top else (),
            mapping_status=(
                MappingStatus.MAPPED
                if top and top.source_refs
                else MappingStatus.UNAVAILABLE
            ),
            architecture_component_id=top.component_id if top else None,
        )
    )

    # -- method-level artifacts (mapped to paragraphs via #125) --------
    comp_by_paragraph = {}
    for c in architecture.components:
        for r in c.source_refs:
            if r.paragraph:
                comp_by_paragraph[r.paragraph.upper()] = c
    for meth in _METHOD_RE.finditer(main_src):
        mname = meth.group(1)
        if mname == "main":
            continue
        para = _decamel(mname)
        comp = comp_by_paragraph.get(para)
        artifacts.append(
            GeneratedJavaArtifact(
                artifact_id=f"art-{sid}-m-{mname.lower()}",
                file_path=main_path,
                class_name=main_class,
                method_name=mname,
                kind="method",
                source_locations=(
                    comp.source_refs
                    if comp
                    else (SourceRef(source_id=sid, source_path=f"{sid}.cbl"),)
                ),
                mapping_status=(
                    MappingStatus.MAPPED if comp else MappingStatus.UNAVAILABLE
                ),
                architecture_component_id=comp.component_id if comp else None,
                business_rule_ids=comp.business_rule_ids if comp else (),
                unsupported_behaviors=tuple(
                    u
                    for u in architecture.unsupported_behaviors
                    if any(sr.paragraph == para for sr in u.source_refs)
                ),
            )
        )

    # -- mechanical data record ---------------------------------------
    if architecture.data_model:
        state_class = f"{main_class}State"
        state_path = f"src/{state_class}.java"
        fields = ",\n    ".join(
            f"{_java_type(d.java_type)} {d.name}" for d in architecture.data_model
        )
        files[state_path] = (
            f"/** Mechanical data holder for {sid} WORKING-STORAGE. "
            f"Generated candidate — semantic equivalence NOT verified. */\n"
            f"public record {state_class}(\n    {fields}\n) {{}}\n"
        )
        artifacts.append(
            GeneratedJavaArtifact(
                artifact_id=f"art-{sid}-record-{state_class.lower()}",
                file_path=state_path,
                class_name=state_class,
                kind="record",
                source_locations=(SourceRef(source_id=sid, source_path=f"{sid}.cbl"),),
                mapping_status=MappingStatus.MAPPED,
                architecture_component_id=next(
                    (
                        c.component_id
                        for c in architecture.components
                        if c.type.value == "DTO"
                    ),
                    None,
                ),
            )
        )

    diags = tuple(
        {"code": u.diagnostic_code or "", "message": u.explanation}
        for u in architecture.unsupported_behaviors
    )

    project = GeneratedProject(
        project_id=(
            f"proj-{sid}-"
            + hashlib.sha256(
                (architecture.architecture_id + GENERATION_VERSION).encode()
            ).hexdigest()[:12]
        ),
        generation_version=GENERATION_VERSION,
        source_id=sid,
        architecture_id=architecture.architecture_id,
        main_class=main_class,
        files=files,
        artifacts=tuple(artifacts),
        assumptions=tuple(a.statement for a in architecture.assumptions),
        unsupported_behaviors=architecture.unsupported_behaviors,
        generator_diagnostics=diags,
        semantic_equivalence_verified=False,
    )
    # embed the manifest (not compiled) so a checkout is self-describing
    import json

    files["MODERNIZATION_MANIFEST.json"] = (
        json.dumps(project.manifest(), indent=2, sort_keys=True) + "\n"
    )
    return project.model_copy(update={"files": files})
