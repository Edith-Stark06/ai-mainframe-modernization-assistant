"""Phase 11 fixtures — deterministic, no live LLM, no COBOL runtime required."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from app.dataset.analysis_bundle import build_analysis_bundle
from app.java_modernization.architecture import build_architecture
from app.java_modernization.generation import generate_project

ELIG = Path("tests/fixtures/phase4/eligibility_rules.cbl")
IF_ELSE = Path("tests/golden/if_else.cbl")


def _bundle(sid: str, path: Path):
    return build_analysis_bundle(
        sid, path.read_text(encoding="utf-8"), tempfile.mkdtemp()
    )


@pytest.fixture(scope="session")
def if_else_bundle():
    return _bundle("IFELSE", IF_ELSE)


@pytest.fixture(scope="session")
def if_else_architecture(if_else_bundle):
    return build_architecture(if_else_bundle)


@pytest.fixture(scope="session")
def if_else_project(if_else_bundle, if_else_architecture):
    return generate_project(if_else_bundle, if_else_architecture)


@pytest.fixture(scope="session")
def elig_bundle():
    return _bundle("ELIGIBILITY", ELIG)


@pytest.fixture(scope="session")
def elig_architecture(elig_bundle):
    return build_architecture(elig_bundle)


@pytest.fixture(scope="session")
def elig_project(elig_bundle, elig_architecture):
    return generate_project(elig_bundle, elig_architecture)


#: task #stage36: eligibility_rules.cbl's Java output *before* that stage
#: (captured directly from the real, unmodified pipeline via the same
#: `_local_perform_targets` monkeypatch the Stage 36 investigation's own
#: corpus verification used to reproduce pre-stage behavior exactly — see
#: the Stage 36 final report). Every one of the three PERFORM'd paragraphs
#: is a `BE009` stub; nothing else about the bundle (business rules, AST,
#: dependencies — all derived from the AST, never from Java generation)
#: changes. Frozen here, rather than re-derived from a live fixture, on
#: purpose: test_6 below needs a bundle where *every* extractable
#: behavioral rule is genuinely unsupported, and no current real fixture
#: reproduces that any more (task #stage36 correctly outlines a real
#: PERFORM target's body whenever one exists) — the one way this bundle
#: could still occur (a PERFORM to a paragraph whose own body is entirely
#: unsupported statements, e.g. READ/INITIALIZE) is exercised elsewhere,
#: not duplicated here.
_ELIG_JAVA_ALL_STUBS = """public class Eligibility {

    private int wsAge = 0;
    private String wsStatus = "";
    private String wsResult = "";
    private int wsAmount = 0;
    private int wsFee = 0;
    private int wsTotal = 0;
    private String wsReview = "";
    private String wsErrorFlag = "";

    public static void main(String[] args) {
        new Eligibility().run();
    }

    public void run() {

        checkEligibility();
        calculateTotal();
        reviewAmount();
        return;

    }

    private void checkEligibility() {
        // TODO: implement CALL/PERFORM target 'CHECK-ELIGIBILITY' (BE009).
    }

    private void calculateTotal() {
        // TODO: implement CALL/PERFORM target 'CALCULATE-TOTAL' (BE009).
    }

    private void reviewAmount() {
        // TODO: implement CALL/PERFORM target 'REVIEW-AMOUNT' (BE009).
    }

}
"""


@pytest.fixture(scope="session")
def elig_bundle_all_stubs(elig_bundle):
    """``elig_bundle`` with its Java generation frozen at the pre-
    #stage36 all-stubs state (task #stage36) — see
    ``_ELIG_JAVA_ALL_STUBS``'s own docstring for why."""
    import dataclasses

    return dataclasses.replace(elig_bundle, java_backend_output=_ELIG_JAVA_ALL_STUBS)


@pytest.fixture(scope="session")
def elig_architecture_all_stubs(elig_bundle_all_stubs):
    return build_architecture(elig_bundle_all_stubs)


@pytest.fixture(scope="session")
def elig_project_all_stubs(elig_bundle_all_stubs, elig_architecture_all_stubs):
    return generate_project(elig_bundle_all_stubs, elig_architecture_all_stubs)
