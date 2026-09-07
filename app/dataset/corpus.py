"""
The Phase 6 controlled source corpus (#118).

Assembles :class:`SourceRecord` objects from:

* the repository's own MIT-licensed test fixtures (``repository_fixture``);
* synthetic programs written for Phase 6 (``synthetic``);
* the ``tests/golden/*.java`` pairs as reviewed / executable-verified
  ``cobol_to_java`` labels.

Provenance and licensing for every entry are documented in
``data/sources/phase6/SOURCES.md``. No external / unverified material is
included.
"""

from __future__ import annotations

from pathlib import Path

from app.dataset.builder import SourceRecord
from app.dataset.schema import Difficulty, Provenance

__all__ = ["REPO_ROOT", "load_phase6_corpus"]

REPO_ROOT = Path(__file__).resolve().parents[2]
_SYN_DIR = REPO_ROOT / "data" / "sources" / "phase6"

_MIT = "MIT"

# (source_id, repo-relative path, difficulty, golden-java repo-relative path or None)
_FIXTURES: tuple[tuple[str, str, Difficulty, str | None], ...] = (
    ("fx_hello_world", "tests/fixtures/hello_world.cbl", Difficulty.EASY, None),
    (
        "fx_move_display",
        "tests/golden/move_display.cbl",
        Difficulty.EASY,
        "tests/golden/move_display.java",
    ),
    (
        "fx_arithmetic",
        "tests/golden/arithmetic.cbl",
        Difficulty.EASY,
        "tests/golden/arithmetic.java",
    ),
    (
        "fx_if_else",
        "tests/golden/if_else.cbl",
        Difficulty.MEDIUM,
        "tests/golden/if_else.java",
    ),
    (
        "fx_call",
        "tests/golden/call.cbl",
        Difficulty.MEDIUM,
        "tests/golden/call.java",
    ),
    (
        "fx_perform_until",
        "tests/golden/perform_until.cbl",
        Difficulty.MEDIUM,
        "tests/golden/perform_until.java",
    ),
    (
        "fx_combined",
        "tests/golden/combined_program.cbl",
        Difficulty.DIFFICULT,
        "tests/golden/combined_program.java",
    ),
    (
        "fx_eligibility",
        "tests/fixtures/phase4/eligibility_rules.cbl",
        Difficulty.MEDIUM,
        None,
    ),
    (
        "fx_simple_proc",
        "tests/fixtures/phase5/simple_procedural.cbl",
        Difficulty.MEDIUM,
        None,
    ),
    (
        "fx_complex_proc",
        "tests/fixtures/phase5/complex_procedural.cbl",
        Difficulty.DIFFICULT,
        None,
    ),
    (
        "fx_highly_coupled",
        "tests/fixtures/phase5/highly_coupled.cbl",
        Difficulty.DIFFICULT,
        None,
    ),
    (
        "fx_file_processing",
        "tests/fixtures/phase5/file_processing.cbl",
        Difficulty.ADVERSARIAL,
        None,
    ),
    (
        "fx_unsupported",
        "tests/fixtures/phase5/unsupported_syntax.cbl",
        Difficulty.ADVERSARIAL,
        None,
    ),
    (
        "fx_incomplete",
        "tests/fixtures/phase5/incomplete_parsing.cbl",
        Difficulty.ADVERSARIAL,
        None,
    ),
    (
        "fx_acctbatch",
        "workspace/2e87036d-b90e-488f-b199-3162eb7c1c7e/complex_acctbatch.cbl",
        Difficulty.DIFFICULT,
        None,
    ),
)

# (source_id, filename under data/sources/phase6/, difficulty, note)
_SYNTHETIC: tuple[tuple[str, str, Difficulty, str], ...] = (
    (
        "syn_status_machine",
        "status_machine.cbl",
        Difficulty.MEDIUM,
        "status-transition rules",
    ),
    (
        "syn_misleading_names",
        "misleading_names.cbl",
        Difficulty.ADVERSARIAL,
        "identifier WS-FRAUD-SCORE is only a loop counter",
    ),
    (
        "syn_misleading_comments",
        "misleading_comments.cbl",
        Difficulty.ADVERSARIAL,
        "a comment claims a discount rule the code never applies",
    ),
    (
        "syn_ambiguous_question",
        "ambiguous_question.cbl",
        Difficulty.ADVERSARIAL,
        "used with a question that is not answerable from the source",
    ),
    (
        "syn_limit_check",
        "limit_check.cbl",
        Difficulty.MEDIUM,
        "numeric limit-check rule",
    ),
)

#: Golden Java files verified to compile with javac (tests/golden/ + the
#: Phase 3 review report).
_JAVA_COMPILES = frozenset(
    {
        "tests/golden/move_display.java",
        "tests/golden/arithmetic.java",
        "tests/golden/if_else.java",
        "tests/golden/call.java",
        "tests/golden/perform_until.java",
        "tests/golden/combined_program.java",
    }
)


def load_phase6_corpus() -> list[SourceRecord]:
    """Return every :class:`SourceRecord` in the Phase 6 corpus."""
    records: list[SourceRecord] = []

    for source_id, rel, difficulty, java_rel in _FIXTURES:
        path = REPO_ROOT / rel
        if not path.exists():
            continue
        reviewed_java = None
        java_compiles = None
        if java_rel:
            jpath = REPO_ROOT / java_rel
            if jpath.exists():
                reviewed_java = jpath.read_text(encoding="utf-8")
                java_compiles = java_rel in _JAVA_COMPILES
        records.append(
            SourceRecord(
                source_id=source_id,
                source=path.read_text(encoding="utf-8"),
                provenance=Provenance.REPOSITORY_FIXTURE,
                license=_MIT,
                difficulty=difficulty,
                reviewed_java=reviewed_java,
                java_compiles=java_compiles,
                notes=f"repository fixture: {rel}",
            )
        )

    for source_id, fname, difficulty, note in _SYNTHETIC:
        path = _SYN_DIR / fname
        if not path.exists():
            continue
        records.append(
            SourceRecord(
                source_id=source_id,
                source=path.read_text(encoding="utf-8"),
                provenance=Provenance.SYNTHETIC,
                license=_MIT,
                difficulty=difficulty,
                notes=f"synthetic (Phase 6): {note}",
            )
        )

    return sorted(records, key=lambda r: r.source_id)
