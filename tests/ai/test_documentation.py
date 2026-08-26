"""
Tests for COBOL Documentation Generation Engine.
"""

import pytest

from app.ai.documentation.models import Documentation, DocumentationSection
from app.ai.documentation.prompts import build_documentation_prompt
from app.ai.documentation.service import DocumentationGenerationService
from app.ai.providers.errors import LLMProviderUnavailableError
from app.ai.providers.fake import FakeLLMProvider


def test_build_documentation_prompt_basic() -> None:
    source = "       IDENTIFICATION DIVISION.\n       PROGRAM-ID. HELLO."
    prompt = build_documentation_prompt(source)

    assert "Please generate technical documentation" in prompt
    assert "=== COBOL SOURCE ===" in prompt
    assert "IDENTIFICATION DIVISION." in prompt
    assert "Title:" in prompt
    assert "Overview:" in prompt


def test_build_documentation_prompt_with_context() -> None:
    source = "       IDENTIFICATION DIVISION."
    context = {
        "program_id": "TESTPGM",
        "dependencies": {"COPY1", "COPY2"},
        "business_rules": ["Rule 1", "Rule 2"],
        "diagnostics": ["Warning 1"],
        "analysis_metadata": {"complexity": 10},
    }
    prompt = build_documentation_prompt(source, context)

    assert "Program Identifier: TESTPGM" in prompt
    assert "=== DEPENDENCIES ===" in prompt
    assert "- COPY1" in prompt
    assert "- COPY2" in prompt
    assert "=== BUSINESS RULES ===" in prompt
    assert "Rule 1" in prompt
    assert "=== DIAGNOSTICS ===" in prompt
    assert "Warning 1" in prompt
    assert "=== ANALYSIS METADATA ===" in prompt
    assert "complexity: 10" in prompt


def test_documentation_models_immutability() -> None:
    doc = Documentation(title="T", overview="O")
    with pytest.raises(Exception):  # Frozen instance
        doc.title = "New Title"  # type: ignore

    sec = DocumentationSection(heading="H", content="C")
    with pytest.raises(Exception):
        sec.heading = "New"  # type: ignore


def test_documentation_models_validation() -> None:
    with pytest.raises(ValueError, match="title cannot be empty"):
        Documentation(title=" ", overview="O")

    with pytest.raises(ValueError, match="overview cannot be empty"):
        Documentation(title="T", overview="")

    with pytest.raises(ValueError, match="heading cannot be empty"):
        DocumentationSection(heading="\n", content="C")

    with pytest.raises(ValueError, match="content cannot be empty"):
        DocumentationSection(heading="H", content="   ")


def test_service_generate_documentation_success() -> None:
    response_text = (
        "Title:\n"
        "My Program\n\n"
        "Overview:\n"
        "This program does something.\n\n"
        "Section:\n"
        "Data Division\n"
        "Contains data."
    )
    provider = FakeLLMProvider(response_text=response_text)
    service = DocumentationGenerationService(provider)

    doc = service.generate_documentation("       IDENTIFICATION DIVISION.")
    assert doc.title == "My Program"
    assert doc.overview == "This program does something."
    assert len(doc.sections) == 1
    assert doc.sections[0].heading == "Data Division"
    assert doc.sections[0].content == "Contains data."


def test_service_generate_documentation_empty_source() -> None:
    provider = FakeLLMProvider()
    service = DocumentationGenerationService(provider)

    with pytest.raises(ValueError, match="COBOL source cannot be empty"):
        service.generate_documentation("   ")


def test_service_generate_documentation_provider_failure() -> None:
    provider = FakeLLMProvider(simulate_failure=True)
    service = DocumentationGenerationService(provider)

    with pytest.raises(LLMProviderUnavailableError):
        service.generate_documentation("       IDENTIFICATION DIVISION.")


def test_service_generate_documentation_malformed_missing_title() -> None:
    response_text = "Overview:\nJust an overview."
    provider = FakeLLMProvider(response_text=response_text)
    service = DocumentationGenerationService(provider)

    with pytest.raises(
        ValueError, match="missing required 'Title:' or 'Overview:' sections"
    ):
        service.generate_documentation("       IDENTIFICATION DIVISION.")


def test_service_generate_documentation_malformed_missing_overview() -> None:
    response_text = "Title:\nJust a title."
    provider = FakeLLMProvider(response_text=response_text)
    service = DocumentationGenerationService(provider)

    with pytest.raises(
        ValueError, match="missing required 'Title:' or 'Overview:' sections"
    ):
        service.generate_documentation("       IDENTIFICATION DIVISION.")


def test_service_generate_documentation_malformed_empty_title() -> None:
    response_text = "Title:\n\nOverview:\nOverview text."
    provider = FakeLLMProvider(response_text=response_text)
    service = DocumentationGenerationService(provider)

    with pytest.raises(ValueError, match="Parsed title section is empty"):
        service.generate_documentation("       IDENTIFICATION DIVISION.")


def test_service_generate_documentation_malformed_empty_overview() -> None:
    response_text = "Title:\nTitle text\n\nOverview:\n   "
    provider = FakeLLMProvider(response_text=response_text)
    service = DocumentationGenerationService(provider)

    with pytest.raises(ValueError, match="Parsed overview section is empty"):
        service.generate_documentation("       IDENTIFICATION DIVISION.")


def test_service_generate_documentation_malformed_section_missing_content() -> None:
    response_text = (
        "Title:\nTitle text\n\n"
        "Overview:\nOverview text\n\n"
        "Section:\nJust A Heading"
    )
    provider = FakeLLMProvider(response_text=response_text)
    service = DocumentationGenerationService(provider)

    with pytest.raises(ValueError, match="Malformed section: missing content"):
        service.generate_documentation("       IDENTIFICATION DIVISION.")


def test_service_generate_documentation_empty_response() -> None:
    response_text = "   "
    provider = FakeLLMProvider(response_text=response_text)
    service = DocumentationGenerationService(provider)

    with pytest.raises(ValueError, match="empty or whitespace-only"):
        service.generate_documentation("       IDENTIFICATION DIVISION.")


def test_documentation_models_sections_immutability() -> None:
    doc = Documentation(
        title="T",
        overview="O",
        sections=(DocumentationSection(heading="H", content="C"),),
    )
    with pytest.raises(AttributeError):
        # Tuple has no attribute 'append'
        doc.sections.append(DocumentationSection(heading="H2", content="C2"))  # type: ignore

    # Verify construction with multiple sections still works
    doc2 = Documentation(
        title="T",
        overview="O",
        sections=(
            DocumentationSection(heading="H1", content="C1"),
            DocumentationSection(heading="H2", content="C2"),
        ),
    )
    assert len(doc2.sections) == 2


class DummyContextObject:
    def __init__(self, value: str):
        self.value = value


class DummyContextSlotsObject:
    __slots__ = ("value",)

    def __init__(self, value: str):
        self.value = value


def test_build_documentation_prompt_determinism_sets() -> None:
    source = "       IDENTIFICATION DIVISION."
    context1 = {"dependencies": {"A", "B", "C"}}
    context2 = {"dependencies": {"C", "A", "B"}}

    prompt1 = build_documentation_prompt(source, context1)
    prompt2 = build_documentation_prompt(source, context2)

    assert prompt1 == prompt2
    # Ensure they are sorted
    idx_a = prompt1.find("\n- A\n")
    idx_b = prompt1.find("\n- B\n")
    idx_c = prompt1.find("\n- C\n")
    assert idx_a < idx_b < idx_c


def test_build_documentation_prompt_determinism_dicts() -> None:
    source = "       IDENTIFICATION DIVISION."
    context1 = {"analysis_metadata": {"z": 1, "a": 2, "m": 3}}
    context2 = {"analysis_metadata": {"m": 3, "z": 1, "a": 2}}

    prompt1 = build_documentation_prompt(source, context1)
    prompt2 = build_documentation_prompt(source, context2)

    assert prompt1 == prompt2
    # Ensure they are sorted
    idx_a = prompt1.find("a: 2")
    idx_m = prompt1.find("m: 3")
    idx_z = prompt1.find("z: 1")
    assert idx_a < idx_m < idx_z


def test_build_documentation_prompt_determinism_objects() -> None:
    source = "       IDENTIFICATION DIVISION."
    obj1 = DummyContextObject("test1")
    obj2 = DummyContextSlotsObject("test2")

    context = {"business_rules": [obj1, obj2]}

    prompt = build_documentation_prompt(source, context)

    # Should not contain memory address (e.g. '0x...') for default repr
    assert "0x" not in prompt
    assert "{value: test1}" in prompt
    assert "{value: test2}" in prompt


def test_build_documentation_prompt_no_mutation() -> None:
    source = "       IDENTIFICATION DIVISION."
    deps = ["B", "A", "C"]
    context = {"dependencies": deps}

    build_documentation_prompt(source, context)

    # The original list should remain unmodified
    assert deps == ["B", "A", "C"]
