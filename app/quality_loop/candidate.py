"""
Candidate versioning helpers (Phase 11).

Every candidate has an immutable identity built from content hashes —
never a random UUID — so two candidates with identical inputs always
get the identical id, and a repair always produces a *new* version
rather than overwriting the one it started from.
"""

from __future__ import annotations

import hashlib

from app.dataset.analysis_bundle import AnalysisBundle
from app.behavioral.extraction.models import BehavioralSuite
from app.java_modernization.architecture.models import JavaArchitecture
from app.java_modernization.generation.models import GeneratedProject
from app.quality_loop.models import CandidateVersion, build_candidate_id

__all__ = ["first_candidate", "next_candidate"]


def _source_hash(source: str) -> str:
    return hashlib.sha256(source.encode("utf-8")).hexdigest()[:16]


def first_candidate(
    *,
    bundle: AnalysisBundle,
    architecture: JavaArchitecture,
    project: GeneratedProject,
    test_suite: BehavioralSuite,
) -> CandidateVersion:
    source_hash = _source_hash(bundle.source)
    architecture_hash = architecture.content_hash()
    generated_project_hash = project.content_hash()
    test_set_hash = test_suite.content_hash()
    candidate_id = build_candidate_id(
        source_hash=source_hash,
        architecture_hash=architecture_hash,
        generated_project_hash=generated_project_hash,
        test_set_hash=test_set_hash,
        version=1,
    )
    return CandidateVersion(
        candidate_id=candidate_id,
        version=1,
        architecture_hash=architecture_hash,
        source_hash=source_hash,
        generated_project_hash=generated_project_hash,
        test_set_hash=test_set_hash,
        parent_candidate_id=None,
        created_from_repair=False,
    )


def next_candidate(
    previous: CandidateVersion,
    *,
    project: GeneratedProject,
    test_suite: BehavioralSuite | None = None,
) -> CandidateVersion:
    """A repair always yields a NEW candidate version -- never an
    overwrite of ``previous``."""
    generated_project_hash = project.content_hash()
    test_set_hash = test_suite.content_hash() if test_suite else previous.test_set_hash
    version = previous.version + 1
    candidate_id = build_candidate_id(
        source_hash=previous.source_hash,
        architecture_hash=previous.architecture_hash,
        generated_project_hash=generated_project_hash,
        test_set_hash=test_set_hash,
        version=version,
    )
    return CandidateVersion(
        candidate_id=candidate_id,
        version=version,
        architecture_hash=previous.architecture_hash,
        source_hash=previous.source_hash,
        generated_project_hash=generated_project_hash,
        test_set_hash=test_set_hash,
        parent_candidate_id=previous.candidate_id,
        created_from_repair=True,
    )
